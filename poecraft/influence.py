"""Влияния (Shaper/Elder/завоеватели) и Eldritch-импликиты (Searing Exarch / Eater of Worlds)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .data import GameData, ModDef
from . import currency_craft as cc

# суффикс тега влияния в данных → название
INFLUENCE_NAMES = {
    "shaper": "Shaper", "elder": "Elder", "crusader": "Crusader",
    "eyrie": "Redeemer", "basilisk": "Hunter", "adjudicator": "Warlord",
}
INFLUENCE_RU = {"Shaper": "Создатель", "Elder": "Древний", "Crusader": "Крестоносец",
                "Redeemer": "Избавительница", "Hunter": "Охотник", "Warlord": "Вождь"}
CONQUEROR_ORBS = {"Crusader": "Crusader's Exalted Orb", "Redeemer": "Redeemer's Exalted Orb",
                  "Hunter": "Hunter's Exalted Orb", "Warlord": "Warlord's Exalted Orb"}

ELDRITCH_TIERS = {1: "Lesser", 2: "Greater", 3: "Grand", 4: "Exceptional", 5: "Exquisite", 6: "Perfect"}
ELDRITCH_CLASSES = {"gloves", "boots", "helmet", "body_armour"}


def influence_tags(data: GameData, item_class: str) -> dict[str, str]:
    """{'Shaper': 'belt_shaper', ...} для класса предмета."""
    if not hasattr(data, "_item_classes"):
        data._item_classes = data._load("item_classes")
    ic = data._item_classes.get(item_class, {})
    out = {}
    for tag in ic.get("influence_tags", []) or []:
        suf = tag.rsplit("_", 1)[-1]
        if suf in INFLUENCE_NAMES:
            out[INFLUENCE_NAMES[suf]] = tag
    order = list(INFLUENCE_NAMES.values())
    return dict(sorted(out.items(), key=lambda kv: order.index(kv[0])))


_INF_SUFFIXES = tuple("_" + k for k in INFLUENCE_NAMES)


def is_influence_mod(mod: ModDef) -> bool:
    """Мод выпадает только при влиянии: положительный вес есть лишь у тегов влияния."""
    if "influence_mod" in mod.tags:
        return True
    pos = [sw["tag"] for sw in mod.spawn_weights if sw["weight"] > 0]
    return bool(pos) and all(t.endswith(_INF_SUFFIXES) for t in pos)


def influence_of(mod: ModDef, tags: dict[str, str]) -> str | None:
    for name, tag in tags.items():
        for sw in mod.spawn_weights:
            if sw["tag"] == tag and sw["weight"] > 0:
                return name
    return None


# ------------------------------------------------------------------ Eldritch
@dataclass
class EldritchMod:
    id: str
    side: str        # exarch / eater
    level: int       # 1..6 (Lesser … Perfect)
    type: str
    text: str
    weight: int


def eldritch_pool(data: GameData, base_tags: set[str], side: str) -> list[EldritchMod]:
    gen = "searing_exarch_implicit" if side == "exarch" else "eater_of_worlds_implicit"
    raw = cc._raw_mods(data)
    out = []
    for mid, m in raw.items():
        if m.get("generation_type") != gen or m.get("domain") != "item":
            continue
        w = 0
        for sw in m.get("spawn_weights", []):
            if sw["tag"] in base_tags:
                w = sw["weight"]
                break
        if w <= 0:
            continue
        mm = re.search(r"(\d+)_*$", mid)
        lvl = int(mm.group(1)) if mm else 1
        out.append(EldritchMod(mid, side, lvl, m.get("type", ""), (m.get("text") or "").replace("\n", " / "), w))
    return out


def eldritch_supported(base_tags: set[str]) -> bool:
    return bool(ELDRITCH_CLASSES & base_tags)
