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
