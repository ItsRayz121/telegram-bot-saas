# Guildizer Dashboard Parity Plan — exact Telegizer 6-tab replica

Goal: restructure the Guildizer server dashboard (embedded UI at
`frontend/src/pages/guildizer/GuildizerServerDetail.js`, separate `discord-board` backend)
into the **exact Telegizer group-dashboard IA**: 6 major tabs → subtabs → every function.
Source of truth: `TELEGIZER_FEATURE_MAP.md` (repo root).

Legend: ✅ backend exists · 🟡 backend partial (extend) · 🆕 new (design UI + settings now, bot enforcement next)
Discord adaptations are noted where Telegram concepts don't map 1:1.

Final tab bar: `Overview · Moderation · Members · Engagement · AI & Integrations · Automation · Analytics · Commands · Team · Billing`
(the middle 6 are the Telegizer-exact parity tabs; Overview/Commands/Team/Billing are server-level extras kept so no existing function is lost).

---

## Tab 1 — MODERATION

### Subtab: AutoMod
- [ ] AutoMod global enable → ✅ `cf_enabled`
- [ ] Default action on violation (delete/warn/timeout/kick/ban) → ✅ `cf_action`
- [ ] Block NSFW / explicit → ✅ `cf_nsfw` (CSAM always bans)
- [ ] Remove foreign Discord invites (≙ Telegram invite-link rule) → ✅ `cf_invites`
- [ ] Remove shortened/suspicious links → ✅ `cf_links`
- [ ] Banned words (comma list) → ✅ `cf_custom_words`
- [ ] Extended block rules (≙ Telegizer 13-rule matrix) → ✅ `extra.automod`:
  - external links + domain whitelist + action
  - excessive emojis (max + action)
  - caps lock (threshold % + min length + action)
  - language/script filter (scripts + action)
  - media blocks: attachments, stickers, voice (action) — Discord equivalent of
    Telegram photo/video/GIF/sticker/voice-note/file rules
- [ ] Smart Moderation (AI): enable, server topic, trusted users, AI rate limit, action → ✅ `extra.automod.smart_mod`
- [ ] Image AI review: enable, action, rate limit → ✅ `extra.automod.image_ai`
- [ ] 🛡️ Bot Protection: enable, policy (kick untrusted / alert only), trusted bot IDs, alert channel → ✅ `extra.bot_policy`
- [ ] 🚨 Raid Mode: enable, window, violator trigger, duplicate threshold, lockdown minutes,
      lockdown action, announce + channel → ✅ `rg_*`
- [ ] Join gate: min account age days → ✅ `jg_min_account_age_days`
- [ ] Emergency Lockdown (manual, 30 min / 2 h / lift) → ✅ `POST /moderation/lockdown`
- [ ] 📋 Protection Activity feed → ✅ `GET /protection/events`
- [ ] Emoji Reactions: enable, 👍 on admin messages, sentiment reactions on member messages, per-user cooldown → 🆕 `extra.emoji_reactions`
- [ ] Command Permissions: delete unauthorized command invocations → 🆕 `extra.command_permissions`
      (note: Discord also has native slash-command permissions; panel links to that)

### Subtab: Behavior
- [ ] Warning thresholds: max warnings, action (timeout/kick/ban/none), timeout minutes → ✅ `extra.warnings`
- [ ] Warning escalation window (count warnings within N hours) → 🆕 `extra.warnings.window_hours`
- [ ] Auto-delete warning messages after N seconds → 🆕 `extra.auto_clean.warn_messages_seconds`
- [ ] Auto-delete action/mod messages after N seconds → 🆕 `extra.auto_clean.action_messages_seconds`
- [ ] Escalating punishment ladder (per step: at warning # → action → duration → count-within) → 🆕 `extra.warn_ladder`
- [ ] Auto Clean join messages → ✅ `extra.auto_clean.join_messages`

### Subtab: Reports
- [ ] `/report` command (built-in, reserved) → ✅
- [ ] Reports inbox + review (resolve/dismiss) → ✅ `GET /reports`, `POST /reports/<id>/review`
- [ ] Notify-admins routing (alert channel) → 🟡 reuse `extra.escalation.alert_channel_id`, add report-specific channel key

---

## Tab 2 — MEMBERS

### Subtab: Verification
- [ ] Enable join verification → ✅ `extra.verification.enabled`
- [ ] Method: button / math / word captcha → ✅ `method`
- [ ] Timeout seconds → ✅ · Max attempts → ✅ · On timeout: kick / keep → ✅
- [ ] Quarantine role + verify channel (bot auto-setup) → ✅ `role_id`/`channel_id` (read-only display)
- [ ] Min account age (join gate duplicate-link from Moderation) → ✅

### Subtab: Welcome
- [ ] Welcome enable + message + channel ({user} {server} {member_count}) → ✅ settings
- [ ] Leave enable + message + channel → ✅ (Discord extra; Telegram has no leave msg)
- [ ] Embed mode, AI-personalized welcome, rules text, image URL, auto-delete after N s → ✅ `welcome2`
- [ ] Auto-role on join (≤10 roles) → ✅ `autorole_*` (≙ Telegram has none — Discord extra)
- [ ] DM new members → 🆕 `welcome2.dm_enabled` + `dm_message`

### Subtab: XP & Roles
- [ ] Enable XP/leveling → ✅ leveling API
- [ ] XP per message + cooldown → ✅
- [ ] Announce level-ups (+channel) → ✅
- [ ] XP per reaction + reaction cooldown → 🟡 add keys
- [ ] Level-up message template + auto-delete → 🟡 add keys
- [ ] Moderation XP penalties (warn/timeout/kick/ban) → 🆕 keys
- [ ] Level → role rewards (from level X grant role Y) → 🟡 verify/extend leveling API

---

## Tab 3 — ENGAGEMENT

### Subtab: Raids
- [ ] Raid coordinator: tweet/post URL, goals (reposts/likes/replies/bookmarks),
      duration, XP reward, pin/announce, reminders → ✅ campaigns API `type=raid` (V2 raid campaign type)

### Subtab: Invite Links
- [ ] Tracked invites / referral leaderboard → ✅ `GET /referrals`
- [ ] Referral settings (reward thresholds etc.) → ✅ `PUT /referrals/settings`
- [ ] Create named invite (name, max uses, expiry) → 🟡 via bot `/invitelink` command; surface in UI

### Subtab: Campaigns
- [ ] Wizard: title, multi-task (Pro), platform, per-task editor (type/platform/verification/XP/link/proof prompt+example),
      deadline, reward+label, max participants, one-submission, resubmission, pin, leaderboard toggle, draft/activate → ✅
- [ ] Proof fields → ✅ growth_api `fields`
- [ ] Submissions review (approve/reject + reason, dup flag) → ✅
- [ ] Per-campaign leaderboard → ✅ · Post/delete announcement → ✅ `POST /campaigns/<id>/post`
- [ ] Public proof feed → ✅ `GET /public/.../proof-feed`

---

## Tab 4 — AI & INTEGRATIONS

### Subtab: Knowledge Base
- [ ] KB documents CRUD (title/content) → ✅ knowledge API
- [ ] `/ask` AI Q&A (built-in) → ✅
- [ ] Auto-reply settings: enable, mention-only, low-confidence fallback, min length → 🆕 `extra.kb_replies`
- [ ] Tone: reply length / emoji / formality → 🆕 (same section)
- [ ] Use auto-responses as AI knowledge → 🆕 flag on auto-responses

### Subtab: Escalation
- [ ] Global escalation enable + keyword triggers + alert channel → ✅ `extra.escalation`
- [ ] Per-type toggles (AI KB low-confidence, image AI, automation errors, unknown commands) → 🆕 `extra.escalation.types`

---

## Tab 5 — AUTOMATION

### Subtab: Scheduler
- [ ] Scheduled messages: title, text, channel, send-at, repeat-every, stop-at, auto-delete, pin/announce → ✅ content API

### Subtab: Auto Reply
- [ ] Triggers: phrase, response, match type, case sensitivity → ✅ auto-responses API

### Subtab: Polls
- [ ] Polls: question, options, multi-answer, duration, channel, schedule → ✅ polls API

### Subtab: Forwarding
- [ ] Channel mirrors (source → destination, filters) → ✅ mirrors API

### Subtab: Workflows
- [ ] Workflows CRUD + execution log → ✅ workflows API

### Subtab: Webhooks
- [ ] Outbound webhooks (URL, events, secret) → ✅
- [ ] Inbound webhooks (token URL → post to channel) → ✅

---

## Tab 6 — ANALYTICS

### Subtab: Members
- [ ] CRM member list (notes, tags, edit) → ✅ crm API

### Subtab: Leaderboard
- [ ] XP leaderboard → ✅ leveling leaderboard

### Subtab: Audit Log
- [ ] Full action/event log (all protection + mod events, paginated) → ✅ `/protection/events` (raise limit, add filter)

### Subtab: Warnings
- [ ] Active warnings list + remove → ✅ warnings API

### Subtab: Digest
- [ ] AI digest: enable, channel, frequency → ✅ digest API (extend with frequency if missing)

### Subtab: AI Activity
- [ ] AI action feed (smart_mod / image_ai / ask events) → 🟡 `/protection/events?category=ai`

---

## Server-level tabs kept (no Telegizer group equivalent)
- Overview (channels/roles) · Commands (custom slash commands) · Team (seats/invites) · Billing (plan, checkout, history, promo)

## Discord-native additions (beyond Telegizer parity)

Features Telegram simply doesn't have; these make Guildizer feel native rather than ported.
Ranked by impact-per-effort:

1. ✅ **Reaction roles / button roles** (Members › Self-roles, 2026-06-11) — menus in
   `GuildSettings.extra["self_roles"]`, persistent `SelfRoleButton` DynamicItem +
   reaction add/remove handling, post/unpost queue in the 20s post loop, dangerous
   permissions never self-assignable. `self_roles.py` + `self_roles_api.py`.
2. ✅ **Anti-nuke guard** (Moderation › AutoMod, 2026-06-11) — per-executor sliding windows
   over bans/kicks/channel+role deletions, audit-log attribution, strip-roles/ban/alert
   response, owner+bot+whitelist exempt. `anti_nuke.py`, settings in `extra.anti_nuke`.
3. ✅ **Ticket system** (Engagement › Tickets, 2026-06-11) — dashboard-configured panel with
   a persistent `TicketOpenButton` DynamicItem → private thread (support role pinged in),
   `TicketCloseButton` posts a .txt transcript to the configured channel then locks+archives.
   Open tickets tracked in `extra.tickets.open` (no table); hand-deleted threads forgotten
   via `on_raw_thread_delete`. `tickets.py` + `tickets_api.py`.
4. ✅ **Join-to-create voice channels + voice XP** (Members › XP & Roles, 2026-06-11) —
   temp rooms registered in `extra.voice_temp` (restart-safe sweep), voice XP via the
   5-min voice loop (ledger reason "voice", `Member.voice_minutes` healed column).
   `voice_features.py`, settings in `extra.voice` via the leveling API.
5. ✅ **Starboard** (Engagement › Starboard, 2026-06-11) — configurable emoji + threshold,
   embed reposts with live count edits (throttled per message), self-star opt-in, NSFW and
   starboard-channel sources excluded. Source→repost map pruned in `extra.starboard.posted`.
   `starboard.py` + `starboard_api.py`.
6. ✅ **Discord native AutoMod sync** (Moderation › AutoMod, 2026-06-12) — mirrors
   `cf_custom_words` (+ optional invite links) into one managed Discord AutoMod keyword
   rule ("Guildizer · Banned words") so words stay blocked while the bot is down. Dirty
   flag set by the moderation PUT, reconciled in the 20s post loop; rule_id/last_synced_at/
   last_error state in `extra.automod.native_sync`. `automod_sync.py`.
7. ✅ **Embed builder for Scheduler** (Automation › Scheduler, 2026-06-12) — optional
   embed (title/text/color/image/thumbnail/footer) on scheduled messages, embed-only
   posts allowed. `ScheduledMessage.embed` JSON column (startup self-heal), sanitized
   in `content_api._clean_embed`, rendered by `_build_scheduled_embed` in the content loop.
8. ✅ **Auto-publish announcements** (Automation › Scheduler, 2026-06-12) — crossposts
   announcement-channel messages (including the bot's own scheduled posts) to follower
   servers, sliding 10/hour/channel budget honoring Discord's cap. Config in
   `GuildSettings.extra["auto_publish"]` (empty channel list = all announcement channels),
   GET/PUT `/auto-publish`, hook at the top of on_message before the bot skip.
9. ✅ **Boost tracking** (Engagement › Boosts, 2026-06-12) — on_member_update
   premium_since transitions: thank-you post ({user}/{server}/{count}), extra reward
   role (dangerous-permission roles refused, removed on unboost), one-time XP via the
   ledger (reason "boost"). Config in `GuildSettings.extra["boosts"]`, `boosts.py` +
   `boosts_api.py`.
10. ✅ **Scheduled events integration** (Engagement › Events, 2026-06-12) — dashboard
    creates native Discord scheduled events (external/voice/stage) via a `guild_events`
    queue table (create_all, no migration); the content loop creates/cancels them and
    posts an optional channel reminder N minutes before start. `content_api` events
    endpoints + `content_runtime` queue helpers + `_create_guild_event` in bot_core.
11. ✅ **Thread auto-management** (Automation › Threads, 2026-06-12) — auto-creates a
    discussion thread on new posts in explicitly chosen channels (named from author +
    first line), 1h/24h/3d/1w auto-archive policy, optional bot/webhook posts. Config
    in `GuildSettings.extra["auto_threads"]`, TTL-cached gate in `auto_threads.py`
    (on_message hook before the bot skip), GET/PUT `/auto-threads`.
12. **Server settings backup/restore** (server-level) — snapshot roles/channels/permissions.

Telegram concepts intentionally NOT ported (no Discord equivalent / natively covered):
- "Admin must start the bot" DM-readiness checks — Discord DMs work by default
- Forum-topic routing — replaced by per-channel selects throughout
- Contact/location-share blocking — Discord has no such message types
- Mini App / TMA — nearest future analog is Discord Activities (out of scope)
- Slow mode, native spoiler blocking — Discord has these built into channel settings

## Build order
1. ✅ This plan.
2. Frontend shell: 6 grouped tabs + subtab bars in `GuildizerServerDetail.js` (URL-driven `?tab=&sub=`).
3. Reorganize existing tab components into the new subtabs (no logic change).
4. New subtab UIs for every 🆕/🟡 item, persisting via existing PUT endpoints.
5. Backend: new `EXTRA_DEFAULTS` sections + PUT acceptance (`emoji_reactions`, `command_permissions`,
   `warn_ladder`, `auto_clean` extensions, `kb_replies`, `escalation.types`, welcome DM, leveling keys).
6. ✅ Bot enforcement for new sections (2026-06-11): emoji_reactions (admin 👍 +
   sentiment reactions w/ per-member cooldown), command_permissions (text-style
   command deletion), warnings.window_hours, warn_ladder (multi-step, per-step
   windows, no reset between steps), auto_clean warn/action timers (automod +
   mod-command confirmations), welcome2 DM, leveling2 (reaction XP via
   message_author_id, level-up template delete-after, warn/timeout/kick/ban XP
   penalties floored at 0, level→role rewards), kb_replies auto-replies
   (mention/question gating, tone prompt, low-confidence fallback), escalation
   types (ai_kb, ai_image, automation, command), reports.alert_channel_id.
   Drive-by fix: governor.safe now returns the coroutine result, repairing the
   verification challenge-message id capture.
7. Cross-check + lint + push.
