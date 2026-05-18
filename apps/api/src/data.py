# apps/api/src/data.py
"""Data loader for the API — extended for ~51 contracts + 6 intelligence layers."""
from __future__ import annotations
import sys
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGES_DIR = REPO_ROOT / "packages"
CACHE_DIR = REPO_ROOT / "research" / "data" / "cache"
if str(PACKAGES_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGES_DIR))

from ingest import cftc_cot, indicators, news, normalize, prices, zones  # noqa: E402
from ingest import tff_cot, regime as regime_mod, retail_sentiment, market_synthesis, news_sentiment  # noqa: E402
from ingest.universe import UNIVERSE, sectors  # noqa: E402
from ingest.zones import annotate_divergence  # noqa: E402


@dataclass
class Bundle:
    annotated: dict[str, pd.DataFrame] = field(default_factory=dict)
    news_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    today_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    retail_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    synthesis: dict[str, dict] = field(default_factory=dict)
    loaded_at: pd.Timestamp | None = None


def build_bundle(years: range = range(2010, 2027)) -> Bundle:
    disagg_contracts = [c for c in UNIVERSE if getattr(c, "report_type", "disagg") == "disagg"]
    tff_contracts    = [c for c in UNIVERSE if getattr(c, "report_type", "disagg") == "tff"]

    cot_disagg = cftc_cot.load_universe(years, disagg_contracts, CACHE_DIR)
    cot_tff    = tff_cot.load_universe(years, tff_contracts, CACHE_DIR)
    cot = pd.concat([c for c in [cot_disagg, cot_tff] if not c.empty], ignore_index=True)

    px = prices.load_universe(UNIVERSE, CACHE_DIR, period="max")
    merged = normalize.join_cot_to_prices(px, cot)

    annotated: dict[str, pd.DataFrame] = {}
    for sym, grp in merged.groupby("symbol"):
        if grp.empty or grp["net_commercials"].isna().all():
            continue
        contract = next((c for c in UNIVERSE if c.symbol == sym), None)
        market_type = getattr(contract, "market_type", "physical") if contract else "physical"
        g = grp.reset_index(drop=True).copy()
        g["market_type"] = market_type
        g = indicators.add_all_indicators(g)
        g = zones.annotate_zones(g)
        g = annotate_divergence(g)
        annotated[sym] = g

    annotated = zones.add_sector_zone(annotated, UNIVERSE)
    annotated = regime_mod.annotate_all_regimes(annotated, CACHE_DIR)

    news_df = news.load_all_news(UNIVERSE, cache_dir=CACHE_DIR)
    news_df = news_sentiment.score_headlines(news_df)

    retail_df = retail_sentiment.load_retail_sentiment(annotated, CACHE_DIR)
    synthesis = market_synthesis.synthesize_all(annotated, news_df, retail_df, CACHE_DIR)

    today_df = zones.today_attention(annotated)

    return Bundle(
        annotated=annotated,
        news_df=news_df,
        today_df=today_df,
        retail_df=retail_df,
        synthesis=synthesis,
        loaded_at=pd.Timestamp.utcnow(),
    )


def sector_of(symbol: str) -> str | None:
    for sec, contracts in sectors().items():
        if any(c.symbol == symbol for c in contracts):
            return sec
    return None
