#!/usr/bin/env node
// Runs after `vite build`. Pre-renders the homepage into build/index.html and keeps an unrendered
// copy as build/app.html, which vercel.json serves for every other route — so the dashboard and other
// app pages never flash homepage content while the bundle loads.
//
// Kill switch: PRERENDER=0 skips this step; build/index.html then stays the plain shell (the old behaviour),
// and app.html is still written so the vercel.json rewrite keeps working.
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { build } from 'vite';

const root = path.resolve(import.meta.dirname, '..');
const out = path.join(root, 'build');
const ssrOut = path.join(root, 'build-ssr');
const indexPath = path.join(out, 'index.html');
const shell = fs.readFileSync(indexPath, 'utf8');

fs.writeFileSync(path.join(out, 'app.html'), shell);

if (process.env.PRERENDER === '0') {
  console.log('[prerender] PRERENDER=0 — skipped; index.html is the plain app shell.');
  process.exit(0);
}

try {
  await build({
    root,
    configFile: path.join(root, 'vite.config.mjs'),
    logLevel: 'warn',
    // Bundle every dependency: Node then never has to resolve MUI's mixed ESM/CJS packages itself.
    ssr: { noExternal: true },
    build: { ssr: 'src/prerender.jsx', outDir: ssrOut, emptyOutDir: true, copyPublicDir: false },
  });
  const entry = fs.readdirSync(ssrOut).find((f) => /^prerender\.m?js$/.test(f));
  const { render } = await import(pathToFileURL(path.join(ssrOut, entry)).href);
  const { html, styles } = render('/');

  const marker = '<div id="root"></div>';
  if (!shell.includes(marker) || !shell.includes('</head>')) throw new Error('index.html has no empty #root / </head> to fill');
  // Without JavaScript the hero chat would stay in its pre-animation (hidden) state.
  const noscript = '<noscript><style>.chat-pending .m{visibility:visible!important}</style></noscript>';
  const page = shell
    .replace('</head>', `${styles}\n${noscript}\n</head>`)
    .replace(marker, `<div id="root">${html}</div>`)
    // The homepage reads fine without JavaScript now; the shell's warning only belongs on app routes.
    .replace(/<noscript>You need to enable JavaScript[^<]*<\/noscript>/, '');
  fs.writeFileSync(indexPath, page);
  console.log(`[prerender] homepage pre-rendered: ${(html.length / 1024).toFixed(0)} KB markup, ${(styles.length / 1024).toFixed(0)} KB critical CSS`);
} catch (err) {
  // A failed pre-render must not fail the deploy: the plain shell works exactly as before.
  console.warn('[prerender] skipped, serving the plain shell:', err && err.stack ? err.stack : err);
  fs.writeFileSync(indexPath, shell);
} finally {
  fs.rmSync(ssrOut, { recursive: true, force: true });
}
