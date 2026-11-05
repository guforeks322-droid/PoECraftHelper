"""Эссенции и фоссилы: изменённые пулы модов и расчёт спама."""

from __future__ import annotations

import copy
import itertools
import json
import random
from dataclasses import dataclass
from functools import lru_cache

from .data import GameData, ModDef
from .pool import ModPool, PoolEntry
from .prices import Prices
from .pool import yield_ui

RESONATORS = {1: "Primitive Chaotic Resonator", 2: "Potent Chaotic Resonator",
              3: "Powerful Chaotic Resonator", 4: "Prime Chaotic Resonator"}

# Фоссилы с эффектами, которые пока не моделируем (влияют не на веса модов)
SPECIAL_FOSSILS = {
    "Fractured Fossil": "создаёт копию предмета с фрактурой одного мода",
    "Gilded Fossil": "повышает цену продажи вендору",
    "Sanctified Fossil": "значения модов роллятся «удачно», но тиров выпадает меньше",
    "Glyphic Fossil": "добавляет шанс мода от осквернённой эссенции",
    "Tangled Fossil": "добавляет шанс мода от осквернённой эссенции",
    "Hollow Fossil": "добавляет гнездо для самоцвета Бездны",
    "Bloodstained Fossil": "добавляет Vaal-импликит",
}


def _raw_mods(data: GameData) -> dict:
    if not hasattr(data, "_raw_mods_cache"):
        data._raw_mods_cache = data._load("mods")
    return data._raw_mods_cache


def _moddef(mid: str, m: dict) -> ModDef:
    return ModDef(mid, m.get("name", ""), m["generation_type"], m.get("type", ""), tuple(m.get("groups", [])),
                  m.get("required_level", 1), m.get("text", "") or "", tuple(m.get("implicit_tags", [])),
                  tuple(m.get("spawn_weights", [])), tuple(m.get("generation_weights", [])))


# ------------------------------------------------------------------ эссенции
@dataclass
class Essence:
    id: str
    name: str
    tier: int
    max_ilvl: int | None
    mod: ModDef


def essences_for(data: GameData, item_class: str) -> list[Essence]:
    raw = _raw_mods(data)
    out = []
    for eid, e in data._load("essences").items():
        mid = e.get("mods", {}).get(item_class)
        m = raw.get(mid) if mid else None
        if not m or m.get("generation_type") not in ("prefix", "suffix"):
            continue
        out.append(Essence(eid, e["name"], e.get("level", 0), e.get("item_level_restriction"), _moddef(mid, m)))
    out.sort(key=lambda x: (x.name.split(" of ")[-1], x.tier))
    return out


def essence_entry(pool: ModPool, mod: ModDef) -> PoolEntry:
    """Мод эссенции как запись пула; тир — относительно обычных тиров того же типа."""
    better = sum(1 for e in pool.all if e.mod.kind == mod.kind and e.mod.type == mod.type and e.mod.level > mod.level)
    return PoolEntry(mod, 0, better + 1)


# ------------------------------------------------------------------ фоссилы
@dataclass
class Fossil:
    id: str
    name: str
    multipliers: tuple    # ((tag, weight/100), ...)
    added: tuple          # id модов, которые фоссил добавляет
    special: str = ""

    @property
    def describe(self) -> str:
        parts = []
        for tag, k in self.multipliers:
            parts.append(f"{tag} ×{k:g}" if k else f"нет {tag}")
        if self.added:
            parts.append(f"+{len(self.added)} особых модов")
        if self.special:
            parts.append(self.special)
        return ", ".join(parts)


def fossils(data: GameData) -> list[Fossil]:
    if hasattr(data, "_fossils_cache"):
        return data._fossils_cache
    out = []
    for fid, f in data._load("fossils").items():
        if not f["name"].endswith("Fossil"):
            continue
        mult = tuple((w["tag"], w["weight"] / 100) for w in f["positive_mod_weights"] + f["negative_mod_weights"])
        out.append(Fossil(fid, f["name"], mult, tuple(f.get("added_mods", [])), SPECIAL_FOSSILS.get(f["name"], "")))
    out.sort(key=lambda x: x.name)
    data._fossils_cache = out
    return out


def fossil_pool(data: GameData, pool: ModPool, chosen: list[Fossil]) -> ModPool:
    """Копия пула с весами, изменёнными фоссилами (множители перемножаются)."""
    fp = copy.copy(pool)
    entries = []
    for e in pool.available:
        k = 1.0
        for f in chosen:
            for tag, mult in f.multipliers:
                if tag in e.mod.tags:
                    k *= mult
        w = int(round(e.weight * k))
        if w > 0:
            entries.append(PoolEntry(e.mod, w, e.tier))
    raw = _raw_mods(data)
    seen = {e.mod.id for e in entries}
    for f in chosen:
        for mid in f.added:
            m = raw.get(mid)
            if not m or mid in seen or m.get("generation_type") not in ("prefix", "suffix"):
                continue
            md = _moddef(mid, m)
            if md.level > pool.ilvl:
                continue
            w = md.weight_for(pool.tags)
            if w > 0:
                entries.append(PoolEntry(md, w, 1))
                seen.add(mid)
    fp.available = entries
    return fp


# ------------------------------------------------------------------ симуляция
def _roller(pool: ModPool, rng, fixed: list[PoolEntry] | None = None):
    import bisect
    from itertools import accumulate
    from .pool import RARE_MOD_COUNT
    ents = pool.available
    if not ents:
        return lambda: list(fixed or [])
    cum = list(accumulate(e.weight for e in ents))
    total = cum[-1]
    max_p, max_s = pool.limits("Rare")
    counts = [c for c, _ in RARE_MOD_COUNT]
    cw = [w for _, w in RARE_MOD_COUNT]
    fixed = fixed or []
    g0 = set(g for f in fixed for g in f.mod.groups)
    p0 = sum(1 for f in fixed if f.mod.kind == "prefix")
    s0 = len(fixed) - p0

    def roll():
        n = rng.choices(counts, weights=cw)[0]
        got, groups, np_, ns = list(fixed), set(g0), p0, s0
        guard = 0
        while len(got) < n and guard < 600 and (np_ < max_p or ns < max_s):
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


def simulate(pool: ModPool, targets, fixed=None, seed=11, min_hits=300, max_trials=150_000):
    rng = random.Random(seed)
    roll = _roller(pool, rng, fixed)
    need = len(targets)
    hits = trials = 0
    while trials < max_trials and (hits < min_hits or trials < 10_000):
        for _ in range(5000):
            trials += 1
            if not trials % 2000:
                yield_ui()
            got = roll()
            if sum(1 for t in targets if any(t.ok(e) for e in got)) == need:
                hits += 1
    return hits / trials, hits, trials


def _card(name, how, p, hits, trials, per_try: dict, prices: Prices, extra_note=""):
    if p <= 0:
        return {"name": name, "how": how, "chance": 0, "attempts": None, "use": {}, "cost_chaos": None,
                "cost_div": None, "simulated": True, "chance_label": "Ни одного попадания в симуляции — так не выйдет.",
                "note": extra_note}
    n = 1 / p
    use = {k: v * n for k, v in per_try.items()}
    missing = [k for k in per_try if prices.get(k) <= 0]
    cost = None if missing else sum(prices.get(k) * v for k, v in use.items())
    if missing:
        extra_note = ("; ".join(x for x in (extra_note, "нет цены на poe.ninja: " + ", ".join(missing)) if x))
    err = 1 / hits ** 0.5
    tr = f"{trials:,}".replace(",", " ")
    att = f"{n:,.0f}".replace(",", " ")
    return {"name": name, "how": how, "chance": p, "attempts": n, "use": use, "cost_chaos": cost,
            "cost_div": cost / prices.divine if cost is not None else None, "simulated": True, "note": extra_note,
            "chance_label": f"Шанс за попытку: {p:.3%} (±{err:.0%}, {tr} роллов) · в среднем ~{att} попыток"}


def method_essence(pool: ModPool, targets, ess: Essence, prices: Prices) -> dict:
    fixed = essence_entry(pool, ess.mod)
    # мод эссенции занимает свою группу; убираем из пула моды той же группы
    p, h, t = simulate(pool, targets, [fixed])
    note = ""
    if ess.max_ilvl and pool.ilvl > ess.max_ilvl:
        note = f"Эта эссенция работает только на предметах до ilvl {ess.max_ilvl}."
    return _card(f"Спам: {ess.name}",
                 f"Гарантирует «{ess.mod.text.splitlines()[0]}» (как T{fixed.tier}), остальные моды случайны.",
                 p, h, t, {ess.name: 1}, prices, note)


def method_fossils(data: GameData, pool: ModPool, targets, chosen: list[Fossil], prices: Prices) -> dict:
    fp = fossil_pool(data, pool, chosen)
    p, h, t = simulate(fp, targets)
    per = {f.name: 1 for f in chosen}
    per[RESONATORS[len(chosen)]] = 1
    special = [f"{f.name}: {f.special} (не учитывается)" for f in chosen if f.special]
    return _card("Фоссилы: " + " + ".join(f.name.replace(" Fossil", "") for f in chosen),
                 "Резонатор с фоссилами: " + "; ".join(f"{f.name.replace(' Fossil', '')} — {f.describe}" for f in chosen),
                 p, h, t, per, prices, "; ".join(special))


def best_essences(data, pool, targets, prices, top=3) -> list[dict]:
    """Эссенции, мод которых закрывает одну из целей, — считаем каждую."""
    out = []
    for ess in essences_for(data, pool.base.item_class):
        fe = essence_entry(pool, ess.mod)
        if not any(t.ok(fe) for t in targets):
            continue
        if ess.max_ilvl and pool.ilvl > ess.max_ilvl:
            continue
        out.append(method_essence(pool, targets, ess, prices))
    # сначала с известной ценой (по стоимости), потом без цены (по шансу)
    out.sort(key=lambda r: (r["cost_chaos"] is None, r["cost_chaos"] or 0, -(r["chance"] or 0)))
    return out[:top]


def best_fossils(data, pool, targets, prices, top=3, max_fossils=4) -> list[dict]:
    """Перебираем полезные фоссилы: быстрая оценка по весам, затем симуляция лучших."""
    useful = []
    tgt_tags = set()
    for t in targets:
        for e in pool.available:
            if t.ok(e):
                tgt_tags.update(e.mod.tags)
    for f in fossils(data):
        if f.special:
            continue
        if not any(k == 0 and tag in tgt_tags for tag, k in f.multipliers):  # не режем нужное
            boosts = any(k > 1 and tag in tgt_tags for tag, k in f.multipliers)
            cuts = any(k < 1 and tag not in tgt_tags for tag, k in f.multipliers)
            if boosts or cuts:
                useful.append(f)
    if not useful:
        return []

    def score(combo):
        fp = fossil_pool(data, pool, list(combo))
        tot = {"prefix": 0, "suffix": 0}
        for e in fp.available:
            tot[e.mod.kind] += e.weight
        s = 1.0
        for t in targets:
            w = sum(e.weight for e in fp.available if t.ok(e))
            s *= (w / tot[t.kind]) if tot[t.kind] else 0
        cost = sum(prices.get(f.name) or 50 for f in combo) + (prices.get(RESONATORS[len(combo)]) or 5)
        return (s / cost) if s else 0

    combos = []
    for n in range(1, min(max_fossils, len(useful)) + 1):
        combos += list(itertools.combinations(useful, n))
    combos.sort(key=score, reverse=True)
    res = [method_fossils(data, pool, targets, list(c), prices) for c in combos[:6]]
    res.sort(key=lambda r: (r["cost_chaos"] is None, r["cost_chaos"] or 0))
    return res[:top]
