# Multi-Chart Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Multi-chart comparison page — pick 2-6 markets and view their charts side by side.
**Architecture:** `/compare` route with a market picker. Uses the existing `api.market()` endpoint (already built) to load data for each selected symbol. Renders a grid of compact Chart components (existing Chart.svelte, reduced height). State is URL-encoded for shareability: `/compare?syms=CL,HG,GC`.
**Tech Stack:** SvelteKit 5, existing Chart.svelte, URL search params

---

## Files
- Create: `apps/web/src/routes/compare/+page.svelte`
- Modify: `apps/web/src/routes/+layout.svelte` — add Compare to nav

---

## Task 1: Compare page

- [ ] **Create `apps/web/src/routes/compare/+page.svelte`**:
```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/state';
  import { api } from '$api/client';
  import type { MarketDetail } from '$api/types';
  import Chart from '$components/chart/Chart.svelte';
  import EmptyState from '$components/primitives/EmptyState.svelte';
  import Skeleton from '$components/primitives/Skeleton.svelte';
  import { universeState } from '$state/universe.svelte';

  const MAX_SYMS = 6;
  let selected = $state<string[]>([]);
  let data = $state<Record<string, MarketDetail | null>>({});
  let loading = $state<Record<string, boolean>>({});
  let searchInput = $state('');

  const filtered = $derived(
    searchInput
      ? universeState.contracts.filter(c =>
          c.symbol.toLowerCase().includes(searchInput.toLowerCase()) ||
          c.name.toLowerCase().includes(searchInput.toLowerCase())
        ).slice(0, 12)
      : []
  );

  function toggle(sym: string) {
    if (selected.includes(sym)) {
      selected = selected.filter(s => s !== sym);
    } else if (selected.length < MAX_SYMS) {
      selected = [...selected, sym];
      loadMarket(sym);
    }
  }

  async function loadMarket(sym: string) {
    loading = { ...loading, [sym]: true };
    try {
      const d = await api.market(sym);
      data = { ...data, [sym]: d };
    } catch {
      data = { ...data, [sym]: null };
    } finally {
      loading = { ...loading, [sym]: false };
    }
  }

  onMount(async () => {
    await universeState.load();
    const symsParam = page.url.searchParams.get('syms');
    if (symsParam) {
      const syms = symsParam.split(',').slice(0, MAX_SYMS);
      selected = syms;
      syms.forEach(loadMarket);
    }
  });

  const cols = $derived(selected.length <= 2 ? 1 : selected.length <= 4 ? 2 : 2);
</script>

<svelte:head><title>Compare · COT_LENS</title></svelte:head>

<div class="page">
  <header class="header">
    <div>
      <div class="eyebrow">analysis</div>
      <h1 class="title">Compare</h1>
      <div class="subtitle">Side-by-side chart comparison (up to 6 markets)</div>
    </div>
  </header>

  <div class="picker">
    <div class="search-wrap">
      <input bind:value={searchInput} placeholder="Search markets to add…" class="search-inp" />
      {#if filtered.length > 0}
        <div class="suggestions">
          {#each filtered as c}
            <button class="sug-btn" class:sel={selected.includes(c.symbol)} onclick={() => toggle(c.symbol)}>
              <span class="num">{c.symbol}</span> <span class="sug-name">{c.name}</span>
              {#if selected.includes(c.symbol)}<span class="sel-check">✓</span>{/if}
            </button>
          {/each}
        </div>
      {/if}
    </div>
    <div class="chips">
      {#each selected as sym}
        <div class="chip">
          <span class="num">{sym}</span>
          <button class="chip-del" onclick={() => toggle(sym)}>✕</button>
        </div>
      {/each}
    </div>
  </div>

  {#if selected.length === 0}
    <EmptyState variant="empty" title="No markets selected" body="Search above to add up to 6 markets for side-by-side comparison." />
  {:else}
    <div class="charts-grid" style:grid-template-columns={`repeat(${cols}, 1fr)`}>
      {#each selected as sym}
        <div class="chart-panel">
          <div class="cp-header">
            <a href="/market/{sym}" class="cp-sym num">{sym}</a>
            {#if data[sym]?.contract}
              <span class="cp-name">{data[sym]?.contract.name}</span>
            {/if}
          </div>
          {#if loading[sym]}
            <Skeleton width="100%" height="280px" radius="var(--r-md)" />
          {:else if data[sym]}
            <Chart bars={data[sym]!.bars} height={280} />
          {:else}
            <div class="cp-error">Failed to load</div>
          {/if}
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .page { padding: var(--sp-6); display: flex; flex-direction: column; gap: var(--sp-4); height: 100%; min-height: 0; overflow-y: auto; scrollbar-width: thin; }
  .eyebrow { font-size: var(--fs-11); text-transform: uppercase; letter-spacing: .06em; color: var(--ink-faint); }
  .title { font-size: var(--fs-20); font-weight: 600; margin: 2px 0 0; }
  .subtitle { font-size: var(--fs-12); color: var(--ink-muted); }
  .picker { display: flex; flex-direction: column; gap: 8px; }
  .search-wrap { position: relative; }
  .search-inp { width: 100%; background: var(--bg-panel); border: 1px solid var(--border); border-radius: var(--r-sm); color: var(--ink); font: inherit; font-size: var(--fs-13); padding: 8px 12px; outline: none; }
  .search-inp:focus { border-color: var(--zone-a2); }
  .suggestions { position: absolute; top: 100%; left: 0; right: 0; background: var(--bg-panel); border: 1px solid var(--border); border-radius: var(--r-sm); z-index: 10; max-height: 200px; overflow-y: auto; }
  .sug-btn { width: 100%; display: flex; align-items: center; gap: 8px; padding: 7px 12px; border: none; background: none; color: var(--ink); font: inherit; font-size: var(--fs-12); cursor: pointer; text-align: left; }
  .sug-btn:hover { background: var(--bg-hover); }
  .sug-btn.sel { color: var(--zone-a2); }
  .sug-name { color: var(--ink-muted); flex: 1; }
  .sel-check { color: var(--zone-a2); }
  .chips { display: flex; gap: 6px; flex-wrap: wrap; }
  .chip { display: flex; align-items: center; gap: 5px; padding: 4px 10px; border-radius: 99px; background: rgba(79,209,197,.1); border: 1px solid rgba(79,209,197,.3); font-size: var(--fs-12); }
  .chip .num { font-family: var(--font-mono); font-weight: 700; color: var(--zone-a3); }
  .chip-del { background: none; border: none; color: var(--ink-faint); cursor: pointer; font-size: 11px; padding: 0 0 0 2px; }
  .charts-grid { display: grid; gap: 10px; }
  .chart-panel { background: var(--bg-panel-2); border: 1px solid var(--border); border-radius: var(--r-md); overflow: hidden; }
  .cp-header { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-bottom: 1px solid var(--border-soft); }
  .cp-sym { font-family: var(--font-mono); font-weight: 700; font-size: var(--fs-13); color: var(--zone-a3); text-decoration: none; }
  .cp-sym:hover { text-decoration: underline; }
  .cp-name { font-size: var(--fs-12); color: var(--ink-muted); }
  .cp-error { padding: 40px; text-align: center; color: var(--ink-faint); font-size: var(--fs-12); }
</style>
```

- [ ] **Add to sidebar** in `+layout.svelte`:
```typescript
{ href: '/compare', label: 'Compare', short: '⊞' },
```

- [ ] **svelte-check + commit + push**:
```bash
cd /Users/praveen/Projects/cot-dashboard/apps/web && npx svelte-check --threshold error 2>&1 | tail -3
git add apps/web/src/routes/compare/ apps/web/src/routes/+layout.svelte
git commit -m "feat: add /compare page — multi-chart side-by-side comparison"
git push
```
