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

# Common commodity names (as the LLM would write them in plain English) ->
# yfinance's continuous-contract ticker. Checked as a case-insensitive
# substring match against the instrument text, since commodities are
# usually named in prose ("WTI Crude Oil", "Gold") rather than as a ticker.
_COMMODITY_MAP = {
    "wti": "CL=F", "crude oil": "CL=F", "brent": "BZ=F",
    "natural gas": "NG=F", "gold": "GC=F", "silver": "SI=F", "copper": "HG=F",
    "corn": "ZC=F", "wheat": "ZW=F", "soybean": "ZS=F",
    "coffee": "KC=F", "cotton": "CT=F", "sugar": "SB=F",
}

_PLAIN_TICKER_RE = re.compile(r"^[A-Z]{1,5}$")
_SLASH_PAIR_RE = re.compile(r"^([A-Z]{2,5})/([A-Z]{2,5})$")
_LEADING_TICKER_RE = re.compile(r"^([A-Z]{1,5})\b")


def resolve_chart_symbol(item: dict):
    """Best-effort mapping from a recommendation to a yfinance-chartable
    symbol. Always tries the actual recommended 'instrument' text FIRST -
    that's what the position is actually about. The matched watchlist
    ticker is only a last-resort fallback, since it can be an unrelated
    incidental mention in the article (e.g. a crypto piece that name-drops
    an AI stock for comparison) rather than the real underlying."""
    instrument = (item.get("analysis", {}) or {}).get("instrument", "").strip()

    if instrument:
        if _PLAIN_TICKER_RE.match(instrument):
            return instrument
        if instrument in _FX_MAP:
            return _FX_MAP[instrument]
        instrument_lower = instrument.lower()
        for name, symbol in _COMMODITY_MAP.items():
            if name in instrument_lower:
                return symbol
        pair_match = _SLASH_PAIR_RE.match(instrument)
        if pair_match:
            # Not a recognized FX major - most likely a crypto pair (e.g.
            # "XRP/USD"), which yfinance addresses as "XRP-USD".
            base, quote = pair_match.groups()
            return f"{base}-{quote}"
        for code, symbol in _FUTURES_MAP.items():
            if code in instrument:
                return symbol
        # Longer descriptive instrument, e.g. an options contract like
        # "AAPL Jan-2027 190 Call" - chart the underlying it's named after.
        leading = _LEADING_TICKER_RE.match(instrument)
        if leading:
            return leading.group(1)

    tickers = item.get("tickers") or []
    if tickers:
        return tickers[0]
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


def get_price_history(symbol, period="1mo", interval="1d"):
    if not symbol:
        return None
    try:
        hist = yf.Ticker(symbol).history(period=period, interval=interval)
        if hist.empty:
            return None
        return hist["Close"]
    except Exception as exc:
        print(f"[prices] failed to fetch history for {symbol}: {exc}")
        return None
