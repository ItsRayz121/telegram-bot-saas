# Telegizer Feature Audit & Discord Compatibility Matrix

> Deliverables 1 + 2 of the Guildizer parity program. Audited 2026-06-11 directly from the
> Telegizer codebase (`backend/models.py` ~110 models, `backend/routes/` 43 route files,
> `backend/bot_features/` 17 modules, `backend/assistant/` 26 modules, `backend/automation/`,
> `backend/group_defaults.py`, `frontend/src/pages/` 70 pages).
>
> **Legend — Discord support:** ✅ Full · 🟡 Partial / different mechanics · ❌ Not possible · ➖ N/A on Discord
> **Legend — Guildizer status:** DONE (shipped in V1 phases 0–8) · PARTIAL · MISSING

---

## 1. Auth & Account

| Feature (Telegizer source) | Discord | Guildizer | Notes |
|---|---|---|---|
| Email/password signup + email verification (`routes/auth.py`) | ✅ | MISSING | Guildizer V1 is OAuth2-only. Decide: keep OAuth2-only (recommended — Discord identity is canonical) or add email as secondary contact for billing receipts. |
| Password reset flow | ✅ | ➖ | Not needed if OAuth2-only. |
| TOTP 2FA + 48h trusted device (`routes/totp.py`) | ✅ | ➖ | Discord OAuth2 inherits Discord's own 2FA. No re-implementation needed. |
| Telegram account linking (`UserTelegramAccount`) | ✅ | DONE | Discord OAuth2 login = the equivalent, already shipped. |
| API keys for users (`routes/api_keys.py`, `UserApiKey`) | ✅ | MISSING | Straight copy — platform-agnostic. |
| Teams: seats, roles, invites (`Team`, `TeamMember`, `TeamInvite`, `routes/team.py`) | ✅ | MISSING | Straight copy. Map team-member access to guild dashboards. |
| Session auth + CSRF (`middleware/`) | ✅ | DONE | Cookie session exists; verify CSRF posture matches Telegizer's enforcement. |
| GDPR deletion / compliance requests (`ComplianceRequest`) | ✅ | MISSING | Straight copy; purge list must cover Discord models. |
| Notifications center (`UserNotification`, `routes/notifications.py`) | ✅ | MISSING | Straight copy; deliver via dashboard + optional bot DM. |

## 2. Bot Deployment Architecture

| Feature | Discord | Guildizer | Notes |
|---|---|---|---|
| Official bot serving all groups (`official_bot.py`) | ✅ | DONE | Gateway + slash commands, auto-sharded. |
| **Custom white-label bots (BYO token)** (`CustomBot`, `bot_manager.py`, `routes/custom_bots.py`) | ✅ | MISSING | **Fully possible on Discord.** See `WHITE_LABEL_ARCHITECTURE.md`. Phase 9. |
| Assistant-bot lineage (Echo → custom assistant bots, `assistant/hub_custom_bot_runner.py`) | ✅ | MISSING | Same white-label mechanism; assistant personality runs over DMs. Phase 17. |
| Bot health monitoring (`BotHealthEvent/State`, `bot_health_monitor.py`) | ✅ | MISSING | Copy; data source = gateway connect/disconnect/error events per client. |
| AI Activity log + error classification (`AIActivity`, `error_classification.py`) | ✅ | PARTIAL | Only `AITokenUsage` ledger exists. Copy classification (info/warning/critical). |
| Per-group bot resolution (official vs custom, `automation/bot_resolver.py`) | ✅ | MISSING | Same pattern: a guild is served by exactly one bot identity. Phase 9. |
| Graceful SIGTERM shutdown | ✅ | DONE | |

## 3. Per-Group Management Settings (from `group_defaults.py` — the canonical matrix)

| Setting block | Discord | Guildizer | Discord mapping |
|---|---|---|---|
| `verification` — join captcha: button/math/word, timeout, attempts, kick-on-fail | 🟡 | PARTIAL | Telegram restricts users pre-captcha. Discord equivalent: assign quarantine role on join, gate channels behind a verified role, captcha via button/modal in a #verify channel. Also offer native Membership Screening + Onboarding as the "easy mode". Join gate (account age) shipped in V1. |
| `welcome` — message, rules, media, auto-delete, topic routing, AI welcome | ✅ | PARTIAL | Basic welcome/leave shipped. Missing: rules text, media embeds, auto-delete, AI-generated welcome, channel routing. |
| `levels` — XP per message/reaction, cooldowns, level roles, rank card, penalties, announcements | ✅ | PARTIAL | Message XP + /rank + /leaderboard shipped. Missing: reaction XP (`on_raw_reaction_add`), XP penalties on mod actions, level-up announcements w/ custom message, **level roles = real Discord roles** (upgrade over Telegram's cosmetic names), rank-card styling. |
| `automod.spam` — flood detection, mute action | ✅ | DONE | Content-filter engine shipped; verify parity of thresholds/actions. |
| `automod.bad_words` | ✅ | DONE | Also map to **native AutoMod keyword rules** (free, zero-latency, blocks before send — better than Telegram). |
| `automod.nsfw_filter` (text + button + CSAM zero-tolerance) | ✅ | PARTIAL | Text filter shipped. Inline-button scan ➖ (no inline keyboards on Discord) → replace with embed/link scan. |
| `automod.external_links` + whitelist | ✅ | MISSING | Copy; native AutoMod can also block links. |
| `automod.telegram_links` | ✅ | MISSING | Becomes **invite-link filter** (`discord.gg/*`) — native AutoMod has a built-in preset. |
| `automod.excessive_emojis`, `caps_lock`, `homoglyphs` | ✅ | MISSING | Straight copy of text heuristics. |
| `automod.forwarded_messages` | 🟡 | ➖ | No forward primitive; nearest analog = message **forwards/snapshots** (new Discord feature) — low priority. |
| `automod` media toggles (photos, videos, gifs, stickers, files, voice/video notes, contact, location, games) | 🟡 | MISSING | Remap to Discord types: attachments by MIME, embeds, stickers, voice messages. Contact/location/games ➖. |
| `automod.language_filter` (script detection) | ✅ | MISSING | Straight copy. |
| `automod.smart_mod` (AI promo detection, hidden URLs, trusted users, rate-limited AI layer) | ✅ | MISSING | Straight copy; uses AI provider + per-user AI rate limit. |
| `bot_policy` — join gate for other bots, approval flow, trusted list, timeout action | ✅ | MISSING | Discord: `member.bot` flag on join → kick/quarantine + admin approval buttons. Cleaner than Telegram. |
| `raid_guard` — behavior detection, lockdown, duplicate-message tracking | ✅ | DONE | Shipped + manual lockdown. Verify duplicate-message logic parity. |
| `moderation` — max warnings, escalation action, mute duration | ✅ | PARTIAL | Engine exists; warnings system + escalation ladder missing (see §4). |
| `warning_escalation` ladder | ✅ | MISSING | Copy; mute → Discord **timeout** (native, up to 28 days). |
| `auto_clean` — delete service messages, command echoes | ✅ | MISSING | Copy; delete join/boost system messages, command invocations are ephemeral anyway. |
| `reports` — /report → admin review queue (`ReportedMessage`) | ✅ | MISSING | Copy; also wire Discord's native **message report context-menu command** (Apps > Report). |
| `knowledge_base` + grounded `/ask` (`KnowledgeDocument`, `bot_features/knowledge_base.py`) | ✅ | MISSING | Copy. V1's `/ask` is raw AI; ground it on per-guild knowledge docs. |
| `auto_responses` — keyword triggers (`AutoResponse`) | ✅ | MISSING | Straight copy on `on_message`. |
| `escalation` — detect frustrated users → alert admins (`EscalationEvent`) | ✅ | MISSING | Straight copy. |
| `image_ai` — image moderation | ✅ | MISSING | Copy; Discord attachments give CDN URLs — easier than Telegram file API. |
| `social_replies` — AI replies to social links | ✅ | MISSING | Straight copy. |
| `reactions` — reaction XP | ✅ | MISSING | `on_raw_reaction_add` — Discord-native. |
| `raids` (shill raids, `Raid`/`OfficialRaid`) | ✅ | MISSING | Copy as campaign/raid engine (raid campaign type partially exists in Campaign model). |
| `digest` — AI group digest (`DigestLog`, `assistant/digest_ai.py`) | ✅ | MISSING | Copy; post to a channel or DM. |
| `admin_alerts` — DM alerts to admins | ✅ | MISSING | Copy; Discord DMs allowed from shared-guild bots. |
| `command_routing` — per-topic command scoping | ✅ | MISSING | Topics → **channels/threads**; scope commands per channel. Discord also has native per-command permission overrides (Integrations page) — expose both. |

## 4. Moderation Command Suite (`bot_manager.py` handlers ×3 impls)

| Command | Discord | Guildizer | Mapping |
|---|---|---|---|
| /warn /removewarning + warning count tracking | ✅ | MISSING | `OfficialWarning` equivalent table. |
| /ban /unban /tempban | ✅ | MISSING | `guild.ban` + scheduled unban job. |
| /kick | ✅ | MISSING | |
| /mute /unmute /tempmute | ✅ | MISSING | Native **timeout** (`member.timeout()`) — better than Telegram permission juggling. |
| /purge (bulk delete) | ✅ | MISSING | `channel.purge()` — native bulk delete (≤14 days old). |
| /userinfo /whois /me | ✅ | MISSING | Richer on Discord (roles, join date, badges). |
| /auditlog | ✅ | MISSING | Own `AuditLog` table + optionally merge Discord's native audit log API. |
| /admins /roles /groupinfo | ✅ | MISSING | Trivial via guild object. |
| /rank /leaderboard | ✅ | DONE | |
| /settings quick-toggles in-chat | ✅ | MISSING | Buttons/selects — nicer than Telegram inline keyboards. |
| /wallet /mywallet (wallet collection) | ✅ | MISSING | Modal input — cleaner than Telegram DM flow. |
| /report | ✅ | MISSING | Plus message context-menu version. |
| /ask (knowledge AI) | 🟡 | PARTIAL | Exists but ungrounded (no KB). |
| /invitelink | ✅ | MISSING | `channel.create_invite()` with tracking (see referrals). |
| /start /help /status /linkgroup /support | 🟡 | ➖/DONE | Linking is OAuth-based on Discord (already better); /help exists via command list UI. |
| Custom commands (dashboard-defined) | ✅ | DONE | Native slash commands w/ dirty-flag resync — superior to Telegram. |
| Per-group command enable/disable (`BotGroupCommand`) | ✅ | MISSING | Per-guild tree filtering + native permission overrides. |

## 5. Scheduling, Content & Channels

| Feature | Discord | Guildizer | Notes |
|---|---|---|---|
| Scheduled messages w/ recurrence (`ScheduledMessage`, `OfficialScheduledMessage`, `scheduler.py`) | ✅ | MISSING | Copy scheduler loop into bot worker; embeds upgrade. |
| Polls (`Poll`, `OfficialPoll`, `routes/polls.py`) | ✅ | MISSING | Discord has a **native polls API** for bots — use it. |
| Channels product: broadcast posts, daily stats (`Channel`, `ChannelPost`, `ChannelDailyStat`, `routes/channels.py`) | 🟡 | MISSING | Telegram channels → Discord **announcement channels** (+ auto-crosspost). Stats differ (no view counts; use reactions/replies). |
| Forum topics discovery (`GroupForumTopic`) | ✅ | MISSING | Discord forums/threads are first-class; sync threads like channels. |

## 6. Automation

| Feature | Discord | Guildizer | Notes |
|---|---|---|---|
| Workflow builder: triggers→conditions→actions (`AutomationWorkflow/Execution`, `automation/engine.py`, `WorkflowBuilder.js`) | ✅ | MISSING | Engine is platform-agnostic; rewrite trigger/action adapters for Discord events. |
| Message forwarding between chats (`ForwardRule/Source/Destination/Log`, `forwarding_runtime.py`) | 🟡 | MISSING | No native forward; implement **mirror via webhooks** (bot creates channel webhook, reposts with original author name/avatar — standard Discord pattern, arguably nicer than Telegram forwarding). Cross-guild allowed if bot is in both. |
| Inbound webhooks (`WebhookIntegration`, `OfficialWebhookIntegration`) | ✅ | MISSING | Copy: POST → bot posts to channel. Discord also has native channel webhooks — expose both. |
| Outbound integration webhooks (`IntegrationWebhook`, `integrations/dispatcher.py`) | ✅ | PARTIAL | Campaign webhook events exist; generalize to all event types. |
| Anti-ban governor (`automation/anti_ban.py`) | ➖ | DONE | Replaced by 429-aware rate-limit governor (discord.py handles buckets). |
| Workspace reminders (`WorkspaceReminder`) | ✅ | PARTIAL | Personal /remind shipped; workspace-level recurring reminders missing. |
| Smart links (`WorkspaceSmartLinks.js`, `bot_links.py`) | ✅ | MISSING | Straight copy (tracked redirect links). |

## 7. Engagement & Growth

| Feature | Discord | Guildizer | Notes |
|---|---|---|---|
| Campaigns engine, multi-task (`EngagementCampaign/Task`) | ✅ | DONE | Buttons+modals proof flow shipped — already better than Telegram deep-links. |
| Campaign custom fields (`EngagementCustomField`) | ✅ | MISSING | Copy; render as modal inputs (5-field modal limit → paginate). |
| Campaign leaderboards (Pro-gated) | ✅ | DONE | |
| Link-validity deep checks (YouTube/X APIs) | ✅ | MISSING | Platform-agnostic copy. |
| Raid campaign type | ✅ | PARTIAL | Verify parity with Telegizer raid campaigns. |
| TG-join auto-verify task | 🟡 | MISSING | Becomes **guild-join auto-verify**: with `guilds` scope, check target-server membership via member fetch — actually *easier* than Telegram. |
| Public proof feed + proof metrics | ✅ | MISSING | Straight copy. |
| Referral system (`Referral`, `routes/referrals.py`, referral bot UI) | ✅ | MISSING | Discord upgrade: per-user **tracked invites** (`InviteLink` + `InviteLinkJoin` → invite-use deltas on `on_member_join`) — the standard "invite tracker" pattern, big Discord market. |
| Invite links w/ join attribution (`InviteLink`, `InviteLinkJoin`) | ✅ | MISSING | As above; needs invite cache + `on_invite_create/delete`. |
| Directory listings (`DirectoryListing`, `routes/directory.py`) | ✅ | MISSING | Straight copy (server discovery directory). |
| Marketplace / partnership deals + escrow + deal chat (`PartnershipDeal`, `DealMessage`, `routes/marketplace.py`) | ✅ | MISSING | Platform-agnostic copy. |
| XP ledger (`XpEvent`) | ✅ | DONE | |

## 8. CRM & Member Management

| Feature | Discord | Guildizer | Notes |
|---|---|---|---|
| Member CRM: profiles, activity, wallets, notes (`Member`, `OfficialMember`, `routes/crm.py`, `GroupCRM.js`) | ✅ | PARTIAL | Member rows exist for XP; full CRM (last-seen, message counts, wallet, admin notes, segments) missing. Discord advantage: full member list always available via Members intent (Telegram can't enumerate members). |
| Member-count sync job (`member_sync.py`) | ✅ | DONE | Gateway events keep it live — better than Telegram's 6h poll. |
| Pending verification / unban queues | ✅ | MISSING | Part of verification + moderation phases. |
| Suspicious activity tracking (`SuspiciousActivity`) | ✅ | MISSING | Copy. |

## 9. Analytics

| Feature | Discord | Guildizer | Notes |
|---|---|---|---|
| Group analytics: messages, actives, joins/leaves, charts (`GroupAnalytics.js`, `OfficialGroupAnalytics.js`, `routes/analytics.py`) | ✅ | MISSING | Aggregate from gateway events; daily-stat rollup table. |
| Analytics hub (cross-group) | ✅ | MISSING | Copy once per-guild analytics exist. |
| Feature usage tracking spine (`FeatureUsageEvent`, `feature_usage.py`) | ✅ | MISSING | Straight copy — feeds admin panel. |
| Channel daily stats | 🟡 | MISSING | No view counts on Discord; track messages/reactions instead. |
| Platform stats (public counters) | ✅ | MISSING | Copy. |

## 10. Assistant (Echo / Hub Engine — `backend/assistant/`, 26 modules)

| Feature | Discord | Guildizer | Notes |
|---|---|---|---|
| Hub engine: tasks, reminders, decisions, meetings, notes, digests (`Hub*` models) | ✅ | PARTIAL | V1 has personal /remind + /note only. Full hub = Phase 17. DMs + threads as surfaces. |
| Knowledge cards + AI search + embeddings | ✅ | MISSING | Platform-agnostic copy. |
| Memory (global/person/project/group-context) + suggestions | ✅ | MISSING | Copy. |
| Group signal extraction → digests (`group_signal_extractor.py`) | ✅ | MISSING | Copy; reads channel messages (Message Content intent). |
| Meeting links + Google Calendar sync (`GroupMeetingLink`, `GoogleCalendarToken`) | ✅ | MISSING | Platform-agnostic copy. |
| Assistant consent + retention + plan limits | ✅ | MISSING | Copy. |
| Custom assistant bots (white-label Echo) | ✅ | MISSING | Rides on Phase 9 white-label runtime. |
| Workflows in hub (`HubSystemAutomation`) | ✅ | MISSING | Copy. |

## 11. Billing & Plans

| Feature | Discord | Guildizer | Notes |
|---|---|---|---|
| NOWPayments checkout + IPN | ✅ | DONE | Separate endpoint, HMAC-verified. |
| Plan gating (free/pro/agency limits, `platform_config.py`) | ✅ | PARTIAL | Guild.plan=pro exists; full per-feature limit matrix missing. |
| Promo codes (`PromoCode`, `PromoCodeUsage`) | ✅ | MISSING | Straight copy. |
| Renewals + pending invoices + payment history pages | ✅ | MISSING | Straight copy. |
| Card payments (Lemon Squeezy — currently disabled in Telegizer) | ✅ | MISSING | Mirror whatever Telegizer ships. Note: Discord users expect card/PayPal; crypto-only conversion will be lower than on crypto-native Telegram. |

## 12. Admin Panel (V1–V4 in Telegizer)

| Feature | Discord | Guildizer | Notes |
|---|---|---|---|
| Admin shell + sidebar, RBAC roles + invite-by-email (`admin_rbac.py`) | ✅ | PARTIAL | V1 has env-var admin IDs + basic drill-downs. Full RBAC missing. |
| User/guild/custom-bot detail pages, admin notes, audit profile | ✅ | PARTIAL | Basic detail endpoints exist; full tabbed pages missing. |
| AI management: providers, balances, pricing, token-usage ledger | ✅ | PARTIAL | Ledger exists; control center missing. |
| Secret vault (`PlatformSecret`, `secret_vault.py`) | ✅ | MISSING | Straight copy. |
| Feature flags (`FeatureFlag`) | ✅ | MISSING | Straight copy. |
| Admin announcements (`AdminAnnouncement`) | ✅ | MISSING | Straight copy. |
| Compliance queue, admin audit log (`AdminAuditLog`) | ✅ | MISSING | Straight copy. |
| System health + bot health tabs | ✅ | MISSING | Data source = gateway/client health events. |
| Proof metrics + unified event log | ✅ | MISSING | Copy. |

## 13. Platform / Site

| Feature | Discord | Guildizer | Notes |
|---|---|---|---|
| Landing, pricing, SEO meta, sitemap | ✅ | PARTIAL | Guildizer lives as a section in telegizer.com; needs its own landing/pricing section. |
| Mini App (TMA) | ➖ | ➖ | No Discord equivalent needed; dashboard covers it. (Discord Activities are a different, optional concept.) |
| Product tour | ✅ | MISSING | Copy pattern. |
| Status page | ✅ | MISSING | Copy. |

---

## Summary counts

- **~140 distinct features audited.**
- **Discord support:** ~85% fully supported, ~10% supported with different mechanics (verification, forwarding-as-webhook-mirror, channels-stats), ~5% N/A (Mini App, Telegram-only message types, anti-ban paranoia).
- **Nothing essential is blocked by Discord.** In several areas Discord is strictly more capable: native timeouts, native AutoMod, real role rewards, full member enumeration, native polls, bulk delete, modals/buttons, invite attribution.
- **Guildizer V1 coverage of the audited surface: roughly 25%.** The remaining 75% is scheduled in `PARITY_ROADMAP.md` (Phases 9–20).

## The three structural gaps (everything else hangs off these)

1. **White-label custom bots** — entire second lineage absent → Phase 9 (see `WHITE_LABEL_ARCHITECTURE.md`).
2. **Settings depth** — Guildizer's `GuildSettings`/`ModerationSettings` cover ~20% of `group_defaults.py`; the deep-merge defaults + self-heal pattern must be extended to the full matrix → Phases 10–12.
3. **The workspace layer** — automation, CRM, analytics, assistant hub, teams, admin V2+ → Phases 13–19.
