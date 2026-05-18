"""Compress a live Bundle into a compact context JSON for DeepSeek.

Target: ~3 000 tokens so the full conversation + response fits in context.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any

import pandas as pd

CONTEXT_KEYS = ("date", "top_markets", "sector_summary", "macro_news", "universe_size")
_MAX_MARKETS = 15
_MAX_NEWS = 8


def build_context(bundle: Any) -> dict:
    date_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    # Build sector lookup from UNIVERSE — today_df doesn't carry sector
    try:
        from ingest.universe import UNIVERSE as _UNI  # noqa: PLC0415
        _sector_map = {c.symbol: c.sector for c in _UNI}
    except Exception:
        _sector_map = {}

    top_markets: list[dict] = []
    if not bundle.today_df.empty:
        for _, row in bundle.today_df.iterrows():
            sym = row["symbol"]
            synth = (bundle.synthesis or {}).get(sym, {})
            confluence = float(synth.get("confluence_score", 0) or 0)
            # zones_on derived from boolean columns if not pre-computed
            if "zones_on" in row.index and isinstance(row.get("zones_on"), list):
                zones_on = list(row["zones_on"])
            else:
                zones_on = [z for z in ("A1","A2","A3","A4","A5") if bool(row.get(z, False))]
            top_markets.append({
                "symbol": sym,
                "sector": _sector_map.get(sym, str(row.get("sector", ""))),
                "n_zones": int(row.get("n_zones", 0) or 0),
                "zones_on": zones_on,
                "cot_index": round(float(row.get("cot_index_comm", 50) or 50), 1),
                "confluence_score": round(confluence, 2),
                "key_factors": list(synth.get("key_factors", [])[:3]),
            })
        top_markets.sort(key=lambda x: x["confluence_score"], reverse=True)
        top_markets = top_markets[:_MAX_MARKETS]

    sector_summary: dict[str, dict] = {}
    if not bundle.today_df.empty:
        # Group by sector using the UNIVERSE map
        from collections import defaultdict as _dd  # noqa: PLC0415
        sec_groups: dict[str, list] = _dd(list)
        for _, row in bundle.today_df.iterrows():
            sec = _sector_map.get(row["symbol"], "other")
            sec_groups[sec].append(row)
        for sector, rows in sec_groups.items():
            cot_vals = [float(r.get("cot_index_comm", 50) or 50) for r in rows if not pd.isna(r.get("cot_index_comm", 50))]
            zone_vals = [int(r.get("n_zones", 0) or 0) for r in rows]
            sector_summary[sector] = {
                "avg_cot_index": round(sum(cot_vals)/len(cot_vals), 1) if cot_vals else 50.0,
                "avg_zones": round(sum(zone_vals)/len(zone_vals), 1) if zone_vals else 0.0,
                "n_markets": len(rows),
            }

    macro_news: list[dict] = []
    if not bundle.news_df.empty and "source_category" in bundle.news_df.columns:
        macro = bundle.news_df[
            bundle.news_df["source_category"].isin(["macro", "agency"])
        ].sort_values("date", ascending=False).head(_MAX_NEWS)
        for _, row in macro.iterrows():
            macro_news.append({
                "source": str(row.get("source", "")),
                "title": str(row.get("title", ""))[:140],
                "date": str(row.get("date", ""))[:10],
                "sentiment_score": round(float(row.get("sentiment_score", 0) or 0), 2),
                "markets": list(row.get("markets", []) or [])[:4],
            })

    universe_size = len(bundle.annotated) if bundle.annotated else 0

    return {
        "date": date_str,
        "top_markets": top_markets,
        "sector_summary": sector_summary,
        "macro_news": macro_news,
        "universe_size": universe_size,
    }


def context_to_str(ctx: dict) -> str:
    import json  # noqa: PLC0415
    return json.dumps(ctx, separators=(",", ":"))
