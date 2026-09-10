"""
Central place to tune what the fund covers. Edit WATCHLIST and MACRO_KEYWORDS
to match your group's strategy/thesis for the semester.
"""

# Tickers/companies your fund actively covers. Used to pull ticker-specific
# news from Finnhub and to prioritize relevance when scoring headlines.
WATCHLIST = [
    "AAPL",
    "MSFT",
    "NVDA",
    "TSLA",
    "AMZN",
]

# Sectors/themes, purely descriptive - passed to the LLM as context so it
# knows your fund's mandate when suggesting positions.
SECTOR_FOCUS = ["Technology", "AI/Semiconductors", "Consumer Discretionary"]

# Keywords that flag a broad macro/market-moving story even if it doesn't
# mention a watchlist ticker (rates, inflation, Fed, indices, etc.)
MACRO_KEYWORDS = [
    "federal reserve", "fed ", "interest rate", "inflation", "cpi", "jobs report",
    "unemployment", "gdp", "recession", "s&p 500", "nasdaq", "dow jones",
    "treasury yield", "ecb", "tariff", "oil price", "opec",
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
MAX_ITEMS_PER_RUN = 16

# Groq model used for summary/recommendation generation
GROQ_MODEL = "llama-3.3-70b-versatile"

# Hugging Face model id for finance sentiment
FINBERT_MODEL = "ProsusAI/finbert"

DATA_DIR = "data"
LATEST_PATH = f"{DATA_DIR}/latest.json"
HISTORY_DIR = f"{DATA_DIR}/history"
