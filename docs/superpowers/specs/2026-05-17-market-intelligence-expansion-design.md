# Market Intelligence Expansion — Design Spec
**Date:** 2026-05-17  
**Status:** Approved  
**Supersedes:** nothing — additive to PLAN.md  

---

## 1. Scope

Expand COT_LENS_v1 with six new intelligence layers, all integrated into the existing market detail page and data pipeline. Nothing is built as a separate service.

| Feature | Approach |
|---|---|
| FX markets | All ~15 CFTC TFF pairs added to universe |
| News sentiment | FinBERT (ProsusAI/finbert) — NLP, not keyword rules |
| HMM regime detector | Per-symbol GaussianHMM (4 hidden states) |
| COT 3-category breakdown | Expose existing columns + divergence signal |
| Open interest | 4th chart pane + intel strip cell |
| CFD retail sentiment | IG + Myfxbook + OANDA, 3-source averaged |

**Layout:** Intelligence strip (4 cells) above chart → chart with OI as 4th pane → COT breakdown section → retail sentiment section → FinBERT-scored news rail.

---

## 2. Data Model Changes

### 2.1 BarRow additions (schemas.py + types.ts)

```python
# schemas.py — BarRow
open_interest: float | None = None
nr_long: float | None = None
nr_short: float | None = None
comm_spec_divergence: int = 0        # weeks active, 0 = not active
regime_label: str | None = None      # "accumulation" | "distribution" | "trending" | "ranging"
regime_proba: list[float] | None = None   # [p0, p1, p2, p3] over 4 states
regime_weeks: int = 0                # consecutive weeks in current regime
```

### 2.2 NewsItem addition
```python
sentiment_score: float | None = None   # FinBERT: positive_prob - negative_prob, -1..+1
sentiment_label: str | None = None     # "positive" | "negative" | "neutral"
```

### 2.3 New response models
```python
class RetailSentimentItem(BaseModel):
    symbol: str
    long_pct: float
    short_pct: float
    source: str            # "ig" | "myfxbook" | "oanda"
    timestamp: datetime

class RetailSentimentResponse(BaseModel):
    symbol: str
    items: list[RetailSentimentItem]
    avg_long_pct: float
    avg_short_pct: float

class RegimeResponse(BaseModel):
    symbol: str
    current_regime: str
    regime_weeks: int
    proba: list[float]               # current bar probability vector
    next_bar_proba: list[float]      # P[current] @ transition_matrix
    transition_matrix: list[list[float]]
    state_names: list[str]           # ordered labels for the 4 states
```

---

## 3. New & Modified Ingest Modules

### 3.1 `packages/ingest/tff_cot.py` — NEW

Downloads CFTC TFF (Traders in Financial Futures) disaggregated futures-only ZIPs. Same year-by-year archive pattern as `cftc_cot.py`.

**Column mapping (TFF → internal):**
```
Dealer_Positions_Long_All    → dealer_long
Dealer_Positions_Short_All   → dealer_short
Asset_Mgr_Positions_Long_All → am_long
Asset_Mgr_Positions_Short_All→ am_short
Lev_Money_Positions_Long_All → lf_long
Lev_Money_Positions_Short_All→ lf_short
Other_Rept_Positions_Long_All→ other_long
Other_Rept_Positions_Short_All→other_short
Open_Interest_All            → open_interest
```

`lf_long/short` is the TFF equivalent of `mm_long/short` (leveraged funds = large specs).  
`net_commercials` for FX = `dealer_long - dealer_short` (dealers hedge physical FX exposure).

Output: same `symbol/date` index as physicals frame — `normalize.py` merges identically.

### 3.2 `packages/ingest/universe.py` — EXTEND

Add `report_type: Literal["disagg", "tff"]` field to `Contract`. Existing 23 physicals get `report_type="disagg"`. New FX contracts get `report_type="tff"`.

**FX universe (~15 contracts):**
```
EURUSD, GBPUSD, JPYUSD, AUDUSD, CADUSD, CHFUSD, NZDUSD,
MXNUSD, BRLUSD, RUBUSD, NOKUSD, SEKUSD, TWDUSD, KRWUSD, INRUSD
```

CFTC codes sourced from TFF disaggregated archive header. YF tickers mapped for price data (`EURUSD=X`, `GBPUSD=X`, etc.).

### 3.3 `packages/ingest/news_sentiment.py` — NEW (FinBERT)

```python
MODEL_ID = "ProsusAI/finbert"   # ~400MB, downloads once, cached to ~/.cache/huggingface
BATCH_SIZE = 32
```

**Interface:**
```python
def load_model() -> tuple[AutoTokenizer, AutoModelForSequenceClassification]:
    """Loads FinBERT. First call downloads; subsequent calls use local cache."""

def score_headlines(news_df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds sentiment_score and sentiment_label columns in-place.
    Skips rows where sentiment_score is already populated (incremental).
    Batches headlines through FinBERT tokenizer → model → softmax.
    sentiment_score = positive_prob - negative_prob  (range -1..+1)
    """
```

**Dependencies added to pyproject.toml:**
```
transformers>=4.40
torch>=2.2          # CPU-only build is fine
```

Scoring runs at daily cron time, not on API requests. Results written back to `news.parquet`. Cold start (first download) ~2 min; warm start ~5s for 300 headlines.

### 3.4 `packages/ingest/regime.py` — NEW (HMM)

```python
N_STATES = 4
FEATURE_COLS = ["log_return", "cot_net_change_pct", "oi_change_pct", "vol_ratio"]
MODEL_CACHE = CACHE_DIR / "regime_{symbol}.pkl"
```

**Pipeline per symbol:**
1. Compute stationary features from annotated DataFrame (all pass ADF stationarity test)
2. Fit `hmmlearn.GaussianHMM(n_components=4, covariance_type="full", n_iter=1000)`  
   Multiple random restarts (n=5), keep highest log-likelihood
3. Post-hoc label states by inspecting mean `log_return` and mean `cot_net_change_pct` per state:
   - High return + rising COT → "trending"
   - Low/negative return + falling COT → "distribution"  
   - Near-zero return + rising COT → "accumulation"
   - Near-zero return + flat COT → "ranging"
4. Decode regime sequence via Viterbi
5. Compute current-bar posterior via forward algorithm
6. Persist model to `regime_{symbol}.pkl`

**Interface:**
```python
def fit_all_regimes(annotated: dict[str, pd.DataFrame]) -> dict[str, Any]:
    """Fit or reload HMM per symbol. Returns {symbol: fitted_model}."""

def annotate_regimes(annotated: dict[str, pd.DataFrame],
                     models: dict[str, Any]) -> dict[str, pd.DataFrame]:
    """Adds regime_label, regime_proba, regime_weeks columns to each frame."""
```

Retrain trigger: weekly, after CFTC data refresh. Incremental: if `regime_{symbol}.pkl` exists and COT data hasn't changed, skip refit.

**Dependency added:**
```
hmmlearn>=0.3
```

### 3.5 `packages/ingest/retail_sentiment.py` — NEW

Three scrapers, one output schema: `{symbol, timestamp, long_pct, short_pct, source}`.

**IG Markets** (`source="ig"`):
- Public JSON endpoint, no auth required
- Returns client sentiment for ~80 instruments
- Epic code → COT symbol mapping (static dict maintained in module)
- Rate limit: 1 req/s, no key needed

**Myfxbook** (`source="myfxbook"`):
- Scrape community outlook HTML page
- Parse long/short percentage table with `lxml`
- Covers ~30 FX pairs — FX symbols only, skip for physicals
- Polite scrape: single request, full page

**OANDA** (`source="oanda"`):
- Public order book/position summary endpoint
- Returns long/short position ratios per instrument
- Instrument code → COT symbol mapping (static dict)

Output written to `research/data/cache/retail_sentiment.parquet`. Rebuilt on daily cron. On query: return all 3 source rows + computed average.

**Dependency added:**
```
lxml>=5.0
```

### 3.6 `packages/ingest/zones.py` — EXTEND

Add `comm_spec_divergence` column:

```python
# Active when commercial net and speculative net (mm for physicals, lf for FX)
# have moved in opposite directions for >= 2 consecutive weekly bars.
# Value = number of consecutive weeks of divergence (0 = not active).
# Richer than A5: fires before extremes are reached, not only at 3y extremes.
```

---

## 4. API Changes

### 4.1 `apps/api/src/data.py` — Bundle additions

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

`build_bundle()` gains:
1. Route each symbol through `tff_cot.load_universe()` or `cftc_cot.load_universe()` based on `report_type`
2. Call `regime.fit_all_regimes(annotated)` and `regime.annotate_regimes(...)`
3. Call `news_sentiment.score_headlines(news_df)` (incremental)
4. Load `retail_sentiment.parquet` into `retail_df`

### 4.2 `apps/api/src/main.py` — New endpoints

```
GET /retail-sentiment/{symbol}  →  RetailSentimentResponse
GET /regime/{symbol}            →  RegimeResponse
```

Existing endpoints unchanged in shape — all BarRow additions are new nullable fields; old clients ignore them.

### 4.3 `apps/web/src/lib/api/` — TS sync

`types.ts` gains new fields on `BarRow` and `NewsItem`, plus `RetailSentimentResponse` and `RegimeResponse` interfaces. `client.ts` gains `retailSentiment(symbol)` and `regime(symbol)` methods.

---

## 5. Frontend Changes

### 5.1 New component: `IntelStrip.svelte`

```
src/lib/components/zone/IntelStrip.svelte
```

4-cell horizontal strip. Props: `{ symbol, divergenceWeeks, retailShortPct, oiChangePct, newsTone }`. Each cell: label + large mono value + sub-line. Divergence cell uses `--zone-a2` (purple) when active.

### 5.2 `Chart.svelte` — 4th pane (OI)

Add OI pane below COT index pane. Redistribute pane fractions so all four sum to 1.0: `PRICE_FRAC=0.55, NETPOS_FRAC=0.18, COT_FRAC=0.13, OI_FRAC=0.14`. Renders as a teal (`--zone-a3`) line. Highlights bars where week-over-week OI change > +5% (confirmation background) or < −5% (liquidation background) with a faint tinted rect.

### 5.3 `market/[symbol]/+page.svelte` — 3 new sections

**Below existing ZoneTimeline:**

1. **IntelStrip** — populated from last bar of `detail.bars` + `retailSentiment` fetch
2. **COT Breakdown** — 4 cards (Commercials, Large Specs / Lev Funds, Asset Managers, Small Specs), each with net position, long/short bar, COT index. Divergence banner when `comm_spec_divergence > 0`.
3. **Retail Sentiment** — 3 source gauges + 3-source average row. Lazy-loaded via `api.retailSentiment(symbol)`.

**NewsRail** — `sentiment_score` shown as a colored badge (+0.82, −0.44) on each headline. Color: green if > 0.2, red if < −0.2, muted if in between.

### 5.4 Sidebar (`+layout.svelte`) — FX section

FX contracts grouped under a new "FX" sector section in the sidebar market list, below the existing commodity sectors. Same click behavior → `/market/[symbol]`.

---

## 6. Cron / Scheduling Changes

**Friday CFTC cron** — extend to also pull TFF ZIPs for FX symbols. Trigger HMM refit after bundle rebuild.

**Daily news cron** — extend to call `news_sentiment.score_headlines()` on new headlines after yfinance fetch.

**Retail sentiment** — run as part of the daily cron (new step before `/refresh`).

---

## 7. New Dependencies

```toml
# pyproject.toml additions
transformers = ">=4.40"
torch = ">=2.2"         # CPU build — add --index-url for torch CPU wheel in Dockerfile
hmmlearn = ">=0.3"      # depends on scikit-learn — add explicitly
scikit-learn = ">=1.4"
lxml = ">=5.0"
```

**Dockerfile note:** `torch` CPU wheel must use the PyTorch CPU index to avoid pulling the 2GB GPU build:
```dockerfile
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu
```

FinBERT model download on first deploy: add `RUN python -c "from transformers import pipeline; pipeline('text-classification', model='ProsusAI/finbert')"` to Dockerfile so the model is baked into the image rather than downloaded at cold start.

---

## 8. Open Questions (resolve before implementation)

1. **OANDA endpoint auth** — verify the public position ratio endpoint doesn't require an API key for the FX instruments we need. If it does, fall back to IG + Myfxbook only.
2. **HMM cold start on thin data** — FX contracts with short history (e.g., KRWUSD, INRUSD) may have < 300 weekly observations. Set minimum threshold: if `len(weekly_data) < 200`, skip HMM fit for that symbol and return `regime_label=null`.
3. **FinBERT Docker image size** — baking the model into the Fly image adds ~400MB. Verify Fly.io free tier storage allows this, or switch to downloading on first start with persistent volume.

---

## 9. Implementation Phases

**Phase A (data + backend):**
- `tff_cot.py` + FX universe
- `retail_sentiment.py`
- `news_sentiment.py` (FinBERT)
- `regime.py` (HMM)
- zones.py divergence column
- schemas + API endpoints

**Phase B (frontend):**
- `IntelStrip.svelte`
- OI pane in `Chart.svelte`
- COT breakdown + retail sentiment sections
- FinBERT scores on NewsRail
- FX in sidebar

**Phase C (infra):**
- Dockerfile torch CPU wheel
- FinBERT model bake-in
- Cron extensions
