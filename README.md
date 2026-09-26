# Game Review Assistant

Ask questions about games — *is Elden Ring too hard for casual players?*, *what do people dislike about Cyberpunk?*, *how do players compare Hades and Dead Cells?* — and get answers grounded in real Steam reviews.

The pipeline is a small RAG stack: Steam ingestion → OpenAI embeddings → ChromaDB retrieval → the OpenAI Responses API (tool calling, structured JSON, streaming) → a Streamlit UI.

## Setup
```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env          # then paste your OPENAI_API_KEY
```

## Run
```bash
python -m src.ingest_steam      # data/games_meta.json + data/reviews.jsonl
python -m src.embed             # embed reviews into chroma_db/
streamlit run app.py
```

Edit the `GAMES` dict in `src/ingest_steam.py` to change which titles are ingested.

## Layout
```
app.py                 Streamlit UI
src/config.py          env, paths, models
src/ingest_steam.py    Steam metadata + reviews
src/embed.py           embeddings → Chroma
src/retrieve.py        semantic search + filters
src/tools.py           get_game_review_stats
src/respond.py         Responses API (tools, schema, stream)
```

Steam's `appdetails` and `appreviews` endpoints are public (no Steam key). Default models are `text-embedding-3-small` and `gpt-4o-mini`.

## Deploy (Streamlit Community Cloud)
1. Push this repo to GitHub.
2. Open [share.streamlit.io](https://share.streamlit.io), sign in with GitHub, and create an app from this repository (`app.py`).
3. In **Advanced settings → Secrets**, add:
   ```toml
   OPENAI_API_KEY = "sk-your-key-here"
   ```
   Do not commit `.env` or `.streamlit/secrets.toml`.
