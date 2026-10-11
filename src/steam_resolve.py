"""Resolve a Steam app id from a store URL or a game name in the user's question."""
from __future__ import annotations

import json
import re
import sqlite3
import unicodedata

import requests

from src.config import APPLIST_DB_PATH, GAMES_META_PATH

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

GET_APPLIST_URLS = (
    "https://api.steampowered.com/ISteamApps/GetAppList/v2/?format=json",
    "https://api.steampowered.com/ISteamApps/GetAppList/v0002/?format=json",
)
STORE_SEARCH_URL = "https://store.steampowered.com/api/storesearch/"
APP_URL_RE = re.compile(r"(?:store\.steampowered\.com/app/|aka\.ms/|/app/)(\d{1,10})", re.I)
# Steam store search of a full sentence is empty; nicknames also miss official titles.
_QUERY_STOP = re.compile(
    r"\b(is|are|was|were|the|a|an|to|for|of|and|or|but|if|what|whats|about|how|"
    r"does|do|did|can|could|should|still|worth|playing|play|it|its|in|on|with|"
    r"this|that|game|games|review|reviews|reviewers|too|very|really|i|you|my|"
    r"your|year|years|like|think|thoughts|anyone|people|players|casual)\b",
    re.I,
)
# Store search for "gta 5" returns the Enhanced SKU; the original listing has the review corpus.
NICKNAMES = {
    "gta 5": (271590, "Grand Theft Auto V"),
    "gta v": (271590, "Grand Theft Auto V"),
    "gta5": (271590, "Grand Theft Auto V"),
    "gtav": (271590, "Grand Theft Auto V"),
}

_apps_cache: list[tuple[str, str, int]] | None = None


def fold(name: str) -> str:
    return unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower().strip()


def parse_steam_app_id(text: str) -> int | None:
    if not text:
        return None
    m = APP_URL_RE.search(text)
    return int(m.group(1)) if m else None


def local_catalog() -> list[tuple[str, str, int]]:
    try:
        with open(GAMES_META_PATH, encoding="utf-8") as f:
            meta = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    rows = []
    for g in meta.values():
        title = g.get("title") or ""
        app_id = g.get("app_id")
        if title and app_id is not None:
            rows.append((fold(title), title, int(app_id)))
    return rows


def _connect() -> sqlite3.Connection:
    from pathlib import Path

    Path(APPLIST_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(APPLIST_DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS apps (appid INTEGER PRIMARY KEY, name TEXT NOT NULL, name_fold TEXT NOT NULL)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS apps_fold ON apps(name_fold)")
    return conn


def applist_ready() -> bool:
    try:
        conn = _connect()
        n = conn.execute("SELECT COUNT(*) FROM apps").fetchone()[0]
        conn.close()
        return n > 1000
    except sqlite3.Error:
        return False


def refresh_applist() -> int:
    last_error = None
    payload = None
    for url in GET_APPLIST_URLS:
        try:
            r = requests.get(url, headers=HEADERS, timeout=120)
            r.raise_for_status()
            payload = r.json()
            break
        except (requests.RequestException, ValueError) as e:
            last_error = e
    if payload is None:
        raise last_error or RuntimeError("Steam app list is unavailable")
    apps = (payload.get("applist") or {}).get("apps") or []
    conn = _connect()
    conn.execute("DELETE FROM apps")
    rows = []
    for app in apps:
        name = (app.get("name") or "").strip()
        appid = app.get("appid")
        if not name or appid is None:
            continue
        rows.append((int(appid), name, fold(name)))
    conn.executemany("INSERT OR REPLACE INTO apps(appid, name, name_fold) VALUES (?, ?, ?)", rows)
    conn.commit()
    conn.close()
    global _apps_cache
    _apps_cache = None
    return len(rows)


def _apps() -> list[tuple[str, str, int]]:
    global _apps_cache
    if _apps_cache is not None:
        return _apps_cache
    if not applist_ready():
        try:
            refresh_applist()
        except Exception:
            _apps_cache = local_catalog()
            return _apps_cache
    conn = _connect()
    rows = conn.execute("SELECT name_fold, name, appid FROM apps WHERE length(name_fold) >= 5").fetchall()
    conn.close()
    _apps_cache = [(f, n, int(i)) for f, n, i in rows] or local_catalog()
    return _apps_cache


def store_search(term: str, limit: int = 8) -> list[dict]:
    term = (term or "").strip()
    if not term:
        return []
    r = requests.get(
        STORE_SEARCH_URL,
        params={"term": term, "l": "english", "cc": "US"},
        headers=HEADERS,
        timeout=30,
    )
    r.raise_for_status()
    items = r.json().get("items") or []
    out = []
    for item in items[:limit]:
        out.append({
            "app_id": int(item["id"]),
            "title": item.get("name") or "",
            "type": item.get("type") or "",
        })
    return out


def _pick_from_rows(query_fold: str, rows: list[tuple[str, str, int]], limit: int) -> list[tuple[str, int]]:
    hits = []
    for name_fold, name, appid in rows:
        if len(name_fold) < 5:
            continue
        idx = query_fold.find(name_fold)
        if idx < 0:
            continue
        before = idx == 0 or not query_fold[idx - 1].isalnum()
        after_i = idx + len(name_fold)
        after = after_i >= len(query_fold) or not query_fold[after_i].isalnum()
        if before and after:
            hits.append((len(name_fold), name, appid))
    hits.sort(reverse=True)
    picked: list[tuple[str, int]] = []
    picked_folds: list[str] = []
    for _length, name, appid in hits:
        nf = fold(name)
        if any(nf in prev or prev in nf for prev in picked_folds):
            continue
        picked.append((name, appid))
        picked_folds.append(nf)
        if len(picked) >= limit:
            break
    return picked


def _phrase_in_query(query_fold: str, phrase: str) -> bool:
    idx = query_fold.find(phrase)
    if idx < 0:
        return False
    before = idx == 0 or not query_fold[idx - 1].isalnum()
    after_i = idx + len(phrase)
    after = after_i >= len(query_fold) or not query_fold[after_i].isalnum()
    return before and after


def search_term_from_query(query: str) -> str:
    """Drop question filler so Steam store search gets 'gta 5', not the whole sentence."""
    q = fold(query)
    q = _QUERY_STOP.sub(" ", q)
    q = re.sub(r"[^\w\s]", " ", q)
    return re.sub(r"\s+", " ", q).strip()


def _store_hits(term: str) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for item in store_search(term):
        if item["type"] not in ("app", "game", ""):
            continue
        title = item.get("title") or ""
        folded = fold(title)
        if "soundtrack" in folded or " dlc" in f" {folded}":
            continue
        out.append((title, item["app_id"]))
    return out


def titles_in_query(query: str, limit: int = 3) -> list[tuple[str, int]]:
    """Games named in the question: nicknames, local catalog, then Steam store search."""
    q = fold(query)
    if not q:
        return []
    picked: list[tuple[str, int]] = []
    seen: set[int] = set()

    def _add(title: str, appid: int) -> None:
        if appid in seen or len(picked) >= limit:
            return
        folded = fold(title)
        if any(folded in fold(t) or fold(t) in folded for t, _aid in picked):
            return
        picked.append((title, appid))
        seen.add(appid)

    for nick, (appid, title) in sorted(NICKNAMES.items(), key=lambda item: -len(item[0])):
        if _phrase_in_query(q, nick):
            _add(title, appid)
    for title, appid in _pick_from_rows(q, local_catalog() + _apps(), limit):
        _add(title, appid)
    term = search_term_from_query(query)
    for candidate in (term, query.strip()):
        if not candidate or len(picked) >= limit:
            break
        for title, appid in _store_hits(candidate):
            _add(title, appid)
            if len(picked) >= limit:
                break
    return picked[:limit]


def resolve_name(name: str) -> dict | None:
    """Best app id for a user-typed title. Local catalog, then Steam store search."""
    name = (name or "").strip()
    if not name:
        return None
    key = fold(name)
    nick = NICKNAMES.get(key)
    if nick:
        appid, title = nick
        return {"title": title, "app_id": appid}
    exact = [row for row in local_catalog() if row[0] == key]
    if not exact:
        exact = [row for row in _apps() if row[0] == key]
    if len(exact) == 1:
        _, title, appid = exact[0]
        return {"title": title, "app_id": appid}
    if len(exact) > 1:
        games = [row for row in exact if "soundtrack" not in row[0] and "dlc" not in row[0]]
        _, title, appid = (games or exact)[0]
        return {"title": title, "app_id": appid}
    for item in store_search(name):
        if item["type"] in ("app", "game", ""):
            return {"title": item["title"], "app_id": item["app_id"]}
    return None
