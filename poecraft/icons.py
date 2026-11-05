"""Иконки валюты, эссенций, фоссилов и влияний.

Картинки не лежат в программе: при первом запуске список берётся у poe.ninja,
а сами PNG скачиваются с CDN игры (web.poecdn.com) в data/icons и дальше
работают офлайн. Если интернета нет — интерфейс просто остаётся без иконок.
"""

from __future__ import annotations

import json
import re
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .data import APP_DIR

ICON_DIR = APP_DIR / "data" / "icons"
INDEX = ICON_DIR / "index.json"
ART_DIR = ICON_DIR / "items"
CDN = "https://web.poecdn.com"
NINJA = "https://poe.ninja/poe1/api/economy/exchange/current/overview?league={league}&type={typ}"
TYPES = ("Currency", "Essence", "Fossil", "Resonator")
UA = {"User-Agent": "PoECraftHelper (icons)"}

# Влияния и Eldritch рисуем иконками соответствующей валюты
INFLUENCE_ICON = {
    "Shaper": "Shaper's Exalted Orb", "Elder": "Elder's Exalted Orb",
    "Crusader": "Crusader's Exalted Orb", "Redeemer": "Redeemer's Exalted Orb",
    "Hunter": "Hunter's Exalted Orb", "Warlord": "Warlord's Exalted Orb",
    "Exarch": "Greater Eldritch Ember", "Eater": "Greater Eldritch Ichor",
}
INFLUENCE_COLOR = {
    "Shaper": "#5aa9e6", "Elder": "#b07cd8", "Crusader": "#e8e8e8", "Redeemer": "#79c2e8",
    "Hunter": "#7ecb72", "Warlord": "#e0a040", "Exarch": "#e8743b", "Eater": "#6fd0b8",
}
# Короткие названия кнопок эмулятора → полное имя предмета
ALIASES = {
    "Transmutation": "Orb of Transmutation", "Alteration": "Orb of Alteration",
    "Augmentation": "Orb of Augmentation", "Regal": "Regal Orb", "Alchemy": "Orb of Alchemy",
    "Chaos": "Chaos Orb", "Exalted": "Exalted Orb", "Annulment": "Orb of Annulment",
    "Scouring": "Orb of Scouring", "Divine": "Divine Orb", "Eldritch Chaos": "Eldritch Chaos Orb",
    "Eldritch Exalt": "Eldritch Exalted Orb", "Eldritch Annul": "Eldritch Orb of Annulment",
    "Veiled Chaos": "Veiled Chaos Orb", "Veiled Exalt": "Veiled Exalted Orb",
    "Exalt": "Exalted Orb", "Annul": "Orb of Annulment", "Aug": "Orb of Augmentation",
    "Alt": "Orb of Alteration", "Scour": "Orb of Scouring", "Transmute": "Orb of Transmutation",
    "Wild lifeforce": "Wild Crystallised Lifeforce", "Vivid lifeforce": "Vivid Crystallised Lifeforce",
    "Primal lifeforce": "Primal Crystallised Lifeforce", "Sacred lifeforce": "Sacred Crystallised Lifeforce",
    "Unveil": "Veiled Chaos Orb",
}


ESSENCE_TIERS = ("Deafening", "Shrieking", "Screaming", "Wailing", "Weeping", "Muttering", "Whispering")


def slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_") or "x"


def fetch_index(league: str | None = None) -> dict[str, str]:
    """{имя предмета: url картинки}. Берёт все типы, включая Chaos/Divine из блока core.
    В одной лиге торгуется не всё, поэтому объединяем текущую лигу и Standard."""
    leagues = [league] if league else []
    if not league:
        try:
            from .prices import current_league
            leagues.append(current_league())
        except Exception:
            pass
        leagues.append("Standard")
    out: dict[str, str] = {}
    for lg in dict.fromkeys(leagues):
        for name, url in _fetch_league(lg).items():
            out.setdefault(name, url)
    return out


def _fetch_league(league: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for typ in TYPES:
        try:
            req = urllib.request.Request(NINJA.format(league=league, typ=typ), headers=UA)
            with urllib.request.urlopen(req, timeout=20) as r:
                d = json.loads(r.read().decode("utf-8"))
        except Exception:
            continue
        for it in d.get("items", []) + (d.get("core") or {}).get("items", []):
            img = it.get("image")
            if it.get("name") and img:
                out[it["name"]] = img if img.startswith("http") else CDN + img
    return out


def resolve(name: str) -> str:
    """Имя из интерфейса → имя предмета в индексе."""
    n = (name or "").strip()
    n = re.sub(r"\s*\(.*?\)\s*$", "", n)       # «Regal Orb (x2)» → «Regal Orb»
    return INFLUENCE_ICON.get(n) or ALIASES.get(n) or n


def find_in_text(text: str, names) -> str | None:
    """Самое длинное имя предмета, которое встречается в тексте совета («Спам: Shrieking Essence of Anger»)."""
    low = (text or "").lower()
    best = None
    for n in list(names) + list(ALIASES) + ["Crafting Bench"]:
        if len(n) > 3 and n.lower() in low and (best is None or len(n) > len(best)):
            best = n
    if best is None and ("верстак" in low or "bench" in low):
        best = "Crafting Bench"
    return best


def find_all(text: str, names, limit: int = 4) -> list[str]:
    """Все предметы из текста по порядку появления (без вложенных: «Chaos Orb» внутри «Eldritch Chaos Orb»)."""
    low = (text or "").lower()
    hits = []
    for n in set(names) | set(ALIASES):
        if len(n) <= 3:
            continue
        i = low.find(n.lower())
        while i >= 0:
            hits.append((i, i + len(n), n))
            i = low.find(n.lower(), i + 1)
    hits.sort(key=lambda h: (h[0], -(h[1] - h[0])))
    out, end = [], -1
    for a, b, n in hits:
        if a >= end:
            out.append(n)
            end = b
    seen = []
    for n in out:
        if resolve(n) not in [resolve(x) for x in seen]:
            seen.append(n)
    return seen[:limit]


class IconStore:
    """Иконки для tkinter. get() никогда не блокирует: если картинки ещё нет, вернёт None,
    а когда фоновая загрузка закончится — вызовет подписчиков (перерисовать интерфейс)."""

    def __init__(self, root):
        self.root = root
        self.index: dict[str, str] = {}
        self._img: dict[tuple, object] = {}
        self._subs: list = []
        self._art_pending: set = set()
        self.ready = False
        try:
            self.index = json.loads(INDEX.read_text(encoding="utf-8"))
        except Exception:
            pass
        threading.Thread(target=self._sync, daemon=True).start()

    # ------------------------------------------------------------ загрузка
    def _sync(self):
        ICON_DIR.mkdir(parents=True, exist_ok=True)
        if len(self.index) < 150:
            idx = fetch_index()
            if idx:
                self.index = idx
                try:
                    INDEX.write_text(json.dumps(idx, ensure_ascii=False, indent=0), encoding="utf-8")
                except OSError:
                    pass
        missing = [(n, u) for n, u in self.index.items() if not (ICON_DIR / f"{slug(n)}.png").exists()]

        def dl(item):
            n, u = item
            try:
                req = urllib.request.Request(u, headers=UA)
                with urllib.request.urlopen(req, timeout=20) as r:
                    data = r.read()
                if data[:4] == b"\x89PNG":
                    (ICON_DIR / f"{slug(n)}.png").write_bytes(data)
            except Exception:
                pass
        if missing:
            with ThreadPoolExecutor(8) as ex:
                list(ex.map(dl, missing))
        self.ready = True
        try:
            self.root.after(0, self._notify)
        except Exception:
            pass

    def subscribe(self, fn):
        self._subs.append(fn)
        if self.ready:
            fn()

    def _notify(self):
        for fn in list(self._subs):
            try:
                fn()
            except Exception:
                pass

    # ------------------------------------------------------------ картинки
    # ------------------------------------------------------------ картинки предметов (баз)
    def base_art(self, base_id: str, dds: str, max_h: int = 150, max_w: int = 110):
        """Картинка базы предмета, как в инвентаре игры. Нет файла — скачиваем в фоне и зовём подписчиков."""
        key = ("art", base_id, max_h, max_w)
        if key in self._img:
            return self._img[key]
        p = ART_DIR / f"{slug(base_id)}.png"
        if not p.exists():
            if dds and base_id not in self._art_pending:
                self._art_pending.add(base_id)
                threading.Thread(target=self._dl_art, args=(base_id, dds, p), daemon=True).start()
            return None
        try:
            from PIL import Image, ImageTk
            im = Image.open(p).convert("RGBA")
            im.thumbnail((max_w, max_h), Image.LANCZOS)
            img = ImageTk.PhotoImage(im, master=self.root)
        except Exception:
            try:
                import tkinter as tk
                img = tk.PhotoImage(file=str(p), master=self.root)
            except Exception:
                img = None
        self._img[key] = img
        return img

    def _dl_art(self, base_id, dds, path):
        url = f"{CDN}/image/{dds.rsplit('.', 1)[0]}.png?scale=1"
        try:
            ART_DIR.mkdir(parents=True, exist_ok=True)
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=20) as r:
                data = r.read()
            if data[:4] == b"\x89PNG":
                path.write_bytes(data)
                self.root.after(0, self._notify)
        except Exception:
            pass

    def find_all(self, text: str, limit: int = 4) -> list[str]:
        return find_all(text, self.index, limit)

    def find(self, text: str) -> str | None:
        return find_in_text(text, self.index)

    def path(self, name: str) -> Path | None:
        n = resolve(name)
        p = ICON_DIR / f"{slug(n)}.png"
        if p.exists():
            return p
        # редкие тиры эссенций не торгуются — берём картинку соседнего тира того же вида
        m = re.match(r"(\w+) (Essence of (.+))", n)
        if m:
            for tier in ESSENCE_TIERS:
                q = ICON_DIR / f"{slug(tier + ' ' + m.group(2))}.png"
                if q.exists():
                    return q
            # этого вида эссенции нет в торговле — картинку берём прямо с CDN игры по её пути
            kind = m.group(3).replace(" ", "")
            num = {t: 7 - i for i, t in enumerate(ESSENCE_TIERS)}.get(m.group(1), 6)
            self._dl_direct(n, f"{CDN}/image/Art/2DItems/Currency/Essence/{kind}{num}.png?scale=1", p)
        return None

    def _dl_direct(self, name, url, path):
        if name in self._art_pending:
            return
        self._art_pending.add(name)

        def run():
            try:
                req = urllib.request.Request(url, headers=UA)
                with urllib.request.urlopen(req, timeout=20) as r:
                    data = r.read()
                if data[:4] == b"\x89PNG":
                    path.write_bytes(data)
                    self.root.after(0, self._notify)
            except Exception:
                pass
        threading.Thread(target=run, daemon=True).start()

    def get(self, name: str, size: int = 24):
        key = (resolve(name), size)
        if key in self._img:
            return self._img[key]
        p = self.path(name)
        if not p:
            return None
        img = None
        try:
            from PIL import Image, ImageTk
            im = Image.open(p).convert("RGBA")
            im.thumbnail((size, size), Image.LANCZOS)
            canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            canvas.paste(im, ((size - im.width) // 2, (size - im.height) // 2), im)
            img = ImageTk.PhotoImage(canvas, master=self.root)
        except Exception:
            try:
                import tkinter as tk
                img = tk.PhotoImage(file=str(p), master=self.root)
                k = max(1, round(img.width() / size))
                if k > 1:
                    img = img.subsample(k)
            except Exception:
                img = None
        self._img[key] = img
        return img


_store: IconStore | None = None


def store(root=None) -> IconStore | None:
    """Одно хранилище на программу. Первый вызов с root его создаёт."""
    global _store
    if _store is None and root is not None:
        _store = IconStore(root)
    return _store
