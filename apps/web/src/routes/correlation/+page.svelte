<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '$lib/api/client';
	import type { CorrelationResponse } from '$lib/api/types';

	let resp = $state<CorrelationResponse | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let windowDays = $state(90);
	let hoveredCell = $state<{ i: number; j: number; v: number | null } | null>(null);

	async function load() {
		loading = true;
		error = null;
		try {
			resp = await api.correlation(windowDays);
		} catch (e) {
			error = (e as Error).message;
		} finally {
			loading = false;
		}
	}

	onMount(load);

	function corrColor(v: number | null): string {
		if (v == null) return 'var(--bg-canvas)';
		if (v >= 0.7) return `rgba(24,224,143,${0.3 + v * 0.5})`;
		if (v <= -0.7) return `rgba(255,90,95,${0.3 + Math.abs(v) * 0.5})`;
		if (Math.abs(v) < 0.3) return 'rgba(138,138,147,0.12)';
		return v > 0
			? `rgba(24,224,143,${Math.abs(v) * 0.4})`
			: `rgba(255,90,95,${Math.abs(v) * 0.4})`;
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
			<div class="subtitle">Rolling {windowDays}-day price correlation across all markets</div>
		</div>
		<div class="controls">
			{#each [30, 60, 90, 180] as w}
				<button
					class="w-btn"
					class:active={windowDays === w}
					onclick={() => {
						windowDays = w;
						load();
					}}>{w}d</button
				>
			{/each}
		</div>
	</header>

	{#if hoveredCell && resp}
		<div class="hover-info">
			<span class="num">{resp.symbols[hoveredCell.i]}</span> ×
			<span class="num">{resp.symbols[hoveredCell.j]}</span>:
			<strong style:color={hoveredCell.v != null && hoveredCell.v > 0 ? 'var(--long)' : 'var(--short)'}
				>{hoveredCell.v?.toFixed(3) ?? 'N/A'}</strong
			>
		</div>
	{/if}

	{#if loading}
		<div class="sk-matrix">
			{#each Array(8) as _}
				<div class="sk-row">
					{#each Array(10) as __}
						<div class="sk-cell"></div>
					{/each}
				</div>
			{/each}
		</div>
	{:else if error}
		<div class="error-state">
			<div class="error-title">Couldn't load correlation</div>
			<div class="error-body">{error}</div>
			<button class="retry-btn" onclick={load}>Retry</button>
		</div>
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
									onmouseenter={() => (hoveredCell = { i, j, v })}
									onmouseleave={() => (hoveredCell = null)}
									title={`${rowSym} × ${resp.symbols[j]}: ${v?.toFixed(3) ?? 'N/A'}`}
								>
									{#if i !== j && v != null}
										<span class="num cell-val">{v.toFixed(2)}</span>
									{:else if i === j}
										<span class="diag">1</span>
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
			<span class="leg-muted">as of {resp.as_of}</span>
		</div>
	{:else}
		<div class="empty">No correlation data available.</div>
	{/if}
</div>

<style>
	.page {
		padding: var(--sp-6);
		display: flex;
		flex-direction: column;
		gap: var(--sp-4);
		height: 100%;
		min-height: 0;
		overflow: auto;
		scrollbar-width: thin;
		scrollbar-color: var(--border) transparent;
	}
	.eyebrow {
		font-size: var(--fs-11);
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: var(--ink-faint);
	}
	.title {
		font-size: var(--fs-20);
		font-weight: 600;
		margin: 2px 0 0;
	}
	.subtitle {
		font-size: var(--fs-12);
		color: var(--ink-muted);
	}
	.header {
		display: flex;
		justify-content: space-between;
		align-items: flex-end;
	}
	.controls {
		display: flex;
		gap: 4px;
	}
	.w-btn {
		padding: 5px 10px;
		border-radius: var(--r-sm);
		border: 1px solid var(--border);
		background: var(--bg-panel);
		font-size: var(--fs-12);
		color: var(--ink-muted);
		cursor: pointer;
		font-family: var(--font-mono);
	}
	.w-btn.active {
		border-color: var(--attn-high);
		color: var(--attn-high);
	}
	.hover-info {
		padding: 8px 12px;
		background: var(--bg-panel);
		border: 1px solid var(--border);
		border-radius: var(--r-sm);
		font-size: var(--fs-12);
	}
	.matrix-wrap {
		overflow: auto;
		flex: 1;
	}
	.matrix {
		border-collapse: collapse;
	}
	.corner,
	.col-head,
	.row-head {
		padding: 3px 5px;
		font-size: 9px;
		font-family: var(--font-mono);
		font-weight: 700;
		color: var(--ink-muted);
		white-space: nowrap;
	}
	.col-head {
		text-align: center;
		writing-mode: vertical-lr;
		transform: rotate(180deg);
		height: 56px;
		vertical-align: bottom;
	}
	.row-head {
		text-align: right;
		position: sticky;
		left: 0;
		background: var(--bg-canvas);
		z-index: 1;
	}
	.cell {
		width: 14px;
		height: 14px;
		text-align: center;
		cursor: default;
		transition: filter 0.1s;
	}
	.cell:hover {
		filter: brightness(1.3);
	}
	.cell-val {
		font-size: 8px;
	}
	.diag {
		color: var(--ink-faint);
		font-size: 8px;
		font-family: var(--font-mono);
	}
	.legend {
		display: flex;
		gap: 16px;
		font-size: 11px;
		align-items: center;
		flex-wrap: wrap;
	}
	.leg-item {
		display: flex;
		align-items: center;
		gap: 4px;
	}
	.leg-muted {
		color: var(--ink-faint);
		margin-left: auto;
		font-family: var(--font-mono);
		font-size: 10px;
	}
	.sk-matrix {
		display: flex;
		flex-direction: column;
		gap: 3px;
	}
	.sk-row {
		display: flex;
		gap: 3px;
	}
	.sk-cell {
		width: 32px;
		height: 14px;
		background: var(--bg-hover);
		border-radius: 2px;
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
	.num {
		font-family: var(--font-mono);
	}
</style>
