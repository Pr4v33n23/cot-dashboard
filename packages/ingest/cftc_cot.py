"""CFTC Commitments of Traders — disaggregated futures-only ingest.

Data source (free): https://www.cftc.gov/MarketReports/CommitmentsofTraders
History archives:
    https://www.cftc.gov/files/dea/history/fut_disagg_txt_YYYY.zip

We use the Disaggregated futures-only report (not Legacy) because layer L3
(component imbalance — producer shorts at 3y low AND consumer longs at 3y high)
needs the Producer/Merchant long/short split.

Per PLAN §1.3: CFTC releases Tuesday snapshot on Friday 15:30 CT. We snapshot
weekly and cache the full year ZIP locally so backtest iterations stay offline.

Functions:
- `download_year(year, cache_dir)` -> Path to local ZIP
- `parse_year(zip_path)`           -> DataFrame of all rows for that year
- `load_universe(years, universe)` -> Tidy long DataFrame indexed by
  (report_date, symbol) with the columns needed by indicators + signals.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests

from .universe import Contract

ARCHIVE_URL = "https://www.cftc.gov/files/dea/history/fut_disagg_txt_{year}.zip"

# Columns we keep from the raw CFTC file. The CFTC schema is wide (~191 cols);
# the names below match the disaggregated futures-only header exactly.
#
# Date-column note: CFTC renamed the report-date column from
# `Report_Date_as_MM_DD_YYYY` to `Report_Date_as_YYYY-MM-DD` in 2015. The
# `As_of_Date_In_Form_YYMMDD` column is the same value in YYMMDD integer form
# and has the same name across the entire 2010+ archive — that's what we use.
RAW_COLUMNS = [
    "Market_and_Exchange_Names",
    "As_of_Date_In_Form_YYMMDD",
    "CFTC_Contract_Market_Code",
    "Open_Interest_All",
    "Prod_Merc_Positions_Long_All",
    "Prod_Merc_Positions_Short_All",
    "Swap_Positions_Long_All",
    "Swap__Positions_Short_All",
    "M_Money_Positions_Long_All",
    "M_Money_Positions_Short_All",
    "Other_Rept_Positions_Long_All",
    "Other_Rept_Positions_Short_All",
    "NonRept_Positions_Long_All",
    "NonRept_Positions_Short_All",
]


def download_year(year: int, cache_dir: Path) -> Path:
    """Download the disaggregated-futures-only ZIP for `year`. Idempotent."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    out = cache_dir / f"fut_disagg_txt_{year}.zip"
    if out.exists() and out.stat().st_size > 0:
        return out
    url = ARCHIVE_URL.format(year=year)
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    out.write_bytes(resp.content)
    return out


def parse_year(zip_path: Path) -> pd.DataFrame:
    """Read the ZIP's inner text file and return a DataFrame of RAW_COLUMNS."""
    with zipfile.ZipFile(zip_path) as zf:
        # The archive contains a single .txt with header row; name varies.
        inner = next(n for n in zf.namelist() if n.lower().endswith(".txt"))
        with zf.open(inner) as fh:
            raw = fh.read()
    df = pd.read_csv(io.BytesIO(raw), low_memory=False)
    keep = [c for c in RAW_COLUMNS if c in df.columns]
    df = df[keep].copy()
    # YYMMDD integer → datetime. Stable across 2010+ archive.
    df["As_of_Date_In_Form_YYMMDD"] = pd.to_datetime(
        df["As_of_Date_In_Form_YYMMDD"].astype("Int64").astype(str).str.zfill(6),
        format="%y%m%d",
        errors="coerce",
    )
    return df


def _match_contract(df: pd.DataFrame, contract: Contract) -> pd.DataFrame:
    """Filter raw CFTC rows to a single contract.

    Match strategy: prefer `CFTC_Contract_Market_Code` equality (stable across
    schema revisions); fall back to `Market_and_Exchange_Names` substring.
    """
    code_col = "CFTC_Contract_Market_Code"
    name_col = "Market_and_Exchange_Names"
    if code_col in df.columns:
        codes = df[code_col].astype(str).str.strip().str.upper()
        hit = df[codes == contract.cftc_code.upper()]
        if not hit.empty:
            return hit
    if name_col in df.columns:
        return df[df[name_col].str.upper().str.contains(contract.cftc_name.upper(), na=False)]
    return df.iloc[0:0]


def load_universe(
    years: Iterable[int],
    universe: Iterable[Contract],
    cache_dir: Path,
) -> pd.DataFrame:
    """Return a tidy DataFrame: one row per (report_date, symbol).

    Columns:
        report_date, symbol, open_interest,
        pm_long, pm_short, sd_long, sd_short,
        mm_long, mm_short, or_long, or_short,
        nr_long, nr_short,
        net_commercials  (= pm_long + sd_long - pm_short - sd_short)
    """
    frames: list[pd.DataFrame] = []
    for year in years:
        zip_path = download_year(year, cache_dir)
        year_df = parse_year(zip_path)
        for contract in universe:
            sub = _match_contract(year_df, contract).copy()
            if sub.empty:
                continue
            sub["symbol"] = contract.symbol
            frames.append(sub)
    if not frames:
        return pd.DataFrame()
    full = pd.concat(frames, ignore_index=True)

    rename = {
        "As_of_Date_In_Form_YYMMDD": "report_date",
        "Open_Interest_All": "open_interest",
        "Prod_Merc_Positions_Long_All": "pm_long",
        "Prod_Merc_Positions_Short_All": "pm_short",
        "Swap_Positions_Long_All": "sd_long",
        "Swap__Positions_Short_All": "sd_short",
        "M_Money_Positions_Long_All": "mm_long",
        "M_Money_Positions_Short_All": "mm_short",
        "Other_Rept_Positions_Long_All": "or_long",
        "Other_Rept_Positions_Short_All": "or_short",
        "NonRept_Positions_Long_All": "nr_long",
        "NonRept_Positions_Short_All": "nr_short",
    }
    full = full.rename(columns=rename)
    numeric_cols = [v for v in rename.values() if v != "report_date"]
    for c in numeric_cols:
        if c in full.columns:
            full[c] = pd.to_numeric(full[c], errors="coerce")

    full["net_commercials"] = (
        full["pm_long"].fillna(0)
        + full["sd_long"].fillna(0)
        - full["pm_short"].fillna(0)
        - full["sd_short"].fillna(0)
    )

    full = full.dropna(subset=["report_date"]).sort_values(["symbol", "report_date"])
    return full.reset_index(drop=True)
