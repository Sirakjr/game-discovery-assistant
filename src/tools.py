"""Tools the model can call: stats, ensure a game is indexed, similar-game recs."""
from src.retrieve import _matches, _meta, ensure_game_indexed, query_app_reviews, recommend_similar_games

GAME_REVIEW_STATS_TOOL = {
    "type": "function",
    "name": "get_game_review_stats",
    "description": "Return aggregate review stats (positive/negative counts, avg playtime) for a game already in the index.",
    "parameters": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Game title as the user named it, or the canonical Steam title."},
        },
        "required": ["title"],
        "additionalProperties": False,
    },
}

ENSURE_GAME_TOOL = {
    "type": "function",
    "name": "ensure_game_indexed",
    "description": (
        "Resolve a game name or Steam URL/app id, fetch reviews if we do not have them yet, "
        "and add them to the search index. Call this when the user names a game that is not "
        "in the retrieved reviews."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Game title or Steam store URL."},
        },
        "required": ["name"],
        "additionalProperties": False,
    },
}

RECOMMEND_TOOL = {
    "type": "function",
    "name": "recommend_similar_games",
    "description": (
        "Recommend other indexed games whose player reviews sit near this game in embedding space. "
        "Not genre tags. Use when the user asks for similar games or what to play next."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Game to find neighbors for."},
        },
        "required": ["title"],
        "additionalProperties": False,
    },
}

ALL_TOOLS = [ENSURE_GAME_TOOL, GAME_REVIEW_STATS_TOOL, RECOMMEND_TOOL]


def get_game_review_stats(title: str) -> dict:
    ensured = ensure_game_indexed(name=title)
    if not ensured.get("ok"):
        return ensured
    canonical = ensured["title"]
    app_id = int(ensured["app_id"])
    result = query_app_reviews(app_id, top_k=100, title=canonical)
    pos = neg = 0
    playtimes = []
    for match in _matches(result):
        meta = _meta(match)
        if meta.get("voted_up"):
            pos += 1
        else:
            neg += 1
        pt = meta.get("playtime_forever")
        if pt:
            playtimes.append(float(pt))
    total = pos + neg
    return {
        "title": canonical,
        "app_id": app_id,
        "positive": pos,
        "negative": neg,
        "positive_pct": round(100 * pos / total, 1) if total else None,
        "avg_playtime_hours": round(sum(playtimes) / len(playtimes) / 60, 1) if playtimes else None,
        "reviews_counted": total,
    }


def run_tool(name: str, args: dict) -> dict:
    if name == "ensure_game_indexed":
        return ensure_game_indexed(name=args.get("name"))
    if name == "get_game_review_stats":
        return get_game_review_stats(args.get("title") or args.get("name") or "")
    if name == "recommend_similar_games":
        return recommend_similar_games(args.get("title") or args.get("name") or "")
    return {"ok": False, "error": f"Unknown tool {name}"}
