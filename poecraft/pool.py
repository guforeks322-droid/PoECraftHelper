"""Пул модов для конкретной базы и ilvl + вероятности."""

from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass

from .data import BaseItem, GameData, ModDef

AFFIX_LIMITS = {"Magic": (1, 1), "Rare": (3, 3)}  # (префиксы, суффиксы); джувелы — (2, 2)
JEWEL_CLASSES = {"Jewel", "AbyssJewel"}

# Сколько модов получает редкий предмет при Chaos / Regal-ролле с нуля (известные веса)
RARE_MOD_COUNT = [(4, 8), (5, 3), (6, 1)]
# Синий предмет: 1 или 2 мода. Точные веса игра не раскрывает, берём 50/50.
MAGIC_MOD_COUNT = [(1, 1), (2, 1)]


@dataclass
class PoolEntry:
    mod: ModDef
    weight: int
    tier: int  # 1 = лучший доступный на этой базе


class ModPool:
    def __init__(self, data: GameData, base: BaseItem, ilvl: int, extra_tags: set[str] | None = None):
        self.base = base
        self.ilvl = ilvl
        self.tags = set(base.tags) | (extra_tags or set())
        entries = []
        for mod in data.mods.values():
            if data.mod_domain(mod.id) != base.domain:
                continue
            w = mod.weight_for(self.tags)
            if w <= 0:
                continue
            entries.append((mod, w))

        # Тиры считаем по всем модам, что могут быть на базе (без учёта ilvl)
        by_type = defaultdict(list)
        for mod, w in entries:
            by_type[(mod.kind, mod.type)].append(mod)
        tier_of = {}
        for mods in by_type.values():
            for i, m in enumerate(sorted(mods, key=lambda m: -m.level), start=1):
                tier_of[m.id] = i

        self.all = [PoolEntry(m, w, tier_of[m.id]) for m, w in entries]
        self.available = [e for e in self.all if e.mod.level <= ilvl]

    # --- поиск мода по имени аффикса из текста предмета ---
    def find(self, name: str, kind: str) -> PoolEntry | None:
        for e in self.all:
            if e.mod.name == name and e.mod.kind == kind:
                return e
        return None

    def limits(self, rarity: str) -> tuple[int, int]:
        if self.base.item_class in JEWEL_CLASSES:
            return (1, 1) if rarity == "Magic" else (2, 2)
        return AFFIX_LIMITS.get(rarity, (0, 0))

    # --- что может выпасть при добавлении одного мода ---
    def candidates(self, present: list[ModDef], rarity: str) -> list[PoolEntry]:
        max_p, max_s = self.limits(rarity)
        n_p = sum(1 for m in present if m.kind == "prefix")
        n_s = sum(1 for m in present if m.kind == "suffix")
        taken = {g for m in present for g in m.groups}
        out = []
        for e in self.available:
            if e.mod.kind == "prefix" and n_p >= max_p:
                continue
            if e.mod.kind == "suffix" and n_s >= max_s:
                continue
            if taken.intersection(e.mod.groups):
                continue
            out.append(e)
        return out

    def chance_add(self, present: list[ModDef], rarity: str, want) -> float:
        """Точный шанс, что один добавленный мод (Exalt/Aug/Regal) подойдёт под want(entry)."""
        cands = self.candidates(present, rarity)
        total = sum(e.weight for e in cands)
        if not total:
            return 0.0
        return sum(e.weight for e in cands if want(e)) / total

    # --- полный реролл: считаем симуляцией ---
    def roll(self, rarity: str, rng: random.Random, keep: list[ModDef] | None = None) -> list[PoolEntry]:
        counts = RARE_MOD_COUNT if rarity == "Rare" else MAGIC_MOD_COUNT
        n = rng.choices([c for c, _ in counts], weights=[w for _, w in counts])[0]
        present = list(keep or [])
        rolled: list[PoolEntry] = []
        while len(present) < n:
            cands = self.candidates(present, rarity)
            if not cands:
                break
            e = rng.choices(cands, weights=[c.weight for c in cands])[0]
            present.append(e.mod)
            rolled.append(e)
        return rolled

    def chance_reroll(self, rarity: str, goal_fn, trials: int = 20000, seed: int = 1) -> float:
        """Шанс, что после Alteration/Chaos предмет удовлетворит goal_fn(список PoolEntry)."""
        rng = random.Random(seed)
        hits = sum(1 for _ in range(trials) if goal_fn(self.roll(rarity, rng)))
        return hits / trials


def yield_ui():
    """Короткая пауза в долгих симуляциях (они идут в фоновом потоке): отдаём GIL, чтобы окно не замирало."""
    import time
    time.sleep(0.003)
