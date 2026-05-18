"""Weekly per-market intelligence synthesis via DeepSeek-V4-Pro (HuggingFace)."""
from __future__ import annotations
import json
import re
from pathlib import Path

import pandas as pd

from ingest._ai import available, chat

REQUIRED_SYNTHESIS_KEYS = ("summary", "confluence_score", "key_factors", "watch")
_DEFAULT: dict = {"summary": "", "confluence_score": 0.0, "key_factors": [], "watch": ""}


def _deterministic_synthesis(payload: dict) -> dict:
    """Rule-based confluence score when AI is unavailable.

    Scores 0-1 based on how many intelligence layers are active:
    1. COT extreme (cot_index >= 85 or <= 15)
    2. Commercial/spec divergence active (>= 2 weeks)
    3. OI confirming (|change| >= 3%)
    4. Retail contra (short% >= 65 or <= 35 when commercials extreme)
    5. Regime is accumulation or distribution (not ranging)
    """
    factors: list[str] = []
    score_parts: list[float] = []

    cot = payload.get("cot", {})
    comm_idx = float(cot.get("comm_cot_index", 50) or 50)
    div_weeks = int(cot.get("divergence_weeks", 0) or 0)

    oi = payload.get("open_interest", {})
    oi_chg = abs(float(oi.get("change_pct", 0) or 0))

    retail = payload.get("retail_sentiment", {})
    avg_short = float(retail.get("avg_short_pct", 50) or 50)

    regime = payload.get("regime", {})
    regime_label = str(regime.get("label", "ranging") or "ranging")
    regime_conf = float(regime.get("confidence", 0.5) or 0.5)

    # 1. COT extreme
    if comm_idx >= 85 or comm_idx <= 15:
        factors.append("extreme commercial positioning")
        score_parts.append(min(1.0, abs(comm_idx - 50) / 50))

    # 2. Divergence active
    if div_weeks >= 2:
        factors.append(f"commercial/spec divergence ({div_weeks} wks)")
        score_parts.append(min(1.0, div_weeks / 8))

    # 3. OI confirmation
    if oi_chg >= 3.0:
        factors.append(f"OI {'expansion' if oi_chg > 0 else 'contraction'} ({oi_chg:.1f}%)")
        score_parts.append(min(1.0, oi_chg / 10))

    # 4. Retail contra (crowd wrong-sided)
    if comm_idx >= 70 and avg_short >= 60:
        factors.append(f"retail {avg_short:.0f}% short vs commercial long")
        score_parts.append((avg_short - 50) / 50)
    elif comm_idx <= 30 and avg_short <= 40:
        factors.append(f"retail {100-avg_short:.0f}% long vs commercial short")
        score_parts.append((50 - avg_short) / 50)

    # 5. Regime signal
    if regime_label in ("accumulation", "distribution", "trending"):
        factors.append(f"regime: {regime_label}")
        score_parts.append(regime_conf * 0.5)

    confluence = round(sum(score_parts) / max(len(score_parts), 1), 3) if score_parts else 0.0
    confluence = min(1.0, confluence)

    mtype = payload.get("market_type", "physical")
    sym = payload.get("symbol", "")
    summary = (
        f"COT Index at {comm_idx:.0f}. "
        + (f"Commercial/spec divergence active for {div_weeks} weeks. " if div_weeks >= 2 else "")
        + (f"OI {oi_chg:+.1f}% this week. " if oi_chg >= 2 else "")
        + (f"Retail {avg_short:.0f}% short. " if avg_short != 50 else "")
        + f"Regime: {regime_label}."
    ).strip()

    return {
        "summary": summary,
        "confluence_score": confluence,
        "key_factors": factors,
        "watch": "",
        "source": "deterministic",
    }

_SYSTEM = (
    "You are a quantitative market analyst. Given structured market data, "
    "produce a JSON object with: "
    "summary (2-3 sentences of factual market context, no predictions), "
    "confluence_score (float 0-1: fraction of intelligence layers that align), "
    "key_factors (list of up to 5 strings naming active signals), "
    "watch (one upcoming event or threshold worth monitoring). "
    "Return ONLY the JSON object."
)


def _build_synthesis_prompt(payload: dict) -> str:
    return (
        f"Synthesize market intelligence for {payload['symbol']} "
        f"({payload['market_type']}):\n{json.dumps(payload, indent=2)}"
    )


def _parse_synthesis_response(content: str) -> dict:
    try:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            raise ValueError("no JSON object found")
        data = json.loads(match.group())
        data.setdefault("summary", "")
        data.setdefault("confluence_score", 0.0)
        data.setdefault("key_factors", [])
        data.setdefault("watch", "")
        data["confluence_score"] = float(max(0.0, min(1.0, data["confluence_score"])))
        return data
    except Exception:
        return dict(_DEFAULT)


def synthesize_market(payload: dict) -> dict:
    if not available():
        # AI unavailable — compute deterministic confluence from COT signals
        return _deterministic_synthesis(payload)
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user",   "content": _build_synthesis_prompt(payload)},
    ]
    raw = chat(messages, temperature=0.1)
    result = _parse_synthesis_response(raw)
    # AI returned empty (rate-limit / billing) — fall back to deterministic
    if not result.get("key_factors") and result.get("confluence_score", 0) == 0.0:
        return _deterministic_synthesis(payload)
    return result


def _build_payload(
    symbol: str,
    df: pd.DataFrame,
    news_df: pd.DataFrame,
    retail_df: pd.DataFrame,
) -> dict:
    from ingest.universe import UNIVERSE  # noqa: PLC0415
    contract = next((c for c in UNIVERSE if c.symbol == symbol), None)
    market_type = getattr(contract, "market_type", "physical") if contract else "physical"
    last = df.iloc[-1]

    comm_net = float(last.get("net_commercials", 0) or 0)
    comm_idx = float(last.get("cot_index_comm", 50) or 50)
    div_col = "comm_spec_divergence" if market_type == "physical" else "am_lf_divergence"
    div_weeks = int(last.get(div_col, 0) or 0)
    spec_net = float((last.get("mm_long", 0) or 0) - (last.get("mm_short", 0) or 0))

    oi_curr = float(last.get("open_interest", 0) or 0)
    oi_prev = float(df["open_interest"].iloc[-5] if len(df) > 5 else oi_curr)
    oi_chg = ((oi_curr - oi_prev) / oi_prev * 100) if oi_prev else 0.0

    regime_label = str(last.get("regime_label") or "unknown")
    regime_weeks = int(last.get("regime_weeks", 0) or 0)
    proba = last.get("regime_proba")
    confidence = float(max(proba)) if isinstance(proba, list) and proba else 0.5

    sym_news = pd.DataFrame()
    if not news_df.empty and "markets" in news_df.columns:
        sym_news = news_df[news_df["markets"].apply(
            lambda m: symbol in m if isinstance(m, list) else False
        )].tail(5)
    news_score = (
        float(sym_news["sentiment_score"].dropna().mean())
        if "sentiment_score" in sym_news.columns and not sym_news.empty
        else 0.0
    )
    headlines = sym_news["title"].tolist()[:3] if not sym_news.empty else []

    sym_retail = retail_df[retail_df["symbol"] == symbol] if not retail_df.empty else pd.DataFrame()
    avg_short = float(sym_retail["short_pct"].mean()) if not sym_retail.empty else 50.0

    return {
        "symbol": symbol,
        "market_type": market_type,
        "cot": {
            "comm_net": comm_net, "comm_cot_index": comm_idx,
            "spec_net": spec_net, "spec_cot_index": round(100 - comm_idx, 1),
            "divergence_weeks": div_weeks,
        },
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
    results: dict[str, dict] = {}
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
