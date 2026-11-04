"""Язык интерфейса: русский (по умолчанию) и английский.

Переводим готовое дерево виджетов: у каждого Label/Button/Checkbutton/вкладки/заголовка
таблицы текст ищется в словаре. Новые строки достаточно добавить в EN.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

EN = {
    # оверлей
    "Цель:": "Goal:", "+ новый": "+ new", "изменить": "edit", "поделиться": "share", "импорт": "import",
    "папка": "folder", "мастерская": "workshop", "⚙": "⚙",
    "Скопируй следующий предмет: Ctrl+Alt+C": "Copy the next item: Ctrl+Alt+C",
    "Загружаю данные модов…": "Loading mod data…",
    # мастерская: шапка
    "⚒ PoE Craft Helper — мастерская": "⚒ PoE Craft Helper — workshop", "База": "Base", "влияние": "influence",
    "Показать моды": "Show mods", "цены…": "prices…", "нет": "none",
    "Пул модов": "Mod pool", "Калькулятор": "Calculator", "Эссенции и фоссилы": "Essences & fossils",
    "Эмулятор": "Emulator", "Сокеты": "Sockets", "Настройки": "Settings",
    # пул
    "Поиск": "Search", "тип кластера": "cluster type", "катализатор 20%": "catalyst 20%",
    "Префиксы": "Prefixes", "Суффиксы": "Suffixes", "Мод": "Mod", "% всех": "% all", "% типа": "% type",
    "тир": "tier", "Выбери базу предмета.": "Pick an item base.",
    "Клик по ☐ — нужен мод · по «до T» — худший тир · двойной клик — тиры":
        "Click ☐ — wanted mod · click «до T» — worst tier · double click — tiers",
    # калькулятор
    "Нужные моды (выбираются во вкладке «Пул модов»):": "Wanted mods (pick them in «Mod pool»):",
    "Посчитать": "Calculate", "+ эссенции": "+ essences", "+ фоссилы": "+ fossils", "+ Harvest": "+ Harvest",
    "Сохранить как крафт:": "Save as craft:", "Сохранить и получить код": "Save & get code",
    "скопировать": "copy", "ничего не выбрано": "nothing selected",
    # эссенции и фоссилы
    "Эссенции для этой базы": "Essences for this base", "Фоссилы (клик по ☐)": "Fossils (click ☐)",
    "Посчитать выбранное": "Calculate selection", "сбросить выбор": "clear selection",
    "Эссенция": "Essence", "мод": "mod", "цена": "price", "фоссил": "fossil", "эффект": "effect",
    "Выбери эссенцию ИЛИ до 4 фоссилов, затем «Посчитать» — для нужных модов из «Пула модов».":
        "Pick an essence OR up to 4 fossils, then «Calculate» — for wanted mods from «Mod pool».",
    # эмулятор
    "Новый белый предмет": "New white item", "↶ отменить": "↶ undo", "Валюта": "Currency",
    "применить": "apply", "Верстак": "Crafting bench", "скрафтить": "craft",
    "снять крафты верстака": "remove bench crafts", "Влияние · Eldritch": "Influence · Eldritch",
    "Exalt завоевателя": "Conqueror exalt", "Ember (Exarch)": "Ember (Exarch)", "Ichor (Eater)": "Ichor (Eater)",
    "+мод/−мод": "+mod/−mod", "тех же модов ↑": "same mods ↑", "тех же модов ↓": "same mods ↓",
    "Veiled (Jun)": "Veiled (Jun)", "Unveil (1 из 3)": "Unveil (1 of 3)",
    "Фоссилы (выбираются во вкладке «Эссенции и фоссилы»)": "Fossils (picked in «Essences & fossils»)",
    "не выбраны": "none selected", "Выбери базу сверху и нажми «Новый белый предмет».":
        "Pick a base above and press «New white item».",
    # сокеты
    "качество": "quality", "сокетов": "sockets", "нужно R": "need R", "взять требования базы": "use base requirements",
    "белые сокеты (механика лиги 3.29: чем ниже ilvl, тем больше белых)":
        "white sockets (3.29 league mechanic: lower ilvl — more white)",
    # настройки
    "Горячие клавиши": "Hotkeys", "Показать / спрятать оверлей": "Show / hide overlay",
    "Показать / спрятать мастерскую": "Show / hide workshop", "Применить": "Apply",
    "нажми сочетание…": "press a combo…", "очистить": "clear",
    "Язык": "Language", "Интерфейс:": "Interface:", "Клиент игры:": "Game client:",
    "Обновления": "Updates", "Обновить данные модов": "Update mod data", "Обновить цены": "Update prices",
    "Проверить обновления программы": "Check for app updates", "Репозиторий релизов (GitHub):": "Releases repo (GitHub):",
    "О программе": "About",
    "Язык интерфейса сменится после перезапуска программы.": "Interface language changes after restarting the app.",
}

_lang = "ru"


def set_lang(lang: str):
    global _lang
    _lang = lang if lang in ("ru", "en") else "ru"


def lang() -> str:
    return _lang


def t(s: str) -> str:
    return EN.get(s, s) if _lang == "en" else s


def translate_tree(root: tk.Misc):
    """Переводит тексты всех виджетов (вызывать после построения интерфейса)."""
    if _lang == "ru":
        return
    stack = [root]
    while stack:
        w = stack.pop()
        stack.extend(w.winfo_children())
        try:
            if isinstance(w, ttk.Notebook):
                for i in range(len(w.tabs())):
                    w.tab(i, text=t(w.tab(i, "text")))
            elif isinstance(w, ttk.Treeview):
                for col in ("#0",) + tuple(w["columns"]):
                    w.heading(col, text=t(w.heading(col, "text")))
            elif "text" in w.keys():
                txt = w.cget("text")
                if isinstance(txt, str) and txt:
                    w.configure(text=t(txt))
        except tk.TclError:
            pass
