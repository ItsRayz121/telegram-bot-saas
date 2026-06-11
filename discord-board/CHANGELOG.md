# Guildizer Changelog

One entry per shipped phase: scope, schema additions, env vars, manual ops.
(V1 phases 0–8 predate this file — see `DISCORD_BOARD_PLAN.md` §6.)

## Phase 9 — White-Label Custom Bot Foundation (2026-06-11)

Guildizer now has the same two-lineage architecture as Telegizer: the official
bot plus customer-owned ("bring your own token") white-label bots, all powered
by one shared engine. Full design: `docs/WHITE_LABEL_ARCHITECTURE.md`.

**Backend**
- `bot_core.py` — NEW. The official bot's entire engine (moderation, raid guard,
  XP, welcome/leave, auto-roles, campaigns, reminders, built-in slash commands)
  extracted into a shared `CoreMixin` + `attach_builtin_commands()`. Both
  lineages run this — features ship to the whole fleet on deploy.
- Bot resolution rule: each guild is served by exactly ONE bot identity
  (`Guild.custom_bot_id`, NULL = official). Event handlers check `serves()`;
  the routing map is cached in-process (15s TTL). No double-moderation when an
  official + custom bot share a guild.
- `custom_bot_manager.py` — NEW. Fleet runner: one gateway client per active
  CustomBot on the official bot's loop; 30s reconcile (start/stop/restart),
  staggered connects, login-failure → status=error + health event. Custom bots
  auto-link guilds on join; unlink on remove (guild reverts to official).
- `custom_bots_api.py` — NEW. Dashboard endpoints: connect (validates token via
  `/users/@me` + `/oauth2/applications/@me`, reads privileged-intent flags),
  replace token, re-check intents, disconnect, per-app invite URL, link/unlink
  guilds. Max 5 bots/user.
- `crypto.py` — NEW. Fernet encryption for tokens at rest; decrypt failures
  degrade to status=error (never crash).
- `discord_api.validate_bot_token()` + app-flag intent constants.
- `command_registrar.resync_dirty(bot, allow=)` — per-identity dirty filtering.
- `campaign_runtime.campaigns_to_post()` now returns (id, guild_id) so each
  identity posts only for guilds it serves; same filter on reminder delivery.
- Models: `CustomBot`, `BotHealthEvent`, `Guild.custom_bot_id` (additive column
  self-heal in `database.py` — no migration needed).

**Frontend** (embedded pillar, `frontend/src/pages/guildizer/`)
- `GuildizerBots.js` — NEW "My Bots" page at `/guildizer/bots`: 3-step connect
  wizard (portal instructions → token validation → invite), bot cards with
  status/intent badges, error surfacing, re-check, token replacement,
  link/unlink servers, disconnect. Entry button on the servers page.

**Env vars (new)**
- `GUILDIZER_ENCRYPTION_KEY` — Fernet key for token storage. Falls back to a
  key derived from `FLASK_SECRET_KEY` (dev only — set it in production).

**Dependencies**: `cryptography==42.0.8` (backend).

**Validation**: backend compileall + smoke suite (API 401 gate, crypto
round-trip, module imports, bot-resolution rule matrix, legacy-column
self-heal, init_db idempotency) all green; frontend CI build green.

**Manual ops**: none beyond the existing V1 launch checklist. Custom bots are
invisible until a user connects one.

## Phase 10 — Moderation Parity Pack (2026-06-11)

Closes the automod-matrix gap with Telegizer and ships the full moderation
command suite. Both lineages (official + white-label) inherit everything.

**Engine**
- `content_filter.py`: emoji counting (unicode + custom Discord emoji), caps
  percentage, foreign-script detection (cyrillic/chinese/korean/arabic/japanese),
  domain whitelist matching.
- `moderation.py`: `evaluate_automod()` (external-link whitelist, emoji flood,
  caps lock, language filter) + `evaluate_media()` (attachments/stickers/voice
  toggles); per-category warning texts.
- Config lives in `ModerationSettings.extra` JSON, deep-merged over
  `protection.EXTRA_DEFAULTS` — self-heals, no migration.
- Warning ladder: /warn and automod warnings count up; at max_warnings the
  configured action fires (timeout/kick/ban) and the count resets.
- Auto-clean: optional deletion of system "X joined" messages.

**Models**: `MemberWarning`, `ModReport`, `ScheduledModAction` (tempban expiry).

**Commands** (`mod_commands.py`, attached to every bot identity): /warn
/warnings /removewarning /mute /unmute /kick /ban /unban /tempban /purge
/userinfo /auditlog /report + right-click "Report Message" context command.
Hidden by default_permissions AND runtime-checked; role-hierarchy + owner/self
guards; every action logs a ProtectionEvent.

**Bot loops**: `process_mod_actions` (60s) executes due tempban unbans, both
lineages, serves()-filtered.

**API** (`protection_api.py`): PUT /moderation accepts `automod`, `warnings`,
`auto_clean` sections (validated); GET returns merged config; new
GET/DELETE /warnings, GET /reports, POST /reports/<id>/review.

**UI** (`ProtectionTab.js`): Automod links & text card, media + warning-ladder
card, open-reports queue with Actioned/Dismiss, recent-warnings list, new
event-category labels.

**Validation**: backend compileall + smoke suite (automod decision matrix,
ladder math incl. reset, reports lifecycle, scheduled-unban due flow, merged
snapshot defaults, wiring imports) green; frontend production build green.

**Env vars**: none new. **Manual ops**: none.

## Phase 11 — Verification & Onboarding Parity (2026-06-11)

Join captcha, foreign-bot policy, and welcome-message depth. Both lineages.

**Verification (`verification.py` + bot_core)**
- Quarantine-role captcha: on join the bot assigns an Unverified role and posts
  a challenge in #verify. Methods: button click, math question, typed word
  (modal). Success removes the role + challenge; wrong answers count attempts
  (live max_attempts config); at the limit the member is kicked.
- Auto-setup on first use: creates the Unverified role + #verify channel
  (overwrites: hidden from everyone, visible to Unverified) and hides other
  channels from the role (capped, governor-safe).
- Timeout sweep in the 60s loop (kick/keep per config), scoped per bot identity
  so the fleet never double-acts. Buttons survive restarts via DynamicItem.
- Model: `PendingVerification`.

**Bot policy (`bot_policy.py`)**
- Untrusted bot joins -> kick (kick_untrusted) or alert-only; alert message with
  one-click admin Trust / Kick buttons (DynamicItems, admin-gated). Trusted ids
  persist so re-invites pass.

**Welcome depth**
- `welcome2` extras in GuildSettings.extra (deep-merged defaults): rich-embed
  mode (author avatar + image), rules text, auto-delete after N seconds.

**Config/API**: `verification` + `bot_policy` sections in ModerationSettings
extra (validated on PUT /moderation); `welcome2` on GET/PUT /settings.
**UI**: Verification + Bot policy cards (ProtectionTab); embed/rules/auto-delete
fields (SettingsTab).

**Validation**: smoke suite (challenge gen, attempt ladder w/ live config,
pass paths incl. whitespace tolerance, expiry-sweep scoping, trust list,
snapshot defaults, wiring imports) green; frontend build green.

**Env vars**: none new. **Manual ops**: bot needs Manage Roles + Manage
Channels for auto-setup (already in the default invite permission set).

## Phase 12 — Scheduling, Polls & Content (2026-06-11)

**Scheduled messages**: dashboard-created, with hourly/daily/weekly recurrence
(missed slots roll forward; one-shots disable after sending). Bot posts via the
new 30s `content_loop`, scoped per bot identity (serves()) so the fleet never
double-posts. Model: `ScheduledMessage`.

**Native Discord polls**: created from the dashboard (2-10 answers, duration up
to 32 days, multi-choice). Bot posts via discord.py's native Poll API, then
finalizes vote counts into the DB after close (status pending->open->ended,
failed on post errors). Model: `Poll`.

**Auto-responses**: keyword triggers (contains / exact, case-insensitive) ->
bot reply, with per-trigger in-memory cooldowns. Runs on the clean-message path
after moderation so filtered messages never trigger replies. Model:
`AutoResponse`.

**API** (`content_api.py`): full CRUD for all three (manage-gated); live polls
cannot be deleted. **Runtime** (`content_runtime.py`): pure DB helpers, all due
queries scoped to served guilds.

**UI**: new **Content** tab in the server detail page — scheduler card
(datetime + recurrence + enable/delete), polls card (results shown after
close), auto-responses table.

**Validation**: smoke suite (due scoping, recurrence roll-forward, one-shot
disable, poll lifecycle incl. failed-post, match semantics exact-vs-contains,
cooldown) green; frontend production build green.

**Env vars**: none new. **Manual ops**: none.

## Phase 13 — Automation Engine (2026-06-11)

Workflows, channel mirroring, and inbound/outbound webhooks. Both lineages.

**Workflows** (`AutomationWorkflow` + `AutomationExecution`): triggers
message_contains / member_join / member_leave / reaction_add (new
on_raw_reaction_add handler), optional channel filter + per-workflow cooldown;
ordered action list (max 5): send_message (placeholders {user}/{server}/
{channel}, optional target channel), add_role/remove_role, timeout, webhook.
Every run recorded with ok/error status; runs_count on the row.

**Channel mirroring** (`MirrorRule`): reposts clean messages (text +
attachment URLs) to another channel via a Discord webhook with the original
author's name/avatar. Cross-server works when the bot is in both. Webhook
created once and cached; deleted webhooks self-heal (recreate next message);
errors surfaced on the rule.

**Inbound webhooks** (`InboundWebhook`): secret-token URLs
(POST /webhooks/in/<token> with {"content": …}); payload relayed into the
channel by enqueuing a one-shot ScheduledMessage — bot/API still coordinate
only via DB. Counters + last-used tracked.

**Outbound webhooks** (`OutboundWebhook`): member_join / member_leave /
moderation_action / raid_activated events POSTed as JSON with optional
HMAC-SHA256 signature (X-Guildizer-Signature); per-hook delivery counters and
last_error. Wired into join/leave/filter-action/raid paths.

**API** (`automation_api.py`): manage-gated CRUD for all four (+ executions
list, per-guild limits 25/10/10). **UI**: new Automation tab — workflow
builder row, mirrors card, webhooks card (copy-URL inbound, event-checkbox
outbound).

**Validation**: smoke suite (trigger matching incl. channel filter, cooldown,
render, execution recording, inbound relay 202/404/400 + queue row, outbound
error capture + event filtering, mirror cache lifecycle) green; frontend
production build green.

**Env vars**: none new. **Manual ops**: mirroring needs Manage Webhooks on the
destination (already in the default invite permission set).

## Phase 14 — Engagement Parity+ (2026-06-11)

Growth tooling: tracked invites/referrals, campaign custom fields, proof link
checks, public proof feed. Both lineages.

**Referrals** (`invite_tracking.py`, `InviteLink` + `InviteJoin`): the serving
bot caches each guild's invite uses (boot + on_invite_create/delete); on join
the invite whose use-count rose attributes the inviter. /invitelink gives every
member a personal tracked invite. Optional XP per referral (GuildSettings
extra, default 0/off); attribution logged as a protection event; self-invites
ignored. Needs Manage Guild to list invites — degrades silently.

**Campaign custom fields** (`CampaignCustomField`): up to 4 admin-defined
inputs injected into the proof modal (Discord's 5-component cap); values stored
in submission proof JSON. Honor-mode campaigns with fields still open the
modal (the fields are the point).

**Proof link checks** (`link_checks.py`): keyless oEmbed validation for
YouTube/X links + generic reachability for other URLs; verdict
(valid/invalid/unknown) annotated on the submission — informs review, never
auto-rejects.

**Public proof feed**: GET /api/public/guilds/<id>/proof-feed — recent
verified submissions with masked usernames (no auth).

**API** (`growth_api.py`): fields CRUD, referrals leaderboard/recent/config,
PUT referral XP setting. **UI** (CampaignsTab): Proof-form-fields card in the
campaign detail, link-check chips + field values on pending submissions,
Referrals card with XP setting + leaderboard on the campaigns list.

**Deferred**: guild-join auto-verify task type (14.6) — needs target-guild
membership semantics; tracked for a later pass.

**Validation**: smoke suite (attribution + XP + idempotent link registration,
custom fields in context + proof JSON, link-check shapes, API gates, open
public feed) green; frontend production build green.

**Env vars**: none new (oEmbed is keyless — YOUTUBE/X keys no longer needed).

## Phase 15 — CRM, Analytics & Usage Spine (2026-06-11)

**Member CRM**: members table gains last_seen / wallet / admin_notes (additive
column self-heal — no migration). Activity is buffered in-memory by the bot
and flushed every ~60s (no per-message writes); message counts stay accurate
whether leveling is on (leveling counts) or off (tracker counts).

**Daily analytics** (`GuildDailyStat`): per-day message/join/leave rollups,
upserted from buffers + join/leave events. API fills missing days with zeros;
"active today" derived from Member.last_seen.

**Feature-usage spine** (`FeatureUsageEvent`): every completed slash command
recorded via a single on_app_command_completion hook (both lineages) — the
data backbone for Phase 19's admin usage analytics.

**Wallet collection**: /wallet (modal input, ephemeral) + /mywallet (masked
display). Wallets visible to admins in the CRM.

**API** (`crm_api.py`): GET /members (search by name/ID, sort xp/messages/
last_seen), PUT /members/<uid> (notes/wallet), GET /analytics?days=7|14|30.

**UI**: new **Members** tab (search/sort list, expandable rows with wallet +
admin notes) and **Analytics** tab (totals cards + per-day bar charts, no
chart lib). Tab bar switched to scrollable (mobile-safe).

**Validation**: smoke suite (flush semantics incl. dual counting modes, rollup
upserts, feature spine, wallet set/clear/trim) green; frontend build green.

**Env vars**: none new. **Manual ops**: none.

## Phase 16 — Knowledge & Applied AI (2026-06-11)

All AI layers run through ai.py + the AITokenUsage ledger and degrade to
no-ops without ANTHROPIC_API_KEY. Both lineages.

**Knowledge base** (`KnowledgeDocument`, `knowledge.py`): per-server docs
ground /ask — prefix-tolerant keyword retrieval picks the top 3 docs into the
system prompt; /ask falls back to the generic assistant when the KB is empty.

**Smart mod**: AI promo/spam classifier on clean messages (community-topic
aware, trusted users skipped, per-user rate limit, min length 20); acts with
the configured automod action and logs as smart_mod.

**Image AI**: vision NSFW check on image attachments (per-guild rate limit),
configured action on flagged images.

**Escalation alerts** (heuristic, zero AI cost): configurable frustration
keywords -> alert channel ping with a jump link; 10-min per-member cooldown.

**AI welcome**: optional one-line personalized welcome appended to the welcome
message. **Daily digest**: per-guild daily activity summary (messages/actives/
joins/leaves/top chatter) posted after a configurable UTC hour, AI-polished
when configured; fixed an hour-0 falsy bug found by tests.

**API** (`knowledge_api.py`): knowledge CRUD + digest config; smart_mod /
image_ai / escalation validated on PUT /moderation; ai_welcome on /settings.
**UI**: Knowledge tab (docs CRUD w/ inline editing), AI moderation +
Escalation cards (ProtectionTab), Daily digest card (ContentTab), AI welcome
switch (SettingsTab).

**Validation**: smoke suite (grounded retrieval incl. prefix matching, digest
due/mark lifecycle incl. hour-0, config sections, AI graceful degradation)
green; frontend build green.

**Env vars**: uses existing `ANTHROPIC_API_KEY` (GUILDIZER-WEB + GUILDIZER-BOT;
all AI features stay off without it).

## Phase 17 — Assistant (Echo Parity, v1) (2026-06-11)

The personal-assistant surface, riding the white-label fleet: every custom bot
is automatically a custom ASSISTANT bot answering under its own identity.

**Tasks** (`Task` model): /task add, /tasks list, /done <id> — personal scope
like reminders/notes, ownership-checked.

**DM assistant**: DMing any Guildizer-powered bot now gets an AI reply
grounded on the member's own open tasks, pending reminders and recent notes
(`assistant.personal_context`). Typing indicator, 5s per-user rate limit,
token usage ledgered. Without an AI key the bot answers with a helpful
pointer to /task /remind /note instead.

**Deferred to a later pass** (tracked in checklist): the full Telegizer hub
engine — memory (person/project), suggestion engine, meeting links + Google
Calendar sync, hub dashboard pages, retention/consent plumbing.

**Validation**: smoke suite (task lifecycle incl. ownership + double-complete,
personal-context grounding + isolation between users) green. No frontend
changes this phase.

**Env vars**: uses existing `ANTHROPIC_API_KEY`. **Manual ops**: none.

## Cross-check Audit — Phases 9–17 (2026-06-11)

Owner-requested full review of the V2 codebase before Phase 18.

**Bugs found & fixed**
1. **Staff messages skipped content features** (introduced Phase 3 design,
   exposed by 12/13): the early staff `return` in on_message also skipped
   auto-responses, mirroring and message workflows for admins/mods. Staff now
   skip only moderation + AI layers; content features run for everyone. Same
   fix covers guilds with a missing moderation row.
2. **Workflow `webhook` action ignored its URL** (Phase 13): it dispatched to
   the guild's outbound-webhook subscribers instead of POSTing to the action's
   own configured URL. New `automation_runtime.post_workflow_webhook`.
3. **DM assistant rate-limit key** (Phase 17): keyed globally, so DMing two
   different bots within 5s silently dropped the second. Now per bot identity.
4. **4 new eslint react-hooks warnings** in AnalyticsTab/MembersTab/
   CampaignsTab (misplaced disable comments) — fixed properly; as a bonus the
   2 pre-existing CampaignsTab warnings from V1 are fixed too.

**Verified clean**
- New authorized end-to-end API suite (session-cookie auth): 40+ requests
  across every V2 endpoint — moderation PUT round-trip incl. every new config
  section + sanitizers, CRM sorts (incl. nullslast paths), analytics series,
  content/automation/growth/knowledge CRUD, public inbound + proof feed,
  cross-guild 403s. All green.
- Loop parity: both lineages start all 5 background loops.
- Command-name collision check across the 28-command tree: none.
- Strict CI build: zero warnings from V2 files (only pre-existing
  Sidebar/Dashboard/GroupCRM/CommandsTab remain).
