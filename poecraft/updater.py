"""Версия программы и проверка обновлений через релизы GitHub."""

from __future__ import annotations

import json
import re
import urllib.request

APP_VERSION = "0.22.0"
DEFAULT_REPO = "guforeks322-droid/PoECraftHelper"   # релизы с обновлениями


def _ver(s: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", s)[:3]) or (0,)


def check(repo: str) -> dict:
    """{'latest': '0.11.0', 'newer': True, 'url': ..., 'notes': ...} или {'error': ...}."""
    repo = (repo or DEFAULT_REPO).strip().strip("/")
    if not repo or "/" not in repo:
        return {"error": "Не задан репозиторий обновлений (формат: владелец/название)."}
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = urllib.request.Request(url, headers={"User-Agent": f"PoECraftHelper/{APP_VERSION}",
                                               "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {"error": f"Не удалось проверить обновления: {e}"}
    tag = d.get("tag_name") or d.get("name") or ""
    asset = next((a.get("browser_download_url") for a in d.get("assets", [])
                  if str(a.get("name", "")).endswith(".zip")), None)
    return {"latest": tag.lstrip("v"), "newer": _ver(tag) > _ver(APP_VERSION),
            "url": asset or d.get("html_url"), "page": d.get("html_url"), "notes": (d.get("body") or "")[:600]}
