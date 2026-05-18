import pandas as pd
import numpy as np
import pytest
from ingest.zones import annotate_zones, annotate_divergence


def _make_df(n=300, market_type="physical"):
    idx = pd.date_range("2020-01-01", periods=n, freq="W")
    df = pd.DataFrame({
        "date": idx, "symbol": "CL", "close": 70.0 + np.arange(n) * 0.05,
        "open": 69.5, "high": 71.0, "low": 69.0, "volume": 100_000,
        "net_commercials": np.sin(np.arange(n) / 10) * 100_000,
        "pm_long": 500_000, "pm_short": 200_000,
        "sd_long": 100_000, "sd_short": 80_000,
        "mm_long": 150_000, "mm_short": 300_000,
        "lf_long": 100_000, "lf_short": 200_000 + np.sin(np.arange(n)/15) * 50_000,
        "am_long": 250_000, "am_short": 180_000,
        "nr_long": 20_000, "nr_short": 25_000,
        "open_interest": 400_000 + np.arange(n) * 500,
        "cot_index_comm": np.clip(np.arange(n) / 3.0, 0, 100),
        "sma_fast": 70.5, "sma_slow": 70.0, "ucl": 75.0, "lcl": 65.0,
        "market_type": market_type,
    })
    return df


def test_physical_zones_present():
    df = _make_df(market_type="physical")
    result = annotate_zones(df)
    for z in ("A1", "A2", "A3", "A4", "A5"):
        assert z in result.columns, f"{z} missing for physical"


def test_financial_zones_all_false():
    df = _make_df(market_type="financial")
    result = annotate_zones(df)
    for z in ("A1", "A2", "A3", "A4", "A5"):
        assert z in result.columns
        assert result[z].sum() == 0, f"{z} should be all False for financial"


def test_comm_spec_divergence_physical():
    df = _make_df(market_type="physical")
    result = annotate_divergence(df)
    assert "comm_spec_divergence" in result.columns
    assert result["comm_spec_divergence"].dtype in (int, "int64", "int32")
    assert result["am_lf_divergence"].sum() == 0  # financial column zeros for physical


def test_am_lf_divergence_financial():
    df = _make_df(market_type="financial")
    result = annotate_divergence(df)
    assert "am_lf_divergence" in result.columns
    assert result["am_lf_divergence"].dtype in (int, "int64", "int32")
    assert result["comm_spec_divergence"].sum() == 0  # physical column zeros for financial


def test_divergence_increases_consecutively():
    df = _make_df(market_type="physical")
    # Make commercials always rise, mm always fall
    df["net_commercials"] = np.arange(300) * 1000.0
    df["mm_long"] = 300_000 - np.arange(300) * 500
    df["mm_short"] = 100_000
    result = annotate_divergence(df)
    # After warm-up period, divergence streak should grow
    assert result["comm_spec_divergence"].max() > 10
