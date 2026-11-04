"""Командная строка.

  python -m poecraft.cli --goal goals/belt_life_res.json item.txt
  python -m poecraft.cli --goal goals/belt_life_res.json --clipboard
  python -m poecraft.cli --goal goals/belt_life_res.json --watch     # следит за буфером
  python -m poecraft.cli --update                                    # обновить данные после патча
"""

from __future__ import annotations

import argparse
import sys
import time

from .advisor import Advisor, Goal
from .data import GameData, download
from .parser import ParseError, looks_like_item, parse_item


def report(advisor: Advisor, text: str, goal: Goal) -> str:
    item = parse_item(text)
    st, adv = advisor.advise(item, goal)
    base = st.pool.base.name if st else item.base_name
    out = [f"Предмет: {item.name} — база {base} ({item.rarity}, ilvl {item.ilvl})"]
    if st:
        for pm, e in zip(item.mods, st.entries):
            tag = "П" if pm.kind == "prefix" else "С"
            if e:
                tier = f"T{e.tier}"
            else:
                tier = "крафт" if pm.crafted else "T?"
            out.append(f"  [{tag}] {tier:<5} {pm.text}")
    out.append(f"\nЦель: {goal.name}")
    out.append(adv.render())
    return "\n".join(out)


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Помощник крафта Path of Exile")
    ap.add_argument("item", nargs="?", help="файл с текстом предмета (Ctrl+Alt+C)")
    ap.add_argument("--goal", help="JSON-файл с целью крафта")
    ap.add_argument("--clipboard", action="store_true", help="взять предмет из буфера обмена")
    ap.add_argument("--watch", action="store_true", help="следить за буфером обмена")
    ap.add_argument("--update", action="store_true", help="скачать свежие данные RePoE")
    a = ap.parse_args(argv)

    if a.update:
        print("Версия данных:", download())
        return
    if not a.goal:
        ap.error("нужна цель: --goal goals/....json")

    data = GameData()
    advisor = Advisor(data)
    goal = Goal.load(a.goal)
    print(f"Данные RePoE: {data.version}\n")

    if a.watch or a.clipboard:
        import pyperclip  # pip install pyperclip
        last = None
        while True:
            text = pyperclip.paste()
            if text != last and looks_like_item(text):
                last = text
                try:
                    print(report(advisor, text, goal))
                except (ParseError, ValueError) as e:
                    print("Ошибка:", e)
                print("-" * 60)
            if not a.watch:
                break
            time.sleep(0.3)
        return

    text = open(a.item, encoding="utf-8").read() if a.item else sys.stdin.read()
    try:
        print(report(advisor, text, goal))
    except (ParseError, ValueError) as e:
        print("Ошибка:", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
