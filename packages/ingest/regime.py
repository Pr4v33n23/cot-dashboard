"""Per-symbol HMM regime detector using hmmlearn GaussianHMM."""
from __future__ import annotations
import pickle
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from hmmlearn import hmm

N_STATES = 4
MIN_BARS = 200
N_RESTARTS = 5

warnings.filterwarnings("ignore", category=RuntimeWarning)


def build_feature_matrix(df: pd.DataFrame) -> np.ndarray:
    """4-feature stationary matrix: log_return, cot_net_change_pct, oi_change_pct, vol_ratio."""
    close = pd.to_numeric(df["close"], errors="coerce")
    log_ret = np.log(close / close.shift(1)).values

    market_type = str(df["market_type"].iloc[0]) if "market_type" in df.columns else "physical"
    if market_type == "physical":
        net = df["net_commercials"].fillna(0)
    else:
        net = df["lf_long"].fillna(0) - df["lf_short"].fillna(0)

    cot_net_chg = net.pct_change().replace([np.inf, -np.inf], np.nan).fillna(0).values

    oi = df["open_interest"].ffill()
    oi_chg = oi.pct_change().replace([np.inf, -np.inf], np.nan).fillna(0).values

    lr = pd.Series(log_ret)
    vol5 = lr.rolling(5).std().values
    vol20 = lr.rolling(20).std().values
    with np.errstate(invalid="ignore", divide="ignore"):
        vol_ratio = np.where(vol20 > 0, vol5 / vol20, 1.0)

    return np.column_stack([log_ret, cot_net_chg, oi_chg, vol_ratio])


def fit_hmm(X: np.ndarray) -> hmm.GaussianHMM | None:
    best_model, best_score = None, -np.inf
    for seed in range(N_RESTARTS):
        try:
            model = hmm.GaussianHMM(
                n_components=N_STATES, covariance_type="full",
                n_iter=1000, random_state=seed, verbose=False,
            )
            model.fit(X)
            score = model.score(X)
            if score > best_score:
                best_score, best_model = score, model
        except Exception:
            continue
    return best_model


def label_states(
    model: hmm.GaussianHMM,
    X: np.ndarray,
    df: pd.DataFrame,
) -> dict[int, str]:
    """Map HMM state indices to semantic labels."""
    states = model.predict(X)
    means: dict[int, tuple[float, float]] = {}
    for s in range(N_STATES):
        mask = states == s
        if mask.sum() == 0:
            means[s] = (0.0, 0.0)
            continue
        means[s] = (float(X[mask, 0].mean()), float(X[mask, 1].mean()))

    sorted_by_ret = sorted(means, key=lambda s: means[s][0], reverse=True)
    mapping: dict[int, str] = {}
    used: set[str] = set()
    candidates = ["trending", "accumulation", "distribution", "ranging"]
    for rank, state in enumerate(sorted_by_ret):
        ret, cot = means[state]
        if rank == 0 and "trending" not in used:
            label = "trending"
        elif cot > 0.01 and "accumulation" not in used:
            label = "accumulation"
        elif cot < -0.01 and "distribution" not in used:
            label = "distribution"
        else:
            label = next((c for c in candidates if c not in used), "ranging")
        used.add(label)
        mapping[state] = label
    return mapping


def annotate_regimes(df: pd.DataFrame, model_cache_dir: Path | None = None) -> pd.DataFrame:
    out = df.copy()
    out["regime_label"] = None
    out["regime_proba"] = [None] * len(out)
    out["regime_weeks"] = 0

    if len(df) < MIN_BARS:
        return out

    X = build_feature_matrix(df)
    valid_mask = ~np.isnan(X).any(axis=1)
    if valid_mask.sum() < MIN_BARS:
        return out

    X_valid = X[valid_mask]
    model = fit_hmm(X_valid)
    if model is None:
        return out

    state_map = label_states(model, X_valid, df.iloc[valid_mask.nonzero()[0]])
    posteriors = model.predict_proba(X_valid)
    raw_states = model.predict(X_valid)
    labels = [state_map.get(s, "ranging") for s in raw_states]

    label_arr = np.full(len(df), None, dtype=object)
    proba_arr = np.full((len(df), N_STATES), np.nan)
    label_arr[valid_mask] = labels
    proba_arr[valid_mask] = posteriors

    streak = 0
    weeks = np.zeros(len(df), dtype=int)
    for i in range(len(label_arr)):
        if i == 0 or label_arr[i] != label_arr[i - 1]:
            streak = 1
        else:
            streak += 1
        weeks[i] = streak

    out["regime_label"] = label_arr
    out["regime_proba"] = [list(p) if not np.isnan(p).any() else None for p in proba_arr]
    out["regime_weeks"] = weeks

    if model_cache_dir is not None:
        model_cache_dir.mkdir(parents=True, exist_ok=True)
        sym = str(df["symbol"].iloc[0])
        with open(model_cache_dir / f"regime_{sym}.pkl", "wb") as f:
            pickle.dump({"model": model, "state_map": state_map}, f)

    return out


def annotate_all_regimes(
    annotated: dict[str, pd.DataFrame],
    model_cache_dir: Path | None = None,
) -> dict[str, pd.DataFrame]:
    result = {}
    for sym, df in annotated.items():
        result[sym] = annotate_regimes(df, model_cache_dir)
    return result
