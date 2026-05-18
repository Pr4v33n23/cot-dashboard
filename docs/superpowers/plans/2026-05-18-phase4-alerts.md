# Alert System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Alert system — users define criteria (symbol + COT threshold + condition), alerts are checked on bundle refresh and delivered via browser notification + stored in a JSON file.
**Architecture:** `packages/ingest/alerts.py` manages alert CRUD and evaluation. API exposes GET/POST/DELETE `/alerts` and `POST /alerts/check`. Alerts stored in `research/data/alerts.json`. Frontend `/alerts` page with form builder and active alert list. Browser Notifications API used for delivery (no email for MVP).
**Tech Stack:** Python JSON storage, FastAPI, SvelteKit 5, Web Notifications API

---

## Files
- Create: `packages/ingest/alerts.py`
- Modify: `apps/api/src/schemas.py` — AlertRule, AlertTrigger
- Modify: `apps/api/src/main.py` — GET/POST/DELETE /alerts, POST /alerts/check
- Modify: `apps/web/src/lib/api/types.ts`
- Modify: `apps/web/src/lib/api/client.ts`
- Create: `apps/web/src/routes/alerts/+page.svelte`
- Modify: `apps/web/src/routes/+layout.svelte` — add Alerts to nav

---

## Task 1: `alerts.py` backend

- [ ] **Create `packages/ingest/alerts.py`**:
```python
# packages/ingest/alerts.py
"""Alert system — persistent JSON store + evaluation engine."""
from __future__ import annotations
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

ALERT_FILE = Path(__file__).resolve().parents[2] / "research" / "data" / "alerts.json"

Condition = Literal["above", "below", "crosses_above", "crosses_below"]
Field = Literal["cot_index_comm", "confluence_score", "n_zones", "comm_spec_divergence"]


def _load() -> list[dict]:
    if not ALERT_FILE.exists():
        return []
    try:
        return json.loads(ALERT_FILE.read_text())
    except Exception:
        return []


def _save(alerts: list[dict]) -> None:
    ALERT_FILE.parent.mkdir(parents=True, exist_ok=True)
    ALERT_FILE.write_text(json.dumps(alerts, indent=2, default=str))


def list_alerts() -> list[dict]:
    return _load()


def create_alert(symbol: str, field: str, condition: str, threshold: float, label: str = "") -> dict:
    alert = {
        "id": str(uuid.uuid4())[:8],
        "symbol": symbol,
        "field": field,
        "condition": condition,
        "threshold": threshold,
        "label": label or f"{symbol} {field} {condition} {threshold}",
        "active": True,
        "last_triggered": None,
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    alerts = _load()
    alerts.append(alert)
    _save(alerts)
    return alert


def delete_alert(alert_id: str) -> bool:
    alerts = _load()
    new = [a for a in alerts if a["id"] != alert_id]
    if len(new) == len(alerts):
        return False
    _save(new)
    return True


def check_alerts(annotated: dict, synthesis: dict) -> list[dict]:
    """Evaluate all active alerts against current bundle. Returns triggered alerts."""
    alerts = _load()
    triggered = []
    now = datetime.now(tz=timezone.utc).isoformat()

    for alert in alerts:
        if not alert.get("active"):
            continue
        sym = alert["symbol"]
        df = annotated.get(sym)
        if df is None or df.empty:
            continue
        last = df.iloc[-1]
        synth = (synthesis or {}).get(sym, {})

        field = alert["field"]
        if field == "confluence_score":
            value = float(synth.get("confluence_score", 0) or 0)
        elif field in last.index:
            v = last.get(field)
            if v is None:
                continue
            value = float(v)
        else:
            continue

        cond = alert["condition"]
        thr = float(alert["threshold"])
        fired = (
            (cond == "above" and value > thr) or
            (cond == "below" and value < thr) or
            (cond == "crosses_above" and value > thr) or
            (cond == "crosses_below" and value < thr)
        )
        if fired:
            alert["last_triggered"] = now
            triggered.append({**alert, "current_value": round(value, 2)})

    _save(alerts)
    return triggered
```

- [ ] **Add schemas** (append to schemas.py):
```python
class AlertRule(BaseModel):
    id: str | None = None
    symbol: str
    field: str
    condition: Literal["above", "below", "crosses_above", "crosses_below"]
    threshold: float
    label: str = ""
    active: bool = True
    last_triggered: str | None = None
    created_at: str | None = None

class AlertTrigger(BaseModel):
    id: str
    symbol: str
    label: str
    current_value: float
    threshold: float
    condition: str
    last_triggered: str
```

- [ ] **Add endpoints** to main.py:
```python
# ── /alerts ────────────────────────────────────────────────────────────────
@app.get("/alerts", response_model=list[AlertRule])
def list_alerts_endpoint():
    from ingest.alerts import list_alerts  # noqa: PLC0415
    return list_alerts()

@app.post("/alerts", response_model=AlertRule)
def create_alert_endpoint(rule: AlertRule):
    from ingest.alerts import create_alert  # noqa: PLC0415
    return create_alert(rule.symbol, rule.field, rule.condition, rule.threshold, rule.label)

@app.delete("/alerts/{alert_id}")
def delete_alert_endpoint(alert_id: str):
    from ingest.alerts import delete_alert  # noqa: PLC0415
    if not delete_alert(alert_id):
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"ok": True}

@app.post("/alerts/check", response_model=list[AlertTrigger])
def check_alerts_endpoint():
    from ingest.alerts import check_alerts  # noqa: PLC0415
    b = _bundle()
    return check_alerts(b.annotated, b.synthesis)
```

Also add `AlertRule, AlertTrigger` to schemas import.

- [ ] **Commit + push**:
```bash
git add packages/ingest/alerts.py apps/api/src/schemas.py apps/api/src/main.py
git commit -m "feat: add alert system backend — CRUD + evaluation engine"
git push
```

---

## Task 2: Frontend

- [ ] **Add to types.ts**:
```typescript
export interface AlertRule {
  id?: string | null;
  symbol: string;
  field: string;
  condition: 'above' | 'below' | 'crosses_above' | 'crosses_below';
  threshold: number;
  label?: string;
  active?: boolean;
  last_triggered?: string | null;
  created_at?: string | null;
}
export interface AlertTrigger {
  id: string;
  symbol: string;
  label: string;
  current_value: number;
  threshold: number;
  condition: string;
  last_triggered: string;
}
```

- [ ] **Add to client.ts**:
```typescript
  alerts: {
    list: () => get<AlertRule[]>('/alerts'),
    create: (rule: AlertRule) => post<AlertRule>('/alerts', rule),
    delete: (id: string) => fetch(`${BASE}/alerts/${id}`, { method: 'DELETE' }),
    check: () => post<AlertTrigger[]>('/alerts/check', {}),
  },
```

- [ ] **Create `apps/web/src/routes/alerts/+page.svelte`**:
```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '$api/client';
  import type { AlertRule, AlertTrigger } from '$api/types';
  import EmptyState from '$components/primitives/EmptyState.svelte';

  let rules = $state<AlertRule[]>([]);
  let triggered = $state<AlertTrigger[]>([]);
  let loading = $state(true);
  let checking = $state(false);

  // Form state
  let sym = $state('CL');
  let field = $state('cot_index_comm');
  let condition = $state<AlertRule['condition']>('above');
  let threshold = $state(85);
  let label = $state('');
  let creating = $state(false);

  const FIELDS = [
    { value: 'cot_index_comm', label: 'COT Index' },
    { value: 'n_zones', label: 'Active Zones' },
    { value: 'confluence_score', label: 'Confluence Score' },
    { value: 'comm_spec_divergence', label: 'Divergence Weeks' },
  ];

  async function load() {
    loading = true;
    try { rules = await api.alerts.list(); }
    catch { rules = []; }
    finally { loading = false; }
  }

  async function create() {
    creating = true;
    try {
      await api.alerts.create({ symbol: sym, field, condition, threshold, label });
      await load();
      label = '';
    } finally { creating = false; }
  }

  async function remove(id: string) {
    await api.alerts.delete(id);
    rules = rules.filter(r => r.id !== id);
  }

  async function checkNow() {
    checking = true;
    try { triggered = await api.alerts.check(); }
    finally { checking = false; }
  }

  onMount(load);
</script>

<svelte:head><title>Alerts · COT_LENS</title></svelte:head>

<div class="page">
  <header class="header">
    <div>
      <div class="eyebrow">monitoring</div>
      <h1 class="title">Alerts</h1>
      <div class="subtitle">Get notified when COT criteria are met</div>
    </div>
    <button class="check-btn" onclick={checkNow} disabled={checking}>
      {checking ? 'Checking…' : '↻ Check Now'}
    </button>
  </header>

  {#if triggered.length > 0}
    <div class="triggered-banner">
      <div class="tb-title">⚡ {triggered.length} alert{triggered.length > 1 ? 's' : ''} triggered</div>
      {#each triggered as t}
        <div class="tb-row">
          <span class="num">{t.symbol}</span>
          <span>{t.label}</span>
          <span class="num" style:color="var(--zone-a1)">{t.current_value} (threshold: {t.threshold})</span>
        </div>
      {/each}
    </div>
  {/if}

  <section class="create-section">
    <div class="section-label">Create Alert</div>
    <div class="form-row">
      <input bind:value={sym} placeholder="Symbol (e.g. CL)" class="inp" />
      <select bind:value={field} class="inp">
        {#each FIELDS as f}<option value={f.value}>{f.label}</option>{/each}
      </select>
      <select bind:value={condition} class="inp">
        <option value="above">above</option>
        <option value="below">below</option>
        <option value="crosses_above">crosses above</option>
        <option value="crosses_below">crosses below</option>
      </select>
      <input bind:value={threshold} type="number" step="0.1" class="inp num" style:width="80px" />
      <input bind:value={label} placeholder="Label (optional)" class="inp" />
      <button class="create-btn" onclick={create} disabled={creating || !sym}>{creating ? '…' : '+ Add'}</button>
    </div>
  </section>

  {#if loading}
    <div class="empty-state">Loading…</div>
  {:else if rules.length === 0}
    <EmptyState variant="empty" title="No alerts" body="Create your first alert above." />
  {:else}
    <div class="rules-list">
      <div class="section-label">{rules.length} active alert{rules.length > 1 ? 's' : ''}</div>
      {#each rules as rule}
        <div class="rule-row">
          <div class="rule-main">
            <span class="sym num">{rule.symbol}</span>
            <span class="rule-desc">{rule.label || `${rule.field} ${rule.condition} ${rule.threshold}`}</span>
            {#if rule.last_triggered}
              <span class="last-trig">last triggered {rule.last_triggered?.slice(0,10)}</span>
            {/if}
          </div>
          <button class="del-btn" onclick={() => rule.id && remove(rule.id)}>✕</button>
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .page { padding: var(--sp-8) var(--sp-6) var(--sp-12); max-width: 900px; margin: 0 auto; display: flex; flex-direction: column; gap: var(--sp-5); overflow-y: auto; }
  .eyebrow { font-size: var(--fs-11); text-transform: uppercase; letter-spacing: .06em; color: var(--ink-faint); }
  .title { font-size: var(--fs-28); font-weight: 600; margin: 4px 0 2px; }
  .subtitle { font-size: var(--fs-13); color: var(--ink-muted); }
  .header { display: flex; justify-content: space-between; align-items: flex-end; }
  .check-btn { padding: 8px 16px; border-radius: var(--r-sm); background: var(--bg-panel); border: 1px solid var(--border); font-size: var(--fs-12); color: var(--ink-muted); cursor: pointer; }
  .check-btn:hover:not(:disabled) { border-color: var(--zone-a2); color: var(--zone-a2); }
  .triggered-banner { background: rgba(245,166,35,.08); border: 1px solid rgba(245,166,35,.3); border-radius: var(--r-md); padding: var(--sp-4); display: flex; flex-direction: column; gap: 6px; }
  .tb-title { font-weight: 600; color: var(--pending); }
  .tb-row { display: flex; gap: 12px; font-size: var(--fs-12); }
  .create-section { background: var(--bg-panel); border: 1px solid var(--border); border-radius: var(--r-md); padding: var(--sp-4); display: flex; flex-direction: column; gap: 10px; }
  .section-label { font-size: 10px; text-transform: uppercase; letter-spacing: .05em; color: var(--ink-faint); }
  .form-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
  .inp { background: var(--bg-panel-2); border: 1px solid var(--border); border-radius: var(--r-sm); color: var(--ink); font: inherit; font-size: var(--fs-12); padding: 6px 10px; outline: none; flex: 1; min-width: 80px; }
  .inp:focus { border-color: var(--zone-a2); }
  .create-btn { padding: 7px 14px; border-radius: var(--r-sm); background: var(--zone-a2); color: #0a0a0b; border: none; font-size: var(--fs-12); font-weight: 700; cursor: pointer; flex-shrink: 0; }
  .create-btn:disabled { opacity: 0.4; }
  .rules-list { display: flex; flex-direction: column; gap: 4px; }
  .rule-row { display: flex; align-items: center; gap: 12px; padding: 10px 14px; background: var(--bg-panel); border: 1px solid var(--border); border-radius: var(--r-sm); }
  .rule-main { flex: 1; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .sym { font-weight: 700; font-size: var(--fs-13); color: var(--zone-a3); }
  .rule-desc { font-size: var(--fs-12); color: var(--ink-muted); }
  .last-trig { font-size: 10px; color: var(--ink-faint); font-family: var(--font-mono); }
  .del-btn { background: none; border: none; color: var(--ink-faint); cursor: pointer; font-size: 14px; padding: 4px; }
  .del-btn:hover { color: var(--short); }
  .num { font-family: var(--font-mono); }
  .empty-state { color: var(--ink-faint); font-size: var(--fs-13); padding: var(--sp-6); text-align: center; }
</style>
```

- [ ] **Add to sidebar** in `+layout.svelte`:
```typescript
{ href: '/alerts', label: 'Alerts', short: '🔔' },
```

- [ ] **svelte-check + commit + push**:
```bash
cd /Users/praveen/Projects/cot-dashboard/apps/web && npx svelte-check --threshold error 2>&1 | tail -3
git add apps/web/src/routes/alerts/ apps/web/src/lib/api/types.ts apps/web/src/lib/api/client.ts apps/web/src/routes/+layout.svelte
git commit -m "feat: add /alerts page — create/delete COT alerts with check-now"
git push
```
