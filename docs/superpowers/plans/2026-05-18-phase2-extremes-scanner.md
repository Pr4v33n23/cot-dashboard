# Extremes Scanner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `/extremes` route showing all 47 markets ranked by how close their current COT index is to a 3-year extreme — surfaces "approaching extreme" markets before A1 fires.
**Architecture:** New `GET /extremes` endpoint computes per-symbol "extremeness score" (distance of current COT index from the nearest 90th/10th percentile of its own 3-year history, normalized 0-1). Frontend table with color-coded score column, sortable. Add Extremes to sidebar nav.
**Tech Stack:** Python, FastAPI, pandas quantile, SvelteKit 5

---

## Files
- Create: `apps/web/src/routes/extremes/+page.svelte`
- Modify: `apps/api/src/schemas.py` — add ExtremesRow, ExtremesResponse
- Modify: `apps/api/src/main.py` — add GET /extremes
- Modify: `apps/web/src/lib/api/types.ts` — add ExtremesRow
- Modify: `apps/web/src/lib/api/client.ts` — add extremes()
- Modify: `apps/web/src/routes/+layout.svelte` — add Extremes to nav

---

## Task 1: Backend — /extremes endpoint

- [ ] **Add to schemas.py** (append at end):
```python
class ExtremesRow(BaseModel):
    symbol: str
    name: str
    sector: str
    market_type: str
    cot_index: float | None
    extremeness: float          # 0-1: how close to a 3y extreme (1 = at extreme)
    direction: Literal["long", "short", "neutral"]  # which extreme approaching
    pct_90: float | None        # 90th percentile of 3y COT index
    pct_10: float | None        # 10th percentile
    n_zones: int
    regime_label: str | None
    confluence_score: float
```

- [ ] **Add endpoint to main.py** (after /extremes route):
```python
# ── /extremes ──────────────────────────────────────────────────────────────
@app.get("/extremes", response_model=list[ExtremesRow])
def extremes_endpoint() -> list[ExtremesRow]:
    """All markets ranked by proximity to a 3-year COT positioning extreme."""
    from ingest.universe import UNIVERSE as _UNI  # noqa: PLC0415
    b = _bundle()
    name_map = {c.symbol: c.name for c in _UNI}
    mtype_map = {c.symbol: getattr(c, "market_type", "physical") for c in _UNI}
    rows: list[ExtremesRow] = []
    for sym, df in b.annotated.items():
        if df.empty or "cot_index_comm" not in df.columns:
            continue
        series = df["cot_index_comm"].dropna()
        if len(series) < 52:
            continue
        current = float(series.iloc[-1])
        lookback = series.iloc[-156:] if len(series) >= 156 else series
        p90 = float(lookback.quantile(0.90))
        p10 = float(lookback.quantile(0.10))
        # Extremeness: distance to nearest threshold normalized by threshold distance from 50
        dist_high = max(0.0, current - p90) / max(1.0, 100 - p90)
        dist_low  = max(0.0, p10 - current) / max(1.0, p10)
        extremeness = round(min(1.0, max(dist_high, dist_low)), 3)
        direction = "long" if current > p90 else ("short" if current < p10 else "neutral")
        last = df.iloc[-1]
        synth = (b.synthesis or {}).get(sym, {})
        rows.append(ExtremesRow(
            symbol=sym,
            name=name_map.get(sym, sym),
            sector=sector_of(sym) or "",
            market_type=mtype_map.get(sym, "physical"),
            cot_index=round(current, 1),
            extremeness=extremeness,
            direction=direction,
            pct_90=round(p90, 1),
            pct_10=round(p10, 1),
            n_zones=int(last.get("n_zones", 0) or 0),
            regime_label=str(last.get("regime_label") or "") or None,
            confluence_score=float(synth.get("confluence_score", 0) or 0),
        ))
    rows.sort(key=lambda r: r.extremeness, reverse=True)
    return rows
```

Also add `ExtremesRow` to the schemas import in main.py.

- [ ] **Verify**:
```bash
cd /Users/praveen/Projects/cot-dashboard && PYTHONPATH=packages .venv/bin/python -c "
import sys; sys.path.insert(0,'packages')
from apps.api.src.main import app
routes = {r.path for r in app.routes if hasattr(r,'path')}
assert '/extremes' in routes
print('OK')
" 2>&1
```

- [ ] **Commit + push**:
```bash
git add apps/api/src/schemas.py apps/api/src/main.py
git commit -m "feat: add GET /extremes endpoint — COT proximity ranking"
git push
```

---

## Task 2: Frontend — types + client + page + nav

- [ ] **Add to types.ts** (append):
```typescript
export interface ExtremesRow {
  symbol: string;
  name: string;
  sector: string;
  market_type: string;
  cot_index: number | null;
  extremeness: number;
  direction: 'long' | 'short' | 'neutral';
  pct_90: number | null;
  pct_10: number | null;
  n_zones: number;
  regime_label: string | null;
  confluence_score: number;
}
```

- [ ] **Add to client.ts** `api` object:
```typescript
  extremes: () => get<ExtremesRow[]>('/extremes'),
```
Also add `ExtremesRow` to the import.

- [ ] **Create `apps/web/src/routes/extremes/+page.svelte`**:
```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '$api/client';
  import type { ExtremesRow } from '$api/types';
  import EmptyState from '$components/primitives/EmptyState.svelte';
  import Skeleton from '$components/primitives/Skeleton.svelte';

  let rows = $state<ExtremesRow[]>([]);
  let loading = $state(true);
  let error = $state<string | null>(null);
  let filter = $state<'all' | 'long' | 'short'>('all');

  const filtered = $derived(filter === 'all' ? rows : rows.filter(r => r.direction === filter));

  async function load() {
    loading = true; error = null;
    try { rows = await api.extremes(); }
    catch (e) { error = (e as Error).message; }
    finally { loading = false; }
  }

  onMount(load);

  function extremeColor(e: number): string {
    if (e >= 0.7) return 'var(--zone-a1)';
    if (e >= 0.4) return 'var(--pending)';
    return 'var(--ink-faint)';
  }

  function dirColor(d: string): string {
    return d === 'long' ? 'var(--long)' : d === 'short' ? 'var(--short)' : 'var(--ink-faint)';
  }
</script>

<svelte:head><title>Extremes · COT_LENS</title></svelte:head>

<div class="page">
  <header class="header">
    <div>
      <div class="eyebrow">positioning</div>
      <h1 class="title">Extremes Scanner</h1>
      <div class="subtitle">All markets ranked by proximity to 3-year COT positioning extreme</div>
    </div>
    <div class="filters">
      {#each ['all','long','short'] as f}
        <button class="filter-btn" class:active={filter === f} onclick={() => filter = f as 'all'|'long'|'short'}>{f}</button>
      {/each}
    </div>
  </header>

  {#if loading}
    <div class="sk-list">{#each Array(10) as _}<div class="sk-row">{#each Array(7) as __}<Skeleton width="80px" height="14px" />{/each}</div>{/each}</div>
  {:else if error}
    <EmptyState variant="error" title="Couldn't load extremes" body={error} retry={load} />
  {:else}
    <div class="table-wrap">
      <table class="grid">
        <thead>
          <tr>
            <th>Market</th>
            <th>Sector</th>
            <th>COT Index</th>
            <th>Direction</th>
            <th>Extremeness</th>
            <th>90th %ile</th>
            <th>10th %ile</th>
            <th>Zones</th>
            <th>Regime</th>
          </tr>
        </thead>
        <tbody>
          {#each filtered as r}
            <tr onclick={() => window.location.href = `/market/${r.symbol}`} style:cursor="pointer">
              <td class="sym-cell">
                <span class="sym num">{r.symbol}</span>
                <span class="name">{r.name}</span>
              </td>
              <td><span class="sector-dot" style:background={`var(--sec-${r.sector})`}></span>{r.sector}</td>
              <td class="num" style:color={r.cot_index != null && r.cot_index >= 70 ? 'var(--long)' : r.cot_index != null && r.cot_index <= 30 ? 'var(--short)' : 'var(--ink)'}>{r.cot_index?.toFixed(1) ?? '—'}</td>
              <td class="num" style:color={dirColor(r.direction)}>{r.direction}</td>
              <td>
                <div class="extreme-bar">
                  <div class="extreme-fill" style:width={`${r.extremeness * 100}%`} style:background={extremeColor(r.extremeness)}></div>
                </div>
                <span class="num" style:color={extremeColor(r.extremeness)} style:font-size="10px">{(r.extremeness * 100).toFixed(0)}%</span>
              </td>
              <td class="num muted">{r.pct_90?.toFixed(1) ?? '—'}</td>
              <td class="num muted">{r.pct_10?.toFixed(1) ?? '—'}</td>
              <td class="num">{r.n_zones > 0 ? r.n_zones : '—'}</td>
              <td class="muted">{r.regime_label ?? '—'}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>

<style>
  .page { padding: var(--sp-8) var(--sp-6) var(--sp-12); max-width: 1200px; margin: 0 auto; display: flex; flex-direction: column; gap: var(--sp-6); overflow-y: auto; scrollbar-width: thin; }
  .eyebrow { font-size: var(--fs-11); text-transform: uppercase; letter-spacing: .06em; color: var(--ink-faint); }
  .title { font-size: var(--fs-28); font-weight: 600; margin: 4px 0 2px; }
  .subtitle { font-size: var(--fs-13); color: var(--ink-muted); }
  .header { display: flex; justify-content: space-between; align-items: flex-end; }
  .filters { display: flex; gap: 4px; }
  .filter-btn { padding: 5px 12px; border-radius: var(--r-sm); border: 1px solid var(--border); background: var(--bg-panel); font-size: var(--fs-12); color: var(--ink-muted); cursor: pointer; text-transform: capitalize; }
  .filter-btn.active { border-color: var(--zone-a2); color: var(--zone-a2); background: rgba(183,148,246,.08); }
  .table-wrap { background: var(--bg-panel); border: 1px solid var(--border); border-radius: var(--r-md); overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; }
  th { padding: 8px 12px; text-align: left; font-size: 10px; text-transform: uppercase; letter-spacing: .05em; color: var(--ink-faint); border-bottom: 1px solid var(--border-soft); white-space: nowrap; }
  td { padding: 8px 12px; font-size: var(--fs-12); border-bottom: 1px solid var(--border-soft); }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: var(--bg-hover); }
  .sym-cell { display: flex; flex-direction: column; gap: 1px; }
  .sym { font-weight: 700; font-size: var(--fs-13); }
  .name { font-size: 10px; color: var(--ink-faint); }
  .sector-dot { display: inline-block; width: 6px; height: 6px; border-radius: 50%; margin-right: 5px; vertical-align: middle; }
  .num { font-family: var(--font-mono); }
  .muted { color: var(--ink-muted); }
  .extreme-bar { width: 80px; height: 5px; background: var(--border); border-radius: 3px; overflow: hidden; display: inline-block; vertical-align: middle; margin-right: 5px; }
  .extreme-fill { height: 100%; border-radius: 3px; }
  .sk-list { display: flex; flex-direction: column; gap: 6px; }
  .sk-row { display: flex; gap: 16px; padding: 8px 0; }
</style>
```

- [ ] **Add to sidebar** in `+layout.svelte` routes array (after Divergence, before Chat):
```typescript
{ href: '/extremes', label: 'Extremes', short: 'EX' },
```

- [ ] **svelte-check**:
```bash
cd /Users/praveen/Projects/cot-dashboard/apps/web && npx svelte-check --threshold error 2>&1 | tail -3
```

- [ ] **Commit + push**:
```bash
git add apps/web/src/routes/extremes/ apps/web/src/lib/api/types.ts apps/web/src/lib/api/client.ts apps/web/src/routes/+layout.svelte
git commit -m "feat: add /extremes scanner — all markets ranked by COT proximity to 3y extreme"
git push
```
