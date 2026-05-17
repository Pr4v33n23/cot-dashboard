# COT Dashboard — `COT_LENS_v1`

Positioning-intelligence dashboard for CME physicals, paired with a deterministic macro news correlator. No LLM commentary, no auto-signals. See [PLAN.md](PLAN.md) for the master design document and [PLAN_v1_archived.md](PLAN_v1_archived.md) + [research/findings.md](research/findings.md) for why the v1 signal-engine approach was archived.

## Status

**Phase 1 — zone engine + news correlator + data spine.** Phase 0 strategy validation was archived after a gate failure (best Sharpe 0.44, 0/23 markets qualifying). The pivot is documented in `findings.md`.

## Phase 1 quickstart

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

The Phase 0 notebook still runs ([research/notebooks/phase0_strategy_validation.ipynb](research/notebooks/phase0_strategy_validation.ipynb)) and is kept as a historical record of the gate failure.

### What's being built in Phase 1

1. **Zone engine** (`packages/ingest/zones.py`) — five "attention lenses" (extreme positioning, price divergence, sector outlier, momentum shift, hedger/speculator imbalance). No buy/sell signals; the engine surfaces *where to look*.
2. **News correlator** (`packages/ingest/news.py` + `news_taxonomy.py`) — pulls yfinance ticker news + USDA WASDE + EIA + FOMC/OPEC calendars + FRED releases. Keyword-tagged to markets via a deterministic taxonomy. No NLP, no sentiment classification.
3. **Data spine** — Parquet on R2, FastAPI origin with `/today`, `/market/:sym`, `/heatmap`, `/divergence/:week`, `/news/:sym`.

### Data-source notes

- **CFTC**: disaggregated futures-only archive (free, public). Schema changed in 2015 — we key off the stable `As_of_Date_In_Form_YYMMDD` column.
- **Prices**: Yahoo Finance via `yfinance`. Stooq added per-symbol captcha + apikey requirement in 2025; yfinance keeps the §0.3 capital stop ($0 spend) intact.
- **News**: yfinance ticker news + USDA / EIA / FOMC / OPEC / FRED — all free.
- **Universe**: 23 physicals (grains, energy, metals, softs, meats). Financials (TFF report) are deferred per §11 Q3.

## Layout

```
packages/ingest/        # Reusable Python modules (will outlive Phase 0)
research/notebooks/     # Phase 0 validation notebook
research/data/cache/    # Local re-downloadable cache (gitignored)
PLAN.md                 # Master design document — single source of truth
```

## Phase 0 stop-losses

Per PLAN.md §0.3:
- **Time stop:** if Phase 0 backtest is not working by 2026-06-15 → pause build.
- **Process stop:** any C-grade trading session during this window → freeze build for 7 days.
- **Capital stop:** $0 spent on vendors/hosting until first signal validates.
