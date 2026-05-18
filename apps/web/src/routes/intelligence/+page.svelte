<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { api } from '$api/client';
	import type {
		DigestResponse, SynthesisResponse, MarketDetail, NewsItem, ZoneKey, TodayRow
	} from '$api/types';
	import { ZONE_NAMES } from '$api/types';
	import ZoneBadge from '$components/zone/ZoneBadge.svelte';
	import EmptyState from '$components/primitives/EmptyState.svelte';
	import Skeleton from '$components/primitives/Skeleton.svelte';

	let digest = $state<DigestResponse | null>(null);
	let digestLoading = $state(true);
	let digestError = $state<string | null>(null);

	let selectedSym = $state<string | null>(null);
	let synthesis = $state<SynthesisResponse | null>(null);
	let detail = $state<MarketDetail | null>(null);
	let symNews = $state<NewsItem[]>([]);
	let symLoading = $state(false);
	let symError = $state<string | null>(null);

	let todayRows = $state<TodayRow[]>([]);
	const aiWatchSyms = $derived(new Set(digest?.watch_markets?.map(w => w.symbol) ?? []));
	const allMarkets = $derived.by(() => {
		if (!todayRows.length) return [] as TodayRow[];
		return [...todayRows].sort((a, b) => {
			const aAI = aiWatchSyms.has(a.symbol) ? 1 : 0;
			const bAI = aiWatchSyms.has(b.symbol) ? 1 : 0;
			if (aAI !== bAI) return bAI - aAI;
			return b.n_zones - a.n_zones || b.total_mag - a.total_mag;
		});
	});

	async function loadDigest() {
		digestLoading = true;
		digestError = null;
		try {
			digest = await api.digest();
		} catch (e) {
			digestError = (e as Error).message;
		} finally {
			digestLoading = false;
		}
	}

	async function selectMarket(sym: string) {
		selectedSym = sym;
		symLoading = true;
		symError = null;
		synthesis = null;
		detail = null;
		symNews = [];
		try {
			const [s, d, n] = await Promise.all([
				api.synthesis(sym),
				api.market(sym),
				api.newsForSymbol(sym, { limit: 20 }),
			]);
			synthesis = s;
			detail = d;
			symNews = n.items;
		} catch (e) {
			symError = (e as Error).message;
		} finally {
			symLoading = false;
		}
	}

	onMount(async () => {
		// Load all markets immediately — list always populated even if digest is empty
		api.today().then(rows => { todayRows = rows; }).catch(() => {});
		await loadDigest();
		const sym = page.url.searchParams.get('sym');
		if (sym) selectMarket(sym);
	});

	const lastBar = $derived(detail?.bars?.at(-1));

	const macroNews = $derived(symNews.filter(n =>
		n.source_category === 'macro' || n.source_category === 'agency'
	));
	const microNews = $derived(symNews.filter(n =>
		n.source_category !== 'macro' && n.source_category !== 'agency'
	));

	const activeZones = $derived.by(() => {
		if (!lastBar) return [] as ZoneKey[];
		return (['A1','A2','A3','A4','A5'] as const).filter(z => lastBar[z]);
	});

	const commNet = $derived(lastBar
		? (lastBar.pm_long ?? 0) + (lastBar.sd_long ?? 0) - (lastBar.pm_short ?? 0) - (lastBar.sd_short ?? 0)
		: 0);
	const specNet = $derived(lastBar
		? (lastBar.mm_long ?? lastBar.lf_long ?? 0) - (lastBar.mm_short ?? lastBar.lf_short ?? 0)
		: 0);
	const nrNet = $derived(lastBar ? (lastBar.nr_long ?? 0) - (lastBar.nr_short ?? 0) : 0);
	const divWeeks = $derived(lastBar
		? (lastBar.comm_spec_divergence || lastBar.am_lf_divergence || 0)
		: 0);

	function signalClass(signal: string) {
		if (signal === 'bullish') return 'sig-bull';
		if (signal === 'bearish') return 'sig-bear';
		return 'sig-neu';
	}

	function scoreColor(score: number | null | undefined): string {
		if (!score) return 'var(--ink-faint)';
		if (score > 0.15) return 'var(--long)';
		if (score < -0.15) return 'var(--short)';
		return 'var(--ink-faint)';
	}

	function fmtScore(score: number | null | undefined): string {
		if (score == null) return '—';
		return score > 0 ? `+${score.toFixed(2)}` : score.toFixed(2);
	}

	async function refresh() {
		try {
			await fetch('/api/intelligence/refresh', { method: 'POST' });
			loadDigest();
		} catch { /* silently ignore */ }
	}
</script>

<svelte:head>
	<title>Intelligence · COT_LENS</title>
</svelte:head>

<div class="page">
	<!-- ── Left: digest ── -->
	<aside class="left">
		<header class="left-header">
			<div>
				<div class="eyebrow">AI · daily digest</div>
				<h1 class="title">Intelligence</h1>
			</div>
			<div class="header-meta">
				<span class="ai-badge">DeepSeek-V4-Pro</span>
				{#if digest}
					<span class="date num">{digest.generated_at.slice(0,10)}</span>
				{/if}
			</div>
		</header>

		{#if digestLoading}
			<div class="skeleton-stack">
				{#each Array(6) as _}
					<Skeleton width="100%" height="14px" />
				{/each}
			</div>
		{:else if digestError}
			<EmptyState variant="error" title="Couldn't load digest" body={digestError} retry={loadDigest} />
		{:else if digest}
			<section class="digest-card">
				<div class="card-label">This week's macro narrative</div>
				<p class="narrative">{digest.macro_narrative}</p>
			</section>

			<section class="digest-card">
				<div class="card-label">Sector signals</div>
				{#each digest.sector_signals as s}
					<div class="sector-row">
						<span class="sec-dot" style:background={`var(--sec-${s.sector})`}></span>
						<span class="sec-name">{s.sector}</span>
						<span class="sec-summary">{s.summary}</span>
						<span class="sec-signal {signalClass(s.signal)}">
							{s.signal === 'bullish' ? '↑' : s.signal === 'bearish' ? '↓' : '→'} {s.signal}
						</span>
					</div>
				{/each}
			</section>

			<section class="digest-card markets-list">
				<div class="card-label">
					All markets · click to analyse
					{#if todayRows.length}
						<span class="market-count num">{todayRows.length}</span>
					{/if}
				</div>
				{#if !todayRows.length}
					<div class="empty-text">Loading markets…</div>
				{:else}
					{#each allMarkets as row}
						<button
							class="watch-row"
							class:active={selectedSym === row.symbol}
							onclick={() => selectMarket(row.symbol)}
						>
							{#if aiWatchSyms.has(row.symbol)}
								<span class="ai-flag">⚡</span>
							{:else}
								<span class="wm-rank num">{row.n_zones > 0 ? row.n_zones : '·'}</span>
							{/if}
							<span class="wm-sym num">{row.symbol}</span>
							<span class="wm-reason">{row.sector}</span>
							{#if row.zones_on.length > 0}
								<span class="zone-pills">
									{#each row.zones_on.slice(0,3) as z}
										<span class="zone-pill zone-{z.toLowerCase()}">{z}</span>
									{/each}
								</span>
							{/if}
							<span class="wm-arrow">›</span>
						</button>
					{/each}
				{/if}
			</section>

			<section class="digest-card">
				<div class="card-label">Macro + scheduled events</div>
				{#await api.newsAllMacro({ limit: 8 }) then newsResp}
					{#each newsResp.items as item}
						<div class="nm-row">
							<span class="nm-type nm-{item.source_category}">{item.source}</span>
							<span class="nm-title">{item.title}</span>
							<span class="nm-score num" style:color={scoreColor(item.sentiment_score)}>
								{fmtScore(item.sentiment_score)}
							</span>
						</div>
					{/each}
				{:catch}
					<span class="empty-text">No macro news available</span>
				{/await}
			</section>

			<button class="refresh-btn" onclick={refresh}>↻ Regenerate digest</button>
		{/if}
	</aside>

	<!-- ── Right: per-market synthesis ── -->
	<main class="right">
		{#if !selectedSym}
			<div class="right-empty">
				<EmptyState
					variant="empty"
					title="Select a market"
					body="Click any market in the watch list to load its full AI analysis."
				/>
			</div>
		{:else if symLoading}
			<div class="right-loading">
				<div class="skeleton-stack wide">
					<Skeleton width="200px" height="24px" />
					<Skeleton width="100%" height="60px" />
					<Skeleton width="100%" height="80px" />
					<Skeleton width="100%" height="120px" />
				</div>
			</div>
		{:else if symError}
			<EmptyState variant="error" title="Couldn't load analysis" body={symError} retry={() => selectMarket(selectedSym!)} />
		{:else if synthesis && detail}
			<div class="right-content">
				<header class="mkt-header">
					<div>
						<div class="mkt-sym num">{detail.contract.symbol} · {detail.contract.name}</div>
						<div class="mkt-sub">{detail.contract.sector} · {detail.contract.cftc_code}</div>
					</div>
					<div class="mkt-badges">
						{#each activeZones as z}
							<ZoneBadge zone={z} magnitude={0.8} />
						{/each}
					</div>
				</header>

				<div class="confluence-strip">
					<div class="cs-score-wrap">
						<div class="cs-label">Confluence</div>
						<div class="cs-score num">{synthesis.confluence_score.toFixed(2)}</div>
					</div>
					<div class="cs-right">
						<div class="cs-bar">
							<div class="cs-fill" style:width={`${synthesis.confluence_score * 100}%`}></div>
						</div>
						<div class="cs-chips">
							{#each synthesis.key_factors as f}
								<span class="chip">{f}</span>
							{/each}
						</div>
					</div>
				</div>

				{#if lastBar}
					<section class="analysis-section">
						<div class="section-label">COT breakdown</div>
						<div class="cot-grid">
							<div class="cot-card">
								<div class="cc-label">Commercials / Dealers</div>
								<div class="cc-val num" style:color={commNet >= 0 ? 'var(--long)' : 'var(--short)'}>
									{commNet >= 0 ? '+' : ''}{(commNet / 1000).toFixed(0)}k
								</div>
								<div class="cc-idx">COT idx: {lastBar.cot_index_comm?.toFixed(1) ?? '—'}</div>
							</div>
							<div class="cot-card">
								<div class="cc-label">Large Specs / Lev Funds</div>
								<div class="cc-val num" style:color={specNet >= 0 ? 'var(--long)' : 'var(--short)'}>
									{specNet >= 0 ? '+' : ''}{(specNet / 1000).toFixed(0)}k
								</div>
								<div class="cc-idx">Net: {specNet >= 0 ? 'long' : 'short'}</div>
							</div>
							<div class="cot-card">
								<div class="cc-label">Small Specs</div>
								<div class="cc-val num" style:color={nrNet >= 0 ? 'var(--long)' : 'var(--short)'}>
									{nrNet >= 0 ? '+' : ''}{(nrNet / 1000).toFixed(0)}k
								</div>
								<div class="cc-idx">Non-reportable</div>
							</div>
							<div class="cot-card">
								<div class="cc-label">Divergence</div>
								<div class="cc-val num" style:color={divWeeks > 0 ? 'var(--zone-a2)' : 'var(--ink-faint)'}>
									{divWeeks > 0 ? `${divWeeks} wk` : '—'}
								</div>
								<div class="cc-idx">{divWeeks > 0 ? 'active' : 'not active'}</div>
							</div>
						</div>
					</section>
				{/if}

				<section class="analysis-section">
					<div class="section-label">DeepSeek analysis</div>
					<p class="summary-text">{synthesis.summary}</p>
				</section>

				<section class="analysis-section">
					<div class="section-label">Macro + micro news · {selectedSym}</div>
					<div class="news-dual">
						<div class="news-col">
							<div class="nc-head macro">Macro (OPEC · EIA · FOMC · WASDE)</div>
							{#each macroNews.slice(0, 5) as item}
								<div class="nc-item">
									<div class="nc-dot" style:background={scoreColor(item.sentiment_score)}></div>
									<div class="nc-title">{item.title}</div>
									<div class="nc-score num" style:color={scoreColor(item.sentiment_score)}>
										{fmtScore(item.sentiment_score)}
									</div>
								</div>
							{:else}
								<div class="empty-text">No macro news</div>
							{/each}
						</div>
						<div class="news-col">
							<div class="nc-head micro">Micro (yfinance ticker)</div>
							{#each microNews.slice(0, 5) as item}
								<div class="nc-item">
									<div class="nc-dot" style:background={scoreColor(item.sentiment_score)}></div>
									<div class="nc-title">{item.title}</div>
									<div class="nc-score num" style:color={scoreColor(item.sentiment_score)}>
										{fmtScore(item.sentiment_score)}
									</div>
								</div>
							{:else}
								<div class="empty-text">No micro news</div>
							{/each}
						</div>
					</div>
				</section>

				{#if synthesis.watch}
					<div class="watch-box">
						<span class="watch-icon">👁</span>
						<div class="watch-text"><strong>Watch:</strong> {synthesis.watch}</div>
					</div>
				{/if}

				<div class="disclaimer">Generated by DeepSeek-V4-Pro from structured data only. Not a trading signal.</div>
			</div>
		{/if}
	</main>
</div>

<style>
	.page {
		display: grid;
		grid-template-columns: 340px 1fr;
		height: 100%;
		min-height: 0;
		overflow: hidden;
	}
	.left {
		display: flex;
		flex-direction: column;
		gap: var(--sp-3);
		overflow-y: auto;
		padding: var(--sp-6) var(--sp-4);
		border-right: 1px solid var(--border);
		scrollbar-width: thin;
		scrollbar-color: var(--border) transparent;
	}
	.left-header {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		padding-bottom: var(--sp-3);
		border-bottom: 1px solid var(--border-soft);
		flex-shrink: 0;
	}
	.eyebrow { font-size: var(--fs-11); text-transform: uppercase; letter-spacing: .06em; color: var(--ink-faint); }
	.title { font-size: var(--fs-20); font-weight: 600; margin: 2px 0 0; }
	.header-meta { display: flex; flex-direction: column; align-items: flex-end; gap: 4px; }
	.ai-badge { font-size: 9px; font-family: var(--font-mono); padding: 2px 7px; border-radius: 99px; background: rgba(183,148,246,.08); color: var(--zone-a2); border: 1px solid rgba(183,148,246,.2); }
	.date { font-size: var(--fs-11); color: var(--ink-faint); }
	.skeleton-stack { display: flex; flex-direction: column; gap: 8px; padding: var(--sp-4) 0; }
	.skeleton-stack.wide { width: 480px; }

	.digest-card { background: var(--bg-panel); border: 1px solid var(--border); border-radius: var(--r-md); overflow: hidden; }
	.card-label { padding: 7px 12px; font-size: 10px; text-transform: uppercase; letter-spacing: .05em; color: var(--ink-faint); border-bottom: 1px solid var(--border-soft); }
	.narrative { margin: 0; padding: 10px 12px; font-size: var(--fs-12); line-height: 1.7; color: var(--ink-muted); border-left: 2px solid var(--zone-a2); }

	.sector-row { display: flex; align-items: center; gap: 6px; padding: 6px 12px; border-bottom: 1px solid var(--border-soft); }
	.sector-row:last-child { border-bottom: none; }
	.sec-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
	.sec-name { font-size: var(--fs-12); font-weight: 600; width: 54px; flex-shrink: 0; }
	.sec-summary { flex: 1; font-size: 10px; color: var(--ink-muted); }
	.sec-signal { font-size: 9px; font-family: var(--font-mono); padding: 2px 6px; border-radius: 99px; flex-shrink: 0; }
	.sig-bull { background: rgba(24,224,143,.1); color: var(--long); }
	.sig-bear { background: rgba(255,90,95,.1); color: var(--short); }
	.sig-neu  { background: rgba(138,138,147,.1); color: var(--ink-muted); }

	.watch-row { width: 100%; display: flex; align-items: center; gap: 7px; padding: 8px 12px; border-bottom: 1px solid var(--border-soft); background: none; cursor: pointer; text-align: left; transition: background .1s; border-left: 2px solid transparent; }
	.watch-row:last-child { border-bottom: none; }
	.watch-row:hover { background: var(--bg-hover); }
	.watch-row.active { background: var(--bg-hover); border-left-color: var(--zone-a2); }
	.wm-rank { color: var(--ink-faint); font-size: 10px; width: 18px; flex-shrink: 0; }
	.wm-sym  { font-size: var(--fs-12); font-weight: 700; width: 48px; flex-shrink: 0; }
	.wm-reason { flex: 1; font-size: 10px; color: var(--ink-muted); }
	.wm-score { font-size: 11px; color: var(--zone-a2); flex-shrink: 0; }
	.wm-arrow { color: var(--ink-faint); font-size: 12px; }

	.markets-list { max-height: 340px; overflow-y: auto; scrollbar-width: thin; scrollbar-color: var(--border) transparent; }
	.market-count { background: var(--border); border-radius: 99px; padding: 1px 6px; font-size: 9px; margin-left: 6px; }
	.ai-flag { font-size: 11px; width: 18px; flex-shrink: 0; color: var(--zone-a2); }
	.zone-pills { display: flex; gap: 2px; flex-shrink: 0; }
	.zone-pill { font-size: 8px; font-family: var(--font-mono); padding: 1px 4px; border-radius: 3px; }
	.zone-a1 { background: rgba(245,166,35,.15); color: var(--zone-a1); }
	.zone-a2 { background: rgba(183,148,246,.15); color: var(--zone-a2); }
	.zone-a3 { background: rgba(79,209,197,.12); color: var(--zone-a3); }
	.zone-a4 { background: rgba(245,101,101,.12); color: var(--zone-a4); }
	.zone-a5 { background: rgba(24,224,143,.10); color: var(--zone-a5); }

	.nm-row { display: flex; align-items: flex-start; gap: 6px; padding: 5px 12px; border-bottom: 1px solid var(--border-soft); }
	.nm-row:last-child { border-bottom: none; }
	.nm-type { font-size: 9px; padding: 1px 5px; border-radius: 3px; font-family: var(--font-mono); flex-shrink: 0; margin-top: 2px; background: rgba(183,148,246,.15); color: var(--zone-a2); }
	.nm-title { flex: 1; font-size: 11px; color: var(--ink-muted); line-height: 1.4; }
	.nm-score { font-size: 10px; flex-shrink: 0; }
	.refresh-btn { background: var(--bg-panel); border: 1px solid var(--border); border-radius: var(--r-sm); padding: 6px 12px; font-size: var(--fs-12); color: var(--ink-muted); cursor: pointer; width: 100%; }
	.refresh-btn:hover { color: var(--ink); background: var(--bg-hover); }
	.empty-text { padding: 8px 10px; font-size: 11px; color: var(--ink-faint); display: block; }

	.right { overflow-y: auto; scrollbar-width: thin; scrollbar-color: var(--border) transparent; }
	.right-empty, .right-loading { display: flex; align-items: center; justify-content: center; height: 100%; }
	.right-content { padding: var(--sp-6); display: flex; flex-direction: column; gap: var(--sp-5); max-width: 860px; }

	.mkt-header { display: flex; align-items: flex-start; justify-content: space-between; padding-bottom: var(--sp-4); border-bottom: 1px solid var(--border-soft); }
	.mkt-sym { font-size: var(--fs-20); font-weight: 700; }
	.mkt-sub { font-size: var(--fs-12); color: var(--ink-muted); margin-top: 3px; }
	.mkt-badges { display: flex; gap: 4px; flex-wrap: wrap; justify-content: flex-end; }

	.confluence-strip { display: flex; align-items: flex-start; gap: var(--sp-4); padding: var(--sp-4); background: var(--bg-panel); border: 1px solid var(--border); border-radius: var(--r-md); }
	.cs-score-wrap { flex-shrink: 0; }
	.cs-label { font-size: 10px; text-transform: uppercase; letter-spacing: .05em; color: var(--ink-faint); }
	.cs-score { font-size: var(--fs-28); font-weight: 700; color: var(--zone-a2); line-height: 1; margin-top: 2px; }
	.cs-right { flex: 1; }
	.cs-bar { height: 5px; background: var(--border); border-radius: 3px; overflow: hidden; }
	.cs-fill { height: 100%; border-radius: 3px; background: linear-gradient(90deg, var(--zone-a3), var(--zone-a2)); }
	.cs-chips { display: flex; gap: 4px; flex-wrap: wrap; margin-top: 8px; }
	.chip { padding: 2px 8px; border-radius: 99px; font-size: 10px; font-family: var(--font-mono); background: rgba(183,148,246,.1); color: var(--zone-a2); border: 1px solid rgba(183,148,246,.2); }

	.analysis-section { display: flex; flex-direction: column; gap: var(--sp-2); }
	.section-label { font-size: 10px; text-transform: uppercase; letter-spacing: .05em; color: var(--ink-faint); }

	.cot-grid { display: grid; grid-template-columns: repeat(4,1fr); gap: var(--sp-2); }
	.cot-card { background: var(--bg-panel); border: 1px solid var(--border); border-radius: var(--r-sm); padding: 8px 10px; }
	.cc-label { font-size: 9px; color: var(--ink-faint); text-transform: uppercase; letter-spacing: .04em; }
	.cc-val { font-size: var(--fs-16); font-weight: 700; margin-top: 3px; }
	.cc-idx { font-size: 10px; color: var(--ink-faint); margin-top: 3px; }

	.summary-text { font-size: var(--fs-13); line-height: 1.7; color: var(--ink-muted); padding: 10px 12px; background: var(--bg-panel); border-radius: var(--r-sm); border-left: 2px solid var(--zone-a2); margin: 0; }

	.news-dual { display: grid; grid-template-columns: 1fr 1fr; gap: var(--sp-2); }
	.news-col { background: var(--bg-panel); border: 1px solid var(--border); border-radius: var(--r-sm); overflow: hidden; }
	.nc-head { padding: 5px 10px; font-size: 9px; text-transform: uppercase; letter-spacing: .05em; border-bottom: 1px solid var(--border-soft); }
	.nc-head.macro { color: var(--zone-a2); }
	.nc-head.micro { color: var(--zone-a3); }
	.nc-item { display: flex; gap: 6px; padding: 6px 10px; border-bottom: 1px solid var(--border-soft); font-size: 11px; }
	.nc-item:last-child { border-bottom: none; }
	.nc-dot { width: 5px; height: 5px; border-radius: 50%; margin-top: 4px; flex-shrink: 0; }
	.nc-title { flex: 1; color: var(--ink-muted); line-height: 1.4; }
	.nc-score { flex-shrink: 0; font-size: 10px; }

	.watch-box { display: flex; gap: var(--sp-2); padding: var(--sp-3); background: rgba(245,166,35,.06); border: 1px solid rgba(245,166,35,.2); border-radius: var(--r-sm); }
	.watch-icon { font-size: 14px; }
	.watch-text { font-size: var(--fs-12); color: var(--ink-muted); line-height: 1.55; }
	.watch-text strong { color: var(--pending); }
	.disclaimer { font-size: 10px; color: var(--ink-faint); padding-top: var(--sp-2); border-top: 1px solid var(--border-soft); }
</style>
