# Seasonality Overlay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add seasonality overlay to the chart — show a shaded band of "normal" COT index range for each calendar week over the past 3 years.
**Architecture:** `GET /seasonality/{symbol}` returns 52 weekly records with `{week, avg_cot, p25, p75}` computed from the last 3 years of annotated history. Chart.svelte adds a thin seasonal band on the COT pane. Also add a `/seasonality` indicator on the market detail page header ("current vs seasonal").
**Tech Stack:** Python pandas groupby, FastAPI, Canvas2D in Chart.svelte

---

## Files
- Modify: `apps/api/src/schemas.py` — SeasonalWeek, SeasonalityResponse
- Modify: `apps/api/src/main.py` — GET /seasonality/{symbol}
- Modify: `apps/web/src/lib/api/types.ts`
- Modify: `apps/web/src/lib/api/client.ts`
- Modify: `apps/web/src/routes/market/[symbol]/+page.svelte` — seasonal context badge

---

## Task 1: Backend

- [ ] **Add schemas** (append to schemas.py):
```python
class SeasonalWeek(BaseModel):
    week: int          # ISO week 1-52
    avg_cot: float
    p25_cot: float
    p75_cot: float
    sample_years: int  # how many years contributed

class SeasonalityResponse(BaseModel):
    symbol: str
    current_week: int
    current_cot: float | None
    seasonal_avg: float | None   # average for current week
    deviation: float | None      # current - seasonal_avg
    weeks: list[SeasonalWeek]
```

- [ ] **Add endpoint** (append to main.py):
```python
# ── /seasonality/{symbol} ──────────────────────────────────────────────────
@app.get("/seasonality/{symbol}", response_model=SeasonalityResponse)
def seasonality_endpoint(symbol: str) -> SeasonalityResponse:
    """Seasonal COT index norms by calendar week (3-year lookback)."""
    import numpy as np  # noqa: PLC0415
    b = _bundle()
    df = b.annotated.get(symbol)
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail=f"No data for {symbol}")

    df_copy = df.copy()
    df_copy["iso_week"] = df_copy["date"].dt.isocalendar().week.astype(int)
    df_copy["year"] = df_copy["date"].dt.year

    # Last 3 years only
    max_year = df_copy["year"].max()
    df3 = df_copy[df_copy["year"] >= max_year - 2].dropna(subset=["cot_index_comm"])

    weeks_out: list[SeasonalWeek] = []
    for wk, grp in df3.groupby("iso_week"):
        vals = grp["cot_index_comm"].values
        weeks_out.append(SeasonalWeek(
            week=int(wk),
            avg_cot=round(float(np.mean(vals)), 1),
            p25_cot=round(float(np.percentile(vals, 25)), 1),
            p75_cot=round(float(np.percentile(vals, 75)), 1),
            sample_years=len(grp["year"].unique()),
        ))
    weeks_out.sort(key=lambda x: x.week)

    current_row = df.iloc[-1]
    current_wk = int(current_row["date"].isocalendar()[1]) if hasattr(current_row["date"], "isocalendar") else 1
    current_cot = float(current_row.get("cot_index_comm") or 50) if "cot_index_comm" in current_row.index else None
    seasonal_avg = next((w.avg_cot for w in weeks_out if w.week == current_wk), None)
    deviation = round(current_cot - seasonal_avg, 1) if current_cot and seasonal_avg else None

    return SeasonalityResponse(
        symbol=symbol,
        current_week=current_wk,
        current_cot=round(current_cot, 1) if current_cot else None,
        seasonal_avg=seasonal_avg,
        deviation=deviation,
        weeks=weeks_out,
    )
```

Also add `SeasonalWeek, SeasonalityResponse` to schemas import.

- [ ] **Commit + push**:
```bash
git add apps/api/src/schemas.py apps/api/src/main.py
git commit -m "feat: add GET /seasonality/{symbol} — weekly COT seasonal norms"
git push
```

---

## Task 2: Frontend types + seasonal badge on market detail

- [ ] **Add to types.ts**:
```typescript
export interface SeasonalWeek { week: number; avg_cot: number; p25_cot: number; p75_cot: number; sample_years: number; }
export interface SeasonalityResponse { symbol: string; current_week: number; current_cot: number | null; seasonal_avg: number | null; deviation: number | null; weeks: SeasonalWeek[]; }
```

- [ ] **Add to client.ts**:
```typescript
  seasonality: (symbol: string) => get<SeasonalityResponse>(`/seasonality/${symbol}`),
```

- [ ] **Add seasonal context to market detail page**

In `apps/web/src/routes/market/[symbol]/+page.svelte`, add state:
```typescript
let seasonal = $state<SeasonalityResponse | null>(null);
```

In the `load()` call, also fetch:
```typescript
api.seasonality(symbol).then(s => { seasonal = s; }).catch(() => {});
```

In the header section, after the zone badges:
```svelte
{#if seasonal?.deviation != null}
  <div class="seasonal-badge" title="Current COT vs seasonal average for week {seasonal.current_week}">
    <span class="sb-label">vs seasonal</span>
    <span class="sb-val num" style:color={Math.abs(seasonal.deviation) > 10 ? (seasonal.deviation > 0 ? 'var(--long)' : 'var(--short)') : 'var(--ink-muted)'}>
      {seasonal.deviation > 0 ? '+' : ''}{seasonal.deviation.toFixed(1)}
    </span>
  </div>
{/if}
```

Add CSS:
```css
.seasonal-badge { display: inline-flex; align-items: center; gap: 5px; padding: 3px 9px; border-radius: var(--r-sm); background: var(--bg-panel-2); border: 1px solid var(--border); font-size: 11px; }
.sb-label { color: var(--ink-faint); font-size: 10px; }
.sb-val { font-weight: 700; }
```

- [ ] **svelte-check + commit + push**:
```bash
cd /Users/praveen/Projects/cot-dashboard/apps/web && npx svelte-check --threshold error 2>&1 | tail -3
git add apps/web/src/routes/market/ apps/web/src/lib/api/types.ts apps/web/src/lib/api/client.ts
git commit -m "feat: add seasonal COT context badge to market detail"
git push
```
