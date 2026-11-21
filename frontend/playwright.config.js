// End-to-end + visual regression tests. They run against the PRODUCTION BUILD
// served locally, with every network call to a third party or the API stubbed,
// so they are deterministic and never touch live data.
//   npm run build   (needs CI unset/false)   then   npm run e2e
//   npm run e2e:update   regenerates screenshot baselines after an intended UI change
const { defineConfig, devices } = require('@playwright/test');

// Locally use the installed Chrome (no browser download); CI uses bundled Chromium. Chromium projects only.
const CHROME = process.env.CI ? undefined : 'chrome';

module.exports = defineConfig({
  testDir: './e2e',
  timeout: 30000,
  retries: process.env.CI ? 1 : 0,
  // The app is a ~1 MB JS bundle that every test cold-loads; many parallel workers starve each other
  // and the first assertion after goto() misses the 5 s default. Bound the workers instead of hiding it.
  workers: process.env.CI ? 2 : 3,
  reporter: [['list']],
  // Baselines are not suffixed with the OS name, so they must be generated on the
  // platform CI uses; the small tolerance absorbs font anti-aliasing noise.
  snapshotPathTemplate: '{testDir}/__screenshots__/{testFilePath}/{arg}{ext}',
  expect: { timeout: 10000, toHaveScreenshot: { maxDiffPixelRatio: 0.02, animations: 'disabled' } },
  // Locally use the installed Chrome (no browser download); CI uses bundled Chromium.
  use: { baseURL: 'http://127.0.0.1:4173', ...devices['Desktop Chrome'], screenshot: process.env.PW_SHOT ? 'only-on-failure' : 'off' },
  projects: [
    { name: 'desktop', use: { viewport: { width: 1280, height: 800 }, channel: CHROME } },
    { name: 'mobile', use: { ...devices['Pixel 5'], channel: CHROME } },
    // Opt-in cross-browser pass. Firefox: `npm run e2e -- --project=firefox` (set FIREFOX_PATH to a firefox.exe
    // if Playwright's own download is not installed). WebKit needs `npx playwright install webkit`; a build from a
    // different Playwright release fails with a protocol mismatch, so it is not wired to a path override.
    { name: 'firefox', use: { ...devices['Desktop Firefox'], viewport: { width: 1280, height: 800 }, launchOptions: process.env.FIREFOX_PATH ? { executablePath: process.env.FIREFOX_PATH } : {} } },
    { name: 'webkit', use: { ...devices['Desktop Safari'], viewport: { width: 1280, height: 800 } } },
  ],
  webServer: {
    // Run serve directly: `npx` startup alone exceeded the 60 s limit on a loaded Windows machine.
    command: 'node node_modules/serve/build/main.js -s build -l 4173 --no-clipboard',
    url: 'http://127.0.0.1:4173',
    reuseExistingServer: !process.env.CI,
    timeout: 60000,
  },
});
