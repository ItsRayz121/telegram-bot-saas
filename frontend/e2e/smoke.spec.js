const { test, expect } = require('@playwright/test');
const { isolate, PUBLIC_ROUTES } = require('./helpers');

test.beforeEach(async ({ page }) => { await isolate(page); });

for (const route of PUBLIC_ROUTES) {
  test(`public page ${route} renders without errors or sideways scroll`, async ({ page }) => {
    const errors = [];
    page.on('pageerror', (e) => errors.push(e.message));
    await page.goto(route);
    await expect(page.locator('h1:visible, h2:visible, h3:visible, h4:visible, h5:visible, h6:visible, input:visible').first()).toBeVisible();
    await expect(page.getByText('Something went wrong')).toHaveCount(0);
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, 'horizontal overflow in px').toBeLessThanOrEqual(1);
    expect(errors).toEqual([]);
  });
}

test('unknown URL does not crash the app', async ({ page }) => {
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.goto('/this-page-does-not-exist');
  await expect(page.locator('body')).not.toBeEmpty();
  await expect(page.getByText('Something went wrong')).toHaveCount(0);
  expect(errors).toEqual([]);
});

test('private page sends a logged-out visitor to login', async ({ page }) => {
  await page.goto('/dashboard');
  await expect(page).toHaveURL(/\/login/);
});

test('platform switcher navigates between products and exposes tab semantics', async ({ page }) => {
  await page.goto('/');
  const tablists = page.getByRole('tablist');
  await expect(tablists.first()).toBeVisible();
  await page.getByRole('tab', { name: /Discord/ }).click();
  await expect(page).toHaveURL(/guildizer-landing/);
});

test('losing the network shows the offline screen and recovers', async ({ page, context }) => {
  await page.goto('/');
  await context.setOffline(true);
  await page.evaluate(() => window.dispatchEvent(new Event('offline')));
  await expect(page.getByRole('alert')).toBeVisible({ timeout: 15000 });
  await context.setOffline(false);
  await page.evaluate(() => window.dispatchEvent(new Event('online')));
  await expect(page.getByRole('alert')).toHaveCount(0, { timeout: 20000 });
});
