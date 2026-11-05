"""Стартовое окно-хаб: плитки, активная цель, недавние предметы и библиотека крафтов.

Игровой оверлей живёт отдельно и появляется сам, когда в игре скопирован предмет.
"""

from __future__ import annotations

import os
import sys
import tkinter as tk
from tkinter import ttk

from poecraft import i18n, recipes
from poecraft.updater import APP_VERSION
from settings_win import frameless

BG = "#0f0d0a"
PANEL = "#16130f"
TITLE = "#1f1a14"
TILE = "#1a1611"
TILE_HI = "#241e16"
LINE = "#3a3127"
GOLD_LINE = "#6b5a22"
FG, MUTED, DIM, GOLD, GOOD, WARN = "#d9d0c1", "#8a7f70", "#5a5248", "#e3b55b", "#7ec27a", "#e07a5f"
FONT = "Segoe UI"

TILES = [
    ("workshop", "⚒", "Мастерская", "пул модов, калькулятор, эмулятор"),
    ("library", "☰", "Мои крафты", "библиотека целей и поиск"),
    ("import", "⇩", "Импорт кода", "вставить код PCH1 из буфера"),
    ("settings", "⚙", "Настройки", "хоткеи, язык, обновления"),
]


class HubWindow(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("PoE Craft Helper")
        self.configure(bg=BG, highlightthickness=1, highlightbackground=LINE)
        self.attributes("-topmost", True)
        geo = app.settings.get("hub_geo")
        if not geo:
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            geo = f"740x590+{max(0, (sw - 740) // 2)}+{max(0, (sh - 590) // 2)}"
        self.geometry(geo)
        self.minsize(660, 540)
        self.protocol("WM_DELETE_WINDOW", self.app.quit)
        self.bind("<Map>", lambda e: e.widget is self and self.after(10, lambda: frameless(self)), add="+")
        self.after(300, lambda: frameless(self))
        self._pending_delete = None
        self._style()
        self._build()
        self.show_home()
        self.lift()
        self._update = None
        self.after(2500, self._check_updates)
        from poecraft import icons
        st = icons.store()
        if st:
            st.subscribe(lambda: self.winfo_exists() and self.state() != "withdrawn" and self.refresh())

    # ------------------------------------------------------------ каркас
    def _style(self):
        st = ttk.Style(self)
        st.configure("H.Treeview", background=PANEL, fieldbackground=PANEL, foreground=FG, rowheight=26,
                     bordercolor=LINE, lightcolor=PANEL, darkcolor=PANEL, font=(FONT, 10))
        st.layout("H.Treeview", [("Treeview.field", {"sticky": "nswe", "border": 1, "children": [
            ("Treeview.padding", {"sticky": "nswe", "children": [("Treeview.treearea", {"sticky": "nswe"})]})]})])
        st.map("H.Treeview", background=[("selected", "#3a2c17")], foreground=[("selected", GOLD)])
        st.configure("H.Treeview.Heading", background=TITLE, foreground=MUTED, bordercolor=LINE,
                     lightcolor=TITLE, darkcolor=TITLE, font=(FONT, 9))
        st.map("H.Treeview.Heading", background=[("active", TITLE)])
        st.configure("H.Vertical.TScrollbar", background=TITLE, troughcolor=PANEL, bordercolor=PANEL,
                     arrowcolor=MUTED, lightcolor=TITLE, darkcolor=TITLE)

    def _build(self):
        head = tk.Frame(self, bg=TITLE)
        head.pack(fill="x")
        title = tk.Label(head, text="  POE CRAFT HELPER", bg=TITLE, fg=GOLD, font=(FONT, 10, "bold"),
                         compound="left")
        try:
            from PIL import Image, ImageTk
            from overlay import resource
            im = Image.open(resource("assets/icon.png")).resize((20, 20), Image.LANCZOS)
            self._title_icon = ImageTk.PhotoImage(im, master=self)
            title.configure(image=self._title_icon)
        except Exception:
            title.configure(text="⚒  POE CRAFT HELPER")
        title.pack(side="left", padx=10, pady=6)
        ver = tk.Label(head, text=f"v{APP_VERSION}", bg=TITLE, fg=DIM, font=(FONT, 8))
        ver.pack(side="left")
        for w in (head, title, ver):
            w.bind("<ButtonPress-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)
            w.bind("<ButtonRelease-1>", lambda e: self._remember_geo())
        self._head_btn(head, "✕", self.app.quit, WARN, "Выход")
        self._head_btn(head, "—", self.hide, GOLD, "Свернуть (оверлей продолжит работать)")
        self._head_btn(head, "⚙", lambda: self.app.open_settings(), GOLD, "Настройки")

        self.page = tk.Frame(self, bg=BG)
        self.page.pack(fill="both", expand=True)

        tk.Frame(self, bg=LINE, height=1).pack(fill="x", side="bottom")
        foot = tk.Frame(self, bg=TITLE)
        foot.pack(fill="x", side="bottom")
        self.status = tk.Label(foot, text="", bg=TITLE, fg=MUTED, font=(FONT, 9), anchor="w")
        self.status.pack(side="left", fill="x", expand=True, padx=10, pady=4)
        grip = tk.Label(foot, text="◢", bg=TITLE, fg=DIM, cursor="size_nw_se" if sys.platform == "win32" else "bottom_right_corner", font=(FONT, 10))
        grip.pack(side="right", padx=2)
        grip.bind("<ButtonPress-1>", self._resize_start)
        grip.bind("<B1-Motion>", self._resize_move)
        grip.bind("<ButtonRelease-1>", lambda e: self._remember_geo())

    def _head_btn(self, parent, text, cmd, hover, tip=""):
        b = tk.Label(parent, text=text, bg=TITLE, fg=MUTED, font=(FONT, 11), cursor="hand2", padx=9)
        b.pack(side="right")
        b.bind("<Button-1>", lambda e: cmd())
        b.bind("<Enter>", lambda e: (b.configure(fg=hover), tip and self.set_status(tip)))
        b.bind("<Leave>", lambda e: b.configure(fg=MUTED))
        return b

    def _drag_start(self, e):
        self._dx, self._dy = e.x_root - self.winfo_x(), e.y_root - self.winfo_y()

    def _drag_move(self, e):
        self.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    def _resize_start(self, e):
        self._rs = (e.x_root, e.y_root, self.winfo_width(), self.winfo_height())

    def _resize_move(self, e):
        x, y, w, h = self._rs
        self.geometry(f"{max(660, w + e.x_root - x)}x{max(540, h + e.y_root - y)}")

    def _remember_geo(self):
        self.app.settings["hub_geo"] = self.geometry()
        self.app.save_settings(self.app.settings)

    def show(self):
        self.deiconify()
        self.lift()
        self.refresh()

    def hide(self):
        self._remember_geo()
        self.withdraw()
        hk = self.app.hotkeys().get("hub")
        self.app.set_status(f"Хаб свёрнут. Вернуть: {hk}" if hk else "Хаб свёрнут.")

    def set_status(self, text, fg=MUTED):
        try:
            self.status.configure(text=text, fg=fg)
        except tk.TclError:
            pass

    def _clear(self):
        for w in self.page.winfo_children():
            w.destroy()

    def _small_btn(self, parent, text, cmd, fg=FG, bg=None):
        bg = bg or parent["bg"]
        b = tk.Label(parent, text=text, bg=bg, fg=fg, font=(FONT, 9), cursor="hand2", padx=8, pady=3,
                     highlightthickness=1, highlightbackground=LINE)
        b.bind("<Button-1>", lambda e: cmd())
        b.bind("<Enter>", lambda e: b.configure(fg=GOLD, highlightbackground=GOLD_LINE))
        b.bind("<Leave>", lambda e: b.configure(fg=fg, highlightbackground=LINE))
        return b

    def _caption(self, parent, text):
        tk.Label(parent, text=text.upper(), bg=parent["bg"], fg=MUTED, font=(FONT, 8, "bold"),
                 anchor="w").pack(fill="x", pady=(12, 4))

    def refresh(self):
        if getattr(self, "mode", "home") == "home":
            self.show_home()
        else:
            self.show_library()

    # ------------------------------------------------------------ обновления (тихая проверка при запуске)
    def _check_updates(self):
        repo = self.app.settings.get("update_repo", "")
        if not repo or not self.app.settings.get("check_updates", True):
            return
        import threading
        from poecraft import updater

        def run():
            res = updater.check(repo)
            try:
                self.after(0, lambda: self._got_update(res))
            except (tk.TclError, RuntimeError):
                pass
        threading.Thread(target=run, daemon=True).start()

    def _got_update(self, res):
        if res.get("newer"):
            self._update = res
            if getattr(self, "mode", "home") == "home":
                self.show_home()

    def _update_banner(self, parent):
        u = self._update
        b = tk.Frame(parent, bg="#2a231a", highlightthickness=1, highlightbackground=GOLD_LINE, cursor="hand2")
        b.pack(fill="x", padx=4, pady=(4, 6))
        l = tk.Label(b, text=f"⬆  Доступна версия {u['latest']} — нажми, чтобы открыть страницу загрузки",
                     bg="#2a231a", fg=GOLD, font=(FONT, 10), anchor="w", padx=10, pady=6, cursor="hand2")
        l.pack(fill="x")
        import webbrowser
        for w in (b, l):
            w.bind("<Button-1>", lambda e: webbrowser.open(u.get("page") or u.get("url")))

    # ------------------------------------------------------------ главная
    def show_home(self):
        self.mode = "home"
        self._clear()
        p = tk.Frame(self.page, bg=BG)
        p.pack(fill="both", expand=True, padx=16, pady=8)
        if getattr(self, "_update", None):
            self._update_banner(p)

        tiles = tk.Frame(p, bg=BG)
        tiles.pack(fill="x", pady=(4, 0))
        for i, (key, icon, name, sub) in enumerate(TILES):
            self._tile(tiles, key, icon, name, sub).grid(row=0, column=i, sticky="nsew", padx=4)
            tiles.columnconfigure(i, weight=1, uniform="t")

        cols = tk.Frame(p, bg=BG)
        cols.pack(fill="both", expand=True)
        left = tk.Frame(cols, bg=BG)
        left.pack(side="left", fill="both", expand=True, padx=(4, 8))
        right = tk.Frame(cols, bg=BG, width=250)
        right.pack(side="left", fill="y", padx=(8, 4))
        right.pack_propagate(False)

        self._caption(left, "Активная цель")
        self._goal_card(left)
        self._caption(right, "Недавние предметы")
        self._recent(right)
        i18n.translate_tree(self.page)
        self._idle_status()

    def _tile(self, parent, key, icon, name, sub):
        f = tk.Frame(parent, bg=TILE, highlightthickness=1, highlightbackground=LINE, cursor="hand2")
        a = tk.Label(f, text=icon, bg=TILE, fg=GOLD, font=(FONT, 20))
        b = tk.Label(f, text=name, bg=TILE, fg=FG, font=(FONT, 11, "bold"))
        c = tk.Label(f, text=sub, bg=TILE, fg=MUTED, font=(FONT, 8), wraplength=140, justify="center")
        a.pack(pady=(12, 0))
        b.pack()
        c.pack(pady=(2, 12), padx=6)
        parts = (f, a, b, c)

        def hover(on):
            for w in parts:
                w.configure(bg=TILE_HI if on else TILE)
            f.configure(highlightbackground=GOLD_LINE if on else LINE)
            b.configure(fg=GOLD if on else FG)
        for w in parts:
            w.bind("<Enter>", lambda e: hover(True))
            w.bind("<Leave>", lambda e: hover(False))
            w.bind("<Button-1>", lambda e, k=key: self._tile_click(k))
        return f

    def _tile_click(self, key):
        if key == "workshop":
            self.app.open_main()
        elif key == "library":
            self.show_library()
        elif key == "import":
            self.import_code()
        elif key == "settings":
            self.app.open_settings()

    def _goal_card(self, parent):
        g, f = self.app.current_goal(), self.app.current_goal_file()
        card = tk.Frame(parent, bg=TILE, highlightthickness=1, highlightbackground=GOLD_LINE)
        card.pack(fill="x")
        inner = tk.Frame(card, bg=TILE)
        inner.pack(fill="x", padx=12, pady=10)
        if not g:
            tk.Label(inner, text="Цель не выбрана", bg=TILE, fg=FG, font=(FONT, 11, "bold"), anchor="w").pack(fill="x")
            tk.Label(inner, text="Выбери крафт в библиотеке или создай новый.", bg=TILE, fg=MUTED,
                     font=(FONT, 9), anchor="w").pack(fill="x", pady=(2, 8))
            row = tk.Frame(inner, bg=TILE)
            row.pack(fill="x")
            self._small_btn(row, "Мои крафты", self.show_library, GOLD).pack(side="left")
            self._small_btn(row, "+ Новый", self.app.new_recipe).pack(side="left", padx=6)
            return
        raw = g.raw
        tk.Label(inner, text=g.name, bg=TILE, fg=GOLD, font=(FONT, 12, "bold"), anchor="w",
                 justify="left", wraplength=380).pack(fill="x")
        cls = recipes.CLASS_RU.get(raw.get("base_class") or "", raw.get("base_class") or "любой класс")
        meta = [cls]
        if raw.get("base"):
            meta.append(raw["base"])
        if raw.get("min_ilvl"):
            meta.append(f"ilvl {raw['min_ilvl']}+")
        if raw.get("author"):
            meta.append(f"автор: {raw['author']}")
        tk.Label(inner, text="  ·  ".join(meta), bg=TILE, fg=MUTED, font=(FONT, 9), anchor="w").pack(fill="x", pady=(2, 6))
        mods = tk.Frame(inner, bg=TILE)
        mods.pack(fill="x")
        for w in raw.get("wanted", []):
            kind = {"prefix": "П", "suffix": "С"}.get(w.get("kind"), "·")
            tier = f"до T{w['max_tier']}" if w.get("max_tier", 99) < 99 else ""
            r = tk.Frame(mods, bg=TILE)
            r.pack(fill="x")
            tk.Label(r, text=kind, bg=TILE, fg=DIM, font=("Consolas", 9), width=2).pack(side="left")
            tk.Label(r, text=w.get("label") or w.get("mod_type"), bg=TILE, fg=FG, font=(FONT, 10),
                     anchor="w").pack(side="left")
            if tier:
                tk.Label(r, text=tier, bg=TILE, fg=MUTED, font=(FONT, 9)).pack(side="right")
        desc = (raw.get("description") or "").strip()
        if desc:
            dr = tk.Frame(inner, bg=TILE)
            dr.pack(fill="x", pady=(8, 0))
            from poecraft import icons
            st = icons.store()
            for n in (st.find_all(desc, 3) if st else []):
                img = st.get(n, 28)
                if img is not None:
                    il = tk.Label(dr, image=img, bg=TILE)
                    il._img = img
                    il.pack(side="left", padx=(0, 4))
            tk.Label(dr, text=desc, bg=TILE, fg=MUTED, font=(FONT, 9), anchor="w", justify="left",
                     wraplength=340).pack(side="left", fill="x", expand=True)
        row = tk.Frame(inner, bg=TILE)
        row.pack(fill="x", pady=(10, 0))
        self._small_btn(row, "Сменить", self.show_library, GOLD).pack(side="left")
        self._small_btn(row, "Изменить", self.app.edit_recipe).pack(side="left", padx=6)
        self._small_btn(row, "Поделиться", self.share).pack(side="left")
        hk = self.app.settings.get("copy_hint", "Ctrl+Alt+C")
        tk.Label(inner, text=f"В игре наведи на предмет и нажми {hk} — оверлей покажет следующий шаг.",
                 bg=TILE, fg=DIM, font=(FONT, 8), anchor="w", justify="left", wraplength=380).pack(fill="x", pady=(10, 0))

    def _recent(self, parent):
        items = self.app.settings.get("recent", [])
        if not items:
            tk.Label(parent, text="Пока пусто. Скопируй предмет в игре — он появится здесь.",
                     bg=BG, fg=DIM, font=(FONT, 9), justify="left", wraplength=240, anchor="w").pack(fill="x")
            return
        for it in items[:6]:
            row = tk.Frame(parent, bg=PANEL, highlightthickness=1, highlightbackground=LINE, cursor="hand2")
            row.pack(fill="x", pady=2)
            done, total = it.get("done", 0), it.get("total", 0)
            color = GOOD if total and done >= total else (GOLD if done else WARN)
            a = tk.Label(row, text=it.get("name", "?"), bg=PANEL, fg=FG, font=(FONT, 10), anchor="w")
            b = tk.Label(row, text=f"{done}/{total}", bg=PANEL, fg=color, font=(FONT, 10, "bold"))
            c = tk.Label(row, text=it.get("goal", ""), bg=PANEL, fg=DIM, font=(FONT, 8), anchor="w")
            b.grid(row=0, column=1, rowspan=2, padx=8)
            a.grid(row=0, column=0, sticky="w", padx=(8, 0), pady=(4, 0))
            c.grid(row=1, column=0, sticky="w", padx=(8, 0), pady=(0, 4))
            row.columnconfigure(0, weight=1)
            parts = (row, a, b, c)
            for w in parts:
                w.bind("<Enter>", lambda e, ws=parts: [x.configure(bg=TILE_HI) for x in ws])
                w.bind("<Leave>", lambda e, ws=parts: [x.configure(bg=PANEL) for x in ws])
                w.bind("<Button-1>", lambda e, t=it.get("text"): t and self.app.reopen_item(t))

    def _idle_status(self):
        if not self.app.data:
            self.set_status("Загружаю данные модов…")
        else:
            hk = self.app.hotkeys()
            parts = [f"данные {self.app.data.version}"]
            if hk.get("overlay"):
                parts.append(f"оверлей {hk['overlay']}")
            if hk.get("hub"):
                parts.append(f"хаб {hk['hub']}")
            self.set_status("  ·  ".join(parts))

    # ------------------------------------------------------------ библиотека
    def show_library(self):
        self.mode = "library"
        self._clear()
        p = tk.Frame(self.page, bg=BG)
        p.pack(fill="both", expand=True, padx=16, pady=10)

        top = tk.Frame(p, bg=BG)
        top.pack(fill="x")
        back = tk.Label(top, text="←  Главная", bg=BG, fg=MUTED, font=(FONT, 10), cursor="hand2")
        back.pack(side="left")
        back.bind("<Button-1>", lambda e: self.show_home())
        back.bind("<Enter>", lambda e: back.configure(fg=GOLD))
        back.bind("<Leave>", lambda e: back.configure(fg=MUTED))
        tk.Label(top, text="МОИ КРАФТЫ", bg=BG, fg=GOLD, font=(FONT, 11, "bold")).pack(side="left", padx=16)
        self.count_lbl = tk.Label(top, text="", bg=BG, fg=DIM, font=(FONT, 9))
        self.count_lbl.pack(side="left")

        sr = tk.Frame(p, bg=TITLE, highlightthickness=1, highlightbackground=LINE)
        sr.pack(fill="x", pady=(10, 6))
        tk.Label(sr, text="⌕", bg=TITLE, fg=MUTED, font=(FONT, 11)).pack(side="left", padx=(8, 2))
        self.q = tk.StringVar()
        e = tk.Entry(sr, textvariable=self.q, bg=TITLE, fg=FG, insertbackground=GOLD, relief="flat",
                     font=(FONT, 10))
        e.pack(side="left", fill="x", expand=True, ipady=5, padx=4)
        self.q.trace_add("write", lambda *a: self._fill_library())
        self.cls_var = tk.StringVar(value="Все классы")
        classes = ["Все классы"] + sorted({recipes.CLASS_RU.get(g.raw.get("base_class") or "", "Любой")
                                           for _, g in self.app.goals})
        cb = ttk.Combobox(sr, textvariable=self.cls_var, values=classes, state="readonly", width=16,
                          style="G.TCombobox", font=(FONT, 9))
        from mainwin import popdown_on_top
        popdown_on_top(cb)
        cb.pack(side="right", padx=6)
        cb.bind("<<ComboboxSelected>>", lambda e: self._fill_library())

        acts = tk.Frame(p, bg=BG)
        acts.pack(fill="x", side="bottom", pady=(8, 0))
        self._small_btn(acts, "★ Сделать активной", self._lib_activate, GOLD).pack(side="left")
        self._small_btn(acts, "+ Новый", self.app.new_recipe).pack(side="left", padx=(6, 0))
        self._small_btn(acts, "Изменить", self._lib_edit).pack(side="left", padx=(6, 0))
        self._small_btn(acts, "Поделиться", self._lib_share).pack(side="left", padx=(6, 0))
        self._small_btn(acts, "Импорт", self.import_code).pack(side="left", padx=(6, 0))
        self.del_btn = self._small_btn(acts, "Удалить", self._lib_delete, WARN)
        self.del_btn.pack(side="right")
        self._small_btn(acts, "Папка", self.app.open_goals).pack(side="right", padx=6)

        body = tk.Frame(p, bg=BG)
        body.pack(fill="both", expand=True)
        self.tv = ttk.Treeview(body, style="H.Treeview", columns=("cls", "author"), show="tree headings",
                               selectmode="browse")
        self.tv.heading("#0", text="Название", anchor="w")
        self.tv.heading("cls", text="Класс", anchor="w")
        self.tv.heading("author", text="Автор", anchor="w")
        self.tv.column("#0", width=330, stretch=True)
        self.tv.column("cls", width=120, stretch=False)
        self.tv.column("author", width=130, stretch=False)
        self.tv.tag_configure("active", foreground=GOLD)
        sb = ttk.Scrollbar(body, orient="vertical", command=self.tv.yview, style="H.Vertical.TScrollbar")
        self.tv.configure(yscrollcommand=sb.set)
        self.tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tv.bind("<Double-1>", lambda e: self._lib_activate())
        self.tv.bind("<<TreeviewSelect>>", lambda e: self._lib_selected())

        self.desc_lbl = tk.Label(p, text="", bg=BG, fg=MUTED, font=(FONT, 9), anchor="w", justify="left",
                                 wraplength=660)
        self.desc_lbl.pack(fill="x", side="bottom", pady=(6, 0))
        self._fill_library()
        i18n.translate_tree(self.page)
        e.focus_set()
        self.set_status("Двойной клик — сделать крафт активным. Код для друзей — «Поделиться».")

    def _fill_library(self):
        if not hasattr(self, "tv") or not self.tv.winfo_exists():
            return
        q = self.q.get().strip().lower()
        cls_f = self.cls_var.get()
        active = self.app.current_goal_file()
        self.tv.delete(*self.tv.get_children())
        shown = 0
        for fname, g in self.app.goals:
            raw = g.raw
            cls = recipes.CLASS_RU.get(raw.get("base_class") or "", "Любой")
            hay = " ".join([g.name, cls, raw.get("author", ""), raw.get("base") or "",
                            " ".join(w.get("label", "") for w in raw.get("wanted", []))]).lower()
            if q and q not in hay:
                continue
            if cls_f not in ("Все классы", "All classes") and cls != cls_f:
                continue
            mark = "★  " if fname == active else "     "
            self.tv.insert("", "end", iid=fname, text=mark + g.name, values=(cls, raw.get("author", "")),
                           tags=("active",) if fname == active else ())
            shown += 1
        self.count_lbl.configure(text=f"{shown} из {len(self.app.goals)}")
        if active and self.tv.exists(active):
            self.tv.selection_set(active)
            self.tv.see(active)

    def _sel(self):
        s = self.tv.selection()
        if not s:
            self.set_status("Сначала выбери крафт в списке.", WARN)
            return None
        return s[0]

    def _lib_selected(self):
        self._pending_delete = None
        self.del_btn.configure(text="Удалить")
        f = self.tv.selection()
        g = dict(self.app.goals).get(f[0]) if f else None
        if g:
            wanted = ", ".join(w.get("label") or w.get("mod_type") for w in g.raw.get("wanted", []))
            desc = (g.raw.get("description") or "").strip()
            plan = g.raw.get("plan") or []
            if plan:
                from poecraft.plans import step_text
                desc = "Рецепт: " + " → ".join(step_text(x).split("  ")[1 if x.get("if") else 0]
                                               for x in plan[:6]) + (" …" if len(plan) > 6 else "") + \
                       (f"\n{desc}" if desc else "")
            self.desc_lbl.configure(text=f"Моды: {wanted}" + (f"\n{desc}" if desc else ""))

    def _lib_activate(self):
        f = self._sel()
        if f:
            self.app.set_goal(f)
            self._fill_library()
            self.set_status(f"Активная цель: {dict(self.app.goals)[f].name}", GOLD)

    def _lib_edit(self):
        f = self._sel()
        if f:
            self.app.set_goal(f)
            self.app.edit_recipe()

    def _lib_share(self):
        f = self._sel()
        if f:
            self._copy_code(dict(self.app.goals)[f])

    def _lib_delete(self):
        f = self._sel()
        if not f:
            return
        if self._pending_delete != f:
            self._pending_delete = f
            self.del_btn.configure(text="Точно удалить?")
            self.set_status("Нажми ещё раз, чтобы удалить файл крафта.", WARN)
            return
        try:
            os.remove(self.app.goals_dir / f)
        except OSError as e:
            return self.set_status(f"Не удалось удалить: {e}", WARN)
        self._pending_delete = None
        self.app.reload_goals()
        self.show_library()
        self.set_status("Крафт удалён.")

    # ------------------------------------------------------------ общие действия
    def _copy_code(self, g):
        code = recipes.encode(g.raw)
        self.app.last_clip = code
        self.app.root.clipboard_clear()
        self.app.root.clipboard_append(code)
        self.set_status(f"Код «{g.name}» скопирован — вставь его в Discord или Telegram.", GOLD)

    def share(self):
        g = self.app.current_goal()
        if g:
            self._copy_code(g)

    def import_code(self):
        try:
            text = self.app.root.clipboard_get()
        except tk.TclError:
            text = ""
        try:
            r = recipes.decode(text)
        except ValueError as e:
            return self.set_status(f"{e} Скопируй код PCH1:… и нажми ещё раз.", WARN)
        self.app.last_clip = text
        self.app._saved(r, None)
        by = f" от {r['author']}" if r.get("author") else ""
        self.refresh()
        self.set_status(f"Добавлен и выбран крафт «{r['name']}»{by}.", GOOD)
