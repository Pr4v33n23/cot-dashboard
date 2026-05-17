"""Macro + per-contract news ingest. Deterministic, no LLM.

Sources (all free, per PLAN §0.3 capital stop):
- yfinance ticker news : real-time per-contract headlines
- scheduled-event calendars : FOMC, OPEC, USDA WASDE (static dates, no scraping)
- EIA & FRED : deferred to post-MVP

Output schema (one row per headline):
    date, source, source_category, ticker, title, url, publisher, markets[]

Tagging:
- Yahoo ticker news is already per-ticker; we still re-run the taxonomy to pick
  up cross-market tags (e.g., a CL=F headline about CPI also tags GC).
- Scheduled events have an explicit markets[] list baked in.
"""

from __future__ import annotations

import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd

from .news_taxonomy import SOURCE_CATEGORIES, markets_for_headline
from .universe import Contract

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)


# ── Scheduled events — curated static calendar ──────────────────────────────
# Hand-curated from public schedules. No scraping. Sourced from:
# - FOMC: federalreserve.gov/monetarypolicy/fomccalendars.htm
# - OPEC: opec.org/meetings/calendar
# - WASDE: usda.gov/oce/commodity/wasde/release-schedule
# Add new dates as they are announced. One year out is enough — pipeline runs
# weekly so a missing event a year ahead is not a defect.

FOMC_DATES_2024_2026 = [
    "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12", "2024-07-31",
    "2024-09-18", "2024-11-07", "2024-12-18",
    "2025-01-29", "2025-03-19", "2025-04-30", "2025-06-18", "2025-07-30",
    "2025-09-17", "2025-10-29", "2025-12-10",
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17", "2026-07-29",
    "2026-09-16", "2026-10-28", "2026-12-16",
]
# Affected markets per FOMC: all rate/dollar-sensitive contracts.
FOMC_MARKETS = ["GC", "SI", "HG", "PL", "CL", "NG"]

OPEC_DATES_2024_2026 = [
    "2024-06-02", "2024-12-05",
    "2025-04-03", "2025-12-04",
    "2026-04-02", "2026-12-03",
]
OPEC_MARKETS = ["CL", "NG", "HO", "RB"]

# WASDE — published ~10th of each month at 12:00 ET.
WASDE_DATES_2024_2026 = [
    f"{y}-{m:02d}-{d:02d}"
    for y in (2024, 2025, 2026)
    for m, d in [(1, 12), (2, 8), (3, 8), (4, 11), (5, 10), (6, 12),
                 (7, 12), (8, 12), (9, 12), (10, 11), (11, 8), (12, 10)]
]
WASDE_MARKETS = ["ZC", "ZW", "ZS", "ZM", "ZL", "ZO", "ZR", "LE", "HE", "GF"]


def scheduled_events() -> pd.DataFrame:
    """Return scheduled-event headlines as a tidy DataFrame.

    Stable, deterministic, offline. Re-run any time and you get the same rows.
    """
    rows: list[dict] = []
    for d in FOMC_DATES_2024_2026:
        rows.append({
            "date": pd.Timestamp(d),
            "source": "fomc",
            "source_category": SOURCE_CATEGORIES["fomc"],
            "ticker": None,
            "title": "FOMC meeting / statement release",
            "url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
            "publisher": "Federal Reserve",
            "markets": FOMC_MARKETS,
        })
    for d in OPEC_DATES_2024_2026:
        rows.append({
            "date": pd.Timestamp(d),
            "source": "opec",
            "source_category": SOURCE_CATEGORIES["opec"],
            "ticker": None,
            "title": "OPEC+ ministerial meeting",
            "url": "https://www.opec.org/opec_web/en/press_room/28.htm",
            "publisher": "OPEC",
            "markets": OPEC_MARKETS,
        })
    for d in WASDE_DATES_2024_2026:
        rows.append({
            "date": pd.Timestamp(d),
            "source": "wasde",
            "source_category": SOURCE_CATEGORIES["wasde"],
            "ticker": None,
            "title": "USDA WASDE report release",
            "url": "https://www.usda.gov/oce/commodity-markets/wasde",
            "publisher": "USDA",
            "markets": WASDE_MARKETS,
        })
    return pd.DataFrame(rows)


# ── Yahoo Finance ticker news ────────────────────────────────────────────────

def _yf_news_for_ticker(yf_ticker: str) -> list[dict]:
    """Pull recent news for one Yahoo Finance ticker. Returns raw items.

    yfinance >=0.2.40 returns a list of dicts. Schema has shifted across
    versions; we read defensively. Older items had top-level keys
    (`title`, `link`, `providerPublishTime`); newer items wrap them under
    `content`. Both shapes are handled.
    """
    import yfinance as yf
    try:
        raw = yf.Ticker(yf_ticker).news or []
    except Exception:  # noqa: BLE001 — surface as empty, don't break pipeline
        return []
    items: list[dict] = []
    for item in raw:
        # Newer yfinance shape: item['content'] = {title, summary, pubDate, canonicalUrl, provider}
        content = item.get("content") if isinstance(item, dict) else None
        if content:
            title = content.get("title")
            url = (content.get("canonicalUrl") or {}).get("url") or (content.get("clickThroughUrl") or {}).get("url")
            publisher = (content.get("provider") or {}).get("displayName")
            pub_date = content.get("pubDate")
            try:
                ts = pd.Timestamp(pub_date)
            except Exception:  # noqa: BLE001
                ts = None
        else:
            title = item.get("title")
            url = item.get("link")
            publisher = item.get("publisher")
            epoch = item.get("providerPublishTime")
            ts = pd.Timestamp(datetime.fromtimestamp(epoch, tz=timezone.utc)) if epoch else None
        if not title or ts is None:
            continue
        items.append({
            "date": ts.tz_localize(None) if ts.tz is not None else ts,
            "title": title,
            "url": url,
            "publisher": publisher,
        })
    return items


def load_yfinance_news(universe: Iterable[Contract]) -> pd.DataFrame:
    """Pull yfinance news for every contract in `universe` and tag via taxonomy."""
    rows: list[dict] = []
    for contract in universe:
        items = _yf_news_for_ticker(contract.yf_ticker)
        for it in items:
            # The primary tag is the contract itself; the taxonomy can add
            # cross-market tags (CPI in a CL=F headline also tags GC).
            cross_tags = markets_for_headline(it["title"])
            markets = sorted({contract.symbol, *cross_tags})
            rows.append({
                "date": it["date"],
                "source": "yfinance",
                "source_category": SOURCE_CATEGORIES["yfinance"],
                "ticker": contract.yf_ticker,
                "title": it["title"],
                "url": it["url"],
                "publisher": it["publisher"],
                "markets": markets,
            })
    return pd.DataFrame(rows)


# ── Orchestrator ─────────────────────────────────────────────────────────────

def load_all_news(
    universe: Iterable[Contract],
    cache_dir: Path | None = None,
    include_scheduled: bool = True,
) -> pd.DataFrame:
    """One-call entry point. Returns the unioned news frame.

    Columns: date, source, source_category, ticker, title, url, publisher, markets.
    """
    frames: list[pd.DataFrame] = []
    if include_scheduled:
        frames.append(scheduled_events())
    frames.append(load_yfinance_news(universe))
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    out = out.dropna(subset=["date", "title"]).sort_values("date").reset_index(drop=True)
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        # `markets` is a list — Parquet handles via Arrow list type.
        out.to_parquet(cache_dir / "news.parquet", index=False)
    return out


def news_for_market(news: pd.DataFrame, symbol: str,
                    from_date: pd.Timestamp | None = None,
                    to_date: pd.Timestamp | None = None) -> pd.DataFrame:
    """Filter a news frame to items tagged for `symbol` within the date range.

    Used by the FastAPI `/news/:sym` endpoint and by the chart's news-pin layer.
    """
    if news.empty:
        return news
    mask = news["markets"].apply(lambda ms: symbol in ms if isinstance(ms, list) else False)
    sub = news[mask].copy()
    if from_date is not None:
        sub = sub[sub["date"] >= pd.Timestamp(from_date)]
    if to_date is not None:
        sub = sub[sub["date"] <= pd.Timestamp(to_date)]
    return sub.sort_values("date", ascending=False).reset_index(drop=True)
