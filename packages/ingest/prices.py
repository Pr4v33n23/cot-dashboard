"""Daily-bar price ingest from Yahoo Finance via the `yfinance` package.

Yahoo Finance continuous-front-month futures use tickers like `CL=F`, `GC=F`,
`ZC=F`. These are auto-rolled and back-adjusted (panama-style), appropriate
for backtest signal generation. PLAN §1.6 applies slippage in ATR units so
back-adjustment doesn't distort the cost model.

## Why not Stooq?

PLAN §1 originally named Stooq. As of mid-2025 Stooq added a per-symbol captcha
+ apikey requirement on the CSV download endpoint, breaking the "free" tier
for programmatic use. Switching to yfinance preserves PLAN §0.3's $0 capital
stop without compromising data quality.

If Phase 0 passes and Phase 1 upgrades to Norgate or Barchart (PLAN §11 Q2),
swap this module out — the downstream contract is `load_universe()` returning
the standard OHLCV schema.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Iterable

import pandas as pd

from .universe import Contract

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)


def _cache_path(cache_dir: Path, symbol: str) -> Path:
    return cache_dir / f"price_{symbol}.parquet"


def download_symbol(
    contract: Contract,
    cache_dir: Path,
    period: str = "max",
    force: bool = False,
) -> Path:
    """Download daily bars for one contract via yfinance. Idempotent unless `force=True`."""
    import yfinance as yf  # local import — keeps top-level import fast

    cache_dir.mkdir(parents=True, exist_ok=True)
    out = _cache_path(cache_dir, contract.symbol)
    if out.exists() and out.stat().st_size > 0 and not force:
        return out
    hist = yf.Ticker(contract.yf_ticker).history(
        period=period, interval="1d", auto_adjust=False
    )
    if hist is None or hist.empty:
        raise RuntimeError(f"yfinance returned no data for {contract.symbol} ({contract.yf_ticker})")
    hist = hist.reset_index()
    hist.columns = [c.strip().lower() for c in hist.columns]
    # Standardize: keep date + OHLCV only, drop dividends/splits/adj-close noise.
    hist["date"] = pd.to_datetime(hist["date"]).dt.tz_localize(None)
    keep = ["date", "open", "high", "low", "close", "volume"]
    hist = hist[[c for c in keep if c in hist.columns]]
    hist.to_parquet(out, index=False)
    return out


def parse_symbol(path: Path, symbol: str) -> pd.DataFrame:
    """Read a cached Parquet OHLCV file and return a tidy DataFrame."""
    df = pd.read_parquet(path)
    df["date"] = pd.to_datetime(df["date"])
    for c in ("open", "high", "low", "close", "volume"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df["symbol"] = symbol
    df = df.dropna(subset=["date", "close"]).sort_values("date")
    return df.reset_index(drop=True)


def load_universe(
    universe: Iterable[Contract],
    cache_dir: Path,
    period: str = "max",
    force: bool = False,
) -> pd.DataFrame:
    """Load daily OHLCV for every contract in `universe` as one tidy frame.

    Returns columns: date, symbol, open, high, low, close, volume.
    Failed contracts are skipped with a printed warning and excluded from output.
    """
    frames: list[pd.DataFrame] = []
    skipped: list[tuple[str, str]] = []
    for contract in universe:
        try:
            path = download_symbol(contract, cache_dir, period=period, force=force)
            frames.append(parse_symbol(path, contract.symbol))
        except Exception as exc:  # noqa: BLE001 — surface as warning
            skipped.append((contract.symbol, str(exc)[:120]))
    if skipped:
        print(f"[prices] skipped {len(skipped)} contracts: {skipped}")
    if not frames:
        return pd.DataFrame(columns=["date", "symbol", "open", "high", "low", "close", "volume"])
    return pd.concat(frames, ignore_index=True)
