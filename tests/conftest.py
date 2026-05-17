# tests/conftest.py
import pandas as pd
import pytest

# 300 weeks covers 3-year lookback window + buffer for rolling indicators
N = 300


@pytest.fixture(scope="module")
def sample_disagg_df() -> pd.DataFrame:
    """Minimal annotated DataFrame for a physical contract (DisAgg)."""
    idx = pd.date_range("2020-01-01", periods=N, freq="W")
    return pd.DataFrame({
        "date": idx, "symbol": "CL", "close": 70.0 + pd.Series(range(N)) * 0.1,
        "open": 69.5, "high": 71.0, "low": 69.0, "volume": 100_000,
        "net_commercials": pd.Series(range(N)) * 100,
        "pm_long": 500_000, "pm_short": 200_000,
        "sd_long": 100_000, "sd_short": 80_000,
        "mm_long": 150_000, "mm_short": 300_000,
        "nr_long": 20_000, "nr_short": 25_000,
        "open_interest": 400_000 + pd.Series(range(N)) * 500,
        "cot_index_comm": pd.Series(range(N)) / 3.0,
        "sma_fast": 70.5, "sma_slow": 70.0, "ucl": 75.0, "lcl": 65.0,
    })


@pytest.fixture(scope="module")
def sample_tff_df() -> pd.DataFrame:
    """Minimal annotated DataFrame for a financial contract (TFF)."""
    idx = pd.date_range("2020-01-01", periods=N, freq="W")
    return pd.DataFrame({
        "date": idx, "symbol": "EURUSD", "close": 1.10 + pd.Series(range(N)) * 0.001,
        "open": 1.095, "high": 1.115, "low": 1.085, "volume": 200_000,
        "net_commercials": pd.Series(range(N)) * -50,
        "dealer_long": 400_000, "dealer_short": 450_000,
        "am_long": 300_000, "am_short": 200_000,
        "lf_long": 100_000, "lf_short": 280_000,
        "nr_long": 15_000, "nr_short": 20_000,
        "open_interest": 350_000 + pd.Series(range(N)) * 300,
        "cot_index_comm": pd.Series(range(N)) / 3.0,
        "sma_fast": 1.105, "sma_slow": 1.100, "ucl": 1.15, "lcl": 1.05,
    })
