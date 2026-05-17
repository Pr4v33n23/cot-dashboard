---
thread: 1 of 3
topic: Why mechanized COT strategies don't work in 2026 — and what does
target_post_date: launch week 1
status: draft
---

# Thread 1 — Why mechanized COT strategies don't work in 2026 (and what does)

## Tweet 1
I just spent a week mechanizing Larry Williams' 1987 World Cup COT strategy.

Backtested it on 23 CME physicals, 15 years of disaggregated futures-only data, walk-forward, all the boring stuff.

Best market: Sharpe 0.44, 2 trades.

A thread on what happened and what I'm building instead. 🧵

## Tweet 2
The setup: Williams won the 1987 Robbins Cup ($10K → $1.1M) by trading WITH commercials at statistical extremes. Briese (2008) formalized it with UCL/LCL bands. Upperman (2008) added the COT Index.

The premise: smart-money hedgers are right at extremes. Bet with them.

## Tweet 3
I encoded the full six-layer signal:
L1: COT Index ≥ 80
L2: net commercial penetrates UCL (μ+1.5σ, 156wk)
L3: producer shorts at 3y low + consumer longs at 3y high
L4: close > 18-SMA, 2 consecutive sessions
L5: 10-SMA crosses 18-SMA, both rising
L6: optional seasonality

## Tweet 4
Tested on 23 physical CME contracts, 2010–2025, walk-forward (5y warmup → 1y OOS rolled annually).

Pass criteria (from PLAN.md):
• Sharpe ≥ 1.2 per market
• Profit factor ≥ 1.5
• Max DD ≤ 25%
• ≥ 30 trades per OOS window
• Win rate ≥ 40%

## Tweet 5
Results:
• 0 of 23 markets passed
• Best market: CT, Sharpe 0.44, 2 trades
• Universe total: 97 trades, 40% winrate, -$5,273 PnL
• Energy (CL/NG/RB/HO) generated ZERO signals across 15 years

Honest, ugly negative result. Repo: github.com/[soon]

## Tweet 6
Why did it fail? Three things, same direction:

1) The framework was never a trigger system. Williams: "I lean with commercials." Briese: "commercials are usually wrong on direction, right on extremes." We encoded it as a precise AND-gate. That was a misreading.

## Tweet 7
2) The commercial-extreme edge has decayed. Multiple studies post-2010 (Sanders 2009, Bohl & Stephan 2013) show the signal weakened after index investment growth + Dodd-Frank swap-dealer reporting. The 2008-era framework was built on a regime that no longer exists.

## Tweet 8
3) The paid-market truth: Briese sells *Bullish Review* for $360/yr. Upperman sells *Insider Capital Group* for $720/yr. NEITHER generates trade signals.

They're dashboards. Positioning history, divergence callouts, sector heatmaps, weekly commentary.

That's the actual market.

## Tweet 9
So I'm pivoting. Same data pipeline. Different product surface.

`COT_LENS_v1` — a positioning intelligence dashboard.

Five "attention lenses" instead of one strategy:
A1 extreme · A2 divergence · A3 sector outlier · A4 momentum · A5 hedger/spec imbalance

Zero buy/sell signals.

## Tweet 10
Plus the differentiator: a deterministic macro news correlator. Free CFTC + free Yahoo news + USDA WASDE + EIA + FOMC + OPEC calendars, all pinned to the same chart timeline.

No LLM. Keyword taxonomy → market mapping. The trader sees the headline + source, supplies the meaning.

## Tweet 11
Architecture: SvelteKit + Canvas2D chart engine + FastAPI origin + Python data pipeline.

Performance budget: < 8ms p99 frame time, < 1.5s TTI cold.

Quality bar: Figma / Linear / Stripe / Excalidraw — not generic SaaS frontend.

## Tweet 12
Why share the negative result?

Because most COT content online is "this strategy gives 80% winrate, $X/mo." Almost all of it is post-hoc fit.

The honest framing: COT is *positional context*. It tells you WHO is loaded up. The trader still does the trading.

## Tweet 13
Next thread: the news correlator design — pinning macro events to position shifts without an LLM, using a static keyword taxonomy + free RSS feeds.

If you trade futures and want positioning context faster than your COT spreadsheet → reply with your most-traded contract and I'll DM the beta link when it's up.

---

# Thread notes (not posted)

- Length: 13 tweets, ~2,400 chars. Fits within X's thread sweet spot.
- CTAs: repo link in tweet 5 once GitHub is public, beta DM in last tweet.
- Tone: technical, honest about failure, no hype.
- Hook test: tweet 1 leads with concrete failure metrics — should beat
  generic "I built a trading bot" openers.
- Best posting time: Tue–Thu, 13:00–16:00 ET for finance Twitter.
