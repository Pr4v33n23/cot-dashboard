<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { fly, fade } from 'svelte/transition';
	import { newsReader } from '$state/newsReader.svelte';
	import EmptyState from '$components/primitives/EmptyState.svelte';
	import Skeleton from '$components/primitives/Skeleton.svelte';

	function onKey(ev: KeyboardEvent) {
		if (ev.key === 'Escape' && newsReader.open) {
			ev.preventDefault();
			newsReader.close();
		}
	}

	onMount(() => {
		window.addEventListener('keydown', onKey);
	});
	onDestroy(() => {
		if (typeof window !== 'undefined') window.removeEventListener('keydown', onKey);
	});

	function fmtDate(d: string | null | undefined): string {
		if (!d) return '';
		try {
			return new Date(d).toISOString().slice(0, 10);
		} catch {
			return d.slice(0, 10);
		}
	}
</script>

{#if newsReader.open}
	<div
		class="scrim"
		transition:fade={{ duration: 180 }}
		onclick={() => newsReader.close()}
		role="presentation"
	></div>

	<aside
		class="drawer"
		transition:fly={{ x: 420, duration: 320, opacity: 0.4 }}
		aria-label="Article reader"
	>
		<header class="head">
			<div class="head-l">
				{#if newsReader.stub?.source}
					<span class="src" data-cat={newsReader.stub.source}>{newsReader.stub.source}</span>
				{/if}
				{#if newsReader.stub?.publisher}
					<span class="pub">· {newsReader.stub.publisher}</span>
				{/if}
				<span class="date num">{fmtDate(newsReader.stub?.date)}</span>
			</div>
			<div class="head-r">
				{#if newsReader.stub?.url}
					<a class="orig" href={newsReader.stub.url} target="_blank" rel="noreferrer">
						open original ↗
					</a>
				{/if}
				<button class="close" onclick={() => newsReader.close()} aria-label="Close reader (Esc)">
					✕
				</button>
			</div>
		</header>

		<div class="body">
			{#if newsReader.loading}
				<div class="loading">
					<h1 class="title-stub">{newsReader.stub?.title ?? 'Loading…'}</h1>
					<div class="skeleton-stack">
						{#each Array(6) as _}
							<Skeleton width="100%" height="12px" />
						{/each}
						<Skeleton width="80%" height="12px" />
					</div>
					<div class="loading-note">extracting article content from {new URL(newsReader.stub?.url ?? 'http://x').hostname}…</div>
				</div>
			{:else if newsReader.error}
				<EmptyState
					variant="error"
					title="Couldn't extract this article"
					body={newsReader.error}
					retry={() => newsReader.retry()}
				/>
				{#if newsReader.stub?.url}
					<div class="fallback">
						<a href={newsReader.stub.url} target="_blank" rel="noreferrer" class="fallback-link">
							Open original article on {new URL(newsReader.stub.url).hostname} ↗
						</a>
					</div>
				{/if}
			{:else if newsReader.article}
				<article class="article">
					<div class="meta-row">
						{#if newsReader.article.site}<span class="site num">{newsReader.article.site}</span>{/if}
						{#if newsReader.article.published}<span class="pub-date num">· {fmtDate(newsReader.article.published)}</span>{/if}
						{#if newsReader.article.byline}<span class="byline">· {newsReader.article.byline}</span>{/if}
						<span class="wc num">· {newsReader.article.word_count.toLocaleString()} words</span>
					</div>
					<h1 class="title">{newsReader.article.title ?? newsReader.stub?.title ?? 'Untitled'}</h1>
					<div class="content">
						{@html newsReader.article.content_html}
					</div>
				</article>
			{/if}
		</div>
	</aside>
{/if}

<style>
	.scrim {
		position: fixed;
		inset: 0;
		background: rgba(10, 10, 11, 0.55);
		backdrop-filter: blur(2px);
		z-index: 90;
	}
	.drawer {
		position: fixed;
		top: 0;
		right: 0;
		bottom: 0;
		width: min(680px, 92vw);
		background: var(--bg-panel);
		border-left: 1px solid var(--border);
		box-shadow: -24px 0 60px rgba(0, 0, 0, 0.4);
		z-index: 100;
		display: flex;
		flex-direction: column;
		min-height: 0;
	}

	.head {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: var(--sp-3);
		padding: var(--sp-3) var(--sp-4);
		border-bottom: 1px solid var(--border-soft);
		flex: none;
	}
	.head-l {
		display: flex;
		align-items: baseline;
		gap: 6px;
		font-size: var(--fs-11);
		color: var(--ink-muted);
		min-width: 0;
		overflow: hidden;
	}
	.src {
		text-transform: uppercase;
		letter-spacing: 0.06em;
		font-family: var(--font-mono);
		color: var(--zone-a1);
	}
	.src[data-cat='agency'] {
		color: var(--zone-a3);
	}
	.src[data-cat='macro'] {
		color: var(--zone-a4);
	}
	.src[data-cat='geopolitics'] {
		color: var(--zone-a2);
	}
	.pub {
		color: var(--ink-faint);
	}
	.date {
		color: var(--ink-faint);
		font-size: var(--fs-11);
		margin-left: var(--sp-2);
	}
	.head-r {
		display: flex;
		align-items: center;
		gap: var(--sp-2);
		flex: none;
	}
	.orig {
		font-size: var(--fs-11);
		color: var(--ink-muted);
		padding: 4px 10px;
		border: 1px solid var(--border);
		border-radius: var(--r-sm);
		transition: color 0.15s, border-color 0.15s;
		white-space: nowrap;
	}
	.orig:hover {
		color: var(--ink);
		border-color: var(--ink-muted);
	}
	.close {
		width: 28px;
		height: 28px;
		display: flex;
		align-items: center;
		justify-content: center;
		color: var(--ink-muted);
		border-radius: var(--r-sm);
		transition: color 0.15s, background 0.15s;
	}
	.close:hover {
		color: var(--ink);
		background: var(--bg-hover);
	}

	.body {
		flex: 1;
		min-height: 0;
		overflow-y: auto;
		padding: var(--sp-6) var(--sp-8) var(--sp-12);
		scrollbar-width: thin;
		scrollbar-color: var(--border) transparent;
	}

	.title-stub,
	.title {
		font-size: clamp(1.3rem, 2.2vw, 1.7rem);
		line-height: 1.25;
		letter-spacing: -0.01em;
		font-weight: 600;
		color: var(--ink);
		margin: 0 0 var(--sp-4);
	}
	.title-stub {
		color: var(--ink-muted);
	}
	.loading-note {
		margin-top: var(--sp-4);
		font-size: var(--fs-12);
		color: var(--ink-faint);
	}
	.skeleton-stack {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}

	.meta-row {
		display: flex;
		align-items: baseline;
		gap: 4px;
		flex-wrap: wrap;
		margin-bottom: var(--sp-3);
		font-size: var(--fs-11);
		color: var(--ink-faint);
		text-transform: lowercase;
		letter-spacing: 0.02em;
	}
	.meta-row .site {
		color: var(--ink-muted);
	}

	.fallback {
		margin-top: var(--sp-4);
		text-align: center;
	}
	.fallback-link {
		display: inline-block;
		padding: var(--sp-2) var(--sp-3);
		border: 1px solid var(--border);
		border-radius: var(--r-sm);
		color: var(--ink-muted);
		font-size: var(--fs-12);
	}
	.fallback-link:hover {
		color: var(--ink);
		border-color: var(--ink-muted);
	}

	/* Article content — reset trafilatura's HTML for our type stack */
	.content :global(*) {
		max-width: 100%;
	}
	.content :global(p) {
		font-size: var(--fs-14);
		line-height: 1.65;
		color: var(--ink);
		margin: 0 0 var(--sp-4);
	}
	.content :global(h1),
	.content :global(h2),
	.content :global(h3) {
		font-weight: 600;
		color: var(--ink);
		letter-spacing: -0.01em;
		margin: var(--sp-6) 0 var(--sp-3);
	}
	.content :global(h1) {
		font-size: var(--fs-20);
	}
	.content :global(h2) {
		font-size: var(--fs-16);
	}
	.content :global(h3) {
		font-size: var(--fs-14);
	}
	.content :global(a) {
		color: var(--attn-high);
		text-decoration: underline;
		text-underline-offset: 2px;
		text-decoration-color: color-mix(in srgb, var(--attn-high) 40%, transparent);
	}
	.content :global(a:hover) {
		text-decoration-color: var(--attn-high);
	}
	.content :global(ul),
	.content :global(ol) {
		padding-left: var(--sp-6);
		margin: 0 0 var(--sp-4);
		color: var(--ink);
	}
	.content :global(li) {
		margin-bottom: 6px;
		line-height: 1.55;
	}
	.content :global(blockquote) {
		margin: var(--sp-4) 0;
		padding: var(--sp-3) var(--sp-4);
		border-left: 2px solid var(--attn-high);
		background: var(--bg-panel-2);
		color: var(--ink-muted);
		font-style: italic;
		border-radius: 0 var(--r-sm) var(--r-sm) 0;
	}
	.content :global(table) {
		width: 100%;
		border-collapse: collapse;
		margin: var(--sp-4) 0;
		font-size: var(--fs-12);
	}
	.content :global(th),
	.content :global(td) {
		padding: 6px 10px;
		border: 1px solid var(--border-soft);
		text-align: left;
	}
	.content :global(th) {
		background: var(--bg-panel-2);
		color: var(--ink-muted);
		font-weight: 500;
	}
	.content :global(code),
	.content :global(pre) {
		font-family: var(--font-mono);
		font-size: var(--fs-12);
		background: var(--bg-panel-2);
		padding: 2px 6px;
		border-radius: 3px;
	}
	.content :global(pre) {
		padding: var(--sp-3);
		overflow-x: auto;
	}

	@media (max-width: 760px) {
		.drawer {
			width: 100vw;
		}
		.body {
			padding: var(--sp-4);
		}
	}
</style>
