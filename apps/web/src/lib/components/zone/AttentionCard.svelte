<script lang="ts">
	import type { TodayRow, ZoneKey } from '$api/types';
	import { ZONE_NAMES, ZONE_BLURB } from '$api/types';
	import ZoneBadge from './ZoneBadge.svelte';

	interface Props {
		row: TodayRow;
		rank: number;
	}

	let { row, rank }: Props = $props();

	const heatLevel = $derived(row.n_zones >= 3 ? 'high' : row.n_zones >= 1 ? 'mid' : 'low');
	const heatColor = $derived(
		row.n_zones >= 3 ? 'var(--attn-high)' : row.n_zones >= 1 ? 'var(--attn-mid)' : 'var(--attn-low)'
	);

	const reason = $derived.by(() => {
		if (row.zones_on.length === 0) return 'No active zones.';
		// Build a deterministic one-line explanation — no LLM.
		const parts: string[] = [];
		const cot = row.cot_index_comm;
		if (row.zones_on.includes('A1') && cot != null) {
			if (cot >= 90) parts.push(`commercials max-long (COT idx ${cot.toFixed(0)})`);
			else if (cot <= 10) parts.push(`commercials max-short (COT idx ${cot.toFixed(0)})`);
		}
		if (row.zones_on.includes('A2')) parts.push('price-vs-positioning divergence');
		if (row.zones_on.includes('A3')) parts.push('sector outlier');
		if (row.zones_on.includes('A4')) parts.push('fast COT-index repositioning');
		if (row.zones_on.includes('A5')) parts.push('hedger/spec at opposing extremes');
		return parts.length ? parts.join(' · ') : 'attention triggered';
	});
</script>

<a
	href={`/market/${row.symbol}`}
	class="card"
	data-heat={heatLevel}
	style:--heat={heatColor}
	style:--sec-color={`var(--sec-${row.sector})`}
	data-sveltekit-preload-data="hover"
>
	<div class="rank num">#{rank}</div>
	<div class="head">
		<div class="sym-row">
			<span class="sym num">{row.symbol}</span>
			<span class="name">{row.name}</span>
			<span class="sector-pill" style:--sec={`var(--sec-${row.sector})`}>
				{row.sector}
			</span>
		</div>
		<div class="reason">{reason}</div>
	</div>
	<div class="zones">
		{#each row.zones_on as z}
			<ZoneBadge zone={z as ZoneKey} magnitude={row.magnitudes[z as ZoneKey]} />
		{/each}
		{#if row.zones_on.length === 0}
			<span class="zones-empty">—</span>
		{/if}
	</div>
	<div class="mag">
		<div class="mag-bar" style:width={`${Math.min(100, (row.total_mag / 5) * 100)}%`}></div>
		<div class="mag-num num">{row.total_mag.toFixed(2)}</div>
	</div>
</a>

<style>
	.card {
		display: grid;
		grid-template-columns: 36px 1fr auto 160px;
		gap: var(--sp-4);
		align-items: center;
		padding: var(--sp-3) var(--sp-4);
		background: var(--bg-panel);
		border: 1px solid var(--border-soft);
		border-radius: var(--r-md);
		color: var(--ink);
		position: relative;
		overflow: hidden;
		transition: transform 0.18s ease, border-color 0.18s ease, background 0.18s ease;
	}
	.card::before {
		content: '';
		position: absolute;
		left: 0;
		top: 0;
		bottom: 0;
		width: 3px;
		background: var(--heat);
		opacity: 0.7;
	}
	.card:hover {
		transform: translateY(-1px);
		border-color: var(--border);
		background: color-mix(in srgb, var(--bg-panel) 90%, var(--heat) 10%);
	}

	.rank {
		color: var(--ink-faint);
		font-size: var(--fs-12);
		text-align: right;
	}

	.head {
		min-width: 0;
	}
	.sym-row {
		display: flex;
		align-items: baseline;
		gap: var(--sp-2);
	}
	.sym {
		font-weight: 600;
		font-size: var(--fs-16);
		color: var(--ink);
	}
	.name {
		color: var(--ink-muted);
		font-size: var(--fs-13);
	}
	.sector-pill {
		font-size: var(--fs-11);
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: var(--sec);
		padding: 1px 6px;
		border: 1px solid color-mix(in srgb, var(--sec) 50%, transparent);
		border-radius: 999px;
	}
	.reason {
		margin-top: 4px;
		font-size: var(--fs-12);
		color: var(--ink-muted);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.zones {
		display: flex;
		gap: 6px;
		align-items: center;
	}
	.zones-empty {
		color: var(--ink-faint);
		font-family: var(--font-mono);
		font-size: var(--fs-12);
	}

	.mag {
		position: relative;
		height: 24px;
		background: var(--bg-canvas);
		border-radius: 4px;
		overflow: hidden;
	}
	.mag-bar {
		position: absolute;
		left: 0;
		top: 0;
		bottom: 0;
		background: linear-gradient(90deg, transparent, var(--heat));
		opacity: 0.6;
	}
	.mag-num {
		position: absolute;
		right: 8px;
		top: 50%;
		transform: translateY(-50%);
		color: var(--ink);
		font-size: var(--fs-12);
	}

	@media (max-width: 900px) {
		.card {
			grid-template-columns: 28px 1fr 100px;
		}
		.mag {
			display: none;
		}
	}
	@media (max-width: 640px) {
		.card {
			grid-template-columns: 1fr;
			gap: var(--sp-2);
			padding: var(--sp-3);
		}
		.rank {
			text-align: left;
		}
		.zones {
			justify-self: start;
		}
		.reason {
			white-space: normal;
		}
	}
</style>
