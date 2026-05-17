"""Attention zones for `COT_LENS_v1` — the five-lens scorer.

Replaces the v1 `signal.py` (mechanized six-layer trigger). Zones do NOT generate
buy/sell signals. They generate *attention*: "this market is positionally
unusual right now; look at the chart + news rail and decide for yourself."

Lenses (PLAN §1.2):
    A1 — Extreme positioning   : COT Index ≥ 90 or ≤ 10
    A2 — Price divergence      : 52w price extreme vs opposite-direction net move
    A3 — Sector outlier        : COT Index > 1.5σ from sector median
    A4 — Momentum shift        : 4-week COT-index ROC in top/bottom decile
    A5 — Hedger/speculator     : commercial + managed-money both at 3y extreme,
                                 on opposite sides

Each lens returns a per-bar boolean column + a per-bar "magnitude" float that
the UI can use to rank "how interesting" the market is today.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

LOOKBACK_3Y_WEEKS = 156          # matches indicators.COT_INDEX_LOOKBACK_WEEKS
LOOKBACK_52W = 260               # ~52 weeks in trading days
DIVERGENCE_LOOKBACK_WEEKS = 3
MOMENTUM_LOOKBACK_WEEKS = 4
A1_HIGH = 90.0
A1_LOW = 10.0
A3_SIGMA = 1.5
A4_DECILE = 0.10
A5_EXTREME_PCTILE = 0.90         # "near 3y extreme" = top/bottom decile


def _mm_net(df: pd.DataFrame) -> pd.Series:
    """Managed-money net position — used in A5."""
    return df["mm_long"].fillna(0) - df["mm_short"].fillna(0)


def annotate_zones(df: pd.DataFrame) -> pd.DataFrame:
    """Per-symbol annotation. Caller must group by symbol before invoking
    (rolling windows would leak across markets otherwise).

    Expects: the output of `indicators.add_all_indicators(...)`.
    Adds:    A1..A5 boolean + magnitude columns + `n_zones` count.
    """
    out = df.copy()

    # ── A1 Extreme positioning ───────────────────────────────────────────
    out["A1"] = (out["cot_index_comm"] >= A1_HIGH) | (out["cot_index_comm"] <= A1_LOW)
    # Magnitude = distance past the threshold, normalized to 0..1 within the
    # 10-point band beyond the threshold.
    out["A1_mag"] = np.where(
        out["cot_index_comm"] >= A1_HIGH,
        ((out["cot_index_comm"] - A1_HIGH) / 10.0).clip(0, 1),
        np.where(
            out["cot_index_comm"] <= A1_LOW,
            ((A1_LOW - out["cot_index_comm"]) / 10.0).clip(0, 1),
            0.0,
        ),
    )

    # ── A2 Price divergence ──────────────────────────────────────────────
    # Price prints new 52w extreme, commercial net moves the opposite way over
    # the prior `DIVERGENCE_LOOKBACK_WEEKS` (3 CFTC releases ≈ 15 trading days).
    rolling_max = out["close"].rolling(LOOKBACK_52W, min_periods=LOOKBACK_52W).max()
    rolling_min = out["close"].rolling(LOOKBACK_52W, min_periods=LOOKBACK_52W).min()
    new_high = out["close"] >= rolling_max
    new_low = out["close"] <= rolling_min
    # 15-trading-day net-commercial change (CFTC weekly → ~3 releases worth).
    net_change_15d = out["net_commercials"] - out["net_commercials"].shift(15)
    out["A2"] = (new_high & (net_change_15d < 0)) | (new_low & (net_change_15d > 0))
    # Magnitude = |net change| normalized to its rolling-3y standard deviation.
    rolling_std = net_change_15d.rolling(LOOKBACK_3Y_WEEKS, min_periods=LOOKBACK_3Y_WEEKS).std(ddof=0)
    out["A2_mag"] = (net_change_15d.abs() / rolling_std).clip(0, 3).fillna(0) / 3.0

    # ── A4 Momentum shift ────────────────────────────────────────────────
    # 4-week rate-of-change on COT Index, top/bottom decile of own 3y history.
    cot_roc = out["cot_index_comm"] - out["cot_index_comm"].shift(20)  # ~4 weeks of daily bars
    roc_high = cot_roc.rolling(LOOKBACK_3Y_WEEKS, min_periods=LOOKBACK_3Y_WEEKS).quantile(1 - A4_DECILE)
    roc_low = cot_roc.rolling(LOOKBACK_3Y_WEEKS, min_periods=LOOKBACK_3Y_WEEKS).quantile(A4_DECILE)
    out["A4"] = (cot_roc >= roc_high) | (cot_roc <= roc_low)
    out["A4_mag"] = (cot_roc.abs() / cot_roc.abs().rolling(LOOKBACK_3Y_WEEKS, min_periods=LOOKBACK_3Y_WEEKS).max()).fillna(0).clip(0, 1)

    # ── A5 Hedger / speculator imbalance ─────────────────────────────────
    # Commercials near 3y extreme AND managed money near 3y opposite extreme.
    mm = _mm_net(out)
    comm_window = out["net_commercials"].rolling(LOOKBACK_3Y_WEEKS, min_periods=LOOKBACK_3Y_WEEKS)
    mm_window = mm.rolling(LOOKBACK_3Y_WEEKS, min_periods=LOOKBACK_3Y_WEEKS)
    comm_hi = out["net_commercials"] >= comm_window.quantile(A5_EXTREME_PCTILE)
    comm_lo = out["net_commercials"] <= comm_window.quantile(1 - A5_EXTREME_PCTILE)
    mm_hi = mm >= mm_window.quantile(A5_EXTREME_PCTILE)
    mm_lo = mm <= mm_window.quantile(1 - A5_EXTREME_PCTILE)
    out["A5"] = (comm_hi & mm_lo) | (comm_lo & mm_hi)
    # Magnitude = mean of the two distances-from-extreme, in 3y-pctile units.
    comm_rank = comm_window.rank(pct=True)
    mm_rank = mm_window.rank(pct=True)
    out["A5_mag"] = np.where(
        out["A5"],
        ((comm_rank - 0.5).abs() + (mm_rank - 0.5).abs()) / 1.0,
        0.0,
    )

    # A3 (sector outlier) is multi-symbol — computed by `add_sector_zone()` below.
    out["A3"] = False
    out["A3_mag"] = 0.0

    out["n_zones"] = out[["A1", "A2", "A3", "A4", "A5"]].sum(axis=1)
    return out


def add_sector_zone(annotated: dict[str, pd.DataFrame], universe) -> dict[str, pd.DataFrame]:
    """Compute A3 — sector outlier. Requires multi-symbol view, so it runs as
    a post-pass over the per-symbol annotated dict.

    For each (sector, date), find the median + std of `cot_index_comm` across
    the sector's contracts. A market triggers A3 when its index is > A3_SIGMA
    standard deviations from the sector median.
    """
    # Build a long frame keyed by (date, symbol, sector, cot_index_comm)
    sector_lookup = {c.symbol: c.sector for c in universe}
    long_rows = []
    for sym, g in annotated.items():
        sector = sector_lookup.get(sym)
        if sector is None:
            continue
        long_rows.append(g[["date", "cot_index_comm"]].assign(symbol=sym, sector=sector))
    if not long_rows:
        return annotated
    long_df = pd.concat(long_rows, ignore_index=True).dropna(subset=["cot_index_comm"])

    # Per (date, sector): median + std across symbols
    grouped = long_df.groupby(["date", "sector"])["cot_index_comm"]
    stats = grouped.agg(["median", "std"]).reset_index()
    stats.columns = ["date", "sector", "sector_median", "sector_std"]
    long_df = long_df.merge(stats, on=["date", "sector"], how="left")
    long_df["z"] = (long_df["cot_index_comm"] - long_df["sector_median"]) / long_df["sector_std"].replace(0, np.nan)
    long_df["A3"] = long_df["z"].abs() >= A3_SIGMA
    long_df["A3_mag"] = (long_df["z"].abs() / 3.0).clip(0, 1).fillna(0)

    # Merge A3 back into each per-symbol frame
    out: dict[str, pd.DataFrame] = {}
    for sym, g in annotated.items():
        a3_for_sym = long_df[long_df["symbol"] == sym][["date", "A3", "A3_mag"]]
        merged = g.drop(columns=["A3", "A3_mag"], errors="ignore").merge(
            a3_for_sym, on="date", how="left"
        )
        merged["A3"] = merged["A3"].fillna(False).astype(bool)
        merged["A3_mag"] = merged["A3_mag"].fillna(0.0)
        merged["n_zones"] = merged[["A1", "A2", "A3", "A4", "A5"]].sum(axis=1)
        out[sym] = merged
    return out


def today_attention(annotated: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Return one row per market for the most-recent bar — the `/today` payload.

    Columns: symbol, date, cot_index_comm, n_zones, A1..A5 booleans,
             A1_mag..A5_mag floats, total_mag (sum of mags for ranking).
    """
    rows = []
    for sym, g in annotated.items():
        if g.empty:
            continue
        last = g.iloc[-1]
        rows.append(
            {
                "symbol": sym,
                "date": last["date"],
                "cot_index_comm": float(last["cot_index_comm"]) if pd.notna(last["cot_index_comm"]) else None,
                "n_zones": int(last["n_zones"]),
                "A1": bool(last["A1"]),
                "A2": bool(last["A2"]),
                "A3": bool(last["A3"]),
                "A4": bool(last["A4"]),
                "A5": bool(last["A5"]),
                "A1_mag": float(last["A1_mag"]),
                "A2_mag": float(last["A2_mag"]),
                "A3_mag": float(last["A3_mag"]),
                "A4_mag": float(last["A4_mag"]),
                "A5_mag": float(last["A5_mag"]),
                "total_mag": float(last[["A1_mag", "A2_mag", "A3_mag", "A4_mag", "A5_mag"]].sum()),
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values(["n_zones", "total_mag"], ascending=False).reset_index(drop=True)
