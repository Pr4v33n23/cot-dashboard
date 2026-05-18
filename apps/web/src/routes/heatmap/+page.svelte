<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '$api/client';
	import type { HeatmapResponse, ZoneKey } from '$api/types';
	import { ZONE_NAMES } from '$api/types';
	import EmptyState from '$components/primitives/EmptyState.svelte';
	import Skeleton from '$components/primitives/Skeleton.svelte';

	let resp = $state<HeatmapResponse | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);

	const grid = $derived.by(() => {
		if (!resp) return [];
		const bySym = new Map<string, {
			sector: string;
			market_type: string;
			regime_label: string | null;
			cells: Record<ZoneKey, { active: boolean; magnitude: number }>;
		}>();
		for (const c of resp.cells) {
			if (!bySym.has(c.symbol)) {
				bySym.set(c.symbol, {
					sector: c.sector,
					market_type: c.market_type ?? 'physical',
					regime_label: c.regime_label ?? null,
					cells: {} as Record<ZoneKey, { active: boolean; magnitude: number }>
				});
			}
			bySym.get(c.symbol)!.cells[c.zone] = { active: c.active, magnitude: c.magnitude };
		}
		// Sort: physicals first (by sector), then financials (by sector)
		return Array.from(bySym.entries())
			.map(([sym, v]) => ({
				symbol: sym,
				sector: v.sector,
				market_type: v.market_type,
				regime_label: v.regime_label,
				cells: v.cells,
				count: Object.values(v.cells).filter((c) => c.active).length
			}))
			.sort((a, b) => {
				// Physicals before financials
				if (a.market_type !== b.market_type)
					return a.market_type === 'physical' ? -1 : 1;
				if (a.sector !== b.sector) return a.sector.localeCompare(b.sector);
				return b.count - a.count;
			});
	});

	async function load() {
		loading = true;
		error = null;
		try {
			resp = await api.heatmap();
		} catch (e) {
			error = (e as Error).message;
		} finally {
			loading = false;
		}
	}

	onMount(load);

	const zones = ['A1', 'A2', 'A3', 'A4', 'A5'] as ZoneKey[];
</script>

<svelte:head>
	<title>Heatmap · COT_LENS</title>
</svelte:head>

<div class="page">
	<header class="header">
		<div>
			<div class="eyebrow">positioning</div>
			<h1 class="title">Heatmap</h1>
			{#if resp}
				<div class="subtitle">week of <span class="num">{resp.week_of}</span></div>
			{/if}
		</div>
	</header>

	{#if loading}
		<div class="sk-table">
			{#each Array(8) as _}
				<div class="sk-row">
					<Skeleton width="80px" height="14px" />
					{#each Array(5) as __}
						<Skeleton width="100%" height="28px" radius="4px" />
					{/each}
					<Skeleton width="20px" height="14px" />
				</div>
			{/each}
		</div>
	{:else if error}
		<EmptyState variant="error" title="Couldn't load heatmap" body={error} retry={load} />
	{:else if grid.length === 0}
		<EmptyState variant="empty" title="No data yet" body="Heatmap is empty." />
	{:else if grid.length}
		<div class="table-wrap">
			<table class="grid">
				<thead>
					<tr>
						<th class="sym-head">market</th>
						{#each zones as z}
							<th class="zone-head" style:--c={`var(--zone-${z.toLowerCase()})`}>
								<span class="zone-key num">{z}</span>
								<span class="zone-name">{ZONE_NAMES[z]}</span>
							</th>
						{/each}
						<th class="count-head">Σ</th>
					</tr>
				</thead>
				<tbody>
					{#each grid as row}
						<tr class:financial-row={row.market_type === 'financial'}>
							<td class="sym-cell">
								<a href={`/market/${row.symbol}`} class="sym-link num">{row.symbol}</a>
								<span class="sector-dot" style:background={`var(--sec-${row.sector})`}></span>
							</td>
							{#if row.market_type === 'financial'}
								<td class="zone-cell regime-span" colspan="5">
									{#if row.regime_label}
										<div class="regime-badge" data-regime={row.regime_label}>
											<span class="regime-dot"></span>
											<span class="regime-text">{row.regime_label}</span>
										</div>
									{:else}
										<span class="no-regime">—</span>
									{/if}
								</td>
								<td class="count-cell num" style:color="var(--ink-faint)">—</td>
							{:else}
								{#each zones as z}
									{@const cell = row.cells[z]}
									<td class="zone-cell">
										{#if cell?.active}
											<div
												class="filled"
												style:--c={`var(--zone-${z.toLowerCase()})`}
												style:--alpha={Math.max(0.35, Math.min(1, cell.magnitude))}
											>
												<span class="mag-text num">{cell.magnitude.toFixed(2)}</span>
											</div>
										{:else}
											<div class="empty-cell"></div>
										{/if}
									</td>
								{/each}
								<td class="count-cell num" data-tone={row.count >= 3 ? 'high' : row.count >= 1 ? 'mid' : 'low'}>
									{row.count}
								</td>
							{/if}
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
</div>

<style>
	.page {
		padding: var(--sp-8) var(--sp-12) var(--sp-12);
		max-width: 1280px;
		margin: 0 auto;
		display: flex;
		flex-direction: column;
		gap: var(--sp-6);
		overflow-y: auto;
		scrollbar-width: thin;
		scrollbar-color: var(--border) transparent;
	}
	.header {
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
		margin: 4px 0 var(--sp-2);
		font-weight: 600;
		letter-spacing: -0.02em;
	}
	.subtitle {
		color: var(--ink-muted);
		font-size: var(--fs-13);
	}

	.table-wrap {
		background: var(--bg-panel);
		border: 1px solid var(--border-soft);
		border-radius: var(--r-md);
		overflow-x: auto;
		overflow-y: visible;
	}
	.grid {
		width: 100%;
		border-collapse: collapse;
	}
	.grid th,
	.grid td {
		padding: 8px 12px;
		text-align: left;
		font-size: var(--fs-12);
	}
	.grid thead th {
		font-size: var(--fs-11);
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: var(--ink-muted);
		font-weight: 500;
		background: var(--bg-panel-2);
		border-bottom: 1px solid var(--border-soft);
	}
	.sym-head {
		width: 90px;
	}
	.zone-head {
		text-align: center;
		border-left: 1px solid var(--border-soft);
	}
	.zone-key {
		display: block;
		color: var(--c);
		font-weight: 600;
	}
	.zone-name {
		display: block;
		font-size: 9px;
		color: var(--ink-faint);
		text-transform: none;
		letter-spacing: 0;
	}
	.count-head {
		text-align: center;
		width: 40px;
	}

	.grid tbody tr {
		border-top: 1px solid var(--border-soft);
		transition: background 0.12s;
	}
	.grid tbody tr:hover {
		background: var(--bg-hover);
	}

	.sym-cell {
		display: flex;
		align-items: center;
		gap: 8px;
	}
	.sym-link {
		color: var(--ink);
		font-weight: 600;
	}
	.sym-link:hover {
		color: var(--attn-high);
	}
	.sector-dot {
		width: 6px;
		height: 6px;
		border-radius: 50%;
	}

	.zone-cell {
		border-left: 1px solid var(--border-soft);
		text-align: center;
		padding: 4px !important;
	}
	.filled {
		height: 28px;
		border-radius: 4px;
		background: color-mix(in srgb, var(--c) calc(var(--alpha) * 60%), transparent);
		border: 1px solid color-mix(in srgb, var(--c) calc(var(--alpha) * 80%), transparent);
		display: flex;
		align-items: center;
		justify-content: center;
	}
	.mag-text {
		font-size: 10px;
		color: var(--ink);
	}
	.empty-cell {
		height: 28px;
		border-radius: 4px;
		background: var(--bg-canvas);
	}

	.count-cell {
		text-align: center;
		font-weight: 600;
	}
	.count-cell[data-tone='high'] {
		color: var(--attn-high);
	}
	.count-cell[data-tone='mid'] {
		color: var(--attn-mid);
	}
	.count-cell[data-tone='low'] {
		color: var(--ink-faint);
	}

	/* Financial instrument rows */
	.financial-row {
		opacity: 0.92;
	}
	.regime-span {
		text-align: left;
		padding: 4px 12px;
	}
	.regime-badge {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		padding: 3px 10px;
		border-radius: 99px;
		font-size: var(--fs-11);
		font-family: var(--font-mono);
		border: 1px solid;
	}
	.regime-badge[data-regime='trending']      { background: rgba(79,209,197,.12); color: var(--zone-a3); border-color: rgba(79,209,197,.3); }
	.regime-badge[data-regime='accumulation']  { background: rgba(24,224,143,.10); color: var(--long);    border-color: rgba(24,224,143,.3); }
	.regime-badge[data-regime='distribution']  { background: rgba(255,90,95,.10);  color: var(--short);   border-color: rgba(255,90,95,.3); }
	.regime-badge[data-regime='ranging']       { background: rgba(138,138,147,.1); color: var(--ink-muted); border-color: var(--border); }
	.regime-dot {
		width: 5px; height: 5px; border-radius: 50%;
		background: currentColor;
	}
	.regime-text { text-transform: capitalize; }
	.no-regime { color: var(--ink-faint); font-size: var(--fs-11); }

	.sk-table {
		display: flex;
		flex-direction: column;
		gap: 2px;
		padding: var(--sp-3);
		background: var(--bg-panel);
		border: 1px solid var(--border-soft);
		border-radius: var(--r-md);
	}
	.sk-row {
		display: grid;
		grid-template-columns: 100px repeat(5, 1fr) 40px;
		gap: var(--sp-3);
		align-items: center;
		padding: 6px var(--sp-3);
	}

	@media (max-width: 900px) {
		.page {
			padding: var(--sp-4) var(--sp-6);
		}
		.title {
			font-size: var(--fs-28);
		}
		.table-wrap {
			overflow-x: auto;
		}
		.grid {
			min-width: 640px;
		}
		.zone-name {
			display: none;
		}
	}
</style>
