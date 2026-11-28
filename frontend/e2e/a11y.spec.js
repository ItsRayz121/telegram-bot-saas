// Accessibility: axe-core on every public page and on the signed-in shell, plus the keyboard
// behaviours axe cannot see. Every API call is stubbed; nothing reaches production.
const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;
const { isolate, PUBLIC_ROUTES } = require('./helpers');

const cors = (route) => ({
  'access-control-allow-origin': route.request().headers().origin || 'http://127.0.0.1:4173',
  'access-control-allow-credentials': 'true',
  'access-control-allow-headers': '*',
  'access-control-allow-methods': 'GET,POST,PUT,PATCH,DELETE,OPTIONS',
});
const json = (route, body, status = 200) => (route.request().method() === 'OPTIONS'
  ? route.fulfill({ status: 204, headers: cors(route) })
  : route.fulfill({ status, contentType: 'application/json', headers: cors(route), body: JSON.stringify(body) }));

const USER = { id: 1, full_name: 'E2E User', email: 'e2e@example.com', email_verified: true, subscription_tier: 'pro', onboarding_completed_steps: [] };

async function signIn(page, onWrite = (r) => json(r, {})) {
  await isolate(page);
  await page.addInitScript((u) => {
    localStorage.setItem('token', 'e2e');
    localStorage.setItem('user', JSON.stringify(u));
    localStorage.setItem('sidebar_collapsed', 'false');
    localStorage.setItem('telegizer_cookie_consent', 'declined');
  }, USER);
  await page.route('**/api/**', (r) => json(r, {}));
  await page.route('**/api/auth/me', (r) => json(r, { user: USER }));
  await page.route('**/api/custom-bots', (r) => (r.request().method() === 'GET' ? json(r, { bots: [] }) : onWrite(r)));
  await page.route('**/api/telegram-groups*', (r) => json(r, { groups: [] }));
}

// Firefox never reports "network idle" while the isolation layer is aborting third-party requests (measured:
// all requests on /echo finish within ~1.2 s and nothing follows). Wait for `load`, then give idle a bounded chance.
async function settle(page) {
  await page.waitForLoadState('load');
  await page.waitForLoadState('networkidle', { timeout: 5000 }).catch(() => {});
  // Wait for every finite CSS/Web animation to finish (dialog and alert entrances, label transitions), so axe never
  // samples a half-faded element. Looping animations (spinners) are ignored.
  await page.evaluate(() => Promise.all(document.getAnimations()
    .filter((a) => a.effect && a.effect.getComputedTiming().iterations !== Infinity)
    .map((a) => a.finished.catch(() => {}))));
  // The homepage hero chat fades its messages in with GSAP (JS-driven, invisible to getAnimations()):
  // wait until every message is fully opaque, or axe measures half-faded text as low contrast.
  await page.waitForFunction(() => [...document.querySelectorAll('.m')]
    .every((el) => getComputedStyle(el).opacity === '1'), null, { timeout: 15000 }).catch(() => {});
}

// Right before analysing, wait until no finite animation is running (a late-mounting alert or dialog may start one
// after the page settled), re-checking a few times so axe never samples a half-faded element.
async function animationsDone(page) {
  for (let i = 0; i < 4; i += 1) {
    const pending = await page.evaluate(() => Promise.all(document.getAnimations()
      .filter((a) => a.effect && a.effect.getComputedTiming().iterations !== Infinity)
      .map((a) => a.finished.then(() => 1, () => 1))).then((r) => r.length));
    await page.waitForTimeout(120);
    if (!pending) return;
  }
}

async function axe(page) {
  await animationsDone(page);
  const res = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze();
  return res.violations
    .filter((v) => v.impact === 'serious' || v.impact === 'critical')
    .map((v) => `${v.id} (${v.impact}): ${v.nodes.slice(0, 3).map((n) => n.target.join(' ')).join(' | ')}`);
}

test.describe('axe: public pages', () => {
  test.beforeEach(async ({ page }) => {
    await isolate(page);
    await page.addInitScript(() => localStorage.setItem('telegizer_cookie_consent', 'declined'));
  });
  for (const route of PUBLIC_ROUTES) {
    test(`${route} has no serious or critical violations`, async ({ page }, testInfo) => {
      // Measured: navigation + axe on the landing page alone takes ~17 s in Firefox (~3 s in Chrome).
      test.slow(testInfo.project.name === 'firefox', 'axe is slower in Firefox');
      await page.goto(route);
      await settle(page);
      expect(await axe(page)).toEqual([]);
    });
  }
});

test.describe('signed-in shell', () => {
  test.beforeEach(async ({ page }) => { await signIn(page); });

  test('bots page has no serious or critical violations', async ({ page }) => {
    await page.goto('/custom-bots');
    await expect(page.locator('main#main-content')).toBeVisible();
    await settle(page);
    expect(await axe(page)).toEqual([]);
  });

  test('navigation is a landmark, marks the current page, and a skip link reaches main', async ({ page, isMobile, browserName }) => {
    // WebKit's Tab key skips links unless a Safari preference is enabled, so keyboard-focusing the skip link cannot be tested there.
    test.skip(browserName === 'webkit', 'WebKit does not Tab to links by default');
    await page.goto('/custom-bots');
    await settle(page);
    await expect(page.locator('main#main-content')).toHaveCount(1);
    await page.keyboard.press('Tab');
    await expect(page.getByRole('link', { name: 'Skip to main content' })).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(page.locator('main#main-content')).toBeFocused();
    if (isMobile) {
      await expect(page.getByRole('navigation', { name: 'Primary' }).locator('[aria-current="page"]')).toHaveCount(1);
    } else {
      await expect(page.getByRole('navigation', { name: 'Main navigation' }).locator('[aria-current="page"]')).toContainText('Bots');
    }
  });

  test('sidebar controls are operable with the keyboard (desktop)', async ({ page, isMobile }) => {
    test.skip(isMobile, 'desktop sidebar');
    await page.goto('/custom-bots');
    await settle(page);
    const account = page.getByRole('button', { name: /E2E User/  });
    await account.focus();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('menuitem', { name: 'Billing and plan' })).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('menuitem', { name: 'Billing and plan' })).toBeHidden();
    await expect(account).toBeFocused();
  });

  test('mobile drawer opens, closes on Escape and returns focus', async ({ page, isMobile }) => {
    test.skip(!isMobile, 'mobile drawer');
    await page.goto('/custom-bots');
    await settle(page);
    const open = page.getByRole('button', { name: 'Open menu' });
    await open.click();
    await expect(page.getByRole('navigation', { name: 'Main navigation' })).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('navigation', { name: 'Main navigation' })).toBeHidden();
    await expect(open).toBeFocused();
  });

  test('reduced motion removes transitions and animations app-wide', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto('/custom-bots');
    await settle(page);
    const offenders = await page.evaluate(() => {
      const bad = [];
      const dur = (v) => Math.max(0, ...v.split(',').map((x) => parseFloat(x) * (x.includes('ms') ? 1 : 1000)));
      for (const el of document.querySelectorAll('body *')) {
        const cs = getComputedStyle(el);
        if (dur(cs.transitionDuration) > 20 || dur(cs.animationDuration) > 20) bad.push(`${el.tagName}.${String(el.className).slice(0, 40)}`);
      }
      return bad.slice(0, 5);
    });
    expect(offenders).toEqual([]);
  });
});

test.describe('connect bot dialog', () => {
  const TOKEN = '123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA';

  test('verify then connect, honest wording, Enter to verify, no closing mid-request', async ({ page }) => {
    let added = 0;
    await signIn(page, (r) => { added += 1; return json(r, { ok: true }); });
    // Held open until the test releases it, so "mid-request" is deterministic on a slow machine
    // (a fixed timer could expire before Escape is pressed, and Escape then rightly closes the dialog).
    let release;
    const gate = new Promise((res) => { release = res; });
    await page.route('**/api/custom-bots/validate-token', async (r) => {
      await gate;
      return json(r, { bot_name: 'Demo', bot_username: 'demo_bot', can_join_groups: true });
    });
    await page.goto('/custom-bots?connect=1');
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText('/newbot')).toBeVisible();

    await dialog.getByLabel('Bot Token').fill('hello');
    await expect(dialog.getByText(/does not look like a bot token/)).toBeVisible();
    await dialog.getByLabel('Bot Token').fill(TOKEN);
    await expect(dialog.getByText(/does not look like|incomplete/)).toHaveCount(0);

    await dialog.getByLabel('Bot Token').press('Enter');
    await expect(dialog.getByRole('button', { name: /Verifying/ })).toBeDisabled();
    await expect(dialog.getByRole('button', { name: 'Cancel' })).toBeDisabled();
    await page.keyboard.press('Escape');
    await expect(dialog).toBeVisible(); // closing mid-request is blocked
    release();

    await expect(dialog.getByText(/not connected yet/)).toBeVisible();
    expect(added).toBe(0); // verifying must not save anything
    await dialog.getByRole('button', { name: 'Connect Bot' }).click();
    await expect(dialog).toBeHidden();
    expect(added).toBe(1);
  });

  test('a rejected token shows the server reason, keeps the token and allows retry', async ({ page }) => {
    await signIn(page);
    await page.route('**/api/custom-bots/validate-token', (r) => json(r, { error: 'Telegram rejected this token.' }, 400));
    await page.goto('/custom-bots?connect=1');
    const dialog = page.getByRole('dialog');
    await dialog.getByLabel('Bot Token').fill(TOKEN);
    await dialog.getByRole('button', { name: 'Verify Token' }).click();
    await expect(dialog.getByRole('alert').filter({ hasText: 'Telegram rejected this token.' })).toBeVisible();
    await expect(dialog.getByLabel('Bot Token')).toHaveValue(TOKEN);
    await expect(dialog.getByRole('button', { name: 'Verify Token' })).toBeEnabled();
  });
});

// Signed-in routes beyond the bots page. API answers are generic empty payloads, so this checks the
// shell, headings, labels and contrast of each page's empty/loading state, not data-heavy states.
const SIGNED_IN_ROUTES = [
  '/dashboard', '/groups', '/groups/4242', '/groups/4242/analytics', '/groups/4242/manage', '/groups/4242/campaigns',
  '/channels', '/ark', '/workspace', '/integrations', '/tasks', '/marketplace/deals',
  '/guildizer', '/guildizer/bots', '/guildizer/servers', '/guildizer/notifications', '/guildizer/referrals',
];
test.describe('axe: signed-in routes', () => {
  test.beforeEach(async ({ page }) => { await signIn(page); });
  for (const route of SIGNED_IN_ROUTES) {
    test(`${route} has no serious or critical violations`, async ({ page }) => {
      await page.goto(route);
      await expect(page.locator('main#main-content')).toBeVisible();
      await settle(page);
      expect(await axe(page)).toEqual([]);
    });
  }
});
