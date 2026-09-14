"""
Turns a scraped+scored news item into a hedge-fund-style trade note using
Groq's free API (an OpenAI-compatible hosted-open-model API). Output is
validated against a Pydantic schema, with one retry if the model returns
malformed JSON.
"""
import json
import os
import time

from pydantic import BaseModel, ValidationError, field_validator

from src.config import GROQ_MODEL, WATCHLIST, SECTOR_FOCUS

VALID_POSITIONS = {"long", "short", "hold"}
VALID_ASSET_CLASSES = {"equity", "etf", "option", "future", "currency", "bond", "commodity"}


class TradeNote(BaseModel):
    summary: str
    catalyst: str
    position: str
    asset_class: str
    instrument: str
    market: str
    horizon: str
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

    @field_validator("asset_class")
    @classmethod
    def asset_class_valid(cls, v):
        v = v.lower().strip()
        if v not in VALID_ASSET_CLASSES:
            raise ValueError(f"asset_class must be one of {VALID_ASSET_CLASSES}, got {v!r}")
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

IMPORTANT - horizon: these are swing/position trades, NOT day trades. Never
reason about intraday price action or say something "could rally today" or
"by the close" - the news will be stale by the time anyone reads this. A
holding period as short as a few days is fine if the catalyst plays out that
fast (e.g. an earnings reaction, a Fed decision this week), but it must never
be same-day/intraday. Longer theses (weeks to months) are just as valid when
the catalyst takes longer to play out.

IMPORTANT - instrument choice: a real hedge fund does not only trade US
large-cap stocks. Pick whichever instrument and asset class most directly
expresses the thesis - equities, ETFs, options (e.g. "AAPL Jan-2027 190
Call"), futures (e.g. "CME E-mini S&P 500 future /ES", "10-Year Treasury
Note future /ZN"), currencies/FX (e.g. "USD/JPY", "EUR/USD"), bonds/rate
products (e.g. "iShares 20+ Year Treasury Bond ETF TLT"), or commodities
(e.g. "WTI Crude Oil", "Brent Crude", "Gold", "Natural Gas"). A Fed rate
story is often better expressed via a rate future, a bond ETF, or the
dollar than by a random stock. Geopolitical stories (e.g. Middle East
tensions) are very often better expressed as a direct commodity trade (oil,
gold) than a random related equity.

IMPORTANT - commodity vs. future/etf: if the trade is fundamentally about a
physical commodity (oil, gold, silver, natural gas, copper, agricultural
products like corn/wheat/soybeans), classify asset_class as "commodity" -
even if you'd actually express it via a futures contract or a commodity
ETF wrapper. Reserve "future" for non-commodity futures (equity-index,
rate) and "etf" for non-commodity ETFs, so "commodity" reliably captures
every commodity-driven thesis regardless of wrapper.

Always name the specific market or exchange the instrument trades on -
mainly the NYSE/NASDAQ for US equities since that's this fund's primary
focus, but use the correct market when the news points elsewhere (e.g.
Tokyo Stock Exchange for a Japanese company, the Bank of Japan for
yen-driven FX moves, CME/CBOT/NYMEX for futures and commodities, the
interbank/FX market for currency pairs, LSE for UK-listed names, etc.).

Respond ONLY with a JSON object with exactly these fields:
{{
  "summary": "1-2 sentence plain-English summary of the news itself",
  "catalyst": "one sentence naming the specific trigger/event driving this (e.g. an earnings beat, a Fed statement, a product announcement) - not generic",
  "position": "long" | "short" | "hold",
  "asset_class": "equity" | "etf" | "option" | "future" | "currency" | "bond" | "commodity",
  "instrument": "the specific ticker/contract/pair/commodity you'd trade, matching asset_class (e.g. 'NVDA', 'TLT', 'AAPL Jan-2027 190 Call', 'CME /ES', 'USD/JPY', 'WTI Crude Oil', 'Gold')",
  "market": "the specific exchange or market this trades on, e.g. 'NASDAQ', 'NYSE', 'Tokyo Stock Exchange (TSE)', 'CME (futures)', 'CBOT (futures)', 'NYMEX (commodities)', 'FX interbank/OTC market'",
  "horizon": "the expected holding period for this specific thesis and what would signal it's time to close the position - e.g. '3-5 days, into the earnings print' or '3-6 months, as the AI capex cycle plays out'. Never intraday/same-day.",
  "explanation": "4-6 sentences, written as spoken talking points, walking through the reasoning chain end to end: what happened -> why it matters for this instrument over the stated horizon -> how the sentiment/valuation/market context supports the position -> why this position specifically (not the alternative). Assume the listener has NOT read the article - make it self-contained. Plain language, no jargon without a quick definition.",
  "rationale": ["2 to 3 short bullet points - a quick-reference cheat sheet version of the explanation, for slides or fast recall during Q&A"],
  "risk": "one sentence on the main risk to this thesis over the stated horizon, phrased so the student can answer 'what could go wrong?' if asked",
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


def _is_daily_quota_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "per day" in text or "tpd" in text or "tokens per day" in text


def analyze_item(client, item: dict) -> tuple:
    """Returns (item, quota_exhausted: bool). quota_exhausted signals the
    caller to stop hitting Groq for the rest of this run - the daily token
    budget is gone and retrying won't help until it rolls over."""
    user_prompt = _build_user_prompt(item)

    last_error = None
    for attempt in range(2):
        try:
            raw = _call_groq(client, user_prompt)
            parsed = json.loads(raw)
            note = TradeNote(**parsed)
            item["analysis"] = note.model_dump()
            return item, False
        except (json.JSONDecodeError, ValidationError, Exception) as exc:
            last_error = exc
            print(f"[analyzer] attempt {attempt + 1} failed for '{item['title'][:60]}': {exc}")
            if _is_daily_quota_error(exc):
                print("[analyzer] daily token quota exhausted, skipping retry and remaining items")
                break
            if "429" in str(exc) or "rate" in str(exc).lower():
                print("[analyzer] rate limited, backing off 20s before retry")
                time.sleep(20)

    quota_exhausted = _is_daily_quota_error(last_error) if last_error else False

    item["analysis"] = {
        "summary": item.get("summary") or item["title"],
        "catalyst": "n/a",
        "position": "hold",
        "asset_class": "equity",
        "instrument": (item.get("tickers") or ["N/A"])[0],
        "market": "n/a",
        "horizon": "n/a",
        "explanation": "Automated analysis failed for this item after two attempts - read the source article directly before presenting on it.",
        "rationale": ["Automated analysis failed; flagged for manual review."],
        "risk": f"Analysis error: {last_error}",
        "confidence": 0.0,
    }
    return item, quota_exhausted


def annotate_items(items: list) -> list:
    from groq import Groq

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set")
    client = Groq(api_key=api_key)

    quota_exhausted = False
    for item in items:
        if quota_exhausted:
            item["analysis"] = {
                "summary": item.get("summary") or item["title"],
                "catalyst": "n/a",
                "position": "hold",
                "asset_class": "equity",
                "instrument": (item.get("tickers") or ["N/A"])[0],
                "market": "n/a",
                "horizon": "n/a",
                "explanation": "Skipped - today's Groq free-tier token budget ran out earlier in this run.",
                "rationale": ["Groq daily token quota exhausted; this item was not analyzed."],
                "risk": "n/a",
                "confidence": 0.0,
            }
            continue
        _, quota_exhausted = analyze_item(client, item)
        time.sleep(1.5)  # stay comfortably under Groq's free-tier per-minute rate limit
    return items
