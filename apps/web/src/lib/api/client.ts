/**
 * Typed fetch client for the COT_LENS_v1 origin server.
 *
 * Goes through Vite's /api proxy in dev (-> http://127.0.0.1:8000),
 * and through a Cloudflare worker in prod (deferred to Phase 3).
 */

import type {
	ArticleResponse,
	ContractMeta,
	DivergenceRow,
	HeatmapResponse,
	MarketDetail,
	NewsResponse,
	StatusResponse,
	TodayRow,
	RetailSentimentResponse, RegimeResponse, SynthesisResponse,
} from './types';

const BASE = '/api';

class ApiError extends Error {
	constructor(public status: number, message: string) {
		super(message);
	}
}

async function get<T>(path: string): Promise<T> {
	const res = await fetch(`${BASE}${path}`, { headers: { Accept: 'application/json' } });
	if (!res.ok) throw new ApiError(res.status, `${res.status} ${res.statusText} on ${path}`);
	return (await res.json()) as T;
}

export const api = {
	status: () => get<StatusResponse>('/status'),
	universe: () => get<ContractMeta[]>('/universe'),
	today: () => get<TodayRow[]>('/today'),
	market: (symbol: string, opts?: { from?: string; to?: string }) => {
		const qs = new URLSearchParams();
		if (opts?.from) qs.set('from', opts.from);
		if (opts?.to) qs.set('to', opts.to);
		const suffix = qs.toString() ? `?${qs}` : '';
		return get<MarketDetail>(`/market/${symbol}${suffix}`);
	},
	heatmap: (weekOf?: string) =>
		get<HeatmapResponse>(`/heatmap${weekOf ? `?week_of=${weekOf}` : ''}`),
	divergence: (week: string) => get<DivergenceRow[]>(`/divergence/${week}`),
	newsForSymbol: (symbol: string, opts?: { from?: string; to?: string; limit?: number }) => {
		const qs = new URLSearchParams();
		if (opts?.from) qs.set('from', opts.from);
		if (opts?.to) qs.set('to', opts.to);
		if (opts?.limit) qs.set('limit', String(opts.limit));
		const suffix = qs.toString() ? `?${qs}` : '';
		return get<NewsResponse>(`/news/${symbol}${suffix}`);
	},
	news: (opts?: { from?: string; to?: string; limit?: number }) => {
		const qs = new URLSearchParams();
		if (opts?.from) qs.set('from', opts.from);
		if (opts?.to) qs.set('to', opts.to);
		if (opts?.limit) qs.set('limit', String(opts.limit));
		const suffix = qs.toString() ? `?${qs}` : '';
		return get<NewsResponse>(`/news${suffix}`);
	},
	article: (url: string) =>
		get<ArticleResponse>(`/article?url=${encodeURIComponent(url)}`),
	retailSentiment: (symbol: string) =>
		get<RetailSentimentResponse>(`/retail-sentiment/${symbol}`),
	regime: (symbol: string) =>
		get<RegimeResponse>(`/regime/${symbol}`),
	synthesis: (symbol: string) =>
		get<SynthesisResponse>(`/synthesis/${symbol}`),
};

export { ApiError };
