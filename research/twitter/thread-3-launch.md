---
thread: 3 of 3
topic: COT_LENS_v1 is live — here's how I use it
target_post_date: launch week 3 (Friday after CFTC release)
status: draft
---

# Thread 3 — `COT_LENS_v1` is live

## Tweet 1
Shipped: COT_LENS_v1 — a positioning intelligence dashboard for CME physicals.

Free during beta. No login. Public URL: [url]

What it is, what it isn't, and how I'll use it this week 🧵

## Tweet 2
The Friday routine, in 90 seconds:

1) Open / (Today). See markets ranked by zones triggered.
2) Click whichever has 3+ zones. Chart + position panes + news rail load.
3) Read the headlines pinned to position shifts. Form a thesis.
4) Cross-check on the Heatmap. Done.

## Tweet 3
The five attention lenses:

A1 — Extreme positioning (COT idx ≥ 90 / ≤ 10)
A2 — Price divergence (52w extreme + opposite-direction net move)
A3 — Sector outlier (>1.5σ from sector median)
A4 — Momentum shift (4w COT idx ROC in top/bottom decile)
A5 — Hedger/spec imbalance at opposite extremes

## Tweet 4
This week's top market: [SYMBOL] with [N] zones.

[1-2 sentence read of WHY commercials are positioned this way, sourced from the news pins on the chart]

Screenshot ⬇️
[chart screenshot of /market/[SYMBOL] showing zones + news pins]

## Tweet 5
What this is NOT:
• Not a signal service. No buy/sell calls. No backtest in the marketing.
• Not an LLM commentary product. Every word is data or a primary source.
• Not a database. CFTC.gov is free.
• Not for Bloomberg subscribers.

## Tweet 6
Tech under the hood (for the engineering folks):

Frontend: SvelteKit + Svelte 5 runes + Canvas2D chart with custom sim engine (fixed-timestep 120Hz + springs)
Backend: FastAPI + pandas, in-memory bundle, /refresh endpoint
Data: CFTC + Yahoo Finance + 5 macro calendars, all free

## Tweet 7
Interactive chart: drag pan, wheel zoom (cursor-relative), shift+wheel horizontal pan, arrow keys step, +/- zoom, esc resets. Crosshair with date/price/COT axis labels. News pins are clickable — opens trafilatura-extracted article in an in-app drawer.

## Tweet 8
Performance: TTI < 1.5s on M1 broadband. p99 frame time < 12ms during interaction. Single rAF loop, fixed-timestep sim, render isolation from any React-style reconciliation. WebGL upgrade ready behind a flag.

## Tweet 9
Roadmap (in order):

v1.1: User-defined zone thresholds
v1.2: Sector heatmap with magnitude shading (shipped)
v2.0: TFF report ingest (financial futures — equities, rates, FX)
v2.1: User watchlists + Friday email digest
v2.2: Real-time news push (WebSocket)

## Tweet 10
Pricing: free during beta. After:
• Free tier: 5 markets, today + heatmap
• $19/mo: full universe, divergence scanner, news reader, weekly digest

If you'd pay, reply with your most-traded contract. If you wouldn't, reply with what's missing — I read every one.

## Tweet 11
Honest acknowledgment: this is v1 of a pivot. The original plan was to ship a mechanized auto-trading strategy. It failed the backtest gate (thread 1).

Pivoting on a failed gate is a feature, not a bug. The product is the visual surface — that survived intact.

## Tweet 12
Links:
• App: [url]
• Code: [repo]
• Phase 0 findings: [findings.md link]
• Master design doc: [PLAN.md link]

Built in public. AMA on the design choices, the failed strategy, or the news correlator architecture.

---

# Thread notes

- Length: 12 tweets, ~2,000 chars.
- Tweet 4 needs a real screenshot — wait until Friday morning CFTC release lands and pick the actual top market.
- Tweet 10 has the pricing CTA — keep it conversational, not pushy.
- Tweet 11 acknowledges the pivot — important for credibility, leans into the build-in-public ethos.
- Post Friday 4:30pm CT (right after CFTC release).
