"""Review-grounded answers via the OpenAI Responses API."""
import json
from collections.abc import Iterator

from openai import OpenAI

from src.config import CHAT_MODEL, OPENAI_API_KEY
from src.retrieve import prepare_query_games, search_reviews
from src.tools import ALL_TOOLS, run_tool

client = OpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = (
    "You answer questions about video games using ONLY the player reviews provided as context "
    "and tool results. Be balanced: reflect both positive and negative sentiment when it exists, "
    "and quote or paraphrase specific reviews. Name the games you're drawing from. "
    "If the user names a game that is missing from the reviews, call ensure_game_indexed. "
    "If they ask about overall reception, call get_game_review_stats. "
    "If they ask for similar games or what to play next, call recommend_similar_games "
    "(those recs come from review embeddings, not store tags). "
    "If the reviews don't cover the question, say so rather than inventing. "
    "Put similar-game suggestions in recommendations when you have them."
)

ANSWER_SCHEMA = {
    "name": "review_grounded_answer",
    "schema": {
        "type": "object",
        "properties": {
            "answer": {"type": "string", "description": "the answer to the question"},
            "supporting_reviews": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "snippet": {"type": "string"},
                        "sentiment": {"type": "string", "enum": ["positive", "negative"]},
                    },
                    "required": ["title", "snippet", "sentiment"],
                    "additionalProperties": False,
                },
            },
            "games_mentioned": {"type": "array", "items": {"type": "string"}},
            "recommendations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "why": {"type": "string"},
                    },
                    "required": ["title", "why"],
                    "additionalProperties": False,
                },
            },
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        },
        "required": [
            "answer",
            "supporting_reviews",
            "games_mentioned",
            "recommendations",
            "confidence",
        ],
        "additionalProperties": False,
    },
}

TEXT_FORMAT = {
    "format": {
        "type": "json_schema",
        "name": ANSWER_SCHEMA["name"],
        "strict": True,
        "schema": ANSWER_SCHEMA["schema"],
    }
}


def build_context(hits: list[dict]) -> str:
    if not hits:
        return "(No matching reviews were retrieved. Call ensure_game_indexed if the user named a specific game.)"
    lines = []
    for h in hits:
        tag = "👍" if h.get("voted_up") else "👎"
        lines.append(f"[{h.get('title')} {tag}] {h.get('text')}")
    return "\n\n".join(lines)


def _tool_args(item, fallback_game: str | None) -> dict:
    raw = item.arguments
    args = raw if isinstance(raw, dict) else json.loads(raw or "{}")
    if fallback_game and not args.get("title") and not args.get("name"):
        args["title"] = fallback_game
        args["name"] = fallback_game
    return args


def answer(query: str, game: str | None = None) -> Iterator[str]:
    prepared = prepare_query_games(query, game=game)
    filter_title = prepared.get("filter_title") or game
    hits = search_reviews(query, game=filter_title)
    context = build_context(hits)
    note = ""
    if prepared.get("titles"):
        note = "Indexed games for this question: " + ", ".join(prepared["titles"]) + "\n\n"

    stream = client.responses.create(
        model=CHAT_MODEL,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"{note}Player reviews:\n{context}\n\nQuestion: {query}",
            },
        ],
        tools=ALL_TOOLS,
        stream=True,
        text=TEXT_FORMAT,
    )

    final = None
    yielded = False
    for event in stream:
        kind = getattr(event, "type", None)
        if kind == "response.output_text.delta" and getattr(event, "delta", None):
            yielded = True
            yield event.delta
        elif kind == "response.completed":
            final = event.response

    rounds = 0
    while final is not None and rounds < 4:
        calls = [item for item in (final.output or []) if getattr(item, "type", None) == "function_call"]
        if not calls:
            break
        rounds += 1
        tool_outputs = []
        for item in calls:
            args = _tool_args(item, filter_title)
            result = run_tool(item.name, args)
            tool_outputs.append({
                "type": "function_call_output",
                "call_id": item.call_id,
                "output": json.dumps(result),
            })
            if item.name == "ensure_game_indexed" and result.get("ok") and result.get("title"):
                extra = search_reviews(query, game=result["title"])
                if extra:
                    tool_outputs[-1]["output"] = json.dumps({
                        **result,
                        "fresh_reviews": [
                            {"title": h["title"], "text": (h.get("text") or "")[:500], "voted_up": h.get("voted_up")}
                            for h in extra[:6]
                        ],
                    })
        followup = client.responses.create(
            model=CHAT_MODEL,
            previous_response_id=final.id,
            tools=ALL_TOOLS,
            text=TEXT_FORMAT,
            input=tool_outputs,
            stream=True,
        )
        followup_final = None
        followup_yielded = False
        for event in followup:
            kind = getattr(event, "type", None)
            if kind == "response.output_text.delta" and getattr(event, "delta", None):
                followup_yielded = True
                yielded = True
                yield event.delta
            elif kind == "response.completed":
                followup_final = event.response
        final = followup_final
        if followup_yielded:
            return
        if final and final.output_text and not any(
            getattr(item, "type", None) == "function_call" for item in (final.output or [])
        ):
            yield final.output_text
            return

    if not yielded and final and final.output_text:
        yield final.output_text


if __name__ == "__main__":
    for chunk in answer("what’s the overall reception of Hades?", game="Hades"):
        print(chunk, end="", flush=True)
