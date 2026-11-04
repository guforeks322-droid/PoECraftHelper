"""Разбор текста предмета, скопированного в игре через Ctrl+Alt+C (английский и русский клиент)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

HEADER_RE = re.compile(
    r'\{\s*(?P<extra>[^"{}]*?)\s*(?P<kind>Prefix|Suffix|[Пп]рефикс|[Сс]уффикс)(?:\s+Modifier)?\s+"(?P<name>[^"]+)"'
    r'(?:\s*\((?:Tier|Rank|Уровень|Ранг|Ступень):\s*(?P<tier>\d+)\))?'
)

# служебные строки: (английский, русский)
LABELS = {
    "item_class": ("Item Class:", "Класс предмета:"),
    "rarity": ("Rarity:", "Редкость:"),
    "ilvl": ("Item Level:", "Уровень предмета:"),
}
RARITY_RU = {"Обычный": "Normal", "Магический": "Magic", "Редкий": "Rare", "Уникальный": "Unique",
             "Обычная": "Normal", "Магическая": "Magic", "Редкая": "Rare", "Уникальная": "Unique"}
CORRUPTED = ("Corrupted", "Осквернено", "Осквернён", "Осквернен")
MIRRORED = ("Mirrored", "Отражено", "Зеркальная копия")
INFLUENCES = ["Shaper", "Elder", "Crusader", "Redeemer", "Hunter", "Warlord"]
INFLUENCES_RU = {"Создател": "Shaper", "Древн": "Elder", "Крестонос": "Crusader",
                 "Избавител": "Redeemer", "Охотни": "Hunter", "Вожд": "Warlord"}
CRAFTED_WORDS = ("Crafted", "Мастер", "Ремесл", "Создан")
CLEAN_SUFFIX = re.compile(r"\s*\((crafted|fractured|implicit|enchant|rune|augmented)\)\s*$")


@dataclass
class ParsedMod:
    kind: str           # prefix / suffix
    name: str           # имя аффикса (как в клиенте)
    tier: int | None    # тир, как его показывает игра
    lines: list[str] = field(default_factory=list)
    crafted: bool = False
    fractured: bool = False

    @property
    def text(self) -> str:
        return " / ".join(self.lines)


@dataclass
class ParsedItem:
    item_class: str = ""
    rarity: str = ""
    name: str = ""
    base_name: str = ""
    ilvl: int = 0
    corrupted: bool = False
    mirrored: bool = False
    influences: list[str] = field(default_factory=list)
    mods: list[ParsedMod] = field(default_factory=list)
    language: str = "en"

    @property
    def prefixes(self):
        return [m for m in self.mods if m.kind == "prefix"]

    @property
    def suffixes(self):
        return [m for m in self.mods if m.kind == "suffix"]


class ParseError(ValueError):
    pass


def looks_like_item(text: str) -> bool:
    return bool(text) and any(l in text for l in LABELS["rarity"]) and any(l in text for l in LABELS["item_class"])


def _label(line: str, key: str) -> str | None:
    for lab in LABELS[key]:
        if line.startswith(lab):
            return line[len(lab):].strip()
    return None


def parse_item(text: str) -> ParsedItem:
    text = text.replace("\r", "")
    if not any(l in text for l in LABELS["rarity"]):
        raise ParseError("Это не похоже на текст предмета PoE (нет строки Rarity / Редкость).")

    sections = [s.strip().split("\n") for s in text.split("--------")]
    item = ParsedItem()
    item.language = "ru" if "Редкость:" in text else "en"

    head = [l.strip() for l in sections[0] if l.strip()]
    for i, line in enumerate(head):
        v = _label(line, "item_class")
        if v is not None:
            item.item_class = v
            continue
        v = _label(line, "rarity")
        if v is not None:
            item.rarity = RARITY_RU.get(v, v)
            rest = head[i + 1:]
            if item.rarity == "Rare" and len(rest) >= 2:
                item.name, item.base_name = rest[0], rest[1]
            elif rest:
                item.name = item.base_name = rest[0]  # Magic/Normal: база внутри названия

    current: ParsedMod | None = None
    for sec in sections[1:]:
        for raw in sec:
            line = raw.strip()
            if not line:
                continue
            v = _label(line, "ilvl")
            if v is not None:
                try:
                    item.ilvl = int(v.split()[0])
                except ValueError:
                    pass
            elif line in CORRUPTED:
                item.corrupted = True
            elif line in MIRRORED:
                item.mirrored = True
            elif line.endswith(" Item") and line.split()[0] in INFLUENCES:
                item.influences.append(line.split()[0])
            elif line.startswith("Предмет "):
                for stem, name in INFLUENCES_RU.items():
                    if stem in line and name not in item.influences:
                        item.influences.append(name)

            m = HEADER_RE.search(line)
            if m:
                kind = "prefix" if m["kind"].lower().startswith(("p", "п")) else "suffix"
                current = ParsedMod(
                    kind=kind,
                    name=m["name"],
                    tier=int(m["tier"]) if m["tier"] else None,
                    crafted=any(w in (m["extra"] or "") for w in CRAFTED_WORDS),
                )
                item.mods.append(current)
                continue
            if line.startswith("{"):
                current = None  # implicit / unique / enchant — не наши аффиксы
                continue
            # строки-пояснения в скобках пропускаем, но "(14-15)% reduced…" — это сам мод
            if current is not None and (not line.startswith("(") or re.match(r"\(\d", line)):
                if line.endswith("(fractured)"):
                    current.fractured = True
                if line.endswith("(crafted)"):
                    current.crafted = True
                current.lines.append(CLEAN_SUFFIX.sub("", line))
        current = None
    return item


VALUE_RE = re.compile(r"-?\d+(?:\.\d+)?\((-?[\d.]+)-(-?[\d.]+)\)")


def canonical(line: str) -> str:
    """'+140(130-144) to maximum Life' → '+(130-144) to maximum life' — как текст мода в RePoE."""
    s = VALUE_RE.sub(lambda m: f"({m.group(1)}-{m.group(2)})", line)
    return re.sub(r"\s+", " ", s).strip().lower()
