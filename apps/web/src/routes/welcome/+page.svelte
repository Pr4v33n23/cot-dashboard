<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { onRender } from '$engine/scheduler';
	import { createSpring } from '$engine/sim/spring';
	import { api } from '$api/client';
	import type { TodayRow } from '$api/types';
	import { ZONE_NAMES } from '$api/types';

	let today = $state<TodayRow[]>([]);
	let loaded = $state(false);

	// Hero canvas: ambient particle field that drifts. No images, no video.
	let heroCanvas: HTMLCanvasElement;
	let heroW = $state(800);
	let heroH = $state(420);

	onMount(async () => {
		try {
			today = (await api.today()).slice(0, 6);
		} catch {
			// landing page works offline — empty preview is fine
		} finally {
			loaded = true;
		}
	});

	// ── Ambient hero animation: drifting dots, no payload images ───────────
	const particles = Array.from({ length: 80 }, () => ({
		x: Math.random(),
		y: Math.random(),
		vx: (Math.random() - 0.5) * 0.0004,
		vy: (Math.random() - 0.5) * 0.0004,
		r: 0.6 + Math.random() * 1.2,
		o: 0.15 + Math.random() * 0.45
	}));

	let stop: (() => void) | null = null;

	function resize() {
		if (!heroCanvas) return;
		const r = heroCanvas.parentElement!.getBoundingClientRect();
		heroW = r.width;
		heroH = r.height;
		const dpr = window.devicePixelRatio || 1;
		heroCanvas.width = heroW * dpr;
		heroCanvas.height = heroH * dpr;
		heroCanvas.style.width = `${heroW}px`;
		heroCanvas.style.height = `${heroH}px`;
		const ctx = heroCanvas.getContext('2d')!;
		ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
	}

	onMount(() => {
		resize();
		const ro = new ResizeObserver(resize);
		ro.observe(heroCanvas.parentElement!);

		stop = onRender(() => {
			const ctx = heroCanvas.getContext('2d')!;
			ctx.clearRect(0, 0, heroW, heroH);
			// Soft radial glow background
			const grad = ctx.createRadialGradient(heroW * 0.7, heroH * 0.4, 0, heroW * 0.7, heroH * 0.4, heroW * 0.6);
			grad.addColorStop(0, 'rgba(183, 148, 246, 0.13)');
			grad.addColorStop(1, 'rgba(10, 10, 11, 0)');
			ctx.fillStyle = grad;
			ctx.fillRect(0, 0, heroW, heroH);

			// Connect-the-dots particle field
			ctx.fillStyle = 'rgba(232, 232, 234, 0.7)';
			for (const p of particles) {
				p.x += p.vx;
				p.y += p.vy;
				if (p.x < 0 || p.x > 1) p.vx *= -1;
				if (p.y < 0 || p.y > 1) p.vy *= -1;
				ctx.globalAlpha = p.o;
				ctx.beginPath();
				ctx.arc(p.x * heroW, p.y * heroH, p.r, 0, Math.PI * 2);
				ctx.fill();
			}
			ctx.globalAlpha = 1;

			// Lines between close particles
			ctx.strokeStyle = 'rgba(183, 148, 246, 0.18)';
			ctx.lineWidth = 0.6;
			for (let i = 0; i < particles.length; i++) {
				for (let j = i + 1; j < particles.length; j++) {
					const a = particles[i];
					const b = particles[j];
					const dx = (a.x - b.x) * heroW;
					const dy = (a.y - b.y) * heroH;
					const d = Math.sqrt(dx * dx + dy * dy);
					if (d < 120) {
						ctx.globalAlpha = (1 - d / 120) * 0.4;
						ctx.beginPath();
						ctx.moveTo(a.x * heroW, a.y * heroH);
						ctx.lineTo(b.x * heroW, b.y * heroH);
						ctx.stroke();
					}
				}
			}
			ctx.globalAlpha = 1;
		});

		return () => {
			ro.disconnect();
			stop?.();
		};
	});

	onDestroy(() => stop?.());
</script>

<svelte:head>
	<title>COT_LENS — positioning intelligence</title>
</svelte:head>

<div class="page">
	<header class="topbar">
		<a href="/" class="brand-link">
			<span class="brand-dot"></span>
			<span class="brand num">COT_LENS</span>
			<span class="brand-sub num">v1</span>
		</a>
		<nav class="topnav">
			<a href="#how">how</a>
			<a href="#what">what</a>
			<a href="#not">what it isn't</a>
			<a class="enter" href="/">enter →</a>
		</nav>
	</header>

	<section class="hero">
		<canvas bind:this={heroCanvas} class="hero-canvas"></canvas>
		<div class="hero-inner">
			<div class="eyebrow num">cot_lens v1 · positioning intelligence + news correlator</div>
			<h1 class="headline">
				<span class="hl-1">Commercial-hedger positioning,</span><br />
				<span class="hl-2">paired with the news that drove it.</span>
			</h1>
			<p class="sub">
				CFTC weekly disaggregated futures-only data + free macro news, on the same timeline.
				No buy/sell signals, no LLM commentary — the data, the news, and the trader's judgment.
			</p>
			<div class="cta-row">
				<a href="/" class="cta-primary">Open dashboard →</a>
				<a href="/heatmap" class="cta-ghost">Sector heatmap</a>
				<a href="/divergence" class="cta-ghost">Divergence scanner</a>
			</div>
		</div>
	</section>

	<section id="what" class="three-col">
		<div class="col">
			<div class="col-num num">01</div>
			<div class="col-title">Five attention lenses</div>
			<div class="col-body">
				Each market scored every CFTC release against five deterministic lenses:
				extreme positioning, price-vs-positioning divergence, sector outlier,
				momentum shift, hedger/speculator imbalance.
				<ul class="lens-list">
					{#each Object.entries(ZONE_NAMES) as [k, n]}
						<li>
							<span class="lk num" style:--c={`var(--zone-${k.toLowerCase()})`}>{k}</span>
							<span class="ln">{n}</span>
						</li>
					{/each}
				</ul>
			</div>
		</div>
		<div class="col">
			<div class="col-num num">02</div>
			<div class="col-title">Macro news on the same timeline</div>
			<div class="col-body">
				Yahoo Finance ticker news, USDA WASDE, EIA petroleum, FOMC, OPEC, FRED —
				pinned to the chart's date axis and tagged by market via a static
				keyword taxonomy. No NLP, no model interpretation; the trader sees the
				headline + source and supplies the meaning.
			</div>
		</div>
		<div class="col">
			<div class="col-num num">03</div>
			<div class="col-title">23 physical contracts</div>
			<div class="col-body">
				Grains, energy, metals, softs, meats. The Williams/Briese/Upperman
				framework is theoretically valid only on physicals — financials live in
				the CFTC's separate TFF report with different categories.
				Expansion deferred to v2.
			</div>
		</div>
	</section>

	{#if loaded && today.length}
		<section class="preview" id="how">
			<div class="preview-head">
				<div class="ph-eye num">live · today</div>
				<div class="ph-title">What the dashboard is showing right now</div>
				<a href="/" class="ph-link">full attention list →</a>
			</div>
			<div class="preview-cards">
				{#each today as r, i}
					<a class="pcard" href={`/market/${r.symbol}`} data-heat={r.n_zones >= 3 ? 'high' : r.n_zones >= 1 ? 'mid' : 'low'}>
						<div class="pc-rank num">#{i + 1}</div>
						<div class="pc-sym num">{r.symbol}</div>
						<div class="pc-name">{r.name}</div>
						<div class="pc-zones">
							{#each r.zones_on as z}
								<span class="pc-z num" style:--c={`var(--zone-${z.toLowerCase()})`}>{z}</span>
							{/each}
							{#if r.zones_on.length === 0}
								<span class="pc-empty">—</span>
							{/if}
						</div>
					</a>
				{/each}
			</div>
		</section>
	{/if}

	<section id="not" class="not-list">
		<div class="not-title">What this isn't</div>
		<ul>
			<li>Not a signal service. No backtest. No promised returns.</li>
			<li>Not an LLM commentary product. Every word you read is data or a primary source.</li>
			<li>Not a database. CFTC.gov has the raw files for free.</li>
			<li>Not for Bloomberg subscribers — they already have these screens.</li>
			<li>Not real-time. Daily refresh; news on its own cadence.</li>
		</ul>
	</section>

	<footer class="foot">
		<div class="foot-l num">
			built in public · zero vendor spend · open-source data only
		</div>
		<div class="foot-r num">
			<a href="/">/today</a>
			<a href="/market/HG">/market/HG</a>
			<a href="/heatmap">/heatmap</a>
			<a href="/divergence">/divergence</a>
		</div>
	</footer>
</div>

<style>
	.page {
		max-width: 1200px;
		margin: 0 auto;
		padding: 0 var(--sp-6);
	}

	/* ── topbar ─────────────────────────────────────────────── */
	.topbar {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: var(--sp-6) 0;
	}
	.brand-link {
		display: flex;
		align-items: center;
		gap: var(--sp-2);
	}
	.brand-dot {
		width: 10px;
		height: 10px;
		border-radius: 3px;
		background: var(--attn-high);
		box-shadow: 0 0 16px rgba(183, 148, 246, 0.6);
	}
	.brand {
		font-weight: 600;
		font-size: var(--fs-14);
		letter-spacing: 0.06em;
	}
	.brand-sub {
		color: var(--ink-faint);
		font-size: var(--fs-11);
	}
	.topnav {
		display: flex;
		align-items: center;
		gap: var(--sp-6);
	}
	.topnav a {
		font-size: var(--fs-12);
		color: var(--ink-muted);
		transition: color 0.15s;
	}
	.topnav a:hover {
		color: var(--ink);
	}
	.topnav .enter {
		padding: 6px 14px;
		border: 1px solid color-mix(in srgb, var(--attn-high) 50%, transparent);
		border-radius: 6px;
		color: var(--ink);
	}
	.topnav .enter:hover {
		background: color-mix(in srgb, var(--attn-high) 14%, transparent);
	}

	/* ── hero ───────────────────────────────────────────────── */
	.hero {
		position: relative;
		min-height: 420px;
		margin: var(--sp-6) 0 var(--sp-12);
		border: 1px solid var(--border-soft);
		border-radius: var(--r-lg);
		overflow: hidden;
		background: var(--bg-panel);
	}
	.hero-canvas {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		opacity: 0.9;
	}
	.hero-inner {
		position: relative;
		padding: var(--sp-12) var(--sp-12) var(--sp-8);
		max-width: 720px;
	}
	.eyebrow {
		font-size: var(--fs-11);
		color: var(--attn-high);
		text-transform: uppercase;
		letter-spacing: 0.12em;
	}
	.headline {
		font-size: clamp(2rem, 5vw, 3.4rem);
		line-height: 1.05;
		letter-spacing: -0.02em;
		margin: var(--sp-3) 0 var(--sp-4);
		font-weight: 600;
	}
	.hl-1 {
		color: var(--ink);
	}
	.hl-2 {
		background: linear-gradient(120deg, var(--attn-high), var(--zone-a3));
		-webkit-background-clip: text;
		background-clip: text;
		color: transparent;
	}
	.sub {
		font-size: var(--fs-16);
		color: var(--ink-muted);
		line-height: 1.55;
		max-width: 56ch;
		margin: 0 0 var(--sp-6);
	}
	.cta-row {
		display: flex;
		gap: var(--sp-3);
		flex-wrap: wrap;
	}
	.cta-primary {
		padding: 10px 18px;
		background: var(--attn-high);
		color: #0a0a0b;
		font-weight: 600;
		font-size: var(--fs-13);
		border-radius: 8px;
		transition: transform 0.15s, box-shadow 0.15s;
		letter-spacing: 0.02em;
	}
	.cta-primary:hover {
		transform: translateY(-1px);
		box-shadow: 0 12px 32px rgba(183, 148, 246, 0.35);
	}
	.cta-ghost {
		padding: 10px 14px;
		border: 1px solid var(--border);
		border-radius: 8px;
		color: var(--ink-muted);
		font-size: var(--fs-13);
		transition: color 0.15s, border-color 0.15s;
	}
	.cta-ghost:hover {
		color: var(--ink);
		border-color: var(--ink-muted);
	}

	/* ── three-col features ─────────────────────────────────── */
	.three-col {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		gap: var(--sp-6);
		margin-bottom: var(--sp-12);
	}
	.col {
		padding: var(--sp-6);
		background: var(--bg-panel);
		border: 1px solid var(--border-soft);
		border-radius: var(--r-md);
	}
	.col-num {
		color: var(--ink-faint);
		font-size: var(--fs-11);
		letter-spacing: 0.1em;
	}
	.col-title {
		font-size: var(--fs-20);
		font-weight: 500;
		margin: var(--sp-2) 0 var(--sp-3);
		letter-spacing: -0.01em;
	}
	.col-body {
		font-size: var(--fs-13);
		color: var(--ink-muted);
		line-height: 1.55;
	}
	.lens-list {
		list-style: none;
		padding: 0;
		margin: var(--sp-3) 0 0;
		display: grid;
		gap: 4px;
	}
	.lens-list li {
		display: grid;
		grid-template-columns: 24px 1fr;
		gap: var(--sp-2);
		align-items: baseline;
		font-size: var(--fs-12);
	}
	.lk {
		color: var(--c);
		font-weight: 600;
	}
	.ln {
		color: var(--ink);
	}

	/* ── live preview ───────────────────────────────────────── */
	.preview {
		margin-bottom: var(--sp-12);
		padding: var(--sp-6);
		background: var(--bg-panel);
		border: 1px solid var(--border-soft);
		border-radius: var(--r-md);
	}
	.preview-head {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		gap: var(--sp-3);
		margin-bottom: var(--sp-4);
		flex-wrap: wrap;
	}
	.ph-eye {
		color: var(--attn-high);
		font-size: var(--fs-11);
		text-transform: uppercase;
		letter-spacing: 0.12em;
	}
	.ph-title {
		flex: 1;
		font-size: var(--fs-16);
		color: var(--ink);
	}
	.ph-link {
		color: var(--ink-muted);
		font-size: var(--fs-12);
	}
	.ph-link:hover {
		color: var(--ink);
	}
	.preview-cards {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
		gap: var(--sp-3);
	}
	.pcard {
		display: grid;
		grid-template-rows: auto auto auto auto;
		gap: 4px;
		padding: var(--sp-3);
		background: var(--bg-panel-2);
		border: 1px solid var(--border-soft);
		border-radius: var(--r-sm);
		color: var(--ink);
		transition: transform 0.18s, border-color 0.18s;
	}
	.pcard:hover {
		transform: translateY(-2px);
		border-color: var(--border);
	}
	.pcard[data-heat='high'] {
		border-left: 2px solid var(--attn-high);
	}
	.pcard[data-heat='mid'] {
		border-left: 2px solid var(--attn-mid);
	}
	.pcard[data-heat='low'] {
		border-left: 2px solid var(--attn-low);
	}
	.pc-rank {
		font-size: var(--fs-11);
		color: var(--ink-faint);
	}
	.pc-sym {
		font-size: var(--fs-20);
		font-weight: 600;
	}
	.pc-name {
		font-size: var(--fs-12);
		color: var(--ink-muted);
	}
	.pc-zones {
		display: flex;
		gap: 4px;
		margin-top: 4px;
		flex-wrap: wrap;
	}
	.pc-z {
		font-size: 10px;
		padding: 1px 5px;
		border-radius: 3px;
		color: var(--c);
		background: color-mix(in srgb, var(--c) 18%, transparent);
		border: 1px solid color-mix(in srgb, var(--c) 40%, transparent);
	}
	.pc-empty {
		color: var(--ink-faint);
		font-size: 10px;
	}

	/* ── what-it-isnt ───────────────────────────────────────── */
	.not-list {
		margin-bottom: var(--sp-12);
	}
	.not-title {
		font-size: var(--fs-11);
		text-transform: uppercase;
		letter-spacing: 0.12em;
		color: var(--attn-high);
		margin-bottom: var(--sp-3);
	}
	.not-list ul {
		list-style: none;
		padding: 0;
		margin: 0;
		display: grid;
		gap: 4px;
		font-size: var(--fs-14);
		color: var(--ink-muted);
	}
	.not-list li {
		padding: var(--sp-2) var(--sp-3);
		background: var(--bg-panel);
		border-left: 2px solid var(--ink-faint);
		border-radius: 0 var(--r-sm) var(--r-sm) 0;
	}

	/* ── footer ─────────────────────────────────────────────── */
	.foot {
		padding: var(--sp-6) 0 var(--sp-12);
		display: flex;
		justify-content: space-between;
		align-items: center;
		border-top: 1px solid var(--border-soft);
		flex-wrap: wrap;
		gap: var(--sp-3);
	}
	.foot-l {
		font-size: var(--fs-11);
		color: var(--ink-faint);
		letter-spacing: 0.04em;
	}
	.foot-r {
		display: flex;
		gap: var(--sp-4);
		font-size: var(--fs-11);
	}
	.foot-r a {
		color: var(--ink-muted);
	}
	.foot-r a:hover {
		color: var(--ink);
	}

	/* ── responsive ────────────────────────────────────────── */
	@media (max-width: 760px) {
		.three-col {
			grid-template-columns: 1fr;
		}
		.hero-inner {
			padding: var(--sp-8) var(--sp-6) var(--sp-6);
		}
		.topnav {
			gap: var(--sp-3);
		}
		.topnav a:not(.enter) {
			display: none;
		}
	}
</style>
