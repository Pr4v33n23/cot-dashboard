<script lang="ts">
	interface Props {
		width?: string;
		height?: string;
		radius?: string;
		variant?: 'block' | 'line' | 'circle' | 'card';
	}

	let { width = '100%', height = '14px', radius = '4px', variant = 'block' }: Props = $props();

	const styles = $derived.by(() => {
		if (variant === 'circle') return { width, height, radius: '50%' };
		if (variant === 'line') return { width, height: '11px', radius: '3px' };
		if (variant === 'card') return { width, height, radius: 'var(--r-md)' };
		return { width, height, radius };
	});
</script>

<span
	class="sk"
	style:width={styles.width}
	style:height={styles.height}
	style:border-radius={styles.radius}
	aria-hidden="true"
></span>

<style>
	.sk {
		display: inline-block;
		background: linear-gradient(
			90deg,
			var(--bg-panel-2) 0%,
			var(--bg-hover) 50%,
			var(--bg-panel-2) 100%
		);
		background-size: 200% 100%;
		animation: shimmer 1.6s ease-in-out infinite;
	}
	@keyframes shimmer {
		0% {
			background-position: 200% 0;
		}
		100% {
			background-position: -200% 0;
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.sk {
			animation: none;
		}
	}
</style>
