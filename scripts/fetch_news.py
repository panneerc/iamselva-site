"""
Builds the data files the website reads:
  data/news.json      - headlines per tab (RSS feeds in feeds.json)
  data/research.json  - analyst rating changes, Wall Street consensus,
                        earnings calendar, penny stocks

Runs every 5 minutes via GitHub Actions (.github/workflows/main.yml).
Run locally:  pip install feedparser requests  &&  python scripts/fetch_news.py

Optional: set FINNHUB_API_KEY (free key from finnhub.io) for live quotes,
buy/hold/sell counts and the earnings calendar. Without it, the analyst
rating changes and penny-stock news still work.
"""
import html
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import feedparser
import requests

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "feeds.json").read_text(encoding="utf-8"))
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
NEWS_FILE = DATA / "news.json"
RESEARCH_FILE = DATA / "research.json"

UA = {"User-Agent": "Mozilla/5.0 (compatible; iamselva.com news aggregator)"}
NOW = datetime.now(timezone.utc)


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def clean(text, limit=220):
    """Strip HTML tags/entities and shorten to a short teaser (never the full article)."""
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(re.sub(r"\s+", " ", text)).strip()
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + "…"
    return text


# Publisher names as readers know them
SOURCE_NAMES = {
    "marketwatch": "MarketWatch", "yahoo": "Yahoo Finance", "bbc": "BBC Sport",
    "the verge": "The Verge", "ars technica": "Ars Technica", "the hindu": "The Hindu",
    "azure updates": "Azure Updates", "microsoft azure blog": "Azure Blog",
}


def short_source(name):
    name = (name or "").strip()
    low = name.lower()
    for key, nice in SOURCE_NAMES.items():
        if low.startswith(key):
            return nice
    name = re.split(r"\s+[-|:–]\s+", name)[0]          # "MarketWatch.com - Top Stories" -> "MarketWatch.com"
    name = re.sub(r"\.(com|net|org|co\.uk|in)$", "", name, flags=re.I)
    return name.strip() or "News"


def entry_time(e):
    for key in ("published_parsed", "updated_parsed"):
        t = e.get(key)
        if t:
            return datetime.fromtimestamp(time.mktime(t), tz=timezone.utc)
    return None


def fetch_feed(url):
    resp = requests.get(url, headers=UA, timeout=20)
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)
    site = clean(feed.feed.get("title", ""), 60)
    items = []
    for e in feed.entries[:40]:
        title = clean(e.get("title", ""), 220)
        link = e.get("link", "")
        if not title or not link:
            continue
        source = site
        if "news.google.com" in url:
            # Google News titles look like "Headline - Publisher"
            src = e.get("source", {})
            source = src.get("title") if isinstance(src, dict) and src.get("title") else source
            if " - " in title:
                title, source = title.rsplit(" - ", 1)
            summary = ""  # Google News summaries just repeat the headline
        else:
            summary = clean(e.get("summary", ""))
            if summary.lower().startswith(title.lower()[:40]):
                summary = ""
        when = entry_time(e)
        items.append({
            "title": title.strip(),
            "link": link,
            "source": short_source(source),
            "summary": summary,
            "published": when.isoformat() if when else None,
        })
    return items


def norm(title):
    return re.sub(r"[^a-z0-9]", "", title.lower())[:70]


def gather(feeds, max_items, max_age_days=7, label=""):
    """Fetch several feeds, drop duplicates/old items, newest first. Returns (items, ok_count)."""
    seen, items, ok = set(), [], 0
    for url in feeds:
        try:
            got = fetch_feed(url)
            ok += 1
            log(f"  [{label}] {len(got):3d} items  {url[:90]}")
        except Exception as ex:
            log(f"  [{label}] FAILED {url[:90]} -> {ex}")
            continue
        for it in got:
            k = norm(it["title"])
            if k and k not in seen:
                seen.add(k)
                items.append(it)
    cutoff = NOW - timedelta(days=max_age_days)
    items = [i for i in items if not i["published"] or datetime.fromisoformat(i["published"]) >= cutoff]
    items.sort(key=lambda i: i["published"] or "", reverse=True)
    return items[:max_items], ok


# ---------------------------------------------------------------- headlines
def build_news():
    old = load_json(NEWS_FILE, {}).get("sections", {})
    sections = {}
    for sec in CONFIG["sections"]:
        items, ok = gather(sec["feeds"], sec.get("max", 40), label=sec["id"])
        if not items and sec["id"] in old:
            log(f"  [{sec['id']}] no fresh items — keeping previous headlines")
            sections[sec["id"]] = old[sec["id"]]
            continue
        sections[sec["id"]] = {"title": sec["title"], "items": items, "feeds_ok": ok, "feeds_total": len(sec["feeds"])}
    out = {"updated": NOW.isoformat(), "order": [s["id"] for s in CONFIG["sections"]], "sections": sections}
    NEWS_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"Wrote {NEWS_FILE.relative_to(ROOT)}")


# ---------------------------------------------------------------- analyst rating changes
FIRMS = [
    ("JPMorgan", r"j\.?\s?p\.?\s?morgan|jpmorgan"), ("Goldman Sachs", r"goldman"),
    ("Morgan Stanley", r"morgan stanley"), ("Bank of America", r"bank of america|bofa"),
    ("Citi", r"\bciti(group)?\b"), ("Wells Fargo", r"wells fargo"), ("UBS", r"\bubs\b"),
    ("Barclays", r"barclays"), ("Deutsche Bank", r"deutsche"), ("Jefferies", r"jefferies"),
    ("Bernstein", r"bernstein"), ("Evercore", r"evercore"), ("Mizuho", r"mizuho"),
    ("Piper Sandler", r"piper sandler"), ("Raymond James", r"raymond james"),
    ("RBC", r"\brbc\b"), ("TD Cowen", r"td cowen|\bcowen\b"), ("Truist", r"truist"),
    ("KeyBanc", r"keybanc"), ("Oppenheimer", r"oppenheimer"), ("Needham", r"needham"),
    ("Wedbush", r"wedbush"), ("BMO", r"\bbmo\b"), ("HSBC", r"\bhsbc\b"),
    ("Baird", r"\bbaird\b"), ("Stifel", r"stifel"), ("Loop Capital", r"loop capital"),
    ("Rosenblatt", r"rosenblatt"), ("Benchmark", r"\bbenchmark\b"), ("Macquarie", r"macquarie"),
    ("Morningstar", r"morningstar"), ("Argus", r"\bargus\b"),
]
RATINGS = r"(strong buy|buy|overweight|outperform|accumulate|positive|neutral|hold|equal[- ]weight|market perform|sector perform|in[- ]line|peer perform|underweight|underperform|reduce|sell|negative)"


def parse_move(title):
    t = title.lower()
    if re.search(r"\bupgrad", t):
        action = "Upgrade"
    elif re.search(r"\bdowngrad", t):
        action = "Downgrade"
    elif re.search(r"\b(initiat|starts coverage|begins coverage|launches coverage|resumes coverage)", t):
        action = "New coverage"
    elif re.search(r"(rais|lift|boost|hik|increas|bump)\w*\s.*price target|price target\s.*\b(rais|lift|boost|hik|increas)", t):
        action = "Target raised"
    elif re.search(r"(cut|lower|trim|slash|reduc)\w*\s.*price target|price target\s.*\b(cut|lower|trim|slash)", t):
        action = "Target cut"
    elif re.search(r"\b(reiterat|maintain|keeps?|affirm)\w*\b.*\b" + RATINGS, t):
        action = "Reiterated"
    else:
        return None
    firm = next((name for name, pat in FIRMS if re.search(pat, t)), None)
    rating = None
    m = re.search(r"\bto (an? )?" + RATINGS + r"\b", t) or re.search(RATINGS + r" rating", t) or re.search(r"\bat (an? )?" + RATINGS + r"\b", t)
    if m:
        rating = m.group(m.lastindex).replace("-", " ").title().replace("Equal Weight", "Equal-weight")
    target = None
    m = re.search(r"to \$\s?(\d+(?:,\d{3})*(?:\.\d+)?)", title) or re.search(r"\$\s?(\d+(?:,\d{3})*(?:\.\d+)?)", title)
    if m and re.search(r"\btarget\b|\bpt\b", t):
        target = "$" + m.group(1)
    ticker = None
    m = re.search(r"\((?:NASDAQ|NYSE|NYSEAMERICAN|AMEX|OTC\w*)\s*:\s*([A-Z.]{1,6})\)", title) or re.search(r"\(([A-Z]{1,5})\)", title)
    if m:
        ticker = m.group(1)
    return {"firm": firm, "action": action, "rating": rating, "target": target, "ticker": ticker}


def build_analyst_moves(rcfg):
    items, ok = gather(rcfg.get("analyst_feeds", []), 400, max_age_days=4, label="analysts")
    moves = []
    for it in items:
        mv = parse_move(it["title"])
        if mv:
            moves.append({**it, **mv})
    # Big-name firm moves first within the same day? Keep newest first — readers expect a feed.
    log(f"  analyst moves found: {len(moves)} (from {len(items)} headlines, {ok} feeds ok)")
    return moves[:120]


# ---------------------------------------------------------------- Finnhub
class Finnhub:
    BASE = "https://finnhub.io/api/v1"

    def __init__(self, key):
        self.key = key
        self.calls = 0
        self.denied = set()

    def get(self, path, **params):
        if path in self.denied:
            return None
        time.sleep(1.05)  # free tier: 60 calls/minute
        self.calls += 1
        r = requests.get(f"{self.BASE}{path}", params={**params, "token": self.key}, headers=UA, timeout=20)
        if r.status_code in (401, 403):
            log(f"  finnhub {path}: access denied ({r.status_code}) — check your key / plan")
            self.denied.add(path)
            return None
        if r.status_code == 429:
            log(f"  finnhub {path}: rate limited, pausing")
            time.sleep(20)
            return None
        r.raise_for_status()
        return r.json()


def score(rec):
    """Buy/sell balance from -2 (all strong sell) to +2 (all strong buy)."""
    if not rec:
        return None
    sb, b, h, s, ss = (rec.get(k, 0) or 0 for k in ("strongBuy", "buy", "hold", "sell", "strongSell"))
    total = sb + b + h + s + ss
    return round((2 * sb + b - s - 2 * ss) / total, 2) if total else None


def verdict(sc):
    if sc is None:
        return None
    if sc >= 1.2:
        return "Strong buy"
    if sc >= 0.5:
        return "Buy"
    if sc > -0.5:
        return "Hold"
    if sc > -1.2:
        return "Sell"
    return "Strong sell"


def quote_and_consensus(fh, symbols, cache, rec_max_age_h=24):
    """Live quote every run; buy/hold/sell counts once a day (they change monthly)."""
    rows = []
    for sym in symbols:
        row = {"symbol": sym}
        try:
            q = fh.get("/quote", symbol=sym)
            if q and q.get("c"):
                row.update(price=q["c"], change=q.get("d"), change_pct=q.get("dp"), prev_close=q.get("pc"),
                           as_of=datetime.fromtimestamp(q["t"], tz=timezone.utc).isoformat() if q.get("t") else None)
        except Exception as ex:
            log(f"  quote {sym}: {ex}")
        c = cache.get(sym, {})
        fresh = c.get("fetched") and NOW - datetime.fromisoformat(c["fetched"]) < timedelta(hours=rec_max_age_h)
        if not fresh:
            try:
                rec = fh.get("/stock/recommendation", symbol=sym)
                if rec is not None:
                    c = {"fetched": NOW.isoformat(), "latest": rec[0] if rec else None, "previous": rec[1] if len(rec) > 1 else None}
                    cache[sym] = c
            except Exception as ex:
                log(f"  recommendation {sym}: {ex}")
        latest, prev = c.get("latest"), c.get("previous")
        if latest:
            sc, psc = score(latest), score(prev)
            row["consensus"] = {
                "period": latest.get("period"),
                "strong_buy": latest.get("strongBuy", 0), "buy": latest.get("buy", 0), "hold": latest.get("hold", 0),
                "sell": latest.get("sell", 0), "strong_sell": latest.get("strongSell", 0),
                "score": sc, "verdict": verdict(sc), "prev_score": psc,
                "trend": None if psc is None or sc is None else ("up" if sc - psc >= 0.05 else "down" if psc - sc >= 0.05 else "flat"),
            }
        rows.append(row)
    return rows


def earnings_calendar(fh, rcfg, previous, watch):
    """All US companies reporting in the next N days. Refreshed every few hours."""
    if previous and previous.get("fetched") and NOW - datetime.fromisoformat(previous["fetched"]) < timedelta(hours=rcfg.get("earnings_refresh_hours", 4)):
        return previous
    start = date.today()
    end = start + timedelta(days=rcfg.get("earnings_days_ahead", 14))
    data = fh.get("/calendar/earnings", **{"from": start.isoformat(), "to": end.isoformat()})
    if not data:
        return previous
    rows = data.get("earningsCalendar", []) or []
    watchset = set(watch)
    by_day = {}
    for r in rows:
        if not r.get("symbol") or "." in r["symbol"]:
            continue
        by_day.setdefault(r["date"], []).append({
            "symbol": r["symbol"], "date": r["date"], "hour": r.get("hour") or "",
            "eps_estimate": r.get("epsEstimate"), "revenue_estimate": r.get("revenueEstimate"),
            "quarter": r.get("quarter"), "year": r.get("year"), "watch": r["symbol"] in watchset,
        })
    days = []
    per_day = rcfg.get("earnings_per_day", 25)
    for d in sorted(by_day):
        lst = by_day[d]
        # Biggest companies first (by expected revenue); always keep your watchlist stocks
        lst.sort(key=lambda x: (not x["watch"], -(x["revenue_estimate"] or 0)))
        days.append({"date": d, "total": len(lst), "items": lst[:per_day]})
    mine = sorted([x for d in by_day.values() for x in d if x["watch"]], key=lambda x: x["date"])
    log(f"  earnings: {len(rows)} reports across {len(days)} days; {len(mine)} from your watchlist")
    return {"fetched": NOW.isoformat(), "from": start.isoformat(), "to": end.isoformat(), "days": days, "watchlist": mine}


# ---------------------------------------------------------------- penny stocks
TICKER_PATTERNS = [
    r"\((?:NASDAQ|NYSE|NYSE ?AMERICAN|AMEX|NASDAQCM|NASDAQGS|NASDAQGM)\s*:\s*([A-Z]{1,5})\)",
    r"\b(?:NASDAQ|NYSE|NYSE American|AMEX)\s*:\s*([A-Z]{1,5})\b",
    r"\$([A-Z]{2,5})\b",
]
NOT_TICKERS = {"USD", "CEO", "IPO", "ETF", "AI", "EPS", "US", "SEC", "FDA", "NYSE", "OTC"}


def find_tickers(text):
    found = []
    for pat in TICKER_PATTERNS:
        for t in re.findall(pat, text or ""):
            if t not in NOT_TICKERS and t not in found:
                found.append(t)
    return found


def build_penny(fh, rcfg, cache):
    news, ok = gather(rcfg.get("penny_feeds", []), 40, max_age_days=10, label="penny")
    mentions = {}
    for it in news:
        for t in find_tickers(it["title"] + " " + it.get("summary", "")):
            m = mentions.setdefault(t, {"count": 0, "headlines": []})
            m["count"] += 1
            if len(m["headlines"]) < 2:
                m["headlines"].append({"title": it["title"], "link": it["link"], "source": it["source"]})
    candidates = list(dict.fromkeys(rcfg.get("penny_watchlist", []) + sorted(mentions, key=lambda t: -mentions[t]["count"])))
    candidates = candidates[: rcfg.get("penny_max_lookups", 15)]
    stocks = []
    if fh and candidates:
        limit = rcfg.get("penny_max_price", 5)
        for row in quote_and_consensus(fh, candidates, cache):
            if row.get("price") and row["price"] <= limit:
                row["mentions"] = mentions.get(row["symbol"], {"count": 0, "headlines": []})
                row["watch"] = row["symbol"] in rcfg.get("penny_watchlist", [])
                stocks.append(row)
    log(f"  penny: {len(news)} headlines, {len(mentions)} tickers mentioned, {len(stocks)} under ${rcfg.get('penny_max_price', 5)}")
    return {"news": news, "stocks": stocks, "max_price": rcfg.get("penny_max_price", 5)}



# ---------------------------------------------------------------- watchlist performance
PERIOD_KEYS = {  # Finnhub /stock/metric field names, first one found wins
    "week": ["5DayPriceReturnDaily"],
    "month": ["4WeekPriceReturnDaily", "monthToDatePriceReturnDaily"],
    "mtd": ["monthToDatePriceReturnDaily"],
    "m3": ["13WeekPriceReturnDaily"],
    "ytd": ["yearToDatePriceReturnDaily"],
    "year": ["52WeekPriceReturnDaily"],
}


HISTORY_FILE = DATA / "history.json"


def record_history(history, sym, price, ts):
    """Keep one closing price per trading day (the last price seen that day, New York time)."""
    if not price or not ts:
        return
    ny = datetime.fromtimestamp(ts, tz=timezone.utc) - timedelta(hours=5)
    day = ny.date().isoformat()
    h = history.setdefault(sym, {})
    h[day] = price
    for d in sorted(h)[:-400]:
        del h[d]


def return_since(history, sym, price, days):
    """% change from the close about `days` calendar days ago, if we have saved prices that far back."""
    h = history.get(sym) or {}
    target = (date.today() - timedelta(days=days)).isoformat()
    older = [d for d in sorted(h) if d <= target]
    if not price or not older or (date.fromisoformat(target) - date.fromisoformat(older[-1])).days > 5:
        return None
    return round((price / h[older[-1]] - 1) * 100, 4)


def performance(fh, symbols, quotes, cache, history, metric_max_age_h=3):
    """Today's move from the live quote; week/month/year returns (as of last close) from /stock/metric."""
    rows = []
    for sym in symbols:
        c = cache.get(sym, {})
        fresh = c.get("fetched") and NOW - datetime.fromisoformat(c["fetched"]) < timedelta(hours=metric_max_age_h)
        if not fresh:
            try:
                m = fh.get("/stock/metric", symbol=sym, metric="all")
                if m is not None:
                    met = m.get("metric") or {}
                    keep = {k: v for k, v in met.items() if "PriceReturn" in k or k in ("52WeekHigh", "52WeekLow", "52WeekHighDate", "52WeekLowDate", "beta", "marketCapitalization")}
                    c = {**c, "fetched": NOW.isoformat(), "metric": keep}
            except Exception as ex:
                log(f"  metric {sym}: {ex}")
        if not c.get("name_fetched") or NOW - datetime.fromisoformat(c["name_fetched"]) > timedelta(days=7):
            try:
                prof = fh.get("/stock/profile2", symbol=sym)
                if prof is not None:
                    c = {**c, "name": prof.get("name") or c.get("name"), "name_fetched": NOW.isoformat()}
            except Exception as ex:
                log(f"  profile {sym}: {ex}")
        cache[sym] = c
        met = c.get("metric", {})
        q = quotes.get(sym)
        if q is None:
            try:
                qq = fh.get("/quote", symbol=sym) or {}
                q = {"price": qq.get("c"), "change_pct": qq.get("dp"), "t": qq.get("t")} if qq.get("c") else {}
            except Exception:
                q = {}
        row = {"symbol": sym, "name": c.get("name"), "price": q.get("price"), "today": q.get("change_pct"),
               "high52": met.get("52WeekHigh"), "low52": met.get("52WeekLow"), "as_of_close": c.get("fetched")}
        for period, keys in PERIOD_KEYS.items():
            row[period] = next((met[k] for k in keys if met.get(k) is not None), None)
        record_history(history, sym, q.get("price"), q.get("t"))
        month = return_since(history, sym, q.get("price"), 30)
        if month is not None:
            row["month"] = month
        row["month_is_mtd"] = month is None and met.get("4WeekPriceReturnDaily") is None and row["month"] is not None
        rows.append(row)
    return rows

# ---------------------------------------------------------------- research file
def build_research():
    rcfg = CONFIG.get("research")
    if not rcfg:
        return
    old = load_json(RESEARCH_FILE, {})
    cache = old.get("_rec_cache", {})
    key = os.environ.get("FINNHUB_API_KEY", "").strip()
    fh = Finnhub(key) if key else None

    out = {"updated": NOW.isoformat(), "finnhub": "ok" if fh else "missing_key"}
    out["analyst_moves"] = build_analyst_moves(rcfg) or old.get("analyst_moves", [])

    watch = rcfg.get("watchlist", [])
    if fh:
        try:
            out["consensus"] = quote_and_consensus(fh, watch, cache)
        except Exception as ex:
            log(f"  consensus FAILED -> {ex}")
            out["consensus"] = old.get("consensus", [])
        try:
            quotes = {r["symbol"]: r for r in out["consensus"] if r.get("price")}
            quotes = {k: {"price": v["price"], "change_pct": v.get("change_pct"),
                          "t": int(datetime.fromisoformat(v["as_of"]).timestamp()) if v.get("as_of") else None} for k, v in quotes.items()}
            history = load_json(HISTORY_FILE, {})
            mcache = old.get("_metric_cache", {})
            out["watchlist"] = {
                "stocks": performance(fh, watch, quotes, mcache, history),
                "benchmarks": performance(fh, rcfg.get("benchmarks", ["SPY", "QQQ"]), {}, mcache, history),
            }
            HISTORY_FILE.write_text(json.dumps(history, separators=(",", ":")), encoding="utf-8")
            out["_metric_cache"] = mcache
            log(f"  watchlist: {len(out['watchlist']['stocks'])} stocks")
        except Exception as ex:
            log(f"  watchlist FAILED -> {ex}")
            out["watchlist"] = old.get("watchlist")
            out["_metric_cache"] = old.get("_metric_cache", {})
        try:
            out["earnings"] = earnings_calendar(fh, rcfg, old.get("earnings"), watch)
        except Exception as ex:
            log(f"  earnings FAILED -> {ex}")
            out["earnings"] = old.get("earnings")
    else:
        log("FINNHUB_API_KEY not set — skipping quotes, consensus and earnings calendar.")
        out["consensus"], out["earnings"], out["watchlist"] = [], None, None

    try:
        out["penny"] = build_penny(fh, rcfg, cache)
        if not out["penny"]["news"] and old.get("penny"):
            out["penny"] = old["penny"]
    except Exception as ex:
        log(f"  penny FAILED -> {ex}")
        out["penny"] = old.get("penny", {"news": [], "stocks": []})

    if fh and fh.denied:
        out["finnhub"] = "denied: " + ", ".join(sorted(fh.denied))
    out["_rec_cache"] = cache
    RESEARCH_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"Wrote {RESEARCH_FILE.relative_to(ROOT)} ({fh.calls if fh else 0} Finnhub calls)")


if __name__ == "__main__":
    build_news()
    build_research()
