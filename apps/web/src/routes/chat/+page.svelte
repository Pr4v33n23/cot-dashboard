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

	function renderContent(text: string): string {
		let html = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
		const known = new Set(['CL','NG','RB','HO','BZ','GC','SI','HG','PL','PA','ALI',
			'ZC','ZS','ZW','KE','ZO','ZM','ZL','ZR','CC','KC','CT','SB','OJ','LBS',
			'LE','GF','HE','ES','NQ','YM','RTY','MES','MNQ','NIY',
			'ZB','ZN','ZF','ZT','FF','SR3',
			'EURUSD','GBPUSD','JPYUSD','AUDUSD','CADUSD','CHFUSD','NZDUSD',
			'MXNUSD','BRLUSD','NOKUSD','SEKUSD']);
		html = html.replace(/\b([A-Z]{2,7})\b/g, (match) =>
			known.has(match)
				? `<a href="/market/${match}" class="sym-chip" data-sveltekit-preload-data="hover">${match}</a>`
				: match
		);
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

	<div class="messages" bind:this={scrollEl}>
		{#if messages.length === 0}
			<div class="welcome">
				<div class="welcome-title">Ask me anything about COT positioning</div>
				<div class="welcome-sub">Grounded in live data across 47 futures markets. Click a prompt or type your question.</div>
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
	.page { display: flex; flex-direction: column; height: 100%; min-height: 0; overflow: hidden; }
	.chat-header { display: flex; align-items: flex-start; justify-content: space-between; padding: var(--sp-6) var(--sp-6) var(--sp-4); border-bottom: 1px solid var(--border-soft); flex-shrink: 0; }
	.eyebrow { font-size: var(--fs-11); text-transform: uppercase; letter-spacing: .06em; color: var(--ink-faint); }
	.title { font-size: var(--fs-20); font-weight: 600; margin: 2px 0 0; }
	.header-right { display: flex; flex-direction: column; align-items: flex-end; gap: 4px; }
	.ai-badge { font-size: 9px; font-family: var(--font-mono); padding: 2px 7px; border-radius: 99px; background: rgba(183,148,246,.08); color: var(--zone-a2); border: 1px solid rgba(183,148,246,.2); }
	.ctx-date { font-size: 10px; color: var(--ink-faint); }
	.messages { flex: 1; overflow-y: auto; padding: var(--sp-6); display: flex; flex-direction: column; gap: var(--sp-4); scrollbar-width: thin; scrollbar-color: var(--border) transparent; }
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
	.input-bar { display: flex; gap: var(--sp-2); padding: var(--sp-4) var(--sp-6); border-top: 1px solid var(--border-soft); background: var(--bg-canvas); flex-shrink: 0; }
	.input-field { flex: 1; background: var(--bg-panel); border: 1px solid var(--border); border-radius: var(--r-md); color: var(--ink); font: inherit; font-size: var(--fs-13); line-height: 1.5; padding: 10px 14px; resize: none; outline: none; scrollbar-width: thin; }
	.input-field:focus { border-color: var(--zone-a2); }
	.input-field:disabled { opacity: 0.5; }
	.send-btn { width: 40px; height: 40px; border-radius: var(--r-sm); background: var(--zone-a2); color: #0a0a0b; border: none; font-size: 18px; font-weight: 700; cursor: pointer; flex-shrink: 0; align-self: flex-end; transition: opacity .12s; }
	.send-btn:disabled { opacity: 0.35; cursor: not-allowed; }
	.send-btn:not(:disabled):hover { opacity: 0.85; }
	.disclaimer { text-align: center; font-size: 10px; color: var(--ink-faint); padding: 0 var(--sp-6) var(--sp-3); flex-shrink: 0; }
</style>
