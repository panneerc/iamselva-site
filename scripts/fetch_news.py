"""
Pulls headlines (RSS) and betting odds (The Odds API) and writes:
  data/news.json  - headlines per section
  data/odds.json  - upcoming games with best moneyline per team

Runs every hour via GitHub Actions (.github/workflows/update.yml).
Run locally:  pip install feedparser requests  &&  python scripts/fetch_news.py
"""
import html
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import requests

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "feeds.json").read_text(encoding="utf-8"))
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
NEWS_FILE = DATA / "news.json"
ODDS_FILE = DATA / "odds.json"

UA = {"User-Agent": "Mozilla/5.0 (iamselva.com news aggregator; +https://iamselva.com)"}
NOW = datetime.now(timezone.utc)


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def clean(text, limit=220):
    """Strip HTML tags/entities and shorten to a short teaser (never the full article)."""
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(re.sub(r"\s+", " ", text)).strip()
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + "…"
    return text


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
        title = clean(e.get("title", ""), 200)
        link = e.get("link", "")
        if not title or not link:
            continue
        source = site
        # Google News titles look like "Headline - Publisher"
        if "news.google.com" in url:
            src = e.get("source", {})
            source = src.get("title") if isinstance(src, dict) and src.get("title") else source
            if " - " in title:
                title, source = title.rsplit(" - ", 1)
            summary = ""  # Google News summaries are just the headline again
        else:
            summary = clean(e.get("summary", ""))
            if summary.lower().startswith(title.lower()[:40].lower()):
                summary = ""
        when = entry_time(e)
        items.append({
            "title": title.strip(),
            "link": link,
            "source": (source or "").replace(" - Google News", "").strip(),
            "summary": summary,
            "published": when.isoformat() if when else None,
        })
    return items


def norm(title):
    return re.sub(r"[^a-z0-9]", "", title.lower())[:70]


def build_news():
    old = {}
    if NEWS_FILE.exists():
        try:
            old = json.loads(NEWS_FILE.read_text(encoding="utf-8")).get("sections", {})
        except Exception:
            old = {}

    sections = {}
    for sec in CONFIG["sections"]:
        seen, items, ok = set(), [], 0
        for url in sec["feeds"]:
            try:
                got = fetch_feed(url)
                ok += 1
                log(f"  [{sec['id']}] {len(got):3d} items  {url[:80]}")
            except Exception as ex:
                log(f"  [{sec['id']}] FAILED {url[:80]} -> {ex}")
                continue
            for it in got:
                k = norm(it["title"])
                if k and k not in seen:
                    seen.add(k)
                    items.append(it)
        # drop anything older than 7 days, newest first
        cutoff = NOW - timedelta(days=7)
        items = [i for i in items if not i["published"] or datetime.fromisoformat(i["published"]) >= cutoff]
        items.sort(key=lambda i: i["published"] or "", reverse=True)
        items = items[: sec.get("max", 40)]

        if not items and sec["id"] in old:
            log(f"  [{sec['id']}] no fresh items — keeping previous headlines")
            sections[sec["id"]] = old[sec["id"]]
            continue
        sections[sec["id"]] = {"title": sec["title"], "items": items, "feeds_ok": ok, "feeds_total": len(sec["feeds"])}

    out = {"updated": NOW.isoformat(), "order": [s["id"] for s in CONFIG["sections"]], "sections": sections}
    NEWS_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"Wrote {NEWS_FILE.relative_to(ROOT)}")


def build_odds():
    key = os.environ.get("ODDS_API_KEY", "").strip()
    cfg = CONFIG.get("odds", {})
    if not key:
        log("ODDS_API_KEY not set — skipping odds (betting tab will show news only).")
        return
    if ODDS_FILE.exists() and not os.environ.get("FORCE_ODDS"):
        try:
            last = datetime.fromisoformat(json.loads(ODDS_FILE.read_text())["updated"])
            if NOW - last < timedelta(hours=cfg.get("refresh_hours", 8)):
                log(f"Odds are fresh (fetched {last:%Y-%m-%d %H:%M} UTC) — skipping to save free credits.")
                return
        except Exception:
            pass

    leagues, remaining = [], None
    for sp in cfg.get("sports", []):
        url = f"https://api.the-odds-api.com/v4/sports/{sp['key']}/odds"
        params = {"apiKey": key, "regions": cfg.get("region", "us"), "markets": "h2h",
                  "oddsFormat": "american", "dateFormat": "iso"}
        try:
            r = requests.get(url, params=params, headers=UA, timeout=20)
            remaining = r.headers.get("x-requests-remaining", remaining)
            if r.status_code == 404 or r.status_code == 422:
                log(f"  odds {sp['title']}: not in season / unavailable")
                continue
            r.raise_for_status()
            events = r.json()
        except Exception as ex:
            log(f"  odds {sp['title']}: FAILED -> {ex}")
            continue

        games = []
        horizon = NOW + timedelta(days=7)
        for ev in events:
            start = datetime.fromisoformat(ev["commence_time"].replace("Z", "+00:00"))
            if start > horizon:
                continue
            best = {}  # team -> (price, book)
            for bk in ev.get("bookmakers", []):
                for m in bk.get("markets", []):
                    if m.get("key") != "h2h":
                        continue
                    for o in m.get("outcomes", []):
                        p = o.get("price")
                        if p is None:
                            continue
                        cur = best.get(o["name"])
                        if cur is None or p > cur[0]:
                            best[o["name"]] = (p, bk.get("title", ""))
            if not best:
                continue
            order = [ev.get("away_team"), ev.get("home_team")] + [n for n in best if n not in (ev.get("away_team"), ev.get("home_team"))]
            games.append({
                "start": start.isoformat(),
                "home": ev.get("home_team"),
                "away": ev.get("away_team"),
                "books": len(ev.get("bookmakers", [])),
                "lines": [{"name": n, "price": best[n][0], "book": best[n][1]} for n in order if n in best],
            })
        games.sort(key=lambda g: g["start"])
        log(f"  odds {sp['title']}: {len(games)} games in next 7 days")
        if games:
            leagues.append({"title": sp["title"], "games": games[:15]})

    ODDS_FILE.write_text(json.dumps({"updated": NOW.isoformat(), "credits_remaining": remaining,
                                     "leagues": leagues}, indent=1), encoding="utf-8")
    log(f"Wrote {ODDS_FILE.relative_to(ROOT)} (API credits left this month: {remaining})")


if __name__ == "__main__":
    build_news()
    build_odds()
