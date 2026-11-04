// Telegizer <-> Guildizer campaign workspace parity, in a real browser.
// The Guildizer fixture is a dump of the REAL backend responses (discord-board test fixtures);
// the same payloads are replayed through Telegizer's endpoints so both platforms render the same
// data through the same shared pages. Screenshots go to e2e/__parity__ (not baselines).
//   npm run e2e:build && npx playwright test e2e/campaigns-parity.spec.js --project=desktop
const { test, expect } = require('@playwright/test');
const path = require('path');
const fx = require('./fixtures/guild-campaigns.json');
const { isolate } = require('./helpers');

const OUT = path.join(__dirname, '__parity__');
const GID = 9210;
const TG = 4242;
const json = (route, body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
const pagesOf = (r) => r.url().split('?')[0];

async function login(page) {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'e2e');
    localStorage.setItem('user', JSON.stringify({ id: 1, email: 'e2e@example.com', email_verified: true, role: 'user' }));
  });
}

async function stubGuildizer(page) {
  const guild = { ...fx.guild, id: String(GID), name: 'Main', is_pro: false, plan: 'free',
    channels: [{ id: '1', name: 'general', type: 0 }, { id: '2', name: 'raids', type: 0 }], roles: [] };
  await page.route('**/api/**', (r) => json(r, {}));
  await page.route(`**/api/guilds/${GID}`, (r) => json(r, guild));
  await page.route(`**/api/guilds/${GID}/campaign-workspace/overview*`, (r) => json(r, fx.overview));
  await page.route(`**/api/guilds/${GID}/campaign-workspace/campaigns?*`, (r) => json(r, fx.campaigns));
  await page.route(`**/api/guilds/${GID}/campaign-workspace/queue*`, (r) => json(r, fx.queue));
  await page.route(`**/api/guilds/${GID}/campaign-workspace/campaigns/9301/summary*`, (r) => json(r, fx.summary));
  await page.route(`**/api/guilds/${GID}/campaign-workspace/campaigns/9301/activity*`, (r) => json(r, fx.activity));
  await page.route(`**/api/guilds/${GID}/campaigns/9301`, (r) => json(r, fx.campaign));
  await page.route(`**/api/guilds/${GID}/campaigns/9301/submissions*`, (r) => json(r, fx.subs));
  await page.route(`**/api/guilds/${GID}/campaigns/9301/leaderboard*`, (r) => json(r, { locked: false, rows: [] }));
  await page.route('**/api/account/x-verify-key', (r) => json(r, { configured: false, status: 'disabled' }));
}

async function stubTelegizer(page) {
  const group = { id: TG, title: 'Main', telegram_group_id: '-1001', username: null };
  await page.route('**/api/**', (r) => json(r, {}));
  await page.route(`**/api/official-groups/${TG}/settings`, (r) => json(r, { group, owner_plan: 'free', access_role: 'owner', timezone: 'UTC' }));
  const base = `**/api/telegram-groups/${TG}/engagement`;
  await page.route(`${base}/overview*`, (r) => json(r, { ...fx.overview, x_autoverify_status: 'disabled' }));
  await page.route(`${base}/campaigns?*`, (r) => json(r, fx.campaigns));
  await page.route(`${base}/queue*`, (r) => json(r, fx.queue));
  await page.route(`${base}/campaigns/9301/summary*`, (r) => json(r, fx.summary));
  await page.route(`${base}/campaigns/9301/activity*`, (r) => json(r, fx.activity));
  await page.route(`**/api/telegram-groups/${TG}/campaigns/9301`, (r) => json(r, { campaign: fx.campaign }));
}

const MAIN_TABS = ['Overview', 'Campaigns', 'Review queue'];
const DETAIL_TABS = ['Summary', 'Submissions', 'Results & rewards', 'Activity', 'Settings'];

const PLATFORMS = [
  { name: 'telegizer', base: `/groups/${TG}/campaigns`, stub: stubTelegizer, noun: 'group' },
  { name: 'guildizer', base: `/guildizer/servers/${GID}/campaigns`, stub: stubGuildizer, noun: 'server' },
];

for (const P of PLATFORMS) {
  test.describe(P.name, () => {
    test.beforeEach(async ({ page }) => { await isolate(page); await login(page); await P.stub(page); });

    for (const [route, label, shot] of [['', 'overview', 'overview'], ['/all', 'list', 'campaigns'], ['/review', 'review', 'review-queue']]) {
      test(`${label} renders with the three workspace tabs`, async ({ page }) => {
        const errors = [];
        page.on('pageerror', (e) => errors.push(e.message));
        await page.goto(P.base + route);
        await expect(page.getByRole('heading', { name: 'Campaigns', level: 1 })).toBeVisible();
        for (const t of MAIN_TABS) await expect(page.getByRole('tab', { name: new RegExp(`^${t}`) })).toBeVisible();
        await expect(page.getByText('Something went wrong')).toHaveCount(0);
        if (label === 'overview') await expect(page.getByText('Active campaigns').first()).toBeVisible();
        if (label === 'list') await expect(page.getByText('Alpha quiz').first()).toBeVisible();
        if (label === 'review') await expect(page.getByText('Submitted proof').first()).toBeVisible();
        await page.screenshot({ path: path.join(OUT, `${P.name}-${shot}.png`), fullPage: true });
        expect(errors).toEqual([]);
      });
    }

    test('campaign page has Summary / Submissions / Results / Activity / Settings', async ({ page }) => {
      const errors = [];
      page.on('pageerror', (e) => errors.push(e.message));
      await page.goto(`${P.base}/9301`);
      await expect(page.getByRole('heading', { name: 'Alpha quiz' })).toBeVisible();
      for (const t of DETAIL_TABS) await expect(page.getByRole('tab', { name: t })).toBeVisible();
      await expect(page.getByText('Pending review').first()).toBeVisible();
      await page.screenshot({ path: path.join(OUT, `${P.name}-campaign-summary.png`), fullPage: true });
      await page.getByRole('tab', { name: 'Activity' }).click();
      await expect(page.getByText('Real history only')).toBeVisible();
      await page.screenshot({ path: path.join(OUT, `${P.name}-campaign-activity.png`), fullPage: true });
      expect(errors).toEqual([]);
    });
  });
}

test.describe('guildizer only (Discord forms in page mode)', () => {
  test.beforeEach(async ({ page }) => { await isolate(page); await login(page); await stubGuildizer(page); });

  test('submissions, results and settings tabs mount the Discord forms', async ({ page }) => {
    const errors = [];
    page.on('pageerror', (e) => errors.push(e.message));
    await page.goto(`/guildizer/servers/${GID}/campaigns/9301?tab=submissions`);
    await expect(page.getByRole('button', { name: /Export all submissions/ })).toBeVisible();
    await expect(page.getByText('ann').first()).toBeVisible();
    await page.screenshot({ path: path.join(OUT, 'guildizer-campaign-submissions.png'), fullPage: true });
    await page.getByRole('tab', { name: 'Results & rewards' }).click();
    await expect(page.getByRole('button', { name: /Pick Winners/ })).toBeVisible();
    await page.screenshot({ path: path.join(OUT, 'guildizer-campaign-results.png'), fullPage: true });
    await page.getByRole('tab', { name: 'Settings' }).click();
    await expect(page.getByText('Edit campaign')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Save changes' })).toBeVisible();
    await page.screenshot({ path: path.join(OUT, 'guildizer-campaign-settings.png'), fullPage: true });
    expect(errors).toEqual([]);
  });

  test('create flow: type picker, wizard steps, review step offers draft and publish', async ({ page }) => {
    const errors = [];
    page.on('pageerror', (e) => errors.push(e.message));
    await page.route(`**/api/guilds/${GID}/campaigns/preview`, (r) => r.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ embed: { title: 'Preview', description: 'd', fields: [] }, buttons: ['Submit proof'], notices: [] }) }));
    await page.goto(`/guildizer/servers/${GID}/campaigns/new`);
    await expect(page.getByText('What kind of campaign?')).toBeVisible();
    await page.screenshot({ path: path.join(OUT, 'guildizer-create-type.png'), fullPage: true });
    await page.getByText('Proof Collection').first().click();
    await expect(page).toHaveURL(/type=proof_collection/);
    await page.getByLabel('Title').fill('E2E campaign');
    await page.getByRole('button', { name: 'Next' }).click();
    await page.getByRole('button', { name: 'Next' }).click();
    await expect(page.getByText('What members will see in Discord')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Save as draft' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Publish now' })).toBeVisible();
    await page.screenshot({ path: path.join(OUT, 'guildizer-create-review.png'), fullPage: true });
    expect(errors).toEqual([]);
  });
});
