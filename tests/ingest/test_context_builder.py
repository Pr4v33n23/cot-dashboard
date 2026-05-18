from __future__ import annotations
import pandas as pd
import pytest
from ingest.context_builder import build_context, CONTEXT_KEYS


def _make_bundle_stub():
    class B:
        today_df = pd.DataFrame({
            "symbol": ["CL", "HG", "ZS"],
            "sector": ["energy", "metals", "grains"],
            "n_zones": [3, 2, 1],
            "total_mag": [1.8, 1.2, 0.6],
            "zones_on": [["A1","A4","A5"], ["A1","A3"], ["A2"]],
            "cot_index_comm": [91.4, 85.2, 62.1],
        })
        synthesis = {
            "CL": {"confluence_score": 0.84, "key_factors": ["extreme commercial long"], "summary": "x", "watch": "y"},
            "HG": {"confluence_score": 0.75, "key_factors": ["OI expansion"], "summary": "x", "watch": "y"},
            "ZS": {"confluence_score": 0.50, "key_factors": [], "summary": "", "watch": ""},
        }
        news_df = pd.DataFrame({
            "title": ["OPEC cuts production", "EIA draw 3M bbl"],
            "source": ["OPEC", "EIA"],
            "source_category": ["macro", "macro"],
            "date": pd.to_datetime(["2026-05-17", "2026-05-16"]),
            "sentiment_score": [0.82, 0.61],
            "markets": [["CL", "HG"], ["CL"]],
        })
        annotated = {}
        retail_df = pd.DataFrame(columns=["symbol","long_pct","short_pct","source","timestamp"])
    return B()


def test_build_context_has_required_keys():
    ctx = build_context(_make_bundle_stub())
    for k in CONTEXT_KEYS:
        assert k in ctx, f"missing key: {k}"


def test_top_markets_sorted_by_confluence():
    ctx = build_context(_make_bundle_stub())
    scores = [m["confluence_score"] for m in ctx["top_markets"]]
    assert scores == sorted(scores, reverse=True)


def test_top_markets_capped():
    ctx = build_context(_make_bundle_stub())
    assert len(ctx["top_markets"]) <= 15


def test_macro_news_present():
    ctx = build_context(_make_bundle_stub())
    assert isinstance(ctx["macro_news"], list)
    assert len(ctx["macro_news"]) > 0


def test_context_serialisable():
    import json
    ctx = build_context(_make_bundle_stub())
    json.dumps(ctx)


def test_sector_summary_present():
    ctx = build_context(_make_bundle_stub())
    assert isinstance(ctx["sector_summary"], dict)
