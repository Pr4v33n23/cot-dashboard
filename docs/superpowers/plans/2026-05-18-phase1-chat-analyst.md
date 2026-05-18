# Phase 1 — Chat AI Analyst Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `/chat` route with a natural language interface grounded in live COT bundle data, allowing traders to ask questions like "what are the three most interesting setups right now?" and receive data-cited answers from DeepSeek-V4-Pro.

**Architecture:** A `context_builder.py` module compresses the live Bundle into a ~3K-token structured JSON snapshot (top markets by confluence, sector signals, macro news). A `POST /chat` endpoint prepends this snapshot as the system context, then calls DeepSeek-V4-Pro via the HF router. The frontend is a full-screen chat UI with conversation history kept client-side, auto-scroll, quick-start prompts, and clickable market symbol chips that deep-link to market detail pages.

**Tech Stack:** Python, FastAPI (SSE streaming), SvelteKit 5 (Svelte runes), openai client (HF router), existing `_ai.py`

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `packages/ingest/context_builder.py` | Compress Bundle → compact JSON context for DeepSeek |
| Create | `tests/ingest/test_context_builder.py` | Tests for context builder |
| Modify | `apps/api/src/schemas.py` | Add ChatMessage, ChatRequest, ChatResponse |
| Create | `apps/api/src/chat.py` | Chat endpoint logic — system prompt + DeepSeek call |
| Modify | `apps/api/src/main.py` | Add POST /chat endpoint |
| Modify | `apps/web/src/lib/api/types.ts` | Add ChatMessage, ChatResponse types |
| Modify | `apps/web/src/lib/api/client.ts` | Add chat() method |
| Create | `apps/web/src/routes/chat/+page.svelte` | Full chat UI |
| Modify | `apps/web/src/routes/+layout.svelte` | Add Chat to sidebar routes |

---

## Task 1: `context_builder.py` — Bundle → compact context

**Files:**
- Create: `packages/ingest/context_builder.py`
- Create: `tests/ingest/test_context_builder.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/ingest/test_context_builder.py
from __future__ import annotations
import pandas as pd
import pytest
from ingest.context_builder import build_context, CONTEXT_KEYS


def _make_bundle_stub():
    """Minimal stub with the same shape as a real Bundle."""
    class B:
        today_df = pd.DataFrame({
            "symbol": ["CL", "HG", "ZS"],
            "sector": ["energy", "metals", "grains"],
            "n_zones": [3, 2, 1],
            "total_mag": [1.8, 1.2, 0.6],
            "zones_on": [["A1","A4","A5"], ["A1","A3"], ["A2"]],
            "cot_index_comm": [91.4, 85.2, 62.1],
        })
        synthesis = {
            "CL": {"confluence_score": 0.84, "key_factors": ["extreme commercial long"], "summary": "x", "watch": "y"},
            "HG": {"confluence_score": 0.75, "key_factors": ["OI expansion"], "summary": "x", "watch": "y"},
            "ZS": {"confluence_score": 0.50, "key_factors": [], "summary": "", "watch": ""},
        }
        news_df = pd.DataFrame({
            "title": ["OPEC cuts production", "EIA draw 3M bbl"],
            "source": ["OPEC", "EIA"],
            "source_category": ["macro", "macro"],
            "date": pd.to_datetime(["2026-05-17", "2026-05-16"]),
            "sentiment_score": [0.82, 0.61],
            "markets": [["CL", "HG"], ["CL"]],
        })
        annotated = {}
        retail_df = pd.DataFrame(columns=["symbol","long_pct","short_pct","source","timestamp"])
    return B()


def test_build_context_has_required_keys():
    ctx = build_context(_make_bundle_stub())
    for k in CONTEXT_KEYS:
        assert k in ctx, f"missing key: {k}"


def test_top_markets_sorted_by_confluence():
    ctx = build_context(_make_bundle_stub())
    scores = [m["confluence_score"] for m in ctx["top_markets"]]
    assert scores == sorted(scores, reverse=True)


def test_top_markets_capped():
    ctx = build_context(_make_bundle_stub())
    assert len(ctx["top_markets"]) <= 15


def test_macro_news_present():
    ctx = build_context(_make_bundle_stub())
    assert isinstance(ctx["macro_news"], list)
    assert len(ctx["macro_news"]) > 0


def test_context_serialisable():
    import json
    ctx = build_context(_make_bundle_stub())
    # Must be JSON-serialisable — DeepSeek receives it as a string
    json.dumps(ctx)


def test_sector_summary_present():
    ctx = build_context(_make_bundle_stub())
    assert isinstance(ctx["sector_summary"], dict)
```

- [ ] **Step 2: Run — verify fails**

```bash
cd /Users/praveen/Projects/cot-dashboard && .venv/bin/python -m pytest tests/ingest/test_context_builder.py -v 2>&1 | tail -5
```

Expected: `ModuleNotFoundError: No module named 'ingest.context_builder'`

- [ ] **Step 3: Implement `context_builder.py`**

```python
# packages/ingest/context_builder.py
"""Compress a live Bundle into a compact context JSON for DeepSeek.

Target: ~3 000 tokens maximum so the full conversation history + response fits
within the model's context window without truncation.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any

import pandas as pd

CONTEXT_KEYS = ("date", "top_markets", "sector_summary", "macro_news", "universe_size")
_MAX_MARKETS = 15
_MAX_NEWS = 8


def build_context(bundle: Any) -> dict:
    """Build a compact context dict from a Bundle object.

    Works with a real Bundle or any stub that has the same attributes.
    """
    date_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    # ── Top markets by confluence ─────────────────────────────────────────
    top_markets: list[dict] = []
    if not bundle.today_df.empty:
        for _, row in bundle.today_df.iterrows():
            sym = row["symbol"]
            synth = (bundle.synthesis or {}).get(sym, {})
            confluence = float(synth.get("confluence_score", 0) or 0)
            top_markets.append({
                "symbol": sym,
                "sector": str(row.get("sector", "")),
                "n_zones": int(row.get("n_zones", 0) or 0),
                "zones_on": list(row.get("zones_on", []) or []),
                "cot_index": round(float(row.get("cot_index_comm", 50) or 50), 1),
                "confluence_score": round(confluence, 2),
                "key_factors": list(synth.get("key_factors", [])[:3]),
                "regime": str(synth.get("regime", "")),
            })
        top_markets.sort(key=lambda x: x["confluence_score"], reverse=True)
        top_markets = top_markets[:_MAX_MARKETS]

    # ── Sector summary ────────────────────────────────────────────────────
    sector_summary: dict[str, dict] = {}
    if not bundle.today_df.empty:
        for sector, grp in bundle.today_df.groupby("sector"):
            avg_cot = grp["cot_index_comm"].dropna().mean()
            avg_zones = grp["n_zones"].mean()
            sector_summary[str(sector)] = {
                "avg_cot_index": round(float(avg_cot), 1) if not pd.isna(avg_cot) else 50.0,
                "avg_zones": round(float(avg_zones), 1),
                "n_markets": len(grp),
            }

    # ── Macro news (last 8 scheduled-event headlines) ────────────────────
    macro_news: list[dict] = []
    if not bundle.news_df.empty and "source_category" in bundle.news_df.columns:
        macro = bundle.news_df[
            bundle.news_df["source_category"].isin(["macro", "agency"])
        ].sort_values("date", ascending=False).head(_MAX_NEWS)
        for _, row in macro.iterrows():
            macro_news.append({
                "source": str(row.get("source", "")),
                "title": str(row.get("title", ""))[:140],
                "date": str(row.get("date", ""))[:10],
                "sentiment_score": round(float(row.get("sentiment_score", 0) or 0), 2),
                "markets": list(row.get("markets", []) or [])[:4],
            })

    # ── Universe size ─────────────────────────────────────────────────────
    universe_size = len(bundle.annotated) if bundle.annotated else 0

    return {
        "date": date_str,
        "top_markets": top_markets,
        "sector_summary": sector_summary,
        "macro_news": macro_news,
        "universe_size": universe_size,
    }


def context_to_str(ctx: dict) -> str:
    """Render context as a compact string for injection into the system prompt."""
    import json  # noqa: PLC0415
    return json.dumps(ctx, separators=(",", ":"))
```

- [ ] **Step 4: Run tests — verify all 6 pass**

```bash
cd /Users/praveen/Projects/cot-dashboard && .venv/bin/python -m pytest tests/ingest/test_context_builder.py -v 2>&1 | tail -10
```

Expected: 6 passed.

- [ ] **Step 5: Run full suite — no regressions**

```bash
.venv/bin/python -m pytest tests/ --tb=short 2>&1 | tail -5
```

Expected: all 51 tests pass.

- [ ] **Step 6: Commit + push**

```bash
git add packages/ingest/context_builder.py tests/ingest/test_context_builder.py
git commit -m "feat: add context_builder — Bundle → compact DeepSeek context"
git push
```

---

## Task 2: Chat schemas + `chat.py` backend logic

**Files:**
- Modify: `apps/api/src/schemas.py` — append ChatMessage, ChatRequest, ChatResponse
- Create: `apps/api/src/chat.py` — system prompt + DeepSeek call

- [ ] **Step 1: Add schemas to `schemas.py`**

Append to the end of `apps/api/src/schemas.py`:

```python
class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]   # conversation history from client
    stream: bool = False


class ChatResponse(BaseModel):
    reply: str
    cited_markets: list[str] = Field(default_factory=list)
    context_date: str | None = None
```

- [ ] **Step 2: Create `apps/api/src/chat.py`**

```python
# apps/api/src/chat.py
"""Chat endpoint logic — grounded DeepSeek analyst over live COT bundle."""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

_PACKAGES = str(Path(__file__).resolve().parents[3] / "packages")
if _PACKAGES not in sys.path:
    sys.path.insert(0, _PACKAGES)

from ingest._ai import available, chat as ai_chat  # noqa: E402
from ingest.context_builder import build_context, context_to_str  # noqa: E402

_SYSTEM_TEMPLATE = """You are COT_LENS Analyst — a professional futures market analyst assistant grounded in live CFTC Commitment of Traders data.

TODAY'S LIVE DATA SNAPSHOT ({date}, {universe_size} markets loaded):
{context}

YOUR RULES:
1. ALWAYS ground answers in the data snapshot above. Quote specific values: COT index numbers, confluence scores, zone names, divergence weeks.
2. When you mention a market, format its symbol in CAPS (CL, HG, ZS etc.) — the UI will auto-link them.
3. Never invent data not in the snapshot. If you don't have something, say so.
4. Physical commodities: use Williams/Briese commercial-hedger framing (commercials = smart money, specs = trend-followers).
5. Financial contracts (FX, indices, rates): use institutional flow framing (Dealers = sell-side hedge, Asset Managers = long-only, Leveraged Funds = directional specs).
6. Always clarify: COT positioning is CONTEXT for analysis, not a trade signal.
7. Be specific and concise. Traders don't want padding.
8. If asked to compare to history, note that historical analog analysis requires the dedicated /extremes tool (coming soon).

TONE: Direct, professional, data-driven. Like a Goldman desk analyst, not a chatbot."""


def build_system_prompt(bundle_context: dict) -> str:
    ctx_str = context_to_str(bundle_context)
    return _SYSTEM_TEMPLATE.format(
        date=bundle_context.get("date", ""),
        universe_size=bundle_context.get("universe_size", 0),
        context=ctx_str,
    )


def extract_cited_markets(text: str) -> list[str]:
    """Extract market symbols mentioned in the response (e.g. CL, HG, EURUSD)."""
    return list(dict.fromkeys(re.findall(r'\b([A-Z]{2,7})\b', text)))


def answer(messages: list[dict], bundle) -> tuple[str, list[str], str]:
    """Call DeepSeek with context + conversation history.

    Returns: (reply_text, cited_markets, context_date)
    """
    ctx = build_context(bundle)
    system_prompt = build_system_prompt(ctx)

    full_messages = [
        {"role": "system", "content": system_prompt},
        *[{"role": m["role"], "content": m["content"]} for m in messages],
    ]

    if not available():
        fallback = _deterministic_answer(messages, ctx)
        return fallback, extract_cited_markets(fallback), ctx.get("date", "")

    reply = ai_chat(full_messages, temperature=0.3)
    if not reply:
        reply = _deterministic_answer(messages, ctx)

    cited = extract_cited_markets(reply)
    return reply, cited, ctx.get("date", "")


def _deterministic_answer(messages: list[dict], ctx: dict) -> str:
    """Rule-based fallback answer when AI is unavailable."""
    last_msg = messages[-1]["content"].lower() if messages else ""
    markets = ctx.get("top_markets", [])

    if not markets:
        return "No market data loaded yet. Try again in a moment."

    if any(w in last_msg for w in ("interesting", "best", "top", "watch", "setup")):
        top = markets[:3]
        lines = [f"Top setups right now (deterministic scoring, AI offline):"]
        for i, m in enumerate(top, 1):
            lines.append(
                f"{i}. **{m['symbol']}** ({m['sector']}) — confluence {m['confluence_score']:.2f}, "
                f"COT index {m['cot_index']}, zones: {', '.join(m['zones_on']) or 'none'}"
            )
        return "\n".join(lines)

    top5 = ", ".join(m["symbol"] for m in markets[:5])
    return (
        f"AI synthesis is currently offline (HuggingFace credits). "
        f"Top markets by deterministic confluence: {top5}. "
        f"Check the Intelligence page for full breakdowns."
    )
```

- [ ] **Step 3: Verify import**

```bash
cd /Users/praveen/Projects/cot-dashboard && PYTHONPATH=packages .venv/bin/python -c "
from apps.api.src.chat import answer, build_system_prompt
print('chat.py import OK')
" 2>&1
```

Expected: `chat.py import OK`

- [ ] **Step 4: Commit + push**

```bash
git add apps/api/src/schemas.py apps/api/src/chat.py
git commit -m "feat: add chat schemas + DeepSeek analyst backend with context grounding"
git push
```

---

## Task 3: `POST /chat` endpoint in `main.py`

**Files:**
- Modify: `apps/api/src/main.py`

- [ ] **Step 1: Add import and endpoint**

In `apps/api/src/main.py`, add to the imports from `.schemas`:
```python
    ChatMessage, ChatRequest, ChatResponse,
```

Add to imports at top of file:
```python
from .chat import answer as chat_answer
```

Add the endpoint after `intelligence_refresh_endpoint`:

```python
# ── /chat ─────────────────────────────────────────────────────────────────
@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(req: ChatRequest) -> ChatResponse:
    """Natural language analyst grounded in live COT bundle data."""
    b = _bundle()
    messages = [{"role": m.role, "content": m.content} for m in req.messages]
    reply, cited, ctx_date = chat_answer(messages, b)
    return ChatResponse(reply=reply, cited_markets=cited, context_date=ctx_date)
```

- [ ] **Step 2: Verify endpoint registered**

```bash
cd /Users/praveen/Projects/cot-dashboard && PYTHONPATH=packages .venv/bin/python -c "
import sys; sys.path.insert(0,'packages')
from apps.api.src.main import app
routes = {r.path for r in app.routes if hasattr(r,'path')}
assert '/chat' in routes, '/chat missing'
print('OK — /chat registered')
" 2>&1
```

Expected: `OK — /chat registered`

- [ ] **Step 3: Commit + push**

```bash
git add apps/api/src/main.py
git commit -m "feat: add POST /chat endpoint for AI analyst"
git push
```

---

## Task 4: TypeScript types + API client method

**Files:**
- Modify: `apps/web/src/lib/api/types.ts`
- Modify: `apps/web/src/lib/api/client.ts`

- [ ] **Step 1: Add types to `types.ts`**

Append to the end of `apps/web/src/lib/api/types.ts`:

```typescript
export interface ChatMessage {
	role: 'user' | 'assistant' | 'system';
	content: string;
}

export interface ChatResponse {
	reply: string;
	cited_markets: string[];
	context_date: string | null;
}
```

- [ ] **Step 2: Add `chat()` to `client.ts`**

In the `api` object, add after `newsAllMacro`:

```typescript
	chat: (messages: ChatMessage[]) =>
		post<ChatResponse>('/chat', { messages }),
```

Also add a `post` helper above the `get` function if not already present. Read the file first — if there's only `get`, add `post` above the `api` object:

```typescript
async function post<T>(path: string, body: unknown): Promise<T> {
	const res = await fetch(`${BASE}${path}`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
		body: JSON.stringify(body),
	});
	if (!res.ok) throw new ApiError(res.status, `${res.status} ${res.statusText} on POST ${path}`);
	return (await res.json()) as T;
}
```

Add `ChatMessage, ChatResponse` to the import at the top of `client.ts`.

- [ ] **Step 3: Run svelte-check**

```bash
cd /Users/praveen/Projects/cot-dashboard/apps/web && npx svelte-check --threshold error 2>&1 | tail -3
```

Expected: `0 errors 0 warnings`

- [ ] **Step 4: Commit + push**

```bash
git add apps/web/src/lib/api/types.ts apps/web/src/lib/api/client.ts
git commit -m "feat: add ChatMessage/ChatResponse types + chat() client method"
git push
```

---

## Task 5: `/chat/+page.svelte` — full chat UI

**Files:**
- Create: `apps/web/src/routes/chat/+page.svelte`

- [ ] **Step 1: Create the route directory**

```bash
mkdir -p /Users/praveen/Projects/cot-dashboard/apps/web/src/routes/chat
```

- [ ] **Step 2: Create `+page.svelte`**

Write the complete file:

```svelte
<!-- apps/web/src/routes/chat/+page.svelte -->
<script lang="ts">
	import { tick } from 'svelte';
	import { api } from '$api/client';
	import type { ChatMessage } from '$api/types';

	interface Message {
		role: 'user' | 'assistant';
		content: string;
		cited: string[];
		loading?: boolean;
		error?: boolean;
	}

	let messages = $state<Message[]>([]);
	let input = $state('');
	let sending = $state(false);
	let scrollEl: HTMLElement;
	let inputEl: HTMLTextAreaElement;
	let contextDate = $state<string | null>(null);

	const QUICK_STARTS = [
		"What are the 3 most interesting setups right now?",
		"Which energy markets have extreme commercial positioning?",
		"Compare the current grain complex COT picture.",
		"Which FX pairs have the biggest institutional divergences?",
		"What macro events this week are most relevant to metals?",
		"Where are commercials at multi-year extremes across all sectors?",
	];

	async function send() {
		const text = input.trim();
		if (!text || sending) return;
		input = '';
		sending = true;

		messages.push({ role: 'user', content: text, cited: [] });
		messages.push({ role: 'assistant', content: '', cited: [], loading: true });
		await scrollToBottom();

		try {
			const history: ChatMessage[] = messages
				.filter(m => !m.loading)
				.map(m => ({ role: m.role, content: m.content }));
			history.push({ role: 'user', content: text });

			const resp = await api.chat(history);
			contextDate = resp.context_date;

			// Replace loading bubble with real response
			const idx = messages.findLastIndex(m => m.loading);
			if (idx !== -1) {
				messages[idx] = {
					role: 'assistant',
					content: resp.reply,
					cited: resp.cited_markets,
					loading: false,
				};
			}
		} catch (e) {
			const idx = messages.findLastIndex(m => m.loading);
			if (idx !== -1) {
				messages[idx] = {
					role: 'assistant',
					content: `Error: ${(e as Error).message}`,
					cited: [],
					loading: false,
					error: true,
				};
			}
		} finally {
			sending = false;
			await scrollToBottom();
			inputEl?.focus();
		}
	}

	async function scrollToBottom() {
		await tick();
		scrollEl?.scrollTo({ top: scrollEl.scrollHeight, behavior: 'smooth' });
	}

	function onKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			send();
		}
	}

	function usePrompt(p: string) {
		input = p;
		inputEl?.focus();
	}

	// Linkify [SYMBOL] patterns in assistant messages
	function renderContent(text: string): string {
		// Bold **text**
		let html = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
		// Market symbols → clickable chips
		html = html.replace(/\b([A-Z]{2,7})\b/g, (match) => {
			const known = ['CL','NG','RB','HO','BZ','GC','SI','HG','PL','PA','ALI',
				'ZC','ZS','ZW','KE','ZO','ZM','ZL','ZR','CC','KC','CT','SB','OJ','LBS',
				'LE','GF','HE','ES','NQ','YM','RTY','MES','MNQ','NIY',
				'ZB','ZN','ZF','ZT','FF','SR3',
				'EURUSD','GBPUSD','JPYUSD','AUDUSD','CADUSD','CHFUSD','NZDUSD',
				'MXNUSD','BRLUSD','NOKUSD','SEKUSD'];
			if (known.includes(match)) {
				return `<a href="/market/${match}" class="sym-chip" data-sveltekit-preload-data="hover">${match}</a>`;
			}
			return match;
		});
		// Newlines → <br>
		html = html.replace(/\n/g, '<br>');
		return html;
	}
</script>

<svelte:head>
	<title>Chat Analyst · COT_LENS</title>
</svelte:head>

<div class="page">
	<header class="chat-header">
		<div>
			<div class="eyebrow">AI analyst</div>
			<h1 class="title">Chat</h1>
		</div>
		<div class="header-right">
			<span class="ai-badge">DeepSeek-V4-Pro</span>
			{#if contextDate}
				<span class="ctx-date num">data: {contextDate}</span>
			{/if}
		</div>
	</header>

	<!-- Messages -->
	<div class="messages" bind:this={scrollEl}>
		{#if messages.length === 0}
			<!-- Welcome + quick-starts -->
			<div class="welcome">
				<div class="welcome-title">Ask me anything about COT positioning</div>
				<div class="welcome-sub">Grounded in live data across {47} futures markets. Click a prompt or type your question.</div>
				<div class="quick-starts">
					{#each QUICK_STARTS as p}
						<button class="qs-btn" onclick={() => usePrompt(p)}>{p}</button>
					{/each}
				</div>
			</div>
		{:else}
			{#each messages as msg}
				<div class="msg" class:user={msg.role === 'user'} class:assistant={msg.role === 'assistant'} class:error-msg={msg.error}>
					{#if msg.role === 'assistant'}
						<div class="msg-avatar">AI</div>
					{/if}
					<div class="msg-body">
						{#if msg.loading}
							<div class="typing-indicator">
								<span></span><span></span><span></span>
							</div>
						{:else}
							<!-- eslint-disable-next-line svelte/no-at-html-tags -->
							<div class="msg-text">{@html renderContent(msg.content)}</div>
							{#if msg.cited.length > 0 && msg.role === 'assistant'}
								<div class="cited">
									{#each [...new Set(msg.cited)].slice(0,8) as sym}
										<a href="/market/{sym}" class="cited-chip num" data-sveltekit-preload-data="hover">{sym}</a>
									{/each}
								</div>
							{/if}
						{/if}
					</div>
					{#if msg.role === 'user'}
						<div class="msg-avatar user-avatar">U</div>
					{/if}
				</div>
			{/each}
		{/if}
	</div>

	<!-- Input -->
	<div class="input-bar">
		<textarea
			bind:this={inputEl}
			bind:value={input}
			onkeydown={onKeydown}
			placeholder="Ask about COT positioning, setups, sector analysis… (Enter to send, Shift+Enter for newline)"
			class="input-field"
			rows={2}
			disabled={sending}
		></textarea>
		<button class="send-btn" onclick={send} disabled={sending || !input.trim()}>
			{sending ? '…' : '↑'}
		</button>
	</div>
	<div class="disclaimer">COT_LENS is a positioning analysis tool. Nothing here is financial advice.</div>
</div>

<style>
	.page {
		display: flex;
		flex-direction: column;
		height: 100%;
		min-height: 0;
		overflow: hidden;
	}

	.chat-header {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		padding: var(--sp-6) var(--sp-6) var(--sp-4);
		border-bottom: 1px solid var(--border-soft);
		flex-shrink: 0;
	}
	.eyebrow { font-size: var(--fs-11); text-transform: uppercase; letter-spacing: .06em; color: var(--ink-faint); }
	.title { font-size: var(--fs-20); font-weight: 600; margin: 2px 0 0; }
	.header-right { display: flex; flex-direction: column; align-items: flex-end; gap: 4px; }
	.ai-badge { font-size: 9px; font-family: var(--font-mono); padding: 2px 7px; border-radius: 99px; background: rgba(183,148,246,.08); color: var(--zone-a2); border: 1px solid rgba(183,148,246,.2); }
	.ctx-date { font-size: 10px; color: var(--ink-faint); }

	.messages {
		flex: 1;
		overflow-y: auto;
		padding: var(--sp-6);
		display: flex;
		flex-direction: column;
		gap: var(--sp-4);
		scrollbar-width: thin;
		scrollbar-color: var(--border) transparent;
	}

	.welcome { display: flex; flex-direction: column; align-items: center; gap: var(--sp-4); padding: var(--sp-12) var(--sp-8); text-align: center; }
	.welcome-title { font-size: var(--fs-20); font-weight: 600; }
	.welcome-sub { font-size: var(--fs-13); color: var(--ink-muted); max-width: 520px; }
	.quick-starts { display: flex; flex-wrap: wrap; gap: var(--sp-2); justify-content: center; max-width: 680px; }
	.qs-btn { padding: 7px 14px; border-radius: var(--r-sm); border: 1px solid var(--border); background: var(--bg-panel); font-size: var(--fs-12); color: var(--ink-muted); cursor: pointer; text-align: left; transition: border-color .12s, color .12s; }
	.qs-btn:hover { border-color: var(--zone-a2); color: var(--ink); }

	.msg { display: flex; gap: var(--sp-3); align-items: flex-start; max-width: 800px; }
	.msg.user { align-self: flex-end; flex-direction: row-reverse; }
	.msg.assistant { align-self: flex-start; }

	.msg-avatar { width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 10px; font-family: var(--font-mono); font-weight: 700; flex-shrink: 0; margin-top: 2px; }
	.msg.assistant .msg-avatar { background: rgba(183,148,246,.15); color: var(--zone-a2); border: 1px solid rgba(183,148,246,.25); }
	.user-avatar { background: var(--border); color: var(--ink-muted); }

	.msg-body { display: flex; flex-direction: column; gap: 6px; }
	.msg.user .msg-text { background: var(--zone-a2); color: #0a0a0b; padding: 10px 14px; border-radius: 14px 14px 4px 14px; font-size: var(--fs-13); line-height: 1.55; }
	.msg.assistant .msg-text { background: var(--bg-panel); border: 1px solid var(--border); padding: 12px 16px; border-radius: 4px 14px 14px 14px; font-size: var(--fs-13); line-height: 1.7; color: var(--ink-muted); }
	.msg.assistant .msg-text :global(strong) { color: var(--ink); }
	.msg.assistant .msg-text :global(.sym-chip) { display: inline-flex; align-items: center; padding: 1px 6px; border-radius: 4px; font-size: 11px; font-family: var(--font-mono); font-weight: 700; background: rgba(79,209,197,.12); color: var(--zone-a3); border: 1px solid rgba(79,209,197,.3); text-decoration: none; margin: 0 1px; }
	.msg.assistant .msg-text :global(.sym-chip:hover) { background: rgba(79,209,197,.2); }
	.error-msg .msg-text { border-color: rgba(255,90,95,.3) !important; background: rgba(255,90,95,.06) !important; color: var(--short) !important; }

	.cited { display: flex; gap: 4px; flex-wrap: wrap; padding-left: 2px; }
	.cited-chip { font-size: 10px; font-family: var(--font-mono); padding: 2px 7px; border-radius: 99px; background: rgba(79,209,197,.08); color: var(--zone-a3); border: 1px solid rgba(79,209,197,.2); text-decoration: none; }
	.cited-chip:hover { background: rgba(79,209,197,.16); }

	.typing-indicator { display: flex; gap: 4px; align-items: center; padding: 12px 16px; background: var(--bg-panel); border: 1px solid var(--border); border-radius: 4px 14px 14px 14px; }
	.typing-indicator span { width: 6px; height: 6px; border-radius: 50%; background: var(--ink-faint); animation: bounce 1.2s infinite; }
	.typing-indicator span:nth-child(2) { animation-delay: .2s; }
	.typing-indicator span:nth-child(3) { animation-delay: .4s; }
	@keyframes bounce { 0%,60%,100%{transform:translateY(0)} 30%{transform:translateY(-6px)} }

	.input-bar {
		display: flex;
		gap: var(--sp-2);
		padding: var(--sp-4) var(--sp-6);
		border-top: 1px solid var(--border-soft);
		background: var(--bg-canvas);
		flex-shrink: 0;
	}
	.input-field {
		flex: 1;
		background: var(--bg-panel);
		border: 1px solid var(--border);
		border-radius: var(--r-md);
		color: var(--ink);
		font: inherit;
		font-size: var(--fs-13);
		line-height: 1.5;
		padding: 10px 14px;
		resize: none;
		outline: none;
		scrollbar-width: thin;
	}
	.input-field:focus { border-color: var(--zone-a2); }
	.input-field:disabled { opacity: 0.5; }
	.send-btn { width: 40px; height: 40px; border-radius: var(--r-sm); background: var(--zone-a2); color: #0a0a0b; border: none; font-size: 18px; font-weight: 700; cursor: pointer; flex-shrink: 0; align-self: flex-end; transition: opacity .12s; }
	.send-btn:disabled { opacity: 0.35; cursor: not-allowed; }
	.send-btn:not(:disabled):hover { opacity: 0.85; }

	.disclaimer { text-align: center; font-size: 10px; color: var(--ink-faint); padding: 0 var(--sp-6) var(--sp-3); flex-shrink: 0; }
</style>
```

- [ ] **Step 3: Run svelte-check**

```bash
cd /Users/praveen/Projects/cot-dashboard/apps/web && npx svelte-check --threshold error 2>&1 | tail -3
```

Expected: `0 errors 0 warnings`

- [ ] **Step 4: Commit + push**

```bash
git add apps/web/src/routes/chat/
git commit -m "feat: add /chat page — AI analyst with quick-start prompts and market chips"
git push
```

---

## Task 6: Sidebar + live test

**Files:**
- Modify: `apps/web/src/routes/+layout.svelte`

- [ ] **Step 1: Add Chat to routes list**

Find `const routes = [` in `+layout.svelte`. Add the Chat entry before Intelligence:

```typescript
const routes = [
    { href: '/', label: 'Today', short: 'TD' },
    { href: '/heatmap', label: 'Heatmap', short: 'HM' },
    { href: '/divergence', label: 'Divergence', short: 'DV' },
    { href: '/chat', label: 'Chat', short: '💬' },
    { href: '/intelligence', label: 'Intelligence', short: 'AI' }
];
```

- [ ] **Step 2: Run svelte-check**

```bash
cd /Users/praveen/Projects/cot-dashboard/apps/web && npx svelte-check --threshold error 2>&1 | tail -3
```

Expected: `0 errors 0 warnings`

- [ ] **Step 3: Live API test — restart API and smoke-test /chat**

```bash
cd /Users/praveen/Projects/cot-dashboard && pkill -f "python.*uvicorn src.main" 2>/dev/null; sleep 1
set -a && source .env && set +a
.venv/bin/python -m uvicorn src.main:app --host 127.0.0.1 --port 8000 --app-dir apps/api --log-level warning > /tmp/api.log 2>&1 &
until curl -sS --max-time 2 http://127.0.0.1:8000/healthz 2>/dev/null | grep -q ok; do sleep 2; done
curl -sS -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"What are the top 3 setups right now?"}]}' | python3 -c "
import sys,json; d=json.load(sys.stdin)
print('reply length:', len(d['reply']))
print('cited markets:', d['cited_markets'][:5])
print('first 200 chars:', d['reply'][:200])
"
```

Expected: reply with market names, confluence values, zone data cited.

- [ ] **Step 4: Final commit + push**

```bash
git add apps/web/src/routes/+layout.svelte
git commit -m "feat: add Chat to sidebar nav — Phase 1 complete"
git push
```

---

## Self-Review

**Spec coverage:**
- ✅ Natural language query interface — Task 5 (chat page)
- ✅ Grounded in live COT data — Task 1 (context_builder)
- ✅ DeepSeek-V4-Pro via HF router — Task 2 (chat.py uses existing `_ai.py`)
- ✅ Quick-start prompts for common queries — Task 5 (QUICK_STARTS array)
- ✅ Clickable market symbol chips — Task 5 (renderContent + sym-chip CSS)
- ✅ Deterministic fallback when AI unavailable — Task 2 (_deterministic_answer)
- ✅ POST /chat endpoint — Task 3
- ✅ TypeScript types + client method — Task 4
- ✅ Sidebar nav entry — Task 6
- ✅ Push to remote after every commit — every task has `git push`
- ✅ Conversation history sent client-side — Task 5 (history array built from messages state)

**Type consistency:**
- `ChatMessage` defined in Task 4 (types.ts) → used in Task 5 (page) ✅
- `chat(messages: ChatMessage[])` in client.ts → called in Task 5 ✅
- `answer(messages: list[dict], bundle)` in chat.py → called in Task 3 (main.py) ✅
- `build_context(bundle)` in context_builder.py → called in Task 2 (chat.py) ✅
