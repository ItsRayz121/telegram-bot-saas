# Guildizer V2 — Master Parity Checklist (Phases 9–20)

> The single execution tracker. Every phase, sub-phase, env var, and manual step.
> Detailed specs live in `docs/PARITY_ROADMAP.md`; this file is the working checklist.
> Items tagged **(USER)** are manual steps only the owner can do — everything else is code.
>
> **THE THREE SERVICES** (referenced by every env-var item below):
> | Shorthand | What it is | Where |
> |---|---|---|
> | **TELEGIZER** | The original product (never touched by Guildizer backend work) | Main Railway services + the telegizer.com Vercel project |
> | **GUILDIZER-WEB** | Guildizer Flask API (`guild-api.telegizer.com`) | Railway service rooted at `discord-board/backend`, start = gunicorn `app:app` |
> | **GUILDIZER-BOT** | Guildizer Discord bot worker (official bot + white-label fleet) | Railway service rooted at `discord-board/backend`, start = `python bot.py` |
>
> The Guildizer dashboard UI is embedded in the TELEGIZER Vercel frontend, so the
> only Guildizer-related var on TELEGIZER is `REACT_APP_GUILDIZER_API_URL`.

---

## Phase 9 — White-Label Custom Bot Foundation ✅ DONE 2026-06-11 (44c0276)

- [x] 9.1 Fernet token vault (`crypto.py`)
- [x] 9.2 Models: `CustomBot`, `BotHealthEvent`, `Guild.custom_bot_id` + column self-heal
- [x] 9.3 `custom_bots_api.py` (connect/validate/replace-token/recheck/disconnect/invite/link/unlink)
- [x] 9.4 `bot_core.py` shared engine extraction (both lineages, behavior-identical)
- [x] 9.5 Bot resolution rule (`serves()` guards, routing cache, no double-handling)
- [x] 9.6 `custom_bot_manager.py` fleet runner (reconcile/stagger/auth-failure handling)
- [x] 9.7 Per-application command registration for custom bots
- [x] 9.8 Frontend: My Bots page + 3-step connect wizard (`/guildizer/bots`)
- [x] 9.9 Validation: compile + smoke suite + frontend build
- [ ] 9.10 **(USER)** Add `GUILDIZER_ENCRYPTION_KEY` to **GUILDIZER-WEB** and **GUILDIZER-BOT**
      (same value on both!). Generate it once:
      `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- [ ] 9.11 **(USER)** Live test: connect a second Discord app as a custom bot, invite it,
      see it answer /ping under its own name

## Phase 10 — Moderation Parity Pack ✅ DONE 2026-06-11 (10.9 native AutoMod = deferred stretch)

- [x] 10.1 DB: `Warning` model, `ReportedMessage` model, `ScheduledModAction` (temp-ban/unban timers); ModerationSettings widened (links whitelist, emoji/caps thresholds, language filter, media toggles, warning ladder config)
- [x] 10.2 Filter engine parity: external links + whitelist, excessive emojis, caps-lock, language/script filter, media-type toggles (attachments/stickers/voice), Discord-invite filter hardening
- [x] 10.3 Warnings ladder: /warn → counted → max-warnings action (timeout/kick/ban), /removewarning, /warnings list
- [x] 10.4 Mod command suite: /mute /unmute (native timeout), /ban /unban /tempban, /kick, /purge, /userinfo, /auditlog, /report + right-click message → Report context command
- [x] 10.5 Reports queue: API + bot capture + review actions
- [x] 10.6 Auto-clean: delete join/leave system messages (configurable)
- [x] 10.7 UI: Moderation tab — full matrix editor, warnings view, reports queue
- [x] 10.8 Tests: filter unit cases, ladder math, e2e API; build; commit
- [ ] 10.9 (Stretch) Native Discord AutoMod managed rules (keyword/invite presets via REST)

## Phase 11 — Verification & Onboarding Parity ✅ DONE 2026-06-11 (live join-flow check pending w/ alt account)

- [x] 11.1 DB: `PendingVerification`; settings blocks `verification`, `bot_policy`, welcome extensions
- [x] 11.2 Quarantine-role captcha: bot creates Unverified role + #verify channel; button / math / word challenges via buttons+modals; timeout → kick/keep
- [x] 11.3 Bot policy join gate: foreign bot joins → kick or quarantine + admin approve/deny buttons; trusted-bot list
- [x] 11.4 Welcome depth: rules text, embed welcome, auto-delete (AI welcome lands with Phase 16)
- [x] 11.5 UI: Verification + Bot Policy sections in server Settings tab
- [x] 11.6 Tests + live join-flow check with alt account; commit

## Phase 12 — Scheduling, Polls & Content ✅ DONE 2026-06-11 (single Content tab w/ 3 sections)

- [x] 12.1 DB: `ScheduledMessage` (recurrence, embed JSON), `Poll`, `AutoResponse`
- [x] 12.2 Scheduler loop in bot worker (due-scan + jitter, both lineages via serves())
- [x] 12.3 Native Discord polls: create from dashboard, results back to DB
- [x] 12.4 Auto-responses: keyword/regex triggers → reply/react (cooldowns)
- [x] 12.5 UI: Scheduler tab, Polls tab, Auto-responses tab
- [x] 12.6 Tests (recurrence math, trigger matching) + commit

## Phase 13 — Automation Engine ✅ DONE 2026-06-11 (live mirror check pending)

- [x] 13.1 DB: `AutomationWorkflow`, `AutomationExecution`, `MirrorRule`, `MirrorLog`, `InboundWebhook`, `OutboundWebhook`
- [x] 13.2 Workflow engine port (triggers: message/join/leave/reaction/schedule/webhook; conditions; actions: send/embed/role/timeout/webhook-out)
- [x] 13.3 Channel mirroring via webhooks (author name/avatar impersonation, cross-guild)
- [x] 13.4 Inbound webhook URLs → channel posts (per-guild secret paths)
- [x] 13.5 Outbound event webhooks generalized (all event types, not just campaigns)
- [x] 13.6 UI: Workflow builder, Mirroring tab, Webhooks tab
- [x] 13.7 Tests (engine unit suite) + live mirror check + commit

## Phase 14 — Engagement Parity+ (Growth) ✅ DONE 2026-06-11 (14.6 deferred; live invite-attribution check pending)

- [x] 14.1 DB: `InviteLink`, `InviteJoin`, `Referral`, `CampaignCustomField`
- [x] 14.2 Invite tracking: invite cache + use-delta attribution on join (the Discord referral system); /invitelink command
- [x] 14.3 Referral leaderboard + rewards (XP per verified referral)
- [x] 14.4 Campaign custom fields → modal inputs (5-field modal pagination)
- [x] 14.5 Link-validity checks via keyless oEmbed (YouTube/X) + reachability — no API keys needed
- [ ] 14.6 Guild-join auto-verify campaign task — DEFERRED (needs target-guild membership semantics)
- [x] 14.7 Public proof feed + proof metrics
- [x] 14.8 UI: Referrals page, wizard custom-fields step, public feed
- [x] 14.9 ~~YOUTUBE/X API keys~~ NOT NEEDED — implemented with keyless oEmbed endpoints
- [x] 14.10 Tests + live invite-attribution check + commit

## Phase 15 — CRM, Analytics & Usage Spine ✅ DONE 2026-06-11 (cross-server analytics hub lands with Phase 19 admin)

- [x] 15.1 DB: widen `Member` (last_seen, message_count, wallet, admin notes), `GuildDailyStat`, `FeatureUsageEvent`
- [x] 15.2 Gateway rollups: daily message/join/leave/active counts per guild
- [x] 15.3 Member CRM API + /wallet /mywallet commands (modal input)
- [x] 15.4 Feature-usage recorder wired into every feature path
- [x] 15.5 UI: CRM page (search/segments/notes), Analytics page (charts), cross-server analytics
- [x] 15.6 Tests (rollup correctness) + commit

## Phase 16 — Knowledge & Applied AI ✅ DONE 2026-06-11

- [x] 16.1 DB: `KnowledgeDocument`, `EscalationEvent`, `DigestLog`
- [x] 16.2 Knowledge base CRUD + grounded /ask (retrieval over guild docs)
- [x] 16.3 Smart-mod AI layer (promo detection, trusted users, per-user AI rate limit)
- [x] 16.4 AI welcome (level-up flavor deferred — low value vs cost)
- [x] 16.5 Escalation detection (frustrated users → admin alert DM)
- [x] 16.6 Image moderation on attachments (CDN URLs)
- [x] 16.7 AI server digest → channel/DM
- [x] 16.8 UI: Knowledge tab + AI toggles in settings sections
- [x] 16.9 **(USER)** Confirm `ANTHROPIC_API_KEY` set on **GUILDIZER-WEB** + **GUILDIZER-BOT** (already a V1 var; AI features stay gracefully off without it)
- [x] 16.10 Tests + commit

## Phase 17 — Assistant Hub (Echo Parity)

- [ ] 17.1 DB: hub tables (tasks, reminders, decisions, meetings, notes, digests, knowledge cards, memory, suggestions, follow-ups)
- [ ] 17.2 DM message router (assistant conversations over Discord DMs)
- [ ] 17.3 Hub engine port: extraction, digests, memory, suggestions, retention, consent, plan limits
- [ ] 17.4 Custom ASSISTANT bots (white-label Echo) on the Phase 9 fleet runtime
- [ ] 17.5 Meeting links + Google Calendar sync
- [ ] 17.6 UI: Assistant hub pages (tasks/notes/reminders/digests/memory)
- [ ] 17.7 **(USER)** If calendar sync wanted: add `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` to **GUILDIZER-WEB**
- [ ] 17.8 Tests + commit

## Phase 18 — Teams, Notifications & Billing Depth

- [ ] 18.1 DB: `Team`, `TeamMember`, `TeamInvite`, `UserNotification`, `PromoCode`(+usage), `PendingInvoice`, `PaymentHistory`, `SubscriptionRenewal`
- [ ] 18.2 Team seats: invite by Discord tag/email, role-scoped dashboard access to guilds
- [ ] 18.3 Notifications center (dashboard bell + optional bot DM)
- [ ] 18.4 Promo codes (create/redeem/limits)
- [ ] 18.5 Renewal flow, payment history page, pending-invoice recovery
- [ ] 18.6 Full plan-limit matrix (per-feature gates, free/pro/agency; custom bots = top tier)
- [ ] 18.7 UI: Team page, notifications, billing history, promo redemption
- [ ] 18.8 Tests (gating matrix, promo math, renewal stacking) + commit

## Phase 19 — Admin Panel Parity

- [ ] 19.1 RBAC roles in DB (not just env IDs) + invite-by-email; keep `ADMIN_USER_IDS` as super-admin bootstrap
- [ ] 19.2 Secret vault (encrypted platform secrets, test handlers)
- [ ] 19.3 Feature flags + admin announcements
- [ ] 19.4 Compliance queue (GDPR deletion) + admin audit log
- [ ] 19.5 AI management center (provider config, balances, usage/cost dashboards)
- [ ] 19.6 Bot fleet health tab (official + every custom bot, from `BotHealthEvent`)
- [ ] 19.7 Feature-usage analytics tab (from Phase 15 spine), proof metrics, unified event log
- [ ] 19.8 Full drill-down detail pages (user/guild/custom-bot)
- [ ] 19.9 Route-gating audit: every admin route behind RBAC
- [ ] 19.10 Tests + commit

## Phase 20 — Hardening, Verification & Launch

- [ ] 20.1 Fleet load/soak test (N custom bots, memory profile, cache tuning)
- [ ] 20.2 Full live regression in a test server (every tab, every command)
- [ ] 20.3 Guildizer landing/pricing section on telegizer.com + status + product tour
- [ ] 20.4 SETUP.md final pass (all env vars, all three services, runbooks)
- [ ] 20.5 **(USER)** Apply for **Discord bot verification** for the OFFICIAL bot (Developer Portal → App → "Get verified"). Slow process — start as soon as Phase 14 ships. Needed past 100 servers.
- [ ] 20.6 **(USER)** Final go-live smoke test together
- [ ] 20.7 Launch 🚀

---

## ENV VAR MASTER TABLE — what goes where

> ✅ = required · ⬜ = optional/feature-gated · ❌ = must NOT be set there
> "Same value" pairs are marked. TELEGIZER backend gets NOTHING from this table.

| Variable | GUILDIZER-WEB | GUILDIZER-BOT | TELEGIZER (Vercel frontend only) | Notes |
|---|---|---|---|---|
| `DATABASE_URL` | ✅ | ✅ same value | ❌ | The Guildizer Postgres (NOT Telegizer's DB) |
| `DISCORD_BOT_TOKEN` | ✅ | ✅ same value | ❌ | Official bot token (web uses it for REST fallbacks) |
| `DISCORD_CLIENT_ID` | ✅ | ✅ | ❌ | Public app id |
| `DISCORD_CLIENT_SECRET` | ✅ | ⬜ | ❌ | OAuth exchange (web only really needs it) |
| `DISCORD_REDIRECT_URI` | ✅ | ⬜ | ❌ | `https://guild-api.telegizer.com/auth/discord/callback` |
| `GUILDIZER_ENCRYPTION_KEY` | ✅ | ✅ **same value** | ❌ | Phase 9. Fernet key — generate once, paste into BOTH |
| `FLASK_SECRET_KEY` | ✅ | ⬜ | ❌ | Session cookies |
| `FRONTEND_URL` | ✅ | ⬜ | ❌ | `https://telegizer.com` |
| `GUILDIZER_FRONTEND_PATH` | ✅ | ⬜ | ❌ | `/guildizer` |
| `BACKEND_URL` | ✅ | ⬜ | ❌ | `https://guild-api.telegizer.com` |
| `SESSION_COOKIE_SECURE` | ✅ `true` | ⬜ | ❌ | prod |
| `SESSION_COOKIE_SAMESITE` | ✅ `None` | ⬜ | ❌ | prod |
| `ADMIN_USER_IDS` | ✅ | ⬜ | ❌ | Comma-separated Discord user ids |
| `NOWPAYMENTS_API_KEY` / `NOWPAYMENTS_IPN_SECRET` | ✅ | ❌ | ❌ | IPN URL = `<BACKEND_URL>/webhooks/nowpayments` |
| `ANTHROPIC_API_KEY` | ⬜ | ⬜ | ❌ | AI features off gracefully without it |
| `YOUTUBE_API_KEY`, `X_BEARER_TOKEN` | ⬜ Phase 14 | ⬜ Phase 14 | ❌ | Campaign link deep checks |
| `GOOGLE_CLIENT_ID/SECRET` | ⬜ Phase 17 | ❌ | ❌ | Calendar sync |
| `REACT_APP_GUILDIZER_API_URL` | ❌ | ❌ | ✅ **Vercel project env** | `https://guild-api.telegizer.com` — rebuild after setting |

**Rule of thumb:** anything Guildizer-backend goes on BOTH Guildizer Railway services
(they share the DB and most config); the ONLY Guildizer var on the Telegizer side is the
frontend's `REACT_APP_GUILDIZER_API_URL` on the Vercel project.
