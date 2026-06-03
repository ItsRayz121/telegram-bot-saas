# Telegizer — E2E QA Checklist

**Before starting:** Deploy latest code to Railway + Vercel. Confirm both `ECHO_BOT_TOKEN` and `ECHO_BOT_USERNAME` are set in Railway.

Mark each item: ✅ Pass | ❌ Fail (note what broke) | ⏭ Skip (N/A for your config)

---

## 1. AUTH

- [ ] Register new account with email — confirmation email arrives
- [ ] Email verification link works and activates account
- [ ] Login with correct credentials succeeds
- [ ] Login with wrong password returns error, does not leak info
- [ ] TOTP setup: scan QR, enter code, confirm 2FA is required on next login
- [ ] Backup codes shown once at TOTP setup, usable for login
- [ ] Password reset flow: email arrives, link works, new password accepted
- [ ] JWT refresh: stay logged in > 15 min, session should still work
- [ ] Logout clears session, protected pages redirect to login

---

## 2. TELEGIZER COMMUNITY BOT — Group Management

> Bot: @telegizer_bot (or your `TELEGRAM_BOT_USERNAME`)

### Setup
- [ ] DM @telegizer_bot `/start` — welcome message with menu appears (no AI assistant response)
- [ ] Add @telegizer_bot to a test group as admin
- [ ] Bot sends welcome message in group: "Telegizer connected. Run /linkgroup…"
- [ ] Run `/linkgroup` in group — receive a TLG-XXXXXXXX code
- [ ] Send that code to @telegizer_bot in private — group appears linked in dashboard

### Moderation
- [ ] `/warn @user reason` — warning logged, member warned
- [ ] `/warnings @user` — shows correct warning count
- [ ] `/ban @user reason` — user banned from group
- [ ] `/kick @user` — user kicked (can rejoin)
- [ ] `/mute @user 10m` — user muted
- [ ] `/unmute @user` — user unmuted
- [ ] `/tempmute @user 30m` — timed mute works
- [ ] `/tempban @user 24h` — timed ban works
- [ ] `/removewarning @user` — warning count decremented
- [ ] `/purge 10` — last 10 messages deleted

### XP / Levels
- [ ] `/xp` — shows current user's XP
- [ ] `/rank` — shows rank in group
- [ ] `/leaderboard` — sorted list of top members
- [ ] `/me` — personal stats card
- [ ] `/whois @user` — user profile card

### Admin Tools
- [ ] `/admins` — lists group admins
- [ ] `/roles` — lists custom roles
- [ ] `/wallet` — shows wallet balance
- [ ] `/groupinfo` — group stats card
- [ ] `/auditlog` — recent mod actions
- [ ] `/report @user reason` — report submitted

### Group AI Commands (these stay in Telegizer regardless of Echo)
- [ ] `/ask what is 2+2` — AI response returned in group
- [ ] `/remind me to check report in 1 hour` — reminder set
- [ ] `/invitelink` — returns group invite link

### Separation checks (with ECHO_BOT_TOKEN set)
- [ ] DM @telegizer_bot a plain sentence ("hello, how are you") — should get redirect to Echo, NOT an AI response
- [ ] Tap any "AI Assistant" button in Telegizer DM menu — should redirect to Echo
- [ ] `/assist` in a group where Echo is NOT present — Telegizer silently ignores (no response)

---

## 3. TELEGIZER ECHO — Assistant Hub Bot

> Bot: `@ECHO_BOT_USERNAME` (your Echo bot)

### Onboarding
- [ ] Add Echo bot to a test group as admin
- [ ] Echo sends consent DM to the user who added it: "You've added me to [group]…"
- [ ] Click "Start" in consent DM — HubConnectedGroup record created
- [ ] Click "Cancel — Remove Me" — Echo leaves the group
- [ ] Re-add Echo, public group warning shows if group has username (public group)

### Message extraction
- [ ] Send messages with task language in group ("we need to finish the report by Friday")
- [ ] Wait for extraction batch OR trigger via dashboard "Run Extraction"
- [ ] HubTask appears in Assistant Hub → Tasks
- [ ] Send meeting language ("standup tomorrow at 9am") — HubMeeting appears in Meetings
- [ ] Send reminder language ("remind me to send invoice") — HubReminder appears in Reminders

### /assist via Echo
- [ ] Create a template in dashboard (Assistant Hub → Templates or Bot Settings → Templates)
- [ ] In a group with Echo: `/assist` — lists available templates
- [ ] `/assist template-name` — template content is posted to group
- [ ] Template use_count incremented (verify in dashboard)
- [ ] `/assist` in a group NOT connected to Echo — no response (silent)

---

## 4. ASSISTANT HUB DASHBOARD

### Hub Overview
- [ ] `/hub` or Assistant → Hub page loads without error
- [ ] "Connect Bot" banner shows **Echo's username** (not @telegizer_bot) if no groups connected
- [ ] Connected groups list shows correct group names and status
- [ ] Pause / Resume group extraction works
- [ ] Disconnect group works (removes HubConnectedGroup)

### Tasks
- [ ] Create task manually — appears in list
- [ ] Edit task title, due date — saves correctly
- [ ] Mark task complete — status updates
- [ ] Delete task — removed from list
- [ ] AI-extracted tasks appear here

### Reminders
- [ ] Create reminder manually with date/time
- [ ] Edit reminder
- [ ] Reminder delivered via bot DM at scheduled time (test with short interval)
- [ ] Dismiss reminder

### Notes
- [ ] Create note manually
- [ ] Edit note content and tags
- [ ] Delete note
- [ ] Save note via Telegizer DM: "note: remember to call Ahmed" — appears in Notes

### Meetings
- [ ] AI-extracted meetings appear with correct title and time
- [ ] Dismiss meeting clears it from upcoming
- [ ] Meeting URL captured from group message (Zoom/Meet/Calendly link)

### Knowledge Base
- [ ] Upload a .txt or .pdf document
- [ ] File appears in knowledge base list
- [ ] Delete file
- [ ] Storage quota shown (100MB per group max)
- [ ] Rate limit: > 3 uploads/min returns 429

### Digests
- [ ] Enable digest for a connected group
- [ ] Set digest time and recipient
- [ ] Trigger manual digest — delivered via bot
- [ ] Digest with AI summary enabled — summary included in output

### Templates
- [ ] Create new template with name and content
- [ ] Edit template
- [ ] Delete template
- [ ] Use template in group via `/assist template-name` (see Echo section above)

---

## 5. CUSTOM BOTS

- [ ] Bot Settings → Connect Your Own Bot — paste token from BotFather
- [ ] Webhook registered automatically — no manual step needed
- [ ] Custom bot appears in Hub bot list
- [ ] Add custom bot to group — consent DM flow same as Echo
- [ ] Custom bot buffers messages, extraction works same as Echo
- [ ] `/assist` works through custom bot (not Telegizer)
- [ ] Disconnect custom bot — webhook removed, groups unlinked

---

## 6. GROUP SETTINGS (Dashboard)

- [ ] Groups page lists all linked groups
- [ ] Per-group settings: automod toggle, XP toggle, digest toggle
- [ ] Forum topics configured and used for custom command routing
- [ ] Verification settings: email/TOTP gate on join works
- [ ] Scheduled message created, fires at scheduled time
- [ ] Poll created, sent to group at schedule time
- [ ] Knowledge base per group: upload, link to bot, bot uses it in `/ask` responses

---

## 7. ANALYTICS

- [ ] Analytics → Overview: summary cards load
- [ ] Analytics → Groups: per-group message/member trends load
- [ ] Analytics → Channels: channel post stats load (if channels linked)
- [ ] Date range filter changes data
- [ ] Assistant Activity tab: extraction counts, token usage

---

## 8. AUTOMATIONS / WORKFLOWS

- [ ] Create a workflow with trigger + action
- [ ] Trigger fires (test with a matching group event)
- [ ] Execution log shows run history
- [ ] Disable workflow — stops firing

### Forwarding
- [ ] Create forwarding rule: group A → group B
- [ ] Message in group A forwarded to group B
- [ ] Filter rules (keyword, sender) applied correctly

---

## 9. BILLING / PAYMENTS

- [ ] Billing page shows current plan and renewal date
- [ ] Upgrade button launches payment flow (NOWPayments)
- [ ] Crypto payment creates PendingInvoice record
- [ ] Paid invoice upgrades account to correct tier
- [ ] PlanGate blocks Pro pages for free users
- [ ] PlanGate passes Pro pages for Pro users

---

## 10. AI SETTINGS

- [ ] AI Settings page loads without error
- [ ] Platform AI status shows correctly (active / pending / not included)
- [ ] Add custom API key (OpenAI/Anthropic/Gemini) — test button returns success
- [ ] Switch between platform AI and custom key — persists on reload
- [ ] Delete custom key — reverts to platform AI
- [ ] "Connect via Telegram" code prompt shows **Echo's username** (not @telegizer_bot)

---

## 11. ACCOUNT / SETTINGS

- [ ] Profile settings: update name, timezone — saves correctly
- [ ] Telegram account connect: generate code, send to bot, link appears
- [ ] Telegram account disconnect — confirmed in settings
- [ ] TOTP: disable 2FA, re-enable, backup codes regenerated
- [ ] Admin panel accessible only by admin accounts (non-admin gets 403)

---

## 12. DIRECTORY / MARKETPLACE

- [ ] Browse directory — community listings load
- [ ] Submit listing — moderation_status set to "pending"
- [ ] Rate limit: > 5 directory requests/min returns 429

---

## 13. SEPARATION REGRESSION CHECKS

These verify today's changes didn't break anything:

- [ ] `/ask` still works in groups via Telegizer (AI group query)
- [ ] `/remind` in group chat still works via Telegizer
- [ ] Note capture in Telegizer DM still works: "note: buy milk" → saved to Notes
- [ ] Reminder intent in Telegizer DM still works: "remind me to call tomorrow" → time picker shown
- [ ] `/warn`, `/ban`, `/xp`, `/leaderboard` all still work normally
- [ ] Group digest still fires (scheduled or manual)
- [ ] Auto-moderation (XP, warnings, flood detection) still active in groups
- [ ] Echo consent DM still triggered when Echo is added to a new group
- [ ] Echo still buffers group messages (check Redis key exists after message sent)
- [ ] Hub extraction still runs and creates tasks/reminders (check via Hub dashboard)

---

## 14. AI ACTIVITY LOGGING (Analytics → AI Activity)

> Verifies the AI Activity Center records every AI/group action exactly once and at zero extra AI cost.
> Open the group's **Analytics → AI Activity** tab to observe metrics, category chips, and the timeline.

### Automation chip
- [ ] **Official scheduled message** — schedule one for an official group; when it fires, **exactly one** `automation` row appears: "Scheduled message sent: <title>"
- [ ] **Official scheduled poll** — fires → one `automation` row: "Scheduled poll sent"
- [ ] **Custom scheduled message** — fires → one `automation` row (custom group)
- [ ] **Custom scheduled poll** — fires → one `automation` row (custom group)
- [ ] **Event workflow** — create a `message_received` workflow; trigger it → one `automation` row: "Workflow ran: <name>"
- [ ] **Scheduled (cron) workflow** — create a `scheduled` workflow; after its interval → one `automation` row: "Scheduled workflow ran: <name>"
- [ ] **Raid reminder** — start a raid with reminders enabled; at the 6h and 1h marks the bot posts a reminder, and **exactly one** `automation` row per dispatched reminder appears: "Raid reminder sent (Xh left)" (`source=raid_reminder`, custom scope). Confirm: 2 reminders dispatched ⇒ exactly 2 `ai_activity` rows, no duplicates, none missing.

### Moderation chip
- [ ] **Official AI moderation** — in an official group with Smart AI Moderation on, post promotional/off-topic text; on removal, **one** `moderation` row appears ("Promotional content removed" / "Off-topic content removed", `source=ai_automod`). Confirm it is **not** double-logged.
- [ ] **Custom AI moderation** (regression) — same in a custom-bot group still logs exactly one row.

### Knowledge / Engagement chips (Image AI)
- [ ] **Image answered** — in a group with Image AI on, post a captioned screenshot the bot can answer → one `knowledge` row: "Image question answered"
- [ ] **Image escalated** — post an image that escalates to support → one `engagement` row: "Image escalated to support". Confirm only one of answered/escalated logs per image (never both).

### Cross-cutting
- [ ] **No duplicates** — each action above produces exactly one `ai_activity` row (compare chip counts before/after a single action).
- [ ] **Zero AI cost** — performing the above triggers no *additional* AI API spend beyond the action itself (logging writes a DB row only).
- [ ] **DM/user-scoped not logged** — workspace reminders, meeting pre-alerts, and daily briefings do **not** create group `ai_activity` rows (they have no group scope — expected).

---

## SIGN-OFF

| Area | Tester | Date | Result |
|---|---|---|---|
| Auth | | | |
| Community Bot | | | |
| Echo Bot | | | |
| Assistant Hub | | | |
| Custom Bots | | | |
| Billing | | | |
| AI Activity logging | | | |
| Separation checks | | | |

**Overall result:** ⬜ PASS — ready to ship &nbsp;&nbsp; ⬜ FAIL — blocking issues found
