# iamselva.com — Markets, Betting & News dashboard

A free, self-updating website:

| Tab | What it shows |
|---|---|
| **Markets** | Live ticker tape + market overview (TradingView) and stock/earnings headlines |
| **Betting** | Best moneyline odds across US sportsbooks (NFL, NBA, Premier League, IPL) + betting news |
| **Arsenal & CSK** | Arsenal and Chennai Super Kings news |
| **Tech & Azure** | Azure service updates, Azure blog, The Verge, Ars Technica |
| **India** | National + Tamil Nadu / Chennai news |
| **Richmond** | Richmond, VA local news |

**How it works:** GitHub Actions runs `scripts/fetch_news.py` every hour. It reads the RSS feeds in `feeds.json` (and the odds API, if you add a key), saves `data/news.json` + `data/odds.json`, and republishes the site on GitHub Pages. Hosting is free; you only pay GoDaddy for the domain.

Only headline + short teaser + link are shown, and every item links back to the original publisher.

---

## Setup (about 30–45 minutes, one time)

### 1. Create a GitHub account
Go to https://github.com/signup (free). Skip if you have one.

### 2. Create the repository
1. Click **+** (top right) → **New repository**.
2. Name: `iamselva-site` · Visibility: **Public** (free GitHub Pages needs public) · leave everything else unchecked.
3. Click **Create repository**.

### 3. Upload the files
1. Unzip `iamselva-site.zip` on your computer.
2. On the new repo page click **uploading an existing file**.
3. Open the unzipped folder, select **everything inside it** (including the `.github` folder) and drag it into the browser.
4. Click **Commit changes**.
5. Check that you can see `.github/workflows/update.yml` in the repo.
   *If the `.github` folder didn't upload:* click **Add file → Create new file**, type the name `.github/workflows/update.yml`, paste the contents of that file, and commit.

### 4. Turn on GitHub Pages
1. Repo **Settings → Pages**.
2. Under **Build and deployment → Source**, choose **GitHub Actions**.

### 5. Allow the updater to save data
1. Repo **Settings → Actions → General**.
2. Scroll to **Workflow permissions** → choose **Read and write permissions** → **Save**.

### 6. Run it the first time
1. Go to the **Actions** tab (click **I understand… enable them** if asked).
2. Click **Update headlines and publish site** → **Run workflow** → **Run workflow**.
3. Wait ~1–2 minutes for the green check. Your site is now live at
   `https://YOUR-GITHUB-USERNAME.github.io/iamselva-site/`
   From now on it refreshes every hour by itself.

### 7. (Optional, recommended) Turn on live betting odds
1. Sign up free at https://the-odds-api.com (Starter plan: 500 credits/month, no card).
2. Copy your API key from the email/dashboard.
3. Repo **Settings → Secrets and variables → Actions → New repository secret**.
   Name: `ODDS_API_KEY` · Secret: *paste key* → **Add secret**.
4. **Actions → Update headlines and publish site → Run workflow**, tick **Fetch odds now**, run.

Odds refresh every 8 hours (4 leagues × 3 times a day ≈ 372 credits/month), so the free plan is never exceeded. Leagues that are out of season are simply hidden.

### 8. Point iamselva.com to the new site (GoDaddy)
1. In GoDaddy, if the domain is attached to **Website Builder**, disconnect it first:
   **My Products → Websites + Marketing → Manage → Settings → (domain) → Disconnect / change domain**.
2. **My Products → Domains → iamselva.com → DNS**.
3. **Delete** the existing `A` record(s) whose name is `@` (often labelled "Parked" or "WebsiteBuilder Site").
4. **Add** four `A` records — Name `@`, TTL 1 hour:
   - `185.199.108.153`
   - `185.199.109.153`
   - `185.199.110.153`
   - `185.199.111.153`
5. Find the `CNAME` record named `www` → **Edit** → Value: `YOUR-GITHUB-USERNAME.github.io` (delete and re-add if it can't be edited).
6. Back in GitHub: repo **Settings → Pages → Custom domain** → type `iamselva.com` → **Save**.
7. Wait for the DNS check to go green (10 minutes to a few hours), then tick **Enforce HTTPS**.

Extra security (recommended): your GitHub profile **Settings → Pages → Add a domain** → `iamselva.com`, and add the `TXT` record it shows you in GoDaddy DNS. This stops anyone else from claiming your domain on GitHub.

---

## Customizing

- **Add/remove news sources:** edit `feeds.json` on GitHub (pencil icon) → commit. The site rebuilds automatically.
  Any RSS feed works. For any topic, use a Google News feed:
  `https://news.google.com/rss/search?q=YOUR+TOPIC&hl=en-US&gl=US&ceid=US:en`
- **Add a new tab:** copy one of the section blocks in `feeds.json`, give it a new `id` and `title`.
- **Change stock tickers:** edit the `WATCHLIST` list near the bottom of `index.html` (TradingView symbols, e.g. `NASDAQ:AMD`, `NYSE:JPM`).
- **Change odds leagues:** edit `odds.sports` in `feeds.json` (sport keys are listed at https://the-odds-api.com/sports-odds-data/sports-apis.html).

## Troubleshooting

- **Actions run is red:** click it → open the failed step to read the error. A single broken feed never fails the run; it's just skipped.
- **Site shows "Waiting for first update":** run the workflow by hand (step 6).
- **Hourly updates stopped:** GitHub can pause scheduled jobs on inactive repos. Actions tab → select the workflow → **Enable workflow**.
- **Test locally:** `pip install feedparser requests` then `python scripts/fetch_news.py`, then `python -m http.server` and open http://localhost:8000.

---
Not financial or betting advice. Must be 21+ to bet in Virginia. Gambling problem? Call 1-800-GAMBLER.
