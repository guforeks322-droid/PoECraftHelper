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

    def _make_pool(self) -> ModPool:
        if not self.influences:
            return self.base_pool
        extra = {self.inf_tags[i] for i in self.influences}
        return ModPool(self.data, self.base_pool.base, self.base_pool.ilvl, extra)

    # ------------------------------------------------------------ состояние
    def snapshot(self):
        return (self.rarity, [ItemMod(m.entry, m.crafted, m.fractured, list(m.values), m.veiled) for m in self.mods],
                dict(self.spent), list(self.log), list(self.influences), self.exarch, self.eater)

    def undo(self):
        if not self.history:
            raise CraftError("Нечего отменять.")
        (self.rarity, self.mods, self.spent, self.log, infl, self.exarch, self.eater) = self.history.pop()
        if infl != self.influences:
            self.influences = infl
            self.pool = self._make_pool()

    def reset(self):
        self.history.clear()
        self.rarity, self.mods, self.spent, self.log = "Normal", [], {}, []
        self.exarch = self.eater = None

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
    def apply(self, action: str, **kw):
        fn = getattr(self, "do_" + action, None)
        if not fn:
            raise CraftError(f"Неизвестное действие: {action}")
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
        fp = cc.fossil_pool(self.data, self.pool, fossils)
        keep = self._keep_locked() if self.rarity == "Rare" else []
        self.rarity = "Rare"
        self.mods = keep
        self._fill("Rare", max(self._count("Rare"), len(keep)), fp)
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
