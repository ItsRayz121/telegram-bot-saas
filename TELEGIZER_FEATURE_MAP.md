# Telegizer — Complete Feature Map

> Source of truth extracted from the code on 2026-06-11:
> `frontend/src/config/featureRegistry.js` (group tabs), `frontend/src/pages/GroupSettings.js` (subtab functions),
> `frontend/src/config/assistantHubRegistry.js` (Echo tabs), `frontend/src/config/adminNav.js` (admin sections),
> `frontend/src/App.js` (routes), `frontend/src/components/Sidebar.js` (main nav).
>
> Purpose: parity checklist for Guildizer (Discord board). Guildizer stays a 100% separate codebase —
> copy business logic, never import it.

---

## Main Sidebar Navigation

1. **Dashboard** (`/dashboard`)
2. **Groups** (`/groups`)
3. **Echo** — AI assistant hub (`/ark`)
4. **Discord — Servers** (`/guildizer`, embedded Guildizer UI)
5. **Referrals** (`/referrals`)
6. **Settings** (`/settings`)
7. User menu: Account Settings · Billing & Plan · Admin Panel (admins) · Logout
8. Extras: Getting Started checklist (5 steps), What's New changelog, Upgrade-to-Pro banner, collapsed-sidebar quick links (Tasks, Knowledge, Memory, Meeting Links)

---

## 1. Dashboard (`/dashboard`)

- Official Telegizer bot card (status, link-group CTA)
- Custom Bots section: add bot (BotFather token), start/stop bot, delete bot, per-bot health indicator
- Trial countdown banner · plan-expired warning · expiry-soon warning · bot-limit upgrade trigger
- Onboarding card · Connect-Telegram banner · waiting/timed-out link banners
- Invite (referral) card · upgrade CTA for free users

---

## 2. Groups (`/groups`)

**Group list page**
- All linked groups (official bot + custom bots) with permission chips: Full Access / Bot Active / Check permissions
- Link group via verification code (with success celebration)
- Unlink group (confirm dialog; legacy custom-bot disconnect supported)
- Permissions detail modal · refresh · hub-conflict guard

**Per-group entry points**
- `/groups/:id` — full group dashboard (6 tabs below)
- `/groups/:id/analytics` — official analytics page
- `/groups/:id/crm` — Community CRM
- `/groups/:id/manage` — Custom Commands + Event Log
- (identical routes per custom bot: `/bot/:id/group/:gid[/analytics|/crm]`)

### Group Dashboard — Tab 1: MODERATION

**Subtab: AutoMod**
- AutoMod global enable
- Banned Words (comma-separated) · Extra NSFW Words
- 13 extended block rules, each with action + warn toggle:
  contact sharing, location sharing, email addresses, spoiler content, voice notes,
  video notes (circles), file attachments, photos, videos, GIFs/animations, stickers, games, bot mentions
- Default action + "warn user" + delete-warning-after
- Language filter: enable + action
- 🛡️ **Bot Protection**: enable, bot policy, notify-admins-via, fallback if no admin decides,
  approval timeout (minutes), auto-trust Telegizer + own custom bots, admin started-bot status list
- 🚨 **Raid Mode**: enable, distinct-spammers trigger, duplicate-posters trigger, detection window (s),
  lockdown duration (min), action on members joining during raid, in-group alert on activation
- **Emergency Lockdown** (manual, with duration picker)
- 📋 **Protection Activity** log
- **Smart Moderation (AI)**: enable, group topic, detect promotional content, detect hidden/obfuscated URLs,
  allow referral codes, AI off-topic/unclear check (action + warn user)
- **Emoji Reactions**: enable, 👍 on every admin message, sentiment reactions on member messages (❤️🔥😂👍🎉🫂)
- **Command Permissions**: delete unauthorized command messages

**Subtab: Behavior**
- Warning Thresholds: max warnings, warning action (ban/mute…), mute duration (min)
- Warning Escalation: warning threshold, time window (hrs), action, mute duration
- Auto-delete warning messages (delete after)
- Escalating punishments ladder: per step — at warning #, action, minutes/hours, count-within window (hrs)
- Auto Clean: delete warn messages after N s, delete action messages after N s

**Subtab: Reports**
- `/report` command enable
- Notify admins (all / selected) with per-admin "DM OK / Start bot" status
- Reports inbox with mark-resolved

### Group Dashboard — Tab 2: MEMBERS

**Subtab: Verification** *(Pro)*
- Enable for new members · method (button/…) · timeout (s) · on-failure (kick or not)
- Max attempts · trigger (on join/…) · verification location + topic
- Verification command routing (access + topic)

**Subtab: Welcome**
- Welcome message enable + text · auto-delete after (s) · welcome topic
- Show rules in welcome + rules text
- DM to new members + DM text

**Subtab: XP & Roles** *(Pro)*
- Enable XP/leveling · XP per message · XP cooldown (s)
- Level-up message, topic, announce toggle, auto-delete after (s)
- XP per reaction + reaction cooldown
- Moderation penalties: warn / mute / kick / ban XP penalties
- Level → role mappings (from level, role name)
- Role command routing

### Group Dashboard — Tab 3: ENGAGEMENT

**Subtab: Raids** *(Pro)*
- Raid Manager + creator: tweet URL, goals (reposts / likes / replies / bookmarks),
  duration (hrs), XP reward, pin raid message, send reminders

**Subtab: Invite Links**
- Tracked invite links: name, max uses, expiry date; per-period stats
- Invite command routing · allowed topic

**Subtab: Campaigns**
- Campaign wizard (stepper):
  - Step 1: title, multi-task mode (Pro), intro/description, platform, instructions,
    verification mode, per-task editor (title, type, platform, verification, XP, task link, proof prompt + example)
  - Step 2: deadline, XP reward + reward label, max participants, one-submission-per-user,
    allow resubmission after rejection, pin group announcement, leaderboard toggle (Pro), activate-now/draft
- Submission review: approve / reject with reason, duplicate-proof flag
- Per-campaign Leaderboard tab · delete group post · campaign webhook events

### Group Dashboard — Tab 4: AI & INTEGRATIONS

**Subtab: Knowledge Base** *(Pro)*
- Enable AI Q&A from knowledge base · KB entries
- Platform AI vs own key: provider, API key, base URL, model
- Automatic knowledge replies: enable, only when @mentioned/replied, allow in group chats,
  low-confidence fallback, min message length (words)
- Tone: reply length, emoji usage, formality level
- Use Auto Replies as AI knowledge
- Human-Like Interaction: enable, emoji react to appreciation, text acknowledgment,
  interaction style, per-user cooldown (min)
- Image Understanding: enable, only when @mentioned, require caption, escalate on low confidence,
  cost mode, max image size (MB)
- AI command routing

**Subtab: Escalation**
- Global escalation enable
- Per-type toggles: 🤖 AI KB low confidence · 🖼️ AI image review · ⚙️ automation errors · 📌 unknown commands
- Admin DM-ready list · auto-learn from admin replies

### Group Dashboard — Tab 5: AUTOMATION

- **Scheduler** *(Pro)*: scheduled messages — title, Markdown text, send-at + timezone,
  repeat every N min, stop-repeating-at, auto-delete after (s), pin, link preview
- **Auto Reply**: triggers — trigger text, response, match type, case-sensitive, "use as AI knowledge"
- **Polls**: polls & quizzes — question, options, quiz mode (correct answer + explanation),
  anonymous, multiple answers, schedule + timezone
- **Forwarding**: per-group forwarding rules
- **Workflows**: per-group workflows (WorkflowBuilder)
- **Webhooks** *(Pro)*: name, description, message template

### Group Dashboard — Tab 6: ANALYTICS

- **Members**: member list, sort, verified/wallet chips, pagination
- **Leaderboard**: XP leaderboard, time filters (all/30d/7d/today), has-wallet filter
- **Audit Log**: moderation/action audit trail, paginated
- **Warnings**: active warnings, remove warning, time filters
- **Digest**: daily/weekly/monthly Telegram reports — send to group (+topic) and/or DM owner,
  per-admin DM status, manual send-now buttons
- **AI Activity**: AI activity log + status cards (deep-link to the owning config tab)

### Group-level standalone pages

- **Official Analytics** (`/groups/:id/analytics`): members joined, verifications passed, AutoMod actions,
  commands used, verification funnel, activity charts, recent events, date-range picker
- **Community CRM** (`/groups/:id/crm`): member profiles, tag filter, sort, segments
  (All / Verified / Unverified / Has Warnings), admin chips, per-member stats
- **Group Management** (`/groups/:id/manage`): Custom Commands (command, response type, response text, enabled)
  + Event Log

---

## 3. Channels (`/channels`, `/channels/:cid`)

- Channel list · link channel · submit listing to Directory
- Channel detail: Members, Avg Views/Post, Engagement Rate, Posts Tracked, authenticity grade, trend chips

---

## 4. Echo — AI Assistant Hub (`/ark`)

- **Hub landing**: official Echo bot + custom assistant bots (add via token), add-to-group flow
- **Assistant co-pilot panel** (right side, every page): chat, suggestions, markdown answers, copy/expand
- **Workspace tabs** (official + each custom assistant bot):
  - **Overview** — recent tasks / meetings / decisions / reminders, group filter
  - **Notes** — manual + AI-extracted, tags, source filter
  - **Reminders** — upcoming/delivered, group-linked
  - **Tasks** — status/group filters, priority, assignee, due date, AI-extracted flag
  - **Templates** — reusable content snippets w/ use counts
  - **Knowledge** — knowledge cards (title, content, tags, use counts)
  - **Automation** — Daily Digest (enable, time, format), Smart Triggers, Forwarding
  - **Settings** — AI personality note, response language, extraction sensitivity,
    connected groups (pause/plan-limit states), Memory, custom bots ("also in Group Management"),
    Telegram DM alerts, message retention, delete-all-data (type DELETE)
- **Standalone workspace pages**: Tasks · Notes · Knowledge · Memory (profile: name/company/role/timezone/priorities/free notes; People: name/role/notes; Projects: name/status) · Meeting Links · Digests · AI Settings · Assistant Bot settings
- **Smart Links** (`/workspace/smart-links`): trigger phrases, URL, response text, scope (global/group), trigger log
- **Reminders** (`/workspace/reminders`): upcoming / delivered tabs
- **Workflow Builder** (`/workflow-builder`)

---

## 5. Discord — Guildizer (`/guildizer`)

- Servers list · server detail · Guildizer bots · Guildizer admin (separate backend, embedded UI)

---

## 6. Referrals (`/referrals`)

- Referral link copy · how-it-works steps · leaderboard (with "You" marker)
- Rewards: 3 referrals → 7 days Pro, 10 → 1 month Pro

---

## 7. Settings (`/settings`)

- Profile · Invite Friends (referral) · Current Plan
- Change Password · Account Security · Two-Factor Authentication
- Connect Telegram Account · Linked Telegram Accounts (set primary, unlink)
- Default Timezone · Google Calendar integration
- Team Members: invite by email, remove member, cancel invite

---

## 8. Billing (`/billing`)

- Plan comparison + upgrade (NOWPayments crypto live; card via Lemon Squeezy disabled)
- 14-day Pro trial · cancel-subscription dialog · payment history · promo codes · team seats

---

## 9. Custom Bots (`/custom-bots`, `/bot/:id`)

- Bot list · add via BotFather token · per-bot settings · per-bot linked groups
  → each group opens the same 6-tab group dashboard (registry-driven parity with the official bot)

---

## 10. Integrations (`/integrations`)

- Account-level webhooks: name, destination URL, HMAC secret (X-Telegizer-Signature), event subscriptions, enable/disable
- Tabs: Webhooks · Event Catalog · Zapier Setup · Make Setup

---

## 11. Analytics Hub (`/analytics`)

- Tabs: **Overview** (linked groups, members joined, AutoMod actions, commands used, range picker) ·
  **Groups** · **Channels** · **Assistant** · **Insights**

---

## 12. Marketplace / Directory / Tasks

- **Directory** (`/directory`, public) + submit listing
- **Marketplace** (`/marketplace`) + Deals (`/marketplace/deals`, `/marketplace/deals/:did`)
- **My Tasks** (`/tasks`): campaign tasks with Pending/Verified/Rejected status
- **Campaign Task** (`/task/:id`): proof submission deep-link flow

---

## 13. Admin Panel (`/admin` — 24 sections, 6 categories, RBAC-gated)

| Category | Sections |
|---|---|
| Overview | Dashboard · Proof Metrics · Reports |
| Users & Access | Users · Roles & Access · Referrals · Suspicious · Directory |
| Bots & Groups | TG Groups · Custom Bots · Bot Health · Diagnostics |
| Product Analytics | Feature Usage · Campaigns · AI Usage · Event Log · Audit Log |
| Platform Settings | Pricing · AI Management · Configuration · Secrets & Keys · System |
| Compliance & Comms | Compliance · Announcements · Promo Codes |

Plus drill-down detail pages: `/admin/users/:id`, `/admin/groups/:id`, `/admin/custom-bots/:id`.
Admin roles: super_admin, admin, support, finance, moderator, analyst.

---

## 14. Public / auth / misc

- Landing · Pricing · About · Contact · Status · Terms · Privacy · Acceptable Use
- Login · Register · Forgot/Reset Password · Verify Email · Team invite (`/team/join/:token`)
- Referral join (`/join`, `/invite/:code`) · Payment success
- **Mini App** (`/mini-app`, Telegram TMA — full dashboard via auth bridge)
- Onboarding tour · universal search bar · PWA install banner · cookie consent

---

## Plan gates (from `featureRegistry.js` PLAN_GATES)

- **Pro**: Member Verification · XP & Levels · Raid Coordinator · AI Knowledge Base ·
  Webhook Integrations · Scheduled Messages · AI Assistant (+ multi-task campaigns, leaderboards)
- **Enterprise**: White Label · Custom Branding · API Access · Priority Support
