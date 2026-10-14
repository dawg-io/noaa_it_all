// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import { BASE, REPO_URL, SIDEBAR, SITE } from './site.mjs';

// The pages come from ../docs: scripts/sync-docs.mjs copies them into
// src/content/docs/ before every build, so edit docs/, not that folder.
export default defineConfig({
	site: SITE,
	base: BASE,
	integrations: [
		starlight({
			title: 'NOAA It All',
			description: 'NOAA and National Weather Service data in Home Assistant.',
			logo: { src: './src/assets/icon.png' },
			favicon: '/favicon.png',
			social: [{ icon: 'github', label: 'GitHub', href: REPO_URL }],
			customCss: ['./src/styles/theme.css'],
			sidebar: SIDEBAR,
		}),
	],
});
