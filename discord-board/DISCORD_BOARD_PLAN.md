# Guildizer — Discord Board Full Build Plan

> **Product name: Guildizer.** Sister product to the Telegizer Telegram board. Replicates Telegizer's
> **functions** on Discord, built as a **100% isolated subfolder**. Created 2026-06-10.
> Note: name avoids the word "Discord" on purpose (Discord trademark rules); "guild" = Discord's word for a server.

---

## 0. The Isolation Rule (BINDING — never violate)

**Not one word of the existing Telegram/Telegizer code changes for anything Discord.**

- Lives in the **same repo** but in this **separate subfolder** (`discord-board/`).
- Uses the **same Vercel + Railway accounts**, but as **new, separate deploy targets**:
  - New Railway service (backend + worker) rooted at `discord-board/backend`, with its **own Postgres DB**.
  - New Vercel project rooted at `discord-board/frontend`.
- Has its **own env vars** (own Discord app, own DB URL, own webhook endpoints).
- The existing root deploy configs (`Procfile`, `railway.toml`, `railway.worker.toml`, `vercel.json`,
  root `requirements.txt`) are **never touched** — so the live Telegizer deploys can't break.
- Reused business logic (campaigns, leaderboards, XP, admin, billing, analytics) is **copied** into
  this folder — **never imported** from the Telegram code. Zero shared imports.

**Deploy scoping safeguard:** the new Railway service + Vercel project must have their **root directory**
set to `discord-board/...` so they only ever build the Discord subfolder, never the Telegram code.

---

## 1. Stack (mirrors Telegizer so logic copies cleanly)

| Layer | Telegizer (don't touch) | Discord board (new) |
|---|---|---|
| Bot | `python-telegram-bot`, polling | `discord.py`, Gateway (websocket) + slash commands |
| Backend | Flask + SQLAlchemy | Flask + SQLAlchemy (copy patterns) |
| Frontend | React (CRA) | React (copy component patterns) |
| Auth | Telegram Mini App `initData` | **Discord OAuth2** (cleaner) |
| DB | Postgres (Railway) | **separate** Postgres (Railway) |
| Billing | NOWPayments | NOWPayments (reuse account, new webhook endpoint) |
| Deploy | Railway + Vercel (root) | Railway + Vercel (**new services, subfolder root**) |

---

## 2. Folder layout (target)

```
discord-board/
  backend/        # Flask app, discord.py bot, models, routes  (own requirements.txt)
  frontend/       # React dashboard  (own package.json)
  DISCORD_BOARD_PLAN.md
```

---

## 3. Phased plan

### Phase 0 — Foundation & Isolation
- Create Discord Application (Dev Portal): bot token, client id/secret, OAuth2 redirect.
- New Railway project + Postgres; new Vercel project (roots set to `discord-board/...`).
- Scaffold Flask backend + React frontend + `discord.py` bot that connects and answers `/ping`.
- **Done when:** bot online in a test server, dashboard loads, round-trip works — zero Telegram coupling.

### Phase 1 — Auth & Server Onboarding
- Discord OAuth2 login (replaces Mini App auth).
- "Invite bot to server" OAuth2 flow with permission scopes.
- Sync guilds / channels / roles into DB. User ↔ server ↔ role models (copy *shape*, rewrite platform fields).
- **Done when:** user logs in, invites bot, sees servers/channels in dashboard.

### Phase 2 — Core Server Management
- Slash-command system (native Discord) + dashboard command builder (copy command logic, new registration layer).
- Welcome/leave messages, auto-roles, role management (lean into Discord's richer roles).
- Per-server settings + self-heal on startup (copy pattern).
- **Done when:** admin configures commands/welcome/auto-roles from dashboard; they work live.

### Phase 3 — Moderation & Protection
- Content filter on top of Discord **AutoMod** + own rules (copy `content_filter.py` logic).
- Raid Guard: join-spike behavior detection (copy `raid_guard.py`) + verification levels.
- Bot Policy join gate + manual emergency lockdown (copy Phase-4b logic).
- Protection Activity dashboard (copy, swap data source).
- Anti-ban paranoia → simple **rate-limit governor** (respect 429 buckets). Discord won't ban a well-behaved bot.
- **Done when:** full moderation suite live, Protection Activity tab populated.

### Phase 4 — Engagement Engine (the differentiator)
- XP / leveling (big proven market on Discord).
- Campaigns engine (copy `engagement.py` + multi-task logic).
- Proof flows via Discord interactions (buttons/modals replace deep-link DM flow — cleaner).
- Campaign leaderboards (copy, Pro-gated). Raid campaign type + webhook events.
- **Done when:** server runs a multi-task campaign with live leaderboard, proof via buttons.

### Phase 5 — Billing & Plans
- Copy plan/pricing model + feature-gating logic.
- Wire NOWPayments (reuse integration patterns, separate webhook endpoint).
- Pro gates on campaigns, leaderboards, advanced moderation.
- **Done when:** user upgrades to Pro and unlocks gated features.

### Phase 6 — Admin Panel
- Copy admin shell/sidebar, RBAC, feature-usage tracking spine, proof metrics, AI mgmt, secret vault patterns.
- Swap data sources Telegram models → Discord models.
- **Done when:** full admin board with drill-downs, user/server detail pages, usage analytics.

### Phase 7 — AI / Assistant (optional, Echo parity)
- Copy assistant logic: reminders, notes, AI search, workflows.
- Wire AI providers (reuse provider patterns + token-usage ledger).
- **Done when:** assistant features live in Discord DMs/threads.

### Phase 8 — Scaling, Verification & Launch
- **Sharding** (required past ~2,500 servers).
- **Discord bot verification + privileged intents** (message-content intent — apply EARLY, slow approval).
- Gateway load testing, graceful shutdown, final live test, launch.
- **Done when:** verified, sharded, production bot.

---

## 4. What to DROP (do not port)
- Custom-bot / "bring your own token" lineage — Telegram-specific (one verified Discord bot serves thousands of servers). Optional white-label upsell later.
- Mini App / `initData` auth bridge — replaced by OAuth2.
- Anti-ban paranoia — becomes a rate-limit governor.

## 5. Effort split
- **~75% value = business logic** already designed once → Phases 4–7 are mostly copy-and-rewire.
- **~25% = platform adapter** genuinely new → Phases 0–3, 8 are fresh Discord work.

---

## 6. Status
- [x] Plan written (2026-06-10)
- [x] Phase 0 — Foundation & Isolation (scaffold, `/ping`, isolated)
- [x] Phase 1 — Auth & Onboarding (Discord OAuth2 login, bot-invite flow, guild/channel/role sync, dashboard + server detail)
- [x] Phase 2 — Core Management (per-guild settings + self-heal, custom slash commands w/ dirty-flag resync, welcome/leave + auto-roles via Members intent, tabbed dashboard)
- [x] Phase 3 — Moderation & Protection (content_filter + moderation engine, behavior-based raid_guard, account-age join gate, manual lockdown, ProtectionEvent audit + Protection tab; rate-limit governor leans on discord.py)
- [x] Phase 4 — Engagement Engine (XP/leveling + /rank + /leaderboard; campaigns engine w/ multi-task, proof via persistent Discord buttons+modals, honor auto-verify, manual review→XP, Pro-gated campaign leaderboard, Guild.plan)
- [x] Phase 5 — Billing & Plans (NOWPayments checkout + HMAC-verified IPN webhook → flips Guild.plan=pro w/ stacking expiry; Subscription model; Billing tab. Decision: monetize engagement, never paywall safety)
- [x] Phase 6 — Admin Panel (RBAC via ADMIN_USER_IDS env, admin_api overview/guilds/users/campaigns/events drill-downs + manual plan grant; analytics derived from existing tables; gated /admin shell w/ sidebar)
- [x] Phase 7 — AI / Assistant (reminders /remind+/reminders w/ DM due loop, notes /note+/notes, AI /ask via Anthropic + AITokenUsage ledger, graceful when unconfigured. Workflows deferred.)
- [x] Phase 8 — Scaling & Launch (AutoShardedClient, one-time boot guard, SIGTERM graceful shutdown; SETUP.md env-var reference + verification + launch checklist). Manual remaining: create Railway/Vercel services, apply for Discord verification, live smoke test.

---

## 7. Build complete (2026-06-10)
All 9 phases (0–8) built, cross-checked, and pushed to `main`. Remaining work is
operational: provision the Railway services + Vercel project (subfolder roots),
set env vars (SETUP.md §C), enable privileged intents, apply for Discord
verification, and run the live smoke test (SETUP.md §D).

---

## 8. V2 — Full Telegizer Parity Program (started 2026-06-11)

V1 (phases 0–8) covers ~25% of Telegizer's audited feature surface. V2 closes the
gap with **Phases 9–20**, including the white-label custom-bot lineage. §4's
"drop custom bots" decision is **reversed** — owner requested full two-lineage
parity, and the analysis confirms it works on Discord.

Authoritative V2 docs (in `docs/`):
- `docs/TELEGIZER_FEATURE_AUDIT.md` — ~140-feature inventory + Discord compatibility matrix
- `docs/WHITE_LABEL_ARCHITECTURE.md` — custom/BYO-token bot architecture (Phase 9)
- `docs/PARITY_ROADMAP.md` — Phases 9–20 specs, commit strategy, risk plan

V2 status:
- [x] Audit, architecture, roadmap docs written (2026-06-11)
- [x] Phase 9 — White-label custom bot foundation (2026-06-11: bot_core.py shared engine, CustomBot + fleet manager, token vault, custom_bots_api, My Bots UI w/ connect wizard, bot-resolution rule. See CHANGELOG.md)
- [x] Phase 10 — Moderation parity pack (2026-06-11: automod matrix in extra JSON, warning ladder, MemberWarning/ModReport/ScheduledModAction, 13 mod commands + report context menu, tempban-expiry loop, reports queue UI. See CHANGELOG.md)
- [x] Phase 11 — Verification & onboarding parity (2026-06-11: quarantine-role captcha button/math/word w/ auto-setup + timeout sweep, bot policy w/ Trust/Kick buttons, welcome embed/rules/auto-delete. See CHANGELOG.md)
- [x] Phase 12 — Scheduling, polls & content (2026-06-11: ScheduledMessage w/ recurrence, native Discord polls w/ result capture, AutoResponse w/ cooldowns, content_loop both lineages, Content tab. See CHANGELOG.md)
- [x] Phase 13 — Automation engine (2026-06-11: AutomationWorkflow/Execution + 4 triggers/4 actions, webhook mirroring w/ author impersonation + self-heal, inbound token URLs -> queued posts, outbound HMAC events, Automation tab. See CHANGELOG.md)
- [x] Phase 14 — Engagement parity+ (2026-06-11: invite tracking + /invitelink + referral XP, campaign custom fields in proof modal, keyless oEmbed link checks, public proof feed. 14.6 join-auto-verify deferred. See CHANGELOG.md)
- [x] Phase 15 — CRM, analytics & usage spine (2026-06-11: Member CRM cols w/ heal, buffered GuildDailyStat rollups, FeatureUsageEvent via on_app_command_completion, /wallet /mywallet, Members + Analytics tabs. See CHANGELOG.md)
- [x] Phase 16 — Knowledge & applied AI (2026-06-11: KB-grounded /ask, smart-mod AI, image AI, escalation alerts, AI welcome, daily digest. See CHANGELOG.md)
- [x] Phase 17 — Assistant v1 (2026-06-11: Task + /task /tasks /done, DM AI assistant grounded on personal items, white-label assistant bots free via fleet. Full hub engine deferred. See CHANGELOG.md)
- [ ] Phase 18 — Teams, notifications & billing depth
- [ ] Phase 19 — Admin panel parity
- [ ] Phase 20 — Hardening, verification & launch
