"""Keyword → market mapping for the news correlator.

Deterministic. No NLP. A headline matches a market if any keyword in that
market's set appears in the headline (case-insensitive, word-boundary regex).
One headline can match multiple markets — that's expected (e.g., a CPI print
tags GC, ZN, and 6E in real-world COT discussions).

Maintenance: keep keywords narrow enough to avoid false-positives. A keyword
that fires on 50%+ of unrelated headlines (e.g., "trade") should be dropped or
qualified ("china trade"). Add new keywords as headlines are observed to fire
on the right markets.

Source-tagging is intentionally LITERAL — no model interpretation, no sentiment
classification, no summarization. The trader supplies the meaning.
"""

from __future__ import annotations

# Keyword sets per market. Word-boundary regex match is done in news.py.
TAXONOMY: dict[str, list[str]] = {
    # ── Grains ───────────────────────────────────────────────────────────
    "ZC": ["corn", "wasde", "ethanol", "ethanol mandate", "midwest drought",
           "midwest planting", "us corn", "china corn", "feed grain"],
    "ZW": ["wheat", "wasde", "winter wheat", "spring wheat", "russia wheat",
           "ukraine wheat", "black sea grain", "kansas drought", "wheat export"],
    "ZS": ["soybean", "soy", "wasde", "brazil soy", "argentina soy",
           "china soybean", "crush margin", "soybean export"],
    "ZM": ["soybean meal", "soy meal", "soymeal", "crush margin"],
    "ZL": ["soybean oil", "soy oil", "biodiesel", "vegetable oil",
           "palm oil", "biofuel mandate"],
    "ZO": ["oats", "oat", "wasde"],
    "ZR": ["rough rice", "rice", "asia rice", "thailand rice", "vietnam rice"],
    # ── Energy ───────────────────────────────────────────────────────────
    "CL": ["opec", "opec+", "crude", "wti", "brent", "saudi", "saudi arabia",
           "iran", "iran sanctions", "russia oil", "russian oil", "pipeline",
           "refinery", "eia inventory", "petroleum status", "shale", "permian",
           "spr", "strategic petroleum reserve", "venezuela oil", "iraq oil"],
    "NG": ["natural gas", "lng", "henry hub", "european gas", "gas storage",
           "winter storm", "freeport lng", "gas pipeline", "eia natural gas"],
    "HO": ["heating oil", "diesel", "distillate", "ulsd", "diesel margin"],
    "RB": ["gasoline", "rbob", "summer driving", "gasoline inventory",
           "refinery", "gasoline crack"],
    # ── Metals ───────────────────────────────────────────────────────────
    "GC": ["gold", "fed", "fomc", "rate cut", "rate hike", "cpi", "pce",
           "inflation", "dollar", "dxy", "real yield", "central bank gold",
           "gold etf", "treasury yield"],
    "SI": ["silver", "fed", "fomc", "industrial silver", "silver etf",
           "solar silver"],
    "HG": ["copper", "china manufacturing", "china pmi", "ev demand",
           "electrification", "lme copper", "chile copper", "peru copper",
           "freeport mcmoran"],
    "PL": ["platinum", "auto catalyst", "diesel demand", "south africa mining",
           "pgm", "palladium"],
    # ── Softs ────────────────────────────────────────────────────────────
    "CC": ["cocoa", "ivory coast", "ghana cocoa", "west africa cocoa",
           "cocoa pod", "cocoa harvest"],
    "KC": ["coffee", "arabica", "brazil coffee", "vietnam coffee",
           "coffee frost", "coffee harvest", "colombia coffee"],
    "CT": ["cotton", "china cotton", "india cotton", "us cotton export",
           "cotton planting", "xinjiang cotton"],
    "SB": ["sugar", "raw sugar", "brazil sugar", "india sugar",
           "thailand sugar", "ethanol mandate", "sugar export"],
    "OJ": ["orange juice", "florida freeze", "florida citrus", "citrus greening",
           "hurricane florida", "brazil orange"],
    # ── Meats ────────────────────────────────────────────────────────────
    "LE": ["live cattle", "cattle on feed", "beef demand", "packer margin",
           "usda cattle", "cold storage beef"],
    "HE": ["lean hogs", "pork", "swine fever", "african swine fever",
           "china pork", "packer hogs", "usda hogs"],
    "GF": ["feeder cattle", "feedlot", "calf prices", "cow herd"],
    # ── Equity Indices ────────────────────────────────────────────────────
    "ES":     ["s&p", "spx", "s&p 500", "sp500", "equity", "stock market", "wall street", "s&p500"],
    "NQ":     ["nasdaq", "tech stocks", "faang", "mega cap", "qqq"],
    "YM":     ["dow", "djia", "blue chip", "dow jones"],
    "RTY":    ["russell", "small cap", "iwm", "russell 2000"],
    "MES":    ["s&p", "spx", "micro s&p"],
    "MNQ":    ["nasdaq", "micro nasdaq"],
    "NIY":    ["nikkei", "japan stocks", "boj", "topix"],
    # ── Interest Rates ────────────────────────────────────────────────────
    "ZB":     ["treasury", "t-bond", "30 year", "long bond", "30yr", "yield curve"],
    "ZN":     ["10-year", "10yr", "treasury note", "10y yield", "10 year yield"],
    "ZF":     ["5-year", "5yr", "5y yield"],
    "ZT":     ["2-year", "2yr", "short end", "2y yield"],
    "FF":     ["fed funds", "federal reserve", "fomc", "rate hike", "rate cut", "fed rate"],
    "SR3":    ["sofr", "secured overnight", "libor replacement"],
    # ── FX ────────────────────────────────────────────────────────────────
    "EURUSD": ["euro", "eur", "ecb", "eurozone", "lagarde", "eu inflation"],
    "GBPUSD": ["sterling", "pound", "gbp", "boe", "bank of england", "uk inflation"],
    "JPYUSD": ["yen", "jpy", "boj", "bank of japan", "japan inflation"],
    "AUDUSD": ["aussie", "aud", "rba", "reserve bank of australia"],
    "CADUSD": ["loonie", "cad", "bank of canada", "boc", "canada gdp"],
    "CHFUSD": ["swiss franc", "chf", "snb", "swiss national bank"],
    "NZDUSD": ["kiwi", "nzd", "rbnz", "reserve bank of new zealand"],
    "MXNUSD": ["peso", "mxn", "banxico", "mexico inflation"],
    "BRLUSD": ["real", "brl", "bcb", "brazil", "banco central"],
    "NOKUSD": ["krone", "nok", "norges bank", "norway oil"],
    "SEKUSD": ["krona", "sek", "riksbank", "sweden inflation"],
}

# Source category tags — used by the UI's NewsRail filter chip row.
SOURCE_CATEGORIES = {
    "yfinance": "market",
    "wasde": "agency",
    "eia": "agency",
    "fomc": "macro",
    "opec": "geopolitics",
    "fred": "macro",
}


def markets_for_headline(headline: str) -> list[str]:
    """Return the list of market symbols a headline matches.

    Pure-function, deterministic. No NLP. Case-insensitive substring with
    word-boundary regex — callers wrap once.
    """
    import re
    h = headline.lower()
    hits = []
    for symbol, keywords in TAXONOMY.items():
        for kw in keywords:
            # Word-boundary on either end so "corn" doesn't match "popcorn"
            # and "fed" doesn't match "federal" (use "fomc" or "rate" for that).
            pattern = r"\b" + re.escape(kw) + r"\b"
            if re.search(pattern, h):
                hits.append(symbol)
                break  # one hit per market is enough
    return hits
