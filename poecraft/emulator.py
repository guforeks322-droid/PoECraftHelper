"""Эмулятор крафта: виртуальный предмет и применение валюты по правилам PoE 1."""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

from .data import GameData, ModDef
from .pool import MAGIC_MOD_COUNT, RARE_MOD_COUNT, ModPool, PoolEntry
from . import currency_craft as cc
from . import influence as inf

RANGE_RE = re.compile(r"\((-?[\d.]+)-(-?[\d.]+)\)")
VALUE_IN_LINE = re.compile(r"(-?\d+(?:\.\d+)?)\(-?[\d.]+-(?:-?[\d.]+)\)")   # «+140(130-144)» → 140

META = {
    "prefix_lock": ("ItemGenerationCannotChangePrefixes", "Prefixes Cannot Be Changed"),
    "suffix_lock": ("ItemGenerationCannotChangeSuffixes", "Suffixes Cannot Be Changed"),
    "no_attack": ("ItemGenerationCannotRollAttackAffixes", "Cannot roll Attack Modifiers"),
    "no_caster": ("ItemGenerationCannotRollCasterAffixes", "Cannot roll Caster Modifiers"),
    "multi_craft": ("ItemGenerationCanHaveMultipleCraftedMods", "Can have up to 3 Crafted Modifiers"),
}


class CraftError(Exception):
    pass


@dataclass
class ItemMod:
    entry: PoolEntry
    crafted: bool = False
    fractured: bool = False
    values: list = field(default_factory=list)
    veiled: bool = False

    @property
    def mod(self) -> ModDef:
        return self.entry.mod

    @property
    def kind(self) -> str:
        return self.mod.kind

    def roll_values(self, rng):
        self.values = []
        for lo, hi in RANGE_RE.findall(self.mod.text):
            lo, hi = float(lo), float(hi)
            if lo.is_integer() and hi.is_integer():
                self.values.append(rng.randint(int(min(lo, hi)), int(max(lo, hi))))
            else:
                self.values.append(round(rng.uniform(min(lo, hi), max(lo, hi)), 1))

    @property
    def text(self) -> str:
        it = iter(self.values)
        def sub(m):
            try:
                v = next(it)
                return str(v)
            except StopIteration:
                return m.group(0)
        return RANGE_RE.sub(sub, self.mod.text).replace("\n", " / ")

    @property
    def meta(self) -> str | None:
        for key, (group, _) in META.items():
            if group in self.mod.groups:
                return key
        return None


def sanctified_pool(pool: ModPool) -> ModPool:
    """Sanctified Fossil: моды высокого уровня выпадают чаще (приближение: вес × уровень мода / 40)."""
    import copy as _c
    fp = _c.copy(pool)
    fp.available = [PoolEntry(e.mod, max(1, int(e.weight * max(0.25, e.mod.level / 40))), e.tier)
                    for e in pool.available]
    return fp


def corrupt_essence_mods(data: GameData, pool: ModPool) -> list[PoolEntry]:
    """Моды «осквернённых» эссенций (Hysteria, Insanity, Horror, Delirium) для этого класса."""
    out = []
    for e in cc.essences_for(data, pool.base.item_class):
        if any(k in e.name for k in ("Hysteria", "Insanity", "Horror", "Delirium")):
            out.append(PoolEntry(e.mod, 1, 1))
    return out


class Emulator:
    def __init__(self, data: GameData, pool: ModPool, seed: int | None = None, influences: list | None = None):
        self.data = data
        self.base_pool = pool                      # пул без влияний (база/ilvl)
        self.inf_tags = inf.influence_tags(data, pool.base.item_class)
        self.influences: list[str] = [i for i in (influences or []) if i in self.inf_tags]
        self.exarch: inf.EldritchMod | None = None
        self.eater: inf.EldritchMod | None = None
        self.pool = self._make_pool()
        self.rng = random.Random(seed)
        self.rarity = "Normal"
        self.mods: list[ItemMod] = []
        self.spent: dict[str, int] = {}
        self.history: list[tuple] = []
        self.log: list[str] = []
        self._bench = None
        # состояние, которое тоже откатывается: осквернение, сплит, катализатор, отпечаток, Hinekora
        self.state = {"corrupted": False, "split": False, "catalyst": None, "quality": 0, "imprint": None,
                      "lock": False, "notes": []}
        self.blocked: set = set()          # (kind, type), заблокированные правым кликом в пуле (как на CoE)

    def _make_pool(self) -> ModPool:
        pool = self.base_pool
        if self.influences:
            extra = {self.inf_tags[i] for i in self.influences}
            pool = ModPool(self.data, self.base_pool.base, self.base_pool.ilvl, extra)
        cat = getattr(self, "state", {}).get("catalyst")
        if cat:
            from .sockets import apply_catalyst
            pool = apply_catalyst(pool, cat, self.state.get("quality", 0))
        return pool

    # ------------------------------------------------------------ состояние
    def snapshot(self):
        st = dict(self.state)
        st["notes"] = list(st.get("notes", []))
        return (self.rarity, [ItemMod(m.entry, m.crafted, m.fractured, list(m.values), m.veiled) for m in self.mods],
                dict(self.spent), list(self.log), list(self.influences), self.exarch, self.eater, st)

    def restore(self, snap, copy: bool = False):
        """Вернуть состояние из snapshot(). copy=True — не трогать сам snapshot (для многократных прогонов)."""
        rarity, mods, spent, log, infl, exarch, eater = snap[:7]
        st = snap[7] if len(snap) > 7 else self.state
        if copy:
            mods = [ItemMod(m.entry, m.crafted, m.fractured, list(m.values), m.veiled) for m in mods]
            spent, log, infl = dict(spent), list(log), list(infl)
            st = dict(st)
            st["notes"] = list(st.get("notes", []))
        old = (list(self.influences), self.state.get("catalyst"), self.state.get("quality"))
        self.rarity, self.mods, self.spent, self.log, self.exarch, self.eater = rarity, mods, spent, log, exarch, eater
        self.influences, self.state = infl, st
        if old != (list(infl), st.get("catalyst"), st.get("quality")):
            self.pool = self._make_pool()

    def undo(self):
        if not self.history:
            raise CraftError("Нечего отменять.")
        self.restore(self.history.pop())

    def reset(self):
        self.history.clear()
        self.rarity, self.mods, self.spent, self.log = "Normal", [], {}, []
        self.exarch = self.eater = None
        self.state = {"corrupted": False, "split": False, "catalyst": None, "quality": 0, "imprint": None,
                      "lock": False, "notes": []}
        self.pool = self._make_pool()

    def _begin(self, currency: str | None, n: int = 1):
        self.history.append(self.snapshot())
        if len(self.history) > 200:
            self.history.pop(0)
        if currency:
            self.spent[currency] = self.spent.get(currency, 0) + n

    def metas(self) -> set:
        return {m.meta for m in self.mods if m.meta}

    @property
    def prefixes(self):
        return [m for m in self.mods if m.kind == "prefix"]

    @property
    def suffixes(self):
        return [m for m in self.mods if m.kind == "suffix"]

    def limits(self):
        return self.pool.limits(self.rarity if self.rarity != "Normal" else "Rare")

    # ------------------------------------------------------------ выбор мода
    def _excluded_tags(self) -> set:
        ex = set()
        if "no_attack" in self.metas():
            ex.add("attack")
        if "no_caster" in self.metas():
            ex.add("caster")
        return ex

    def candidates(self, rarity: str, pool: ModPool | None = None) -> list[PoolEntry]:
        pool = pool or self.pool
        present = [m.mod for m in self.mods]
        ex = self._excluded_tags()
        out = pool.candidates(present, rarity)
        if ex:
            out = [e for e in out if not ex.intersection(e.mod.tags)]
        if self.blocked:
            out = [e for e in out if (e.mod.kind, e.mod.type) not in self.blocked]
        return out

    def _add_random(self, rarity: str, pool: ModPool | None = None) -> ItemMod | None:
        c = self.candidates(rarity, pool)
        if not c:
            return None
        e = self.rng.choices(c, weights=[x.weight for x in c])[0]
        im = ItemMod(e)
        im.roll_values(self.rng)
        self.mods.append(im)
        return im

    def _fill(self, rarity: str, n: int, pool: ModPool | None = None):
        while len(self.mods) < n:
            if not self._add_random(rarity, pool):
                break

    def _count(self, rarity):
        table = RARE_MOD_COUNT if rarity == "Rare" else MAGIC_MOD_COUNT
        return self.rng.choices([c for c, _ in table], weights=[w for _, w in table])[0]

    def _keep_locked(self) -> list[ItemMod]:
        """Какие моды переживают реролл (Chaos/Scour/эссенция/фоссилы)."""
        m = self.metas()
        keep = [x for x in self.mods if x.fractured]
        if "prefix_lock" in m:
            keep += [x for x in self.prefixes if x not in keep]
        if "suffix_lock" in m:
            keep += [x for x in self.suffixes if x not in keep]
        # сам метамод стоит на противоположной стороне и при реролле пропадает
        return keep

    # ------------------------------------------------------------ валюта
    CORRUPTED_OK = {"tainted_chaos", "tainted_exalt", "tainted_divine", "bench", "remove_crafted",
                    "imprint_restore", "lock"}

    def apply(self, action: str, **kw):
        fn = getattr(self, "do_" + action, None)
        if not fn:
            raise CraftError(f"Неизвестное действие: {action}")
        if self.state.get("corrupted") and action not in self.CORRUPTED_OK:
            raise CraftError("Предмет осквернён — на него действуют только Tainted-валюта и верстак.")
        if action.startswith("tainted") and not self.state.get("corrupted"):
            raise CraftError("Tainted-валюта работает только на осквернённых предметах (сначала Vaal Orb).")
        return fn(**kw)

    def do_transmute(self):
        if self.rarity != "Normal":
            raise CraftError("Transmutation работает только на белом предмете.")
        self._begin("Orb of Transmutation")
        self.rarity = "Magic"
        self._fill("Magic", self._count("Magic"))
        self.log.append("Transmutation → синий")

    def do_alteration(self):
        if self.rarity != "Magic":
            raise CraftError("Alteration работает только на синем предмете.")
        self._begin("Orb of Alteration")
        self.mods = [m for m in self.mods if m.fractured]
        self._fill("Magic", self._count("Magic"))
        self.log.append("Alteration")

    def do_augment(self):
        if self.rarity != "Magic":
            raise CraftError("Augmentation работает только на синем предмете.")
        if len(self.mods) >= 2:
            raise CraftError("На синем предмете уже 2 мода.")
        self._begin("Orb of Augmentation")
        m = self._add_random("Magic")
        self.log.append("Augmentation" + ("" if m else " — нечего добавить"))

    def do_regal(self):
        if self.rarity != "Magic":
            raise CraftError("Regal работает только на синем предмете.")
        self._begin("Regal Orb")
        self.rarity = "Rare"
        self._add_random("Rare")
        self.log.append("Regal → редкий")

    def do_alchemy(self):
        if self.rarity != "Normal":
            raise CraftError("Alchemy работает только на белом предмете.")
        self._begin("Orb of Alchemy")
        self.rarity = "Rare"
        self._fill("Rare", self._count("Rare"))
        self.log.append("Alchemy → редкий")

    def do_chaos(self):
        if self.rarity != "Rare":
            raise CraftError("Chaos работает только на редком предмете.")
        self._begin("Chaos Orb")
        keep = self._keep_locked()
        self.mods = keep
        self._fill("Rare", max(self._count("Rare"), len(keep)))
        self.log.append("Chaos" + (" (с защитой)" if len(keep) else ""))

    def do_exalt(self):
        if self.rarity != "Rare":
            raise CraftError("Exalted Orb работает только на редком предмете.")
        mp, ms = self.limits()
        if len(self.prefixes) >= mp and len(self.suffixes) >= ms:
            raise CraftError("Все 6 слотов заняты.")
        self._begin("Exalted Orb")
        m = self._add_random("Rare")
        self.log.append("Exalt" + ("" if m else " — нечего добавить"))

    def do_annul(self):
        if self.rarity == "Normal" or not self.mods:
            raise CraftError("Нечего снимать.")
        m = self.metas()
        can = [x for x in self.mods if not x.fractured
               and not ("prefix_lock" in m and x.kind == "prefix")
               and not ("suffix_lock" in m and x.kind == "suffix")]
        if not can:
            raise CraftError("Все моды защищены — Annulment ничего не снимет.")
        self._begin("Orb of Annulment")
        victim = self.rng.choice(can)
        self.mods.remove(victim)
        self.log.append(f"Annulment сняла: {victim.text}")

    def do_scour(self):
        if self.rarity == "Normal":
            raise CraftError("Предмет и так белый.")
        self._begin("Orb of Scouring")
        keep = self._keep_locked()
        self.mods = keep
        if not keep:
            self.rarity = "Normal"
        self.log.append("Scouring")

    def do_divine(self):
        if not self.mods:
            raise CraftError("Нет модов для Divine.")
        self._begin("Divine Orb")
        for m in self.mods:
            if not m.fractured:
                m.roll_values(self.rng)
        self.log.append("Divine — значения перероллены")

    def do_essence(self, essence: cc.Essence):
        if self.rarity == "Magic":
            raise CraftError("Эссенция работает на белом предмете (или на редком — Shrieking/Deafening).")
        if self.rarity == "Rare" and essence.tier < 6:
            raise CraftError("На редкий предмет можно только Shrieking/Deafening и особые эссенции.")
        if essence.max_ilvl and self.pool.ilvl > essence.max_ilvl:
            raise CraftError(f"Эта эссенция только для предметов до ilvl {essence.max_ilvl}.")
        self._begin(essence.name)
        keep = self._keep_locked() if self.rarity == "Rare" else []
        self.rarity = "Rare"
        self.mods = keep
        fe = cc.essence_entry(self.pool, essence.mod)
        if not any(g in essence.mod.groups for x in self.mods for g in x.mod.groups):
            im = ItemMod(fe)
            im.roll_values(self.rng)
            self.mods.append(im)
        self._fill("Rare", max(self._count("Rare"), len(self.mods)))
        self.log.append(f"{essence.name}")

    def do_fossils(self, fossils: list):
        if not fossils or len(fossils) > 4:
            raise CraftError("Нужно от 1 до 4 фоссилов.")
        if self.rarity == "Magic":
            raise CraftError("Фоссилы работают на белом или редком предмете.")
        self._begin(cc.RESONATORS[len(fossils)])
        for f in fossils:
            self.spent[f.name] = self.spent.get(f.name, 0) + 1
        names = {f.name for f in fossils}
        if "Fractured Fossil" in names and (self.influences or self.state.get("split")):
            raise CraftError("Fractured Fossil не работает на предметах с влиянием и уже расколотых (Split).")
        fp = cc.fossil_pool(self.data, self.pool, fossils)
        if "Sanctified Fossil" in names:
            fp = sanctified_pool(fp)
        keep = self._keep_locked() if self.rarity == "Rare" else []
        self.rarity = "Rare"
        self.mods = keep
        # Glyphic (100%) / Tangled (10%): мод «осквернённой» эссенции
        ce = max((self.data._load("fossils").get(f.id, {}).get("corrupted_essence_chance", 0) for f in fossils),
                 default=0)
        if ce and self.rng.random() * 100 < ce:
            cands = corrupt_essence_mods(self.data, self.pool)
            if cands:
                e = self.rng.choice(cands)
                im = ItemMod(e)
                im.roll_values(self.rng)
                self.mods.append(im)
        self._fill("Rare", max(self._count("Rare"), len(self.mods)), fp)
        if "Sanctified Fossil" in names:
            for m in self.mods:
                if m not in keep:
                    lucky = ItemMod(m.entry)
                    lucky.roll_values(self.rng)
                    m.values = [max(a, b, key=abs) for a, b in zip(m.values, lucky.values)] or m.values
        notes = []
        if "Fractured Fossil" in names:
            can = [m for m in self.mods if not m.crafted and not m.fractured]
            if can:
                fm = self.rng.choice(can)
                fm.fractured = True
                self.state["split"] = True
                notes.append(f"Fractured: копия предмета, «{fm.text}» зафрактурен (Split)")
        if "Bloodstained Fossil" in names:
            notes.append(self._vaal_implicit())
            self.state["corrupted"] = True
        if "Hollow Fossil" in names:
            notes.append("Hollow: добавлен абиссальный сокет")
        if "Gilded Fossil" in names:
            notes.append("Gilded: предмет дороже продаётся торговцу")
        self.state["notes"] = [n for n in self.state.get("notes", []) if not n.startswith(("Gilded", "Hollow"))] + notes
        self.log.append("Фоссилы: " + " + ".join(f.name.replace(" Fossil", "") for f in fossils))

    # ------------------------------------------------------------ влияния
    def do_conqueror(self, name: str):
        orb = inf.CONQUEROR_ORBS.get(name)
        if not orb:
            raise CraftError("Неизвестное влияние.")
        if name not in self.inf_tags:
            raise CraftError(f"У этого типа предметов нет влияния {name}.")
        if self.rarity != "Rare":
            raise CraftError(f"{orb} работает только на редком предмете.")
        if self.influences:
            raise CraftError("Предмет уже с влиянием.")
        if self.exarch or self.eater:
            raise CraftError("На предмете с Eldritch-импликитами влияние добавить нельзя.")
        mp, ms = self.limits()
        if len(self.prefixes) >= mp and len(self.suffixes) >= ms:
            raise CraftError("Нужен свободный слот.")
        self._begin(orb)
        self.influences = [name]
        self.pool = self._make_pool()
        c = [e for e in self.candidates("Rare") if inf.influence_of(e.mod, self.inf_tags) == name]
        if c:
            e = self.rng.choices(c, weights=[x.weight for x in c])[0]
            im = ItemMod(e)
            im.roll_values(self.rng)
            self.mods.append(im)
        self.log.append(f"{orb}: влияние {name}")

    # ------------------------------------------------------------ Eldritch
    def _eldritch_check(self):
        if not inf.eldritch_supported(self.base_pool.tags):
            raise CraftError("Eldritch-импликиты бывают только на шлемах, перчатках, ботинках и нагрудниках.")
        if self.influences:
            raise CraftError("На предмет с влиянием Eldritch-валюту применить нельзя.")

    def _roll_eldritch(self, side: str, level: int, keep_type: str | None = None):
        pool = [m for m in inf.eldritch_pool(self.data, self.base_pool.tags, side) if m.level == level]
        if keep_type:
            pool = [m for m in pool if m.type == keep_type] or pool
        if not pool:
            return None
        return self.rng.choices(pool, weights=[m.weight for m in pool])[0]

    def do_eldritch_currency(self, side: str, level: int):
        self._eldritch_check()
        name = f"{inf.ELDRITCH_TIERS[level]} Eldritch {'Ember' if side == 'exarch' else 'Ichor'}"
        m = self._roll_eldritch(side, level)
        if not m:
            raise CraftError("Для этой базы нет таких импликитов.")
        self._begin(name)
        setattr(self, side, m)
        self.log.append(f"{name}: {m.text}")

    def dominance(self) -> str | None:
        a = self.exarch.level if self.exarch else 0
        b = self.eater.level if self.eater else 0
        if a == b:
            return None
        return "exarch" if a > b else "eater"

    def _dominant_kind(self) -> str:
        d = self.dominance()
        if not d:
            raise CraftError("Нет доминирования: тиры импликитов Exarch и Eater равны (или их нет).")
        return "prefix" if d == "exarch" else "suffix"

    def do_eldritch_chaos(self):
        if self.rarity != "Rare":
            raise CraftError("Eldritch Chaos работает только на редком предмете.")
        kind = self._dominant_kind()
        self._begin("Eldritch Chaos Orb")
        old = [m for m in self.mods if m.kind == kind and not m.fractured]
        n = max(1, len(old))
        self.mods = [m for m in self.mods if m not in old]
        for _ in range(n):
            c = [e for e in self.candidates("Rare") if e.mod.kind == kind]
            if not c:
                break
            e = self.rng.choices(c, weights=[x.weight for x in c])[0]
            im = ItemMod(e)
            im.roll_values(self.rng)
            self.mods.append(im)
        self.log.append(f"Eldritch Chaos: перероллены {'префиксы' if kind == 'prefix' else 'суффиксы'}")

    def do_eldritch_exalt(self):
        if self.rarity != "Rare":
            raise CraftError("Eldritch Exalted Orb работает только на редком предмете.")
        kind = self._dominant_kind()
        mp, ms = self.limits()
        if (kind == "prefix" and len(self.prefixes) >= mp) or (kind == "suffix" and len(self.suffixes) >= ms):
            raise CraftError(f"Нет свободного {'префикса' if kind == 'prefix' else 'суффикса'}.")
        c = [e for e in self.candidates("Rare") if e.mod.kind == kind]
        self._begin("Eldritch Exalted Orb")
        if c:
            e = self.rng.choices(c, weights=[x.weight for x in c])[0]
            im = ItemMod(e)
            im.roll_values(self.rng)
            self.mods.append(im)
        self.log.append(f"Eldritch Exalt: +{'префикс' if kind == 'prefix' else 'суффикс'}")

    def do_eldritch_annul(self):
        kind = self._dominant_kind()
        can = [m for m in self.mods if m.kind == kind and not m.fractured]
        if not can:
            raise CraftError("Нечего снимать с доминирующей стороны.")
        self._begin("Eldritch Orb of Annulment")
        v = self.rng.choice(can)
        self.mods.remove(v)
        self.log.append(f"Eldritch Annul сняла: {v.text}")

    def do_conflict(self):
        self._eldritch_check()
        if not (self.exarch and self.eater):
            raise CraftError("Нужны оба импликита: Exarch и Eater.")
        d = self.dominance() or self.rng.choice(["exarch", "eater"])
        other = "eater" if d == "exarch" else "exarch"
        dm, om = getattr(self, d), getattr(self, other)
        self._begin("Orb of Conflict")
        up = self._roll_eldritch(d, min(6, dm.level + 1), dm.type) or dm
        down = self._roll_eldritch(other, max(1, om.level - 1), om.type) or om
        setattr(self, d, up)
        setattr(self, other, down)
        self.log.append("Orb of Conflict: доминирующий импликит усилен, второй ослаблен")

    # ------------------------------------------------------------ Harvest
    def _reforge(self, first_pick=None, weight_fn=None, keep_count=False):
        """Общий реролл редкого предмета (как Chaos, с учётом замков)."""
        before = len(self.mods)
        keep = self._keep_locked()
        self.rarity = "Rare"
        self.mods = keep
        if first_pick:
            c = [e for e in self.candidates("Rare") if first_pick(e)]
            if c:
                e = self.rng.choices(c, weights=[x.weight for x in c])[0]
                im = ItemMod(e)
                im.roll_values(self.rng)
                self.mods.append(im)
        n = max(self._count("Rare"), len(self.mods))
        if keep_count:
            n = max(n, before)
        while len(self.mods) < n:
            c = self.candidates("Rare")
            if not c:
                break
            ws = [weight_fn(x) if weight_fn else x.weight for x in c]
            if not any(ws):
                break
            e = self.rng.choices(c, weights=ws)[0]
            im = ItemMod(e)
            im.roll_values(self.rng)
            self.mods.append(im)

    def do_harvest_reforge(self, label: str):
        from .harvest import HARVEST
        tag, color, amount, _ = HARVEST[label]
        if self.rarity != "Rare":
            raise CraftError("Harvest Reforge работает на редком предмете.")
        if not [e for e in self.candidates("Rare") if tag in e.mod.tags] and not self._keep_locked():
            raise CraftError(f"На этой базе нет модов с тегом {tag}.")
        self._begin(color, amount)
        self._reforge(first_pick=lambda e: tag in e.mod.tags)
        self.log.append(f"Harvest Reforge {label}")

    def do_harvest_same(self, more: bool = True):
        from .harvest import SAME_TYPES_COST, SAME_TYPES_MULT
        if self.rarity != "Rare":
            raise CraftError("Этот Harvest-крафт работает на редком предмете.")
        groups = {g for m in self.mods for g in m.mod.groups}
        k = SAME_TYPES_MULT if more else 1 / SAME_TYPES_MULT
        self._begin(*SAME_TYPES_COST)
        self._reforge(weight_fn=lambda e: e.weight * (k if groups & set(e.mod.groups) else 1), keep_count=more)
        self.log.append("Harvest: reforge, " + ("больше шанс тех же модов" if more else "меньше шанс тех же модов"))

    def do_harvest_augment(self, label: str):
        from .harvest import HARVEST
        tag, color, _, amount = HARVEST[label]
        if not amount:
            raise CraftError("Для этого тега нет Harvest-крафта «добавить мод».")
        if self.rarity == "Normal":
            raise CraftError("Нужен синий или редкий предмет.")
        if self.influences:
            raise CraftError("Этот Harvest-крафт работает только на предметах без влияния.")
        c = [e for e in self.candidates(self.rarity) if tag in e.mod.tags]
        if not c:
            raise CraftError(f"Нет свободного места под мод с тегом {tag} (или таких модов нет).")
        self._begin(color, amount)
        e = self.rng.choices(c, weights=[x.weight for x in c])[0]
        im = ItemMod(e)
        im.roll_values(self.rng)
        removable = [m for m in self.mods if not m.fractured]
        self.mods.append(im)
        txt = ""
        if removable:
            v = self.rng.choice(removable)
            self.mods.remove(v)
            txt = f", снят: {v.text}"
        self.log.append(f"Harvest: +{label} мод ({im.text}){txt}")

    # ------------------------------------------------------------ Veiled
    def _veiled_mod(self, kind: str) -> ItemMod:
        md = ModDef(f"veiled_{kind}", "Veiled", kind, "Veiled", (f"Veiled_{kind}",), 1,
                    f"Veiled {'префикс' if kind == 'prefix' else 'суффикс'} (открыть у Jun)", (), (), ())
        return ItemMod(PoolEntry(md, 0, 1), veiled=True)

    def do_veiled_chaos(self):
        if self.rarity != "Rare":
            raise CraftError("Veiled Chaos Orb работает только на редком предмете.")
        self._begin("Veiled Chaos Orb")
        self._reforge()
        mp, ms = self.limits()
        kinds = [k for k, n, mx in (("prefix", len(self.prefixes), mp), ("suffix", len(self.suffixes), ms))]
        k = self.rng.choice(kinds)
        same = [m for m in self.mods if m.kind == k and not m.fractured and m not in self._keep_locked()]
        if (len(self.prefixes) if k == "prefix" else len(self.suffixes)) >= (mp if k == "prefix" else ms) and same:
            self.mods.remove(self.rng.choice(same))
        self.mods.append(self._veiled_mod(k))
        self.log.append("Veiled Chaos: на предмете Veiled-мод")

    def do_veiled_exalt(self):
        if self.rarity != "Rare":
            raise CraftError("Veiled Exalted Orb работает только на редком предмете.")
        if any(m.veiled for m in self.mods):
            raise CraftError("На предмете уже есть Veiled-мод.")
        mp, ms = self.limits()
        kinds = [k for k, n, mx in (("prefix", len(self.prefixes), mp), ("suffix", len(self.suffixes), ms)) if n < mx]
        if not kinds:
            raise CraftError("Нет свободного слота.")
        self._begin("Veiled Exalted Orb")
        self.mods.append(self._veiled_mod(self.rng.choice(kinds)))
        self.log.append("Veiled Exalt: добавлен Veiled-мод")

    def unveil_options(self, n: int = 3) -> list[PoolEntry]:
        from .harvest import unveil_pool
        v = next((m for m in self.mods if m.veiled), None)
        if not v:
            raise CraftError("На предмете нет Veiled-мода.")
        taken = {g for m in self.mods if not m.veiled for g in m.mod.groups}
        pool = [e for e in unveil_pool(self.data, self.base_pool.tags, self.base_pool.ilvl)
                if e.mod.kind == v.kind and not taken & set(e.mod.groups)]
        opts, types = [], set()
        while pool and len(opts) < n:
            e = self.rng.choices(pool, weights=[x.weight for x in pool])[0]
            opts.append(e)
            pool = [x for x in pool if x.mod.type != e.mod.type]
        if not opts:
            raise CraftError("Для этой базы нет подходящих модов Jun.")
        self._pending_unveil = opts
        return opts

    def do_unveil(self, index: int):
        opts = getattr(self, "_pending_unveil", None)
        if not opts or not (0 <= index < len(opts)):
            raise CraftError("Сначала открой варианты Unveil.")
        v = next((m for m in self.mods if m.veiled), None)
        self._begin(None)
        self.mods.remove(v)
        im = ItemMod(opts[index])
        im.roll_values(self.rng)
        self.mods.append(im)
        self._pending_unveil = None
        self.log.append(f"Unveil: {im.text}")

    # ------------------------------------------------------------ верстак
    def bench_options(self) -> list[dict]:
        if self._bench is None:
            raw = cc._raw_mods(self.data)
            cls = self.pool.base.item_class
            out = []
            for b in self.data.bench:
                if cls not in b["item_classes"]:
                    continue
                m = raw.get(b["id"])
                if not m:
                    continue
                out.append({**b, "mod": cc._moddef(b["id"], m)})
            self._bench = out
        return self._bench

    def do_bench(self, option: dict):
        if self.rarity == "Normal":
            raise CraftError("Сначала сделай предмет синим или редким.")
        crafted = [m for m in self.mods if m.crafted]
        limit = 3 if "multi_craft" in self.metas() or "multi_craft" in [self._meta_of(option)] else 1
        if len(crafted) >= limit and self._meta_of(option) != "multi_craft":
            raise CraftError("Уже есть крафт с верстака (сними его или сделай «Can have up to 3 Crafted»).")
        md: ModDef = option["mod"]
        if any(set(md.groups) & set(m.mod.groups) for m in self.mods):
            raise CraftError("Мод этой группы уже есть на предмете.")
        mp, ms = self.limits()
        if self.rarity == "Magic":
            mp, ms = 1, 1
        if md.kind == "prefix" and len(self.prefixes) >= mp or md.kind == "suffix" and len(self.suffixes) >= ms:
            raise CraftError(f"Нет свободного {'префикса' if md.kind == 'prefix' else 'суффикса'}.")
        cost = option.get("cost", {})
        self._begin(None)
        from .advisor import CURRENCY_RU
        for k, v in cost.items():
            name = CURRENCY_RU.get(k, k)
            self.spent[name] = self.spent.get(name, 0) + v
        im = ItemMod(PoolEntry(md, 0, 1), crafted=True)
        im.roll_values(self.rng)
        self.mods.append(im)
        self.log.append(f"Верстак: {md.text.splitlines()[0]}")

    @staticmethod
    def _meta_of(option: dict) -> str | None:
        for key, (group, _) in META.items():
            if group in option["mod"].groups:
                return key
        return None

    def do_remove_crafted(self):
        if not any(m.crafted for m in self.mods):
            raise CraftError("Нет крафтов с верстака.")
        self._begin(None)
        self.mods = [m for m in self.mods if not m.crafted]
        self.log.append("Сняты крафты верстака")

    # ------------------------------------------------------------ осквернение и Tainted
    def _vaal_implicit(self) -> str:
        raw = cc._raw_mods(self.data)
        tags = set(self.pool.tags)
        cands = []
        for mid, m in raw.items():
            if m.get("generation_type") != "corrupted" or m.get("domain") != "item":
                continue
            if m.get("required_level", 1) > self.pool.ilvl:
                continue
            w = next((sw["weight"] for sw in m.get("spawn_weights", []) if sw["tag"] in tags), 0)
            if w > 0:
                cands.append((m.get("text", "").replace("\n", " / "), w))
        if not cands:
            return "Vaal-имплицит"
        t = self.rng.choices([c[0] for c in cands], weights=[c[1] for c in cands])[0]
        return f"Vaal-имплицит: {t}"

    def do_vaal(self):
        """Vaal Orb: 1/4 — ничего, 1/4 — Vaal-имплицит, 1/4 — перекат в редкий, 1/4 — сокеты (тут не меняем)."""
        if self.state.get("corrupted"):
            raise CraftError("Предмет уже осквернён.")
        self._begin("Vaal Orb")
        self.state["corrupted"] = True
        r = self.rng.randrange(4)
        notes = self.state.setdefault("notes", [])
        if r == 1:
            notes.append(self._vaal_implicit())
            self.log.append("Vaal: новый имплицит")
        elif r == 2 and self.rarity in ("Magic", "Rare"):
            keep = [m for m in self.mods if m.fractured]
            self.rarity = "Rare"
            self.mods = keep
            self._fill("Rare", max(self._count("Rare"), len(keep)))
            notes.append("Vaal: предмет перекатился в редкий")
            self.log.append("Vaal: перекат в редкий")
        elif r == 3:
            notes.append("Vaal: изменились сокеты/связи")
            self.log.append("Vaal: сокеты")
        else:
            self.log.append("Vaal: без изменений")

    def do_tainted_chaos(self):
        if self.rarity != "Rare":
            raise CraftError("Tainted Chaos Orb — только на осквернённом редком предмете.")
        self._begin("Tainted Chaos Orb")
        keep = [m for m in self.mods if m.fractured]
        if self.rng.random() < 0.5:
            self.mods = keep
            self._fill("Rare", max(self._count("Rare"), len(keep)))
            self.log.append("Tainted Chaos: перекат")
        else:
            self.mods = keep
            self.rarity = "Normal" if not keep else "Rare"
            self.log.append("Tainted Chaos: все моды сняты")

    def do_tainted_exalt(self):
        if self.rarity != "Rare":
            raise CraftError("Tainted Exalted Orb — только на осквернённом редком предмете.")
        mp, ms = self.limits()
        full = len(self.prefixes) >= mp and len(self.suffixes) >= ms
        can_remove = [m for m in self.mods if not m.fractured]
        self._begin("Tainted Exalted Orb")
        if (full or self.rng.random() < 0.5) and can_remove:
            v = self.rng.choice(can_remove)
            self.mods.remove(v)
            self.log.append(f"Tainted Exalt: снят {v.text}")
        else:
            m = self._add_random("Rare")
            self.log.append("Tainted Exalt: добавлен мод" if m else "Tainted Exalt: нечего добавить")

    def do_tainted_divine(self):
        """Tainted Divine Teardrop: тир каждого мода случайно на ступень выше или ниже."""
        if self.rarity != "Rare" or not self.mods:
            raise CraftError("Tainted Divine Teardrop — только на осквернённом редком предмете с модами.")
        self._begin("Tainted Divine Teardrop")
        for m in self.mods:
            if m.crafted or m.fractured:
                continue
            tiers = sorted((e for e in self.pool.available if e.mod.kind == m.kind and e.mod.type == m.mod.type),
                           key=lambda e: e.tier)
            cur = next((i for i, e in enumerate(tiers) if e.mod.id == m.mod.id), None)
            if cur is None:
                continue
            nxt = cur + (-1 if self.rng.random() < 0.5 else 1)
            if 0 <= nxt < len(tiers):
                m.entry = tiers[nxt]
                m.roll_values(self.rng)
        self.log.append("Tainted Divine Teardrop: тиры сдвинуты")

    # ------------------------------------------------------------ Awakener / Maven
    def awakener_options(self, other: str) -> list[PoolEntry]:
        """Моды влияния other для этой базы — какой мод был на уничтожаемом предмете."""
        if other not in self.inf_tags:
            return []
        p = ModPool(self.data, self.base_pool.base, self.base_pool.ilvl, {self.inf_tags[other]})
        return [e for e in p.available if inf.influence_of(e.mod, self.inf_tags) == other]

    def do_awakener(self, other: str, mod_id: str | None = None):
        """Awakener's Orb: второй предмет с влиянием other уничтожается. Этот предмет становится редким
        с обоими влияниями: по одному модуу влияния от каждого предмета, остальное — случайно."""
        if len(self.influences) != 1:
            raise CraftError("Нужен предмет ровно с одним влиянием (второе даст уничтожаемый предмет).")
        if other == self.influences[0] or other not in self.inf_tags:
            raise CraftError("Второе влияние должно быть другим и доступным для этой базы.")
        mine = [m for m in self.mods if inf.influence_of(m.mod, self.inf_tags) == self.influences[0]]
        theirs = self.awakener_options(other)
        pick = next((e for e in theirs if e.mod.id == mod_id), None) or (theirs and self.rng.choice(theirs))
        self._begin("Awakener's Orb")
        keep = [self.rng.choice(mine)] if mine else []
        self.influences = [self.influences[0], other]
        self.pool = self._make_pool()
        self.rarity = "Rare"
        self.mods = keep
        if pick and not any(set(pick.mod.groups) & set(k.mod.groups) for k in keep):
            im = ItemMod(pick)
            im.roll_values(self.rng)
            self.mods.append(im)
        self._fill("Rare", max(self._count("Rare"), len(self.mods)))
        self.log.append(f"Awakener's Orb: влияния {' + '.join(self.influences)}")

    def do_dominance(self):
        """Orb of Dominance (Maven's Orb): нужно ≥2 мода влияния — один случайный удаляется,
        другой случайный возвышается (Elevated)."""
        im = [m for m in self.mods if inf.is_influence_mod(m.mod) and not m.crafted]
        if len(im) < 2:
            raise CraftError("Нужно минимум 2 мода влияния.")
        self._begin("Orb of Dominance")
        victim = self.rng.choice(im)
        self.mods.remove(victim)
        rest = [m for m in im if m is not victim and "Maven" not in m.mod.id]
        if not rest:
            self.log.append(f"Dominance: снят {victim.text}, возвышать нечего")
            return
        target = self.rng.choice(rest)
        raw = cc._raw_mods(self.data)
        elev = [(mid, m) for mid, m in raw.items() if "Maven" in mid and m.get("type") == target.mod.type
                and m.get("generation_type") == target.kind]
        if elev:
            mid, m = elev[0]
            target.entry = PoolEntry(cc._moddef(mid, m), 0, 1)
            target.roll_values(self.rng)
            self.log.append(f"Dominance: снят {victim.text}, возвышен {target.text}")
        else:
            self.log.append(f"Dominance: снят {victim.text} (возвышенной версии у этого мода нет)")

    # ------------------------------------------------------------ Beastcrafting
    def do_beast_prefix(self):
        """Farric Wolf Alpha: добавить префикс, снять случайный суффикс."""
        return self._beast_swap("prefix")

    def do_beast_suffix(self):
        """Farric Lynx Alpha: добавить суффикс, снять случайный префикс."""
        return self._beast_swap("suffix")

    def _beast_swap(self, add: str):
        if self.rarity != "Rare":
            raise CraftError("Только на редком предмете.")
        mp, ms = self.limits()
        if add == "prefix" and len(self.prefixes) >= mp or add == "suffix" and len(self.suffixes) >= ms:
            raise CraftError(f"Нужен свободный {'префикс' if add == 'prefix' else 'суффикс'}.")
        rem = "suffix" if add == "prefix" else "prefix"
        lock = ("suffix_lock" if rem == "suffix" else "prefix_lock") in self.metas()
        self._begin("Farric Wolf Alpha" if add == "prefix" else "Farric Lynx Alpha")
        can = [m for m in self.mods if m.kind == rem and not m.fractured]
        removed = None
        if can and not lock:
            removed = self.rng.choice(can)
            self.mods.remove(removed)
        c = [e for e in self.candidates("Rare") if e.mod.kind == add]
        if c:
            e = self.rng.choices(c, weights=[x.weight for x in c])[0]
            im = ItemMod(e)
            im.roll_values(self.rng)
            self.mods.append(im)
        self.log.append(f"Зверь: +{add}" + (f", снят {removed.text}" if removed else ""))

    def do_beast_influence(self):
        """Craicic Maw: добавить мод влияния предмета."""
        if self.rarity != "Rare" or not self.influences:
            raise CraftError("Нужен редкий предмет с влиянием.")
        mp, ms = self.limits()
        if len(self.prefixes) >= mp and len(self.suffixes) >= ms:
            raise CraftError("Нужен свободный слот.")
        c = [e for e in self.candidates("Rare") if inf.influence_of(e.mod, self.inf_tags) in self.influences]
        if not c:
            raise CraftError("Нет подходящих модов влияния.")
        self._begin("Craicic Maw")
        e = self.rng.choices(c, weights=[x.weight for x in c])[0]
        im = ItemMod(e)
        im.roll_values(self.rng)
        self.mods.append(im)
        self.log.append("Craicic Maw: мод влияния")

    def do_beast_split(self):
        """Fenumal Plagued Arachnid: два предмета с половиной модов; здесь остаётся первая копия."""
        if self.rarity != "Rare" or len(self.mods) < 2:
            raise CraftError("Нужен редкий предмет минимум с 2 модами.")
        if self.influences or self.state.get("split"):
            raise CraftError("Нельзя расколоть предмет с влиянием или уже расколотый.")
        self._begin("Fenumal Plagued Arachnid")
        mods = list(self.mods)
        self.rng.shuffle(mods)
        half = len(mods) // 2
        a, b = mods[:half], mods[half:]
        if self.rng.random() < 0.5:
            a, b = b, a
        self.mods = [m for m in self.mods if m in a]
        self.state["split"] = True
        self.state.setdefault("notes", []).append("Split: вторая копия — " + "; ".join(m.text for m in b))
        self.log.append("Split: на этой копии " + str(len(a)) + " мод(ов)")

    def do_beast_aspect(self, aspect: str):
        """Духи-звери: крафтовый суффикс «Grants Level 20 Aspect of the …»."""
        ids = {"Cat": "GrantsCatAspect1", "Avian": "GrantsBirdAspect1_", "Spider": "GrantsSpiderAspect1",
               "Crab": "GrantsCrabAspect1_"}
        m = cc._raw_mods(self.data).get(ids.get(aspect, ""))
        if not m or self.rarity not in ("Magic", "Rare"):
            raise CraftError("Аспект — на магический или редкий предмет.")
        mp, ms = self.limits()
        if self.rarity == "Magic":
            ms = 1
        if len(self.suffixes) >= ms:
            raise CraftError("Нужен свободный суффикс.")
        if any(x.crafted for x in self.mods) and "multi_craft" not in self.metas():
            raise CraftError("На предмете уже есть крафт.")
        import dataclasses
        md = dataclasses.replace(cc._moddef(ids[aspect], m), kind="suffix")
        self._begin(None)
        self.mods.append(ItemMod(PoolEntry(md, 0, 1), crafted=True))
        self.log.append(f"Аспект: {aspect}")

    def do_imprint(self):
        if self.rarity != "Magic":
            raise CraftError("Отпечаток (Craicic Chimeral) — только магического предмета.")
        if self.state.get("split") or any(m.fractured for m in self.mods):
            raise CraftError("Нельзя сделать отпечаток расколотого/фрактурного предмета.")
        self._begin("Craicic Chimeral")
        self.state["imprint"] = (self.rarity, [ItemMod(m.entry, m.crafted, m.fractured, list(m.values), m.veiled)
                                               for m in self.mods])
        self.log.append("Отпечаток сохранён")

    def do_imprint_restore(self):
        imp = self.state.get("imprint")
        if not imp:
            raise CraftError("Нет отпечатка.")
        self._begin(None)
        self.rarity = imp[0]
        self.mods = [ItemMod(m.entry, m.crafted, m.fractured, list(m.values), m.veiled) for m in imp[1]]
        self.state["imprint"] = None
        self.log.append("Предмет восстановлен из отпечатка")

    # ------------------------------------------------------------ катализаторы (кольца, амулеты, пояса)
    def do_catalyst(self, name: str):
        from .sockets import CATALYST_CLASSES, CATALYSTS
        if self.pool.base.item_class not in CATALYST_CLASSES:
            raise CraftError("Катализаторы — только для колец, амулетов и поясов.")
        if name not in CATALYSTS:
            raise CraftError("Неизвестный катализатор.")
        q = self.state.get("quality", 0)
        if self.state.get("catalyst") == name and q >= 20:
            raise CraftError("Качество уже 20%.")
        step = {"Normal": 5, "Magic": 2}.get(self.rarity, 1)
        self._begin(name)
        if self.state.get("catalyst") != name:
            self.state["catalyst"] = name        # другой катализатор меняет тип качества, величина сохраняется
        self.state["quality"] = min(20, q + step)
        self.pool = self._make_pool()
        self.log.append(f"{name}: качество {self.state['quality']}%")

    # ------------------------------------------------------------ предмет из игры
    def load_item(self, item, match) -> list[str]:
        """Ставит в эмулятор предмет, скопированный в игре. match(pool, parsed_mod) → PoolEntry|None.
        Возвращает строки модов, которые не удалось распознать (их на предмете не будет)."""
        if item.rarity not in ("Normal", "Magic", "Rare"):
            raise CraftError("В эмулятор можно положить только обычный, магический или редкий предмет.")
        self.reset()
        self.rarity = item.rarity
        unknown: list[str] = []
        from .parser import canonical
        bench = None
        for pm in item.mods:
            entry = None if pm.crafted else match(self.pool, pm)
            if entry is None and pm.crafted:
                if bench is None:
                    bench = self.bench_options()
                want = [canonical(l) for l in pm.lines]
                for o in bench:
                    lines = [canonical(x) for x in o["mod"].text.split("\n")]
                    if want and lines[:len(want)] == want:
                        entry = PoolEntry(o["mod"], 0, 1)
                        break
            if entry is None:
                unknown.append(pm.text)
                continue
            im = ItemMod(entry, crafted=pm.crafted, fractured=pm.fractured)
            vals = [float(v) for l in pm.lines for v in VALUE_IN_LINE.findall(l)]
            im.values = [int(v) if v.is_integer() else v for v in vals]
            if len(im.values) != len(RANGE_RE.findall(entry.mod.text)):
                im.roll_values(self.rng)
            self.mods.append(im)
        self.log.append(f"Из игры: {item.name or item.base_name}" + (f" (не распознано: {len(unknown)})" if unknown else ""))
        return unknown

    # ------------------------------------------------------------ подсказки
    def chances(self, targets) -> dict:
        """Шансы ближайших шагов для недостающих целей."""
        have = {t for t in targets for m in self.mods if not m.crafted and t.ok(m.entry)}
        missing = [t for t in targets if t not in have]
        out = {"have": len(have), "need": len(targets), "missing": [t.label for t in missing]}
        if not missing:
            return out
        want = lambda e: any(t.ok(e) for t in missing)
        def share(rarity, pool=None, extra_exclude=()):
            c = self.candidates(rarity, pool)
            if extra_exclude:
                c = [e for e in c if not set(extra_exclude) & set(e.mod.tags)]
            tot = sum(e.weight for e in c)
            return sum(e.weight for e in c if want(e)) / tot if tot else 0
        if self.rarity == "Rare":
            out["exalt"] = share("Rare")
            kinds = {t.kind for t in missing}
            mp, ms = self.limits()
            open_p, open_s = mp - len(self.prefixes), ms - len(self.suffixes)
            if len(kinds) == 1 and ((kinds == {"prefix"} and open_s) or (kinds == {"suffix"} and open_p)):
                k = next(iter(kinds))
                c = [e for e in self.candidates("Rare") if e.mod.kind == k]
                tot = sum(e.weight for e in c)
                out["exalt_blocked"] = sum(e.weight for e in c if want(e)) / tot if tot else 0
            for tag, key in (("attack", "exalt_no_attack"), ("caster", "exalt_no_caster")):
                if not any(tag in t_e.mod.tags for t_e in self.pool.available if want(t_e)):
                    out[key] = share("Rare", extra_exclude=(tag,))
        if self.rarity == "Magic" and len(self.mods) < 2:
            out["augment"] = share("Magic")
        if self.rarity == "Magic" and len(self.mods) == 2:
            out["regal"] = share("Rare")
        return out
