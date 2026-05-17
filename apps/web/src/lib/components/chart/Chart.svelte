<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { onRender } from '$engine/scheduler';
	import { createSpring } from '$engine/sim/spring';
	import { newsReader } from '$state/newsReader.svelte';
	import { tryCreateCandleLayer, type CandleLayer } from '$engine/render/webgl/candles';
	import type { BarRow, NewsItem } from '$api/types';
	// 4-canvas stack (z-order, bottom → top):
	//   1. base    — pane backgrounds, grid, axes, labels, date ticks
	//   2. webgl   — candles via WebGL2 (transparent clear, Canvas2D fallback)
	//   3. lines   — 18-SMA, net commercial area+line, COT line, zone dots, news pins
	//   4. overlay — crosshair, axis labels, bar outline
	// Base + webgl are dirty-redrawn only when view/data/size changes; lines is
	// always redrawn alongside base (cheap); overlay redraws every frame.

	interface Props {
		bars: BarRow[];
		news?: NewsItem[];
		height?: number;
	}

	let { bars, news = [], height = 580 }: Props = $props();

	// ── Refs ────────────────────────────────────────────────────────────────
	let wrap: HTMLDivElement;
	let base: HTMLCanvasElement;
	let webgl: HTMLCanvasElement;
	let lines: HTMLCanvasElement;
	let overlay: HTMLCanvasElement;
	let width = $state(900);

	// WebGL candle renderer — initialized on mount; null when WebGL2 is unavailable.
	let candleLayer: CandleLayer | null = null;
	let usingWebGL = $state(false);
	// Bars uploaded to the GPU; we re-upload only when the bars reference changes.
	let candlesUploadedFor: BarRow[] | null = null;

	// ── View state (the visible bar window) ─────────────────────────────────
	// Springs animate zoom/pan; consumer code reads spring.value each render.
	const viewStart = createSpring(0, { stiffness: 220, damping: 28 });
	const viewEnd = createSpring(1, { stiffness: 220, damping: 28 });

	const MIN_BARS = 20;

	// ── Pointer / interaction state ────────────────────────────────────────
	let mouseX = $state(-1);
	let mouseY = $state(-1);
	let inside = $state(false);
	let panning = false;
	let panStartX = 0;
	let panStartViewStart = 0;
	let panStartViewEnd = 0;
	let hoverPin = $state<NewsItem | null>(null);
	let hoverPinX = $state(0);
	let hoverPinY = $state(0);
	let hoverBarIdx = $state<number | null>(null);

	// ── Geometry constants ─────────────────────────────────────────────────
	const PRICE_FRAC = 0.62;
	const NETPOS_FRAC = 0.2;
	const COT_FRAC = 0.18;
	const PAD_L = 60;
	const PAD_R = 64; // room for right-side COT axis label
	const HUD_H = 28; // top HUD ribbon height (always visible, never overlaps candles)
	const PAD_T = HUD_H + 4;
	const PAD_B = 28;
	const NEWS_AXIS_OFFSET = 8;

	// View-derived geometry (read from springs each frame)
	// Each non-price pane is inset by PANE_GAP so the dark canvas gutter shows
	// through between panes — gives clear visual separation without a heavy rule.
	const PANE_GAP = 4;
	function paneRects(h: number, w: number) {
		const innerH = h - PAD_T - PAD_B;
		const ph = Math.floor(innerH * PRICE_FRAC);
		const nh = Math.floor(innerH * NETPOS_FRAC);
		const ch = innerH - ph - nh;
		const x = PAD_L;
		const width = w - PAD_L - PAD_R;
		return {
			price: { x, y: PAD_T, w: width, h: ph - Math.floor(PANE_GAP / 2) },
			netpos: {
				x,
				y: PAD_T + ph + Math.floor(PANE_GAP / 2),
				w: width,
				h: nh - PANE_GAP
			},
			cot: {
				x,
				y: PAD_T + ph + nh + Math.floor(PANE_GAP / 2),
				w: width,
				h: ch - Math.floor(PANE_GAP / 2)
			}
		};
	}

	function cssVar(name: string): string {
		return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
	}

	// ── Cached state between renders ───────────────────────────────────────
	let baseDirty = true;
	let lastViewStart = -1;
	let lastViewEnd = -1;
	let lastWidth = 0;
	let lastBarsRef: BarRow[] | null = null;
	let priceLoCache = 0;
	let priceSpanCache = 1;
	let netLoCache = 0;
	let netSpanCache = 1;
	let visibleBarsCache: BarRow[] = [];
	let visibleNewsCache: { it: NewsItem; barIdx: number }[] = [];

	// ── Resize ─────────────────────────────────────────────────────────────
	function resize() {
		if (!wrap) return;
		width = wrap.clientWidth;
		baseDirty = true;
	}

	// ── Reset view (called on init + data change + double-click) ───────────
	function resetView() {
		viewStart.jump(0);
		viewEnd.jump(bars.length);
		baseDirty = true;
	}

	// ── Math helpers ───────────────────────────────────────────────────────
	function clampView(start: number, end: number): [number, number] {
		const n = bars.length;
		let span = Math.max(MIN_BARS, end - start);
		// Clamp span to data range
		if (span > n) span = n;
		// Clamp start to [0, n - span]
		let s = Math.max(0, Math.min(n - span, start));
		let e = s + span;
		return [s, e];
	}

	function setView(start: number, end: number, animate = true) {
		const [s, e] = clampView(start, end);
		if (animate) {
			viewStart.set(s);
			viewEnd.set(e);
		} else {
			viewStart.jump(s);
			viewEnd.jump(e);
		}
		baseDirty = true;
	}

	// ── Wheel: zoom around cursor (with shift => horizontal pan) ──────────
	function onWheel(ev: WheelEvent) {
		ev.preventDefault();
		const r = base.getBoundingClientRect();
		const px = ev.clientX - r.left;
		const rects = paneRects(height, width);
		const inChart = px >= rects.price.x && px <= rects.price.x + rects.price.w;
		if (!inChart) return;

		const startNow = viewStart.value;
		const endNow = viewEnd.value;
		const span = endNow - startNow;

		// Trackpad pinch-zoom emits ctrlKey on wheel.
		const isZoom = !ev.shiftKey;

		if (isZoom) {
			const zoomFactor = ev.deltaY > 0 ? 1.15 : 1 / 1.15;
			const cursorFrac = (px - rects.price.x) / rects.price.w;
			const cursorBar = startNow + cursorFrac * span;
			const newSpan = Math.max(MIN_BARS, Math.min(bars.length, span * zoomFactor));
			const newStart = cursorBar - cursorFrac * newSpan;
			setView(newStart, newStart + newSpan);
		} else {
			// Horizontal pan via shift+wheel
			const dx = (ev.deltaY + ev.deltaX) * (span / rects.price.w);
			setView(startNow + dx, endNow + dx);
		}
	}

	// ── Pointer: hover + click+drag pan + news pin hit ─────────────────────
	function onPointerDown(ev: PointerEvent) {
		// If user is clicking a news pin, open it in-app instead of starting a pan.
		// Cmd/Ctrl-click escapes to a new tab for the original page.
		if (hoverPin && hoverPin.url) {
			if (ev.metaKey || ev.ctrlKey) {
				window.open(hoverPin.url, '_blank', 'noopener');
			} else {
				newsReader.openItem(hoverPin);
			}
			return;
		}
		(ev.target as Element).setPointerCapture(ev.pointerId);
		panning = true;
		panStartX = ev.clientX;
		panStartViewStart = viewStart.value;
		panStartViewEnd = viewEnd.value;
		overlay.style.cursor = 'grabbing';
	}

	function onPointerUp(ev: PointerEvent) {
		(ev.target as Element).releasePointerCapture?.(ev.pointerId);
		panning = false;
		overlay.style.cursor = '';
	}

	function onPointerMove(ev: PointerEvent) {
		const r = base.getBoundingClientRect();
		mouseX = ev.clientX - r.left;
		mouseY = ev.clientY - r.top;
		inside = true;

		if (panning) {
			const rects = paneRects(height, width);
			const span = panStartViewEnd - panStartViewStart;
			const dxPx = ev.clientX - panStartX;
			const dxBars = -(dxPx / rects.price.w) * span;
			setView(panStartViewStart + dxBars, panStartViewEnd + dxBars, false);
			return;
		}

		// Hover hit-test
		recomputeHover();
	}

	function onPointerLeave() {
		inside = false;
		hoverPin = null;
		hoverBarIdx = null;
	}

	function onDoubleClick() {
		resetView();
	}

	function recomputeHover() {
		const rects = paneRects(height, width);
		const start = viewStart.value;
		const end = viewEnd.value;
		const span = end - start;
		const stepX = rects.price.w / span;

		// Bar index under cursor (only count if inside chart)
		if (mouseX >= rects.price.x && mouseX <= rects.price.x + rects.price.w) {
			const rel = (mouseX - rects.price.x) / stepX;
			const idx = Math.max(0, Math.min(bars.length - 1, Math.round(start + rel - 0.5)));
			hoverBarIdx = idx;
		} else {
			hoverBarIdx = null;
		}

		// News pin hit-test (axisY)
		const axisY = height - PAD_B + NEWS_AXIS_OFFSET;
		let nearest: { it: NewsItem; barIdx: number; dist: number } | null = null;
		for (const v of visibleNewsCache) {
			const x = rects.price.x + (v.barIdx - start) * stepX + stepX / 2;
			const dx = Math.abs(x - mouseX);
			const dy = Math.abs(mouseY - axisY - 3);
			if (dx < 8 && dy < 10 && (!nearest || dx + dy < nearest.dist)) {
				nearest = { it: v.it, barIdx: v.barIdx, dist: dx + dy };
			}
		}
		if (nearest) {
			hoverPin = nearest.it;
			hoverPinX = rects.price.x + (nearest.barIdx - start) * stepX + stepX / 2;
			hoverPinY = axisY;
			overlay.style.cursor = 'pointer';
		} else {
			hoverPin = null;
			if (!panning) overlay.style.cursor = 'crosshair';
		}
	}

	// ── Keyboard nav ───────────────────────────────────────────────────────
	function onKey(ev: KeyboardEvent) {
		if (!inside) return;
		const start = viewStart.value;
		const end = viewEnd.value;
		const span = end - start;
		const stepBars = Math.max(1, Math.round(span * 0.05));
		switch (ev.key) {
			case 'ArrowLeft':
				ev.preventDefault();
				setView(start - stepBars, end - stepBars);
				break;
			case 'ArrowRight':
				ev.preventDefault();
				setView(start + stepBars, end + stepBars);
				break;
			case '+':
			case '=':
				ev.preventDefault();
				setView(start + span * 0.1, end - span * 0.1);
				break;
			case '-':
			case '_':
				ev.preventDefault();
				setView(start - span * 0.1, end + span * 0.1);
				break;
			case 'Escape':
				ev.preventDefault();
				resetView();
				break;
		}
	}

	// Parse a CSS hex color to a [r, g, b] tuple in 0..1 — used to pass colors
	// into the WebGL candle shader.
	function hexToRgb(hex: string): [number, number, number] {
		const h = hex.trim().replace('#', '');
		const v = h.length === 3 ? h.split('').map((c) => c + c).join('') : h;
		const n = parseInt(v.slice(0, 6) || '888888', 16);
		return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
	}

	function resizeCanvases(W: number, H: number, dpr: number): void {
		for (const c of [base, webgl, lines, overlay]) {
			if (!c) continue;
			if (c.width !== W * dpr || c.height !== H * dpr) {
				c.width = W * dpr;
				c.height = H * dpr;
				c.style.width = `${W}px`;
				c.style.height = `${H}px`;
			}
		}
		// WebGL viewport tracks the device-pixel size of its canvas.
		if (candleLayer && webgl) candleLayer.resize(W, H, dpr);
	}

	// ── Base render: backgrounds, grid, axes, labels, date ticks ──────────
	// Also dispatches to the WebGL/Canvas2D candle layer and the lines canvas.
	// Name kept as `drawBase` because the render loop drives it via `baseDirty`.
	function drawBase() {
		if (!base) return;
		const dpr = window.devicePixelRatio || 1;
		const W = width;
		const H = height;

		resizeCanvases(W, H, dpr);

		const ctx = base.getContext('2d')!;
		ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
		ctx.clearRect(0, 0, W, H);

		const linesCtx = lines.getContext('2d')!;
		linesCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
		linesCtx.clearRect(0, 0, W, H);

		// Clear WebGL (transparent) so the previous frame's candles don't ghost.
		if (candleLayer) candleLayer.clear();

		if (!bars.length) return;

		const ink = cssVar('--ink');
		const inkFaint = cssVar('--ink-faint');
		const inkMuted = cssVar('--ink-muted');
		const rule = cssVar('--rule');
		const long = cssVar('--long');
		const short = cssVar('--short');
		const sma = cssVar('--pending');
		const a1 = cssVar('--zone-a1');
		const a2 = cssVar('--zone-a2');
		const a3 = cssVar('--zone-a3');
		const a4 = cssVar('--zone-a4');
		const a5 = cssVar('--zone-a5');
		const zoneColors: Record<string, string> = { A1: a1, A2: a2, A3: a3, A4: a4, A5: a5 };
		const monoFont = `11px ${cssVar('--font-mono') || 'monospace'}`;

		const rects = paneRects(H, W);
		const start = viewStart.value;
		const end = viewEnd.value;
		const startInt = Math.max(0, Math.floor(start));
		const endInt = Math.min(bars.length, Math.ceil(end));
		const span = end - start;
		const stepX = rects.price.w / span;

		// Cache visible bars + visible news for hover hit-testing
		visibleBarsCache = bars.slice(startInt, endInt);

		// Visible news: pin index = closest bar index
		visibleNewsCache = [];
		for (const it of news) {
			const d = it.date.slice(0, 10);
			let lo = 0;
			let hi = bars.length - 1;
			while (lo < hi) {
				const mid = (lo + hi) >> 1;
				if (bars[mid].date < d) lo = mid + 1;
				else hi = mid;
			}
			const idx = lo;
			if (idx >= startInt && idx < endInt) visibleNewsCache.push({ it, barIdx: idx });
		}

		// Compute price extents over visible window
		let lo = Infinity;
		let hi = -Infinity;
		for (let i = startInt; i < endInt; i++) {
			const b = bars[i];
			if (b.low != null && b.low < lo) lo = b.low;
			if (b.high != null && b.high > hi) hi = b.high;
			if (b.sma_slow != null) {
				if (b.sma_slow < lo) lo = b.sma_slow;
				if (b.sma_slow > hi) hi = b.sma_slow;
			}
		}
		if (!isFinite(lo)) {
			lo = 0;
			hi = 1;
		}
		const pad = (hi - lo) * 0.05 || 1;
		lo -= pad;
		hi += pad;
		priceLoCache = lo;
		priceSpanCache = hi - lo;

		const px = (i: number) => rects.price.x + (i - start) * stepX + stepX / 2;
		const py = (v: number) => rects.price.y + rects.price.h - ((v - lo) / priceSpanCache) * rects.price.h;

		// Net commercial extents — force zero into the visible range so the
		// baseline projects inside the pane (otherwise the area fill leaks
		// into adjacent panes when all visible values are same-signed).
		let nlo = Infinity;
		let nhi = -Infinity;
		for (let i = startInt; i < endInt; i++) {
			const v = bars[i].net_commercials;
			if (v == null) continue;
			if (v < nlo) nlo = v;
			if (v > nhi) nhi = v;
		}
		if (!isFinite(nlo)) {
			nlo = -1;
			nhi = 1;
		}
		nlo = Math.min(0, nlo);
		nhi = Math.max(0, nhi);
		const nPad = (nhi - nlo) * 0.08 || 1;
		nlo -= nPad;
		nhi += nPad;
		netLoCache = nlo;
		netSpanCache = nhi - nlo;
		const ny = (v: number) => rects.netpos.y + rects.netpos.h - ((v - nlo) / netSpanCache) * rects.netpos.h;

		const cy = (v: number) => rects.cot.y + rects.cot.h - (v / 100) * rects.cot.h;

		// ── Pane backgrounds ───────────────────────────────────────────────
		ctx.fillStyle = cssVar('--bg-panel-2');
		for (const r of [rects.price, rects.netpos, rects.cot]) ctx.fillRect(r.x, r.y, r.w, r.h);

		// ── Horizontal grid (price pane) ───────────────────────────────────
		ctx.strokeStyle = rule;
		ctx.lineWidth = 1;
		ctx.fillStyle = inkFaint;
		ctx.font = monoFont;
		ctx.textAlign = 'right';
		ctx.textBaseline = 'middle';
		const priceTicks = 5;
		for (let i = 0; i <= priceTicks; i++) {
			const v = lo + (priceSpanCache * i) / priceTicks;
			const y = py(v);
			ctx.beginPath();
			ctx.moveTo(rects.price.x, y + 0.5);
			ctx.lineTo(rects.price.x + rects.price.w, y + 0.5);
			ctx.stroke();
			ctx.fillText(v.toFixed(v > 100 ? 0 : 2), rects.price.x - 6, y);
		}

		// COT pane reference lines (80/20)
		ctx.strokeStyle = `color-mix(in srgb, ${a1} 35%, transparent)`;
		ctx.setLineDash([3, 4]);
		ctx.beginPath();
		ctx.moveTo(rects.cot.x, cy(80));
		ctx.lineTo(rects.cot.x + rects.cot.w, cy(80));
		ctx.moveTo(rects.cot.x, cy(20));
		ctx.lineTo(rects.cot.x + rects.cot.w, cy(20));
		ctx.stroke();
		ctx.setLineDash([]);
		ctx.fillStyle = inkFaint;
		ctx.textAlign = 'right';
		ctx.fillText('80', rects.cot.x - 6, cy(80));
		ctx.fillText('20', rects.cot.x - 6, cy(20));
		ctx.textAlign = 'left';
		ctx.fillText('COT', rects.cot.x + rects.cot.w + 6, cy(50));

		// Net commercial pane: zero line + label
		const zeroY = ny(0);
		ctx.strokeStyle = `color-mix(in srgb, ${ink} 20%, transparent)`;
		ctx.beginPath();
		ctx.moveTo(rects.netpos.x, zeroY + 0.5);
		ctx.lineTo(rects.netpos.x + rects.netpos.w, zeroY + 0.5);
		ctx.stroke();
		ctx.fillStyle = inkMuted;
		ctx.textAlign = 'right';
		ctx.fillText('NET', rects.netpos.x - 6, rects.netpos.y + rects.netpos.h / 2);

		// ── Candles: WebGL2 if available, Canvas2D fallback ─────────────
		if (candleLayer && usingWebGL) {
			// Upload bars to GPU only when the reference changes.
			if (candlesUploadedFor !== bars) {
				candleLayer.setBars(
					bars.map((b) => ({
						open: b.open ?? 0,
						high: b.high ?? 0,
						low: b.low ?? 0,
						close: b.close ?? 0
					}))
				);
				candlesUploadedFor = bars;
			}
			const colorUp = hexToRgb(long);
			const colorDown = hexToRgb(short);
			candleLayer.draw(
				{
					viewStart: start,
					viewEnd: end,
					priceLo: lo,
					priceHi: hi,
					rect: rects.price,
					canvas: { w: W, h: H },
					barPx: Math.max(1, stepX * 0.7)
				},
				colorUp,
				colorDown
			);
		} else {
			// Canvas2D fallback path — draws on the lines canvas, clipped.
			linesCtx.save();
			linesCtx.beginPath();
			linesCtx.rect(rects.price.x, rects.price.y, rects.price.w, rects.price.h);
			linesCtx.clip();
			const cw = Math.max(1, stepX * 0.7);
			for (let i = startInt; i < endInt; i++) {
				const b = bars[i];
				if (b.open == null || b.close == null || b.high == null || b.low == null) continue;
				const x = px(i);
				const up = b.close >= b.open;
				const color = up ? long : short;
				linesCtx.strokeStyle = color;
				linesCtx.fillStyle = color;
				linesCtx.beginPath();
				linesCtx.moveTo(Math.floor(x) + 0.5, py(b.high));
				linesCtx.lineTo(Math.floor(x) + 0.5, py(b.low));
				linesCtx.stroke();
				const y0 = py(b.open);
				const y1 = py(b.close);
				const top = Math.min(y0, y1);
				const bh = Math.max(1, Math.abs(y1 - y0));
				linesCtx.fillRect(
					Math.floor(x - cw / 2),
					Math.floor(top),
					Math.max(1, Math.floor(cw)),
					bh
				);
			}
			linesCtx.restore();
		}

		// ── 18-SMA on lines canvas (always on top of candles) ───────────
		let drawn = false;
		linesCtx.save();
		linesCtx.beginPath();
		linesCtx.rect(rects.price.x, rects.price.y, rects.price.w, rects.price.h);
		linesCtx.clip();
		linesCtx.strokeStyle = sma;
		linesCtx.lineWidth = 1.25;
		linesCtx.beginPath();
		for (let i = startInt; i < endInt; i++) {
			const v = bars[i].sma_slow;
			if (v == null) continue;
			if (!drawn) {
				linesCtx.moveTo(px(i), py(v));
				drawn = true;
			} else linesCtx.lineTo(px(i), py(v));
		}
		linesCtx.stroke();
		linesCtx.restore();

		// ── Net commercial area (clipped to the netpos pane) ────────────
		linesCtx.save();
		linesCtx.beginPath();
		linesCtx.rect(rects.netpos.x, rects.netpos.y, rects.netpos.w, rects.netpos.h);
		linesCtx.clip();

		linesCtx.beginPath();
		linesCtx.moveTo(px(startInt), zeroY);
		let started = false;
		for (let i = startInt; i < endInt; i++) {
			const v = bars[i].net_commercials;
			if (v == null) continue;
			if (!started) {
				linesCtx.lineTo(px(i), zeroY);
				started = true;
			}
			linesCtx.lineTo(px(i), ny(v));
		}
		linesCtx.lineTo(px(endInt - 1), zeroY);
		linesCtx.closePath();
		linesCtx.fillStyle = `color-mix(in srgb, ${inkMuted} 20%, transparent)`;
		linesCtx.fill();
		linesCtx.strokeStyle = inkMuted;
		linesCtx.lineWidth = 1;
		linesCtx.beginPath();
		drawn = false;
		for (let i = startInt; i < endInt; i++) {
			const v = bars[i].net_commercials;
			if (v == null) continue;
			if (!drawn) {
				linesCtx.moveTo(px(i), ny(v));
				drawn = true;
			} else linesCtx.lineTo(px(i), ny(v));
		}
		linesCtx.stroke();
		linesCtx.restore();

		// ── COT Index line (clipped to the cot pane) ────────────────────
		linesCtx.save();
		linesCtx.beginPath();
		linesCtx.rect(rects.cot.x, rects.cot.y, rects.cot.w, rects.cot.h);
		linesCtx.clip();
		linesCtx.strokeStyle = a3;
		linesCtx.lineWidth = 1.25;
		linesCtx.beginPath();
		drawn = false;
		for (let i = startInt; i < endInt; i++) {
			const v = bars[i].cot_index_comm;
			if (v == null) continue;
			if (!drawn) {
				linesCtx.moveTo(px(i), cy(v));
				drawn = true;
			} else linesCtx.lineTo(px(i), cy(v));
		}
		linesCtx.stroke();
		linesCtx.restore();

		// ── Zone marker dots (on lines canvas) ───────────────────────────
		const dotY = rects.price.y + 6;
		for (let i = startInt; i < endInt; i++) {
			const b = bars[i];
			const zones = (['A1', 'A2', 'A3', 'A4', 'A5'] as const).filter((z) => b[z]);
			if (!zones.length) continue;
			for (let j = 0; j < zones.length; j++) {
				linesCtx.fillStyle = zoneColors[zones[j]];
				linesCtx.beginPath();
				linesCtx.arc(px(i), dotY + j * 6, 2.2, 0, Math.PI * 2);
				linesCtx.fill();
			}
		}

		// ── News pins on date axis (lines canvas) ────────────────────────
		const axisY = H - PAD_B + NEWS_AXIS_OFFSET;
		for (const v of visibleNewsCache) {
			const x = rects.price.x + (v.barIdx - start) * stepX + stepX / 2;
			const cat = v.it.source_category;
			const pinColor = cssVar(
				`--zone-${cat === 'agency' ? 'a3' : cat === 'macro' ? 'a4' : cat === 'geopolitics' ? 'a2' : 'a1'}`
			);
			linesCtx.fillStyle = pinColor;
			linesCtx.beginPath();
			linesCtx.moveTo(x, axisY);
			linesCtx.lineTo(x - 3.5, axisY + 7);
			linesCtx.lineTo(x + 3.5, axisY + 7);
			linesCtx.closePath();
			linesCtx.fill();
		}

		// ── Date ticks ────────────────────────────────────────────────────
		ctx.fillStyle = inkFaint;
		ctx.textAlign = 'center';
		ctx.textBaseline = 'top';
		const ticks = 6;
		for (let i = 0; i <= ticks; i++) {
			const frac = i / ticks;
			const bIdx = Math.min(bars.length - 1, Math.round(start + frac * span));
			const xv = rects.price.x + frac * rects.price.w;
			const d = bars[bIdx].date.slice(0, 10);
			ctx.fillText(d, xv, H - PAD_B + 18);
		}

		baseDirty = false;
		lastViewStart = start;
		lastViewEnd = end;
		lastWidth = W;
		lastBarsRef = bars;
	}

	// ── Overlay render (crosshair + axis labels + zone halo on hovered bar)
	function drawOverlay() {
		if (!overlay) return;
		const dpr = window.devicePixelRatio || 1;
		const W = width;
		const H = height;
		const ctx = overlay.getContext('2d')!;
		ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
		ctx.clearRect(0, 0, W, H);
		if (!inside || hoverBarIdx == null || !bars.length) return;

		const rects = paneRects(H, W);
		const start = viewStart.value;
		const end = viewEnd.value;
		const span = end - start;
		const stepX = rects.price.w / span;
		const ink = cssVar('--ink');
		const inkMuted = cssVar('--ink-muted');
		const monoFont = `11px ${cssVar('--font-mono') || 'monospace'}`;

		const b = bars[hoverBarIdx];
		const x = rects.price.x + (hoverBarIdx - start) * stepX + stepX / 2;
		const inPrice = mouseY >= rects.price.y && mouseY <= rects.price.y + rects.price.h;
		const inNetpos = mouseY >= rects.netpos.y && mouseY <= rects.netpos.y + rects.netpos.h;
		const inCot = mouseY >= rects.cot.y && mouseY <= rects.cot.y + rects.cot.h;

		// Vertical crosshair
		ctx.strokeStyle = 'rgba(232,232,234,0.28)';
		ctx.lineWidth = 1;
		ctx.setLineDash([3, 3]);
		ctx.beginPath();
		ctx.moveTo(x + 0.5, rects.price.y);
		ctx.lineTo(x + 0.5, rects.cot.y + rects.cot.h);
		ctx.stroke();

		// Horizontal crosshair (only in the pane the cursor is in)
		if (inPrice || inNetpos || inCot) {
			ctx.beginPath();
			ctx.moveTo(rects.price.x, mouseY + 0.5);
			ctx.lineTo(rects.price.x + rects.price.w, mouseY + 0.5);
			ctx.stroke();
		}
		ctx.setLineDash([]);

		// Date label at bottom axis
		ctx.fillStyle = cssVar('--bg-canvas');
		const dateLabel = b.date.slice(0, 10);
		ctx.font = monoFont;
		ctx.textAlign = 'center';
		ctx.textBaseline = 'middle';
		const dateW = ctx.measureText(dateLabel).width + 12;
		const dateY = H - PAD_B + 18;
		ctx.fillStyle = cssVar('--bg-active');
		ctx.fillRect(x - dateW / 2, dateY - 8, dateW, 16);
		ctx.fillStyle = ink;
		ctx.fillText(dateLabel, x, dateY);

		// Left price label (price pane)
		if (inPrice && priceSpanCache > 0) {
			const v = priceLoCache + (1 - (mouseY - rects.price.y) / rects.price.h) * priceSpanCache;
			const text = v.toFixed(v > 100 ? 0 : 2);
			ctx.textAlign = 'right';
			const labelW = ctx.measureText(text).width + 12;
			ctx.fillStyle = cssVar('--bg-active');
			ctx.fillRect(rects.price.x - labelW - 2, mouseY - 8, labelW, 16);
			ctx.fillStyle = ink;
			ctx.fillText(text, rects.price.x - 8, mouseY);
		}

		// Left label for net pane
		if (inNetpos && netSpanCache > 0) {
			const v = netLoCache + (1 - (mouseY - rects.netpos.y) / rects.netpos.h) * netSpanCache;
			const text = (v / 1000).toFixed(0) + 'K';
			ctx.textAlign = 'right';
			const labelW = ctx.measureText(text).width + 12;
			ctx.fillStyle = cssVar('--bg-active');
			ctx.fillRect(rects.netpos.x - labelW - 2, mouseY - 8, labelW, 16);
			ctx.fillStyle = inkMuted;
			ctx.fillText(text, rects.netpos.x - 8, mouseY);
		}

		// Right COT label
		if (inCot) {
			const v = (1 - (mouseY - rects.cot.y) / rects.cot.h) * 100;
			const text = v.toFixed(0);
			ctx.textAlign = 'left';
			const labelW = ctx.measureText(text).width + 12;
			ctx.fillStyle = cssVar('--bg-active');
			ctx.fillRect(rects.cot.x + rects.cot.w + 2, mouseY - 8, labelW, 16);
			ctx.fillStyle = cssVar('--zone-a3');
			ctx.fillText(text, rects.cot.x + rects.cot.w + 8, mouseY);
		}

		// Highlight current bar's candle outline subtly
		const cw = Math.max(2, stepX * 0.7);
		ctx.strokeStyle = 'rgba(232,232,234,0.5)';
		ctx.lineWidth = 1;
		ctx.strokeRect(Math.floor(x - cw / 2) - 1, rects.price.y, Math.ceil(cw) + 2, rects.price.h);
	}

	// ── Frame loop: redraw base only when view/data changes, overlay always
	let stopRender: (() => void) | null = null;

	function startLoop() {
		stopRender = onRender(() => {
			// Detect view drift from springs
			const s = viewStart.value;
			const e = viewEnd.value;
			if (s !== lastViewStart || e !== lastViewEnd || width !== lastWidth || bars !== lastBarsRef) {
				baseDirty = true;
			}
			if (baseDirty) drawBase();
			drawOverlay();
		});
	}

	onMount(() => {
		// Try to set up the WebGL2 candle layer. If it fails (no WebGL2 support,
		// driver issue, etc.) we silently fall back to Canvas2D candles.
		candleLayer = tryCreateCandleLayer(webgl);
		usingWebGL = candleLayer !== null;

		resize();
		// Initialize view to full range
		viewStart.jump(0);
		viewEnd.jump(bars.length);
		lastBarsRef = bars;
		baseDirty = true;
		startLoop();

		const ro = new ResizeObserver(resize);
		ro.observe(wrap);

		window.addEventListener('keydown', onKey);

		return () => {
			ro.disconnect();
			stopRender?.();
			window.removeEventListener('keydown', onKey);
			candleLayer?.dispose();
			candleLayer = null;
			viewStart.dispose();
			viewEnd.dispose();
		};
	});

	// Reset view when the bars array reference changes (e.g. range button switch)
	$effect(() => {
		void bars;
		if (lastBarsRef && bars !== lastBarsRef) {
			lastBarsRef = bars;
			viewStart.jump(0);
			viewEnd.jump(bars.length);
			baseDirty = true;
		}
	});

	const visibleSpanLabel = $derived.by(() => {
		const s = Math.max(0, Math.floor(viewStart.value));
		const e = Math.min(bars.length, Math.ceil(viewEnd.value));
		if (e - s < 1 || !bars.length) return '';
		const startDate = bars[s]?.date.slice(0, 10);
		const endDate = bars[Math.min(bars.length - 1, e - 1)]?.date.slice(0, 10);
		return `${startDate} → ${endDate} · ${e - s} bars`;
	});

	const hoverBar = $derived(hoverBarIdx != null ? bars[hoverBarIdx] : null);
</script>

<div class="chart-wrap" bind:this={wrap} style:height={`${height}px`}>
	<canvas bind:this={base} class="canvas-layer base"></canvas>
	<canvas bind:this={webgl} class="canvas-layer webgl"></canvas>
	<canvas bind:this={lines} class="canvas-layer lines"></canvas>
	<canvas
		bind:this={overlay}
		class="canvas-layer overlay"
		onwheel={onWheel}
		onpointerdown={onPointerDown}
		onpointerup={onPointerUp}
		onpointermove={onPointerMove}
		onpointerleave={onPointerLeave}
		ondblclick={onDoubleClick}
	></canvas>
	{#if usingWebGL}
		<span class="gl-badge num" title="WebGL2 candle layer active">GL</span>
	{/if}

	<!-- Top HUD ribbon — single horizontal row, never overlaps candles. -->
	<div class="hud-ribbon">
		<div class="hud-left">
			<span class="hud-span num">{visibleSpanLabel}</span>
		</div>
		<div class="hud-right">
			{#if hoverBar}
				<span class="hud-date num">{hoverBar.date}</span>
				<span class="hud-stat"><em>O</em><span class="num">{hoverBar.open?.toFixed(2) ?? '—'}</span></span>
				<span class="hud-stat"><em>H</em><span class="num">{hoverBar.high?.toFixed(2) ?? '—'}</span></span>
				<span class="hud-stat"><em>L</em><span class="num">{hoverBar.low?.toFixed(2) ?? '—'}</span></span>
				<span class="hud-stat hud-close" data-up={hoverBar.close != null && hoverBar.open != null && hoverBar.close >= hoverBar.open}>
					<em>C</em><span class="num">{hoverBar.close?.toFixed(2) ?? '—'}</span>
				</span>
				<span class="hud-stat hud-sma"><em>MA</em><span class="num">{hoverBar.sma_slow?.toFixed(2) ?? '—'}</span></span>
				<span class="hud-stat hud-cot"><em>COT</em><span class="num">{hoverBar.cot_index_comm?.toFixed(1) ?? '—'}</span></span>
				<span class="hud-stat hud-net">
					<em>NET</em>
					<span class="num">
						{hoverBar.net_commercials != null ? (hoverBar.net_commercials / 1000).toFixed(0) + 'K' : '—'}
					</span>
				</span>
				{@const activeZones = (['A1','A2','A3','A4','A5'] as const).filter((z) => hoverBar[z])}
				{#if activeZones.length}
					<span class="hud-zones">
						{#each activeZones as z}
							<span class="hud-zone num" style:--c={`var(--zone-${z.toLowerCase()})`}>{z}</span>
						{/each}
					</span>
				{/if}
			{:else}
				<span class="hud-hint num">drag · wheel zoom · ⇧wheel pan · ← → · + − · esc · dbl-click reset</span>
			{/if}
		</div>
	</div>

	<!-- News pin tooltip is preserved below -->


	<!-- News pin tooltip -->
	{#if hoverPin}
		<div
			class="pin-tooltip"
			style:left={`${hoverPinX}px`}
			style:bottom={`${PAD_B + 14}px`}
		>
			<div class="pt-row">
				<span class="pt-src" data-cat={hoverPin.source_category}>{hoverPin.source}</span>
				{#if hoverPin.publisher}
					<span class="pt-pub">· {hoverPin.publisher}</span>
				{/if}
				<span class="pt-date num">{hoverPin.date.slice(0, 10)}</span>
			</div>
			<div class="pt-title">{hoverPin.title}</div>
			{#if hoverPin.url}
				<div class="pt-foot">click to open ↗</div>
			{/if}
		</div>
	{/if}
</div>

<style>
	.chart-wrap {
		position: relative;
		width: 100%;
		background: var(--bg-panel);
		border: 1px solid var(--border-soft);
		border-radius: var(--r-md);
		overflow: hidden;
		user-select: none;
	}
	.canvas-layer {
		position: absolute;
		left: 0;
		top: 0;
	}
	.canvas-layer.base {
		z-index: 1;
	}
	.canvas-layer.webgl {
		z-index: 2;
		pointer-events: none;
	}
	.canvas-layer.lines {
		z-index: 3;
		pointer-events: none;
	}
	.canvas-layer.overlay {
		z-index: 4;
		touch-action: none;
		cursor: crosshair;
	}
	.gl-badge {
		position: absolute;
		right: var(--sp-3);
		bottom: var(--sp-3);
		z-index: 6;
		font-size: 9px;
		padding: 2px 5px;
		color: var(--zone-a3);
		background: color-mix(in srgb, var(--zone-a3) 12%, transparent);
		border: 1px solid color-mix(in srgb, var(--zone-a3) 35%, transparent);
		border-radius: 3px;
		letter-spacing: 0.06em;
		pointer-events: none;
		opacity: 0.6;
	}

	.hud-ribbon {
		position: absolute;
		top: 0;
		left: 0;
		right: 0;
		height: 28px;
		padding: 0 var(--sp-3);
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--sp-3);
		background: linear-gradient(180deg, rgba(10, 10, 11, 0.85), rgba(10, 10, 11, 0.55) 70%, transparent);
		pointer-events: none;
		z-index: 5;
		font-size: var(--fs-11);
		letter-spacing: 0.02em;
	}
	.hud-left {
		display: flex;
		align-items: center;
		gap: var(--sp-2);
	}
	.hud-span {
		color: var(--ink-muted);
		font-size: var(--fs-11);
	}
	.hud-right {
		display: flex;
		align-items: center;
		gap: var(--sp-3);
		overflow: hidden;
		min-width: 0;
	}
	.hud-date {
		color: var(--ink);
		font-size: var(--fs-11);
		padding-right: var(--sp-2);
		border-right: 1px solid var(--border-soft);
	}
	.hud-stat {
		display: inline-flex;
		align-items: baseline;
		gap: 4px;
		color: var(--ink);
		font-size: var(--fs-11);
	}
	.hud-stat em {
		font-style: normal;
		color: var(--ink-faint);
		font-size: 10px;
		text-transform: uppercase;
		letter-spacing: 0.08em;
	}
	.hud-close[data-up='true'] .num {
		color: var(--long);
	}
	.hud-close[data-up='false'] .num {
		color: var(--short);
	}
	.hud-sma .num {
		color: var(--pending);
	}
	.hud-cot .num {
		color: var(--zone-a3);
	}
	.hud-net .num {
		color: var(--ink-muted);
	}
	.hud-zones {
		display: inline-flex;
		gap: 3px;
		padding-left: var(--sp-2);
		border-left: 1px solid var(--border-soft);
	}
	.hud-zone {
		font-size: 10px;
		padding: 1px 4px;
		border-radius: 3px;
		color: var(--c);
		border: 1px solid color-mix(in srgb, var(--c) 45%, transparent);
		background: color-mix(in srgb, var(--c) 14%, transparent);
	}
	.hud-hint {
		font-size: 10px;
		color: var(--ink-faint);
		letter-spacing: 0.04em;
		white-space: nowrap;
	}

	.pin-tooltip {
		position: absolute;
		transform: translateX(-50%);
		max-width: 320px;
		min-width: 220px;
		background: rgba(10, 10, 11, 0.95);
		backdrop-filter: blur(8px);
		border: 1px solid var(--border);
		border-radius: var(--r-sm);
		padding: var(--sp-2) var(--sp-3);
		font-size: var(--fs-12);
		color: var(--ink);
		pointer-events: none;
		z-index: 10;
		box-shadow: var(--shadow-2);
	}
	.pt-row {
		display: flex;
		align-items: baseline;
		gap: 6px;
		font-size: 10px;
		color: var(--ink-muted);
		margin-bottom: 4px;
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}
	.pt-src[data-cat='agency'] {
		color: var(--zone-a3);
	}
	.pt-src[data-cat='macro'] {
		color: var(--zone-a4);
	}
	.pt-src[data-cat='geopolitics'] {
		color: var(--zone-a2);
	}
	.pt-src[data-cat='market'] {
		color: var(--zone-a1);
	}
	.pt-date {
		margin-left: auto;
		color: var(--ink-faint);
	}
	.pt-title {
		font-size: var(--fs-12);
		color: var(--ink);
		line-height: 1.35;
	}
	.pt-foot {
		margin-top: 6px;
		font-size: 10px;
		color: var(--ink-faint);
		text-align: right;
	}
</style>
