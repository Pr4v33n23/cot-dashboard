/**
 * Frame scheduler.
 *
 * One global rAF loop tickets out a fixed-timestep simulation step + a variable
 * render step (Glenn Fiedler "Fix Your Timestep!" pattern). All animation,
 * spring physics, scrub motion, and chart hover state should hook into this
 * scheduler — never into per-component CSS transitions or setTimeout chains.
 *
 * Subscribers come in three flavors:
 *   - sim(dt)    : pure state update, runs at SIM_HZ regardless of refresh rate
 *   - render(t)  : runs once per rAF callback (display refresh rate)
 *   - idle()     : requestIdleCallback fallback for telemetry / non-critical work
 *
 * Cleanup is via the unsubscribe closure each `on*` returns.
 */

const SIM_HZ = 120;
const SIM_DT = 1 / SIM_HZ;
const MAX_FRAME_BUDGET_MS = 14; // PLAN: warn if rAF overruns this

type SimCb = (dt: number) => void;
type RenderCb = (now: number) => void;
type IdleCb = () => void;

const simSubs = new Set<SimCb>();
const renderSubs = new Set<RenderCb>();
const idleSubs = new Set<IdleCb>();

let running = false;
let lastTime = 0;
let accumulator = 0;
let rafId: number | null = null;

function frame(now: number) {
	if (!running) return;
	const nowSec = now / 1000;
	const frameStart = performance.now();

	if (lastTime === 0) lastTime = nowSec;
	let delta = nowSec - lastTime;
	lastTime = nowSec;
	// Clamp huge deltas (tab backgrounded) so springs don't catapult.
	if (delta > 0.25) delta = 0.25;

	accumulator += delta;
	while (accumulator >= SIM_DT) {
		for (const cb of simSubs) cb(SIM_DT);
		accumulator -= SIM_DT;
	}
	for (const cb of renderSubs) cb(nowSec);

	const frameMs = performance.now() - frameStart;
	if (frameMs > MAX_FRAME_BUDGET_MS && import.meta.env.DEV) {
		console.warn(`[scheduler] frame overran: ${frameMs.toFixed(1)}ms`);
	}

	rafId = requestAnimationFrame(frame);
}

function ensureRunning() {
	if (running) return;
	running = true;
	lastTime = 0;
	accumulator = 0;
	rafId = requestAnimationFrame(frame);
}

function maybeStop() {
	if (simSubs.size === 0 && renderSubs.size === 0) {
		running = false;
		if (rafId !== null) cancelAnimationFrame(rafId);
		rafId = null;
	}
}

export function onSim(cb: SimCb): () => void {
	simSubs.add(cb);
	ensureRunning();
	return () => {
		simSubs.delete(cb);
		maybeStop();
	};
}

export function onRender(cb: RenderCb): () => void {
	renderSubs.add(cb);
	ensureRunning();
	return () => {
		renderSubs.delete(cb);
		maybeStop();
	};
}

export function onIdle(cb: IdleCb): () => void {
	idleSubs.add(cb);
	const ric =
		typeof requestIdleCallback !== 'undefined'
			? requestIdleCallback
			: (fn: IdleRequestCallback) => setTimeout(() => fn({ didTimeout: false, timeRemaining: () => 50 }), 0);
	const id = ric(() => {
		for (const c of idleSubs) c();
	});
	return () => {
		idleSubs.delete(cb);
		if (typeof cancelIdleCallback !== 'undefined') cancelIdleCallback(id as number);
	};
}

export const SCHED_INFO = { SIM_HZ, SIM_DT, MAX_FRAME_BUDGET_MS };
