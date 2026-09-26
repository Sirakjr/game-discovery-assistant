"""Review-grounded answers via the OpenAI Responses API."""
import json
from collections.abc import Iterator
from openai import OpenAI
from src.config import OPENAI_API_KEY, CHAT_MODEL
from src.retrieve import search_reviews
from src.tools import GAME_REVIEW_STATS_TOOL, get_game_review_stats

client = OpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = (
    "You answer questions about video games using ONLY the player reviews provided as context. "
    "Be balanced: reflect both positive and negative sentiment when it exists, and quote or "
    "paraphrase specific reviews. Name the games you're drawing from. If the user asks about a "
    "game's overall reception, call get_game_review_stats for hard numbers. If the reviews don't "
    "cover the question, say so rather than inventing."
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
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        },
        "required": ["answer", "supporting_reviews", "games_mentioned", "confidence"],
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
    lines = []
    for h in hits:
        tag = "👍" if h.get("voted_up") else "👎"
        lines.append(f"[{h.get('title')} {tag}] {h.get('text')}")
    return "\n\n".join(lines)


def answer(query: str, game: str | None = None) -> Iterator[str]:
    hits = search_reviews(query, game=game)
    context = build_context(hits)
    stream = client.responses.create(
        model=CHAT_MODEL,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Player reviews:\n{context}\n\nQuestion: {query}",
            },
        ],
        tools=[GAME_REVIEW_STATS_TOOL],
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

    if final is None:
        return

    for item in final.output:
        if item.type == "function_call" and item.name == "get_game_review_stats":
            raw = item.arguments
            args = raw if isinstance(raw, dict) else json.loads(raw or "{}")
            title = args.get("title") or args.get("game") or args.get("name") or game
            if not title:
                continue
            stats = get_game_review_stats(title)
            followup = client.responses.create(
                model=CHAT_MODEL,
                previous_response_id=final.id,
                tools=[GAME_REVIEW_STATS_TOOL],
                text=TEXT_FORMAT,
                input=[{
                    "type": "function_call_output",
                    "call_id": item.call_id,
                    "output": json.dumps(stats),
                }],
                stream=True,
            )
            followup_yielded = False
            followup_final = None
            for event in followup:
                kind = getattr(event, "type", None)
                if kind == "response.output_text.delta" and getattr(event, "delta", None):
                    followup_yielded = True
                    yield event.delta
                elif kind == "response.completed":
                    followup_final = event.response
            if not followup_yielded and followup_final and followup_final.output_text:
                yield followup_final.output_text
            return

    if not yielded and final.output_text:
        yield final.output_text


if __name__ == "__main__":
    for chunk in answer("what’s the overall reception of Hades?", game="Hades"):
        print(chunk, end="", flush=True)
