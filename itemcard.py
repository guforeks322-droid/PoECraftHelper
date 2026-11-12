"""Карточка предмета для эмулятора — в духе подсказки из игры.

Шапка цвета редкости, картинка базы, имплициты, моды с метками тиров и полосками
качества ролла, подсветка того, что изменило последнее действие, и лента истории
крафта (клик по шагу — откатиться к нему). Рамку и разделители рисуем сами.
"""

from __future__ import annotations

import re
import tkinter as tk

from poecraft import icons
from poecraft import influence as inf

BG = "#0c0a08"
PANEL = "#100e0b"
FG, MUTED, DIM, GOLD, GOOD, WARN = "#d9d0c1", "#8a7f70", "#5a5248", "#e3b55b", "#7ec27a", "#e07a5f"
from poecraft import fonts as _fonts
FONT = _fonts.UI
TFONT = _fonts.TITLE   # заголовки
MOD_FG = "#8f9cff"          # явные моды — синие, как в игре
IMPLICIT_FG = "#8f9cff"
CRAFT_FG = "#b8c4ff"
FRAC_FG = "#a29162"
VEIL_FG = "#d4a44c"
INFL_FG = "#c39bd3"
RARITY = {  # (рамка, шапка, текст имени)
    "Normal": ("#6e6e6e", "#1d1c1a", "#d0d0d0"),
    "Magic": ("#4a4fa8", "#13162b", "#8f9cff"),
    "Rare": ("#a8933c", "#2a2410", "#f0dc78"),
}
FLASH_NEW, FLASH_CHANGED = "#1d3b1f", "#3d3414"
RANGE_RE = re.compile(r"\((-?[\d.]+)-(-?[\d.]+)\)")


def roll_quality(text: str, values: list) -> float | None:
    """Где стоит ролл внутри диапазона: 0 — минимум, 1 — максимум (для гибридов — среднее)."""
    ranges = RANGE_RE.findall(text)
    if not ranges or not values or len(ranges) != len(values):
        return None
    qs = []
    for (lo, hi), v in zip(ranges, values):
        lo, hi = abs(float(lo)), abs(float(hi))
        lo, hi = min(lo, hi), max(lo, hi)
        qs.append(1.0 if hi == lo else max(0.0, min(1.0, (abs(float(v)) - lo) / (hi - lo))))
    return sum(qs) / len(qs)


def quality_color(q: float) -> str:
    return GOOD if q >= 0.67 else (GOLD if q >= 0.34 else WARN)


class ItemCard(tk.Frame):
    def __init__(self, master, data, on_rewind=None):
        super().__init__(master, bg=BG, highlightthickness=2, highlightbackground=RARITY["Normal"][0])
        self.data = data
        self.on_rewind = on_rewind
        self._prev: dict | None = None
        self._prev_key = None
        # карточка прокручивается колесом, если модов и пометок много
        self._cv = tk.Canvas(self, bg=BG, highlightthickness=0, bd=0)
        self._cv.pack(fill="both", expand=True)
        self.body = tk.Frame(self._cv, bg=BG)
        self._win = self._cv.create_window(0, 0, window=self.body, anchor="nw")
        self.body.bind("<Configure>", lambda e: self._cv.configure(scrollregion=self._cv.bbox("all")))
        self._cv.bind("<Configure>", lambda e: self._cv.itemconfigure(self._win, width=e.width))
        for w in (self._cv, self.body):
            w.bind("<MouseWheel>", self._wheel)
            w.bind("<Button-4>", lambda e: self._cv.yview_scroll(-2, "units"))
            w.bind("<Button-5>", lambda e: self._cv.yview_scroll(2, "units"))
        self.empty()

    # ------------------------------------------------------------ служебное
    def _clear(self):
        for w in self.body.winfo_children():
            w.destroy()

    def empty(self, text="Выбери базу сверху и нажми «Новый белый предмет»\nили «Предмет из игры»."):
        self._clear()
        self.configure(highlightbackground=RARITY["Normal"][0])
        tk.Label(self.body, text=text, bg=BG, fg=MUTED, font=(FONT, 10), justify="center").pack(expand=True, pady=40)

    def _sep(self, color):
        c = tk.Canvas(self.body, height=9, bg=BG, highlightthickness=0, bd=0)
        c.pack(fill="x", padx=18, pady=3)

        def draw(e=None):
            c.delete("all")
            w = c.winfo_width()
            if w < 10:
                return
            m = w // 2
            c.create_line(0, 4, m - 8, 4, fill=color)
            c.create_line(m + 8, 4, w, 4, fill=color)
            c.create_polygon(m, 0, m + 5, 4, m, 8, m - 5, 4, fill=color, outline="")
        c.bind("<Configure>", draw)

    def _flash(self, widgets, color, base, step=0, steps=10):
        """Плавно гасим подсветку строки: color → base."""
        if step > steps:
            return
        t = step / steps
        c1 = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
        c2 = [int(base[i:i + 2], 16) for i in (1, 3, 5)]
        mix = "#" + "".join(f"{round(a + (b - a) * t):02x}" for a, b in zip(c1, c2))
        alive = [w for w in widgets if w.winfo_exists()]
        for w in alive:
            try:
                w.configure(bg=mix)
            except tk.TclError:
                pass
        if alive:
            self.after(70 if step else 350, lambda: self._flash(alive, color, base, step + 1, steps))

    # ------------------------------------------------------------ отрисовка
    def render(self, em, targets=(), prices=None, steps=(), chances=None):
        """steps/chances больше не рисуются в карточке — они справа (журнал и цели)."""
        if em is None:
            self._prev = None
            return self.empty()
        self._clear()
        self.after_idle(self._bind_click)
        border, head_bg, name_fg = RARITY.get(em.rarity, RARITY["Normal"])
        self.configure(highlightbackground=border)
        base = em.pool.base
        st = icons.store()

        # что изменилось с прошлого раза (для подсветки)
        key = (base.id, em.pool.ilvl)
        prev = self._prev if self._prev_key == key else None
        cur = {}
        for m in em.mods:
            cur.setdefault(m.mod.id, []).append(tuple(m.values))
        self._prev, self._prev_key = cur, key

        # шапка
        head = tk.Frame(self.body, bg=head_bg)
        head.pack(fill="x")
        title = {"Normal": base.name, "Magic": "Магический " + base.name, "Rare": "Редкий предмет"}[em.rarity]
        tk.Label(head, text=title, bg=head_bg, fg=name_fg, font=(TFONT, 15)).pack(pady=(6, 0))
        if em.rarity == "Rare":
            tk.Label(head, text=base.name, bg=head_bg, fg=name_fg, font=(FONT, 11)).pack()
        mp, ms = em.limits()
        if em.rarity == "Magic":
            mp = ms = 1
        sub = f"ilvl {em.pool.ilvl}  ·  префиксы {len(em.prefixes)}/{mp}  ·  суффиксы {len(em.suffixes)}/{ms}"
        tk.Label(head, text=sub, bg=head_bg, fg=MUTED, font=(FONT, 8)).pack(pady=(0, 6))
        st_ = getattr(em, "state", {})
        flags = []
        if st_.get("catalyst"):
            flags.append((f"Качество {st_.get('quality', 0)}% · {st_['catalyst'].replace(' Catalyst', '')}", GOLD))
        if st_.get("split"):
            flags.append(("Split", MUTED))
        if st_.get("imprint"):
            flags.append(("есть отпечаток", MUTED))
        if st_.get("destroyed"):
            flags.append(("Уничтожен", "#ff5050"))
        elif st_.get("twice"):
            flags.append(("Дважды осквернён", "#d24a4a"))
        elif st_.get("corrupted"):
            flags.append(("Осквернён", "#d24a4a"))
        if flags:
            fr = tk.Frame(head, bg=head_bg)
            fr.pack(pady=(0, 6))
            for t, c in flags:
                tk.Label(fr, text=t, bg=head_bg, fg=c, font=(FONT, 8, "bold")).pack(side="left", padx=5)

        # картинка базы + иконки влияний
        raw = self.data.base_raw.get(base.id, {})
        dds = (raw.get("visual_identity") or {}).get("dds_file", "")
        art = st.base_art(base.id, dds, 92, 110) if st else None
        if art is not None or em.influences:
            ar = tk.Frame(self.body, bg=PANEL)
            ar.pack(fill="x")
            if art is not None:
                l = tk.Label(ar, image=art, bg=PANEL)
                l._img = art
                l.pack(pady=6)
            if em.influences:
                ir = tk.Frame(ar, bg=PANEL)
                ir.pack(pady=(0, 6))
                for n in em.influences:
                    img = st.get(n, 22) if st else None
                    l = tk.Label(ir, image=img, text="" if img else n, bg=PANEL, fg=INFL_FG, font=(FONT, 8),
                                 compound="left")
                    l._img = img
                    l.pack(side="left", padx=3)

        # имплициты базы и Eldritch
        impl = []
        from poecraft import currency_craft as cc
        rawmods = cc._raw_mods(self.data)
        for mid in raw.get("implicits", []):
            t = (rawmods.get(mid) or {}).get("text", "")
            if t and "Has 1 Abyssal Socket" not in t:
                impl.append((t.replace("\n", " / "), IMPLICIT_FG))
        if "AbyssJewelSocketImplicit" in raw.get("implicits", []):
            impl.append(("Has 1 Abyssal Socket", IMPLICIT_FG))
        for side, ttl in (("exarch", "Searing Exarch"), ("eater", "Eater of Worlds")):
            e = getattr(em, side)
            if e:
                dom = "  ◆" if em.dominance() == side else ""
                impl.append((f"{e.text}   [{ttl} · {inf.ELDRITCH_TIERS[e.level]}]{dom}", CRAFT_FG))
        for n in st_.get("notes", []):
            impl.append((n, "#d24a4a" if n.startswith("Vaal") else MUTED))
        if impl:
            self._sep(border)
            for t, c in impl:
                tk.Label(self.body, text=t, bg=BG, fg=c, font=(FONT, 9), wraplength=420).pack()

        # моды
        self._sep(border)
        if not em.mods:
            tk.Label(self.body, text="модов нет", bg=BG, fg=DIM, font=(FONT, 9)).pack(pady=4)
        removed = []
        if prev is not None:
            for mid, vals in prev.items():
                left = len(cur.get(mid, []))
                if left < len(vals):
                    removed.append(mid)
        for kind, cap in (("prefix", "ПРЕФИКСЫ"), ("suffix", "СУФФИКСЫ")):
            mods = [m for m in em.mods if m.kind == kind]
            gone = [mid for mid in removed if self._kind_of(mid, em) == kind]
            if not mods and not gone:
                continue
            tk.Label(self.body, text=cap, bg=BG, fg=DIM, font=(FONT, 7, "bold"), anchor="w").pack(fill="x", padx=14,
                                                                                                    pady=(4, 0))
            for m in mods:
                state = None
                if prev is not None:
                    if m.mod.id not in prev:
                        state = "new"
                    elif tuple(m.values) not in prev[m.mod.id]:
                        state = "changed"
                self._mod_row(m, targets, state)
            for mid in gone:
                self._removed_row(mid)

        # история, потрачено, шансы
        self._sep(border)
        self._spent(em, prices)

    def _wheel(self, e):
        if self.body.winfo_reqheight() > self._cv.winfo_height():
            self._cv.yview_scroll(-1 if e.delta > 0 else 1, "units")

    def _bind_click(self):
        """Клик по любому месту предмета — применить выбранный метод (как в игре: валюта → предмет)."""
        fn = getattr(self, "on_click", None)
        if not fn:
            return

        def walk(w):
            try:
                w.bind("<Button-1>", lambda e: fn(), add="+")
                w.bind("<MouseWheel>", self._wheel, add="+")
                w.bind("<Button-4>", lambda e: self._cv.yview_scroll(-2, "units"), add="+")
                w.bind("<Button-5>", lambda e: self._cv.yview_scroll(2, "units"), add="+")
                w.configure(cursor="hand2")
            except tk.TclError:
                pass
            for c in w.winfo_children():
                walk(c)
        for c in self.body.winfo_children():     # детей пересоздаём при каждой отрисовке — без дублей
            walk(c)
        if not getattr(self, "_self_bound", False):
            for w in (self, self.body, self._cv):
                w.bind("<Button-1>", lambda e: fn())
            self._self_bound = True

    @staticmethod
    def _kind_of(mid, em):
        from poecraft import currency_craft as cc
        m = cc._raw_mods(em.data).get(mid) or {}
        return m.get("generation_type")

    def _mod_row(self, m, targets, state):
        wanted = any(t.ok(m.entry) for t in targets) if not m.crafted else False
        row = tk.Frame(self.body, bg=BG)
        row.pack(fill="x", padx=12, pady=1)
        if m.crafted:
            badge, bbg, bfg = "крафт", "#1c2036", CRAFT_FG
        elif m.veiled:
            badge, bbg, bfg = "скрыт", "#2e2412", VEIL_FG
        else:
            t = m.entry.tier
            badge = f"T{t}"
            bbg, bfg = (("#3a2c10", GOLD) if t == 1 else (("#1d3320", GOOD) if t <= 3 else ("#24201a", MUTED)))
        b = tk.Label(row, text=badge, bg=bbg, fg=bfg, font=(FONT, 8, "bold"), width=5)
        b.pack(side="left")
        fg = (CRAFT_FG if m.crafted else VEIL_FG if m.veiled else FRAC_FG if m.fractured else
              INFL_FG if inf.is_influence_mod(m.mod) else MOD_FG)
        txt = ("✓ " if wanted else "") + m.text + ("   (фрактур)" if m.fractured else "")
        lab = tk.Label(row, text=txt, bg=BG, fg=GOOD if wanted else fg, font=(FONT, 10), anchor="w",
                       justify="left", wraplength=290)
        q = None if (m.crafted or m.veiled) else roll_quality(m.mod.text, m.values)
        parts = [row, lab]
        if q is not None:
            qf = tk.Frame(row, bg=BG)
            qf.pack(side="right")
            cv = tk.Canvas(qf, width=54, height=6, bg="#2a241c", highlightthickness=0, bd=0)
            cv.pack(side="left", pady=6)
            cv.create_rectangle(0, 0, max(2, int(54 * q)), 6, fill=quality_color(q), width=0)
            ql = tk.Label(qf, text=f"{q:.0%}", bg=BG, fg=quality_color(q), font=(FONT, 8), width=5, anchor="e")
            ql.pack(side="left")
            parts += [qf, ql]
            rng = " / ".join(f"{a}–{b}" for a, b in RANGE_RE.findall(m.mod.text))
            tip = f"{m.mod.name} · T{m.entry.tier} · диапазон {rng} · ролл {q:.0%}"
            for w in (lab, cv, ql):
                w.bind("<Enter>", lambda e, t=tip: self._tip(t))
                w.bind("<Leave>", lambda e: self._tip(""))
        lab.pack(side="left", fill="x", expand=True, padx=(8, 4))
        if state:
            self._flash(parts, FLASH_NEW if state == "new" else FLASH_CHANGED, BG)

    def _removed_row(self, mid):
        from poecraft import currency_craft as cc
        m = cc._raw_mods(self.data).get(mid) or {}
        row = tk.Frame(self.body, bg=BG)
        row.pack(fill="x", padx=12, pady=1)
        tk.Label(row, text="убран", bg="#3a1a14", fg=WARN, font=(FONT, 8, "bold"), width=5).pack(side="left")
        tk.Label(row, text=(m.get("text") or mid).replace("\n", " / "), bg=BG, fg=WARN, anchor="w",
                 font=(FONT, 10, "overstrike"), wraplength=300, justify="left").pack(side="left", padx=(8, 0))

    def _history(self, steps):
        if not steps:
            return
        st = icons.store()
        cap = tk.Frame(self.body, bg=BG)
        cap.pack(fill="x", padx=14)
        tk.Label(cap, text="ИСТОРИЯ  ·  клик по шагу — вернуться к нему", bg=BG, fg=DIM, font=(FONT, 7, "bold"),
                 anchor="w").pack(fill="x")
        strip = tk.Frame(self.body, bg=BG)
        strip.pack(fill="x", padx=12, pady=(2, 4))
        shown = steps[-18:]
        offset = len(steps) - len(shown)
        if offset:
            tk.Label(strip, text=f"…{offset}", bg=BG, fg=DIM, font=(FONT, 8)).pack(side="left")
        for i, step in enumerate(shown):
            icon, label = step[0], step[1]
            idx = offset + i
            img = st.get(icon, 22) if st and icon else None
            w = tk.Label(strip, image=img or "", text="" if img else (label or "?")[:3], bg="#1a1611", fg=FG,
                         font=(FONT, 7), cursor="hand2", width=26 if img else 3, height=26 if img else 1,
                         highlightthickness=1, highlightbackground="#3a3127")
            w._img = img
            w.pack(side="left", padx=1)
            w.bind("<Enter>", lambda e, x=w, t=label, k=idx: (x.configure(highlightbackground=GOLD),
                                                            self._tip(f"Шаг {k + 1}: {t} — клик, чтобы откатиться сюда")))
            w.bind("<Leave>", lambda e, x=w: (x.configure(highlightbackground="#3a3127"), self._tip("")))
            w.bind("<Button-1>", lambda e, k=idx: self.on_rewind and self.on_rewind(k + 1))

    def _spent(self, em, prices):
        items = [(k, v) for k, v in em.spent.items() if v]
        row = tk.Frame(self.body, bg=BG)
        row.pack(fill="x", padx=14, pady=(2, 2))
        tk.Label(row, text="Потрачено:", bg=BG, fg=GOLD, font=(FONT, 9, "bold")).pack(side="left")
        if not items:
            tk.Label(row, text="ничего", bg=BG, fg=MUTED, font=(FONT, 9)).pack(side="left", padx=4)
            return
        st = icons.store()
        for k, v in items:
            img = st.get(k, 18) if st else None
            l = tk.Label(row, image=img or "", text=f"×{v}" if img else f"{k.replace('Orb of ', '')}: {v}",
                         compound="left", bg=BG, fg=MUTED, font=(FONT, 9))
            l._img = img
            l.pack(side="left", padx=(4, 0))
        if prices:
            total = sum(prices.get(k) * v for k, v in items)
            tk.Label(self.body, text=f"≈ {total:,.0f}c ({total / prices.divine:.2f} div)".replace(",", " "),
                     bg=BG, fg=MUTED, font=(FONT, 9), anchor="w").pack(fill="x", padx=14)

    def _tip(self, text):
        fn = getattr(self, "on_tip", None)
        if fn:
            fn(text)


def render_chances(box, ch, bg=BG):
    """Блок «Цели»: сколько нужных модов уже есть, чего не хватает и шансы следующих шагов полосками."""
    from mainwin import pct
    done = ch["have"] >= ch["need"]
    pad = tk.Frame(box, bg=bg)
    pad.pack(fill="x", padx=8, pady=6)
    tk.Label(pad, text=f"{ch['have']}/{ch['need']} нужных модов" + ("  — всё на месте!" if done else ""),
             bg=bg, fg=GOOD if done else GOLD, font=(FONT, 10, "bold"), anchor="w").pack(fill="x")
    if done:
        return
    tk.Label(pad, text="не хватает: " + ", ".join(ch["missing"]), bg=bg, fg=MUTED, font=(FONT, 9),
             anchor="w", justify="left", wraplength=300).pack(fill="x", pady=(0, 4))
    for key, label in (("augment", "Augmentation"), ("regal", "Regal"), ("exalt", "Exalt"),
                       ("exalt_blocked", "Exalt с блоком слота"),
                       ("exalt_no_attack", "Exalt + Cannot roll Attack"),
                       ("exalt_no_caster", "Exalt + Cannot roll Caster")):
        if key in ch:
            r = tk.Frame(pad, bg=bg)
            r.pack(fill="x")
            tk.Label(r, text=label, bg=bg, fg=FG, font=(FONT, 9), width=24, anchor="w").pack(side="left")
            v = ch[key]
            tk.Label(r, text=pct(v), bg=bg, fg=GOOD if v >= 0.2 else FG, font=(FONT, 9), width=6,
                     anchor="e").pack(side="right")
            cv = tk.Canvas(r, width=70, height=6, bg="#2a241c", highlightthickness=0, bd=0)
            cv.pack(side="right", pady=6)
            cv.create_rectangle(0, 0, max(2, int(70 * min(1, v))), 6, fill=GOOD if v >= 0.2 else GOLD, width=0)
