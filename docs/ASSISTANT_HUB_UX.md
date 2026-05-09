# ASSISTANT HUB — UX & UI SYSTEM SPECIFICATION
**Version:** 5.0  
**Status:** Final — Ready for Sprint 1  
**Change from v4.0:** Public group warning UI added to group connection flow. Plan downgrade state added to Settings tab (paused groups). Free plan access confirmed with limits. Plan names updated to Free/Pro/Enterprise.

---

## 1. UX PHILOSOPHY

### The Core Mental Model
Assistant Hub follows the same interaction pattern as Group Management. Users already know this pattern — they use it for Groups and Channels. The learning curve is zero.

```
Groups UX:           Groups page (cards) → Manage Group → Top tabs (Members | Moderation | ...)
Assistant Hub UX:    Hub page (cards)    → Manage Assistant → Top tabs (Overview | Notes | ...)
```

This consistency is not a coincidence. It is the architecture. Every new section in Telegizer should follow this same pattern.

### Design Reference (Existing Telegizer Patterns)
- Landing page: card grid — same as current Groups page and Dashboard bot section
- Management workspace: top tabs — same as current Group Management tabs
- Card information density: same as existing group cards (status, connected count, last activity, action buttons)
- NOT: separate productivity SaaS navigation, Notion-style workspace, nested sidebar trees

### Core UX Rules
1. Sidebar stays minimal — features are never promoted to sidebar-level navigation
2. Assistant Hub is one sidebar item — leads to the bot cards page
3. Bot cards page mirrors Groups page — same card-based layout
4. Clicking "Manage Assistant" mirrors clicking "Manage" on a group — opens top-tab workspace
5. All assistant features live inside the workspace tabs
6. Automation is contextual to each assistant identity — not a global sidebar concept
7. Every extracted item always shows its source group
8. Empty states are actionable — no blank screens
9. The assistant should feel like a Telegizer-native feature, not a separate product

---

## 2. FINAL SIDEBAR STRUCTURE

```
┌───────────────────────────┐
│  TELEGIZER                │
│───────────────────────────│
│  Dashboard                │
│───────────────────────────│
│  COMMUNITIES              │
│  Groups                   │
│  Channels                 │
│───────────────────────────│
│  ASSISTANT HUB            │
│  Hub                      │  ← leads to assistant cards page
│───────────────────────────│
│  AUTOMATION               │
│  Forwarding               │  ← kept as-is, unchanged
│  Workflows                │  ← kept as-is, unchanged
│───────────────────────────│
│  ACCOUNT                  │
│  Billing                  │
│  Settings                 │
└───────────────────────────┘
```

The global `AUTOMATION` sidebar section (Forwarding, Workflows) remains exactly as it is today. It is not moved or removed.

The `Automation` tab inside each assistant workspace is a **separate, additional** concept — it covers assistant-specific behaviors (digest rules, smart triggers, forwarding digests to a chat). These are distinct from the global platform Automation features.

---

## 3. LEVEL 1 — ASSISTANT HUB LANDING PAGE (Bot Cards)

Clicking "Hub" in the sidebar opens the **Assistant Hub landing page**.

This page follows the same visual pattern as the existing Groups page and Dashboard bot section.

```
┌──────────────────────────────────────────────────────────────────┐
│  AI Assistant Hub                                                │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  🤖  Official Telegizer Assistant          [Active]       │   │
│  │  @telegizer_bot · Shared · Always Active                  │   │
│  │                                                           │   │
│  │  4 groups connected  ·  Last summary: 2 hours ago        │   │
│  │  3 pending tasks  ·  1 meeting today                     │   │
│  │                                                           │   │
│  │  [+ Add to Group]          [⚙ Manage Assistant]          │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  Custom Bots                              [49 slots free]        │
│  [+ Add Bot]                                                     │
│                                                                  │
│  ┌────────────────────────────┐  ┌────────────────────────────┐ │
│  │  ⚡ CreatorX Assistant     │  │  ⚡ Agency Assistant        │ │
│  │  @creatorbotxyz            │  │  @agencyassist             │ │
│  │                            │  │                            │ │
│  │  2 groups · Active         │  │  1 group · Active          │ │
│  │  Last: Yesterday           │  │  Last: May 6               │ │
│  │                            │  │                            │ │
│  │  [⚙ Manage Assistant]      │  │  [⚙ Manage Assistant]      │ │
│  └────────────────────────────┘  └────────────────────────────┘ │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Card Information (mirrors group card pattern)

**Official bot card shows:**
- Bot name, username, type badge (Shared / Always Active)
- Connected group count
- Last summary timestamp
- Quick stats: pending tasks count, meetings today
- `[+ Add to Group]` — quick action to connect a new group
- `[⚙ Manage Assistant]` — opens assistant workspace

**Custom bot card shows:**
- Bot name, username
- Connected group count, status badge (Active / Paused)
- Last activity timestamp
- `[⚙ Manage Assistant]`

### V1 State
- Only Official Telegizer Assistant card appears
- "Custom Bots" section shows `[+ Add Bot]` with plan gate if Free
- No custom bot cards in V1

---

## 4. LEVEL 2 — ASSISTANT MANAGEMENT WORKSPACE (Top Tabs)

Clicking "Manage Assistant" on any bot card opens that bot's management workspace.

This follows exactly the same pattern as the existing Group Management page.

```
┌──────────────────────────────────────────────────────────────────┐
│  ← Hub    🤖 Official Telegizer Assistant             [Active]   │
│           @telegizer_bot · 4 groups connected                    │
├──────────────────────────────────────────────────────────────────┤
│  Overview  │  Notes  │  Reminders  │  Tasks  │  Templates  │  Knowledge  │  Automation  │  Settings  │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  [tab content area]                                              │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

The "← Hub" back link returns to the bot cards page.

**Tab visibility by version:**

| Tab | V1 | V1.5 | Notes |
|---|---|---|---|
| Overview | ✓ | ✓ | Always first |
| Notes | ✓ | ✓ | |
| Reminders | ✓ | ✓ | |
| Tasks | ✓ | ✓ | |
| Templates | ✓ | ✓ | |
| Knowledge | — | ✓ | Hidden in V1 |
| Automation | ✓ | ✓ | V1: digest + triggers only |
| Settings | ✓ | ✓ | Always last |

---

## 5. TAB CONTENT SPECIFICATIONS

### Tab: Overview

The intelligence dashboard for this bot — all extracted items surfaced across connected groups.

```
┌──────────────────────────────────────────────────────────────────┐
│  Overview  │  Notes  │  Reminders  │  Tasks  │  ...             │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Today · May 9, 2026                    [Group: All ▾]  [⟳]    │
│                                                                  │
│  ─── TASKS (3) ─────────────────────────────────────────────    │
│  □  Finalize investor deck    [CreatorX Team]    Due May 11      │
│     [Confirm]  [Edit]  [Dismiss]                                 │
│                                                                  │
│  □  Send invoice to Acme      [Finance Ops]      Overdue ●      │
│     [Confirm]  [Edit]  [Dismiss]                                 │
│                                                                  │
│  □  Review contract           [Legal Group]      No date        │
│     [Confirm]  [Edit]  [Dismiss]                                 │
│                                                                  │
│  ─── MEETINGS (1) ──────────────────────────────────────────    │
│  ○  Investor deck review      [CreatorX Team]    Tomorrow 3pm   │
│     [Confirm]  [Edit]  [Dismiss]                                 │
│                                                                  │
│  ─── DECISIONS (2) ─────────────────────────────────────────    │
│  ◆  Sara handles partnership  [CreatorX Team]                   │
│     [Dismiss]                                                    │
│                                                                  │
│  ◆  Beta delayed to June      [Marketing Group]                 │
│     [Dismiss]                                                    │
│                                                                  │
│  ─── REMINDERS (1) ─────────────────────────────────────────    │
│  ◉  Follow up with Ahmed      [Internal Ops]     Today 5pm      │
│     [Done]  [Snooze]  [Dismiss]                                  │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

**Behavior:**
- Default: today's new items grouped by type
- Source group shown on every item in brackets
- Empty sections not shown (no empty DECISIONS header if no decisions)
- Overdue items shown with red marker — never hidden
- Group filter: all groups → single group
- Confirm → item moves to its tab (Tasks, Reminders) with confirmed status
- Dismiss → removed from Overview only, item not deleted

**Overview Empty State (no groups connected):**
```
│  Add the Telegizer bot to your private groups to get started.   │
│  The assistant will silently observe and surface items here.    │
│  [+ Add to Group]                                               │
```

**Overview Empty State (groups connected, no activity yet):**
```
│  Watching 2 groups. I'll surface tasks and meetings here        │
│  when there's discussion activity.                              │
```

---

### Tab: Notes

```
┌──────────────────────────────────────────────────────────────────┐
│  Notes  │  [+ New Note]  [Group: All ▾]  [All | Manual | AI]   │
├──────────────────────────────────────────────────────────────────┤
│  May 9                                                           │
│  📌 Partnership deal terms agreed      [CreatorX Team]   AI     │
│  📝 Meeting prep checklist             [Manual]                  │
│                                                                  │
│  May 7                                                           │
│  📌 Q2 goals finalized                 [Internal Ops]    AI     │
│  📝 Investor talking points            [Manual]                  │
└──────────────────────────────────────────────────────────────────┘
```

AI badge = extracted by assistant. No badge = manually created. Source group always shown on extracted notes.

---

### Tab: Reminders

```
┌──────────────────────────────────────────────────────────────────┐
│  Reminders  │  [+ New Reminder]  [Upcoming | Delivered | All]   │
├──────────────────────────────────────────────────────────────────┤
│  TODAY                                                           │
│  ◉  Follow up with Ahmed         [Internal Ops]    5:00 PM      │
│                                                                  │
│  TOMORROW                                                        │
│  ◉  Investor deck review (1hr)   [CreatorX Team]   2:00 PM      │
│                                                                  │
│  THIS WEEK                                                       │
│  ◉  Send weekly report           [Manual]          Fri 9:00 AM  │
└──────────────────────────────────────────────────────────────────┘
```

---

### Tab: Tasks

```
┌──────────────────────────────────────────────────────────────────┐
│  Tasks  │  [+ New Task]  [Pending | Confirmed | Done]  [Group ▾]│
├──────────────────────────────────────────────────────────────────┤
│  OVERDUE                                                         │
│  ●  Send invoice to Acme         [Finance Ops]    Was May 8     │
│                                                                  │
│  TODAY                                                           │
│  □  Review partnership contract  [Legal Group]                   │
│                                                                  │
│  UPCOMING                                                        │
│  □  Finalize investor deck       [CreatorX Team]  May 11        │
│  □  Prepare Q2 report            [Internal Ops]   May 15        │
│                                                                  │
│  NO DATE                                                         │
│  □  Update onboarding docs       [CreatorX Team]                │
└──────────────────────────────────────────────────────────────────┘
```

Clicking a task opens an inline detail panel (not a new page).

---

### Tab: Templates

```
┌──────────────────────────────────────────────────────────────────┐
│  Templates  │  [+ New Template]                                  │
│  Dispatch reusable content into groups with /assist [name]       │
├──────────────────────────────────────────────────────────────────┤
│  Name                   Trigger              Uses    Last Used   │
│  ─────────────────────────────────────────────────────────────  │
│  CreatorX Intro         /assist intro        12      May 7      │
│  Partnership FAQ        /assist faq          3       May 3      │
│  Rate Card 2026         /assist rates        7       May 9      │
└──────────────────────────────────────────────────────────────────┘
```

Templates are bot-scoped. Templates from Telegizer Official do not appear in Custom Bot workspaces.

---

### Tab: Knowledge (V1.5)

```
┌──────────────────────────────────────────────────────────────────┐
│  Knowledge  │  [+ New Card]   7 of 10 used   [Upgrade for more] │
│  Answer @mention queries using stored project information        │
├──────────────────────────────────────────────────────────────────┤
│  CreatorX Users          #metrics #users             [Edit][Del] │
│  Rate Card 2026          #pricing #rates             [Edit][Del] │
│  Partnership FAQ         #faq #partners              [Edit][Del] │
└──────────────────────────────────────────────────────────────────┘
```

Knowledge tab is hidden in V1. Appears in V1.5.

---

### Tab: Automation

Automation is bot-contextual behavior — rules and triggers that apply to this specific assistant across all its connected groups.

**V1 Automation Tab (Digest + Smart Triggers only):**

```
┌──────────────────────────────────────────────────────────────────┐
│  Automation                                                      │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ── DAILY DIGEST ────────────────────────────────────────────   │
│  Send a daily summary to your Telegram DM                        │
│  Status       [✓ Enabled]                                        │
│  Time         [9:00 PM ▾]                                        │
│  Format       [Compact ▾]                                        │
│                                                                  │
│  ── SMART TRIGGERS ──────────────────────────────────────────   │
│  Automated behaviors when specific events are detected           │
│                                                                  │
│  [✓] Meeting Reminder                                            │
│      Remind me 1 hour before any extracted meeting               │
│                                                                  │
│  [✓] Deadline Alert                                              │
│      Send me a DM immediately when a task with a                 │
│      deadline is extracted                                       │
│                                                                  │
│  [ ] Follow-up Reminder                                          │
│      Remind me 2 days after a follow-up is detected             │
│                                                                  │
│  ── FORWARDING ──────────────────────────────────────────────   │
│  Forward extracted summaries to another Telegram chat            │
│  [Coming in V1.5]                                                │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

**V1.5 Automation Tab adds:**
- Forwarding rules (forward digest or extracted items to a Telegram chat/channel)
- Per-group trigger overrides (disable a trigger for one specific group)

**V2 Automation Tab adds:**
- Scheduled summary rules
- Unanswered question alerts
- Follow-up detection rules

**What Automation never becomes:**
- A visual workflow builder
- A drag-and-drop automation canvas
- A Zapier/n8n interface
- A cross-bot automation system

All automations are pre-built toggles. Users enable or disable them. They cannot build custom trigger conditions.

---

### Tab: Settings

All bot-level configuration in one place. Structured identically for both Official and Custom bots (Custom bots show inheritance indicators).

```
┌──────────────────────────────────────────────────────────────────┐
│  Settings                                                        │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ── AI ASSISTANT ────────────────────────────────────────────   │
│  Personality Note                                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ I'm a founder focused on growth. Keep extractions        │  │
│  │ focused on action items and decisions.                   │  │
│  └──────────────────────────────────────────────────────────┘  │
│  Max 200 chars · Applied to all extractions for this bot        │
│                                                                  │
│  Response Language      [English ▾]                             │
│  Extraction Sensitivity [Minimal] [Standard ✓] [Aggressive]     │
│                                                                  │
│  ── CONNECTED GROUPS ────────────────────────────────────────   │
│  ●  CreatorX Team       Active             [Group Settings]     │
│  ●  Marketing Group     Active             [Group Settings]     │
│  ○  Legal Group         Paused             [Group Settings]     │
│  [+ Add to Group]                                               │
│                                                                  │
│  ── MEMORY ──────────────────────────────────────────────────   │
│  Global memory is shared across all your bots.                  │
│  People saved: 2   Projects saved: 1                            │
│  [Edit Memory →]                                                │
│                                                                  │
│  ── NOTIFICATIONS ───────────────────────────────────────────   │
│  Telegram DM alerts    [✓ Enabled]                              │
│                                                                  │
│  ── PRIVACY & DATA ──────────────────────────────────────────   │
│  Message retention     [72 hours ▾]                             │
│  [Export data from this bot]                                    │
│  [Delete data from this bot]                                    │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Settings Tab — Custom Bot (Inheritance Indicators)

```
│  Extraction Sensitivity      ↩ Inherited from Telegizer Official │
│  [Minimal] [Standard ✓] [Aggressive]                [Override]  │
│                                                                  │
│  Daily Digest                ↩ Inherited — 9:00 PM, Compact     │
│                                                     [Override]  │
```

`↩ Inherited` label on settings using the official bot's value.
`[Override]` creates a bot-specific value.
`[Reset to inherited]` replaces `[Override]` after a value is set.

---

## 6. GROUP SETTINGS OVERLAY

Clicking `[Group Settings]` in the Settings tab opens a modal overlay — not a new page.

```
┌──────────────────────────────────────────────────────┐
│  Group Settings · CreatorX Team            [× Close] │
├──────────────────────────────────────────────────────┤
│  Display Name      [CreatorX Team__________]         │
│  Category          [Team ▾]                          │
│                                                      │
│  ── EXTRACTION ─────────────────────────────────    │
│  Tasks       [✓]   Reminders   [✓]                  │
│  Decisions   [✓]   Meetings    [✓]                  │
│                                                      │
│  ── BEHAVIOR ───────────────────────────────────    │
│  Status        [Active ▾]                           │
│  Active Mode   [Off ▾]   (@mention replies, V1.5)   │
│                                                      │
│  ── SILENCE WINDOW ─────────────────────────────    │
│  No DMs from this group:                            │
│  [10:00 PM ▾]   to   [08:00 AM ▾]                  │
│                                                      │
│  ── DANGER ZONE ────────────────────────────────    │
│  [Delete data from this group]                      │
│  [Disconnect group]                                 │
└──────────────────────────────────────────────────────┘
```

---

## 7. MEMORY MANAGEMENT OVERLAY

Accessed via Settings tab → `[Edit Memory →]`. Opens as a full-screen overlay. Memory is user-scoped — shared across all bots.

```
┌──────────────────────────────────────────────────────────────────┐
│  Assistant Memory                                     [× Close]  │
│  Shared across all your assistants                               │
├──────────────────────────────────────────────────────────────────┤
│  YOUR CONTEXT                                                    │
│  Name         [Fazal________________]                            │
│  Company      [CreatorX_______________]                          │
│  Role         [Founder________________]                          │
│  Timezone     [PKT (UTC+5) ▾]                                    │
│  Notes        [Growth metrics and investor prep_______________]  │
│               Max 500 characters                                 │
│                                                                  │
│  ── PEOPLE ─────────────────────────────────────────────────    │
│  [+ Add Person]                                                  │
│  Ahmed   Marketing Lead   [CreatorX Team]          [Edit][Del]  │
│  Sara    Partnerships     [CreatorX, Marketing]    [Edit][Del]  │
│                                                                  │
│  ── PROJECTS ───────────────────────────────────────────────    │
│  [+ Add Project]                                                 │
│  Alpha Launch   Active   Due Jun 2026   [CreatorX] [Edit][Del]  │
│                                                                  │
│                                            [Save Changes]        │
└──────────────────────────────────────────────────────────────────┘
```

---

## 8. ADD TO GROUP FLOW

Triggered from `[+ Add to Group]` on bot card or in Settings tab.

```
STEP 1 — Instructions overlay:
  "Add @TelegizerBot to your private Telegram group.
   No admin permissions needed.
   Once added, I'll DM you to confirm."
  [Copy bot username]       [I added the bot →]

STEP 2 — Waiting:
  "Waiting for you to add the bot to a group..."
  [animated pulse]
  [Cancel]

STEP 3 — Consent pending:
  "Check your Telegram DM from @TelegizerBot to confirm."

STEP 3a — Public/large group warning (if detected):
  Shown in the DM. Dashboard reflects pending state.
  ┌─────────────────────────────────────────────────────┐
  │  ⚠️  Large or public group detected                  │
  │                                                     │
  │  Assistant Hub works best in private team groups.   │
  │  For public community management, use Group         │
  │  Management instead.                                │
  │                                                     │
  │  [Connect Anyway]            [Cancel]               │
  └─────────────────────────────────────────────────────┘

STEP 4 — Connected:
  "CreatorX Team connected. Activity will appear in Overview."
  [Go to Overview]
```

### Plan Limit — Paused Groups State (Settings Tab)

When a user is on Free plan and has groups paused due to the 2-group limit:

```
│  ── CONNECTED GROUPS ────────────────────────────────────────   │
│  ●  CreatorX Team       Active             [Group Settings]     │
│  ●  Marketing Group     Active             [Group Settings]     │
│  ○  Legal Group         Paused · Plan limit   [Swap]  [Upgrade] │
│  ○  Finance Ops         Paused · Plan limit   [Swap]  [Upgrade] │
│                                                                  │
│  Free plan: 2 active groups.  [Upgrade to Pro →]               │
```

`[Swap]` activates this group by letting user choose which active group to pause.
`[Upgrade]` opens billing.
Paused groups remain visible in all tabs — historical data never hidden.

---

## 9. ONBOARDING FLOW

Shown on first visit to the Hub page (before any assistant is configured).

### Step 1 — What Is This

```
┌──────────────────────────────────────────────────────────────────┐
│  Welcome to AI Assistant Hub                                     │
│                                                                  │
│  Your AI assistant for Telegram teams.                          │
│  Quietly observes your groups. Surfaces what matters.           │
│                                                                  │
│  ✓  Extracts tasks, decisions, meetings from discussions         │
│  ✓  Sends you a daily digest of what matters                     │
│  ✓  No admin permissions required in your groups                 │
│  ✗  Does not talk in groups unless you allow it                  │
│  ✗  Does not store your messages permanently                     │
│                                                                  │
│                                       [Get Started →]            │
└──────────────────────────────────────────────────────────────────┘
```

### Step 2 — Quick Context (Optional)

```
│  Tell me a bit about yourself (helps with extractions)          │
│  Name / Company / Role / Timezone                               │
│  [Skip for now]                          [Continue →]           │
```

### Step 3 — Connect First Group

```
│  Add @TelegizerBot to your first private group                  │
│  [Copy bot username]                                            │
│  Waiting...  [pulse]        [I'll do this later]               │
```

### Step 4 — Done

```
│  You're ready.                                                  │
│  Activity from your groups will appear in Overview.             │
│                                      [Go to Overview →]         │
```

---

## 10. TELEGRAM DM MESSAGE FORMATS

### Consent DM
```
You added me to [GroupName].

Before I start:
• I'll extract tasks, reminders, and meetings
• Raw messages deleted after 72 hours
• Extracted items stored in your Telegizer account
• Other members not notified automatically

Start observing this group?
[✓ Start]   [✗ Cancel]
```

### Immediate Alert DM
```
📅 Meeting detected · CreatorX Team

Investor deck review call
Tomorrow at 3:00 PM

→ telegizer.com/hub
```

### Daily Digest DM — Compact
```
📊 Today · May 9

CreatorX Team → 2 tasks, 1 meeting tomorrow
Marketing Group → 1 decision
Finance Ops → 1 overdue task ⚠️

→ Open Hub
```

### Reminder DM
```
🔔 Reminder

Follow up with Ahmed about the contract review.
From: Internal Ops

[Done] [Snooze 1hr]
```

---

## 11. EMPTY STATES

| Location | When | Message | Action |
|---|---|---|---|
| Hub page | No groups connected | "Add the Telegizer bot to your private groups to get started." | [+ Add to Group] |
| Overview tab | Groups connected, no activity | "Watching [N] group(s). Activity will appear here." | — |
| Notes tab | No notes | "No notes yet. I'll extract them from group discussions." | [+ New Note] |
| Tasks tab | No tasks | "No tasks yet. I'll surface them from group discussions." | [+ New Task] |
| Reminders tab | No reminders | "No reminders scheduled." | [+ New Reminder] |
| Templates tab | No templates | "Create templates to dispatch reusable content into your groups." | [+ New Template] |
| Knowledge tab | No cards | "Add knowledge cards so I can answer questions from your groups." | [+ New Card] |
| Automation tab | — | Always shows content (digest + triggers toggles visible even when disabled) | — |

---

## 12. ROUTE STRUCTURE

```
/hub                                        ← Hub landing page (bot cards)

/hub/official                               ← Official bot workspace → defaults to Overview
/hub/official/overview
/hub/official/notes
/hub/official/reminders
/hub/official/tasks
/hub/official/templates
/hub/official/automation
/hub/official/settings
(Knowledge hidden in V1)

/hub/bots/:bot_id                           ← Custom bot workspace (V1.5+)
/hub/bots/:bot_id/overview
/hub/bots/:bot_id/notes
/hub/bots/:bot_id/reminders
/hub/bots/:bot_id/tasks
/hub/bots/:bot_id/templates
/hub/bots/:bot_id/knowledge
/hub/bots/:bot_id/automation
/hub/bots/:bot_id/settings
```

Routes use `/hub` prefix to match existing Telegizer URL convention (`/groups`, `/channels`).

---

## 13. RESPONSIVE BEHAVIOR

- Sidebar collapses to icons on tablet (Hub = robot icon)
- Bot cards page: single column on mobile
- Workspace tabs: horizontally scrollable on mobile, no wrapping
- Group settings overlay: full-screen sheet on mobile
- Memory overlay: full-screen sheet on mobile
- All tap targets: minimum 44px
