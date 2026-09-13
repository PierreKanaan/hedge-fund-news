"""
Pulls recent financial news from free RSS feeds + the Finnhub free API,
deduplicates, tags items with matched watchlist tickers / macro relevance,
and extracts full article text for downstream analysis.
"""
import hashlib
import os
import time
from datetime import datetime, timedelta, timezone

import feedparser
import requests
import trafilatura

from src.config import (
    RSS_FEEDS,
    WATCHLIST,
    MACRO_KEYWORDS,
    LOOKBACK_HOURS,
    MAX_ITEMS_PER_RUN,
)

FINNHUB_BASE = "https://finnhub.io/api/v1"


def _item_id(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def _match_tickers(text: str) -> list:
    text_upper = text.upper()
    return [t for t in WATCHLIST if t in text_upper]


def _is_macro(text: str) -> bool:
    text_lower = text.lower()
    return any(kw in text_lower for kw in MACRO_KEYWORDS)


def _within_lookback(published: datetime) -> bool:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    return published >= cutoff


def _parse_feed_time(entry) -> datetime:
    for key in ("published_parsed", "updated_parsed"):
        val = getattr(entry, key, None)
        if val:
            return datetime.fromtimestamp(time.mktime(val), tz=timezone.utc)
    return datetime.now(timezone.utc)


def fetch_rss_items() -> list:
    items = []
    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
        except Exception as exc:
            print(f"[scraper] failed to parse feed {feed_url}: {exc}")
            continue
        source = feed.feed.get("title", feed_url)
        for entry in feed.entries:
            title = entry.get("title", "").strip()
            summary = entry.get("summary", "").strip()
            url = entry.get("link", "").strip()
            if not title or not url:
                continue
            published = _parse_feed_time(entry)
            if not _within_lookback(published):
                continue
            combined = f"{title} {summary}"
            items.append(
                {
                    "id": _item_id(url),
                    "title": title,
                    "summary": summary,
                    "url": url,
                    "source": source,
                    "published_at": published.isoformat(),
                    "tickers": _match_tickers(combined),
                    "is_macro": _is_macro(combined),
                }
            )
    return items


def fetch_finnhub_items(api_key: str) -> list:
    if not api_key:
        print("[scraper] no FINNHUB_API_KEY set, skipping Finnhub")
        return []

    items = []

    # General market news + dedicated forex news (so currency stories show up
    # reliably rather than relying only on keyword matches in general news)
    for category in ("general", "forex"):
        try:
            resp = requests.get(
                f"{FINNHUB_BASE}/news",
                params={"category": category, "token": api_key},
                timeout=15,
            )
            resp.raise_for_status()
            for entry in resp.json():
                published = datetime.fromtimestamp(entry.get("datetime", 0), tz=timezone.utc)
                if not _within_lookback(published):
                    continue
                title = entry.get("headline", "").strip()
                summary = entry.get("summary", "").strip()
                url = entry.get("url", "").strip()
                if not title or not url:
                    continue
                combined = f"{title} {summary}"
                items.append(
                    {
                        "id": _item_id(url),
                        "title": title,
                        "summary": summary,
                        "url": url,
                        "source": entry.get("source", "Finnhub"),
                        "published_at": published.isoformat(),
                        "tickers": _match_tickers(combined),
                        "is_macro": _is_macro(combined) or category == "forex",
                    }
                )
        except Exception as exc:
            print(f"[scraper] Finnhub {category} news request failed: {exc}")

    # Company-specific news for each watchlist ticker
    today = datetime.now(timezone.utc).date()
    from_date = today - timedelta(days=3)
    for ticker in WATCHLIST:
        try:
            resp = requests.get(
                f"{FINNHUB_BASE}/company-news",
                params={
                    "symbol": ticker,
                    "from": from_date.isoformat(),
                    "to": today.isoformat(),
                    "token": api_key,
                },
                timeout=15,
            )
            resp.raise_for_status()
            for entry in resp.json():
                published = datetime.fromtimestamp(entry.get("datetime", 0), tz=timezone.utc)
                if not _within_lookback(published):
                    continue
                title = entry.get("headline", "").strip()
                summary = entry.get("summary", "").strip()
                url = entry.get("url", "").strip()
                if not title or not url:
                    continue
                items.append(
                    {
                        "id": _item_id(url),
                        "title": title,
                        "summary": summary,
                        "url": url,
                        "source": entry.get("source", "Finnhub"),
                        "published_at": published.isoformat(),
                        "tickers": sorted(set(_match_tickers(f"{title} {summary}") + [ticker])),
                        "is_macro": _is_macro(f"{title} {summary}"),
                    }
                )
        except Exception as exc:
            print(f"[scraper] Finnhub company news failed for {ticker}: {exc}")

    return items


def dedupe(items: list) -> list:
    seen = {}
    for item in items:
        key = item["id"]
        if key not in seen:
            seen[key] = item
        else:
            # Prefer the version that already has tickers/macro tags if duplicate
            existing = seen[key]
            existing["tickers"] = sorted(set(existing["tickers"] + item["tickers"]))
            existing["is_macro"] = existing["is_macro"] or item["is_macro"]
    return list(seen.values())


def rank_and_trim(items: list, limit: int) -> list:
    def score(item):
        return (len(item["tickers"]) > 0, item["is_macro"], item["published_at"])

    ranked = sorted(items, key=score, reverse=True)
    return ranked[:limit]


def attach_full_text(items: list) -> list:
    for item in items:
        try:
            downloaded = trafilatura.fetch_url(item["url"])
            text = trafilatura.extract(downloaded) if downloaded else None
            item["text"] = text or item["summary"]
        except Exception as exc:
            print(f"[scraper] full-text extraction failed for {item['url']}: {exc}")
            item["text"] = item["summary"]
    return items


def scrape() -> list:
    finnhub_key = os.environ.get("FINNHUB_API_KEY", "")
    rss_items = fetch_rss_items()
    finnhub_items = fetch_finnhub_items(finnhub_key)
    print(f"[scraper] RSS: {len(rss_items)} items, Finnhub: {len(finnhub_items)} items")

    all_items = dedupe(rss_items + finnhub_items)
    relevant = [i for i in all_items if i["tickers"] or i["is_macro"]]
    print(f"[scraper] {len(relevant)}/{len(all_items)} items relevant (watchlist or macro)")

    trimmed = rank_and_trim(relevant, MAX_ITEMS_PER_RUN)
    trimmed = attach_full_text(trimmed)
    return trimmed


if __name__ == "__main__":
    for i in scrape():
        print(f"- [{i['source']}] {i['title']} (tickers={i['tickers']}, macro={i['is_macro']})")
