"""
Streamlit dashboard for the fund's news digest. Deployed free on Streamlit
Community Cloud, reading the JSON files that GitHub Actions commits to
data/latest.json and data/history/.

Run locally:  streamlit run dashboard/app.py
"""
import glob
import json
import os

import pandas as pd
import streamlit as st

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
LATEST_PATH = os.path.join(DATA_DIR, "latest.json")
HISTORY_DIR = os.path.join(DATA_DIR, "history")

st.set_page_config(page_title="Fund News Dashboard", layout="wide")

POSITION_COLORS = {"long": "#1a7f37", "short": "#c62828", "hold": "#8a6d00"}


@st.cache_data(ttl=300)
def load_report(path):
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def list_history_dates():
    files = sorted(glob.glob(os.path.join(HISTORY_DIR, "*.json")), reverse=True)
    return [os.path.splitext(os.path.basename(f))[0] for f in files]


st.title("📈 Fund News Dashboard")

dates = list_history_dates()
choice = st.sidebar.selectbox("Report date", ["latest"] + dates)
path = LATEST_PATH if choice == "latest" else os.path.join(HISTORY_DIR, f"{choice}.json")

report = load_report(path)

if not report:
    st.warning(
        "No report found yet. Run `python -m src.pipeline --dry-run` locally, "
        "or wait for the next scheduled GitHub Actions run."
    )
    st.stop()

st.caption(f"Generated at {report.get('generated_at', 'unknown')} · {report.get('item_count', 0)} items")

items = report.get("items", [])
if not items:
    st.info("No relevant items in this report.")
    st.stop()

all_tickers = sorted({t for i in items for t in i.get("tickers", [])})
positions = sorted({i.get("analysis", {}).get("position", "hold") for i in items})

ticker_filter = st.sidebar.multiselect("Filter by ticker", all_tickers)
position_filter = st.sidebar.multiselect("Filter by position", positions)

filtered = items
if ticker_filter:
    filtered = [i for i in filtered if set(i.get("tickers", [])) & set(ticker_filter)]
if position_filter:
    filtered = [i for i in filtered if i.get("analysis", {}).get("position") in position_filter]

st.sidebar.markdown("---")
st.sidebar.metric("Items shown", len(filtered))

for item in filtered:
    a = item.get("analysis", {})
    position = a.get("position", "hold")
    color = POSITION_COLORS.get(position, "#444")
    sentiment = item.get("sentiment", {})

    with st.container(border=True):
        st.markdown(f"#### [{item['title']}]({item['url']})")
        meta_cols = st.columns([3, 2, 2])
        meta_cols[0].caption(f"{item.get('source', '')}")
        meta_cols[1].caption(f"Tickers: {', '.join(item.get('tickers', [])) or '—'}")
        meta_cols[2].caption(f"FinBERT: {sentiment.get('label', 'n/a')} ({sentiment.get('confidence', 0)})")

        st.write(a.get("summary", ""))
        st.caption(f"**Catalyst:** {a.get('catalyst', '')}")
        st.markdown(
            f"<span style='background:{color};color:white;padding:4px 12px;"
            f"border-radius:12px;font-weight:600;'>{position.upper()} — {a.get('instrument','')} "
            f"· confidence {a.get('confidence', 0):.0%}</span>",
            unsafe_allow_html=True,
        )
        st.markdown("**Talking points (read this to the class):**")
        st.info(a.get("explanation", ""))
        st.markdown("**Cheat-sheet bullets:**")
        for bullet in a.get("rationale", []):
            st.markdown(f"- {bullet}")
        st.caption(f"⚠️ If they ask \"what could go wrong\": {a.get('risk', '')}")
