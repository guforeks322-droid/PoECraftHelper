"""Главное окно: локальный веб-сервер (127.0.0.1) + HTML-интерфейс.

Окно открывается в Microsoft Edge в режиме приложения (без вкладок и адресной строки),
а если Edge нет — в браузере по умолчанию. Всё работает только на этом компьютере.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import recipes
from .calc import Target, calculate, pool_table
from .data import APP_DIR, GameData
from .pool import ModPool
from .prices import Prices

UI_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "poecraft" / "ui"
if not UI_DIR.exists():
    UI_DIR = Path(__file__).resolve().parent / "ui"

CRAFT_DOMAINS = {"item", "flask", "misc", "abyss_jewel"}
SKIP_CLASSES = {"HiddenItem", "FishingRod"}


class App:
    def __init__(self, data: GameData | None = None):
        self.data = data or GameData()
        self.prices = Prices()
        self._pools: dict[tuple, ModPool] = {}
        self._lock = threading.Lock()
        threading.Thread(target=self.prices.refresh, daemon=True).start()

    def pool(self, base_name: str, ilvl: int) -> ModPool:
        key = (base_name, ilvl)
        with self._lock:
            if key not in self._pools:
                base = self.data.bases.get(base_name)
                if not base:
                    raise ValueError(f"Нет такой базы: {base_name}")
                if len(self._pools) > 40:
                    self._pools.clear()
                self._pools[key] = ModPool(self.data, base, ilvl)
            return self._pools[key]

    def bases(self) -> list[dict]:
        out = []
        for b in self.data.bases.values():
            if b.domain in CRAFT_DOMAINS and b.item_class not in SKIP_CLASSES:
                out.append({"name": b.name, "cls": b.item_class,
                            "cls_ru": recipes.CLASS_RU.get(b.item_class, b.item_class)})
        out.sort(key=lambda b: (b["cls_ru"], b["name"]))
        return out

    # ------------------------------------------------------------- API
    def api(self, path: str, q: dict, body: dict | None):
        if path == "/api/bases":
            return {"bases": self.bases(), "version": self.data.version}
        if path == "/api/pool":
            base, ilvl = q["base"], int(q.get("ilvl", 84))
            p = self.pool(base, ilvl)
            t = pool_table(p)
            t.update(base=base, ilvl=ilvl, cls=p.base.item_class, tags=sorted(p.tags))
            return t
        if path == "/api/calc":
            p = self.pool(body["base"], int(body.get("ilvl", 84)))
            targets = [Target(t["kind"], t["type"], int(t["max_tier"]), t.get("label", "")) for t in body["targets"]]
            if not targets:
                raise ValueError("Выбери хотя бы один нужный мод.")
            self.prices.refresh()
            return {"results": calculate(p, targets, self.prices), "prices": self.prices.info()}
        if path == "/api/prices":
            if q.get("refresh"):
                self.prices.refresh(force=True)
            return self.prices.info()
        if path == "/api/save_goal":
            rec = {
                "name": body["name"], "author": body.get("author", ""),
                "description": body.get("description", ""),
                "base_class": self.data.bases[body["base"]].item_class, "base": body["base"],
                "min_ilvl": int(body.get("ilvl", 0)) or None,
                "wanted": [{"label": t.get("label") or t["type"], "mod_type": t["type"], "kind": t["kind"],
                            "max_tier": int(t["max_tier"])} for t in body["targets"]],
            }
            path_ = recipes.save(rec, APP_DIR / "goals")
            return {"saved": path_.name, "code": recipes.encode(rec)}
        raise KeyError(path)


def make_handler(app: App):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, payload, ctype="application/json; charset=utf-8"):
            data = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _handle(self, body=None):
            u = urlparse(self.path)
            if not u.path.startswith("/api/"):
                f = UI_DIR / ("index.html" if u.path in ("/", "") else u.path.lstrip("/"))
                if f.is_file() and UI_DIR in f.resolve().parents:
                    ctype = {"html": "text/html", "js": "text/javascript", "css": "text/css",
                             "svg": "image/svg+xml", "png": "image/png"}.get(f.suffix[1:], "application/octet-stream")
                    return self._send(200, f.read_bytes(), ctype + "; charset=utf-8")
                return self._send(404, {"error": "not found"})
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            try:
                return self._send(200, app.api(u.path, q, body))
            except KeyError as e:
                return self._send(404, {"error": f"нет метода {e}"})
            except Exception as e:
                return self._send(400, {"error": str(e)})

        def do_GET(self):
            self._handle()

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
            except Exception:
                return self._send(400, {"error": "плохой JSON"})
            self._handle(body)

    return H


_server = None


def start(data: GameData | None = None, port: int = 0) -> str:
    """Запускает сервер в фоне (один раз). Возвращает адрес."""
    global _server
    if _server is None:
        _server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(App(data)))
        threading.Thread(target=_server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{_server.server_address[1]}/"


def open_window(url: str):
    """Edge в режиме приложения — выглядит как отдельная программа."""
    if sys.platform == "win32":
        for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"),
                     os.environ.get("LOCALAPPDATA")):
            if not base:
                continue
            edge = Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
            if edge.exists():
                profile = APP_DIR / "data" / "edge_profile"
                subprocess.Popen([str(edge), f"--app={url}", "--window-size=1280,860",
                                  f"--user-data-dir={profile}", "--no-first-run"],
                                 creationflags=0x08000000)  # CREATE_NO_WINDOW
                return
    webbrowser.open(url)


if __name__ == "__main__":
    u = start(port=int(sys.argv[1]) if len(sys.argv) > 1 else 8765)
    print("Главное окно:", u)
    open_window(u)
    threading.Event().wait()
