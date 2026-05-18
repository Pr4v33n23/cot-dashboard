import numpy as np
import pandas as pd
import pytest
from ingest.regime import (
    build_feature_matrix,
    fit_hmm,
    label_states,
    annotate_regimes,
    MIN_BARS,
)

def _make_df(n=300, market_type="physical"):
    np.random.seed(42)
    idx = pd.date_range("2020-01-01", periods=n, freq="W")
    return pd.DataFrame({
        "date": idx, "symbol": "CL", "market_type": market_type,
        "close": 70 + np.cumsum(np.random.randn(n) * 0.5),
        "net_commercials": np.sin(np.arange(n) / 20) * 50000,
        "lf_long": 100000 + np.random.randn(n) * 5000,
        "lf_short": 200000 + np.sin(np.arange(n)/15) * 50000,
        "open_interest": 400000 + np.arange(n) * 200,
        "cot_index_comm": np.clip(np.arange(n) / 3.0, 0, 100),
    })

def test_build_feature_matrix_shape():
    df = _make_df(n=300, market_type="physical")
    X = build_feature_matrix(df)
    assert X.shape[1] == 4  # log_return, cot_net_change_pct, oi_change_pct, vol_ratio

def test_build_feature_matrix_financial():
    df = _make_df(n=300, market_type="financial")
    X = build_feature_matrix(df)
    assert X.shape[1] == 4

def test_fit_hmm_returns_model():
    df = _make_df(n=300)
    X = build_feature_matrix(df)
    valid = ~np.isnan(X).any(axis=1)
    model = fit_hmm(X[valid])
    assert model is not None
    assert model.n_components == 4

def test_label_states_returns_known_labels():
    df = _make_df(n=300)
    X = build_feature_matrix(df)
    valid = ~np.isnan(X).any(axis=1)
    model = fit_hmm(X[valid])
    mapping = label_states(model, X[valid], df.iloc[valid.nonzero()[0]])
    assert set(mapping.values()).issubset({"trending","accumulation","distribution","ranging"})

def test_annotate_regimes_adds_columns():
    df = _make_df(n=300)
    result = annotate_regimes(df)
    assert "regime_label" in result.columns
    assert "regime_proba" in result.columns
    assert "regime_weeks" in result.columns

def test_thin_data_skipped():
    df = _make_df(n=MIN_BARS - 1)
    result = annotate_regimes(df)
    assert result["regime_label"].isna().all()
