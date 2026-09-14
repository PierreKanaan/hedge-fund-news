"""
Lightweight price lookups via yfinance (free, no API key) - used to snapshot
an "entry price" for each recommendation (for the track record) and to draw
small price charts on the dashboard. Yahoo's API is unofficial/undocumented,
so every call here is best-effort: failures return None rather than raising,
since a missing price or chart should never break the rest of the pipeline
or dashboard.
"""
import re

import yfinance as yf

# A handful of common currency-pair spellings, mapped to yfinance's FX
# ticker format (e.g. "USD/JPY" quotes JPY per USD -> yfinance symbol "JPY=X").
_FX_MAP = {
    "USD/JPY": "JPY=X", "EUR/USD": "EURUSD=X", "GBP/USD": "GBPUSD=X",
    "USD/CHF": "CHF=X", "AUD/USD": "AUDUSD=X", "USD/CAD": "CAD=X",
}

# Common futures shorthand -> yfinance's continuous-contract ticker.
_FUTURES_MAP = {
    "/ES": "ES=F", "/NQ": "NQ=F", "/CL": "CL=F", "/GC": "GC=F", "/ZN": "ZN=F",
    "/YM": "YM=F", "/RTY": "RTY=F", "/SI": "SI=F",
}

_PLAIN_TICKER_RE = re.compile(r"^[A-Z]{1,5}$")


def resolve_chart_symbol(item: dict):
    """Best-effort mapping from a recommendation to a yfinance-chartable
    symbol. Prefers the matched watchlist ticker (most reliable - it's the
    real company driving the thesis even when the recommended instrument is
    a derivative on it), then falls back to parsing the free-form
    'instrument' text for FX/futures/plain-ticker cases. Returns None (skip
    charting) for anything else, e.g. a specific options contract, rather
    than guessing at something that might mislead."""
    tickers = item.get("tickers") or []
    if tickers:
        return tickers[0]

    instrument = (item.get("analysis", {}) or {}).get("instrument", "").strip()
    if not instrument:
        return None
    if instrument in _FX_MAP:
        return _FX_MAP[instrument]
    for code, symbol in _FUTURES_MAP.items():
        if code in instrument:
            return symbol
    if _PLAIN_TICKER_RE.match(instrument):
        return instrument
    return None


def get_last_price(symbol):
    if not symbol:
        return None
    try:
        hist = yf.Ticker(symbol).history(period="5d")
        if hist.empty:
            return None
        return round(float(hist["Close"].iloc[-1]), 2)
    except Exception as exc:
        print(f"[prices] failed to fetch last price for {symbol}: {exc}")
        return None


def get_price_history(symbol, period="1mo"):
    if not symbol:
        return None
    try:
        hist = yf.Ticker(symbol).history(period=period)
        if hist.empty:
            return None
        return hist["Close"]
    except Exception as exc:
        print(f"[prices] failed to fetch history for {symbol}: {exc}")
        return None
