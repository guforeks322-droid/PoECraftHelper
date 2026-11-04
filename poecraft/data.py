"""Загрузка и индексация игровых данных из RePoE (https://repoe-fork.github.io).

Данные кэшируются в папке data/. Обновить после патча:
    python -m poecraft.cli --update
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

BASE_URL = "https://repoe-fork.github.io"
FILES = ["mods", "base_items", "essences", "fossils", "crafting_bench_options", "item_classes", "cluster_jewels"]
import sys as _sys

# В собранном .exe данные лежат рядом с exe, а не внутри него
APP_DIR = (Path(_sys.executable).resolve().parent if getattr(_sys, "frozen", False)
           else Path(__file__).resolve().parent.parent)
DATA_DIR = APP_DIR / "data"


FILES_RU = ["base_items", "mods"]   # для русского клиента игры


def download(data_dir: Path = DATA_DIR, verbose: bool = True, russian: bool = True) -> str:
    """Скачивает свежие файлы RePoE. Возвращает версию данных."""
    data_dir.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        url = f"{BASE_URL}/{name}.min.json"
        if verbose:
            print(f"  скачиваю {url}")
        with urllib.request.urlopen(url, timeout=120) as r:
            (data_dir / f"{name}.json").write_bytes(r.read())
    if russian:
        (data_dir / "ru").mkdir(exist_ok=True)
        for name in FILES_RU:
            url = f"{BASE_URL}/Russian/{name}.min.json"
            if verbose:
                print(f"  скачиваю {url}")
            with urllib.request.urlopen(url, timeout=180) as r:
                (data_dir / "ru" / f"{name}.json").write_bytes(r.read())
    try:
        with urllib.request.urlopen(f"{BASE_URL}/version.txt", timeout=30) as r:
            version = r.read().decode().strip()
    except Exception:
        version = "unknown"
    (data_dir / "version.txt").write_text(version)
    return version


@dataclass(frozen=True)
class ModDef:
    id: str
    name: str            # имя аффикса, например "Fecund" / "of the Kiln"
    kind: str            # "prefix" | "suffix"
    type: str            # "IncreasedLife" — тиры одного мода имеют один type
    groups: tuple        # моды из одной группы не могут быть на предмете вместе
    level: int           # минимальный ilvl
    text: str            # "+(130-144) to maximum Life"
    tags: tuple          # implicit_tags: life, resistance, fire ...
    spawn_weights: tuple
    generation_weights: tuple

    def weight_for(self, item_tags: set[str]) -> int:
        """Вес выпадения: берётся первый тег из списка, который есть у предмета."""
        w = 0
        for sw in self.spawn_weights:
            if sw["tag"] in item_tags:
                w = sw["weight"]
                break
        # generation_weights — множители (их меняют, например, фоссилы и влияния)
        for gw in self.generation_weights:
            if gw["tag"] in item_tags:
                w = w * gw["weight"] // 100
                break
        return w


@dataclass(frozen=True)
class BaseItem:
    id: str
    name: str
    item_class: str
    domain: str
    tags: frozenset


class GameData:
    def __init__(self, data_dir: Path = DATA_DIR):
        self.dir = data_dir
        if not (data_dir / "mods.json").exists():
            print("Данных нет, скачиваю RePoE…")
            download(data_dir)

    def _load(self, name: str):
        return json.loads((self.dir / f"{name}.json").read_text(encoding="utf-8"))

    @property
    def version(self) -> str:
        p = self.dir / "version.txt"
        return p.read_text().strip() if p.exists() else "unknown"

    @cached_property
    def mods(self) -> dict[str, ModDef]:
        out = {}
        for mid, m in self._load("mods").items():
            if m.get("generation_type") not in ("prefix", "suffix"):
                continue
            if m.get("is_essence_only"):
                continue
            out[mid] = ModDef(
                id=mid,
                name=m.get("name", ""),
                kind=m["generation_type"],
                type=m.get("type", ""),
                groups=tuple(m.get("groups", [])),
                level=m.get("required_level", 1),
                text=m.get("text", "") or "",
                tags=tuple(m.get("implicit_tags", [])),
                spawn_weights=tuple(m.get("spawn_weights", [])),
                generation_weights=tuple(m.get("generation_weights", [])),
            )
            # domain храним отдельно, чтобы не раздувать dataclass
            self._domains[mid] = m.get("domain")
        return out

    @cached_property
    def _domains(self) -> dict[str, str]:
        return {}

    def mod_domain(self, mod_id: str) -> str:
        self.mods  # гарантируем загрузку
        return self._domains.get(mod_id, "")

    @cached_property
    def bases(self) -> dict[str, BaseItem]:
        """Индекс баз по имени (только выпускаемые в игре)."""
        out = {}
        for bid, b in self._load("base_items").items():
            if b.get("release_state") != "released":
                continue
            name = b["name"]
            # при дублях имени предпочитаем базу с доменом item/flask/misc
            if name in out and out[name].domain in ("item", "flask", "misc", "abyss_jewel"):
                continue
            out[name] = BaseItem(bid, name, b["item_class"], b["domain"], frozenset(b.get("tags", [])))
        return out

    @cached_property
    def bench(self) -> list[dict]:
        """Крафты верстака, добавляющие мод: текст, префикс/суффикс, группы, классы, цена."""
        raw_mods = self._load("mods")
        out = []
        for o in self._load("crafting_bench_options"):
            mid = o.get("actions", {}).get("add_explicit_mod")
            m = raw_mods.get(mid) if mid else None
            if not m or m.get("generation_type") not in ("prefix", "suffix"):
                continue
            out.append({
                "id": mid,
                "text": m.get("text", ""),
                "type": m.get("type", ""),
                "kind": m["generation_type"],
                "groups": tuple(m.get("groups", [])),
                "item_classes": set(o.get("item_classes", [])),
                "cost": {k.rsplit("/", 1)[-1]: v for k, v in o.get("cost", {}).items()},
            })
        return out

    # ---------------------------------------------------------- русский клиент
    @property
    def has_russian(self) -> bool:
        return (self.dir / "ru" / "base_items.json").exists() and (self.dir / "ru" / "mods.json").exists()

    @cached_property
    def ru_bases(self) -> dict[str, BaseItem]:
        """Русское название базы → BaseItem (английский)."""
        if not self.has_russian:
            return {}
        raw_en = self._load("base_items")
        raw_ru = json.loads((self.dir / "ru" / "base_items.json").read_text(encoding="utf-8"))
        out = {}
        for bid, b in raw_ru.items():
            en = raw_en.get(bid)
            if not en or en.get("release_state") != "released":
                continue
            base = self.bases.get(en["name"])
            if base and b.get("name") and b["name"] not in out:
                out[b["name"]] = base
        return out

    @cached_property
    def ru_mods(self) -> dict[str, tuple[str, frozenset]]:
        """id мода → (русский текст, все формы русского имени аффикса)."""
        if not self.has_russian:
            return {}
        import re as _re
        raw = json.loads((self.dir / "ru" / "mods.json").read_text(encoding="utf-8"))
        out = {}
        for mid, m in raw.items():
            if m.get("generation_type") not in ("prefix", "suffix"):
                continue
            name = m.get("name") or ""
            forms = set(_re.findall(r"\{([^{}]+)\}", name)) or {name}
            out[mid] = (m.get("text") or "", frozenset(f.strip() for f in forms if f.strip()))
        return out

    def find_base_any(self, text: str) -> BaseItem | None:
        b = self.find_base(text)
        if b:
            return b
        ru = self.ru_bases
        if text in ru:
            return ru[text]
        hits = [name for name in ru if name and name in text]
        return ru[max(hits, key=len)] if hits else None

    def find_base(self, text: str) -> BaseItem | None:
        """Ищет базу по строке (для синих предметов имя базы спрятано внутри названия)."""
        if text in self.bases:
            return self.bases[text]
        hits = [b for name, b in self.bases.items() if name and name in text]
        return max(hits, key=lambda b: len(b.name), default=None)
