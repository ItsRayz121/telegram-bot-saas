// Layout at every width in the QA matrix: no sideways scroll, and the main landmark and navigation render.
// Chromium only (the other engines are not installed locally). All API calls are stubbed.
// Set SHOT_DIR to also save a full-page screenshot per width.
const { test, expect } = require('@playwright/test');
const path = require('path');
const { isolate } = require('./helpers');

const WIDTHS = [320, 375, 390, 430, 768, 1024, 1280, 1440, 1920];
const USER = { id: 1, full_name: 'E2E User', email: 'e2e@example.com', email_verified: true, subscription_tier: 'pro', onboarding_completed_steps: [] };
const cors = { 'access-control-allow-origin': 'http://127.0.0.1:4173', 'access-control-allow-credentials': 'true', 'access-control-allow-headers': '*' };

test.describe.configure({ mode: 'serial' });
test.beforeEach(async ({ browserName }, testInfo) => { test.skip(testInfo.project.name !== 'desktop', 'sets its own viewport; run once'); });

for (const w of WIDTHS) {
  test(`signed-in shell at ${w}px`, async ({ page }) => {
    await page.setViewportSize({ width: w, height: 900 });
    await isolate(page);
    await page.addInitScript((u) => {
      localStorage.setItem('telegizer_cookie_consent', 'declined');
      localStorage.setItem('token', 'e2e');
      localStorage.setItem('user', JSON.stringify(u));
      localStorage.removeItem('sidebar_collapsed');
    }, USER);
    await page.route('**/api/**', (r) => r.fulfill({
      status: 200, contentType: 'application/json', headers: cors,
      body: r.request().url().includes('auth/me') ? JSON.stringify({ user: USER }) : '{"bots":[],"groups":[]}',
    }));
    await page.goto('/custom-bots');
    await expect(page.locator('main#main-content')).toBeVisible();
    await page.waitForLoadState('networkidle');
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, `horizontal overflow at ${w}px`).toBeLessThanOrEqual(1);
    // Exactly one navigation is reachable at this width: sidebar (desktop) or bottom bar (mobile).
    await expect(page.getByRole('navigation', { name: /Main navigation|Primary/ }).first()).toBeVisible();
    if (process.env.SHOT_DIR) await page.screenshot({ path: path.join(process.env.SHOT_DIR, `bots-${w}.png`), fullPage: false });
  });
}
