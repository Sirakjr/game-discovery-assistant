import json
import os
import unicodedata
import streamlit as st
from src.config import GAMES_META_PATH
from src.respond import answer


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


def pick_covers(meta: dict, mentioned: list | None, focused: str | None, k: int = 4) -> list[dict]:
    picked, seen = [], set()

    def add(name: str | None) -> None:
        g = lookup_meta(meta, name)
        if not g or g["title"] in seen:
            return
        picked.append(g)
        seen.add(g["title"])

    for name in mentioned or []:
        add(name)
        if len(picked) >= k:
            return picked
    add(focused)
    return picked


def show_game_row(games: list[dict]) -> None:
    if not games:
        return
    cols = st.columns(len(games))
    for col, g in zip(cols, games):
        with col:
            st.image(steam_header_url(g["app_id"]), use_container_width=True)
            st.caption(g["title"])


st.set_page_config(page_title="Game Review Assistant", layout="wide")
st.title("🎮 Game Review Assistant")
st.caption("Ask about games — answered from real Steam player reviews.")

meta = {}
game = None
if os.path.exists(GAMES_META_PATH):
    meta = json.load(open(GAMES_META_PATH, encoding="utf-8"))
    titles = sorted(g["title"] for g in meta.values())
    choice = st.selectbox("Focus on one game? (optional)", ["All games"] + titles)
    game = None if choice == "All games" else choice

query = st.text_input(
    "Your question",
    placeholder="e.g. is Elden Ring too hard for casual players?",
)

if query:
    st.subheader("Answer")
    box = st.empty()
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

    if meta:
        covers = pick_covers(meta, mentioned, focused=game)
        if covers:
            st.subheader("Cover art")
            st.caption("Steam store headers for games named in the answer — not recommendations.")
            show_game_row(covers)
