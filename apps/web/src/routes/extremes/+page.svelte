<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '$lib/api/client';
	import type { ExtremesRow } from '$lib/api/types';

	let rows = $state<ExtremesRow[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let filter = $state<'all' | 'long' | 'short'>('all');

	const filtered = $derived(filter === 'all' ? rows : rows.filter((r) => r.direction === filter));

	async function load() {
		loading = true;
		error = null;
		try {
			rows = await api.extremes();
		} catch (e) {
			error = (e as Error).message;
		} finally {
			loading = false;
		}
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
			{#each (['all', 'long', 'short'] as const) as f}
				<button class="filter-btn" class:active={filter === f} onclick={() => (filter = f)}
					>{f}</button
				>
			{/each}
		</div>
	</header>

	{#if loading}
		<div class="sk-list">
			{#each Array(10) as _}
				<div class="sk-row">
					{#each Array(7) as __}
						<div class="sk-cell"></div>
					{/each}
				</div>
			{/each}
		</div>
	{:else if error}
		<div class="error-state">
			<div class="error-title">Couldn't load extremes</div>
			<div class="error-body">{error}</div>
			<button class="retry-btn" onclick={load}>Retry</button>
		</div>
	{:else if filtered.length === 0}
		<div class="empty">No markets match this filter.</div>
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
						<tr
							onclick={() => (window.location.href = `/market/${r.symbol}`)}
							style:cursor="pointer"
						>
							<td class="sym-cell">
								<span class="sym num">{r.symbol}</span>
								<span class="name">{r.name}</span>
							</td>
							<td>
								<span
									class="sector-dot"
									style:background={`var(--sec-${r.sector})`}
								></span>{r.sector}
							</td>
							<td
								class="num"
								style:color={r.cot_index != null && r.cot_index >= 70
									? 'var(--long)'
									: r.cot_index != null && r.cot_index <= 30
										? 'var(--short)'
										: 'var(--ink)'}>{r.cot_index?.toFixed(1) ?? '—'}</td
							>
							<td class="num" style:color={dirColor(r.direction)}>{r.direction}</td>
							<td>
								<div class="extreme-bar">
									<div
										class="extreme-fill"
										style:width={`${r.extremeness * 100}%`}
										style:background={extremeColor(r.extremeness)}
									></div>
								</div>
								<span
									class="num"
									style:color={extremeColor(r.extremeness)}
									style:font-size="10px">{(r.extremeness * 100).toFixed(0)}%</span
								>
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
	.page {
		padding: var(--sp-8) var(--sp-6) var(--sp-12);
		max-width: 1200px;
		margin: 0 auto;
		display: flex;
		flex-direction: column;
		gap: var(--sp-6);
		overflow-y: auto;
		scrollbar-width: thin;
	}
	.eyebrow {
		font-size: var(--fs-11);
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: var(--ink-faint);
	}
	.title {
		font-size: var(--fs-28);
		font-weight: 600;
		margin: 4px 0 2px;
	}
	.subtitle {
		font-size: var(--fs-13);
		color: var(--ink-muted);
	}
	.header {
		display: flex;
		justify-content: space-between;
		align-items: flex-end;
	}
	.filters {
		display: flex;
		gap: 4px;
	}
	.filter-btn {
		padding: 5px 12px;
		border-radius: var(--r-sm);
		border: 1px solid var(--border);
		background: var(--bg-panel);
		font-size: var(--fs-12);
		color: var(--ink-muted);
		cursor: pointer;
		text-transform: capitalize;
	}
	.filter-btn.active {
		border-color: var(--attn-high);
		color: var(--attn-high);
		background: rgba(183, 148, 246, 0.08);
	}
	.table-wrap {
		background: var(--bg-panel);
		border: 1px solid var(--border);
		border-radius: var(--r-md);
		overflow-x: auto;
	}
	table {
		width: 100%;
		border-collapse: collapse;
	}
	th {
		padding: 8px 12px;
		text-align: left;
		font-size: 10px;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--ink-faint);
		border-bottom: 1px solid var(--border-soft);
		white-space: nowrap;
	}
	td {
		padding: 8px 12px;
		font-size: var(--fs-12);
		border-bottom: 1px solid var(--border-soft);
	}
	tr:last-child td {
		border-bottom: none;
	}
	tr:hover td {
		background: var(--bg-hover);
	}
	.sym-cell {
		display: flex;
		flex-direction: column;
		gap: 1px;
	}
	.sym {
		font-weight: 700;
		font-size: var(--fs-13);
	}
	.name {
		font-size: 10px;
		color: var(--ink-faint);
	}
	.sector-dot {
		display: inline-block;
		width: 6px;
		height: 6px;
		border-radius: 50%;
		margin-right: 5px;
		vertical-align: middle;
	}
	.num {
		font-family: var(--font-mono);
	}
	.muted {
		color: var(--ink-muted);
	}
	.extreme-bar {
		width: 80px;
		height: 5px;
		background: var(--border);
		border-radius: 3px;
		overflow: hidden;
		display: inline-block;
		vertical-align: middle;
		margin-right: 5px;
	}
	.extreme-fill {
		height: 100%;
		border-radius: 3px;
	}
	.sk-list {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}
	.sk-row {
		display: flex;
		gap: 16px;
		padding: 8px 0;
		border-bottom: 1px solid var(--border-soft);
	}
	.sk-cell {
		height: 14px;
		width: 80px;
		background: var(--bg-hover);
		border-radius: 3px;
		animation: pulse 1.6s ease-in-out infinite;
	}
	@keyframes pulse {
		0%,
		100% {
			opacity: 1;
		}
		50% {
			opacity: 0.4;
		}
	}
	.error-state {
		padding: var(--sp-8);
		text-align: center;
		display: flex;
		flex-direction: column;
		gap: var(--sp-3);
		align-items: center;
	}
	.error-title {
		font-size: var(--fs-14);
		font-weight: 600;
		color: var(--short);
	}
	.error-body {
		font-size: var(--fs-12);
		color: var(--ink-muted);
	}
	.retry-btn {
		padding: 6px 16px;
		border-radius: var(--r-sm);
		border: 1px solid var(--border);
		background: var(--bg-panel);
		font-size: var(--fs-12);
		color: var(--ink);
		cursor: pointer;
	}
	.empty {
		padding: var(--sp-8);
		text-align: center;
		color: var(--ink-faint);
		font-size: var(--fs-13);
	}
</style>
