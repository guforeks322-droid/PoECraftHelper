"""Отчёты об ошибках: всё неперехваченное пишется в logs/errors.log рядом с программой,
а пользователю показывается окно с кнопкой «Скопировать отчёт» — его можно прислать автору."""

from __future__ import annotations

import datetime
import platform
import sys
import threading
import traceback

from .data import APP_DIR
from .updater import APP_VERSION

LOG_DIR = APP_DIR / "logs"
_shown = 0


def report_text(exc_type, exc, tb, where: str = "") -> str:
    lines = traceback.format_exception(exc_type, exc, tb)
    head = (f"PoE Craft Helper {APP_VERSION} · {platform.platform()} · Python {platform.python_version()}"
            f"{' · ' + where if where else ''}\n{datetime.datetime.now():%Y-%m-%d %H:%M:%S}\n")
    return head + "".join(lines)


def write(text: str) -> str | None:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        path = LOG_DIR / "errors.log"
        if path.exists() and path.stat().st_size > 512_000:      # не раздуваем: старый лог в .old
            path.replace(LOG_DIR / "errors.old.log")
        with path.open("a", encoding="utf-8") as f:
            f.write(text + "\n" + "-" * 60 + "\n")
        return str(path)
    except OSError:
        return None


def _show(root, text: str, path: str | None):
    """Небольшое окно поверх всего: что случилось + кнопка копирования. Не больше 3 окон за запуск."""
    global _shown
    if root is None or _shown >= 3:
        return
    _shown += 1
    import tkinter as tk
    from . import i18n
    try:
        w = tk.Toplevel(root)
        w.title(i18n.t("Ошибка — PoE Craft Helper"))
        w.configure(bg="#16130f")
        w.attributes("-topmost", True)
        last = text.strip().splitlines()[-1][:300]
        tk.Label(w, text=i18n.t("Что-то пошло не так. Программа продолжает работать."), bg="#16130f", fg="#e3b55b",
                 font=("Segoe UI", 11, "bold"), anchor="w").pack(fill="x", padx=14, pady=(12, 4))
        tk.Label(w, text=last, bg="#16130f", fg="#e07a5f", font=("Segoe UI", 9), anchor="w", justify="left",
                 wraplength=460).pack(fill="x", padx=14)
        tk.Label(w, text=i18n.t("Отчёт сохранён:") + f" {path}" if path else "", bg="#16130f", fg="#8a7f70",
                 font=("Segoe UI", 8), anchor="w", justify="left", wraplength=460).pack(fill="x", padx=14, pady=(6, 0))
        row = tk.Frame(w, bg="#16130f")
        row.pack(fill="x", padx=14, pady=12)

        def copy():
            w.clipboard_clear()
            w.clipboard_append(text)
            b.configure(text=i18n.t("Скопировано ✓"))
        b = tk.Button(row, text=i18n.t("Скопировать отчёт"), command=copy, bg="#2a2116", fg="#e3b55b",
                      activebackground="#3a2c17", activeforeground="#e3b55b", relief="flat", padx=12, pady=4)
        b.pack(side="left")
        tk.Button(row, text=i18n.t("Закрыть"), command=w.destroy, bg="#1f1a14", fg="#d8cfc0", relief="flat",
                  padx=12, pady=4).pack(side="right")
        w.update_idletasks()
        x = (w.winfo_screenwidth() - w.winfo_reqwidth()) // 2
        y = (w.winfo_screenheight() - w.winfo_reqheight()) // 3
        w.geometry(f"+{x}+{y}")
    except Exception:  # noqa: BLE001 — окно ошибки само не должно ронять программу
        pass


def install(root) -> None:
    """Перехват ошибок: в главном потоке, в обработчиках Tk и в фоновых потоках."""
    def handle(exc_type, exc, tb, where=""):
        if issubclass(exc_type, KeyboardInterrupt):
            return
        text = report_text(exc_type, exc, tb, where)
        path = write(text)
        try:
            sys.__stderr__ and sys.__stderr__.write(text)
        except Exception:  # noqa: BLE001
            pass
        try:
            root.after(0, lambda: _show(root, text, path))
        except Exception:  # noqa: BLE001
            pass

    sys.excepthook = lambda t, e, tb: handle(t, e, tb, "main")
    root.report_callback_exception = lambda t, e, tb: handle(t, e, tb, "ui")
    threading.excepthook = lambda a: handle(a.exc_type, a.exc_value, a.exc_traceback, f"thread {a.thread.name}")
