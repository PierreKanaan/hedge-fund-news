"""
Finance-tuned sentiment scoring using FinBERT (ProsusAI/finbert), run locally
on CPU via transformers. No API key or network dependency at inference time
beyond the one-time model download (cached by the transformers/HF cache).
"""
from functools import lru_cache

from src.config import FINBERT_MODEL

_LABELS = ["positive", "negative", "neutral"]


@lru_cache(maxsize=1)
def _get_pipeline():
    from transformers import AutoModelForSequenceClassification, AutoTokenizer, pipeline

    tokenizer = AutoTokenizer.from_pretrained(FINBERT_MODEL)
    model = AutoModelForSequenceClassification.from_pretrained(FINBERT_MODEL)
    return pipeline(
        "text-classification",
        model=model,
        tokenizer=tokenizer,
        top_k=None,
        truncation=True,
        max_length=512,
        device=-1,  # CPU
    )


def score_text(text: str) -> dict:
    """Returns {"label": "positive"|"negative"|"neutral", "confidence": float}."""
    if not text or not text.strip():
        return {"label": "neutral", "confidence": 0.0}

    clf = _get_pipeline()
    results = clf(text[:2000])[0]  # list of {label, score} for all classes
    best = max(results, key=lambda r: r["score"])
    return {"label": best["label"].lower(), "confidence": round(float(best["score"]), 4)}


def annotate_items(items: list) -> list:
    for item in items:
        basis = f"{item['title']}. {item.get('summary', '')}"
        item["sentiment"] = score_text(basis)
    return items


if __name__ == "__main__":
    samples = [
        "Company beats earnings expectations, raises full-year guidance.",
        "Regulators fine the bank amid ongoing fraud investigation.",
        "The company will hold its annual meeting next month.",
    ]
    for s in samples:
        print(s, "->", score_text(s))
