<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '$api/client';
	import type { DivergenceRow } from '$api/types';
	import EmptyState from '$components/primitives/EmptyState.svelte';
	import Skeleton from '$components/primitives/Skeleton.svelte';

	let rows = $state<DivergenceRow[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	const week = new Date().toISOString().slice(0, 10);

	async function load() {
		loading = true;
		error = null;
		try {
			rows = await api.divergence(week);
		} catch (e) {
			error = (e as Error).message;
		} finally {
			loading = false;
		}
	}

	onMount(load);

	const maxMag = $derived(rows.length ? Math.max(...rows.map((r) => r.magnitude), 1) : 1);
</script>

<svelte:head>
	<title>Divergence · COT_LENS</title>
</svelte:head>

<div class="page">
	<header class="header">
		<div>
			<div class="eyebrow">divergence</div>
			<h1 class="title">A2 scanner</h1>
			<div class="subtitle">
				price prints a 52-week extreme while commercials move the opposite direction
				· week of <span class="num">{week}</span>
			</div>
		</div>
	</header>

	{#if loading}
		<div class="sk-rows">
			{#each Array(4) as _}
				<div class="sk-row">
					<Skeleton width="48px" height="22px" />
					<div class="sk-body">
						<Skeleton width="180px" height="14px" />
						<Skeleton width="240px" height="11px" />
					</div>
					<Skeleton width="100%" height="22px" radius="4px" />
				</div>
			{/each}
		</div>
	{:else if error}
		<EmptyState variant="error" title="Couldn't run scan" body={error} retry={load} />
	{:else if rows.length === 0}
		<EmptyState
			variant="empty"
			title="No divergences this week"
			body="A2 is appropriately rare. Check back next Friday after the CFTC release."
		/>
	{:else}
		<div class="rows">
			{#each rows as r}
				<a href={`/market/${r.symbol}`} class="row" data-dir={r.direction}>
					<div class="rank num">{r.symbol}</div>
					<div class="meta">
						<div class="name-row">
							<span class="name">{r.name}</span>
							<span class="dir-pill">{r.direction}</span>
						</div>
						<div class="data num">
							close <strong>{r.close.toFixed(2)}</strong>
							· net comm <strong>{r.net_commercials.toLocaleString()}</strong>
						</div>
					</div>
					<div class="bar-wrap">
						<div class="bar" style:width={`${(r.magnitude / maxMag) * 100}%`}></div>
						<span class="bar-num num">{r.magnitude.toFixed(2)}</span>
					</div>
				</a>
			{/each}
		</div>
	{/if}
</div>

<style>
	.page {
		padding: var(--sp-8) var(--sp-12) var(--sp-12);
		max-width: 1200px;
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
		max-width: 64ch;
	}

	.sk-rows {
		display: flex;
		flex-direction: column;
		gap: var(--sp-2);
	}
	.sk-row {
		display: grid;
		grid-template-columns: 64px 1fr 260px;
		align-items: center;
		gap: var(--sp-4);
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

	@media (max-width: 800px) {
		.page {
			padding: var(--sp-4) var(--sp-6);
		}
		.title {
			font-size: var(--fs-28);
		}
		.row {
			grid-template-columns: 56px 1fr;
		}
		.bar-wrap {
			grid-column: 1 / -1;
		}
		.sk-row {
			grid-template-columns: 56px 1fr;
		}
	}

	.rows {
		display: flex;
		flex-direction: column;
		gap: var(--sp-2);
	}
	.row {
		display: grid;
		grid-template-columns: 64px 1fr 260px;
		align-items: center;
		gap: var(--sp-4);
		padding: var(--sp-3) var(--sp-4);
		background: var(--bg-panel);
		border: 1px solid var(--border-soft);
		border-radius: var(--r-md);
		color: var(--ink);
		transition: transform 0.18s, border-color 0.18s;
	}
	.row:hover {
		transform: translateY(-1px);
		border-color: var(--border);
	}
	.rank {
		font-size: var(--fs-16);
		font-weight: 600;
	}
	.name-row {
		display: flex;
		align-items: center;
		gap: var(--sp-3);
	}
	.name {
		font-size: var(--fs-14);
		color: var(--ink);
	}
	.dir-pill {
		font-size: 10px;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		padding: 2px 6px;
		border-radius: 999px;
		border: 1px solid;
	}
	.row[data-dir='bullish'] .dir-pill {
		color: var(--long);
		border-color: color-mix(in srgb, var(--long) 40%, transparent);
	}
	.row[data-dir='bearish'] .dir-pill {
		color: var(--short);
		border-color: color-mix(in srgb, var(--short) 40%, transparent);
	}
	.data {
		font-size: var(--fs-12);
		color: var(--ink-muted);
		margin-top: 2px;
	}
	.bar-wrap {
		position: relative;
		height: 22px;
		background: var(--bg-canvas);
		border-radius: 4px;
		overflow: hidden;
	}
	.bar {
		position: absolute;
		left: 0;
		top: 0;
		bottom: 0;
		background: linear-gradient(90deg, transparent, var(--attn-high));
		opacity: 0.6;
	}
	.bar-num {
		position: absolute;
		right: 8px;
		top: 50%;
		transform: translateY(-50%);
		font-size: var(--fs-12);
		color: var(--ink);
	}

</style>
