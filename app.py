import json
import os
import unicodedata

import streamlit as st

from src.config import GAMES_META_PATH, OPENAI_API_KEY, PINECONE_API_KEY
from src.respond import answer
from src.retrieve import recommend_similar_games


def steam_header_url(app_id: int) -> str:
    return (
        "https://shared.akamai.steamstatic.com/store_item_assets/"
        f"steam/apps/{app_id}/header.jpg"
    )


def _fold(name: str) -> str:
    return unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower().strip()


def lookup_meta(meta: dict, name: str | None) -> dict | None:
    if not name:
        return None
    key = _fold(name)
    for g in meta.values():
        if _fold(g["title"]) == key:
            return g
    return None


def pick_covers(meta: dict, mentioned: list | None, focused: str | None, recs: list | None, k: int = 4) -> list[dict]:
    picked, seen = [], set()

    def add(name: str | None = None, app_id: int | None = None, title: str | None = None) -> None:
        g = lookup_meta(meta, name or title)
        if not g and app_id:
            g = {"title": title or name or str(app_id), "app_id": int(app_id)}
        if not g or g["title"] in seen:
            return
        picked.append(g)
        seen.add(g["title"])

    for name in mentioned or []:
        add(name=name)
        if len(picked) >= k:
            return picked
    for rec in recs or []:
        add(title=rec.get("title"), app_id=rec.get("app_id"))
        if len(picked) >= k:
            return picked
    add(name=focused)
    return picked


def show_game_row(games: list[dict]) -> None:
    if not games:
        return
    cols = st.columns(len(games))
    for col, g in zip(cols, games):
        with col:
            st.image(steam_header_url(g["app_id"]), width="stretch")
            st.caption(g["title"])


st.set_page_config(page_title="Game Review Assistant", layout="wide")
st.title("🎮 Game Review Assistant")
st.caption(
    "Ask about a game by name or Steam URL. Answers come from Steam player reviews. "
    "Games that are not in the index yet are fetched on first ask."
)

missing = [name for name, val in (("OPENAI_API_KEY", OPENAI_API_KEY), ("PINECONE_API_KEY", PINECONE_API_KEY)) if not val]
if missing:
    st.error("Missing " + ", ".join(missing) + ". Set them in .env (local) or App settings → Secrets (Streamlit Cloud).")
    st.stop()

meta = {}
game = None
if os.path.exists(GAMES_META_PATH):
    meta = json.load(open(GAMES_META_PATH, encoding="utf-8"))
    titles = sorted(g["title"] for g in meta.values())
    choice = st.selectbox("Focus on one indexed game? (optional)", ["All games"] + titles)
    game = None if choice == "All games" else choice

query = st.text_input(
    "Your question",
    placeholder="e.g. is Elden Ring too hard for casual players?",
)

if query:
    st.subheader("Answer")
    box = st.empty()
    with st.spinner("Resolving game, retrieving reviews, writing answer…"):
        with box:
            collected = st.write_stream(answer(query, game=game))
    if isinstance(collected, list):
        collected = "".join(c for c in collected if isinstance(c, str))
    text = collected if isinstance(collected, str) else ""
    result = json.loads(text) if text.strip().startswith("{") else {}

    box.markdown(result.get("answer") or text)
    mentioned = result.get("games_mentioned") or []

    reviews = result.get("supporting_reviews", [])
    if reviews:
        with st.expander(f"Supporting reviews ({len(reviews)})"):
            for r in reviews:
                tag = "👍" if r.get("sentiment") in (True, "positive") else "👎"
                st.markdown(f"**{r.get('title')}** {tag} — {r.get('snippet')}")

    rec_title = game or (mentioned[0] if mentioned else None)
    recs = []
    if rec_title:
        rec_result = recommend_similar_games(rec_title, k=3)
        recs = rec_result.get("recommendations") or []
        if recs:
            st.subheader("Similar by reviews")
            st.caption(
                f"Games whose player reviews sit near {rec_result.get('title') or rec_title} "
                "in the index — not Steam genre tags."
            )
            for rec in recs:
                why = rec.get("why") or ""
                line = f"**{rec.get('title')}**"
                if why:
                    line += f" — {why}"
                st.markdown(line)

    if os.path.exists(GAMES_META_PATH):
        meta = json.load(open(GAMES_META_PATH, encoding="utf-8"))
    covers = pick_covers(meta, mentioned, focused=game, recs=recs)
    if covers:
        st.subheader("Cover art")
        show_game_row(covers)
