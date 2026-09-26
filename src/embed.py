"""Embed Steam reviews and store them in a persistent Chroma collection."""
import json
import chromadb
from openai import OpenAI
from src.config import OPENAI_API_KEY, EMBEDDING_MODEL, REVIEWS_PATH, CHROMA_DIR, COLLECTION_NAME

client = OpenAI(api_key=OPENAI_API_KEY)


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


def get_embeddings(texts: list[str]) -> list[list[float]]:
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    return [d.embedding for d in response.data]


def get_collection():
    chroma = chromadb.PersistentClient(path=CHROMA_DIR)
    return chroma.get_or_create_collection(name=COLLECTION_NAME)


def build_index(batch_size: int = 100) -> None:
    reviews = load_reviews()
    collection = get_collection()
    for i in range(0, len(reviews), batch_size):
        batch = reviews[i:i + batch_size]
        documents = [build_document(review) for review in batch]
        embeddings = get_embeddings(documents)
        collection.add(
            ids=[review["review_id"] for review in batch],
            embeddings=embeddings,
            documents=documents,
            metadatas=[
                {
                    "title": review["title"],
                    "app_id": review["app_id"],
                    "voted_up": review["voted_up"],
                    "playtime_forever": review["playtime_forever"],
                }
                for review in batch
            ],
        )


if __name__ == "__main__":
    build_index()
    print("Review index built.")
