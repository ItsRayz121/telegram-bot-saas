#!/usr/bin/env node
/**
 * Generates public/sitemap.xml before each build.
 * Run via: node scripts/generate-sitemap.js
 * Wired into package.json "build" script automatically.
 */

const fs = require('fs');
const path = require('path');

const BASE_URL = 'https://telegizer.com';
const TODAY = new Date().toISOString().split('T')[0]; // YYYY-MM-DD

/**
 * priority: 1.0 = most important, 0.5 = default
 * changefreq: how often Google should re-crawl
 */
const PAGES = [
  { loc: '/',               changefreq: 'weekly',  priority: '1.0' },
  { loc: '/pricing',        changefreq: 'weekly',  priority: '0.9' },
  { loc: '/directory',      changefreq: 'daily',   priority: '0.8' },
  { loc: '/marketplace',    changefreq: 'weekly',  priority: '0.7' },
  { loc: '/about',          changefreq: 'monthly', priority: '0.8' },
  { loc: '/contact',        changefreq: 'monthly', priority: '0.7' },
  { loc: '/privacy',        changefreq: 'monthly', priority: '0.5' },
  { loc: '/terms',          changefreq: 'monthly', priority: '0.5' },
  { loc: '/acceptable-use', changefreq: 'monthly', priority: '0.4' },
];

function buildSitemap(pages) {
  const urls = pages
    .map(
      ({ loc, changefreq, priority }) =>
        `  <url>\n    <loc>${BASE_URL}${loc}</loc>\n    <lastmod>${TODAY}</lastmod>\n    <changefreq>${changefreq}</changefreq>\n    <priority>${priority}</priority>\n  </url>`
    )
    .join('\n');

  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls}\n</urlset>\n`;
}

const outPath = path.join(__dirname, '..', 'public', 'sitemap.xml');
fs.writeFileSync(outPath, buildSitemap(PAGES), 'utf8');
console.log(`[sitemap] Written ${PAGES.length} URLs → ${outPath} (lastmod: ${TODAY})`);
