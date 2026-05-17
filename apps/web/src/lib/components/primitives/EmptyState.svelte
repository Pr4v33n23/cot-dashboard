<script lang="ts">
	interface Props {
		variant?: 'loading' | 'empty' | 'error';
		title?: string;
		body?: string;
		retry?: () => void;
	}

	let { variant = 'loading', title, body, retry }: Props = $props();

	const defaults = {
		loading: { title: 'Loading…', body: 'Fetching the latest from the origin server.' },
		empty: { title: 'Nothing to show', body: 'No data in this window.' },
		error: { title: 'Failed to load', body: 'Something went wrong fetching from the API.' }
	};

	const t = $derived(title ?? defaults[variant].title);
	const b = $derived(body ?? defaults[variant].body);
</script>

<div class="state" data-variant={variant}>
	{#if variant === 'loading'}
		<div class="spinner" aria-hidden="true">
			<span></span><span></span><span></span>
		</div>
	{:else if variant === 'error'}
		<div class="icon">!</div>
	{:else}
		<div class="icon dot">·</div>
	{/if}
	<div class="title">{t}</div>
	<div class="body">{b}</div>
	{#if retry && variant === 'error'}
		<button onclick={retry} class="retry">Retry</button>
	{/if}
</div>

<style>
	.state {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: var(--sp-2);
		padding: var(--sp-12) var(--sp-6);
		min-height: 240px;
		color: var(--ink-muted);
		text-align: center;
	}
	.state[data-variant='error'] .icon {
		color: var(--short);
		border-color: color-mix(in srgb, var(--short) 50%, transparent);
	}
	.icon {
		width: 32px;
		height: 32px;
		border: 1px solid var(--border);
		border-radius: 50%;
		display: flex;
		align-items: center;
		justify-content: center;
		font-family: var(--font-mono);
		font-size: var(--fs-16);
		color: var(--ink-muted);
		margin-bottom: var(--sp-2);
	}
	.icon.dot {
		font-size: 24px;
		line-height: 1;
	}
	.title {
		font-size: var(--fs-14);
		color: var(--ink);
	}
	.body {
		font-size: var(--fs-12);
		color: var(--ink-faint);
		max-width: 40ch;
	}
	.retry {
		margin-top: var(--sp-3);
		padding: 6px 14px;
		font-size: var(--fs-12);
		color: var(--ink);
		background: var(--bg-panel);
		border: 1px solid var(--border);
		border-radius: var(--r-sm);
		transition: background 0.12s, border-color 0.12s;
	}
	.retry:hover {
		background: var(--bg-hover);
		border-color: var(--ink-muted);
	}

	/* ── Spinner: three dots with phased motion ─────────────────────── */
	.spinner {
		display: inline-flex;
		gap: 6px;
		margin-bottom: var(--sp-2);
	}
	.spinner span {
		width: 6px;
		height: 6px;
		border-radius: 50%;
		background: var(--attn-high);
		animation: bounce 1.1s ease-in-out infinite;
	}
	.spinner span:nth-child(2) {
		animation-delay: 0.15s;
	}
	.spinner span:nth-child(3) {
		animation-delay: 0.3s;
	}
	@keyframes bounce {
		0%, 80%, 100% {
			opacity: 0.3;
			transform: scale(0.8);
		}
		40% {
			opacity: 1;
			transform: scale(1);
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.spinner span {
			animation: none;
			opacity: 0.8;
		}
	}
</style>
