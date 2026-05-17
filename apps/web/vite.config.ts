import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

const API_TARGET = process.env.COT_API_URL ?? 'http://127.0.0.1:8000';

export default defineConfig({
	plugins: [sveltekit()],
	server: {
		port: 5173,
		strictPort: true,
		proxy: {
			'/api': {
				target: API_TARGET,
				changeOrigin: true,
				rewrite: (p) => p.replace(/^\/api/, '')
			}
		}
	}
});
