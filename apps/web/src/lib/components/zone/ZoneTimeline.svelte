<script lang="ts">
	import type { BarRow, ZoneKey } from '$api/types';
	import { ZONE_NAMES } from '$api/types';

	interface Props {
		bars: BarRow[];
		height?: number;
	}

	let { bars, height = 90 }: Props = $props();

	const zones: ZoneKey[] = ['A1', 'A2', 'A3', 'A4', 'A5'];

	// Per-lens density: count active bars per zone + last-active date.
	const summary = $derived.by(() => {
		const out: Record<ZoneKey, { count: number; lastDate: string | null; lastIdx: number }> = {
			A1: { count: 0, lastDate: null, lastIdx: -1 },
			A2: { count: 0, lastDate: null, lastIdx: -1 },
			A3: { count: 0, lastDate: null, lastIdx: -1 },
			A4: { count: 0, lastDate: null, lastIdx: -1 },
			A5: { count: 0, lastDate: null, lastIdx: -1 }
		};
		for (let i = 0; i < bars.length; i++) {
			const b = bars[i];
			for (const z of zones) {
				if (b[z]) {
					out[z].count++;
					out[z].lastDate = b.date;
					out[z].lastIdx = i;
				}
			}
		}
		return out;
	});

	// Build a tiny per-zone strip showing every active bar as a tick.
	// Render width = 100%, ticks positioned by bar index.
	function strip(zone: ZoneKey, width: number): { x: number; height: number }[] {
		if (!bars.length || !width) return [];
		const ticks: { x: number; height: number }[] = [];
		for (let i = 0; i < bars.length; i++) {
			if (bars[i][zone]) {
				ticks.push({
					x: (i / Math.max(1, bars.length - 1)) * width,
					height: 100
				});
			}
		}
		return ticks;
	}

	const STRIP_W = 480; // logical width, scales via SVG viewBox

	function ago(date: string | null): string {
		if (!date) return 'never';
		const then = new Date(date).getTime();
		const now = Date.now();
		const days = Math.floor((now - then) / 86_400_000);
		if (days <= 0) return 'today';
		if (days === 1) return 'yesterday';
		if (days < 30) return `${days}d ago`;
		if (days < 365) return `${Math.floor(days / 30)}mo ago`;
		return `${Math.floor(days / 365)}y ago`;
	}
</script>

<div class="timeline" style:height={`${height}px`}>
	<div class="t-head">
		<span class="t-title">Zone activations · history</span>
		<span class="t-sub num">{bars.length} bars</span>
	</div>
	<div class="t-grid">
		{#each zones as z}
			{@const s = summary[z]}
			{@const ticks = strip(z, STRIP_W)}
			<div class="row" style:--c={`var(--zone-${z.toLowerCase()})`}>
				<div class="label">
					<span class="key num">{z}</span>
					<span class="name">{ZONE_NAMES[z]}</span>
				</div>
				<svg
					class="strip"
					viewBox={`0 0 ${STRIP_W} 14`}
					preserveAspectRatio="none"
					aria-hidden="true"
				>
					<rect x="0" y="6" width={STRIP_W} height="2" fill="var(--border-soft)" />
					{#each ticks as t}
						<rect x={t.x} y="0" width="1.5" height="14" fill="var(--c)" opacity="0.85" />
					{/each}
				</svg>
				<div class="meta num">{s.count} · {ago(s.lastDate)}</div>
			</div>
		{/each}
	</div>
</div>

<style>
	.timeline {
		background: var(--bg-panel);
		border: 1px solid var(--border-soft);
		border-radius: var(--r-md);
		padding: var(--sp-3) var(--sp-4);
		display: flex;
		flex-direction: column;
		gap: var(--sp-2);
	}
	.t-head {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
	}
	.t-title {
		font-size: var(--fs-11);
		color: var(--ink-muted);
		text-transform: uppercase;
		letter-spacing: 0.1em;
	}
	.t-sub {
		font-size: var(--fs-11);
		color: var(--ink-faint);
	}

	.t-grid {
		display: grid;
		grid-template-columns: 1fr;
		gap: 4px;
	}
	.row {
		display: grid;
		grid-template-columns: 130px 1fr 100px;
		align-items: center;
		gap: var(--sp-3);
	}
	.label {
		display: flex;
		gap: 6px;
		align-items: baseline;
	}
	.key {
		color: var(--c);
		font-size: var(--fs-11);
		font-weight: 600;
		width: 18px;
	}
	.name {
		font-size: var(--fs-11);
		color: var(--ink-muted);
	}
	.strip {
		width: 100%;
		height: 14px;
		display: block;
	}
	.meta {
		font-size: var(--fs-11);
		color: var(--ink-faint);
		text-align: right;
	}
</style>
