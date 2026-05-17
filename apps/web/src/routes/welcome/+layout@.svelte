<script lang="ts">
	import '$design/tokens.css';
	let { children } = $props();
</script>

<div class="shell">
	{@render children()}
</div>

<style>
	.shell {
		min-height: 100vh;
		background: var(--bg-canvas);
		color: var(--ink);
		font-family: var(--font-sans);
	}
</style>
