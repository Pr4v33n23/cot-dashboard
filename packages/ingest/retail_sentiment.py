"""Retail sentiment from IG, Myfxbook, OANDA, CBOE Put/Call, CFTC NR proxy."""
from __future__ import annotations
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

REQUIRED_COLS = ["symbol", "long_pct", "short_pct", "source", "timestamp"]

_IG_URL = "https://api.ig.com/gateway/deal/clientsentiment"
_MYFXBOOK_URL = "https://www.myfxbook.com/community/outlook"
_CBOE_PC_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/SPX_P-C_Ratio.json"
_INDEX_SYMBOLS = {"ES", "NQ", "YM", "RTY", "MES", "MNQ", "NIY"}


def _now() -> datetime:
    return datetime.now(tz=timezone.utc).replace(tzinfo=None)


def _parse_ig_response(data: dict) -> pd.DataFrame:
    rows = []
    for item in data.get("instrumentSentimentList", []):
        name = item.get("instrumentName", "").replace("/", "").replace("-", "").replace(" ", "")
        rows.append({
            "symbol": name,
            "long_pct": float(item["longPositionPercentage"]),
            "short_pct": float(item["shortPositionPercentage"]),
            "source": "ig",
            "timestamp": _now(),
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
                    rows.append({
                        "symbol": sym, "long_pct": long_p, "short_pct": short_p,
                        "source": "myfxbook", "timestamp": _now(),
                    })
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
    return {
        "symbol": symbol, "long_pct": long_p, "short_pct": 100 - long_p,
        "source": "nr_proxy", "timestamp": _now(),
    }


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
        items = data.get("data", [])
        latest = items[-1] if items else {}
        pc = float(latest.get("ratio", 1.0))
        long_p = round(1 / (1 + pc) * 100, 1)
        rows = [{
            "symbol": sym, "long_pct": long_p, "short_pct": 100 - long_p,
            "source": "put_call", "timestamp": _now(),
        } for sym in _INDEX_SYMBOLS]
        return pd.DataFrame(rows, columns=REQUIRED_COLS)
    except Exception:
        return pd.DataFrame(columns=REQUIRED_COLS)


def merge_sources(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    return (
        df.groupby("symbol")[["long_pct", "short_pct"]]
        .mean()
        .rename(columns={"long_pct": "avg_long_pct", "short_pct": "avg_short_pct"})
        .reset_index()
    )


def load_retail_sentiment(
    annotated: dict[str, pd.DataFrame],
    cache_dir: Path,
) -> pd.DataFrame:
    frames = [_fetch_ig(), _fetch_myfxbook(), _fetch_put_call()]

    for sym, df in annotated.items():
        if df.empty:
            continue
        last = df.iloc[-1]
        if "nr_long" in last.index and "nr_short" in last.index:
            frames.append(pd.DataFrame(
                [_compute_nr_proxy(sym, last)], columns=REQUIRED_COLS
            ))

    all_df = pd.concat([f for f in frames if not f.empty], ignore_index=True)
    if not all_df.empty:
        cache_dir.mkdir(parents=True, exist_ok=True)
        all_df.to_parquet(cache_dir / "retail_sentiment.parquet", index=False)
    return all_df
