# Cross-Market Correlation Matrix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cross-market correlation page showing rolling 90-day price correlation matrix across all markets.
**Architecture:** `GET /correlation` computes rolling 90-day Pearson correlation of daily log-returns for all symbols with sufficient data, returns a matrix. Frontend renders a color-coded correlation heatmap grid. Users can click a cell to see the correlation chart.
**Tech Stack:** Python pandas/numpy correlation, FastAPI, SvelteKit 5

---

## Files
- Modify: `apps/api/src/schemas.py` — CorrelationResponse
- Modify: `apps/api/src/main.py` — GET /correlation
- Modify: `apps/web/src/lib/api/types.ts`
- Modify: `apps/web/src/lib/api/client.ts`
- Create: `apps/web/src/routes/correlation/+page.svelte`
- Modify: `apps/web/src/routes/+layout.svelte`

---

## Task 1: Backend

- [ ] **Add schemas** (append to schemas.py):
```python
class CorrelationResponse(BaseModel):
    symbols: list[str]
    matrix: list[list[float | None]]   # NxN, None = insufficient data
    as_of: date
```

- [ ] **Add endpoint** (append to main.py):
```python
# ── /correlation ───────────────────────────────────────────────────────────
@app.get("/correlation", response_model=CorrelationResponse)
def correlation_endpoint(window: int = Query(default=90, ge=20, le=365)) -> CorrelationResponse:
    """Rolling correlation matrix of daily log-returns across all loaded markets."""
    import numpy as np  # noqa: PLC0415
    b = _bundle()

    # Build aligned price matrix (last `window` days)
    series: dict[str, "pd.Series"] = {}
    for sym, df in b.annotated.items():
        if df.empty or "close" not in df.columns:
            continue
        close = df.set_index("date")["close"].dropna()
        if len(close) < window + 5:
            continue
        log_ret = close.apply(lambda x: float(x)).pct_change().tail(window)
        series[sym] = log_ret

    if not series:
        return CorrelationResponse(symbols=[], matrix=[], as_of=__import__('datetime').date.today())

    symbols = sorted(series.keys())
    n = len(symbols)
    matrix: list[list[float | None]] = [[None] * n for _ in range(n)]

    for i, s1 in enumerate(symbols):
        matrix[i][i] = 1.0
        for j, s2 in enumerate(symbols):
            if j <= i:
                continue
            aligned = pd.concat([series[s1], series[s2]], axis=1).dropna()
            if len(aligned) < 20:
                continue
            corr = float(aligned.iloc[:,0].corr(aligned.iloc[:,1]))
            if not (corr != corr):  # check NaN
                matrix[i][j] = round(corr, 3)
                matrix[j][i] = round(corr, 3)

    from datetime import date as _date  # noqa: PLC0415
    return CorrelationResponse(symbols=symbols, matrix=matrix, as_of=_date.today())
```

Also add `CorrelationResponse` to schemas import.

- [ ] **Commit + push**:
```bash
git add apps/api/src/schemas.py apps/api/src/main.py
git commit -m "feat: add GET /correlation — rolling 90d price correlation matrix"
git push
```

---

## Task 2: Frontend

- [ ] **Add to types.ts**:
```typescript
export interface CorrelationResponse { symbols: string[]; matrix: (number | null)[][]; as_of: string; }
```

- [ ] **Add to client.ts**:
```typescript
  correlation: (window?: number) => get<CorrelationResponse>(`/correlation${window ? `?window=${window}` : ''}`),
```

- [ ] **Create `apps/web/src/routes/correlation/+page.svelte`**:
```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '$api/client';
  import type { CorrelationResponse } from '$api/types';
  import EmptyState from '$components/primitives/EmptyState.svelte';
  import Skeleton from '$components/primitives/Skeleton.svelte';

  let resp = $state<CorrelationResponse | null>(null);
  let loading = $state(true);
  let error = $state<string | null>(null);
  let window_days = $state(90);
  let hoveredCell = $state<{i: number, j: number, v: number | null} | null>(null);

  async function load() {
    loading = true; error = null;
    try { resp = await api.correlation(window_days); }
    catch (e) { error = (e as Error).message; }
    finally { loading = false; }
  }

  onMount(load);

  function corrColor(v: number | null): string {
    if (v == null) return 'var(--bg-panel-2)';
    if (v >= 0.7) return `rgba(24,224,143,${0.3 + v * 0.5})`;
    if (v <= -0.7) return `rgba(255,90,95,${0.3 + Math.abs(v) * 0.5})`;
    if (Math.abs(v) < 0.3) return 'rgba(138,138,147,0.15)';
    return v > 0 ? `rgba(24,224,143,${Math.abs(v) * 0.4})` : `rgba(255,90,95,${Math.abs(v) * 0.4})`;
  }

  function corrTextColor(v: number | null): string {
    if (v == null) return 'var(--ink-faint)';
    if (Math.abs(v ?? 0) > 0.5) return 'var(--ink)';
    return 'var(--ink-muted)';
  }
</script>

<svelte:head><title>Correlation · COT_LENS</title></svelte:head>

<div class="page">
  <header class="header">
    <div>
      <div class="eyebrow">analysis</div>
      <h1 class="title">Correlation Matrix</h1>
      <div class="subtitle">Rolling {window_days}-day price correlation across all markets</div>
    </div>
    <div class="controls">
      {#each [30, 60, 90, 180] as w}
        <button class="w-btn" class:active={window_days === w} onclick={() => { window_days = w; load(); }}>{w}d</button>
      {/each}
    </div>
  </header>

  {#if hoveredCell && resp}
    <div class="hover-info">
      <span class="num">{resp.symbols[hoveredCell.i]}</span> × <span class="num">{resp.symbols[hoveredCell.j]}</span>:
      <strong style:color={corrColor(hoveredCell.v)}>{hoveredCell.v?.toFixed(3) ?? 'N/A'}</strong>
    </div>
  {/if}

  {#if loading}
    <Skeleton width="100%" height="400px" radius="var(--r-md)" />
  {:else if error}
    <EmptyState variant="error" title="Couldn't load correlation" body={error} retry={load} />
  {:else if resp && resp.symbols.length > 0}
    <div class="matrix-wrap">
      <table class="matrix">
        <thead>
          <tr>
            <th class="corner"></th>
            {#each resp.symbols as sym}
              <th class="col-head num">{sym}</th>
            {/each}
          </tr>
        </thead>
        <tbody>
          {#each resp.symbols as rowSym, i}
            <tr>
              <th class="row-head num">{rowSym}</th>
              {#each resp.symbols as _, j}
                {@const v = resp.matrix[i]?.[j] ?? null}
                <td
                  class="cell"
                  style:background={corrColor(v)}
                  style:color={corrTextColor(v)}
                  onmouseenter={() => hoveredCell = {i, j, v}}
                  onmouseleave={() => hoveredCell = null}
                  title={`${rowSym} × ${resp.symbols[j]}: ${v?.toFixed(3) ?? 'N/A'}`}
                >
                  {#if i !== j && v != null}
                    <span class="num" style:font-size="9px">{v.toFixed(2)}</span>
                  {:else if i === j}
                    <span style:color="var(--ink-faint)" style:font-size="9px">1</span>
                  {/if}
                </td>
              {/each}
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
    <div class="legend">
      <span class="leg-item" style:color="var(--long)">■ High positive</span>
      <span class="leg-item" style:color="var(--ink-faint)">■ Uncorrelated</span>
      <span class="leg-item" style:color="var(--short)">■ Negative</span>
      <span class="leg-item muted">as of {resp.as_of}</span>
    </div>
  {/if}
</div>

<style>
  .page { padding: var(--sp-6); display: flex; flex-direction: column; gap: var(--sp-4); height: 100%; min-height: 0; overflow: auto; }
  .eyebrow { font-size: var(--fs-11); text-transform: uppercase; letter-spacing: .06em; color: var(--ink-faint); }
  .title { font-size: var(--fs-20); font-weight: 600; margin: 2px 0 0; }
  .subtitle { font-size: var(--fs-12); color: var(--ink-muted); }
  .header { display: flex; justify-content: space-between; align-items: flex-end; }
  .controls { display: flex; gap: 4px; }
  .w-btn { padding: 5px 10px; border-radius: var(--r-sm); border: 1px solid var(--border); background: var(--bg-panel); font-size: var(--fs-12); color: var(--ink-muted); cursor: pointer; font-family: var(--font-mono); }
  .w-btn.active { border-color: var(--zone-a2); color: var(--zone-a2); }
  .hover-info { padding: 8px 12px; background: var(--bg-panel); border: 1px solid var(--border); border-radius: var(--r-sm); font-size: var(--fs-12); }
  .matrix-wrap { overflow: auto; flex: 1; }
  .matrix { border-collapse: collapse; }
  .corner, .col-head, .row-head { padding: 4px 6px; font-size: 9px; font-family: var(--font-mono); font-weight: 700; color: var(--ink-muted); white-space: nowrap; }
  .col-head { text-align: center; writing-mode: vertical-lr; transform: rotate(180deg); height: 60px; vertical-align: bottom; }
  .row-head { text-align: right; }
  .cell { width: 16px; height: 16px; text-align: center; cursor: default; }
  .legend { display: flex; gap: 16px; font-size: 11px; }
  .leg-item { display: flex; align-items: center; gap: 4px; }
  .muted { color: var(--ink-faint); margin-left: auto; font-family: var(--font-mono); }
</style>
```

- [ ] **Add to sidebar** in `+layout.svelte`:
```typescript
{ href: '/correlation', label: 'Correlation', short: '⊗' },
```

- [ ] **svelte-check + commit + push**:
```bash
cd /Users/praveen/Projects/cot-dashboard/apps/web && npx svelte-check --threshold error 2>&1 | tail -3
git add apps/web/src/routes/correlation/ apps/web/src/lib/api/types.ts apps/web/src/lib/api/client.ts apps/web/src/routes/+layout.svelte
git commit -m "feat: add /correlation — 90-day rolling price correlation matrix"
git push
```
