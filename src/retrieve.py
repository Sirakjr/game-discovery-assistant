"""Semantic search, on-demand indexing, and similar-game recs over Pinecone."""
from __future__ import annotations

from collections import Counter

from src.config import ON_DEMAND_REVIEWS
from src.embed import get_embeddings, get_index, upsert_reviews
from src.ingest_steam import ingest_app
from src.steam_resolve import parse_steam_app_id, resolve_name, titles_in_query


def _matches(result) -> list:
    if result is None:
        return []
    if isinstance(result, dict):
        return result.get("matches") or []
    return list(getattr(result, "matches", None) or [])


def _meta(match) -> dict:
    if isinstance(match, dict):
        return match.get("metadata") or {}
    return dict(getattr(match, "metadata", None) or {})


def _score(match) -> float:
    if isinstance(match, dict):
        return float(match.get("score") or 0)
    return float(getattr(match, "score", 0) or 0)


def _values(match) -> list[float] | None:
    raw = match.get("values") if isinstance(match, dict) else getattr(match, "values", None)
    if raw is None:
        return None
    return list(raw)


def _pinecone_filter(game: str | None = None, app_id: int | None = None, sentiment: bool | None = None) -> dict | None:
    clauses = []
    if app_id is not None:
        clauses.append({"app_id": {"$eq": float(int(app_id))}})
    elif game is not None:
        clauses.append({"title": {"$eq": game}})
    if sentiment is not None:
        clauses.append({"voted_up": {"$eq": bool(sentiment)}})
    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


def _probe_vector(label: str) -> list[float]:
    return get_embeddings([label])[0]


def query_app_reviews(app_id: int, top_k: int = 20, include_values: bool = False, title: str | None = None):
    label = title or f"Steam app {app_id} player reviews"
    return get_index().query(
        vector=_probe_vector(label),
        top_k=top_k,
        filter={"app_id": {"$eq": float(int(app_id))}},
        include_metadata=True,
        include_values=include_values,
    )


def game_is_indexed(app_id: int, title: str | None = None) -> bool:
    result = query_app_reviews(app_id, top_k=1, title=title)
    return bool(_matches(result))


def ensure_game_indexed(name: str | None = None, app_id: int | None = None) -> dict:
    """Resolve a game, ingest/embed it if needed, return canonical title + app_id."""
    resolved_title = None
    if app_id is None and name:
        url_id = parse_steam_app_id(name)
        if url_id:
            app_id = url_id
        else:
            found = resolve_name(name)
            if not found:
                return {"ok": False, "error": f"Could not resolve a Steam app for '{name}'."}
            app_id = found["app_id"]
            resolved_title = found["title"]
    if app_id is None:
        return {"ok": False, "error": "Provide a game name or Steam app id."}

    if game_is_indexed(app_id, title=resolved_title):
        title = resolved_title
        if not title:
            peek = query_app_reviews(app_id, top_k=1)
            hits = _matches(peek)
            title = _meta(hits[0]).get("title") if hits else resolved_title
        return {"ok": True, "title": title, "app_id": int(app_id), "already_indexed": True}

    meta, reviews = ingest_app(int(app_id), want=ON_DEMAND_REVIEWS)
    if not meta:
        return {"ok": False, "error": f"Steam returned no metadata for app {app_id}."}
    if not reviews:
        return {"ok": False, "error": f"No English reviews found for {meta.get('title')}.", "title": meta.get("title"), "app_id": int(app_id)}
    upsert_reviews(reviews)
    return {
        "ok": True,
        "title": meta["title"],
        "app_id": int(app_id),
        "already_indexed": False,
        "reviews_indexed": len(reviews),
    }


def prepare_query_games(query: str, game: str | None = None) -> dict:
    """Index any games named (or linked) in the question. Filter to one title when unambiguous."""
    ensured: list[dict] = []
    try:
        url_id = parse_steam_app_id(query)
        if url_id:
            ensured.append(ensure_game_indexed(app_id=url_id))
        elif game:
            ensured.append(ensure_game_indexed(name=game))
        else:
            for _name, appid in titles_in_query(query, limit=3):
                ensured.append(ensure_game_indexed(app_id=appid))
    except Exception as e:
        return {"ensured": [{"ok": False, "error": str(e)}], "filter_title": game, "titles": []}
    ok = [e for e in ensured if e.get("ok")]
    titles = [e["title"] for e in ok if e.get("title")]
    filter_title = titles[0] if len(titles) == 1 else None
    return {"ensured": ensured, "filter_title": filter_title, "titles": titles}


def search_reviews(
    query: str,
    k: int = 6,
    game: str | None = None,
    sentiment: bool | None = None,
    app_id: int | None = None,
) -> list[dict]:
    q_vec = get_embeddings([query])[0]
    where = _pinecone_filter(game=game, app_id=app_id, sentiment=sentiment)
    result = get_index().query(
        vector=q_vec,
        top_k=k,
        filter=where,
        include_metadata=True,
    )
    hits = []
    for match in _matches(result):
        meta = _meta(match)
        hits.append({
            "text": meta.get("text") or "",
            "title": meta.get("title"),
            "app_id": meta.get("app_id"),
            "voted_up": meta.get("voted_up"),
            "playtime": meta.get("playtime_forever"),
            "distance": 1.0 - _score(match),
            "score": _score(match),
        })
    return hits


def recommend_similar_games(title: str, k: int = 3) -> dict:
    ensured = ensure_game_indexed(name=title)
    if not ensured.get("ok"):
        return ensured
    canonical = ensured["title"]
    app_id = int(ensured["app_id"])
    seed = query_app_reviews(app_id, top_k=20, include_values=True, title=canonical)
    vectors = [v for m in _matches(seed) if (v := _values(m))]
    if vectors:
        dim = len(vectors[0])
        vibe = [sum(row[i] for row in vectors) / len(vectors) for i in range(dim)]
    else:
        vibe = get_embeddings([f"Game: {canonical}"])[0]
    result = get_index().query(
        vector=vibe,
        top_k=50,
        filter={"app_id": {"$ne": float(app_id)}},
        include_metadata=True,
    )
    votes: Counter[str] = Counter()
    best_score: dict[str, float] = {}
    app_by_title: dict[str, int] = {}
    for match in _matches(result):
        meta = _meta(match)
        other = meta.get("title")
        other_id = meta.get("app_id")
        if not other or int(other_id or 0) == app_id:
            continue
        score = _score(match)
        votes[other] += 1
        if other not in best_score or score > best_score[other]:
            best_score[other] = score
            if other_id is not None:
                app_by_title[other] = int(other_id)
    ranked = sorted(votes, key=lambda t: (votes[t], best_score.get(t, 0)), reverse=True)
    recs = [
        {
            "title": t,
            "app_id": app_by_title.get(t),
            "support": votes[t],
            "score": round(best_score[t], 3),
        }
        for t in ranked[:k]
    ]
    return {"ok": True, "title": canonical, "app_id": app_id, "recommendations": recs}


if __name__ == "__main__":
    print(prepare_query_games("is Elden Ring too hard for casual players?"))
    print(search_reviews("is it too hard for casual players?", game="ELDEN RING")[:2])
    print(recommend_similar_games("Hades"))
