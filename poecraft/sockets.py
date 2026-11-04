"""Цвета сокетов: Chromatic Orb и рецепты верстака (Vorici).

Формула шансов цвета — как в калькуляторе Siveran (siveran.github.io/calc.html, версия июля 2026):
  * один атрибут:  свой цвет 0.9·(10+треб)/(сумма+20), чужой 0.05 + 0.9·5/(сумма+20)
  * два атрибута: свой цвет 0.9·треб/сумма, третий цвет 0.1
  * три атрибута: треб/сумма
Белые сокеты (механика лиги 3.29 Allflame) — по желанию: 1 − 0.00375·max(ilvl−14,1)·(1+q/100).
"""

from __future__ import annotations

from itertools import product
from math import factorial

# (R, G, B, цена в Chromatic, описание)
VORICI = [
    (1, 0, 0, 4, "1R"), (0, 1, 0, 4, "1G"), (0, 0, 1, 4, "1B"),
    (2, 0, 0, 25, "2R"), (0, 2, 0, 25, "2G"), (0, 0, 2, 25, "2B"),
    (0, 1, 1, 15, "1G1B"), (1, 0, 1, 15, "1R1B"), (1, 1, 0, 15, "1R1G"),
    (3, 0, 0, 120, "3R"), (0, 3, 0, 120, "3G"), (0, 0, 3, 120, "3B"),
    (2, 1, 0, 100, "2R1G"), (2, 0, 1, 100, "2R1B"), (1, 2, 0, 100, "1R2G"),
    (0, 2, 1, 100, "2G1B"), (1, 0, 2, 100, "1R2B"), (0, 1, 2, 100, "1G2B"),
]


def color_chances(str_: int, dex: int, int_: int) -> tuple[float, float, float]:
    reqs = [max(0, str_), max(0, dex), max(0, int_)]
    a = sum(reqs)
    nz = sum(1 for r in reqs if r > 0)
    if nz == 0:
        return (1 / 3, 1 / 3, 1 / 3)
    r = 0.9
    if nz == 1:
        f = lambda v: r * (10 + v) / (a + 20) if v > 0 else 0.05 + r * 5 / (a + 20)
    elif nz == 2:
        f = lambda v: r * v / a if v > 0 else 1 - r
    else:
        f = lambda v: v / a
    return tuple(f(v) for v in reqs)


def white_chance(ilvl: int, quality: int = 0) -> float:
    w = 1 - 0.00375 * max(ilvl - 14, 1) * (1 + min(quality, 30) / 100)
    return min(max(w, 0.0), 0.99)


def prob_at_least(chances, n: int, need: tuple[int, int, int], white: float = 0.0) -> float:
    """P(среди n сокетов хотя бы need[R], need[G], need[B]). Точный перебор (n ≤ 6)."""
    pr, pg, pb = (c * (1 - white) for c in chances)
    pw = white
    total = 0.0
    for r in range(n + 1):
        for g in range(n + 1 - r):
            for b in range(n + 1 - r - g):
                w = n - r - g - b
                if r < need[0] or g < need[1] or b < need[2]:
                    continue
                coef = factorial(n) / (factorial(r) * factorial(g) * factorial(b) * factorial(w))
                total += coef * pr ** r * pg ** g * pb ** b * pw ** w
    return total


def _dists(n, probs):
    """Все распределения n сокетов по цветам (len(probs) цветов) с вероятностями."""
    k = len(probs)
    def rec(i, left):
        if i == k - 1:
            yield (left,)
            return
        for c in range(left + 1):
            for rest in rec(i + 1, left - c):
                yield (c,) + rest
    for d in rec(0, n):
        coef = factorial(n)
        pr = 1.0
        for c, p in zip(d, probs):
            coef /= factorial(c)
            pr *= p ** c
        yield d, coef * pr


def prob_recipe(chances, n, want, fixed=(0, 0, 0), nonwhite=0, white=0.0):
    """Шанс: fixed — гарантированные цвета, nonwhite — сокеты без белого, остальные — с белым."""
    n_rest = n - sum(fixed) - nonwhite
    if n_rest < 0:
        return 0.0
    need = [max(0, w - f) for w, f in zip(want, fixed)]
    e = chances                                            # без белого
    u = tuple(c * (1 - white) for c in chances) + (white,)  # с белым
    total = 0.0
    for d1, p1 in _dists(nonwhite, e):
        for d2, p2 in _dists(n_rest, u):
            if all(d1[i] + d2[i] >= need[i] for i in range(3)):
                total += p1 * p2
    return total


def bench_color_recipes(data, item_class: str) -> list[tuple]:
    """Рецепты цвета с верстака из данных игры: (R, G, B, небелых, цена, описание)."""
    out = []
    for o in data._load("crafting_bench_options"):
        cs = o.get("actions", {}).get("color_sockets")
        if not cs or item_class not in o.get("item_classes", []):
            continue
        cost = sum(o.get("cost", {}).values())
        out.append((cs.count("R"), cs.count("G"), cs.count("B"), cs.count("N"), cost,
                    f"{len(cs)} небелых" if set(cs) == {"N"} else cs))
    return out


def methods(str_: int, dex: int, int_: int, sockets: int, want: tuple[int, int, int],
            chrom_price: float, white: float = 0.0, recipes=None) -> tuple[list[dict], tuple]:
    """Chromatic-спам и рецепты верстака. recipes — из bench_color_recipes (или старые VORICI)."""
    ch = color_chances(str_, dex, int_)
    out = []
    p = prob_recipe(ch, sockets, want, white=white)
    if p > 0:
        out.append({"name": "Chromatic Orb спам", "chance": p, "tries": 1 / p, "cost": 1 / p})
    if recipes is None:
        recipes = [(r, g, b, 0, c, d) for r, g, b, c, d in VORICI]
    for r, g, b, nw, cost, desc in recipes:
        if r > want[0] or g > want[1] or b > want[2] or r + g + b + nw > sockets:
            continue
        if nw and not (r or g or b) and white <= 0:
            continue  # «N небелых» имеет смысл только когда есть белые сокеты
        p = prob_recipe(ch, sockets, want, (r, g, b), nw, white)
        if p > 0:
            out.append({"name": f"Верстак: {desc} ({cost} Chromatic)", "chance": p, "tries": 1 / p, "cost": cost / p})
    for m in out:
        m["cost_chaos"] = m["cost"] * chrom_price
    out.sort(key=lambda m: m["cost"])
    return out, ch


# ------------------------------------------------------------------ катализаторы
CATALYSTS = {
    "Abrasive Catalyst": ("attack",),
    "Accelerating Catalyst": ("speed",),
    "Fertile Catalyst": ("life", "mana"),
    "Imbued Catalyst": ("caster",),
    "Intrinsic Catalyst": ("attribute",),
    "Noxious Catalyst": ("physical", "chaos"),
    "Prismatic Catalyst": ("resistance",),
    "Tempering Catalyst": ("defences",),
    "Turbulent Catalyst": ("elemental",),
    "Unstable Catalyst": ("critical",),
}
CATALYST_CLASSES = {"Ring", "Amulet", "Belt"}


def apply_catalyst(pool, name: str, quality: int = 20):
    """Вес модов с тегами катализатора × (1 + качество/100) — как в Craft of Exile."""
    import copy
    from .pool import PoolEntry
    tags = set(CATALYSTS.get(name, ()))
    if not tags or pool.base.item_class not in CATALYST_CLASSES:
        return pool
    k = 1 + min(max(quality, 0), 20) / 100
    fp = copy.copy(pool)
    fp.available = [PoolEntry(e.mod, int(round(e.weight * k)) if tags & set(e.mod.tags) else e.weight, e.tier)
                    for e in pool.available]
    return fp
