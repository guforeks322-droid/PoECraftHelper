"""Главное окно поверх игры (без браузера): пул модов и калькулятор.

Открывается кнопкой «окно ⧉» в оверлее. Без рамки, всегда сверху, полупрозрачное,
перетаскивается за заголовок, размер меняется уголком справа снизу.
"""

from __future__ import annotations

import queue
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
from poecraft import hotkeys as hkmod
from poecraft.updater import APP_VERSION
from poecraft.data import APP_DIR, GameData
from poecraft.pool import ModPool
from poecraft.prices import Prices

BG, BG1, BG2, LINE = "#0f0d0a", "#16130f", "#1f1a14", "#3a3127"
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
        self.inf_box.pack(side="left", padx=(4, 10))
        self.inf_box.bind("<<ComboboxSelected>>", lambda e: self.load_pool())
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
        grip = tk.Label(foot, text="◢", bg=BG, fg=MUTED, cursor="size_nw_se", font=(FONT, 10))
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
            tv = ttk.Treeview(fr, style="D.Treeview", columns=("chk", "all", "kind", "tier"),
                              show="tree headings", selectmode="browse")
            tv.heading("#0", text="Мод", anchor="w")
            tv.heading("chk", text="")
            tv.heading("all", text="% всех")
            tv.heading("kind", text="% типа")
            tv.heading("tier", text="тир")
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
        self.fos_tv = mk(panes, (None, " ", "фоссил", "эффект", "цена"), (0, 26, 110, 190, 60), 1)
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
            tv.insert("", "end", iid=name, values=("☑" if name in self.fos_sel else "☐",
                      name.replace(" Fossil", ""), fo.describe, self._price_txt(name)),
                      tags=("sel",) if name in self.fos_sel else ())
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
            tv.insert("", "end", iid=e.id, text=e.name, values=(short(e.mod.text), f"T{fe.tier}", self._price_txt(e.name)))

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
        f = self.tab_emu
        self.emu: Emulator | None = None
        f.columnconfigure(0, weight=5)
        f.columnconfigure(1, weight=3)
        f.columnconfigure(2, weight=3)
        f.rowconfigure(1, weight=1)

        top = tk.Frame(f, bg=BG)
        top.grid(row=0, column=0, columnspan=3, sticky="we", padx=6, pady=(8, 4))
        self._act(top, "Новый белый предмет", self.emu_new).pack(side="left")
        self._btn(top, "↶ отменить", lambda: self.emu_do("undo")).pack(side="left", padx=(10, 0))
        self.emu_status = tk.Label(top, text="Выбери базу сверху и нажми «Новый белый предмет».", bg=BG, fg=MUTED,
                                   font=(FONT, 9))
        self.emu_status.pack(side="left", padx=10)

        self.emu_card = tk.Text(f, bg=BG1, fg=FG, relief="flat", wrap="word", font=(FONT, 10), width=50,
                                highlightthickness=1, highlightbackground=LINE, padx=12, pady=10, cursor="arrow")
        self.emu_card.grid(row=1, column=0, sticky="nsew", padx=(6, 4), pady=(0, 6))
        for tag, kw in (("Normal", dict(foreground="#c8c8c8", font=(FONT, 12, "bold"))),
                        ("Magic", dict(foreground="#8888ff", font=(FONT, 12, "bold"))),
                        ("Rare", dict(foreground="#ffff77", font=(FONT, 12, "bold"))),
                        ("m", dict(foreground=MUTED, font=(FONT, 9))), ("good", dict(foreground=GOOD)),
                        ("craft", dict(foreground=BLUE)), ("frac", dict(foreground="#a29162")),
                        ("h", dict(foreground=GOLD, font=(FONT, 10, "bold"))), ("bad", dict(foreground=WARN)),
                        ("infl", dict(foreground="#c39bd3")), ("veil", dict(foreground="#d4a44c"))):
            self.emu_card.tag_configure(tag, **kw)
        self.emu_card.configure(state="disabled")

        side = tk.Frame(f, bg=BG)
        side.grid(row=1, column=1, sticky="nsew", padx=(4, 6), pady=(0, 6))
        tk.Label(side, text="Валюта", bg=BG, fg=GOLD, font=(FONT, 10, "bold"), anchor="w").pack(fill="x")
        grid = tk.Frame(side, bg=BG)
        grid.pack(fill="x", pady=(2, 6))
        buttons = [("Transmutation", "transmute"), ("Alteration", "alteration"), ("Augmentation", "augment"),
                   ("Regal", "regal"), ("Alchemy", "alchemy"), ("Chaos", "chaos"), ("Exalted", "exalt"),
                   ("Annulment", "annul"), ("Scouring", "scour"), ("Divine", "divine")]
        for i, (label, act) in enumerate(buttons):
            b = self._act(grid, label, lambda a=act: self.emu_do(a))
            b.configure(font=(FONT, 9), padx=6, pady=3, width=12)
            b.grid(row=i // 2, column=i % 2, sticky="we", padx=2, pady=2)
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        tk.Label(side, text="Эссенция", bg=BG, fg=GOLD, font=(FONT, 10, "bold"), anchor="w").pack(fill="x", pady=(4, 0))
        er = tk.Frame(side, bg=BG)
        er.pack(fill="x")
        self.emu_ess_var = tk.StringVar()
        self.emu_ess_box = ttk.Combobox(er, textvariable=self.emu_ess_var, state="readonly", style="D.TCombobox",
                                        font=(FONT, 9), width=28)
        popdown_on_top(self.emu_ess_box)
        self.emu_ess_box.pack(side="left", fill="x", expand=True)
        self._btn(er, "применить", self.emu_essence).pack(side="left")

        tk.Label(side, text="Фоссилы (выбираются во вкладке «Эссенции и фоссилы»)", bg=BG, fg=GOLD,
                 font=(FONT, 9, "bold"), anchor="w", wraplength=300, justify="left").pack(fill="x", pady=(6, 0))
        fr = tk.Frame(side, bg=BG)
        fr.pack(fill="x")
        self.emu_fos_lbl = tk.Label(fr, text="не выбраны", bg=BG, fg=MUTED, font=(FONT, 9), anchor="w")
        self.emu_fos_lbl.pack(side="left", fill="x", expand=True)
        self._btn(fr, "применить", self.emu_fossils).pack(side="left")

        tk.Label(side, text="Верстак", bg=BG, fg=GOLD, font=(FONT, 10, "bold"), anchor="w").pack(fill="x", pady=(6, 0))
        br = tk.Frame(side, bg=BG)
        br.pack(fill="x")
        self.emu_bench_var = tk.StringVar()
        self.emu_bench_box = ttk.Combobox(br, textvariable=self.emu_bench_var, state="readonly", style="D.TCombobox",
                                          font=(FONT, 9), width=28)
        popdown_on_top(self.emu_bench_box)
        self.emu_bench_box.pack(side="left", fill="x", expand=True)
        self._btn(br, "скрафтить", self.emu_bench).pack(side="left")
        self._btn(side, "снять крафты верстака", lambda: self.emu_do("remove_crafted")).pack(anchor="w")

        side2 = tk.Frame(f, bg=BG)
        side2.grid(row=1, column=2, sticky="nsew", padx=(4, 6), pady=(0, 6))
        tk.Label(side2, text="Влияние · Eldritch", bg=BG, fg=GOLD, font=(FONT, 10, "bold"), anchor="w").pack(fill="x", pady=(0, 0))
        ir = tk.Frame(side2, bg=BG)
        ir.pack(fill="x")
        self.emu_conq_var = tk.StringVar(value="Crusader")
        cq = ttk.Combobox(ir, textvariable=self.emu_conq_var, state="readonly", style="D.TCombobox",
                          values=list(inf.CONQUEROR_ORBS), width=10, font=(FONT, 9))
        popdown_on_top(cq)
        cq.pack(side="left")
        self._btn(ir, "Exalt завоевателя", lambda: self.emu_do("conqueror", name=self.emu_conq_var.get())).pack(side="left")
        er2 = tk.Frame(side2, bg=BG)
        er2.pack(fill="x", pady=(2, 0))
        self.emu_eld_var = tk.StringVar(value="Grand")
        eb = ttk.Combobox(er2, textvariable=self.emu_eld_var, state="readonly", style="D.TCombobox",
                          values=[inf.ELDRITCH_TIERS[i] for i in (1, 2, 3, 4)], width=10, font=(FONT, 9))
        popdown_on_top(eb)
        eb.pack(side="left")
        lvl = lambda: {v: k for k, v in inf.ELDRITCH_TIERS.items()}[self.emu_eld_var.get()]
        self._btn(er2, "Ember (Exarch)", lambda: self.emu_do("eldritch_currency", side="exarch", level=lvl())).pack(side="left")
        self._btn(er2, "Ichor (Eater)", lambda: self.emu_do("eldritch_currency", side="eater", level=lvl())).pack(side="left")
        eg = tk.Frame(side2, bg=BG)
        eg.pack(fill="x", pady=(2, 0))
        for i, (label, act) in enumerate((("Eldritch Chaos", "eldritch_chaos"), ("Eldritch Exalt", "eldritch_exalt"),
                                          ("Eldritch Annul", "eldritch_annul"), ("Orb of Conflict", "conflict"))):
            b = self._act(eg, label, lambda a=act: self.emu_do(a))
            b.configure(font=(FONT, 9), padx=4, pady=2)
            b.grid(row=i // 2, column=i % 2, sticky="we", padx=2, pady=2)
        eg.columnconfigure(0, weight=1)
        eg.columnconfigure(1, weight=1)
        tk.Label(side2, text="Harvest", bg=BG, fg=GOLD, font=(FONT, 10, "bold"), anchor="w").pack(fill="x", pady=(8, 0))
        hr = tk.Frame(side2, bg=BG)
        hr.pack(fill="x")
        from poecraft.harvest import HARVEST
        self.emu_hv_var = tk.StringVar(value="Fire")
        hb = ttk.Combobox(hr, textvariable=self.emu_hv_var, state="readonly", style="D.TCombobox",
                          values=list(HARVEST), width=10, font=(FONT, 9))
        popdown_on_top(hb)
        hb.pack(side="left")
        self._btn(hr, "Reforge", lambda: self.emu_do("harvest_reforge", label=self.emu_hv_var.get())).pack(side="left")
        self._btn(hr, "+мод/−мод", lambda: self.emu_do("harvest_augment", label=self.emu_hv_var.get())).pack(side="left")
        hr2 = tk.Frame(side2, bg=BG)
        hr2.pack(fill="x")
        self._btn(hr2, "тех же модов ↑", lambda: self.emu_do("harvest_same", more=True)).pack(side="left")
        self._btn(hr2, "тех же модов ↓", lambda: self.emu_do("harvest_same", more=False)).pack(side="left")

        tk.Label(side2, text="Veiled (Jun)", bg=BG, fg=GOLD, font=(FONT, 10, "bold"), anchor="w").pack(fill="x", pady=(8, 0))
        vg = tk.Frame(side2, bg=BG)
        vg.pack(fill="x")
        for i, (label, cmd) in enumerate((("Veiled Chaos", lambda: self.emu_do("veiled_chaos")),
                                          ("Veiled Exalt", lambda: self.emu_do("veiled_exalt")),
                                          ("Unveil (1 из 3)", self.emu_unveil))):
            b = self._act(vg, label, cmd)
            b.configure(font=(FONT, 9), padx=4, pady=2)
            b.grid(row=i // 2, column=i % 2, sticky="we", padx=2, pady=2)
        vg.columnconfigure(0, weight=1)
        vg.columnconfigure(1, weight=1)
        self.emu_unveil_frame = tk.Frame(side2, bg=BG)
        self.emu_unveil_frame.pack(fill="x", pady=(4, 0))
        self.emu_spent = tk.Label(side, text="", bg=BG, fg=FG, font=(FONT, 9), anchor="w", justify="left",
                                  wraplength=320)
        # потраченное теперь выводится в карточке предмета

    def emu_new(self):
        if not self.pool:
            self.emu_status.configure(text="Сначала выбери базу сверху.", fg=WARN)
            return
        infl = [self.inf_var.get()] if self.inf_var.get() in getattr(self, "inf_map", {}) else []
        self.emu = Emulator(self.data, self.base_pool, influences=infl)
        self._emu_lists()
        self.emu_status.configure(text=f"{self.pool.base.name}, ilvl {self.pool.ilvl}", fg=MUTED)
        self._emu_render()

    def _emu_lists(self):
        if not self.emu:
            return
        ess = [e for e in cc.essences_for(self.data, self.pool.base.item_class)
               if not (e.max_ilvl and self.pool.ilvl > e.max_ilvl)]
        self._emu_ess = {f"{e.name} — {short(e.mod.text)}": e for e in ess}
        self.emu_ess_box["values"] = list(self._emu_ess)
        opts = self.emu.bench_options()
        metas = [o for o in opts if any(g.startswith("ItemGeneration") for g in o["mod"].groups)]
        rest = [o for o in opts if o not in metas]
        from poecraft.advisor import CURRENCY_RU

        def lbl(o):
            cost = ", ".join(f"{v} {CURRENCY_RU.get(k, k).replace('Orb of ', '').replace(' Orb', '')}" for k, v in o["cost"].items())
            return f"{'★ ' if o in metas else ''}{o['mod'].text.splitlines()[0]}  [{cost}]"
        self._emu_bench = {lbl(o): o for o in metas + rest}
        self.emu_bench_box["values"] = list(self._emu_bench)

    def emu_do(self, action, **kw):
        if not self.emu:
            self.emu_status.configure(text="Сначала нажми «Новый белый предмет».", fg=WARN)
            return
        try:
            if action == "undo":
                self.emu.undo()
            else:
                self.emu.apply(action, **kw)
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
        self.emu_do("essence", essence=e)

    def emu_fossils(self):
        if not self.fos_sel:
            self.emu_status.configure(text="Выбери фоссилы во вкладке «Эссенции и фоссилы».", fg=WARN)
            return
        self.emu_do("fossils", fossils=[self.fos_list[n] for n in self.fos_sel])

    def emu_bench(self):
        o = self._emu_bench.get(self.emu_bench_var.get()) if self.emu else None
        if not o:
            self.emu_status.configure(text="Выбери крафт верстака в списке.", fg=WARN)
            return
        self.emu_do("bench", option=o)

    def _emu_render(self):
        em = self.emu
        c = self.emu_card
        c.configure(state="normal")
        c.delete("1.0", "end")
        self.emu_fos_lbl.configure(text=", ".join(n.replace(" Fossil", "") for n in self.fos_sel) or "не выбраны")
        if not em:
            c.configure(state="disabled")
            return
        targets = self._targets()
        names = {"Normal": "Обычный", "Magic": "Магический", "Rare": "Редкий"}
        c.insert("end", f"{em.pool.base.name}\n", em.rarity)
        mp, ms = em.limits()
        c.insert("end", f"{names[em.rarity]} · ilvl {em.pool.ilvl} · префиксов {len(em.prefixes)}/{mp if em.rarity != 'Magic' else 1}"
                        f" · суффиксов {len(em.suffixes)}/{ms if em.rarity != 'Magic' else 1}\n\n", "m")
        if em.influences:
            c.insert("end", "Влияние: " + ", ".join(em.influences) + "\n", "infl")
        for side_, title_ in (("exarch", "Searing Exarch"), ("eater", "Eater of Worlds")):
            im_ = getattr(em, side_)
            if im_:
                dom = " (доминирует)" if em.dominance() == side_ else ""
                c.insert("end", f"{title_} [{inf.ELDRITCH_TIERS[im_.level]}]{dom}: ", "m")
                c.insert("end", im_.text + "\n", "craft")
        if em.influences or em.exarch or em.eater:
            c.insert("end", "\n")
        if not em.mods:
            c.insert("end", "Модов нет.\n", "m")
        for kind, title in (("prefix", "Префиксы"), ("suffix", "Суффиксы")):
            mods = [m for m in em.mods if m.kind == kind]
            if not mods:
                continue
            c.insert("end", title + "\n", "h")
            for m in mods:
                tag = "craft" if m.crafted else ("veil" if m.veiled else
                      ("good" if any(t.ok(m.entry) for t in targets) else
                       ("infl" if inf.is_influence_mod(m.mod) else None)))
                tier = "крафт" if m.crafted else ("скрыт" if m.veiled else f"T{m.entry.tier}")
                c.insert("end", f"  {tier:<6}", "m")
                c.insert("end", m.text + "\n", tag or ())
            c.insert("end", "\n")
        if targets:
            ch = em.chances(targets)
            c.insert("end", f"Цели: {ch['have']}/{ch['need']}", "h")
            if ch["missing"]:
                c.insert("end", "  · не хватает: " + ", ".join(ch["missing"]) + "\n", "m")
                for key, label in (("augment", "Augmentation"), ("regal", "Regal"), ("exalt", "Exalt"),
                                   ("exalt_blocked", "Exalt с блоком другого типа слота"),
                                   ("exalt_no_attack", "Exalt + «Cannot roll Attack»"),
                                   ("exalt_no_caster", "Exalt + «Cannot roll Caster»")):
                    if key in ch:
                        c.insert("end", f"  {label}: ", "m")
                        c.insert("end", f"{pct(ch[key])}\n", "good" if ch[key] >= 0.2 else ())
            else:
                c.insert("end", "  · всё на месте!\n", "good")
        total = sum(self.prices.get(k) * v for k, v in em.spent.items())
        parts_ = [f"{k.replace('Orb of ', '').replace(' Orb', '')}: {v}" for k, v in em.spent.items() if v]
        c.insert("end", "\nПотрачено: ", "h")
        c.insert("end", (" · ".join(parts_) + f"   ≈ {total:,.0f}c ({total / self.prices.divine:.2f} div)".replace(",", " "))
                 if parts_ else "ничего", "m")
        c.configure(state="disabled")

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
                          values=("☑" if sel else "☐", pct(g["chance_all"]), pct(g["chance_kind"]), f"{i18n.t('до T')}{tier}"),
                          tags=("sel",) if sel else (("infl",) if is_inf else ()))
                for t in g["tiers"]:
                    rng_ = " ".join(__import__("re").findall(r"\([\d.]+-[\d.]+\)|(?<![\w(])\d+(?:\.\d+)?(?![\w)-])", t["text"]))
                    tv.insert(gid, "end", text=f"T{t['tier']}  {rng_}   {t['name']} · ilvl {t['level']}",
                              values=("", "", f"{t['weight']}", ""), tags=("tier" if t["available"] else "na",))

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
        elif col == "#4":  # тир по кругу
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
        for r in results:
            o.insert("end", r["name"], "h")
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
