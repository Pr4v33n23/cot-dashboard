<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '$lib/api/client';
	import type { AlertRule, AlertTrigger } from '$lib/api/types';

	let rules = $state<AlertRule[]>([]);
	let triggered = $state<AlertTrigger[]>([]);
	let loading = $state(true);
	let checking = $state(false);

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
		{ value: 'comm_spec_divergence', label: 'Divergence Weeks' }
	];

	async function load() {
		loading = true;
		try {
			rules = await api.alerts.list();
		} catch {
			rules = [];
		} finally {
			loading = false;
		}
	}

	async function create() {
		creating = true;
		try {
			await api.alerts.create({ symbol: sym, field, condition, threshold, label });
			await load();
			label = '';
		} finally {
			creating = false;
		}
	}

	async function remove(id: string) {
		await api.alerts.delete(id);
		rules = rules.filter((r) => r.id !== id);
	}

	async function checkNow() {
		checking = true;
		try {
			triggered = await api.alerts.check();
		} finally {
			checking = false;
		}
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
					<span class="num" style:color="var(--zone-a1)"
						>{t.current_value} (threshold: {t.threshold})</span
					>
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
			<input
				bind:value={threshold}
				type="number"
				step="0.1"
				class="inp num"
				style:width="80px"
			/>
			<input bind:value={label} placeholder="Label (optional)" class="inp" />
			<button class="create-btn" onclick={create} disabled={creating || !sym}
				>{creating ? '…' : '+ Add'}</button
			>
		</div>
	</section>

	{#if loading}
		<div class="empty-state">Loading…</div>
	{:else if rules.length === 0}
		<div class="empty-state">No alerts yet. Create your first alert above.</div>
	{:else}
		<div class="rules-list">
			<div class="section-label">{rules.length} active alert{rules.length > 1 ? 's' : ''}</div>
			{#each rules as rule}
				<div class="rule-row">
					<div class="rule-main">
						<span class="sym num">{rule.symbol}</span>
						<span class="rule-desc"
							>{rule.label || `${rule.field} ${rule.condition} ${rule.threshold}`}</span
						>
						{#if rule.last_triggered}
							<span class="last-trig">last triggered {rule.last_triggered?.slice(0, 10)}</span>
						{/if}
					</div>
					<button class="del-btn" onclick={() => rule.id && remove(rule.id)}>✕</button>
				</div>
			{/each}
		</div>
	{/if}
</div>

<style>
	.page {
		padding: var(--sp-8) var(--sp-6) var(--sp-12);
		max-width: 900px;
		margin: 0 auto;
		display: flex;
		flex-direction: column;
		gap: var(--sp-5);
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
	.check-btn {
		padding: 8px 16px;
		border-radius: var(--r-sm);
		background: var(--bg-panel);
		border: 1px solid var(--border);
		font-size: var(--fs-12);
		color: var(--ink-muted);
		cursor: pointer;
	}
	.check-btn:hover:not(:disabled) {
		border-color: var(--attn-high);
		color: var(--attn-high);
	}
	.triggered-banner {
		background: rgba(245, 166, 35, 0.08);
		border: 1px solid rgba(245, 166, 35, 0.3);
		border-radius: var(--r-md);
		padding: var(--sp-4);
		display: flex;
		flex-direction: column;
		gap: 6px;
	}
	.tb-title {
		font-weight: 600;
		color: #f5a623;
	}
	.tb-row {
		display: flex;
		gap: 12px;
		font-size: var(--fs-12);
	}
	.create-section {
		background: var(--bg-panel);
		border: 1px solid var(--border);
		border-radius: var(--r-md);
		padding: var(--sp-4);
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	.section-label {
		font-size: 10px;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--ink-faint);
	}
	.form-row {
		display: flex;
		gap: 8px;
		flex-wrap: wrap;
		align-items: center;
	}
	.inp {
		background: var(--bg-canvas);
		border: 1px solid var(--border);
		border-radius: var(--r-sm);
		color: var(--ink);
		font: inherit;
		font-size: var(--fs-12);
		padding: 6px 10px;
		outline: none;
		flex: 1;
		min-width: 80px;
	}
	.inp:focus {
		border-color: var(--attn-high);
	}
	.create-btn {
		padding: 7px 14px;
		border-radius: var(--r-sm);
		background: var(--attn-high);
		color: #0a0a0b;
		border: none;
		font-size: var(--fs-12);
		font-weight: 700;
		cursor: pointer;
		flex-shrink: 0;
	}
	.create-btn:disabled {
		opacity: 0.4;
	}
	.rules-list {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}
	.rule-row {
		display: flex;
		align-items: center;
		gap: 12px;
		padding: 10px 14px;
		background: var(--bg-panel);
		border: 1px solid var(--border);
		border-radius: var(--r-sm);
	}
	.rule-main {
		flex: 1;
		display: flex;
		align-items: center;
		gap: 10px;
		flex-wrap: wrap;
	}
	.sym {
		font-weight: 700;
		font-size: var(--fs-13);
		color: var(--attn-high);
	}
	.rule-desc {
		font-size: var(--fs-12);
		color: var(--ink-muted);
	}
	.last-trig {
		font-size: 10px;
		color: var(--ink-faint);
		font-family: var(--font-mono);
	}
	.del-btn {
		background: none;
		border: none;
		color: var(--ink-faint);
		cursor: pointer;
		font-size: 14px;
		padding: 4px;
	}
	.del-btn:hover {
		color: var(--short);
	}
	.num {
		font-family: var(--font-mono);
	}
	.empty-state {
		color: var(--ink-faint);
		font-size: var(--fs-13);
		padding: var(--sp-6);
		text-align: center;
	}
</style>
