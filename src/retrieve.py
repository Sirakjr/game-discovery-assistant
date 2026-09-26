"""Semantic search over review embeddings, with optional title/sentiment filters."""
from src.embed import get_embeddings, get_collection


def search_reviews(
    query: str,
    k: int = 6,
    game: str | None = None,
    sentiment: bool | None = None,
) -> list[dict]:
    collection = get_collection()
    q_vec = get_embeddings([query])[0]
    where = {}
    if game is not None:
        where["title"] = game
    if sentiment is not None:
        where["voted_up"] = sentiment
    results = collection.query(
        query_embeddings=[q_vec],
        n_results=k,
        where=where or None,
    )
    docs = results["documents"][0]
    metas = results["metadatas"][0]
    dists = results["distances"][0]
    return [
        {
            "text": text,
            "title": meta.get("title"),
            "voted_up": meta.get("voted_up"),
            "playtime": meta.get("playtime_forever"),
            "distance": dist,
        }
        for text, meta, dist in zip(docs, metas, dists)
    ]


if __name__ == "__main__":
    for hit in search_reviews("is it too hard for casual players?", game="ELDEN RING"):
        print(hit)
