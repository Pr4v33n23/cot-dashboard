---
title: COT Dashboard — `COT_LENS_v1` (positioning intelligence + news correlator)
status: APPROVED — Phase 1 in progress
created: 2026-05-16
approved: 2026-05-16
authority: User-directed pivot following Phase 0 gate failure (see research/findings.md)
sources: Williams 1979, Briese 2008, Upperman 2008, Paul 1994, DeMarco 2011
tags: [project, cot, saas, full-stack, design, plan]
supersedes: PLAN_v1_archived.md
---

> **Mandate:** Build a hostable, world-class web platform that surfaces commercial-hedger positioning context for the CME physicals universe, paired with a deterministic macro news correlator that pins the news driving each position shift onto the same timeline. No LLM commentary, no auto-signals — the product is the *visual surface*, and the trader supplies the interpretation.
>
> **Single source of truth.** This document supersedes [PLAN_v1_archived.md](PLAN_v1_archived.md), which tested COT-as-mechanized-strategy and failed the Phase 0 gate (best Sharpe 0.44, 0/23 markets qualifying). All implementation references this file.

---

## TL;DR

| Item | v1 (signal engine) — failed gate | v2 (positioning lens) |
|---|---|---|
| **Product** | Mechanized auto-signals on 6-layer Williams strategy | Decision-support dashboard for discretionary traders |
| **Promised value** | "Take these trades" | "Here is where positioning is *interesting* today" |
| **Phase 0 gate** | Sharpe ≥ 1.0 on backtest — FAILED | None. There is no signal to backtest. |
| **Frontend** | React 19 + Vite + WebGL2 + Canvas2D (unchanged) | React 19 + Vite + WebGL2 + Canvas2D (unchanged) |
| **Backend** | FastAPI + Rust strategy core | FastAPI only (Rust core deferred to v3) |
| **Data pipeline** | CFTC + Stooq → backtest engine | CFTC + yfinance → attention engine (reuses everything except backtest) |
| **NECST score** | 4.0 / 5 | **4.4 / 5** (Need bumped 0.7 → 0.9 — see §0.2) |
| **Timeline** | 5 weeks across 6 phases | **3 weeks across 4 phases** (no backtest gate, no Rust core) |
| **Pricing** | Deferred to Phase 5 | Same — defer until first customer commitment |
| **Comp** | None — auto-signal products mostly fail in this space | Briese ($360/yr), Upperman ($720/yr), CMEGroup COT tool (free, ugly) — real, paid market |

---

## 0. Context

### 0.1 What the v1 gate taught us

Three things, all of which point the same direction:

1. **The Williams/Briese/Upperman framework was never a trigger system.** Re-reading: Williams used COT as a *bias* to be combined with seasonality + technical setups (*Long-Term Secrets*, ch.12). Briese explicitly wrote "commercials are usually wrong on direction, right on extremes" (ch.4). Upperman called COT Index a "background indicator" (ch.6). Encoding it as a mechanized 6-layer AND was a misreading.

2. **The commercial-extreme edge has decayed.** Multiple academic studies post-2010 (Sanders/Boris/Manfredo 2009; Bohl/Stephan 2013) document weakening of the commercial-positioning signal coinciding with index investment growth and Dodd-Frank swap-dealer reporting. Briese's 2008 framework was built on a regime that no longer exists. Even with our v1.1 fixes (decile-based L3, MFE-gated 50% rule), the edge isn't there.

3. **The proven-paid market is dashboards, not autotraders.** Briese sells *Bullish Review* for $360/yr. Upperman sells *Insider Capital Group* for $720/yr. Neither generates trade signals. Both are positioning visualizations with weekly commentary. That market exists and pays.

### 0.2 Updated NECST audit

| Commandment | v1 score | v2 score | Reasoning change |
|---|---|---|---|
| Need | 0.7 | **0.9** | Discretionary traders who already trade COT-aware need *better tools* — concrete, observed demand (Briese/Upperman customer bases). Systematic traders who wanted auto-signals were a much smaller market AND the product didn't work for them. |
| Entry | 0.6 | **0.7** | Same data pipeline barrier; UX quality moat is now the *primary* moat (not an "also"). |
| Control | 0.9 | 0.9 | Unchanged. Own data, own hosting, own IP. |
| Scale | 1.0 | 1.0 | Unchanged. Digital subscription. |
| Time | 0.8 | **0.9** | No model maintenance, no strategy decay risk, no backtest re-validation. Lighter ongoing burden. |
| **Total** | **4.0/5** | **4.4/5** | |

Marco would route this through.

### 0.3 Pre-defined stop-losses (per Jim Paul §1.1)

- **Time stop:** if the dashboard is not deployable to a public URL by 2026-06-09 (3 weeks) → pause build, route focus to challenge.
- **Process stop:** any C-grade trading session → freeze build for 7 days.
- **Capital stop:** $0 spent on data vendors, hosting, or services until first paying user commits.
- **Product stop:** if Praveen + 5 Twitter followers shown the live dashboard say "I wouldn't pay for this" → reroute. (This replaces v1's quantitative gate. Honest, fast, qualitative.)

---

## 1. The product — `COT_LENS_v1`

### 1.1 Core thesis

A trader opens the dashboard each Friday after the CFTC release (15:30 CT). In 90 seconds they answer:

> *"Where is hedger positioning unusual right now, and is it confirming or contradicting price?"*

That answer is what they pay for. Not "buy crude at 78.40." Not "Sharpe 1.6 backtest." Just **positioning context, rendered well, faster than they could do it themselves.**

### 1.2 Five attention zones (replaces the six-layer signal)

Each market is scored across five lenses every CFTC release. A market that scores "interesting" on ≥ 1 lens surfaces in the attention list.

| Lens | Definition | Book source |
|---|---|---|
| **A1 — Extreme positioning** | COT Index ≥ 90 or ≤ 10 (commercials, 3-year window). | Upperman ch.6 |
| **A2 — Price divergence** | Price prints new 52-week extreme but commercial net position moves the opposite direction (3-week trailing). | Briese ch.7 |
| **A3 — Sector outlier** | Within correlated complex (grains / energies / metals / softs / meats), COT Index is > 1.5σ from sector median. | New — prop-desk convention, not in books |
| **A4 — Momentum shift** | COT Index 4-week rate-of-change in top/bottom decile of its own history. "Hedgers are repositioning *fast*." | Briese ch.5 |
| **A5 — Hedger/speculator imbalance** | Commercial net position and managed-money net position both near 3-year extreme on opposite sides. Classic "smart money vs dumb money" setup. | Williams *Long-Term Secrets* ch.12 |

**Critical:** zones do NOT generate buy/sell signals. They generate *attention*. The dashboard shows the lens, the supporting data, and a brief explanation. The trader decides.

### 1.3 What the dashboard surfaces

| Surface | Content |
|---|---|
| **Today** (default route) | Markets ranked by total zones triggered this week. Per-market badge row + 1-line "why." |
| **Market detail** | Price chart + commercial/MM/swap-dealer net-position panes + COT Index + zone history overlay. Crosshair, scrub. |
| **Sector heatmap** | All 23 contracts × 5 zones, current week. Click-to-drill. |
| **Divergence scanner** | A2-only view, ranked by divergence magnitude. |
| **News correlator** | Free macro/commodity news pinned to the position timeline. See §1.6 — *the* differentiator vs Briese/Upperman. |

### 1.4 Data & schedule

CFTC releases Tuesday snapshot Friday 15:30 CT. Pipeline runs Friday 16:00 CT via GitHub Actions cron. Zone scores recomputed, written to Postgres, web app polls (MVP) or WebSocket (post-MVP).

News ingest runs on its own cadence — daily for RSS feeds, weekly catch-up for scheduled-event calendars (WASDE, EIA, FOMC, OPEC). See §1.6.

### 1.5 What this is NOT

- Not a signal service. No P&L promises. No backtest in the marketing.
- Not a database — Quandl, CFTC.gov itself, and CMEGroup all provide raw data for free.
- Not an LLM commentary product — every piece of text the user reads is either (a) deterministic from data (zone reasoning) or (b) verbatim from a primary source (news headline + link). No model-generated prose.
- Not for institutional traders who already have Bloomberg COT screens.

The wedge: **retail and small-prop discretionary futures traders ($5K–$500K accounts) who currently squint at ugly Briese PDFs or CMEGroup tables.**

### 1.6 Macro news correlator — the differentiator

**Question the correlator answers:** *"Why are commercials positioned this way right now?"*

Answered **without an LLM**. Reasoning emerges from the juxtaposition of three deterministic things on a shared timeline:

1. The price chart for the market.
2. The commercial/MM/swap-dealer net position pane.
3. **Pinned news events** filtered to that market, with full source attribution.

The user looks at a sharp position shift and sees the news that landed that week — no model interpretation, just the data. This is what discretionary traders do manually today by alt-tabbing between Reuters, USDA, and their COT spreadsheet. We collapse it into one surface.

**News sources (free only, per §0.3 capital stop):**

| Source | Cadence | Coverage | Cost |
|---|---|---|---|
| Yahoo Finance ticker news (via `yfinance`) | Real-time | Per-contract headlines, source-attributed | $0 |
| USDA WASDE / Crop Production reports | Scheduled | Grains, meats | $0 (RSS) |
| EIA Weekly Petroleum Status | Wed 10:30 ET | Energy | $0 (API, no key for headlines) |
| FOMC meeting calendar | Scheduled | Macro context | $0 (static calendar) |
| OPEC meeting calendar | Scheduled | Energy | $0 (static calendar) |
| FRED economic releases (CPI, NFP, etc.) | Scheduled | Macro context | $0 (FRED API, key is free) |

**Tagging logic — no NLP, just keyword taxonomy:**

A static `packages/ingest/news_taxonomy.py` file maps keyword sets to markets. Examples:

```python
TAXONOMY = {
  "CL": ["opec", "crude", "wti", "saudi", "iran", "russia oil", "pipeline"],
  "ZC": ["corn", "wasde", "ethanol", "midwest drought", "midwest planting"],
  "GC": ["fed", "fomc", "rate cut", "rate hike", "cpi", "gold", "dollar"],
  # ... per contract
}
```

A headline matches a market iff it contains ≥ 1 keyword from that market's set (case-insensitive, word-boundary regex). One headline can match multiple markets (e.g., a CPI print tags GC + ZN + 6E).

**No sentiment scoring. No summarization. No model.** Headline + source + date + URL, rendered as-is. The trader supplies the interpretation.

**UI integration:**

- **News rail** on the market-detail page: vertical timeline alongside the chart. Each item = date + source pill + headline (links out). Filter by source category.
- **News pins** on the chart's date axis: small icons at the event date; hover shows the headline.
- **Position-change context**: when a position pane shows a > 1σ weekly net-position change, the top 3 headlines from that week for that market auto-highlight.

**What this is NOT:**

- Not a sentiment engine. We do not classify headlines as bullish/bearish.
- Not a news aggregator product. The news is a *companion* to the positioning data — not browseable in isolation.
- Not real-time alerts (post-MVP). MVP is end-of-day refresh, same cadence as the CFTC report.

---

## 2. Engineering philosophy

**Unchanged from PLAN v1 §2.** The browser is treated as a rendering runtime + graphics engine + simulation environment. WebGL2 for chart pixels, React for orchestration only, workers for compute, fixed-timestep sim engine, spring-driven motion.

Performance budgets (TTI < 1.5s, frame time < 8ms p99, etc.) unchanged.

The only deletion: **no backtest worker**, since there's no backtest. This shrinks the WASM payload from ~600KB to ~0KB and brings TTI well under budget.

---

## 3. Architecture

Same diagram as PLAN v1 §3.1 except:

- **Origin (Fly.io):** FastAPI only. No Rust backtest core. No PyO3 binding.
- **Browser worker pool:** indicator + tile decode workers stay. Backtest worker deleted.
- **Edge (Cloudflare):** unchanged.

Concrete deletions from the v1 file structure (§6 of PLAN.md):

```
packages/strategy-core/             ← DELETE (Rust backtest)
packages/ingest/backtest.py          ← DELETE (Python backtest, gate failed)
packages/ingest/metrics.py           ← DELETE (was scoring backtest)
packages/ingest/signal.py            ← REPLACE with zones.py (the 5 lenses)
apps/web/src/workers/backtest.worker.ts  ← never built; do not build
apps/web/src/routes/backtest/        ← never built; do not build
apps/web/src/routes/replay/          ← keep for v2 (price + position scrub is still valuable)
apps/web/src/routes/strategy/        ← DELETE — no strategy editor
```

Concrete additions:

```
packages/ingest/zones.py             ← the 5 lens scorers (replaces signal.py)
packages/ingest/news.py              ← ingest yfinance/USDA/EIA/FOMC/OPEC/FRED feeds
packages/ingest/news_taxonomy.py     ← keyword → market mapping
apps/web/src/routes/today/           ← default: today's attention list
apps/web/src/routes/heatmap/         ← sector × zone grid
apps/web/src/routes/divergence/      ← A2 scanner
apps/web/src/components/zone-badge/  ← reusable lens chip
apps/web/src/components/attention-card/  ← per-market card with lens reasoning
apps/web/src/components/news-rail/   ← vertical news timeline on market detail
apps/web/src/components/news-pin/    ← chart-axis event marker
```

---

## 4. Design system

**Unchanged from PLAN v1 §4.** Same tokens, same primitives, same density philosophy. Two color additions:

| Token | Value | Use |
|---|---|---|
| **Attention high** | #B794F6 (cool purple) | Markets triggering ≥ 3 zones |
| **Attention low** | #4A5568 (cool gray) | Markets triggering 0 zones (default state) |

Status colors (long green / short coral / pending amber) are *removed from the market list* — there is no directional call to make. They remain on the chart for user-drawn annotations.

---

## 5. Component hierarchy

```
<App>
  <Providers>
    <Layout>
      <Sidebar>
        <RouteList />              // Today, Heatmap, Divergence, Markets
        <MarketList virtualized /> // 23 physicals, ranked by zones triggered
      </Sidebar>
      <Main>
        <Toolbar>
          <WeekPicker />           // jump to any prior CFTC release
          <SectorFilter />
        </Toolbar>
        <RouteOutlet />            // Today | Heatmap | Divergence | Market
      </Main>
    </Layout>
  </Providers>
</App>
```

Per-route specifics:

- **Today** route: ranked `<AttentionCard>` list, each card = market + zone badges + 1-line explanation + sparkline.
- **Market** route: `<Chart>` (WebGL price + Canvas2D overlay, news pins on date axis) + `<PositionPane>` (commercial / MM / swap-dealer stacked) + `<ZoneTimeline>` (when each zone has historically fired for this market) + `<NewsRail>` (vertical news timeline, source-attributed, filterable by category).
- **Heatmap** route: 23 rows × 5 cols grid. Cell = zone triggered? color. Click → market detail.
- **Divergence** route: ranked list, divergence magnitude as horizontal bar.

---

## 6. File structure

```
cot-dashboard/
├── apps/
│   ├── web/                              # React 19 + Vite frontend (NEW for v2 build)
│   │   └── (same as PLAN v1 §6, with route deletions/additions per §3 above)
│   └── api/                              # FastAPI origin (NEW for v2 build)
│       └── (same as PLAN v1 §6, minus backtest endpoints)
│
├── packages/
│   ├── ingest/                           # EXISTING — keep universe, cftc_cot, prices, normalize, indicators
│   │   ├── universe.py                   # ✓ keep
│   │   ├── cftc_cot.py                   # ✓ keep
│   │   ├── prices.py                     # ✓ keep
│   │   ├── normalize.py                  # ✓ keep
│   │   ├── indicators.py                 # ✓ keep
│   │   ├── zones.py                      # ✚ NEW — replaces signal.py
│   │   ├── signal.py                     # ✗ DELETE
│   │   ├── backtest.py                   # ✗ DELETE
│   │   └── metrics.py                    # ✗ DELETE
│   │
│   └── shared-types/                     # TS ↔ Pydantic
│
├── infra/
│   ├── fly.toml
│   ├── cloudflare-worker/
│   └── github-actions/friday-ingest.yml
│
├── research/
│   ├── notebooks/phase0_strategy_validation.ipynb  # ✓ keep as historical record
│   └── findings.md                       # ✓ keep — explains why v1 failed
│
├── PLAN_v1_archived.md                   # ← rename of current PLAN.md if v2 approved
├── PLAN.md                               # ← this file becomes PLAN.md if approved
└── README.md
```

---

## 7. Build phases (3 weeks)

### Phase 0 — REMOVED

No backtest gate. The product validation gate is replaced by §0.3 product stop: "5 Twitter followers say I wouldn't pay" → kill.

### Phase 1 — Zone engine + news correlator + data spine (Week 1)

- Write `packages/ingest/zones.py` implementing A1–A5 over the existing annotated DataFrame.
- Write `packages/ingest/sector.py` for sector-relative outlier math (A3).
- Write `packages/ingest/news.py` — ingest yfinance ticker news + USDA WASDE + EIA + FOMC/OPEC calendars + FRED releases.
- Write `packages/ingest/news_taxonomy.py` — keyword → market mapping for all 23 contracts.
- Parquet store on R2 (price + COT + news, partitioned by date).
- Friday cron: pull CFTC + prices, recompute zones, write Parquet + Postgres summary.
- Daily cron: pull RSS news + scheduled-event deltas, tag, write to Postgres.
- FastAPI: `/today`, `/market/:sym`, `/heatmap`, `/divergence/:week`, `/news/:sym?from&to`.
- Auth via Clerk free tier (deferred decision now resolved by speed).
- **Definition of done:** `curl /today` returns ranked markets with zone scores. `curl /news/CL?from=2026-04-01&to=2026-05-01` returns tagged headlines with sources.

### Phase 2 — Web shell + chart + news rail (Week 2)

- Vite + React 19 + TS scaffold.
- Design tokens + 7 base primitives (Button, Input, Select, Dialog, Tooltip, Tabs, Badge).
- Layout shell.
- WebGL chart primitive: candles + MAs + position-pane histogram. (Canvas2D fallback acceptable per PLAN v1 §10.)
- News pins on chart date axis. `NewsRail` component on market-detail page.
- Pointer + crosshair + spring-driven hover.
- **Definition of done:** market detail page renders 5-year price + position + news data with working scrub. Hovering a news pin shows headline + source.

### Phase 3 — Routes + polish (Week 3)

- `Today`, `Heatmap`, `Divergence`, `Market` routes wired.
- `AttentionCard` + `ZoneBadge` + `ZoneTimeline` + `NewsRail` + `NewsPin` components.
- Mobile-responsive (tablet+ only; phone is post-MVP).
- Loading + empty + error states for every route.
- Landing page.
- Deploy: Vercel (web) + Fly.io (api) + Cloudflare (edge).
- **Definition of done:** public URL, shareable, "would you pay?" survey question goes out.

### Phase 6 — Twitter content (parallel, continuous)

Three threads, one per week:
- Week 1: "Why mechanized COT strategies don't work in 2026 (and what does)" — uses findings.md.
- Week 2: "Pairing CFTC positioning with the news that caused it — no LLM, just timeline overlay"
- Week 3: "Launch — `COT_LENS_v1` is live, here's how I use it"

Build-in-public is the customer acquisition funnel.

---

## 8. Performance tactics

Unchanged from PLAN v1 §8 except: no WASM core to preload. Initial JS bundle target tightens from < 180KB to **< 120KB** gzipped.

---

## 9. Scalability roadmap

| Stage | Users | Architecture change |
|---|---|---|
| MVP | 1–10 | Single Fly.io machine. R2 for data. No queue. |
| Early | 10–100 | Redis tile cache. Postgres replica. |
| Growth | 100–1K | Real-time news push via WebSocket. User-defined keyword alerts. |
| Scale | 1K–10K | Multi-region edge. Postgres → CockroachDB or partitioned. |
| Big | 10K+ | Custom zone authoring — users define their own attention rules. |

---

## 10. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Users want signals not context, won't pay for "lens" | Medium | Project stops | Product stop in §0.3. Validate with 5 followers before building Phase 2. |
| Briese/Upperman cut prices in response | Low | Margin pressure | Out-execute on UX + commentary. Both products are slow-moving. |
| CFTC stops publishing weekly | Very Low | Total break | No mitigation. Acceptable tail risk. |
| Build time bleeds into LucidFlex eval | High | Mission failure | 3-week time stop. Process stop on any C-grade session. |
| User acquisition stalls (no audience) | High | No revenue | Twitter threads start Week 1, shipping = launch event. |

---

## 11. Open questions — answer before Phase 1

1. **Pricing model:** flat $19/mo? Tiered ($0 read-only / $29 full + heatmap + divergence)? Lifetime $299? (Differs from v1 §11 because the product is positioning context, not auto-signals — pricing should reflect that.)
2. **News history depth:** ingest news only going forward (cheap, simple, but no historical correlation panels), OR backfill 3 years of news for every contract (expensive in HTTP traffic, gives users immediate context on chart scrubs)?
3. **Universe scope:** keep 23 physicals from v1? Or expand to financials by adding the TFF report ingest (different categories — Dealer/Asset Manager — but same dashboard treatment)?

Three questions, not six. Pivot is leaner.

---

## 12. Quality bar

Unchanged from PLAN v1 §12. Figma / Linear / Stripe / Excalidraw quality. The pivot doesn't lower this bar — if anything, the bar matters MORE now because the product *is* the visual surface.

---

## What survives from v1

- All ingest code in `packages/ingest/` except `signal.py`, `backtest.py`, `metrics.py`
- All design system thinking in PLAN.md §2–4
- The architecture in PLAN.md §3 minus the Rust core
- The notebook + findings.md as historical record of why v1 failed
- The NECST framework + Jim Paul stop-losses

## What dies

- `WILLIAMS_COT_SWING_v1` as a tradeable strategy
- The backtest engine and walk-forward harness
- The Rust strategy core
- Phase 0 as a blocking gate
- The implicit claim that this product will help users *make trades*; it helps users *understand positioning*

## Links

- [research/findings.md](research/findings.md) — full Phase 0 post-mortem
- [PLAN.md](PLAN.md) — original v1 plan (would be renamed `PLAN_v1_archived.md`)
- Source PDFs in `raw/books/` — unchanged
