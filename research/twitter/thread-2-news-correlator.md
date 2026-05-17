---
thread: 2 of 3
topic: Pairing CFTC positioning with the news that drove it — no LLM, just timeline overlay
target_post_date: launch week 2
status: draft
---

# Thread 2 — Pairing CFTC positioning with the news that drove it (no LLM)

## Tweet 1
"Why are commercials suddenly net-long copper?"

If you trade futures, you ask this every week.

I built a thing that answers it without an LLM. Just data on a shared timeline.

Walking through the design 🧵

## Tweet 2
The problem: COT data tells you the WHO. Commercials added 12K longs in HG last week. OK — but WHY?

Most COT tools stop here. You alt-tab to Reuters / Bloomberg / USDA / EIA to piece it together.

That alt-tab is the product.

## Tweet 3
The deterministic approach (no LLM, no sentiment classification):

1) Ingest free news from sources tagged by category:
• Yahoo Finance ticker news (per-contract)
• USDA WASDE schedule
• EIA Weekly Petroleum Status
• FOMC + OPEC meeting calendars
• FRED economic releases

## Tweet 4
2) A static `news_taxonomy.py` maps keywords → markets:

```python
TAXONOMY = {
  "CL": ["opec", "crude", "wti", "saudi", "iran", ...],
  "ZC": ["corn", "wasde", "ethanol", "midwest drought", ...],
  "GC": ["fed", "fomc", "rate cut", "cpi", "dollar", ...],
}
```

23 markets, ~10 keywords each. ~280 LOC total.

## Tweet 5
3) Headline match = word-boundary regex against the keyword set. Case-insensitive. One headline can tag multiple markets (a CPI print fires GC + SI + 6E).

No sentiment. No summarization. No model. Just substring matching.

The trader supplies the interpretation.

## Tweet 6
4) UI rendering:
• News pins on the chart's date axis, colored by source category
• Click a pin → in-app reader (trafilatura-extracted, sanitized HTML, native typography)
• Vertical news rail beside the chart, filterable by category
• Hover a pin → headline tooltip

## Tweet 7
The "no LLM" bit isn't an aesthetic choice. It's a trust choice.

Every word the user reads on COT_LENS is either (a) deterministic from data (zone reasoning) or (b) verbatim from a primary source (news headline + link). Nothing generated. Nothing hallucinated.

## Tweet 8
Tech stack:
• Python `trafilatura` for in-app article extraction
• FastAPI `/article?url=...` with LRU cache
• Svelte 5 drawer for the reader UX
• Springs (not CSS transitions) for the drawer slide-in
• All keyboard-accessible (Esc to close, Cmd-click escapes to new tab)

## Tweet 9
The Article Extract pipeline:
1) User clicks pin / news item
2) Front-end calls /article?url=...
3) Server fetches the page, trafilatura extracts main content + metadata
4) Returns sanitized HTML + title + byline + word count
5) Drawer renders with our typography tokens

~80ms cold, ~5ms cached.

## Tweet 10
Why this matters: most "AI news summary" products force you to trust a black box. This forces you to read the actual primary source — but inside your trading flow, not in a separate browser tab.

The data context (COT + chart) and the news context are on the same screen.

## Tweet 11
What's deferred to v2:
• Real-time news push (WebSocket)
• User-defined keyword alerts
• Sentiment SCORES (still no NLP — but volume + recency metrics per market)
• Custom taxonomy authoring per user
• Backfill of historical news beyond yfinance's ~10-item window

## Tweet 12
Code in next thread (Phase 6 launch). Repo will be public the week we go live.

If you'd find a "CFTC + macro news on one timeline" dashboard useful, reply with the contract you trade most — helps me prioritize the taxonomy.

---

# Thread notes

- Length: 12 tweets, ~2,100 chars.
- Hooks: deterministic-news angle is unusual in 2026 (everyone has LLM commentary). Lean into it.
- Engagement bait: tweet 4 code snippet usually performs well.
- Best posting time: Wed–Fri morning ET (futures market open).
