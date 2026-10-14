// Settings shared by astro.config.mjs and scripts/sync-docs.mjs.

// The site is served from the public repository's GitHub Pages. The deploy
// workflow overrides both from what Pages reports, so a custom domain needs no
// change here; these defaults are for local and pull request builds.
export const SITE = process.env.DOCS_SITE || 'https://dawg-io.github.io';
export const BASE = process.env.DOCS_BASE || '/noaa_it_all';

// Links that leave docs/ (the README, the changelog) go to the public repository.
export const REPO_URL = 'https://github.com/dawg-io/noaa_it_all';

// Every page in docs/ except README.md (the home page) must be listed here, by
// its file name without .md; sync-docs.mjs fails the build otherwise.
export const SIDEBAR = [
	{ label: 'Getting Started', items: ['configuration', 'forecast-offices'] },
	{ label: 'Reference', items: ['devices', 'entities', 'entity-naming', 'data-sources'] },
	{ label: 'Examples', items: ['automations', 'dashboards'] },
	{ label: 'Help', items: ['troubleshooting'] },
];
