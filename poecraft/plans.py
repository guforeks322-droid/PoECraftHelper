"""Рецепты крафта с развилками: шаги «что кинуть», «повторять, пока…», «если не вышло — …».

Рецепт — список шагов (JSON, хранится в крафте и в коде PCH1):
    {"do": "chaos", "kw": {}, "until": {"t": "goal"}, "max": 300, "else": "stop"}
    {"do": "exalt", "if": {"t": "free", "kind": "suffix"}, "else": 5}
Поля:
    do     — действие эмулятора (chaos, exalt, essence, fossils, bench, …) или "altaug" (Alt и Aug при свободном слоте)
    kw     — параметры: essence → имя эссенции, fossils → список имён, bench → id мода верстака …
    if     — условие перед шагом; не выполнено → переход по else
    until  — повторять действие, пока условие не выполнится (не больше max раз); не вышло → переход по else
    else   — "next" (дальше), "stop" (неудача), число (перейти к шагу N, с нуля)
Условия:
    {"t": "goal"}               все нужные моды есть
    {"t": "count", "n": 2}      есть хотя бы n нужных модов
    {"t": "has", "i": 0}        есть нужный мод №i
    {"t": "free", "kind": "prefix"|"suffix"}   свободный слот
    {"t": "rarity", "v": "Magic"}
    {"t": "not", "c": {...}}
"""

from __future__ import annotations

import random

from . import currency_craft as cc
from .emulator import CraftError, Emulator
from .pool import yield_ui

ACTIONS = [  # (действие, подпись, параметр)
    ("transmute", "Transmutation", None), ("altaug", "Alteration (+Aug)", None), ("alteration", "Alteration", None),
    ("augment", "Augmentation", None), ("regal", "Regal", None), ("alchemy", "Alchemy", None),
    ("chaos", "Chaos", None), ("exalt", "Exalted", None), ("annul", "Annulment", None),
    ("scour", "Scouring", None), ("divine", "Divine", None), ("essence", "Эссенция", "essence"),
    ("fossils", "Фоссилы", "fossils"), ("bench", "Верстак", "bench"), ("remove_crafted", "Снять крафты", None),
    ("conqueror", "Exalt завоевателя", "conqueror"), ("harvest_reforge", "Harvest Reforge", "harvest"),
    ("eldritch_chaos", "Eldritch Chaos", None), ("eldritch_exalt", "Eldritch Exalt", None),
    ("eldritch_annul", "Eldritch Annul", None), ("veiled_chaos", "Veiled Chaos", None),
    ("beast_prefix", "Зверь: +префикс −суффикс", None), ("beast_suffix", "Зверь: +суффикс −префикс", None),
]
ACTION_LABEL = {a: l for a, l, _ in ACTIONS}
ACTION_PARAM = {a: p for a, _, p in ACTIONS}

CONDITIONS = [  # подпись → условие (для выпадающих списков)
    ("—", None),
    ("все нужные моды", {"t": "goal"}),
    ("ещё не все нужные моды", {"t": "not", "c": {"t": "goal"}}),
    ("хотя бы 1 нужный мод", {"t": "count", "n": 1}),
    ("хотя бы 2 нужных мода", {"t": "count", "n": 2}),
    ("хотя бы 3 нужных мода", {"t": "count", "n": 3}),
    ("есть свободный префикс", {"t": "free", "kind": "prefix"}),
    ("есть свободный суффикс", {"t": "free", "kind": "suffix"}),
    ("нет свободного префикса", {"t": "not", "c": {"t": "free", "kind": "prefix"}}),
    ("нет свободного суффикса", {"t": "not", "c": {"t": "free", "kind": "suffix"}}),
    ("предмет обычный", {"t": "rarity", "v": "Normal"}),
    ("предмет магический", {"t": "rarity", "v": "Magic"}),
    ("предмет редкий", {"t": "rarity", "v": "Rare"}),
]


def cond_label(c) -> str:
    for label, cc_ in CONDITIONS:
        if cc_ == c:
            return label
    if c and c.get("t") == "has":
        return f"есть нужный мод №{c['i'] + 1}"
    return "—" if not c else str(c)


def step_text(s: dict, targets=()) -> str:
    """Человеческое описание шага для списка."""
    a = ACTION_LABEL.get(s.get("do"), s.get("do"))
    kw = s.get("kw") or {}
    if kw.get("essence"):
        a += f": {kw['essence']}"
    if kw.get("fossils"):
        a += ": " + " + ".join(x.replace(" Fossil", "") for x in kw["fossils"])
    if kw.get("bench_text"):
        a += f": {kw['bench_text']}"
    if kw.get("name"):
        a += f": {kw['name']}"
    if kw.get("label"):
        a += f" ({kw['label']})"
    parts = []
    if s.get("if"):
        parts.append(f"если {cond_label(s['if'])}")
    parts.append(a)
    if s.get("until"):
        parts.append(f"↻ пока не {cond_label(s['until'])} (≤{s.get('max', 300)})")
    tail = s.get("else", "next")
    if s.get("if") or s.get("until"):
        parts.append({"next": "· иначе дальше", "stop": "· иначе стоп"}.get(tail, f"· иначе → шаг {int(tail) + 1}"
                                                                         if isinstance(tail, int) else ""))
    return "  ".join(p for p in parts if p)


# ------------------------------------------------------------------ шаблоны
def presets(goal_n: int) -> dict[str, list]:
    need = {"t": "goal"}
    return {
        "Alt+Aug → Regal → Exalt": [
            {"do": "transmute", "if": {"t": "rarity", "v": "Normal"}, "else": "next"},
            {"do": "altaug", "until": {"t": "count", "n": min(2, goal_n)}, "max": 3000, "else": "stop"},
            {"do": "regal"},
            {"do": "exalt", "if": {"t": "not", "c": need}, "else": "next"},
        ],
        "Chaos до цели": [
            {"do": "alchemy", "if": {"t": "rarity", "v": "Normal"}, "else": "next"},
            {"do": "chaos", "if": {"t": "not", "c": need}, "until": need, "max": 5000, "else": "stop"},
        ],
        "Эссенция до цели": [
            {"do": "essence", "kw": {"essence": ""}, "until": need, "max": 3000, "else": "stop"},
        ],
        "Фоссилы до цели": [
            {"do": "fossils", "kw": {"fossils": []}, "until": need, "max": 3000, "else": "stop"},
        ],
        "Эссенция → блок префиксов → Exalt": [
            {"do": "essence", "kw": {"essence": ""}, "until": {"t": "count", "n": max(1, goal_n - 1)}, "max": 3000,
             "else": "stop"},
            {"do": "bench", "kw": {"meta": "suffix_lock"}, "if": {"t": "free", "kind": "suffix"}, "else": 0},
            {"do": "exalt"},
            {"do": "remove_crafted"},
        ],
    }


# ------------------------------------------------------------------ выполнение
class PlanRunner:
    def __init__(self, data, em: Emulator, targets, trim_history: bool = True):
        self.data, self.em, self.targets = data, em, list(targets)
        self.trim_history = trim_history
        self._ess = {e.name: e for e in cc.essences_for(data, em.pool.base.item_class)}
        self._fos = {f.name: f for f in cc.fossils(data)}

    # условия
    def have(self) -> list[bool]:
        return [any(not m.crafted and t.ok(m.entry) for m in self.em.mods) for t in self.targets]

    def check(self, c) -> bool:
        if not c:
            return True
        t = c.get("t")
        if t == "goal":
            return all(self.have()) if self.targets else False
        if t == "count":
            return sum(self.have()) >= c.get("n", 1)
        if t == "has":
            h = self.have()
            return 0 <= c.get("i", 0) < len(h) and h[c["i"]]
        if t == "free":
            mp, ms = self.em.limits()
            if self.em.rarity == "Magic":
                mp = ms = 1
            return (len(self.em.prefixes) < mp) if c.get("kind") == "prefix" else (len(self.em.suffixes) < ms)
        if t == "rarity":
            return self.em.rarity == c.get("v")
        if t == "not":
            return not self.check(c.get("c"))
        return False

    # действия
    def do(self, step):
        a, kw = step["do"], dict(step.get("kw") or {})
        em = self.em
        if a == "altaug":
            em.apply("alteration")
            if em.rarity == "Magic" and len(em.mods) == 1 and not self.check({"t": "goal"}):
                em.apply("augment")
            return
        if a == "essence":
            e = self._ess.get(kw.get("essence", ""))
            if not e:
                raise CraftError("В шаге не выбрана эссенция.")
            return em.apply("essence", essence=e)
        if a == "fossils":
            fos = [self._fos[n] for n in kw.get("fossils", []) if n in self._fos]
            if not fos:
                raise CraftError("В шаге не выбраны фоссилы.")
            return em.apply("fossils", fossils=fos)
        if a == "bench":
            opts = em.bench_options()
            o = None
            if kw.get("meta"):
                o = next((x for x in opts if em._meta_of(x) == kw["meta"]), None)
            elif kw.get("bench"):
                o = next((x for x in opts if x["mod"].id == kw["bench"]), None)
            if not o:
                raise CraftError("Такого крафта верстака нет для этой базы.")
            return em.apply("bench", option=o)
        kw.pop("bench_text", None)
        return em.apply(a, **kw)

    def run(self, steps: list, op_limit: int = 30000) -> dict:
        """Один предмет по рецепту. Возвращает {'ok', 'ops', 'per_step', 'error'}."""
        pc, ops = 0, 0
        per_step = [0] * len(steps)
        jumps = 0
        while 0 <= pc < len(steps) and ops < op_limit:
            s = steps[pc]
            target = None
            if s.get("if") and not self.check(s["if"]):
                target = s.get("else", "next")
            else:
                try:
                    if s.get("until"):
                        n = 0
                        while not self.check(s["until"]) and n < int(s.get("max", 300)):
                            self.do(s)
                            n += 1
                            if not n % 400:
                                yield_ui()
                            per_step[pc] += 1
                            if self.trim_history and len(self.em.history) > 30:
                                del self.em.history[:]
                        ops += n
                        if not self.check(s["until"]):
                            target = s.get("else", "stop")
                    else:
                        self.do(s)
                        per_step[pc] += 1
                        ops += 1
                except CraftError as e:
                    if s.get("if") or s.get("until"):
                        target = s.get("else", "stop")
                    else:
                        return {"ok": False, "ops": ops, "per_step": per_step, "error": f"шаг {pc + 1}: {e}"}
            if target is None or target == "next":
                pc += 1
            elif target == "stop":
                return {"ok": self.check({"t": "goal"}), "ops": ops, "per_step": per_step, "error": None}
            else:
                jumps += 1
                if jumps > 2000:
                    break
                pc = int(target)
        return {"ok": self.check({"t": "goal"}), "ops": ops, "per_step": per_step, "error": None}


def simulate(data, em: Emulator, targets, steps, n: int, prices, time_budget: float = 30.0, progress=None) -> dict:
    """N предметов по рецепту от текущего состояния эмулятора. Предмет в эмуляторе не меняется."""
    import time
    start = em.snapshot()
    hist = list(em.history)
    rng_state = em.rng.getstate()
    runner = PlanRunner(data, em, targets)
    ok = 0
    costs, ops, per_step, errors = [], [], [0] * len(steps), []
    t0 = time.time()
    done = 0
    for i in range(n):
        em.restore(start, copy=True)
        em.rng = random.Random()
        r = runner.run(steps)
        done += 1
        if r["error"]:
            errors.append(r["error"])
            if len(errors) > 3 and ok == 0:
                break
        ok += bool(r["ok"])
        ops.append(r["ops"])
        per_step = [a + b for a, b in zip(per_step, r["per_step"])]
        costs.append(sum(prices.get(k) * (v - start[2].get(k, 0)) for k, v in em.spent.items()))
        if progress and i % 10 == 0:
            progress(i, n)
        if time.time() - t0 > time_budget:
            break
    em.restore(start)
    em.history = hist
    em.rng.setstate(rng_state)
    total = sum(costs)
    return {"items": done, "ok": ok, "rate": ok / done if done else 0, "avg_cost": total / done if done else 0,
            "cost_per_success": total / ok if ok else None, "avg_ops": sum(ops) / done if done else 0,
            "per_step": [x / done for x in per_step] if done else per_step, "errors": errors[:3]}
