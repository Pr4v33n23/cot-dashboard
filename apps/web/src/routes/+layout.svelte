<script lang="ts">
	import '$design/tokens.css';
	import { onMount, tick } from 'svelte';
	import { page } from '$app/state';
	import { fly } from 'svelte/transition';
	import { universeState } from '$state/universe.svelte';
	import { createSpring } from '$engine/sim/spring';
	import { onRender } from '$engine/scheduler';
	import NewsReader from '$components/news/NewsReader.svelte';
	import favicon from '$lib/assets/favicon.svg';

	let { children } = $props();

	const routes = [
		{ href: '/', label: 'Today', short: 'TD' },
		{ href: '/heatmap', label: 'Heatmap', short: 'HM' },
		{ href: '/divergence', label: 'Divergence', short: 'DV' },
		{ href: '/extremes', label: 'Extremes', short: 'EX' },
		{ href: '/alerts', label: 'Alerts', short: '🔔' },
		{ href: '/compare', label: 'Compare', short: '⊞' },
		{ href: '/correlation', label: 'Correlation', short: '⊗' },
		{ href: '/chat', label: 'Chat', short: '💬' },
		{ href: '/intelligence', label: 'Intelligence', short: 'AI' }
	];

	const sectorGroups = $derived.by(() => {
		const groups: Record<string, typeof universeState.contracts> = {};
		for (const c of universeState.contracts) {
			(groups[c.sector] ??= []).push(c);
		}
		return Object.entries(groups);
	});

	const currentSymbol = $derived.by(() => {
		const m = page.url.pathname.match(/\/market\/([^/]+)/);
		return m ? m[1] : null;
	});

	const isRouteActive = (href: string) => {
		if (href === '/') return page.url.pathname === '/';
		return page.url.pathname.startsWith(href);
	};

	// ── Sidebar collapse (springy width) ─────────────────────────────────
	let collapsed = $state(false);
	const widthSpring = createSpring(240, { stiffness: 240, damping: 28 });
	let sidebarWidth = $state(240);

	// Below 980px (tablet portrait + phone), start collapsed.
	function initialCollapse(): boolean {
		if (typeof window === 'undefined') return false;
		return window.matchMedia('(max-width: 980px)').matches;
	}

	// ── Springy active-route indicator (rail on the left of the active link)
	const indicatorTop = createSpring(0, { stiffness: 380, damping: 32 });
	const indicatorHeight = createSpring(0, { stiffness: 380, damping: 32 });
	let indicatorY = $state(0);
	let indicatorH = $state(0);
	let routesEl: HTMLElement | null = $state(null);
	const routeRefs = new Map<string, HTMLElement>();

	// Action to capture each route link element into the map (Svelte 5
	// `bind:this` doesn't accept arbitrary expressions inside an {#each}).
	function trackRoute(node: HTMLElement, href: string) {
		routeRefs.set(href, node);
		queueMicrotask(syncIndicator);
		return {
			destroy() {
				routeRefs.delete(href);
			}
		};
	}

	async function syncIndicator() {
		await tick();
		if (!routesEl) return;
		// Find active route element
		const active = routes.find((r) => isRouteActive(r.href));
		if (!active) return;
		const el = routeRefs.get(active.href);
		if (!el) return;
		const parent = routesEl.getBoundingClientRect();
		const r = el.getBoundingClientRect();
		indicatorTop.set(r.top - parent.top);
		indicatorHeight.set(r.height);
	}

	$effect(() => {
		void page.url.pathname;
		void universeState.contracts.length; // refresh after universe loads (changes layout)
		syncIndicator();
	});

	$effect(() => {
		widthSpring.set(collapsed ? 64 : 240);
	});

	function onKeydown(ev: KeyboardEvent) {
		// Cmd/Ctrl + \ toggles the sidebar (familiar from VS Code / Linear).
		if ((ev.metaKey || ev.ctrlKey) && ev.key === '\\') {
			ev.preventDefault();
			collapsed = !collapsed;
		}
	}

	onMount(() => {
		universeState.load();
		// One-shot init for the indicator after universe loads
		syncIndicator();
		window.addEventListener('keydown', onKeydown);

		const stop = onRender(() => {
			sidebarWidth = widthSpring.value;
			indicatorY = indicatorTop.value;
			indicatorH = indicatorHeight.value;
		});

		// Auto-collapse on tablet+phone widths
		if (initialCollapse()) {
			collapsed = true;
		}
		// Initial values without animating
		const initial = collapsed ? 64 : 240;
		widthSpring.jump(initial);
		sidebarWidth = initial;

		// Watch viewport changes — keep collapsed if viewport shrinks below threshold
		const mql = window.matchMedia('(max-width: 980px)');
		const onMql = (e: MediaQueryListEvent) => {
			if (e.matches) collapsed = true;
		};
		mql.addEventListener('change', onMql);

		return () => {
			stop();
			window.removeEventListener('keydown', onKeydown);
			mql.removeEventListener('change', onMql);
			widthSpring.dispose();
			indicatorTop.dispose();
			indicatorHeight.dispose();
		};
	});
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
</svelte:head>

<div class="app" style:--sidebar-w={`${sidebarWidth}px`}>
	<aside class="sidebar" class:collapsed>
		<header class="brand">
			<button
				class="brand-mark"
				onclick={() => (collapsed = !collapsed)}
				aria-label={collapsed ? 'expand sidebar' : 'collapse sidebar'}
				title={collapsed ? 'expand (⌘\\)' : 'collapse (⌘\\)'}
			>
				<span class="brand-dot"></span>
				{#if !collapsed}
					<span class="brand-name num">COT_LENS</span>
				{/if}
			</button>
			{#if !collapsed}
				<div class="brand-sub">v1 · positioning intelligence</div>
			{/if}
		</header>

		<nav class="routes" bind:this={routesEl}>
			<div
				class="route-indicator"
				style:transform={`translateY(${indicatorY}px)`}
				style:height={`${indicatorH}px`}
				aria-hidden="true"
			></div>
			{#each routes as r}
				<a
					href={r.href}
					class="route"
					class:active={isRouteActive(r.href)}
					data-sveltekit-preload-data="hover"
					use:trackRoute={r.href}
				>
					<span class="route-glyph num">{r.short}</span>
					{#if !collapsed}
						<span class="route-label">{r.label}</span>
					{/if}
				</a>
			{/each}
		</nav>

		<div class="section-label" class:hide={collapsed}>
			<span>Markets</span>
			<span class="num">{universeState.contracts.length}</span>
		</div>
		<div class="markets">
			{#each sectorGroups as [sector, contracts]}
				<div class="sector-group">
					{#if !collapsed}
						<div class="sector-label" style:--sec-color={`var(--sec-${sector})`}>
							<span class="sector-bar"></span>
							{sector}
						</div>
					{/if}
					{#each contracts as c}
						<a
							href={`/market/${c.symbol}`}
							class="market-row"
							class:active={currentSymbol === c.symbol}
							data-sveltekit-preload-data="hover"
							style:--sec-color={`var(--sec-${c.sector})`}
							title={collapsed ? `${c.symbol} · ${c.name}` : ''}
						>
							<span class="market-sym num">{c.symbol}</span>
							{#if !collapsed}
								<span class="market-name">{c.name}</span>
							{/if}
						</a>
					{/each}
				</div>
			{/each}
			{#if universeState.loading && universeState.contracts.length === 0}
				<div class="empty">loading…</div>
			{/if}
			{#if universeState.error}
				<div class="error">{universeState.error}</div>
			{/if}
		</div>

		<footer class="footer" class:collapsed>
			<div class="status-line">
				<span class="status-dot"></span>
				{#if !collapsed && universeState.status}
					<span class="num">
						{universeState.status.n_markets}m · {universeState.status.n_news}n
					</span>
				{/if}
			</div>
			{#if !collapsed}
				<div class="ink-faint">
					{universeState.status?.loaded_at?.slice(0, 16).replace('T', ' ') ?? '—'}
				</div>
			{/if}
		</footer>
	</aside>

	<main class="main">
		{#key page.url.pathname}
			<div class="route-frame" in:fly={{ y: 12, duration: 280, delay: 30 }}>
				{@render children()}
			</div>
		{/key}
	</main>
</div>

<!-- Global in-app news reader drawer (open via newsReader.openItem / openUrl) -->
<NewsReader />

<style>
	.app {
		display: grid;
		grid-template-columns: var(--sidebar-w) 1fr;
		height: 100vh;
		min-height: 100vh;
		background: var(--bg-canvas);
		color: var(--ink);
		overflow: hidden;
	}

	.sidebar {
		background: var(--bg-panel);
		border-right: 1px solid var(--border);
		display: flex;
		flex-direction: column;
		min-height: 0;
		min-width: 0;
		overflow: hidden;
	}

	@media print {
		.sidebar { display: none !important; }
		.app { grid-template-columns: 1fr !important; }
		.main { overflow: visible !important; }
	}

	.brand {
		padding: var(--sp-4) var(--sp-3) var(--sp-3);
		border-bottom: 1px solid var(--border-soft);
	}
	.brand-mark {
		display: flex;
		align-items: center;
		gap: var(--sp-2);
		cursor: pointer;
	}
	.brand-mark:hover .brand-dot {
		transform: scale(1.15);
		box-shadow: 0 0 16px rgba(183, 148, 246, 0.7);
	}
	.brand-dot {
		width: 8px;
		height: 8px;
		border-radius: 2px;
		background: var(--attn-high);
		box-shadow: 0 0 12px rgba(183, 148, 246, 0.5);
		transition: transform 0.15s ease, box-shadow 0.15s ease;
		flex: none;
	}
	.brand-name {
		font-weight: 600;
		font-size: var(--fs-14);
		letter-spacing: 0.06em;
		white-space: nowrap;
	}
	.brand-sub {
		margin-top: 4px;
		font-size: var(--fs-11);
		color: var(--ink-faint);
		letter-spacing: 0.04em;
		white-space: nowrap;
	}

	.routes {
		position: relative;
		padding: var(--sp-3) var(--sp-2);
		display: flex;
		flex-direction: column;
		gap: 2px;
		border-bottom: 1px solid var(--border-soft);
	}
	.route-indicator {
		position: absolute;
		left: 0;
		width: 2px;
		background: var(--attn-high);
		border-radius: 0 2px 2px 0;
		box-shadow: 0 0 8px rgba(183, 148, 246, 0.55);
		pointer-events: none;
		will-change: transform, height;
	}
	.route {
		display: flex;
		align-items: center;
		gap: var(--sp-3);
		padding: 7px var(--sp-3);
		border-radius: var(--r-sm);
		font-size: var(--fs-13);
		color: var(--ink-muted);
		transition: color 0.15s, background 0.15s;
		white-space: nowrap;
	}
	.route:hover {
		color: var(--ink);
		background: var(--bg-hover);
	}
	.route.active {
		color: var(--ink);
	}
	.route-glyph {
		font-size: 10px;
		color: var(--ink-faint);
		width: 18px;
		text-align: center;
		letter-spacing: 0.05em;
	}
	.route.active .route-glyph {
		color: var(--attn-high);
	}
	.route-label {
		flex: 1;
	}

	.section-label {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: var(--sp-4) var(--sp-4) var(--sp-2);
		font-size: var(--fs-11);
		text-transform: uppercase;
		letter-spacing: 0.1em;
		color: var(--ink-faint);
	}
	.section-label.hide {
		visibility: hidden;
		height: 0;
		padding: 0;
		overflow: hidden;
	}

	.markets {
		flex: 1;
		overflow-y: auto;
		padding: 0 var(--sp-2) var(--sp-3);
		scrollbar-width: thin;
		scrollbar-color: var(--border) transparent;
	}

	.sector-group {
		margin-bottom: var(--sp-3);
	}
	.sector-label {
		display: flex;
		align-items: center;
		gap: 6px;
		padding: 4px var(--sp-2);
		font-size: var(--fs-11);
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: var(--ink-muted);
	}
	.sector-bar {
		width: 8px;
		height: 2px;
		background: var(--sec-color);
		border-radius: 1px;
	}

	.market-row {
		display: grid;
		grid-template-columns: 36px 1fr;
		align-items: center;
		gap: var(--sp-2);
		padding: 5px var(--sp-2);
		border-radius: var(--r-sm);
		font-size: var(--fs-12);
		color: var(--ink-muted);
		transition: color 0.12s, background 0.12s;
		position: relative;
		white-space: nowrap;
	}
	.sidebar.collapsed .market-row {
		grid-template-columns: 1fr;
		justify-items: center;
	}
	.market-row:hover {
		color: var(--ink);
		background: var(--bg-hover);
	}
	.market-row.active {
		color: var(--ink);
		background: var(--bg-active);
	}
	.market-row.active::before {
		content: '';
		position: absolute;
		left: -8px;
		top: 25%;
		bottom: 25%;
		width: 2px;
		background: var(--sec-color);
		border-radius: 0 2px 2px 0;
	}
	.market-sym {
		color: var(--ink);
		font-weight: 500;
	}
	.market-name {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.footer {
		padding: var(--sp-3) var(--sp-4);
		border-top: 1px solid var(--border-soft);
		font-size: var(--fs-11);
	}
	.footer.collapsed {
		padding: var(--sp-3);
		display: flex;
		justify-content: center;
	}
	.status-line {
		display: flex;
		align-items: center;
		gap: 6px;
		color: var(--ink-muted);
	}
	.status-dot {
		width: 6px;
		height: 6px;
		border-radius: 50%;
		background: var(--long);
		box-shadow: 0 0 8px rgba(24, 224, 143, 0.5);
		animation: pulse 2.4s ease-in-out infinite;
	}
	@keyframes pulse {
		0%, 100% { opacity: 1; }
		50% { opacity: 0.45; }
	}
	.ink-faint {
		color: var(--ink-faint);
		margin-top: 2px;
	}

	.empty,
	.error {
		padding: var(--sp-3) var(--sp-2);
		font-size: var(--fs-12);
		color: var(--ink-faint);
	}
	.error {
		color: var(--short);
	}

	.main {
		min-width: 0;
		min-height: 0;
		overflow: hidden;
		position: relative;
		display: flex;
		flex-direction: column;
	}
	.route-frame {
		flex: 1;
		min-height: 0;
		display: flex;
		flex-direction: column;
	}
	/* The page-level container in each route fills the route-frame and
	   decides its own overflow strategy. Routes that scroll the whole page
	   (Today, Heatmap, Divergence) set `overflow-y: auto` on .page; routes
	   that pin to the viewport (Market) keep `overflow: hidden` and let
	   their inner panels scroll independently. */
	.route-frame :global(.page) {
		flex: 1;
		min-height: 0;
	}
</style>
