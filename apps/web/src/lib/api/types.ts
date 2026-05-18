// Mirrors apps/api/src/schemas.py. Keep them in sync.
// If/when the Phase 3 deploy adds OpenAPI codegen, generate from /openapi.json.

export type ZoneKey = 'A1' | 'A2' | 'A3' | 'A4' | 'A5';

export const ZONE_NAMES: Record<ZoneKey, string> = {
	A1: 'Extreme positioning',
	A2: 'Price divergence',
	A3: 'Sector outlier',
	A4: 'Momentum shift',
	A5: 'Hedger/Speculator imbalance'
};

export const ZONE_BLURB: Record<ZoneKey, string> = {
	A1: 'COT Index at the top/bottom decile of its 3-year range — commercials are loaded up.',
	A2: 'Price prints a new 52-week extreme but commercials are moving the other way.',
	A3: 'Within the sector, this market is more than 1.5σ from peers on COT Index.',
	A4: '4-week COT-Index rate-of-change in the top/bottom decile of own history.',
	A5: 'Commercials and managed money are both near 3-year extremes, on opposite sides.'
};

export interface ContractMeta {
	symbol: string;
	name: string;
	sector: string;
	cftc_code: string;
	yf_ticker: string;
	point_value: number;
	tick_size: number;
}

export interface TodayRow {
	symbol: string;
	name: string;
	sector: string;
	date: string; // ISO date
	cot_index_comm: number | null;
	n_zones: number;
	zones_on: ZoneKey[];
	magnitudes: Record<ZoneKey, number>;
	total_mag: number;
}

export interface BarRow {
	date: string;
	open?: number | null;
	high?: number | null;
	low?: number | null;
	close?: number | null;
	volume?: number | null;
	sma_fast?: number | null;
	sma_slow?: number | null;
	cot_index_comm?: number | null;
	net_commercials?: number | null;
	pm_long?: number | null;
	pm_short?: number | null;
	sd_long?: number | null;
	sd_short?: number | null;
	mm_long?: number | null;
	mm_short?: number | null;
	ucl?: number | null;
	lcl?: number | null;
	A1: boolean;
	A2: boolean;
	A3: boolean;
	A4: boolean;
	A5: boolean;
	n_zones: number;
	open_interest?: number | null;
	nr_long?: number | null;
	nr_short?: number | null;
	dealer_long?: number | null;
	dealer_short?: number | null;
	am_long?: number | null;
	am_short?: number | null;
	lf_long?: number | null;
	lf_short?: number | null;
	comm_spec_divergence: number;
	am_lf_divergence: number;
	regime_label?: string | null;
	regime_proba?: number[] | null;
	regime_weeks: number;
	confluence_score?: number | null;
}

export interface MarketDetail {
	contract: ContractMeta;
	from_date: string;
	to_date: string;
	bars: BarRow[];
}

export interface HeatmapCell {
	symbol: string;
	sector: string;
	zone: ZoneKey;
	active: boolean;
	magnitude: number;
	market_type: string;
	regime_label?: string | null;
}

export interface HeatmapResponse {
	week_of: string;
	cells: HeatmapCell[];
}

export interface DivergenceRow {
	symbol: string;
	name: string;
	sector: string;
	date: string;
	magnitude: number;
	direction: 'bullish' | 'bearish';
	close: number;
	net_commercials: number;
}

export interface NewsItem {
	date: string; // ISO datetime
	source: string;
	source_category: string;
	ticker: string | null;
	title: string;
	url: string | null;
	publisher: string | null;
	markets: string[];
	sentiment_score?: number | null;
	sentiment_label?: string | null;
	sentiment_reason?: string | null;
}

export interface NewsResponse {
	symbol?: string | null;
	from_date?: string | null;
	to_date?: string | null;
	items: NewsItem[];
}

export interface StatusResponse {
	ok: boolean;
	loaded_at: string | null;
	n_markets: number;
	n_news: number;
	zones: { key: ZoneKey; name: string }[];
}

export interface ArticleResponse {
	url: string;
	title: string | null;
	site: string | null;
	byline: string | null;
	published: string | null;
	content_html: string;
	word_count: number;
	fetched_at: string;
}

export interface RetailSentimentItem {
  symbol: string;
  long_pct: number;
  short_pct: number;
  source: string;
  timestamp: string;
}

export interface RetailSentimentResponse {
  symbol: string;
  items: RetailSentimentItem[];
  avg_long_pct: number;
  avg_short_pct: number;
}

export interface RegimeResponse {
  symbol: string;
  market_type: string;
  current_regime: string;
  regime_weeks: number;
  proba: number[];
  next_bar_proba: number[];
  transition_matrix: number[][];
  state_names: string[];
}

export interface SynthesisResponse {
  symbol: string;
  summary: string;
  confluence_score: number;
  key_factors: string[];
  watch: string;
  generated_at?: string | null;
}

export interface SectorSignal {
	sector: string;
	summary: string;
	signal: 'bullish' | 'bearish' | 'neutral';
}

export interface WatchMarket {
	symbol: string;
	name: string;
	sector: string;
	confluence_score: number;
	reason: string;
}

export interface DigestResponse {
	generated_at: string;
	macro_narrative: string;
	sector_signals: SectorSignal[];
	watch_markets: WatchMarket[];
}

export interface ChatMessage {
	role: 'user' | 'assistant' | 'system';
	content: string;
}

export interface ChatResponse {
	reply: string;
	cited_markets: string[];
	context_date: string | null;
}

export interface ExtremesRow {
	symbol: string;
	name: string;
	sector: string;
	market_type: string;
	cot_index: number | null;
	extremeness: number;
	direction: 'long' | 'short' | 'neutral';
	pct_90: number | null;
	pct_10: number | null;
	n_zones: number;
	regime_label: string | null;
	confluence_score: number;
}

export interface AnalogueEntry {
	date: string;
	weeks_ago: number;
	similarity: number;
	cot_index_then: number;
	price_then: number | null;
	fwd_4w_pct: number | null;
	fwd_8w_pct: number | null;
	fwd_12w_pct: number | null;
}

export interface AnaloguesResponse {
	symbol: string;
	current_cot_index: number | null;
	analogues: AnalogueEntry[];
}

export interface AlertRule {
	id?: string | null;
	symbol: string;
	field: string;
	condition: 'above' | 'below' | 'crosses_above' | 'crosses_below';
	threshold: number;
	label?: string;
	active?: boolean;
	last_triggered?: string | null;
	created_at?: string | null;
}

export interface AlertTrigger {
	id: string;
	symbol: string;
	label: string;
	current_value: number;
	threshold: number;
	condition: string;
	last_triggered: string;
}
