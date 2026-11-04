"""Точка входа для .exe: запуск двойным кликом, выбор цели из меню, слежение за буфером."""

import sys
import time
import traceback

if sys.platform == "win32":  # кириллица в консоли Windows
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        ctypes.windll.kernel32.SetConsoleCP(65001)
        ctypes.windll.kernel32.SetConsoleTitleW("PoE Craft Helper")
    except Exception:
        pass
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

from poecraft.advisor import Advisor, Goal
from poecraft.cli import main as cli_main, report
from poecraft.data import APP_DIR, GameData, download
from poecraft.parser import ParseError, looks_like_item


def pick_goal():
    goals = sorted((APP_DIR / "goals").glob("*.json"))
    if not goals:
        print("В папке goals нет ни одной цели (.json).")
        return None
    print("Выбери цель крафта:")
    loaded = []
    for i, g in enumerate(goals, 1):
        try:
            goal = Goal.load(g)
            loaded.append(goal)
            print(f"  {i}. {goal.name}")
        except Exception as e:
            loaded.append(None)
            print(f"  {i}. [ошибка в {g.name}: {e}]")
    print("  u. Обновить данные модов (после патча)")
    while True:
        s = input("> ").strip().lower()
        if s == "u":
            print("Версия данных:", download())
            continue
        if s.isdigit() and 1 <= int(s) <= len(loaded) and loaded[int(s) - 1]:
            return loaded[int(s) - 1]
        print("Введи номер из списка.")


def interactive():
    import pyperclip

    print("=" * 60)
    print(" PoE Craft Helper — помощник крафта Path of Exile")
    print("=" * 60)
    data = GameData()
    print(f"Данные модов: {data.version}\n")
    goal = pick_goal()
    if not goal:
        return
    advisor = Advisor(data)
    print(f"\nЦель: {goal.name}")
    print("Теперь в игре наведи на предмет и нажми Ctrl+Alt+C.")
    print("Совет появится здесь. Закрыть — Ctrl+C или крестик.\n")

    last = pyperclip.paste()
    while True:
        text = pyperclip.paste()
        if text != last:
            last = text
            if looks_like_item(text):
                try:
                    print(report(advisor, text, goal))
                except (ParseError, ValueError) as e:
                    print("Ошибка:", e)
                print("-" * 60)
        time.sleep(0.3)


if __name__ == "__main__":
    try:
        if len(sys.argv) > 1:
            cli_main()
        else:
            interactive()
    except KeyboardInterrupt:
        pass
    except Exception:
        traceback.print_exc()
        input("\nПроизошла ошибка. Нажми Enter, чтобы закрыть…")
