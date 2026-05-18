# Intelligence Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a `/intelligence` route combining a weekly AI-generated cross-market digest (left panel) with per-market DeepSeek synthesis loaded on click (right panel).

**Architecture:** New `packages/ingest/intelligence.py` module builds a structured payload and calls DeepSeek-V4-Pro to produce the digest. Result is cached to `research/data/cache/intelligence_digest.json` and served via `GET /intelligence/digest`. The frontend is a single SvelteKit page with a 340px left panel (digest) and a flex-fill right panel (per-market synthesis loaded on click). All DeepSeek calls go through the existing `_ai.py` shared client.

**Tech Stack:** Python, FastAPI, pandas, SvelteKit 5 (Svelte runes), huggingface_hub (DeepSeek-V4-Pro via `_ai.py`)

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `packages/ingest/intelligence.py` | Digest payload builder + DeepSeek call + cache |
| Create | `tests/ingest/test_intelligence.py` | Tests for intelligence module |
| Modify | `apps/api/src/schemas.py` | Add SectorSignal, WatchMarket, DigestResponse |
| Modify | `apps/api/src/main.py` | Add /intelligence/digest, /intelligence/refresh, macro_only param on /news |
| Modify | `apps/web/src/lib/api/types.ts` | Add DigestResponse, SectorSignal, WatchMarket |
| Modify | `apps/web/src/lib/api/client.ts` | Add digest(), newsAllMacro() methods |
| Create | `apps/web/src/routes/intelligence/+page.svelte` | Combined Intelligence page |
| Modify | `apps/web/src/routes/+layout.svelte` | Add Intelligence to routes list |
| Modify | `apps/web/src/routes/market/[symbol]/+page.svelte` | Add deep-link to /intelligence?sym= |

---

## Task 1: `intelligence.py` module + tests

**Files:**
- Create: `packages/ingest/intelligence.py`
- Create: `tests/ingest/test_intelligence.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/ingest/test_intelligence.py
from __future__ import annotations
import json
import pandas as pd
import pytest
from unittest.mock import patch
from ingest.intelligence import (
    build_digest_payload,
    _parse_digest,
    generate_digest,
    REQUIRED_KEYS,
)

SAMPLE_SYNTHESIS = {
    "CL": {"confluence_score": 0.84, "key_factors": ["extreme commercial long"], "summary": "x", "watch": "y"},
    "HG": {"confluence_score": 0.79, "key_factors": ["accumulation"], "summary": "x", "watch": "y"},
}
VALID_DIGEST = json.dumps({
    "macro_narrative": "Commercials near extreme longs across energy.",
    "sector_signals": [{"sector": "energy", "summary": "Comm extreme long", "signal": "bullish"}],
    "watch_markets": [{"symbol": "CL", "reason": "5-week divergence"}],
})


def test_build_digest_payload_has_required_keys():
    ann = {}
    news = pd.DataFrame()
    payload = build_digest_payload(ann, news, SAMPLE_SYNTHESIS)
    for k in ("date", "top_markets", "sector_summary", "macro_news", "divergence_count", "regime_counts"):
        assert k in payload, f"missing key: {k}"


def test_build_digest_top_markets_sorted_descending():
    ann = {}
    news = pd.DataFrame()
    payload = build_digest_payload(ann, news, SAMPLE_SYNTHESIS)
    scores = [m["confluence_score"] for m in payload["top_markets"]]
    assert scores == sorted(scores, reverse=True)


def test_build_digest_top_markets_limit_10():
    big_synth = {f"S{i}": {"confluence_score": float(i) / 100} for i in range(50)}
    payload = build_digest_payload({}, pd.DataFrame(), big_synth)
    assert len(payload["top_markets"]) <= 10


def test_parse_digest_valid_json():
    result = _parse_digest(VALID_DIGEST)
    assert set(REQUIRED_KEYS).issubset(result.keys())
    assert result["macro_narrative"] != ""
    assert isinstance(result["sector_signals"], list)
    assert isinstance(result["watch_markets"], list)


def test_parse_digest_malformed_returns_defaults():
    result = _parse_digest("not json at all {{ broken")
    assert result["macro_narrative"] == ""
    assert result["sector_signals"] == []
    assert result["watch_markets"] == []


def test_generate_digest_no_token_returns_defaults():
    with patch("ingest.intelligence.available", return_value=False):
        result = generate_digest({"date": "2026-05-18"})
    assert result["macro_narrative"] == ""


def test_generate_digest_calls_chat_once():
    with patch("ingest.intelligence.chat") as mock_chat, \
         patch("ingest.intelligence.available", return_value=True):
        mock_chat.return_value = VALID_DIGEST
        result = generate_digest({"date": "2026-05-18"})
    mock_chat.assert_called_once()
    assert result["macro_narrative"] != ""
```

- [ ] **Step 2: Run — verify fails**

```bash
cd /Users/praveen/Projects/cot-dashboard && .venv/bin/python -m pytest tests/ingest/test_intelligence.py -v 2>&1 | tail -5
```

Expected: `ModuleNotFoundError: No module named 'ingest.intelligence'`

- [ ] **Step 3: Implement `intelligence.py`**

```python
# packages/ingest/intelligence.py
"""Cross-market intelligence digest via DeepSeek-V4-Pro."""
from __future__ import annotations
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from ingest._ai import available, chat

REQUIRED_KEYS = ("macro_narrative", "sector_signals", "watch_markets")
_DEFAULT: dict = {"macro_narrative": "", "sector_signals": [], "watch_markets": []}

_SYSTEM = (
    "You are a quantitative market analyst producing a weekly intelligence digest. "
    "Given structured COT, regime, and news data, produce a JSON object with: "
    "macro_narrative (3-4 sentences on the dominant cross-market theme this week), "
    "sector_signals (array of {sector, summary, signal} where signal is 'bullish'|'bearish'|'neutral'), "
    "watch_markets (top 5 markets array of {symbol, reason}). "
    "All statements must be derived from the provided data. No invented facts. No trading advice. "
    "Return ONLY the JSON object."
)


def build_digest_payload(
    annotated: dict[str, pd.DataFrame],
    news_df: pd.DataFrame,
    synthesis: dict[str, dict],
) -> dict:
    from ingest.universe import UNIVERSE  # noqa: PLC0415

    # Top 10 markets by confluence_score
    top_markets = sorted(
        [
            {
                "symbol": sym,
                "confluence_score": float(data.get("confluence_score", 0) or 0),
                "key_factors": data.get("key_factors", [])[:3],
                "regime": (
                    str(annotated[sym].iloc[-1].get("regime_label", "unknown"))
                    if sym in annotated and not annotated[sym].empty
                    else "unknown"
                ),
            }
            for sym, data in synthesis.items()
            if float(data.get("confluence_score", 0) or 0) > 0
        ],
        key=lambda x: x["confluence_score"],
        reverse=True,
    )[:10]

    # Sector summary
    sec_map: dict[str, list[str]] = {}
    for c in UNIVERSE:
        sec_map.setdefault(c.sector, []).append(c.symbol)

    sector_summary: dict[str, dict] = {}
    for sec, syms in sec_map.items():
        scores = [float(synthesis[s].get("confluence_score", 0) or 0) for s in syms if s in synthesis]
        cot_vals = [
            float(v)
            for s in syms
            if s in annotated and not annotated[s].empty
            for v in [annotated[s].iloc[-1].get("cot_index_comm")]
            if v is not None and not (isinstance(v, float) and pd.isna(v))
        ]
        sector_summary[sec] = {
            "avg_confluence": round(sum(scores) / len(scores), 3) if scores else 0,
            "avg_cot_index": round(sum(cot_vals) / len(cot_vals), 1) if cot_vals else 50,
            "n_markets": len(syms),
        }

    # Macro news (last 10 scheduled-event headlines)
    macro_news: list[dict] = []
    if not news_df.empty and "source_category" in news_df.columns:
        macro = news_df[news_df["source_category"].isin(["macro", "agency"])].tail(10)
        for _, row in macro.iterrows():
            macro_news.append({
                "source": str(row.get("source", "")),
                "title": str(row.get("title", "")),
                "sentiment_score": float(row.get("sentiment_score", 0) or 0),
            })

    # Regime distribution across all annotated symbols
    regime_counts: dict[str, int] = {}
    for df in annotated.values():
        if df.empty:
            continue
        label = df.iloc[-1].get("regime_label")
        if label and isinstance(label, str):
            regime_counts[label] = regime_counts.get(label, 0) + 1

    # Count of markets with active divergence
    div_count = sum(
        1 for df in annotated.values()
        if not df.empty and int(
            df.iloc[-1].get("comm_spec_divergence", 0) or
            df.iloc[-1].get("am_lf_divergence", 0) or 0
        ) > 0
    )

    return {
        "date": datetime.now(tz=timezone.utc).strftime("%Y-%m-%d"),
        "top_markets": top_markets,
        "sector_summary": sector_summary,
        "macro_news": macro_news,
        "divergence_count": div_count,
        "regime_counts": regime_counts,
    }


def _parse_digest(content: str) -> dict:
    try:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            raise ValueError("no JSON object found")
        data = json.loads(match.group())
        for k in REQUIRED_KEYS:
            data.setdefault(k, _DEFAULT[k])
        return data
    except Exception:
        return dict(_DEFAULT)


def generate_digest(payload: dict) -> dict:
    if not available():
        return dict(_DEFAULT)
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": f"Generate digest from:\n{json.dumps(payload, indent=2)}"},
    ]
    raw = chat(messages, temperature=0.15)
    return _parse_digest(raw)


def load_or_generate_digest(
    annotated: dict[str, pd.DataFrame],
    news_df: pd.DataFrame,
    synthesis: dict[str, dict],
    cache_dir: Path,
    force: bool = False,
) -> dict:
    cache_path = cache_dir / "intelligence_digest.json"
    if not force and cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text())
            generated_at_str = cached.get("generated_at", "2000-01-01T00:00:00")
            generated_at = datetime.fromisoformat(generated_at_str.replace("Z", "+00:00"))
            age_days = (datetime.now(tz=timezone.utc) - generated_at).days
            if age_days < 7:
                return cached
        except Exception:
            pass
    result = generate_digest(build_digest_payload(annotated, news_df, synthesis))
    result["generated_at"] = datetime.now(tz=timezone.utc).isoformat()
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(result, indent=2, default=str))
    return result
```

- [ ] **Step 4: Run tests — verify all 7 pass**

```bash
cd /Users/praveen/Projects/cot-dashboard && .venv/bin/python -m pytest tests/ingest/test_intelligence.py -v 2>&1 | tail -12
```

Expected: 7 passed.

- [ ] **Step 5: Run full suite — no regressions**

```bash
.venv/bin/python -m pytest tests/ --tb=short 2>&1 | tail -5
```

Expected: 45 passed (38 existing + 7 new).

- [ ] **Step 6: Commit**

```bash
git add packages/ingest/intelligence.py tests/ingest/test_intelligence.py
git commit -m "feat: add intelligence digest module (DeepSeek-V4-Pro, cached weekly)"
```

---

## Task 2: Backend schemas + API endpoints

**Files:**
- Modify: `apps/api/src/schemas.py` — add 3 new models at end of file
- Modify: `apps/api/src/main.py` — add 2 new endpoints + `macro_only` param on `/news`

- [ ] **Step 1: Add models to `schemas.py`**

Append to the end of `apps/api/src/schemas.py`:

```python
class SectorSignal(BaseModel):
    sector: str
    summary: str
    signal: Literal["bullish", "bearish", "neutral"]


class WatchMarket(BaseModel):
    symbol: str
    name: str
    sector: str
    confluence_score: float
    reason: str


class DigestResponse(BaseModel):
    generated_at: datetime
    macro_narrative: str
    sector_signals: list[SectorSignal]
    watch_markets: list[WatchMarket]
```

- [ ] **Step 2: Update imports in `main.py`**

Find the existing schemas import block in `main.py` and add the three new types:

```python
from .schemas import (
    # ... existing imports ...
    SectorSignal, WatchMarket, DigestResponse,
)
```

- [ ] **Step 3: Add `macro_only` to both `/news` endpoints**

In `news_for_symbol` (line ~332), add param and filter:

```python
@app.get("/news/{symbol}", response_model=NewsResponse)
def news_for_symbol(
    symbol: str,
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    limit: int | None = Query(default=None),
    macro_only: bool = Query(default=False),
) -> NewsResponse:
```

After the existing date-range filter, add before building `items`:
```python
    if macro_only:
        sub = sub[sub["source_category"].isin(["macro", "agency"])]
```

Apply the same `macro_only: bool = Query(default=False)` param and filter to `news_all` (line ~394).

- [ ] **Step 4: Add `/intelligence/digest` and `/intelligence/refresh` endpoints**

Add after the `synthesis_endpoint` function in `main.py`:

```python
# ── /intelligence/digest ──────────────────────────────────────────────────
@app.get("/intelligence/digest", response_model=DigestResponse)
def intelligence_digest_endpoint() -> DigestResponse:
    from ingest.intelligence import load_or_generate_digest  # noqa: PLC0415
    b = _bundle()
    data = load_or_generate_digest(b.annotated, b.news_df, b.synthesis, CACHE_DIR)

    from ingest.universe import UNIVERSE as _UNI  # noqa: PLC0415
    name_map = {c.symbol: c.name for c in _UNI}
    sec_map  = {c.symbol: c.sector for c in _UNI}

    watch: list[WatchMarket] = []
    for wm in data.get("watch_markets", []):
        sym = wm.get("symbol", "")
        watch.append(WatchMarket(
            symbol=sym,
            name=name_map.get(sym, sym),
            sector=sec_map.get(sym, ""),
            confluence_score=float(b.synthesis.get(sym, {}).get("confluence_score", 0.0)),
            reason=wm.get("reason", ""),
        ))

    generated_at_str = data.get("generated_at", datetime.utcnow().isoformat())
    try:
        generated_at = datetime.fromisoformat(generated_at_str.replace("Z", "+00:00"))
    except Exception:
        generated_at = datetime.utcnow()

    return DigestResponse(
        generated_at=generated_at,
        macro_narrative=data.get("macro_narrative", ""),
        sector_signals=[SectorSignal(**s) for s in data.get("sector_signals", [])],
        watch_markets=watch,
    )


@app.post("/intelligence/refresh")
def intelligence_refresh_endpoint() -> dict:
    from ingest.intelligence import load_or_generate_digest  # noqa: PLC0415
    b = _bundle()
    load_or_generate_digest(b.annotated, b.news_df, b.synthesis, CACHE_DIR, force=True)
    return {"ok": True}
```

- [ ] **Step 5: Verify imports compile**

```bash
cd /Users/praveen/Projects/cot-dashboard && .venv/bin/python -c "
import sys; sys.path.insert(0,'packages')
from apps.api.src.main import app
routes = [r.path for r in app.routes if hasattr(r,'path')]
print('digest route:', '/intelligence/digest' in routes)
print('refresh route:', '/intelligence/refresh' in routes)
" 2>&1
```

Expected:
```
digest route: True
refresh route: True
```

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/schemas.py apps/api/src/main.py
git commit -m "feat: add /intelligence/digest + /intelligence/refresh endpoints, macro_only on /news"
```

---

## Task 3: TypeScript types + API client

**Files:**
- Modify: `apps/web/src/lib/api/types.ts`
- Modify: `apps/web/src/lib/api/client.ts`

- [ ] **Step 1: Add types to `types.ts`**

Append to the end of `apps/web/src/lib/api/types.ts`:

```typescript
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
```

- [ ] **Step 2: Add import to `client.ts`**

In the existing import at the top of `apps/web/src/lib/api/client.ts`, add the three new types:

```typescript
import type {
	// ... existing types ...
	DigestResponse,
	SectorSignal,   // imported for completeness — used by DigestResponse
	WatchMarket,    // imported for completeness — used by DigestResponse
} from './types';
```

- [ ] **Step 3: Add methods to `client.ts`**

In the `api` object, add after `synthesis`:

```typescript
	digest: () =>
		get<DigestResponse>('/intelligence/digest'),
	newsAllMacro: (opts?: { limit?: number }) => {
		const qs = new URLSearchParams();
		qs.set('macro_only', 'true');
		if (opts?.limit) qs.set('limit', String(opts.limit));
		return get<NewsResponse>(`/news?${qs}`);
	},
```

- [ ] **Step 4: Run svelte-check**

```bash
cd /Users/praveen/Projects/cot-dashboard/apps/web && npx svelte-check --threshold error 2>&1 | tail -3
```

Expected: `0 errors 0 warnings`

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/lib/api/types.ts apps/web/src/lib/api/client.ts
git commit -m "feat: add DigestResponse types + digest/newsAllMacro client methods"
```

---

## Task 4: Intelligence page — `/intelligence/+page.svelte`

**Files:**
- Create: `apps/web/src/routes/intelligence/+page.svelte`

- [ ] **Step 1: Create the route directory**

```bash
mkdir -p /Users/praveen/Projects/cot-dashboard/apps/web/src/routes/intelligence
```

- [ ] **Step 2: Create `+page.svelte`**

```svelte
<!-- apps/web/src/routes/intelligence/+page.svelte -->
<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { api } from '$api/client';
	import type {
		DigestResponse, SynthesisResponse, MarketDetail, NewsItem, ZoneKey
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
		await loadDigest();
		// Auto-select from URL ?sym=
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
			<!-- Macro narrative -->
			<section class="digest-card">
				<div class="card-label">This week's macro narrative</div>
				<p class="narrative">{digest.macro_narrative}</p>
			</section>

			<!-- Sector signals -->
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

			<!-- Watch markets -->
			<section class="digest-card">
				<div class="card-label">Top markets · click to analyse</div>
				{#each digest.watch_markets as wm, i}
					<button
						class="watch-row"
						class:active={selectedSym === wm.symbol}
						onclick={() => selectMarket(wm.symbol)}
					>
						<span class="wm-rank num">{String(i + 1).padStart(2,'0')}</span>
						<span class="wm-sym num">{wm.symbol}</span>
						<span class="wm-reason">{wm.reason}</span>
						<span class="wm-score num">{wm.confluence_score.toFixed(2)}</span>
						<span class="wm-arrow">›</span>
					</button>
				{/each}
			</section>

			<!-- Global macro news -->
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
				<div class="skeleton-stack">
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
				<!-- Market header -->
				<header class="mkt-header">
					<div>
						<div class="mkt-sym num">{detail.contract.symbol} · {detail.contract.name}</div>
						<div class="mkt-sub">{detail.contract.sector} · {detail.contract.market_type ?? 'physical'} · {detail.contract.cftc_code}</div>
					</div>
					<div class="mkt-badges">
						{#each activeZones as z}
							<ZoneBadge zone={z} magnitude={lastBar?.[`${z}_mag`] ?? 0} />
						{/each}
					</div>
				</header>

				<!-- Confluence strip -->
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

				<!-- COT breakdown -->
				{#if lastBar}
					<section class="analysis-section">
						<div class="section-label">COT breakdown</div>
						<div class="cot-grid">
							{@const commNet = (lastBar.pm_long ?? 0) + (lastBar.sd_long ?? 0) - (lastBar.pm_short ?? 0) - (lastBar.sd_short ?? 0)}
							{@const specNet = (lastBar.mm_long ?? lastBar.lf_long ?? 0) - (lastBar.mm_short ?? lastBar.lf_short ?? 0)}
							{@const divWeeks = lastBar.comm_spec_divergence || lastBar.am_lf_divergence || 0}
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
								{@const nrNet = (lastBar.nr_long ?? 0) - (lastBar.nr_short ?? 0)}
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

				<!-- DeepSeek analysis -->
				<section class="analysis-section">
					<div class="section-label">DeepSeek analysis</div>
					<p class="summary-text">{synthesis.summary}</p>
				</section>

				<!-- Dual news feed -->
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

				<!-- Watch -->
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

	/* ── Left ── */
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
	}
	.eyebrow { font-size: var(--fs-11); text-transform: uppercase; letter-spacing: .06em; color: var(--ink-faint); }
	.title { font-size: var(--fs-20); font-weight: 600; margin: 2px 0 0; }
	.header-meta { display: flex; flex-direction: column; align-items: flex-end; gap: 4px; }
	.ai-badge { font-size: 9px; font-family: var(--font-mono); padding: 2px 7px; border-radius: 99px; background: rgba(183,148,246,.08); color: var(--zone-a2); border: 1px solid rgba(183,148,246,.2); }
	.date { font-size: var(--fs-11); color: var(--ink-faint); }

	.skeleton-stack { display: flex; flex-direction: column; gap: 8px; padding: var(--sp-4) 0; }

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

	.nm-row { display: flex; align-items: flex-start; gap: 6px; padding: 5px 12px; border-bottom: 1px solid var(--border-soft); }
	.nm-row:last-child { border-bottom: none; }
	.nm-type { font-size: 9px; padding: 1px 5px; border-radius: 3px; font-family: var(--font-mono); flex-shrink: 0; margin-top: 2px; }
	.nm-macro { background: rgba(183,148,246,.15); color: var(--zone-a2); }
	.nm-agency { background: rgba(183,148,246,.15); color: var(--zone-a2); }
	.nm-market { background: rgba(79,209,197,.12); color: var(--zone-a3); }
	.nm-title { flex: 1; font-size: 11px; color: var(--ink-muted); line-height: 1.4; }
	.nm-score { font-size: 10px; flex-shrink: 0; }

	.refresh-btn { background: var(--bg-panel); border: 1px solid var(--border); border-radius: var(--r-sm); padding: 6px 12px; font-size: var(--fs-12); color: var(--ink-muted); cursor: pointer; width: 100%; }
	.refresh-btn:hover { color: var(--ink); border-color: var(--border); background: var(--bg-hover); }

	/* ── Right ── */
	.right { overflow-y: auto; scrollbar-width: thin; scrollbar-color: var(--border) transparent; }
	.right-empty, .right-loading { display: flex; align-items: center; justify-content: center; height: 100%; }
	.right-loading .skeleton-stack { width: 480px; gap: 12px; }

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
	.empty-text { padding: 8px 10px; font-size: 11px; color: var(--ink-faint); }

	.watch-box { display: flex; gap: var(--sp-2); padding: var(--sp-3); background: rgba(245,166,35,.06); border: 1px solid rgba(245,166,35,.2); border-radius: var(--r-sm); }
	.watch-icon { font-size: 14px; }
	.watch-text { font-size: var(--fs-12); color: var(--ink-muted); line-height: 1.55; }
	.watch-text strong { color: var(--pending); }

	.disclaimer { font-size: 10px; color: var(--ink-faint); padding-top: var(--sp-2); border-top: 1px solid var(--border-soft); }
</style>
```

- [ ] **Step 3: Run svelte-check**

```bash
cd /Users/praveen/Projects/cot-dashboard/apps/web && npx svelte-check --threshold error 2>&1 | tail -3
```

Expected: `0 errors 0 warnings`

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/routes/intelligence/
git commit -m "feat: add /intelligence combined digest + per-market synthesis page"
```

---

## Task 5: Sidebar route + market detail deep-link

**Files:**
- Modify: `apps/web/src/routes/+layout.svelte` — add Intelligence to routes
- Modify: `apps/web/src/routes/market/[symbol]/+page.svelte` — add AI Analysis link

- [ ] **Step 1: Add route to sidebar**

In `apps/web/src/routes/+layout.svelte`, find:
```typescript
const routes = [
    { href: '/', label: 'Today', short: 'TD' },
    { href: '/heatmap', label: 'Heatmap', short: 'HM' },
    { href: '/divergence', label: 'Divergence', short: 'DV' }
```

Add the Intelligence entry:
```typescript
const routes = [
    { href: '/', label: 'Today', short: 'TD' },
    { href: '/heatmap', label: 'Heatmap', short: 'HM' },
    { href: '/divergence', label: 'Divergence', short: 'DV' },
    { href: '/intelligence', label: 'Intelligence', short: 'AI' }
```

- [ ] **Step 2: Add deep-link to market detail page**

In `apps/web/src/routes/market/[symbol]/+page.svelte`, find the `<header class="header">` section. After the existing zone badges or sector eyebrow, add the AI analysis link. Read the file first to find the exact location, then add:

```svelte
<a href={`/intelligence?sym=${symbol}`} class="ai-link">
    ✦ AI Analysis
</a>
```

Add the corresponding CSS in the `<style>` block:
```css
.ai-link {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 3px 10px;
    border-radius: var(--r-sm);
    font-size: var(--fs-11);
    color: var(--zone-a2);
    background: rgba(183,148,246,.08);
    border: 1px solid rgba(183,148,246,.2);
    transition: background .12s;
}
.ai-link:hover {
    background: rgba(183,148,246,.16);
}
```

- [ ] **Step 3: Run svelte-check**

```bash
cd /Users/praveen/Projects/cot-dashboard/apps/web && npx svelte-check --threshold error 2>&1 | tail -3
```

Expected: `0 errors 0 warnings`

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/routes/+layout.svelte apps/web/src/routes/market/
git commit -m "feat: add Intelligence to sidebar nav + AI Analysis link on market detail"
```

---

## Task 6: Smoke test

- [ ] **Step 1: Verify API endpoint (API must be running on :8000)**

```bash
cd /Users/praveen/Projects/cot-dashboard && curl -sS http://127.0.0.1:8000/intelligence/digest | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f'generated_at: {d[\"generated_at\"]}')
print(f'narrative len: {len(d[\"macro_narrative\"])} chars')
print(f'sectors: {[s[\"sector\"] for s in d[\"sector_signals\"]]}')
print(f'watch markets: {[w[\"symbol\"] for w in d[\"watch_markets\"]]}')
"
```

Expected: narrative text, list of sectors, list of symbols. (If HF_TOKEN not set, narrative will be empty — that is correct.)

- [ ] **Step 2: Verify `/news` macro_only filter**

```bash
curl -sS 'http://127.0.0.1:8000/news?macro_only=true&limit=3' | python3 -c "
import sys, json
d = json.load(sys.stdin)
cats = {i['source_category'] for i in d['items']}
print(f'source_categories: {cats}')
assert cats.issubset({'macro','agency'}), f'unexpected categories: {cats}'
print('PASS: only macro/agency sources returned')
"
```

Expected: `PASS: only macro/agency sources returned`

- [ ] **Step 3: Verify svelte-check clean**

```bash
cd /Users/praveen/Projects/cot-dashboard/apps/web && npx svelte-check --threshold error 2>&1 | tail -3
```

Expected: `0 errors 0 warnings`

- [ ] **Step 4: Tag complete**

```bash
git tag intelligence-complete
```

---

## Self-Review

**Spec coverage:**
- ✅ §2 Layout — two-panel page with 340px left, flex-fill right
- ✅ §3 GET /intelligence/digest — Task 2
- ✅ §3 POST /intelligence/refresh — Task 2
- ✅ §3 /news macro_only — Task 2
- ✅ §4 intelligence.py — Task 1
- ✅ §5 +page.svelte — Task 4
- ✅ §5 sidebar route — Task 5
- ✅ §5 market detail deep-link — Task 5
- ✅ §5 TypeScript types — Task 3
- ✅ §5 client methods — Task 3
- ✅ §9 Open question 1 (macro_only) — Task 2, answered and implemented
- ✅ §9 Open question 2 (refresh button) — Task 4, "↻ Regenerate digest" button calls POST /intelligence/refresh
- ✅ §9 Open question 3 (skeleton loaders) — Task 4, skeleton loading state on right panel

**Type consistency check:**
- `DigestResponse` defined in Task 2 (schemas.py) → used in Task 3 (types.ts) → used in Task 4 (+page.svelte) ✅
- `WatchMarket` has `symbol`, `name`, `sector`, `confluence_score`, `reason` — consistent across schemas.py → types.ts → page ✅
- `load_or_generate_digest` signature in Task 1 matches call in Task 2 (main.py) ✅
- `api.digest()` returns `DigestResponse` — consistent between client.ts and page ✅
