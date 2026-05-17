<script lang="ts">
	import type { ZoneKey } from '$api/types';
	import { ZONE_NAMES, ZONE_BLURB } from '$api/types';

	interface Props {
		zone: ZoneKey;
		magnitude?: number;
		size?: 'sm' | 'md';
	}

	let { zone, magnitude = 1, size = 'md' }: Props = $props();

	const color = $derived(`var(--zone-${zone.toLowerCase()})`);
	const alpha = $derived(0.18 + Math.min(1, Math.max(0, magnitude)) * 0.35);
</script>

<span
	class="badge {size}"
	style:--c={color}
	style:background={`color-mix(in srgb, ${color} ${(alpha * 100).toFixed(0)}%, transparent)`}
	style:border-color={`color-mix(in srgb, ${color} ${(alpha * 100 + 20).toFixed(0)}%, transparent)`}
	title={`${ZONE_NAMES[zone]} — ${ZONE_BLURB[zone]}`}
>
	<span class="dot" style:background={color}></span>
	{zone}
</span>

<style>
	.badge {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		padding: 2px 8px 2px 6px;
		border-radius: 999px;
		border: 1px solid;
		color: var(--ink);
		font-family: var(--font-mono);
		font-size: var(--fs-11);
		line-height: 1;
		font-weight: 500;
		user-select: none;
		cursor: help;
		transition: transform 0.12s;
	}
	.badge:hover {
		transform: translateY(-1px);
	}
	.badge.sm {
		font-size: 10px;
		padding: 1px 6px 1px 5px;
		gap: 4px;
	}
	.dot {
		width: 6px;
		height: 6px;
		border-radius: 50%;
		flex: none;
	}
</style>
