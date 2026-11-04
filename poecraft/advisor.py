"""Советчик: смотрит на предмет и цель, предлагает следующий шаг с шансами."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .data import GameData, ModDef
from .parser import ParsedItem
from .pool import ModPool, PoolEntry

CURRENCY_RU = {
    "CurrencyUpgradeToMagic": "Orb of Transmutation",
    "CurrencyUpgradeToRare": "Orb of Alchemy",
    "CurrencyRerollRare": "Chaos Orb",
    "CurrencyAddModToRare": "Exalted Orb",
    "CurrencyRerollMagic": "Orb of Alteration",
    "CurrencyAddModToMagic": "Orb of Augmentation",
    "CurrencyUpgradeMagicToRare": "Regal Orb",
    "CurrencyModValues": "Divine Orb",
    "CurrencyConvertToNormal": "Orb of Scouring",
    "CurrencyRemoveMod": "Orb of Annulment",
    "CurrencyRerollSocketNumbers": "Jeweller's Orb",
    "CurrencyRerollSocketColours": "Chromatic Orb",
    "CurrencyRerollSocketLinks": "Orb of Fusing",
    "CurrencyVaal": "Vaal Orb",
    "CurrencyUpgradeToRareAndSetSockets": "Orb of Alchemy",
}


def _max_value(bench_opt: dict) -> float:
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", bench_opt["text"])]
    return max(nums, default=0)


ESTIMATE_NOTE = "Это оценка симуляцией: точное соотношение «1 мод / 2 мода» у синих предметов игра не раскрывает."

# ----------------------------------------------------------------- цели
@dataclass
class Want:
    label: str
    pattern: str = ""
    max_tier: int = 99
    mod_type: str = ""      # точное совпадение с type мода из RePoE (надёжнее regex)
    kind: str = ""          # prefix / suffix / "" — любой

    def matches_text(self, text: str) -> bool:
        return bool(self.pattern) and re.search(self.pattern, text, re.I) is not None

    def matches_bench(self, b: dict) -> bool:
        """Подходит ли крафт верстака (по типу мода, если он задан, иначе по тексту)."""
        if self.mod_type:
            return b.get("type") == self.mod_type and (not self.kind or b.get("kind") == self.kind)
        return self.matches_text(b.get("text", ""))

    def matches(self, e: PoolEntry) -> bool:
        if e.tier > self.max_tier:
            return False
        if self.kind and e.mod.kind != self.kind:
            return False
        if self.mod_type:
            return e.mod.type == self.mod_type
        return self.matches_text(e.mod.text)


def text_pattern(mod_text: str) -> str:
    """Регулярка по тексту мода без чисел: '+(130-144) to maximum Life' → 'to maximum Life$'."""
    first = mod_text.split("\n")[0]
    core = re.sub(r"^[+\-]?\(?[\d.]+(?:-[\d.]+)?\)?%?\s*", "", first).strip()
    return re.escape(core) + "$"


@dataclass
class Goal:
    name: str
    wanted: list[Want]
    base_class: str | None = None  # "Belt", "Ring"… (как в RePoE)
    raw: dict = field(default_factory=dict)  # исходный крафт — для «Поделиться»

    @classmethod
    def from_dict(cls, d: dict) -> "Goal":
        from .recipes import recipe_from_dict
        r = recipe_from_dict(d)
        wanted = [Want(w["label"], w["pattern"], w["max_tier"], w["mod_type"], w["kind"]) for w in r["wanted"]]
        return cls(r["name"], wanted, r["base_class"], r)

    @classmethod
    def load(cls, path: str | Path) -> "Goal":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


# ----------------------------------------------------------------- результат
@dataclass
class Advice:
    step: str
    why: str
    chance: float | None = None   # шанс успеха одного применения
    notes: list[str] = field(default_factory=list)

    def render(self) -> str:
        s = f"Следующий шаг: {self.step}\nПочему: {self.why}"
        if self.chance is not None:
            if self.chance > 0:
                s += f"\nШанс за одну попытку: {self.chance:.1%}"
                if self.chance < 1:
                    s += f" (в среднем попыток: ~{max(1, round(1 / self.chance))})"
            else:
                s += "\nШанс: 0% — этим способом нужный мод не получить."
        for n in self.notes:
            s += f"\n• {n}"
        return s


@dataclass
class ItemState:
    """Предмет, связанный с базой модов."""
    parsed: ParsedItem
    pool: ModPool
    entries: list[PoolEntry | None]   # по одному на каждый мод предмета (None — не нашли, напр. крафт)

    @property
    def mod_defs(self) -> list[ModDef]:
        out = []
        for pm, e in zip(self.parsed.mods, self.entries):
            if e:
                out.append(e.mod)
            else:  # неизвестный мод (крафт верстака и т.п.) всё равно занимает слот
                out.append(ModDef(f"unknown:{pm.name}", pm.name, pm.kind, "", (), 1, pm.text, (), (), ()))
        return out


class Advisor:
    def __init__(self, data: GameData):
        self.data = data

    # --- связываем распарсенный предмет с игровыми данными
    def resolve(self, item: ParsedItem) -> ItemState:
        base = self.data.find_base_any(item.base_name)
        if base is None:
            raise ValueError(f"Не нашёл базу предмета «{item.base_name}» в данных RePoE.")
        extra = None
        if item.influences:
            from .influence import influence_tags
            tags = influence_tags(self.data, base.item_class)
            extra = {tags[i] for i in item.influences if i in tags} or None
        pool = ModPool(self.data, base, item.ilvl or 100, extra)
        entries = [None if pm.crafted else self._match_mod(pool, pm) for pm in item.mods]
        return ItemState(item, pool, entries)

    def _match_mod(self, pool: ModPool, pm) -> PoolEntry | None:
        """Ищем мод: по английскому имени, по русскому имени (все формы рода), по тексту с диапазоном."""
        from .parser import canonical
        e = pool.find(pm.name, pm.kind)
        if e:
            return e
        want = [canonical(l) for l in pm.lines]
        ru = self.data.ru_mods
        by_text, by_name = [], []
        for e in pool.all:
            if e.mod.kind != pm.kind:
                continue
            texts = [e.mod.text]
            if e.mod.id in ru:
                texts.append(ru[e.mod.id][0])
                if pm.name in ru[e.mod.id][1]:
                    by_name.append(e)
            for tx in texts:
                lines = [canonical(x) for x in tx.split("\n")]
                if want and lines[:len(want)] == want:
                    by_text.append(e)
                    break
        if by_text:
            # если и имя совпало — берём пересечение (это точный тир)
            both = [e for e in by_text if e in by_name]
            return (both or by_text)[0]
        return by_name[0] if len(by_name) == 1 else None

    def advise(self, item: ParsedItem, goal: Goal) -> tuple[ItemState | None, Advice]:
        if item.corrupted:
            return None, Advice("Стоп", "Предмет осквернён — валютой его уже не изменить.")
        if item.mirrored:
            return None, Advice("Стоп", "Предмет — зеркальная копия, менять нельзя.")
        st = self.resolve(item)
        if goal.base_class and st.pool.base.item_class != goal.base_class:
            return st, Advice("Стоп", f"Цель для «{goal.base_class}», а это «{st.pool.base.item_class}».")
        return st, self._advise(st, goal)

    # --- основная логика
    def _advise(self, st: ItemState, goal: Goal) -> Advice:
        item, pool = st.parsed, st.pool
        good, bad = [], []
        for pm, e in zip(item.mods, st.entries):
            w = next((w for w in goal.wanted if (e and w.matches(e)) or (not e and w.matches_text(pm.text))), None)
            (good if w else bad).append((pm, e, w))
        have = {id(w) for *_, w in good}
        missing = [w for w in goal.wanted if id(w) not in have]
        want_missing = lambda e: any(w.matches(e) for w in missing)

        # Проверка: может ли нужный мод вообще выпасть на этой базе/ilvl
        impossible = [w for w in missing if not any(w.matches(e) for e in pool.available)]
        notes = []
        if impossible:
            notes.append("Не выпадает на этой базе/ilvl: " + ", ".join(
                f"{w.label} (тир ≤{w.max_tier})" for w in impossible))

        if not missing:
            return Advice("Готово", "Все нужные моды на месте. Дальше — Divine на значения или продажа.", notes=notes)

        if item.rarity == "Normal":
            p = pool.chance_reroll("Magic", lambda r: any(want_missing(e) for e in r))
            return Advice("Orb of Transmutation, потом Alteration",
                          "Белый предмет: делаем синим и роллим альтами.", p, notes + [ESTIMATE_NOTE])

        if item.rarity == "Magic":
            p_alt = pool.chance_reroll("Magic", lambda r: any(want_missing(e) for e in r))
            if not good:
                return Advice("Orb of Alteration", "Нужных модов нет — перероллить.", p_alt, notes + [ESTIMATE_NOTE])
            present = st.mod_defs
            if len(item.mods) == 1:
                p = pool.chance_add(present, "Magic", want_missing)
                return Advice("Orb of Augmentation",
                              f"Есть «{good[0][2].label}», свободен второй слот — аугаем.", p, notes)
            if bad:
                labels = [w.label for w in goal.wanted]
                p2 = pool.chance_reroll("Magic", lambda r: sum(any(w.matches(e) for w in goal.wanted) for e in r) >= 2)
                return Advice("Orb of Alteration",
                              f"Один мод нужный, второй мусорный. Шанс сразу словить два нужных за альт: {p2:.2%}.",
                              p_alt, notes + ["Можно и Regal: оставить мусор и надеяться на крафт верстаком позже.", ESTIMATE_NOTE])
            p = pool.chance_add(present, "Rare", want_missing)
            return Advice("Regal Orb", "Оба мода нужные — делаем редким, получим третий мод.", p, notes)

        if item.rarity == "Rare":
            return self._advise_rare(st, goal, good, bad, missing, want_missing, notes)

        return Advice("?", f"Редкость «{item.rarity}» пока не поддерживается.", notes=notes)

    def _advise_rare(self, st, goal, good, bad, missing, want_missing, notes) -> Advice:
        item, pool = st.parsed, st.pool
        present = st.mod_defs
        max_p, max_s = pool.limits("Rare")
        open_p = max_p - len(item.prefixes)
        open_s = max_s - len(item.suffixes)
        has_crafted = any(pm.crafted for pm in item.mods)

        # 1) Один мод остался и его можно сделать верстаком
        if len(missing) == 1 and not has_crafted:
            w = missing[0]
            taken = {g for m in present for g in m.groups}
            for b in self.data.bench:
                if pool.base.item_class not in b["item_classes"] or not w.matches_bench(b):
                    continue
                if taken.intersection(b["groups"]):
                    continue
                if (b["kind"] == "prefix" and open_p) or (b["kind"] == "suffix" and open_s):
                    cost = ", ".join(f"{v}× {CURRENCY_RU.get(k, k)}" for k, v in b["cost"].items())
                    best = [x for x in self.data.bench if pool.base.item_class in x["item_classes"]
                            and x["groups"] == b["groups"] and w.matches_bench(x)]
                    top = max(best, key=_max_value)
                    return Advice("Крафт на верстаке",
                                  f"Остался только «{w.label}», слот свободен. Верстак: {top['text']} "
                                  f"(цена {', '.join(f'{v}× {CURRENCY_RU.get(k, k)}' for k, v in top['cost'].items())}).",
                                  1.0, notes + ["Значение у верстака ниже, чем у топ-тиров. Если нужен высокий тир — сначала Exalt."])

        # 2) Есть свободные слоты под недостающее — Exalt
        need_p = any(any(w.matches(e) and e.mod.kind == "prefix" for e in pool.available) for w in missing)
        need_s = any(any(w.matches(e) and e.mod.kind == "suffix" for e in pool.available) for w in missing)
        if (need_p and open_p) or (need_s and open_s):
            p = pool.chance_add(present, "Rare", want_missing)
            extra = []
            if has_crafted:
                extra.append("Сначала сними крафт верстака, если он занимает нужный тип слота.")
            if open_p and not need_p or open_s and not need_s:
                extra.append("Заблокируй ненужный тип слота крафтом «Prefixes/Suffixes Cannot Be Changed» "
                             "или любым модом верстака — шанс Exalt'а вырастет.")
                blocked = list(present)
                if open_p and not need_p:
                    blocked += [ModDef("block", "block", "prefix", "", (), 1, "", (), (), ())] * open_p
                if open_s and not need_s:
                    blocked += [ModDef("block", "block", "suffix", "", (), 1, "", (), (), ())] * open_s
                p_blocked = pool.chance_add(blocked, "Rare", want_missing)
                extra.append(f"С блоком шанс: {p_blocked:.1%} вместо {p:.1%}.")
            return Advice("Exalted Orb",
                          "Не хватает: " + ", ".join(w.label for w in missing) + ". Есть свободный слот.",
                          p, notes + extra)

        # 3) Слоты забиты мусором, но нужного уже много — Annul
        removable = [x for x in good + bad if not x[0].fractured]
        bad_removable = [x for x in bad if not x[0].fractured]
        if bad_removable and len(good) >= 2:
            p = len(bad_removable) / len(removable)
            return Advice("Orb of Annulment (риск)",
                          "Слоты заняты мусором: " + ", ".join(pm.name for pm, *_ in bad_removable)
                          + ". Анулл снимет случайный мод — может снести и нужный.",
                          p, notes + ["Потом — Exalt или верстак на освободившееся место."])

        # 4) Иначе — перекрафт целиком
        p = pool.chance_reroll("Rare", lambda r: all(any(w.matches(e) for e in r) for w in goal.wanted))
        return Advice("Chaos Orb (или Scouring → заново)",
                      "Нужного мало, а свободных слотов нет. Шанс получить все нужные моды Chaos'ом:",
                      p, notes + ["Если шанс крошечный — дешевле начать с белой базы через Alt→Regal."])
