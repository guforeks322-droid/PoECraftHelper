"""Ссылки на официальный трейд Path of Exile.

Программа ничего не покупает и не шлёт запросов поиска сама: она только собирает ссылку
`pathofexile.com/trade/search/<лига>?q=<запрос>` и открывает её в браузере. Чтобы искать
по модам, нужен словарь «текст мода → id стата трейда» — его один раз скачиваем с
pathofexile.com/api/trade/data/stats (как делают другие помощники) и кэшируем.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request

from .data import APP_DIR

STATS_URL = "https://{host}/api/trade/data/stats"
CACHE = APP_DIR / "data" / "trade_stats.json"
UA = {"User-Agent": "PoECraftHelper (github.com/guforeks322-droid/PoECraftHelper)"}
RANGE_RE = re.compile(r"\(?(-?[\d.]+)-(-?[\d.]+)\)?")
NUM_RE = re.compile(r"[+-]?\d+(?:\.\d+)?")


def host(lang: str = "en") -> str:
    return "ru.pathofexile.com" if lang == "ru" else "www.pathofexile.com"


def normalize(text: str) -> str:
    """'+(130-144) to maximum Life' и '+140 to maximum Life' → '+# to maximum life'."""
    t = RANGE_RE.sub("#", text.split("\n")[0])
    t = NUM_RE.sub(lambda m: ("+" if m.group(0).startswith("+") else "") + "#", t)
    t = t.replace("+#", "+#").replace("##", "#")
    return re.sub(r"\s+", " ", t).strip().lower()


def load_stats(fetch: bool = True) -> dict[str, str]:
    """{нормализованный текст: id} для явных модов (explicit) и модов влияния/крафта."""
    raw = None
    try:
        raw = json.loads(CACHE.read_text(encoding="utf-8"))
    except Exception:
        pass
    if raw is None and fetch:
        try:
            req = urllib.request.Request(STATS_URL.format(host=host()), headers=UA)
            with urllib.request.urlopen(req, timeout=20) as r:
                raw = json.loads(r.read().decode("utf-8"))
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(json.dumps(raw), encoding="utf-8")
        except Exception:
            raw = None
    return stats_index(raw) if raw else {}


def stats_index(raw: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for group in raw.get("result", []):
        if group.get("id") not in ("explicit", "crafted", "fractured"):
            continue
        for e in group.get("entries", []):
            key = normalize(e.get("text", ""))
            if group["id"] == "explicit" or key not in out:
                out.setdefault(key, e["id"].replace("crafted.", "explicit.").replace("fractured.", "explicit."))
    return out


def min_value(mod_text: str) -> float | None:
    """Нижняя граница первого диапазона мода: «+(130-144) to maximum Life» → 130."""
    m = RANGE_RE.search(mod_text)
    if not m:
        return None
    lo, hi = float(m.group(1)), float(m.group(2))
    v = min(lo, hi) if lo >= 0 else max(lo, hi)
    return int(v) if v.is_integer() else v


def search_url(league: str, query: dict, lang: str = "en") -> str:
    q = json.dumps({"query": query, "sort": {"price": "asc"}}, ensure_ascii=False, separators=(",", ":"))
    return f"https://{host(lang)}/trade/search/{urllib.parse.quote(league)}?q={urllib.parse.quote(q)}"


def base_query(base_name: str, ilvl: int | None = None, influence: str | None = None) -> dict:
    """Белая (обычная) база нужного ilvl, неосквернённая — для крафта."""
    misc = {"corrupted": {"option": "false"}}
    if ilvl:
        misc["ilvl"] = {"min": int(ilvl)}
    if influence:
        misc[f"{influence.lower()}_item"] = {"option": "true"}
    return {"status": {"option": "online"}, "type": base_name,
            "filters": {"type_filters": {"filters": {"rarity": {"option": "normal"}}},
                        "misc_filters": {"filters": misc}}}


def mods_query(base_name: str | None, mods: list[tuple[str, float | None]], stats: dict[str, str],
               ilvl: int | None = None) -> tuple[dict, list[str]]:
    """Готовый предмет с модами. mods: [(текст мода, минимум)]. Возвращает запрос и тексты,
    которые не нашлись в словаре трейда (их придётся добавить руками)."""
    filters, missing = [], []
    for text, lo in mods:
        sid = stats.get(normalize(text))
        if not sid:
            missing.append(text.split("\n")[0])
            continue
        f = {"id": sid}
        if lo is not None:
            f["value"] = {"min": lo}
        filters.append(f)
    q = {"status": {"option": "online"}, "stats": [{"type": "and", "filters": filters}]}
    if base_name:
        q["type"] = base_name
    if ilvl:
        q["filters"] = {"misc_filters": {"filters": {"ilvl": {"min": int(ilvl)}}}}
    return q, missing
