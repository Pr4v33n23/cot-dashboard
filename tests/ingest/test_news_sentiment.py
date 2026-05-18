import pandas as pd
import pytest
from unittest.mock import patch
from ingest.news_sentiment import score_headlines, _build_batch_prompt, _parse_response

HEADLINES = pd.DataFrame({
    "title": [
        "OPEC cuts production by 1 million barrels",
        "US inventory build for third consecutive week",
        "Fed holds rates unchanged",
    ],
    "date": pd.to_datetime(["2026-05-01", "2026-05-02", "2026-05-03"]),
})

def test_build_prompt_contains_headlines():
    prompt = _build_batch_prompt(HEADLINES["title"].tolist())
    assert "OPEC" in prompt
    assert "inventory" in prompt

def test_parse_response_valid_json():
    mock_json = '[{"title":"OPEC","sentiment":"positive","score":0.8,"reasoning":"supply cut bullish"},{"title":"inventory","sentiment":"negative","score":-0.5,"reasoning":"build bearish"},{"title":"Fed","sentiment":"neutral","score":0.0,"reasoning":"no change"}]'
    result = _parse_response(mock_json, 3)
    assert len(result) == 3
    assert result[0]["score"] == 0.8
    assert result[1]["sentiment"] == "negative"

def test_parse_response_malformed_returns_neutral():
    result = _parse_response("not json", 2)
    assert len(result) == 2
    assert all(r["sentiment"] == "neutral" for r in result)

def test_score_headlines_skips_already_scored():
    df = HEADLINES.copy()
    df["sentiment_score"] = [0.5, None, None]
    df["sentiment_label"] = ["positive", None, None]

    with patch("ingest.news_sentiment._call_api") as mock_api, \
         patch("ingest.news_sentiment.available", return_value=True):
        mock_api.return_value = [
            {"score": -0.5, "sentiment": "negative", "reasoning": "bearish"},
            {"score": 0.0,  "sentiment": "neutral",  "reasoning": "neutral"},
        ]
        result = score_headlines(df.copy())

    assert result["sentiment_score"].iloc[0] == 0.5   # already scored — unchanged
    assert result["sentiment_score"].iloc[1] == -0.5  # newly scored
    mock_api.assert_called_once()  # called once for 2 unscored rows

def test_score_headlines_no_api_key_returns_null():
    df = HEADLINES.copy()
    with patch("ingest.news_sentiment.available", return_value=False):
        result = score_headlines(df.copy())
    assert result["sentiment_score"].isna().all()
