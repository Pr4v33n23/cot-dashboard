"""FastAPI origin server for `COT_LENS_v1`.

Endpoints:
    GET  /healthz                   smoke check
    GET  /status                    bundle status + zone catalog
    GET  /universe                  contract metadata for sidebar
    GET  /today                     ranked attention list, most-recent bar per market
    GET  /market/{symbol}           full annotated frame, paginated by date range
    GET  /heatmap                   23 x 5 grid of active zones, current week
    GET  /divergence/{week}         A2-only view, ranked by magnitude
    GET  /news/{symbol}             news filtered for a market in a date range
    POST /refresh                   rebuild the in-memory bundle (rerun ingest + annotate)

Run locally:
    uvicorn src.main:app --reload --port 8000 --app-dir apps/api
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from typing import Iterator

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .article import fetch_article
from .data import Bundle, build_bundle, sector_of
from .schemas import (
    ArticleResponse,
    BarRow,
    ContractMeta,
    DivergenceRow,
    HeatmapCell,
    HeatmapResponse,
    MarketDetail,
    NewsItem,
    NewsResponse,
    StatusResponse,
    TodayRow,
    ZONE_NAMES,
    ZoneCatalogEntry,
)


# Lazy import — keeps cold start fast for /healthz
def _universe():
    from ingest.universe import UNIVERSE
    return UNIVERSE


def _contract(symbol: str):
    for c in _universe():
        if c.symbol == symbol:
            return c
    raise HTTPException(status_code=404, detail=f"Unknown symbol: {symbol}")


_STATE: dict[str, Bundle | None] = {"bundle": None}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _STATE["bundle"] = build_bundle()
    yield
    _STATE["bundle"] = None


app = FastAPI(
    title="COT_LENS_v1",
    description="Positioning intelligence + macro news correlator for CME physicals.",
    version="0.1.0",
    lifespan=lifespan,
)

# Permissive CORS in dev; lock down before production deploy.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _bundle() -> Bundle:
    b = _STATE["bundle"]
    if b is None:
        raise HTTPException(status_code=503, detail="bundle not loaded yet")
    return b


# ── /healthz ───────────────────────────────────────────────────────────────
@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


# ── /status ────────────────────────────────────────────────────────────────
@app.get("/status", response_model=StatusResponse)
def status() -> StatusResponse:
    b = _bundle()
    return StatusResponse(
        ok=True,
        loaded_at=b.loaded_at.to_pydatetime() if b.loaded_at is not None else None,
        n_markets=len(b.annotated),
        n_news=len(b.news_df),
        zones=[ZoneCatalogEntry(key=k, name=v) for k, v in ZONE_NAMES.items()],
    )


# ── /refresh ───────────────────────────────────────────────────────────────
@app.post("/refresh", response_model=StatusResponse)
def refresh() -> StatusResponse:
    _STATE["bundle"] = build_bundle()
    return status()


# ── /universe ──────────────────────────────────────────────────────────────
@app.get("/universe", response_model=list[ContractMeta])
def universe_endpoint() -> list[ContractMeta]:
    return [
        ContractMeta(
            symbol=c.symbol,
            name=c.name,
            sector=c.sector,
            cftc_code=c.cftc_code,
            yf_ticker=c.yf_ticker,
            point_value=c.point_value,
            tick_size=c.tick_size,
        )
        for c in _universe()
    ]


# ── /today ─────────────────────────────────────────────────────────────────
def _zones_on(row: pd.Series) -> list[str]:
    return [z for z in ("A1", "A2", "A3", "A4", "A5") if bool(row.get(z, False))]


@app.get("/today", response_model=list[TodayRow])
def today_endpoint() -> list[TodayRow]:
    b = _bundle()
    if b.today_df.empty:
        return []
    name_lookup = {c.symbol: c.name for c in _universe()}
    out: list[TodayRow] = []
    for _, row in b.today_df.iterrows():
        sym = row["symbol"]
        mags = {z: float(row[f"{z}_mag"]) for z in ("A1", "A2", "A3", "A4", "A5")}
        out.append(
            TodayRow(
                symbol=sym,
                name=name_lookup.get(sym, sym),
                sector=sector_of(sym) or "",
                date=row["date"].date() if hasattr(row["date"], "date") else row["date"],
                cot_index_comm=row.get("cot_index_comm"),
                n_zones=int(row["n_zones"]),
                zones_on=_zones_on(row),
                magnitudes=mags,
                total_mag=float(row["total_mag"]),
            )
        )
    return out


# ── /market/{symbol} ───────────────────────────────────────────────────────
@app.get("/market/{symbol}", response_model=MarketDetail)
def market_endpoint(
    symbol: str,
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
) -> MarketDetail:
    b = _bundle()
    contract = _contract(symbol)
    df = b.annotated.get(symbol)
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail=f"No data for {symbol}")

    if from_date is None:
        # Default: last 3 years — frontend can request more via ?from=
        from_date = (df["date"].max() - pd.DateOffset(years=3)).date()
    if to_date is None:
        to_date = df["date"].max().date()

    mask = (df["date"] >= pd.Timestamp(from_date)) & (df["date"] <= pd.Timestamp(to_date))
    sub = df[mask]

    bar_cols = ["open", "high", "low", "close", "volume", "sma_fast", "sma_slow",
                "cot_index_comm", "net_commercials", "pm_long", "pm_short",
                "sd_long", "sd_short", "mm_long", "mm_short", "ucl", "lcl",
                "A1", "A2", "A3", "A4", "A5", "n_zones"]
    bars: list[BarRow] = []
    for _, row in sub.iterrows():
        bars.append(BarRow(
            date=row["date"].date(),
            **{c: (None if pd.isna(row.get(c)) else (bool(row[c]) if c in ("A1","A2","A3","A4","A5")
                                                     else (int(row[c]) if c == "n_zones" else float(row[c]))))
               for c in bar_cols if c in row.index},
        ))

    return MarketDetail(
        contract=ContractMeta(
            symbol=contract.symbol,
            name=contract.name,
            sector=contract.sector,
            cftc_code=contract.cftc_code,
            yf_ticker=contract.yf_ticker,
            point_value=contract.point_value,
            tick_size=contract.tick_size,
        ),
        from_date=from_date,
        to_date=to_date,
        bars=bars,
    )


# ── /heatmap ───────────────────────────────────────────────────────────────
@app.get("/heatmap", response_model=HeatmapResponse)
def heatmap_endpoint(week_of: date | None = Query(default=None)) -> HeatmapResponse:
    b = _bundle()
    if not b.annotated:
        return HeatmapResponse(week_of=date.today(), cells=[])

    cells: list[HeatmapCell] = []
    target_dt = pd.Timestamp(week_of) if week_of else None
    actual_date: pd.Timestamp | None = None

    for sym, g in b.annotated.items():
        if g.empty:
            continue
        if target_dt is None:
            row = g.iloc[-1]
        else:
            # nearest bar <= target_dt
            sub = g[g["date"] <= target_dt]
            if sub.empty:
                continue
            row = sub.iloc[-1]
        actual_date = row["date"]
        sec = sector_of(sym) or ""
        for z in ("A1", "A2", "A3", "A4", "A5"):
            cells.append(
                HeatmapCell(
                    symbol=sym,
                    sector=sec,
                    zone=z,
                    active=bool(row[z]),
                    magnitude=float(row[f"{z}_mag"]),
                )
            )

    return HeatmapResponse(
        week_of=actual_date.date() if actual_date is not None else (week_of or date.today()),
        cells=cells,
    )


# ── /divergence/{week} ─────────────────────────────────────────────────────
@app.get("/divergence/{week}", response_model=list[DivergenceRow])
def divergence_endpoint(week: date) -> list[DivergenceRow]:
    """A2-only view ranked by magnitude. `week` is an inclusive date —
    the most-recent bar <= week is scored per market."""
    b = _bundle()
    name_lookup = {c.symbol: c.name for c in _universe()}
    target = pd.Timestamp(week)
    rows: list[DivergenceRow] = []
    for sym, g in b.annotated.items():
        sub = g[g["date"] <= target]
        if sub.empty:
            continue
        last = sub.iloc[-1]
        if not bool(last["A2"]):
            continue
        # bullish divergence = price-low + commercial-net-up
        is_bullish = (last["close"] <= sub["close"].rolling(260, min_periods=260).min().iloc[-1])
        rows.append(
            DivergenceRow(
                symbol=sym,
                name=name_lookup.get(sym, sym),
                sector=sector_of(sym) or "",
                date=last["date"].date(),
                magnitude=float(last["A2_mag"]),
                direction="bullish" if is_bullish else "bearish",
                close=float(last["close"]),
                net_commercials=float(last["net_commercials"]),
            )
        )
    rows.sort(key=lambda r: r.magnitude, reverse=True)
    return rows


# ── /news/{symbol} ─────────────────────────────────────────────────────────
@app.get("/news/{symbol}", response_model=NewsResponse)
def news_for_symbol(
    symbol: str,
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    limit: int = Query(default=200, ge=1, le=1000),
) -> NewsResponse:
    b = _bundle()
    _contract(symbol)  # 404 if unknown

    if from_date is None:
        from_date = (pd.Timestamp.utcnow().normalize() - pd.DateOffset(days=90)).date()
    if to_date is None:
        to_date = (pd.Timestamp.utcnow().normalize() + pd.DateOffset(days=30)).date()

    from ingest import news as news_mod
    sub = news_mod.news_for_market(
        b.news_df, symbol,
        from_date=pd.Timestamp(from_date),
        to_date=pd.Timestamp(to_date),
    )
    sub = sub.head(limit)

    items = [
        NewsItem(
            date=row["date"].to_pydatetime() if hasattr(row["date"], "to_pydatetime") else row["date"],
            source=row["source"],
            source_category=row["source_category"],
            ticker=row.get("ticker") if not pd.isna(row.get("ticker")) else None,
            title=row["title"],
            url=row.get("url") if not pd.isna(row.get("url")) else None,
            publisher=row.get("publisher") if not pd.isna(row.get("publisher")) else None,
            markets=row["markets"] if isinstance(row["markets"], list) else [],
        )
        for _, row in sub.iterrows()
    ]
    return NewsResponse(symbol=symbol, from_date=from_date, to_date=to_date, items=items)


# ── /article?url=… ──────────────────────────────────────────────────────────
@app.get("/article", response_model=ArticleResponse)
def article_endpoint(url: str = Query(..., min_length=10, max_length=2048)) -> ArticleResponse:
    """Fetch + extract article content from a URL for the in-app reader.
    No LLM. Pure trafilatura extraction. Cached in-process."""
    try:
        a = fetch_article(url)
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"extract failed: {type(e).__name__}: {e}")
    return ArticleResponse(
        url=a.url,
        title=a.title,
        site=a.site,
        byline=a.byline,
        published=a.published,
        content_html=a.content_html,
        word_count=a.word_count,
        fetched_at=a.fetched_at,
    )


# ── /news (all markets) ─────────────────────────────────────────────────────
@app.get("/news", response_model=NewsResponse)
def news_all(
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    limit: int = Query(default=200, ge=1, le=1000),
) -> NewsResponse:
    b = _bundle()
    if from_date is None:
        from_date = (pd.Timestamp.utcnow().normalize() - pd.DateOffset(days=14)).date()
    if to_date is None:
        to_date = (pd.Timestamp.utcnow().normalize() + pd.DateOffset(days=30)).date()
    sub = b.news_df[
        (b.news_df["date"] >= pd.Timestamp(from_date))
        & (b.news_df["date"] <= pd.Timestamp(to_date))
    ].sort_values("date", ascending=False).head(limit)
    items = [
        NewsItem(
            date=row["date"].to_pydatetime() if hasattr(row["date"], "to_pydatetime") else row["date"],
            source=row["source"],
            source_category=row["source_category"],
            ticker=row.get("ticker") if not pd.isna(row.get("ticker")) else None,
            title=row["title"],
            url=row.get("url") if not pd.isna(row.get("url")) else None,
            publisher=row.get("publisher") if not pd.isna(row.get("publisher")) else None,
            markets=row["markets"] if isinstance(row["markets"], list) else [],
        )
        for _, row in sub.iterrows()
    ]
    return NewsResponse(from_date=from_date, to_date=to_date, items=items)
