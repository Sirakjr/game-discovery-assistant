"""Ingest game metadata and player reviews from Steam's public store APIs."""
import json
import time
import requests
from src.config import GAMES_META_PATH, REVIEWS_PATH, REVIEWS_PER_GAME

GAMES = {
    "Hades": 1145360,
    "Stardew Valley": 413150,
    "Elden Ring": 1245620,
    "The Witcher 3: Wild Hunt": 292030,
    "Hollow Knight": 367520,
    "Celeste": 504230,
    "It Takes Two": 1426210,
    "Overcooked! 2": 728880,
    "Portal 2": 620,
    "Cuphead": 268910,
    "Disco Elysium": 632470,
    "Dead Cells": 588650,
    "Terraria": 105600,
    "Baldur's Gate 3": 1086940,
    "Slay the Spire": 646570,
    "Red Dead Redemption 2": 1174180,
    "Factorio": 427520,
    "Divinity: Original Sin 2": 435150,
    "Rocket League": 252950,
    "Sekiro: Shadows Die Twice": 814380,
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def _pick_appdetails(payload: dict, appid: int) -> dict:
    """Steam often keys appdetails by a DLC/edition id; the game lives on steam_appid."""
    if not isinstance(payload, dict):
        return {}
    candidates = list(payload.values())
    if str(appid) in payload:
        candidates = [payload[str(appid)], *candidates]
    for entry in candidates:
        if not isinstance(entry, dict) or not entry.get("success"):
            continue
        d = entry.get("data") or {}
        if d.get("steam_appid") in (appid, None) or d.get("type") == "game":
            return d
    return {}


def fetch_metadata(appid: int, retries: int = 4) -> dict:
    url = f"https://store.steampowered.com/api/appdetails?appids={appid}"
    for attempt in range(retries):
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        d = _pick_appdetails(r.json(), appid)
        if d:
            return {
                "app_id": appid,
                "title": d.get("name"),
                "genres": ", ".join(g["description"] for g in d.get("genres", [])),
                "description": d.get("short_description", ""),
                "release": d.get("release_date", {}).get("date", ""),
            }
        time.sleep(2 ** (attempt + 1))
    return {}


def fetch_reviews(appid: int, want: int = REVIEWS_PER_GAME) -> list[dict]:
    out, cursor = [], "*"
    while len(out) < want:
        url = (
            f"https://store.steampowered.com/appreviews/{appid}"
            f"?json=1&language=english&num_per_page=100&filter=recent&purchase_type=all&cursor={cursor}"
        )
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        payload = r.json()
        batch = payload.get("reviews", [])
        if not batch:
            break
        for rev in batch:
            out.append({
                "review_id": rev.get("recommendationid"),
                "review_text": (rev.get("review") or "").strip(),
                "voted_up": rev.get("voted_up"),
                "playtime_forever": rev.get("author", {}).get("playtime_forever"),
                "timestamp_created": rev.get("timestamp_created"),
            })
        cursor = payload.get("cursor")
        if not cursor:
            break
        time.sleep(0.5)
    return out[:want]


def main():
    meta_out, review_count = {}, 0
    with open(REVIEWS_PATH, "w", encoding="utf-8") as rf:
        for title, appid in GAMES.items():
            try:
                meta = fetch_metadata(appid)
                if not meta:
                    print(f"  ! no metadata for {title} ({appid}) - skipping")
                    continue
                print(f"  {title} -> Steam says '{meta['title']}' ({appid})")
                meta_out[str(appid)] = meta
                for rev in fetch_reviews(appid):
                    if not rev["review_text"]:
                        continue
                    rev["app_id"] = appid
                    rev["title"] = meta["title"]
                    rf.write(json.dumps(rev, ensure_ascii=False) + "\n")
                    review_count += 1
                time.sleep(1.5)
            except Exception as e:
                print(f"  ! error on {title}: {e}")
    with open(GAMES_META_PATH, "w", encoding="utf-8") as mf:
        json.dump(meta_out, mf, ensure_ascii=False, indent=2)
    print(f"\nDone. {len(meta_out)} games, {review_count} reviews -> {REVIEWS_PATH}")


def ingest_app(appid: int, want: int | None = None) -> tuple[dict, list[dict]]:
    """Fetch one game and append it to the local JSON files. Returns (meta, reviews)."""
    from src.config import ON_DEMAND_REVIEWS

    want = ON_DEMAND_REVIEWS if want is None else want
    meta = fetch_metadata(appid)
    if not meta or not meta.get("title"):
        return {}, []
    reviews = []
    with open(REVIEWS_PATH, "a", encoding="utf-8") as rf:
        for rev in fetch_reviews(appid, want=want):
            if not rev["review_text"]:
                continue
            rev["app_id"] = appid
            rev["title"] = meta["title"]
            rf.write(json.dumps(rev, ensure_ascii=False) + "\n")
            reviews.append(rev)
    try:
        with open(GAMES_META_PATH, encoding="utf-8") as mf:
            meta_out = json.load(mf)
    except (FileNotFoundError, json.JSONDecodeError):
        meta_out = {}
    meta_out[str(appid)] = meta
    with open(GAMES_META_PATH, "w", encoding="utf-8") as mf:
        json.dump(meta_out, mf, ensure_ascii=False, indent=2)
    return meta, reviews


if __name__ == "__main__":
    main()
