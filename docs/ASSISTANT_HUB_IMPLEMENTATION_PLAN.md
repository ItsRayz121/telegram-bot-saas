# ASSISTANT HUB — IMPLEMENTATION PLAN
**Version:** 3.0  
**Status:** Final  
**Total V1 Duration:** 10–11 weeks  
**V1.5 Duration:** 6–8 weeks after V1 launch  
**Change from v2.0:** Navigation aligned with Telegizer Group Management pattern. Automation tab added to assistant workspace for assistant-specific behaviors (digest, smart triggers). Global Automation sidebar kept unchanged. Route prefix changed from /assistant to /hub.

---

## IMPLEMENTATION PRINCIPLES

- Ship the smallest version that proves the passive model works before building anything else
- Each sprint must be independently testable
- AI quality must be validated with real messages before each AI-dependent sprint ships
- No sprint ships broken UX — every screen has a working empty state
- Backend is always ahead of frontend by at least one sprint
- Privacy controls ship in V1, not V1.5

---

## V1 IMPLEMENTATION — THE RELIABLE CORE

---

### SPRINT 1 — Foundation & Data Layer (Weeks 1–2)

**Goal:** Database ready, Telegram webhook live, message buffering working.

**Backend**
- Create all database tables (see `ASSISTANT_HUB_DATABASE.md` v2.0)
- `bot_identities`, `assistant_hub_global`, `assistant_bot_settings`
- `connected_groups`, `extraction_batches`
- `tasks`, `reminders`, `decisions`, `meetings`, `notes`
- `templates`, `knowledge_cards` (bot-scoped)
- `memory_global`, `memory_people`, `memory_projects`, `memory_group_context`, `memory_suggestions`
- `system_automations` (seed pre-built records), `bot_automation_settings`
- `inbox_items`, `digests`
- Auto-create official `bot_identities` record when user enables Assistant Hub
- Settings resolver service: `getEffectiveSettings(botId)` — single access point, never bypass
- Telegram webhook receiver endpoint
- Bot update handler: receive group messages, identify which bot the group is connected to, filter accordingly
- Redis setup: buffer keys include `bot_id` prefix (`assistant:buffer:{bot_id}:{group_id}`)
- BullMQ: queue scaffold (extraction queue, notification queue)
- Plan limits enforcement service (check connected group count per bot, total extraction calls)

**Frontend — Sidebar & Navigation**
- Global AUTOMATION sidebar section (Forwarding, Workflows) remains unchanged — do not touch
- "Hub" sidebar item already exists in current sidebar under ASSISTANT HUB section — keep as-is
- Route scaffold:
  - `/hub` → bot cards landing page (Telegizer Official card, Custom Bots section)
  - `/hub/official` → Telegizer Official workspace → redirects to /hub/official/overview
  - `/hub/official/:tab` → tab routing (overview, notes, reminders, tasks, templates, automation, settings)
- Bot cards page: Official bot card with group count, last activity, pending task count
- Bot workspace shell: top tab bar with correct tabs, "← Hub" back link
- V1: Knowledge tab not rendered (hidden)
- V1: Custom Bots section shows plan-gated "+ Add Bot" with "Coming in V1.5" for Free plan
- Automation tab visible in V1 with Digest + Smart Triggers content
- Page shells for all tabs (empty states defined per tab)
- Basic auth guard: redirect to main Telegizer login if not authenticated

**Infrastructure**
- Redis instance configured
- Worker process scaffold (separate process)
- Environment variables: `OPENAI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `REDIS_URL`, `ENCRYPTION_KEY`

**Testing**
- Confirm Telegram webhook receives messages in test group
- Confirm messages written to Redis buffer with correct `bot_id:group_id` key structure and TTL
- Confirm official bot identity auto-created on Assistant Hub enable
- Confirm settings resolver returns correct defaults for official bot
- Confirm database tables created with correct indexes

**NOT in Sprint 1**
- Any AI calls
- Any frontend data display
- Consent flow
- Extraction
- Custom bot UI (V1.5)

---

### SPRINT 2 — Consent Flow & Group Connection (Weeks 3–4)

**Goal:** User can connect a group with full consent flow. Privacy controls functional.

**Backend**
- Bot join event handler: detect when bot is added to a group
- Consent DM sender: bot DMs the user who added it with consent message
- Consent confirmation handler: process user's confirm/cancel button response
- If confirm: create `connected_groups` record, set `consent_confirmed_at`
- If cancel: bot leaves group, no database record created
- Introduction message sender (optional, user-controlled from DM response)
- Group disconnect handler: bot leaves group, prompt for data deletion
- Pause/resume toggle endpoint

**Frontend**
- Settings tab (`/hub/official/settings`) — Connected Groups section: group list with status badges, [+ Add to Group] button, [Group Settings] per group
- Connect new group flow (instruction screen + polling state + success state + public group warning overlay)
- Group settings overlay component (modal/sheet): name, category, extraction toggles, silence window, active/paused
- Disconnect group confirmation modal

**Privacy**
- Export all data endpoint (returns JSON, async for large datasets)
- Delete data from one group endpoint
- Delete all assistant data endpoint (cascading)
- Retention window setting (stored in `assistant_hub_settings`)
- Retention enforcement cron (daily cleanup job)

**Frontend — Settings**
- Settings tab (`/hub/official/settings`) — Privacy & Data section: retention window selector, export button, delete all data (with "DELETE" confirmation)

**Testing**
- Full consent flow end-to-end with real Telegram group
- Cancel flow: bot leaves, no database record
- Disconnect: bot leaves group, data deleted if requested
- Export: JSON file contains expected structure
- Delete: all data removed, bot leaves all groups

---

### SPRINT 3 — Extraction Pipeline (Weeks 5–6)

**Goal:** Batch extraction working, items appearing in database. This is the most critical sprint.

**Pre-Sprint (before coding begins)**
- Build test corpus: 20+ real Telegram conversation samples
- Cover: task assignments, meeting scheduling, deadline mentions, decisions, quiet conversations
- Run extraction prompt manually against all samples
- Tune prompt until precision > 90% on obvious items
- Document edge cases and known failure modes

**Backend**
- Extraction worker: BullMQ worker processing extraction queue
- Standard batch trigger: cron every 30 minutes
- Immediate trigger detection: keyword/pattern matching on message receipt
- Priority queue processor: runs every 2 minutes for triggered messages
- Memory context builder: assembles injection string from memory tables
- OpenAI API integration: GPT-4o-mini call with extraction prompt
- JSON output validator: schema validation before storage
- Write extracted items to: `tasks`, `reminders`, `decisions`, `meetings`
- Create `inbox_items` records for each extracted item
- Log batch to `extraction_batches` (token count, status)
- Daily call limit enforcement (check against plan limits)

**Backend — Automation Triggers (partial)**
- Post-extraction: check if meeting_reminder automation is enabled → create reminder
- Post-extraction: check if deadline_alert automation is enabled → flag for DM

**Testing (critical)**
- Run extraction against all 20+ test corpus samples
- Validate: correct items extracted, no hallucinated items
- Validate: JSON schema validation catches malformed outputs
- Validate: empty conversations produce no AI call, no database writes
- Validate: 500-message overflow cap works
- Validate: daily limit enforcement stops extraction at threshold
- Cost monitoring: log tokens used per batch, calculate per-user daily cost

**NOT in Sprint 3**
- Frontend display (Sprint 4)
- Notification/DM delivery (Sprint 4)
- Any memory suggestion logic

---

### SPRINT 4 — Inbox & Notification Delivery (Weeks 7–8)

**Goal:** Inbox showing extracted items, daily digest delivered to Telegram DM.

**Backend**
- Inbox items API: fetch items for user, sorted by urgency, filterable by group/type
- Item action endpoints: confirm, dismiss (update `inbox_items` and source tables)
- Notification decision engine: immediate DM vs digest queue
- Telegram DM formatter: compact and detailed digest formats
- Daily digest builder: pulls items since last digest, groups by source group
- Digest delivery cron: fires at user's configured digest time
- Immediate DM sender: for urgent items (deadline_alert automation)
- Reminder scheduler: cron checks reminders due within next 5 minutes, sends DM

**Frontend**
- Overview tab (`/hub/official/overview`): full intelligence view with sections (Tasks, Meetings, Decisions, Reminders), group filter, action buttons per item
- Overview empty states (no groups connected; groups connected but no activity yet)
- Tasks tab (`/hub/official/tasks`): task list with status tabs and group filter
- Reminders tab (`/hub/official/reminders`): list with upcoming/overdue grouping
- Notes tab (`/hub/official/notes`): list with manual/extracted badge
- Task detail panel (inline, not new page)
- Create/edit modals: task, reminder, note (accessible from their respective tabs)

**Frontend — Automation Tab**
- Automation tab (`/hub/official/automation`): Daily Digest section + Smart Triggers toggle list
- Digest section: enable/disable, time picker, format selector
- Smart Triggers: Meeting Reminder toggle, Deadline Alert toggle, Follow-up Reminder toggle
- Forwarding section: visible but labeled "Coming in V1.5" — not functional in V1
- Automation tab ships with real content in V1 — not a placeholder

**Frontend — Settings Tab (partial)**
- Settings tab (`/hub/official/settings`): scaffold with all sections
- AI Assistant section: personality note, language, sensitivity
- Connected Groups section: list with status badges, [+ Add to Group] button, [Group Settings] per group
- Group settings overlay component (modal/sheet)
- Notifications section: Telegram DM preferences

**Testing**
- Inbox displays correct items from test extraction data
- Confirm action on task updates status correctly
- Dismiss removes from inbox, item still in tasks list
- Daily digest delivered to correct Telegram DM at configured time
- Digest format correct (compact vs detailed)
- Overdue items marked correctly
- Immediate DM fires for deadline_alert automation
- Reminder DM fires at correct time

---

### SPRINT 5 — Manual Creation & Templates (Weeks 9–10)

**Goal:** User can manually create all item types. Templates working in Telegram groups.

**Backend**
- Manual create endpoints: POST for tasks, reminders, notes (no group required)
- Manual edit endpoints: PATCH for all item types
- Manual delete endpoints: DELETE for all item types
- Templates CRUD: create, read, update, delete (bot-scoped)
- `/assist [name]` command handler: bot receives command in group, looks up template by `bot_id` + name, sends content
- Template use_count increment on dispatch
- `/assist` unknown template: bot replies "Template '[name]' not found. Check your dashboard."

**Frontend**
- Create task modal: full form with all fields
- Create reminder modal: content + datetime picker
- Create note modal: content + tags
- Edit modals for all three types
- Delete confirmation for all three types
- Templates tab (`/hub/official/templates`): list, create, edit, delete, usage stats

**Testing**
- Create task manually, appears in tasks and inbox
- Create reminder, delivers at correct time
- Create note, appears in notes
- Template dispatched correctly to Telegram group
- Unknown template: correct error response in group
- Template use_count increments correctly

---

### SPRINT 6 — Memory & Settings Completion (Weeks 10–11, partial overlap)

**Goal:** Memory system functional, all settings screens complete, plan gating enforced.

**Backend**
- Memory CRUD: global context, people, projects, group context
- Memory context injection: update extraction worker to include memory in every prompt
- Validate: extraction quality improves with memory context vs without
- Plan limits: enforce knowledge card limits, template limits, memory entry limits
- Upgrade prompts: return 402 with `plan_limit` error code when limit hit

**Frontend**
- Memory management overlay: global context form, people CRUD, projects CRUD (accessible from Settings tab → "Edit Memory →")
- Settings tab — Memory section: shows count of people/projects saved, "Edit Memory →" link
- Settings tab — Privacy & Data section: retention window, export, delete
- Onboarding flow (4-step: welcome, context, connect group, done) — shown on first visit to /hub before any groups connected
- Plan limit UI: show current usage vs limit inside each relevant tab, upgrade CTA when approaching limit
- All empty states finalized across all tabs
- All loading states finalized
- All error states finalized

**Testing**
- Add memory entries, verify they appear in extraction prompts (check batch logs)
- Verify extraction output improves with context (compare with/without memory)
- Plan limits: Free user cannot add 4th group, sees upgrade prompt
- Onboarding: complete flow for new user end-to-end
- All settings save and persist correctly

**Pre-Launch Checklist**
- [ ] Telegram webhook: tested with 5+ real groups
- [ ] Extraction: 90%+ precision on test corpus
- [ ] Privacy: export, delete, pause all tested end-to-end
- [ ] Cost monitoring: per-user daily cost logged and alertable
- [ ] Rate limits: Telegram API rate limits respected
- [ ] Encryption: content fields encrypted at rest
- [ ] Consent: cannot begin observation without confirmed consent
- [ ] Plan gating: Free user limited to 2 groups

---

## V1.5 IMPLEMENTATION — INTELLIGENCE LAYER

*Begin after V1 launch and first retention data (approximately weeks 12–18)*

---

### SPRINT 7 — Custom Bot Management + Knowledge Cards + @Mentions (Weeks 12–14)

**Goal:** Custom bots connectable to Assistant Hub. Knowledge cards working per-bot. @mention replies functional.

**Backend — Custom Bot Management**
- Endpoint: connect existing Module A custom bot to Assistant Hub
  - Receives `custom_bot_id` from Module A, creates `bot_identities` record (type: custom)
  - Auto-creates `assistant_bot_settings` record with all NULLs (full inheritance from official)
- Endpoint: disconnect custom bot from Assistant Hub (does not delete Module A bot)
- Settings resolver: confirm inheritance works correctly for custom bots
- Duplicate group warning: if user connects same Telegram group to two bots, return warning response (allow but warn)

**Backend — Knowledge Cards**
- Knowledge cards CRUD (bot-scoped, plan-gated per bot)
- Keyword matching retrieval function (filters by `bot_id`)
- @mention detection: identifies which bot was mentioned (different token = different bot)
- Query classifier (rule-based, no AI)
- Answer formatter: inject matched card content into GPT-4o-mini prompt
- Reply formatter: single message, ≤300 characters
- Active Mode per-group toggle enforcement
- Rate limiter: 5 bot replies per group per hour (Redis counter keyed by `bot_id:group_id`)
- Unknown query response: "I don't have that information. Add it to your knowledge base."
- Data queries (tasks, meetings, reminders): direct DB query filtered by `bot_id`

**Frontend — Custom Bot Management**
- Context switcher: custom bots now appear as active options (not "coming soon")
- Custom bot connection flow: select from existing Module A bots list
- Per-bot settings page: inheritance indicators on all inheritable fields
  - "↩ Inherited from Telegizer Official" label with "[Override]" link
  - "[Reset to inherited]" link after override is set
- Custom bot disconnect confirmation modal

**Frontend — Knowledge Cards**
- Knowledge tab (`/hub/bots/:bot_id/knowledge`): cards list, create, edit, delete (bot-context aware)
- Card limit usage indicator per bot
- Active Mode toggle in per-group settings (with explanation)
- Plan upgrade prompt when card limit reached

**Testing**
- Connect custom bot: appears in context switcher, inherits official bot settings
- Override one setting on custom bot: only that setting overridden, others still inherited
- Disconnect custom bot: removed from switcher, Module A bot unaffected
- Same Telegram group connected to two bots: warning shown, both allowed
- Knowledge card created under official bot: NOT visible when custom bot context active
- Knowledge card created under custom bot: visible only in that bot context
- @mention in group connected to custom bot: uses custom bot's knowledge cards
- Inheritance: custom bot with NULL sensitivity uses official bot's sensitivity value

---

### SPRINT 8 — Automations & Memory Suggestions (Weeks 15–18)

**Goal:** Pre-built automations toggle-able, memory suggestions delivered via digest.

**Backend**
- `system_automations` table seeded with pre-built automation definitions
- `bot_automation_settings` table: store per-bot user toggle state
- Automation engine: runs after each extraction batch
  - meeting_reminder: create reminder at meeting_time - 60 minutes
  - deadline_alert: DM immediately when task with due_date extracted
  - follow_up_reminder: create reminder at now + 2 days when follow-up detected
- Memory suggestion detector: name frequency analysis per batch
  - Threshold: name appears in extraction context 3+ times
  - Check against existing `memory_people` — skip if already known
  - Write to `memory_suggestions` table
- Suggestion delivery: bundle with daily digest (not immediate DM)
- Suggestion resolution: approve writes to `memory_people`, skip updates status

**Frontend**
- Automation tab (`/hub/official/automation`): toggle list, clean explanation per automation
- Memory suggestion cards in inbox (new item type: suggestion)
- Suggestion card: name + optional role field + approve/skip/block buttons

**Testing**
- Meeting extracted with scheduled_at → reminder created at correct time
- Task with due_date extracted → immediate DM when automation enabled
- Name appearing 3+ times in extractions → suggestion queued (not immediate)
- Suggestion delivered in next digest
- Approve suggestion → person added to memory_people
- Skip suggestion → status = skipped, never shown again for same name
- Automation disabled → no action taken even if trigger event occurs

---

## SUCCESS CRITERIA BY PHASE

### V1 Success Criteria (measure after 30 days live)

| Metric | Target |
|---|---|
| Extraction precision (user feedback: "this was wrong") | < 10% of items reported as wrong |
| Daily active users / Monthly active users (DAU/MAU) | > 40% |
| Users who complete onboarding and connect first group | > 70% |
| Users who return to inbox 3+ days in first week | > 35% |
| Cost per user per month (AI + infrastructure) | < $5 for Free, < $15 for Pro |

### V1.5 Success Criteria (measure after 60 days post-V1.5)

| Metric | Target |
|---|---|
| Knowledge cards created per active user | Average > 3 |
| @mention queries answered correctly | > 85% |
| Automation toggled on by % of users | > 50% for meeting_reminder |
| Memory suggestions approved (not skipped) | > 40% |

---

## TECHNICAL DEPENDENCIES

| Dependency | Purpose | When Needed |
|---|---|---|
| OpenAI API (gpt-4o-mini) | Extraction | Sprint 3 |
| OpenAI API (gpt-4o) | On-demand summaries | Sprint 4 |
| Redis (BullMQ) | Message buffer, job queue | Sprint 1 |
| PostgreSQL | Primary database | Sprint 1 |
| Telegram Bot API | Webhook, DM delivery | Sprint 1 |
| chrono-node (or similar) | Date/time pre-parsing | Sprint 3 |
| AES-256-GCM encryption | Content field encryption | Sprint 2 |
| pgvector | Semantic search | V2 only — do not install in V1 |

---

## WHAT IS NOT BUILT IN THIS PLAN

These items are explicitly excluded from V1 and V1.5 scope:

- Custom automation builder of any kind
- Visual workflow editor
- Webhook outputs / Zapier integration
- Google Calendar sync (V2)
- File uploads to knowledge base (V2)
- Embeddings or vector search (V2, conditional)
- Team/multi-user accounts (V3)
- Relationship memory pattern analysis (V3)
- Mobile companion app (V3)
- WhatsApp or Gmail integration (never in current planning horizon)
- Any auto-reply that is not @mention triggered
- Public group assistant behavior (Module A handles public groups)
