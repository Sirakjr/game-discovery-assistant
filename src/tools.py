"""Aggregate review stats the model can request as a tool."""
import json
from src.config import REVIEWS_PATH

GAME_REVIEW_STATS_TOOL = {
    "type": "function",
    "name": "get_game_review_stats",
    "description": "Return aggregate review stats (positive/negative counts, avg playtime) for a game.",
    "parameters": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Exact game title as stored in reviews."},
        },
        "required": ["title"],
        "additionalProperties": False,
    },
}


def get_game_review_stats(title: str) -> dict:
    pos = neg = 0
    playtimes = []
    with open(REVIEWS_PATH, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r.get("title", "").lower() != title.lower():
                continue
            if r.get("voted_up"):
                pos += 1
            else:
                neg += 1
            if r.get("playtime_forever"):
                playtimes.append(r["playtime_forever"])
    total = pos + neg
    return {
        "title": title,
        "positive": pos,
        "negative": neg,
        "positive_pct": round(100 * pos / total, 1) if total else None,
        "avg_playtime_hours": round(sum(playtimes) / len(playtimes) / 60, 1) if playtimes else None,
        "reviews_counted": total,
    }
