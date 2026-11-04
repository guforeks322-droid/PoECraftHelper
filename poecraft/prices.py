"""Цены валюты, эссенций и фоссилов с poe.ninja (в хаосах). Кэш на 1 час."""

from __future__ import annotations

import json
import time
import urllib.request

from .data import DATA_DIR

NINJA = "https://poe.ninja/poe1/api"
UA = {"User-Agent": "PoECraftHelper/0.2 (+github)"}
CACHE = DATA_DIR / "prices.json"
TTL = 3600

# Если poe.ninja недоступен — грубые значения, чтобы калькулятор всё равно работал
FALLBACK = {
    "Chaos Orb": 1, "Divine Orb": 350, "Exalted Orb": 3, "Orb of Alteration": 0.15,
    "Orb of Augmentation": 0.05, "Regal Orb": 0.15, "Orb of Transmutation": 0.01,
    "Orb of Alchemy": 0.2, "Orb of Scouring": 0.5, "Orb of Annulment": 10,
}


def _get(url: str):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def current_league() -> str:
    state = _get(f"{NINJA}/data/index-state")
    for lg in state.get("economyLeagues", []):
        n = lg["name"]
        if "Hardcore" not in n and n not in ("Standard", "Ruthless") and "Ruthless" not in n:
            return n
    return "Standard"


def fetch(league: str | None = None) -> dict:
    league = league or current_league()
    prices: dict[str, float] = {}
    for typ in ("Currency", "Essence", "Fossil", "Resonator"):
        try:
            d = _get(f"{NINJA}/economy/exchange/current/overview?league={league}&type={typ}")
        except Exception:
            continue
        names = {i["id"]: i["name"] for i in d.get("items", [])}
        for line in d.get("lines", []):
            n = names.get(line["id"])
            if n and line.get("primaryValue"):
                prices[n] = float(line["primaryValue"])
    prices["Chaos Orb"] = 1.0
    return {"league": league, "time": time.time(), "prices": prices}


class Prices:
    def __init__(self):
        self.league = "?"
        self.updated = 0.0
        self.table: dict[str, float] = dict(FALLBACK)
        self.source = "запасные цены"
        self._load_cache()

    def _load_cache(self):
        try:
            d = json.loads(CACHE.read_text(encoding="utf-8"))
            self._apply(d, "кэш poe.ninja")
        except Exception:
            pass

    def _apply(self, d: dict, source: str):
        self.table = {**FALLBACK, **d["prices"]}
        self.league = d["league"]
        self.updated = d["time"]
        self.source = source

    def refresh(self, force: bool = False) -> bool:
        if not force and time.time() - self.updated < TTL:
            return True
        try:
            d = fetch()
            if len(d["prices"]) < 5:
                return False
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            self._apply(d, "poe.ninja")
            return True
        except Exception:
            return False

    def get(self, name: str) -> float:
        return self.table.get(name, FALLBACK.get(name, 0.0))

    @property
    def divine(self) -> float:
        return self.get("Divine Orb") or 350

    def info(self) -> dict:
        return {"league": self.league, "source": self.source, "updated": self.updated,
                "divine": self.divine,
                "main": {k: self.get(k) for k in FALLBACK}}
