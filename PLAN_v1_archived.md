---
title: COT Dashboard — Master Design Document
status: PLAN (Phase 0 gate pending)
created: 2026-05-16
authority: User-directed override of Marco hard-rule (see §0)
sources: Williams 1979, Briese 2008, Upperman 2008, Paul 1994, DeMarco 2011
tags: [project, cot, saas, full-stack, design, plan]
---

> **Mandate:** Build a hostable, world-class web platform that mechanizes the commercial-hedger-extreme strategy Larry Williams used to win the 1987 Robbins World Cup, applied to the full CME futures universe on the daily timeframe — with backtest, live signals, replay, and Figma/Linear-grade UX.
>
> **Single source of truth.** This document supersedes any earlier scratch plans. All implementation references this file.

---

## TL;DR

| Item | Decision |
|---|---|
| **Strategy** | `WILLIAMS_COT_SWING_v1` — COT Index ≥80 + UCL penetration + producer/consumer imbalance + 10/18 SMA confirmation. Trail 18MA. Exit on 50% rule. 1% risk per trade. |
| **Universe** | All CME-reported futures (~40 contracts), daily bars |
| **Frontend** | React 19 + Vite + TypeScript + WebGL2 + Zustand + Web Workers |
| **Backend** | FastAPI origin + Rust strategy core (WASM in browser, PyO3 on server) |
| **Hosting** | Vercel (web) + Fly.io (api) + Cloudflare Workers (edge/tile) + R2 (Parquet) |
| **Timeline** | 6 phases over 5 weeks |
| **Hard gate** | Phase 0 walk-forward Sharpe ≥1.0 across half the universe — *no UI built until edge is validated* |
| **Stop-losses** | 30-day time stop · Process stop on any C-grade trading session · $0 capital until backtest validates |

Six open questions in §11 require answers before Phase 0 starts.

---

## 0. Context — Override & Mission Alignment

### 0.1 The override (logged 2026-05-16)

CLAUDE.md hard-rule: *"No new business ideas, SaaS, PropFlow, or income vehicles until first payout received."*

User-directed override. Acknowledged risk: 3–6 weeks of build time pulls focus from LucidFlex eval (currently 9.5% to target, $286/$3,000, consistency 42.66%, 3 active leaks).

### 0.2 Retroactive NECST audit (DeMarco)

| Commandment | Score | Reasoning |
|---|---|---|
| Need | 0.7/1 | Briese/Upperman charge $200–500/mo for similar tooling; market exists. |
| Entry | 0.6/1 | Data pipeline + UX bar = moderate moat. Idea is not novel. |
| Control | 0.9/1 | Own IP, own data store, own hosting. |
| Scale | 1.0/1 | Digital subscription, infinite copies. |
| Time | 0.8/1 | Subscription = passive once built. Ongoing data refresh required. |
| **Total** | **4.0/5** | **Passes NECST gate.** Would have been Marco-approved had it been routed. |

### 0.3 Pre-defined stop-losses (per Jim Paul §1.1)

- **Time stop:** if Phase 0 backtest + Phase 1 data pipeline are not working by 2026-06-15 → pause build, reroute focus to challenge.
- **Process stop:** any C-grade trading session or rule violation during this build window → freeze build for 7 days.
- **Capital stop:** $0 spent on data vendors, hosting, or services until first signal validates in backtest.

---

## 1. Strategy — `WILLIAMS_COT_SWING_v1`

### 1.1 Theoretical foundation (extracted from `raw/books/`)

**Williams — *How I Made One Million Dollars* (1979)**
Commercials are the smart money. Trade *with* commercials at their statistical extremes. Combine COT positioning with seasonal patterns and volatility expansion. He took $10K → $1.1M in 12 months in the 1987 Robbins Cup using aggressive position sizing on a fundamental edge.

**Briese — *The Commitments of Traders Bible* (2008) — the IMPA system**
UCL (Upper Commercial Limit) and LCL (Lower Commercial Limit) are statistically-derived bands on net-commercial position. Penetration of UCL/LCL = "statistical evidence that an imbalance does indeed exist… the market is at the very least vulnerable to a price correction and possibly a significant trend reversal." (Briese, ch.4)

Trigger sequence:
1. Net-commercial position penetrates UCL (or LCL).
2. After penetration, check producer/consumer split: which side is driving the imbalance?
3. Confirmation: daily close > 18-day SMA for two consecutive sessions.
4. Trend confirmed: 10-day SMA crosses above 18-day SMA, both pointing up.
5. Stop: trail under 18-day SMA *on close only* (stop-close-only). "We not only avoid false stop-outs, but we also reduce the frequency of leaving additional money on the table." (Briese, ch.6)
6. Exit: 50% rule — exit when price retraces 50% of the move from entry to highest close.
7. Risk: 10% rule (we will use 2% — see §1.4).

**Upperman — *COT Index* (2008)**
Formula (identical to George Lane's %K stochastic, with net position substituting for price):

```
COT_Index = 100 × (Net_now − Net_min) / (Net_max − Net_min)
```

Look-back: rolling 156-week (3-year) window. Computed separately for commercials, large specs, small specs. Reading >80% = commercial bullish extreme. Reading <20% = commercial bearish extreme.

**Paul — *What I Learned Losing a Million Dollars* (1994)**
"Your exit criteria create a discrete event, ending the position and preventing the continuous process from going on and on." Every signal must ship with a pre-defined invalidation. Define exit *before* entry. Internalize losses → death spiral.

**DeMarco — *The Millionaire Fastlane* (2011)**
The platform itself is the Fastlane vehicle. NECST = 4.0/5. Many traders × subscription = law of effection.

### 1.2 The mechanized signal

**Universe:** all CME-reported futures with continuous COT history ≥ 5 years and ADV above market-specific liquidity floor.

**Bar resolution:** daily settlement. Strategy timeframe: daily. Holding period: 5–40 bars.

**Long signal — all six layers must be true (mirror for shorts):**

| Layer | Rule | Book source |
|---|---|---|
| L1 — Positioning extreme | `COT_Index_Commercials ≥ 80` for most recent CFTC release | Upperman ch.6 |
| L2 — Statistical confirmation | Net-commercial position penetrates UCL (rolling mean + 1.5σ over 156 weeks) | Briese ch.4 |
| L3 — Component imbalance | Commercial *producer* shorts at 3yr low **AND** commercial *consumer* longs at 3yr high (disaggregated report) | Briese ch.5 |
| L4 — Trend trigger | Daily close > 18-day SMA for 2 consecutive sessions | Briese ch.6 |
| L5 — Trend confirmation | 10-day SMA crosses above 18-day SMA, both pointing up | Briese ch.6 |
| L6 — Seasonality booster (optional) | Calendar window has ≥70% positive 15-year historical bias | Williams ch.7 |

**Entry:** market order at next session's open after all required layers confirm.

### 1.3 Data & schedule

- CFTC release: Tuesday snapshot, published Friday 15:30 CT.
- Pipeline runs Friday 16:00 CT via GitHub Actions cron.
- Recompute indicators → write Parquet → write signal summary to Postgres → notify clients via WebSocket (post-MVP) or polling (MVP).

### 1.4 Position sizing (Praveen-safe)

Williams' 10% rule is too aggressive. We use:

- Fixed-fractional: 1% account equity at risk per trade.
- Risk per trade = entry − initial stop (in dollars per contract).
- Contracts = `floor(0.01 × equity / risk_per_contract)`.
- Max 5 concurrent positions.
- Max 2% total at risk across any correlation cluster (e.g. ZC/ZW/ZS = grains).

### 1.5 Stops & exits

| Type | Rule |
|---|---|
| Initial stop | 5-bar swing low **OR** 2× ATR(14), whichever is closer to entry |
| Trending stop | Trail 18-day SMA, stop-close-only |
| 50% rule exit | Retrace 50% of move from entry to highest close → exit |
| Trend break exit | 10 SMA crosses below 18 SMA → exit |
| Signal flip exit | COT Index crosses below 50 → exit |
| Time stop | 40 bars max hold |

**Invalidation tracking:** every signal logs its pre-defined invalidation. If invalidation triggers and we did not exit → flag as discipline failure (process metric, separate from P&L).

### 1.6 Backtest framework

- **Engine:** vectorized Rust core (preferred) or Numba/NumPy Python fallback.
- **Walk-forward only:** 5-year train → 1-year out-of-sample, rolled annually. No in-sample tuning.
- **Cost model:** $4.50 RT commission, 0.1×ATR(14) slippage per side, futures price already includes carry.
- **Pass criteria (per-market scorecard):**
  - Out-of-sample Sharpe ≥ 1.2
  - Out-of-sample profit factor ≥ 1.5
  - Max drawdown ≤ 25%
  - ≥ 30 trades per out-of-sample window
  - Win rate ≥ 40% (trend-following; payoff ratio > win rate is expected)
- **Robustness tests:** parameter perturbation (±20% on every threshold), market exclusion (drop each market once, re-test), regime split (pre/post-2020).
- **Output:** per-contract scorecard. Failed contracts kept on platform for visualization but flagged "do not trade."

### 1.7 What this is NOT

- Not day-trading. Not crypto-style leverage. Not a black-box ML model.
- Not "follow commercials always" — commercials are usually wrong on direction, right on extremes (Briese ch.4).

---

## 2. Engineering Philosophy

The browser is treated as a **rendering runtime, graphics engine, and simulation environment** — not a document viewer.

### 2.1 Layer separation (non-negotiable)

| Layer | Owns | Forbidden |
|---|---|---|
| React | Component tree, route orchestration, accessibility, focus | Direct DOM measurement in render path. Layout-triggering animations. |
| Zustand | Cross-component semantic state (selected market, date range, theme) | Per-frame state. Hover state. |
| Sim engine | Per-frame state — hover lerp, scrub clock, replay | DOM access. Network. |
| Renderer | All chart pixels | Layout. Focus. Accessibility. |
| Workers | Backtest, indicator math, tile decode | UI state. |
| Edge (Cloudflare) | Auth verification, tile routing, edge cache | Persistent storage. |
| Origin (Fly.io) | Auth source of truth, write paths, backtest dispatch | Static asset delivery. |

### 2.2 Performance budgets

| Surface | Budget |
|---|---|
| TTI (cold, M1 broadband) | < 1.5s |
| Frame time steady state | < 8ms p99 |
| Frame time during interaction | < 12ms p99 |
| Initial JS bundle | < 180KB gzipped |
| Worker boot | < 80ms |
| WebGL context create | < 50ms |
| Chart cold render (10K bars) | < 80ms |
| Chart pan (100K-bar buffer) | sub-frame |

### 2.3 Why each optimization matters (one-liner)

- **WebGL for chart pixels** skips Style + Layout + Paint — GPU just composites.
- **React only for orchestration** keeps the JS step bounded to mount/unmount, not every frame.
- **Workers for backtest** keeps main thread under budget during heavy compute.
- **Edge-cached tiles** kills round-trip latency on the most-fetched assets.
- **Fixed-timestep sim** makes replay deterministic — scrub feels like Figma, not a slideshow.
- **Spring-driven motion** (no CSS transitions) keeps animation owned by the sim engine, not the layout engine.

---

## 3. Architecture

### 3.1 System diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        BROWSER (Client)                          │
│                                                                  │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│   │  React 19    │◄──►│  Zustand     │◄──►│  Sim Engine  │      │
│   │ (Orchestrate)│    │  (State)     │    │  (Workers)   │      │
│   └──────┬───────┘    └──────────────┘    └──────┬───────┘      │
│          │                                        │              │
│          ▼                                        ▼              │
│   ┌──────────────────────────────────────────────────┐          │
│   │     Frame Scheduler (rAF + RIC)                   │          │
│   │     Fixed-timestep simulation @ 120Hz logical     │          │
│   │     Variable render @ display refresh             │          │
│   └──────────────┬────────────────────┬──────────────┘          │
│                  │                    │                          │
│                  ▼                    ▼                          │
│       ┌──────────────────┐   ┌──────────────────┐               │
│       │  WebGL2 Renderer │   │  Canvas2D Layer  │               │
│       │  (Price + COT,   │   │  (Crosshair,     │               │
│       │   batched draws) │   │   tooltips, text)│               │
│       └──────────────────┘   └──────────────────┘               │
│                                                                  │
│   ┌──────────────────────────────────────────────────┐          │
│   │   Web Worker Pool (Comlink)                       │          │
│   │   - Backtest worker (WASM Rust core)              │          │
│   │   - Indicator worker                              │          │
│   │   - Tile decoder worker                           │          │
│   └──────────────────────────────────────────────────┘          │
│                                                                  │
└──────────────────────────┬──────────────────────────────────────┘
                           │  HTTP/2 + WebSocket
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                EDGE (Cloudflare Workers)                         │
│   - Auth verification (Clerk JWT)                                │
│   - Tile API: /tile/:market/:from/:to → Parquet column slice     │
│   - Signal API: /signal/:market → recent + history               │
│   - WebSocket: live tick relay (post-MVP)                        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                       ORIGIN (Fly.io)                            │
│                                                                  │
│   ┌──────────────────┐   ┌─────────────────────┐                │
│   │  FastAPI         │◄─►│  Rust Backtest Core │                │
│   │  (Python)        │   │  (single binary,    │                │
│   │                  │   │   PyO3 bindings)    │                │
│   └────────┬─────────┘   └─────────┬───────────┘                │
│            │                       │                             │
│            ▼                       ▼                             │
│   ┌──────────────────┐   ┌─────────────────────┐                │
│   │   Postgres       │   │   R2 / S3           │                │
│   │  (Users, signals,│   │  (Parquet:          │                │
│   │   audit log)     │   │   prices + COT)     │                │
│   └──────────────────┘   └─────────────────────┘                │
└──────────────────────────────────────────────────────────────────┘
                           ▲
                           │  Cron (Friday 16:00 CT)
                           │
┌──────────────────────────┴──────────────────────────────────────┐
│            INGEST PIPELINE (GitHub Actions)                      │
│   1. CFTC COT report (weekly Friday)                             │
│   2. Daily settlement bars (Norgate / Barchart / CME)            │
│   3. Recompute indicators + signals                              │
│   4. Write Parquet + Postgres summary                            │
└──────────────────────────────────────────────────────────────────┘
```

### 3.2 Rendering pipeline

```
data tiles (Parquet column slices)
   ↓
worker: decode → typed arrays (Float32Array OHLCV + COT positions)
   ↓
main thread: shared into renderer geometry buffers (zero-copy)
   ↓
GPU: vertex shader projects bar/line geometry via view matrix
   ↓
GPU: fragment shader applies theme tokens
   ↓
composite with Canvas2D overlay (crosshair, text) via z-stacking
```

- **Candles:** one draw call per market via batched geometry. 10,000 candles = 1 draw call.
- **COT histogram:** instanced rendering. One quad mesh, per-instance attributes (height, color).
- **Axis + crosshair + tooltips:** Canvas2D overlay. Redrawn only on pointer move, not every frame.
- **Dirty-region optimization:** crosshair-only updates do NOT redraw WebGL layer.

### 3.3 Interaction pipeline

```
pointer event (raw)
   ↓
Event batcher (coalesce within frame budget)
   ↓
Pointer state → sim engine input buffer
   ↓
Sim engine: target value updated
   ↓
Spring interpolator: current chases target each frame
   ↓
Renderer reads interpolated value → next frame
```

- **No React state on hover.** Hover lives in the sim engine. React only sees semantic changes.
- **Crosshair latency budget:** 1 frame (≤16.6ms). More than that = engineering bug.
- **Scrub:** pointer-capture + RAF interpolation. Handle never waits on React reconciliation.

### 3.4 Simulation engine

- Fixed-timestep accumulator (Glenn Fiedler "Fix Your Timestep!" pattern).
- Logical step: 1/120s. Render step: display refresh rate (60/120/144Hz adaptive).
- Pure functional state update: `state_{t+1} = f(state_t, input_t, dt)`.
- All animations are spring-driven (stiffness, damping, mass). No easing functions. No CSS transitions.
- Replay clock is deterministic — same seed + same inputs ⇒ bit-identical replay. This is what makes scrub feel like Figma.

### 3.5 Scheduler

| Priority | Work | Mechanism |
|---|---|---|
| 1. Input | Pointer, keyboard, scroll | Event listeners, batched per frame |
| 2. Animation | Spring interpolation, scrub | rAF, fixed-timestep |
| 3. Render | WebGL + Canvas2D composite | rAF, after animation step |
| 4. Idle | Backtest progress, telemetry flush | requestIdleCallback |
| 5. Background | Worker-side compute | Web Workers |

- **Frame budget guard:** if rAF overruns 14ms, skip next non-critical step and warn in dev.
- `startTransition` wraps non-urgent re-renders (filter, market reorder).
- `Suspense` wraps lazy route panels (Backtest tab, Strategy editor).

### 3.6 Animation system

- `useSpring(target, { stiffness, damping, mass, restDelta })` reading from sim engine.
- Master timeline for multi-element transitions. Children stagger via offsets, not setTimeout.
- Motion characters:
  - Page transitions: 400ms, ease-out-quint, with z-translate depth shift.
  - Hover lift: stiffness 300, damping 30.
  - Crosshair snap: stiffness 600, damping 40.
  - Number ticker: 250ms lerp on COT index updates.
- `prefers-reduced-motion`: springs collapse to instant updates.

---

## 4. Design System

### 4.1 Visual tokens

| Token | Value | Use |
|---|---|---|
| Spacing | 4-px grid: 4, 8, 12, 16, 24, 32, 48, 64 | Layout, gutter |
| Type family | Inter Variable + JetBrains Mono | Inter prose, Mono numbers |
| Type scale | 11, 12, 13, 14, 16, 20, 28, 40 | Dense, technical |
| Line height | 1.45 prose, 1.1 numeric | Numbers don't need breathing |
| bg-canvas | #0A0A0B | Near-black, no OLED smear |
| bg-panel | #111114 | Elevated surfaces |
| ink | #E8E8EA | Primary text |
| ink-muted | #8A8A93 | Secondary text |
| Long | #18E08F (electric green) | Status only, never decoration |
| Short | #FF5A5F (warm coral) | Status only |
| Signal pending | #F5A623 (amber) | Status only |
| Elevation 1 | 0 1px 2px rgba(0,0,0,.6) | Cards |
| Elevation 2 | 0 8px 24px rgba(0,0,0,.5) | Modals |
| Radius | 6, 10, 14 | Subtle |
| Motion default | spring(300, 30) | General hover/lift |
| Motion snappy | spring(600, 40) | Crosshair, fine controls |
| Motion gentle | spring(180, 22) | Large surface enter/exit |

### 4.2 Component primitives (hand-rolled, shadcn-lite)

- `Button` — primary, secondary, ghost, destructive
- `Input` — single-line, multi-line, numeric (locale-aware)
- `Select` — keyboard navigable, virtualized at >50 items
- `Dialog` — focus-trapped, escape-closable, portal-rendered
- `Tooltip` — collision-aware, 200ms hover delay, 0ms on focus
- `Toast` — staggered queue, swipe-dismiss
- `Tabs` — indicator spring-animated (not CSS)
- `Chart` — composite: WebGL canvas + Canvas2D overlay + React frame

All primitives: ARIA-correct, keyboard navigable, `prefers-reduced-motion` aware, Storybook/Ladle stories shipped.

### 4.3 Information density

Default screen = 4 live data regions:
1. Market chart (top center, dominant)
2. COT histogram + index (under chart, full width)
3. Signal card (right column)
4. Market list (left column, virtualized)

- Numbers right-aligned, monospace, subtle vertical rules between columns.
- No icons without text labels (exception: universally understood play/pause).

---

## 5. Component Hierarchy

```
<App>
  <Providers>                            // Theme, query client, auth, sim engine
    <Layout>
      <Sidebar>
        <MarketList virtualized />
        <SavedScreens />
      </Sidebar>
      <Main>
        <Toolbar>
          <DateRangePicker />
          <SignalFilter />
          <ReplayControls />              // play, pause, scrub, speed
        </Toolbar>
        <ChartSurface>                    // The hot path
          <Chart>                         // WebGL + Canvas2D composite
            <PricePane />                 // Candles, MAs, signal overlays
            <CotPane />                   // Net positions + COT index
            <SeasonalityPane optional />  // 15yr seasonal overlay
            <Crosshair />                 // Canvas2D
            <Axis />                      // Canvas2D
          </Chart>
          <SignalPanel>
            <SignalCard live />
            <SignalHistory virtualized />
          </SignalPanel>
        </ChartSurface>
        <BottomRail collapsible>
          <BacktestSummary />
          <TradeList virtualized />
        </BottomRail>
      </Main>
    </Layout>
  </Providers>
</App>
```

Per-component contract: every component documents props, state flow, a11y considerations, perf considerations, render strategy, loading states, edge cases — enforced via Storybook/Ladle MDX.

---

## 6. File Structure

```
cot-dashboard/
├── apps/
│   ├── web/                              # React 19 + Vite frontend
│   │   ├── index.html
│   │   ├── vite.config.ts
│   │   ├── src/
│   │   │   ├── main.tsx
│   │   │   ├── app/
│   │   │   │   ├── App.tsx
│   │   │   │   ├── routes.tsx
│   │   │   │   └── providers.tsx
│   │   │   ├── routes/
│   │   │   │   ├── dashboard/
│   │   │   │   ├── market/[symbol]/
│   │   │   │   ├── backtest/
│   │   │   │   ├── replay/
│   │   │   │   └── strategy/
│   │   │   ├── components/
│   │   │   │   ├── chart/                # WebGL chart primitives
│   │   │   │   │   ├── Chart.tsx
│   │   │   │   │   ├── PricePane.tsx
│   │   │   │   │   ├── CotPane.tsx
│   │   │   │   │   ├── Crosshair.tsx
│   │   │   │   │   └── Axis.tsx
│   │   │   │   ├── timeline/
│   │   │   │   ├── signal-card/
│   │   │   │   ├── backtest-table/
│   │   │   │   └── primitives/           # Button, Input, Dialog, etc.
│   │   │   ├── engine/                   # Sim + render
│   │   │   │   ├── scheduler.ts          # rAF + RIC orchestration
│   │   │   │   ├── sim/
│   │   │   │   │   ├── state.ts
│   │   │   │   │   ├── reducer.ts
│   │   │   │   │   ├── spring.ts
│   │   │   │   │   └── timeline.ts
│   │   │   │   ├── render/
│   │   │   │   │   ├── webgl/
│   │   │   │   │   │   ├── context.ts
│   │   │   │   │   │   ├── shaders/
│   │   │   │   │   │   ├── batches/
│   │   │   │   │   │   └── viewport.ts
│   │   │   │   │   └── canvas2d/
│   │   │   │   └── input/
│   │   │   │       ├── pointer.ts
│   │   │   │       └── keyboard.ts
│   │   │   ├── workers/
│   │   │   │   ├── backtest.worker.ts
│   │   │   │   ├── indicator.worker.ts
│   │   │   │   └── tile.worker.ts
│   │   │   ├── state/                    # Zustand stores
│   │   │   │   ├── markets.ts
│   │   │   │   ├── signals.ts
│   │   │   │   ├── ui.ts
│   │   │   │   └── auth.ts
│   │   │   ├── api/                      # Typed fetch client
│   │   │   │   ├── client.ts
│   │   │   │   └── schemas.ts
│   │   │   ├── design/                   # Design system
│   │   │   │   ├── tokens.css
│   │   │   │   ├── typography.css
│   │   │   │   ├── motion.ts
│   │   │   │   └── theme.ts
│   │   │   └── lib/
│   │   └── tests/
│   │
│   └── api/                              # Origin server
│       ├── src/
│       │   ├── main.py
│       │   ├── routes/
│       │   │   ├── markets.py
│       │   │   ├── tiles.py
│       │   │   ├── signals.py
│       │   │   ├── backtest.py
│       │   │   └── auth.py
│       │   ├── services/
│       │   │   ├── parquet_store.py
│       │   │   ├── cot_indicators.py
│       │   │   └── signal_engine.py
│       │   └── models/
│       ├── tests/
│       └── pyproject.toml
│
├── packages/
│   ├── strategy-core/                    # Rust workspace
│   │   ├── Cargo.toml
│   │   ├── src/
│   │   │   ├── lib.rs
│   │   │   ├── indicators/
│   │   │   │   ├── cot_index.rs
│   │   │   │   ├── ucl_lcl.rs
│   │   │   │   ├── sma.rs
│   │   │   │   └── seasonality.rs
│   │   │   ├── backtest/
│   │   │   │   ├── engine.rs
│   │   │   │   ├── walk_forward.rs
│   │   │   │   └── metrics.rs
│   │   │   └── williams/
│   │   │       └── signal.rs             # The mechanized strategy
│   │   ├── wasm/                         # wasm-bindgen output for browser
│   │   └── python/                       # PyO3 bindings for server
│   │
│   ├── ingest/                           # Python ingest pipeline
│   │   ├── cftc_cot.py
│   │   ├── prices.py
│   │   └── normalize.py
│   │
│   └── shared-types/                     # TS ↔ Pydantic mirror
│
├── infra/
│   ├── fly.toml
│   ├── cloudflare-worker/
│   ├── github-actions/
│   │   └── friday-ingest.yml
│   └── terraform/                        # post-MVP
│
├── docs/
│   ├── design.md → ../wiki/projects/cot-dashboard/design.md  (this file)
│   └── runbooks/
│
├── package.json                          # pnpm workspaces
├── pnpm-workspace.yaml
└── README.md
```

---

## 7. Build Phases

### Phase 0 — Strategy validation (Week 0, BLOCKING GATE)

- Pull free CFTC COT data + free daily futures bars (Yahoo/Stooq or CME direct).
- Implement `WILLIAMS_COT_SWING_v1` in a Jupyter notebook (Python, NumPy/Pandas).
- Walk-forward backtest across full CME universe.
- **PASS GATE:** out-of-sample Sharpe ≥ 1.0 across ≥50% of liquid universe. Otherwise project pauses. Williams' edge may not generalize to 2026 markets — and we will not build UI on a broken edge (Jim Paul rule).

### Phase 1 — Data spine (Week 1)

- Parquet store on R2.
- Friday cron pulls CFTC + price vendor.
- API tile endpoint: `/tile/:market/:from/:to`.
- Auth via Clerk free tier.

### Phase 2 — Core renderer (Week 2)

- Vite + React 19 + TS scaffold.
- WebGL chart primitive: candles + MAs + COT histogram.
- Pointer + crosshair.
- Design tokens + 5 base primitives (Button, Input, Select, Dialog, Tooltip).

### Phase 3 — Strategy engine (Week 3)

- Rust core: indicators + signal generator.
- WASM build for browser. PyO3 build for server.
- Server-side backtest endpoint.
- Backtest tab + trade list.

### Phase 4 — Simulation + replay (Week 4)

- Fixed-timestep sim engine.
- Replay clock, scrub, speed controls.
- Spring-driven hover, crosshair, transitions.

### Phase 5 — Polish + hosting (Week 5)

- Auth + paywall (Stripe).
- Deploy: Vercel (web), Fly.io (api), Cloudflare (edge).
- Landing page.
- First paying user.

### Phase 6 — Twitter content layer (parallel, continuous from Week 1)

- Every phase ships a Twitter thread.
- "Reverse-engineering Williams' world championship strategy. Open build."
- This is the user acquisition engine and the Content + Coaching vehicle.

---

## 8. Performance Tactics

- **Code splitting:** route-level via React.lazy + Suspense. Strategy editor and Backtest tab not in initial bundle.
- **modulepreload:** above-the-fold routes only.
- **Asset preloading:** WASM core preloaded, not instantiated until first backtest.
- **Immutable caching:** versioned filenames, 1-year cache, content-hash invalidation.
- **CDN:** Cloudflare edge for static + tile API.
- **Memoization:** `useMemo` only where profiled. `React.memo` on chart frame.
- **Virtualization:** market list, trade list, signal history.
- **Idle hydration:** below-the-fold panels hydrate on `requestIdleCallback`.
- **Zero raster images** in the product. Charts vector. Logos inline SVG.

---

## 9. Scalability Roadmap

| Stage | Users | Architecture change |
|---|---|---|
| MVP | 1–10 | Single Fly.io machine. R2 for data. No queue. |
| Early | 10–100 | Redis tile cache. Postgres replica. |
| Growth | 100–1K | Backtest worker pool (Fly autoscale). WebSocket relay for live ticks. |
| Scale | 1K–10K | Multi-region edge. Postgres → CockroachDB or partitioned. Content-addressable backtest cache. |
| Big | 10K+ | Strategy marketplace. Users author + sell strategies. Revenue share. |

---

## 10. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Strategy doesn't backtest profitably in 2026 markets | Medium | Project stops | Phase 0 gate. No UI on broken edge. |
| Data vendor costs exceed runway | Medium | Build stalls | Free CFTC + free daily bars for MVP. Pay only after first customer. |
| Build time bleeds into LucidFlex eval | High | Mission failure | 30-day time stop. Process stop on any C-grade session. |
| WebGL complexity slows shipping | Medium | Phase 4 slips | Canvas2D fallback. WebGL is upgrade, not gate. |
| User acquisition stalls (no audience) | High | No revenue | Phase 6 content starts Week 1, not Week 5. Build in public. |
| CFTC schema changes | Low | Pipeline break | Schema-validated ingest. Daily sanity-check email. |

---

## 11. Open Questions — required before Phase 0

These need user input *before* any code is written:

1. **Strategy bias:** ship `WILLIAMS_COT_SWING_v1` only, OR also ship a counter-strategy ("trade *against* small specs at extremes" — also documented by Briese) for comparison?
2. **Data vendor:** Norgate ($30/mo) vs Barchart ($100/mo) vs free Stooq + manual CME scrape (0$, messier)?
3. **Auth provider:** Clerk (fast, $25/mo at scale) vs Lucia (free, self-rolled)?
4. **Backtest core language:** Rust (fast, harder build) vs Python+Numba (slower, instant iteration)?
5. **Pricing model:** flat $29/mo? Tiered ($0 for 10 markets / $49 full universe)? Lifetime $499?
6. **First-customer commitment:** ship for Praveen + 10 Twitter followers, OR target 100 paying users in 90 days?

---

## 12. Quality Bar

The implementation must resemble the engineering quality of Figma, Linear, Stripe, Excalidraw — not a generic SaaS frontend. Specifically:

- Every interaction feels immediate, tactile, intentional, fluid.
- Motion communicates hierarchy, causality, spatial relationship, system state — never decoration.
- Information dense without clutter.
- 60+ fps under load. Degrades gracefully on weaker hardware.
- Accessible: keyboard nav everywhere, ARIA correct, WCAG AA contrast.

Write code like a Staff frontend engineer + a browser rendering engineer + a graphics systems engineer + a design systems architect.

---

## Links

- [[wiki/trading/concepts/override-log]] — Marco override entry with stop-losses
- [[wiki/income/content-creator]] — Twitter content strategy this build feeds
- [[wiki/trading/concepts/challenge-state]] — LucidFlex eval state (check before every build session)
- [[wiki/sources/fastlane-book]] — NECST framework
- Source PDFs in `raw/books/`:
  - `Larry_Williams_How_I_made_one_million_dollars_last.pdf`
  - `The Commitments of Traders Bible How... (z-lib.org).pdf`
  - `Commitments of Traders Strategies fo... (Z-Library).pdf`
  - `What I Learned Losing a Million Dolla... (z-lib.org).pdf`
  - `the-millionaire-fastlane.pdf`
