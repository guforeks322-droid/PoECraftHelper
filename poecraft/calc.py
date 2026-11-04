"""Калькулятор методов крафта: шанс за попытку и ожидаемая стоимость."""

from __future__ import annotations

import random
from dataclasses import dataclass

from .pool import ModPool, PoolEntry
from .prices import Prices

TRIALS = 20000


@dataclass(frozen=True)
class Target:
    kind: str       # prefix / suffix
    type: str       # тип мода из RePoE (IncreasedLife, FireResistance…)
    max_tier: int
    label: str = ""

    def ok(self, e: PoolEntry) -> bool:
        return e.mod.kind == self.kind and e.mod.type == self.type and e.tier <= self.max_tier


def _hits(entries, targets):
    return {t for t in targets for e in entries if t.ok(e)}


def pool_table(pool: ModPool) -> dict:
    """Все моды базы по группам, как во вкладке «Пул модов»."""
    total = sum(e.weight for e in pool.available)
    by_kind = {"prefix": 0, "suffix": 0}
    for e in pool.available:
        by_kind[e.mod.kind] += e.weight
    groups: dict[tuple, dict] = {}
    for e in sorted(pool.all, key=lambda e: (e.mod.kind, e.mod.type, e.tier)):
        key = (e.mod.kind, e.mod.type)
        g = groups.setdefault(key, {"kind": e.mod.kind, "type": e.mod.type, "tiers": [],
                                    "weight": 0, "tags": list(e.mod.tags)})
        avail = e.mod.level <= pool.ilvl
        g["tiers"].append({"tier": e.tier, "name": e.mod.name, "level": e.mod.level,
                           "text": e.mod.text, "weight": e.weight, "available": avail})
        if avail:
            g["weight"] += e.weight
    out = []
    for g in groups.values():
        if not g["weight"]:
            continue
        g["text"] = next((t["text"] for t in g["tiers"] if t["available"]), g["tiers"][0]["text"])
        g["chance_all"] = g["weight"] / total if total else 0
        g["chance_kind"] = g["weight"] / by_kind[g["kind"]] if by_kind[g["kind"]] else 0
        out.append(g)
    out.sort(key=lambda g: (g["kind"] != "prefix", -g["weight"], g["type"]))
    return {"total_weight": total, "prefix_weight": by_kind["prefix"], "suffix_weight": by_kind["suffix"],
            "groups": out}


# ------------------------------------------------------------------ методы
def _fast_rare_roller(pool: ModPool, rng):
    """Быстрый ролл редкого предмета: выбор по накопленным весам + отбраковка
    (мод того же типа слота сверх лимита или из уже занятой группы). Распределение
    то же, что у честного выбора из отфильтрованного пула."""
    import bisect
    from itertools import accumulate
    from .pool import RARE_MOD_COUNT
    ents = pool.available
    cum = list(accumulate(e.weight for e in ents))
    total = cum[-1]
    max_p, max_s = pool.limits("Rare")
    counts = [c for c, _ in RARE_MOD_COUNT]
    cw = [w for _, w in RARE_MOD_COUNT]

    def roll():
        n = rng.choices(counts, weights=cw)[0]
        got, groups, np_, ns = [], set(), 0, 0
        guard = 0
        while len(got) < n and guard < 500:
            guard += 1
            e = ents[bisect.bisect_right(cum, rng.random() * total)]
            if e.mod.kind == "prefix":
                if np_ >= max_p:
                    continue
            elif ns >= max_s:
                continue
            if groups.intersection(e.mod.groups):
                continue
            got.append(e)
            groups.update(e.mod.groups)
            if e.mod.kind == "prefix":
                np_ += 1
            else:
                ns += 1
        return got
    return roll


def method_chaos(pool: ModPool, targets: list[Target], prices: Prices, rng) -> dict:
    """Симуляция: крутим, пока не наберём 400 попаданий (или 300 000 роллов)."""
    roll = _fast_rare_roller(pool, rng)
    need = len(targets)
    hits = trials = 0
    while trials < 300_000 and (hits < 400 or trials < TRIALS):
        for _ in range(10000):
            trials += 1
            if len(_hits(roll(), targets)) == need:
                hits += 1
    p = hits / trials
    r = _result("Chaos Orb спам", "Роллим редкий предмет Chaos'ом, пока не выпадут все нужные моды.",
                p, {"Chaos Orb": 1}, prices.get("Chaos Orb"), prices, simulated=True)
    if hits:
        err = 1 / hits ** 0.5
        tr = f"{trials:,}".replace(",", " ")
        att = f"{1 / p:,.0f}".replace(",", " ")
        r["chance_label"] = f"Шанс за попытку: {p:.3%} (±{err:.0%}, симуляция {tr} роллов) · в среднем ~{att} попыток"
    return r


def _magic_outcomes(pool: ModPool, targets: list[Target]):
    """Точный перебор исходов «Alteration (+Augmentation при пользе)».

    Возвращает (P[все цели], E[число аугов], {набор попаданий: вероятность}).
    Синий предмет получает 1 или 2 мода (MAGIC_MOD_COUNT). Если выпал один нужный мод и
    второй слот может дать недостающий — аугаем. Для пары «префикс + суффикс» итоговый шанс
    не зависит от того, как часто выпадает 1 или 2 мода.
    """
    from .pool import MAGIC_MOD_COUNT
    wsum = sum(w for _, w in MAGIC_MOD_COUNT)
    p_n = {n: w / wsum for n, w in MAGIC_MOD_COUNT}
    first = pool.candidates([], "Magic")
    tot1 = sum(e.weight for e in first)
    dist: dict[frozenset, float] = {}
    e_aug = 0.0

    def add(key, pr):
        dist[key] = dist.get(key, 0.0) + pr

    for e1 in first:
        p1 = e1.weight / tot1
        h1 = frozenset(_hits([e1], targets))
        second = pool.candidates([e1.mod], "Magic")
        tot2 = sum(e.weight for e in second)
        # n = 2: второй мод выпадает сам
        if tot2:
            for e2 in second:
                add(h1 | _hits([e2], targets), p_n.get(2, 0) * p1 * e2.weight / tot2)
        else:
            add(h1, p_n.get(2, 0) * p1)
        # n = 1: аугаем, если есть нужный мод и второй слот может дать недостающее
        free_kind = "suffix" if e1.mod.kind == "prefix" else "prefix"
        if h1 and tot2 and any(t.kind == free_kind for t in targets if t not in h1):
            e_aug += p_n.get(1, 0) * p1
            for e2 in second:
                add(h1 | _hits([e2], targets), p_n.get(1, 0) * p1 * e2.weight / tot2)
        else:
            add(h1, p_n.get(1, 0) * p1)
    p_all = sum(pr for k, pr in dist.items() if len(k) == len(targets))
    return p_all, e_aug, dist


def method_alt(pool: ModPool, targets: list[Target], prices: Prices, rng) -> dict | None:
    kinds = [t.kind for t in targets]
    if len(targets) > 2 or kinds.count("prefix") > 1 or kinds.count("suffix") > 1:
        return None
    p, e_aug, _ = _magic_outcomes(pool, targets)
    use = {"Orb of Alteration": 1, "Orb of Augmentation": e_aug}
    per = sum(prices.get(k) * v for k, v in use.items())
    return _result("Alteration + Augmentation",
                   "Альтаем синий предмет, аугаем, если выпал один нужный мод и свободен второй слот.",
                   p, use, per, prices)


def method_alt_regal(pool: ModPool, targets: list[Target], prices: Prices, rng) -> dict | None:
    """Alt+Aug до двух нужных модов, затем Regal на третий. Неудача → Scour + Transmute заново."""
    if len(targets) != 3:
        return None
    kinds = [t.kind for t in targets]
    if kinds.count("prefix") > 2 or kinds.count("suffix") > 2:
        return None

    _, e_aug, dist = _magic_outcomes(pool, targets)
    pairs = {k: pr for k, pr in dist.items() if len(k) >= 2}
    p1 = sum(pairs.values())
    if p1 <= 0:
        return _result("Alt → Aug → Regal", "Два нужных мода на синем предмете не собрать.", 0, {}, 0, prices)
    alts1 = 1 / p1
    augs1 = e_aug / p1

    # Шанс Regal'а добить третий мод (взвешиваем по тому, какую пару собрали)
    p2 = 0.0
    for key, pr in pairs.items():
        missing = [t for t in targets if t not in key]
        present = [next(e for e in pool.available if t.ok(e)).mod for t in key]
        p2 += (pr / p1) * pool.chance_add(present, "Rare", lambda e: any(t.ok(e) for t in missing))
    if p2 <= 0:
        return _result("Alt → Aug → Regal", "Regal не может дать недостающий мод.", 0, {}, 0, prices)

    cycle = {"Orb of Alteration": alts1, "Orb of Augmentation": augs1, "Regal Orb": 1}
    fail = {"Orb of Scouring": 1, "Orb of Transmutation": 1}
    use = {k: v / p2 for k, v in cycle.items()}
    for k, v in fail.items():
        use[k] = use.get(k, 0) + v * (1 / p2 - 1)
    total = sum(prices.get(k) * v for k, v in use.items())
    return {
        "name": "Alt → Aug → Regal",
        "how": "Собираем два нужных мода на синем предмете альтами, Regal на третий. "
               "Если Regal промахнулся — Scour, Transmute и заново.",
        "chance": p2, "chance_label": f"Шанс Regal'а: {p2:.1%}; синий с 2 нужными модами: 1 из ~{alts1:.0f} альтов",
        "attempts": 1 / p2, "use": use, "cost_chaos": total, "cost_div": total / prices.divine,
        "simulated": False,
    }


def _result(name, how, p, per_try, per_cost, prices, simulated=False):
    if p <= 0:
        return {"name": name, "how": how, "chance": 0, "attempts": None, "use": {},
                "cost_chaos": None, "cost_div": None, "simulated": simulated}
    n = 1 / p
    use = {k: v * n for k, v in per_try.items()}
    total = per_cost * n
    return {"name": name, "how": how, "chance": p, "attempts": n, "use": use,
            "cost_chaos": total, "cost_div": total / prices.divine, "simulated": simulated}


def calculate(pool: ModPool, targets: list[Target], prices: Prices, seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    out = []
    for fn in (method_alt, method_alt_regal, method_chaos):
        r = fn(pool, targets, prices, rng)
        if r:
            out.append(r)
    out.sort(key=lambda r: (r["cost_chaos"] is None, r["cost_chaos"] or 0))
    return out
