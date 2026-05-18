"""Pydantic response schemas. Keep tight — the frontend reads these literally."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

ZoneKey = Literal["A1", "A2", "A3", "A4", "A5"]
ZONE_NAMES: dict[str, str] = {
    "A1": "Extreme positioning",
    "A2": "Price divergence",
    "A3": "Sector outlier",
    "A4": "Momentum shift",
    "A5": "Hedger/Speculator imbalance",
}


class ContractMeta(BaseModel):
    symbol: str
    name: str
    sector: str
    cftc_code: str
    yf_ticker: str
    point_value: float
    tick_size: float


class TodayRow(BaseModel):
    symbol: str
    name: str
    sector: str
    date: date
    cot_index_comm: float | None
    n_zones: int
    zones_on: list[ZoneKey]
    magnitudes: dict[ZoneKey, float]
    total_mag: float


class BarRow(BaseModel):
    date: date
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None
    sma_fast: float | None = None
    sma_slow: float | None = None
    cot_index_comm: float | None = None
    net_commercials: float | None = None
    pm_long: float | None = None
    pm_short: float | None = None
    sd_long: float | None = None
    sd_short: float | None = None
    mm_long: float | None = None
    mm_short: float | None = None
    ucl: float | None = None
    lcl: float | None = None
    A1: bool = False
    A2: bool = False
    A3: bool = False
    A4: bool = False
    A5: bool = False
    n_zones: int = 0
    open_interest: float | None = None
    nr_long: float | None = None
    nr_short: float | None = None
    dealer_long: float | None = None
    dealer_short: float | None = None
    am_long: float | None = None
    am_short: float | None = None
    lf_long: float | None = None
    lf_short: float | None = None
    comm_spec_divergence: int = 0
    am_lf_divergence: int = 0
    regime_label: str | None = None
    regime_proba: list[float] | None = None
    regime_weeks: int = 0
    confluence_score: float | None = None


class MarketDetail(BaseModel):
    contract: ContractMeta
    from_date: date
    to_date: date
    bars: list[BarRow]


class HeatmapCell(BaseModel):
    symbol: str
    sector: str
    zone: ZoneKey
    active: bool
    magnitude: float


class HeatmapResponse(BaseModel):
    week_of: date
    cells: list[HeatmapCell]


class DivergenceRow(BaseModel):
    symbol: str
    name: str
    sector: str
    date: date
    magnitude: float
    direction: Literal["bullish", "bearish"]  # bullish = price-low / commercial-net-up
    close: float
    net_commercials: float


class NewsItem(BaseModel):
    date: datetime
    source: str
    source_category: str
    ticker: str | None = None
    title: str
    url: str | None = None
    publisher: str | None = None
    markets: list[str] = Field(default_factory=list)
    sentiment_score: float | None = None
    sentiment_label: str | None = None
    sentiment_reason: str | None = None


class NewsResponse(BaseModel):
    symbol: str | None = None
    from_date: date | None = None
    to_date: date | None = None
    items: list[NewsItem]


class ZoneCatalogEntry(BaseModel):
    key: ZoneKey
    name: str


class StatusResponse(BaseModel):
    ok: bool
    loaded_at: datetime | None
    n_markets: int
    n_news: int
    zones: list[ZoneCatalogEntry]


class ArticleResponse(BaseModel):
    url: str
    title: str | None = None
    site: str | None = None
    byline: str | None = None
    published: str | None = None
    content_html: str
    word_count: int
    fetched_at: str


class RetailSentimentItem(BaseModel):
    symbol: str
    long_pct: float
    short_pct: float
    source: str
    timestamp: datetime


class RetailSentimentResponse(BaseModel):
    symbol: str
    items: list[RetailSentimentItem]
    avg_long_pct: float
    avg_short_pct: float


class RegimeResponse(BaseModel):
    symbol: str
    market_type: str
    current_regime: str
    regime_weeks: int
    proba: list[float]
    next_bar_proba: list[float]
    transition_matrix: list[list[float]]
    state_names: list[str]


class SynthesisResponse(BaseModel):
    symbol: str
    summary: str
    confluence_score: float
    key_factors: list[str]
    watch: str
    generated_at: datetime | None = None
