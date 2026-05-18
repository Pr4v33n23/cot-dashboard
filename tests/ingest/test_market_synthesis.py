import pandas as pd
import pytest
from unittest.mock import patch
from ingest.market_synthesis import (
    _build_synthesis_prompt,
    _parse_synthesis_response,
    synthesize_market,
    REQUIRED_SYNTHESIS_KEYS,
)

SAMPLE_PAYLOAD = {
    "symbol": "CL", "market_type": "physical",
    "cot": {"comm_net": 182400, "comm_cot_index": 91.4,
            "spec_net": -94200, "spec_cot_index": 8.2, "divergence_weeks": 5},
    "regime": {"label": "accumulation", "weeks": 5, "confidence": 0.81},
    "open_interest": {"current": 412000, "change_pct": 6.1},
    "retail_sentiment": {"avg_short_pct": 71},
    "news_sentiment": {"score": 0.55, "top_headlines": ["OPEC cuts production"]},
}

VALID_RESPONSE = '{"summary":"Commercials at extreme.","confluence_score":0.82,"key_factors":["extreme commercial long"],"watch":"OPEC May 22"}'

def test_build_prompt_contains_symbol():
    prompt = _build_synthesis_prompt(SAMPLE_PAYLOAD)
    assert "CL" in prompt
    assert "182400" in prompt

def test_parse_valid_response():
    result = _parse_synthesis_response(VALID_RESPONSE)
    assert set(REQUIRED_SYNTHESIS_KEYS).issubset(result.keys())
    assert 0 <= result["confluence_score"] <= 1

def test_parse_malformed_returns_defaults():
    result = _parse_synthesis_response("not json at all")
    assert "summary" in result
    assert result["confluence_score"] == 0.0

def test_synthesize_no_api_key_returns_default():
    with patch("ingest.market_synthesis.available", return_value=False):
        result = synthesize_market(SAMPLE_PAYLOAD)
    assert result["confluence_score"] == 0.0
    assert "summary" in result

def test_synthesize_calls_chat():
    with patch("ingest.market_synthesis.chat") as mock_chat, \
         patch("ingest.market_synthesis.available", return_value=True):
        mock_chat.return_value = VALID_RESPONSE
        result = synthesize_market(SAMPLE_PAYLOAD)
    mock_chat.assert_called_once()
    assert result["confluence_score"] == pytest.approx(0.82)
