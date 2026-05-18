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
from datetime import date, datetime, timedelta, timezone
from typing import Iterator

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .article import fetch_article
from .chat import answer as chat_answer
from .data import Bundle, build_bundle, sector_of, CACHE_DIR
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
    RetailSentimentItem, RetailSentimentResponse,
    RegimeResponse, SynthesisResponse,
    SectorSignal, WatchMarket, DigestResponse,
    ChatMessage, ChatRequest, ChatResponse,
    ExtremesRow,
    AnalogueEntry, AnaloguesResponse,
    AlertRule, AlertTrigger,
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

    _bool_cols  = {"A1", "A2", "A3", "A4", "A5"}
    _int_cols   = {"n_zones", "comm_spec_divergence", "am_lf_divergence", "regime_weeks"}
    _str_cols   = {"regime_label", "sentiment_label", "sentiment_reason"}
    _list_cols  = {"regime_proba"}
    bar_cols = [
        "open", "high", "low", "close", "volume", "sma_fast", "sma_slow",
        "cot_index_comm", "net_commercials", "pm_long", "pm_short",
        "sd_long", "sd_short", "mm_long", "mm_short", "ucl", "lcl",
        "open_interest", "nr_long", "nr_short",
        "dealer_long", "dealer_short", "am_long", "am_short", "lf_long", "lf_short",
        "A1", "A2", "A3", "A4", "A5", "n_zones",
        "comm_spec_divergence", "am_lf_divergence",
        "regime_label", "regime_proba", "regime_weeks",
        "confluence_score", "sentiment_score", "sentiment_label", "sentiment_reason",
    ]

    def _cast(col: str, val):
        if col in _bool_cols:   return bool(val)
        if col in _int_cols:    return int(val)
        if col in _str_cols:    return str(val)
        if col in _list_cols:   return val if isinstance(val, list) else None
        return float(val)

    bars: list[BarRow] = []
    for _, row in sub.iterrows():
        fields: dict = {"date": row["date"].date()}
        for c in bar_cols:
            if c not in row.index:
                continue
            v = row.get(c)
            if c in _list_cols:
                fields[c] = v if isinstance(v, list) else None
            elif c in _str_cols:
                fields[c] = None if (v is None or (isinstance(v, float) and pd.isna(v))) else str(v)
            else:
                try:
                    fields[c] = None if (v is None or (isinstance(v, float) and pd.isna(v))) else _cast(c, v)
                except (ValueError, TypeError):
                    fields[c] = None
        bars.append(BarRow(**fields))

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

    from ingest.universe import UNIVERSE as _UNI  # noqa: PLC0415
    _mtype = {c.symbol: getattr(c, "market_type", "physical") for c in _UNI}

    for sym, g in b.annotated.items():
        if g.empty:
            continue
        if target_dt is None:
            row = g.iloc[-1]
        else:
            sub = g[g["date"] <= target_dt]
            if sub.empty:
                continue
            row = sub.iloc[-1]
        actual_date = row["date"]
        sec = sector_of(sym) or ""
        mtype = _mtype.get(sym, "physical")
        rlabel = row.get("regime_label")
        regime = str(rlabel) if rlabel and not (isinstance(rlabel, float)) else None
        for z in ("A1", "A2", "A3", "A4", "A5"):
            cells.append(
                HeatmapCell(
                    symbol=sym,
                    sector=sec,
                    zone=z,
                    active=bool(row[z]),
                    magnitude=float(row[f"{z}_mag"]),
                    market_type=mtype,
                    regime_label=regime,
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
    macro_only: bool = Query(default=False),
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
    if macro_only:
        sub = sub[sub["source_category"].isin(["macro", "agency"])]
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
    macro_only: bool = Query(default=False),
) -> NewsResponse:
    b = _bundle()
    if from_date is None:
        from_date = (pd.Timestamp.utcnow().normalize() - pd.DateOffset(days=14)).date()
    if to_date is None:
        to_date = (pd.Timestamp.utcnow().normalize() + pd.DateOffset(days=30)).date()
    sub = b.news_df[
        (b.news_df["date"] >= pd.Timestamp(from_date))
        & (b.news_df["date"] <= pd.Timestamp(to_date))
    ].sort_values("date", ascending=False)
    if macro_only:
        sub = sub[sub["source_category"].isin(["macro", "agency"])]
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
    return NewsResponse(from_date=from_date, to_date=to_date, items=items)


@app.get("/retail-sentiment/{symbol}", response_model=RetailSentimentResponse)
def retail_sentiment_endpoint(symbol: str) -> RetailSentimentResponse:
    b = _bundle()
    if b.retail_df.empty:
        return RetailSentimentResponse(symbol=symbol, items=[], avg_long_pct=50.0, avg_short_pct=50.0)
    sym_df = b.retail_df[b.retail_df["symbol"] == symbol]
    if sym_df.empty:
        return RetailSentimentResponse(symbol=symbol, items=[], avg_long_pct=50.0, avg_short_pct=50.0)
    items = [RetailSentimentItem(**row) for row in sym_df.to_dict("records")]
    avg_long = float(sym_df["long_pct"].mean())
    avg_short = float(sym_df["short_pct"].mean())
    return RetailSentimentResponse(symbol=symbol, items=items, avg_long_pct=avg_long, avg_short_pct=avg_short)


@app.get("/regime/{symbol}", response_model=RegimeResponse)
def regime_endpoint(symbol: str) -> RegimeResponse:
    import pickle  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415
    b = _bundle()
    if symbol not in b.annotated:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not found")
    df = b.annotated[symbol]
    last = df.iloc[-1]
    from ingest.universe import UNIVERSE as _UNI  # noqa: PLC0415
    contract = next((c for c in _UNI if c.symbol == symbol), None)
    market_type = getattr(contract, "market_type", "physical") if contract else "physical"
    proba = last.get("regime_proba") or [0.25, 0.25, 0.25, 0.25]
    if not isinstance(proba, list):
        proba = [0.25, 0.25, 0.25, 0.25]
    state_names = ["trending", "accumulation", "distribution", "ranging"]
    tm: list[list[float]] = [[0.25] * 4 for _ in range(4)]
    cache_path = CACHE_DIR / f"regime_{symbol}.pkl"
    if cache_path.exists():
        try:
            with open(cache_path, "rb") as f:
                obj = pickle.load(f)
            tm = obj["model"].transmat_.tolist()
        except Exception:
            pass
    next_proba = list(np.array(proba) @ np.array(tm))
    return RegimeResponse(
        symbol=symbol, market_type=market_type,
        current_regime=str(last.get("regime_label") or "unknown"),
        regime_weeks=int(last.get("regime_weeks") or 0),
        proba=proba, next_bar_proba=next_proba,
        transition_matrix=tm, state_names=state_names,
    )


@app.get("/synthesis/{symbol}", response_model=SynthesisResponse)
def synthesis_endpoint(symbol: str) -> SynthesisResponse:
    b = _bundle()
    data = b.synthesis.get(symbol, {})
    return SynthesisResponse(
        symbol=symbol,
        summary=data.get("summary", ""),
        confluence_score=float(data.get("confluence_score", 0.0)),
        key_factors=data.get("key_factors", []),
        watch=data.get("watch", ""),
    )


# ── /intelligence/digest ───────────────────────────────────────────────────
@app.get("/intelligence/digest", response_model=DigestResponse)
def intelligence_digest_endpoint() -> DigestResponse:
    from ingest.intelligence import load_or_generate_digest  # noqa: PLC0415
    b = _bundle()
    data = load_or_generate_digest(b.annotated, b.news_df, b.synthesis, CACHE_DIR)

    from ingest.universe import UNIVERSE as _UNI  # noqa: PLC0415
    name_map = {c.symbol: c.name for c in _UNI}
    sec_map  = {c.symbol: c.sector for c in _UNI}

    watch: list[WatchMarket] = []
    for wm in data.get("watch_markets", []):
        sym = wm.get("symbol", "")
        if not sym:
            continue
        watch.append(WatchMarket(
            symbol=sym,
            name=name_map.get(sym, sym),
            sector=sec_map.get(sym, ""),
            confluence_score=float((b.synthesis or {}).get(sym, {}).get("confluence_score", 0.0)),
            reason=wm.get("reason", ""),
        ))

    generated_at_str = data.get("generated_at", datetime.now(tz=timezone.utc).isoformat())
    try:
        generated_at = datetime.fromisoformat(generated_at_str.replace("Z", "+00:00"))
    except Exception:
        generated_at = datetime.now(tz=timezone.utc)

    return DigestResponse(
        generated_at=generated_at,
        macro_narrative=data.get("macro_narrative", ""),
        sector_signals=[
            SectorSignal(**{**s, "signal": str(s.get("signal", "neutral")).lower()})
            for s in data.get("sector_signals", [])
            if s.get("sector")
        ],
        watch_markets=watch,
    )


@app.get("/extremes", response_model=list[ExtremesRow])
def extremes_endpoint() -> list[ExtremesRow]:
    """All markets ranked by proximity to a 3-year COT positioning extreme."""
    from ingest.universe import UNIVERSE as _UNI  # noqa: PLC0415
    b = _bundle()
    name_map = {c.symbol: c.name for c in _UNI}
    mtype_map = {c.symbol: getattr(c, "market_type", "physical") for c in _UNI}
    rows: list[ExtremesRow] = []
    for sym, df in b.annotated.items():
        if df.empty or "cot_index_comm" not in df.columns:
            continue
        series = df["cot_index_comm"].dropna()
        if len(series) < 52:
            continue
        current = float(series.iloc[-1])
        lookback = series.iloc[-156:] if len(series) >= 156 else series
        p90 = float(lookback.quantile(0.90))
        p10 = float(lookback.quantile(0.10))
        dist_high = max(0.0, current - p90) / max(1.0, 100 - p90)
        dist_low  = max(0.0, p10 - current) / max(1.0, p10)
        extremeness = round(min(1.0, max(dist_high, dist_low)), 3)
        direction = "long" if current > p90 else ("short" if current < p10 else "neutral")
        last = df.iloc[-1]
        synth = (b.synthesis or {}).get(sym, {})
        rows.append(ExtremesRow(
            symbol=sym,
            name=name_map.get(sym, sym),
            sector=sector_of(sym) or "",
            market_type=mtype_map.get(sym, "physical"),
            cot_index=round(current, 1),
            extremeness=extremeness,
            direction=direction,
            pct_90=round(p90, 1),
            pct_10=round(p10, 1),
            n_zones=int(last.get("n_zones", 0) or 0),
            regime_label=str(last.get("regime_label") or "") or None,
            confluence_score=float(synth.get("confluence_score", 0) or 0),
        ))
    rows.sort(key=lambda r: r.extremeness, reverse=True)
    return rows


@app.get("/analogues/{symbol}", response_model=AnaloguesResponse)
def analogues_endpoint(symbol: str, top_n: int = Query(default=5, le=10)) -> AnaloguesResponse:
    """Find the N most similar historical COT profiles for this symbol."""
    import numpy as np  # noqa: PLC0415
    b = _bundle()
    df = b.annotated.get(symbol)
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail=f"No data for {symbol}")

    def _vec(row):
        ci = float(row.get("cot_index_comm", 50) or 50) / 100.0
        dw = min(float(row.get("comm_spec_divergence", 0) or row.get("am_lf_divergence", 0) or 0), 12) / 12.0
        nz = float(row.get("n_zones", 0) or 0) / 5.0
        return np.array([ci, dw, nz])

    current_row = df.iloc[-1]
    current_vec = _vec(current_row)
    current_cot = float(current_row.get("cot_index_comm", 50) or 50)
    norm_cur = np.linalg.norm(current_vec)

    results = []
    close_col = "close"
    cutoff = len(df) - 4
    for i in range(52, cutoff):
        row = df.iloc[i]
        vec = _vec(row)
        norm_v = np.linalg.norm(vec)
        if norm_cur < 1e-9 or norm_v < 1e-9:
            continue
        sim = float(np.dot(current_vec, vec) / (norm_cur * norm_v))

        def _fwd(weeks, idx=i):
            j = idx + weeks
            if j >= len(df):
                return None
            p0 = df.iloc[idx].get(close_col)
            p1 = df.iloc[j].get(close_col)
            if p0 and p1 and float(p0) > 0:
                return round((float(p1) - float(p0)) / float(p0) * 100, 2)
            return None

        results.append(AnalogueEntry(
            date=row["date"].date() if hasattr(row["date"], "date") else row["date"],
            weeks_ago=len(df) - 1 - i,
            similarity=round(sim, 3),
            cot_index_then=round(float(row.get("cot_index_comm", 50) or 50), 1),
            price_then=float(row.get(close_col)) if row.get(close_col) else None,
            fwd_4w_pct=_fwd(4),
            fwd_8w_pct=_fwd(8),
            fwd_12w_pct=_fwd(12),
        ))

    results.sort(key=lambda x: x.similarity, reverse=True)
    return AnaloguesResponse(
        symbol=symbol,
        current_cot_index=round(current_cot, 1),
        analogues=results[:top_n],
    )


@app.get("/alerts", response_model=list[AlertRule])
def list_alerts_endpoint():
    from ingest.alerts import list_alerts  # noqa: PLC0415
    return list_alerts()


@app.post("/alerts", response_model=AlertRule)
def create_alert_endpoint(rule: AlertRule):
    from ingest.alerts import create_alert  # noqa: PLC0415
    return create_alert(rule.symbol, rule.field, rule.condition, rule.threshold, rule.label)


@app.delete("/alerts/{alert_id}")
def delete_alert_endpoint(alert_id: str):
    from ingest.alerts import delete_alert  # noqa: PLC0415
    if not delete_alert(alert_id):
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"ok": True}


@app.post("/alerts/check", response_model=list[AlertTrigger])
def check_alerts_endpoint():
    from ingest.alerts import check_alerts  # noqa: PLC0415
    b = _bundle()
    return check_alerts(b.annotated, b.synthesis)


@app.post("/intelligence/refresh")
def intelligence_refresh_endpoint() -> dict:
    from ingest.intelligence import load_or_generate_digest  # noqa: PLC0415
    b = _bundle()
    load_or_generate_digest(b.annotated, b.news_df, b.synthesis, CACHE_DIR, force=True)
    return {"ok": True}


# ── /chat ──────────────────────────────────────────────────────────────────
@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(req: ChatRequest) -> ChatResponse:
    """Natural language analyst grounded in live COT bundle data."""
    b = _bundle()
    messages = [{"role": m.role, "content": m.content} for m in req.messages]
    reply, cited, ctx_date = chat_answer(messages, b)
    return ChatResponse(reply=reply, cited_markets=cited, context_date=ctx_date)
