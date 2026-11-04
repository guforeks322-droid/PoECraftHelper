"""Крафты (цели): сохранение, загрузка и коды для обмена.

Код крафта: "PCH1:" + base64url(zlib(json)). Короткий, влезает в сообщение
Discord/Telegram, как PoB-код.
"""

from __future__ import annotations

import base64
import json
import re
import zlib
from pathlib import Path

PREFIX = "PCH1:"
FORMAT_VERSION = 1
CODE_RE = re.compile(r"PCH1:[A-Za-z0-9_\-]+=*")

# Классы предметов, для которых имеет смысл крафт (как в RePoE)
CRAFT_CLASSES = [
    "Belt", "Ring", "Amulet", "Body Armour", "Helmet", "Gloves", "Boots", "Shield", "Quiver",
    "Jewel", "AbyssJewel", "Wand", "Bow", "Claw", "Dagger", "Rune Dagger", "One Hand Sword",
    "Thrusting One Hand Sword", "One Hand Axe", "One Hand Mace", "Sceptre", "Two Hand Sword",
    "Two Hand Axe", "Two Hand Mace", "Staff", "Warstaff", "LifeFlask", "ManaFlask",
    "HybridFlask", "UtilityFlask",
]

CLASS_RU = {
    "Belt": "Пояс", "Ring": "Кольцо", "Amulet": "Амулет", "Body Armour": "Нагрудник",
    "Helmet": "Шлем", "Gloves": "Перчатки", "Boots": "Ботинки", "Shield": "Щит",
    "Quiver": "Колчан", "Jewel": "Самоцвет", "AbyssJewel": "Самоцвет Бездны", "Wand": "Жезл",
    "Bow": "Лук", "Claw": "Когти", "Dagger": "Кинжал", "Rune Dagger": "Рунический кинжал",
    "One Hand Sword": "Одноручный меч", "Thrusting One Hand Sword": "Колющий меч",
    "One Hand Axe": "Одноручный топор", "One Hand Mace": "Одноручная булава", "Sceptre": "Скипетр",
    "Two Hand Sword": "Двуручный меч", "Two Hand Axe": "Двуручный топор",
    "Two Hand Mace": "Двуручная булава", "Staff": "Посох", "Warstaff": "Боевой посох",
    "LifeFlask": "Флакон жизни", "ManaFlask": "Флакон маны", "HybridFlask": "Гибридный флакон",
    "UtilityFlask": "Флакон-утилита",
}


def recipe_from_dict(d: dict) -> dict:
    """Проверяет и нормализует крафт. Бросает ValueError, если что-то не так."""
    if not isinstance(d, dict):
        raise ValueError("Крафт должен быть объектом JSON.")
    name = str(d.get("name", "")).strip()
    if not name:
        raise ValueError("У крафта нет названия.")
    wanted = d.get("wanted")
    if not isinstance(wanted, list) or not wanted:
        raise ValueError("В крафте нет ни одного нужного мода.")
    out_w = []
    for w in wanted[:12]:
        if not isinstance(w, dict) or not (w.get("mod_type") or w.get("pattern")):
            raise ValueError("Нужный мод описан неверно.")
        pattern = str(w.get("pattern", ""))
        if pattern:
            re.compile(pattern)  # кривой regex -> ошибка сразу
        out_w.append({
            "label": str(w.get("label", w.get("mod_type", "")))[:80],
            "mod_type": str(w.get("mod_type", "")),
            "kind": w.get("kind") if w.get("kind") in ("prefix", "suffix") else "",
            "pattern": pattern,
            "max_tier": max(1, min(99, int(w.get("max_tier", 99)))),
        })
    return {
        "v": FORMAT_VERSION,
        "name": name[:100],
        "author": str(d.get("author", ""))[:40],
        "description": str(d.get("description", ""))[:500],
        "base_class": str(d.get("base_class", "")) or None,
        "base": str(d.get("base", "")) or None,
        "min_ilvl": int(d["min_ilvl"]) if d.get("min_ilvl") else None,
        "wanted": out_w,
    }


def encode(recipe: dict) -> str:
    raw = json.dumps(recipe_from_dict(recipe), ensure_ascii=False, separators=(",", ":")).encode()
    return PREFIX + base64.urlsafe_b64encode(zlib.compress(raw, 9)).decode().rstrip("=")


def decode(code: str) -> dict:
    m = CODE_RE.search(code.strip())
    if not m:
        raise ValueError("Не нашёл код крафта (он начинается с PCH1:).")
    body = m.group(0)[len(PREFIX):]
    body += "=" * (-len(body) % 4)
    try:
        raw = zlib.decompress(base64.urlsafe_b64decode(body))
        d = json.loads(raw)
    except Exception:
        raise ValueError("Код крафта повреждён — скопируй его целиком.")
    return recipe_from_dict(d)


_TR = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
               ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p",
                "r", "s", "t", "u", "f", "h", "ts", "ch", "sh", "sch", "", "y", "", "e", "yu", "ya"]))


def slugify(name: str) -> str:
    """Имя файла только из латиницы — без проблем с кодировками у любого пользователя."""
    s = "".join(_TR.get(c, _TR.get(c.lower(), c).capitalize() if c.lower() in _TR else c) for c in name)
    s = re.sub(r"[^A-Za-z0-9\- ]+", "", s).strip().replace(" ", "_")
    return (s or "craft")[:50]


def save(recipe: dict, folder: Path, filename: str | None = None) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    rec = recipe_from_dict(recipe)
    path = folder / (filename or f"{slugify(rec['name'])}.json")
    if filename is None:
        i = 2
        while path.exists():
            path = folder / f"{slugify(rec['name'])}_{i}.json"
            i += 1
    path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    return path
