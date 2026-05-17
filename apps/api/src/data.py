"""Data loader for the API.

Single-process, in-memory cache. At startup:
1. Load CFTC + prices from local Parquet cache (re-download missing years/symbols).
2. Merge weekly COT onto daily bars.
3. Annotate each per-symbol frame with indicators + zones.
4. Run the multi-symbol A3 sector pass.
5. Load news (scheduled + yfinance) and tag.

Subsequent requests query the in-memory dicts — no recompute, no disk IO.

When the Friday cron writes fresh Parquet, the recommended pattern is to
hit `POST /refresh` (admin only — deferred to Phase 1 auth wiring) or
just restart the process. Either way costs ~5 seconds.
"""

from __future__ import annotations

import sys
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

# Resolve the repo root so we can find packages/ + research/data/cache/ from any cwd.
REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGES_DIR = REPO_ROOT / "packages"
CACHE_DIR = REPO_ROOT / "research" / "data" / "cache"
if str(PACKAGES_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGES_DIR))

from ingest import cftc_cot, indicators, news, normalize, prices, zones  # noqa: E402
from ingest.universe import UNIVERSE, sectors  # noqa: E402


@dataclass
class Bundle:
    """In-memory state shared by every route handler."""
    annotated: dict[str, pd.DataFrame] = field(default_factory=dict)
    news_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    today_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    loaded_at: pd.Timestamp | None = None


def build_bundle(years: range = range(2010, 2027)) -> Bundle:
    cot = cftc_cot.load_universe(years, UNIVERSE, CACHE_DIR)
    px = prices.load_universe(UNIVERSE, CACHE_DIR, period="max")
    merged = normalize.join_cot_to_prices(px, cot)

    annotated: dict[str, pd.DataFrame] = {}
    for sym, grp in merged.groupby("symbol"):
        if grp.empty or grp["net_commercials"].isna().all():
            continue
        g = indicators.add_all_indicators(grp.reset_index(drop=True))
        g = zones.annotate_zones(g)
        annotated[sym] = g
    annotated = zones.add_sector_zone(annotated, UNIVERSE)

    news_df = news.load_all_news(UNIVERSE, cache_dir=CACHE_DIR)
    today_df = zones.today_attention(annotated)

    return Bundle(
        annotated=annotated,
        news_df=news_df,
        today_df=today_df,
        loaded_at=pd.Timestamp.utcnow(),
    )


def sector_of(symbol: str) -> str | None:
    for sec, contracts in sectors().items():
        if any(c.symbol == symbol for c in contracts):
            return sec
    return None
