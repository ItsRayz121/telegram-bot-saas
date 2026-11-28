#!/usr/bin/env node
// Production build: Vite, then the homepage pre-render (scripts/prerender.mjs).
// Cross-platform on purpose — the old CRA script used `$(date …)`, which only worked in a POSIX shell.
const { spawnSync } = require('child_process');

const env = { ...process.env, REACT_APP_BUILD_TIME: process.env.REACT_APP_BUILD_TIME || new Date().toISOString().replace(/\.\d+Z$/, 'Z') };

function run(cmd, args) {
  const r = spawnSync(cmd, args, { stdio: 'inherit', shell: true, env });
  if (r.status !== 0) process.exit(r.status === null ? 1 : r.status);
}

run('npx', ['vite', 'build']);
run('node', ['scripts/prerender.mjs']);
