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

## Discord-native additions (beyond Telegizer parity — proposed, not yet approved)

Features Telegram simply doesn't have; these would make Guildizer feel native rather than ported.
Ranked by impact-per-effort:

1. **Reaction roles / button roles** (Members › new "Self-roles" subtab) — the single most
   expected Discord bot feature; pairs with the existing autorole + role-rewards plumbing.
2. **Anti-nuke guard** (Moderation › AutoMod) — alert/revert on mass channel/role deletions or
   mass bans by a compromised admin account; natural extension of bot_policy + raid guard.
3. **Ticket system** (new Engagement or server-level subtab) — button → private support thread,
   with transcript on close; Discord-native support flow.
4. **Join-to-create voice channels + voice XP** (Members › XP & Roles) — temp voice rooms;
   award XP for voice minutes (leveling2 already has the storage pattern).
5. **Starboard** (Engagement) — ⭐-threshold reposts to a best-of channel.
6. **Discord native AutoMod sync** (Moderation › AutoMod) — push banned words/links into
   Discord's built-in AutoMod via API so filtering happens even when the bot is down.
7. **Embed builder for Scheduler** (Automation › Scheduler) — title/color/image embeds, the
   Discord-native equivalent of Telegram rich posts.
8. **Auto-publish announcements** (Automation) — auto-publish posts in announcement channels
   to follower servers.
9. **Boost tracking** (Engagement) — thank-you message + booster role + XP on server boost.
10. **Scheduled events integration** (Engagement) — create Discord server events from the
    dashboard; remind attendees.
11. **Thread auto-management** (Automation) — auto-thread on posts in chosen channels,
    auto-archive policy.
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
