---
title: Phase 0 findings — WILLIAMS_COT_SWING_v1
date: 2026-05-16
status: GATE FAIL
authority: PLAN.md §0.3 stop-loss + §7 Phase 0 protocol
---

# Phase 0 — gate FAIL

Out-of-sample Sharpe ≥ 1.0 across ≥ 50% of the liquid universe (PLAN §7 Phase 0): **not met**. 0 of 23 physical contracts qualify. Best market sharpe: 0.44 (Cotton, 2 trades).

Per PLAN §0.3 stop-loss protocol: **do not proceed to Phase 1.** This file documents what was tested, what failed, and what the honest options are.

---

## What was built

| Component | Status |
|---|---|
| Universe — 23 physicals (grains, energy, metals, softs, meats) | ✓ |
| CFTC disaggregated futures-only ingest, 2010–2025 (835 weeks × 23 = 19K rows) | ✓ |
| Daily-bar ingest via Yahoo Finance — 23 contracts × ~6500 bars = 148K rows | ✓ |
| Forward-fill weekly COT → daily bars with +3-day release offset (no look-ahead) | ✓ |
| Indicators: COT Index (3y), UCL/LCL (μ±1.5σ, 3y), SMA(10/18), ATR(14) | ✓ |
| Six-layer signal generator (L1 extreme → L2 UCL break → L3 component imbalance → L4 trend trigger → L5 trend confirm) | ✓ |
| Vectorized backtest: 1% risk, ATR-based initial stop, trail 18-SMA stop-close-only, 50% rule, trend break, COT flip, 40-bar time stop | ✓ |
| Walk-forward harness: 5y warmup → 1y OOS, rolled annually | ✓ |
| §1.6 scorecard + project-level gate | ✓ |

## Deviations from PLAN.md

These are documented changes made during Phase 0, not silent drift:

1. **Price vendor: Stooq → Yahoo Finance.** Stooq added per-symbol captcha + apikey requirement in 2025, breaking the "free" assumption. yfinance preserves the §0.3 capital stop (still $0 spend).
2. **Universe restricted to physicals only.** The CFTC disaggregated report uses commercial/non-commercial categories that map onto physical hedgers but NOT onto financial futures (equity indices, rates, FX). Financials use the separate TFF report with Dealer/Asset Manager categories. The Williams/Briese commercial-hedger framework is theoretically valid only on physicals.
3. **L3 interpretation: literal 3y min/max → top/bottom decile of 3y range.** Literal min/max yielded near-zero signals across the universe (PM long/short rarely set a new 3y extreme on the exact bar all other layers fire). Briese's "near the extreme" language reads as decile-bracket, not literal extreme. This is the only interpretation choice that could be called tuning — but the threshold (10th/90th pctile) was set a priori, not optimized.
4. **CFTC schema fix.** Date column renamed in 2015 (`Report_Date_as_MM_DD_YYYY` → `Report_Date_as_YYYY-MM-DD`). Switched to the stable `As_of_Date_In_Form_YYMMDD` integer field.
5. **50% rule MFE gate.** Briese's 50% retracement rule, taken literally, fires on any intrabar wiggle (median hold 2 bars). Added a minimum-MFE gate (MFE ≥ 1×ATR) before the rule activates — this is a literal-interpretation bug fix, not parameter tuning.

## Results

OOS walk-forward (5y warmup → 1y rolled OOS, 2015–2025):

| Symbol | Trades | Win rate | Profit factor | Sharpe (OOS) | Max DD | Total PnL ($) |
|---|--:|--:|--:|--:|--:|--:|
| CT | 2 | 100% | ∞ | 0.44 | 0.4% | 797 |
| CC | 8 | 63% | 13.7 | 0.28 | 7.3% | 48,130 |
| ZS | 2 | 0% | 0.0 | 0.26 | 0.6% | -577 |
| LE | 7 | 29% | 1.4 | 0.25 | 7.5% | 1,884 |
| ZL | 8 | 75% | 17.1 | 0.22 | 6.5% | 13,745 |
| ZM | 5 | 60% | 1.3 | 0.20 | 9.5% | 764 |
| ZC | 9 | 56% | 0.9 | 0.19 | 2.7% | -236 |
| ZO | 12 | 50% | 1.3 | 0.02 | 9.6% | 2,597 |
| (and 7 markets with 0 trades — CL, NG, RB, HO, GC, SI, ZR) | | | | | | |
| (and 8 markets with negative Sharpe) | | | | | | |
| **Universe total** | **97** | **40%** | — | **best 0.44** | — | **-5,273** |

Required to pass per PLAN §1.6: Sharpe ≥ 1.2 (gate: ≥ 1.0), profit factor ≥ 1.5, max DD ≤ 25%, ≥ 30 trades per OOS window, win rate ≥ 40%.

Nothing comes close on Sharpe. Trade counts are 2 orders of magnitude below the per-window requirement.

## What the data is telling us

1. **Energy markets have ~zero L3 signals.** Producer/Merchant longs and shorts in CL/NG/RB/HO don't reach decile extremes during the same window where commercials are net-extreme. Likely cause: swap-dealer dominance in energy markets has decoupled the Producer/Merchant book from "real" commercial positioning. The original Briese framework was written before swap dealers were broken out (pre-2008 the Legacy report lumped them with commercials).

2. **Soft ag (CC, ZL, ZM) shows the best edge — but at 5–12 trades, not statistically meaningful.** Direction is right (positive PnL, ≥60% winrate), magnitude is right (PFs of 13+ on the winners), but the sample is far too small to commit capital.

3. **The strategy is fundamentally low-frequency.** Six AND-ed layers on weekly COT releases gate down to ~2–13 trades per market over 10 OOS years. The §1.6 pass criterion of ≥ 30 trades per *1-year* window is structurally incompatible with the published framework. Either the criterion is wrong, or the strategy needs more triggers.

4. **The edge is consistent with documented decay of the commercial-extreme thesis.** Multiple academic studies (e.g., Sanders, Boris, Manfredo 2009; Bohl & Stephan 2013) have shown the commercial-positioning edge weakened materially after 2008 — coinciding with index investment growth (CFTC's "Index Trader Supplement" was added in 2007 for that reason) and post-Dodd-Frank swap-dealer reporting. The Williams 1987 / Briese 2008 / Upperman 2008 framework was largely built on a regime that no longer exists.

## Options

Per PLAN §0.3, the explicit stop-loss is now triggered. Three honest paths:

### A. Respect the stop-loss (recommended)

Pause this build. Reroute focus to LucidFlex eval per PLAN §0.3. Ship a Twitter thread documenting the negative result (PLAN §7 Phase 6 still applies — build in public means publishing what *didn't* work too). Marco was right; the override should be reversed.

The repo is left in a runnable state. If a future trader wants to test a different strategy on the same plumbing, the ingest + indicator + backtest scaffolding survives.

### B. Targeted v1.1 iteration (≤ 2 sessions, hard stop)

Two literature-justified modifications worth one batch of effort:
1. **Add L6 (seasonality booster from Williams ch.7).** Skipped in v1. Williams used seasonal bias as a primary edge alongside COT. Adding it could double the signal rate AND act as an additional regime filter.
2. **Reformulate L3 as "Producer/Merchant net change YoY" instead of percentile of absolute level.** Briese's actual focus is on commercial *behavior change*, not absolute position level.

If v1.1 doesn't pass after one targeted iteration, revert to option A. No further work.

### C. Pivot strategy (DO NOT — out of scope)

Switching to a fundamentally different strategy is outside the Phase 0 mandate and would invalidate the override. Marco hard-rule applies again.

## Recommendation

**Option A.** The data says the edge isn't there at the literature thresholds. We have one Twitter thread of honest research and no build debt. LucidFlex challenge resumes Monday.

## Repro

```bash
cd cot-dashboard
.venv/bin/python -c "
import sys; sys.path.insert(0, 'packages')
from pathlib import Path
from ingest.universe import UNIVERSE
from ingest import cftc_cot, prices, normalize, indicators, signal, backtest, metrics
cot = cftc_cot.load_universe(range(2010, 2026), UNIVERSE, Path('research/data/cache'))
px  = prices.load_universe(UNIVERSE, Path('research/data/cache'))
merged = normalize.join_cot_to_prices(px, cot)
annotated = {sym: signal.annotate_signals(indicators.add_all_indicators(g.reset_index(drop=True)))
             for sym, g in merged.groupby('symbol') if not g['net_commercials'].isna().all()}
results = {s: backtest.walk_forward(g, next(c for c in UNIVERSE if c.symbol==s)) for s,g in annotated.items()}
cards = [metrics.score(s, r.to_trades_df(), r.equity_curve) for s,r in results.items()]
print(metrics.universe_gate(cards))
"
```
