"""Прайс-чек Timeless Jewel (Glorious Vanity, Lethal Pride, Brutal Restraint, Militant Faith,
Elegant Hubris, Heroic Tragedy) по сиду и завоевателю.

Цену таймлесса задаёт сид (какие ноды он даёт) и завоеватель (кейстоун). Поэтому ищем на
официальном трейде тот же сид: у того же завоевателя или у любого из этой серии. Id статов
трейда — `explicit.pseudo_timeless_jewel_<завоеватель>` (так же ищет калькулятор Vilsol).

Русский клиент: строки модов на русском берём из словаря статов ru.pathofexile.com
(`/api/trade/data/stats`). Из каждой строки с «#» делаем регулярку, поэтому язык клиента
не важен. Английские регулярки встроены на случай, если словарь не скачался.
"""

from __future__ import annotations

import json
import re
import statistics
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from .data import DATA_DIR

UA = {"User-Agent": "PoECraftHelper (github.com/guforeks322-droid/PoECraftHelper)",
      "Accept": "application/json"}
API = "https://www.pathofexile.com"
CACHE = DATA_DIR / "timeless_stats.json"
CACHE_TTL = 7 * 24 * 3600

# номер серии — как в калькуляторе Vilsol (vilsol.github.io/timeless-jewels), завоеватели оттуда же
JEWELS: dict[str, tuple[int, list[str]]] = {
    "Glorious Vanity": (1, ["Xibaqua", "Ahuana", "Doryani", "Zerphi"]),
    "Lethal Pride": (2, ["Kaom", "Rakiata", "Kiloava", "Akoya"]),
    "Brutal Restraint": (3, ["Asenath", "Nasima", "Balbala", "Deshret"]),
    "Militant Faith": (4, ["Avarius", "Dominus", "Maxarius", "Venarius"]),
    "Elegant Hubris": (5, ["Cadiro", "Victario", "Caspiro", "Chitus"]),
    "Heroic Tragedy": (6, ["Vorana", "Uhtred", "Medved"]),
}
CONQ_TO_JEWEL = {c.lower(): j for j, (_, cs) in JEWELS.items() for c in cs}

NUM = r"(\d+)(?:\s*\(\d+\s*-\s*\d+\))?"     # «8000» или «8000(2000-10000)» в расширенной копии
EN_PATTERNS = [
    rf"Bathed in the blood of {NUM} sacrificed in the name of (\w+)",
    rf"Commanded leadership over {NUM} warriors under (\w+)",
    rf"Denoted service of {NUM} dekhara in the akhara of (\w+)",
    rf"Carved to glorify {NUM} new faithful converted by High Templar (\w+)",
    rf"Commissioned {NUM} coins to commemorate (\w+)",
    rf"Remembrancing {NUM} songworthy deeds by the line of (\w+)",
]
# Русский клиент: тип джевела — по строке «Пассивные умения в радиусе завоёваны <фракция>»
# (англ. «Passives in radius are Conquered by the Vaal/Karui/…»), сид — первое число строки
# перед ней. Так не нужен словарь трейда и не важно, как переведено имя завоевателя.
FACTION_RU = [("ваал", "Glorious Vanity"), ("кару", "Lethal Pride"), ("маракет", "Brutal Restraint"),
              ("храмов", "Militant Faith"), ("темпл", "Militant Faith"), ("вечн", "Elegant Hubris"),
              ("калгу", "Heroic Tragedy")]
FACTION_EN = [("vaal", "Glorious Vanity"), ("karui", "Lethal Pride"), ("maraketh", "Brutal Restraint"),
              ("templar", "Militant Faith"), ("eternal", "Elegant Hubris"), ("kalguur", "Heroic Tragedy")]
CONQUERED_RE = re.compile(r"(?:завоев[а-яё]*|завоёв[а-яё]*|Conquered by)\s+(?:the\s+)?(.+)$", re.I)
# Известные русские имена завоевателей (дополняется словарём трейда, если он скачался)
CONQ_RU = {"ахвана": "Ahuana"}
CURRENCY_SHORT = {"chaos": "c", "divine": "div", "exalted": "ex", "mirror": "mirror"}


@dataclass
class TimelessJewel:
    jewel: str             # английское имя серии
    seed: int
    conqueror: str         # английское имя (Doryani); если не узнали — имя из клиента
    corrupted: bool = False
    extra: list[str] = field(default_factory=list)   # мод Devotion у Militant Faith

    @property
    def conqueror_known(self) -> bool:
        """Узнали ли английское имя (нужно для поиска «только свой» и ссылки на калькулятор)."""
        return self.conqueror in JEWELS[self.jewel][1]

    @property
    def vilsol_id(self) -> int:
        return JEWELS[self.jewel][0]

    @property
    def conquerors(self) -> list[str]:
        return JEWELS[self.jewel][1]

    def vilsol_url(self) -> str:
        """Ссылка на калькулятор Vilsol сразу в режиме «Enter Seed» с этим сидом.

        Калькулятор показывает поле сида только при mode=seed и известном завоевателе.
        Если английское имя завоевателя не узнали (русский клиент), передаём первого
        из серии: по словам самого калькулятора, завоеватель меняет только кейстоун,
        а ноды в радиусе от него не зависят."""
        conq = self.conqueror if self.conqueror_known else JEWELS[self.jewel][1][0]
        q = urllib.parse.urlencode({"jewel": self.vilsol_id, "conqueror": conq,
                                    "seed": self.seed, "mode": "seed"})
        return f"https://vilsol.github.io/timeless-jewels/tree?{q}"


# ---------------------------------------------------------------- словарь статов (рус/англ)
_patterns: list[tuple[re.Pattern, str | None]] | None = None   # (регулярка, завоеватель или None)
_lock = threading.Lock()


def _download_stats(host: str) -> list[dict]:
    req = urllib.request.Request(f"https://{host}/api/trade/data/stats", headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = json.loads(r.read().decode("utf-8"))
    out = []
    for group in raw.get("result", []):
        for e in group.get("entries", []):
            if "timeless_jewel_" in e.get("id", ""):
                out.append({"id": e["id"], "text": e.get("text", "")})
    return out


def load_entries(fetch: bool = True) -> list[dict]:
    """Строки модов таймлессов с трейда (англ + рус), кэш на неделю."""
    try:
        d = json.loads(CACHE.read_text(encoding="utf-8"))
        if time.time() - d.get("time", 0) < CACHE_TTL or not fetch:
            return d["entries"]
    except Exception:
        d = None
    if not fetch:
        return []
    entries = []
    for host in ("www.pathofexile.com", "ru.pathofexile.com"):
        try:
            entries += _download_stats(host)
        except Exception:
            pass
    if entries:
        try:
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(json.dumps({"time": time.time(), "entries": entries}, ensure_ascii=False),
                             encoding="utf-8")
        except Exception:
            pass
        return entries
    return d["entries"] if d else []


def _entry_regex(text: str) -> re.Pattern | None:
    if "#" not in text:
        return None
    parts = [re.escape(p) for p in text.split("#")]
    body = NUM.join(parts).replace("\\ ", " ").replace(" ", r"\s+")
    try:
        return re.compile(body, re.I)
    except re.error:
        return None


def patterns(fetch: bool = False) -> list[tuple[re.Pattern, str | None]]:
    global _patterns
    with _lock:
        if _patterns is not None and not fetch:
            return _patterns
        pats: list[tuple[re.Pattern, str | None]] = []
        for e in load_entries(fetch=fetch):
            rx = _entry_regex(e["text"])
            conq = e["id"].rsplit("_", 1)[-1]
            if rx and conq.lower() in CONQ_TO_JEWEL:
                pats.append((rx, conq))
                last = re.findall(r"[А-Яа-яЁё'-]+", e["text"])
                if last:               # «… во имя Дориани» → дориани: Doryani
                    jewel = CONQ_TO_JEWEL[conq.lower()]
                    CONQ_RU.setdefault(last[-1].lower(),
                                       next(c for c in JEWELS[jewel][1] if c.lower() == conq.lower()))
        pats += [(re.compile(p), None) for p in EN_PATTERNS]
        _patterns = pats
        return pats


def warm_up():
    """Скачать словарь в фоне (для русского клиента)."""
    threading.Thread(target=lambda: patterns(fetch=True), daemon=True).start()


# ---------------------------------------------------------------- разбор предмета
def _extras(jewel: str, text: str) -> tuple[list[str], bool]:
    extra = []
    if jewel == "Militant Faith":
        for line in text.split("\n"):
            line = re.sub(r"\s*\(\d+-\d+\)", "", line).strip()
            if ("Devotion" in line or "благочест" in line.lower()) and not line.startswith("{"):
                extra.append(line)
    corrupted = any(w in text for w in ("\nCorrupted", "\nОсквернено", "\nОсквернён", "\nОсквернен"))
    return extra, corrupted


def _parse_by_faction(text: str) -> TimelessJewel | None:
    """Запасной путь (в первую очередь для русского клиента): строка «… завоёваны <фракция>»
    даёт тип джевела, строка перед ней — сид (первое число) и завоевателя (последнее слово)."""
    lines = [l.strip() for l in text.split("\n")]
    for i, line in enumerate(lines):
        m = CONQUERED_RE.search(line)
        if not m or i == 0:
            continue
        who = m.group(1).lower()
        table = FACTION_RU if re.search("[а-яё]", who) else FACTION_EN
        jewel = next((j for key, j in table if key in who), None)
        if not jewel:
            continue
        seed_line = next((l for l in reversed(lines[:i]) if re.search(r"\d{2,}", l) and not l.startswith("{")), "")
        num = re.search(r"(\d+)", seed_line)
        if not num:
            continue
        word = re.findall(r"[A-Za-zА-Яа-яЁё'-]+", seed_line)
        raw = word[-1] if word else ""
        conq = _conqueror_name(jewel, raw)
        extra, corrupted = _extras(jewel, text)
        return TimelessJewel(jewel, int(num.group(1)), conq, corrupted, extra)
    return None


def _conqueror_name(jewel: str, raw: str) -> str:
    """Слово из клиента → английское имя завоевателя, если знаем; иначе как есть."""
    low = raw.lower()
    for c in JEWELS[jewel][1]:
        if c.lower() == low:
            return c
    for ru, en in CONQ_RU.items():           # русские падежи: «Ахваны», «Мазкотля» → по основе
        if low.startswith(ru[:max(4, len(ru) - 2)]) and en in JEWELS[jewel][1]:
            return en
    return raw


def parse(text: str) -> TimelessJewel | None:
    """Текст предмета (Ctrl+C / Ctrl+Alt+C, англ. или рус. клиент) → TimelessJewel или None."""
    if not text:
        return None
    text = text.replace("\r", "")
    for rx, conq in patterns():
        m = rx.search(text)
        if not m:
            continue
        seed = int(m.group(1))
        name = conq or (m.group(2) if m.lastindex and m.lastindex >= 2 else "")
        jewel = CONQ_TO_JEWEL.get(name.lower())
        if not jewel:
            continue
        conq_name = next(c for c in JEWELS[jewel][1] if c.lower() == name.lower())
        extra = []
        if jewel == "Militant Faith":
            for line in text.split("\n"):
                line = re.sub(r"\s*\(\d+-\d+\)", "", line).strip()
                if ("Devotion" in line or "благочест" in line.lower()) and not line.startswith("{"):
                    extra.append(line)
        corrupted = any(w in text for w in ("\nCorrupted", "\nОсквернено", "\nОсквернён", "\nОсквернен"))
        return TimelessJewel(jewel, seed, conq_name, corrupted, extra)
    return _parse_by_faction(text)


def is_timeless(text: str) -> bool:
    return parse(text) is not None


# ---------------------------------------------------------------- трейд
class TradeError(Exception):
    pass


_blocked_until = 0.0


def _request(url: str, body: dict | None = None):
    global _blocked_until
    if time.time() < _blocked_until:
        raise TradeError(f"Лимит запросов трейда, подожди {int(_blocked_until - time.time()) + 1} с")
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = dict(UA)
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 429:
            wait = int(e.headers.get("Retry-After") or 60)
            _blocked_until = time.time() + wait
            raise TradeError(f"Трейд просит подождать {wait} с (лимит запросов)")
        try:
            msg = json.loads(e.read().decode("utf-8")).get("error", {}).get("message", "")
        except Exception:
            msg = ""
        raise TradeError(f"Трейд ответил {e.code}{': ' + msg if msg else ''}")
    except urllib.error.URLError as e:
        raise TradeError(f"Нет связи с трейдом: {e.reason}")


def build_query(j: TimelessJewel, any_conqueror: bool = True, status: str = "online") -> dict:
    conqs = j.conquerors if (any_conqueror or not j.conqueror_known) else [j.conqueror]
    filters = [{"id": f"explicit.pseudo_timeless_jewel_{c.lower()}",
                "value": {"min": j.seed, "max": j.seed}} for c in conqs]
    return {"query": {"status": {"option": status},
                      "stats": [{"type": "count", "value": {"min": 1}, "filters": filters}],
                      "filters": {"trade_filters": {"filters": {"sale_type": {"option": "priced"}}}}},
            "sort": {"price": "asc"}}


def trade_url(league: str, query: dict, lang: str = "en") -> str:
    host = "ru.pathofexile.com" if lang == "ru" else "www.pathofexile.com"
    q = json.dumps(query, ensure_ascii=False, separators=(",", ":"))
    return f"https://{host}/trade/search/{urllib.parse.quote(league)}?q={urllib.parse.quote(q)}"


def trade_leagues() -> list[str]:
    d = _request(f"{API}/api/trade/data/leagues")
    return [lg["id"] for lg in d.get("result", []) if lg.get("realm", "pc") == "pc"]


@dataclass
class Listing:
    amount: float | None
    currency: str
    seller: str
    online: bool
    indexed: str
    conqueror: str
    corrupted: bool

    def price_text(self) -> str:
        if self.amount is None:
            return "?"
        a = f"{self.amount:g}"
        return f"{a} {CURRENCY_SHORT.get(self.currency, self.currency)}"


@dataclass
class Result:
    total: int
    listings: list[Listing]
    query: dict
    league: str


def search(j: TimelessJewel, league: str, any_conqueror: bool = True, count: int = 20,
           status: str = "online") -> Result:
    query = build_query(j, any_conqueror, status)
    lg = urllib.parse.quote(league)
    res = _request(f"{API}/api/trade/search/{lg}", query)
    qid, ids = res["id"], res.get("result", [])
    listings: list[Listing] = []
    for i in range(0, min(count, len(ids)), 10):
        chunk = ",".join(ids[i:i + 10])
        data = _request(f"{API}/api/trade/fetch/{chunk}?query={qid}")
        for r in data.get("result", []):
            if not r:
                continue
            lst, item = r.get("listing", {}), r.get("item", {})
            price = lst.get("price") or {}
            acc = lst.get("account", {})
            mods = " ".join(item.get("explicitMods", []))
            conq = next((c for c in j.conquerors if c in mods), "")
            listings.append(Listing(price.get("amount"), price.get("currency", ""),
                                    acc.get("lastCharacterName") or acc.get("name", "?"),
                                    bool(acc.get("online")), lst.get("indexed", ""), conq,
                                    bool(item.get("corrupted"))))
    return Result(res.get("total", 0), listings, query, league)


def to_chaos(listing: Listing, divine: float) -> float | None:
    if listing.amount is None:
        return None
    if listing.currency == "chaos":
        return float(listing.amount)
    if listing.currency == "divine" and divine:
        return float(listing.amount) * divine
    return None


def summary(listings: list[Listing], divine: float, top: int = 10) -> tuple[float, float] | None:
    """(минимум, медиана первых top лотов) в хаосах."""
    vals = [v for v in (to_chaos(l, divine) for l in listings[:top]) if v]
    if not vals:
        return None
    return min(vals), statistics.median(vals)
