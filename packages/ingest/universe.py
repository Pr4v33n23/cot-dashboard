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

from dataclasses import dataclass


@dataclass(frozen=True)
class Contract:
    symbol: str
    name: str
    sector: str
    cftc_name: str
    cftc_code: str
    yf_ticker: str
    point_value: float
    tick_size: float


# Curated universe. CFTC codes verified against disaggregated futures-only
# archive for 2024. Yahoo Finance tickers verified to return ≥ 10 years of
# daily bars as of 2026-05-16.
UNIVERSE: tuple[Contract, ...] = (
    # Grains — CBT
    Contract("ZC",  "Corn",                "grains",  "CORN",                       "002602", "ZC=F", 50.0,   0.25),
    Contract("ZW",  "Wheat SRW",           "grains",  "WHEAT-SRW",                  "001602", "ZW=F", 50.0,   0.25),
    Contract("ZS",  "Soybeans",            "grains",  "SOYBEANS",                   "005602", "ZS=F", 50.0,   0.25),
    Contract("ZM",  "Soybean Meal",        "grains",  "SOYBEAN MEAL",               "026603", "ZM=F", 100.0,  0.10),
    Contract("ZL",  "Soybean Oil",         "grains",  "SOYBEAN OIL",                "007601", "ZL=F", 600.0,  0.01),
    Contract("ZO",  "Oats",                "grains",  "OATS",                       "004603", "ZO=F", 50.0,   0.25),
    Contract("ZR",  "Rough Rice",          "grains",  "ROUGH RICE",                 "039601", "ZR=F", 2000.0, 0.005),
    # Energy — NYMEX
    Contract("CL",  "Crude Oil WTI",       "energy",  "WTI-PHYSICAL",               "067651", "CL=F", 1000.0,  0.01),
    Contract("NG",  "Natural Gas",         "energy",  "NAT GAS NYME",               "023651", "NG=F", 10000.0, 0.001),
    Contract("HO",  "Heating Oil",         "energy",  "NY HARBOR ULSD",             "022651", "HO=F", 42000.0, 0.0001),
    Contract("RB",  "RBOB Gasoline",       "energy",  "GASOLINE RBOB",              "111659", "RB=F", 42000.0, 0.0001),
    # Metals — COMEX / NYMEX
    Contract("GC",  "Gold",                "metals",  "GOLD",                       "088691", "GC=F", 100.0,  0.10),
    Contract("SI",  "Silver",              "metals",  "SILVER",                     "084691", "SI=F", 5000.0, 0.005),
    Contract("HG",  "Copper",              "metals",  "COPPER- #1",                 "085692", "HG=F", 25000.0, 0.0005),
    Contract("PL",  "Platinum",            "metals",  "PLATINUM",                   "076651", "PL=F", 50.0,   0.10),
    # Softs — ICE Futures U.S.
    Contract("CC",  "Cocoa",               "softs",   "COCOA",                      "073732", "CC=F", 10.0,   1.0),
    Contract("KC",  "Coffee C",            "softs",   "COFFEE C",                   "083731", "KC=F", 375.0,  0.05),
    Contract("CT",  "Cotton #2",           "softs",   "COTTON NO. 2",               "033661", "CT=F", 500.0,  0.01),
    Contract("SB",  "Sugar #11",           "softs",   "SUGAR NO. 11",               "080732", "SB=F", 1120.0, 0.01),
    Contract("OJ",  "Orange Juice",        "softs",   "FRZN CONCENTRATED ORANGE",   "040701", "OJ=F", 150.0,  0.05),
    # Meats — CME
    Contract("LE",  "Live Cattle",         "meats",   "LIVE CATTLE",                "057642", "LE=F", 400.0,  0.025),
    Contract("HE",  "Lean Hogs",           "meats",   "LEAN HOGS",                  "054642", "HE=F", 400.0,  0.025),
    Contract("GF",  "Feeder Cattle",       "meats",   "FEEDER CATTLE",              "061641", "GF=F", 500.0,  0.025),
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
