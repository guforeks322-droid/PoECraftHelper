"""Общие элементы мастерской: прокручиваемый список и карточки результатов (калькулятор, сокеты)."""

from __future__ import annotations

import sys
import tkinter as tk

from poecraft import icons

BG, BG1, BG2, LINE = "#0f0d0a", "#16130f", "#1f1a14", "#3a3127"
CARD, CARD_BEST = "#1a1611", "#1c2216"
FG, MUTED, DIM, GOLD, GOOD, WARN = "#d9d0c1", "#8a7f70", "#5a5248", "#e3b55b", "#7ec27a", "#e07a5f"
GOLD_LINE = "#6b5124"
from poecraft import fonts as _fonts
FONT = _fonts.UI
TFONT = _fonts.TITLE   # заголовки


class ScrollList(tk.Frame):
    """Вертикальный список с прокруткой колесом мыши."""

    def __init__(self, master, bg=BG1, **kw):
        super().__init__(master, bg=bg, highlightthickness=1, highlightbackground=LINE, **kw)
        self.cv = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.cv.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.cv, bg=bg)
        self._win = self.cv.create_window(0, 0, window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: self.cv.configure(scrollregion=self.cv.bbox("all")))
        self.cv.bind("<Configure>", lambda e: self.cv.itemconfigure(self._win, width=e.width))
        self.bind_wheel(self.cv)
        self.bind_wheel(self.inner)

    def bind_wheel(self, w):
        w.bind("<MouseWheel>", lambda e: self._scroll(-1 if e.delta > 0 else 1), add="+")
        w.bind("<Button-4>", lambda e: self._scroll(-1), add="+")
        w.bind("<Button-5>", lambda e: self._scroll(1), add="+")

    def _scroll(self, d):
        if self.inner.winfo_reqheight() > self.cv.winfo_height():
            self.cv.yview_scroll(d * 2, "units")

    def clear(self):
        for w in self.inner.winfo_children():
            w.destroy()
        self.cv.yview_moveto(0)

    def finish(self):
        """Привязать прокрутку ко всем новым виджетам."""
        def walk(w):
            self.bind_wheel(w)
            for c in w.winfo_children():
                walk(c)
        walk(self.inner)

    def message(self, text, fg=MUTED):
        self.clear()
        tk.Label(self.inner, text=text, bg=self.inner["bg"], fg=fg, font=(FONT, 10), justify="left",
                 anchor="w", wraplength=640).pack(fill="x", padx=14, pady=14)


def bar(parent, frac, width=160, color=None, bg="#2a241c"):
    cv = tk.Canvas(parent, width=width, height=6, bg=bg, highlightthickness=0, bd=0)
    frac = max(0.0, min(1.0, frac or 0))
    cv.create_rectangle(0, 0, max(2, int(width * frac)), 6, fill=color or (GOOD if frac >= 0.2 else GOLD), width=0)
    return cv


def result_card(parent, *, title, icon_names=(), best=False, desc="", cost="", cost_bad=False, chance=None,
                chance_text="", uses=(), note=""):
    """Карточка метода: иконки, название, «дешевле всего», цена крупно, шанс полоской, расход валюты."""
    bgc = CARD_BEST if best else CARD
    c = tk.Frame(parent, bg=bgc, highlightthickness=1, highlightbackground=GOOD if best else LINE)
    c.pack(fill="x", padx=8, pady=4)
    top = tk.Frame(c, bg=bgc)
    top.pack(fill="x", padx=10, pady=(8, 0))
    st = icons.store()
    for n in icon_names:
        img = st.get(n, 26) if st else None
        if img is not None:
            l = tk.Label(top, image=img, bg=bgc)
            l._img = img
            l.pack(side="left", padx=(0, 2))
    tk.Label(top, text=title, bg=bgc, fg=GOLD, font=(TFONT, 13), anchor="w").pack(side="left", padx=(4, 0))
    if best:
        tk.Label(top, text="ДЕШЕВЛЕ ВСЕГО", bg="#2a4a2a", fg=GOOD, font=(FONT, 7, "bold"), padx=6).pack(side="left",
                                                                                                    padx=8)
    tk.Label(top, text=cost, bg=bgc, fg=WARN if cost_bad else FG, font=(FONT, 13, "bold")).pack(side="right")
    if desc:
        tk.Label(c, text=desc, bg=bgc, fg=MUTED, font=(FONT, 9), anchor="w", justify="left",
                 wraplength=620).pack(fill="x", padx=10, pady=(2, 0))
    if chance is not None or chance_text:
        r = tk.Frame(c, bg=bgc)
        r.pack(fill="x", padx=10, pady=(4, 0))
        if chance is not None:
            bar(r, chance, 140, bg="#2a241c").pack(side="left", pady=5)
        tk.Label(r, text=chance_text, bg=bgc, fg=FG, font=(FONT, 9)).pack(side="left", padx=8)
    if uses:
        r = tk.Frame(c, bg=bgc)
        r.pack(fill="x", padx=10, pady=(4, 0))
        for name, txt in uses:
            img = st.get(name, 18) if st else None
            l = tk.Label(r, image=img or "", text=txt if img else f"{name}: {txt}", compound="left", bg=bgc,
                         fg=MUTED, font=(FONT, 9))
            l._img = img
            l.pack(side="left", padx=(0, 10))
    if note:
        tk.Label(c, text="⚠ " + note, bg=bgc, fg=WARN, font=(FONT, 9), anchor="w", justify="left",
                 wraplength=620).pack(fill="x", padx=10, pady=(4, 0))
    tk.Frame(c, bg=bgc, height=8).pack(fill="x")
    return c


def socket_preview(parent, want, n, bg=BG1):
    """Рисунок нужных сокетов: R/G/B кружки, остальные — серые."""
    cv = tk.Canvas(parent, width=max(1, n) * 26 + 6, height=30, bg=bg, highlightthickness=0, bd=0)
    colors = ["#d24a4a"] * want[0] + ["#5fb85f"] * want[1] + ["#5a8fe0"] * want[2]
    colors += ["#4a4038"] * (n - len(colors))
    for i, col in enumerate(colors[:n]):
        x = 4 + i * 26
        cv.create_oval(x, 4, x + 22, 26, fill=col, outline="#0c0a08", width=2)
        if i < n - 1:
            cv.create_line(x + 22, 15, x + 26, 15, fill="#a08860", width=3)
    return cv
