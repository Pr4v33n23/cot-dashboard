# Historical Analog Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Historical Analog Engine — for any market, find the 5 most similar historical COT profiles and show what price did 4/8/12 weeks later.
**Architecture:** `GET /analogues/{symbol}` scans the full annotated history for the symbol, computes cosine similarity between current [cot_index, divergence_weeks, n_zones, oi_change] vector and every historical 4-week window, returns top 5 with forward price performance. Frontend shows a compact analog list in a section on the market detail page.
**Tech Stack:** Python, numpy cosine similarity, FastAPI, Svelte 5

---

## Files
- Modify: `apps/api/src/schemas.py` — add AnalogueEntry, AnaloguesResponse
- Modify: `apps/api/src/main.py` — add GET /analogues/{symbol}
- Modify: `apps/web/src/lib/api/types.ts` — add AnalogueEntry, AnaloguesResponse
- Modify: `apps/web/src/lib/api/client.ts` — add analogues()
- Modify: `apps/web/src/routes/market/[symbol]/+page.svelte` — add analogue section

---

## Task 1: Backend

- [ ] **Add schemas** (append to schemas.py):
```python
class AnalogueEntry(BaseModel):
    date: date
    weeks_ago: int
    similarity: float           # 0-1, higher = more similar
    cot_index_then: float
    price_then: float | None
    fwd_4w_pct: float | None    # price change 4 weeks after
    fwd_8w_pct: float | None
    fwd_12w_pct: float | None

class AnaloguesResponse(BaseModel):
    symbol: str
    current_cot_index: float | None
    analogues: list[AnalogueEntry]
```

- [ ] **Add endpoint** to main.py:
```python
# ── /analogues/{symbol} ────────────────────────────────────────────────────
@app.get("/analogues/{symbol}", response_model=AnaloguesResponse)
def analogues_endpoint(symbol: str, top_n: int = Query(default=5, le=10)) -> AnaloguesResponse:
    """Find the N most similar historical COT profiles for this symbol."""
    import numpy as np  # noqa: PLC0415
    b = _bundle()
    df = b.annotated.get(symbol)
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail=f"No data for {symbol}")

    # Feature vector: [cot_index_norm, divergence_weeks_norm, n_zones_norm, oi_chg_norm]
    def _vec(row):
        ci = float(row.get("cot_index_comm", 50) or 50) / 100.0
        dw = min(float(row.get("comm_spec_divergence", 0) or row.get("am_lf_divergence", 0) or 0), 12) / 12.0
        nz = float(row.get("n_zones", 0) or 0) / 5.0
        return np.array([ci, dw, nz])

    current_row = df.iloc[-1]
    current_vec = _vec(current_row)
    current_cot = float(current_row.get("cot_index_comm", 50) or 50)
    norm_cur = np.linalg.norm(current_vec)

    results = []
    close_col = "close"
    # Only scan history up to 4 weeks before present (avoid look-ahead)
    cutoff = len(df) - 4
    for i in range(52, cutoff):
        row = df.iloc[i]
        vec = _vec(row)
        norm_v = np.linalg.norm(vec)
        if norm_cur < 1e-9 or norm_v < 1e-9:
            continue
        sim = float(np.dot(current_vec, vec) / (norm_cur * norm_v))
        # Forward returns
        def _fwd(weeks):
            j = i + weeks
            if j >= len(df):
                return None
            p0 = df.iloc[i].get(close_col)
            p1 = df.iloc[j].get(close_col)
            if p0 and p1 and float(p0) > 0:
                return round((float(p1) - float(p0)) / float(p0) * 100, 2)
            return None

        results.append(AnalogueEntry(
            date=row["date"].date() if hasattr(row["date"], "date") else row["date"],
            weeks_ago=len(df) - 1 - i,
            similarity=round(sim, 3),
            cot_index_then=round(float(row.get("cot_index_comm", 50) or 50), 1),
            price_then=float(row.get(close_col)) if row.get(close_col) else None,
            fwd_4w_pct=_fwd(4),
            fwd_8w_pct=_fwd(8),
            fwd_12w_pct=_fwd(12),
        ))

    results.sort(key=lambda x: x.similarity, reverse=True)
    return AnaloguesResponse(
        symbol=symbol,
        current_cot_index=round(current_cot, 1),
        analogues=results[:top_n],
    )
```

Also add `AnalogueEntry, AnaloguesResponse` to schemas import.

- [ ] **Commit + push**:
```bash
git add apps/api/src/schemas.py apps/api/src/main.py
git commit -m "feat: add GET /analogues/{symbol} — historical COT similarity search"
git push
```

---

## Task 2: Frontend — types + client + section in market detail

- [ ] **Add to types.ts**:
```typescript
export interface AnalogueEntry {
  date: string;
  weeks_ago: number;
  similarity: number;
  cot_index_then: number;
  price_then: number | null;
  fwd_4w_pct: number | null;
  fwd_8w_pct: number | null;
  fwd_12w_pct: number | null;
}
export interface AnaloguesResponse {
  symbol: string;
  current_cot_index: number | null;
  analogues: AnalogueEntry[];
}
```

- [ ] **Add to client.ts**:
```typescript
  analogues: (symbol: string) => get<AnaloguesResponse>(`/analogues/${symbol}`),
```

- [ ] **Add analogue section to `apps/web/src/routes/market/[symbol]/+page.svelte`**

In the `<script>` section, add:
```typescript
let analogues = $state<AnaloguesResponse | null>(null);
```

In the `load()` function, after loading `detail`, also fetch:
```typescript
api.analogues(symbol).then(a => { analogues = a; }).catch(() => {});
```

Add import: `import type { AnaloguesResponse } from '$api/types';`

Add section in the template after the NewsRail section:
```svelte
{#if analogues && analogues.analogues.length > 0}
  <section class="analogues-section">
    <div class="section-label">Historical Analogues · {analogues.analogues.length} closest matches</div>
    <div class="analogue-note">Times when this market's COT profile was most similar to today. Not a signal — historical context only.</div>
    <table class="analogue-table">
      <thead>
        <tr><th>Date</th><th>Wks ago</th><th>Similarity</th><th>COT idx then</th><th>+4w</th><th>+8w</th><th>+12w</th></tr>
      </thead>
      <tbody>
        {#each analogues.analogues as a}
          <tr>
            <td class="num">{a.date}</td>
            <td class="num muted">{a.weeks_ago}</td>
            <td class="num" style:color="var(--zone-a2)">{(a.similarity * 100).toFixed(0)}%</td>
            <td class="num">{a.cot_index_then.toFixed(1)}</td>
            {#each [a.fwd_4w_pct, a.fwd_8w_pct, a.fwd_12w_pct] as pct}
              <td class="num" style:color={pct == null ? 'var(--ink-faint)' : pct > 0 ? 'var(--long)' : 'var(--short)'}>
                {pct == null ? '—' : `${pct > 0 ? '+' : ''}${pct.toFixed(1)}%`}
              </td>
            {/each}
          </tr>
        {/each}
      </tbody>
    </table>
  </section>
{/if}
```

Add CSS:
```css
.analogues-section { display: flex; flex-direction: column; gap: 8px; }
.analogue-note { font-size: 11px; color: var(--ink-faint); font-style: italic; }
.analogue-table { width: 100%; border-collapse: collapse; background: var(--bg-panel); border: 1px solid var(--border); border-radius: var(--r-md); overflow: hidden; }
.analogue-table th { padding: 6px 10px; font-size: 10px; text-transform: uppercase; color: var(--ink-faint); border-bottom: 1px solid var(--border-soft); text-align: left; }
.analogue-table td { padding: 6px 10px; font-size: var(--fs-12); border-bottom: 1px solid var(--border-soft); }
.analogue-table tr:last-child td { border-bottom: none; }
.analogue-table tr:hover td { background: var(--bg-hover); }
.num { font-family: var(--font-mono); }
.muted { color: var(--ink-muted); }
```

- [ ] **svelte-check + commit + push**:
```bash
cd /Users/praveen/Projects/cot-dashboard/apps/web && npx svelte-check --threshold error 2>&1 | tail -3
git add apps/web/src/routes/market/ apps/web/src/lib/api/types.ts apps/web/src/lib/api/client.ts
git commit -m "feat: add historical analogue section to market detail page"
git push
```
