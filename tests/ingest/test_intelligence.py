# tests/ingest/test_intelligence.py
from __future__ import annotations
import json
import pandas as pd
import pytest
from unittest.mock import patch
from ingest.intelligence import (
    build_digest_payload,
    _parse_digest,
    generate_digest,
    REQUIRED_KEYS,
)

SAMPLE_SYNTHESIS = {
    "CL": {"confluence_score": 0.84, "key_factors": ["extreme commercial long"], "summary": "x", "watch": "y"},
    "HG": {"confluence_score": 0.79, "key_factors": ["accumulation"], "summary": "x", "watch": "y"},
}
VALID_DIGEST = json.dumps({
    "macro_narrative": "Commercials near extreme longs across energy.",
    "sector_signals": [{"sector": "energy", "summary": "Comm extreme long", "signal": "bullish"}],
    "watch_markets": [{"symbol": "CL", "reason": "5-week divergence"}],
})


def test_build_digest_payload_has_required_keys():
    ann = {}
    news = pd.DataFrame()
    payload = build_digest_payload(ann, news, SAMPLE_SYNTHESIS)
    for k in ("date", "top_markets", "sector_summary", "macro_news", "divergence_count", "regime_counts"):
        assert k in payload, f"missing key: {k}"


def test_build_digest_top_markets_sorted_descending():
    ann = {}
    news = pd.DataFrame()
    payload = build_digest_payload(ann, news, SAMPLE_SYNTHESIS)
    scores = [m["confluence_score"] for m in payload["top_markets"]]
    assert scores == sorted(scores, reverse=True)


def test_build_digest_top_markets_limit_10():
    big_synth = {f"S{i}": {"confluence_score": float(i) / 100} for i in range(50)}
    payload = build_digest_payload({}, pd.DataFrame(), big_synth)
    assert len(payload["top_markets"]) <= 10


def test_parse_digest_valid_json():
    result = _parse_digest(VALID_DIGEST)
    assert set(REQUIRED_KEYS).issubset(result.keys())
    assert result["macro_narrative"] != ""
    assert isinstance(result["sector_signals"], list)
    assert isinstance(result["watch_markets"], list)


def test_parse_digest_malformed_returns_defaults():
    result = _parse_digest("not json at all {{ broken")
    assert result["macro_narrative"] == ""
    assert result["sector_signals"] == []
    assert result["watch_markets"] == []


def test_generate_digest_no_token_returns_defaults():
    with patch("ingest.intelligence.available", return_value=False):
        result = generate_digest({"date": "2026-05-18"})
    assert result["macro_narrative"] == ""


def test_generate_digest_calls_chat_once():
    with patch("ingest.intelligence.chat") as mock_chat, \
         patch("ingest.intelligence.available", return_value=True):
        mock_chat.return_value = VALID_DIGEST
        result = generate_digest({"date": "2026-05-18"})
    mock_chat.assert_called_once()
    assert result["macro_narrative"] != ""
