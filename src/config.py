"""
Central place to tune what the fund covers. Edit SECTORS and MACRO_KEYWORDS
to match your group's strategy/thesis for the semester.
"""

# Sectors the fund covers, each with a watchlist of tickers and a relevance
# weight. Weight influences which news wins one of the day's limited item
# slots (see scraper._item_score) - it's a multiplier on top of relevance
# signals like a ticker match and recency, not a hard quota or filter. That
# means a high-weight sector (Technology) usually dominates, but a very
# fresh/important story in a lower-weight sector can still outrank a stale,
# minor tech story - weight tilts the odds, it doesn't guarantee the outcome.
SECTORS = {
    "Technology / AI & Semiconductors": {
        "weight": 2.0,
        "tickers": ["AAPL", "MSFT", "NVDA"],
    },
    "Consumer Discretionary": {
        "weight": 1.0,
        "tickers": ["AMZN", "TSLA"],
    },
    "Healthcare / Pharma": {
        "weight": 1.0,
        "tickers": ["JNJ", "UNH", "LLY", "PFE"],
    },
    "Financials / Banks": {
        "weight": 1.0,
        "tickers": ["JPM", "GS", "BAC", "WFC"],
    },
    "Energy": {
        "weight": 1.0,
        "tickers": ["XOM", "CVX", "OXY"],
    },
    "Agriculture / Commodities": {
        "weight": 1.0,
        "tickers": ["ADM", "DE", "MOS", "CTVA"],
    },
    "Industrials / Defense": {
        "weight": 1.0,
        "tickers": ["BA", "LMT", "CAT"],
    },
    "Consumer Staples": {
        "weight": 0.8,
        "tickers": ["PG", "KO", "WMT"],
    },
}

# Derived lookups - built once here so scraper.py/analyzer.py/dashboard
# don't each have to flatten SECTORS themselves.
WATCHLIST = [t for s in SECTORS.values() for t in s["tickers"]]
TICKER_SECTOR = {t: name for name, s in SECTORS.items() for t in s["tickers"]}
TICKER_SECTOR_WEIGHT = {t: s["weight"] for s in SECTORS.values() for t in s["tickers"]}

# Weights applied to the FINAL display/sort order only (the LLM decides
# asset class during analysis, after news has already been selected, so
# this can't influence which news gets picked the way sector weight does).
ASSET_CLASS_WEIGHTS = {
    "equity": 1.0, "etf": 0.9, "commodity": 0.9, "option": 0.7,
    "future": 0.6, "currency": 0.6, "bond": 0.6,
}

# Purely descriptive, passed to the LLM as context so it knows the fund's
# overall mandate. Kept separate from SECTORS' tickers/weights above.
SECTOR_FOCUS = list(SECTORS.keys())

# Keywords that flag a broad macro/market-moving story even if it doesn't
# mention a watchlist ticker. Covers rates/inflation, but also FX, bonds,
# futures/commodities, and non-US markets (esp. Japan) so the fund isn't
# limited to US large-cap equity news - a hedge fund trades across all of
# these asset classes and markets.
MACRO_KEYWORDS = [
    # Rates / inflation / US macro
    "federal reserve", "fed ", "interest rate", "rate hike", "rate cut", "inflation",
    "cpi", "jobs report", "unemployment", "gdp", "recession", "s&p 500", "nasdaq",
    "dow jones", "treasury yield", "10-year", "yield curve",
    # Currencies / FX
    "dollar index", "dxy", "currency", "forex", "fx market", "usd/jpy", "eur/usd",
    "yen", "euro", "pound sterling",
    # Bonds / rates products
    "bond market", "bond yield", "treasury note", "treasury bond",
    # Futures / commodities
    "futures", "crude oil", "wti", "brent", "opec", "gold price", "commodities",
    "natural gas", "silver", "copper", "wheat", "corn", "soybean",
    # Geopolitical - these move commodities (esp. oil) even when the
    # headline doesn't mention "oil" or "commodity" directly
    "middle east", "israel", "iran", "strait of hormuz", "houthi", "red sea",
    "geopolitical", "sanctions",
    # Non-US markets, esp. Japan
    "bank of japan", "boj", "nikkei", "japan", "tokyo stock exchange",
    "ecb", "european central bank", "bank of england", "china", "tariff",
]

# Free RSS feeds, no API key required.
RSS_FEEDS = [
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=%5EGSPC&region=US&lang=en-US",
    "https://www.marketwatch.com/rss/topstories",
    "https://www.marketwatch.com/rss/marketpulse",
    "https://www.cnbc.com/id/20910258/device/rss/rss.html",  # CNBC Markets
    "https://www.investing.com/rss/news_25.rss",  # Investing.com stock market news
    "https://seekingalpha.com/market_currents.xml",
]

# How far back to look for news (hours)
LOOKBACK_HOURS = 48

# Max number of items to run through sentiment + LLM analysis per pipeline run
# (keeps each run fast/cheap and within free API rate limits)
MAX_ITEMS_PER_RUN = 40

# Repo identity, used by the dashboard's "run scraper now" button to trigger
# the GitHub Actions workflow via the GitHub API.
GITHUB_OWNER = "PierreKanaan"
GITHUB_REPO_NAME = "hedge-fund-news"
GITHUB_WORKFLOW_FILE = "scrape_and_analyze.yml"

# Groq model used for summary/recommendation generation.
# Groq's free-tier model lineup changes over time - if this starts 404ing,
# run `curl https://api.groq.com/openai/v1/models -H "Authorization: Bearer $GROQ_API_KEY"`
# to see what's currently available and swap the id below.
GROQ_MODEL = "openai/gpt-oss-120b"

# Hugging Face model id for finance sentiment
FINBERT_MODEL = "ProsusAI/finbert"

DATA_DIR = "data"
LATEST_PATH = f"{DATA_DIR}/latest.json"
HISTORY_DIR = f"{DATA_DIR}/history"
