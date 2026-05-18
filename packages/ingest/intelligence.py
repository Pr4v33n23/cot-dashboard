# packages/ingest/intelligence.py
"""Cross-market intelligence digest via DeepSeek-V4-Pro."""
from __future__ import annotations
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from ingest._ai import available, chat

REQUIRED_KEYS = ("macro_narrative", "sector_signals", "watch_markets")
_DEFAULT: dict = {"macro_narrative": "", "sector_signals": [], "watch_markets": []}

_SYSTEM = (
    "You are a quantitative market analyst producing a weekly intelligence digest. "
    "Given structured COT, regime, and news data, produce a JSON object with: "
    "macro_narrative (3-4 sentences on the dominant cross-market theme this week), "
    "sector_signals (array of {sector, summary, signal} where signal is 'bullish'|'bearish'|'neutral'), "
    "watch_markets (top 5 markets array of {symbol, reason}). "
    "All statements must be derived from the provided data. No invented facts. No trading advice. "
    "Return ONLY the JSON object."
)


def build_digest_payload(
    annotated: dict[str, pd.DataFrame],
    news_df: pd.DataFrame,
    synthesis: dict[str, dict],
) -> dict:
    from ingest.universe import UNIVERSE  # noqa: PLC0415

    top_markets = sorted(
        [
            {
                "symbol": sym,
                "confluence_score": float(data.get("confluence_score", 0) or 0),
                "key_factors": data.get("key_factors", [])[:3],
                "regime": (
                    str(annotated[sym].iloc[-1].get("regime_label", "unknown"))
                    if sym in annotated and not annotated[sym].empty
                    else "unknown"
                ),
            }
            for sym, data in synthesis.items()
            if float(data.get("confluence_score", 0) or 0) > 0
        ],
        key=lambda x: x["confluence_score"],
        reverse=True,
    )[:10]

    sec_map: dict[str, list[str]] = {}
    for c in UNIVERSE:
        sec_map.setdefault(c.sector, []).append(c.symbol)

    sector_summary: dict[str, dict] = {}
    for sec, syms in sec_map.items():
        scores = [float(synthesis[s].get("confluence_score", 0) or 0) for s in syms if s in synthesis]
        cot_vals = [
            float(v)
            for s in syms
            if s in annotated and not annotated[s].empty
            for v in [annotated[s].iloc[-1].get("cot_index_comm")]
            if v is not None and not (isinstance(v, float) and pd.isna(v))
        ]
        sector_summary[sec] = {
            "avg_confluence": round(sum(scores) / len(scores), 3) if scores else 0,
            "avg_cot_index": round(sum(cot_vals) / len(cot_vals), 1) if cot_vals else 50,
            "n_markets": len(syms),
        }

    macro_news: list[dict] = []
    if not news_df.empty and "source_category" in news_df.columns:
        macro = news_df[news_df["source_category"].isin(["macro", "agency"])].tail(10)
        for _, row in macro.iterrows():
            macro_news.append({
                "source": str(row.get("source", "")),
                "title": str(row.get("title", "")),
                "sentiment_score": float(row.get("sentiment_score", 0) or 0),
            })

    regime_counts: dict[str, int] = {}
    for df in annotated.values():
        if df.empty:
            continue
        label = df.iloc[-1].get("regime_label")
        if label and isinstance(label, str):
            regime_counts[label] = regime_counts.get(label, 0) + 1

    div_count = sum(
        1 for df in annotated.values()
        if not df.empty and int(
            df.iloc[-1].get("comm_spec_divergence", 0) or
            df.iloc[-1].get("am_lf_divergence", 0) or 0
        ) > 0
    )

    return {
        "date": datetime.now(tz=timezone.utc).strftime("%Y-%m-%d"),
        "top_markets": top_markets,
        "sector_summary": sector_summary,
        "macro_news": macro_news,
        "divergence_count": div_count,
        "regime_counts": regime_counts,
    }


def _parse_digest(content: str) -> dict:
    try:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            raise ValueError("no JSON object found")
        data = json.loads(match.group())
        for k in REQUIRED_KEYS:
            data.setdefault(k, _DEFAULT[k])
        return data
    except Exception:
        return dict(_DEFAULT)


def generate_digest(payload: dict) -> dict:
    if not available():
        return dict(_DEFAULT)
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": f"Generate digest from:\n{json.dumps(payload, indent=2)}"},
    ]
    raw = chat(messages, temperature=0.15)
    return _parse_digest(raw)


def load_or_generate_digest(
    annotated: dict[str, pd.DataFrame],
    news_df: pd.DataFrame,
    synthesis: dict[str, dict],
    cache_dir: Path,
    force: bool = False,
) -> dict:
    cache_path = cache_dir / "intelligence_digest.json"
    if not force and cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text())
            generated_at_str = cached.get("generated_at", "2000-01-01T00:00:00")
            generated_at = datetime.fromisoformat(generated_at_str.replace("Z", "+00:00"))
            age_days = (datetime.now(tz=timezone.utc) - generated_at).days
            if age_days < 7:
                return cached
        except Exception:
            pass
    result = generate_digest(build_digest_payload(annotated, news_df, synthesis))
    result["generated_at"] = datetime.now(tz=timezone.utc).isoformat()
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(result, indent=2, default=str))
    return result
