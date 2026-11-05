"""Плавное перетаскивание окон без системной рамки.

В Windows окно отдаём системе, как будто схватили его за обычный заголовок
(WM_NCLBUTTONDOWN + HTCAPTION): двигает сама Windows, без потока <B1-Motion>
и пересчёта geometry() на каждый пиксель — поэтому не лагает даже с прозрачностью.
На других системах — запасной вариант: позиция ставится не чаще ~60 раз в секунду.
"""

from __future__ import annotations

import sys

WM_NCLBUTTONDOWN, HTCAPTION = 0x00A1, 2


def native_drag(win, on_done=None) -> bool:
    """Начать системное перетаскивание окна. True — Windows двигает окно сама
    (вызов возвращается, когда кнопку мыши отпустили; тогда зовём on_done)."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        u = ctypes.windll.user32
        hwnd = int(win.wm_frame(), 16)
        u.ReleaseCapture()
        u.SendMessageW(hwnd, WM_NCLBUTTONDOWN, HTCAPTION, 0)
    except Exception:  # noqa: BLE001 — что-то пошло не так: двигаем по-старому
        return False
    if on_done:
        win.after_idle(on_done)
    return True


def throttled_geometry(win, spec: str, ms: int = 16):
    """Копим последнее значение geometry() и применяем раз в кадр, а не на каждое движение мыши."""
    win._pch_geo = spec
    if getattr(win, "_pch_geo_job", None):
        return

    def go():
        win._pch_geo_job = None
        win.geometry(win._pch_geo)

    win._pch_geo_job = win.after(ms, go)


def throttled_move(win, x: int, y: int, ms: int = 16):
    throttled_geometry(win, f"+{x}+{y}", ms)


def ensure_topmost(win) -> None:
    """Вернуть окну «поверх всех», только если его кто-то снял (игра, другое окно).

    Раньше раз в 2 секунды вызывался attributes('-topmost', True) — Tk каждый раз заново
    ставит окно наверх и перерисовывает его, отсюда мерцание. Теперь сначала проверяем флаг
    и, если он на месте, ничего не трогаем; если нет — ставим без активации и перерисовки."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        u = ctypes.windll.user32
        hwnd = int(win.wm_frame(), 16)
        GWL_EXSTYLE, WS_EX_TOPMOST = -20, 0x00000008
        if u.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOPMOST:
            return
        HWND_TOPMOST = ctypes.c_void_p(-1)
        SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_NOOWNERZORDER = 0x1, 0x2, 0x10, 0x200
        u.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_NOOWNERZORDER)
    except Exception:  # noqa: BLE001
        pass
