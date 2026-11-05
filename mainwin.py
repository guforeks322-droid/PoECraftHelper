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


NONE = i18n.t("нет")


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
        self.title(i18n.t("PoE Craft Helper — мастерская"))
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
            self._paint_base_art()
            for w, n, sz in getattr(self, "_iconed_fixed", []):
                if w.winfo_exists():
                    img = self._row_icon(n, sz)
                    if img is not None:
                        w.configure(image=img, text="", width=sz + 4, height=sz + 4)
                        w._img = img
            if self.emu:
                self._emu_lists()
                self.emu_card._prev = None
                self._emu_render()
        except Exception:
            pass

    def _paint_base_art(self, base=None):
        base = base or (self.pool.base if self.pool else None)
        st = icons.store()
        img = None
        if st and base:
            dds = (self.data.base_raw.get(base.id, {}).get("visual_identity") or {}).get("dds_file", "")
            img = st.base_art(base.id, dds, 42, 60)
        self.base_art.configure(image=img or "", width=0 if img else 6)
        self.base_art._img = img

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

        bar_ = tk.Frame(self, bg=BG1, highlightthickness=1, highlightbackground=LINE)
        bar_.pack(fill="x", padx=8, pady=(8, 4))
        ctl = tk.Frame(bar_, bg=BG1)
        ctl.pack(fill="x", padx=6, pady=4)
        self.base_art = tk.Label(ctl, bg=BG1, width=6)
        self.base_art.pack(side="left", padx=(0, 8))
        tk.Label(ctl, text="База", bg=BG1, fg=MUTED, font=(FONT, 9)).pack(side="left")
        self.base_var = tk.StringVar()
        self.base_box = ttk.Combobox(ctl, textvariable=self.base_var, values=self.base_names,
                                     style="D.TCombobox", width=30, font=(FONT, 10))
        popdown_on_top(self.base_box)
        self.base_box.pack(side="left", padx=(4, 10))
        self.base_box.bind("<KeyRelease>", self._filter_bases)
        self.base_box.bind("<<ComboboxSelected>>", lambda e: self.load_pool())
        self.base_box.bind("<Return>", lambda e: self.load_pool())
        tk.Label(ctl, text="ilvl", bg=BG1, fg=MUTED, font=(FONT, 9)).pack(side="left")
        self.ilvl_var = tk.StringVar(value=str(self.settings.get("main_ilvl", 84)))
        il = self._entry(ctl, self.ilvl_var, 5)
        il.pack(side="left", padx=(4, 10))
        il.bind("<Return>", lambda e: self.load_pool())
        tk.Label(ctl, text="влияние", bg=BG1, fg=MUTED, font=(FONT, 9)).pack(side="left")
        self.inf_var = tk.StringVar(value=NONE)
        self.inf_box = ttk.Combobox(ctl, textvariable=self.inf_var, state="readonly", style="D.TCombobox",
                                    values=[NONE], width=11, font=(FONT, 9))
        popdown_on_top(self.inf_box)
        self.inf_box.pack(side="left", padx=(4, 2))
        self.inf_box.bind("<<ComboboxSelected>>", lambda e: (self._paint_influence(), self.load_pool()))
        self.inf_icon = tk.Label(ctl, bg=BG1)
        self.inf_icon.pack(side="left", padx=(0, 10))
        self._act(ctl, "Показать моды", self.load_pool).pack(side="left")
        self.info_lbl = tk.Label(ctl, text="", bg=BG1, fg=MUTED, font=(FONT, 9))
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
        self.tab_plan = tk.Frame(self.nb, bg=BG)
        self.nb.add(self.tab_plan, text="Рецепты")
        self.tab_sock = tk.Frame(self.nb, bg=BG)
        self.nb.add(self.tab_sock, text="Сокеты")

        self.nb.bind("<<NotebookTabChanged>>", lambda e: self._render_targets())
        self._build_pool()
        self._build_calc()
        self._build_ef()
        self._build_emu()
        self._build_plans()
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
        self.cat_var = tk.StringVar(value=NONE)
        cb = ttk.Combobox(self.cat_frame, textvariable=self.cat_var, state="readonly", style="D.TCombobox",
                          values=[NONE] + list(sk.CATALYSTS), width=20, font=(FONT, 9))
        popdown_on_top(cb)
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda e: self.load_pool())
        # сводка как на Craft of Exile: сколько групп, веса, цели, блокировки
        self.pool_stats = tk.Frame(self.tab_pool, bg=BG)
        self.pool_stats.pack(fill="x", padx=4, pady=(2, 6))
        self._stat_lbls = {}
        for key, cap in (("groups", "групп модов"), ("pw", "вес префиксов"), ("sw", "вес суффиксов"),
                         ("sel", "нужных модов"), ("blk", "заблокировано")):
            c = tk.Frame(self.pool_stats, bg=BG1, highlightthickness=1, highlightbackground=LINE)
            c.pack(side="left", padx=(0, 6), ipadx=8)
            v = tk.Label(c, text="—", bg=BG1, fg=GOLD if key in ("sel",) else FG, font=(FONT, 12, "bold"))
            v.pack(anchor="w", padx=8, pady=(4, 0))
            tk.Label(c, text=cap, bg=BG1, fg=MUTED, font=(FONT, 8)).pack(anchor="w", padx=8, pady=(0, 4))
            self._stat_lbls[key] = v
        self.pool_hint = tk.Label(self.pool_stats, text="☐ — нужен мод · «до T» — худший тир · двойной клик — тиры\n"
                                                        "правый клик — заблокировать мод (уйдёт из пула и шансов)",
                                  bg=BG, fg=MUTED, font=(FONT, 8), justify="left")
        self.pool_hint.pack(side="right", padx=6)

        cols = tk.Frame(self.tab_pool, bg=BG)
        cols.pack(fill="both", expand=True)
        cols.columnconfigure(0, weight=1, uniform="c")
        cols.columnconfigure(1, weight=1, uniform="c")
        cols.rowconfigure(1, weight=1)
        self.trees = {}
        self._pool_caps = {}
        for i, (kind, name) in enumerate((("prefix", "ПРЕФИКСЫ"), ("suffix", "СУФФИКСЫ"))):
            lbl = tk.Label(cols, text=name, bg=BG, fg=GOLD, font=(FONT, 9, "bold"), anchor="w")
            lbl.grid(row=0, column=i, sticky="we", padx=4)
            self._pool_caps[kind] = lbl
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
            tv.bind("<Button-3>", lambda e, t=tv: self._tree_block(e, t))
            tv.tag_configure("blocked", foreground="#5a5248", font=(FONT, 9, "overstrike"))
            self.trees[kind] = tv

    def _build_calc(self):
        """Калькулятор: слева цели и настройки, справа карточки методов (как сравнение на Craft of Exile)."""
        from ui_cards import ScrollList
        f = self.tab_calc
        left = tk.Frame(f, bg=BG, width=300)
        left.pack(side="left", fill="y", padx=(6, 6), pady=8)
        left.pack_propagate(False)
        self._cap(left, "Цели")
        self.targets_box = tk.Frame(left, bg=BG1, highlightthickness=1, highlightbackground=LINE)
        self.targets_box.pack(fill="x", pady=(2, 10))
        self.targets_lbl = tk.Label(self.targets_box, text="", bg=BG1)   # совместимость
        self._cap(left, "Методы")
        opts = tk.Frame(left, bg=BG1, highlightthickness=1, highlightbackground=LINE)
        opts.pack(fill="x", pady=(2, 10))
        tk.Label(opts, text="Всегда: Alt+Aug, Alt→Regal, Chaos", bg=BG1, fg=MUTED, font=(FONT, 9),
                 anchor="w").pack(fill="x", padx=8, pady=(6, 2))
        self.use_ess = tk.BooleanVar(value=True)
        self.use_fos = tk.BooleanVar(value=True)
        self.use_hv = tk.BooleanVar(value=True)
        for text, var in (("+ эссенции", self.use_ess), ("+ фоссилы", self.use_fos), ("+ Harvest", self.use_hv)):
            tk.Checkbutton(opts, text=text, variable=var, bg=BG1, fg=FG, selectcolor=BG2, activebackground=BG1,
                           activeforeground=GOLD, font=(FONT, 9), highlightthickness=0, bd=0,
                           anchor="w").pack(fill="x", padx=8)
        tk.Frame(opts, bg=BG1, height=6).pack()
        self._act(left, "Посчитать", self.calculate).pack(fill="x")
        self.calc_status = tk.Label(left, text="", bg=BG, fg=MUTED, font=(FONT, 8), anchor="w", justify="left",
                                    wraplength=290)
        self.calc_status.pack(fill="x", pady=(4, 10))
        self._cap(left, "Трейд")
        tf = tk.Frame(left, bg=BG1, highlightthickness=1, highlightbackground=LINE)
        tf.pack(fill="x", pady=(2, 10))
        tr = tk.Frame(tf, bg=BG1)
        tr.pack(fill="x", padx=8, pady=6)
        self._btn(tr, "⌕ купить базу", self.trade_base).pack(side="left")
        self._btn(tr, "⌕ готовый предмет", self.trade_ready).pack(side="left", padx=(6, 0))
        tk.Label(tf, text="Откроет официальный трейд в браузере: белая база этого ilvl или уже готовый "
                          "предмет с нужными модами — сравни с ценой крафта.", bg=BG1, fg=DIM, font=(FONT, 8),
                 wraplength=270, justify="left", anchor="w").pack(fill="x", padx=8, pady=(0, 6))
        self._cap(left, "Сохранить как крафт")
        sv = tk.Frame(left, bg=BG1, highlightthickness=1, highlightbackground=LINE)
        sv.pack(fill="x", pady=(2, 0))
        self.goal_name = tk.StringVar()
        self._entry(sv, self.goal_name, 30).pack(fill="x", padx=8, pady=(8, 4))
        self._act(sv, "Сохранить и получить код", self.save_goal).pack(fill="x", padx=8)
        self.code_var = tk.StringVar()
        self.code_entry = tk.Entry(sv, textvariable=self.code_var, bg=BG2, fg=GOOD, relief="flat",
                                   readonlybackground=BG2, state="readonly", font=("Consolas", 8))
        self.code_entry.pack(fill="x", padx=8, pady=(6, 2))
        self._btn(sv, "скопировать код", self.copy_code).pack(anchor="e", padx=4, pady=(0, 6))

        right = tk.Frame(f, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(0, 6), pady=8)
        self._cap(right, "Сравнение методов")
        self.out = ScrollList(right)
        self.out.pack(fill="both", expand=True, pady=(2, 0))
        self.out.message("Отметь нужные моды во вкладке «Пул модов» и нажми «Посчитать» — здесь появятся "
                         "все способы с ценой, шансом и расходом валюты, самый дешёвый — первым.")

    # ------------------------------------------------------------ эссенции и фоссилы
    def _build_ef(self):
        """Эссенции и фоссилы: выбор иконками, наглядный сдвиг шансов и карточка цены."""
        from ui_cards import ScrollList
        f = self.tab_ef
        self.fos_sel: list[str] = []
        self.ef_ess: str | None = None
        self.ess_list: dict[str, cc.Essence] = {}
        self.fos_list = {x.name: x for x in cc.fossils(self.data)}

        left = tk.Frame(f, bg=BG, width=372)
        left.pack(side="left", fill="y", padx=(6, 6), pady=8)
        left.pack_propagate(False)
        self._cap(left, "Эссенции для этой базы")
        self.ef_ess_grid = tk.Frame(left, bg=BG1, highlightthickness=1, highlightbackground=LINE)
        self.ef_ess_grid.pack(fill="x", pady=(2, 2))
        self.ef_tier_row = tk.Frame(left, bg=BG)
        self.ef_tier_row.pack(fill="x", pady=(0, 8))
        self._cap(left, "Фоссилы — до 4")
        self.ef_fos_grid = tk.Frame(left, bg=BG1, highlightthickness=1, highlightbackground=LINE)
        self.ef_fos_grid.pack(fill="x", pady=(2, 8))
        self.ef_sel_lbl = tk.Label(left, text="ничего не выбрано", bg=BG, fg=MUTED, font=(FONT, 9), anchor="w",
                                   justify="left", wraplength=360)
        self.ef_sel_lbl.pack(fill="x")
        row = tk.Frame(left, bg=BG)
        row.pack(fill="x", pady=6)
        self._act(row, "Посчитать выбранное", self.calculate_ef).pack(side="left")
        self._btn(row, "сброс", self._ef_clear).pack(side="left", padx=8)
        self.ef_status = tk.Label(left, text="", bg=BG, fg=MUTED, font=(FONT, 8), anchor="w", justify="left",
                                  wraplength=360)
        self.ef_status.pack(fill="x")

        right = tk.Frame(f, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(0, 6), pady=8)
        self._cap(right, "Как сдвинулись шансы")
        self.ef_shift_box = ScrollList(right)
        self.ef_shift_box.configure(height=300)
        self.ef_shift_box.pack(fill="both", expand=True, pady=(2, 8))
        self.ef_shift = self.ef_shift_box          # совместимость со старым кодом
        self._cap(right, "Цена крафта")
        self.ef_out = ScrollList(right, height=170)
        self.ef_out.pack(fill="x", pady=(2, 0))
        self.ef_out.message("Выбери эссенцию или фоссилы и нажми «Посчитать выбранное».")
        self._fill_fossils()
        self._show_shift()

    def _price_txt(self, name):
        v = self.prices.get(name)
        return f"{v:.1f}c" if v and v < 10 else (f"{v:.0f}c" if v else "—")

    def _ef_tile(self, parent, i, name, text, selected, cmd, tip, cols=9):
        t = tk.Label(parent, text=text, bg=TILE, fg=MUTED, font=(FONT, 7), cursor="hand2", width=4, height=2,
                     highlightthickness=2, highlightbackground=GOLD if selected else TILE)
        t.grid(row=i // cols, column=i % cols, padx=1, pady=1)
        img = self._row_icon(name, 30)
        if img is not None:
            t.configure(image=img, text="", width=34, height=34)
            t._img = img
        t.bind("<Button-1>", lambda e: cmd())
        t.bind("<Enter>", lambda e: self.status.configure(text=tip, fg=MUTED))
        return t

    def _fill_fossils(self):
        g = getattr(self, "ef_fos_grid", None)
        if g is None:
            return
        for w in g.winfo_children():
            w.destroy()
        for i, (name, fo) in enumerate(self.fos_list.items()):
            self._ef_tile(g, i, name, name.replace(" Fossil", "")[:5], name in self.fos_sel,
                          lambda n=name: self._fossil_toggle(n), f"{name}: {fo.describe} · {self._price_txt(name)}",
                          cols=8)
        self._ef_sel_paint()

    def _fill_essences(self):
        g = getattr(self, "ef_ess_grid", None)
        if g is None:
            return
        for w in g.winfo_children():
            w.destroy()
        self.ess_list = {}
        if not self.pool:
            tk.Label(g, text="выбери базу сверху", bg=BG1, fg=MUTED, font=(FONT, 9)).pack(padx=8, pady=8)
            return
        # по одной иконке на вид эссенции; тир выбирается строкой ниже
        order = {t: i for i, t in enumerate(icons.ESSENCE_TIERS)}
        kinds: dict[str, list] = {}
        for e in cc.essences_for(self.data, self.pool.base.item_class):
            if e.max_ilvl and self.pool.ilvl > e.max_ilvl:
                continue
            self.ess_list[e.id] = e
            tier, _, kind = e.name.partition(" Essence of ")
            if not kind:
                tier, kind = "", e.name.replace("Essence of ", "")
            kinds.setdefault(kind, []).append((order.get(tier, -1), e))
        cur = self.ess_list.get(self.ef_ess) if self.ef_ess else None
        cur_kind = cur.name.partition(" Essence of ")[2] or cur.name.replace("Essence of ", "") if cur else None
        for i, (kind, lst) in enumerate(sorted(kinds.items())):
            lst.sort(key=lambda x: x[0])
            best = lst[0][1]
            fe = cc.essence_entry(self.pool, best.mod)
            self._ef_tile(g, i, best.name, kind[:5], kind == cur_kind, lambda x=best.id: self._essence_toggle(x),
                          f"{kind}: {short(best.mod.text)} (лучший тир T{fe.tier}) · {self._price_txt(best.name)}",
                          cols=8)
        self._ess_kinds = kinds
        tr = getattr(self, "ef_tier_row", None)
        if tr is not None:
            for w in tr.winfo_children():
                w.destroy()
            if cur_kind and cur_kind in kinds:
                tk.Label(tr, text="тир:", bg=BG, fg=MUTED, font=(FONT, 8)).pack(side="left")
                for _, e in kinds[cur_kind]:
                    t = e.name.split(" Essence")[0] if " Essence of " in e.name else "—"
                    b = tk.Label(tr, text=t, bg=BG, fg=GOLD if e.id == self.ef_ess else MUTED, font=(FONT, 8),
                                 cursor="hand2", padx=3)
                    b.pack(side="left")
                    b.bind("<Button-1>", lambda ev, x=e.id: self._essence_pick_tier(x))
        if self.ef_ess not in self.ess_list:
            self.ef_ess = None
        self._ef_sel_paint()

    def _essence_pick_tier(self, eid):
        self.ef_ess = eid
        self._fill_essences()
        self._show_shift()

    def _essence_toggle(self, eid):
        self.ef_ess = None if self.ef_ess == eid else eid
        if self.ef_ess:
            self.fos_sel.clear()
            self._fill_fossils()
        self._fill_essences()
        self._show_shift()

    def _fossil_toggle(self, name):
        if name in self.fos_sel:
            self.fos_sel.remove(name)
        elif len(self.fos_sel) < 4:
            self.fos_sel.append(name)
        else:
            self.ef_status.configure(text="Максимум 4 фоссила (резонатор Prime).", fg=WARN)
        if self.fos_sel and self.ef_ess:
            self.ef_ess = None
            self._fill_essences()
        self._fill_fossils()
        self._emu_fos_paint()
        self._show_shift()

    def _fossil_click(self, e):        # старый обработчик таблицы — больше не используется
        return "break"

    def _ef_clear(self):
        self.fos_sel.clear()
        self.ef_ess = None
        self._fill_fossils()
        self._fill_essences()
        self._emu_fos_paint()
        self._show_shift()

    def _ef_sel_paint(self):
        if not hasattr(self, "ef_sel_lbl"):
            return
        key = (self.ef_ess, tuple(self.fos_sel))
        if getattr(self, "_ef_last_key", None) not in (None, key) and hasattr(self, "ef_out"):
            self.ef_out.message("Выбор изменился — нажми «Посчитать выбранное».")
        self._ef_last_key = key
        if self.ef_ess and self.ef_ess in self.ess_list:
            t = "Эссенция: " + self.ess_list[self.ef_ess].name
        elif self.fos_sel:
            t = "Фоссилы: " + ", ".join(n.replace(" Fossil", "") for n in self.fos_sel)
        else:
            t = "ничего не выбрано — клик по иконке"
        self.ef_sel_lbl.configure(text=t, fg=GOLD if (self.ef_ess or self.fos_sel) else MUTED)

    def _ef_changed(self, what):
        self._show_shift()

    def _targets(self):
        return [Target(k[0], k[1], v["max_tier"], v["label"]) for k, v in self.selected.items()]

    def _show_shift(self):
        """Наглядно: шанс каждого нужного мода «было → стало» и какие моды стали чаще, реже или пропали."""
        box = getattr(self, "ef_shift_box", None)
        if box is None:
            return
        box.clear()
        inner = box.inner
        if not self.pool:
            return box.message("Выбери базу сверху.")
        ess = self.ess_list.get(self.ef_ess) if self.ef_ess else None
        fos = [self.fos_list[n] for n in self.fos_sel]
        if not ess and not fos:
            return box.message("Кликни по эссенции или фоссилам слева — здесь будет видно, как меняются шансы "
                               "нужных модов (отмечаются ☐ в «Пуле модов») и всего пула.")
        base = self._calc_pool()
        if fos:
            after = cc.fossil_pool(self.data, base, fos)
            forced = None
        else:
            forced = cc.essence_entry(base, ess.mod)
            import copy as _c
            after = _c.copy(base)
            after.available = [e for e in base.available if not set(e.mod.groups) & set(ess.mod.groups)]

        def shares(pool):
            out, tot = {}, {"prefix": 0, "suffix": 0}
            for e in pool.available:
                tot[e.mod.kind] += e.weight
                k = (e.mod.kind, e.mod.type)
                out[k] = out.get(k, 0) + e.weight
            return {k: w / tot[k[0]] if tot[k[0]] else 0 for k, w in out.items()}
        s0, s1 = shares(base), shares(after)
        from ui_cards import bar
        bg = inner["bg"]
        if forced is not None:
            tk.Label(inner, text=f"Гарантирован:  {short(ess.mod.text)}  (T{forced.tier})", bg=bg, fg=GOOD,
                     font=(FONT, 10, "bold"), anchor="w").pack(fill="x", padx=12, pady=(10, 2))
        targets = self._targets()
        if targets:
            tk.Label(inner, text="НУЖНЫЕ МОДЫ — шанс среди своего типа", bg=bg, fg=DIM, font=(FONT, 7, "bold"),
                     anchor="w").pack(fill="x", padx=12, pady=(10, 2))
            for t in targets:
                ok_forced = forced is not None and t.ok(forced)
                b0 = sum(e.weight for e in base.available if t.ok(e))
                tot0 = sum(e.weight for e in base.available if e.mod.kind == t.kind)
                b1 = sum(e.weight for e in after.available if t.ok(e))
                tot1 = sum(e.weight for e in after.available if e.mod.kind == t.kind)
                p0, p1 = (b0 / tot0 if tot0 else 0), (1.0 if ok_forced else (b1 / tot1 if tot1 else 0))
                r = tk.Frame(inner, bg=bg)
                r.pack(fill="x", padx=12, pady=2)
                tk.Label(r, text=t.label, bg=bg, fg=FG, font=(FONT, 9), width=22, anchor="w").pack(side="left")
                col = tk.Frame(r, bg=bg)
                col.pack(side="left")
                bar(col, p0, 170, color="#6e6356").pack(anchor="w", pady=1)
                bar(col, p1, 170, color=GOOD if p1 > p0 else (WARN if p1 < p0 else GOLD)).pack(anchor="w", pady=1)
                arrow = "гарантирован" if ok_forced else f"{pct(p0)} → {pct(p1)}"
                fg = GOOD if p1 > p0 * 1.05 else (WARN if p1 < p0 * 0.95 else FG)
                tk.Label(r, text=arrow, bg=bg, fg=fg, font=(FONT, 9, "bold"), anchor="w").pack(side="left", padx=10)
        # весь пул: что выросло/упало сильнее всего
        names = {(e.mod.kind, e.mod.type): short(e.mod.text) for e in base.available}
        changes = []
        for k, v0 in s0.items():
            v1 = s1.get(k, 0)
            if v0 > 0:
                changes.append((v1 / v0, k, v0, v1))
        up = sorted([c for c in changes if c[0] > 1.05], reverse=True)[:6]
        down = sorted([c for c in changes if 0 < c[0] < 0.95])[:6]
        gone = [c for c in changes if c[0] == 0][:8]
        for title, items, fg in (("ЧАЩЕ", up, GOOD), ("РЕЖЕ", down, GOLD), ("ПРОПАЛИ ИЗ ПУЛА", gone, WARN)):
            if not items:
                continue
            tk.Label(inner, text=title, bg=bg, fg=DIM, font=(FONT, 7, "bold"), anchor="w").pack(fill="x", padx=12,
                                                                                              pady=(10, 2))
            for ratio, k, v0, v1 in items:
                r = tk.Frame(inner, bg=bg)
                r.pack(fill="x", padx=12)
                tk.Label(r, text=("П " if k[0] == "prefix" else "С ") + names.get(k, k[1]), bg=bg, fg=FG,
                         font=(FONT, 9), anchor="w").pack(side="left", fill="x", expand=True)
                txt = "✕" if v1 == 0 else f"×{ratio:.1f}  ({pct(v0)} → {pct(v1)})"
                tk.Label(r, text=txt, bg=bg, fg=fg, font=(FONT, 9)).pack(side="right")
        box.finish()

    def calculate_ef(self):
        if not self.pool or not self.selected:
            self.ef_status.configure(text="Сначала выбери базу и отметь нужные моды в «Пуле модов».", fg=WARN)
            return
        targets = self._targets()
        pool = self._calc_pool()
        ess = self.ess_list.get(self.ef_ess) if self.ef_ess else None
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
        self._btn(top, "⌕ такой на трейде", self.trade_emu).pack(side="left", padx=(4, 0))
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
                                 ("bench", "", "Верстак"), ("beast", "", "Звери"), ("vaal", "Vaal Orb", "Vaal"),
                                 ("qual", "Prismatic Catalyst", "Качество")):
            t = tk.Label(tabs, text=" " + label, bg=BG, fg=MUTED, font=(FONT, 8), compound="left", padx=2, pady=4,
                         cursor="hand2", anchor="w")
            n = len(self._emu_tabs)
            t.grid(row=n // 5, column=n % 5, sticky="we")
            tabs.columnconfigure(n % 5, weight=1, uniform="tabs")
            t.configure(anchor="center")
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
        self._page_beast(self._emu_pages["beast"])
        self._page_vaal(self._emu_pages["vaal"])
        self._page_qual(self._emu_pages["qual"])
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
        self.apply_btn = self._act(r1, "Применить", self.emu_apply_selected)
        self.apply_btn.pack(side="right")
        r2 = tk.Frame(bar, bg=BG1)
        r2.pack(fill="x", padx=8, pady=(2, 6))
        self.sim_btn = self._btn(r2, "▶ Крутить до цели", self.emu_sim_toggle, GOOD)
        self.sim_btn.pack(side="left")
        tk.Label(r2, text="предметов:", bg=BG1, fg=MUTED, font=(FONT, 8)).pack(side="left", padx=(10, 2))
        self.sim_n = tk.StringVar(value="100")
        self._entry(r2, self.sim_n, 5).pack(side="left")
        self._btn(r2, "▦ Прогнать", self.emu_sim_fixed).pack(side="left", padx=(4, 0))
        self.lock_var = tk.BooleanVar(value=False)
        lk = tk.Checkbutton(r2, text="Hinekora", variable=self.lock_var, bg=BG1, fg=MUTED, selectcolor=BG2,
                            activebackground=BG1, activeforeground=GOLD, font=(FONT, 8), bd=0, highlightthickness=0)
        lk.pack(side="right", padx=(6, 0))
        self.aug_var = tk.BooleanVar(value=True)
        tk.Checkbutton(r2, text="+Aug", variable=self.aug_var, bg=BG1, fg=MUTED, selectcolor=BG2,
                       activebackground=BG1, activeforeground=GOLD, font=(FONT, 8), bd=0,
                       highlightthickness=0).pack(side="right")
        self.sim_lbl = tk.Label(bar, text="Клик по предмету или «Применить» — кинуть выбранное. "
                                          "Двойной клик по валюте — кинуть сразу.", bg=BG1, fg=DIM,
                                font=(FONT, 8), anchor="w", justify="left", wraplength=410)
        self.sim_lbl.pack(fill="x", padx=8, pady=(0, 6))

    def emu_pick(self, action, **kw):
        """Выбрать метод (валюту/эссенцию/фоссилы…). Применяется кликом по предмету или «Применить»."""
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
        if getattr(self, "_lock_pending", False):
            self.emu_status.configure(text="Сначала реши: оставить результат Hinekora's Lock или отказаться.", fg=WARN)
            return
        if self._emu_sel and self.lock_var.get() and self.emu:
            return self._apply_with_lock()
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

    def _apply_with_lock(self):
        """Hinekora's Lock: показать результат следующего действия и дать отказаться (валюта не тратится)."""
        n = len(self._emu_steps)
        action, kw = self._emu_sel[0], self._emu_sel[1]
        self.emu_do(action, **kw)
        if len(self._emu_steps) == n:     # ошибка — ничего не применилось
            return
        self._lock_pending = True
        self.emu.spent["Hinekora's Lock"] = self.emu.spent.get("Hinekora's Lock", 0) + 1
        bar = tk.Frame(self.emu_page.master, bg="#2a2116", highlightthickness=1, highlightbackground=GOLD_LINE)
        bar.pack(fill="x", before=self.emu_page, pady=(0, 4))
        tk.Label(bar, text="Hinekora's Lock: предмет показан так, как выйдет. Оставить результат?", bg="#2a2116",
                 fg=GOLD, font=(FONT, 9, "bold"), anchor="w", justify="left", wraplength=330).pack(fill="x", padx=8,
                                                                                               pady=(6, 2))
        bar = tk.Frame(bar, bg="#2a2116")
        bar.pack(fill="x", padx=4, pady=(0, 4))

        def decide(keep):
            self._lock_pending = False
            bar.destroy()
            if not keep:
                self.emu.undo()
                self._emu_steps.pop()
                self.emu.spent["Hinekora's Lock"] = self.emu.spent.get("Hinekora's Lock", 0) + 1
                self.emu_status.configure(text="Отказался — валюта не потрачена, Lock израсходован.", fg=MUTED)
            else:
                self.emu_status.configure(text="Результат оставлен.", fg=GOOD)
            self.emu_card._prev = None
            self._emu_render()
        self._btn(bar, "✗ отказаться", lambda: decide(False), WARN).pack(side="right", padx=4)
        self._btn(bar, "✓ оставить", lambda: decide(True), GOOD).pack(side="right")
        self._emu_render()

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
            em.restore(start, copy=True)

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
            em.restore(start)
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
        l = tk.Label(parent, text=i18n.t(text).upper(), bg=parent["bg"], fg=GOLD, font=(FONT, 9, "bold"), anchor="w")
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
            t.grid(row=i // 8, column=i % 8, padx=1, pady=1)
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
        self._cap_small(p, "Awakener's Orb — второе влияние")
        self._note(p, "Уничтожает второй предмет с другим влиянием. Этот предмет станет редким с двумя "
                      "влияниями: по одному моду влияния от каждого, остальное — случайно.").pack(fill="x")
        ar = tk.Frame(p, bg=BG1)
        ar.pack(fill="x", pady=4)
        self.awk_inf = tk.StringVar(value="Warlord")
        cb = ttk.Combobox(ar, textvariable=self.awk_inf, state="readonly", style="D.TCombobox", width=10,
                          values=["Shaper", "Elder", "Crusader", "Redeemer", "Hunter", "Warlord"], font=(FONT, 9))
        popdown_on_top(cb)
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda e: self._awk_fill())
        self.awk_mod = tk.StringVar()
        self.awk_box = ttk.Combobox(ar, textvariable=self.awk_mod, state="readonly", style="D.TCombobox",
                                    font=(FONT, 9))
        popdown_on_top(self.awk_box)
        self.awk_box.pack(side="left", fill="x", expand=True, padx=4)
        self._awk_opts = {}
        self._tile(p, "Awakener's Orb", "Awakener's Orb", self._awk_pick, size=24, compact=True,
                   tip="Выбери влияние и мод уничтожаемого предмета (или «случайный»)").pack(fill="x", pady=(0, 6))
        og = tk.Frame(p, bg=BG1)
        og.pack(fill="x")
        self._tile(og, "Orb of Dominance", "Orb of Dominance", lambda: self.emu_pick("dominance"), size=24,
                   compact=True, tip="Maven's Orb: снимает случайный мод влияния и возвышает другой (нужно ≥2)").grid(
            row=0, column=0, sticky="we", padx=2)
        self._tile(og, "", "Craicic Maw", lambda: self.emu_pick("beast_influence"), size=24,
                   compact=True, tip="Звериный крафт: добавляет мод влияния предмета").grid(row=0, column=1,
                                                                                            sticky="we", padx=2)
        og.columnconfigure(0, weight=1, uniform="og")
        og.columnconfigure(1, weight=1, uniform="og")

    def _cap_small(self, parent, text):
        tk.Label(parent, text=text, bg=parent["bg"], fg=GOLD, font=(FONT, 9, "bold"), anchor="w").pack(
            fill="x", pady=(10, 0))

    def _awk_fill(self):
        if not self.emu:
            self._awk_opts = {}
            self.awk_box["values"] = []
            return
        opts = self.emu.awakener_options(self.awk_inf.get())
        self._awk_opts = {"случайный мод этого влияния": None}
        self._awk_opts.update({f"{'П' if e.mod.kind == 'prefix' else 'С'} T{e.tier}  {short(e.mod.text)}": e.mod.id
                               for e in opts})
        self.awk_box["values"] = list(self._awk_opts)
        self.awk_mod.set("случайный мод этого влияния")

    def _awk_pick(self):
        if not self._awk_opts:
            self._awk_fill()
        self.emu_pick("awakener", other=self.awk_inf.get(), mod_id=self._awk_opts.get(self.awk_mod.get()))

    def _page_beast(self, p):
        self._note(p, "Звериные крафты Менажери. Прочие рецепты (уники, валюта) на крафт модов не влияют.").pack(fill="x")
        g = tk.Frame(p, bg=BG1)
        g.pack(fill="x", pady=6)
        items = (("Farric Wolf Alpha: +префикс, −суффикс", "beast_prefix", {}),
                 ("Farric Lynx Alpha: +суффикс, −префикс", "beast_suffix", {}),
                 ("Fenumal Arachnid: расколоть (Split)", "beast_split", {}),
                 ("Craicic Maw: +мод влияния", "beast_influence", {}),
                 ("Craicic Chimeral: отпечаток (magic)", "imprint", {}),
                 ("Восстановить из отпечатка", "imprint_restore", {}))
        for i, (label, act, kw) in enumerate(items):
            self._tile(g, "", label, lambda a=act, k=kw: self.emu_pick(a, **k), size=20, compact=True).grid(
                row=i, column=0, sticky="we", pady=1)
        g.columnconfigure(0, weight=1)
        self._cap_small(p, "Аспекты духов-зверей (крафтовый суффикс)")
        ag = tk.Frame(p, bg=BG1)
        ag.pack(fill="x", pady=4)
        for i, a in enumerate(("Cat", "Avian", "Spider", "Crab")):
            self._tile(ag, "", f"Aspect of the {a}", lambda x=a: self.emu_pick("beast_aspect", aspect=x),
                       size=20, compact=True).grid(row=i // 2, column=i % 2, sticky="we", padx=1, pady=1)
        ag.columnconfigure(0, weight=1, uniform="ag")
        ag.columnconfigure(1, weight=1, uniform="ag")

    def _page_vaal(self, p):
        self._note(p, "Vaal Orb оскверняет предмет: ничего / Vaal-имплицит / перекат в редкий / сокеты — по 25%. "
                      "После этого работают только Tainted-валюта и верстак.").pack(fill="x")
        g = tk.Frame(p, bg=BG1)
        g.pack(fill="x", pady=6)
        for i, (name, act, label, tip) in enumerate((
                ("Vaal Orb", "vaal", "Vaal", "Осквернить предмет"),
                ("Tainted Chaos Orb", "tainted_chaos", "T. Chaos", "50%: перекат редкого, 50%: снять все моды"),
                ("Tainted Exalted Orb", "tainted_exalt", "T. Exalt", "Добавляет или снимает мод (50/50)"),
                ("Tainted Divine Teardrop", "tainted_divine", "T. Teardrop", "Тир каждого мода ±1"))):
            self._tile(g, name, label, lambda a=act: self.emu_pick(a), tip=tip).grid(row=0, column=i, sticky="we", padx=2)
            g.columnconfigure(i, weight=1, uniform="vg")

    def _page_qual(self, p):
        self._note(p, "Катализаторы (кольца, амулеты, пояса): качество до 20% усиливает моды своего тега и "
                      "повышает их шанс выпасть на столько же процентов. Обычный предмет +5%, магический +2%, "
                      "редкий +1% за катализатор.").pack(fill="x")
        g = tk.Frame(p, bg=BG1)
        g.pack(fill="x", pady=6)
        for i, name in enumerate(sk.CATALYSTS):
            self._tile(g, name, name.replace(" Catalyst", "").replace("Accelerating", "Accel."), lambda n=name: self.emu_pick("catalyst", name=n),
                       tip=f"{name}: теги {', '.join(sk.CATALYSTS[name])}").grid(row=i // 5, column=i % 5,
                                                                                sticky="we", padx=1, pady=1)
            g.columnconfigure(i % 5, weight=1, uniform="ct")

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
        self.emu.blocked = set(getattr(self, "blocked", set()))
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
        self.inf_var.set(one[0] if len(one) == 1 else NONE)
        self._paint_influence()
        self.load_pool()
        if not self.pool:
            return
        self.emu = Emulator(self.data, self.base_pool, influences=[i for i in item.influences if i in tags])
        self.emu.blocked = set(getattr(self, "blocked", set()))
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
        self._awk_fill()

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
            t.grid(row=i // 8, column=i % 8, padx=1, pady=1)
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
        "vaal": ("Vaal Orb", "Vaal Orb"), "tainted_chaos": ("Tainted Chaos Orb", "Tainted Chaos"),
        "tainted_exalt": ("Tainted Exalted Orb", "Tainted Exalt"),
        "tainted_divine": ("Tainted Divine Teardrop", "Tainted Divine Teardrop"),
        "dominance": ("Orb of Dominance", "Orb of Dominance"), "beast_prefix": ("", "Farric Wolf Alpha"),
        "beast_suffix": ("", "Farric Lynx Alpha"), "beast_split": ("", "Fenumal Plagued Arachnid: Split"),
        "beast_influence": ("", "Craicic Maw"), "imprint": ("", "Отпечаток (Craicic Chimeral)"),
        "imprint_restore": ("", "Восстановить отпечаток"),
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
        if action == "awakener":
            return "Awakener's Orb", f"Awakener's Orb (+{kw.get('other')})"
        if action == "catalyst":
            return kw["name"], kw["name"]
        if action == "beast_aspect":
            return "", f"Aspect of the {kw['aspect']}"
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
        st = getattr(em, "state", {})
        return {"rarity": em.rarity, "mods": mods, "impl": impl, "infl": list(em.influences),
                "state": {"quality": st.get("quality", 0), "catalyst": st.get("catalyst"),
                          "corrupted": st.get("corrupted"), "split": st.get("split"),
                          "imprint": bool(st.get("imprint")), "notes": list(st.get("notes", []))}}

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
        sa, sb = a.get("state", {}), b.get("state", {})
        if (sa.get("quality"), sa.get("catalyst")) != (sb.get("quality"), sb.get("catalyst")):
            out.append(("chg", f"качество {sa.get('quality', 0)}% → {sb.get('quality', 0)}%"
                        + (f" ({sb['catalyst'].replace(' Catalyst', '')})" if sb.get("catalyst") else "")))
        if sb.get("corrupted") and not sa.get("corrupted"):
            out.append(("del", "предмет осквернён"))
        if sb.get("split") and not sa.get("split"):
            out.append(("m", "Split"))
        if sb.get("imprint") != sa.get("imprint"):
            out.append(("m", "отпечаток сохранён" if sb.get("imprint") else "восстановлено из отпечатка"))
        for n in sb.get("notes", []):
            if n not in sa.get("notes", []):
                out.append(("add", n))
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
    # ------------------------------------------------------------ рецепты (пошаговые планы)
    def _build_plans(self):
        """Рецепт крафта из шагов с развилками и прогон по нему N предметов — реальная цена всего пути."""
        from poecraft import plans
        from ui_cards import ScrollList
        self.plan: list[dict] = []
        f = self.tab_plan
        left = tk.Frame(f, bg=BG, width=430)
        left.pack(side="left", fill="y", padx=(6, 6), pady=8)
        left.pack_propagate(False)
        self._cap(left, "Шаблоны")
        pr = tk.Frame(left, bg=BG1, highlightthickness=1, highlightbackground=LINE)
        pr.pack(fill="x", pady=(2, 8))
        self.plan_presets = tk.Frame(pr, bg=BG1)
        self.plan_presets.pack(fill="x", padx=4, pady=4)
        for i, name in enumerate(plans.presets(2)):
            b = self._btn(self.plan_presets, name, lambda n=name: self.plan_preset(n))
            b.grid(row=i // 2, column=i % 2, sticky="w")
        self._cap(left, "Шаги рецепта")
        lf = tk.Frame(left, bg=BG1, highlightthickness=1, highlightbackground=LINE)
        lf.pack(fill="x", pady=(2, 4))
        self.plan_lb = tk.Listbox(lf, bg=BG1, fg=FG, selectbackground="#3a2c17", selectforeground=GOLD,
                                  relief="flat", highlightthickness=0, font=(FONT, 9), height=9, activestyle="none")
        self.plan_lb.pack(fill="x", padx=4, pady=4)
        self.plan_lb.bind("<<ListboxSelect>>", lambda e: self._plan_load_step())
        br = tk.Frame(left, bg=BG)
        br.pack(fill="x", pady=(0, 8))
        for text, cmd in (("+ добавить", self.plan_add), ("✎ заменить", self.plan_update), ("× удалить", self.plan_del),
                          ("▲", lambda: self.plan_move(-1)), ("▼", lambda: self.plan_move(1)),
                          ("очистить", self.plan_clear)):
            self._btn(br, text, cmd).pack(side="left")

        self._cap(left, "Шаг")
        ed = tk.Frame(left, bg=BG1, highlightthickness=1, highlightbackground=LINE)
        ed.pack(fill="x", pady=(2, 8))
        ed.columnconfigure(1, weight=1)

        def row(r, label):
            tk.Label(ed, text=label, bg=BG1, fg=MUTED, font=(FONT, 9), anchor="w").grid(
                row=r, column=0, sticky="w", padx=(8, 6), pady=3)

        def combo(r, var, values, width=30):
            cb = ttk.Combobox(ed, textvariable=var, values=values, state="readonly", style="D.TCombobox", width=width)
            cb.grid(row=r, column=1, sticky="we", padx=(0, 8), pady=3)
            popdown_on_top(cb)
            return cb

        self._plan_act_labels = [i18n.t(l) for _, l, _ in plans.ACTIONS]
        self._plan_cond_labels = [i18n.t(l) for l, _ in plans.CONDITIONS]
        self.pl_if = tk.StringVar(value="—")
        self.pl_act = tk.StringVar(value=self._plan_act_labels[0])
        self.pl_par = tk.StringVar()
        self.pl_until = tk.StringVar(value="—")
        self.pl_max = tk.StringVar(value="300")
        self.pl_else = tk.StringVar(value=i18n.t("дальше"))
        row(0, "если")
        combo(0, self.pl_if, self._plan_cond_labels)
        row(1, "сделать")
        cb = combo(1, self.pl_act, self._plan_act_labels)
        cb.bind("<<ComboboxSelected>>", lambda e: self._plan_param_values())
        row(2, "параметр")
        self.pl_par_box = combo(2, self.pl_par, [])
        self.pl_par_box.bind("<<ComboboxSelected>>", lambda e: self._plan_param_pick())
        self.pl_fos: list[str] = []
        self.pl_fos_lbl = tk.Label(ed, text="", bg=BG1, fg=GOLD, font=(FONT, 8), anchor="w", wraplength=300,
                                   justify="left")
        self.pl_fos_lbl.grid(row=3, column=1, sticky="we", padx=(0, 8))
        row(4, "повторять, пока")
        combo(4, self.pl_until, self._plan_cond_labels)
        row(5, "не больше раз")
        self._entry(ed, self.pl_max, 8).grid(row=5, column=1, sticky="w", padx=(0, 8), pady=3)
        row(6, "иначе")
        self.pl_else_box = combo(6, self.pl_else, [i18n.t("дальше"), i18n.t("стоп")])
        tk.Label(ed, text="«если» — шаг выполняется только при условии; «повторять, пока» — кидать, пока условие "
                          "не выполнится. Не вышло → «иначе»: дальше, стоп (неудача) или вернуться к шагу.",
                 bg=BG1, fg=DIM, font=(FONT, 8), wraplength=400, justify="left", anchor="w").grid(
            row=7, column=0, columnspan=2, sticky="we", padx=8, pady=(2, 6))
        self._plan_param_values()

        right = tk.Frame(f, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(0, 6), pady=8)
        self._cap(right, "Прогон рецепта")
        rr = tk.Frame(right, bg=BG1, highlightthickness=1, highlightbackground=LINE)
        rr.pack(fill="x", pady=(2, 6))
        tk.Label(rr, text="предметов:", bg=BG1, fg=MUTED, font=(FONT, 9)).pack(side="left", padx=(8, 4), pady=6)
        self.pl_n = tk.StringVar(value="1000")
        self._entry(rr, self.pl_n, 7).pack(side="left")
        self._act(rr, "▦ Прогнать", self.plan_run).pack(side="left", padx=8, pady=6)
        self._btn(rr, "▶ один раз в эмуляторе", self.plan_once).pack(side="left")
        self.pl_status = tk.Label(right, text="", bg=BG, fg=MUTED, font=(FONT, 8), anchor="w", justify="left")
        self.pl_status.pack(fill="x")
        self.pl_out = ScrollList(right)
        self.pl_out.pack(fill="both", expand=True, pady=(4, 0))
        self.pl_out.message("Собери рецепт из шагов слева или возьми шаблон. Цели — моды, отмеченные в «Пуле модов». "
                            "Прогон стартует с предмета в эмуляторе (или с белой базы) и повторяет весь путь много "
                            "раз: видно шанс успеха, среднюю цену и сколько раз срабатывает каждый шаг.\n\n"
                            "Рецепт сохраняется вместе с крафтом («Калькулятор» → «Сохранить как крафт»).")
        self._plan_refresh()

    def _plan_param_values(self):
        from poecraft import plans
        a = self._plan_action()
        p = plans.ACTION_PARAM.get(a)
        vals: list[str] = []
        self._plan_bench_map = {}
        if p == "essence" and self.pool:
            vals = sorted(e.name for e in cc.essences_for(self.data, self.pool.base.item_class))
        elif p == "fossils":
            vals = sorted(self.fos_list)
        elif p == "bench":
            meta = {"prefix_lock": "Префиксы нельзя менять", "suffix_lock": "Суффиксы нельзя менять",
                    "no_attack": "Нельзя моды атаки", "no_caster": "Нельзя моды заклинаний",
                    "multi_craft": "До 3 крафтов"}
            self._plan_bench_map = {i18n.t(v): ("meta", k) for k, v in meta.items()}
            em = self._plan_em(fresh=True)
            if em:
                for o in em.bench_options():
                    if em._meta_of(o):
                        continue
                    t = short(o["mod"].text)
                    self._plan_bench_map.setdefault(t, ("bench", o["mod"].id))
            vals = list(self._plan_bench_map)
        elif p == "conqueror":
            vals = list(inf.CONQUEROR_ORBS)
        elif p == "harvest":
            from poecraft.harvest import HARVEST
            vals = list(HARVEST)
        self.pl_par_box.configure(values=vals, state="readonly" if vals else "disabled")
        if self.pl_par.get() not in vals:
            self.pl_par.set(vals[0] if vals and p != "fossils" else "")
        if p != "fossils":
            self.pl_fos = []
        self._plan_fos_paint()

    def _plan_param_pick(self):
        from poecraft import plans
        if plans.ACTION_PARAM.get(self._plan_action()) == "fossils":
            n = self.pl_par.get()
            if n and n not in self.pl_fos and len(self.pl_fos) < 4:
                self.pl_fos.append(n)
            self.pl_par.set("")
            self._plan_fos_paint()

    def _plan_fos_paint(self):
        if self.pl_fos:
            self.pl_fos_lbl.configure(text="фоссилы: " + " + ".join(x.replace(" Fossil", "") for x in self.pl_fos)
                                           + "   (выбери ещё, до 4; «очистить» в списке шагов — сброс)")
        else:
            self.pl_fos_lbl.configure(text="")

    def _plan_action(self):
        from poecraft import plans
        lab = self.pl_act.get()
        return next((a for a, l, _ in plans.ACTIONS if i18n.t(l) == lab), "chaos")

    def _plan_cond(self, label):
        from poecraft import plans
        return {i18n.t(l): c for l, c in plans.CONDITIONS}.get(label)

    def _plan_step_from_editor(self):
        from poecraft import plans
        a = self._plan_action()
        p = plans.ACTION_PARAM.get(a)
        s: dict = {"do": a}
        kw: dict = {}
        par = self.pl_par.get()
        if p == "essence":
            if not par:
                raise ValueError("Выбери эссенцию.")
            kw["essence"] = par
        elif p == "fossils":
            if not self.pl_fos:
                raise ValueError("Выбери хотя бы один фоссил.")
            kw["fossils"] = list(self.pl_fos)
        elif p == "bench":
            if par not in self._plan_bench_map:
                raise ValueError("Выбери крафт верстака.")
            k, v = self._plan_bench_map[par]
            kw[k] = v
            if k == "bench":
                kw["bench_text"] = par
        elif p == "conqueror":
            kw["name"] = par
        elif p == "harvest":
            kw["label"] = par
        if kw:
            s["kw"] = kw
        c_if, c_until = self._plan_cond(self.pl_if.get()), self._plan_cond(self.pl_until.get())
        if c_if:
            s["if"] = c_if
        if c_until:
            s["until"] = c_until
            try:
                s["max"] = max(1, min(100000, int(self.pl_max.get())))
            except ValueError:
                s["max"] = 300
        if c_if or c_until:
            e = self.pl_else.get()
            s["else"] = "next" if e == i18n.t("дальше") else "stop" if e == i18n.t("стоп") else int(e.split()[-1]) - 1
        return s

    def _plan_refresh(self, sel=None):
        from poecraft import plans
        self.plan_lb.delete(0, "end")
        for i, s in enumerate(self.plan):
            self.plan_lb.insert("end", f"{i + 1}. {i18n.t(plans.step_text(s))}")
        if sel is not None and 0 <= sel < len(self.plan):
            self.plan_lb.selection_set(sel)
            self.plan_lb.see(sel)
        self.pl_else_box.configure(values=[i18n.t("дальше"), i18n.t("стоп")] +
                                   [f"{i18n.t('к шагу')} {i + 1}" for i in range(len(self.plan))])

    def _plan_sel(self):
        s = self.plan_lb.curselection()
        return s[0] if s else None

    def _plan_load_step(self):
        from poecraft import plans
        i = self._plan_sel()
        if i is None:
            return
        s = self.plan[i]
        self.pl_act.set(i18n.t(plans.ACTION_LABEL.get(s["do"], s["do"])))
        self._plan_param_values()
        kw = s.get("kw") or {}
        if kw.get("essence"):
            self.pl_par.set(kw["essence"])
        elif kw.get("fossils"):
            self.pl_fos = list(kw["fossils"])
            self._plan_fos_paint()
        elif kw.get("meta"):
            self.pl_par.set(next((k for k, v in self._plan_bench_map.items() if v == ("meta", kw["meta"])), ""))
        elif kw.get("bench_text"):
            self.pl_par.set(kw["bench_text"])
        elif kw.get("name") or kw.get("label"):
            self.pl_par.set(kw.get("name") or kw.get("label"))
        self.pl_if.set(i18n.t(plans.cond_label(s.get("if"))))
        self.pl_until.set(i18n.t(plans.cond_label(s.get("until"))))
        self.pl_max.set(str(s.get("max", 300)))
        e = s.get("else", "next")
        self.pl_else.set(i18n.t("дальше") if e == "next" else i18n.t("стоп") if e == "stop"
                         else f"{i18n.t('к шагу')} {int(e) + 1}")

    def plan_add(self):
        try:
            s = self._plan_step_from_editor()
        except ValueError as e:
            self.pl_status.configure(text=str(e), fg=WARN)
            return
        i = self._plan_sel()
        pos = len(self.plan) if i is None else i + 1
        self.plan.insert(pos, s)
        self._plan_refresh(pos)
        self.pl_status.configure(text="", fg=MUTED)

    def plan_update(self):
        i = self._plan_sel()
        if i is None:
            return self.plan_add()
        try:
            self.plan[i] = self._plan_step_from_editor()
        except ValueError as e:
            self.pl_status.configure(text=str(e), fg=WARN)
            return
        self._plan_refresh(i)

    def plan_del(self):
        i = self._plan_sel()
        if i is not None:
            del self.plan[i]
            self._plan_refresh(min(i, len(self.plan) - 1))

    def plan_move(self, d):
        i = self._plan_sel()
        if i is None or not 0 <= i + d < len(self.plan):
            return
        self.plan[i], self.plan[i + d] = self.plan[i + d], self.plan[i]
        self._plan_refresh(i + d)

    def plan_clear(self):
        self.plan = []
        self.pl_fos = []
        self._plan_fos_paint()
        self._plan_refresh()

    def plan_preset(self, name):
        from poecraft import plans
        steps = [dict(x) for x in plans.presets(max(1, len(self._targets())))[name]]
        ess = None
        if self.pool:
            if self.ef_ess and self.ef_ess in self.ess_list:
                ess = self.ess_list[self.ef_ess].name
        for s in steps:
            kw = s.get("kw")
            if kw is not None:
                kw = s["kw"] = dict(kw)
                if "essence" in kw and not kw["essence"] and ess:
                    kw["essence"] = ess
                if "fossils" in kw and not kw["fossils"] and getattr(self, "fos_sel", None):
                    kw["fossils"] = list(self.fos_sel)
        self.plan = steps
        self._plan_refresh()
        miss = [i + 1 for i, s in enumerate(steps) if (s.get("kw") or {}).get("essence") == ""
                or (s.get("kw") or {}).get("fossils") == []]
        self.pl_status.configure(
            text=(f"Шаблон «{name}». Выбери параметр в шаге {', '.join(map(str, miss))} (выдели шаг → параметр → "
                  "«заменить»)." if miss else f"Шаблон «{name}» — можно прогнать."), fg=WARN if miss else MUTED)

    def _plan_em(self, fresh=False):
        """Копия предмета из эмулятора (или новая белая база) — рецепт не трогает сам эмулятор."""
        if not self.pool:
            return None
        src = self.emu if (self.emu and not fresh) else None
        if src:
            em = Emulator(self.data, src.pool, influences=list(src.influences))
            em.blocked = set(src.blocked)
            em.restore(src.snapshot(), copy=True)
        else:
            infl = [self.inf_var.get()] if self.inf_var.get() in getattr(self, "inf_map", {}) else []
            em = Emulator(self.data, self.base_pool, influences=infl)
            em.blocked = set(getattr(self, "blocked", set()))
        em.spent = {}
        return em

    def _plan_check(self):
        if not self.pool:
            self.pl_status.configure(text="Сначала выбери базу сверху.", fg=WARN)
            return None
        if not self.plan:
            self.pl_status.configure(text="В рецепте нет шагов.", fg=WARN)
            return None
        targets = self._targets()
        if not targets:
            self.pl_status.configure(text="Отметь нужные моды во вкладке «Пул модов».", fg=WARN)
            return None
        return targets

    def plan_run(self):
        from poecraft import plans
        targets = self._plan_check()
        if targets is None or getattr(self, "_plan_busy", False):
            return
        try:
            n = max(1, min(100000, int(self.pl_n.get())))
        except ValueError:
            n = 1000
        em = self._plan_em()
        steps = [dict(s) for s in self.plan]
        self._plan_busy = True
        self.pl_status.configure(text=f"Прогоняю {n:,} предметов…".replace(",", " "), fg=GOLD)
        prog = {"i": 0}

        def work():
            try:
                r = plans.simulate(self.data, em, targets, steps, n, self.prices, time_budget=25.0,
                                   progress=lambda i, t: prog.__setitem__("i", i))
            except Exception as e:  # noqa: BLE001
                r = {"error": str(e)}
            self.after(0, lambda: self._plan_done(r, steps))

        def tick():
            if self._plan_busy:
                self.pl_status.configure(text=f"Прогоняю… {prog['i']:,} / {n:,}".replace(",", " "), fg=GOLD)
                self.after(300, tick)

        threading.Thread(target=work, daemon=True).start()
        tick()

    def _plan_done(self, r, steps):
        from poecraft import plans
        from ui_cards import result_card
        self._plan_busy = False
        self.pl_out.clear()
        if r.get("error"):
            self.pl_status.configure(text=f"Ошибка: {r['error']}", fg=WARN)
            return
        dv = self.prices.divine or 1
        sp = lambda x: f"{x:,.0f}".replace(",", " ")
        cps = r["cost_per_success"]
        self.pl_status.configure(text=f"Готово: {sp(r['items'])} предметов"
                                      + (" (упёрлись во время)" if r["items"] < int(self.pl_n.get() or 0) else ""),
                                 fg=GOOD if r["ok"] else WARN)
        result_card(self.pl_out.inner, title="Рецепт: " + (self.goal_name.get().strip() or f"{len(steps)} шагов"),
                    best=cps is not None,
                    cost=(f"{sp(cps)}c · {cps / dv:.2f} div" if cps is not None else "нет успехов"),
                    cost_bad=cps is None,
                    desc=f"в среднем на попытку ≈ {sp(r['avg_cost'])}c · {r['avg_ops']:.0f} действий",
                    chance=r["rate"], chance_text=f"успех {r['rate'] * 100:.1f}% · {sp(r['ok'])} из {sp(r['items'])}",
                    note="" if cps is not None else "рецепт ни разу не довёл предмет до цели — проверь шаги")
        box = tk.Frame(self.pl_out.inner, bg=BG1, highlightthickness=1, highlightbackground=LINE)
        box.pack(fill="x", padx=4, pady=6)
        tk.Label(box, text="СКОЛЬКО РАЗ СРАБАТЫВАЕТ ШАГ (в среднем на предмет)", bg=BG1, fg=GOLD,
                 font=(FONT, 8, "bold"), anchor="w").pack(fill="x", padx=8, pady=(6, 2))
        for i, (s, k) in enumerate(zip(steps, r["per_step"])):
            tk.Label(box, text=f"{i + 1}. {i18n.t(plans.step_text(s))}", bg=BG1, fg=FG, font=(FONT, 9), anchor="w",
                     wraplength=520, justify="left").pack(fill="x", padx=8)
            tk.Label(box, text=f"    × {k:.1f}", bg=BG1, fg=MUTED, font=(FONT, 8), anchor="w").pack(fill="x", padx=8)
        tk.Frame(box, bg=BG1, height=6).pack()
        for e in r.get("errors") or []:
            tk.Label(self.pl_out.inner, text="⚠ " + e, bg=BG, fg=WARN, font=(FONT, 9), anchor="w").pack(fill="x", padx=6)
        self.pl_out.finish()

    def plan_once(self):
        """Один проход рецепта прямо в эмуляторе — с журналом, можно отмотать."""
        from poecraft import plans
        targets = self._plan_check()
        if targets is None:
            return
        if not self.emu:
            self.emu_new()
        if not self.emu:
            return
        r = plans.PlanRunner(self.data, self.emu, targets, trim_history=False).run([dict(s) for s in self.plan])
        self.emu_card._prev = None
        self._emu_render()
        self.nb.select(self.tab_emu)
        msg = "Рецепт дошёл до цели ✓" if r["ok"] else (r["error"] or "Рецепт не дошёл до цели")
        self.emu_status.configure(text=f"{msg} · {r['ops']} действий", fg=GOOD if r["ok"] else WARN)

    def _build_sockets(self):
        """Сокеты: слева предмет и что нужно, справа карточки способов (Chromatic и рецепты верстака)."""
        from ui_cards import ScrollList
        f = self.tab_sock
        left = tk.Frame(f, bg=BG, width=300)
        left.pack(side="left", fill="y", padx=(6, 6), pady=8)
        left.pack_propagate(False)
        self.sk_vars = {}

        def field(parent, key, label, default, color=MUTED):
            r = tk.Frame(parent, bg=BG1)
            r.pack(fill="x", padx=8, pady=2)
            tk.Label(r, text=label, bg=BG1, fg=color, font=(FONT, 9), width=16, anchor="w").pack(side="left")
            v = tk.StringVar(value=default)
            e = self._entry(r, v, 6)
            e.pack(side="right")
            v.trace_add("write", lambda *a: self._sock_preview())
            self.sk_vars[key] = v

        self._cap(left, "Предмет")
        pf = tk.Frame(left, bg=BG1, highlightthickness=1, highlightbackground=LINE)
        pf.pack(fill="x", pady=(2, 10))
        tk.Frame(pf, bg=BG1, height=4).pack()
        for key, label, default in (("str", "Сила (Str)", "0"), ("dex", "Ловкость (Dex)", "0"),
                                    ("int", "Интеллект (Int)", "0"), ("ilvl", "ilvl", "84"), ("q", "качество", "20")):
            field(pf, key, label, default)
        self._btn(pf, "взять требования базы", self._sock_from_base).pack(anchor="w", padx=4, pady=(2, 6))

        self._cap(left, "Нужно")
        nf = tk.Frame(left, bg=BG1, highlightthickness=1, highlightbackground=LINE)
        nf.pack(fill="x", pady=(2, 10))
        tk.Frame(nf, bg=BG1, height=4).pack()
        field(nf, "n", "сокетов", "6")
        field(nf, "R", "красных", "0", "#e07a5f")
        field(nf, "G", "зелёных", "0", GOOD)
        field(nf, "B", "синих", "0", BLUE)
        self.sk_prev = tk.Frame(nf, bg=BG1)
        self.sk_prev.pack(fill="x", padx=8, pady=6)
        self.sk_white = tk.BooleanVar(value=False)
        tk.Checkbutton(nf, text="белые сокеты (3.29: ниже ilvl — больше белых)", variable=self.sk_white, bg=BG1,
                       fg=FG, selectcolor=BG2, activebackground=BG1, activeforeground=GOLD, font=(FONT, 8),
                       highlightthickness=0, bd=0, anchor="w", wraplength=270, justify="left").pack(fill="x", padx=8,
                                                                                                 pady=(0, 6))
        self._act(left, "Посчитать", self.calc_sockets).pack(fill="x")
        self._note(left, "Формула — как в калькуляторе Siveran. Число сокетов и связи надёжнее делать "
                         "верстаком: 6 сокетов — 350 Jeweller's, 6 связей — 1500 Fusing.").pack(fill="x", pady=8)

        right = tk.Frame(f, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(0, 6), pady=8)
        self._cap(right, "Способы покраски")
        self.sk_out = ScrollList(right)
        self.sk_out.pack(fill="both", expand=True, pady=(2, 0))
        self.sk_out.message("Введи требования атрибутов предмета (или «взять требования базы»), число сокетов "
                            "и сколько нужно красных/зелёных/синих.")
        self._sock_preview()

    def _sock_preview(self):
        from ui_cards import socket_preview
        if not hasattr(self, "sk_prev"):
            return
        for w in self.sk_prev.winfo_children():
            w.destroy()
        try:
            v = {k: int(self.sk_vars[k].get() or 0) for k in ("n", "R", "G", "B")}
        except (ValueError, KeyError):
            return
        n = max(1, min(6, v["n"]))
        want = (v["R"], v["G"], v["B"])
        if sum(want) <= n:
            socket_preview(self.sk_prev, want, n).pack(side="left")

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
        from ui_cards import result_card
        o = self.sk_out
        o.clear()
        tk.Label(o.inner, text=f"Шанс цвета одного сокета:  R {ch[0] * (1 - white):.1%}   G {ch[1] * (1 - white):.1%}   "
                               f"B {ch[2] * (1 - white):.1%}" + (f"   белый {white:.1%}" if white else ""),
                 bg=o.inner["bg"], fg=MUTED, font=(FONT, 9), anchor="w").pack(fill="x", padx=12, pady=(8, 2))
        sp = lambda x: f"{x:,.0f}".replace(",", " ")
        for i, m in enumerate(res):
            result_card(o.inner, title=m["name"], icon_names=["Chromatic Orb"], best=i == 0,
                        cost=f"{sp(m["cost_chaos"])}c", chance=None,
                        chance_text=f"шанс {m['chance']:.3%} · в среднем ~{sp(m['tries'])} попыток · "
                                    f"~{sp(m['cost'])} Chromatic")
        if not res:
            o.message("Так не получится.", WARN)
        o.finish()

    def _sock_msg(self, text, tag="m"):
        self.sk_out.message(text, WARN if tag == "bad" else MUTED)

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
        from poecraft import winmove
        self._dx, self._dy = e.x_root - self.winfo_x(), e.y_root - self.winfo_y()
        if winmove.native_drag(self, self._remember):
            return "break"

    def _drag_move(self, e):
        from poecraft import winmove
        winmove.throttled_move(self, e.x_root - self._dx, e.y_root - self._dy)

    def _resize_start(self, e):
        self._rw, self._rh, self._rx, self._ry = self.winfo_width(), self.winfo_height(), e.x_root, e.y_root

    def _resize_move(self, e):
        w = max(640, self._rw + e.x_root - self._rx)
        h = max(420, self._rh + e.y_root - self._ry)
        from poecraft import winmove
        winmove.throttled_geometry(self, f"{w}x{h}")

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
        self.inf_box["values"] = [NONE] + list(self.inf_map)
        if self.inf_var.get() not in self.inf_box["values"]:
            self.inf_var.set(NONE)
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
            self.ench_frame.pack(side="left")
        else:
            self.ench_frame.pack_forget()
        if base.item_class in sk.CATALYST_CLASSES:
            self.cat_frame.pack(side="left")
        else:
            self.cat_frame.pack_forget()
            self.cat_var.set(NONE)
        extra = set(base_extra)
        if infl in self.inf_map:
            extra.add(self.inf_map[infl])
        self.base_pool = ModPool(self.data, base, ilvl, base_extra or None)
        self.pool = ModPool(self.data, base, ilvl, extra) if extra != base_extra else self.base_pool
        if self.cat_var.get() in sk.CATALYSTS:
            self.pool = sk.apply_catalyst(self.pool, self.cat_var.get(), 20)
        if getattr(self, "_blocked_base", None) != base.name:
            self.blocked = set()
            self._blocked_base = base.name
        self.table = self._table_with_blocks()
        self._paint_base_art(base)
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

    def _pool_stats_paint(self):
        t = self.table
        if not t or not hasattr(self, "_stat_lbls"):
            return
        sp = lambda x: f"{x:,.0f}".replace(",", " ")
        groups = t["groups"]
        self._stat_lbls["groups"].configure(text=str(sum(1 for g in groups if not g.get("blocked"))))
        self._stat_lbls["pw"].configure(text=sp(t["prefix_weight"]))
        self._stat_lbls["sw"].configure(text=sp(t["suffix_weight"]))
        self._stat_lbls["sel"].configure(text=str(len(self.selected)))
        self._stat_lbls["blk"].configure(text=str(len(getattr(self, "blocked", ()))),
                                         fg=WARN if getattr(self, "blocked", None) else FG)
        for kind, lbl in self._pool_caps.items():
            n = sum(1 for g in groups if g["kind"] == kind and not g.get("blocked"))
            lbl.configure(text=f"{'ПРЕФИКСЫ' if kind == 'prefix' else 'СУФФИКСЫ'}  ·  {n}")

    def _render_pool(self):
        if not self.table:
            return
        self._pool_stats_paint()
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
                if g.get("blocked"):
                    tv.insert("", "end", iid=gid, text="⊘ " + short(g["text"]),
                              values=("", "—", "—", "", "блок"), tags=("blocked",))
                    continue
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

    # ---- блокировка модов правым кликом (как на Craft of Exile)
    def _calc_pool(self):
        """Пул без заблокированных модов — для калькулятора, эссенций/фоссилов и эмулятора."""
        if not getattr(self, "blocked", None):
            return self.pool
        import copy as _c
        fp = _c.copy(self.pool)
        fp.available = [e for e in self.pool.available if (e.mod.kind, e.mod.type) not in self.blocked]
        return fp

    def _table_with_blocks(self):
        full = pool_table(self.pool)
        if not getattr(self, "blocked", None):
            return full
        part = pool_table(self._calc_pool())
        by = {(g["kind"], g["type"]): g for g in part["groups"]}
        out = []
        for g in full["groups"]:
            key = (g["kind"], g["type"])
            if key in self.blocked:
                g = dict(g, blocked=True, chance_all=0.0, chance_kind=0.0)
            else:
                g = by.get(key, g)
            out.append(g)
        part["groups"] = out
        return part

    def _tree_block(self, e, tv):
        iid = tv.identify_row(e.y)
        if not iid or "|" not in iid:
            return
        kind, typ = iid.split("|", 1)
        key = (kind, typ)
        self.blocked = getattr(self, "blocked", set())
        if key in self.blocked:
            self.blocked.discard(key)
        else:
            self.blocked.add(key)
            self.selected.pop(key, None)
        if self.emu:
            self.emu.blocked = set(self.blocked)
        self.table = self._table_with_blocks()
        self._render_pool()
        n = len(self.blocked)
        self.status.configure(text=f"Заблокировано модов: {n} — они не выпадают в эмуляторе и не учитываются в шансах. "
                                   "Правый клик ещё раз — разблокировать." if n else "Блокировки сняты.", fg=MUTED)
        return "break"

    def _tree_click(self, e, tv: ttk.Treeview):
        region = tv.identify_region(e.x, e.y)
        if region != "cell" and region != "tree":
            return
        iid = tv.identify_row(e.y)
        col = tv.identify_column(e.x)
        if not iid or "|" not in iid:
            return
        g = self._group(iid)
        if not g or g.get("blocked"):
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
        self._pool_stats_paint()
        self._render_targets()
        return "break"

    def _render_targets(self):
        box = getattr(self, "targets_box", None)
        if box is None:
            return
        for w in box.winfo_children():
            w.destroy()
        if not self.selected:
            tk.Label(box, text="ничего не выбрано — клик по ☐ во вкладке «Пул модов»", bg=BG1, fg=MUTED,
                     font=(FONT, 9), wraplength=270, justify="left", anchor="w").pack(fill="x", padx=8, pady=8)
            return
        for k, v in list(self.selected.items()):
            r = tk.Frame(box, bg=BG1)
            r.pack(fill="x", padx=6, pady=2)
            tk.Label(r, text="П" if k[0] == "prefix" else "С", bg="#24201a", fg=MUTED, font=(FONT, 8, "bold"),
                     width=2).pack(side="left")
            tk.Label(r, text=v["label"], bg=BG1, fg=FG, font=(FONT, 9), anchor="w").pack(side="left", padx=6,
                                                                                        fill="x", expand=True)
            tk.Label(r, text=f"{i18n.t('до T')}{v['max_tier']}", bg=BG1, fg=GOLD, font=(FONT, 9)).pack(side="left")
            x = tk.Label(r, text="✕", bg=BG1, fg=DIM, font=(FONT, 9), cursor="hand2", padx=4)
            x.pack(side="left")
            x.bind("<Button-1>", lambda e, key=k: self._unselect(key))
        if hasattr(self, "ef_shift_box"):
            self._show_shift()

    def _unselect(self, key):
        self.selected.pop(key, None)
        self._render_targets()
        self._render_pool()
        if self.emu:
            self._emu_render()

    # ------------------------------------------------------------ расчёт
    def calculate(self):
        if not self.pool or not self.selected:
            self.calc_status.configure(text="Сначала выбери базу и отметь нужные моды.", fg=WARN)
            return
        targets = [Target(k[0], k[1], v["max_tier"], v["label"]) for k, v in self.selected.items()]
        self.calc_status.configure(text="считаю… (Chaos-симуляция может занять несколько секунд)", fg=MUTED)
        pool = self._calc_pool()
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
        from ui_cards import result_card
        o = getattr(self, target)
        o.clear()
        best = next((r for r in results if r["cost_chaos"] is not None), None)
        dv = self.prices.divine
        st = icons.store()
        for r in results:
            names = st.find_all(r["name"] + " " + r["how"][:80], 4) if st else []
            if r.get("chance_label"):
                ct = r["chance_label"]
            elif r["chance"]:
                ct = f"шанс {pct(r['chance'])} · в среднем ~{r['attempts']:,.0f} попыток".replace(",", " ")
            else:
                ct = ""
            uses = [(k, f"~{v:,.1f}".replace(",", " ") if v < 10 else f"~{v:,.0f}".replace(",", " "))
                    for k, v in r["use"].items() if v > 0.05]
            result_card(o.inner, title=r["name"], icon_names=names, best=r is best, desc=r["how"],
                        cost=money(r["cost_chaos"], dv, r.get("chance") or 0), cost_bad=r["cost_chaos"] is None,
                        chance=r["chance"] if r.get("chance") else None, chance_text=ct, uses=uses,
                        note=r.get("note") or "")
        if not results:
            o.message("Для такого набора модов пока нет подходящих методов.")
        o.finish()
        st = self.calc_status if target == "out" else self.ef_status
        st.configure(text=f"цены: {self.prices.league}, {self.prices.source}", fg=MUTED)

    # ------------------------------------------------------------ трейд
    def _trade_lang(self):
        lang = self.settings.get("game_lang", "auto")
        if lang == "auto":
            lang = "ru" if i18n.lang() == "ru" else "en"
        return lang

    def _open_trade(self, query, note=""):
        import webbrowser
        from poecraft import trade
        url = trade.search_url(self.prices.league or "Standard", query, self._trade_lang())
        webbrowser.open(url)
        self.status.configure(text="Открыл трейд в браузере." + (" " + note if note else ""), fg=WARN if note else MUTED)

    def trade_base(self):
        if not self.pool:
            return self.status.configure(text="Сначала выбери базу.", fg=WARN)
        from poecraft import trade
        infl = self.inf_var.get() if self.inf_var.get() in getattr(self, "inf_map", {}) else None
        self._open_trade(trade.base_query(self.pool.base.name, self.pool.ilvl, infl))

    def _trade_mods(self, mods, base_name, ilvl):
        """Словарь статов трейда качаем один раз в фоне, потом открываем ссылку."""
        from poecraft import trade

        def work():
            st = trade.load_stats()
            self.after(0, lambda: done(st))

        def done(st):
            if not st:
                self._open_trade(trade.base_query(base_name, ilvl),
                                 "Не удалось загрузить список модов трейда — открыл поиск только базы.")
                return
            q, miss = trade.mods_query(base_name, mods, st, ilvl)
            self._open_trade(q, ("Не нашёл на трейде: " + "; ".join(miss) + " — добавь вручную.") if miss else "")
        self.status.configure(text="Готовлю поиск на трейде…", fg=MUTED)
        threading.Thread(target=work, daemon=True).start()

    def trade_ready(self):
        """Готовый предмет: по каждому нужному моду — худший допустимый тир как минимум."""
        if not self.pool or not self.selected:
            return self.status.configure(text="Отметь нужные моды в «Пуле модов».", fg=WARN)
        from poecraft import trade
        mods = []
        for (kind, typ), v in self.selected.items():
            tiers = sorted((e for e in self.pool.all if e.mod.kind == kind and e.mod.type == typ and e.tier <= v["max_tier"]),
                           key=lambda e: -e.tier)
            if tiers:
                mods.append((tiers[0].mod.text, trade.min_value(tiers[0].mod.text)))
        self._trade_mods(mods, self.pool.base.name, None)

    def trade_emu(self):
        """Такой же предмет, как в эмуляторе: моды не хуже 90% от текущих значений."""
        if not self.emu or not self.emu.mods:
            return self.emu_status.configure(text="В эмуляторе нет модов.", fg=WARN)
        mods = []
        for m in self.emu.mods:
            if m.crafted or m.veiled:
                continue
            v = m.values[0] if m.values else None
            lo = None if v is None else (int(v * 0.9) if float(v).is_integer() else round(v * 0.9, 1))
            mods.append((m.mod.text, lo))
        self._trade_mods(mods, self.emu.pool.base.name, None)

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
        if getattr(self, "plan", None):
            rec["plan"] = [dict(x) for x in self.plan]
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
