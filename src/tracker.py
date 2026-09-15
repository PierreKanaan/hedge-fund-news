"""
Persistent track record for every long/short pick the pipeline has ever made.

Why a separate file instead of re-deriving from data/history/*.json on each
dashboard open: history files carry full article text (~250KB/day), and
judging a pick needs the price PATH since entry (for take-profit/stop-loss
rules later), which would mean a yfinance call per symbol on every page load.
Instead the daily pipeline run appends one day of OHLC per symbol here, so
the dashboard can score any pick as of any past date from one small file,
and a live-price call is only needed for "as of right now".

Layout of data/track_record.json:
    picks:  {item_id: {date, title, symbol, position, instrument, entry_price, ...}}
    prices: {symbol: {"YYYY-MM-DD": [open, high, low, close]}}   # daily bars,
            from the earliest pick on that symbol onward (~30 bytes/bar)

Usage:
    python -m src.tracker --backfill   # (re)build from every data/history/*.json
"""
import argparse
import glob
import json
import os
import time
from datetime import date, datetime, timedelta

import yfinance as yf

from src.config import HISTORY_DIR, TRACK_RECORD_PATH

SCOREABLE_POSITIONS = ("long", "short")


def load(path=TRACK_RECORD_PATH) -> dict:
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"updated_at": None, "picks": {}, "prices": {}}


def save(track: dict, path=TRACK_RECORD_PATH):
    track["updated_at"] = datetime.utcnow().isoformat()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(track, f, separators=(",", ":"), sort_keys=True)


def register_report(track: dict, report: dict) -> int:
    """Adds the report's scoreable picks (long/short with a chart symbol and
    an entry price). A pick already registered keeps its original entry -
    re-running a day never rewrites history."""
    report_date = report.get("generated_at", "")[:10]
    added = 0
    for item in report.get("items", []):
        a = item.get("analysis") or {}
        position = a.get("position")
        symbol = item.get("chart_symbol")
        entry_price = item.get("entry_price")
        if position not in SCOREABLE_POSITIONS or not symbol or entry_price is None:
            continue
        pid = item["id"]
        if pid in track["picks"]:
            continue
        track["picks"][pid] = {
            "date": report_date,
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "symbol": symbol,
            "position": position,
            "instrument": a.get("instrument", ""),
            "asset_class": a.get("asset_class", ""),
            "sector": item.get("sector"),
            "entry_price": entry_price,
            "confidence": a.get("confidence"),
        }
        added += 1
    return added


def refresh_prices(track: dict, pause: float = 0.3) -> int:
    """Fetches daily OHLC for every tracked symbol from its earliest pick to
    today and merges it in (existing bars are overwritten with the latest
    values, which also cleans up any partial bar saved mid-session)."""
    earliest = {}
    for pick in track["picks"].values():
        sym = pick["symbol"]
        earliest[sym] = min(earliest.get(sym, pick["date"]), pick["date"])

    bars_added = 0
    for sym, start in sorted(earliest.items()):
        try:
            hist = yf.Ticker(sym).history(start=start, interval="1d", auto_adjust=False)
        except Exception as exc:
            print(f"[tracker] history fetch failed for {sym}: {exc}")
            continue
        if hist is None or hist.empty:
            continue
        store = track["prices"].setdefault(sym, {})
        for ts, row in hist.iterrows():
            bar = [round(float(row[c]), 4) for c in ("Open", "High", "Low", "Close")]
            key = ts.date().isoformat()
            if key not in store:
                bars_added += 1
            store[key] = bar
        time.sleep(pause)
    return bars_added


def update_from_report(report: dict, path=TRACK_RECORD_PATH) -> dict:
    """Pipeline hook: register today's picks, then top up daily bars for
    every symbol ever picked."""
    track = load(path)
    added = register_report(track, report)
    bars = refresh_prices(track)
    save(track, path)
    print(f"[tracker] +{added} picks, +{bars} daily bars -> {len(track['picks'])} picks, "
          f"{len(track['prices'])} symbols tracked ({path})")
    return track


def backfill(path=TRACK_RECORD_PATH) -> dict:
    track = load(path)
    for f in sorted(glob.glob(os.path.join(HISTORY_DIR, "*.json"))):
        with open(f) as fh:
            report = json.load(fh)
        added = register_report(track, report)
        print(f"[tracker] {os.path.basename(f)}: +{added} picks")
    bars = refresh_prices(track)
    save(track, path)
    print(f"[tracker] backfill done: {len(track['picks'])} picks, {len(track['prices'])} symbols, +{bars} bars")
    return track


# ---------- Scoring (pure functions, shared with the dashboard) ----------

def price_path(track: dict, symbol: str, start: str, end: str) -> list:
    """Daily bars for symbol with start <= date <= end, oldest first, as
    (date, open, high, low, close). The entry day is included: the pipeline
    runs pre-market (or, for a manual run, mid-session), so the entry price
    is the prior close / price at that moment and the rest of that day is
    a real move. For a weekend report the first bar is simply Monday's."""
    bars = track.get("prices", {}).get(symbol, {})
    return [(d, *bars[d]) for d in sorted(bars) if start <= d <= end]


def score_pick(pick: dict, path: list, live_price=None, mode="directional",
               fluke_pct=0.2, take_profit_pct=3.0, stop_loss_pct=3.0) -> dict:
    """Judges one pick given the bars since entry (see price_path) and an
    optional live price for the most recent point.

    directional: hit if the latest price has moved in the pick's direction by
        more than fluke_pct, miss if against it by more than fluke_pct, else
        flat. Re-evaluated on every view, so a hit can become a miss.
    tp_sl: walk the daily highs/lows since entry; the first level touched
        wins (take profit -> hit, stop loss -> miss). Nothing touched yet ->
        open, showing unrealized P&L. Path-dependent, so it needs the bars.
    Returns: verdict, pct (signed, in the pick's favour when positive), price.
    """
    entry = pick["entry_price"]
    sign = 1 if pick["position"] == "long" else -1
    latest_price = live_price if live_price is not None else (path[-1][4] if path else None)
    if latest_price is None or not entry:
        return {"verdict": "n/a", "pct": None, "price": None, "raw_pct": None}
    raw_pct = (latest_price - entry) / entry * 100
    pnl_pct = sign * raw_pct

    if mode == "tp_sl":
        for _d, _o, hi, lo, _c in path:
            best = sign * ((hi if sign > 0 else lo) - entry) / entry * 100
            worst = sign * ((lo if sign > 0 else hi) - entry) / entry * 100
            # Conservative: if both levels were touched on the same day,
            # assume the stop hit first.
            if worst <= -stop_loss_pct:
                return {"verdict": "miss", "pct": round(-stop_loss_pct, 2), "price": latest_price, "raw_pct": round(raw_pct, 2)}
            if best >= take_profit_pct:
                return {"verdict": "hit", "pct": round(take_profit_pct, 2), "price": latest_price, "raw_pct": round(raw_pct, 2)}
        if live_price is not None:  # intraday, not yet in a daily bar
            if pnl_pct <= -stop_loss_pct:
                return {"verdict": "miss", "pct": round(-stop_loss_pct, 2), "price": latest_price, "raw_pct": round(raw_pct, 2)}
            if pnl_pct >= take_profit_pct:
                return {"verdict": "hit", "pct": round(take_profit_pct, 2), "price": latest_price, "raw_pct": round(raw_pct, 2)}
        return {"verdict": "open", "pct": round(pnl_pct, 2), "price": latest_price, "raw_pct": round(raw_pct, 2)}

    if pnl_pct > fluke_pct:
        verdict = "hit"
    elif pnl_pct < -fluke_pct:
        verdict = "miss"
    else:
        verdict = "flat"
    return {"verdict": verdict, "pct": round(pnl_pct, 2), "price": latest_price, "raw_pct": round(raw_pct, 2)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--backfill", action="store_true", help="rebuild from data/history/*.json")
    args = parser.parse_args()
    if args.backfill:
        backfill()
    else:
        parser.print_help()
