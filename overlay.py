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
WIDTH = 400


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

        self._build_ui()
        i18n.translate_tree(self.root)
        self.hk = HotkeyManager(lambda action: self.root.after(0, lambda: self._on_hotkey(action)))
        self.apply_hotkeys()
        self._load_goals()
        self.set_status("Загружаю данные модов…")
        threading.Thread(target=self._init_data, daemon=True).start()

        self.root.after(300, self._poll_clipboard)
        self.root.after(100, self._poll_results)
        self.root.after(1000, self._keep_on_top)

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

        # Заголовок (за него таскаем окно)
        head = tk.Frame(r, bg=BG2)
        head.pack(fill="x")
        title = tk.Label(head, text="⚒ PoE Craft Helper", bg=BG2, fg=GOLD, font=(FONT, 10, "bold"))
        title.pack(side="left", padx=8, pady=4)
        for w in (head, title):
            w.bind("<ButtonPress-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)
            w.bind("<ButtonRelease-1>", self._drag_end)
        self._btn(head, "✕", self.quit, WARN).pack(side="right", padx=(0, 6))
        self.collapse_btn = self._btn(head, "—", self.toggle_collapse)
        self.collapse_btn.pack(side="right")
        self._btn(head, "◐", self.cycle_alpha).pack(side="right")
        self._btn(head, "⚙", self.open_settings).pack(side="right")

        # Тело
        self.body = tk.Frame(r, bg=BG)
        self.body.pack(fill="both", expand=True)

        row = tk.Frame(self.body, bg=BG)
        row.pack(fill="x", padx=8, pady=(8, 4))
        tk.Label(row, text="Цель:", bg=BG, fg=MUTED, font=(FONT, 9)).pack(side="left")
        self.goal_var = tk.StringVar()
        self.goal_box = ttk.Combobox(row, textvariable=self.goal_var, state="readonly",
                                     style="G.TCombobox", font=(FONT, 9), width=34)
        from mainwin import popdown_on_top
        popdown_on_top(self.goal_box)
        self.goal_box.pack(side="left", padx=4, fill="x", expand=True)
        self.goal_box.bind("<<ComboboxSelected>>", self._goal_changed)

        acts = tk.Frame(self.body, bg=BG)
        acts.pack(fill="x", padx=6, pady=(0, 4))
        for text, cmd in (("+ новый", self.new_recipe), ("изменить", self.edit_recipe),
                          ("поделиться", self.share_recipe), ("импорт", self.import_recipe),
                          ("папка", self.open_goals), ("мастерская", self.open_main)):
            self._btn(acts, text, cmd).pack(side="left")

        self.item_lbl = tk.Label(self.body, text="", bg=BG, fg=FG, font=(FONT, 10, "bold"),
                                 anchor="w", justify="left", wraplength=WIDTH - 20)
        self.item_lbl.pack(fill="x", padx=10)
        self.mods_frame = tk.Frame(self.body, bg=BG)
        self.mods_frame.pack(fill="x", padx=10)

        sep = tk.Frame(self.body, bg="#3a3127", height=1)
        sep.pack(fill="x", padx=8, pady=6)

        self.step_lbl = tk.Label(self.body, text="", bg=BG, fg=GOLD, font=(FONT, 14, "bold"),
                                 anchor="w", justify="left", wraplength=WIDTH - 20)
        self.step_lbl.pack(fill="x", padx=10)
        self.chance_lbl = tk.Label(self.body, text="", bg=BG, fg=FG, font=(FONT, 10),
                                   anchor="w", justify="left")
        self.chance_lbl.pack(fill="x", padx=10)
        self.why_lbl = tk.Label(self.body, text="", bg=BG, fg=FG, font=(FONT, 9),
                                anchor="w", justify="left", wraplength=WIDTH - 20)
        self.why_lbl.pack(fill="x", padx=10, pady=(4, 0))
        self.notes_lbl = tk.Label(self.body, text="", bg=BG, fg=MUTED, font=(FONT, 9),
                                  anchor="w", justify="left", wraplength=WIDTH - 20)
        self.notes_lbl.pack(fill="x", padx=10, pady=(4, 0))

        self.status_lbl = tk.Label(self.body, text="", bg=BG, fg=MUTED, font=(FONT, 8),
                                   anchor="w", justify="left", wraplength=WIDTH - 20)
        self.status_lbl.pack(fill="x", padx=10, pady=(8, 8))
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
                       and w.winfo_viewable()]
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
            RecipeEditor(self.root, self.data, lambda r: self._saved(r, None))

    def edit_recipe(self):
        if not self._need_data():
            return
        g, f = self.current_goal(), self.current_goal_file()
        if not g:
            return self.new_recipe()
        from editor import RecipeEditor
        RecipeEditor(self.root, self.data, lambda r: self._saved(r, f), recipe=g.raw)

    def _saved(self, recipe, filename):
        path = recipes.save(recipe, GOALS_DIR, filename)
        self.settings["goal"] = path.name
        save_settings(self.settings)
        self._load_goals()
        self.set_status(f"Крафт «{recipe['name']}» сохранён.")
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
        if self.last_text:
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
            self.set_status("Нет цели — добавь .json в папку goals (кнопка «папка»).")
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
                else:
                    self.show(*msg[1:])
        except queue.Empty:
            pass
        self.root.after(100, self._poll_results)

    # ------------------------------------------------------------ вывод
    def set_status(self, text):
        self.status_lbl.configure(text=text)
        self._resize()

    def show(self, item, base, mods, adv):
        name = item.name if item.name == base else f"{item.name} — {base}"
        self.item_lbl.configure(text=f"{name}   ({item.rarity}, ilvl {item.ilvl})", pady=4)
        for w in self.mods_frame.winfo_children():
            w.destroy()
        for kind, tier, text, ok in mods:
            row = tk.Frame(self.mods_frame, bg=BG)
            row.pack(fill="x")
            color = GOOD if ok else BAD
            tk.Label(row, text=f"{kind} {tier:<5}", bg=BG, fg=color, font=("Consolas", 9),
                     width=9, anchor="w").pack(side="left")
            tk.Label(row, text=text, bg=BG, fg=color, font=(FONT, 9), anchor="w",
                     justify="left", wraplength=WIDTH - 100).pack(side="left", fill="x")

        self.step_lbl.configure(text=adv.step)
        if adv.chance is None:
            self.chance_lbl.configure(text="")
        elif adv.chance >= 1:
            self.chance_lbl.configure(text="Гарантированно", fg=GOOD)
        elif adv.chance > 0:
            tries = max(1, round(1 / adv.chance))
            self.chance_lbl.configure(text=f"Шанс: {adv.chance:.1%}   ·   в среднем ~{tries} попыт.",
                                      fg=GOOD if adv.chance >= 0.2 else FG)
        else:
            self.chance_lbl.configure(text="Шанс: 0% — так не получится", fg=WARN)
        self.why_lbl.configure(text=adv.why)
        self.notes_lbl.configure(text="\n".join("• " + n for n in adv.notes))
        self.set_status("Скопируй следующий предмет: Ctrl+Alt+C")

    def run(self):
        self.root.mainloop()


def main():
    Overlay().run()


if __name__ == "__main__":
    main()
