// Builds the Starlight content from ../docs before every build, so docs/ stays
// plain GitHub Markdown that also reads correctly on github.com.
//
// For each docs/*.md page it:
// - moves the page's "# Title" into front matter, which Starlight requires;
// - makes README.md the home page;
// - points links to other pages at their site URLs, and links that leave docs/
//   (the README, the changelog) at the public repository;
// - points screenshots at public/images/, since Astro leaves raw <img> tags alone;
// - turns GitHub alerts (> [!NOTE]) into Starlight asides (:::note).
// Code blocks and inline code are left as they are.

import { copyFileSync, cpSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { BASE, REPO_URL, SIDEBAR } from '../site.mjs';

const website = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const repo = resolve(website, '..');
const docs = join(repo, 'docs');
const content = join(website, 'src', 'content', 'docs');
const base = BASE.replace(/\/?$/, '/');

const ALERTS = { NOTE: 'note', TIP: 'tip', IMPORTANT: 'note', WARNING: 'caution', CAUTION: 'danger' };

// docs/README.md becomes a landing page; its "# Title" is replaced by this.
const HOME = {
	title: 'NOAA It All',
	description:
		'NOAA and National Weather Service data in Home Assistant: weather, surf, nearshore marine ' +
		'forecasts, hurricanes and space weather.',
	template: 'splash',
	hero: {
		tagline:
			'NOAA and National Weather Service data in Home Assistant: weather, surf, nearshore marine ' +
			'forecasts, hurricanes, and space weather, aurora, meteor showers and eclipses.',
		image: { file: '../../assets/icon.png' },
		actions: [
			{ text: 'Get started', link: `${base}configuration/`, icon: 'right-arrow' },
			{ text: 'View on GitHub', link: REPO_URL, icon: 'external', variant: 'minimal' },
		],
	},
};

const posixPath = (path) => path.split(sep).join('/');

function siteTarget(target, fromDir) {
	if (/^[a-z][a-z0-9+.-]*:/i.test(target) || target.startsWith('#') || target.startsWith('/')) {
		return target;
	}
	const at = target.indexOf('#');
	const path = at === -1 ? target : target.slice(0, at);
	const hash = at === -1 ? '' : target.slice(at);
	const absolute = resolve(fromDir, path);
	const inDocs = posixPath(relative(docs, absolute));
	if (inDocs.startsWith('../')) {
		return `${REPO_URL}/blob/main/${posixPath(relative(repo, absolute))}${hash}`;
	}
	if (inDocs.endsWith('.md')) {
		const page = inDocs.slice(0, -3);
		return `${base}${page === 'README' ? '' : `${page}/`}${hash}`;
	}
	return `${base}${inDocs}${hash}`;
}

function rewriteLinks(line, fromDir) {
	// Odd parts are inline code, which is left alone.
	return line
		.split(/(`[^`]*`)/)
		.map((part, i) =>
			i % 2
				? part
				: part
						.replace(/(\]\(\s*<?)([^\s)>]+)/g, (_, open, target) => open + siteTarget(target, fromDir))
						.replace(/(\s(?:src|href)=")([^"]+)(")/gi, (_, open, target, close) =>
							open + siteTarget(target, fromDir) + close,
						),
		)
		.join('');
}

function transform(markdown, file) {
	const fromDir = dirname(file);
	const out = [];
	let title = null;
	let fence = null;
	let alert = false;
	for (const line of markdown.split('\n')) {
		const marker = line.match(/^\s*(`{3,}|~{3,})/);
		if (fence) {
			if (marker && marker[1][0] === fence[0] && marker[1].length >= fence.length) fence = null;
			out.push(line);
			continue;
		}
		if (alert) {
			if (line.startsWith('>')) {
				out.push(rewriteLinks(line.replace(/^> ?/, ''), fromDir));
				continue;
			}
			out.push(':::');
			alert = false;
		}
		if (marker) {
			fence = marker[1];
			out.push(line);
			continue;
		}
		const heading = title === null && line.match(/^# (.+)$/);
		if (heading) {
			title = heading[1].replace(/[`*]/g, '').trim();
			continue;
		}
		const kind = line.match(/^> \[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*$/);
		if (kind) {
			out.push(`:::${ALERTS[kind[1]]}`);
			alert = true;
			continue;
		}
		out.push(rewriteLinks(line, fromDir));
	}
	if (alert) out.push(':::');
	if (title === null) throw new Error(`${posixPath(relative(repo, file))} has no "# Title" line`);
	return { title, body: out.join('\n').replace(/^\n+/, '') };
}

// JSON is valid YAML, so each value is written as JSON.
function frontMatter(data) {
	const lines = Object.entries(data).map(([key, value]) => `${key}: ${JSON.stringify(value)}`);
	return `---\n${lines.join('\n')}\n---\n\n`;
}

const pages = readdirSync(docs).filter((name) => name.endsWith('.md'));
const listed = SIDEBAR.flatMap((group) => group.items);
const missing = pages.map((name) => name.slice(0, -3)).filter((page) => page !== 'README' && !listed.includes(page));
const unknown = listed.filter((page) => !pages.includes(`${page}.md`));
if (missing.length || unknown.length) {
	if (missing.length) console.error(`Not in the sidebar in website/site.mjs: ${missing.join(', ')}`);
	if (unknown.length) console.error(`In the sidebar but not in docs/: ${unknown.join(', ')}`);
	process.exit(1);
}

rmSync(content, { recursive: true, force: true });
rmSync(join(website, 'public'), { recursive: true, force: true });
mkdirSync(content, { recursive: true });
mkdirSync(join(website, 'src', 'assets'), { recursive: true });

for (const name of pages) {
	const file = join(docs, name);
	const { title, body } = transform(readFileSync(file, 'utf-8'), file);
	const home = name === 'README.md';
	writeFileSync(join(content, home ? 'index.md' : name), frontMatter(home ? HOME : { title }) + body);
}

cpSync(join(docs, 'images'), join(website, 'public', 'images'), { recursive: true });
copyFileSync(join(repo, 'icon.png'), join(website, 'public', 'favicon.png'));
copyFileSync(join(repo, 'icon.png'), join(website, 'src', 'assets', 'icon.png'));

console.log(`Synced ${pages.length} pages from docs/ (base ${base})`);
