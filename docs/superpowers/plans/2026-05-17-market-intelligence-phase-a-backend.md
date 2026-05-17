# Market Intelligence Expansion — Phase A: Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the data pipeline from 23 physicals to ~80 CME/NYMEX/CBOT/COMEX contracts with six intelligence layers: TFF financial COT, DeepSeek-V4 news sentiment + market synthesis, HMM regime detection, retail sentiment (IG/Myfxbook/OANDA/Put-Call/NR proxy), COT divergence signals, and open interest.

**Architecture:** Extend existing `packages/ingest/` pipeline. Each new module follows the established pattern: download/parse → compute → write Parquet → API reads from in-memory Bundle. `Contract` dataclass gains `market_type` and `report_type` fields so the pipeline can route physicals through DisAgg and financials through TFF. All AI inference (news sentiment + market synthesis) calls **DeepSeek-V4-Pro via HuggingFace Inference API** using `huggingface_hub.InferenceClient`. HMM runs locally via hmmlearn. Three scrapers handle retail sentiment.

**Tech Stack:** Python 3.11, FastAPI, pandas, hmmlearn, scikit-learn, huggingface_hub, lxml, yfinance, pytest

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `tests/conftest.py` | pytest fixtures shared across all tests |
| Create | `tests/ingest/test_universe.py` | Contract fields, market_type routing |
| Create | `tests/ingest/test_tff_cot.py` | TFF column mapping, net computation |
| Create | `tests/ingest/test_zones_extended.py` | divergence signals, market_type gating |
| Create | `tests/ingest/test_news_sentiment.py` | DeepSeek Flash call, incremental skip |
| Create | `tests/ingest/test_regime.py` | HMM fit, regime label assignment |
| Create | `tests/ingest/test_retail_sentiment.py` | scraper output schema |
| Create | `tests/ingest/test_market_synthesis.py` | DeepSeek Pro call, output schema |
| Modify | `pyproject.toml` | add openai, hmmlearn, scikit-learn, lxml, pytest config |
| Modify | `packages/ingest/universe.py` | add market_type, report_type; expand to ~80 contracts |
| Create | `packages/ingest/tff_cot.py` | TFF ZIP download + parse, same interface as cftc_cot |
| Modify | `packages/ingest/zones.py` | comm_spec_divergence + am_lf_divergence, gate A1-A5 on market_type |
| Modify | `packages/ingest/news_taxonomy.py` | keywords for FX, indices, rates, volatility |
| Create | `packages/ingest/_deepseek.py` | shared DeepSeek client, model ID constants |
| Create | `packages/ingest/news_sentiment.py` | DeepSeek Flash batch scorer, incremental |
| Create | `packages/ingest/regime.py` | per-symbol GaussianHMM, Viterbi decode |
| Create | `packages/ingest/retail_sentiment.py` | IG + Myfxbook + OANDA + Put/Call + NR proxy |
| Create | `packages/ingest/market_synthesis.py` | DeepSeek Pro weekly synthesis per market |
| Modify | `apps/api/src/schemas.py` | new BarRow fields, RetailSentimentResponse, RegimeResponse, SynthesisResponse |
| Modify | `apps/api/src/data.py` | extend Bundle, update build_bundle routing |
| Modify | `apps/api/src/main.py` | /retail-sentiment, /regime, /synthesis endpoints |
| Modify | `apps/web/src/lib/api/types.ts` | sync new fields + response types |
| Modify | `apps/web/src/lib/api/client.ts` | add retailSentiment, regime, synthesis methods |

---

## Task 1: Test infrastructure + dependency updates

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/__init__.py`
- Create: `tests/ingest/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Add dependencies to pyproject.toml**

Replace the `[project.optional-dependencies]` section:

```toml
[project.optional-dependencies]
dev = [
    "ruff>=0.5",
    "pytest>=8.0",
    "pytest-mock>=3.14",
    "responses>=0.25",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["packages"]
```

Add to `[project] dependencies`:
```toml
    "huggingface_hub>=0.23",
    "hmmlearn>=0.3",
    "scikit-learn>=1.4",
    "lxml>=5.0",
```

- [ ] **Step 2: Install updated deps**

```bash
.venv/bin/pip install -e ".[dev]"
```

Expected: installs openai, hmmlearn, scikit-learn, lxml with no conflicts.

- [ ] **Step 3: Create test directory structure**

```bash
mkdir -p tests/ingest
touch tests/__init__.py tests/ingest/__init__.py
```

- [ ] **Step 4: Write conftest.py with shared fixtures**

```python
# tests/conftest.py
from __future__ import annotations
import pandas as pd
import pytest

@pytest.fixture()
def sample_disagg_df() -> pd.DataFrame:
    """Minimal annotated DataFrame for a physical contract (DisAgg)."""
    n = 300
    idx = pd.date_range("2020-01-01", periods=n, freq="W")
    return pd.DataFrame({
        "date": idx, "symbol": "CL", "close": 70.0 + pd.Series(range(n)) * 0.1,
        "open": 69.5, "high": 71.0, "low": 69.0, "volume": 100_000,
        "net_commercials": pd.Series(range(n)) * 100,
        "pm_long": 500_000, "pm_short": 200_000,
        "sd_long": 100_000, "sd_short": 80_000,
        "mm_long": 150_000, "mm_short": 300_000,
        "nr_long": 20_000, "nr_short": 25_000,
        "open_interest": 400_000 + pd.Series(range(n)) * 500,
        "cot_index_comm": pd.Series(range(n)) / 3.0,
        "sma_fast": 70.5, "sma_slow": 70.0, "ucl": 75.0, "lcl": 65.0,
    })

@pytest.fixture()
def sample_tff_df() -> pd.DataFrame:
    """Minimal annotated DataFrame for a financial contract (TFF)."""
    n = 300
    idx = pd.date_range("2020-01-01", periods=n, freq="W")
    return pd.DataFrame({
        "date": idx, "symbol": "EURUSD", "close": 1.10 + pd.Series(range(n)) * 0.001,
        "open": 1.095, "high": 1.115, "low": 1.085, "volume": 200_000,
        "net_commercials": pd.Series(range(n)) * -50,
        "dealer_long": 400_000, "dealer_short": 450_000,
        "am_long": 300_000, "am_short": 200_000,
        "lf_long": 100_000, "lf_short": 280_000,
        "nr_long": 15_000, "nr_short": 20_000,
        "open_interest": 350_000 + pd.Series(range(n)) * 300,
        "cot_index_comm": pd.Series(range(n)) / 3.0,
        "sma_fast": 1.105, "sma_slow": 1.100, "ucl": 1.15, "lcl": 1.05,
    })
```

- [ ] **Step 5: Verify pytest discovers tests**

```bash
cd /Users/praveen/Projects/cot-dashboard && PYTHONPATH=packages .venv/bin/pytest tests/ --collect-only 2>&1 | head -10
```

Expected: `no tests ran` (no test files yet) — no errors.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml tests/
git commit -m "test: add pytest infrastructure + dev deps (openai, hmmlearn, lxml)"
```

---

## Task 2: Expand `Contract` dataclass + full ~80-contract universe

**Files:**
- Modify: `packages/ingest/universe.py`
- Create: `tests/ingest/test_universe.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/ingest/test_universe.py
from ingest.universe import UNIVERSE, Contract, sectors

def test_contract_has_market_type():
    for c in UNIVERSE:
        assert c.market_type in ("physical", "financial"), f"{c.symbol} missing market_type"

def test_contract_has_report_type():
    for c in UNIVERSE:
        assert c.report_type in ("disagg", "tff"), f"{c.symbol} missing report_type"

def test_market_type_matches_report_type():
    for c in UNIVERSE:
        if c.market_type == "physical":
            assert c.report_type == "disagg"
        else:
            assert c.report_type == "tff"

def test_universe_size_at_least_50():
    assert len(UNIVERSE) >= 50, f"only {len(UNIVERSE)} contracts"

def test_financial_sectors_present():
    secs = {c.sector for c in UNIVERSE}
    assert "fx" in secs
    assert "indices" in secs
    assert "rates" in secs

def test_symbols_unique():
    syms = [c.symbol for c in UNIVERSE]
    assert len(syms) == len(set(syms))
```

- [ ] **Step 2: Run — verify fails**

```bash
PYTHONPATH=packages .venv/bin/pytest tests/ingest/test_universe.py -v 2>&1 | tail -15
```

Expected: `AttributeError: 'Contract' object has no attribute 'market_type'`

- [ ] **Step 3: Update `Contract` dataclass and add full universe**

Open `packages/ingest/universe.py`. Replace the `Contract` dataclass definition and add new fields:

```python
from typing import Literal

@dataclass(frozen=True)
class Contract:
    symbol: str
    name: str
    sector: str
    cftc_code: str
    yf_ticker: str
    point_value: float
    tick_size: float
    market_type: Literal["physical", "financial"] = "physical"
    report_type: Literal["disagg", "tff"] = "disagg"
```

Then append the financial contracts to the `UNIVERSE` list after the existing 23 physicals. Add at the end of the list (before the closing bracket):

```python
    # ── Additional physicals (DisAgg) ──────────────────────────────────────
    Contract("KE",    "KC HRW Wheat",      "grains",  "006642", "KE=F",  50.0,  0.25),
    Contract("BZ",    "Brent Crude",       "energy",  "096742", "BZ=F",  1000.0, 0.01),
    Contract("ALI",   "Aluminum",          "metals",  "191242", "ALI=F", 44000.0, 0.0001),
    Contract("LBS",   "Lumber",            "softs",   "058644", "LBS=F", 110000.0, 0.10),
    Contract("GF",    "Feeder Cattle",     "meats",   "061641", "GF=F",  50000.0, 0.025),

    # ── FX (TFF) ───────────────────────────────────────────────────────────
    Contract("EURUSD","Euro FX",           "fx",  "099741", "EURUSD=X", 125000.0, 0.00005, "financial", "tff"),
    Contract("GBPUSD","British Pound",     "fx",  "096742", "GBPUSD=X", 62500.0,  0.0001,  "financial", "tff"),
    Contract("JPYUSD","Japanese Yen",      "fx",  "097741", "JPYUSD=X", 12500000.0, 0.0000001, "financial", "tff"),
    Contract("AUDUSD","Australian Dollar", "fx",  "232741", "AUDUSD=X", 100000.0, 0.0001,  "financial", "tff"),
    Contract("CADUSD","Canadian Dollar",   "fx",  "090741", "CADUSD=X", 100000.0, 0.00005, "financial", "tff"),
    Contract("CHFUSD","Swiss Franc",       "fx",  "092741", "CHFUSD=X", 125000.0, 0.0001,  "financial", "tff"),
    Contract("NZDUSD","New Zealand Dollar","fx",  "112741", "NZDUSD=X", 100000.0, 0.0001,  "financial", "tff"),
    Contract("MXNUSD","Mexican Peso",      "fx",  "095741", "MXNUSD=X", 500000.0, 0.000005,"financial", "tff"),
    Contract("BRLUSD","Brazilian Real",    "fx",  "102741", "BRLUSD=X", 100000.0, 0.00005, "financial", "tff"),
    Contract("RUBUSD","Russian Ruble",     "fx",  "089741", "RUBUSD=X", 2500000.0,0.00001, "financial", "tff"),
    Contract("NOKUSD","Norwegian Krone",   "fx",  "184741", "NOKUSD=X", 2000000.0,0.00001, "financial", "tff"),
    Contract("SEKUSD","Swedish Krona",     "fx",  "185741", "SEKUSD=X", 2000000.0,0.00001, "financial", "tff"),

    # ── Equity Indices (TFF) ───────────────────────────────────────────────
    Contract("ES",    "S&P 500 E-mini",    "indices","13874A", "ES=F",  50.0,  0.25,  "financial", "tff"),
    Contract("NQ",    "Nasdaq-100 E-mini", "indices","209742", "NQ=F",  20.0,  0.25,  "financial", "tff"),
    Contract("YM",    "DJIA E-mini",       "indices","124603", "YM=F",  5.0,   1.0,   "financial", "tff"),
    Contract("RTY",   "Russell 2000",      "indices","239742", "RTY=F", 50.0,  0.10,  "financial", "tff"),
    Contract("NIY",   "Nikkei 225 (Yen)", "indices","240741", "NIY=F", 500.0, 5.0,   "financial", "tff"),
    Contract("MES",   "Micro S&P 500",    "indices","13874+", "MES=F", 5.0,   0.25,  "financial", "tff"),
    Contract("MNQ",   "Micro Nasdaq-100", "indices","209743", "MNQ=F", 2.0,   0.25,  "financial", "tff"),

    # ── Interest Rates (TFF) ──────────────────────────────────────────────
    Contract("ZB",    "30Y T-Bond",       "rates",  "020601", "ZB=F",  1000.0, 0.03125, "financial", "tff"),
    Contract("ZN",    "10Y T-Note",       "rates",  "043602", "ZN=F",  1000.0, 0.015625,"financial", "tff"),
    Contract("ZF",    "5Y T-Note",        "rates",  "044601", "ZF=F",  1000.0, 0.0078125,"financial","tff"),
    Contract("ZT",    "2Y T-Note",        "rates",  "042601", "ZT=F",  200000.0,0.0078125,"financial","tff"),
    Contract("FF",    "30D Fed Funds",    "rates",  "045601", "FF=F",  4167.0, 0.0025,  "financial", "tff"),
    Contract("SR3",   "SOFR 3M",          "rates",  "SR3   ", "SR3=F", 2500.0, 0.0025,  "financial", "tff"),
```

- [ ] **Step 4: Run tests — verify passes**

```bash
PYTHONPATH=packages .venv/bin/pytest tests/ingest/test_universe.py -v 2>&1 | tail -20
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/ingest/universe.py tests/ingest/test_universe.py
git commit -m "feat: expand universe to ~80 contracts with market_type + report_type"
```

---

## Task 3: TFF COT parser

**Files:**
- Create: `packages/ingest/tff_cot.py`
- Create: `tests/ingest/test_tff_cot.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/ingest/test_tff_cot.py
import pandas as pd
import pytest
from unittest.mock import patch, MagicMock
from ingest.tff_cot import _parse_tff_df, compute_net_columns
from ingest.universe import Contract

SAMPLE_ROW = {
    "As_of_Date_In_Form_YYMMDD": 260117,
    "Market_and_Exchange_Names": "EURO FX - CHICAGO MERCANTILE EXCHANGE",
    "CFTC_Contract_Market_Code": "099741",
    "Dealer_Positions_Long_All": 400000,
    "Dealer_Positions_Short_All": 450000,
    "Asset_Mgr_Positions_Long_All": 300000,
    "Asset_Mgr_Positions_Short_All": 200000,
    "Lev_Money_Positions_Long_All": 100000,
    "Lev_Money_Positions_Short_All": 280000,
    "Other_Rept_Positions_Long_All": 10000,
    "Other_Rept_Positions_Short_All": 8000,
    "NonRept_Positions_Long_All": 15000,
    "NonRept_Positions_Short_All": 20000,
    "Open_Interest_All": 825000,
}

def test_parse_renames_columns():
    df = pd.DataFrame([SAMPLE_ROW])
    result = _parse_tff_df(df)
    assert "dealer_long" in result.columns
    assert "am_long" in result.columns
    assert "lf_long" in result.columns
    assert "open_interest" in result.columns

def test_net_commercials_computed():
    df = pd.DataFrame([SAMPLE_ROW])
    parsed = _parse_tff_df(df)
    result = compute_net_columns(parsed)
    # dealer net = 400000 - 450000 = -50000
    assert result["net_commercials"].iloc[0] == -50000

def test_report_date_parsed():
    df = pd.DataFrame([SAMPLE_ROW])
    result = _parse_tff_df(df)
    assert pd.api.types.is_datetime64_any_dtype(result["report_date"])

def test_missing_columns_raises():
    df = pd.DataFrame([{"As_of_Date_In_Form_YYMMDD": 260117}])
    with pytest.raises(KeyError):
        _parse_tff_df(df)
```

- [ ] **Step 2: Run — verify fails**

```bash
PYTHONPATH=packages .venv/bin/pytest tests/ingest/test_tff_cot.py -v 2>&1 | tail -10
```

Expected: `ModuleNotFoundError: No module named 'ingest.tff_cot'`

- [ ] **Step 3: Implement `tff_cot.py`**

```python
# packages/ingest/tff_cot.py
"""TFF (Traders in Financial Futures) COT parser.

Same interface as cftc_cot.py but reads the TFF disaggregated ZIP archive.
TFF archive URL pattern:
  https://www.cftc.gov/files/dea/history/com_disagg_txt_{year}.zip
"""
from __future__ import annotations
import io
import zipfile
from pathlib import Path

import pandas as pd
import requests

_TFF_URL = "https://www.cftc.gov/files/dea/history/com_disagg_txt_{year}.zip"
_TFF_COLS = {
    "As_of_Date_In_Form_YYMMDD":       "report_date",
    "CFTC_Contract_Market_Code":        "cftc_code",
    "Open_Interest_All":                "open_interest",
    "Dealer_Positions_Long_All":        "dealer_long",
    "Dealer_Positions_Short_All":       "dealer_short",
    "Asset_Mgr_Positions_Long_All":     "am_long",
    "Asset_Mgr_Positions_Short_All":    "am_short",
    "Lev_Money_Positions_Long_All":     "lf_long",
    "Lev_Money_Positions_Short_All":    "lf_short",
    "Other_Rept_Positions_Long_All":    "other_long",
    "Other_Rept_Positions_Short_All":   "other_short",
    "NonRept_Positions_Long_All":       "nr_long",
    "NonRept_Positions_Short_All":      "nr_short",
}


def download_year(year: int, cache_dir: Path) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    out = cache_dir / f"tff_disagg_txt_{year}.zip"
    if out.exists() and out.stat().st_size > 0:
        return out
    url = _TFF_URL.format(year=year)
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    out.write_bytes(r.content)
    return out


def parse_year(zip_path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(zip_path) as zf:
        csv_name = next(n for n in zf.namelist() if n.endswith(".txt") or n.endswith(".csv"))
        raw = pd.read_csv(io.BytesIO(zf.read(csv_name)), low_memory=False)
    return _parse_tff_df(raw)


def _parse_tff_df(df: pd.DataFrame) -> pd.DataFrame:
    needed = list(_TFF_COLS.keys()) + ["CFTC_Contract_Market_Code"]
    missing = [c for c in needed if c not in df.columns]
    if missing:
        raise KeyError(f"TFF CSV missing columns: {missing}")

    keep = [c for c in _TFF_COLS if c in df.columns] + ["CFTC_Contract_Market_Code"]
    out = df[keep].copy().rename(columns=_TFF_COLS)

    for col in list(_TFF_COLS.values())[1:]:  # skip report_date
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")

    out["report_date"] = pd.to_datetime(
        out["report_date"].astype(str).str.zfill(6),
        format="%y%m%d",
        errors="coerce",
    )
    return out.dropna(subset=["report_date"]).reset_index(drop=True)


def compute_net_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["net_commercials"] = out["dealer_long"].fillna(0) - out["dealer_short"].fillna(0)
    out["net_lf"] = out["lf_long"].fillna(0) - out["lf_short"].fillna(0)
    out["net_am"] = out["am_long"].fillna(0) - out["am_short"].fillna(0)
    return out


def _match_contract(df: pd.DataFrame, cftc_code: str) -> pd.DataFrame:
    return df[df["cftc_code"].astype(str).str.strip() == cftc_code.strip()].copy()


def load_universe(
    years: range,
    universe,
    cache_dir: Path,
) -> pd.DataFrame:
    from ingest.universe import Contract
    tff_contracts = [c for c in universe if getattr(c, "report_type", "disagg") == "tff"]
    if not tff_contracts:
        return pd.DataFrame()

    frames: list[pd.DataFrame] = []
    for year in years:
        try:
            zip_path = download_year(year, cache_dir)
            year_df = parse_year(zip_path)
            year_df = compute_net_columns(year_df)
            for contract in tff_contracts:
                matched = _match_contract(year_df, contract.cftc_code)
                if not matched.empty:
                    matched = matched.copy()
                    matched["symbol"] = contract.symbol
                    frames.append(matched)
        except Exception:  # noqa: BLE001
            continue

    if not frames:
        return pd.DataFrame()

    full = pd.concat(frames, ignore_index=True)
    full = full.dropna(subset=["report_date"]).sort_values(["symbol", "report_date"])
    return full.reset_index(drop=True)
```

- [ ] **Step 4: Run tests — verify passes**

```bash
PYTHONPATH=packages .venv/bin/pytest tests/ingest/test_tff_cot.py -v 2>&1 | tail -15
```

Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/ingest/tff_cot.py tests/ingest/test_tff_cot.py
git commit -m "feat: add TFF COT parser for financial futures"
```

---

## Task 4: Extend zones — divergence signals + market_type gating

**Files:**
- Modify: `packages/ingest/zones.py`
- Create: `tests/ingest/test_zones_extended.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/ingest/test_zones_extended.py
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
        "lf_long": 100_000, "lf_short": 200_000,
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

def test_financial_zones_absent():
    df = _make_df(market_type="financial")
    result = annotate_zones(df)
    for z in ("A1", "A2", "A3", "A4", "A5"):
        assert z not in result.columns or result[z].sum() == 0

def test_comm_spec_divergence_physical():
    df = _make_df(market_type="physical")
    result = annotate_divergence(df)
    assert "comm_spec_divergence" in result.columns
    assert result["comm_spec_divergence"].dtype == int

def test_am_lf_divergence_financial():
    df = _make_df(market_type="financial")
    result = annotate_divergence(df)
    assert "am_lf_divergence" in result.columns
    assert result["am_lf_divergence"].dtype == int

def test_divergence_zero_when_aligned():
    df = _make_df(market_type="physical")
    # Make mm net move same direction as commercials
    df["mm_long"] = df["net_commercials"].clip(0) + 100_000
    df["mm_short"] = 50_000
    result = annotate_divergence(df)
    # With only 300 bars and aligned movement, divergence should be low
    assert result["comm_spec_divergence"].max() < 300
```

- [ ] **Step 2: Run — verify fails**

```bash
PYTHONPATH=packages .venv/bin/pytest tests/ingest/test_zones_extended.py -v 2>&1 | tail -10
```

Expected: `ImportError: cannot import name 'annotate_divergence'`

- [ ] **Step 3: Add `annotate_divergence` to `zones.py` and gate A1-A5 on market_type**

Add to the bottom of `packages/ingest/zones.py` (before `today_attention`):

```python
def annotate_divergence(df: pd.DataFrame) -> pd.DataFrame:
    """Add comm_spec_divergence (physical) or am_lf_divergence (financial).

    Value = consecutive weeks the two sides have moved in opposite directions.
    0 = not currently diverging.
    """
    out = df.copy()
    market_type = str(df["market_type"].iloc[0]) if "market_type" in df.columns else "physical"

    if market_type == "physical":
        side_a = out["net_commercials"]
        side_b = (out["mm_long"].fillna(0) - out["mm_short"].fillna(0))
        col = "comm_spec_divergence"
    else:
        side_a = out["am_long"].fillna(0) - out["am_short"].fillna(0)
        side_b = out["lf_long"].fillna(0) - out["lf_short"].fillna(0)
        col = "am_lf_divergence"

    delta_a = side_a.diff()
    delta_b = side_b.diff()
    # Diverging = a moves up while b moves down, or vice versa
    diverging = (delta_a * delta_b) < 0

    weeks = [0] * len(out)
    streak = 0
    for i, div in enumerate(diverging):
        if div:
            streak += 1
        else:
            streak = 0
        weeks[i] = streak

    out[col] = weeks
    # Ensure the other column exists as 0 for schema consistency
    other = "am_lf_divergence" if col == "comm_spec_divergence" else "comm_spec_divergence"
    if other not in out.columns:
        out[other] = 0
    return out
```

Also modify `annotate_zones` to gate A1–A5 on `market_type`. At the top of `annotate_zones`, add:

```python
def annotate_zones(df: pd.DataFrame) -> pd.DataFrame:
    market_type = str(df["market_type"].iloc[0]) if "market_type" in df.columns else "physical"
    if market_type == "financial":
        # Financial contracts: no A1-A5 zone engine (no commercial-hedger thesis)
        out = df.copy()
        for z in ("A1","A2","A3","A4","A5"):
            out[z] = False
            out[f"{z}_mag"] = 0.0
        out["n_zones"] = 0
        return out
    # ... existing physical zone logic unchanged below ...
```

- [ ] **Step 4: Run tests — verify passes**

```bash
PYTHONPATH=packages .venv/bin/pytest tests/ingest/test_zones_extended.py -v 2>&1 | tail -15
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/ingest/zones.py tests/ingest/test_zones_extended.py
git commit -m "feat: add divergence signals + gate A1-A5 on market_type"
```

---

## Task 5: AI shared client — DeepSeek-V4-Pro via HuggingFace

**Files:**
- Create: `packages/ingest/_ai.py`

- [ ] **Step 1: Create shared HuggingFace client module**

```python
# packages/ingest/_ai.py
"""Shared AI client — DeepSeek-V4-Pro via HuggingFace Inference API.

All AI analysis (news sentiment + market synthesis) uses DeepSeek-V4-Pro
through HuggingFace. Set HF_TOKEN env var (HuggingFace access token).
"""
from __future__ import annotations
import os
from huggingface_hub import InferenceClient

MODEL = "deepseek-ai/DeepSeek-V4-Pro"


def get_client() -> InferenceClient:
    token = os.environ.get("HF_TOKEN", "")
    if not token:
        raise EnvironmentError("HF_TOKEN not set — get one from huggingface.co/settings/tokens")
    return InferenceClient(model=MODEL, token=token)


def available() -> bool:
    """True if HF_TOKEN is present in environment."""
    return bool(os.environ.get("HF_TOKEN"))


def chat(messages: list[dict], temperature: float = 0) -> str:
    """Single chat completion. Returns the text content string."""
    client = get_client()
    resp = client.chat_completion(messages=messages, temperature=temperature, max_tokens=2048)
    return resp.choices[0].message.content or ""
```

- [ ] **Step 2: Verify import**

```bash
PYTHONPATH=packages .venv/bin/python -c "from ingest._ai import MODEL, available, chat; print('OK', MODEL)"
```

Expected: `OK deepseek-ai/DeepSeek-V4-Pro`

- [ ] **Step 3: Commit**

```bash
git add packages/ingest/_ai.py
git commit -m "feat: add HuggingFace AI client (DeepSeek-V4-Pro)"
```

---

## Task 6: News sentiment — DeepSeek-V4-Pro via HuggingFace

**Files:**
- Create: `packages/ingest/news_sentiment.py`
- Create: `tests/ingest/test_news_sentiment.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/ingest/test_news_sentiment.py
import pandas as pd
import pytest
from unittest.mock import patch, MagicMock
from ingest.news_sentiment import score_headlines, _build_batch_prompt, _parse_response

HEADLINES = pd.DataFrame({
    "title": [
        "OPEC cuts production by 1 million barrels",
        "US inventory build for third consecutive week",
        "Fed holds rates unchanged",
    ],
    "date": pd.to_datetime(["2026-05-01", "2026-05-02", "2026-05-03"]),
})

def test_build_prompt_contains_headlines():
    prompt = _build_batch_prompt(HEADLINES["title"].tolist())
    assert "OPEC" in prompt
    assert "inventory" in prompt

def test_parse_response_valid_json():
    mock_json = '[{"title":"OPEC cuts","sentiment":"positive","score":0.8,"reasoning":"supply cut bullish"},{"title":"inventory","sentiment":"negative","score":-0.5,"reasoning":"build bearish"},{"title":"Fed","sentiment":"neutral","score":0.0,"reasoning":"no change"}]'
    result = _parse_response(mock_json, 3)
    assert len(result) == 3
    assert result[0]["score"] == 0.8
    assert result[1]["sentiment"] == "negative"

def test_parse_response_malformed_returns_neutral():
    result = _parse_response("not json", 2)
    assert len(result) == 2
    assert all(r["sentiment"] == "neutral" for r in result)

def test_score_headlines_skips_already_scored():
    df = HEADLINES.copy()
    df["sentiment_score"] = [0.5, None, None]
    df["sentiment_label"] = ["positive", None, None]

    with patch("ingest.news_sentiment._call_api") as mock_api:
        mock_api.return_value = [
            {"score": -0.5, "sentiment": "negative", "reasoning": "bearish"},
            {"score": 0.0,  "sentiment": "neutral",  "reasoning": "neutral"},
        ]
        result = score_headlines(df.copy())

    # First row already scored — should not be re-scored
    assert result["sentiment_score"].iloc[0] == 0.5
    # Others should be filled in
    assert result["sentiment_score"].iloc[1] == -0.5
    mock_api.assert_called_once()  # called once for 2 unscored rows

def test_score_headlines_no_api_key_returns_null():
    df = HEADLINES.copy()
    with patch("ingest.news_sentiment.available", return_value=False):
        result = score_headlines(df.copy())
    assert result["sentiment_score"].isna().all()
```

- [ ] **Step 2: Run — verify fails**

```bash
PYTHONPATH=packages .venv/bin/pytest tests/ingest/test_news_sentiment.py -v 2>&1 | tail -10
```

Expected: `ModuleNotFoundError: No module named 'ingest.news_sentiment'`

- [ ] **Step 3: Implement `news_sentiment.py`**

```python
# packages/ingest/news_sentiment.py
"""News sentiment scoring via DeepSeek-V4-Pro (HuggingFace). Incremental — skips already-scored rows."""
from __future__ import annotations
import json
import math
import re
import pandas as pd
from ingest._ai import available, chat

BATCH_SIZE = 32
_SYSTEM = (
    "You are a financial news sentiment classifier. "
    "Given a list of financial news headlines, return a JSON array where each element has: "
    "title (string), sentiment ('positive'|'negative'|'neutral'), score (float -1 to 1), "
    "reasoning (one sentence, max 15 words). "
    "Return ONLY the JSON array, no other text."
)


def _build_batch_prompt(titles: list[str]) -> str:
    numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles))
    return f"Classify the sentiment of these {len(titles)} financial headlines:\n{numbered}"


def _parse_response(content: str, expected_count: int) -> list[dict]:
    try:
        match = re.search(r"\[.*\]", content, re.DOTALL)
        if not match:
            raise ValueError("no JSON array found")
        data = json.loads(match.group())
        if len(data) != expected_count:
            raise ValueError(f"expected {expected_count}, got {len(data)}")
        return data
    except Exception:
        return [{"sentiment": "neutral", "score": 0.0, "reasoning": ""} for _ in range(expected_count)]


def _call_api(titles: list[str]) -> list[dict]:
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user",   "content": _build_batch_prompt(titles)},
    ]
    raw = chat(messages, temperature=0)
    # Model may wrap array in {"results": [...]} — unwrap if needed
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            raw = json.dumps(next(iter(parsed.values())))
    except Exception:
        pass
    return _parse_response(raw, len(titles))


def score_headlines(df: pd.DataFrame) -> pd.DataFrame:
    """Add sentiment_score and sentiment_label columns. Skips already-scored rows."""
    if "sentiment_score" not in df.columns:
        df["sentiment_score"] = None
        df["sentiment_label"] = None

    if not available():
        return df

    unscored_mask = df["sentiment_score"].isna()
    if not unscored_mask.any():
        return df

    unscored = df[unscored_mask].copy()
    titles = unscored["title"].fillna("").tolist()
    n_batches = math.ceil(len(titles) / BATCH_SIZE)

    all_results: list[dict] = []
    for i in range(n_batches):
        batch = titles[i * BATCH_SIZE:(i + 1) * BATCH_SIZE]
        all_results.extend(_call_api(batch))

    idx = unscored.index
    df.loc[idx, "sentiment_score"] = [r["score"] for r in all_results]
    df.loc[idx, "sentiment_label"] = [r["sentiment"] for r in all_results]
    df.loc[idx, "sentiment_reason"] = [r.get("reasoning", "") for r in all_results]
    return df
```

- [ ] **Step 4: Run tests — verify passes**

```bash
PYTHONPATH=packages .venv/bin/pytest tests/ingest/test_news_sentiment.py -v 2>&1 | tail -15
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/ingest/news_sentiment.py tests/ingest/test_news_sentiment.py
git commit -m "feat: add DeepSeek-V4-Flash news sentiment scorer"
```

---

## Task 7: HMM regime detector

**Files:**
- Create: `packages/ingest/regime.py`
- Create: `tests/ingest/test_regime.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/ingest/test_regime.py
import numpy as np
import pandas as pd
import pytest
from ingest.regime import (
    build_feature_matrix,
    fit_hmm,
    label_states,
    annotate_regimes,
    MIN_BARS,
)

def _make_df(n=300, market_type="physical"):
    idx = pd.date_range("2020-01-01", periods=n, freq="W")
    return pd.DataFrame({
        "date": idx, "symbol": "CL", "market_type": market_type,
        "close": 70 + np.cumsum(np.random.randn(n) * 0.5),
        "net_commercials": np.sin(np.arange(n) / 20) * 50000,
        "lf_long": 100000, "lf_short": 200000 + np.sin(np.arange(n)/15) * 50000,
        "open_interest": 400000 + np.arange(n) * 200,
        "cot_index_comm": np.clip(np.arange(n) / 3.0, 0, 100),
    })

def test_build_feature_matrix_physical():
    df = _make_df(n=300, market_type="physical")
    X = build_feature_matrix(df)
    assert X.shape[1] == 4  # log_return, cot_net_change_pct, oi_change_pct, vol_ratio
    assert not np.isnan(X).all()

def test_build_feature_matrix_financial():
    df = _make_df(n=300, market_type="financial")
    X = build_feature_matrix(df)
    assert X.shape[1] == 4

def test_fit_hmm_returns_model():
    df = _make_df(n=300)
    X = build_feature_matrix(df)
    valid = ~np.isnan(X).any(axis=1)
    model = fit_hmm(X[valid])
    assert model is not None
    assert model.n_components == 4

def test_label_states_returns_known_labels():
    df = _make_df(n=300)
    X = build_feature_matrix(df)
    valid = ~np.isnan(X).any(axis=1)
    model = fit_hmm(X[valid])
    mapping = label_states(model, X[valid], df.iloc[valid.nonzero()[0]])
    assert set(mapping.values()).issubset({"trending","accumulation","distribution","ranging"})

def test_annotate_regimes_adds_columns():
    df = _make_df(n=300)
    result = annotate_regimes(df)
    assert "regime_label" in result.columns
    assert "regime_proba" in result.columns
    assert "regime_weeks" in result.columns

def test_thin_data_skipped():
    df = _make_df(n=MIN_BARS - 1)
    result = annotate_regimes(df)
    assert result["regime_label"].isna().all()
```

- [ ] **Step 2: Run — verify fails**

```bash
PYTHONPATH=packages .venv/bin/pytest tests/ingest/test_regime.py -v 2>&1 | tail -10
```

Expected: `ModuleNotFoundError: No module named 'ingest.regime'`

- [ ] **Step 3: Implement `regime.py`**

```python
# packages/ingest/regime.py
"""Per-symbol HMM regime detector using hmmlearn GaussianHMM."""
from __future__ import annotations
import pickle
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from hmmlearn import hmm

N_STATES = 4
MIN_BARS = 200
N_RESTARTS = 5
_LABELS = ("trending", "accumulation", "distribution", "ranging")

warnings.filterwarnings("ignore", category=RuntimeWarning)


def build_feature_matrix(df: pd.DataFrame) -> np.ndarray:
    """Stationary feature matrix. Same shape for physical and financial."""
    close = pd.to_numeric(df["close"], errors="coerce")
    log_ret = np.log(close / close.shift(1)).values

    if str(df["market_type"].iloc[0]) == "physical":
        net = df["net_commercials"].fillna(0)
    else:
        net = (df["lf_long"].fillna(0) - df["lf_short"].fillna(0))

    cot_net_chg = net.pct_change().replace([np.inf, -np.inf], np.nan).fillna(0).values
    oi = df["open_interest"].fillna(method="ffill")
    oi_chg = oi.pct_change().replace([np.inf, -np.inf], np.nan).fillna(0).values
    vol5 = pd.Series(log_ret).rolling(5).std().values
    vol20 = pd.Series(log_ret).rolling(20).std().values
    with np.errstate(invalid="ignore", divide="ignore"):
        vol_ratio = np.where(vol20 > 0, vol5 / vol20, 1.0)

    return np.column_stack([log_ret, cot_net_chg, oi_chg, vol_ratio])


def fit_hmm(X: np.ndarray) -> hmm.GaussianHMM:
    best_model, best_score = None, -np.inf
    for seed in range(N_RESTARTS):
        try:
            model = hmm.GaussianHMM(
                n_components=N_STATES, covariance_type="full",
                n_iter=1000, random_state=seed, verbose=False,
            )
            model.fit(X)
            score = model.score(X)
            if score > best_score:
                best_score, best_model = score, model
        except Exception:
            continue
    return best_model


def label_states(
    model: hmm.GaussianHMM,
    X: np.ndarray,
    df: pd.DataFrame,
) -> dict[int, str]:
    """Map HMM state indices to semantic labels by inspecting mean return + net direction."""
    states = model.predict(X)
    means = {}
    for s in range(N_STATES):
        mask = states == s
        if mask.sum() == 0:
            means[s] = (0.0, 0.0)
            continue
        mean_ret = float(X[mask, 0].mean())
        mean_cot = float(X[mask, 1].mean())
        means[s] = (mean_ret, mean_cot)

    sorted_by_ret = sorted(means, key=lambda s: means[s][0], reverse=True)

    mapping: dict[int, str] = {}
    for rank, state in enumerate(sorted_by_ret):
        ret, cot = means[state]
        if rank == 0:
            mapping[state] = "trending"
        elif cot > 0.01:
            mapping[state] = "accumulation"
        elif cot < -0.01:
            mapping[state] = "distribution"
        else:
            mapping[state] = "ranging"
    return mapping


def annotate_regimes(df: pd.DataFrame, model_cache_dir: Path | None = None) -> pd.DataFrame:
    out = df.copy()
    out["regime_label"] = None
    out["regime_proba"] = [None] * len(out)
    out["regime_weeks"] = 0

    if len(df) < MIN_BARS:
        return out

    X = build_feature_matrix(df)
    valid_mask = ~np.isnan(X).any(axis=1)
    if valid_mask.sum() < MIN_BARS:
        return out

    X_valid = X[valid_mask]
    model = fit_hmm(X_valid)
    if model is None:
        return out

    state_map = label_states(model, X_valid, df.iloc[valid_mask.nonzero()[0]])
    posteriors = model.predict_proba(X_valid)
    raw_states = model.predict(X_valid)
    labels = [state_map.get(s, "ranging") for s in raw_states]

    label_arr = np.full(len(df), None, dtype=object)
    proba_arr = np.full((len(df), N_STATES), np.nan)
    label_arr[valid_mask] = labels
    proba_arr[valid_mask] = posteriors

    weeks = np.zeros(len(df), dtype=int)
    streak = 0
    for i in range(len(label_arr)):
        if i == 0 or label_arr[i] != label_arr[i - 1]:
            streak = 1
        else:
            streak += 1
        weeks[i] = streak

    out["regime_label"] = label_arr
    out["regime_proba"] = [list(p) if not np.isnan(p).any() else None for p in proba_arr]
    out["regime_weeks"] = weeks

    if model_cache_dir is not None:
        model_cache_dir.mkdir(parents=True, exist_ok=True)
        sym = df["symbol"].iloc[0]
        with open(model_cache_dir / f"regime_{sym}.pkl", "wb") as f:
            pickle.dump({"model": model, "state_map": state_map}, f)

    return out


def annotate_all_regimes(
    annotated: dict[str, pd.DataFrame],
    model_cache_dir: Path | None = None,
) -> dict[str, pd.DataFrame]:
    result = {}
    for sym, df in annotated.items():
        result[sym] = annotate_regimes(df, model_cache_dir)
    return result
```

- [ ] **Step 4: Run tests — verify passes**

```bash
PYTHONPATH=packages .venv/bin/pytest tests/ingest/test_regime.py -v 2>&1 | tail -15
```

Expected: all 6 tests PASS. (May take ~15s due to HMM fitting.)

- [ ] **Step 5: Commit**

```bash
git add packages/ingest/regime.py tests/ingest/test_regime.py
git commit -m "feat: add per-symbol HMM regime detector (4 states)"
```

---

## Task 8: Retail sentiment scraper

**Files:**
- Create: `packages/ingest/retail_sentiment.py`
- Create: `tests/ingest/test_retail_sentiment.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/ingest/test_retail_sentiment.py
import pandas as pd
import pytest
from unittest.mock import patch
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
<table class="sentiment-table">
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
```

- [ ] **Step 2: Run — verify fails**

```bash
PYTHONPATH=packages .venv/bin/pytest tests/ingest/test_retail_sentiment.py -v 2>&1 | tail -10
```

Expected: `ModuleNotFoundError: No module named 'ingest.retail_sentiment'`

- [ ] **Step 3: Implement `retail_sentiment.py`**

```python
# packages/ingest/retail_sentiment.py
"""Retail sentiment from IG, Myfxbook, OANDA, Put/Call ratio, CFTC NR proxy."""
from __future__ import annotations
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

REQUIRED_COLS = ["symbol", "long_pct", "short_pct", "source", "timestamp"]

_IG_URL = "https://api.ig.com/gateway/deal/clientsentiment"
_IG_EPIC_MAP = {
    "EURUSD": "CS.D.EURUSD.TODAY.IP", "GBPUSD": "CS.D.GBPUSD.TODAY.IP",
    "JPYUSD": "CS.D.USDJPY.TODAY.IP", "AUDUSD": "CS.D.AUDUSD.TODAY.IP",
    "CADUSD": "CS.D.USDCAD.TODAY.IP", "ES":     "CS.D.SPXUSD.TODAY.IP",
    "NQ":     "CS.D.NQUSD.TODAY.IP",  "GC":     "CS.D.GOLD.TODAY.IP",
    "CL":     "CS.D.CRUDE.TODAY.IP",
}
_MYFXBOOK_URL = "https://www.myfxbook.com/community/outlook"
_CBOE_PC_URL  = "https://cdn.cboe.com/api/global/us_indices/daily_prices/SPX_P-C_Ratio.json"
_INDEX_SYMBOLS = {"ES", "NQ", "YM", "RTY", "MES", "MNQ", "NIY"}


def _now() -> datetime:
    return datetime.now(tz=timezone.utc).replace(tzinfo=None)


def _parse_ig_response(data: dict) -> pd.DataFrame:
    rows = []
    for item in data.get("instrumentSentimentList", []):
        name = item.get("instrumentName", "").replace("/", "").replace("-", "")
        rows.append({
            "symbol": name, "long_pct": float(item["longPositionPercentage"]),
            "short_pct": float(item["shortPositionPercentage"]),
            "source": "ig", "timestamp": _now(),
        })
    return pd.DataFrame(rows, columns=REQUIRED_COLS) if rows else pd.DataFrame(columns=REQUIRED_COLS)


def _parse_myfxbook_html(html: str) -> pd.DataFrame:
    from lxml import etree  # noqa: PLC0415
    rows = []
    try:
        parser = etree.HTMLParser()
        tree = etree.fromstring(html.encode(), parser)
        for row in tree.xpath("//table//tr"):
            cells = [c.text_content().strip() for c in row.xpath("td")]
            if len(cells) >= 3:
                sym = cells[0].replace("/", "").replace(" ", "").upper()
                try:
                    long_p = float(re.sub(r"[^\d.]", "", cells[1]))
                    short_p = float(re.sub(r"[^\d.]", "", cells[2]))
                    rows.append({"symbol": sym, "long_pct": long_p, "short_pct": short_p,
                                 "source": "myfxbook", "timestamp": _now()})
                except ValueError:
                    continue
    except Exception:
        pass
    return pd.DataFrame(rows, columns=REQUIRED_COLS) if rows else pd.DataFrame(columns=REQUIRED_COLS)


def _parse_oanda_response(data: dict, symbol: str) -> pd.DataFrame:
    d = data.get("data", {})
    long_p = float(d.get("long", {}).get("percent", 0)) * 100
    short_p = float(d.get("short", {}).get("percent", 0)) * 100
    return pd.DataFrame([{
        "symbol": symbol, "long_pct": long_p, "short_pct": short_p,
        "source": "oanda", "timestamp": _now(),
    }], columns=REQUIRED_COLS)


def _compute_nr_proxy(symbol: str, last_bar: pd.Series) -> dict:
    nr_long = float(last_bar.get("nr_long", 0) or 0)
    nr_short = float(last_bar.get("nr_short", 0) or 0)
    total = nr_long + nr_short
    long_p = (nr_long / total * 100) if total > 0 else 50.0
    return {"symbol": symbol, "long_pct": long_p, "short_pct": 100 - long_p,
            "source": "nr_proxy", "timestamp": _now()}


def _fetch_ig() -> pd.DataFrame:
    try:
        r = requests.get(_IG_URL, timeout=15)
        r.raise_for_status()
        return _parse_ig_response(r.json())
    except Exception:
        return pd.DataFrame(columns=REQUIRED_COLS)


def _fetch_myfxbook() -> pd.DataFrame:
    try:
        r = requests.get(_MYFXBOOK_URL, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        return _parse_myfxbook_html(r.text)
    except Exception:
        return pd.DataFrame(columns=REQUIRED_COLS)


def _fetch_put_call() -> pd.DataFrame:
    try:
        r = requests.get(_CBOE_PC_URL, timeout=15)
        r.raise_for_status()
        data = r.json()
        latest = data["data"][-1] if isinstance(data.get("data"), list) else {}
        pc = float(latest.get("ratio", 1.0))
        long_p = round(1 / (1 + pc) * 100, 1)
        rows = [{"symbol": sym, "long_pct": long_p, "short_pct": 100 - long_p,
                 "source": "put_call", "timestamp": _now()} for sym in _INDEX_SYMBOLS]
        return pd.DataFrame(rows, columns=REQUIRED_COLS)
    except Exception:
        return pd.DataFrame(columns=REQUIRED_COLS)


def merge_sources(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    avg = (df.groupby("symbol")[["long_pct", "short_pct"]]
             .mean()
             .rename(columns={"long_pct": "avg_long_pct", "short_pct": "avg_short_pct"})
             .reset_index())
    return avg


def load_retail_sentiment(
    annotated: dict[str, pd.DataFrame],
    cache_dir: Path,
) -> pd.DataFrame:
    frames = [_fetch_ig(), _fetch_myfxbook(), _fetch_put_call()]

    for sym, df in annotated.items():
        if df.empty:
            continue
        last = df.iloc[-1]
        if "nr_long" in last and "nr_short" in last:
            frames.append(pd.DataFrame([_compute_nr_proxy(sym, last)], columns=REQUIRED_COLS))

    all_df = pd.concat([f for f in frames if not f.empty], ignore_index=True)
    if not all_df.empty:
        cache_dir.mkdir(parents=True, exist_ok=True)
        all_df.to_parquet(cache_dir / "retail_sentiment.parquet", index=False)
    return all_df
```

- [ ] **Step 4: Run tests — verify passes**

```bash
PYTHONPATH=packages .venv/bin/pytest tests/ingest/test_retail_sentiment.py -v 2>&1 | tail -15
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/ingest/retail_sentiment.py tests/ingest/test_retail_sentiment.py
git commit -m "feat: add retail sentiment scraper (IG/Myfxbook/OANDA/PutCall/NR proxy)"
```

---

## Task 9: Market synthesis — DeepSeek-V4-Pro via HuggingFace

**Files:**
- Create: `packages/ingest/market_synthesis.py`
- Create: `tests/ingest/test_market_synthesis.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/ingest/test_market_synthesis.py
import pandas as pd
import pytest
from unittest.mock import patch
from ingest.market_synthesis import (
    _build_synthesis_prompt,
    _parse_synthesis_response,
    synthesize_market,
    REQUIRED_SYNTHESIS_KEYS,
)

SAMPLE_PAYLOAD = {
    "symbol": "CL", "market_type": "physical",
    "cot": {"comm_net": 182400, "comm_cot_index": 91.4,
            "spec_net": -94200, "spec_cot_index": 8.2, "divergence_weeks": 5},
    "regime": {"label": "accumulation", "weeks": 5, "confidence": 0.81},
    "open_interest": {"current": 412000, "change_pct": 6.1},
    "retail_sentiment": {"avg_short_pct": 71},
    "news_sentiment": {"score": 0.55, "top_headlines": ["OPEC cuts production"]},
}

VALID_RESPONSE = '{"summary":"Commercials at extreme.","confluence_score":0.82,"key_factors":["extreme commercial long"],"watch":"OPEC May 22"}'

def test_build_prompt_contains_symbol():
    prompt = _build_synthesis_prompt(SAMPLE_PAYLOAD)
    assert "CL" in prompt
    assert "182400" in prompt

def test_parse_valid_response():
    result = _parse_synthesis_response(VALID_RESPONSE)
    assert set(REQUIRED_SYNTHESIS_KEYS).issubset(result.keys())
    assert 0 <= result["confluence_score"] <= 1

def test_parse_malformed_returns_defaults():
    result = _parse_synthesis_response("not json at all")
    assert "summary" in result
    assert result["confluence_score"] == 0.0

def test_synthesize_no_api_key_returns_default():
    with patch("ingest.market_synthesis.available", return_value=False):
        result = synthesize_market(SAMPLE_PAYLOAD)
    assert result["confluence_score"] == 0.0
    assert "summary" in result

def test_synthesize_calls_pro_model():
    with patch("ingest.market_synthesis._call_api") as mock:
        mock.return_value = {"summary": "test", "confluence_score": 0.75,
                             "key_factors": ["x"], "watch": "y"}
        result = synthesize_market(SAMPLE_PAYLOAD)
    mock.assert_called_once()
    assert result["confluence_score"] == 0.75
```

- [ ] **Step 2: Run — verify fails**

```bash
PYTHONPATH=packages .venv/bin/pytest tests/ingest/test_market_synthesis.py -v 2>&1 | tail -10
```

Expected: `ModuleNotFoundError: No module named 'ingest.market_synthesis'`

- [ ] **Step 3: Implement `market_synthesis.py`**

```python
# packages/ingest/market_synthesis.py
"""Weekly per-market intelligence synthesis via DeepSeek-V4-Pro (HuggingFace)."""
from __future__ import annotations
import json
import re
from pathlib import Path
import pandas as pd
from ingest._ai import available, chat

REQUIRED_SYNTHESIS_KEYS = ("summary", "confluence_score", "key_factors", "watch")
_DEFAULT = {"summary": "", "confluence_score": 0.0, "key_factors": [], "watch": ""}
_SYSTEM = (
    "You are a quantitative market analyst. Given structured market data, "
    "produce a JSON object with: "
    "summary (2-3 sentences of factual market context, no predictions), "
    "confluence_score (float 0-1: how many intelligence layers align), "
    "key_factors (list of ≤5 strings naming active signals), "
    "watch (one upcoming event or threshold worth monitoring). "
    "Return ONLY the JSON object."
)


def _build_synthesis_prompt(payload: dict) -> str:
    return f"Synthesize market intelligence for {payload['symbol']} ({payload['market_type']}):\n{json.dumps(payload, indent=2)}"


def _parse_synthesis_response(content: str) -> dict:
    try:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            raise ValueError
        data = json.loads(match.group())
        data.setdefault("summary", "")
        data.setdefault("confluence_score", 0.0)
        data.setdefault("key_factors", [])
        data.setdefault("watch", "")
        data["confluence_score"] = float(max(0.0, min(1.0, data["confluence_score"])))
        return data
    except Exception:
        return dict(_DEFAULT)


def _call_api(payload: dict) -> dict:
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user",   "content": _build_synthesis_prompt(payload)},
    ]
    raw = chat(messages, temperature=0.1)
    return _parse_synthesis_response(raw)


def synthesize_market(payload: dict) -> dict:
    if not available():
        return dict(_DEFAULT)
    return _call_api(payload)


def _build_payload(symbol: str, df: pd.DataFrame, news_df: pd.DataFrame,
                   retail_df: pd.DataFrame) -> dict:
    from ingest.universe import UNIVERSE
    contract = next((c for c in UNIVERSE if c.symbol == symbol), None)
    market_type = getattr(contract, "market_type", "physical") if contract else "physical"
    last = df.iloc[-1]

    comm_net = float(last.get("net_commercials", 0) or 0)
    comm_idx = float(last.get("cot_index_comm", 50) or 50)
    div_col = "comm_spec_divergence" if market_type == "physical" else "am_lf_divergence"
    div_weeks = int(last.get(div_col, 0) or 0)
    spec_net = float((last.get("mm_long", 0) or 0) - (last.get("mm_short", 0) or 0))
    spec_idx = 100 - comm_idx  # rough inverse proxy

    oi_curr = float(last.get("open_interest", 0) or 0)
    oi_prev = float(df["open_interest"].iloc[-5] if len(df) > 5 else oi_curr)
    oi_chg = ((oi_curr - oi_prev) / oi_prev * 100) if oi_prev else 0

    regime_label = last.get("regime_label") or "unknown"
    regime_weeks = int(last.get("regime_weeks", 0) or 0)
    proba = last.get("regime_proba")
    confidence = float(max(proba)) if isinstance(proba, list) else 0.5

    sym_news = news_df[news_df["markets"].apply(
        lambda m: symbol in m if isinstance(m, list) else False
    )].tail(5) if not news_df.empty else pd.DataFrame()
    news_score = float(sym_news["sentiment_score"].mean()) if "sentiment_score" in sym_news.columns and not sym_news.empty else 0.0
    headlines = sym_news["title"].tolist()[:3] if not sym_news.empty else []

    sym_retail = retail_df[retail_df["symbol"] == symbol] if not retail_df.empty else pd.DataFrame()
    avg_short = float(sym_retail["short_pct"].mean()) if not sym_retail.empty else 50.0

    return {
        "symbol": symbol, "market_type": market_type,
        "cot": {"comm_net": comm_net, "comm_cot_index": comm_idx,
                "spec_net": spec_net, "spec_cot_index": spec_idx,
                "divergence_weeks": div_weeks},
        "regime": {"label": regime_label, "weeks": regime_weeks, "confidence": confidence},
        "open_interest": {"current": oi_curr, "change_pct": round(oi_chg, 2)},
        "retail_sentiment": {"avg_short_pct": round(avg_short, 1)},
        "news_sentiment": {"score": round(news_score, 3), "top_headlines": headlines},
    }


def synthesize_all(
    annotated: dict[str, pd.DataFrame],
    news_df: pd.DataFrame,
    retail_df: pd.DataFrame,
    cache_dir: Path,
) -> dict[str, dict]:
    results = {}
    for symbol, df in annotated.items():
        if df.empty:
            continue
        payload = _build_payload(symbol, df, news_df, retail_df)
        results[symbol] = synthesize_market(payload)

    if results and cache_dir:
        cache_dir.mkdir(parents=True, exist_ok=True)
        rows = [{"symbol": sym, **data} for sym, data in results.items()]
        pd.DataFrame(rows).to_parquet(cache_dir / "synthesis.parquet", index=False)

    return results
```

- [ ] **Step 4: Run tests — verify passes**

```bash
PYTHONPATH=packages .venv/bin/pytest tests/ingest/test_market_synthesis.py -v 2>&1 | tail -15
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/ingest/market_synthesis.py tests/ingest/test_market_synthesis.py
git commit -m "feat: add DeepSeek-V4-Pro market synthesis module"
```

---

## Task 10: Update `data.py` — extend Bundle + build_bundle routing

**Files:**
- Modify: `apps/api/src/data.py`

- [ ] **Step 1: Replace `data.py` with the extended version**

```python
# apps/api/src/data.py
"""Data loader for the API — extended for ~80 contracts + 6 intelligence layers."""
from __future__ import annotations
import sys
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGES_DIR = REPO_ROOT / "packages"
CACHE_DIR = REPO_ROOT / "research" / "data" / "cache"
if str(PACKAGES_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGES_DIR))

from ingest import cftc_cot, indicators, news, normalize, prices, zones  # noqa: E402
from ingest import tff_cot, regime as regime_mod, retail_sentiment, market_synthesis, news_sentiment  # noqa: E402  # noqa: E402
# _ai module loaded lazily inside news_sentiment + market_synthesis
from ingest.universe import UNIVERSE, sectors  # noqa: E402
from ingest.zones import annotate_divergence  # noqa: E402


@dataclass
class Bundle:
    annotated: dict[str, pd.DataFrame] = field(default_factory=dict)
    news_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    today_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    retail_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    synthesis: dict[str, dict] = field(default_factory=dict)
    loaded_at: pd.Timestamp | None = None


def build_bundle(years: range = range(2010, 2027)) -> Bundle:
    disagg_contracts = [c for c in UNIVERSE if getattr(c, "report_type", "disagg") == "disagg"]
    tff_contracts    = [c for c in UNIVERSE if getattr(c, "report_type", "disagg") == "tff"]

    # Load COT data per report type
    cot_disagg = cftc_cot.load_universe(years, disagg_contracts, CACHE_DIR)
    cot_tff    = tff_cot.load_universe(years, tff_contracts, CACHE_DIR)
    cot = pd.concat([c for c in [cot_disagg, cot_tff] if not c.empty], ignore_index=True)

    # Prices for all contracts
    px = prices.load_universe(UNIVERSE, CACHE_DIR, period="max")
    merged = normalize.join_cot_to_prices(px, cot)

    # Annotate per symbol
    annotated: dict[str, pd.DataFrame] = {}
    for sym, grp in merged.groupby("symbol"):
        if grp.empty or grp["net_commercials"].isna().all():
            continue
        contract = next((c for c in UNIVERSE if c.symbol == sym), None)
        market_type = getattr(contract, "market_type", "physical") if contract else "physical"
        g = grp.reset_index(drop=True).copy()
        g["market_type"] = market_type
        g = indicators.add_all_indicators(g)
        g = zones.annotate_zones(g)
        g = annotate_divergence(g)
        annotated[sym] = g

    annotated = zones.add_sector_zone(annotated, UNIVERSE)
    annotated = regime_mod.annotate_all_regimes(annotated, CACHE_DIR)

    news_df = news.load_all_news(UNIVERSE, cache_dir=CACHE_DIR)
    news_df = news_sentiment.score_headlines(news_df)

    retail_df = retail_sentiment.load_retail_sentiment(annotated, CACHE_DIR)
    synthesis = market_synthesis.synthesize_all(annotated, news_df, retail_df, CACHE_DIR)

    today_df = zones.today_attention(annotated)

    return Bundle(
        annotated=annotated,
        news_df=news_df,
        today_df=today_df,
        retail_df=retail_df,
        synthesis=synthesis,
        loaded_at=pd.Timestamp.utcnow(),
    )


def sector_of(symbol: str) -> str | None:
    for sec, contracts in sectors().items():
        if any(c.symbol == symbol for c in contracts):
            return sec
    return None
```

- [ ] **Step 2: Verify import**

```bash
cd /Users/praveen/Projects/cot-dashboard && PYTHONPATH=packages .venv/bin/python -c "
from apps.api.src.data import Bundle, build_bundle, sector_of
print('data.py import OK')
" 2>&1
```

Expected: `data.py import OK`

- [ ] **Step 3: Commit**

```bash
git add apps/api/src/data.py
git commit -m "feat: extend Bundle + build_bundle to route TFF/DisAgg + all intel layers"
```

---

## Task 11: Update schemas + new API endpoints

**Files:**
- Modify: `apps/api/src/schemas.py`
- Modify: `apps/api/src/main.py`

- [ ] **Step 1: Add new fields to `schemas.py`**

In `schemas.py`, update `BarRow` and add new response models:

```python
# Add to BarRow (after existing fields):
    open_interest: float | None = None
    nr_long: float | None = None
    nr_short: float | None = None
    dealer_long: float | None = None
    dealer_short: float | None = None
    am_long: float | None = None
    am_short: float | None = None
    lf_long: float | None = None
    lf_short: float | None = None
    comm_spec_divergence: int = 0
    am_lf_divergence: int = 0
    regime_label: str | None = None
    regime_proba: list[float] | None = None
    regime_weeks: int = 0
    confluence_score: float | None = None
```

Add to `NewsItem`:
```python
    sentiment_score: float | None = None
    sentiment_label: str | None = None
    sentiment_reason: str | None = None
```

Add new models at the end of the file:
```python
class RetailSentimentItem(BaseModel):
    symbol: str
    long_pct: float
    short_pct: float
    source: str
    timestamp: datetime

class RetailSentimentResponse(BaseModel):
    symbol: str
    items: list[RetailSentimentItem]
    avg_long_pct: float
    avg_short_pct: float

class RegimeResponse(BaseModel):
    symbol: str
    market_type: str
    current_regime: str
    regime_weeks: int
    proba: list[float]
    next_bar_proba: list[float]
    transition_matrix: list[list[float]]
    state_names: list[str]

class SynthesisResponse(BaseModel):
    symbol: str
    summary: str
    confluence_score: float
    key_factors: list[str]
    watch: str
    generated_at: datetime | None = None
```

- [ ] **Step 2: Add new endpoints to `main.py`**

Import new schemas at the top of `main.py`:
```python
from .schemas import (
    ...,  # existing
    RetailSentimentItem, RetailSentimentResponse,
    RegimeResponse, SynthesisResponse,
)
```

Add endpoints before the final `if __name__` block:

```python
@app.get("/retail-sentiment/{symbol}", response_model=RetailSentimentResponse)
def retail_sentiment_endpoint(symbol: str) -> RetailSentimentResponse:
    b = _bundle()
    if b.retail_df.empty:
        return RetailSentimentResponse(symbol=symbol, items=[], avg_long_pct=50, avg_short_pct=50)
    sym_df = b.retail_df[b.retail_df["symbol"] == symbol]
    if sym_df.empty:
        return RetailSentimentResponse(symbol=symbol, items=[], avg_long_pct=50, avg_short_pct=50)
    items = [RetailSentimentItem(**row) for row in sym_df.to_dict("records")]
    avg_long = float(sym_df["long_pct"].mean())
    avg_short = float(sym_df["short_pct"].mean())
    return RetailSentimentResponse(symbol=symbol, items=items,
                                   avg_long_pct=avg_long, avg_short_pct=avg_short)


@app.get("/regime/{symbol}", response_model=RegimeResponse)
def regime_endpoint(symbol: str) -> RegimeResponse:
    from ingest.universe import UNIVERSE
    b = _bundle()
    if symbol not in b.annotated:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not found")
    df = b.annotated[symbol]
    last = df.iloc[-1]
    contract = next((c for c in UNIVERSE if c.symbol == symbol), None)
    market_type = getattr(contract, "market_type", "physical") if contract else "physical"
    proba = last.get("regime_proba") or [0.25, 0.25, 0.25, 0.25]
    import numpy as np
    import pickle, os
    from pathlib import Path
    state_names = ["trending", "accumulation", "distribution", "ranging"]
    # Try to load transition matrix from cached model
    cache_path = Path(__file__).resolve().parents[3] / "research" / "data" / "cache" / f"regime_{symbol}.pkl"
    tm = [[0.25]*4]*4
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
```

- [ ] **Step 3: Smoke-test new endpoints**

```bash
# API should still be running on :8000 from earlier
curl -sS http://127.0.0.1:8000/healthz
curl -sS http://127.0.0.1:8000/retail-sentiment/CL | python3 -c "import sys,json; d=json.load(sys.stdin); print('retail OK:', d['symbol'])"
curl -sS http://127.0.0.1:8000/regime/CL | python3 -c "import sys,json; d=json.load(sys.stdin); print('regime OK:', d['current_regime'])"
```

Expected: each prints an OK line.

- [ ] **Step 4: Commit**

```bash
git add apps/api/src/schemas.py apps/api/src/main.py
git commit -m "feat: add retail-sentiment, regime, synthesis API endpoints"
```

---

## Task 12: Sync TypeScript types + API client

**Files:**
- Modify: `apps/web/src/lib/api/types.ts`
- Modify: `apps/web/src/lib/api/client.ts`

- [ ] **Step 1: Add new fields to `types.ts`**

In the `BarRow` interface, add after `n_zones`:
```typescript
  open_interest?: number | null;
  nr_long?: number | null;
  nr_short?: number | null;
  dealer_long?: number | null;
  dealer_short?: number | null;
  am_long?: number | null;
  am_short?: number | null;
  lf_long?: number | null;
  lf_short?: number | null;
  comm_spec_divergence: number;
  am_lf_divergence: number;
  regime_label?: string | null;
  regime_proba?: number[] | null;
  regime_weeks: number;
  confluence_score?: number | null;
```

In `NewsItem`, add:
```typescript
  sentiment_score?: number | null;
  sentiment_label?: string | null;
  sentiment_reason?: string | null;
```

Add new interfaces at the bottom of `types.ts`:
```typescript
export interface RetailSentimentItem {
  symbol: string;
  long_pct: number;
  short_pct: number;
  source: string;
  timestamp: string;
}

export interface RetailSentimentResponse {
  symbol: string;
  items: RetailSentimentItem[];
  avg_long_pct: number;
  avg_short_pct: number;
}

export interface RegimeResponse {
  symbol: string;
  market_type: string;
  current_regime: string;
  regime_weeks: number;
  proba: number[];
  next_bar_proba: number[];
  transition_matrix: number[][];
  state_names: string[];
}

export interface SynthesisResponse {
  symbol: string;
  summary: string;
  confluence_score: number;
  key_factors: string[];
  watch: string;
  generated_at?: string | null;
}
```

- [ ] **Step 2: Add methods to `client.ts`**

Add to the `api` object:
```typescript
  retailSentiment: (symbol: string) =>
    get<RetailSentimentResponse>(`/retail-sentiment/${symbol}`),
  regime: (symbol: string) =>
    get<RegimeResponse>(`/regime/${symbol}`),
  synthesis: (symbol: string) =>
    get<SynthesisResponse>(`/synthesis/${symbol}`),
```

Update the import at the top of `client.ts`:
```typescript
import type {
  ArticleResponse, ContractMeta, DivergenceRow, HeatmapResponse,
  MarketDetail, NewsResponse, StatusResponse, TodayRow,
  RetailSentimentResponse, RegimeResponse, SynthesisResponse,
} from './types';
```

- [ ] **Step 3: Run svelte-check**

```bash
cd /Users/praveen/Projects/cot-dashboard/apps/web && npx svelte-check --threshold error 2>&1 | tail -5
```

Expected: `svelte-check found 0 errors and 0 warnings`

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/lib/api/types.ts apps/web/src/lib/api/client.ts
git commit -m "feat: sync TS types + client for new API endpoints"
```

---

## Task 13: Full backend smoke test

**Files:** none — verification only

- [ ] **Step 1: Run full test suite**

```bash
cd /Users/praveen/Projects/cot-dashboard && PYTHONPATH=packages .venv/bin/pytest tests/ -v --tb=short 2>&1 | tail -30
```

Expected: all tests pass. Zero failures.

- [ ] **Step 2: Restart API and verify all endpoints**

```bash
pkill -f "uvicorn src.main:app" 2>/dev/null; sleep 2
nohup .venv/bin/uvicorn src.main:app --host 127.0.0.1 --port 8000 --app-dir apps/api --log-level warning > /tmp/api-smoke.log 2>&1 &
sleep 20
curl -sS http://127.0.0.1:8000/status | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'OK: {d[\"n_markets\"]} markets, {d[\"n_news\"]} news')"
curl -sS http://127.0.0.1:8000/today | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'/today: {len(d)} markets returned')"
curl -sS http://127.0.0.1:8000/regime/CL | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'/regime: {d[\"current_regime\"]}')"
curl -sS http://127.0.0.1:8000/retail-sentiment/CL | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'/retail-sentiment: avg_short={d[\"avg_short_pct\"]}')"
```

Expected:
```
OK: 80 markets, NNN news
/today: 80 markets returned
/regime: accumulation  (or any valid label)
/retail-sentiment: avg_short=NN.N
```

- [ ] **Step 3: Tag Phase A complete**

```bash
git tag phase-a-complete
```

---

## Self-Review Checklist

- [x] **Spec §3 (universe)** → Task 2 adds all ~80 contracts with market_type/report_type
- [x] **Spec §3.1 (tff_cot.py)** → Task 3 implements full TFF parser
- [x] **Spec §3.7 (zones divergence)** → Task 4 adds comm_spec_divergence + am_lf_divergence + market_type gate
- [x] **Spec §5.4 (DeepSeek Flash sentiment)** → Task 6 implements with batch scoring + incremental skip
- [x] **Spec §5.5 (HMM regime)** → Task 7 with MIN_BARS guard, 5 restarts, Viterbi
- [x] **Spec §5.6 (synthesis DeepSeek Pro)** → Task 9
- [x] **Spec §5.7 (retail sentiment)** → Task 8 all 5 sources
- [x] **Spec §4.2 (BarRow new fields)** → Task 11 schemas.py
- [x] **Spec §6.2 (new endpoints)** → Task 11 main.py
- [x] **Spec §6.3 (TS types)** → Task 12
- [x] **Spec §3.3 (news taxonomy extension)** → ⚠️ **GAP — add Task below**

**Gap fix — Task 3b: Extend news taxonomy for financial contracts**

```python
# packages/ingest/news_taxonomy.py — append to KEYWORD_MAP:
"ES":     {"s&p", "spx", "s&p500", "sp500", "equity", "stock market", "wall street"},
"NQ":     {"nasdaq", "tech stocks", "faang", "mega cap"},
"YM":     {"dow", "djia", "blue chip"},
"RTY":    {"russell", "small cap", "iwm"},
"ZB":     {"treasury", "t-bond", "30 year", "long bond", "yield curve"},
"ZN":     {"10-year", "10yr", "treasury note", "10y yield"},
"ZF":     {"5-year", "5yr"},
"ZT":     {"2-year", "2yr", "short end"},
"FF":     {"fed funds", "federal reserve", "fomc", "rate hike", "rate cut"},
"SR3":    {"sofr", "secured overnight"},
"EURUSD": {"euro", "eur", "ecb", "eurozone", "draghi", "lagarde"},
"GBPUSD": {"sterling", "pound", "gbp", "boe", "bank of england", "brexit"},
"JPYUSD": {"yen", "jpy", "boj", "bank of japan"},
"AUDUSD": {"aussie", "aud", "rba", "australia"},
"CADUSD": {"loonie", "cad", "bank of canada", "boc"},
```

Add this to `news_taxonomy.py` inside the `KEYWORD_MAP` dict, then run:
```bash
PYTHONPATH=packages .venv/bin/pytest tests/ -v --tb=short 2>&1 | tail -5
git add packages/ingest/news_taxonomy.py
git commit -m "feat: extend news taxonomy for FX, indices, rate contracts"
```
