"""Central config. Loads env vars once so every module shares the same setup."""
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4o-mini")
EMBEDDING_DIM = 1536

GAMES_META_PATH = str(ROOT / "data" / "games_meta.json")
REVIEWS_PATH = str(ROOT / "data" / "reviews.jsonl")
APPLIST_DB_PATH = str(ROOT / "data" / "steam_apps.sqlite")

PINECONE_INDEX = os.getenv("PINECONE_INDEX", "game-review-assistant")
PINECONE_CLOUD = os.getenv("PINECONE_CLOUD", "aws")
PINECONE_REGION = os.getenv("PINECONE_REGION", "us-east-1")

REVIEWS_PER_GAME = 80
ON_DEMAND_REVIEWS = 40
METADATA_TEXT_LIMIT = 3500
