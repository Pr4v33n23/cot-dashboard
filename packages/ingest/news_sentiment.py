"""News sentiment scoring via DeepSeek-V4-Pro (HuggingFace). Incremental."""
from __future__ import annotations
import json
import math
import re

import pandas as pd

from ingest._ai import available, chat

BATCH_SIZE = 32
_SYSTEM = (
    "You are a financial news sentiment classifier. "
    "Given a list of financial news headlines, return a JSON array where each element has: "
    "title (string), sentiment ('positive'|'negative'|'neutral'), score (float -1 to 1), "
    "reasoning (one sentence, max 15 words). "
    "Return ONLY the JSON array, no other text."
)


def _build_batch_prompt(titles: list[str]) -> str:
    numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles))
    return f"Classify the sentiment of these {len(titles)} financial headlines:\n{numbered}"


def _parse_response(content: str, expected_count: int) -> list[dict]:
    try:
        match = re.search(r"\[.*\]", content, re.DOTALL)
        if not match:
            raise ValueError("no JSON array found")
        data = json.loads(match.group())
        if len(data) != expected_count:
            raise ValueError(f"expected {expected_count}, got {len(data)}")
        return data
    except Exception:
        return [{"sentiment": "neutral", "score": 0.0, "reasoning": ""} for _ in range(expected_count)]


def _call_api(titles: list[str]) -> list[dict]:
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user",   "content": _build_batch_prompt(titles)},
    ]
    raw = chat(messages, temperature=0)
    # Model may wrap array in {"results": [...]} — unwrap if needed
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            raw = json.dumps(next(iter(parsed.values())))
    except Exception:
        pass
    return _parse_response(raw, len(titles))


def score_headlines(df: pd.DataFrame) -> pd.DataFrame:
    """Add sentiment_score, sentiment_label, sentiment_reason columns. Skips already-scored."""
    if "sentiment_score" not in df.columns:
        df = df.copy()
        df["sentiment_score"] = None
        df["sentiment_label"] = None
        df["sentiment_reason"] = None

    if not available():
        return df

    unscored_mask = df["sentiment_score"].isna()
    if not unscored_mask.any():
        return df

    unscored = df[unscored_mask].copy()
    titles = unscored["title"].fillna("").tolist()
    n_batches = math.ceil(len(titles) / BATCH_SIZE)

    all_results: list[dict] = []
    for i in range(n_batches):
        batch = titles[i * BATCH_SIZE:(i + 1) * BATCH_SIZE]
        all_results.extend(_call_api(batch))

    idx = unscored.index
    df = df.copy()
    df.loc[idx, "sentiment_score"] = [r["score"] for r in all_results]
    df.loc[idx, "sentiment_label"] = [r["sentiment"] for r in all_results]
    df.loc[idx, "sentiment_reason"] = [r.get("reasoning", "") for r in all_results]
    return df
