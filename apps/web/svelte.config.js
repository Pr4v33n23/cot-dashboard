import adapter from '@sveltejs/adapter-static';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	compilerOptions: {
		runes: ({ filename }) => (filename.split(/[/\\]/).includes('node_modules') ? undefined : true)
	},
	kit: {
		adapter: adapter({
			fallback: 'index.html', // SPA fallback for client-side routing
			pages: 'build',
			assets: 'build',
			precompress: false,
			strict: true
		}),
		alias: {
			$engine: 'src/lib/engine',
			$api: 'src/lib/api',
			$state: 'src/lib/state',
			$design: 'src/lib/design',
			$components: 'src/lib/components'
		}
	}
};

export default config;
