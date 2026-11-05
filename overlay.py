"""Оверлей поверх игры: полупрозрачное окно, всегда сверху.

Скопируй предмет в игре (Ctrl+Alt+C) — совет появится в окне.
Игра должна быть в режиме «Оконный без рамки» (Windowed Fullscreen),
иначе Windows не покажет поверх неё другие окна.
"""

from __future__ import annotations

import json
import os
import queue
import sys
import threading
import time
import tkinter as tk
import traceback
from tkinter import ttk

from poecraft.advisor import Advisor, Goal
from poecraft.data import APP_DIR, GameData, download
from poecraft.parser import ParseError, looks_like_item, parse_item
from poecraft import recipes
from poecraft import i18n
from poecraft.hotkeys import DEFAULT_HOTKEYS, HotkeyManager

# ---------------------------------------------------------------- стиль
BG = "#14110d"
BG2 = "#1f1a14"
FG = "#d9d0c1"
MUTED = "#8a7f70"
GOLD = "#e3b55b"
GOOD = "#7ec27a"
BAD = "#8a7f70"
WARN = "#e07a5f"
FONT = "Segoe UI"
SETTINGS = APP_DIR / "settings.json"
GOALS_DIR = APP_DIR / "goals"
WIDTH = 390
CARD = "#1a1611"
TRACK = "#2a241c"
LINE = "#3a3127"
GOLD_LINE = "#6b5a22"
DIM = "#5a5248"
# цвета заголовка по редкости — как в игре, только приглушённые
RARITY = {"Normal": ("#1f1d1a", "#c8c8c8"), "Magic": ("#161a2a", "#8888ff"),
          "Rare": ("#2a2410", "#f0dc78"), "Unique": ("#2a1a0e", "#c87c3c")}


def load_settings() -> dict:
    try:
        return json.loads(SETTINGS.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_settings(d: dict):
    try:
        SETTINGS.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


class Overlay:
    def __init__(self):
        self.settings = load_settings()
        self.save_settings = save_settings
        i18n.set_lang(self.settings.get("ui_lang", "ru"))
        self.root = tk.Tk()
        self.root.title("PoE Craft Helper")
        self.root.overrideredirect(True)          # без рамки
        self.root.attributes("-topmost", True)    # поверх всех окон
        self.root.attributes("-alpha", self.settings.get("alpha", 0.92))
        self.root.configure(bg=BG, highlightthickness=1, highlightbackground="#3a3127")
        x, y = self.settings.get("pos", (60, 120))
        self.root.geometry(f"{WIDTH}x10+{x}+{y}")

        self.collapsed = False
        self.results: queue.Queue = queue.Queue()
        self.last_clip = None
        self.data = None
        self.advisor = None
        self.goals: list[tuple[str, Goal]] = []

        from poecraft import icons
        icons.store(self.root)            # иконки валюты: из data/icons или скачать в фоне
        self._build_ui()
        i18n.translate_tree(self.root)
        self.hk = HotkeyManager(lambda action: self.root.after(0, lambda: self._on_hotkey(action)))
        self.apply_hotkeys()
        self._load_goals()
        self.set_status("Загружаю данные модов…")
        threading.Thread(target=self._init_data, daemon=True).start()

        self.goals_dir = GOALS_DIR
        self.hub = None
        if self.settings.get("hub_on_start", True):
            self.root.withdraw()          # оверлей появится сам, когда скопируешь предмет
            self.root.after(50, self.open_hub)

        self.root.after(300, self._poll_clipboard)
        self.root.after(100, self._poll_results)
        self.root.after(1000, self._keep_on_top)
        self.root.after(500, self._auto_hide)

    # ------------------------------------------------------------ UI
    def _build_ui(self):
        r = self.root
        style = ttk.Style(r)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("G.TCombobox", fieldbackground=BG2, background=BG2, foreground=FG,
                        arrowcolor=GOLD, bordercolor="#3a3127", lightcolor=BG2, darkcolor=BG2)
        style.map("G.TCombobox",
                  fieldbackground=[("readonly", BG2)], foreground=[("readonly", FG)],
                  selectbackground=[("readonly", BG2)], selectforeground=[("readonly", GOLD)])
        r.option_add("*TCombobox*Listbox.background", BG2)
        r.option_add("*TCombobox*Listbox.foreground", FG)
        r.option_add("*TCombobox*Listbox.selectBackground", "#3a3127")

        # Заголовок карточки: цвет по редкости предмета, за него таскаем окно
        self.head = tk.Frame(r, bg=BG2)
        self.head.pack(fill="x")
        hl = tk.Frame(self.head, bg=BG2)
        hl.pack(side="left", fill="x", expand=True, padx=10, pady=(5, 5))
        self.title_lbl = tk.Label(hl, text="⚒ PoE Craft Helper", bg=BG2, fg=GOLD, font=(FONT, 11, "bold"),
                                  anchor="w")
        self.title_lbl.pack(fill="x")
        self.sub_lbl = tk.Label(hl, text="скопируй предмет в игре", bg=BG2, fg=MUTED, font=(FONT, 8), anchor="w")
        self.sub_lbl.pack(fill="x")
        self._drag_widgets = [self.head, hl, self.title_lbl, self.sub_lbl]
        for w in self._drag_widgets:
            w.bind("<ButtonPress-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)
            w.bind("<ButtonRelease-1>", self._drag_end)
        self.head_btns = []
        for text, cmd, fg in (("✕", self.hide_overlay, WARN), ("—", self.toggle_collapse, FG),
                              ("◐", self.cycle_alpha, FG), ("⌂", self.open_hub, GOLD)):
            b = self._btn(self.head, text, cmd, fg)
            b.pack(side="right", padx=(0, 6 if text == "✕" else 0))
            self.head_btns.append(b)
            if text == "—":
                self.collapse_btn = b
        self.rarity_line = tk.Frame(r, bg=LINE, height=1)
        self.rarity_line.pack(fill="x")

        # Тело
        self.body = tk.Frame(r, bg=BG)
        self.body.pack(fill="both", expand=True)

        row = tk.Frame(self.body, bg=BG)
        row.pack(fill="x", padx=10, pady=(8, 2))
        tk.Label(row, text="Цель:", bg=BG, fg=MUTED, font=(FONT, 9)).pack(side="left")
        self.goal_var = tk.StringVar()
        self.goal_box = ttk.Combobox(row, textvariable=self.goal_var, state="readonly",
                                     style="G.TCombobox", font=(FONT, 9), width=34)
        from mainwin import popdown_on_top
        popdown_on_top(self.goal_box)
        self.goal_box.pack(side="left", padx=(6, 0), fill="x", expand=True)
        self.goal_box.bind("<<ComboboxSelected>>", self._goal_changed)

        self.mods_frame = tk.Frame(self.body, bg=BG)
        self.mods_frame.pack(fill="x", padx=10, pady=(4, 0))

        # Карточка «следующий шаг»
        self.step_card = tk.Frame(self.body, bg=CARD, highlightthickness=1, highlightbackground=GOLD_LINE)
        inner = tk.Frame(self.step_card, bg=CARD)
        inner.pack(fill="x", padx=10, pady=8)
        self.step_cap = tk.Label(inner, text="СЛЕДУЮЩИЙ ШАГ", bg=CARD, fg=MUTED, font=(FONT, 7, "bold"), anchor="w")
        self.step_cap.pack(fill="x")
        srow = tk.Frame(inner, bg=CARD)
        srow.pack(fill="x")
        self.step_icon = tk.Label(srow, bg=CARD)
        self.step_lbl = tk.Label(srow, text="", bg=CARD, fg=GOLD, font=(FONT, 14, "bold"),
                                 anchor="w", justify="left", wraplength=WIDTH - 90)
        self.step_lbl.pack(side="left", fill="x", expand=True)
        cr = tk.Frame(inner, bg=CARD)
        cr.pack(fill="x", pady=(4, 0))
        self.chance_lbl = tk.Label(cr, text="", bg=CARD, fg=FG, font=(FONT, 10), anchor="w")
        self.chance_lbl.pack(side="left")
        self.tries_lbl = tk.Label(cr, text="", bg=CARD, fg=MUTED, font=(FONT, 9), anchor="e")
        self.tries_lbl.pack(side="right")
        self.bar = tk.Canvas(inner, height=5, bg=TRACK, highlightthickness=0, bd=0)
        self.bar.pack(fill="x", pady=(4, 0))
        self.bar.bind("<Configure>", lambda e: self._draw_bar())
        self.why_lbl = tk.Label(inner, text="", bg=CARD, fg=FG, font=(FONT, 9),
                                anchor="w", justify="left", wraplength=WIDTH - 44)
        self.why_lbl.pack(fill="x", pady=(6, 0))
        self.notes_lbl = tk.Label(inner, text="", bg=CARD, fg=MUTED, font=(FONT, 9),
                                  anchor="w", justify="left", wraplength=WIDTH - 44)
        self.notes_lbl.pack(fill="x", pady=(4, 0))

        self.status_lbl = tk.Label(self.body, text="", bg=BG, fg=MUTED, font=(FONT, 8),
                                   anchor="w", justify="left", wraplength=WIDTH - 20)
        self.status_lbl.pack(fill="x", padx=10, pady=(6, 8), side="bottom")
        self.body.bind("<Enter>", lambda e: self._hover(True))
        self.root.bind("<Enter>", lambda e: self._hover(True), add="+")
        self.root.bind("<Leave>", lambda e: self._hover(False), add="+")
        self._resize()

    def _btn(self, parent, text, cmd, fg=FG):
        size = 10 if len(text) == 1 else 8
        b = tk.Label(parent, text=text, bg=parent["bg"], fg=fg, font=(FONT, size), cursor="hand2", padx=5)
        b.bind("<Button-1>", lambda e: cmd())
        b.bind("<Enter>", lambda e: b.configure(fg=GOLD))
        b.bind("<Leave>", lambda e: b.configure(fg=fg))
        return b

    def _resize(self):
        self.root.update_idletasks()
        h = self.root.winfo_reqheight()
        self.root.geometry(f"{WIDTH}x{h}")

    # ------------------------------------------------------------ перетаскивание
    def _drag_start(self, e):
        self._dx, self._dy = e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y()

    def _drag_move(self, e):
        self.root.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    def _drag_end(self, e):
        self.settings["pos"] = (self.root.winfo_x(), self.root.winfo_y())
        save_settings(self.settings)

    # ------------------------------------------------------------ кнопки
    def toggle_collapse(self):
        self.collapsed = not self.collapsed
        if self.collapsed:
            self.body.pack_forget()
            self.collapse_btn.configure(text="▢")
        else:
            self.body.pack(fill="both", expand=True)
            self.collapse_btn.configure(text="—")
        self._resize()
        self.root.after(30, self._draw_bar)

    def cycle_alpha(self):
        levels = [0.92, 0.75, 0.55, 1.0]
        cur = self.settings.get("alpha", 0.92)
        nxt = levels[(levels.index(cur) + 1) % len(levels)] if cur in levels else 0.92
        self.settings["alpha"] = nxt
        self.root.attributes("-alpha", nxt)
        save_settings(self.settings)

    def open_main(self):
        """Главное окно поверх игры: пул модов и калькулятор (без браузера)."""
        if not self.data:
            self.set_status("Данные ещё загружаются, подожди пару секунд…")
            return
        try:
            win = getattr(self, "main_win", None)
            if win is not None and win.winfo_exists():
                if win.state() == "withdrawn":
                    win.show()
                else:
                    win.hide()
                return
            from mainwin import MainWindow
            self.main_win = MainWindow(self.root, self.data, self.settings, save_settings,
                                       on_goal_saved=self._goal_saved_from_main)
            self.main_win.app = self
        except Exception as e:
            self.set_status(f"Не удалось открыть главное окно: {e}")

    def _goal_saved_from_main(self, filename):
        self._load_goals()
        names = [f for f, _ in self.goals]
        if filename in names:
            self.goal_box.current(names.index(filename))
            self._goal_changed()

    # ------------------------------------------------------------ хаб
    def open_hub(self):
        try:
            if self.hub is not None and self.hub.winfo_exists():
                self.hub.show()
                return
            from hub import HubWindow
            self.hub = HubWindow(self)
        except Exception as e:
            traceback.print_exc()
            self.root.deiconify()
            self.set_status(f"Не удалось открыть хаб: {e}")

    def toggle_hub(self):
        if self.hub is not None and self.hub.winfo_exists() and self.hub.state() != "withdrawn":
            self.hub.hide()
        else:
            self.open_hub()

    def refresh_hub(self):
        if self.hub is not None and self.hub.winfo_exists() and self.hub.state() != "withdrawn":
            self.hub.refresh()

    def hide_overlay(self):
        self.root.withdraw()
        if self.hub is None or not self.hub.winfo_exists():
            self.open_hub()

    def set_goal(self, filename: str):
        names = [f for f, _ in self.goals]
        if filename in names:
            self.goal_box.current(names.index(filename))
            self._goal_changed()

    def reload_goals(self):
        self._load_goals()
        self.refresh_hub()

    def reopen_item(self, text: str):
        self.root.deiconify()
        self.root.attributes("-topmost", True)
        self.last_text = text
        self._analyze(text)

    def _remember_item(self, item, mods):
        g = self.current_goal()
        if not g or not self.last_text:
            return
        done = sum(1 for m in mods if m[3])
        entry = {"name": item.name or item.base_name, "goal": g.name, "done": min(done, len(g.wanted)),
                 "total": len(g.wanted), "text": self.last_text}
        rec = [r for r in self.settings.get("recent", []) if r.get("text") != self.last_text]
        self.settings["recent"] = [entry] + rec[:7]
        save_settings(self.settings)
        self.refresh_hub()

    def open_goals(self):
        GOALS_DIR.mkdir(exist_ok=True)
        try:
            os.startfile(GOALS_DIR)  # Windows
        except Exception:
            self.set_status(f"Папка целей: {GOALS_DIR}")

    # ------------------------------------------------------------ горячие клавиши
    def hotkeys(self) -> dict:
        hk = dict(DEFAULT_HOTKEYS)
        hk.update(self.settings.get("hotkeys", {}))
        return hk

    def apply_hotkeys(self) -> list[str]:
        """(Пере)регистрирует глобальные горячие клавиши. Возвращает список ошибок."""
        errors = self.hk.start({k: v for k, v in self.hotkeys().items() if v})
        if errors:
            self.set_status("Горячие клавиши: " + "; ".join(errors))
        return errors

    def _on_hotkey(self, action: str):
        if action == "overlay":
            if self.root.state() == "withdrawn":
                self.root.deiconify()
                self.root.attributes("-topmost", True)
            else:
                self.root.withdraw()
        elif action == "workshop":
            self.open_main()
        elif action == "settings":
            self.open_settings()
        elif action == "hub":
            self.toggle_hub()

    def open_settings(self, section: str = "hotkeys"):
        from settings_win import SettingsWindow
        win = getattr(self, "settings_win", None)
        if win is not None and win.winfo_exists():
            win.deiconify()
            win.lift()
            win.show(section)
            return
        self.settings_win = SettingsWindow(self, section)

    def quit(self):
        try:
            self.hk.stop()
        except Exception:
            pass
        self.settings["pos"] = (self.root.winfo_x(), self.root.winfo_y())
        save_settings(self.settings)
        self.root.destroy()

    def _keep_on_top(self):
        # некоторые игры перехватывают topmost — периодически возвращаем
        try:
            from mainwin import popdown_open
            if not self.settings.get("keep_on_top", True):
                self.root.attributes("-topmost", False)
                self.root.after(2000, self._keep_on_top)
                return
            if popdown_open():
                self.root.after(2000, self._keep_on_top)
                return
            editors = [w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel)
                       and w.winfo_viewable() and w is not self.hub]
            if editors:
                for w in editors:
                    w.lift()
            else:
                self.root.attributes("-topmost", True)
        except tk.TclError:
            return
        self.root.after(2000, self._keep_on_top)

    # ------------------------------------------------------------ цели
    def _load_goals(self):
        self.goals = []
        for p in sorted(GOALS_DIR.glob("*.json")):
            try:
                self.goals.append((p.name, Goal.load(p)))
            except Exception as e:
                print("Ошибка в цели", p, e)
        self.goal_box["values"] = [g.name for _, g in self.goals]
        want = self.settings.get("goal")
        names = [f for f, _ in self.goals]
        idx = names.index(want) if want in names else 0
        if self.goals:
            self.goal_box.current(idx)

    # ------------------------------------------------------------ крафты: создать / поделиться
    def _need_data(self) -> bool:
        if not self.data or not self.advisor:
            self.set_status("Данные ещё загружаются, подожди пару секунд…")
            return False
        return True

    def new_recipe(self):
        if self._need_data():
            from editor import RecipeEditor
            RecipeEditor(self._parent(), self.data, lambda r: self._saved(r, None))

    def edit_recipe(self):
        if not self._need_data():
            return
        g, f = self.current_goal(), self.current_goal_file()
        if not g:
            return self.new_recipe()
        from editor import RecipeEditor
        RecipeEditor(self._parent(), self.data, lambda r: self._saved(r, f), recipe=g.raw)

    def _parent(self):
        """Окно, рядом с которым открывать редактор: хаб, если он виден, иначе оверлей."""
        if self.hub is not None and self.hub.winfo_exists() and self.hub.state() != "withdrawn":
            return self.hub
        return self.root

    def _saved(self, recipe, filename):
        path = recipes.save(recipe, GOALS_DIR, filename)
        self.settings["goal"] = path.name
        save_settings(self.settings)
        self._load_goals()
        self.set_status(f"Крафт «{recipe['name']}» сохранён.")
        self.refresh_hub()
        if self.last_text:
            self._analyze(self.last_text)

    def share_recipe(self):
        g = self.current_goal()
        if not g:
            return self.set_status("Сначала выбери крафт.")
        code = recipes.encode(g.raw)
        self.last_clip = code  # чтобы не принять свой же код за новый буфер
        self.root.clipboard_clear()
        self.root.clipboard_append(code)
        self.set_status(f"Код крафта «{g.name}» скопирован ({len(code)} симв.). "
                        "Вставь его в Discord/Telegram — другой игрок нажмёт «импорт».")

    def import_recipe(self):
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            text = ""
        try:
            r = recipes.decode(text)
        except ValueError as e:
            return self.set_status(f"Импорт: {e} Скопируй код и нажми «импорт» ещё раз.")
        self._saved(r, None)
        by = f" от {r['author']}" if r.get("author") else ""
        self.set_status(f"Добавлен крафт «{r['name']}»{by}.")

    def _reload_goals(self):
        self._load_goals()
        self.set_status("Цели перезагружены.")
        self.last_clip = None  # пересчитать последний предмет

    def _goal_changed(self, _=None):
        g = self.current_goal_file()
        if g:
            self.settings["goal"] = g
            save_settings(self.settings)
        self.refresh_hub()
        if self.last_text and self.root.state() != "withdrawn":
            self._analyze(self.last_text)

    def current_goal(self) -> Goal | None:
        i = self.goal_box.current()
        return self.goals[i][1] if 0 <= i < len(self.goals) else None

    def current_goal_file(self) -> str | None:
        i = self.goal_box.current()
        return self.goals[i][0] if 0 <= i < len(self.goals) else None

    # ------------------------------------------------------------ данные
    def _init_data(self):
        try:
            self.data = GameData()
            _ = self.data.mods, self.data.bases, self.data.bench  # прогрев
            self.advisor = Advisor(self.data)
            self.results.put(("status", f"Данные {self.data.version}. Наведи на предмет в игре и нажми Ctrl+Alt+C."))
            self.results.put(("hub",))
        except Exception as e:
            self.results.put(("status", f"Не удалось загрузить данные: {e}"))

    last_text = None

    def _poll_clipboard(self):
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            text = None
        if text and text != self.last_clip:
            self.last_clip = text
            if looks_like_item(text):
                if self.settings.get("auto_show", True) and self.root.state() == "withdrawn":
                    self.root.deiconify()
                    self.root.attributes("-topmost", True)
                self.last_text = text
                self._analyze(text)
        self.root.after(300, self._poll_clipboard)

    def _analyze(self, text):
        goal = self.current_goal()
        if not self.advisor:
            self.set_status("Данные ещё загружаются, подожди пару секунд…")
            self.last_clip = None
            return
        if not goal:
            self.set_status("Нет цели — выбери крафт в хабе (⌂ → Мои крафты).")
            return
        self.set_status("Считаю…")
        threading.Thread(target=self._work, args=(text, goal), daemon=True).start()

    def _work(self, text, goal):
        try:
            item = parse_item(text)
            st, adv = self.advisor.advise(item, goal)
            mods = []
            if st:
                for pm, e in zip(item.mods, st.entries):
                    ok = any((e and w.matches(e)) or (not e and w.matches_text(pm.text)) for w in goal.wanted)
                    tier = f"T{e.tier}" if e else ("крафт" if pm.crafted else "T?")
                    mods.append(("П" if pm.kind == "prefix" else "С", tier, pm.text, ok))
            base = st.pool.base.name if st else item.base_name
            self.results.put(("result", item, base, mods, adv))
        except (ParseError, ValueError) as e:
            self.results.put(("status", f"Ошибка: {e}"))
        except Exception:
            self.results.put(("status", "Ошибка:\n" + traceback.format_exc(limit=2)))

    def _poll_results(self):
        try:
            while True:
                msg = self.results.get_nowait()
                if msg[0] == "status":
                    self.set_status(msg[1])
                elif msg[0] == "hub":
                    self.refresh_hub()
                else:
                    self.show(*msg[1:])
        except queue.Empty:
            pass
        self.root.after(100, self._poll_results)

    # ------------------------------------------------------------ вывод
    def set_status(self, text):
        self.status_lbl.configure(text=text)
        if self.root.state() == "withdrawn" and getattr(self, "hub", None) is not None:
            try:
                if self.hub.winfo_exists() and self.hub.state() != "withdrawn":
                    self.hub.set_status(text)
            except tk.TclError:
                pass
        self._resize()

    def show(self, item, base, mods, adv):
        hb, hf = RARITY.get(item.rarity, (BG2, GOLD))
        name = item.name if item.name and item.name != base else base
        sub = [base] if name != base else []
        sub += [f"ilvl {item.ilvl}", {"Normal": "обычный", "Magic": "магический", "Rare": "редкий",
                                      "Unique": "уникальный"}.get(item.rarity, item.rarity)]
        if item.influences:
            sub.append(", ".join(item.influences))
        if item.corrupted:
            sub.append("осквернён")
        self._paint_head(hb, hf, GOLD_LINE if item.rarity == "Rare" else LINE)
        self.title_lbl.configure(text=name)
        self.sub_lbl.configure(text="  ·  ".join(str(x) for x in sub if x))

        for w in self.mods_frame.winfo_children():
            w.destroy()
        limit = 2 if "Jewel" in (item.item_class or "") else (1 if item.rarity == "Magic" else 3)
        for kind_key, cap in (("П", "ПРЕФИКСЫ"), ("С", "СУФФИКСЫ")):
            part = [m for m in mods if m[0] == kind_key]
            hdr = tk.Frame(self.mods_frame, bg=BG)
            hdr.pack(fill="x", pady=(6, 1))
            tk.Label(hdr, text=cap, bg=BG, fg=MUTED, font=(FONT, 7, "bold")).pack(side="left")
            free = max(0, limit - len(part))
            tk.Label(hdr, text=f"{len(part)}/{limit}" + (f"  ·  свободно {free}" if free else ""),
                     bg=BG, fg=GOOD if free else DIM, font=(FONT, 8)).pack(side="left", padx=6)
            if not part:
                tk.Label(self.mods_frame, text="—", bg=BG, fg=DIM, font=(FONT, 9), anchor="w").pack(fill="x")
            for _, tier, text, ok in part:
                row = tk.Frame(self.mods_frame, bg=BG)
                row.pack(fill="x")
                tk.Label(row, text="✓" if ok else "·", bg=BG, fg=GOOD if ok else DIM, font=(FONT, 10, "bold"),
                         width=2, anchor="w").pack(side="left")
                tk.Label(row, text=tier, bg=BG, fg=GOOD if ok else MUTED, font=("Consolas", 9),
                         width=6, anchor="w").pack(side="right")
                tk.Label(row, text=text, bg=BG, fg=FG if ok else MUTED, font=(FONT, 9), anchor="w",
                         justify="left", wraplength=WIDTH - 110).pack(side="left", fill="x")

        self.step_card.pack(fill="x", padx=10, pady=(10, 0), before=self.status_lbl)
        self.step_lbl.configure(text=adv.step)
        self._paint_step_icon(adv.step)
        c = adv.chance
        if c is None:
            self.chance_lbl.configure(text="")
            self.tries_lbl.configure(text="")
        elif c >= 1:
            self.chance_lbl.configure(text="Гарантированно", fg=GOOD)
            self.tries_lbl.configure(text="1 действие")
        elif c > 0:
            self.chance_lbl.configure(text=f"Шанс {c:.1%}", fg=GOOD if c >= 0.2 else FG)
            self.tries_lbl.configure(text=f"в среднем ~{max(1, round(1 / c))} попыт.")
        else:
            self.chance_lbl.configure(text="Шанс 0% — так не получится", fg=WARN)
            self.tries_lbl.configure(text="")
        self._chance = c
        self.root.after(30, self._draw_bar)
        self.why_lbl.configure(text=adv.why)
        self.notes_lbl.configure(text="\n".join("• " + n for n in adv.notes))
        self.set_status("Скопируй следующий предмет: Ctrl+Alt+C")
        self._remember_item(item, mods)
        self._shown_at = time.time()
        self._place_near_cursor()
        self.root.lift()
        self.root.attributes("-topmost", True)

    def _paint_step_icon(self, step):
        from poecraft import icons
        st = icons.store()
        name = st.find(step) if st else None
        img = st.get(name, 36) if name else None
        if img is not None:
            self.step_icon.configure(image=img)
            self.step_icon._img = img
            self.step_icon.pack(side="left", padx=(0, 8), before=self.step_lbl)
        else:
            self.step_icon.pack_forget()

    def _paint_head(self, bg, fg, line):
        for w in self._drag_widgets:
            w.configure(bg=bg)
        for b in self.head_btns:
            b.configure(bg=bg)
        self.title_lbl.configure(fg=fg)
        self.rarity_line.configure(bg=line)

    def _draw_bar(self):
        c = getattr(self, "_chance", None)
        self.bar.delete("all")
        if c is None:
            return
        w = max(1, self.bar.winfo_width())
        self.bar.create_rectangle(0, 0, max(3, int(w * max(0.0, min(1.0, c)))), 5, fill=GOOD if c >= 1 else GOLD, width=0)

    # ------------------------------------------------------------ как в APT: у курсора и автоскрытие
    def _place_near_cursor(self):
        if self.settings.get("overlay_position", "fixed") != "cursor":
            return
        self.root.update_idletasks()
        px, py = self.root.winfo_pointerxy()
        w, h = self.root.winfo_width(), self.root.winfo_reqheight()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        # инвентарь справа — ставим карточку левее курсора, иначе правее
        x = px - w - 24 if px > sw // 2 else px + 24
        y = min(max(0, py - 40), max(0, sh - h - 40))
        self.root.geometry(f"+{max(0, x)}+{y}")

    def _hover(self, inside):
        self._mouse_inside = inside

    def _auto_hide(self):
        secs = int(self.settings.get("overlay_autohide", 0) or 0)
        shown = getattr(self, "_shown_at", None)
        if (secs and shown and self.root.state() != "withdrawn" and not getattr(self, "_mouse_inside", False)
                and time.time() - shown > secs):
            from mainwin import popdown_open
            if not popdown_open():
                self.root.withdraw()
                self._shown_at = None
        self.root.after(500, self._auto_hide)

    def run(self):
        self.root.mainloop()


def main():
    Overlay().run()


if __name__ == "__main__":
    main()
