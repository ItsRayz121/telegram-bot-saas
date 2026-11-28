// Vite build for the Telegizer web app (replaced Create React App in 2026-11).
//
// Kept deliberately compatible with what CRA produced, so nothing outside this folder had to change:
//   - output goes to build/ (Vercel's output directory) and hashed files to build/static/
//     (vercel.json caches /static/* forever and public/sw.js serves /static/* cache-first);
//   - code keeps reading process.env.REACT_APP_* — those names are what Vercel has set, so they are
//     substituted at build time below instead of being renamed to import.meta.env.VITE_*;
//   - files that contain JSX are .jsx (Vite's bundler only parses JSX in .jsx/.tsx); plain modules stay .js.
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = { ...loadEnv(mode, process.cwd(), 'REACT_APP_'), ...pick(process.env, 'REACT_APP_') };
  const define = { 'process.env.NODE_ENV': JSON.stringify(mode === 'production' || mode === 'test' ? mode : 'development') };
  for (const [k, v] of Object.entries(env)) define[`process.env.${k}`] = JSON.stringify(v);
  // Anything not set (e.g. REACT_APP_SENTRY_DSN locally) must still compile to `undefined`, as under CRA.
  define['process.env'] = '({})';

  return {
    plugins: [react()],
    define,
    server: { port: 3000, open: false },
    preview: { port: 4173 },
    build: {
      outDir: 'build',
      assetsDir: 'static',
      sourcemap: false,
      // Same browser floor CRA's browserslist gave us in practice.
      target: ['es2020', 'chrome87', 'firefox78', 'safari14', 'edge88'],
      chunkSizeWarningLimit: 1500,
    },
    test: {
      environment: 'jsdom',
      globals: true,
      include: ['src/**/*.test.{js,jsx}'],
      setupFiles: ['src/setupTests.js'],
      // Each jsdom worker takes ~20 s to start on a slow machine; too many at once starve each other
      // and Vitest gives up on them ("Timeout waiting for worker"). Two threads finish sooner.
      pool: 'threads',
      maxWorkers: 2,
      testTimeout: 20000,
    },
  };
});

function pick(obj, prefix) {
  return Object.fromEntries(Object.entries(obj).filter(([k]) => k.startsWith(prefix)));
}
