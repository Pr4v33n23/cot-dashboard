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
