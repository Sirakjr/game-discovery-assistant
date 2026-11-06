"""Central config. Loads env vars once so every module shares the same setup."""
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def env_str(name: str, default: str | None = None) -> str | None:
    raw = os.getenv(name)
    if raw is None:
        return default
    text = str(raw).strip().strip('"').strip("'")
    return text or default


OPENAI_API_KEY = env_str("OPENAI_API_KEY")
PINECONE_API_KEY = env_str("PINECONE_API_KEY")
EMBEDDING_MODEL = env_str("EMBEDDING_MODEL", "text-embedding-3-small")
CHAT_MODEL = env_str("CHAT_MODEL", "gpt-4o-mini")
EMBEDDING_DIM = 1536

GAMES_META_PATH = str(ROOT / "data" / "games_meta.json")
REVIEWS_PATH = str(ROOT / "data" / "reviews.jsonl")
APPLIST_DB_PATH = str(ROOT / "data" / "steam_apps.sqlite")

PINECONE_INDEX = env_str("PINECONE_INDEX", "game-review-assistant")
PINECONE_CLOUD = env_str("PINECONE_CLOUD", "aws")
PINECONE_REGION = env_str("PINECONE_REGION", "us-east-1")

REVIEWS_PER_GAME = 80
ON_DEMAND_REVIEWS = 40
METADATA_TEXT_LIMIT = 3500
