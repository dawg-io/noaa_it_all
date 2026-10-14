// Checks the built site in dist/: every link, image and #anchor that stays on
// the site must resolve to a page or file it has, the way GitHub Pages serves
// it. Catches a link that sync-docs.mjs left pointing at a .md file.

import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { BASE } from '../site.mjs';

const website = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const dist = join(website, 'dist');
const base = BASE.replace(/\/?$/, '/');
const origin = 'https://site.invalid';

function htmlFiles(dir) {
	return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
		const path = join(dir, entry.name);
		if (entry.isDirectory()) return htmlFiles(path);
		return entry.name.endsWith('.html') ? [path] : [];
	});
}

const idCache = new Map();
function idsIn(file) {
	if (!idCache.has(file)) {
		const html = readFileSync(file, 'utf-8');
		idCache.set(file, new Set([...html.matchAll(/\sid="([^"]+)"/g)].map((m) => m[1])));
	}
	return idCache.get(file);
}

function fileFor(pathname) {
	if (!pathname.startsWith(base)) return null;
	let path = decodeURIComponent(pathname.slice(base.length));
	if (path === '' || path.endsWith('/')) path += 'index.html';
	for (const candidate of [join(dist, path), join(dist, path, 'index.html')]) {
		if (existsSync(candidate) && statSync(candidate).isFile()) return candidate;
	}
	return null;
}

const pages = htmlFiles(dist);
const errors = [];
for (const page of pages) {
	const pageUrl = base + relative(dist, page).split(sep).join('/').replace(/(^|\/)index\.html$/, '$1');
	const html = readFileSync(page, 'utf-8');
	// Attributes of real tags only: code examples show <img src="…"> with the
	// < escaped, so they don't match.
	for (const [, raw] of html.matchAll(/<[a-z][^<>]*?\s(?:href|src)="([^"]*)"/gi)) {
		const ref = raw.replaceAll('&amp;', '&');
		if (ref === '' || ref === '#' || /^(https?|mailto|data|javascript):/i.test(ref)) continue;
		const url = new URL(ref, origin + pageUrl);
		const target = url.pathname === new URL(origin + pageUrl).pathname ? page : fileFor(url.pathname);
		const where = `${relative(dist, page)}: ${ref}`;
		if (!target) {
			errors.push(`${where} (no such page or file)`);
		} else if (url.hash && target.endsWith('.html') && !idsIn(target).has(decodeURIComponent(url.hash.slice(1)))) {
			errors.push(`${where} (no such anchor)`);
		}
	}
}

if (errors.length) {
	console.error(`${errors.length} broken link(s) in dist/:\n${errors.join('\n')}`);
	process.exit(1);
}
console.log(`Checked ${pages.length} pages in dist/: every on-site link resolves`);
