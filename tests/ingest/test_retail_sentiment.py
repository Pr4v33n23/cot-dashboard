import pandas as pd
import pytest
from ingest.retail_sentiment import (
    _parse_ig_response,
    _parse_myfxbook_html,
    _parse_oanda_response,
    _compute_nr_proxy,
    merge_sources,
    REQUIRED_COLS,
)

IG_SAMPLE = {
    "instrumentSentimentList": [
        {"instrumentName": "EURUSD", "longPositionPercentage": 35.2, "shortPositionPercentage": 64.8},
        {"instrumentName": "GBPUSD", "longPositionPercentage": 41.0, "shortPositionPercentage": 59.0},
    ]
}

MYFXBOOK_HTML = """
<table>
  <tr><th>Symbol</th><th>Long</th><th>Short</th></tr>
  <tr><td>EUR/USD</td><td>32%</td><td>68%</td></tr>
  <tr><td>GBP/USD</td><td>45%</td><td>55%</td></tr>
</table>
"""

OANDA_SAMPLE = {
    "data": {
        "instrument": "EUR_USD",
        "long": {"percent": 0.38},
        "short": {"percent": 0.62},
    }
}

def test_parse_ig_response_schema():
    df = _parse_ig_response(IG_SAMPLE)
    assert set(REQUIRED_COLS).issubset(df.columns)
    assert (df["source"] == "ig").all()
    assert df["long_pct"].between(0, 100).all()

def test_parse_ig_symbol_mapped():
    df = _parse_ig_response(IG_SAMPLE)
    assert "EURUSD" in df["symbol"].values

def test_parse_myfxbook_html_schema():
    df = _parse_myfxbook_html(MYFXBOOK_HTML)
    assert set(REQUIRED_COLS).issubset(df.columns)
    assert (df["source"] == "myfxbook").all()

def test_parse_oanda_schema():
    df = _parse_oanda_response(OANDA_SAMPLE, "EURUSD")
    assert set(REQUIRED_COLS).issubset(df.columns)
    assert df["long_pct"].iloc[0] == pytest.approx(38.0)

def test_nr_proxy_schema():
    bar = pd.Series({"nr_long": 20000, "nr_short": 30000})
    result = _compute_nr_proxy("ZB", bar)
    assert result["long_pct"] == pytest.approx(40.0)
    assert result["short_pct"] == pytest.approx(60.0)

def test_merge_sources_averages():
    rows = [
        {"symbol": "EURUSD", "long_pct": 30.0, "short_pct": 70.0, "source": "ig"},
        {"symbol": "EURUSD", "long_pct": 32.0, "short_pct": 68.0, "source": "myfxbook"},
    ]
    df = pd.DataFrame(rows)
    result = merge_sources(df)
    assert result.loc[result["symbol"] == "EURUSD", "avg_long_pct"].iloc[0] == pytest.approx(31.0)
