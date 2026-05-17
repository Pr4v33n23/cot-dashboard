/**
 * WebGL2 candle layer.
 *
 * Replaces the per-candle Canvas2D draw loop with two batched draw calls:
 *   1. Wicks  — LINES primitive, 2 vertices per candle
 *   2. Bodies — TRIANGLES primitive, 6 vertices per candle (two triangles)
 *
 * Per-vertex attributes:
 *   - aBarIdx (float)  : bar index (0..n-1) — projected via uniform xRange
 *   - aValue  (float)  : price value (open/high/low/close depending on vertex)
 *   - aSide   (float)  : -1 for left edge of body, +1 for right edge (0 for wicks)
 *   - aColor  (float)  : 1.0 for up (green), 0.0 for down (red)
 *
 * Uniforms set per draw:
 *   - uXRange  (vec2) : [viewStart, viewEnd]
 *   - uYRange  (vec2) : [priceLo, priceHi]
 *   - uRect    (vec4) : [x, y, w, h] of the price pane in CSS pixels
 *   - uCanvas  (vec2) : [canvasWidth, canvasHeight] in CSS pixels
 *   - uBarPx   (float): body width in pixels
 *   - uColors  (vec3[2]) : down (R), up (G)
 *
 * Falls back to Canvas2D when WebGL2 context creation fails.
 */

export interface CandleData {
	open: number;
	high: number;
	low: number;
	close: number;
}

interface ViewParams {
	viewStart: number;
	viewEnd: number;
	priceLo: number;
	priceHi: number;
	rect: { x: number; y: number; w: number; h: number };
	canvas: { w: number; h: number };
	barPx: number;
}

const VS = /* glsl */ `#version 300 es
	in float aBarIdx;
	in float aValue;
	in float aSide;
	in float aColor;

	uniform vec2 uXRange;
	uniform vec2 uYRange;
	uniform vec4 uRect;
	uniform vec2 uCanvas;
	uniform float uBarPx;

	out float vColor;

	void main() {
		float xSpan = uXRange.y - uXRange.x;
		float xn = (aBarIdx - uXRange.x) / xSpan;
		float xPx = uRect.x + xn * uRect.z + aSide * uBarPx * 0.5;

		float ySpan = uYRange.y - uYRange.x;
		float yn = (aValue - uYRange.x) / ySpan;
		float yPx = uRect.y + uRect.w - yn * uRect.w;
		// uRect.w is the height (we stored [x, y, w, h] as vec4 — w-component is .w; h via .a? No, glsl vec4.w == .a)
		// In GLSL vec4, components are x, y, z, w; so we'll store as [x, y, w_width, h_height].
		// Actually overwrite above to be unambiguous: use uRect.zw for size.
		yPx = uRect.y + uRect.w - yn * uRect.w;

		vec2 clip = vec2(
			(xPx / uCanvas.x) * 2.0 - 1.0,
			1.0 - (yPx / uCanvas.y) * 2.0
		);
		gl_Position = vec4(clip, 0.0, 1.0);
		vColor = aColor;
	}
`;

const FS = /* glsl */ `#version 300 es
	precision mediump float;

	in float vColor;
	uniform vec3 uColorUp;
	uniform vec3 uColorDown;

	out vec4 oColor;

	void main() {
		vec3 c = mix(uColorDown, uColorUp, step(0.5, vColor));
		oColor = vec4(c, 1.0);
	}
`;

function compile(gl: WebGL2RenderingContext, type: number, src: string): WebGLShader {
	const sh = gl.createShader(type)!;
	gl.shaderSource(sh, src);
	gl.compileShader(sh);
	if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
		const log = gl.getShaderInfoLog(sh);
		gl.deleteShader(sh);
		throw new Error(`Shader compile failed: ${log}`);
	}
	return sh;
}

function link(gl: WebGL2RenderingContext, vs: WebGLShader, fs: WebGLShader): WebGLProgram {
	const p = gl.createProgram()!;
	gl.attachShader(p, vs);
	gl.attachShader(p, fs);
	gl.linkProgram(p);
	if (!gl.getProgramParameter(p, gl.LINK_STATUS)) {
		const log = gl.getProgramInfoLog(p);
		gl.deleteProgram(p);
		throw new Error(`Program link failed: ${log}`);
	}
	return p;
}

export class CandleLayer {
	private gl: WebGL2RenderingContext;
	private program: WebGLProgram;
	private vao: WebGLVertexArrayObject;
	private bodyBuf: WebGLBuffer;
	private wickBuf: WebGLBuffer;
	private bodyCount = 0;
	private wickCount = 0;

	private loc!: {
		aBarIdx: number;
		aValue: number;
		aSide: number;
		aColor: number;
		uXRange: WebGLUniformLocation;
		uYRange: WebGLUniformLocation;
		uRect: WebGLUniformLocation;
		uCanvas: WebGLUniformLocation;
		uBarPx: WebGLUniformLocation;
		uColorUp: WebGLUniformLocation;
		uColorDown: WebGLUniformLocation;
	};

	constructor(canvas: HTMLCanvasElement) {
		const gl = canvas.getContext('webgl2', {
			antialias: true,
			premultipliedAlpha: false,
			preserveDrawingBuffer: false
		});
		if (!gl) throw new Error('WebGL2 not available');
		this.gl = gl;

		const vs = compile(gl, gl.VERTEX_SHADER, VS);
		const fs = compile(gl, gl.FRAGMENT_SHADER, FS);
		this.program = link(gl, vs, fs);

		this.loc = {
			aBarIdx: gl.getAttribLocation(this.program, 'aBarIdx'),
			aValue: gl.getAttribLocation(this.program, 'aValue'),
			aSide: gl.getAttribLocation(this.program, 'aSide'),
			aColor: gl.getAttribLocation(this.program, 'aColor'),
			uXRange: gl.getUniformLocation(this.program, 'uXRange')!,
			uYRange: gl.getUniformLocation(this.program, 'uYRange')!,
			uRect: gl.getUniformLocation(this.program, 'uRect')!,
			uCanvas: gl.getUniformLocation(this.program, 'uCanvas')!,
			uBarPx: gl.getUniformLocation(this.program, 'uBarPx')!,
			uColorUp: gl.getUniformLocation(this.program, 'uColorUp')!,
			uColorDown: gl.getUniformLocation(this.program, 'uColorDown')!
		};

		this.vao = gl.createVertexArray()!;
		this.bodyBuf = gl.createBuffer()!;
		this.wickBuf = gl.createBuffer()!;
	}

	/**
	 * Build vertex buffers from candle data.
	 * Each vertex = [barIdx, value, side, color] — 4 floats × N vertices.
	 */
	setBars(bars: CandleData[]): void {
		const gl = this.gl;

		// Bodies: 6 vertices per candle (two triangles forming the rect)
		const bodyVerts = new Float32Array(bars.length * 6 * 4);
		let b = 0;
		for (let i = 0; i < bars.length; i++) {
			const { open, high, low, close } = bars[i];
			if (
				open == null ||
				high == null ||
				low == null ||
				close == null ||
				!isFinite(open) ||
				!isFinite(close)
			) {
				// Push a zero-area triangle (invisible) to keep indexing simple
				for (let v = 0; v < 6; v++) {
					bodyVerts[b++] = i;
					bodyVerts[b++] = 0;
					bodyVerts[b++] = 0;
					bodyVerts[b++] = 0;
				}
				continue;
			}
			const up = close >= open ? 1 : 0;
			const top = Math.max(open, close);
			const bot = Math.min(open, close);
			// Triangle 1: TL, BL, BR
			// Triangle 2: TL, BR, TR
			// (side: -1 = left edge, +1 = right edge)
			// Vertex format: [barIdx, value, side, color]
			// TL
			bodyVerts[b++] = i;
			bodyVerts[b++] = top;
			bodyVerts[b++] = -1;
			bodyVerts[b++] = up;
			// BL
			bodyVerts[b++] = i;
			bodyVerts[b++] = bot;
			bodyVerts[b++] = -1;
			bodyVerts[b++] = up;
			// BR
			bodyVerts[b++] = i;
			bodyVerts[b++] = bot;
			bodyVerts[b++] = 1;
			bodyVerts[b++] = up;
			// TL
			bodyVerts[b++] = i;
			bodyVerts[b++] = top;
			bodyVerts[b++] = -1;
			bodyVerts[b++] = up;
			// BR
			bodyVerts[b++] = i;
			bodyVerts[b++] = bot;
			bodyVerts[b++] = 1;
			bodyVerts[b++] = up;
			// TR
			bodyVerts[b++] = i;
			bodyVerts[b++] = top;
			bodyVerts[b++] = 1;
			bodyVerts[b++] = up;
		}
		this.bodyCount = bars.length * 6;
		gl.bindBuffer(gl.ARRAY_BUFFER, this.bodyBuf);
		gl.bufferData(gl.ARRAY_BUFFER, bodyVerts, gl.STATIC_DRAW);

		// Wicks: 2 vertices per candle (high, low) at side=0
		const wickVerts = new Float32Array(bars.length * 2 * 4);
		let w = 0;
		for (let i = 0; i < bars.length; i++) {
			const { open, high, low, close } = bars[i];
			if (high == null || low == null || !isFinite(high) || !isFinite(low)) {
				for (let v = 0; v < 2; v++) {
					wickVerts[w++] = i;
					wickVerts[w++] = 0;
					wickVerts[w++] = 0;
					wickVerts[w++] = 0;
				}
				continue;
			}
			const up = close >= open ? 1 : 0;
			// high
			wickVerts[w++] = i;
			wickVerts[w++] = high;
			wickVerts[w++] = 0;
			wickVerts[w++] = up;
			// low
			wickVerts[w++] = i;
			wickVerts[w++] = low;
			wickVerts[w++] = 0;
			wickVerts[w++] = up;
		}
		this.wickCount = bars.length * 2;
		gl.bindBuffer(gl.ARRAY_BUFFER, this.wickBuf);
		gl.bufferData(gl.ARRAY_BUFFER, wickVerts, gl.STATIC_DRAW);
	}

	resize(cssW: number, cssH: number, dpr: number): void {
		const gl = this.gl;
		const canvas = gl.canvas as HTMLCanvasElement;
		canvas.width = Math.floor(cssW * dpr);
		canvas.height = Math.floor(cssH * dpr);
		canvas.style.width = `${cssW}px`;
		canvas.style.height = `${cssH}px`;
		gl.viewport(0, 0, canvas.width, canvas.height);
	}

	clear(): void {
		const gl = this.gl;
		gl.clearColor(0, 0, 0, 0);
		gl.clear(gl.COLOR_BUFFER_BIT);
	}

	draw(params: ViewParams, colorUp: [number, number, number], colorDown: [number, number, number]): void {
		const gl = this.gl;
		gl.useProgram(this.program);

		gl.uniform2f(this.loc.uXRange, params.viewStart, params.viewEnd);
		gl.uniform2f(this.loc.uYRange, params.priceLo, params.priceHi);
		// uRect is [x, y, w, h]; in shader we treat .z = width, .w = height
		gl.uniform4f(
			this.loc.uRect,
			params.rect.x,
			params.rect.y,
			params.rect.w,
			params.rect.h
		);
		gl.uniform2f(this.loc.uCanvas, params.canvas.w, params.canvas.h);
		gl.uniform1f(this.loc.uBarPx, params.barPx);
		gl.uniform3fv(this.loc.uColorUp, colorUp);
		gl.uniform3fv(this.loc.uColorDown, colorDown);

		gl.bindVertexArray(this.vao);

		// ── Bodies (triangles) ──────────────────────────────────────────
		gl.bindBuffer(gl.ARRAY_BUFFER, this.bodyBuf);
		const stride = 4 * 4;
		gl.enableVertexAttribArray(this.loc.aBarIdx);
		gl.vertexAttribPointer(this.loc.aBarIdx, 1, gl.FLOAT, false, stride, 0);
		gl.enableVertexAttribArray(this.loc.aValue);
		gl.vertexAttribPointer(this.loc.aValue, 1, gl.FLOAT, false, stride, 4);
		gl.enableVertexAttribArray(this.loc.aSide);
		gl.vertexAttribPointer(this.loc.aSide, 1, gl.FLOAT, false, stride, 8);
		gl.enableVertexAttribArray(this.loc.aColor);
		gl.vertexAttribPointer(this.loc.aColor, 1, gl.FLOAT, false, stride, 12);

		gl.drawArrays(gl.TRIANGLES, 0, this.bodyCount);

		// ── Wicks (lines) ───────────────────────────────────────────────
		gl.bindBuffer(gl.ARRAY_BUFFER, this.wickBuf);
		gl.vertexAttribPointer(this.loc.aBarIdx, 1, gl.FLOAT, false, stride, 0);
		gl.vertexAttribPointer(this.loc.aValue, 1, gl.FLOAT, false, stride, 4);
		gl.vertexAttribPointer(this.loc.aSide, 1, gl.FLOAT, false, stride, 8);
		gl.vertexAttribPointer(this.loc.aColor, 1, gl.FLOAT, false, stride, 12);

		gl.lineWidth(1.0);
		gl.drawArrays(gl.LINES, 0, this.wickCount);
	}

	dispose(): void {
		const gl = this.gl;
		gl.deleteBuffer(this.bodyBuf);
		gl.deleteBuffer(this.wickBuf);
		gl.deleteVertexArray(this.vao);
		gl.deleteProgram(this.program);
	}
}

export function tryCreateCandleLayer(canvas: HTMLCanvasElement): CandleLayer | null {
	try {
		return new CandleLayer(canvas);
	} catch (err) {
		if (typeof console !== 'undefined') {
			console.warn('[webgl] candle layer init failed, falling back to Canvas2D:', err);
		}
		return null;
	}
}
