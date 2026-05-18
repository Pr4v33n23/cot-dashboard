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

    top_markets: list[dict] = []
    if not bundle.today_df.empty:
        for _, row in bundle.today_df.iterrows():
            sym = row["symbol"]
            synth = (bundle.synthesis or {}).get(sym, {})
            confluence = float(synth.get("confluence_score", 0) or 0)
            top_markets.append({
                "symbol": sym,
                "sector": str(row.get("sector", "")),
                "n_zones": int(row.get("n_zones", 0) or 0),
                "zones_on": list(row.get("zones_on", []) or []),
                "cot_index": round(float(row.get("cot_index_comm", 50) or 50), 1),
                "confluence_score": round(confluence, 2),
                "key_factors": list(synth.get("key_factors", [])[:3]),
            })
        top_markets.sort(key=lambda x: x["confluence_score"], reverse=True)
        top_markets = top_markets[:_MAX_MARKETS]

    sector_summary: dict[str, dict] = {}
    if not bundle.today_df.empty:
        for sector, grp in bundle.today_df.groupby("sector"):
            avg_cot = grp["cot_index_comm"].dropna().mean()
            avg_zones = grp["n_zones"].mean()
            sector_summary[str(sector)] = {
                "avg_cot_index": round(float(avg_cot), 1) if not pd.isna(avg_cot) else 50.0,
                "avg_zones": round(float(avg_zones), 1),
                "n_markets": len(grp),
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
