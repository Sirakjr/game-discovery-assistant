"""Central config. Loads env vars once so every module shares the same setup."""
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4o-mini")

GAMES_META_PATH = str(ROOT / "data" / "games_meta.json")
REVIEWS_PATH = str(ROOT / "data" / "reviews.jsonl")

CHROMA_DIR = str(ROOT / "chroma_db")
COLLECTION_NAME = "game_reviews"

REVIEWS_PER_GAME = 80

REVIEWS_PER_GAME = 80
