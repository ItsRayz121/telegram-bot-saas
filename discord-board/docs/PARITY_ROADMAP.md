# Guildizer Parity Roadmap, Commit Strategy & Risk Plan

> Deliverables 4–6. Continues the phase numbering from `DISCORD_BOARD_PLAN.md` (V1 = phases
> 0–8, shipped 2026-06-10). V2 = **Phases 9–20**, ordered by dependency and product value.
> Every phase follows: **Develop → Test → Validate → Commit to main → Next phase** (no
> approval gates between phases, per the owner's standing instruction).
>
> Binding rules for every phase: Telegizer code is **never touched** (isolation rule);
> behavior goes in **shared modules** so custom bots inherit it (lineage rule); deep-merge
> defaults + startup self-heal for all new settings (no migrations where avoidable).

---

## Phase 9 — White-Label Custom Bot Foundation ⭐ (the architecture keystone)

- **Description**: BYO-token Discord bots powered by the Guildizer engine. Full design in
  `WHITE_LABEL_ARCHITECTURE.md`.
- **Dependencies**: none (first V2 phase). Phase 17 and admin fleet views depend on it.
- **DB**: `custom_bots` table; `guilds.custom_bot_id`; `bot_health_events`.
- **Backend**: `crypto.py` (Fernet), `custom_bots_api.py` (CRUD + token validation +
  app-flags intent check + invite URL), `bot_core.py` extraction, `custom_bot_manager.py`
  fleet worker, per-app command registrar, bot-resolution rule (one bot per guild).
- **Discord API**: `GET /users/@me`, `GET /oauth2/applications/@me` (flags), per-token gateway
  sessions, per-app command registration.
- **UI**: "My Bots" panel — connect wizard (token → intent check → activate → invite),
  bot status cards, guild linking.
- **Testing**: token validation unit tests (mocked REST); fleet manager start/stop/reload;
  resolution rule (official stands down); live smoke: second Discord app answering /ping + a
  custom command in a test server.

## Phase 10 — Moderation Parity Pack

- **Description**: close the automod matrix gap + full mod-command suite + warnings ladder.
- **Dependencies**: Phase 9's `bot_core.py` (commands written once, both lineages).
- **DB**: `warnings`, `reported_messages`, `scheduled_unbans`; widen `ModerationSettings`
  JSON to full `group_defaults.automod` shape (links/invites whitelist, emojis, caps,
  homoglyphs, language filter, media-type toggles, smart_mod AI block).
- **Backend**: port filter heuristics from Telegizer `content_filter.py`/`moderation.py`;
  warning-escalation ladder (warn→timeout→kick→ban); native AutoMod rule management
  (create/update via REST as "managed by Guildizer" rules); auto-clean; reports queue.
- **Discord API**: timeouts, bans w/ delete-message-seconds, `channel.purge`, AutoMod REST,
  audit-log reasons on every action.
- **UI**: Moderation tab → full matrix editor (copy Telegizer's GroupSettings sections);
  warnings + reports views.
- **Commands**: /warn /removewarning /mute /unmute /tempban /kick /ban /purge /userinfo
  /whois /me /admins /roles /auditlog /report (+ message context-menu Report).
- **Testing**: filter unit tests ported with Telegizer's cases; live: trigger each action
  class in test server.

## Phase 11 — Verification & Onboarding Parity

- **Description**: join captcha (button/math/word) via quarantine-role pattern; bot-policy
  join gate for foreign bots; welcome depth (rules, media embeds, auto-delete, AI welcome,
  channel routing).
- **Dependencies**: Phase 10 (role/permission helpers).
- **DB**: `pending_verifications`; settings blocks `verification`, `bot_policy`, extend `welcome`.
- **Backend/Discord API**: role assignment on join, #verify channel bootstrap (bot creates
  role + channel overwrites), button/modal captcha, timeout→kick job; `member.bot` gate with
  admin approve/deny buttons.
- **UI**: Verification + Bot Policy sections in server settings.
- **Testing**: join-flow live test with an alt account + a scrap bot.

## Phase 12 — Scheduling, Polls & Content

- **Description**: scheduled/recurring messages with embeds; native Discord polls; keyword
  auto-responses; auto-clean of system messages.
- **Dependencies**: none beyond Phase 9.
- **DB**: `scheduled_messages`, `polls`, `auto_responses`.
- **Backend**: scheduler loop in bot worker (copy Telegizer scheduler pattern + jitter);
  poll create/results via native polls API.
- **UI**: Scheduler + Polls + Auto-responses tabs (copy Telegizer panels).
- **Testing**: schedule fire + recurrence; poll round-trip.

## Phase 13 — Automation Engine (Workflows, Mirroring, Webhooks)

- **Description**: port the trigger→condition→action workflow engine; message mirroring
  ("forwarding") via channel webhooks with author impersonation; inbound webhook URLs →
  channel posts; generalize outbound event webhooks.
- **Dependencies**: Phase 9; Phase 12 scheduler (time triggers).
- **DB**: `automation_workflows`, `automation_executions`, `mirror_rules`, `mirror_logs`,
  `inbound_webhooks`, `outbound_webhooks`.
- **Backend**: engine copy with Discord adapters (triggers: message/join/leave/reaction/
  schedule/webhook; actions: send/embed/role-add/timeout/webhook-out); webhook mirror runtime
  (create/reuse channel webhook, repost with username+avatar override).
- **Discord API**: webhooks create/execute, events already on gateway.
- **UI**: WorkflowBuilder port; Mirroring + Webhooks tabs.
- **Testing**: engine unit tests (port Telegizer's), live mirror between two channels.

## Phase 14 — Engagement Parity+ (Referrals, Invites, Custom Fields, Proof Feed)

- **Description**: tracked invites with join attribution (the Discord-native referral
  system), campaign custom fields, link-validity deep checks, public proof feed + metrics,
  guild-join auto-verify task type.
- **Dependencies**: Phase 9.
- **DB**: `invite_links`, `invite_joins`, `referrals`, `campaign_custom_fields`.
- **Backend**: invite cache + delta attribution on `on_member_join`; custom fields → modal
  inputs; YouTube/X validity checks (copy); proof feed routes.
- **UI**: Referrals page, campaign wizard custom-fields step, public feed page.
- **Testing**: invite attribution live test (alt account), modal field round-trip.

## Phase 15 — CRM, Analytics & Usage Spine

- **Description**: member CRM (activity, wallets via modal, admin notes, segments); per-guild
  analytics dashboards (messages/actives/joins/leaves charts); cross-guild analytics hub;
  `FeatureUsageEvent` spine.
- **Dependencies**: Phase 10 (member data enrichment).
- **DB**: widen `members` (last_seen, message_count, wallet, notes), `guild_daily_stats`,
  `feature_usage_events`.
- **Backend**: gateway-event rollups (daily-stat upserts), CRM routes, usage recorder.
- **UI**: CRM page, Analytics page w/ charts (copy Telegizer components), wallet command.
- **Testing**: rollup correctness against seeded events.

## Phase 16 — Knowledge & Applied AI

- **Description**: per-guild knowledge base grounding /ask; smart-mod AI layer; AI welcome /
  level-up flavor; escalation detection; social replies; image moderation; AI digest.
- **Dependencies**: Phases 10, 15 (settings + usage ledger).
- **DB**: `knowledge_documents`, `escalation_events`, `digest_logs`.
- **Backend**: copy Telegizer's KB retrieval + prompts; image AI on attachment CDN URLs;
  all calls through the existing `AITokenUsage` ledger + per-user rate limits.
- **UI**: Knowledge tab, AI toggles across settings sections.
- **Testing**: grounded /ask answers from seeded docs; ledger rows written.

## Phase 17 — Assistant Hub (Echo Parity)

- **Description**: full hub engine over Discord DMs/threads — tasks, reminders, decisions,
  meetings, notes, digests, knowledge cards, memory + suggestions, follow-ups, consent,
  retention, plan limits; custom **assistant** bots ride the Phase 9 runtime.
- **Dependencies**: Phases 9, 16.
- **DB**: hub tables (copy `hub_models.py` shapes, Discord ID fields).
- **Backend**: copy `assistant/` engine modules; surface = DM message router + slash commands.
- **UI**: Assistant hub pages (copy Telegizer's AssistantHub/Tasks/Notes/Digests/Memory).
- **Testing**: DM round-trips, digest generation, retention job.

## Phase 18 — Teams, Notifications & Billing Depth

- **Description**: team seats/roles/invites; notifications center; promo codes; renewals,
  payment history, pending invoices; full plan-limit matrix (`platform_config` copy).
- **Dependencies**: none hard; scheduled late because it's pure copy work.
- **DB**: `teams`, `team_members`, `team_invites`, `user_notifications`, `promo_codes`(+usage),
  `pending_invoices`, `payment_history`, `subscription_renewals`.
- **UI**: Team page, notifications bell, billing history, promo redemption.
- **Testing**: gating matrix unit tests; promo math; renewal stacking.

## Phase 19 — Admin Panel Parity (V2–V4 equivalents)

- **Description**: RBAC roles + invite-by-email; secret vault; feature flags; announcements;
  compliance queue; admin audit log; AI management center + provider balances; bot-fleet
  health tab; proof metrics; unified event log; full drill-down detail pages.
- **Dependencies**: Phases 9 (fleet health), 15 (usage spine), 18 (billing data).
- **DB**: `admin_audit_logs`, `platform_secrets`, `feature_flags`, `admin_announcements`,
  `compliance_requests`, `admin_roles`.
- **UI**: extend the existing /admin shell with the missing categories (no public-app
  structure changes — admin shell is exempt per the approved V3 exception pattern, but
  confirm before any *public* sidebar change).
- **Testing**: route-gating audit (every admin route behind RBAC — replicate Telegizer's
  81/81 check).

## Phase 20 — Hardening, Verification & Launch

- **Description**: load/soak test the fleet worker; finalize Discord **bot verification**
  application for the official bot (privileged intents at scale — apply EARLY, it's slow);
  product pages (landing/pricing section, status, tour); SETUP.md updates; full live
  regression in a test server; launch checklist.
- **Exit**: verified official bot, fleet runtime stable, all dashboards live.

---

## Sequencing rationale

9 (architecture keystone, unblocks two lineages) → 10–12 (server-management depth — the
visible "is it a real MEE6 competitor?" surface) → 13–14 (automation + growth differentiators)
→ 15–16 (data + AI depth) → 17 (assistant, biggest copy job, needs 9+16) → 18–19 (platform
plumbing, pure copy) → 20 (launch). Each phase is independently shippable; auto-deploy from
`main` stays safe because new code paths are settings-gated off by default.

---

# GitHub Commit Strategy (Deliverable 5)

1. **Branch**: commit directly to `main`, push after every validated phase (repo rule —
   Railway/Vercel auto-deploy). No feature branches/PRs unless the owner asks.
2. **Scope guard**: every commit touches **only** `discord-board/**` (+ optionally
   `frontend/src/pages/guildizer/**` for the embedded dashboard section). `git diff --stat`
   is checked against this before each commit. Zero Telegizer files, ever.
3. **Granularity**: one commit per phase minimum; large phases split into coherent
   sub-commits (model layer / engine / API / UI), each leaving `main` deployable.
4. **Message convention**: `feat(guildizer): phase 9 — white-label custom bot foundation`
   with body listing files + behavior, matching repo style.
5. **Pre-commit checks, every time**:
   - `python -m compileall discord-board/backend` (syntax gate)
   - backend unit tests for the touched engine modules
   - `npm run build` for the touched frontend (CI=true to catch warnings-as-errors locally)
   - `git diff` reviewed for secrets (tokens/keys) — none ever committed
6. **Changelog**: `discord-board/CHANGELOG.md` gets an entry per phase (date, scope, schema
   additions, env vars added, manual ops needed). The plan file's §6 status list is ticked
   in the same commit.
7. **Deploy safety**: schema is create_all + self-heal (additive only); settings-gated
   features default OFF so a deploy never changes live behavior until an admin enables it.

---

# Risk Assessment & Mitigation (Deliverable 6)

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | **Telegizer regression** from Guildizer work | Low | Critical | Isolation rule: separate folder/DB/deploy roots; commit scope guard (§2 above); zero shared imports — verified per commit. |
| R2 | `bot_core.py` extraction (Phase 9.3) breaks the official bot | Medium | High | Pure mechanical refactor commit with no behavior change, validated live (/ping, welcome, filter, XP) **before** the fleet lands on top. |
| R3 | **Privileged-intent friction** on custom bots (customer forgets toggles) | High | Medium | App-flags check blocks activation until intents are on; "needs attention" badge; re-check button. |
| R4 | Custom bot hits **100-server unverified cap** | Low | Medium | Surface count + warning at 75; document customer-side verification path. |
| R5 | Fleet worker memory growth with many clients | Medium | Medium | Disable member chunking + trim caches per client; partition-by-id scaling knob from day one; per-client health metrics. |
| R6 | Discord **bot verification** for the official bot is slow/denied | Medium | High | Apply early (Phase 20 says start the application as soon as feature set stabilizes ~Phase 14); keep data-use answers ready (moderation/leveling justify both privileged intents). |
| R7 | Rate limits during mass command-registration / campaign posts | Medium | Low | discord.py honors buckets; registrar staggers per app; governor already in place. |
| R8 | Token security (custom bot tokens at rest) | Low | Critical | Fernet encryption, key in env only, never logged/returned, re-encrypt-on-rotation callback pattern copied from Telegizer; 401 auto-disable. |
| R9 | Schema drift between create_all and live Postgres | Medium | Medium | Additive-only columns + startup self-heal (proven Telegizer pattern); migration script only when unavoidable, run via Railway preDeployCommand. |
| R10 | Scope creep: 12 phases stall before launch | Medium | High | Each phase independently shippable + gated off by default; product is sellable from Phase 12 onward even if later phases slip. |
| R11 | Double-handling when official + custom bot share a guild | Medium | Medium | Bot-resolution rule is written into `bot_core` entry points (single authority per guild), tested explicitly in Phase 9. |
| R12 | Discord ToS / data-privacy concerns (message content storage) | Low | High | Store derived stats, not message bodies (except where a feature requires excerpts, e.g. reports — retention-capped); privacy policy section for Guildizer; honor guild-leave purge. |
