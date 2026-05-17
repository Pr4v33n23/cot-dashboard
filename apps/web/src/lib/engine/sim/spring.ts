/**
 * Critically-undamped spring.
 *
 * Used for hover, crosshair, scrub, tab indicator, number ticker, etc.
 * Drives ALL UI animation; no CSS transitions.
 *
 * Integrates against the sim scheduler (fixed dt). Consumer reads `value` each
 * render frame.
 *
 *   const s = createSpring(0, { stiffness: 300, damping: 30 });
 *   s.set(target);
 *   // ... in render: read s.value
 *
 * Parameters use Svelte/Framer Motion convention (stiffness, damping, mass).
 */

import { onSim } from '../scheduler';

export interface SpringOptions {
	stiffness?: number; // higher = snappier
	damping?: number; // higher = less overshoot
	mass?: number;
	restDelta?: number; // settle threshold (positional)
	restVelocity?: number; // settle threshold (velocity)
}

export interface Spring {
	readonly value: number;
	readonly velocity: number;
	target: number;
	set(target: number): void;
	jump(value: number): void;
	dispose(): void;
}

export function createSpring(initial: number, opts: SpringOptions = {}): Spring {
	const stiffness = opts.stiffness ?? 300;
	const damping = opts.damping ?? 30;
	const mass = opts.mass ?? 1;
	const restDelta = opts.restDelta ?? 0.001;
	const restVelocity = opts.restVelocity ?? 0.001;

	let value = initial;
	let velocity = 0;
	let target = initial;
	let active = false;

	const unsub = onSim((dt: number) => {
		if (!active) return;
		// Hooke's law spring with viscous damping. Semi-implicit Euler.
		const displacement = value - target;
		const springForce = -stiffness * displacement;
		const dampForce = -damping * velocity;
		const acceleration = (springForce + dampForce) / mass;
		velocity += acceleration * dt;
		value += velocity * dt;

		if (Math.abs(velocity) < restVelocity && Math.abs(displacement) < restDelta) {
			value = target;
			velocity = 0;
			active = false;
		}
	});

	return {
		get value() {
			return value;
		},
		get velocity() {
			return velocity;
		},
		get target() {
			return target;
		},
		set target(t: number) {
			target = t;
			active = true;
		},
		set(t: number) {
			target = t;
			active = true;
		},
		jump(v: number) {
			value = v;
			velocity = 0;
			target = v;
			active = false;
		},
		dispose() {
			unsub();
		}
	};
}
