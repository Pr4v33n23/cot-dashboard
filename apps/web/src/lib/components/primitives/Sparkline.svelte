<script lang="ts">
	interface Props {
		values: number[];
		width?: number;
		height?: number;
		color?: string;
		fillColor?: string;
		strokeWidth?: number;
	}

	let {
		values,
		width = 120,
		height = 28,
		color = 'var(--ink-muted)',
		fillColor,
		strokeWidth = 1.25
	}: Props = $props();

	const path = $derived.by(() => {
		if (!values.length) return '';
		const pad = 1;
		const min = Math.min(...values);
		const max = Math.max(...values);
		const span = max - min || 1;
		const stepX = (width - pad * 2) / Math.max(1, values.length - 1);
		const ys = values.map(
			(v) => height - pad - ((v - min) / span) * (height - pad * 2)
		);
		const xs = values.map((_, i) => pad + i * stepX);
		let d = `M ${xs[0]} ${ys[0]}`;
		for (let i = 1; i < xs.length; i++) d += ` L ${xs[i]} ${ys[i]}`;
		return d;
	});

	const fillPath = $derived.by(() => {
		if (!fillColor || !path) return '';
		return `${path} L ${width - 1} ${height - 1} L 1 ${height - 1} Z`;
	});
</script>

<svg {width} {height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
	{#if fillColor}
		<path d={fillPath} fill={fillColor} opacity="0.35" />
	{/if}
	<path d={path} fill="none" stroke={color} stroke-width={strokeWidth} stroke-linecap="round" stroke-linejoin="round" />
</svg>
