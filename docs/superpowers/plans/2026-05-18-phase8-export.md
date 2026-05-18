# PDF/Print Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** PDF/print research export from the market detail page — one click generates a printable research note.
**Architecture:** Use the browser's native `window.print()` with a `@media print` CSS override that hides the sidebar/nav and formats the content as a clean research document. No server-side rendering needed. Add a "Export PDF" button on the market detail page. Print CSS formats it as A4 with the market name, date, chart (as is), COT breakdown, synthesis, and news.
**Tech Stack:** CSS @media print, SvelteKit, browser window.print()

---

## Files
- Modify: `apps/web/src/routes/market/[symbol]/+page.svelte` — add Export button + print styles
- Modify: `apps/web/src/lib/design/tokens.css` — add @media print base rules
- Modify: `apps/web/src/routes/+layout.svelte` — hide sidebar on print

---

## Task 1: Print CSS + export button

- [ ] **Add to `tokens.css`** (append at end):
```css
@media print {
  :root {
    --bg-canvas: #ffffff;
    --bg-panel: #f8f8f8;
    --bg-panel-2: #f0f0f0;
    --ink: #0a0a0b;
    --ink-muted: #444;
    --ink-faint: #888;
    --border: #ccc;
    --border-soft: #e0e0e0;
  }
  body { background: white; color: #0a0a0b; font-size: 11pt; }
}
```

- [ ] **Add to `+layout.svelte`** — hide sidebar on print:

Find the `.sidebar` CSS rule and add after it:
```css
@media print {
  .sidebar { display: none !important; }
  .app { grid-template-columns: 1fr !important; }
  .main { overflow: visible !important; }
}
```

- [ ] **Add to `market/[symbol]/+page.svelte`**:

In the header, add an export button after the AI Analysis link:
```svelte
<button class="export-btn" onclick={() => window.print()} title="Export as PDF">⬇ Export PDF</button>
```

Add CSS:
```css
.export-btn { padding: 4px 10px; border-radius: var(--r-sm); font-size: var(--fs-11); color: var(--ink-muted); background: var(--bg-panel); border: 1px solid var(--border); cursor: pointer; transition: color .12s; }
.export-btn:hover { color: var(--ink); border-color: var(--ink-muted); }

@media print {
  .export-btn, .ai-link { display: none; }
  .page { overflow: visible !important; padding: 0 !important; }
  .header { padding-bottom: 12pt; border-bottom: 2px solid #ccc; margin-bottom: 12pt; }
  .title { font-size: 18pt; }
  .chart-wrap { height: 280px !important; page-break-after: avoid; }
}
```

- [ ] **svelte-check + commit + push**:
```bash
cd /Users/praveen/Projects/cot-dashboard/apps/web && npx svelte-check --threshold error 2>&1 | tail -3
git add apps/web/src/routes/market/ apps/web/src/lib/design/tokens.css apps/web/src/routes/+layout.svelte
git commit -m "feat: add Export PDF button to market detail page (browser print)"
git push
```
