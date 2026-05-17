/**
 * Universe + status state — loaded once, used everywhere.
 *
 * Svelte 5 runes. Imported components read the proxied fields directly
 * (`universeState.contracts`) and stay reactive across the SPA.
 */

import { api } from '$api/client';
import type { ContractMeta, StatusResponse } from '$api/types';

class UniverseState {
	contracts = $state<ContractMeta[]>([]);
	status = $state<StatusResponse | null>(null);
	loading = $state(false);
	error = $state<string | null>(null);

	bySymbol(symbol: string): ContractMeta | undefined {
		return this.contracts.find((c) => c.symbol === symbol);
	}

	sectorOf(symbol: string): string {
		return this.bySymbol(symbol)?.sector ?? '';
	}

	async load() {
		if (this.loading || this.contracts.length > 0) return;
		this.loading = true;
		this.error = null;
		try {
			const [u, s] = await Promise.all([api.universe(), api.status()]);
			this.contracts = u;
			this.status = s;
		} catch (e) {
			this.error = (e as Error).message;
		} finally {
			this.loading = false;
		}
	}
}

export const universeState = new UniverseState();
