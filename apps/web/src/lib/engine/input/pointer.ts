/**
 * Pointer input batcher.
 *
 * Pointer events fire many times per frame; we collapse the latest position
 * into a single per-frame value the renderer reads. Avoids forcing layout
 * or React-style re-render per move.
 *
 * Usage:
 *   const p = createPointer(canvasEl);
 *   onRender(() => {
 *     if (p.dirty) {
 *       drawCrosshair(p.x, p.y);
 *       p.consume();
 *     }
 *   });
 */

export interface PointerState {
	readonly x: number;
	readonly y: number;
	readonly inside: boolean;
	readonly dirty: boolean;
	consume(): void;
	dispose(): void;
}

export function createPointer(target: HTMLElement): PointerState {
	let x = -1;
	let y = -1;
	let inside = false;
	let dirty = false;

	const handleMove = (ev: PointerEvent) => {
		const rect = target.getBoundingClientRect();
		x = ev.clientX - rect.left;
		y = ev.clientY - rect.top;
		inside = true;
		dirty = true;
	};

	const handleLeave = () => {
		inside = false;
		dirty = true;
	};

	target.addEventListener('pointermove', handleMove, { passive: true });
	target.addEventListener('pointerenter', handleMove, { passive: true });
	target.addEventListener('pointerleave', handleLeave, { passive: true });

	return {
		get x() {
			return x;
		},
		get y() {
			return y;
		},
		get inside() {
			return inside;
		},
		get dirty() {
			return dirty;
		},
		consume() {
			dirty = false;
		},
		dispose() {
			target.removeEventListener('pointermove', handleMove);
			target.removeEventListener('pointerenter', handleMove);
			target.removeEventListener('pointerleave', handleLeave);
		}
	};
}
