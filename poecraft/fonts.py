"""Шрифты программы: Inter для текста и Forum (римские капители, есть кириллица) для заголовков.

Файлы лежат в assets/fonts и подключаются только для этой программы (FR_PRIVATE) —
в систему ничего не ставится. Если подключить не вышло, остаётся Segoe UI.
Оба шрифта — SIL Open Font License, лицензии рядом с файлами.
"""

from __future__ import annotations

import sys
from pathlib import Path

UI = "Segoe UI"        # основной текст
TITLE = "Segoe UI"     # заголовки, названия предметов
_loaded = False


def _base() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


def load() -> tuple[str, str]:
    """Подключить шрифты (один раз). Вызывать до создания окон."""
    global UI, TITLE, _loaded
    if _loaded:
        return UI, TITLE
    _loaded = True
    folder = _base() / "assets" / "fonts"
    files = sorted(folder.glob("*.ttf")) if folder.is_dir() else []
    if not files:
        return UI, TITLE
    ok = set()
    if sys.platform == "win32":
        try:
            import ctypes
            FR_PRIVATE = 0x10
            add = ctypes.windll.gdi32.AddFontResourceExW
            for f in files:
                if add(str(f), FR_PRIVATE, 0):
                    ok.add(f.stem.split("-")[0])
        except Exception:  # noqa: BLE001
            ok = set()
    else:
        ok = {f.stem.split("-")[0] for f in files}   # на Linux/Mac берём, если шрифт есть в системе
    if "Inter" in ok:
        UI = "Inter"
    if "Forum" in ok:
        TITLE = "Forum"
    return UI, TITLE


load()
