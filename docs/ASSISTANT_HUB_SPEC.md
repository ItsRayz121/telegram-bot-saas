# TELEGIZER ASSISTANT HUB — PRODUCT SPECIFICATION
**Version:** 4.0  
**Status:** Final — Ready for Sprint 1  
**Scope:** Module B — Assistant Hub (isolated from Module A public moderation)  
**Change from v3.0:** 5 backend decisions finalized — lazy record creation, shared @telegizer_bot token, Free plan access with limits, private-group focus with public group warning, downgrade = auto-pause with data preserved.

---

## 1. PRODUCT VISION

### What It Is
Assistant Hub is a passive AI intelligence layer that sits inside private Telegram groups, observes conversations, and surfaces what matters — tasks, decisions, meetings, reminders — into a unified personal inbox, without interrupting anyone.

### The Problem It Solves
Telegram is where real work happens for millions of teams. Decisions get buried in scroll. Tasks get promised and forgotten. Meetings get missed. There is no memory layer. Assistant Hub is that memory layer.

### Core Value Proposition
The assistant does the work of paying attention so the user does not have to.

### What Makes It Different

| Comparison | Differentiation |
|---|---|
| Telegram bots | They respond publicly, require commands, announce themselves. Assistant Hub is silent by default. |
| Slack AI | Requires migration to Slack. Works within Slack's message store. Assistant Hub works inside existing Telegram workflows. |
| Notion AI | Document-first. Requires content to already exist. Assistant Hub extracts from natural conversation. |
| AI chatbots | Respond when asked. Assistant Hub observes without being asked. |
| Automation tools | Require manual configuration. Assistant Hub works passively from day one. |
| Moderation systems | Enforce rules. Assistant Hub has zero enforcement role. |

---

## 2. PRODUCT POSITIONING

### Primary Statement
**"Your AI assistant for Telegram teams."**

### Differentiator Line
**"Quietly observes your groups. Surfaces what matters."**

### Product Category
AI productivity assistant for Telegram-native teams.

### Target Users
- Startup founders using Telegram for team coordination
- Creator teams managing projects via private groups
- Agencies running client projects inside Telegram
- Small-to-mid teams that live in Telegram and resist switching tools

### What Assistant Hub Must Never Become
- A moderation tool
- A chatbot that talks publicly without being asked
- A command-line interface for Telegram
- An automation platform or workflow builder
- A surveillance or monitoring system
- Another feature-bloated productivity app

### What Must Always Be Protected
- The passive model — the moment the assistant starts talking publicly by default, the product is dead
- The single-assistant-across-groups experience — users never configure per-group assistants separately
- Privacy-first defaults — opt-in observation, transparent extraction, full user control
- Simplicity of the inbox — if the inbox becomes complex, the product has failed

---

## 3. PRODUCT PHILOSOPHY (NON-NEGOTIABLE PRINCIPLES)

Every future feature decision is measured against these principles. If a feature violates a principle, the feature loses.

**Principle 1 — The assistant never interrupts.**
It does not speak in groups unless directly @mentioned. It does not post summaries publicly. It does not announce itself during conversations. Silence is the default. Silence is the feature.

**Principle 2 — The assistant works behind the scenes.**
Processing, extraction, summarization, and reminder creation happen invisibly. The user experiences outputs — inbox items, DMs, digests — not the machinery.

**Principle 3 — Extraction is not storage.**
Raw conversations are temporary buffers, not permanent records. The product stores what was extracted (tasks, decisions, reminders), not what was said. This is both a privacy principle and an architecture principle.

**Principle 4 — The assistant serves the user, not the group.**
It is a personal tool for the person who set it up. Its outputs go to that person's inbox and DMs. Other group members may never know it exists.

**Principle 5 — Human approval gates memory.**
The assistant never writes to its own memory automatically. It may suggest. The user approves. Memory is always user-authored, AI-assisted.

**Principle 6 — Trust is the product.**
Reliability matters more than capability. A smaller set of things done correctly beats a large set done inconsistently. An assistant that hallucinates or misextracts will be abandoned permanently.

**Principle 7 — Automation complexity is a debt.**
Pre-built automations only. No custom builders ever. Every toggle and condition added is a support ticket waiting to happen.

**Principle 8 — Privacy defaults protect users who do not read documentation.**
Consent must be explicit before observation begins. Retention windows are short by default. Deletion is one click. The user who never reads privacy settings must still be protected.

---

## 4. BOT IDENTITY HIERARCHY

### Architecture Overview

```
User Account
  └── Assistant Hub
        ├── Telegizer Official Bot    ← auto-created on Assistant Hub enable
        │     ├── Settings (AI personality, sensitivity, digest, templates, KB)
        │     └── Connected Groups → Extracted Data (tasks, reminders, decisions, meetings)
        │
        └── Custom Bot A              ← user connects from Module A (V1.5+)
              ├── Settings (inherits from Official; overrides where configured)
              └── Connected Groups → Extracted Data
```

### Three-Tier Data Ownership

| Level | Owns | Shared? |
|---|---|---|
| User | Account, billing, global memory (people, projects), unified inbox | Across all bots |
| Bot | Personality, templates, knowledge cards, automations, digest settings, connected groups | Per bot only |
| Group | Extracted tasks, reminders, decisions, meetings, notes, consent record | Per bot-group combination |

### Inheritance Model

**Telegizer Core (infrastructure — immutable)**
Extraction pipeline, AI model selection, privacy enforcement, data retention, encryption.
Cannot be overridden by any bot or user configuration.

**Official Telegizer Bot (user-configured)**
The baseline assistant. All settings configured here become the defaults for custom bots.

**Custom Bots (inheritable + overridable)**
Inherit all inheritable settings from Official Bot unless explicitly overridden.
Settings that are always bot-specific (never inherited): AI personality note, templates, knowledge cards, Telegram bot token.
Settings that are inheritable: extraction sensitivity, digest settings, automation toggles, notification preferences, silence windows.

**Inheritance Resolution Rule:**
A custom bot setting of NULL means "use the official bot's value." A custom bot setting with an explicit value overrides the official bot. This is resolved at runtime by the settings resolver service — never by reading raw database values directly.

### What Global Memory Means in This Hierarchy

Global memory (people, projects, context notes) is user-scoped, not bot-scoped. It is shared across all bots. When extracting from a group connected to "CreatorX Bot," the memory context injected into the extraction prompt includes all the user's memory entries regardless of which bot they were created under. This is correct behavior — the user has one organizational memory.

### Navigation Model (UX)

Assistant Hub follows the exact same interaction pattern as Group Management.

```
Groups:         Groups page (cards) → Manage Group → Top tabs (Members | Moderation | ...)
Assistant Hub:  Hub page (cards)    → Manage Assistant → Top tabs (Overview | Notes | ...)
```

"Hub" is one sidebar item. Clicking it opens a bot cards page. Clicking "Manage Assistant" on a card opens that bot's workspace. Navigation inside a workspace uses top tabs. The sidebar never shows feature-level items for Assistant Hub.

Workspace tabs: Overview | Notes | Reminders | Tasks | Templates | Knowledge (V1.5) | Automation | Settings

Automation is a workspace tab — not a global sidebar concept. Forwarding rules, smart triggers, and digest configuration live inside the Automation tab of the relevant assistant workspace.

---

## 5. NAVIGATION & UX STRUCTURE RULES

These rules are permanent. They define what the product is allowed to become in future versions.

1. **Assistant Hub ("Hub") is one sidebar item.** Features are never promoted to sidebar-level navigation.
2. **Global Automation sidebar stays as-is.** The existing `AUTOMATION → Forwarding, Workflows` sidebar section is not changed. The `Automation` tab inside each assistant workspace is a separate, additional concept covering assistant-specific behaviors (digest rules, smart triggers).
3. **Hub landing page shows bot cards.** Identical card-based layout to the existing Groups page.
4. **"Manage Assistant" opens a tabbed workspace.** Identical interaction to clicking "Manage" on a group — opens top-tab management UI.
5. **Workspace tabs are the navigation.** Overview | Notes | Reminders | Tasks | Templates | Knowledge | Automation | Settings. Nothing else.
6. **Data is bot-scoped inside a workspace.** Official bot workspace shows only data from groups connected to it. Custom bot workspace shows only that bot's data.
7. **Settings, group management, and memory are all inside the workspace.** Settings tab contains all bot config. Group settings open as overlays. Memory management opens as an overlay. No separate pages.
8. **Routes use /hub prefix.** Consistent with existing /groups and /channels URL structure.

---

## 6. FINALIZED SYSTEM DECISIONS

### Activation — Lazy Record Creation
The Hub sidebar item and bot cards page are visible to all users by default. No action required to see the UI. Backend records (`assistant_hub_global`, `bot_identities`, `assistant_bot_settings`) are created on first meaningful interaction — when the user first opens the Hub page or initiates group connection. No mass migration at deployment. No records pre-created for existing users.

### Bot Token — Shared @telegizer_bot
The Official Telegizer Assistant uses the existing shared `@telegizer_bot` token. No separate bot token is created for Assistant Hub in V1. The webhook handler routes updates by module context: a message from a group flagged as an Assistant Hub group is routed to the assistant pipeline; moderation groups route to Module A. Custom bots continue using their individual BotFather tokens.

### Plan Access — Free Plan Gets Assistant Hub
Assistant Hub is available on all plans including Free, with tiered limits. Plan names match the real Telegizer plan names used in the existing app. Limits are enforced at the API layer, not at UI render time (UI shows limits, enforcement happens on write).

| Feature | Free | Pro | Enterprise |
|---|---|---|---|
| Connected groups (official bot) | 2 | 10 | Unlimited |
| Custom assistant bots | 0 | 2 | Unlimited |
| Templates per bot | 5 | 30 | Unlimited |
| Knowledge cards per bot | 10 | 50 | Unlimited |
| Memory people entries | 5 | 50 | Unlimited |
| Extraction calls per day | 30 | 300 | Unlimited |
| Digest history retention | 30 days | 90 days | 90 days |

### Group Type — Private Groups Focus
Assistant Hub is designed for private groups. The bot connection flow shows a warning when a public or large group is detected (member count above threshold, or group type = public via Telegram API). The warning is informational — it does not block connection in V1. Public group management remains the responsibility of Module A (Group Management). Assistant Hub positioning never promotes public group use.

Public group detection logic:
- If `chat.type == 'supergroup'` AND `chat.username` is set (public supergroup) → show warning
- If member count > 500 → show warning
- Warning message: "This looks like a public group. Assistant Hub works best in private team groups. Continue?"

### Downgrade — Auto-Pause With Data Preserved
When a user downgrades to a lower plan:
- All historical extracted data is kept — nothing is deleted
- Groups exceeding the new plan limit are automatically paused (`is_active = false`, `pause_reason = 'plan_limit'`)
- Extraction stops for paused groups — data remains visible
- User is shown which groups were paused with an upgrade CTA
- User can choose which groups to keep active (within new limit) — activating one requires pausing another
- If user deletes account: full data deletion per privacy spec

---

## 8. MODULE ISOLATION REQUIREMENTS

Assistant Hub (Module B) is isolated from Public Group Management (Module A).

- Separate sidebar section in Telegizer dashboard
- Separate database tables with no shared foreign keys to moderation tables
- Separate bot behavior logic — moderation handlers and assistant handlers are distinct code paths
- No shared settings UI
- No shared admin concepts
- Shared: Telegizer user account, bot instance, billing plan

The assistant must never feel like a moderation dashboard, admin panel, or automod system.

---

## 9. CORE FEATURES BY VERSION

### V1 — The Reliable Core

| Feature | Description |
|---|---|
| Group connection | User connects private Telegram groups via dashboard |
| Consent flow | Bot DMs user before observation begins; user must confirm |
| Passive observation | Bot silently reads messages in connected groups |
| Message buffering | Raw messages buffered in Redis with 72-hour TTL |
| Batch extraction | Every 30 minutes: AI extracts tasks, reminders, decisions, meetings from buffer |
| Unified inbox | Dashboard shows all extracted items, tagged by source group |
| Daily digest | Telegram DM delivered at user-configured time |
| Immediate DM alerts | Urgent items (meetings, deadlines) sent immediately, not batched |
| Manual creation | User can manually create tasks, reminders, notes from dashboard |
| Quick Reply Templates | Reusable content blocks dispatched into groups via `/assist [name]` |
| Manual memory | User manually enters people, projects, global context |
| Centralized settings | One assistant setup applies across all connected groups |
| Per-group overrides | Group-specific: display name, category, silence window, extraction types |
| Privacy controls | Export, delete, pause, retention window |
| Plan gating | Group limits by plan tier |

### V1.5 — Intelligence Layer

| Feature | Description |
|---|---|
| Knowledge cards | Text-only knowledge entries, keyword-matched retrieval |
| @mention replies | Bot responds in group when @mentioned (OFF by default) |
| Pre-built automations | Toggle list: meeting reminder, deadline alert, follow-up reminder |
| On-demand summaries | User asks via DM: "what meetings are tomorrow?" |
| Memory suggestions | AI suggests memory additions; user approves before saving |
| Per-group silence windows | No DMs from a group during specified hours |

### V2 — Depth

| Feature | Description |
|---|---|
| pgvector embeddings | Semantic knowledge retrieval (only if card limits proven insufficient) |
| Cross-group summaries | "Across all groups this week..." |
| Follow-up detection | Promise made but never resolved |
| Unanswered question detection | Question in group goes unanswered for 24h → alert |
| Relationship memory | Approved people/role entries from AI suggestions |
| Activity analytics | Group activity patterns, recurring topics |
| Google Calendar push | Extracted meetings → calendar event (one-way) |
| Smart history search | Search across all extracted items |

### V3 — Platform

| Feature | Description |
|---|---|
| Team accounts | Multi-user shared assistant |
| Shared knowledge base | Team-scoped knowledge cards |
| API access | Enterprise integrations |
| Zapier/n8n output | Push tasks to Linear, Notion, etc. |
| Mobile companion app | Inbox access on mobile |

---

## 10. ASSISTANT BEHAVIOR SPECIFICATION

### Group Behavior (V1)
- Bot joins group, sends no message, makes no announcement
- Bot reads all messages, writes none
- Bot does not respond to commands or mentions
- Bot does not react to messages
- Bot does not reveal its presence

### Group Behavior (V1.5 — Active Mode enabled by group owner)
- Bot responds only to direct @mentions
- Bot sends a single reply (≤300 characters) per @mention
- Bot does not respond to messages not directed at it
- Rate limit: 5 bot replies per group per hour
- Bot never sends multi-message responses
- Bot never posts summaries into the group

### DM Behavior
- All output goes to user's Telegram DM with the bot
- Consent message sent on group join
- Immediate alerts sent as they occur (meeting detected, deadline found)
- Daily digest sent at user-configured time
- Reminder delivery sent at reminder time

### Command Support
- `/assist [name]` — dispatches a saved template into the group (V1)
- All other interaction happens via DM or dashboard, not group commands

---

## 11. CENTRALIZED VS GROUP-LEVEL CONFIGURATION

### Centralized (applies across all groups)
- AI personality note
- Response language
- Extraction sensitivity (Minimal / Standard / Aggressive)
- Digest schedule and format
- Notification preferences
- Pre-built automation toggles
- Memory entries (people, projects, global context)
- Knowledge cards

### Per-Group Overrides
- Display name for the group
- Category tag (Team / Project / Personal / Community)
- Silence window (no DMs from this group during these hours)
- Enable/disable: task extraction, reminder extraction, decision extraction, meeting extraction
- Active Mode toggle (@mention replies, V1.5)
- Active / Paused status

---

## 12. WHAT SHOULD NEVER BE BUILT

These items are permanently excluded regardless of user requests, market pressure, or feature comparisons:

- Custom automation trigger/condition builder
- Visual workflow editor
- Auto-reply to general group messages without @mention
- Per-group separate assistant setup (defeats centralized model)
- AI that writes to memory without user approval
- Public group assistant behavior (Module A handles public groups)
- Email or WhatsApp integrations before V3
- Competitive intelligence features
- AI-generated profiles of individuals without explicit user approval
- Permanent storage of raw conversation text

---

## 13. LONG-TERM COMPETITIVE MOAT

The moat is not the feature set. It is the organizational memory that accumulates over time.

After 6 months of use, a user's assistant knows:
- Who their key people are across every group
- What their active projects are
- What was decided, when, and in which group
- What follow-ups were promised and to whom
- Their team's communication patterns

That accumulated context is irreplaceable. It cannot be rebuilt quickly by a competitor. It grows more valuable every week. Everything in V1 and V1.5 exists to get users to day 180.
