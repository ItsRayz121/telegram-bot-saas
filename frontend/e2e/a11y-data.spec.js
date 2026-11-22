// Accessibility on DATA-HEAVY signed-in states (populated lists, tables, charts, campaign workspaces).
// a11y.spec.js covers the shell and empty/loading states; this covers what users see with real content.
// Every API call is stubbed (the campaign fixture is a dump of real backend responses); nothing reaches production.
const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;
const { isolate } = require('./helpers');
const fx = require('./fixtures/guild-campaigns.json');

const GID = 9210;
const TG = 4242;
const USER = { id: 1, full_name: 'E2E User', email: 'e2e@example.com', email_verified: true, subscription_tier: 'pro', role: 'user', onboarding_completed_steps: [] };
const cors = (route) => ({
  'access-control-allow-origin': route.request().headers().origin || 'http://127.0.0.1:4173',
  'access-control-allow-credentials': 'true',
  'access-control-allow-headers': '*',
  'access-control-allow-methods': 'GET,POST,PUT,PATCH,DELETE,OPTIONS',
});
const json = (route, body, status = 200) => (route.request().method() === 'OPTIONS'
  ? route.fulfill({ status: 204, headers: cors(route) })
  : route.fulfill({ status, contentType: 'application/json', headers: cors(route), body: JSON.stringify(body) }));

const day = (n) => new Date(Date.UTC(2026, 10, 1 + n)).toISOString().slice(0, 10);
const ANALYTICS = {
  analytics: {
    summary: { member_joins: 480, verifications_passed: 392, verifications_failed: 31, automod_actions: 77, commands_used: 903 },
    daily_joins: Array.from({ length: 30 }, (_, i) => ({ date: day(i), count: 8 + ((i * 7) % 19) })),
    events_by_type: { member_joined: 480, verification_passed: 392, verification_failed: 31, automod_action: 77, command_triggered: 903 },
    recent_events: Array.from({ length: 12 }, (_, i) => ({
      id: i + 1, created_at: `2026-11-${10 + (i % 9)}T10:${10 + i}:00Z`,
      event_type: ['member_joined', 'verification_passed', 'verification_failed', 'automod_action'][i % 4], message: `Event number ${i + 1}`,
    })),
  },
};
const GROUPS = Array.from({ length: 8 }, (_, i) => ({
  id: TG + i, telegram_group_id: `-100${1000 + i}`, title: `Community ${i + 1}`, access_role: i % 3 ? 'owner' : 'admin', source: 'official',
  bot_status: i % 4 ? 'active' : 'inactive', linked_via_bot_type: 'official', last_activity: '2026-11-20T08:00:00Z', member_count: 120 + i * 40,
}));
const BOTS = Array.from({ length: 4 }, (_, i) => ({
  id: i + 1, bot_name: `Helper bot ${i + 1}`, bot_username: `helper${i + 1}_bot`, status: i % 2 ? 'active' : 'paused', health_status: i === 3 ? 'error' : 'ok',
  linked_groups_count: i, last_active: '2026-11-21T09:00:00Z', created_at: '2026-10-01T09:00:00Z',
}));

async function signIn(page) {
  await isolate(page);
  await page.addInitScript((u) => {
    localStorage.setItem('token', 'e2e');
    localStorage.setItem('user', JSON.stringify(u));
    localStorage.setItem('sidebar_collapsed', 'false');
    localStorage.setItem('telegizer_cookie_consent', 'declined');
  }, USER);
  await page.route('**/api/**', (r) => json(r, {}));
  await page.route('**/api/auth/me', (r) => json(r, { user: USER }));
}

async function settle(page) {
  await page.waitForLoadState('load');
  await page.waitForLoadState('networkidle', { timeout: 5000 }).catch(() => {});
  // Wait for every finite CSS/Web animation to finish (dialog and alert entrances, label transitions), so axe never
  // samples a half-faded element. Looping animations (spinners) are ignored.
  await page.evaluate(() => Promise.all(document.getAnimations()
    .filter((a) => a.effect && a.effect.getComputedTiming().iterations !== Infinity)
    .map((a) => a.finished.catch(() => {}))));
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

const CASES = [
  {
    name: 'group analytics with charts and an events table', route: `/groups/${TG}/analytics`, expect: /Event number 1/,
    stub: async (page) => {
      await page.route(`**/api/telegram-groups/${TG}`, (r) => json(r, { group: GROUPS[0] }));
      await page.route(`**/api/official-groups/${TG}/analytics*`, (r) => json(r, ANALYTICS));
    },
  },
  {
    name: 'groups list with several groups', route: '/groups', expect: /Community 3/,
    stub: async (page) => { await page.route('**/api/telegram-groups', (r) => json(r, { groups: GROUPS })); },
  },
  {
    name: 'bots list with mixed health', route: '/custom-bots', expect: /Helper bot 4/,
    stub: async (page) => {
      await page.route('**/api/custom-bots', (r) => json(r, { bots: BOTS }));
      await page.route('**/api/telegram-groups*', (r) => json(r, { groups: [] }));
    },
  },
];

const tgCampaignStub = async (page) => {
  const group = { id: TG, title: 'Main', telegram_group_id: '-1001', username: null };
  await page.route(`**/api/official-groups/${TG}/settings`, (r) => json(r, { group, owner_plan: 'free', access_role: 'owner', timezone: 'UTC' }));
  const base = `**/api/telegram-groups/${TG}/engagement`;
  await page.route(`${base}/overview*`, (r) => json(r, { ...fx.overview, x_autoverify_status: 'disabled' }));
  await page.route(`${base}/campaigns?*`, (r) => json(r, fx.campaigns));
  await page.route(`${base}/queue*`, (r) => json(r, fx.queue));
  await page.route(`${base}/campaigns/9301/summary*`, (r) => json(r, fx.summary));
  await page.route(`${base}/campaigns/9301/activity*`, (r) => json(r, fx.activity));
  await page.route(`**/api/telegram-groups/${TG}/campaigns/9301`, (r) => json(r, { campaign: fx.campaign }));
};

const guildStub = async (page) => {
  const guild = { ...fx.guild, id: String(GID), name: 'Main', is_pro: false, plan: 'free', channels: [{ id: '1', name: 'general', type: 0 }], roles: [] };
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
};

for (const [platform, base, stub] of [['telegizer', `/groups/${TG}/campaigns`, tgCampaignStub], ['guildizer', `/guildizer/servers/${GID}/campaigns`, guildStub]]) {
  for (const [label, suffix, expectText] of [['overview', '', /Active campaigns/], ['list', '/all', /Alpha quiz/], ['detail', '/9301', /Alpha quiz/]]) {
    CASES.push({ name: `${platform} campaign ${label} with recorded data`, route: base + suffix, expect: expectText, stub });
  }
}
CASES.push({
  name: 'guildizer campaign submissions table with recorded data', route: `/guildizer/servers/${GID}/campaigns/9301?tab=submissions`, expect: /Export all submissions/, stub: guildStub,
});

test.describe('axe: data-heavy signed-in states', () => {
  for (const c of CASES) {
    test(`${c.name} has no serious or critical violations`, async ({ page }) => {
      test.slow(true, 'axe over a populated page is slow, especially outside Chromium or on a busy machine');
      await signIn(page);
      await c.stub(page);
      await page.goto(c.route);
      await expect(page.locator('main#main-content')).toBeVisible();
      await expect(page.getByText(c.expect).locator('visible=true').first()).toBeVisible(); // proves the populated state rendered, not an empty/error shell
      await settle(page);
      expect(await axe(page)).toEqual([]);
    });
  }
});
