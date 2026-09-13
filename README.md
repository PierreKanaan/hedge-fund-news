# Fund News Digest

Automated pipeline for a student "hedge fund" group project: scrapes financial
news, runs it through FinBERT (sentiment) + Groq (an LLM) to produce a
summary, a recommended position (long/short/hold) across any asset class a
fund might trade (equities, ETFs, options, futures, currencies, bonds) with
the specific exchange/market it trades on, a holding horizon (days to
months - never day-trade/intraday calls), and a presentation-ready
explanation, then delivers it every morning via email and a live dashboard.
100% free stack.

## Stack

| Piece            | Tool                                  | Why |
|-------------------|----------------------------------------|-----|
| News scraping      | `feedparser` (RSS) + Finnhub free API | No cost, no scraping fragility |
| Full article text  | `trafilatura`                          | Clean text extraction for the LLM |
| Sentiment           | FinBERT (`ProsusAI/finbert`), local CPU inference | Open-source, finance-tuned, no API dependency |
| Summary/recommendation | Groq API (free, hosts Llama 3.3 etc.) | Fast, generous free tier, structured JSON output |
| Scheduling            | GitHub Actions (cron, free)         | Runs even if your laptop is off |
| Email                  | Gmail SMTP + App Password           | Free, no third-party email service |
| Dashboard               | Streamlit Community Cloud (free)  | Live, browsable from phone or laptop |

## One-time setup

### 1. Get free API keys
- **Groq**: sign up at https://console.groq.com → API Keys → create a key.
- **Finnhub**: sign up at https://finnhub.io/register → your key is on the dashboard.

### 2. Gmail App Password (for sending the digest)
1. Enable 2-Step Verification on the Gmail account you want to send from.
2. Go to https://myaccount.google.com/apppasswords, create an app password
   (name it "fund-news" or similar).
3. Save the 16-character password — you'll never see it again after this.

### 3. Local `.env` (for testing before pushing to GitHub)
```
cp .env.example .env
# then fill in GROQ_API_KEY, FINNHUB_API_KEY, GMAIL_ADDRESS, GMAIL_APP_PASSWORD, EMAIL_RECIPIENTS
```

### 4. Install dependencies and test locally
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Dry run: scrapes + scores + writes data/latest.json, no email sent.
# Works even without GROQ_API_KEY (uses placeholder analysis) so you can
# sanity-check the scraper and dashboard first.
python -m src.pipeline --dry-run

# View the dashboard locally
streamlit run dashboard/app.py

# Full run (needs all 5 env vars set), sends a real email:
python -m src.pipeline
```

### 5. Push to GitHub
```bash
gh repo create hedge-fund-news --public --source=. --remote=origin
git add -A
git commit -m "Initial fund news digest pipeline"
git push -u origin main
```
(No `gh` CLI? Create an empty repo at github.com/new, then:
`git remote add origin <your-repo-url> && git branch -M main && git push -u origin main`)

### 6. Add secrets to GitHub
Repo → Settings → Secrets and variables → Actions → New repository secret.
Add all 5: `GROQ_API_KEY`, `FINNHUB_API_KEY`, `GMAIL_ADDRESS`,
`GMAIL_APP_PASSWORD`, `EMAIL_RECIPIENTS` (comma-separated emails).

Test it: Actions tab → "Scrape, analyze, and email fund news digest" →
Run workflow (uses the `workflow_dispatch` trigger, no need to wait for the
schedule).

### 7. Deploy the dashboard
1. Go to https://share.streamlit.io, sign in with GitHub.
2. "New app" → pick your repo → main file path: `dashboard/app.py`.
3. Deploy. You'll get a public URL — bookmark it on your phone.
   (Free tier apps sleep after ~12h with no visitors; the first open after a
   gap takes ~30-60s to wake up, so open it a minute before presenting.)

### 8. Enable the "Run scraper now" button on the dashboard
The dashboard has a button that triggers a fresh scrape/analysis run on
demand, by calling the GitHub Actions API - separate from the repo secrets
in step 6, this needs a token added to the *Streamlit app's own* secrets:
1. Create a GitHub token: https://github.com/settings/tokens → "Fine-grained
   tokens" → generate one scoped to just this repo, with **Actions:
   Read and write** permission.
2. In Streamlit Community Cloud: open your app → Settings → Secrets → add:
   ```
   GITHUB_TOKEN = "your token here"
   ```
3. Save. The button will now work; without this it just shows a clear
   message instead of failing silently.

## Customizing

- **Watchlist / sectors / macro keywords**: edit `src/config.py`.
- **Schedule**: edit the `cron` line in `.github/workflows/scrape_and_analyze.yml`.
- **How many items per run**: `MAX_ITEMS_PER_RUN` in `src/config.py` (currently 40).
- **Email look**: `src/emailer.py` (`_item_html` / `build_digest_html`).
- **Dashboard look**: `dashboard/app.py` (CSS is inline at the top of the file).

## A real limit worth knowing: Groq's daily token cap

Groq's free tier caps usage at **200,000 tokens/day** (separate from, and
usually tighter than, its per-minute limit) - shared across *every* call:
the scheduled run, any manual "Run scraper now" clicks, and local testing.
One scheduled run of 40 items comfortably fits (roughly 90k-120k tokens), but
repeatedly re-running the pipeline the same day (e.g. testing, or clicking
"Run scraper now" more than once or twice) can exhaust it. When that
happens, remaining items for that run get a "Groq daily token quota
exhausted" placeholder instead of real analysis (the pipeline fails fast and
gracefully rather than hanging or crashing) - it recovers gradually over the
following ~24h on a rolling basis, no action needed, just don't re-trigger
runs back-to-back the same day.

## Project layout
```
src/
  config.py     watchlist, RSS feeds, macro keywords, tunables
  scraper.py    RSS + Finnhub fetch, dedupe, relevance filter, full-text extraction
  sentiment.py  FinBERT scoring (local CPU inference)
  analyzer.py   Groq call -> structured summary/position/rationale/risk
  emailer.py    HTML digest + Gmail SMTP send
  pipeline.py   orchestrates the full run, writes data/latest.json + history
dashboard/
  app.py        Streamlit dashboard
data/
  latest.json          most recent run
  history/YYYY-MM-DD.json
.github/workflows/
  scrape_and_analyze.yml   scheduled + manually-triggerable CI job
```
