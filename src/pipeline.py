"""
Orchestrates the full run: scrape -> sentiment -> LLM analysis -> persist -> email.

Usage:
    python -m src.pipeline                       # full run, sends email
    python -m src.pipeline --dry-run              # no email, but still calls Groq
                                                    # for real analysis (uses quota)
    python -m src.pipeline --dry-run --skip-groq  # fully free test: scrape, sentiment,
                                                    # price snapshots, placeholder analysis -
                                                    # no email, no Groq quota used at all.
                                                    # Good for testing the scraper/ranking/
                                                    # dashboard without touching the daily
                                                    # token budget.
"""
import argparse
import json
import os
from datetime import datetime, timezone

from src.config import LATEST_PATH, HISTORY_DIR, DATA_DIR
from src import scraper, sentiment, prices


def _mock_analysis(items: list) -> list:
    """Used in --dry-run when no GROQ_API_KEY is available, so the pipeline
    can still be tested end-to-end (scrape/sentiment/persist/dashboard)."""
    for item in items:
        item["analysis"] = {
            "summary": item.get("summary") or item["title"],
            "catalyst": "n/a (dry run)",
            "position": "hold",
            "asset_class": "equity",
            "instrument": (item.get("tickers") or ["N/A"])[0],
            "market": "n/a (dry run)",
            "horizon": "n/a (dry run)",
            "explanation": "[dry-run] Groq not called - set GROQ_API_KEY for a real explanation.",
            "rationale": ["[dry-run] Groq not called - set GROQ_API_KEY for real analysis."],
            "risk": "n/a (dry run)",
            "confidence": 0.0,
        }
    return items


def run(dry_run: bool = False, skip_groq: bool = False) -> dict:
    print("[pipeline] scraping...")
    items = scraper.scrape()

    print("[pipeline] scoring sentiment (FinBERT)...")
    items = sentiment.annotate_items(items)

    if os.environ.get("GROQ_API_KEY") and not skip_groq:
        print("[pipeline] running LLM analysis (Groq)...")
        from src import analyzer

        items = analyzer.annotate_items(items)
    else:
        reason = "--skip-groq passed" if skip_groq else "GROQ_API_KEY not set"
        print(f"[pipeline] {reason}, using placeholder analysis (no Groq quota used)")
        items = _mock_analysis(items)

    print("[pipeline] snapshotting entry prices...")
    for item in items:
        symbol = prices.resolve_chart_symbol(item)
        item["chart_symbol"] = symbol
        item["entry_price"] = prices.get_last_price(symbol) if symbol else None

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "item_count": len(items),
        "items": items,
    }

    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(HISTORY_DIR, exist_ok=True)
    with open(LATEST_PATH, "w") as f:
        json.dump(report, f, indent=2)
    history_path = f"{HISTORY_DIR}/{datetime.now(timezone.utc).date().isoformat()}.json"
    with open(history_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"[pipeline] wrote {LATEST_PATH} and {history_path}")

    if not dry_run:
        from src import emailer

        emailer.send_digest(report)
    else:
        print("[pipeline] dry-run: skipping email")

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="skip sending email")
    parser.add_argument(
        "--skip-groq", action="store_true",
        help="use placeholder analysis instead of calling Groq - free, uses no daily token quota",
    )
    args = parser.parse_args()
    run(dry_run=args.dry_run, skip_groq=args.skip_groq)
