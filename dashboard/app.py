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
import plotly.graph_objects as go
import requests
import streamlit as st
from plotly.subplots import make_subplots

# Streamlit Community Cloud runs this script from a different working
# directory context than local `streamlit run`, so the repo root isn't
# automatically on sys.path there - add it explicitly before importing
# anything from src.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src import prices, tracker  # noqa: E402

DATA_DIR = os.path.join(_REPO_ROOT, "data")
LATEST_PATH = os.path.join(DATA_DIR, "latest.json")
HISTORY_DIR = os.path.join(DATA_DIR, "history")
TRACK_RECORD_PATH = os.path.join(DATA_DIR, "track_record.json")

GITHUB_OWNER = "PierreKanaan"
GITHUB_REPO = "hedge-fund-news"
GITHUB_WORKFLOW_FILE = "scrape_and_analyze.yml"

POSITION_COLORS = {"long": "#1a7f37", "short": "#c62828", "hold": "#8a6d00"}
ASSET_CLASS_ICONS = {
    "equity": "📈", "etf": "🧺", "option": "🎯", "commodity": "🛢️",
    "future": "⏳", "currency": "💱", "bond": "🏦",
}
VERDICT_LABELS = {
    "hit": "✅ Hit", "miss": "❌ Miss", "flat": "➖ Flat", "open": "⏳ Open", "n/a": "— n/a",
}
# Directional mode: a move smaller than this (either way) is noise, not a
# verdict. 0.2% is roughly a large-cap's bid/ask + a few ticks.
FLUKE_PCT = 0.2
# Take-profit / stop-loss mode defaults - the class's eventual "real"
# strategy; a 2-3% adverse move is within the allowed margin, not a loss.
DEFAULT_TAKE_PROFIT_PCT = 3.0
DEFAULT_STOP_LOSS_PCT = 3.0

# yfinance (period, interval) per timeframe. Intraday bars for the short
# ranges, daily for the medium ones, weekly for 5Y so the chart stays light.
CHART_RANGES = {
    "1D": {"period": "1d", "interval": "5m"},
    "5D": {"period": "5d", "interval": "30m"},
    "1M": {"period": "1mo", "interval": "1d"},
    "3M": {"period": "3mo", "interval": "1d"},
    "6M": {"period": "6mo", "interval": "1d"},
    "YTD": {"period": "ytd", "interval": "1d"},
    "1Y": {"period": "1y", "interval": "1d"},
    "5Y": {"period": "5y", "interval": "1wk"},
}
CHART_TYPES = ["Line", "Candles"]
CHART_INDICATORS = ["SMA 20", "SMA 50", "Volume"]
DEFAULT_CHART_SETTINGS = {"range": "3M", "type": "Line", "indicators": ["Volume"], "entry": True}

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
def cached_ohlc_history(symbol, period, interval):
    return prices.get_ohlc_history(symbol, period=period, interval=interval)


def build_price_figure(df, symbol, interval, chart_type, indicators, entry_price, flagged_at, position):
    """Interactive Plotly price chart. The y-axis autoscales to the data's
    own range (Streamlit's built-in line_chart anchors at zero, which
    flattened every stock's move into a straight line), plus zoom/pan, a
    range slider, optional SMAs/volume, and the entry-price marker so the
    move since the trade was flagged is visible at a glance."""
    show_volume = "Volume" in indicators and df["Volume"].fillna(0).sum() > 0
    fig = make_subplots(
        rows=2 if show_volume else 1, cols=1, shared_xaxes=True,
        row_heights=[0.75, 0.25] if show_volume else [1.0], vertical_spacing=0.03,
    )
    line_color = POSITION_COLORS.get(position, "#1f77b4")

    if chart_type == "Candles":
        fig.add_trace(go.Candlestick(
            x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
            name=symbol, increasing_line_color="#1a7f37", decreasing_line_color="#c62828",
        ), row=1, col=1)
    else:
        fig.add_trace(go.Scatter(
            x=df.index, y=df["Close"], mode="lines", name=symbol,
            line=dict(color=line_color, width=2),
            hovertemplate="%{x|%b %d %Y %H:%M}<br>Close: %{y:,.2f}<extra></extra>",
        ), row=1, col=1)

    for label, window, color in (("SMA 20", 20, "#f28e2b"), ("SMA 50", 50, "#7b4fbf")):
        if label in indicators and len(df) >= window:
            fig.add_trace(go.Scatter(
                x=df.index, y=df["Close"].rolling(window).mean(), mode="lines",
                name=label, line=dict(color=color, width=1.2, dash="dot"),
                hovertemplate=label + ": %{y:,.2f}<extra></extra>",
            ), row=1, col=1)

    if show_volume:
        up = df["Close"] >= df["Open"]
        fig.add_trace(go.Bar(
            x=df.index, y=df["Volume"], name="Volume", marker_color=up.map({True: "#1a7f37", False: "#c62828"}),
            opacity=0.45, hovertemplate="Vol: %{y:,.0f}<extra></extra>",
        ), row=2, col=1)

    if entry_price is not None:
        fig.add_hline(
            y=entry_price, line=dict(color="#888", width=1, dash="dash"), row=1, col=1,
            annotation_text=f"entry ${entry_price:,.2f}", annotation_position="top left",
            annotation_font=dict(size=11, color="#888"),
        )
    if flagged_at is not None:
        flagged_ts = pd.Timestamp(flagged_at)
        idx_tz = df.index.tz
        flagged_ts = flagged_ts.tz_convert(idx_tz) if flagged_ts.tzinfo and idx_tz else flagged_ts.tz_localize(None)
        if df.index.min() <= flagged_ts <= df.index.max():
            fig.add_vline(x=flagged_ts, line=dict(color="#888", width=1, dash="dot"), row=1, col=1)

    layout = dict(
        height=380 if show_volume else 300, margin=dict(l=10, r=10, t=10, b=10),
        showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0, font=dict(size=11)),
        hovermode="x unified", dragmode="zoom",
        xaxis=dict(rangeslider=dict(visible=not show_volume, thickness=0.06)),
    )
    fig.update_layout(**layout)
    fig.update_yaxes(autorange=True, fixedrange=False, tickformat=",.2f", row=1, col=1)
    if show_volume:
        fig.update_yaxes(showticklabels=False, row=2, col=1)
        fig.update_xaxes(rangeslider=dict(visible=False), row=1, col=1)
    if interval in ("1d", "1wk"):
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])  # hide weekend gaps
    fig.update_xaxes(showspikes=True, spikemode="across", spikesnap="cursor", spikethickness=1)
    return fig


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
    sectors_present = sorted({i.get("sector") for i in items if i.get("sector")})

    filter_cols = st.columns([2, 2, 3, 3])
    with filter_cols[0]:
        ticker_filter = st.multiselect("Ticker", all_tickers)
    with filter_cols[1]:
        sector_filter = st.multiselect("Sector", sectors_present)
    with filter_cols[2]:
        position_filter = st.segmented_control(
            "Position", ["long", "short", "hold"], selection_mode="multi", default=[]
        )
    with filter_cols[3]:
        asset_class_filter = st.segmented_control(
            "Asset class", asset_classes_present, selection_mode="multi", default=[]
        )

    filtered = items
    if ticker_filter:
        filtered = [i for i in filtered if set(i.get("tickers", [])) & set(ticker_filter)]
    if sector_filter:
        filtered = [i for i in filtered if i.get("sector") in sector_filter]
    if position_filter:
        filtered = [i for i in filtered if i.get("analysis", {}).get("position") in position_filter]
    if asset_class_filter:
        filtered = [i for i in filtered if i.get("analysis", {}).get("asset_class") in asset_class_filter]

    st.caption(f"Showing {len(filtered)} of {len(items)} items")

    with st.expander("⚙️ Chart defaults (each card can override its own timeframe)", expanded=False):
        c1, c2, c3, c4 = st.columns([2.2, 1.2, 2, 1])
        default_range = c1.segmented_control(
            "Timeframe", list(CHART_RANGES.keys()),
            default=DEFAULT_CHART_SETTINGS["range"], key="chart_default_range",
        ) or DEFAULT_CHART_SETTINGS["range"]
        chart_type = c2.segmented_control(
            "Type", CHART_TYPES, default=DEFAULT_CHART_SETTINGS["type"], key="chart_type",
        ) or DEFAULT_CHART_SETTINGS["type"]
        indicators = c3.multiselect(
            "Indicators", CHART_INDICATORS, default=DEFAULT_CHART_SETTINGS["indicators"], key="chart_indicators",
        )
        show_entry = c4.toggle("Entry marker", value=DEFAULT_CHART_SETTINGS["entry"], key="chart_entry")
        st.caption("Charts are interactive: drag to zoom, double-click to reset, hover for values.")

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
                {item.get('source','')} · {published} · tickers: {tickers} · sector: {item.get('sector') or 'Macro / cross-asset'}
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
            # Keying on default_range makes a card's override reset whenever
            # the global default changes, otherwise it'd silently stick.
            card_range = st.segmented_control(
                f"📉 {symbol}", list(CHART_RANGES.keys()), default=default_range,
                key=f"range_{item['id']}_{default_range}", label_visibility="visible",
            ) or default_range
            range_cfg = CHART_RANGES[card_range]
            df = cached_ohlc_history(symbol, range_cfg["period"], range_cfg["interval"])
            if df is not None and not df.empty:
                entry_price = item.get("entry_price")
                last_close = float(df["Close"].iloc[-1])
                caption = f"{symbol} · {card_range} · last {last_close:,.2f}"
                if entry_price:
                    move = (last_close - entry_price) / entry_price * 100
                    caption += f" · entry {entry_price:,.2f} when flagged ({move:+.1f}% since)"
                st.caption(caption)
                fig = build_price_figure(
                    df, symbol, range_cfg["interval"], chart_type, indicators,
                    entry_price if show_entry else None,
                    report.get("generated_at") if show_entry else None,
                    position,
                )
                st.plotly_chart(fig, use_container_width=True, key=f"chart_{item['id']}",
                                config={"displaylogo": False, "scrollZoom": True})
            else:
                st.caption(f"Chart unavailable for {symbol} on this timeframe right now.")
        else:
            st.caption("No chartable symbol for this instrument (e.g. a specific option contract).")
        st.markdown("</div>", unsafe_allow_html=True)


def render_track_record():
    st.subheader("📊 Track Record")

    track = load_report(TRACK_RECORD_PATH)
    if not track or not track.get("picks"):
        st.info("No scoreable long/short picks yet - the track record fills in as daily runs accumulate.")
        return

    pick_dates = sorted({p["date"] for p in track["picks"].values()})
    first_day = date.fromisoformat(pick_dates[0])
    today = date.today()

    with st.container(border=True):
        c1, c2, c3 = st.columns([2, 2, 1.4])
        mode_label = c1.segmented_control(
            "Scoring rule", ["Directional", "Take-profit / stop-loss"],
            default="Directional", key="tr_mode",
        ) or "Directional"
        mode = "directional" if mode_label == "Directional" else "tp_sl"
        if mode == "directional":
            fluke = c2.number_input(
                "Ignore moves smaller than (%)", min_value=0.0, max_value=5.0,
                value=FLUKE_PCT, step=0.1, format="%.1f", key="tr_fluke",
                help="Anything inside this band is a flat, not a hit or a miss.",
            )
            tp = sl = None
        else:
            cc1, cc2 = c2.columns(2)
            tp = cc1.number_input("Take profit (%)", 0.5, 50.0, DEFAULT_TAKE_PROFIT_PCT, 0.5, key="tr_tp")
            sl = cc2.number_input("Stop loss (%)", 0.5, 50.0, DEFAULT_STOP_LOSS_PCT, 0.5, key="tr_sl")
            fluke = FLUKE_PCT
        as_of = c3.date_input("As of", value=today, min_value=first_day, max_value=today, key="tr_asof")
        live = as_of >= today
        if mode == "directional":
            st.caption(
                f"Every long/short pick vs. {'the live price right now' if live else f'the close on {as_of}'}. "
                f"A move in the pick's direction above {fluke:.1f}% is a Hit, against it a Miss, inside that band a Flat. "
                "Re-judged every time you look, so a Hit can turn into a Miss tomorrow - pick a past date to see how it stood then."
            )
        else:
            st.caption(
                f"Walks each pick's daily highs/lows since entry: first touch of +{tp:.1f}% is a Hit, "
                f"-{sl:.1f}% a Miss (same-day touch of both counts as the stop). Untouched picks stay Open with unrealized P&L. "
                f"Evaluated as of {'now' if live else as_of}."
            )

    as_of_str = as_of.isoformat()
    rows = []
    for pid, pick in track["picks"].items():
        if pick["date"] > as_of_str:
            continue
        path = tracker.price_path(track, pick["symbol"], pick["date"], as_of_str)
        live_price = cached_last_price(pick["symbol"]) if live else None
        result = tracker.score_pick(
            pick, path, live_price=live_price, mode=mode, fluke_pct=fluke,
            take_profit_pct=tp or DEFAULT_TAKE_PROFIT_PCT, stop_loss_pct=sl or DEFAULT_STOP_LOSS_PCT,
        )
        sign = 1 if pick["position"] == "long" else -1
        spark = [round(sign * (c - pick["entry_price"]) / pick["entry_price"] * 100, 2) for _d, _o, _h, _l, c in path]
        if live_price is not None:
            spark.append(round(sign * (live_price - pick["entry_price"]) / pick["entry_price"] * 100, 2))
        rows.append({
            "date": pick["date"], "title": pick["title"][:70], "position": pick["position"],
            "instrument": pick["instrument"], "symbol": pick["symbol"],
            "entry_price": pick["entry_price"], "price": result["price"],
            "pnl_pct": result["pct"], "verdict": result["verdict"], "path": spark or [0.0],
            "days": len(path),
        })

    if not rows:
        st.info("No picks on or before that date.")
        return

    hits = sum(1 for r in rows if r["verdict"] == "hit")
    misses = sum(1 for r in rows if r["verdict"] == "miss")
    undecided = len(rows) - hits - misses
    scored = hits + misses
    pnls = [r["pnl_pct"] for r in rows if r["pnl_pct"] is not None]
    avg_pnl = sum(pnls) / len(pnls) if pnls else None

    m = st.columns(5)
    m[0].metric("Hit rate", f"{hits / scored:.0%}" if scored else "n/a")
    m[1].metric("Hits", hits)
    m[2].metric("Misses", misses)
    m[3].metric("Flat / open", undecided)
    m[4].metric("Avg P&L per pick", f"{avg_pnl:+.2f}%" if avg_pnl is not None else "n/a",
                help="Signed in the pick's favour: a short that fell 2% counts as +2%.")

    # Per-report-day scoreboard: "what did the news from day X turn into?"
    by_day = {}
    for r in rows:
        d = by_day.setdefault(r["date"], {"picks": 0, "hits": 0, "misses": 0, "pnl": []})
        d["picks"] += 1
        d["hits"] += r["verdict"] == "hit"
        d["misses"] += r["verdict"] == "miss"
        if r["pnl_pct"] is not None:
            d["pnl"].append(r["pnl_pct"])
    day_rows = []
    for d, v in sorted(by_day.items(), reverse=True):
        sc = v["hits"] + v["misses"]
        day_rows.append({
            "Report day": d, "Picks": v["picks"], "Hits": v["hits"], "Misses": v["misses"],
            "Undecided": v["picks"] - sc,
            "Hit rate": f"{v['hits'] / sc:.0%}" if sc else "n/a",
            "Avg P&L": f"{sum(v['pnl']) / len(v['pnl']):+.2f}%" if v["pnl"] else "n/a",
        })
    st.markdown("**By report day**")
    st.dataframe(pd.DataFrame(day_rows), width="stretch", hide_index=True)

    st.markdown("**Every pick**")
    df = pd.DataFrame(rows).sort_values(["date", "pnl_pct"], ascending=[False, False])
    df["verdict"] = df["verdict"].map(lambda v: VERDICT_LABELS.get(v, "— n/a"))
    df = df.rename(columns={
        "date": "Date", "title": "Headline", "position": "Position", "instrument": "Instrument",
        "symbol": "Symbol", "entry_price": "Entry $", "price": "Price $", "pnl_pct": "P&L %",
        "verdict": "Verdict", "path": "Path since entry", "days": "Days",
    })
    st.dataframe(
        df, width="stretch", hide_index=True,
        column_config={
            "P&L %": st.column_config.NumberColumn(format="%+.2f%%"),
            "Entry $": st.column_config.NumberColumn(format="%.2f"),
            "Price $": st.column_config.NumberColumn(format="%.2f"),
            "Path since entry": st.column_config.LineChartColumn(
                "P&L path %", help="Daily P&L % in the pick's favour since entry (last point = latest price)",
            ),
        },
    )
    st.caption(
        f"{len(track['picks'])} picks tracked since {pick_dates[0]} across {len(track.get('prices', {}))} symbols. "
        "Daily bars are stored by the morning pipeline run, so past-date views use official closes; "
        "today's view uses the live price."
    )


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
