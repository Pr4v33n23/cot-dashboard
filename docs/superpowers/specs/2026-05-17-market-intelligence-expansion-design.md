# Market Intelligence Expansion — Design Spec
**Date:** 2026-05-17  
**Status:** Approved  
**Supersedes:** nothing — additive to PLAN.md  

---

## 1. Scope

Expand COT_LENS_v1 to the **full CME Group CFTC-reportable universe** (~80 contracts across CME, NYMEX, CBOT, COMEX) with six intelligence layers applied uniformly. Contracts are typed as `physical` or `financial` — the intelligence layer adapts its framing per type, but the same ML pipeline (HMM, FinBERT, OI, retail sentiment) runs on all of them.

| Feature | Physical contracts | Financial contracts |
|---|---|---|
| COT breakdown | Commercial/LargeSpec/SmallSpec + Williams/Briese framing | Dealer/AssetMgr/LevFunds + institutional-flow framing |
| A1–A5 zone engine | ✅ applies | ❌ not applicable (no commercial hedger thesis) |
| HMM regime detector | ✅ | ✅ |
| FinBERT news sentiment | ✅ | ✅ |
| Open interest | ✅ | ✅ |
| Retail sentiment | IG + Myfxbook + OANDA | IG (indices/FX) + Put/Call ratio (indices) + CFTC non-reportable proxy (rates/VIX) |
| Divergence signal | comm vs specs | dealer/AM vs lev funds |

**Contract count:** ~38 physicals (DisAgg report) + ~42 financials (TFF report) = ~80 total.

**Layout:** Intelligence strip (4 cells) → chart with OI pane → COT breakdown (framing adapts to market type) → retail sentiment → FinBERT-scored news.

---

## 2. Market Type Framework

Every `Contract` gets a `market_type: "physical" | "financial"` field and a `report_type: "disagg" | "tff"` field (these always co-vary — all physicals use DisAgg, all financials use TFF).

### 2.1 Physical contracts (DisAgg report)

COT categories: `Producer/Merchant (pm)`, `Swap Dealer (sd)`, `Managed Money (mm)`, `Other Reportable (or)`, `Non-Reportable (nr)`.

Intelligence framing:
- "Commercials" = `pm + sd` net (real producers/end-users with physical exposure)
- "Large Specs" = `mm` net (trend-following CTAs)
- "Small Specs" = `nr` net
- A1–A5 zone engine applies
- Divergence signal: commercial net vs mm net

### 2.2 Financial contracts (TFF report)

COT categories: `Dealer Intermediary (dealer)`, `Asset Manager (am)`, `Leveraged Funds (lf)`, `Other Reportable (other)`, `Non-Reportable (nr)`.

Intelligence framing (different from physicals — no Williams/Briese):
- "Dealers" = sell-side banks, market makers, hedging fx/rate exposure
- "Asset Managers" = pension funds, mutual funds, long-only allocators
- "Leveraged Funds" = hedge funds, CTAs — the directional speculative money
- Divergence signal: `am` (institutional allocators) vs `lf` (leveraged specs) — when these move in opposite directions, it signals a potential inflection
- A1–A5 zones **not shown** — replaced by HMM regime label as the primary attention signal

### 2.3 UI indicator

Each market detail page header shows a pill: `⟨physical⟩` or `⟨financial⟩`. The COT breakdown section title and category labels change accordingly. A tooltip explains the framing in plain language.

---

## 3. Full Universe (~80 contracts)

### 3.1 Physical contracts — DisAgg report (~38)

**Grains (CBOT):**
ZC (Corn), ZS (Soybeans), ZW (Chicago Wheat), KE (KC HRW Wheat), ZO (Oats), ZR (Rough Rice), ZL (Soybean Oil), ZM (Soybean Meal)

**Energy (NYMEX):**
CL (Crude Oil WTI), NG (Natural Gas), RB (RBOB Gasoline), HO (Heating Oil), BZ (Brent Crude)

**Metals (COMEX/NYMEX):**
GC (Gold), SI (Silver), HG (Copper), PL (Platinum), PA (Palladium), ALI (Aluminum)

**Softs (ICE/CBOT, CFTC-reportable):**
CC (Cocoa), KC (Coffee), CT (Cotton), SB (Sugar #11), OJ (Orange Juice), LBS (Lumber)

**Livestock (CME):**
LE (Live Cattle), GF (Feeder Cattle), HE (Lean Hogs)

*(Note: 23 already in production. ~15 additions: KE, BZ, ALI, LBS, GF + verify remaining against CFTC DisAgg header)*

### 3.2 Financial contracts — TFF report (~42)

**FX (CME):**
EURUSD, GBPUSD, JPYUSD, AUDUSD, CADUSD, CHFUSD, NZDUSD, MXNUSD, BRLUSD, RUBUSD, NOKUSD, SEKUSD, TWDUSD, KRWUSD, INRUSD

**Equity Indices (CME):**
ES (S&P 500 E-mini), NQ (Nasdaq-100 E-mini), YM (DJIA E-mini), RTY (Russell 2000 E-mini), NIY (Nikkei 225 Yen), DAX (not CME — skip), MES (Micro S&P), MNQ (Micro Nasdaq)

**Interest Rates (CBOT):**
ZB (30Y T-Bond), ZN (10Y T-Note), ZF (5Y T-Note), ZT (2Y T-Note), FF (30D Fed Funds), SR3 (SOFR 3M), SR1 (SOFR 1M)

**Volatility:**
VX (CBOE VIX Futures — separate CFTC report, include if CFTC-reportable)

*(Exact CFTC codes verified against TFF archive header at implementation time)*

---

## 4. Data Model Changes

### 4.1 `Contract` struct additions (`universe.py`)

```python
market_type: Literal["physical", "financial"]   # drives UI framing + which zone engine runs
report_type: Literal["disagg", "tff"]           # drives which parser fetches data
sector: str  # existing — add new sectors: "fx", "indices", "rates", "volatility"
```

### 4.2 `BarRow` additions (`schemas.py` + `types.ts`)

```python
open_interest: float | None = None
nr_long: float | None = None
nr_short: float | None = None
# TFF-only columns (None for physicals)
dealer_long: float | None = None
dealer_short: float | None = None
am_long: float | None = None
am_short: float | None = None
lf_long: float | None = None
lf_short: float | None = None
# Computed
comm_spec_divergence: int = 0       # physicals only: weeks active
am_lf_divergence: int = 0           # financials only: weeks AM vs LF diverging
regime_label: str | None = None     # all markets
regime_proba: list[float] | None = None
regime_weeks: int = 0
```

### 4.3 `NewsItem` addition

```python
sentiment_score: float | None = None   # FinBERT: positive_prob - negative_prob
sentiment_label: str | None = None     # "positive" | "negative" | "neutral"
```

### 4.4 New response models

```python
class RetailSentimentItem(BaseModel):
    symbol: str
    long_pct: float
    short_pct: float
    source: str       # "ig" | "myfxbook" | "oanda" | "put_call" | "nr_proxy"
    timestamp: datetime

class RetailSentimentResponse(BaseModel):
    symbol: str
    items: list[RetailSentimentItem]
    avg_long_pct: float
    avg_short_pct: float

class RegimeResponse(BaseModel):
    symbol: str
    market_type: str
    current_regime: str
    regime_weeks: int
    proba: list[float]
    next_bar_proba: list[float]
    transition_matrix: list[list[float]]
    state_names: list[str]
```

---

## 5. New & Modified Ingest Modules

### 5.1 `packages/ingest/tff_cot.py` — NEW

Downloads CFTC TFF disaggregated futures-only ZIPs. Same year-by-year archive pattern as `cftc_cot.py`. Column mapping:

```
Dealer_Positions_Long_All     → dealer_long
Dealer_Positions_Short_All    → dealer_short
Asset_Mgr_Positions_Long_All  → am_long
Asset_Mgr_Positions_Short_All → am_short
Lev_Money_Positions_Long_All  → lf_long
Lev_Money_Positions_Short_All → lf_short
Other_Rept_Positions_Long_All → other_long
Other_Rept_Positions_Short_All→ other_short
NonRept_Positions_Long_All    → nr_long
NonRept_Positions_Short_All   → nr_short
Open_Interest_All             → open_interest
```

`net_commercials` for financials = `dealer_long - dealer_short` (dealers hedge institutional flow).

Output: same `symbol/date` index — `normalize.py` merges identically.

### 5.2 `packages/ingest/universe.py` — EXTEND

Add `market_type` and `report_type` to `Contract`. Existing 23 physicals get `market_type="physical", report_type="disagg"`. Add ~15 more physicals (same type). All ~42 financials get `market_type="financial", report_type="tff"`.

New sector strings: `"fx"`, `"indices"`, `"rates"`, `"volatility"`.

### 5.3 `packages/ingest/news_taxonomy.py` — EXTEND

Add keyword mappings for all new contracts:
- Equity indices: SPX, S&P, Nasdaq, Fed, rate, inflation, earnings, GDP, CPI, NFP, recession
- Interest rates: treasury, yield, Fed, FOMC, inflation, bond, auction, duration
- FX: dollar, euro, sterling, yen, yuan, RBA, BOE, ECB, BOJ, DXY
- VIX: volatility, VIX, fear, uncertainty, options, hedging

### 5.4 `packages/ingest/news_sentiment.py` — NEW (DeepSeek V4 API)

Uses **DeepSeek-V4-Flash** via `api.deepseek.com` (OpenAI-compatible). Flash chosen for batch news scoring — fast, cheap (~$0.07/M input tokens), sufficient quality for structured classification tasks.

```python
MODEL = "deepseek-v4-flash"
API_BASE = "https://api.deepseek.com/v1"   # OpenAI-compatible
BATCH_SIZE = 32                             # headlines per API call (packed into one prompt)
```

Each batch call sends up to 32 headlines packed into a single prompt requesting structured JSON output:
```json
[{"title": "...", "sentiment": "positive|negative|neutral", "score": 0.82, "reasoning": "..."}]
```

Output per headline:
- `sentiment_score`: float ∈ [−1, +1] (provided directly by model, not derived)
- `sentiment_label`: `"positive" | "negative" | "neutral"`
- `sentiment_reason`: 1-sentence deterministic explanation (e.g., "OPEC cut = supply reduction = bullish crude")

Incremental — skip headlines where `sentiment_score` is already populated. Written back to `news.parquet`. Runs at daily cron. API key stored as `DEEPSEEK_API_KEY` env var (Fly secret + GitHub Actions secret).

**Cost estimate:** ~300 headlines/day × ~80 tokens = 24K tokens/day → ~$0.002/day (~$0.70/year at Flash pricing).

### 5.5 `packages/ingest/regime.py` — NEW (HMM per market)

```python
N_STATES = 4
# Physical features
PHYS_FEATURES = ["log_return", "cot_net_change_pct", "oi_change_pct", "vol_ratio"]
# Financial features (no commercial net — use lf_net instead)
FIN_FEATURES  = ["log_return", "lf_net_change_pct", "oi_change_pct", "vol_ratio"]
```

Fits `hmmlearn.GaussianHMM(n_components=4, covariance_type="full", n_iter=1000)` per symbol. 5 random restarts, keep highest log-likelihood. Post-hoc state labeling by inspecting mean return and COT net direction:

| Label | Mean return | Net COT change |
|---|---|---|
| `trending` | high | aligned |
| `accumulation` | near-zero | rising |
| `distribution` | near-zero | falling |
| `ranging` | near-zero | flat |

Minimum data threshold: skip HMM fit if `len(weekly_bars) < 200` — set `regime_label=null` for those bars.

Retrain weekly after CFTC refresh. Models persisted to `research/data/cache/regime_{symbol}.pkl`.

### 5.6 `packages/ingest/market_synthesis.py` — NEW (DeepSeek V4 Pro)

Uses **DeepSeek-V4-Pro** via `api.deepseek.com`. Pro chosen here because this is the key value-add output — a structured per-market intelligence summary that synthesises all data layers into coherent context a trader can act on.

**Input per market (structured, not free-form):**
```python
{
  "symbol": "CL",
  "market_type": "physical",
  "cot": {
    "comm_net": 182400, "comm_cot_index": 91.4,
    "spec_net": -94200, "spec_cot_index": 8.2,
    "divergence_weeks": 5
  },
  "regime": {"label": "accumulation", "weeks": 5, "confidence": 0.81},
  "open_interest": {"current": 412000, "change_pct": 6.1},
  "retail_sentiment": {"avg_short_pct": 71},
  "news_sentiment": {"score": 0.55, "top_headlines": ["OPEC cuts...", "Inventory draw..."]}
}
```

**Output (structured JSON, stored per market per week):**
```json
{
  "summary": "Commercials are at a 3-year extreme long while specs are near extreme short. Rising OI confirms new money entering. Retail is 71% short — positioned against commercials. Regime: accumulation for 5 weeks.",
  "confluence_score": 0.84,
  "key_factors": ["extreme commercial long", "spec capitulation", "OI expansion", "retail contra"],
  "watch": "OPEC+ meeting May 22 — potential catalyst for the positioning thesis to play out.",
  "framework": "physical"
}
```

Stored in `research/data/cache/synthesis_{symbol}.parquet`. Rebuilt weekly after CFTC refresh (not daily — synthesis is a weekly snapshot aligned to COT release cadence).

New API endpoint: `GET /synthesis/{symbol}` returns the latest synthesis object.

New `BarRow` field: `confluence_score: float | None = None` — surfaces in the intelligence strip and `/today` ranking.

**Cost estimate:** ~80 markets × ~800 tokens input × ~300 tokens output = ~88K tokens/week → ~$0.05/week (~$2.60/year at Pro pricing).

### 5.7 `packages/ingest/retail_sentiment.py` — NEW

Three primary + two supplementary sources:

**Primary (FX + some commodities):**
- **IG Markets** (`source="ig"`): public JSON, no auth, ~80 instruments — FX + equity indices + some commodities
- **Myfxbook** (`source="myfxbook"`): HTML scrape, ~30 FX pairs
- **OANDA** (`source="oanda"`): public position ratio endpoint — FX instruments

**Supplementary (financials without broker coverage):**
- **Put/Call ratio** (`source="put_call"`): CBOE daily P/C ratio for equity index contracts (ES, NQ, YM, RTY). Invert to long/short percentage: `long_pct = 1 / (1 + pc_ratio)`. Free from CBOE data endpoint.
- **CFTC non-reportable proxy** (`source="nr_proxy"`): For interest rate and VIX contracts, use `nr_long / (nr_long + nr_short)` as retail sentiment proxy — non-reportable positions are small retail traders by definition.

Output schema: `{symbol, timestamp, long_pct, short_pct, source}`. Written to `retail_sentiment.parquet`. Built on daily cron.

### 5.7 `packages/ingest/zones.py` — EXTEND

`annotate_zones()` checks `market_type` before running each lens:
- A1–A5: run only for `market_type="physical"`
- `comm_spec_divergence`: physicals only (comm vs mm)
- `am_lf_divergence`: financials only (am vs lf), same consecutive-weeks logic

---

## 6. API Changes

### 6.1 `data.py` — Bundle additions

```python
@dataclass
class Bundle:
    annotated: dict[str, pd.DataFrame]
    news_df: pd.DataFrame
    today_df: pd.DataFrame
    retail_df: pd.DataFrame          # NEW
    regime_models: dict[str, Any]    # NEW
    loaded_at: pd.Timestamp | None
```

`build_bundle()` routes each symbol through the correct parser (`tff_cot` vs `cftc_cot`) based on `report_type`. Calls `regime.fit_all_regimes()` and `news_sentiment.score_headlines()` after data load.

### 6.2 `main.py` — New endpoints

```
GET /retail-sentiment/{symbol}  →  RetailSentimentResponse
GET /regime/{symbol}            →  RegimeResponse
```

### 6.3 `schemas.py` + `types.ts` — sync all new fields

---

## 7. Frontend Changes

### 7.1 Sidebar (`+layout.svelte`)

Add sector groups for `"fx"`, `"indices"`, `"rates"`, `"volatility"` below the existing commodity sectors. Visual separator (`<hr>` with "Financials" label) between physicals and financials.

`/today` (attention list): for physicals shows A-zone badges; for financials shows HMM regime badge (e.g., `accumulation`, `trending`). Both types appear in the ranked list, sorted by `total_mag` (physicals) or `regime_confidence` (financials).

### 7.2 New component: `IntelStrip.svelte`

```
src/lib/components/intelligence/IntelStrip.svelte
```

5-cell strip (adds Confluence). Props: `{ divergenceWeeks, retailShortPct, oiChangePct, newsTone, confluenceScore, marketType }`. Cell labels adapt: physicals show "COT Divergence", financials show "AM/LF Divergence".

5th cell — **Confluence** (DeepSeek-V4-Pro score):
- Value: `0.84` (0–1 float, coloured green → amber → red)
- Sub-line: `"4 factors aligned"` (count of key_factors from synthesis)
- Clicking opens a drawer showing the full `synthesis.summary` + `watch` field

### 7.2a New component: `SynthesisDrawer.svelte`

```
src/lib/components/intelligence/SynthesisDrawer.svelte
```

Slide-in drawer (same pattern as `NewsReader.svelte`). Shows:
- `synthesis.summary` — 2–3 sentence structured market context
- `synthesis.key_factors` — bulleted list of active signals
- `synthesis.watch` — upcoming catalyst to monitor
- Timestamp: "Generated {date} after CFTC release"
- Disclaimer: *"Generated by DeepSeek-V4-Pro from structured data. Not a trading signal."*

Triggered by clicking the Confluence cell in IntelStrip.

### 7.3 Chart.svelte — OI as 4th pane

Redistribute pane height fractions: `PRICE_FRAC=0.55, NETPOS_FRAC=0.18, COT_FRAC=0.13, OI_FRAC=0.14`. OI line in `--zone-a3` (teal). Bars where OI Δ > +5% show confirmation background; Δ < −5% show liquidation background.

### 7.4 `market/[symbol]/+page.svelte` — 3 new sections

**COT Breakdown section** — adapts per `market_type`:
- Physical: 4 cards (Commercials, Managed Money, Other Reportable, Small Specs) + divergence banner
- Financial: 4 cards (Dealers, Asset Managers, Leveraged Funds, Non-Reportable) + AM/LF divergence banner + note: *"Commercial-hedger framing does not apply to financial futures. Dealer = sell-side hedge; Leveraged Funds = directional specs."*

**Retail Sentiment section** — source mix adapts per market type:
- FX: IG + Myfxbook + OANDA
- Equity indices: IG + Put/Call ratio
- Rates/VIX: CFTC non-reportable proxy (with label: *"Retail proxy: CFTC non-reportable position ratio"*)

**NewsRail** — `sentiment_score` badge on each headline (colored ±float).

### 7.5 `AttentionCard.svelte` + `/today` route

For financials, replace zone badges with a single HMM regime badge (e.g., `● trending 6wk`). The `reason` line adapts: *"Regime: trending for 6 weeks. AM net long, LF net short. OI rising."* instead of the physical zone reasoning.

---

## 8. Cron / Scheduling Changes

**Friday CFTC cron:** pull both DisAgg ZIPs (physicals) and TFF ZIPs (financials). Trigger HMM refit after bundle rebuild. Run `retail_sentiment.py` for supplementary sources.

**Daily news cron:** call `news_sentiment.score_headlines()` on new headlines. Run IG/Myfxbook/OANDA/CBOE P-C scrapes.

---

## 9. New Dependencies

```toml
# pyproject.toml additions
openai = ">=1.30"         # DeepSeek API is OpenAI-compatible — use openai client
hmmlearn = ">=0.3"
scikit-learn = ">=1.4"    # hmmlearn dependency — add explicitly
lxml = ">=5.0"
```

FinBERT/torch/transformers are **removed** — replaced by DeepSeek API. No local model, no GPU requirement, no 700MB Docker layer.

**Dockerfile — new secret mount:**
```dockerfile
# No model bake-in needed. API key injected at runtime via Fly secret.
# DEEPSEEK_API_KEY set via: fly secrets set DEEPSEEK_API_KEY=sk-...
```

**GitHub Actions secrets:** Add `DEEPSEEK_API_KEY` to repo secrets for cron jobs.

**DeepSeek client initialisation (shared across modules):**
```python
# packages/ingest/_deepseek.py
from openai import OpenAI

def get_client() -> OpenAI:
    return OpenAI(
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url="https://api.deepseek.com/v1",
    )

FLASH = "deepseek-v4-flash"   # news sentiment — fast, cheap
PRO   = "deepseek-v4-pro"     # market synthesis — full power
```

---

## 10. Open Questions

1. **VIX futures CFTC code** — verify VX (CBOE) appears in a CFTC-reportable report accessible from the standard archive URL. If not, exclude from universe.
2. **OANDA FX auth** — verify public position endpoint doesn't require API key for all 15 FX symbols.
3. **HMM cold start on thin data** — contracts with < 200 weekly bars skip HMM fit, return `regime_label=null`. UI shows "Insufficient history" in regime cell.
4. **DeepSeek model IDs** — collection page shows `deepseek-v4-flash` and `deepseek-v4-pro` as display names. Verify exact API model ID strings from `api.deepseek.com/v1/models` at implementation time.
5. **`/today` ranking for financials** — physicals rank by `n_zones + total_mag`. Financials: rank by `confluence_score` (DeepSeek-V4-Pro output) when available, fall back to `regime_confidence × abs(am_lf_divergence)` while synthesis is warming up.
6. **DeepSeek API rate limits** — Flash batch scoring 300 headlines daily is well within limits. Pro synthesis of 80 markets weekly should also be fine. Verify TPM limits on the free/paid tier before launch.

---

## 11. Implementation Phases

**Phase A — Data + backend (~1 week):**
- Expand universe (physicals completion + all financials)
- `tff_cot.py` + extend `cftc_cot.py` for missing physicals
- `retail_sentiment.py` (all 5 sources)
- `news_sentiment.py` (FinBERT, incremental)
- `regime.py` (HMM, all ~80 symbols)
- `zones.py` divergence columns (physical + financial variants)
- Schema + API endpoint updates

**Phase B — Frontend (~1 week):**
- `IntelStrip.svelte`
- OI pane in `Chart.svelte`
- COT breakdown section (both market_type variants)
- Retail sentiment section (source mix adapts)
- FinBERT scores on NewsRail
- Sidebar physicals/financials split
- `/today` route: regime badge for financials

**Phase C — Infra (~2 days):**
- Dockerfile torch CPU wheel + FinBERT bake-in
- Cron extensions (TFF ZIPs + daily scrapes)
- Verify all ~80 CFTC codes against live archive headers
