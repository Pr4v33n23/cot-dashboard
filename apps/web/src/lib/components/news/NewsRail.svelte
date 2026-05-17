<script lang="ts">
	import type { NewsItem } from '$api/types';
	import { newsReader } from '$state/newsReader.svelte';

	interface Props {
		items: NewsItem[];
		title?: string;
	}

	let { items, title = 'News' }: Props = $props();

	function openItem(it: NewsItem, ev: MouseEvent) {
		// Cmd/Ctrl-click or middle click escapes to a new tab (original page).
		if (!it.url) return;
		if (ev.metaKey || ev.ctrlKey || ev.button === 1) {
			window.open(it.url, '_blank', 'noopener');
			return;
		}
		ev.preventDefault();
		newsReader.openItem(it);
	}

	const categories = ['all', 'market', 'agency', 'macro', 'geopolitics'] as const;
	let activeCat = $state<(typeof categories)[number]>('all');

	const filtered = $derived(
		activeCat === 'all' ? items : items.filter((i) => i.source_category === activeCat)
	);

	const groups = $derived.by(() => {
		const map = new Map<string, NewsItem[]>();
		for (const i of filtered) {
			const day = i.date.slice(0, 10);
			(map.get(day) ?? map.set(day, []).get(day)!).push(i);
		}
		return Array.from(map.entries()).sort(([a], [b]) => (a < b ? 1 : -1));
	});

	function srcColor(cat: string) {
		switch (cat) {
			case 'agency':
				return 'var(--zone-a3)';
			case 'macro':
				return 'var(--zone-a4)';
			case 'geopolitics':
				return 'var(--zone-a2)';
			default:
				return 'var(--zone-a1)';
		}
	}
</script>

<aside class="rail">
	<header class="head">
		<div class="title">{title}</div>
		<div class="count num">{items.length}</div>
	</header>

	<div class="cats">
		{#each categories as c}
			<button
				class="cat"
				class:active={activeCat === c}
				onclick={() => (activeCat = c)}
			>{c}</button>
		{/each}
	</div>

	<div class="scroll">
		{#each groups as [day, group]}
			<div class="group">
				<div class="day num">{day}</div>
				{#each group as it}
					<a
						class="item"
						href={it.url ?? '#'}
						onclick={(ev) => openItem(it, ev)}
						title="Open in app · ⌘-click for new tab"
						style:--c={srcColor(it.source_category)}
					>
						<div class="row">
							<span class="src">{it.source}</span>
							{#if it.publisher}
								<span class="pub">· {it.publisher}</span>
							{/if}
							{#if it.markets.length > 1}
								<span class="tags num">{it.markets.slice(0, 4).join(' ')}</span>
							{/if}
						</div>
						<div class="title-line">{it.title}</div>
					</a>
				{/each}
			</div>
		{/each}
		{#if filtered.length === 0}
			<div class="empty">no news in this window</div>
		{/if}
	</div>
</aside>

<style>
	.rail {
		display: flex;
		flex-direction: column;
		background: var(--bg-panel);
		border: 1px solid var(--border-soft);
		border-radius: var(--r-md);
		overflow: hidden;
		min-height: 0;
	}
	.head {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: var(--sp-3) var(--sp-4);
		border-bottom: 1px solid var(--border-soft);
	}
	.title {
		font-size: var(--fs-13);
		font-weight: 600;
		color: var(--ink);
	}
	.count {
		color: var(--ink-muted);
		font-size: var(--fs-11);
	}
	.cats {
		display: flex;
		gap: 2px;
		padding: var(--sp-2);
		border-bottom: 1px solid var(--border-soft);
	}
	.cat {
		padding: 4px var(--sp-2);
		font-size: var(--fs-11);
		color: var(--ink-muted);
		border-radius: 4px;
		text-transform: lowercase;
		letter-spacing: 0.04em;
		transition: color 0.12s, background 0.12s;
	}
	.cat:hover {
		color: var(--ink);
		background: var(--bg-hover);
	}
	.cat.active {
		color: var(--ink);
		background: var(--bg-active);
	}

	.scroll {
		overflow-y: auto;
		padding: var(--sp-3) var(--sp-2);
		scrollbar-width: thin;
		scrollbar-color: var(--border) transparent;
		flex: 1;
		min-height: 0;
	}
	.group {
		margin-bottom: var(--sp-4);
	}
	.day {
		font-size: var(--fs-11);
		color: var(--ink-faint);
		letter-spacing: 0.06em;
		padding: 0 var(--sp-2) 4px;
		text-transform: uppercase;
	}
	.item {
		display: block;
		padding: var(--sp-2) var(--sp-2);
		border-radius: var(--r-sm);
		border-left: 2px solid var(--c);
		margin-bottom: 2px;
		transition: background 0.12s;
	}
	.item:hover {
		background: var(--bg-hover);
	}
	.row {
		display: flex;
		gap: 6px;
		align-items: baseline;
		font-size: var(--fs-11);
		color: var(--ink-muted);
		margin-bottom: 2px;
	}
	.src {
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--c);
	}
	.pub {
		color: var(--ink-faint);
	}
	.tags {
		margin-left: auto;
		color: var(--ink-faint);
		font-size: 10px;
	}
	.title-line {
		font-size: var(--fs-12);
		color: var(--ink);
		line-height: 1.35;
	}
	.empty {
		padding: var(--sp-6);
		text-align: center;
		color: var(--ink-faint);
		font-size: var(--fs-12);
	}
</style>
