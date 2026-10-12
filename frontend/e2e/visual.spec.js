const { test, expect } = require('@playwright/test');
const { isolate } = require('./helpers');

// Above-the-fold snapshots of the pages that carry the brand. Baselines live in
// e2e/__screenshots__. After an intended design change run `npm run e2e:update`
// and review the image diff in the commit.
const PAGES = { landing: '/', pricing: '/pricing', login: '/login', echo: '/echo' };

for (const [name, route] of Object.entries(PAGES)) {
  test(`visual: ${name}`, async ({ page }, info) => {
    await isolate(page);
    await page.goto(route);
    await page.waitForLoadState('networkidle');
    // The landing hero has JS-driven motion, so it gets a looser threshold and more time to settle.
    const loose = name === 'landing';
    await expect(page).toHaveScreenshot(`${name}-${info.project.name}.png`, {
      fullPage: false, timeout: 20000, maxDiffPixelRatio: loose ? 0.08 : 0.02,
    });
  });
}
