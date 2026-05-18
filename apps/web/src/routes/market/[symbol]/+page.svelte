<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { api } from '$api/client';
	import type { MarketDetail, NewsItem, ZoneKey } from '$api/types';
	import { ZONE_NAMES } from '$api/types';
	import Chart from '$components/chart/Chart.svelte';
	import NewsRail from '$components/news/NewsRail.svelte';
	import ZoneBadge from '$components/zone/ZoneBadge.svelte';
	import ZoneTimeline from '$components/zone/ZoneTimeline.svelte';
	import EmptyState from '$components/primitives/EmptyState.svelte';
	import Skeleton from '$components/primitives/Skeleton.svelte';

	let symbol = $derived(page.params.symbol!);
	let detail = $state<MarketDetail | null>(null);
	let news = $state<NewsItem[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let range = $state<'1y' | '3y' | '5y' | 'max'>('3y');

	function fromDateForRange(r: '1y' | '3y' | '5y' | 'max'): string | undefined {
		if (r === 'max') return undefined;
		const yrs = { '1y': 1, '3y': 3, '5y': 5 }[r];
		const d = new Date();
		d.setFullYear(d.getFullYear() - yrs);
		return d.toISOString().slice(0, 10);
	}

	async function load() {
		loading = true;
		error = null;
		try {
			const from = fromDateForRange(range);
			const [m, n] = await Promise.all([
				api.market(symbol, from ? { from } : undefined),
				api.newsForSymbol(symbol, { from: from ?? '2024-01-01', limit: 300 })
			]);
			detail = m;
			news = n.items;
		} catch (e) {
			error = (e as Error).message;
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		void symbol;
		void range;
		load();
	});

	const lastBar = $derived(detail?.bars?.at(-1));
	const activeZones = $derived.by(() => {
		if (!lastBar) return [] as ZoneKey[];
		return (['A1', 'A2', 'A3', 'A4', 'A5'] as const).filter((z) => lastBar[z]);
	});
</script>

<svelte:head>
	<title>{symbol} · COT_LENS</title>
</svelte:head>

<div class="page">
	{#if loading && !detail}
		<div class="sk-page">
			<div class="sk-header">
				<div class="sk-titleblock">
					<Skeleton width="80px" height="11px" />
					<Skeleton width="320px" height="32px" />
					<Skeleton width="280px" height="11px" />
				</div>
				<div class="sk-stats">
					{#each Array(3) as _}
						<div class="sk-stat">
							<Skeleton width="70px" height="11px" />
							<Skeleton width="90px" height="20px" />
						</div>
					{/each}
				</div>
			</div>
			<Skeleton width="100%" height="560px" radius="var(--r-md)" />
			<Skeleton width="100%" height="90px" radius="var(--r-md)" />
		</div>
	{:else if error}
		<EmptyState variant="error" title={`Couldn't load ${symbol}`} body={error} retry={load} />
	{:else if detail}
		<header class="header">
			<div class="title-block">
				<div class="eyebrow">{detail.contract.sector}</div>
				<h1 class="title">
					<span class="num">{detail.contract.symbol}</span>
					<span class="name">{detail.contract.name}</span>
				</h1>
				<div class="meta num">
					CFTC {detail.contract.cftc_code} · ${detail.contract.point_value.toLocaleString()}/pt ·
					tick {detail.contract.tick_size}
				</div>
			</div>

			<div class="stats">
				{#if lastBar}
					<div class="stat">
						<div class="stat-label">last close</div>
						<div class="stat-val num">{lastBar.close?.toFixed(2) ?? '—'}</div>
					</div>
					<div class="stat">
						<div class="stat-label">COT index</div>
						<div class="stat-val num">{lastBar.cot_index_comm?.toFixed(1) ?? '—'}</div>
					</div>
					<div class="stat">
						<div class="stat-label">zones today</div>
						<div class="stat-val num">{lastBar.n_zones}</div>
					</div>
				{/if}
				<div class="range">
					{#each ['1y', '3y', '5y', 'max'] as const as r}
						<button
							class:active={range === r}
							onclick={() => (range = r)}>{r}</button
						>
					{/each}
				</div>
			</div>
		</header>

		{#if activeZones.length}
			<section class="zones-bar">
				<span class="zb-label">active</span>
				{#each activeZones as z}
					<ZoneBadge zone={z} magnitude={0.8} />
					<span class="zb-text">{ZONE_NAMES[z]}</span>
				{/each}
				<a href={`/intelligence?sym=${symbol}`} class="ai-link num">✦ AI Analysis</a>
			</section>
		{/if}

		<div class="layout">
			<div class="chart-col">
				<Chart bars={detail.bars} {news} height={560} />
				<ZoneTimeline bars={detail.bars} />
			</div>
			<div class="news-col">
				<NewsRail items={news} title="News · {symbol}" />
			</div>
		</div>
	{/if}
</div>

<style>
	.page {
		display: flex;
		flex-direction: column;
		gap: var(--sp-4);
		padding: var(--sp-6) var(--sp-8);
		height: 100%;
		min-height: 0;
		overflow: hidden; /* Market route pins to viewport; inner panels scroll */
	}
	.header {
		display: flex;
		justify-content: space-between;
		align-items: flex-end;
		gap: var(--sp-8);
		padding-bottom: var(--sp-3);
		border-bottom: 1px solid var(--border-soft);
	}
	.eyebrow {
		text-transform: uppercase;
		letter-spacing: 0.14em;
		font-size: var(--fs-11);
		color: var(--ink-muted);
	}
	.title {
		font-size: var(--fs-28);
		margin: 2px 0 4px;
		font-weight: 600;
		letter-spacing: -0.01em;
		display: flex;
		gap: var(--sp-3);
		align-items: baseline;
	}
	.title .name {
		color: var(--ink-muted);
		font-weight: 400;
		font-size: var(--fs-20);
	}
	.meta {
		font-size: var(--fs-11);
		color: var(--ink-faint);
		letter-spacing: 0.04em;
	}

	.stats {
		display: flex;
		gap: var(--sp-6);
		align-items: flex-end;
	}
	.stat {
		text-align: right;
	}
	.stat-label {
		font-size: var(--fs-11);
		color: var(--ink-muted);
		text-transform: uppercase;
		letter-spacing: 0.08em;
	}
	.stat-val {
		font-size: var(--fs-20);
		color: var(--ink);
	}
	.range {
		display: flex;
		gap: 2px;
		background: var(--bg-panel);
		border: 1px solid var(--border-soft);
		border-radius: var(--r-sm);
		padding: 2px;
	}
	.range button {
		padding: 4px 10px;
		font-size: var(--fs-11);
		color: var(--ink-muted);
		border-radius: 4px;
		font-family: var(--font-mono);
	}
	.range button:hover {
		color: var(--ink);
	}
	.range button.active {
		background: var(--bg-active);
		color: var(--ink);
	}

	.zones-bar {
		display: flex;
		align-items: center;
		gap: var(--sp-3);
		flex-wrap: wrap;
	}
	.ai-link {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		padding: 3px 10px;
		border-radius: var(--r-sm);
		font-size: var(--fs-11);
		color: var(--zone-a2);
		background: rgba(183,148,246,.08);
		border: 1px solid rgba(183,148,246,.2);
		transition: background .12s;
	}
	.ai-link:hover {
		background: rgba(183,148,246,.16);
	}
	.zb-label {
		font-size: var(--fs-11);
		color: var(--ink-faint);
		text-transform: uppercase;
		letter-spacing: 0.08em;
	}
	.zb-text {
		font-size: var(--fs-12);
		color: var(--ink-muted);
		margin-right: var(--sp-4);
	}

	.layout {
		display: grid;
		grid-template-columns: 1fr 340px;
		grid-template-rows: minmax(0, 1fr);
		gap: var(--sp-4);
		flex: 1;
		min-height: 0;
	}
	.chart-col {
		display: flex;
		flex-direction: column;
		gap: var(--sp-3);
		min-width: 0;
		min-height: 0;
	}
	.news-col {
		min-height: 0;
		min-width: 0;
		display: flex;
		overflow: hidden;
	}
	.news-col :global(.rail) {
		flex: 1;
		min-height: 0;
		max-height: 100%;
	}

	.sk-page {
		display: flex;
		flex-direction: column;
		gap: var(--sp-3);
	}
	.sk-header {
		display: flex;
		justify-content: space-between;
		align-items: flex-end;
		gap: var(--sp-8);
		padding-bottom: var(--sp-3);
		border-bottom: 1px solid var(--border-soft);
	}
	.sk-titleblock {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}
	.sk-stats {
		display: flex;
		gap: var(--sp-6);
	}
	.sk-stat {
		display: flex;
		flex-direction: column;
		gap: 4px;
		align-items: flex-end;
	}

	@media (max-width: 1100px) {
		.page {
			padding: var(--sp-4) var(--sp-6);
			overflow-y: auto; /* allow page scroll when chart + news stack */
			scrollbar-width: thin;
			scrollbar-color: var(--border) transparent;
		}
		.layout {
			grid-template-columns: 1fr;
			grid-template-rows: auto auto;
		}
		.news-col {
			max-height: 380px;
		}
	}
	@media (max-width: 760px) {
		.header {
			flex-direction: column;
			align-items: flex-start;
			gap: var(--sp-3);
		}
		.title {
			font-size: var(--fs-20);
		}
		.title .name {
			font-size: var(--fs-14);
		}
		.stats {
			width: 100%;
			justify-content: space-between;
			flex-wrap: wrap;
		}
		.sk-header {
			flex-direction: column;
			align-items: flex-start;
		}
	}
</style>
