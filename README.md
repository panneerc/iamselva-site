# iamselva.com — Markets, Stocks & News

A free, self-updating website, hosted on GitHub Pages and refreshed every 5 minutes.

| Tab | What it shows | Source |
|---|---|---|
| **Markets** | Ticker tape, market overview (SPY, QQQ, DIA, IWM, Sensex, Nifty) and market headlines | TradingView, MarketWatch, Yahoo Finance, Google News |
| **Top 100 Stocks** | S&P 500 heat map and the biggest US stocks by market value | TradingView |
| **Analyst Ratings** | Upgrades, downgrades, new coverage and price-target changes (JPMorgan, Goldman Sachs, Morgan Stanley, BofA and more), plus buy/hold/sell counts for your watchlist and whether analysts got more or less bullish since last month | News headlines (parsed), Finnhub |
| **Earnings** | Your watchlist's next results, everyone reporting in the next 2 weeks (biggest first), and the US/India economic calendar | Finnhub, TradingView |
| **Penny Stocks** | This week's penny-stock articles (Yahoo Finance and others) and live prices for the stocks under $5 they name | Google News, Finnhub |
| **Sports, Arsenal & CSK, Tech & Azure, India, Richmond** | Headlines | RSS feeds |

**How it works:** GitHub Actions runs `scripts/fetch_news.py` every 5 minutes. It reads the feeds in `feeds.json`, asks Finnhub for quotes, analyst counts and earnings dates, saves `data/news.json` and `data/research.json`, and republishes the site. Hosting is free; you only pay GoDaddy for the domain.

Only headline + short teaser + link are shown, and every item links back to the original publisher.

---

## Turn on live prices, analyst counts and earnings dates (free, one time)

Without this key, the Analyst Ratings headlines, penny-stock articles and economic calendar still work. With it, you also get prices, buy/hold/sell counts and the earnings calendar.

1. Go to https://finnhub.io and click **Get free API key**. Sign up (no card needed).
2. Copy the key shown on your dashboard.
3. In your GitHub repo: **Settings → Secrets and variables → Actions → New repository secret**.
   - Name: `FINNHUB_API_KEY`
   - Secret: paste the key → **Add secret**.
4. **Actions** tab → **Update headlines and publish site** → **Run workflow**.

The free plan allows 60 requests a minute. Each update uses about 16, so you're well inside it. Analyst counts are re-checked once a day and the earnings calendar every 4 hours, because they change slowly.

## Customizing

All of this is in `feeds.json` (edit on GitHub with the pencil icon, then commit; the site rebuilds itself):

- **Your watchlist:** `research.watchlist`, e.g. `["AAPL", "MSFT", "NVDA"]`. Used for the analyst table and "Your stocks' next results".
- **Penny stocks you always want checked:** `research.penny_watchlist`, e.g. `["SNDL", "OCGN"]`.
- **Penny price limit:** `research.penny_max_price` (default 5).
- **How far ahead earnings go:** `research.earnings_days_ahead` (default 14).
- **More analyst news:** add Google News searches to `research.analyst_feeds`, e.g.
  `https://news.google.com/rss/search?q=Citi+upgrades+OR+downgrades+when:3d&hl=en-US&gl=US&ceid=US:en`
- **Headline tabs:** add/remove RSS feeds in `sections`. Copy a section block to add a new tab.
- **Ticker symbols:** edit `WATCHLIST` near the bottom of `index.html` (TradingView symbols, e.g. `NASDAQ:AMD`, `NYSE:JPM`).

## Good to know

- **Prices:** TradingView widgets show exchange data; US quotes in free widgets and on Finnhub's free plan can be delayed by up to 15 minutes. Index levels use the ETFs that track them (SPY, QQQ, DIA) because the official index feeds are not licensed for free widgets.
- **Analyst rating changes** are read from news headlines, so a few may be missed or show without a rating or target. Detailed rating feeds (Benzinga, Finnhub premium) cost money.
- **Scheduled runs** can be a few minutes late when GitHub is busy. If updates ever stop, open **Actions → Update headlines and publish site** and click **Enable workflow**.

## Troubleshooting

- **A run is red:** click it → open the failed step to read the error. One broken feed never fails the run; it's skipped.
- **"This part needs a free data key":** the `FINNHUB_API_KEY` secret is missing or misspelled (see above).
- **Test locally:** `pip install feedparser requests`, then `FINNHUB_API_KEY=yourkey python scripts/fetch_news.py`, then `python -m http.server` and open http://localhost:8000.

---
Analyst ratings are opinions. Nothing on this site is financial advice.
