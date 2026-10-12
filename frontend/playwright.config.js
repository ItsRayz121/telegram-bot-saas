// End-to-end + visual regression tests. They run against the PRODUCTION BUILD
// served locally, with every network call to a third party or the API stubbed,
// so they are deterministic and never touch live data.
//   npm run build   (needs CI unset/false)   then   npm run e2e
//   npm run e2e:update   regenerates screenshot baselines after an intended UI change
const { defineConfig, devices } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './e2e',
  timeout: 30000,
  retries: process.env.CI ? 1 : 0,
  reporter: [['list']],
  // Baselines are not suffixed with the OS name, so they must be generated on the
  // platform CI uses; the small tolerance absorbs font anti-aliasing noise.
  snapshotPathTemplate: '{testDir}/__screenshots__/{testFilePath}/{arg}{ext}',
  expect: { toHaveScreenshot: { maxDiffPixelRatio: 0.02, animations: 'disabled' } },
  // Locally use the installed Chrome (no browser download); CI uses bundled Chromium.
  use: { baseURL: 'http://127.0.0.1:4173', ...devices['Desktop Chrome'], channel: process.env.CI ? undefined : 'chrome' },
  projects: [
    { name: 'desktop', use: { viewport: { width: 1280, height: 800 } } },
    { name: 'mobile', use: { ...devices['Pixel 5'] } },
  ],
  webServer: {
    command: 'npx serve -s build -l 4173 --no-clipboard',
    url: 'http://127.0.0.1:4173',
    reuseExistingServer: !process.env.CI,
    timeout: 60000,
  },
});
