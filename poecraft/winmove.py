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
    """Начать системное перетаскивание окна: Windows двигает его сама.

    Сообщение именно ПОСЫЛАЕМ (PostMessage), а не отправляем (SendMessage). SendMessage
    запускал цикл перетаскивания Windows внутри вызова ctypes, пока Python отпустил GIL.
    Таймеры Tk (after) срабатывали внутри этого цикла, и Python 3.12 падал с
    «PyEval_RestoreThread: … GIL is released». С PostMessage цикл идёт в обычной очереди
    окна, где Tk правильно передаёт управление Python. Когда кнопку отпустили, зовём on_done."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        u = ctypes.windll.user32
        hwnd = int(win.wm_frame(), 16)
        u.ReleaseCapture()
        if not u.PostMessageW(hwnd, WM_NCLBUTTONDOWN, HTCAPTION, 0):
            return False
    except Exception:  # noqa: BLE001 — что-то пошло не так: двигаем по-старому
        return False
    win._pch_native_drag = True          # пока тащит Windows, throttled_move ничего не делает

    def done():
        win._pch_native_drag = False
        if on_done:
            on_done()
    _when_mouse_released(win, done)
    return True


def _when_mouse_released(win, cb, started: float | None = None):
    """Позвать cb, когда левая кнопка мыши отпущена (конец перетаскивания)."""
    import ctypes
    import time
    started = started or time.time()
    try:
        held = ctypes.windll.user32.GetAsyncKeyState(0x01) & 0x8000
    except Exception:  # noqa: BLE001
        held = 0
    if held and time.time() - started < 120:
        win.after(50, lambda: _when_mouse_released(win, cb, started))
    else:
        win.after(50, cb)


def throttled_geometry(win, spec: str, ms: int = 16):
    """Копим последнее значение geometry() и применяем раз в кадр, а не на каждое движение мыши."""
    if getattr(win, "_pch_native_drag", False):
        return
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


def show_in_taskbar(win) -> None:
    """Своя кнопка на панели задач для окна-«ребёнка» (хаб, мастерская).

    Без этого Windows не показывает такие окна на панели задач: они принадлежат
    скрытому окну оверлея. После «Свернуть» окно было некуда вернуть, кроме горячей клавиши.
    WS_EX_APPWINDOW заставляет панель задач показать окно; чтобы стиль подхватился,
    окно на миг прячем и показываем снова (только один раз)."""
    if sys.platform != "win32" or getattr(win, "_pch_taskbar", False):
        return
    try:
        import ctypes
        u = ctypes.windll.user32
        hwnd = int(win.wm_frame(), 16)
        GWL_EXSTYLE, WS_EX_APPWINDOW, WS_EX_TOOLWINDOW = -20, 0x00040000, 0x00000080
        ex = u.GetWindowLongW(hwnd, GWL_EXSTYLE)
        if not ex & WS_EX_APPWINDOW or ex & WS_EX_TOOLWINDOW:
            u.SetWindowLongW(hwnd, GWL_EXSTYLE, (ex | WS_EX_APPWINDOW) & ~WS_EX_TOOLWINDOW)
            if u.IsWindowVisible(hwnd):
                u.ShowWindow(hwnd, 0)      # SW_HIDE
                u.ShowWindow(hwnd, 5)      # SW_SHOW
        win._pch_taskbar = True
    except Exception:  # noqa: BLE001
        pass
