<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '$api/client';
	import type { TodayRow } from '$api/types';
	import { ZONE_NAMES } from '$api/types';
	import AttentionCard from '$components/zone/AttentionCard.svelte';
	import EmptyState from '$components/primitives/EmptyState.svelte';
	import Skeleton from '$components/primitives/Skeleton.svelte';

	let rows = $state<TodayRow[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let weekOf = $state<string | null>(null);

	const summary = $derived.by(() => {
		const total = rows.length;
		const hot = rows.filter((r) => r.n_zones >= 3).length;
		const warm = rows.filter((r) => r.n_zones >= 1 && r.n_zones < 3).length;
		const cold = total - hot - warm;
		return { total, hot, warm, cold };
	});

	const zoneCounts = $derived.by(() => {
		const counts: Record<string, number> = { A1: 0, A2: 0, A3: 0, A4: 0, A5: 0 };
		for (const r of rows) for (const z of r.zones_on) counts[z]++;
		return counts;
	});

	async function load() {
		loading = true;
		error = null;
		try {
			rows = await api.today();
			weekOf = rows[0]?.date ?? null;
		} catch (e) {
			error = (e as Error).message;
		} finally {
			loading = false;
		}
	}

	onMount(load);
</script>

<svelte:head>
	<title>Today · COT_LENS</title>
</svelte:head>

<div class="page">
	<header class="header">
		<div class="title-block">
			<div class="eyebrow">attention</div>
			<h1 class="title">Today</h1>
			{#if weekOf}
				<div class="subtitle">CFTC release week of <span class="num">{weekOf}</span></div>
			{/if}
		</div>
		<div class="summary">
			<div class="summary-cell">
				<div class="cell-num num" data-tone="high">{summary.hot}</div>
				<div class="cell-label">3+ zones</div>
			</div>
			<div class="summary-cell">
				<div class="cell-num num" data-tone="mid">{summary.warm}</div>
				<div class="cell-label">1–2 zones</div>
			</div>
			<div class="summary-cell">
				<div class="cell-num num" data-tone="low">{summary.cold}</div>
				<div class="cell-label">quiet</div>
			</div>
			<div class="summary-cell">
				<div class="cell-num num">{summary.total}</div>
				<div class="cell-label">markets</div>
			</div>
		</div>
	</header>

	<section class="zone-legend">
		{#each Object.entries(ZONE_NAMES) as [key, name]}
			<div class="legend-cell">
				<span class="legend-dot" style:--c={`var(--zone-${key.toLowerCase()})`}></span>
				<span class="legend-key num">{key}</span>
				<span class="legend-name">{name}</span>
				<span class="legend-count num">{zoneCounts[key]}</span>
			</div>
		{/each}
	</section>

	{#if loading}
		<div class="skeleton-grid">
			{#each Array(8) as _, i}
				<div class="sk-row">
					<Skeleton width="36px" height="36px" radius="6px" />
					<div class="sk-body">
						<Skeleton width="220px" height="14px" />
						<Skeleton width="320px" height="11px" />
					</div>
					<Skeleton width="80px" height="20px" radius="999px" />
					<Skeleton width="160px" height="22px" radius="4px" />
				</div>
			{/each}
		</div>
	{:else if error}
		<EmptyState variant="error" title="Couldn't load today" body={error} retry={load} />
	{:else if rows.length === 0}
		<EmptyState variant="empty" title="No markets to show" body="The data bundle is empty. Try refreshing." />
	{:else}
		<div class="grid">
			{#each rows as row, i}
				<AttentionCard {row} rank={i + 1} />
			{/each}
		</div>
	{/if}
</div>

<style>
	.page {
		padding: var(--sp-8) var(--sp-12) var(--sp-12);
		max-width: 1480px;
		margin: 0 auto;
		display: flex;
		flex-direction: column;
		gap: var(--sp-6);
		overflow-y: auto;
		scrollbar-width: thin;
		scrollbar-color: var(--border) transparent;
	}

	.header {
		display: flex;
		justify-content: space-between;
		align-items: flex-end;
		gap: var(--sp-8);
		padding-bottom: var(--sp-4);
		border-bottom: 1px solid var(--border-soft);
	}
	.eyebrow {
		text-transform: uppercase;
		letter-spacing: 0.14em;
		font-size: var(--fs-11);
		color: var(--attn-high);
	}
	.title {
		font-size: var(--fs-40);
		line-height: 1;
		letter-spacing: -0.02em;
		margin: 4px 0 var(--sp-2);
		font-weight: 600;
	}
	.subtitle {
		color: var(--ink-muted);
		font-size: var(--fs-13);
	}

	.summary {
		display: grid;
		grid-template-columns: repeat(4, minmax(80px, auto));
		gap: var(--sp-6);
	}
	.summary-cell {
		text-align: right;
	}
	.cell-num {
		font-size: var(--fs-28);
		font-weight: 500;
	}
	.cell-num[data-tone='high'] {
		color: var(--attn-high);
	}
	.cell-num[data-tone='mid'] {
		color: var(--attn-mid);
	}
	.cell-num[data-tone='low'] {
		color: var(--ink-faint);
	}
	.cell-label {
		font-size: var(--fs-11);
		text-transform: uppercase;
		letter-spacing: 0.1em;
		color: var(--ink-muted);
		margin-top: 2px;
	}

	.zone-legend {
		display: grid;
		grid-template-columns: repeat(5, 1fr);
		gap: var(--sp-3);
		padding: var(--sp-3);
		background: var(--bg-panel-2);
		border: 1px solid var(--border-soft);
		border-radius: var(--r-md);
	}
	.legend-cell {
		display: grid;
		grid-template-columns: 8px 18px 1fr auto;
		gap: var(--sp-2);
		align-items: center;
		font-size: var(--fs-12);
	}
	.legend-dot {
		width: 8px;
		height: 8px;
		border-radius: 2px;
		background: var(--c);
	}
	.legend-key {
		color: var(--ink);
		font-size: var(--fs-11);
	}
	.legend-name {
		color: var(--ink-muted);
		font-size: var(--fs-12);
	}
	.legend-count {
		color: var(--ink-faint);
		font-size: var(--fs-12);
	}

	.grid {
		display: flex;
		flex-direction: column;
		gap: var(--sp-2);
	}

	.skeleton-grid {
		display: flex;
		flex-direction: column;
		gap: var(--sp-2);
	}
	.sk-row {
		display: grid;
		grid-template-columns: 36px 1fr auto 160px;
		gap: var(--sp-4);
		align-items: center;
		padding: var(--sp-3) var(--sp-4);
		background: var(--bg-panel);
		border: 1px solid var(--border-soft);
		border-radius: var(--r-md);
	}
	.sk-body {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}

	@media (max-width: 1100px) {
		.page {
			padding: var(--sp-6);
		}
		.header {
			flex-direction: column;
			align-items: flex-start;
			gap: var(--sp-4);
		}
		.summary {
			grid-template-columns: repeat(4, 1fr);
			width: 100%;
		}
		.summary-cell {
			text-align: left;
		}
	}
	@media (max-width: 700px) {
		.page {
			padding: var(--sp-4);
		}
		.title {
			font-size: var(--fs-28);
		}
		.summary {
			grid-template-columns: repeat(2, 1fr);
			gap: var(--sp-3);
		}
		.zone-legend {
			grid-template-columns: 1fr;
		}
		.sk-row {
			grid-template-columns: 28px 1fr 60px 100px;
		}
	}
</style>
