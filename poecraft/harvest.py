"""Harvest (Horticrafting) и Veiled-моды.

Таблица крафтов и цены в lifeforce — по PoE Wiki (версия 3.29):
«Reforge a Rare item with random modifiers, including a X modifier» и т.д.
"""

from __future__ import annotations

import random

from .calc import Target
from .data import GameData, ModDef
from .pool import ModPool, PoolEntry
from .prices import Prices
from . import currency_craft as cc

WILD, VIVID, PRIMAL, SACRED = ("Wild Crystallised Lifeforce", "Vivid Crystallised Lifeforce",
                               "Primal Crystallised Lifeforce", "Sacred Crystallised Lifeforce")

# метка → (тег мода в данных, цвет lifeforce, сколько для Reforge, сколько для Augment или None)
HARVEST = {
    "Fire":      ("fire", WILD, 50, 15000),
    "Cold":      ("cold", VIVID, 50, 15000),
    "Lightning": ("lightning", PRIMAL, 50, 15000),
    "Physical":  ("physical", VIVID, 50, 15000),
    "Life":      ("life", WILD, 75, 17500),
    "Defence":   ("defences", PRIMAL, 75, 17500),
    "Chaos":     ("chaos", VIVID, 100, 17500),
    "Attack":    ("attack", WILD, 75, 17500),
    "Caster":    ("caster", PRIMAL, 75, 17500),
    "Speed":     ("speed", VIVID, 150, 20000),
    "Critical":  ("critical", PRIMAL, 150, 20000),
    "Elemental": ("elemental", WILD, 200, None),
    "Attribute": ("attribute", VIVID, 200, None),
    "Mana":      ("mana", PRIMAL, 200, None),
    "Minion":    ("minion", PRIMAL, 200, None),
}
SAME_TYPES_COST = (WILD, 200)
SAME_TYPES_MULT = 10.0   # оценка: игра не раскрывает множитель «more likely / less likely»


def tag_candidates(cands: list[PoolEntry], tag: str) -> list[PoolEntry]:
    return [e for e in cands if tag in e.mod.tags]


# ------------------------------------------------------------------ калькулятор
def _roll_with_tag(pool: ModPool, tag: str, rng, fixed=None):
    """Реролл как Chaos, но первый мод гарантированно с тегом."""
    roll_rest = cc._roller(pool, rng, fixed)
    tagged = tag_candidates(pool.available, tag)
    if not tagged:
        return None
    import bisect
    from itertools import accumulate
    cum = list(accumulate(e.weight for e in tagged))

    def roll():
        first = tagged[bisect.bisect_right(cum, rng.random() * cum[-1])]
        inner = cc._roller(pool, rng, (fixed or []) + [first])
        return inner()
    return roll


def method_harvest(pool: ModPool, targets: list[Target], label: str, prices: Prices) -> dict | None:
    tag, color, amount, _ = HARVEST[label]
    rng = random.Random(23)
    # заранее строим ролл-функцию: первый мод с тегом, остальное — обычный пул
    tagged = tag_candidates(pool.available, tag)
    if not tagged:
        return None
    import bisect
    from itertools import accumulate
    cum = list(accumulate(e.weight for e in tagged))
    need = len(targets)
    hits = trials = 0
    rollers: dict[str, object] = {}
    while trials < 120_000 and (hits < 300 or trials < 10_000):
        for _ in range(2000):
            trials += 1
            first = tagged[bisect.bisect_right(cum, rng.random() * cum[-1])]
            r = rollers.get(first.mod.id)
            if r is None:
                r = rollers[first.mod.id] = cc._roller(pool, rng, [first])
            got = r()
            if sum(1 for t in targets if any(t.ok(e) for e in got)) == need:
                hits += 1
    p = hits / trials
    return cc._card(f"Harvest: Reforge {label}",
                    f"Реролл редкого предмета с гарантированным модом тега «{tag}» ({amount} {color.split()[0]} lifeforce).",
                    p, hits, trials, {color: amount}, prices)


def best_harvest(pool: ModPool, targets: list[Target], prices: Prices, top: int = 2) -> list[dict]:
    """Перебираем теги, под которые попадает хотя бы одна цель."""
    tgt_tags = set()
    for t in targets:
        for e in pool.available:
            if t.ok(e):
                tgt_tags.update(e.mod.tags)
    out = []
    for label, (tag, *_rest) in HARVEST.items():
        if tag in tgt_tags:
            r = method_harvest(pool, targets, label, prices)
            if r:
                out.append(r)
    out.sort(key=lambda r: (r["cost_chaos"] is None, r["cost_chaos"] or 0))
    return out[:top]


# ------------------------------------------------------------------ Veiled
def unveil_pool(data: GameData, base_tags: set[str], ilvl: int) -> list[PoolEntry]:
    """Моды Jun, которые можно получить при Unveil (без особых модов Catarina / It That Fled)."""
    raw = cc._raw_mods(data)
    out = []
    for mid, m in raw.items():
        if m.get("domain") != "unveiled" or m.get("generation_type") not in ("prefix", "suffix"):
            continue
        if m.get("required_level", 1) > ilvl:
            continue
        w = 0
        for sw in m.get("spawn_weights", []):
            if sw["tag"] in base_tags:
                w = sw["weight"]
                break
        if w <= 0:
            continue
        md = cc._moddef(mid, m)
        out.append(PoolEntry(md, w, 1))
    # тир внутри типа: по уровню
    by_type: dict[tuple, list] = {}
    for e in out:
        by_type.setdefault((e.mod.kind, e.mod.type), []).append(e)
    res = []
    for lst in by_type.values():
        for i, e in enumerate(sorted(lst, key=lambda e: -e.mod.level), 1):
            res.append(PoolEntry(e.mod, e.weight, i))
    return res
