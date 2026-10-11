"""Embed Steam reviews and upsert them into Pinecone."""
from __future__ import annotations

import json
import time

from openai import APIError, OpenAI, RateLimitError
from pinecone import Pinecone, ServerlessSpec

from src.config import (
    EMBEDDING_DIM,
    EMBEDDING_MODEL,
    METADATA_TEXT_LIMIT,
    OPENAI_API_KEY,
    PINECONE_API_KEY,
    PINECONE_CLOUD,
    PINECONE_INDEX,
    PINECONE_REGION,
    REVIEWS_PATH,
)

openai_client = OpenAI(api_key=OPENAI_API_KEY)
_index = None


def load_reviews(path: str = REVIEWS_PATH) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def build_document(review: dict) -> str:
    return f"Game: {review['title']}\nReview: {review['review_text']}"


def get_embeddings(texts: list[str], retries: int = 5) -> list[list[float]]:
    last_error = None
    for attempt in range(retries):
        try:
            response = openai_client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
            return [d.embedding for d in response.data]
        except (RateLimitError, APIError) as e:
            last_error = e
            time.sleep(2 ** attempt)
    raise last_error or RuntimeError("embedding request failed")


def _index_names(pc: Pinecone) -> set[str]:
    listed = pc.list_indexes()
    names = getattr(listed, "names", None)
    if callable(names):
        return set(names())
    out = set()
    for item in listed:
        if isinstance(item, str):
            out.add(item)
        elif isinstance(item, dict):
            out.add(item.get("name") or item.get("id"))
        else:
            out.add(getattr(item, "name", None) or str(item))
    return {n for n in out if n}


def get_index():
    global _index
    if _index is not None:
        return _index
    if not PINECONE_API_KEY:
        raise RuntimeError("PINECONE_API_KEY is not set")
    pc = Pinecone(api_key=PINECONE_API_KEY)
    if PINECONE_INDEX not in _index_names(pc):
        pc.create_index(
            name=PINECONE_INDEX,
            dimension=EMBEDDING_DIM,
            metric="cosine",
            spec=ServerlessSpec(cloud=PINECONE_CLOUD, region=PINECONE_REGION),
        )
        for _ in range(30):
            desc = pc.describe_index(PINECONE_INDEX)
            status = getattr(desc, "status", None)
            ready = getattr(status, "ready", None) if status is not None else None
            if ready is True or (isinstance(desc, dict) and (desc.get("status") or {}).get("ready")):
                break
            time.sleep(2)
    _index = pc.Index(PINECONE_INDEX)
    return _index


def review_metadata(review: dict) -> dict:
    text = (review.get("review_text") or "")[:METADATA_TEXT_LIMIT]
    playtime = review.get("playtime_forever") or 0
    try:
        playtime = float(playtime)
    except (TypeError, ValueError):
        playtime = 0.0
    return {
        "title": review["title"],
        "app_id": int(review["app_id"]),  # Pinecone often returns this as float in queries
        "voted_up": bool(review.get("voted_up")),
        "playtime_forever": playtime,
        "text": text,
    }


def upsert_reviews(reviews: list[dict], batch_size: int = 80) -> int:
    if not reviews:
        return 0
    index = get_index()
    count = 0
    for i in range(0, len(reviews), batch_size):
        batch = reviews[i:i + batch_size]
        documents = [build_document(review) for review in batch]
        embeddings = get_embeddings(documents)
        vectors = []
        for review, embedding in zip(batch, embeddings):
            rid = str(review.get("review_id") or f"{review['app_id']}-{count}")
            vectors.append({
                "id": rid,
                "values": embedding,
                "metadata": review_metadata(review),
            })
            count += 1
        index.upsert(vectors=vectors)
        time.sleep(0.15)
    return count


def build_index(batch_size: int = 80) -> None:
    upsert_reviews(load_reviews(), batch_size=batch_size)


if __name__ == "__main__":
    build_index()
    print("Review index built in Pinecone.")
