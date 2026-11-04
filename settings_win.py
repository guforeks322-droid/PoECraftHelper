"""Окно настроек в стиле «меню слева, раздел справа, Сохранить/Отмена внизу».

Все изменения копятся в черновике и применяются только по «Сохранить».
"""

from __future__ import annotations

import copy
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import ttk

from poecraft import hotkeys as hkmod
from poecraft import i18n
from poecraft.data import APP_DIR
from poecraft.updater import APP_VERSION

BG = "#0f0d0a"        # содержимое
SIDE = "#16130f"      # меню слева
TITLE = "#1f1a14"     # заголовок
FIELD = "#1f1a14"     # поля
BANNER = "#2a231a"    # подсказка сверху
LINE = "#3a3127"
FG, MUTED, GOLD, GOOD, WARN = "#d9d0c1", "#8a7f70", "#e3b55b", "#7ec27a", "#e07a5f"
FONT = "Segoe UI"

SECTIONS = [
    ("hotkeys", "Горячие клавиши"),
    ("overlay", "Оверлей"),
    ("workshop", "Мастерская"),
    None,
    ("language", "Язык"),
    ("prices", "Цены"),
    ("data", "Данные игры"),
    None,
    ("updates", "Обновления"),
    ("about", "О программе"),
]
HOTKEY_ACTIONS = [
    ("overlay", "Показать / спрятать оверлей"),
    ("workshop", "Показать / спрятать мастерскую"),
    ("settings", "Открыть настройки"),
]


def frameless(win: tk.Toplevel):
    """Убираем системную рамку Windows, но оставляем окно «обычным» (работает клавиатура)."""
    import sys
    if sys.platform != "win32":
        return
    try:
        import ctypes
        u = ctypes.windll.user32
        hwnd = int(win.wm_frame(), 16)
        style = u.GetWindowLongW(hwnd, -16)
        if not style & 0x00C00000:
            return
        u.SetWindowLongW(hwnd, -16, (style & ~(0x00C00000 | 0x00040000 | 0x00010000)) | 0x00020000 | 0x00080000)
        u.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027)
    except Exception:
        pass


class SettingsWindow(tk.Toplevel):
    def __init__(self, app, start: str = "hotkeys"):
        super().__init__(app.root)
        self.app = app
        self.draft = copy.deepcopy(app.settings)
        self.draft.setdefault("hotkeys", {})
        self.title("Настройки — PoE Craft Helper")
        self.configure(bg=SIDE, highlightthickness=1, highlightbackground=LINE)
        self.attributes("-topmost", True)
        self.geometry(app.settings.get("settings_geo", "820x600+300+140"))
        self.minsize(720, 520)
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.bind("<Map>", lambda e: e.widget is self and self.after(10, lambda: frameless(self)), add="+")
        self.after(300, lambda: frameless(self))
        self._capture_key = None
        self._style()
        self._build()
        self.show(start)
        i18n.translate_tree(self)
        self.lift()
        self.focus_force()

    # ------------------------------------------------------------ каркас
    def _style(self):
        st = ttk.Style(self)
        st.configure("S.TCombobox", fieldbackground=FIELD, background=FIELD, foreground=FG, arrowcolor=GOLD,
                     bordercolor=LINE, lightcolor=FIELD, darkcolor=FIELD)
        st.map("S.TCombobox", fieldbackground=[("readonly", FIELD)], foreground=[("readonly", FG)])
        st.configure("S.Horizontal.TScale", background=BG, troughcolor=FIELD, bordercolor=LINE,
                     lightcolor=GOLD, darkcolor=GOLD)

    def _build(self):
        # заголовок (за него таскаем окно)
        head = tk.Frame(self, bg=TITLE, height=30)
        head.pack(fill="x")
        title = tk.Label(head, text="НАСТРОЙКИ — PoE Craft Helper", bg=TITLE, fg=MUTED, font=(FONT, 10))
        title.pack(side="left", padx=10, pady=5)
        close = tk.Label(head, text="✕", bg=TITLE, fg=MUTED, font=(FONT, 11), cursor="hand2", padx=10)
        close.pack(side="right")
        close.bind("<Button-1>", lambda e: self.cancel())
        close.bind("<Enter>", lambda e: close.configure(fg=WARN))
        close.bind("<Leave>", lambda e: close.configure(fg=MUTED))
        for w in (head, title):
            w.bind("<ButtonPress-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)

        body = tk.Frame(self, bg=SIDE)
        body.pack(fill="both", expand=True)

        # меню слева
        side = tk.Frame(body, bg=SIDE, width=190)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        tk.Frame(side, bg=SIDE, height=8).pack()
        self.menu_items = {}
        for sec in SECTIONS:
            if sec is None:
                tk.Frame(side, bg=LINE, height=1).pack(fill="x", padx=12, pady=6)
                continue
            key, label = sec
            it = tk.Label(side, text=label.upper(), bg=SIDE, fg=MUTED, font=(FONT, 10), anchor="w",
                          padx=16, pady=7, cursor="hand2")
            it.pack(fill="x", padx=6, pady=1)
            it.bind("<Button-1>", lambda e, k=key: self.show(k))
            it.bind("<Enter>", lambda e, w=it, k=key: k != self.current and w.configure(fg=FG))
            it.bind("<Leave>", lambda e, w=it, k=key: k != self.current and w.configure(fg=MUTED))
            self.menu_items[key] = it
        quit_btn = tk.Label(side, text="ВЫХОД", bg=SIDE, fg=MUTED, font=(FONT, 10), pady=6, cursor="hand2",
                            highlightthickness=1, highlightbackground=LINE)
        quit_btn.pack(fill="x", padx=14, pady=(18, 0))
        quit_btn.bind("<Button-1>", lambda e: self.quit_app())
        quit_btn.bind("<Enter>", lambda e: quit_btn.configure(fg=WARN))
        quit_btn.bind("<Leave>", lambda e: quit_btn.configure(fg=MUTED))
        tk.Label(side, text=f"версия {APP_VERSION}", bg=SIDE, fg="#5a5248", font=(FONT, 8)).pack(side="bottom", pady=8)

        # содержимое справа
        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True)
        self.content = tk.Frame(right, bg=BG)
        self.content.pack(fill="both", expand=True, padx=16, pady=12)

        foot = tk.Frame(right, bg=BG)
        foot.pack(fill="x", side="bottom")
        tk.Frame(right, bg=LINE, height=1).pack(fill="x", side="bottom")
        self.foot_status = tk.Label(foot, text="", bg=BG, fg=MUTED, font=(FONT, 9), anchor="w")
        self.foot_status.pack(side="left", padx=16)
        for text, cmd in (("ОТМЕНА", self.cancel), ("СОХРАНИТЬ", self.save)):
            b = tk.Label(foot, text=text, bg=BG, fg=GOLD if text == "СОХРАНИТЬ" else FG, font=(FONT, 10, "bold"),
                         padx=14, pady=8, cursor="hand2")
            b.pack(side="right", padx=4)
            b.bind("<Button-1>", lambda e, c=cmd: c())
        self.pages = {}

    def _drag_start(self, e):
        self._dx, self._dy = e.x_root - self.winfo_x(), e.y_root - self.winfo_y()

    def _drag_move(self, e):
        self.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    def show(self, key: str):
        self.current = key
        for k, it in self.menu_items.items():
            on = k == key
            it.configure(bg=TITLE if on else SIDE, fg=GOLD if on else MUTED)
        for w in self.content.winfo_children():
            w.destroy()
        getattr(self, f"_page_{key}")(self.content)
        i18n.translate_tree(self.content)

    # ------------------------------------------------------------ элементы
    def _banner(self, parent, text):
        b = tk.Label(parent, text="ⓘ  " + text, bg=BANNER, fg=FG, font=(FONT, 10), anchor="w", padx=10, pady=5)
        b.pack(fill="x", pady=(0, 12))

    def _h(self, parent, text):
        tk.Label(parent, text=text.upper(), bg=BG, fg=FG, font=(FONT, 10, "bold"), anchor="w").pack(fill="x", pady=(10, 4))

    def _row(self, parent, label, sub=False):
        r = tk.Frame(parent, bg=BG)
        r.pack(fill="x", pady=3)
        tk.Label(r, text=label, bg=BG, fg=MUTED if sub else FG, font=(FONT, 10), anchor="w",
                 width=34, padx=16 if sub else 0).pack(side="left")
        return r

    def _check(self, parent, label, key, default=False):
        v = tk.BooleanVar(value=self.draft.get(key, default))
        r = tk.Frame(parent, bg=BG)
        r.pack(fill="x", pady=3)
        cb = tk.Checkbutton(r, text=label, variable=v, bg=BG, fg=FG, selectcolor=FIELD, activebackground=BG,
                            activeforeground=GOLD, font=(FONT, 10), highlightthickness=0, bd=0,
                            command=lambda: self.draft.__setitem__(key, v.get()))
        cb.pack(side="left")
        return v

    def _button(self, parent, text, cmd):
        b = tk.Label(parent, text=text, bg="#3a2c17", fg=GOLD, font=(FONT, 10), padx=12, pady=4, cursor="hand2",
                     highlightthickness=1, highlightbackground="#6b5124")
        b.bind("<Button-1>", lambda e: cmd())
        return b

    def _combo(self, parent, values, current, on_change, width=24):
        v = tk.StringVar(value=current)
        cb = ttk.Combobox(parent, textvariable=v, state="readonly", values=values, style="S.TCombobox",
                          width=width, font=(FONT, 10))
        try:
            from mainwin import popdown_on_top
            popdown_on_top(cb)
        except Exception:
            pass
        cb.bind("<<ComboboxSelected>>", lambda e: on_change(v.get()))
        return cb

    def _note(self, parent, text="", fg=MUTED):
        l = tk.Label(parent, text=text, bg=BG, fg=fg, font=(FONT, 9), anchor="w", justify="left", wraplength=560)
        l.pack(fill="x", pady=(6, 0))
        return l

    # ------------------------------------------------------------ горячие клавиши
    def _page_hotkeys(self, p):
        self._banner(p, "Кликни по полю и нажми сочетание. Backspace — сбросить.")
        cur = dict(hkmod.DEFAULT_HOTKEYS)
        cur.update(self.draft.get("hotkeys", {}))
        self.hk_fields = {}
        for key, label in HOTKEY_ACTIONS:
            r = self._row(p, label)
            f = tk.Label(r, text="", bg=FIELD, fg=FG, font=(FONT, 10), width=22, pady=4, cursor="hand2",
                         highlightthickness=1, highlightbackground=LINE)
            f.pack(side="left")
            f.bind("<Button-1>", lambda e, k=key: self._start_capture(k))
            self.hk_fields[key] = f
            self._paint_hotkey(key, cur.get(key, ""))
        self.hk_note = self._note(p, "" if hkmod.HotkeyManager(None).supported else
                                  "Глобальные горячие клавиши работают только в Windows.")
        self._h(p, "Буфер обмена")
        self._note(p, "Предмет в игре копируется сочетанием Ctrl+Alt+C — его задаёт сама игра. "
                      "Программа ловит копирование автоматически.")

    def _paint_hotkey(self, key, combo):
        f = self.hk_fields[key]
        if self._capture_key == key:
            f.configure(text="нажми сочетание…", fg=GOLD, highlightbackground=GOLD)
        elif combo:
            f.configure(text=" + ".join(combo.split("+")), fg=FG, highlightbackground=LINE)
        else:
            f.configure(text="Не задано", fg=WARN, highlightbackground=LINE)

    def _start_capture(self, key):
        prev = self._capture_key
        self._capture_key = key
        if prev and prev != key:
            self._paint_hotkey(prev, self._hk(prev))
        self._paint_hotkey(key, self._hk(key))
        self.focus_force()
        self.bind("<KeyPress>", self._on_key)

    def _hk(self, key):
        cur = dict(hkmod.DEFAULT_HOTKEYS)
        cur.update(self.draft.get("hotkeys", {}))
        return cur.get(key, "")

    def _on_key(self, e):
        key = self._capture_key
        if not key:
            return
        if e.keysym == "BackSpace":
            combo = ""
        elif e.keysym == "Escape":
            combo = self._hk(key)
        else:
            combo = hkmod.from_tk_event(e)
            if combo is None:
                return "break"          # нажат только модификатор — ждём основную клавишу
            if not any(m in combo for m in ("Ctrl", "Alt", "Shift")) and not combo.split("+")[-1].startswith("F"):
                self.hk_note.configure(text="Добавь Ctrl, Alt или Shift — иначе клавиша будет мешать в игре.", fg=WARN)
                return "break"
            dup = [k for k, _ in HOTKEY_ACTIONS if k != key and self._hk(k) == combo]
            if dup:
                self.hk_note.configure(text=f"{combo} уже назначено на другое действие.", fg=WARN)
                return "break"
        self.draft["hotkeys"][key] = combo
        self._capture_key = None
        self.unbind("<KeyPress>")
        self._paint_hotkey(key, combo)
        self.hk_note.configure(text="Не забудь «Сохранить».", fg=MUTED)
        return "break"

    # ------------------------------------------------------------ оверлей / мастерская
    def _alpha(self, p, key, default, live):
        r = self._row(p, "Непрозрачность")
        v = tk.DoubleVar(value=self.draft.get(key, default))
        lbl = tk.Label(r, text=f"{v.get():.0%}", bg=BG, fg=GOLD, font=(FONT, 10), width=5)

        def changed(x):
            val = round(float(x), 2)
            self.draft[key] = val
            lbl.configure(text=f"{val:.0%}")
            live(val)
        s = ttk.Scale(r, from_=0.4, to=1.0, variable=v, command=changed, length=240, style="S.Horizontal.TScale")
        s.pack(side="left")
        lbl.pack(side="left", padx=8)

    def _page_overlay(self, p):
        self._banner(p, "Маленькая панель с подсказками поверх игры.")
        self._h(p, "Вид")
        self._alpha(p, "alpha", 0.92, lambda a: self.app.root.attributes("-alpha", a))
        self._h(p, "Поведение")
        self._check(p, "Показывать оверлей, когда скопирован предмет (даже если он спрятан)", "auto_show", True)
        self._check(p, "Держать поверх всех окон", "keep_on_top", True)
        r = tk.Frame(p, bg=BG)
        r.pack(fill="x", pady=(10, 0))
        self._button(r, "Вернуть оверлей в угол экрана", self._reset_overlay_pos).pack(side="left")
        self._note(p, "Если оверлей не виден поверх игры — переключи игру в режим «Оконный без рамки».")

    def _reset_overlay_pos(self):
        self.draft["pos"] = (60, 120)
        self.app.root.geometry("+60+120")
        self.app.root.deiconify()

    def _page_workshop(self, p):
        self._banner(p, "Большое окно: пул модов, калькулятор, эмулятор, сокеты.")
        self._h(p, "Вид")

        def live(a):
            w = getattr(self.app, "main_win", None)
            if w is not None and w.winfo_exists():
                w.attributes("-alpha", a)
        self._alpha(p, "main_alpha", 0.95, live)
        self._h(p, "Расчёты")
        r = self._row(p, "База по умолчанию: ilvl")
        v = tk.StringVar(value=str(self.draft.get("main_ilvl", 84)))
        e = tk.Entry(r, textvariable=v, width=6, bg=FIELD, fg=FG, insertbackground=FG, relief="flat",
                     highlightthickness=1, highlightbackground=LINE, font=(FONT, 10))
        e.pack(side="left")
        v.trace_add("write", lambda *a: v.get().isdigit() and self.draft.__setitem__("main_ilvl", int(v.get())))
        r = tk.Frame(p, bg=BG)
        r.pack(fill="x", pady=(10, 0))
        self._button(r, "Сбросить размер и положение окна", self._reset_workshop).pack(side="left")

    def _reset_workshop(self):
        self.draft["main_geo"] = "1180x760+120+60"
        w = getattr(self.app, "main_win", None)
        if w is not None and w.winfo_exists():
            w.geometry("1180x760+120+60")

    # ------------------------------------------------------------ язык
    def _page_language(self, p):
        self._banner(p, "Язык интерфейса меняется после перезапуска программы.")
        r = self._row(p, "Интерфейс")
        names = {"ru": "Русский", "en": "English"}
        self._combo(r, list(names.values()), names[self.draft.get("ui_lang", "ru")],
                    lambda v: self.draft.__setitem__("ui_lang", "en" if v == "English" else "ru"), 16).pack(side="left")
        r = self._row(p, "Клиент игры (текст Ctrl+Alt+C)")
        g = {"auto": "Авто (по тексту предмета)", "ru": "Русский", "en": "English"}
        inv = {v: k for k, v in g.items()}
        self._combo(r, list(g.values()), g[self.draft.get("game_lang", "auto")],
                    lambda v: self.draft.__setitem__("game_lang", inv[v]), 26).pack(side="left")
        has_ru = getattr(self.app.data, "has_russian", False) if self.app.data else False
        self._note(p, "Русские данные для клиента: " + ("загружены ✓" if has_ru else
                   "не загружены — раздел «Данные игры» → «Обновить данные модов»."), GOOD if has_ru else WARN)

    # ------------------------------------------------------------ цены
    def _prices(self):
        w = getattr(self.app, "main_win", None)
        if w is not None and w.winfo_exists():
            return w.prices
        if not hasattr(self, "_own_prices"):
            from poecraft.prices import Prices
            self._own_prices = Prices()
        return self._own_prices

    def _page_prices(self, p):
        self._banner(p, "Цены валюты, эссенций, фоссилов и lifeforce берутся с poe.ninja.")
        pr = self._prices()
        when = time.strftime("%d.%m.%Y %H:%M", time.localtime(pr.updated)) if pr.updated else "—"
        self._h(p, "Сейчас")
        info = tk.Label(p, text=f"Лига: {pr.league}\n1 Divine = {pr.divine:.0f} Chaos\nИсточник: {pr.source}, обновлено {when}",
                        bg=BG, fg=FG, font=(FONT, 10), anchor="w", justify="left")
        info.pack(fill="x")
        r = tk.Frame(p, bg=BG)
        r.pack(fill="x", pady=(12, 0))
        st = self._note(p)
        self._button(r, "Обновить цены сейчас", lambda: self._bg(
            lambda: pr.refresh(force=True), lambda ok, err: (
                st.configure(text=f"Цены обновлены: лига {pr.league}." if ok and not err else
                             f"Не удалось обновить цены. {err or ''}", fg=GOOD if ok and not err else WARN),
                self.show("prices") if ok and not err else None))).pack(side="left")
        self._note(p, "Цены обновляются автоматически раз в час. После старта новой лиги программа "
                      "сама переключится на неё.")

    # ------------------------------------------------------------ данные
    def _page_data(self, p):
        d = self.app.data
        self._banner(p, "Данные модов из файлов игры (RePoE). Обновляй после каждого патча.")
        self._h(p, "Версия")
        tk.Label(p, text=f"Данные RePoE: {d.version if d else '…'}"
                         f"{' + русские' if d and d.has_russian else ''}\nПапка: {APP_DIR / 'data'}",
                 bg=BG, fg=FG, font=(FONT, 10), anchor="w", justify="left").pack(fill="x")
        self._h(p, "Загрузка")
        ru = self._check(p, "Скачивать русские данные (для русского клиента)", "download_ru", True)
        r = tk.Frame(p, bg=BG)
        r.pack(fill="x", pady=(8, 0))
        st = self._note(p)

        def run():
            from poecraft.data import download
            return download(APP_DIR / "data", verbose=False, russian=ru.get())
        self._button(r, "Обновить данные модов", lambda: (
            st.configure(text="Скачиваю (≈50 МБ)… окно можно не закрывать.", fg=MUTED),
            self._bg(run, lambda v, err: st.configure(
                text=f"Готово: {v}. Перезапусти программу, чтобы данные применились." if not err else
                f"Ошибка загрузки: {err}", fg=GOOD if not err else WARN)))).pack(side="left")

    # ------------------------------------------------------------ обновления
    def _page_updates(self, p):
        self._banner(p, "Новые версии программы публикуются как релизы на GitHub.")
        r = self._row(p, "Репозиторий релизов (владелец/название)")
        v = tk.StringVar(value=self.draft.get("update_repo", ""))
        tk.Entry(r, textvariable=v, width=30, bg=FIELD, fg=FG, insertbackground=FG, relief="flat",
                 highlightthickness=1, highlightbackground=LINE, font=(FONT, 10)).pack(side="left")
        v.trace_add("write", lambda *a: self.draft.__setitem__("update_repo", v.get().strip()))
        self._check(p, "Проверять обновления при запуске", "check_updates", True)
        r = tk.Frame(p, bg=BG)
        r.pack(fill="x", pady=(10, 0))
        st = self._note(p, f"Установлена версия {APP_VERSION}.")
        self._update_url = None
        st.configure(cursor="hand2")
        st.bind("<Button-1>", lambda e: self._update_url and webbrowser.open(self._update_url))

        def done(res, err):
            if err or res.get("error"):
                st.configure(text=str(err or res["error"]), fg=WARN)
            elif res["newer"]:
                self._update_url = res["url"]
                st.configure(text=f"Доступна версия {res['latest']} (у тебя {APP_VERSION}). Кликни, чтобы скачать.", fg=GOOD)
            else:
                st.configure(text=f"У тебя последняя версия ({APP_VERSION}).", fg=GOOD)
        from poecraft import updater
        self._button(r, "Проверить обновления", lambda: (st.configure(text="Проверяю…", fg=MUTED),
                     self._bg(lambda: updater.check(v.get()), done))).pack(side="left")

    # ------------------------------------------------------------ о программе
    def _page_about(self, p):
        tk.Label(p, text="⚒ PoE Craft Helper", bg=BG, fg=GOLD, font=(FONT, 16, "bold"), anchor="w").pack(fill="x", pady=(4, 0))
        tk.Label(p, text=f"версия {APP_VERSION}", bg=BG, fg=MUTED, font=(FONT, 10), anchor="w").pack(fill="x")
        self._note(p, "Помощник крафта для Path of Exile 1: подсказки по предмету из буфера обмена, пул модов, "
                      "калькулятор, эссенции и фоссилы, эмулятор, влияния, Eldritch, Harvest, кластеры, сокеты.", FG)
        self._h(p, "Безопасность")
        self._note(p, "Программа ничего не нажимает в игре и не читает её память — только буфер обмена. "
                      "Это соответствует правилам GGG «одно действие на одно нажатие».")
        self._h(p, "Источники")
        for text, url in (("Данные модов — RePoE", "https://repoe-fork.github.io"),
                          ("Цены — poe.ninja", "https://poe.ninja"),
                          ("Формула сокетов — калькулятор Siveran", "https://siveran.github.io/calc.html")):
            l = tk.Label(p, text="↗ " + text, bg=BG, fg=GOLD, font=(FONT, 10), anchor="w", cursor="hand2")
            l.pack(fill="x", pady=1)
            l.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))
        self._note(p, "Path of Exile принадлежит Grinding Gear Games. Программа не связана с GGG и не одобрена ими.")

    # ------------------------------------------------------------ сохранить / отмена
    def _bg(self, fn, done):
        def run():
            try:
                res, err = fn(), None
            except Exception as e:
                res, err = None, e
            try:
                self.after(0, lambda: done(res, err))
            except tk.TclError:
                pass
        threading.Thread(target=run, daemon=True).start()

    def save(self):
        old_lang = self.app.settings.get("ui_lang", "ru")
        self.draft["settings_geo"] = self.geometry()
        self.app.settings.clear()
        self.app.settings.update(self.draft)
        self.app.save_settings(self.app.settings)
        errors = self.app.apply_hotkeys()
        self.app.root.attributes("-alpha", self.app.settings.get("alpha", 0.92))
        if errors:
            self.foot_status.configure(text="Сохранено, но: " + "; ".join(errors), fg=WARN)
            return
        if self.app.settings.get("ui_lang", "ru") != old_lang:
            self.foot_status.configure(text="Сохранено. Язык сменится после перезапуска.", fg=GOLD)
            return
        self.destroy()

    def cancel(self):
        # откатываем «живые» изменения прозрачности
        self.app.root.attributes("-alpha", self.app.settings.get("alpha", 0.92))
        w = getattr(self.app, "main_win", None)
        if w is not None and w.winfo_exists():
            w.attributes("-alpha", self.app.settings.get("main_alpha", 0.95))
        self.destroy()

    def quit_app(self):
        self.destroy()
        self.app.quit()
