"""
Turns a scraped+scored news item into a hedge-fund-style trade note using
Groq's free API (an OpenAI-compatible hosted-open-model API). Output is
validated against a Pydantic schema, with one retry if the model returns
malformed JSON.
"""
import json
import os

from pydantic import BaseModel, ValidationError, field_validator

from src.config import GROQ_MODEL, WATCHLIST, SECTOR_FOCUS

VALID_POSITIONS = {"long", "short", "hold"}


class TradeNote(BaseModel):
    summary: str
    catalyst: str
    position: str
    instrument: str
    explanation: str
    rationale: list
    risk: str
    confidence: float

    @field_validator("position")
    @classmethod
    def position_valid(cls, v):
        v = v.lower().strip()
        if v not in VALID_POSITIONS:
            raise ValueError(f"position must be one of {VALID_POSITIONS}, got {v!r}")
        return v

    @field_validator("confidence")
    @classmethod
    def confidence_range(cls, v):
        return max(0.0, min(1.0, float(v)))


SYSTEM_PROMPT = f"""You are a hedge fund analyst at a student-run fund covering: {', '.join(SECTOR_FOCUS)}.
Your watchlist tickers are: {', '.join(WATCHLIST)}.
Given a news item (headline, article text, and a sentiment signal from a finance NLP model),
produce a trade-oriented note that a student can read aloud to defend the position live in
front of their class, including likely questions from classmates or the professor.

Respond ONLY with a JSON object with exactly these fields:
{{
  "summary": "1-2 sentence plain-English summary of the news itself",
  "catalyst": "one sentence naming the specific trigger/event driving this (e.g. an earnings beat, a Fed statement, a product announcement) - not generic",
  "position": "long" | "short" | "hold",
  "instrument": "specific ticker or instrument you'd trade on this (e.g. a watchlist ticker, a sector ETF, or the relevant company's ticker)",
  "explanation": "4-6 sentences, written as spoken talking points, walking through the reasoning chain end to end: what happened -> why it matters for this instrument -> how the sentiment/valuation/market context supports the position -> why this position specifically (not the alternative). Assume the listener has NOT read the article - make it self-contained. Plain language, no jargon without a quick definition.",
  "rationale": ["2 to 3 short bullet points - a quick-reference cheat sheet version of the explanation, for slides or fast recall during Q&A"],
  "risk": "one sentence on the main risk to this thesis, phrased so the student can answer 'what could go wrong?' if asked",
  "confidence": 0.0 to 1.0
}}
No markdown, no prose outside the JSON object.
"""


def _build_user_prompt(item: dict) -> str:
    sentiment = item.get("sentiment", {})
    tickers = ", ".join(item.get("tickers", [])) or "none matched"
    return (
        f"Headline: {item['title']}\n"
        f"Source: {item.get('source', 'unknown')}\n"
        f"Matched watchlist tickers: {tickers}\n"
        f"Macro-relevant: {item.get('is_macro', False)}\n"
        f"FinBERT sentiment: {sentiment.get('label', 'unknown')} "
        f"(confidence {sentiment.get('confidence', 0)})\n\n"
        f"Article text:\n{(item.get('text') or item.get('summary') or '')[:4000]}"
    )


def _call_groq(client, user_prompt: str) -> str:
    completion = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.3,
        max_tokens=1500,
        reasoning_effort="low",
    )
    return completion.choices[0].message.content


def analyze_item(client, item: dict) -> dict:
    user_prompt = _build_user_prompt(item)

    last_error = None
    for attempt in range(2):
        try:
            raw = _call_groq(client, user_prompt)
            parsed = json.loads(raw)
            note = TradeNote(**parsed)
            item["analysis"] = note.model_dump()
            return item
        except (json.JSONDecodeError, ValidationError, Exception) as exc:
            last_error = exc
            print(f"[analyzer] attempt {attempt + 1} failed for '{item['title'][:60]}': {exc}")

    item["analysis"] = {
        "summary": item.get("summary") or item["title"],
        "catalyst": "n/a",
        "position": "hold",
        "instrument": (item.get("tickers") or ["N/A"])[0],
        "explanation": "Automated analysis failed for this item after two attempts - read the source article directly before presenting on it.",
        "rationale": ["Automated analysis failed; flagged for manual review."],
        "risk": f"Analysis error: {last_error}",
        "confidence": 0.0,
    }
    return item


def annotate_items(items: list) -> list:
    from groq import Groq

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set")
    client = Groq(api_key=api_key)

    for item in items:
        analyze_item(client, item)
    return items
