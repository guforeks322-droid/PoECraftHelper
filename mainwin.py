"""Главное окно поверх игры (без браузера): пул модов и калькулятор.

Открывается кнопкой «окно ⧉» в оверлее. Без рамки, всегда сверху, полупрозрачное,
перетаскивается за заголовок, размер меняется уголком справа снизу.
"""

from __future__ import annotations

import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk

from poecraft import recipes
from poecraft.calc import Target, calculate, pool_table
from poecraft import currency_craft as cc
from poecraft.emulator import CraftError, Emulator
from poecraft import influence as inf
from poecraft import sockets as sk
from poecraft import i18n
from poecraft import icons
from poecraft import hotkeys as hkmod
from poecraft.updater import APP_VERSION
from poecraft.data import APP_DIR, GameData
from poecraft.pool import ModPool
from poecraft.prices import Prices

BG, BG1, BG2, LINE = "#0f0d0a", "#16130f", "#1f1a14", "#3a3127"
TILE, TILE_HI = "#1a1611", "#2a2116"
DIM = "#5a5248"
GOLD_LINE = "#6b5124"
FG, MUTED, GOLD, GOOD, WARN, BLUE = "#d9d0c1", "#8a7f70", "#e3b55b", "#7ec27a", "#e07a5f", "#8fb3e0"
FONT = "Segoe UI"
CRAFT_DOMAINS = {"item", "flask", "misc", "abyss_jewel", "affliction_jewel"}
SKIP_CLASSES = {"HiddenItem", "FishingRod"}


_POPDOWNS: list = []


def popdown_on_top(cb: ttk.Combobox):
    """Список комбобокса — отдельное окно; у окна «поверх всех» он прячется под ним. Поднимаем."""
    def raise_pd():
        try:
            pd = cb.tk.eval(f"ttk::combobox::PopdownWindow {cb}")
            cb.tk.call("wm", "attributes", pd, "-topmost", 1)
            cb.tk.call("raise", pd)
        except tk.TclError:
            pass

    def post():
        raise_pd()
        for d in (15, 60, 150):
            cb.after(d, raise_pd)
    cb.configure(postcommand=post)
    _POPDOWNS.append(cb)
    return cb


def weight_bar(frac: float, cells: int = 8) -> str:
    """Полоска веса мода из символов блоков: █████▍ — как столбики на Craft of Exile."""
    parts = " ▏▎▍▌▋▊▉█"
    x = max(0.0, min(1.0, frac)) * cells
    full = int(x)
    rest = parts[int((x - full) * 8)] if full < cells else ""
    return ("█" * full + rest).rstrip() or "▏"


def popdown_open() -> bool:
    """Открыт ли сейчас какой-нибудь выпадающий список (тогда не трогаем порядок окон)."""
    for cb in list(_POPDOWNS):
        try:
            pd = cb.tk.eval(f"ttk::combobox::PopdownWindow {cb}")
            if cb.tk.eval(f"winfo ismapped {pd}") == "1":
                return True
        except tk.TclError:
            _POPDOWNS.remove(cb)
    return False


def short(text: str) -> str:
    import re
    first = text.replace("\n", " / ")
    return re.sub(r"\(([\d.]+)-([\d.]+)\)", "#", first)


def pct(x: float) -> str:
    return f"{x * 100:.2f}%" if x < 0.01 else f"{x * 100:.1f}%"


def money(c: float | None, divine: float, chance: float = 0) -> str:
    if c is None:
        return "цена неизвестна" if chance else "не выйдет"
    s = f"{c:,.0f}c".replace(",", " ")
    return s + (f"  ≈ {c / divine:.2f} div" if divine else "")


class MainWindow(tk.Toplevel):
    def __init__(self, master: tk.Misc, data: GameData, settings: dict, save_settings, on_goal_saved=None):
        super().__init__(master)
        self.data = data
        self.settings = settings
        self._save_settings = save_settings
        self.on_goal_saved = on_goal_saved
        self.prices = Prices()
        self.pool: ModPool | None = None
        self.table: dict | None = None
        self.selected: dict[tuple, dict] = {}      # (kind, type) -> {max_tier, label}
        self.q: queue.Queue = queue.Queue()

        # Обычное окно (с рамкой) — в окнах без рамки Windows плохо отдаёт фокус клавиатуры.
        self.title("PoE Craft Helper — мастерская")
        self.configure(highlightthickness=1)
        self.minsize(640, 420)
        self.attributes("-topmost", True)
        self.protocol("WM_DELETE_WINDOW", self.hide)
        self.attributes("-alpha", settings.get("main_alpha", 0.95))
        self.configure(bg=BG, highlightthickness=1, highlightbackground=LINE)
        geo = settings.get("main_geo", "1180x760+120+60")
        self.geometry(geo)

        self.bases = sorted(
            (b for b in data.bases.values() if b.domain in CRAFT_DOMAINS and b.item_class not in SKIP_CLASSES),
            key=lambda b: (recipes.CLASS_RU.get(b.item_class, b.item_class), b.name))
        self.base_names = [b.name for b in self.bases]

        self._style()
        self._build()
        # снимаем рамку, когда окно реально появилось на экране (и при каждом показе)
        self.bind("<Map>", lambda e: e.widget is self and self.after(10, self._frameless), add="+")
        self.after(300, self._frameless)
        threading.Thread(target=self._refresh_prices, daemon=True).start()
        self.after(100, self._poll)
        self.after(1500, self._keep_on_top)
        last = settings.get("main_base")
        if last in data.bases:
            self.base_var.set(last)
            self.load_pool()

    # ------------------------------------------------------------ стиль
    def _style(self):
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure("D.Treeview", background=BG1, fieldbackground=BG1, foreground=FG, rowheight=22,
                     bordercolor=LINE, lightcolor=BG1, darkcolor=BG1, borderwidth=1, font=(FONT, 9))
        st.layout("D.Treeview", [("Treeview.field", {"sticky": "nswe", "border": 1, "children": [
            ("Treeview.padding", {"sticky": "nswe", "children": [("Treeview.treearea", {"sticky": "nswe"})]})]})])
        st.map("D.Treeview", background=[("selected", "#3a2c17")], foreground=[("selected", GOLD)])
        st.configure("D.Treeview.Heading", background=BG2, foreground=MUTED, bordercolor=LINE,
                     relief="flat", font=(FONT, 9))
        st.map("D.Treeview.Heading", background=[("active", BG2)])
        st.configure("D.TNotebook", background=BG, borderwidth=1, bordercolor=LINE, lightcolor=BG, darkcolor=BG,
                     tabmargins=(0, 0, 0, 0))
        st.configure("D.TNotebook.Tab", background=BG2, foreground=MUTED, padding=(14, 5), font=(FONT, 10),
                     bordercolor=LINE, lightcolor=BG2, darkcolor=BG2, focuscolor=BG2)
        st.map("D.TNotebook.Tab", background=[("selected", BG)], foreground=[("selected", GOLD)],
               lightcolor=[("selected", BG)], expand=[("selected", (0, 0, 0, 0))])
        st.configure("D.TCombobox", fieldbackground=BG2, background=BG2, foreground=FG, arrowcolor=GOLD,
                     bordercolor=LINE, lightcolor=BG2, darkcolor=BG2, insertcolor=FG)
        st.map("D.TCombobox", fieldbackground=[("readonly", BG2)], foreground=[("readonly", FG)])
        st.configure("D.Vertical.TScrollbar", background=LINE, troughcolor=BG1, bordercolor=BG1,
                     arrowcolor=MUTED, lightcolor=LINE, darkcolor=LINE, gripcount=0, arrowsize=11)
        st.map("D.Vertical.TScrollbar", background=[("active", "#5a4a35")])
        self.option_add("*TCombobox*Listbox.background", BG2)
        self.option_add("*TCombobox*Listbox.foreground", FG)
        self.option_add("*TCombobox*Listbox.selectBackground", "#3a2c17")

    def _btn(self, parent, text, cmd, fg=FG, big=False):
        b = tk.Label(parent, text=text, bg=parent["bg"], fg=fg, cursor="hand2",
                     font=(FONT, 10 if big or len(text) <= 2 else 9), padx=6, pady=2)
        b.bind("<Button-1>", lambda e: cmd())
        b.bind("<Enter>", lambda e: b.configure(fg=GOLD))
        b.bind("<Leave>", lambda e: b.configure(fg=fg))
        return b

    def _act(self, parent, text, cmd):
        b = tk.Label(parent, text=text, bg="#3a2c17", fg=GOLD, cursor="hand2", font=(FONT, 10),
                     padx=12, pady=4, highlightthickness=1, highlightbackground="#6b5124")
        b.bind("<Button-1>", lambda e: cmd())
        return b

    def _tile(self, parent, icon, label, cmd, size=32, compact=False, tip=""):
        """Кнопка-плитка как на Craft of Exile: иконка валюты и подпись. Без иконки — только текст."""
        t = tk.Label(parent, text=label, bg=TILE, fg=FG, cursor="hand2", font=(FONT, 8),
                     compound="left" if compact else "top", padx=4, pady=3 if compact else 4,
                     highlightthickness=1, highlightbackground=LINE)
        t.bind("<Button-1>", lambda e: cmd())
        t.bind("<Enter>", lambda e: (t.configure(bg=TILE_HI, fg=GOLD, highlightbackground="#6b5124"),
                                     tip and self.emu_status.configure(text=tip, fg=MUTED)))
        t.bind("<Leave>", lambda e: t.configure(bg=TILE, fg=FG, highlightbackground=LINE))
        self._icon(t, icon, size)
        return t

    def _icon(self, widget, name, size=24):
        """Ставит иконку на виджет сейчас или когда она скачается."""
        if not hasattr(self, "_iconed"):
            self._iconed = []
            st = icons.store()
            if st:
                st.subscribe(self._refresh_icons)
        self._iconed.append((widget, name, size))
        self._apply_icon(widget, name, size)

    def _apply_icon(self, widget, name, size):
        st = icons.store()
        img = st.get(name, size) if st else None
        if img is not None:
            try:
                widget.configure(image=img)
                widget._img = img
            except tk.TclError:
                pass

    def _refresh_icons(self):
        self._iconed = [(w, n, s) for w, n, s in getattr(self, "_iconed", []) if w.winfo_exists()]
        for w, n, s in self._iconed:
            self._apply_icon(w, n, s)
        try:
            self._fill_fossils()
            self._fill_essences()
            self._paint_influence()
            for w, n, sz in getattr(self, "_iconed_fixed", []):
                if w.winfo_exists():
                    img = self._row_icon(n, sz)
                    if img is not None:
                        w.configure(image=img, text="", width=sz + 4, height=sz + 4)
                        w._img = img
            if self.emu:
                self.emu_card._prev = None
                self._emu_render()
        except Exception:
            pass

    def _paint_influence(self):
        name = self.inf_var.get()
        img = self._row_icon(name, 22) if name in icons.INFLUENCE_ICON else None
        self.inf_icon.configure(image=img or "")
        self.inf_icon._img = img

    def _row_icon(self, name, size=20):
        st = icons.store()
        return st.get(name, size) if st else None

    def _entry(self, parent, var, width):
        return tk.Entry(parent, textvariable=var, width=width, bg=BG2, fg=FG, insertbackground=FG,
                        relief="flat", highlightthickness=1, highlightbackground=LINE,
                        highlightcolor=GOLD, font=(FONT, 10))

    # ------------------------------------------------------------ интерфейс
    def _build(self):
        head = tk.Frame(self, bg=BG2)
        head.pack(fill="x")
        title = tk.Label(head, text="⚒ PoE Craft Helper — мастерская", bg=BG2, fg=GOLD, font=(FONT, 10, "bold"))
        title.pack(side="left", padx=8, pady=4)
        self.bind("<Configure>", self._on_configure)
        for w in (head, title):
            w.bind("<ButtonPress-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)
            w.bind("<ButtonRelease-1>", lambda e: self._remember())
        self._btn(head, "✕", self.hide, WARN).pack(side="right", padx=(0, 6))
        self._btn(head, "—", self.minimize).pack(side="right")
        self._btn(head, "◐", self.cycle_alpha).pack(side="right")
        self._btn(head, "⚙", lambda: getattr(self, "app", None) and self.app.open_settings()).pack(side="right")
        self.price_lbl = tk.Label(head, text="цены…", bg=BG2, fg=MUTED, font=(FONT, 8))
        self.price_lbl.pack(side="right", padx=8)

        ctl = tk.Frame(self, bg=BG)
        ctl.pack(fill="x", padx=10, pady=(8, 4))
        tk.Label(ctl, text="База", bg=BG, fg=MUTED, font=(FONT, 9)).pack(side="left")
        self.base_var = tk.StringVar()
        self.base_box = ttk.Combobox(ctl, textvariable=self.base_var, values=self.base_names,
                                     style="D.TCombobox", width=30, font=(FONT, 10))
        popdown_on_top(self.base_box)
        self.base_box.pack(side="left", padx=(4, 10))
        self.base_box.bind("<KeyRelease>", self._filter_bases)
        self.base_box.bind("<<ComboboxSelected>>", lambda e: self.load_pool())
        self.base_box.bind("<Return>", lambda e: self.load_pool())
        tk.Label(ctl, text="ilvl", bg=BG, fg=MUTED, font=(FONT, 9)).pack(side="left")
        self.ilvl_var = tk.StringVar(value=str(self.settings.get("main_ilvl", 84)))
        il = self._entry(ctl, self.ilvl_var, 5)
        il.pack(side="left", padx=(4, 10))
        il.bind("<Return>", lambda e: self.load_pool())
        tk.Label(ctl, text="влияние", bg=BG, fg=MUTED, font=(FONT, 9)).pack(side="left")
        self.inf_var = tk.StringVar(value="нет")
        self.inf_box = ttk.Combobox(ctl, textvariable=self.inf_var, state="readonly", style="D.TCombobox",
                                    values=["нет"], width=11, font=(FONT, 9))
        popdown_on_top(self.inf_box)
        self.inf_box.pack(side="left", padx=(4, 2))
        self.inf_box.bind("<<ComboboxSelected>>", lambda e: (self._paint_influence(), self.load_pool()))
        self.inf_icon = tk.Label(ctl, bg=BG)
        self.inf_icon.pack(side="left", padx=(0, 10))
        self._act(ctl, "Показать моды", self.load_pool).pack(side="left")
        self.info_lbl = tk.Label(ctl, text="", bg=BG, fg=MUTED, font=(FONT, 9))
        self.info_lbl.pack(side="left", padx=10)

        self.nb = ttk.Notebook(self, style="D.TNotebook")
        self.nb.pack(fill="both", expand=True, padx=8, pady=(4, 0))
        self.tab_pool = tk.Frame(self.nb, bg=BG)
        self.tab_calc = tk.Frame(self.nb, bg=BG)
        self.nb.add(self.tab_pool, text="Пул модов")
        self.nb.add(self.tab_calc, text="Калькулятор")
        self.tab_ef = tk.Frame(self.nb, bg=BG)
        self.nb.add(self.tab_ef, text="Эссенции и фоссилы")
        self.tab_emu = tk.Frame(self.nb, bg=BG)
        self.nb.add(self.tab_emu, text="Эмулятор")
        self.tab_sock = tk.Frame(self.nb, bg=BG)
        self.nb.add(self.tab_sock, text="Сокеты")

        self.nb.bind("<<NotebookTabChanged>>", lambda e: self._render_targets())
        self._build_pool()
        self._build_calc()
        self._build_ef()
        self._build_emu()
        self._build_sockets()
        i18n.translate_tree(self)

        foot = tk.Frame(self, bg=BG)
        foot.pack(fill="x")
        self.status = tk.Label(foot, text="Выбери базу предмета.", bg=BG, fg=MUTED, font=(FONT, 8), anchor="w")
        self.status.pack(side="left", fill="x", expand=True, padx=10, pady=3)
        grip = tk.Label(foot, text="◢", bg=BG, fg=MUTED, cursor="size_nw_se" if sys.platform == "win32" else "bottom_right_corner", font=(FONT, 10))
        grip.pack(side="right", padx=2)
        grip.bind("<ButtonPress-1>", self._resize_start)
        grip.bind("<B1-Motion>", self._resize_move)
        grip.bind("<ButtonRelease-1>", lambda e: self._remember())

    def _build_pool(self):
        top = tk.Frame(self.tab_pool, bg=BG)
        top.pack(fill="x", pady=(8, 4))
        tk.Label(top, text="Поиск", bg=BG, fg=MUTED, font=(FONT, 9)).pack(side="left", padx=(4, 4))
        self.filter_var = tk.StringVar()
        e = self._entry(top, self.filter_var, 24)
        e.pack(side="left")
        self.filter_var.trace_add("write", lambda *a: self._render_pool())
        # тип кластера (enchant) — только для кластер-самоцветов
        self.ench_frame = tk.Frame(top, bg=BG)
        tk.Label(self.ench_frame, text="тип кластера", bg=BG, fg=MUTED, font=(FONT, 9)).pack(side="left", padx=(10, 4))
        self.ench_var = tk.StringVar()
        self.ench_box = ttk.Combobox(self.ench_frame, textvariable=self.ench_var, state="readonly",
                                     style="D.TCombobox", width=34, font=(FONT, 9))
        popdown_on_top(self.ench_box)
        self.ench_box.pack(side="left")
        self.ench_box.bind("<<ComboboxSelected>>", lambda e: self.load_pool())
        # катализатор — только для колец, амулетов и поясов
        self.cat_frame = tk.Frame(top, bg=BG)
        tk.Label(self.cat_frame, text="катализатор 20%", bg=BG, fg=MUTED, font=(FONT, 9)).pack(side="left", padx=(10, 4))
        self.cat_var = tk.StringVar(value="нет")
        cb = ttk.Combobox(self.cat_frame, textvariable=self.cat_var, state="readonly", style="D.TCombobox",
                          values=["нет"] + list(sk.CATALYSTS), width=20, font=(FONT, 9))
        popdown_on_top(cb)
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda e: self.load_pool())
        self.pool_hint = tk.Label(top, text="Клик по ☐ — нужен мод · по «до T» — худший тир · двойной клик — тиры",
                                  bg=BG, fg=MUTED, font=(FONT, 8))
        self.pool_hint.pack(side="left", padx=10)

        cols = tk.Frame(self.tab_pool, bg=BG)
        cols.pack(fill="both", expand=True)
        cols.columnconfigure(0, weight=1, uniform="c")
        cols.columnconfigure(1, weight=1, uniform="c")
        cols.rowconfigure(1, weight=1)
        self.trees = {}
        for i, (kind, name) in enumerate((("prefix", "Префиксы"), ("suffix", "Суффиксы"))):
            lbl = tk.Label(cols, text=name, bg=BG, fg=GOLD, font=(FONT, 10, "bold"), anchor="w")
            lbl.grid(row=0, column=i, sticky="we", padx=4)
            fr = tk.Frame(cols, bg=BG)
            fr.grid(row=1, column=i, sticky="nsew", padx=4, pady=(0, 4))
            tv = ttk.Treeview(fr, style="D.Treeview", columns=("chk", "all", "kind", "bar", "tier"),
                              show="tree headings", selectmode="browse")
            tv.heading("#0", text="Мод", anchor="w")
            tv.heading("chk", text="")
            tv.heading("all", text="% всех")
            tv.heading("kind", text="% типа")
            tv.heading("tier", text="тир")
            tv.heading("bar", text="вес", anchor="w")
            tv.column("bar", width=74, anchor="w", stretch=False)
            tv.column("#0", width=230, stretch=True)
            tv.column("chk", width=26, anchor="center", stretch=False)
            tv.column("all", width=58, anchor="e", stretch=False)
            tv.column("kind", width=58, anchor="e", stretch=False)
            tv.column("tier", width=52, anchor="center", stretch=False)
            tv.tag_configure("sel", foreground=GOLD)
            tv.tag_configure("tier", foreground=MUTED)
            tv.tag_configure("na", foreground="#5a5248")
            tv.tag_configure("infl", foreground="#c39bd3")
            sb = ttk.Scrollbar(fr, orient="vertical", command=tv.yview, style="D.Vertical.TScrollbar")
            tv.configure(yscrollcommand=sb.set)
            tv.pack(side="left", fill="both", expand=True)
            sb.pack(side="right", fill="y")
            tv.bind("<Button-1>", lambda e, t=tv: self._tree_click(e, t))
            self.trees[kind] = tv

    def _build_calc(self):
        f = self.tab_calc
        tk.Label(f, text="Нужные моды (выбираются во вкладке «Пул модов»):", bg=BG, fg=MUTED,
                 font=(FONT, 9), anchor="w").pack(fill="x", padx=6, pady=(8, 2))
        self.targets_lbl = tk.Label(f, text="", bg=BG, fg=FG, font=(FONT, 9), anchor="w", justify="left")
        self.targets_lbl.pack(fill="x", padx=12)
        row = tk.Frame(f, bg=BG)
        row.pack(fill="x", padx=6, pady=6)
        self._act(row, "Посчитать", self.calculate).pack(side="left")
        self.use_ess = tk.BooleanVar(value=True)
        self.use_fos = tk.BooleanVar(value=True)
        self.use_hv = tk.BooleanVar(value=True)
        for text, var in (("+ эссенции", self.use_ess), ("+ фоссилы", self.use_fos), ("+ Harvest", self.use_hv)):
            tk.Checkbutton(row, text=text, variable=var, bg=BG, fg=FG, selectcolor=BG2, activebackground=BG,
                           activeforeground=GOLD, font=(FONT, 9), highlightthickness=0, bd=0).pack(side="left", padx=(10, 0))
        self.calc_status = tk.Label(row, text="", bg=BG, fg=MUTED, font=(FONT, 9))
        self.calc_status.pack(side="left", padx=10)

        self.out = tk.Text(f, bg=BG1, fg=FG, relief="flat", wrap="word", font=(FONT, 10), height=14,
                           highlightthickness=1, highlightbackground=LINE, padx=10, pady=8, cursor="arrow")
        self.out.pack(fill="both", expand=True, padx=6)
        self.out.tag_configure("h", foreground=GOLD, font=(FONT, 11, "bold"))
        self.out.tag_configure("best", foreground=GOOD, font=(FONT, 9, "bold"))
        self.out.tag_configure("big", foreground=FG, font=(FONT, 13, "bold"))
        self.out.tag_configure("m", foreground=MUTED, font=(FONT, 9))
        self.out.tag_configure("bad", foreground=WARN)
        self.out.configure(state="disabled")

        sv = tk.Frame(f, bg=BG)
        sv.pack(fill="x", padx=6, pady=8)
        tk.Label(sv, text="Сохранить как крафт:", bg=BG, fg=GOLD, font=(FONT, 9, "bold")).pack(side="left")
        self.goal_name = tk.StringVar()
        self._entry(sv, self.goal_name, 30).pack(side="left", padx=6)
        self._act(sv, "Сохранить и получить код", self.save_goal).pack(side="left")
        self.code_var = tk.StringVar()
        cr = tk.Frame(f, bg=BG)
        cr.pack(fill="x", padx=6, pady=(0, 6))
        self.code_entry = tk.Entry(cr, textvariable=self.code_var, bg=BG2, fg=GOOD, relief="flat",
                                   readonlybackground=BG2, state="readonly", font=("Consolas", 9))
        self.code_entry.pack(side="left", fill="x", expand=True)
        self._btn(cr, "скопировать", self.copy_code).pack(side="left", padx=4)

    # ------------------------------------------------------------ эссенции и фоссилы
    def _build_ef(self):
        f = self.tab_ef
        top = tk.Frame(f, bg=BG)
        top.pack(fill="x", padx=6, pady=(8, 4))
        tk.Label(top, text="Выбери эссенцию ИЛИ до 4 фоссилов, затем «Посчитать» — для нужных модов из «Пула модов».",
                 bg=BG, fg=MUTED, font=(FONT, 9)).pack(side="left")

        panes = tk.Frame(f, bg=BG)
        panes.pack(fill="both", expand=True)
        panes.columnconfigure(0, weight=1, uniform="p")
        panes.columnconfigure(1, weight=1, uniform="p")
        panes.rowconfigure(1, weight=1)
        tk.Label(panes, text="Эссенции для этой базы", bg=BG, fg=GOLD, font=(FONT, 10, "bold"),
                 anchor="w").grid(row=0, column=0, sticky="we", padx=4)
        tk.Label(panes, text="Фоссилы (клик по ☐)", bg=BG, fg=GOLD, font=(FONT, 10, "bold"),
                 anchor="w").grid(row=0, column=1, sticky="we", padx=4)

        def mk(parent, cols, widths, col):
            fr = tk.Frame(parent, bg=BG)
            fr.grid(row=1, column=col, sticky="nsew", padx=4)
            tv = ttk.Treeview(fr, style="D.Treeview", columns=cols[1:], show="headings" if cols[0] is None else "tree headings",
                              selectmode="browse", height=8)
            if cols[0] is not None:
                tv.heading("#0", text=cols[0], anchor="w")
                tv.column("#0", width=widths[0], stretch=True)
            for c, w in zip(cols[1:], widths[1:]):
                tv.heading(c, text=c)
                tv.column(c, width=w, anchor="w" if w > 80 else "center", stretch=w > 80)
            sb = ttk.Scrollbar(fr, orient="vertical", command=tv.yview, style="D.Vertical.TScrollbar")
            tv.configure(yscrollcommand=sb.set)
            tv.pack(side="left", fill="both", expand=True)
            sb.pack(side="right", fill="y")
            return tv

        self.ess_tv = mk(panes, ("Эссенция", "мод", "тир", "цена"), (190, 170, 40, 60), 0)
        self.fos_tv = mk(panes, ("Фоссил", "✓", "эффект", "цена"), (150, 28, 190, 60), 1)
        self.ess_tv.bind("<<TreeviewSelect>>", lambda e: self._ef_changed("ess"))
        self.fos_tv.bind("<Button-1>", self._fossil_click)
        self.fos_sel: list[str] = []
        self.ess_list: dict[str, cc.Essence] = {}
        self.fos_list = {x.name: x for x in cc.fossils(self.data)}
        self._fill_fossils()

        row = tk.Frame(f, bg=BG)
        row.pack(fill="x", padx=6, pady=6)
        self._act(row, "Посчитать выбранное", self.calculate_ef).pack(side="left")
        self._btn(row, "сбросить выбор", self._ef_clear).pack(side="left", padx=8)
        self.ef_status = tk.Label(row, text="", bg=BG, fg=MUTED, font=(FONT, 9))
        self.ef_status.pack(side="left", padx=6)
        self.ef_shift = tk.Label(f, text="", bg=BG, fg=FG, font=(FONT, 9), anchor="w", justify="left")
        self.ef_shift.pack(fill="x", padx=10)

        self.ef_out = tk.Text(f, bg=BG1, fg=FG, relief="flat", wrap="word", font=(FONT, 10), height=8,
                              highlightthickness=1, highlightbackground=LINE, padx=10, pady=8, cursor="arrow")
        self.ef_out.pack(fill="both", expand=True, padx=6, pady=(4, 6))
        for tag, kw in (("h", dict(foreground=GOLD, font=(FONT, 11, "bold"))), ("best", dict(foreground=GOOD, font=(FONT, 9, "bold"))),
                        ("big", dict(foreground=FG, font=(FONT, 13, "bold"))), ("m", dict(foreground=MUTED, font=(FONT, 9))),
                        ("bad", dict(foreground=WARN))):
            self.ef_out.tag_configure(tag, **kw)
        self.ef_out.configure(state="disabled")

    def _price_txt(self, name):
        v = self.prices.get(name)
        return f"{v:.1f}c" if v and v < 10 else (f"{v:.0f}c" if v else "—")

    def _fill_fossils(self):
        tv = self.fos_tv
        tv.delete(*tv.get_children())
        for name, fo in self.fos_list.items():
            img = self._row_icon(name)
            tv.insert("", "end", iid=name, text=" " + name.replace(" Fossil", ""),
                      values=("☑" if name in self.fos_sel else "☐", fo.describe, self._price_txt(name)),
                      tags=("sel",) if name in self.fos_sel else (), **({"image": img} if img else {}))
        tv.tag_configure("sel", foreground=GOLD)

    def _fill_essences(self):
        tv = self.ess_tv
        tv.delete(*tv.get_children())
        self.ess_list = {}
        if not self.pool:
            return
        for e in cc.essences_for(self.data, self.pool.base.item_class):
            if e.max_ilvl and self.pool.ilvl > e.max_ilvl:
                continue
            fe = cc.essence_entry(self.pool, e.mod)
            self.ess_list[e.id] = e
            img = self._row_icon(e.name)
            tv.insert("", "end", iid=e.id, text=" " + e.name, values=(short(e.mod.text), f"T{fe.tier}",
                      self._price_txt(e.name)), **({"image": img} if img else {}))

    def _fossil_click(self, e):
        iid = self.fos_tv.identify_row(e.y)
        if not iid:
            return
        if iid in self.fos_sel:
            self.fos_sel.remove(iid)
        elif len(self.fos_sel) < 4:
            self.fos_sel.append(iid)
        else:
            self.ef_status.configure(text="Максимум 4 фоссила (резонатор Prime).", fg=WARN)
        if self.fos_sel and self.ess_tv.selection():
            self.ess_tv.selection_remove(self.ess_tv.selection())
        self._fill_fossils()
        self._ef_changed("fos")
        return "break"

    def _ef_clear(self):
        self.fos_sel.clear()
        if self.ess_tv.selection():
            self.ess_tv.selection_remove(self.ess_tv.selection())
        self._fill_fossils()
        self.ef_shift.configure(text="")

    def _ef_changed(self, what):
        if what == "ess" and self.ess_tv.selection() and self.fos_sel:
            self.fos_sel.clear()
            self._fill_fossils()
        self._show_shift()

    def _targets(self):
        return [Target(k[0], k[1], v["max_tier"], v["label"]) for k, v in self.selected.items()]

    def _show_shift(self):
        """Как фоссилы меняют шанс каждого нужного мода (доля веса среди префиксов/суффиксов)."""
        if not self.pool or not self.fos_sel or not self.selected:
            self.ef_shift.configure(text="")
            return
        fp = cc.fossil_pool(self.data, self.pool, [self.fos_list[n] for n in self.fos_sel])

        def share(pool, t):
            tot = sum(e.weight for e in pool.available if e.mod.kind == t.kind)
            w = sum(e.weight for e in pool.available if t.ok(e))
            return w / tot if tot else 0
        lines = [f"{t.label}:  {pct(share(self.pool, t))} → {pct(share(fp, t))}" for t in self._targets()]
        self.ef_shift.configure(text="Шанс среди своего типа: " + "   ·   ".join(lines))

    def calculate_ef(self):
        if not self.pool or not self.selected:
            self.ef_status.configure(text="Сначала выбери базу и отметь нужные моды в «Пуле модов».", fg=WARN)
            return
        targets = self._targets()
        pool = self.pool
        ess = self.ess_list.get(self.ess_tv.selection()[0]) if self.ess_tv.selection() else None
        fos = [self.fos_list[n] for n in self.fos_sel]
        if not ess and not fos:
            self.ef_status.configure(text="Выбери эссенцию или фоссилы.", fg=WARN)
            return
        self.ef_status.configure(text="считаю…", fg=MUTED)

        def work():
            try:
                r = cc.method_essence(pool, targets, ess, self.prices) if ess else \
                    cc.method_fossils(self.data, pool, targets, fos, self.prices)
                res = [r]
            except Exception as e:
                res = [{"name": "Ошибка расчёта", "how": str(e), "chance": 0, "use": {}, "cost_chaos": None}]
            self.q.put(("calc", res, "ef_out"))
        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------ эмулятор
    def _build_emu(self):
        """Эмулятор в раскладке Craft of Exile: предмет слева, валюта и вкладки действий в центре,
        цели и журнал справа."""
        f = self.tab_emu
        self.emu: Emulator | None = None
        self._emu_steps: list = []
        f.columnconfigure(0, weight=0, minsize=440)
        f.columnconfigure(1, weight=1)
        f.columnconfigure(2, weight=0, minsize=330)
        f.rowconfigure(1, weight=1)

        # ---- панель инструментов
        top = tk.Frame(f, bg=BG)
        top.grid(row=0, column=0, columnspan=3, sticky="we", padx=6, pady=(8, 6))
        self._act(top, "Новый белый предмет", self.emu_new).pack(side="left")
        self._act(top, "⇩ Предмет из игры", self.emu_from_clipboard).pack(side="left", padx=(6, 0))
        tk.Frame(top, bg=LINE, width=1, height=22).pack(side="left", padx=10)
        self._btn(top, "↶ шаг назад", lambda: self.emu_do("undo")).pack(side="left")
        self._btn(top, "⟲ к началу", lambda: self.emu_rewind(0)).pack(side="left", padx=(4, 0))
        self.emu_status = tk.Label(top, text="Выбери базу сверху и нажми «Новый белый предмет».", bg=BG, fg=MUTED,
                                   font=(FONT, 9), anchor="w")
        self.emu_status.pack(side="left", padx=12, fill="x", expand=True)

        # ---- слева: предмет
        from itemcard import ItemCard
        left = tk.Frame(f, bg=BG)
        left.grid(row=1, column=0, sticky="nsew", padx=(6, 6), pady=(0, 6))
        self._build_method_bar(left)
        self.emu_card = ItemCard(left, self.data, on_rewind=self.emu_rewind)
        self.emu_card.on_tip = lambda t: t and self.emu_status.configure(text=t, fg=MUTED)
        self.emu_card.on_click = self.emu_apply_selected
        self.emu_card.pack(fill="both", expand=True)
        self.bind("<space>", lambda e: (not isinstance(e.widget, (tk.Entry, ttk.Combobox))) and self.emu_apply_selected())

        # ---- центр: валюта + вкладки
        mid = tk.Frame(f, bg=BG)
        mid.grid(row=1, column=1, sticky="nsew", padx=4, pady=(0, 6))
        self._cap(mid, "Валюта")
        grid = tk.Frame(mid, bg=BG)
        grid.pack(fill="x", pady=(2, 8))
        buttons = [("Transmutation", "transmute", "Transmute"), ("Alteration", "alteration", "Alteration"),
                   ("Augmentation", "augment", "Augment"), ("Regal", "regal", "Regal"),
                   ("Alchemy", "alchemy", "Alchemy"), ("Chaos", "chaos", "Chaos"), ("Exalted", "exalt", "Exalted"),
                   ("Annulment", "annul", "Annul"), ("Scouring", "scour", "Scour"), ("Divine", "divine", "Divine")]
        for i, (name, act, label) in enumerate(buttons):
            self._tile(grid, name, label, lambda a=act: self.emu_pick(a), tip=self.STEP_TIPS.get(act, "")).grid(
                row=i // 5, column=i % 5, sticky="we", padx=2, pady=2)
        for c in range(5):
            grid.columnconfigure(c, weight=1, uniform="cur")

        tabs = tk.Frame(mid, bg=BG)
        tabs.pack(fill="x")
        tk.Frame(mid, bg=GOLD_LINE, height=1).pack(fill="x")
        self.emu_page = tk.Frame(mid, bg=BG1, highlightthickness=0)
        self.emu_page.pack(fill="both", expand=True)
        self._emu_tabs, self._emu_pages = {}, {}
        for key, icon, label in (("ess", "Deafening Essence of Greed", "Эссенции"), ("fos", "Pristine Fossil", "Фоссилы"),
                                 ("inf", "Crusader", "Влияние"), ("eld", "Exarch", "Eldritch"),
                                 ("hv", "Wild Crystallised Lifeforce", "Harvest"), ("veil", "Veiled Chaos Orb", "Veiled"),
                                 ("bench", "", "Верстак")):
            t = tk.Label(tabs, text=" " + label, bg=BG, fg=MUTED, font=(FONT, 9), compound="left", padx=3, pady=4,
                         cursor="hand2", anchor="w")
            n = len(self._emu_tabs)
            t.grid(row=n // 4, column=n % 4, sticky="we")
            tabs.columnconfigure(n % 4, weight=1, uniform="tabs")
            if icon:
                self._icon(t, icon, 18)
            t.bind("<Button-1>", lambda e, k=key: self._emu_tab(k))
            t.bind("<Enter>", lambda e, w=t, k=key: k != self._emu_cur and w.configure(fg=FG))
            t.bind("<Leave>", lambda e, w=t, k=key: k != self._emu_cur and w.configure(fg=MUTED))
            self._emu_tabs[key] = t
            page = tk.Frame(self.emu_page, bg=BG1)
            self._emu_pages[key] = page
        self._emu_cur = None
        self._page_ess(self._emu_pages["ess"])
        self._page_fos(self._emu_pages["fos"])
        self._page_inf(self._emu_pages["inf"])
        self._page_eld(self._emu_pages["eld"])
        self._page_hv(self._emu_pages["hv"])
        self._page_veil(self._emu_pages["veil"])
        self._page_bench(self._emu_pages["bench"])
        self._emu_tab(self.settings.get("emu_tab", "ess"))

        # ---- справа: цели и журнал
        right = tk.Frame(f, bg=BG)
        right.grid(row=1, column=2, sticky="nsew", padx=(6, 6), pady=(0, 6))
        self._cap(right, "Цели")
        self.emu_goals = tk.Frame(right, bg=BG1, highlightthickness=1, highlightbackground=LINE)
        self.emu_goals.pack(fill="x", pady=(2, 10))
        jh = tk.Frame(right, bg=BG)
        jh.pack(fill="x")
        self._cap(jh, "Журнал крафта", side="left")
        tk.Label(jh, text="клик по шагу — откат", bg=BG, fg=MUTED, font=(FONT, 8)).pack(side="right")
        jf = tk.Frame(right, bg=BG1, highlightthickness=1, highlightbackground=LINE)
        jf.pack(fill="both", expand=True, pady=(2, 0))
        self.emu_journal = tk.Text(jf, bg=BG1, fg=FG, relief="flat", wrap="word", font=(FONT, 9), width=36,
                                   height=8, padx=6, pady=4, cursor="arrow", highlightthickness=0)
        jsb = ttk.Scrollbar(jf, orient="vertical", command=self.emu_journal.yview, style="D.Vertical.TScrollbar")
        self.emu_journal.configure(yscrollcommand=jsb.set)
        jsb.pack(side="right", fill="y")
        self.emu_journal.pack(side="left", fill="both", expand=True)
        for tag, kw in (("step", dict(foreground=GOLD, font=(FONT, 9, "bold"))), ("add", dict(foreground=GOOD)),
                        ("del", dict(foreground=WARN, overstrike=True)), ("chg", dict(foreground="#e8c860")),
                        ("m", dict(foreground=MUTED, font=(FONT, 8)))):
            self.emu_journal.tag_configure(tag, **kw)
        self.emu_journal.configure(state="disabled")

    # ------------------------------------------------------------ выбранный метод (как на Craft of Exile)
    def _build_method_bar(self, parent):
        """Плашка «Метод»: что выбрано, кнопка применить и симуляция — над предметом."""
        self._emu_sel = None
        self._sim_job = None
        bar = tk.Frame(parent, bg=BG1, highlightthickness=1, highlightbackground=LINE)
        bar.pack(fill="x", pady=(0, 6))
        r1 = tk.Frame(bar, bg=BG1)
        r1.pack(fill="x", padx=8, pady=(6, 2))
        tk.Label(r1, text="МЕТОД", bg=BG1, fg=MUTED, font=(FONT, 8, "bold")).pack(side="left")
        self.sel_icon = tk.Label(r1, bg=BG1)
        self.sel_icon.pack(side="left", padx=(8, 4))
        self.sel_lbl = tk.Label(r1, text="не выбран — кликни по валюте справа", bg=BG1, fg=MUTED, font=(FONT, 10),
                                anchor="w")
        self.sel_lbl.pack(side="left", fill="x", expand=True)
        self.apply_btn = self._act(r1, "Применить  ␣", self.emu_apply_selected)
        self.apply_btn.pack(side="right")
        r2 = tk.Frame(bar, bg=BG1)
        r2.pack(fill="x", padx=8, pady=(2, 6))
        self.sim_btn = self._btn(r2, "▶ Крутить до цели", self.emu_sim_toggle, GOOD)
        self.sim_btn.pack(side="left")
        tk.Label(r2, text="предметов:", bg=BG1, fg=MUTED, font=(FONT, 8)).pack(side="left", padx=(10, 2))
        self.sim_n = tk.StringVar(value="100")
        self._entry(r2, self.sim_n, 5).pack(side="left")
        self._btn(r2, "▦ Прогнать", self.emu_sim_fixed).pack(side="left", padx=(4, 0))
        self.aug_var = tk.BooleanVar(value=True)
        tk.Checkbutton(r2, text="+Aug", variable=self.aug_var, bg=BG1, fg=MUTED, selectcolor=BG2,
                       activebackground=BG1, activeforeground=GOLD, font=(FONT, 8), bd=0,
                       highlightthickness=0).pack(side="right")
        self.sim_lbl = tk.Label(bar, text="Клик по предмету или «Применить» (пробел) — кинуть выбранное. "
                                          "Двойной клик по валюте — кинуть сразу.", bg=BG1, fg=DIM,
                                font=(FONT, 8), anchor="w", justify="left", wraplength=410)
        self.sim_lbl.pack(fill="x", padx=8, pady=(0, 6))

    def emu_pick(self, action, **kw):
        """Выбрать метод (валюту/эссенцию/фоссилы…). Применяется кликом по предмету, пробелом или «Применить»."""
        if self._sim_job:
            self.emu_sim_stop()
        icon, label = self._step_of(action, kw)
        self._emu_sel = (action, kw, icon, label)
        img = self._row_icon(icon, 26) if icon else None
        self.sel_icon.configure(image=img or "")
        self.sel_icon._img = img
        self.sel_lbl.configure(text=label, fg=GOLD)
        now = __import__("time").time()
        last = getattr(self, "_pick_t", (None, 0))
        self._pick_t = (label, now)
        if last[0] == label and now - last[1] < 0.35:      # двойной клик по той же валюте — кинуть сразу
            self.emu_apply_selected()

    def emu_apply_selected(self):
        if not self._emu_sel:
            self.emu_status.configure(text="Сначала выбери метод — кликни по валюте, эссенции или фоссилам.", fg=WARN)
            return
        action, kw = self._emu_sel[0], self._emu_sel[1]
        if action == "alteration" and self.aug_var.get():
            self.emu_do("alteration")
            if self.emu and self.emu.rarity == "Magic" and len(self.emu.mods) == 1 and not self._goal_met():
                self.emu_do("augment")
            return
        self.emu_do(action, **kw)

    # ------------------------------------------------------------ симуляция
    def _goal_met(self) -> bool:
        targets = self._targets()
        em = self.emu
        return bool(targets) and em is not None and all(
            any(not m.crafted and t.ok(m.entry) for m in em.mods) for t in targets)

    def _sim_once(self, em):
        action, kw = self._emu_sel[0], self._emu_sel[1]
        em.apply(action, **kw)
        if action == "alteration" and self.aug_var.get() and em.rarity == "Magic" and len(em.mods) == 1:
            if not all(any(t.ok(m.entry) for m in em.mods) for t in self._targets()):
                em.apply("augment")

    def emu_sim_toggle(self):
        if self._sim_job and getattr(self, "_sim", None) is None and getattr(self, "_fixed_finish", None):
            self.after_cancel(self._sim_job)
            return self._fixed_finish()
        if self._sim_job:
            return self.emu_sim_stop()
        if not self.emu or not self._emu_sel:
            self.emu_status.configure(text="Нужны предмет и выбранный метод (например Chaos или эссенция).", fg=WARN)
            return
        if not self._targets():
            self.emu_status.configure(text="Отметь нужные моды во вкладке «Пул модов» — иначе не понять, когда остановиться.",
                                      fg=WARN)
            return
        if self._goal_met():
            self.emu_status.configure(text="Цель уже выполнена.", fg=GOOD)
            return
        em = self.emu
        self._sim = {"snap": em.snapshot(), "hist": list(em.history), "n": 0, "spent0": dict(em.spent),
                     "t0": __import__("time").time()}
        self.sim_btn.configure(text="■ Стоп", fg=WARN)
        self._sim_job = self.after(1, self._sim_tick)

    def _sim_tick(self):
        em, sim = self.emu, self._sim
        import time as _t
        t_end = _t.time() + 0.04
        try:
            while _t.time() < t_end:
                self._sim_once(em)
                sim["n"] += 1
                if len(em.history) > 50:
                    del em.history[:-5]
                if self._goal_met() or sim["n"] >= 200000:
                    return self.emu_sim_stop(done=True)
        except CraftError as e:
            self.emu_status.configure(text=f"Симуляция остановлена: {e}", fg=WARN)
            return self.emu_sim_stop()
        cost = self._spent_cost(em.spent, sim["spent0"])
        self.sim_lbl.configure(text=f"Кручу… попыток {sim['n']:,} · потрачено ≈ {cost:,.0f}c".replace(",", " "), fg=GOLD)
        self.emu_card.render(em, self._targets(), self.prices)
        self._sim_job = self.after(15, self._sim_tick)

    def _spent_cost(self, spent, base=None):
        base = base or {}
        return sum(self.prices.get(k) * (v - base.get(k, 0)) for k, v in spent.items())

    def emu_sim_stop(self, done=False):
        if self._sim_job:
            try:
                self.after_cancel(self._sim_job)
            except tk.TclError:
                pass
        self._sim_job = None
        self.sim_btn.configure(text="▶ Крутить до цели", fg=GOOD)
        sim = getattr(self, "_sim", None)
        if not sim or not self.emu:
            return
        em = self.emu
        em.history = sim["hist"] + [sim["snap"]]       # «шаг назад» вернёт предмет до автокрутки
        cost = self._spent_cost(em.spent, sim["spent0"])
        label = self._emu_sel[3] if self._emu_sel else "?"
        self._emu_steps.append((self._emu_sel[2] if self._emu_sel else "", f"Автокрутка: {label} ×{sim['n']}",
                                [("m", f"{sim['n']:,} попыток · ≈ {cost:,.0f}c ({cost / self.prices.divine:.2f} div)"
                                  .replace(",", " ")),
                                 ("add" if done else "m", "цель достигнута" if done else "остановлено вручную")]))
        self.sim_lbl.configure(text=(f"Готово за {sim['n']:,} попыток · ≈ {cost:,.0f}c" if done else
                                     f"Остановлено после {sim['n']:,} попыток · ≈ {cost:,.0f}c").replace(",", " "),
                               fg=GOOD if done else MUTED)
        self._sim = None
        self._emu_render()

    def emu_sim_fixed(self):
        """Как «Run fixed simulation» на Craft of Exile: N предметов от текущего состояния, статистика попыток."""
        if not self.emu or not self._emu_sel or not self._targets():
            self.emu_status.configure(text="Нужны предмет, выбранный метод и отмеченные нужные моды.", fg=WARN)
            return
        if self._goal_met():
            self.sim_lbl.configure(text="Цель на предмете уже выполнена — откатись (⟲ к началу) или возьми новый "
                                        "предмет, тогда прогон покажет, сколько стоит дойти до цели.", fg=WARN)
            return
        try:
            n = max(1, min(2000, int(self.sim_n.get())))
        except ValueError:
            n = 100
        if self._sim_job:
            return
        import random as _r
        import time as _t
        em = self.emu
        start = em.snapshot()
        saved = (list(em.history), list(self._emu_steps), em.rng.getstate())
        targets = self._targets()
        limit = 20000
        res = {"attempts": [], "costs": [], "t0": _t.time()}

        def restore_start():
            (em.rarity, em.mods, em.spent, em.log, infl, em.exarch, em.eater) = (
                start[0], [type(m)(m.entry, m.crafted, m.fractured, list(m.values), m.veiled) for m in start[1]],
                dict(start[2]), list(start[3]), list(start[4]), start[5], start[6])
            if infl != em.influences:
                em.influences = list(infl)
                em.pool = em._make_pool()

        def work():
            """Один предмет за раз, кусками по ~40 мс — интерфейс не замирает."""
            t_end = _t.time() + 0.04
            try:
                while _t.time() < t_end:
                    if res.get("cur") is None:
                        if len(res["attempts"]) >= n or _t.time() - res["t0"] > 60:
                            return finish()
                        restore_start()
                        em.rng = _r.Random()
                        res["cur"] = 0
                    if res["cur"] >= limit or all(any(not m.crafted and t.ok(m.entry) for m in em.mods)
                                                  for t in targets):
                        res["attempts"].append(res["cur"])
                        res["costs"].append(self._spent_cost(em.spent, start[2]))
                        res["cur"] = None
                        continue
                    self._sim_once(em)
                    res["cur"] += 1
                    if len(em.history) > 20:
                        del em.history[:]
            except CraftError as e:
                res["error"] = str(e)
                return finish()
            self.sim_lbl.configure(text=f"Прогоняю: {len(res['attempts'])}/{n} предметов…", fg=GOLD)
            self._sim_job = self.after(1, work)

        def finish():
            self._sim_job = None
            self.sim_btn.configure(text="▶ Крутить до цели", fg=GOOD)
            (em.rarity, em.mods, em.spent, em.log, infl, em.exarch, em.eater) = start
            if infl != em.influences:
                em.influences = list(infl)
                em.pool = em._make_pool()
            em.history, self._emu_steps = saved[0], saved[1]
            em.rng.setstate(saved[2])
            a, c = sorted(res["attempts"]), res["costs"]
            if not a:
                self.sim_lbl.configure(text=res.get("error") or "Этот метод не работает на таком предмете.", fg=WARN)
                return self._emu_render()
            sp = lambda x: f"{x:,.0f}".replace(",", " ")
            med, p90 = a[len(a) // 2], a[min(len(a) - 1, int(len(a) * 0.9))]
            fail = sum(1 for x in a if x >= limit)
            avg_c = sum(c) / len(c)
            self.sim_lbl.configure(
                text=(f"{len(a)} предметов: в среднем {sp(sum(a) / len(a))} попыток (медиана {sp(med)}, "
                      f"90% — до {sp(p90)}) · ≈ {sp(avg_c)}c ({avg_c / self.prices.divine:.2f} div) за предмет"
                      + (f" · {fail} не дошли за {sp(limit)}" if fail else "")), fg=GOOD)
            self._emu_render()

        self.sim_btn.configure(text="■ Стоп", fg=WARN)
        self._sim = None
        self._fixed_finish = finish
        self._sim_job = self.after(1, work)

    STEP_TIPS = {
        "transmute": "Transmutation: обычный → магический (1–2 мода)",
        "alteration": "Alteration: перекатить магический предмет",
        "augment": "Augmentation: добавить мод магическому предмету",
        "regal": "Regal: магический → редкий, +1 мод",
        "alchemy": "Alchemy: обычный → редкий (4–6 модов)",
        "chaos": "Chaos: перекатить редкий предмет полностью",
        "exalt": "Exalted: добавить случайный мод редкому предмету",
        "annul": "Annulment: убрать случайный мод",
        "scour": "Scouring: убрать все моды (кроме фрактуров)",
        "divine": "Divine: перекатить значения модов внутри их тиров",
    }

    def _cap(self, parent, text, side=None):
        l = tk.Label(parent, text=text.upper(), bg=parent["bg"], fg=GOLD, font=(FONT, 9, "bold"), anchor="w")
        l.pack(side=side) if side else l.pack(fill="x")
        return l

    def _emu_tab(self, key):
        if key not in self._emu_pages:
            key = "ess"
        if self._emu_cur:
            self._emu_pages[self._emu_cur].pack_forget()
        self._emu_cur = key
        self._emu_pages[key].pack(fill="both", expand=True, padx=8, pady=8)
        for k, t in self._emu_tabs.items():
            t.configure(fg=GOLD if k == key else MUTED, bg=BG1 if k == key else BG)
        self.settings["emu_tab"] = key

    def _note(self, parent, text):
        l = tk.Label(parent, text=text, bg=parent["bg"], fg=MUTED, font=(FONT, 8), anchor="w", justify="left",
                     wraplength=330)
        l.bind("<Configure>", lambda e: l.configure(wraplength=max(200, e.width - 8)))
        return l

    # ---- вкладки действий
    def _page_ess(self, p):
        self._note(p, "Клик по иконке — лучший доступный тир этой эссенции. Нужен другой тир — выбери в списке.").pack(fill="x")
        self.emu_ess_grid = tk.Frame(p, bg=BG1)
        self.emu_ess_grid.pack(fill="x", pady=6)
        er = tk.Frame(p, bg=BG1)
        er.pack(fill="x")
        self.emu_ess_var = tk.StringVar()
        self.emu_ess_box = ttk.Combobox(er, textvariable=self.emu_ess_var, state="readonly", style="D.TCombobox",
                                        font=(FONT, 9))
        popdown_on_top(self.emu_ess_box)
        self.emu_ess_box.pack(side="left", fill="x", expand=True)
        self._act(er, "Применить", self.emu_essence).pack(side="left", padx=(6, 0))

    def _page_fos(self, p):
        self._note(p, "Выбери до 4 фоссилов (клик — выбрать/снять), затем «Применить». "
                      "Резонатор подберётся сам.").pack(fill="x")
        self.emu_fos_grid = tk.Frame(p, bg=BG1)
        self.emu_fos_grid.pack(fill="x", pady=6)
        self._emu_fos_tiles = {}
        for i, name in enumerate(self.fos_list):
            t = tk.Label(self.emu_fos_grid, text=name.replace(" Fossil", "")[:5], bg=TILE, fg=MUTED, font=(FONT, 7),
                         cursor="hand2", highlightthickness=2, highlightbackground=TILE, width=4, height=2)
            t.grid(row=i // 9, column=i % 9, padx=1, pady=1)
            fo = self.fos_list[name]
            tip = f"{name}: {fo.describe} · {self._price_txt(name)}"
            t.bind("<Button-1>", lambda e, n=name: self._emu_fos_toggle(n))
            t.bind("<Enter>", lambda e, tp=tip: self.emu_status.configure(text=tp, fg=MUTED))
            self._emu_fos_tiles[name] = t
            self._icon_fixed(t, name, 30)
        r = tk.Frame(p, bg=BG1)
        r.pack(fill="x")
        self.emu_fos_lbl = tk.Label(r, text="не выбраны", bg=BG1, fg=FG, font=(FONT, 9), anchor="w",
                                    justify="left", wraplength=260)
        self.emu_fos_lbl.pack(side="left", fill="x", expand=True)
        self._btn(r, "сброс", self._emu_fos_clear).pack(side="right")
        self._act(r, "Применить", self.emu_fossils).pack(side="right", padx=(0, 6))

    def _icon_fixed(self, widget, name, size):
        """Иконка в квадратной плитке: без картинки — текст, с картинкой — фиксированный размер в пикселях."""
        self._iconed_fixed = getattr(self, "_iconed_fixed", [])
        self._iconed_fixed.append((widget, name, size))
        img = self._row_icon(name, size)
        if img is not None:
            widget.configure(image=img, text="", width=size + 4, height=size + 4)
            widget._img = img

    def _emu_fos_toggle(self, name):
        if name in self.fos_sel:
            self.fos_sel.remove(name)
        elif len(self.fos_sel) < 4:
            self.fos_sel.append(name)
        else:
            self.emu_status.configure(text="Максимум 4 фоссила.", fg=WARN)
        self._emu_fos_paint()
        self._fill_fossils()

    def _emu_fos_clear(self):
        self.fos_sel.clear()
        self._emu_fos_paint()
        self._fill_fossils()

    def _emu_fos_paint(self):
        for n, t in getattr(self, "_emu_fos_tiles", {}).items():
            t.configure(highlightbackground=GOLD if n in self.fos_sel else TILE)
        if hasattr(self, "emu_fos_lbl"):
            self.emu_fos_lbl.configure(text=", ".join(n.replace(" Fossil", "") for n in self.fos_sel) or "не выбраны")

    def _page_inf(self, p):
        self._note(p, "Exalt завоевателя добавляет мод своего влияния и делает предмет влиятельным. "
                      "Shaper и Elder выбираются в поле «влияние» сверху.").pack(fill="x")
        ir = tk.Frame(p, bg=BG1)
        ir.pack(fill="x", pady=6)
        for i, name in enumerate(inf.CONQUEROR_ORBS):
            self._tile(ir, name, name, lambda n=name: self.emu_pick("conqueror", name=n),
                       tip=f"{inf.CONQUEROR_ORBS[name]}: добавляет мод влияния {name}").grid(
                row=0, column=i, sticky="we", padx=2, pady=2)
            ir.columnconfigure(i, weight=1, uniform="cq")

    def _page_eld(self, p):
        self._note(p, "Ember — имплицит Searing Exarch, Ichor — Eater of Worlds (только броня: шлем, "
                      "перчатки, ботинки, нагрудник). Chaos/Exalt/Annul действуют на сторону доминирующего.").pack(fill="x")
        er = tk.Frame(p, bg=BG1)
        er.pack(fill="x", pady=6)
        tk.Label(er, text="тир", bg=BG1, fg=MUTED, font=(FONT, 9)).pack(side="left")
        self.emu_eld_var = tk.StringVar(value="Grand")
        eb = ttk.Combobox(er, textvariable=self.emu_eld_var, state="readonly", style="D.TCombobox",
                          values=[inf.ELDRITCH_TIERS[i] for i in (1, 2, 3, 4)], width=10, font=(FONT, 9))
        popdown_on_top(eb)
        eb.pack(side="left", padx=6)
        lvl = lambda: {v: k for k, v in inf.ELDRITCH_TIERS.items()}[self.emu_eld_var.get()]
        for side_key, name, label in (("exarch", "Exarch", "Ember"), ("eater", "Eater", "Ichor")):
            self._tile(er, name, label, lambda k=side_key: self.emu_pick("eldritch_currency", side=k, level=lvl()),
                       size=24, compact=True).pack(side="left", padx=2, fill="x", expand=True)
        eg = tk.Frame(p, bg=BG1)
        eg.pack(fill="x")
        for i, (name, act, label) in enumerate((("Eldritch Chaos", "eldritch_chaos", "Chaos"),
                                                ("Eldritch Exalt", "eldritch_exalt", "Exalt"),
                                                ("Eldritch Annul", "eldritch_annul", "Annul"),
                                                ("Orb of Conflict", "conflict", "Conflict"))):
            self._tile(eg, name, label, lambda a=act: self.emu_pick(a), tip=name).grid(
                row=0, column=i, sticky="we", padx=2, pady=2)
            eg.columnconfigure(i, weight=1, uniform="eg")

    def _page_hv(self, p):
        from poecraft.harvest import HARVEST
        self._note(p, "Reforge — перекат с гарантированным модом выбранного тега. "
                      "«+мод/−мод» — добавить мод тега, убрав другой.").pack(fill="x")
        hr = tk.Frame(p, bg=BG1)
        hr.pack(fill="x", pady=6)
        tk.Label(hr, text="тег", bg=BG1, fg=MUTED, font=(FONT, 9)).pack(side="left")
        self.emu_hv_var = tk.StringVar(value="Fire")
        hb = ttk.Combobox(hr, textvariable=self.emu_hv_var, state="readonly", style="D.TCombobox",
                          values=list(HARVEST), width=14, font=(FONT, 9))
        popdown_on_top(hb)
        hb.pack(side="left", padx=6)
        hg = tk.Frame(p, bg=BG1)
        hg.pack(fill="x")
        for i, (label, cmd) in enumerate((
                ("Reforge", lambda: self.emu_pick("harvest_reforge", label=self.emu_hv_var.get())),
                ("+мод / −мод", lambda: self.emu_pick("harvest_augment", label=self.emu_hv_var.get())),
                ("те же моды ↑", lambda: self.emu_pick("harvest_same", more=True)),
                ("те же моды ↓", lambda: self.emu_pick("harvest_same", more=False)))):
            self._tile(hg, "Wild Crystallised Lifeforce", label, cmd, size=20, compact=True).grid(
                row=i // 2, column=i % 2, sticky="we", padx=2, pady=2)
        hg.columnconfigure(0, weight=1, uniform="hv")
        hg.columnconfigure(1, weight=1, uniform="hv")

    def _page_veil(self, p):
        self._note(p, "Veiled Chaos/Exalt дают скрытый мод, у Jun можно выбрать 1 из 3 вариантов.").pack(fill="x")
        vg = tk.Frame(p, bg=BG1)
        vg.pack(fill="x", pady=6)
        for i, (name, label, cmd) in enumerate((("Veiled Chaos", "Veiled Chaos", lambda: self.emu_pick("veiled_chaos")),
                                                ("Veiled Exalt", "Veiled Exalt", lambda: self.emu_pick("veiled_exalt")),
                                                ("Unveil", "Unveil (1 из 3)", self.emu_unveil))):
            self._tile(vg, name, label, cmd).grid(row=0, column=i, sticky="we", padx=2, pady=2)
            vg.columnconfigure(i, weight=1, uniform="vg")
        self.emu_unveil_frame = tk.Frame(p, bg=BG1)
        self.emu_unveil_frame.pack(fill="x", pady=(4, 0))

    def _page_bench(self, p):
        sr = tk.Frame(p, bg=BG1)
        sr.pack(fill="x")
        tk.Label(sr, text="поиск", bg=BG1, fg=MUTED, font=(FONT, 9)).pack(side="left")
        self.emu_bench_q = tk.StringVar()
        self._entry(sr, self.emu_bench_q, 20).pack(side="left", fill="x", expand=True, padx=6)
        self.emu_bench_q.trace_add("write", lambda *a: self._emu_bench_fill())
        lf = tk.Frame(p, bg=BG1)
        lf.pack(fill="both", expand=True, pady=6)
        self.emu_bench_lb = tk.Listbox(lf, bg=BG2, fg=FG, selectbackground="#3a2c17", selectforeground=GOLD,
                                       relief="flat", font=(FONT, 9), activestyle="none", highlightthickness=0,
                                       height=10)
        sb = ttk.Scrollbar(lf, orient="vertical", command=self.emu_bench_lb.yview, style="D.Vertical.TScrollbar")
        self.emu_bench_lb.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.emu_bench_lb.pack(side="left", fill="both", expand=True)
        self.emu_bench_lb.bind("<Double-Button-1>", lambda e: self.emu_bench())
        self._note(p, "★ — метакрафты. Двойной клик по строке — скрафтить.").pack(fill="x")
        br = tk.Frame(p, bg=BG1)
        br.pack(fill="x", pady=(4, 0))
        self._btn(br, "снять крафты", lambda: self.emu_do("remove_crafted")).pack(side="right")
        self._act(br, "Скрафтить", self.emu_bench).pack(side="right", padx=6)
        self._emu_bench = {}
        self._emu_bench_keys = []

    def _emu_bench_fill(self):
        q = self.emu_bench_q.get().lower().strip()
        self._emu_bench_keys = [k for k in self._emu_bench if q in k.lower()]
        self.emu_bench_lb.delete(0, "end")
        for k in self._emu_bench_keys:
            self.emu_bench_lb.insert("end", k)

    def emu_new(self):
        if not self.pool:
            self.emu_status.configure(text="Сначала выбери базу сверху.", fg=WARN)
            return
        infl = [self.inf_var.get()] if self.inf_var.get() in getattr(self, "inf_map", {}) else []
        self.emu = Emulator(self.data, self.base_pool, influences=infl)
        self._emu_steps = []
        self.emu_card._prev = None
        self._emu_lists()
        self.emu_status.configure(text=f"{self.pool.base.name}, ilvl {self.pool.ilvl}", fg=MUTED)
        self._emu_render()

    def emu_from_clipboard(self):
        try:
            text = self.clipboard_get()
        except tk.TclError:
            text = ""
        app = getattr(self, "app", None)
        if not text and app and app.last_text:
            text = app.last_text
        self.load_item_text(text)

    def load_item_text(self, text: str):
        """Предмет, скопированный в игре (Ctrl+Alt+C), — в эмулятор как есть: база, ilvl, влияния, моды."""
        from poecraft.advisor import Advisor
        from poecraft.parser import ParseError, looks_like_item, parse_item
        self.show()
        self.nb.select(self.tab_emu)
        if not text or not looks_like_item(text):
            self.emu_status.configure(text="В буфере нет предмета — наведи на него в игре и нажми Ctrl+Alt+C.", fg=WARN)
            return
        try:
            item = parse_item(text)
        except (ParseError, ValueError) as e:
            self.emu_status.configure(text=f"Не понял предмет: {e}", fg=WARN)
            return
        base = self.data.find_base_any(item.base_name)
        if base is None:
            self.emu_status.configure(text=f"Не нашёл базу «{item.base_name}».", fg=WARN)
            return
        self.base_var.set(base.name)
        self.ilvl_var.set(str(item.ilvl or 84))
        tags = inf.influence_tags(self.data, base.item_class)
        one = [i for i in item.influences if i in tags]
        self.inf_var.set(one[0] if len(one) == 1 else "нет")
        self._paint_influence()
        self.load_pool()
        if not self.pool:
            return
        self.emu = Emulator(self.data, self.base_pool, influences=[i for i in item.influences if i in tags])
        self._emu_steps = []
        self.emu_card._prev = None
        try:
            unknown = self.emu.load_item(item, Advisor(self.data)._match_mod)
        except CraftError as e:
            self.emu = None
            self.emu_status.configure(text=str(e), fg=WARN)
            return
        self._emu_lists()
        self._emu_render()
        msg = f"Из игры: {item.name or base.name} · ilvl {item.ilvl}"
        if item.corrupted:
            msg += " · осквернён (в игре валюта уже не сработает)"
        if unknown:
            msg += f" · не распознано модов: {len(unknown)}"
        self.emu_status.configure(text=msg, fg=WARN if unknown or item.corrupted else GOOD)

    def _emu_lists(self):
        if not self.emu:
            return
        ess = [e for e in cc.essences_for(self.data, self.pool.base.item_class)
               if not (e.max_ilvl and self.pool.ilvl > e.max_ilvl)]
        self._emu_ess = {f"{e.name} — {short(e.mod.text)}": e for e in ess}
        self.emu_ess_box["values"] = list(self._emu_ess)
        self._emu_ess_icons(ess)
        opts = self.emu.bench_options()
        metas = [o for o in opts if any(g.startswith("ItemGeneration") for g in o["mod"].groups)]
        rest = [o for o in opts if o not in metas]
        from poecraft.advisor import CURRENCY_RU

        def lbl(o):
            cost = ", ".join(f"{v} {CURRENCY_RU.get(k, k).replace('Orb of ', '').replace(' Orb', '')}" for k, v in o["cost"].items())
            return f"{'★ ' if o in metas else ''}{o['mod'].text.splitlines()[0]}  [{cost}]"
        self._emu_bench = {lbl(o): o for o in metas + rest}
        self._emu_bench_fill()

    def _emu_ess_icons(self, ess):
        """Сетка иконок эссенций как на Craft of Exile: по одной на вид, лучший доступный тир."""
        for w in self.emu_ess_grid.winfo_children():
            w.destroy()
        order = {t: i for i, t in enumerate(icons.ESSENCE_TIERS)}
        best = {}
        for e in ess:
            tier, _, kind = e.name.partition(" Essence of ")
            if not kind:
                tier, kind = "", e.name.replace("Essence of ", "")
            cur = best.get(kind)
            if cur is None or order.get(tier, -1) < order.get(cur[0], 99) or not cur[0]:
                best[kind] = (tier, e)
        for i, (kind, (tier, e)) in enumerate(sorted(best.items())):
            t = tk.Label(self.emu_ess_grid, bg=TILE, cursor="hand2", highlightthickness=1, highlightbackground=LINE,
                         text=kind[:4], fg=MUTED, font=(FONT, 7), width=4, height=2)
            t.grid(row=i // 9, column=i % 9, padx=1, pady=1)
            tip = f"{e.name}: {short(e.mod.text)} · {self._price_txt(e.name)}"
            t.bind("<Button-1>", lambda ev, x=e: self.emu_pick("essence", essence=x))
            t.bind("<Enter>", lambda ev, w=t, tp=tip: (w.configure(bg=TILE_HI, highlightbackground="#6b5124"),
                                                      self.emu_status.configure(text=tp, fg=MUTED)))
            t.bind("<Leave>", lambda ev, w=t: w.configure(bg=TILE, highlightbackground=LINE))
            img = self._row_icon(e.name, 28)
            if img is not None:
                t.configure(image=img, text="", width=30, height=30)
                t._img = img

    def emu_do(self, action, **kw):
        if not self.emu:
            self.emu_status.configure(text="Сначала нажми «Новый белый предмет».", fg=WARN)
            return
        try:
            if action == "undo":
                self.emu.undo()
                if self._emu_steps:
                    self._emu_steps.pop()
            else:
                before = self._emu_state()
                self.emu.apply(action, **kw)
                icon, label = self._step_of(action, kw)
                self._emu_steps.append((icon, label, self._emu_diff(before, self._emu_state())))
            self.emu_status.configure(text=self.emu.log[-1] if self.emu.log else "", fg=MUTED)
        except CraftError as e:
            self.emu_status.configure(text=str(e), fg=WARN)
        self._emu_render()

    def emu_unveil(self):
        if not self.emu:
            self.emu_status.configure(text="Сначала нажми «Новый белый предмет».", fg=WARN)
            return
        for w in self.emu_unveil_frame.winfo_children():
            w.destroy()
        try:
            opts = self.emu.unveil_options()
        except CraftError as e:
            self.emu_status.configure(text=str(e), fg=WARN)
            return
        tk.Label(self.emu_unveil_frame, text="Выбери мод:", bg=BG, fg=MUTED, font=(FONT, 9)).pack(anchor="w")
        for i, e in enumerate(opts):
            b = tk.Label(self.emu_unveil_frame, text="• " + e.mod.text.replace("\n", " / "), bg=BG, fg=GOOD,
                         cursor="hand2", font=(FONT, 9), anchor="w", justify="left", wraplength=300)
            b.pack(fill="x")
            b.bind("<Button-1>", lambda ev, k=i: self._emu_pick_unveil(k))

    def _emu_pick_unveil(self, k):
        for w in self.emu_unveil_frame.winfo_children():
            w.destroy()
        self.emu_do("unveil", index=k)

    def emu_essence(self):
        e = self._emu_ess.get(self.emu_ess_var.get()) if self.emu else None
        if not e:
            self.emu_status.configure(text="Выбери эссенцию в списке.", fg=WARN)
            return
        self.emu_pick("essence", essence=e)

    def emu_fossils(self):
        if not self.fos_sel:
            self.emu_status.configure(text="Выбери фоссилы — клик по иконкам на вкладке «Фоссилы».", fg=WARN)
            return
        self.emu_pick("fossils", fossils=[self.fos_list[n] for n in self.fos_sel])

    def emu_bench(self):
        sel = self.emu_bench_lb.curselection()
        key = self._emu_bench_keys[sel[0]] if sel and sel[0] < len(self._emu_bench_keys) else None
        o = self._emu_bench.get(key) if self.emu and key else None
        if not o:
            self.emu_status.configure(text="Выбери крафт верстака в списке.", fg=WARN)
            return
        self.emu_do("bench", option=o)

    def _emu_render(self):
        em = self.emu
        self._emu_fos_paint()
        if not em:
            self.emu_card.render(None)
            self._emu_goals_render(None, bool(self.selected))
            self._emu_journal_render()
            return
        targets = self._targets()
        ch = em.chances(targets) if targets else None
        self.emu_card.render(em, targets, self.prices)
        self._emu_goals_render(ch, bool(targets))
        self._emu_journal_render()

    STEP_ICONS = {
        "transmute": ("Orb of Transmutation", "Transmutation"), "alteration": ("Orb of Alteration", "Alteration"),
        "augment": ("Orb of Augmentation", "Augmentation"), "regal": ("Regal Orb", "Regal"),
        "alchemy": ("Orb of Alchemy", "Alchemy"), "chaos": ("Chaos Orb", "Chaos"), "exalt": ("Exalted Orb", "Exalted"),
        "annul": ("Orb of Annulment", "Annulment"), "scour": ("Orb of Scouring", "Scouring"),
        "divine": ("Divine Orb", "Divine"), "eldritch_chaos": ("Eldritch Chaos Orb", "Eldritch Chaos"),
        "eldritch_exalt": ("Eldritch Exalted Orb", "Eldritch Exalt"),
        "eldritch_annul": ("Eldritch Orb of Annulment", "Eldritch Annul"), "conflict": ("Orb of Conflict", "Conflict"),
        "veiled_chaos": ("Veiled Chaos Orb", "Veiled Chaos"), "veiled_exalt": ("Veiled Exalted Orb", "Veiled Exalt"),
        "unveil": ("Veiled Chaos Orb", "Unveil у Jun"), "remove_crafted": ("", "Снять крафты верстака"),
        "harvest_reforge": ("Wild Crystallised Lifeforce", "Harvest Reforge"),
        "harvest_same": ("Wild Crystallised Lifeforce", "Harvest: те же моды"),
        "harvest_augment": ("Wild Crystallised Lifeforce", "Harvest +мод/−мод"),
    }

    def _step_of(self, action, kw):
        if action == "essence":
            return kw["essence"].name, kw["essence"].name
        if action == "fossils":
            names = [f.name for f in kw["fossils"]]
            return names[0], " + ".join(names)
        if action == "conqueror":
            return kw["name"], inf.CONQUEROR_ORBS.get(kw["name"], kw["name"])
        if action == "eldritch_currency":
            side = "Exarch" if kw.get("side") == "exarch" else "Eater"
            return side, f"{inf.ELDRITCH_TIERS.get(kw.get('level'), '')} {'Ember' if side == 'Exarch' else 'Ichor'}"
        if action == "bench":
            return "", "Верстак: " + kw["option"]["mod"].text.splitlines()[0]
        icon, label = self.STEP_ICONS.get(action, ("", action))
        if kw.get("label"):
            label += f" ({kw['label']})"
        return icon, label

    def _emu_state(self) -> dict:
        em = self.emu
        mods = {}
        for m in em.mods:
            tier = "крафт" if m.crafted else ("скрыт" if m.veiled else f"T{m.entry.tier}")
            mods.setdefault(m.mod.id, []).append((m.text, tier, m.kind))
        impl = {s: getattr(em, s).text for s in ("exarch", "eater") if getattr(em, s)}
        return {"rarity": em.rarity, "mods": mods, "impl": impl, "infl": list(em.influences)}

    @staticmethod
    def _emu_diff(a: dict, b: dict) -> list[tuple[str, str]]:
        """[(вид, текст)]: вид = add / del / chg / m (редкость, влияние, имплициты)."""
        names = {"Normal": "обычный", "Magic": "магический", "Rare": "редкий"}
        out = []
        if a["rarity"] != b["rarity"]:
            out.append(("m", f"{names.get(a['rarity'], a['rarity'])} → {names.get(b['rarity'], b['rarity'])}"))
        for i in b["infl"]:
            if i not in a["infl"]:
                out.append(("add", f"влияние {i}"))
        for side, ttl in (("exarch", "Exarch"), ("eater", "Eater")):
            x, y = a["impl"].get(side), b["impl"].get(side)
            if x != y:
                out.append(("chg" if x and y else ("add" if y else "del"),
                            f"{ttl}: {x} → {y}" if x and y else f"{ttl}: {y or x}"))
        for mid in list(a["mods"]) + [k for k in b["mods"] if k not in a["mods"]]:
            old, new = a["mods"].get(mid, []), b["mods"].get(mid, [])
            if old == new:
                continue
            if old and new and len(old) == len(new):
                for o, n in zip(old, new):
                    if o != n:
                        out.append(("chg", f"{n[1]}  {o[0]} → {n[0]}"))
                continue
            for o in old[len(new):] if len(old) > len(new) else []:
                out.append(("del", f"{o[1]}  {o[0]}"))
            for n in new[len(old):] if len(new) > len(old) else []:
                out.append(("add", f"{n[1]}  {n[0]}"))
        if not out:
            out.append(("m", "ничего не изменилось"))
        return out

    def _emu_goals_render(self, ch, has_targets):
        g = self.emu_goals
        for w in g.winfo_children():
            w.destroy()
        if not has_targets:
            tk.Label(g, text="Отметь нужные моды во вкладке «Пул модов» (☐) — здесь появятся шансы "
                             "следующего Exalt'а и что ещё не хватает.", bg=BG1, fg=MUTED, font=(FONT, 9),
                     wraplength=300, justify="left", anchor="w").pack(fill="x", padx=8, pady=8)
            return
        if not ch:
            tk.Label(g, text="Создай предмет, чтобы увидеть шансы.", bg=BG1, fg=MUTED, font=(FONT, 9),
                     anchor="w").pack(fill="x", padx=8, pady=8)
            return
        from itemcard import render_chances
        render_chances(g, ch, BG1)

    def _emu_journal_render(self):
        j = self.emu_journal
        j.configure(state="normal")
        j.delete("1.0", "end")
        st = icons.store()
        if not self._emu_steps:
            j.insert("end", "Пока пусто — примени валюту, и здесь будет видно, что она добавила, убрала "
                            "или перекатила.", "m")
        for i, step in enumerate(self._emu_steps):
            icon, label = step[0], step[1]
            diff = step[2] if len(step) > 2 else []
            tag = f"s{i}"
            start = j.index("end-1c")
            img = st.get(icon, 18) if st and icon else None
            if img is not None:
                j.image_create("end", image=img, padx=2)
            j.insert("end", f" {i + 1}. {label}\n", ("step", tag))
            for kind, text in diff:
                mark = {"add": "+ ", "del": "− ", "chg": "~ ", "m": "  "}[kind]
                j.insert("end", "    ", tag)
                j.insert("end", mark + text + "\n", (kind, tag))
            j.tag_bind(tag, "<Button-1>", lambda e, k=i: self.emu_rewind(k + 1))
            j.tag_bind(tag, "<Enter>", lambda e, t=tag: j.tag_configure(t, background="#2a2116"))
            j.tag_bind(tag, "<Leave>", lambda e, t=tag: j.tag_configure(t, background=""))
        j.see("end")
        j.configure(state="disabled")

    def emu_rewind(self, n_steps: int):
        """Откатиться к состоянию после шага n (1 — после первого действия)."""
        if not self.emu:
            return
        try:
            while len(self._emu_steps) > n_steps:
                self.emu.undo()
                self._emu_steps.pop()
        except CraftError:
            self._emu_steps = self._emu_steps[:n_steps]
        self.emu_card._prev = None          # не подсвечивать «убрано» после отката на несколько шагов
        self.emu_status.configure(text=f"Вернулся к шагу {n_steps}." if n_steps else "Вернулся к началу.", fg=MUTED)
        self._emu_render()

    # ------------------------------------------------------------ сокеты
    def _build_sockets(self):
        f = self.tab_sock
        row = tk.Frame(f, bg=BG)
        row.pack(fill="x", padx=8, pady=(10, 4))
        self.sk_vars = {}
        for key, label, default, w in (("str", "Str", "0", 5), ("dex", "Dex", "0", 5), ("int", "Int", "0", 5),
                                       ("ilvl", "ilvl", "84", 4), ("q", "качество", "20", 4),
                                       ("n", "сокетов", "6", 3), ("R", "нужно R", "0", 3), ("G", "G", "0", 3),
                                       ("B", "B", "0", 3)):
            tk.Label(row, text=label, bg=BG, fg={"R": "#e07a5f", "G": GOOD, "B": BLUE}.get(key, MUTED),
                     font=(FONT, 9)).pack(side="left", padx=(8, 3))
            v = tk.StringVar(value=default)
            self._entry(row, v, w).pack(side="left")
            self.sk_vars[key] = v
        self._act(row, "Посчитать", self.calc_sockets).pack(side="left", padx=12)
        row2 = tk.Frame(f, bg=BG)
        row2.pack(fill="x", padx=8)
        self.sk_white = tk.BooleanVar(value=False)
        tk.Checkbutton(row2, text="белые сокеты (механика лиги 3.29: чем ниже ilvl, тем больше белых)",
                       variable=self.sk_white, bg=BG, fg=FG, selectcolor=BG2, activebackground=BG,
                       activeforeground=GOLD, font=(FONT, 9), highlightthickness=0, bd=0).pack(side="left")
        self._btn(row2, "взять требования базы", self._sock_from_base).pack(side="left", padx=10)
        self.sk_out = tk.Text(f, bg=BG1, fg=FG, relief="flat", wrap="word", font=(FONT, 10),
                              highlightthickness=1, highlightbackground=LINE, padx=12, pady=10, cursor="arrow")
        self.sk_out.pack(fill="both", expand=True, padx=8, pady=8)
        for tag, kw in (("h", dict(foreground=GOLD, font=(FONT, 11, "bold"))), ("m", dict(foreground=MUTED, font=(FONT, 9))),
                        ("best", dict(foreground=GOOD, font=(FONT, 10, "bold"))), ("bad", dict(foreground=WARN))):
            self.sk_out.tag_configure(tag, **kw)
        self.sk_out.insert("end", "Введи требования атрибутов предмета (или нажми «взять требования базы»), "
                                  "число сокетов и сколько нужно красных/зелёных/синих.", "m")
        self.sk_out.configure(state="disabled")

    def _sock_from_base(self):
        if not self.pool:
            return
        raw = self.data._load("base_items").get(self.pool.base.id, {})
        req = raw.get("requirements") or {}
        for key, k2 in (("str", "strength"), ("dex", "dexterity"), ("int", "intelligence")):
            self.sk_vars[key].set(str(req.get(k2, 0)))
        self.sk_vars["ilvl"].set(str(self.pool.ilvl))
        recipes = sk.bench_color_recipes(self.data, self.pool.base.item_class)
        self.sk_white.set(any(r[3] for r in recipes))

    def calc_sockets(self):
        try:
            v = {k: int(x.get() or 0) for k, x in self.sk_vars.items()}
        except ValueError:
            self._sock_msg("Нужны целые числа.", "bad")
            return
        n, want = v["n"], (v["R"], v["G"], v["B"])
        if not 1 <= n <= 6 or sum(want) == 0 or sum(want) > n:
            self._sock_msg("Сокетов 1–6, а нужных цветов — от 1 до числа сокетов.", "bad")
            return
        cls = self.pool.base.item_class if self.pool else "Body Armour"
        recipes = sk.bench_color_recipes(self.data, cls) or None
        white = sk.white_chance(v["ilvl"], v["q"]) if self.sk_white.get() else 0.0
        res, ch = sk.methods(v["str"], v["dex"], v["int"], n, want, self.prices.get("Chromatic Orb") or 0.2,
                             white, recipes)
        o = self.sk_out
        o.configure(state="normal")
        o.delete("1.0", "end")
        o.insert("end", "Шанс цвета одного сокета: ", "m")
        o.insert("end", f"R {ch[0] * (1 - white):.1%} · G {ch[1] * (1 - white):.1%} · B {ch[2] * (1 - white):.1%}"
                        + (f" · белый {white:.1%}" if white else "") + "\n\n")
        for i, m in enumerate(res):
            o.insert("end", m["name"], "h")
            if i == 0:
                o.insert("end", "   дешевле всего", "best")
            o.insert("end", f"\n  шанс {m['chance']:.3%} · в среднем ~{m['tries']:,.0f} попыток · "
                            f"~{m['cost']:,.0f} Chromatic ≈ {m['cost_chaos']:,.0f}c\n\n".replace(",", " "))
        if not res:
            o.insert("end", "Так не получится.", "bad")
        o.insert("end", "Формула — как в калькуляторе Siveran (siveran.github.io). Число сокетов и связи "
                        "надёжнее делать верстаком: 6 сокетов — 350 Jeweller's, 6 связей — 1500 Fusing.", "m")
        o.configure(state="disabled")

    def _sock_msg(self, text, tag="m"):
        o = self.sk_out
        o.configure(state="normal")
        o.delete("1.0", "end")
        o.insert("end", text, tag)
        o.configure(state="disabled")

    # ------------------------------------------------------------ окно
    def _focus_input(self, e):
        w = e.widget
        try:
            if isinstance(w, (tk.Entry, ttk.Combobox, ttk.Entry)) and w.winfo_toplevel() is self:
                self.focus_force()
                w.focus_set()
        except Exception:
            pass

    def _drag_start(self, e):
        self._dx, self._dy = e.x_root - self.winfo_x(), e.y_root - self.winfo_y()

    def _drag_move(self, e):
        self.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    def _resize_start(self, e):
        self._rw, self._rh, self._rx, self._ry = self.winfo_width(), self.winfo_height(), e.x_root, e.y_root

    def _resize_move(self, e):
        w = max(640, self._rw + e.x_root - self._rx)
        h = max(420, self._rh + e.y_root - self._ry)
        self.geometry(f"{w}x{h}")

    def _frameless(self):
        """Убираем системный заголовок и рамку, но окно остаётся «обычным» для Windows —
        поэтому клавиатура работает (в отличие от overrideredirect)."""
        import sys
        if sys.platform != "win32":
            return
        try:
            import ctypes
            u = ctypes.windll.user32
            hwnd = int(self.wm_frame(), 16)
            GWL_STYLE, WS_CAPTION, WS_THICKFRAME = -16, 0x00C00000, 0x00040000
            WS_MINIMIZEBOX, WS_MAXIMIZEBOX, WS_SYSMENU = 0x00020000, 0x00010000, 0x00080000
            style = u.GetWindowLongW(hwnd, GWL_STYLE)
            if not style & WS_CAPTION:
                return  # уже без рамки
            style &= ~(WS_CAPTION | WS_THICKFRAME | WS_MAXIMIZEBOX)
            style |= WS_MINIMIZEBOX | WS_SYSMENU   # чтобы работало сворачивание
            u.SetWindowLongW(hwnd, GWL_STYLE, style)
            SWP = 0x0001 | 0x0002 | 0x0004 | 0x0020  # NOSIZE|NOMOVE|NOZORDER|FRAMECHANGED
            u.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP)
            self._hwnd = hwnd
        except Exception:
            pass

    def minimize(self):
        self.iconify()

    def _on_configure(self, e):
        if e.widget is self:
            if getattr(self, "_geo_job", None):
                self.after_cancel(self._geo_job)
            self._geo_job = self.after(800, self._remember)

    def _remember(self):
        self.settings["main_geo"] = self.geometry()
        self._save_settings(self.settings)

    def cycle_alpha(self):
        levels = [0.95, 0.8, 0.65, 1.0]
        cur = self.settings.get("main_alpha", 0.95)
        nxt = levels[(levels.index(cur) + 1) % len(levels)] if cur in levels else 0.95
        self.settings["main_alpha"] = nxt
        self.attributes("-alpha", nxt)
        self._save_settings(self.settings)

    def hide(self):
        self._remember()
        self.withdraw()

    def show(self):
        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)
        self.after(30, self._frameless)

    def _keep_on_top(self):
        try:
            if self.state() == "normal" and not popdown_open():
                self.attributes("-topmost", True)
        except tk.TclError:
            return
        self.after(2000, self._keep_on_top)

    # ------------------------------------------------------------ данные
    def _refresh_prices(self):
        self.prices.refresh()
        self.q.put(("prices",))

    def _filter_bases(self, e):
        if e.keysym in ("Return", "Up", "Down", "Escape", "Tab"):
            return
        # фильтруем с задержкой, чтобы не тормозить ввод
        if getattr(self, "_filter_job", None):
            self.after_cancel(self._filter_job)
        self._filter_job = self.after(300, self._apply_base_filter)

    def _apply_base_filter(self):
        self._filter_job = None
        s = self.base_var.get().lower()
        self.base_box["values"] = [n for n in self.base_names if s in n.lower()] or self.base_names

    def load_pool(self):
        name = self.base_var.get().strip()
        base = self.data.bases.get(name)
        if not base:
            hits = [n for n in self.base_names if name.lower() in n.lower()]
            if len(hits) == 1:
                base = self.data.bases[hits[0]]
                self.base_var.set(hits[0])
            else:
                self.status.configure(text=f"Не нашёл базу «{name}». Выбери из списка.", fg=WARN)
                return
        try:
            ilvl = max(1, min(100, int(self.ilvl_var.get())))
        except ValueError:
            ilvl = 84
            self.ilvl_var.set("84")
        if not self.pool or self.pool.base.name != base.name:
            self.selected.clear()
        self.inf_map = inf.influence_tags(self.data, base.item_class)
        self.inf_box["values"] = ["нет"] + list(self.inf_map)
        if self.inf_var.get() not in self.inf_box["values"]:
            self.inf_var.set("нет")
        infl = self.inf_var.get()
        base_extra = set()
        if base.domain == "affliction_jewel":
            ench = self._cluster_enchants(base)
            names = list(ench)
            self.ench_box["values"] = names
            if self.ench_var.get() not in ench:
                self.ench_var.set(names[0] if names else "")
            if self.ench_var.get() in ench:
                base_extra.add(ench[self.ench_var.get()])
            self.ench_frame.pack(side="left", before=self.pool_hint)
        else:
            self.ench_frame.pack_forget()
        if base.item_class in sk.CATALYST_CLASSES:
            self.cat_frame.pack(side="left", before=self.pool_hint)
        else:
            self.cat_frame.pack_forget()
            self.cat_var.set("нет")
        extra = set(base_extra)
        if infl in self.inf_map:
            extra.add(self.inf_map[infl])
        self.base_pool = ModPool(self.data, base, ilvl, base_extra or None)
        self.pool = ModPool(self.data, base, ilvl, extra) if extra != base_extra else self.base_pool
        if self.cat_var.get() in sk.CATALYSTS:
            self.pool = sk.apply_catalyst(self.pool, self.cat_var.get(), 20)
        self.table = pool_table(self.pool)
        self.settings.update(main_base=base.name, main_ilvl=ilvl)
        self._save_settings(self.settings)
        cls = recipes.CLASS_RU.get(base.item_class, base.item_class) if i18n.lang() == "ru" else base.item_class
        infl = self.inf_var.get()
        self.info_lbl.configure(text=f"{cls}" + (f" · влияние {infl} (◆ — его моды)" if infl in self.inf_map else ""))
        self.status.configure(text=f"{len(self.table['groups'])} {i18n.t('групп модов · вес префиксов')} "
                                   f"{self.table['prefix_weight']:,} · {i18n.t('суффиксов')} {self.table['suffix_weight']:,}"
                              .replace(",", " "), fg=MUTED)
        # выбранные моды, которых нет на новой базе/ilvl, убираем
        keys = {(g["kind"], g["type"]) for g in self.table["groups"]}
        for k in list(self.selected):
            if k not in keys:
                del self.selected[k]
        self._render_pool()
        self._render_targets()
        self._fill_essences()
        if getattr(self, "emu", None) and self.emu.pool.base.name != self.pool.base.name:
            self.emu = None
            self._emu_render()
            self.emu_status.configure(text="База сменилась — нажми «Новый белый предмет».", fg=MUTED)
        elif getattr(self, "emu", None):
            self.emu.base_pool = self.base_pool  # ilvl мог поменяться
            self.emu.pool = self.emu._make_pool()

    def _cluster_enchants(self, base) -> dict:
        """{'12% increased Fire Damage (Fire Damage)': 'affliction_fire_damage', ...} для размера кластера."""
        if not hasattr(self, "_cj"):
            self._cj = self.data._load("cluster_jewels")
        cj = next((v for k, v in self._cj.items() if v["name"] == base.name), None)
        out = {}
        for ps in (cj or {}).get("passive_skills", []):
            out[ps["name"]] = ps["tag"]
        return dict(sorted(out.items()))

    def _render_pool(self):
        if not self.table:
            return
        f = self.filter_var.get().lower().strip()
        for kind, tv in self.trees.items():
            tv.delete(*tv.get_children())
            top = max((g["chance_kind"] for g in self.table["groups"] if g["kind"] == kind), default=0) or 1
            for g in self.table["groups"]:
                if g["kind"] != kind:
                    continue
                if f and f not in g["text"].lower() and f not in g["type"].lower() and f not in " ".join(g["tags"]):
                    continue
                key = (g["kind"], g["type"])
                sel = self.selected.get(key)
                avail = [t for t in g["tiers"] if t["available"]]
                worst = max(t["tier"] for t in avail)
                tier = sel["max_tier"] if sel else min(3, worst)
                gid = f"{g['kind']}|{g['type']}"
                is_inf = any(inf.is_influence_mod(e.mod) for e in self.pool.all
                             if e.mod.kind == g["kind"] and e.mod.type == g["type"])
                tv.insert("", "end", iid=gid, text=("◆ " if is_inf else "") + short(g["text"]),
                          values=("☑" if sel else "☐", pct(g["chance_all"]), pct(g["chance_kind"]),
                                  weight_bar(g["chance_kind"] / top), f"{i18n.t('до T')}{tier}"),
                          tags=("sel",) if sel else (("infl",) if is_inf else ()))
                for t in g["tiers"]:
                    rng_ = " ".join(__import__("re").findall(r"\([\d.]+-[\d.]+\)|(?<![\w(])\d+(?:\.\d+)?(?![\w)-])", t["text"]))
                    tv.insert(gid, "end", text=f"T{t['tier']}  {rng_}   {t['name']} · ilvl {t['level']}",
                              values=("", "", f"{t['weight']}", "", ""), tags=("tier" if t["available"] else "na",))

    def _group(self, gid: str):
        kind, typ = gid.split("|", 1)
        return next((g for g in self.table["groups"] if g["kind"] == kind and g["type"] == typ), None)

    def _tree_click(self, e, tv: ttk.Treeview):
        region = tv.identify_region(e.x, e.y)
        if region != "cell" and region != "tree":
            return
        iid = tv.identify_row(e.y)
        col = tv.identify_column(e.x)
        if not iid or "|" not in iid:
            return
        g = self._group(iid)
        if not g:
            return
        key = (g["kind"], g["type"])
        avail = sorted(t["tier"] for t in g["tiers"] if t["available"])
        cur = tv.set(iid, "tier")
        import re as _re
        _m = _re.search(r"(\d+)$", cur or "")
        cur_t = int(_m.group(1)) if _m else min(3, avail[-1])
        if col == "#1":  # ☐
            if key in self.selected:
                del self.selected[key]
            else:
                self.selected[key] = {"max_tier": cur_t, "label": short(g["text"])}
        elif col == "#5":  # тир по кругу
            nxt = avail[(avail.index(cur_t) + 1) % len(avail)] if cur_t in avail else avail[0]
            tv.set(iid, "tier", f"{i18n.t('до T')}{nxt}")
            if key in self.selected:
                self.selected[key]["max_tier"] = nxt
            return "break"
        else:
            return
        sel = key in self.selected
        tv.set(iid, "chk", "☑" if sel else "☐")
        tv.item(iid, tags=("sel",) if sel else ())
        return "break"

    def _render_targets(self):
        if not self.selected:
            self.targets_lbl.configure(text="ничего не выбрано", fg=MUTED)
            return
        lines = [f"{i18n.t('П') if k[0] == 'prefix' else i18n.t('С')} · {v['label']}  — {i18n.t('до T')}{v['max_tier']}"
                 for k, v in self.selected.items()]
        self.targets_lbl.configure(text="\n".join(lines), fg=FG)

    # ------------------------------------------------------------ расчёт
    def calculate(self):
        if not self.pool or not self.selected:
            self.calc_status.configure(text="Сначала выбери базу и отметь нужные моды.", fg=WARN)
            return
        targets = [Target(k[0], k[1], v["max_tier"], v["label"]) for k, v in self.selected.items()]
        self.calc_status.configure(text="считаю… (Chaos-симуляция может занять несколько секунд)", fg=MUTED)
        pool = self.pool
        use_e, use_f, use_h = self.use_ess.get(), self.use_fos.get(), self.use_hv.get()

        def work():
            res = calculate(pool, targets, self.prices)
            try:
                if use_e:
                    res += cc.best_essences(self.data, pool, targets, self.prices)
                if use_f:
                    res += cc.best_fossils(self.data, pool, targets, self.prices)
                if use_h:
                    from poecraft.harvest import best_harvest
                    res += best_harvest(pool, targets, self.prices)
            except Exception as e:
                res.append({"name": "Ошибка расчёта", "how": str(e), "chance": 0, "use": {}, "cost_chaos": None})
            res.sort(key=lambda r: (r["cost_chaos"] is None, r["cost_chaos"] or 0, -(r.get("chance") or 0)))
            self.q.put(("calc", res, "out"))
        threading.Thread(target=work, daemon=True).start()

    def _show_results(self, results, target="out"):
        o = getattr(self, target)
        o.configure(state="normal")
        o.delete("1.0", "end")
        best = next((r for r in results if r["cost_chaos"] is not None), None)
        dv = self.prices.divine
        st = icons.store()
        for r in results:
            for n in (st.find_all(r["name"] + " " + r["how"][:80], 4) if st else []):
                img = st.get(n, 22)
                if img is not None:
                    o.image_create("end", image=img, padx=1)
            o.insert("end", (" " if st else "") + r["name"], "h")
            if r is best:
                o.insert("end", "   дешевле всего", "best")
            o.insert("end", "\n" + r["how"] + "\n", "m")
            o.insert("end", money(r["cost_chaos"], dv, r.get("chance") or 0) + "\n",
                     "big" if r["cost_chaos"] is not None else "bad")
            if r.get("chance_label"):
                o.insert("end", r["chance_label"] + "\n")
            elif r["chance"]:
                o.insert("end", f"Шанс за попытку: {pct(r['chance'])} · в среднем ~{r['attempts']:,.0f} попыток\n"
                         .replace(",", " "))
            use = [f"{k}: ~{v:,.1f}".replace(",", " ") if v < 10 else f"{k}: ~{v:,.0f}".replace(",", " ")
                   for k, v in r["use"].items() if v > 0.05]
            if use:
                o.insert("end", "  " + "   ·   ".join(use) + "\n", "m")
            if r.get("note"):
                o.insert("end", "  ⚠ " + r["note"] + "\n", "bad")
            o.insert("end", "\n")
        if not results:
            o.insert("end", "Для такого набора модов пока нет подходящих методов.", "m")
        o.configure(state="disabled")
        st = self.calc_status if target == "out" else self.ef_status
        st.configure(text=f"цены: {self.prices.league}, {self.prices.source}", fg=MUTED)

    def save_goal(self):
        name = self.goal_name.get().strip()
        if not self.pool or not self.selected:
            self.calc_status.configure(text="Сначала выбери базу и нужные моды.", fg=WARN)
            return
        if not name:
            self.calc_status.configure(text="Введи название крафта.", fg=WARN)
            return
        rec = {"name": name, "base_class": self.pool.base.item_class, "base": self.pool.base.name,
               "min_ilvl": self.pool.ilvl,
               "wanted": [{"label": v["label"], "mod_type": k[1], "kind": k[0], "max_tier": v["max_tier"]}
                          for k, v in self.selected.items()]}
        try:
            path = recipes.save(rec, APP_DIR / "goals")
            code = recipes.encode(rec)
        except Exception as e:
            self.calc_status.configure(text=f"Ошибка: {e}", fg=WARN)
            return
        self.code_var.set(code)
        self.calc_status.configure(text=f"Сохранено: goals/{path.name} — уже есть в списке оверлея.", fg=GOOD)
        if self.on_goal_saved:
            self.on_goal_saved(path.name)

    def copy_code(self):
        if self.code_var.get():
            self.clipboard_clear()
            self.clipboard_append(self.code_var.get())
            self.calc_status.configure(text="Код скопирован.", fg=GOOD)

    def _poll(self):
        try:
            while True:
                m = self.q.get_nowait()
                if m[0] == "prices":
                    self.price_lbl.configure(text=f"{self.prices.league} · 1 div = {self.prices.divine:.0f}c · {self.prices.source}")
                    self._fill_fossils()
                    self._fill_essences()
                elif m[0] == "calc":
                    self._show_results(m[1], m[2] if len(m) > 2 else "out")
        except queue.Empty:
            pass
        try:
            self.after(150, self._poll)
        except tk.TclError:
            pass
