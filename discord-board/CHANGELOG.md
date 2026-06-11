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
