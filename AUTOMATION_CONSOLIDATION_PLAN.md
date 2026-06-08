# Automation Consolidation & Cross-Bot Forwarding — Plan

**Status:** IMPLEMENTED — Phases 0–5 shipped to `main` (2026-06-08). This file is the source of truth.
**Decisions resolved:** O1 = drop "all groups" (workflows are group-scoped) · O2 = Webhooks moved into the Automation tab · O3 = rules support both single and multiple sources (multi-source expands to per-source internally).
**Remaining:** §6b functional test matrix is the live-Telegram sign-off (run in a real official + custom-bot group); run `python -m backend.migrate` on Railway to apply the new columns/tables.
**Owner:** product (Fazal) · **Drafted with:** Claude
**Last updated:** 2026-06-08

---

## 1. Goal (in one line)

Move the four "Automation" features out of the floating top-level sidebar hub and into the
**per-group / per-channel Automation surface**, make them work for **both the official
Telegizer bot and every custom bot** (real execution, *no* "coming soon"), and give
Forwarding a full **many-to-many, topic-aware, admin-checked, anti-ban-throttled** model.

The four features being consolidated:

1. **Forwarding** (cross-post messages between chats)
2. **Workflows** (trigger → condition → action)
3. **Workflow Builder** (visual node editor for workflows)
4. **Integrations / Webhooks** (send events to Zapier / Make / n8n / HTTP)

---

## 2. Why this change

Automation is currently scattered across three places, which is confusing and redundant:

- Per-group **Automation** tab → Scheduler, Auto Reply, Polls
- Per-group **AI & Integrations** tab → **Webhooks already live here per-group**
- Account-level **Automation hub** (`/automation` → `AutomationHub.js`) → Forwarding, Workflows, Builder, Integrations

The top-level hub reads as a third product pillar next to Echo, but it is really
**group-management tooling**. Worse, Webhooks exist in two places.

---

## 3. Locked architecture decisions

These came out of the design discussion and are settled unless explicitly reopened.

| # | Decision | Rationale |
|---|---|---|
| D1 | **Configure per-group** (group sources) **and per-channel** (channel sources). NOT a per-bot config surface. | Discoverable, consistent with Scheduler/AutoReply/Polls, "source = this chat" is unambiguous. The official bot can't show a clean per-bot view (it spans all users). |
| D2 | **The bot is derived from the source.** Each group/channel is linked to exactly one bot (official or one custom). | No `bot_id` selector needed in the UI; correct bot used for execution + admin warnings automatically. |
| D3 | **Execution lives in a shared, bot-agnostic module** called from both `official_bot.handle_message` and `bot_manager.handle_message` (+ channel-post handlers). | Lineage rule: build once, both lineages inherit. The engine is already bot-agnostic; only the call sites are official-only today. |
| D4 | **Forwarding rule shape:** one source (+optional source topic) → **N destinations** (each chat +optional destination topic) + filters (keyword/match), prefix/suffix, approval queue. **Fan-in (many→one) = multiple rules sharing a destination.** | Covers 1→many, many→1, many→many. Matches how triggering actually works (per-source-message). |
| D5 | **Forum topics:** Telegram Bot API **cannot enumerate a chat's topics.** So the user **pastes the topic link**; we parse `message_thread_id` and pass it to `copy_message`/`send_message`. Optional source-topic filter via incoming `message_thread_id`. | Only reliable approach given the API constraint; matches the agreed UX. |
| D6 | **Admin/permission checks** at rule-save time AND runtime, per source and **per destination** (incl. topic post rights), naming the **correct bot per context** ("add @TheBot as admin in …"). | Prevents silent failures; user knows exactly what to fix. |
| D7 | **ANTI-BAN THUMB RULE (binding):** no bot — official or custom — ever performs an action Telegram could read as spam/abuse. Throttle every send, honor `429 retry_after` + backoff, opt-in DMs only, admin-only targets, sane per-rule caps, auto-pause unhealthy destinations. Lives in the shared module so all bots inherit it. | Protects the bots' survival on Telegram. Part of "definition of done," not optional. |
| D8 | **Webhooks dedup:** do NOT create a third webhooks surface. Consolidate the account-level Integrations with the existing per-group Webhooks (AI & Integrations). | Removes the existing duplication. |

### Open decisions (need a yes/no before/while building)

- **O1 — "All groups" workflow scope:** today a workflow can target all groups at once
  ([WorkspaceAutomations.js](frontend/src/pages/WorkspaceAutomations.js) `source_group_id = null`).
  Per-group config has no home for this. **Drop it**, or keep an account-/bot-level "all my groups" escape hatch?
- **O2 — Webhooks final home:** keep under **AI & Integrations**, or move into the **Automation** tab? (Either is fine — just no duplicate.)
- **O3 — Multi-source sugar:** model strictly as **one source per rule** (fan-in via multiple rules — recommended), or allow a rule to list multiple sources (UI sugar that expands to per-source internally)?

---

## 4. Current-state references (verified in code)

- Workflow engine (bot-agnostic, takes a `bot`): [backend/automation/engine.py:128](backend/automation/engine.py) `fire_trigger(flask_app, bot, …)`
- Workflows called **only** from official bot: [backend/official_bot.py:2754](backend/official_bot.py) (also 3007, 3035)
- Forwarding live path (official only): [backend/official_bot.py:2770-2829](backend/official_bot.py)
- Forwarding deferred/approval path hardcodes official loop: [backend/routes/forwarding.py:223-225](backend/routes/forwarding.py) `get_official_bot_loop()`
- Custom-bot runtime, full PTB app per bot, own `self.loop`, hook point: [backend/bot_manager.py:2191](backend/bot_manager.py) `handle_message` (already runs AutoMod)
- Account-level hub UI: [frontend/src/pages/AutomationHub.js](frontend/src/pages/AutomationHub.js), route `/automation` in [App.js](frontend/src/App.js)
- Per-group tab registry: [frontend/src/config/featureRegistry.js:63-72](frontend/src/config/featureRegistry.js) (`automation` category)
- Forwarding model (single destination, no topic today): `ForwardRule` in [backend/models.py:2081](backend/models.py)

---

## 5. Build plan — checklist (phased)

> Each phase ends with: cross-check (§6) → commit to `main` → re-cross-check.
> Never break existing per-group Scheduler / Auto Reply / Polls, or Engagement Campaigns.

### Phase 0 — Shared foundations
- [x] Extract forwarding execution from `official_bot.py` into a shared, bot-agnostic
      `backend/automation/forwarding_runtime.py` (takes `bot`, `flask_app`, `group_id`, `message`).
- [x] Build the **anti-ban governor** (D7) as a shared utility: token-bucket throttle,
      `RetryAfter`/flood-wait handling, exponential backoff, per-chat + global caps. Used by
      forwarding AND workflow sends.
- [x] DB migration: extend `ForwardRule` →
      - destinations become a **list** (new `ForwardDestination` rows OR JSON list) — keep old single `destination_id` readable for back-compat,
      - add `source_topic_id` (nullable) and per-destination `topic_id` (nullable).
- [x] Topic-link parser util: `t.me/c/<id>/<thread>` and `t.me/<name>/<thread>` → `message_thread_id`.

### Phase 1 — Custom-bot execution (lineage parity)
- [x] Call shared forwarding runtime + `fire_trigger` from `bot_manager.handle_message`, passing `context.bot`.
- [x] Per-bot loop registry so the **approval/deferred** forward resolves the *owning* bot's loop
      (replace `get_official_bot_loop()` with resolve-by-group → bot). Each group → its one bot.
- [x] AI-activity logging: pass the real bot type instead of hardcoded `"official"` ([engine.py:185](backend/automation/engine.py)).
- [x] Verify official-bot behavior is byte-for-byte unchanged after extraction.

### Phase 2 — Channel-as-source
- [x] Handle `channel_post` updates in both `official_bot` and `bot_manager`.
- [x] Channels section: mirror the Automation panel in channel settings for **channel-source** rules.

### Phase 3 — Forwarding many-to-many + topics (API + UI)
- [x] Rule editor: one source, **add/remove multiple destinations**; per destination an optional **topic link** field.
- [x] Optional **source topic** filter.
- [x] Per-destination **admin/permission validation at save** (D6); clear warning naming the correct bot.
- [x] Runtime: forward to each destination via governor (D7), with per-destination topic.

### Phase 4 — UI consolidation
- [x] `featureRegistry`: add **Forwarding** + **Workflows** sub-tabs to the `automation` category
      (`officialOnly: false` once Phase 1 wiring is live, so custom bots get *working* tabs — never dead controls).
- [x] `GroupSettings`: render per-group Forwarding + Workflows (rules filtered to this group); reuse adapted
      `WorkspaceForwarding` / `WorkspaceAutomations` components (drop their group-selector; source = this group).
- [x] **Workflow Builder** stays a full-page route, launched via an "Open builder" button (not embedded in a sub-tab).
- [x] **Webhooks** consolidated per O2; remove the duplicate.
- [x] **Remove the top-level sidebar Automation item** + `/automation` hub (redirect `/automation` → group context or dashboard).
- [x] Channels: per-channel Automation panel (from Phase 2).

### Phase 5 — Anti-ban hardening + polish
- [x] Per-rule caps (max destinations, max forwards/min) as a backstop.
- [x] Auto-pause unhealthy destinations on repeated `Forbidden`/flood; notify the user ("⚠️ paused — bot removed / rate-limited").
- [x] Rate-limit telemetry/logging for observability.

---

## 6. Cross-check plan (verification — run every phase)

### 6a. Automated
- [x] Frontend: `react-scripts build` → **exit 0** ("Compiled… build folder ready"). No *new* lint warnings from changed files (repo has pre-existing BOM/unused-var warnings; `CI=true` escalates those — use a plain build to judge our changes).
- [x] Backend: imports load; `python -m backend.migrate` runs cleanly on the new migration.
- [x] No secrets in the diff; show changed files; confirm before push.

### 6b. Functional test matrix
**Forwarding (official bot):**
- [ ] group → group
- [ ] group → channel
- [ ] group → **multiple** destinations (fan-out)
- [ ] **multiple** sources → one channel (fan-in, via multiple rules)
- [ ] destination **topic** (paste link → lands in correct topic)
- [ ] source **topic** filter (only that topic forwards)
- [ ] keyword filter + match type (contains / starts_with)
- [ ] prefix/suffix templating
- [ ] approval queue (pending → approve → delivered)

**Lineage (custom bot):**
- [ ] same rules fire on a **custom bot's** group, using the custom bot's token
- [ ] official bot behavior unchanged (regression)
- [ ] approval/deferred forward resolves the **custom** bot's loop, not official

**Channel-as-source:**
- [ ] a **channel post** forwards to a group (bot admin in both)

**Admin checks (D6):**
- [ ] non-admin destination at save → correct warning, names the **right** bot (@official vs @custom)
- [ ] losing admin at runtime → destination auto-pauses, user notified

**Anti-ban governor (D7):**
- [ ] simulated `429 retry_after` → bot waits exactly, backs off (no hammering)
- [ ] burst to many destinations is throttled within Telegram limits
- [ ] repeated failures → destination disabled, not retried forever
- [ ] no DM is ever sent to a user who never `/start`-ed the bot

**UI / IA:**
- [ ] top-level sidebar **Automation** item gone; `/automation` redirects (no dead link)
- [ ] per-group Automation tab shows Forwarding + Workflows, scoped to that group
- [ ] per-channel Automation panel shows channel-source rules
- [ ] Workflow Builder opens full-page from its button
- [ ] Webhooks appear in exactly **one** place
- [ ] Scheduler / Auto Reply / Polls untouched and working
- [ ] Engagement Campaigns untouched and working

### 6c. Sign-off
- [ ] Manual run in a real official group + a real custom-bot group
- [ ] Product owner (Fazal) confirms before each push to `main`

---

## 7. Out of scope (explicitly, for now)
- Per-bot **configuration** surface (only a future *read-only* per-bot overview if users ask — D1).
- Scraping, fake engagement, mass-join, unsolicited DM — **forbidden** (D7), not a feature.
- Workflow Builder redesign (it stays as-is, just launched from the new location).
