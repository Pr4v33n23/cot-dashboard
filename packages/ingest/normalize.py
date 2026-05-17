"""Merge weekly COT reports onto daily price bars.

CFTC reports are weekly (Tuesday snapshot, Friday release). Strategy executes
on daily bars. We forward-fill COT data onto every daily bar at and after its
release date, so the signal logic never sees a value before it was public.

Look-ahead avoidance: the merge uses `release_date = report_date + offset`,
where `offset` defaults to 3 days (Tuesday snapshot → Friday release). Bars
strictly before `release_date` see the prior week's values.
"""

from __future__ import annotations

import pandas as pd

RELEASE_OFFSET_DAYS = 3  # Tuesday snapshot -> Friday release per PLAN §1.3


def join_cot_to_prices(
    prices: pd.DataFrame,
    cot: pd.DataFrame,
    release_offset_days: int = RELEASE_OFFSET_DAYS,
) -> pd.DataFrame:
    """Return prices joined with the most-recently-released COT row.

    Args:
        prices: tidy daily OHLCV (columns: date, symbol, open, high, low, close, volume)
        cot: tidy weekly COT (columns: report_date, symbol, ...)
        release_offset_days: business days from CFTC `report_date` until the data
            is public. Bars whose `date < report_date + offset` cannot see it.

    Returns:
        Daily DataFrame with one row per (date, symbol) and every COT column
        forward-filled within symbol from the moment of release.
    """
    if prices.empty or cot.empty:
        return prices.copy()

    cot = cot.copy()
    cot["release_date"] = cot["report_date"] + pd.Timedelta(days=release_offset_days)
    # Normalize dtype precision so merge_asof's strict dtype check passes
    # regardless of upstream source (yfinance ships ms, CFTC ships ns).
    cot["release_date"] = pd.to_datetime(cot["release_date"]).astype("datetime64[ns]")
    cot = cot.sort_values(["symbol", "release_date"])

    prices = prices.sort_values(["symbol", "date"]).copy()
    prices["date"] = pd.to_datetime(prices["date"]).astype("datetime64[ns]")

    merged_frames: list[pd.DataFrame] = []
    for symbol, price_grp in prices.groupby("symbol", sort=False):
        cot_grp = cot[cot["symbol"] == symbol].drop(columns=["symbol"])
        if cot_grp.empty:
            merged_frames.append(price_grp)
            continue
        # As-of merge: each daily bar sees the latest COT row whose
        # release_date <= bar date. Equivalent to forward-fill from release.
        merged = pd.merge_asof(
            price_grp.sort_values("date"),
            cot_grp.sort_values("release_date"),
            left_on="date",
            right_on="release_date",
            direction="backward",
        )
        merged_frames.append(merged)

    return pd.concat(merged_frames, ignore_index=True).sort_values(["symbol", "date"]).reset_index(drop=True)
