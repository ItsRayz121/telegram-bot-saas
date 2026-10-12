// Builds the app for the e2e run. The API host is the real one, but every request to it
// is answered by a stub in e2e/helpers.js, so the tests never reach production.
const { spawnSync } = require('child_process');
const r = spawnSync('npx', ['react-scripts', 'build'], {
  stdio: 'inherit', shell: true,
  env: { ...process.env, CI: 'false', REACT_APP_API_URL: 'https://api.telegizer.com' },
});
process.exit(r.status === null ? 1 : r.status);
