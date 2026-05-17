"""CME + ICE physical futures universe for WILLIAMS_COT_SWING_v1.

Each contract carries:
- `symbol`         : Internal short symbol (CME root where possible).
- `name`           : Human-readable name.
- `sector`         : Correlation cluster (per PLAN §1.4 — max 2% risk per cluster).
- `cftc_name`      : Substring match against the CFTC "Market_and_Exchange_Names"
                     column in the disaggregated futures-only report.
- `cftc_code`      : CFTC contract market code (6-char). Primary match key.
- `yf_ticker`      : Continuous front-month symbol on Yahoo Finance (e.g. "CL=F").
- `point_value`    : USD per 1.00 price move per contract — used for P&L conversion
                     in the backtest. Sourced from CME / ICE contract specs.
- `tick_size`      : Minimum price increment.

## Phase 0 universe scope — physicals only

The CFTC disaggregated futures-only report uses commercial/non-commercial
categories that map cleanly onto physical hedgers (producers, end-users) but
NOT onto financial futures (equity indices, rates, FX). Financials live in the
separate "Traders in Financial Futures" (TFF) report with different categories
(Dealer Intermediary, Asset Manager, Leveraged Funds).

Williams/Briese/Upperman's commercial-hedger-extreme framework was designed for
physical commodities where commercial = real producer or end-user with physical
exposure. Applying it to TFF "dealers" would be conceptually unsound.

Decision: Phase 0 restricts to 23 physical contracts (grains, energy, metals,
softs, meats). TFF support + a separate dealer-positioning strategy variant
can be added in a later phase if Phase 0 passes.

## Data source notes

- CFTC: free disaggregated futures-only ZIPs from cftc.gov (one per year).
- Prices: Yahoo Finance via the `yfinance` package (PLAN.md §1 originally named
  Stooq, but Stooq added a per-symbol captcha + apikey requirement in 2025).
  Switched to yfinance to preserve the §0.3 capital stop (still $0 spend).
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
    cftc_name: str = ""


# Curated universe. CFTC codes verified against disaggregated futures-only
# archive for 2024. Yahoo Finance tickers verified to return ≥ 10 years of
# daily bars as of 2026-05-16.
UNIVERSE: tuple[Contract, ...] = (
    # Grains — CBT
    Contract("ZC",  "Corn",                "grains",  "002602", "ZC=F", 50.0,   0.25, cftc_name="CORN"),
    Contract("ZW",  "Wheat SRW",           "grains",  "001602", "ZW=F", 50.0,   0.25, cftc_name="WHEAT-SRW"),
    Contract("ZS",  "Soybeans",            "grains",  "005602", "ZS=F", 50.0,   0.25, cftc_name="SOYBEANS"),
    Contract("ZM",  "Soybean Meal",        "grains",  "026603", "ZM=F", 100.0,  0.10, cftc_name="SOYBEAN MEAL"),
    Contract("ZL",  "Soybean Oil",         "grains",  "007601", "ZL=F", 600.0,  0.01, cftc_name="SOYBEAN OIL"),
    Contract("ZO",  "Oats",                "grains",  "004603", "ZO=F", 50.0,   0.25, cftc_name="OATS"),
    Contract("ZR",  "Rough Rice",          "grains",  "039601", "ZR=F", 2000.0, 0.005, cftc_name="ROUGH RICE"),
    # Energy — NYMEX
    Contract("CL",  "Crude Oil WTI",       "energy",  "067651", "CL=F", 1000.0,  0.01,   cftc_name="WTI-PHYSICAL"),
    Contract("NG",  "Natural Gas",         "energy",  "023651", "NG=F", 10000.0, 0.001,  cftc_name="NAT GAS NYME"),
    Contract("HO",  "Heating Oil",         "energy",  "022651", "HO=F", 42000.0, 0.0001, cftc_name="NY HARBOR ULSD"),
    Contract("RB",  "RBOB Gasoline",       "energy",  "111659", "RB=F", 42000.0, 0.0001, cftc_name="GASOLINE RBOB"),
    # Metals — COMEX / NYMEX
    Contract("GC",  "Gold",                "metals",  "088691", "GC=F", 100.0,  0.10,   cftc_name="GOLD"),
    Contract("SI",  "Silver",              "metals",  "084691", "SI=F", 5000.0, 0.005,  cftc_name="SILVER"),
    Contract("HG",  "Copper",              "metals",  "085692", "HG=F", 25000.0, 0.0005, cftc_name="COPPER- #1"),
    Contract("PL",  "Platinum",            "metals",  "076651", "PL=F", 50.0,   0.10,   cftc_name="PLATINUM"),
    # Softs — ICE Futures U.S.
    Contract("CC",  "Cocoa",               "softs",   "073732", "CC=F", 10.0,   1.0,   cftc_name="COCOA"),
    Contract("KC",  "Coffee C",            "softs",   "083731", "KC=F", 375.0,  0.05,  cftc_name="COFFEE C"),
    Contract("CT",  "Cotton #2",           "softs",   "033661", "CT=F", 500.0,  0.01,  cftc_name="COTTON NO. 2"),
    Contract("SB",  "Sugar #11",           "softs",   "080732", "SB=F", 1120.0, 0.01,  cftc_name="SUGAR NO. 11"),
    Contract("OJ",  "Orange Juice",        "softs",   "040701", "OJ=F", 150.0,  0.05,  cftc_name="FRZN CONCENTRATED ORANGE"),
    # Meats — CME
    Contract("LE",  "Live Cattle",         "meats",   "057642", "LE=F", 400.0,  0.025, cftc_name="LIVE CATTLE"),
    Contract("HE",  "Lean Hogs",           "meats",   "054642", "HE=F", 400.0,  0.025, cftc_name="LEAN HOGS"),
    Contract("GF",  "Feeder Cattle",       "meats",   "061641", "GF=F", 500.0,  0.025, cftc_name="FEEDER CATTLE"),

    # ── Additional physicals (DisAgg) ─────────────────────────────────────
    Contract("KE",    "KC HRW Wheat",       "grains",  "006642", "KE=F",    50.0,    0.25),
    Contract("BZ",    "Brent Crude",        "energy",  "096742", "BZ=F",    1000.0,  0.01),
    Contract("ALI",   "Aluminum",           "metals",  "191242", "ALI=F",   44000.0, 0.0001),
    Contract("LBS",   "Lumber",             "softs",   "058644", "LBS=F",   110000.0, 0.10),

    # ── FX (TFF) ──────────────────────────────────────────────────────────
    Contract("EURUSD","Euro FX",            "fx",      "099741", "EURUSD=X", 125000.0,   0.00005,    "financial", "tff"),
    Contract("GBPUSD","British Pound",      "fx",      "096742", "GBPUSD=X", 62500.0,    0.0001,     "financial", "tff"),
    Contract("JPYUSD","Japanese Yen",       "fx",      "097741", "JPYUSD=X", 12500000.0, 0.0000001,  "financial", "tff"),
    Contract("AUDUSD","Australian Dollar",  "fx",      "232741", "AUDUSD=X", 100000.0,   0.0001,     "financial", "tff"),
    Contract("CADUSD","Canadian Dollar",    "fx",      "090741", "CADUSD=X", 100000.0,   0.00005,    "financial", "tff"),
    Contract("CHFUSD","Swiss Franc",        "fx",      "092741", "CHFUSD=X", 125000.0,   0.0001,     "financial", "tff"),
    Contract("NZDUSD","New Zealand Dollar", "fx",      "112741", "NZDUSD=X", 100000.0,   0.0001,     "financial", "tff"),
    Contract("MXNUSD","Mexican Peso",       "fx",      "095741", "MXNUSD=X", 500000.0,   0.000005,   "financial", "tff"),
    Contract("BRLUSD","Brazilian Real",     "fx",      "102741", "BRLUSD=X", 100000.0,   0.00005,    "financial", "tff"),
    Contract("RUBUSD","Russian Ruble",      "fx",      "089741", "RUBUSD=X", 2500000.0,  0.00001,    "financial", "tff"),
    Contract("NOKUSD","Norwegian Krone",    "fx",      "184741", "NOKUSD=X", 2000000.0,  0.00001,    "financial", "tff"),
    Contract("SEKUSD","Swedish Krona",      "fx",      "185741", "SEKUSD=X", 2000000.0,  0.00001,    "financial", "tff"),

    # ── Equity Indices (TFF) ──────────────────────────────────────────────
    Contract("ES",    "S&P 500 E-mini",     "indices", "13874A", "ES=F",    50.0,    0.25,   "financial", "tff"),
    Contract("NQ",    "Nasdaq-100 E-mini",  "indices", "209742", "NQ=F",    20.0,    0.25,   "financial", "tff"),
    Contract("YM",    "DJIA E-mini",        "indices", "124603", "YM=F",    5.0,     1.0,    "financial", "tff"),
    Contract("RTY",   "Russell 2000",       "indices", "239742", "RTY=F",   50.0,    0.10,   "financial", "tff"),
    Contract("NIY",   "Nikkei 225 Yen",     "indices", "240741", "NIY=F",   500.0,   5.0,    "financial", "tff"),
    Contract("MES",   "Micro S&P 500",      "indices", "13874+", "MES=F",   5.0,     0.25,   "financial", "tff"),
    Contract("MNQ",   "Micro Nasdaq-100",   "indices", "209743", "MNQ=F",   2.0,     0.25,   "financial", "tff"),

    # ── Interest Rates (TFF) ──────────────────────────────────────────────
    Contract("ZB",    "30Y T-Bond",         "rates",   "020601", "ZB=F",    1000.0,   0.03125,   "financial", "tff"),
    Contract("ZN",    "10Y T-Note",         "rates",   "043602", "ZN=F",    1000.0,   0.015625,  "financial", "tff"),
    Contract("ZF",    "5Y T-Note",          "rates",   "044601", "ZF=F",    1000.0,   0.0078125, "financial", "tff"),
    Contract("ZT",    "2Y T-Note",          "rates",   "042601", "ZT=F",    200000.0, 0.0078125, "financial", "tff"),
    Contract("FF",    "30D Fed Funds",      "rates",   "045601", "FF=F",    4167.0,   0.0025,    "financial", "tff"),
    Contract("SR3",   "SOFR 3M",            "rates",   "SR3   ", "SR3=F",   2500.0,   0.0025,    "financial", "tff"),
)


def by_symbol(symbol: str) -> Contract:
    for c in UNIVERSE:
        if c.symbol == symbol:
            return c
    raise KeyError(f"Unknown symbol: {symbol}")


def sectors() -> dict[str, list[Contract]]:
    out: dict[str, list[Contract]] = {}
    for c in UNIVERSE:
        out.setdefault(c.sector, []).append(c)
    return out
