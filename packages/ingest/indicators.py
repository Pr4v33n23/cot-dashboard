"""Indicators used by WILLIAMS_COT_SWING_v1.

All functions are vectorized over a per-symbol DataFrame and return a new
column. Callers group by symbol before invoking.

Citations:
- COT Index — Upperman ch.6: 100 * (Net_now - Net_min) / (Net_max - Net_min)
  over a rolling 156-week (3-year) window of weekly COT values.
- UCL/LCL — Briese ch.4: rolling mean + k*std on net commercial position,
  with k = 1.5 over a 156-week window.
- SMA — Briese ch.6: 10 / 18 day moving averages on settlement close.
- ATR — Wilder 1978: 14-day average true range, used for initial stop sizing.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# PLAN §1.1 — Upperman lookback is 156 weekly reports (3 years).
COT_INDEX_LOOKBACK_WEEKS = 156
# PLAN §1.2 — UCL/LCL ±1.5σ over the same window.
UCL_K_SIGMA = 1.5
# Daily moving averages from PLAN §1.2 L4 + L5.
SMA_FAST = 10
SMA_SLOW = 18
ATR_LOOKBACK = 14


def cot_index(net: pd.Series, lookback: int = COT_INDEX_LOOKBACK_WEEKS) -> pd.Series:
    """Upperman COT Index on a weekly net-position series.

    Returns 0–100 floats. NaN until lookback fills.
    """
    rolling_min = net.rolling(lookback, min_periods=lookback).min()
    rolling_max = net.rolling(lookback, min_periods=lookback).max()
    denom = (rolling_max - rolling_min).replace(0, np.nan)
    return 100.0 * (net - rolling_min) / denom


def ucl_lcl(
    net: pd.Series,
    lookback: int = COT_INDEX_LOOKBACK_WEEKS,
    k: float = UCL_K_SIGMA,
) -> tuple[pd.Series, pd.Series]:
    """Briese's statistical bands on net-commercial position.

    Returns (ucl, lcl) where ucl = mean + k*std, lcl = mean - k*std,
    both over a `lookback`-week rolling window.
    """
    mean = net.rolling(lookback, min_periods=lookback).mean()
    std = net.rolling(lookback, min_periods=lookback).std(ddof=0)
    return mean + k * std, mean - k * std


def sma(close: pd.Series, window: int) -> pd.Series:
    return close.rolling(window, min_periods=window).mean()


def true_range(high: pd.Series, low: pd.Series, prev_close: pd.Series) -> pd.Series:
    return pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, lookback: int = ATR_LOOKBACK) -> pd.Series:
    """Wilder ATR — exponential smoothing equivalent via rolling mean of TR."""
    tr = true_range(high, low, close.shift(1))
    # Wilder's smoothing == EWM with alpha = 1/N; rolling mean is close enough for Phase 0.
    return tr.rolling(lookback, min_periods=lookback).mean()


def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Annotate a merged (price + COT) DataFrame with every indicator column.

    Expects per-symbol grouping by the caller — do NOT pass a multi-symbol frame
    or rolling windows will leak across symbols.
    """
    out = df.copy()
    out["cot_index_comm"] = cot_index(out["net_commercials"])
    out["ucl"], out["lcl"] = ucl_lcl(out["net_commercials"])
    out["sma_fast"] = sma(out["close"], SMA_FAST)
    out["sma_slow"] = sma(out["close"], SMA_SLOW)
    out["atr"] = atr(out["high"], out["low"], out["close"])
    # Layer-3 component indicators (PLAN §1.2 L3):
    # producer shorts "near" 3y low, consumer (PM long) "near" 3y high.
    #
    # A literal `<=` against rolling-min only fires when a NEW extreme prints,
    # which gives ~0 signals across the universe. Briese ch.5 describes the
    # condition as "near the extreme", not "at the literal extreme". We
    # implement "near" as the bottom/top decile of the 3-year window.
    pm_short_window = out["pm_short"].rolling(COT_INDEX_LOOKBACK_WEEKS, min_periods=COT_INDEX_LOOKBACK_WEEKS)
    pm_long_window = out["pm_long"].rolling(COT_INDEX_LOOKBACK_WEEKS, min_periods=COT_INDEX_LOOKBACK_WEEKS)
    out["pm_short_3y_low"] = out["pm_short"] <= pm_short_window.quantile(0.10)
    out["pm_long_3y_high"] = out["pm_long"] >= pm_long_window.quantile(0.90)
    out["pm_long_3y_low"] = out["pm_long"] <= pm_long_window.quantile(0.10)
    out["pm_short_3y_high"] = out["pm_short"] >= pm_short_window.quantile(0.90)
    return out
