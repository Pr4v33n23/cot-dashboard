"""TFF (Traders in Financial Futures) COT parser.

Same interface as cftc_cot.py but reads the TFF disaggregated ZIP archive.
TFF archive URL pattern:
  https://www.cftc.gov/files/dea/history/fut_fin_txt_{year}.zip
"""
from __future__ import annotations
import io
import zipfile
from pathlib import Path

import pandas as pd
import requests

_TFF_URL = "https://www.cftc.gov/files/dea/history/fut_fin_txt_{year}.zip"
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
    needed = list(_TFF_COLS.keys())
    missing = [c for c in needed if c not in df.columns]
    if missing:
        raise KeyError(f"TFF CSV missing columns: {missing}")

    keep = [c for c in _TFF_COLS if c in df.columns]
    out = df[keep].copy().rename(columns=_TFF_COLS)

    for col in list(_TFF_COLS.values())[2:]:  # skip report_date and cftc_code
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
