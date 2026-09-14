"""
Streamlit dashboard for the fund's news digest. Deployed free on Streamlit
Community Cloud, reading the JSON files that GitHub Actions commits to
data/latest.json and data/history/.

Run locally:  streamlit run dashboard/app.py
"""
import glob
import json
import os
import sys
from datetime import date, datetime

import pandas as pd
import requests
import streamlit as st

# Streamlit Community Cloud runs this script from a different working
# directory context than local `streamlit run`, so the repo root isn't
# automatically on sys.path there - add it explicitly before importing
# anything from src.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src import prices  # noqa: E402

DATA_DIR = os.path.join(_REPO_ROOT, "data")
LATEST_PATH = os.path.join(DATA_DIR, "latest.json")
HISTORY_DIR = os.path.join(DATA_DIR, "history")

GITHUB_OWNER = "PierreKanaan"
GITHUB_REPO = "hedge-fund-news"
GITHUB_WORKFLOW_FILE = "scrape_and_analyze.yml"

POSITION_COLORS = {"long": "#1a7f37", "short": "#c62828", "hold": "#8a6d00"}
ASSET_CLASS_ICONS = {
    "equity": "📈", "etf": "🧺", "option": "🎯",
    "future": "⏳", "currency": "💱", "bond": "🏦",
}
VERDICT_LABELS = {"hit": "✅ Hit", "miss": "❌ Miss", "too_early": "⏳ Too early"}
TRACK_RECORD_GRACE_DAYS = 2
TRACK_RECORD_THRESHOLD_PCT = 1.0

CHART_RANGES = {
    "Day": {"period": "1d", "interval": "5m"},
    "Week": {"period": "5d", "interval": "30m"},
    "Month": {"period": "1mo", "interval": "1d"},
}

st.set_page_config(page_title="Fund News Dashboard", page_icon="📈", layout="wide")

st.markdown(
    """
    <style>
    @keyframes fadeInUp {
        from { opacity: 0; transform: translateY(10px); }
        to   { opacity: 1; transform: translateY(0); }
    }
    .news-card {
        animation: fadeInUp 0.45s ease both;
        border: 1px solid rgba(128,128,128,0.25);
        border-radius: 12px 12px 0 0;
        padding: 18px 20px 8px 20px;
        margin-top: 16px;
        transition: box-shadow 0.15s ease;
    }
    .news-card:hover { box-shadow: 0 6px 18px rgba(0,0,0,0.12); }
    .news-title { font-size: 16px; font-weight: 700; margin-bottom: 4px; }
    .news-title a { text-decoration: none; color: inherit; }
    .news-title a:hover { text-decoration: underline; }
    .news-meta { font-size: 12px; opacity: 0.65; margin-bottom: 10px; }
    .pill {
        display: inline-block; color: #fff; font-size: 12px; font-weight: 700;
        padding: 4px 12px; border-radius: 14px; margin-bottom: 8px;
    }
    .subtle-box {
        background: rgba(128,128,128,0.08); border-radius: 8px;
        padding: 10px 14px; font-size: 13.5px; line-height: 1.55; margin: 8px 0;
    }
    .risk-line { font-size: 12.5px; opacity: 0.8; margin-top: 6px; }
    .chart-wrap {
        border: 1px solid rgba(128,128,128,0.25); border-top: none;
        border-radius: 0 0 12px 12px; padding: 4px 20px 14px 20px; margin-bottom: 16px;
    }
    div[data-testid="stButton"] button { transition: transform 0.1s ease; }
    div[data-testid="stButton"] button:hover { transform: scale(1.02); }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(ttl=120)
def load_report(path):
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


@st.cache_data(ttl=900)
def cached_price_history(symbol, period, interval):
    hist = prices.get_price_history(symbol, period=period, interval=interval)
    return hist.to_dict() if hist is not None else None


@st.cache_data(ttl=1800)
def cached_last_price(symbol):
    return prices.get_last_price(symbol)


def list_history_dates():
    files = sorted(glob.glob(os.path.join(HISTORY_DIR, "*.json")))
    return [os.path.splitext(os.path.basename(f))[0] for f in files]


def trigger_scraper():
    token = None
    try:
        token = st.secrets.get("GITHUB_TOKEN")
    except Exception:
        token = None
    if not token:
        return False, "No GITHUB_TOKEN configured in this app's Streamlit secrets - see README."

    url = (
        f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
        f"/actions/workflows/{GITHUB_WORKFLOW_FILE}/dispatches"
    )
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    try:
        resp = requests.post(url, headers=headers, json={"ref": "main"}, timeout=15)
        if resp.status_code == 204:
            return True, "Scraper run triggered - takes about 3-6 minutes. Refresh this page after that."
        return False, f"GitHub API error {resp.status_code}: {resp.text[:200]}"
    except Exception as exc:
        return False, str(exc)


def render_news_feed():
    dates = list_history_dates()  # ascending, oldest -> newest
    if "date_idx" not in st.session_state:
        st.session_state.date_idx = len(dates) - 1 if dates else 0

    nav_cols = st.columns([1, 3, 1])
    with nav_cols[0]:
        if st.button("◀ Previous day", disabled=st.session_state.date_idx <= 0):
            st.session_state.date_idx -= 1
    with nav_cols[2]:
        if st.button("Next day ▶", disabled=st.session_state.date_idx >= len(dates) - 1):
            st.session_state.date_idx += 1

    if dates:
        selected_date = dates[st.session_state.date_idx]
        try:
            pretty_date = datetime.strptime(selected_date, "%Y-%m-%d").strftime("%A, %B %d %Y")
        except ValueError:
            pretty_date = selected_date
        with nav_cols[1]:
            st.markdown(f"<h4 style='text-align:center;'>{pretty_date}</h4>", unsafe_allow_html=True)
        path = os.path.join(HISTORY_DIR, f"{selected_date}.json")
    else:
        path = LATEST_PATH

    report = load_report(path)

    if not report:
        st.warning(
            "No report found yet. Run `python -m src.pipeline --dry-run` locally, "
            "or click **Run scraper now** above / wait for the next scheduled run."
        )
        return

    st.caption(f"Generated at {report.get('generated_at', 'unknown')} · {report.get('item_count', 0)} items")

    items = report.get("items", [])
    if not items:
        st.info("No relevant items in this report.")
        return

    positions_all = [i.get("analysis", {}).get("position", "hold") for i in items]
    metric_cols = st.columns(4)
    metric_cols[0].metric("Total items", len(items))
    metric_cols[1].metric("Long", positions_all.count("long"))
    metric_cols[2].metric("Short", positions_all.count("short"))
    metric_cols[3].metric("Hold", positions_all.count("hold"))

    st.markdown("---")

    all_tickers = sorted({t for i in items for t in i.get("tickers", [])})
    asset_classes_present = sorted({i.get("analysis", {}).get("asset_class", "equity") for i in items})

    filter_cols = st.columns([2, 3, 3])
    with filter_cols[0]:
        ticker_filter = st.multiselect("Ticker", all_tickers)
    with filter_cols[1]:
        position_filter = st.segmented_control(
            "Position", ["long", "short", "hold"], selection_mode="multi", default=[]
        )
    with filter_cols[2]:
        asset_class_filter = st.segmented_control(
            "Asset class", asset_classes_present, selection_mode="multi", default=[]
        )

    filtered = items
    if ticker_filter:
        filtered = [i for i in filtered if set(i.get("tickers", [])) & set(ticker_filter)]
    if position_filter:
        filtered = [i for i in filtered if i.get("analysis", {}).get("position") in position_filter]
    if asset_class_filter:
        filtered = [i for i in filtered if i.get("analysis", {}).get("asset_class") in asset_class_filter]

    st.caption(f"Showing {len(filtered)} of {len(items)} items")

    chart_range = st.segmented_control(
        "Chart range (applies to all charts below)",
        list(CHART_RANGES.keys()), default="Month", key="chart_range",
    ) or "Month"
    range_cfg = CHART_RANGES[chart_range]

    for idx, item in enumerate(filtered):
        a = item.get("analysis", {})
        position = a.get("position", "hold")
        color = POSITION_COLORS.get(position, "#444")
        asset_class = a.get("asset_class", "equity")
        icon = ASSET_CLASS_ICONS.get(asset_class, "📄")
        sentiment = item.get("sentiment", {})
        tickers = ", ".join(item.get("tickers", [])) or "—"
        rationale_html = "".join(f"<li>{r}</li>" for r in a.get("rationale", []))

        try:
            published = datetime.fromisoformat(item.get("published_at", "")).strftime("%b %d, %Y · %H:%M UTC")
        except ValueError:
            published = item.get("published_at", "")

        st.markdown(
            f"""
            <div class="news-card" style="animation-delay:{min(idx, 8) * 0.05}s;">
              <div class="news-title"><a href="{item['url']}" target="_blank">{item['title']}</a></div>
              <div class="news-meta">
                {item.get('source','')} · {published} · tickers: {tickers}
                · FinBERT: {sentiment.get('label','n/a')} ({sentiment.get('confidence', 0)})
              </div>
              <div class="subtle-box"><b>Catalyst:</b> {a.get('catalyst','')}</div>
              <span class="pill" style="background:{color};">
                {icon} {position.upper()} — {a.get('instrument','')} ({asset_class}) · confidence {a.get('confidence', 0):.0%}
              </span>
              <div class="news-meta"><b>Market:</b> {a.get('market','')} &nbsp;·&nbsp; <b>Horizon:</b> {a.get('horizon','')}</div>
              <div class="subtle-box"><b>Talking points (read this to the class):</b><br>{a.get('explanation','')}</div>
              <div style="font-size:13px;"><b>Cheat-sheet bullets:</b>
                <ul style="margin:4px 0 4px 18px;padding:0;">{rationale_html}</ul>
              </div>
              <div class="risk-line">⚠️ If they ask "what could go wrong": {a.get('risk','')}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        symbol = item.get("chart_symbol")
        st.markdown('<div class="chart-wrap">', unsafe_allow_html=True)
        if symbol:
            hist_dict = cached_price_history(symbol, range_cfg["period"], range_cfg["interval"])
            if hist_dict:
                series = pd.Series(hist_dict)
                entry_price = item.get("entry_price")
                caption = f"📉 {symbol} - {chart_range.lower()} view"
                if entry_price is not None:
                    caption += f" · entry price when flagged: ${entry_price}"
                st.caption(caption)
                st.line_chart(series, height=160)
            else:
                st.caption(f"Chart unavailable for {symbol} on this timeframe right now.")
        else:
            st.caption("No chartable symbol for this instrument (e.g. a specific option contract).")
        st.markdown("</div>", unsafe_allow_html=True)


def render_track_record():
    st.subheader("📊 Track Record")
    st.caption(
        f"Every long/short pick vs. its price today. Picks younger than "
        f"{TRACK_RECORD_GRACE_DAYS} days are marked \"too early\" rather than scored - "
        f"not enough time has passed to judge the thesis fairly. Holds aren't directional "
        f"bets, so they're excluded from scoring."
    )

    files = sorted(glob.glob(os.path.join(HISTORY_DIR, "*.json")))
    rows = []
    for f in files:
        rep = load_report(f)
        if not rep:
            continue
        report_date = rep.get("generated_at", "")[:10]
        for item in rep.get("items", []):
            a = item.get("analysis", {})
            position = a.get("position")
            symbol = item.get("chart_symbol")
            entry_price = item.get("entry_price")
            if position not in ("long", "short") or not symbol or entry_price is None:
                continue
            rows.append(
                {
                    "date": report_date,
                    "title": item.get("title", "")[:70],
                    "position": position,
                    "instrument": a.get("instrument", ""),
                    "symbol": symbol,
                    "entry_price": entry_price,
                }
            )

    if not rows:
        st.info("No scoreable long/short picks yet - track record fills in as reports accumulate.")
        return

    today = date.today()
    for row in rows:
        current_price = cached_last_price(row["symbol"])
        row["current_price"] = current_price
        try:
            days_old = (today - date.fromisoformat(row["date"])).days
        except ValueError:
            days_old = 0

        if current_price is None:
            row["pct_change"] = None
            row["verdict"] = "n/a"
            continue

        pct_change = (current_price - row["entry_price"]) / row["entry_price"] * 100
        row["pct_change"] = round(pct_change, 2)

        if days_old < TRACK_RECORD_GRACE_DAYS:
            row["verdict"] = "too_early"
        elif row["position"] == "long":
            row["verdict"] = "hit" if pct_change >= TRACK_RECORD_THRESHOLD_PCT else (
                "miss" if pct_change <= -TRACK_RECORD_THRESHOLD_PCT else "too_early"
            )
        else:  # short
            row["verdict"] = "hit" if pct_change <= -TRACK_RECORD_THRESHOLD_PCT else (
                "miss" if pct_change >= TRACK_RECORD_THRESHOLD_PCT else "too_early"
            )

    hits = sum(1 for r in rows if r["verdict"] == "hit")
    misses = sum(1 for r in rows if r["verdict"] == "miss")
    too_early = sum(1 for r in rows if r["verdict"] in ("too_early", "n/a"))
    scored = hits + misses
    hit_rate = f"{hits / scored:.0%}" if scored else "n/a"

    metric_cols = st.columns(4)
    metric_cols[0].metric("Hit rate", hit_rate)
    metric_cols[1].metric("Hits", hits)
    metric_cols[2].metric("Misses", misses)
    metric_cols[3].metric("Too early / pending", too_early)

    df = pd.DataFrame(rows).sort_values("date", ascending=False)
    df["verdict"] = df["verdict"].map(lambda v: VERDICT_LABELS.get(v, "— n/a"))
    df = df.rename(columns={
        "date": "Date", "title": "Headline", "position": "Position", "instrument": "Instrument",
        "symbol": "Chart symbol", "entry_price": "Entry $", "current_price": "Current $",
        "pct_change": "% change", "verdict": "Verdict",
    })
    st.dataframe(df, width="stretch", hide_index=True)


# ---------- Header + top controls ----------
header_cols = st.columns([3, 1])
with header_cols[0]:
    st.title("📈 Fund News Dashboard")
with header_cols[1]:
    if st.button("🔄 Run scraper now", width="stretch"):
        ok, message = trigger_scraper()
        (st.success if ok else st.error)(message)

tab_feed, tab_track_record = st.tabs(["📰 News Feed", "📊 Track Record"])
with tab_feed:
    render_news_feed()
with tab_track_record:
    render_track_record()
