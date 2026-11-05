"""Глобальные горячие клавиши Windows (RegisterHotKey) — без сторонних библиотек.

Горячая клавиша работает, даже когда активна игра. Программа только реагирует на
нажатие (показать/спрятать своё окно) и ничего не отправляет в игру.
"""

from __future__ import annotations

import sys
import threading

DEFAULT_HOTKEYS = {"overlay": "Ctrl+Shift+O", "workshop": "Ctrl+Shift+M", "hub": "Ctrl+Shift+H",
                   "to_emulator": "Ctrl+Shift+E"}

MOD = {"ctrl": 0x0002, "alt": 0x0001, "shift": 0x0004, "win": 0x0008}
MOD_NOREPEAT = 0x4000
WM_HOTKEY, WM_QUIT = 0x0312, 0x0012

VK = {**{chr(c): c for c in range(ord("A"), ord("Z") + 1)},
      **{str(d): 0x30 + d for d in range(10)},
      **{f"F{i}": 0x6F + i for i in range(1, 13)},
      "SPACE": 0x20, "TAB": 0x09, "ESC": 0x1B, "HOME": 0x24, "END": 0x23, "INSERT": 0x2D,
      "DELETE": 0x2E, "PAGEUP": 0x21, "PAGEDOWN": 0x22, "`": 0xC0, "~": 0xC0}


def parse(combo: str) -> tuple[int, int] | None:
    """'Ctrl+Shift+O' → (модификаторы, код клавиши). None — если строка неверная."""
    if not combo:
        return None
    parts = [p.strip() for p in combo.replace("-", "+").split("+") if p.strip()]
    mods, key = 0, None
    for p in parts:
        low = p.lower()
        if low in MOD:
            mods |= MOD[low]
        elif p.upper() in VK:
            key = VK[p.upper()]
        else:
            return None
    if key is None:
        return None
    return mods, key


def normalize(combo: str) -> str:
    parsed = parse(combo)
    if not parsed:
        return ""
    parts = [p.strip() for p in combo.replace("-", "+").split("+") if p.strip()]
    order = ["ctrl", "alt", "shift", "win"]
    mods = sorted((p.capitalize() for p in parts if p.lower() in MOD), key=lambda x: order.index(x.lower()))
    key = next(p.upper() for p in parts if p.lower() not in MOD)
    return "+".join(mods + [key])


def from_tk_event(e) -> str | None:
    """Комбинация из события tkinter (для поля «нажми сочетание»)."""
    key = e.keysym
    if key in ("Control_L", "Control_R", "Alt_L", "Alt_R", "Shift_L", "Shift_R", "Super_L", "Super_R"):
        return None
    key = {"space": "Space", "Escape": "Esc", "Prior": "PageUp", "Next": "PageDown", "grave": "`"}.get(key, key)
    if len(key) == 1:
        key = key.upper()
    mods = []
    if e.state & 0x0004:
        mods.append("Ctrl")
    if e.state & 0x20000 or e.state & 0x0008:   # Alt на Windows / X11
        mods.append("Alt")
    if e.state & 0x0001:
        mods.append("Shift")
    combo = "+".join(mods + [key])
    return normalize(combo) or None


class HotkeyManager:
    """Отдельный поток с очередью сообщений Windows; callback вызывается с именем действия."""

    def __init__(self, callback):
        self.callback = callback
        self.thread: threading.Thread | None = None
        self.thread_id = None
        self.errors: list[str] = []

    @property
    def supported(self) -> bool:
        return sys.platform == "win32"

    def start(self, bindings: dict[str, str]):
        """bindings: {'overlay': 'Ctrl+Shift+O', ...}. Перезапускает регистрацию."""
        self.stop()
        if not self.supported:
            return []
        ready = threading.Event()
        self.errors = []

        def run():
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            self.thread_id = kernel32.GetCurrentThreadId()
            ids = {}
            for i, (action, combo) in enumerate(bindings.items(), start=1):
                parsed = parse(combo)
                if not parsed:
                    continue
                mods, vk = parsed
                if user32.RegisterHotKey(None, i, mods | MOD_NOREPEAT, vk):
                    ids[i] = action
                else:
                    self.errors.append(f"{combo} уже занято другой программой")
            ready.set()
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY and msg.wParam in ids:
                    try:
                        self.callback(ids[msg.wParam])
                    except Exception:
                        pass
            for i in ids:
                user32.UnregisterHotKey(None, i)

        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        ready.wait(2)
        return list(self.errors)

    def stop(self):
        if self.thread and self.thread_id and self.supported:
            import ctypes
            ctypes.windll.user32.PostThreadMessageW(self.thread_id, WM_QUIT, 0, 0)
            self.thread.join(1)
        self.thread = None
        self.thread_id = None


def send_copy(advanced: bool = True) -> bool:
    """Одно нажатие Ctrl+Alt+C (или Ctrl+C) — как в Awakened PoE Trade: игра сама кладёт
    предмет под курсором в буфер. Сначала отпускаем модификаторы горячей клавиши,
    которые пользователь ещё держит, иначе игра получит Ctrl+Shift+Alt+C."""
    if sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

    class INPUT(ctypes.Structure):
        class _U(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]
        _anonymous_ = ("u",)
        _fields_ = [("type", wintypes.DWORD), ("u", _U)]

    KEYUP = 0x0002
    CTRL, ALT, SHIFT, LWIN, C = 0x11, 0x12, 0x10, 0x5B, 0x43
    user32 = ctypes.windll.user32
    seq = [(k, KEYUP) for k in (SHIFT, ALT, CTRL, LWIN) if user32.GetAsyncKeyState(k) & 0x8000]
    keys = [CTRL, ALT, C] if advanced else [CTRL, C]
    seq += [(k, 0) for k in keys] + [(k, KEYUP) for k in reversed(keys)]
    arr = (INPUT * len(seq))()
    for i, (vk, flags) in enumerate(seq):
        arr[i].type = 1
        arr[i].ki = KEYBDINPUT(vk, 0, flags, 0, 0)
    return user32.SendInput(len(seq), arr, ctypes.sizeof(INPUT)) == len(seq)
