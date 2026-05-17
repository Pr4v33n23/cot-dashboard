/**
 * Global news-reader state.
 *
 * Single drawer instance mounted in the root layout. Anywhere in the app can
 * call `newsReader.open({ url, ... })` to slide it in.
 */

import { api } from '$api/client';
import type { ArticleResponse, NewsItem } from '$api/types';

interface OpenArgs {
	url: string;
	title?: string | null;
	source?: string | null;
	publisher?: string | null;
	date?: string | null;
}

class NewsReaderState {
	open = $state(false);
	loading = $state(false);
	error = $state<string | null>(null);
	article = $state<ArticleResponse | null>(null);
	// The summary we already had at click time — shown instantly while loading.
	stub = $state<OpenArgs | null>(null);

	openItem(item: NewsItem) {
		if (!item.url) return;
		this.openUrl({
			url: item.url,
			title: item.title,
			source: item.source,
			publisher: item.publisher,
			date: item.date
		});
	}

	async openUrl(args: OpenArgs) {
		this.open = true;
		this.stub = args;
		this.error = null;
		this.article = null;
		this.loading = true;
		try {
			this.article = await api.article(args.url);
		} catch (e) {
			this.error = (e as Error).message;
		} finally {
			this.loading = false;
		}
	}

	close() {
		this.open = false;
		// Keep the article around briefly so closing animation looks clean,
		// then clear. We don't really need to clear — staying in memory is fine.
	}

	retry() {
		if (this.stub) {
			this.openUrl(this.stub);
		}
	}
}

export const newsReader = new NewsReaderState();
