# Telegizer Assistant — Architecture & Product Audit Report

> **Date:** 2026-05-04  
> **Scope:** Full platform review through an assistant-first lens  
> **Primary goal:** Make Telegizer Assistant the strongest possible core product — the daily-use AI operations assistant for Telegram admins and community managers.

---

## Table of Contents
1. [What Is Strong Already](#a-what-is-strong-already)
2. [Current Gaps Hurting Assistant Potential](#b-current-gaps)
3. [High-Impact Improvements](#c-high-impact-improvements)
4. [Strategic Ideas](#d-strategic-ideas)
5. [Recommended Build Phases](#e-build-phases)
6. [Technical Refactors](#f-technical-refactors)
7. [Phase Execution Tracker](#phase-execution-tracker)

---

## A. What Is Strong Already

| Area | Detail |
|---|---|
| **Multi-turn state machine** | `AssistantConversationState` (pending_intent + collected_data + awaiting_field + expires_at) is the right primitive. Most competitors use simple webhook→response loops. |
| **Dual-surface delivery** | Web LiveChat and Telegram Bot DM share the same `process_message()` backend. Architecturally correct and rare. |
| **Multi-provider AI routing** | Gemini / Anthropic / OpenAI with per-workspace keys, quota tracking, and fallback is production-grade. |
| **3-tier intent routing** | keyword pre-filter → AI parsing → keyword fallback chain. Fast, reliable, never fully breaks. |
| **All data models exist** | Meeting, Task, Note, WorkspaceReminder, TelegramGroup, MessageBuffer, DigestLog, AutoReplyLog — raw data is there. |
| **Event dispatcher** | `fire_event()` for `meeting.created`, `resource.attached`, `group.issue.detected` — hooks exist, just not flowing back into the assistant yet. |

---

## B. Current Gaps Hurting Assistant Potential

### B1 — No Memory (Critical)
`AssistantConversationState` tracks only the *current* pending intent. Every session starts cold. `BotDMMessage` history is logged but never read back into context.

### B2 — No AssistantContextService (Critical)
Every handler builds its own context inline. No unified, cached, pre-built user context object. Adding a new data source requires touching every handler individually.

### B3 — MessageBuffer Is a Dead End
Raw 300-message window dump into AI prompt. Caps at ~12,000 chars, has no semantic structure, cannot be searched, reprocesses same messages on every query.

### B4 — Assistant Is a Widget, Not a Product
Buried as a collapsible card at the bottom of the AssistantHub page. Users must navigate to a specific page and scroll to find it.

### B5 — No Proactive Intelligence
100% reactive. No scheduled briefings, no meeting alerts, no group health alerts, no inactive group nudges.

### B6 — No Semantic Search / RAG
Users can list notes but cannot search them. No embeddings, no vector store. Notes and messages become dead storage as volume grows.

### B7 — Assistant Cannot Take Platform Actions
Can create meetings/notes/tasks/reminders. Cannot trigger digests, change AutoMod settings, post announcements, or manage automations.

### B8 — No Feedback Loop
No thumbs up/down, no intent accuracy tracking, no way to measure assistant quality.

### B9 — Telegram Is a Second-Class Surface
Requires users to own a separate AssistantBot (Pro+). The main @telegizer_bot doesn't serve as a personal DM assistant. Power users on Telegram get a degraded experience.

### B10 — WorkspaceKnowledgeDocument Is Disconnected
Model exists but is never injected into assistant context. Users upload docs but assistant cannot reference them.

---

## C. High-Impact Improvements

### C1 — AssistantContextService
Single service called before every AI interaction returning a structured workspace snapshot injected into all AI prompts.

### C2 — Conversation Short-Term Memory
Read last 8 `BotDMMessage` exchanges and include as conversation history in every AI system prompt.

### C3 — GroupSignalExtractor Pipeline
Replace raw MessageBuffer dumps with pre-computed `GroupDailySignal` records (spam_score, conflict_score, top_topics, health_status, ai_summary). Updated every 2 hours per group.

### C4 — Proactive Intelligence Engine
Scheduler-driven: reminder delivery, meeting pre-alerts, daily briefing, group health alerts, inactive group nudges.

### C5 — Assistant Action Surface
Give assistant write access: trigger_digest, post_announcement, update_automod, create_auto_reply, enable_feature. Assistant becomes a platform operator, not just an advisor.

### C6 — Semantic Search Over Notes / Messages
pgvector embeddings on Note, WorkspaceKnowledgeDocument, MessageBuffer chunks. Enables "find my notes about X" and "search messages for Y".

---

## D. Strategic Ideas

### D1 — Persistent Right Sidebar (Co-Pilot Pattern)
Replace buried chat widget with a permanent 340px right sidebar visible on every page. Collapsible to icon strip. Mobile: floating button → full-screen drawer.

```
┌─────────────────────────────────────────────────────────────────┐
│  Telegizer                                    [user] [settings] │
├──────────────┬──────────────────────────────┬───────────────────┤
│  NAV         │   MAIN CONTENT AREA          │  ASSISTANT        │
│              │                              │  SIDEBAR (340px)  │
│  Dashboard   │   Groups / Analytics /       │  ┌─────────────┐  │
│  Groups      │   Meetings / Notes /         │  │ Briefing    │  │
│  Analytics   │   AutoMod / Digests          │  │ Today...    │  │
│  AutoMod     │                              │  └─────────────┘  │
│  Digests     │                              │  [conversation]   │
│  Tasks       │                              │  [suggestions]    │
│  Notes       │                              │  [input bar]      │
│  Settings    │                              │                   │
└──────────────┴──────────────────────────────┴───────────────────┘
```

### D2 — Assistant Modes as Product Tiers

| Mode | Capability | Plan |
|---|---|---|
| Schedule Manager | Meetings, reminders, tasks | Free |
| Notes & Knowledge | Notes, links, semantic search | Free |
| Group Analyst | Group health reports, issues | Starter |
| Proactive Briefings | Daily briefing, meeting alerts | Pro |
| Platform Operator | Control AutoMod, digests, announcements | Pro |
| Multi-Group Commander | Broadcast, cross-group ops | Enterprise |

### D3 — "Teach the Assistant" via Knowledge Base
Users upload SOPs, community rules, content calendars. Assistant references this in every moderation recommendation and group suggestion. High switching cost once users have trained it.

### D4 — Team / Multi-Admin Assistant (Enterprise)
Shared assistant workspace where multiple admins see the same conversation history and context. Collaborative task assignment.

### D5 — Assistant-Generated Playbooks
After 30+ days, surface behavioral insights: "Your most active groups are Mon–Thu 6–9 PM — want me to schedule digests then?" Extremely sticky.

### D6 — Telegizer Assistant API / Zapier Integration
Expose assistant as API endpoint. External tools (Zapier, Make.com, webhooks) can trigger assistant actions. Turns assistant into a workflow automation hub.

---

## E. Build Phases

### Ideal Placement Decision
**Persistent Right Sidebar — the Co-Pilot Pattern.** Not a page, not a widget, not a modal. A permanent panel on the right side of every screen. Always visible, always ready.

---

## Phase Execution Tracker

---

### Phase 1 — Foundation (Backend Intelligence Core)
**Goal:** Make the assistant smart before making it more visible. Fix data access layer first.  
**Duration:** ~2 weeks  
**Status:** 🔄 In Progress

#### Tasks

| # | Task | File(s) | Status |
|---|---|---|---|
| 1.1 | Build `AssistantContextService` | `backend/assistant/context_service.py` | ⬜ Pending |
| 1.2 | Inject conversation short-term memory into `process_message()` | `backend/assistant/personal_assistant.py` | ⬜ Pending |
| 1.3 | Audit + fix proactive reminder delivery in scheduler | `backend/scheduler.py` | ⬜ Pending |
| 1.4 | Add meeting pre-alert scheduler task | `backend/scheduler.py` | ⬜ Pending |

#### AssistantContext Structure
```python
@dataclass
class AssistantContext:
    user:                dict          # plan, timezone, telegram_user_id, joined_days_ago
    groups:              list[dict]    # id, title, member_count, is_active, last_message_at
    upcoming_meetings:   list[dict]    # next 5, with notes/reminders
    upcoming_reminders:  list[dict]    # next 5 undelivered
    pending_tasks:       list[dict]    # top 10 by created_at
    recent_notes:        list[dict]    # last 5, with tags
    recent_conversation: list[dict]    # last 8 BotDMMessage turns
    knowledge_docs:      list[dict]    # titles + first 200 chars
    platform_today:      dict          # messages_received, automations_fired, digests_sent
    group_alerts:        list[dict]    # GroupDailySignal issues from last 24h (Phase 3+)
```

#### Deliverable
Assistant knows who the user is, what's on their plate, and what they said recently. Reminders and meeting alerts reliably arrive. Context is consistent across all intents.

---

### Phase 2 — UI Repositioning (Persistent Sidebar)
**Goal:** Move assistant from buried widget to permanent co-pilot sidebar.  
**Duration:** ~1.5 weeks  
**Status:** ⬜ Pending

#### Tasks

| # | Task | File(s) | Status |
|---|---|---|---|
| 2.1 | Create `AppLayout` 3-column layout with sidebar slot | `frontend/src/layouts/AppLayout.js` | ⬜ Pending |
| 2.2 | Build `AssistantSidebar` persistent component | `frontend/src/components/AssistantSidebar.js` | ⬜ Pending |
| 2.3 | Add `POST /api/assistant/briefing` endpoint | `backend/routes/assistant.py` + `context_service.py` | ⬜ Pending |
| 2.4 | Mobile floating button + full-screen drawer | `AssistantSidebar.js` (responsive) | ⬜ Pending |
| 2.5 | Update nav, demote AssistantHub to config page | `frontend/src/` nav files | ⬜ Pending |

#### AssistantSidebar Component Tree
```
AssistantSidebar
  ├── SidebarHeader         (title, collapse button, Telegram link status)
  ├── BriefingCard          (today's briefing — loads on mount, refresh button)
  ├── ConversationHistory   (full scrollable message thread, persists across pages)
  ├── SuggestionChips       (contextual, changes based on last intent)
  └── InputBar              (text field + send button, always at bottom)
```

#### Deliverable
User opens Telegizer → immediately sees assistant greeting on the right. Every page has the assistant visible. Feels like a co-pilot, not a feature.

---

### Phase 3 — Proactive Intelligence Engine
**Goal:** Assistant starts initiating conversations, not just responding.  
**Duration:** ~2.5 weeks  
**Status:** ⬜ Pending

#### Tasks

| # | Task | File(s) | Status |
|---|---|---|---|
| 3.1 | Create `GroupDailySignal` model + migration | `backend/models.py` + migration | ⬜ Pending |
| 3.2 | Build `GroupSignalExtractor` scheduler pipeline | `backend/assistant/group_signal_extractor.py` | ⬜ Pending |
| 3.3 | Build `send_daily_briefings()` scheduler task | `backend/scheduler.py` | ⬜ Pending |
| 3.4 | Build `check_group_health()` proactive alert task | `backend/scheduler.py` | ⬜ Pending |
| 3.5 | Build `check_inactive_groups()` nudge task | `backend/scheduler.py` | ⬜ Pending |

#### GroupDailySignal Model
```python
class GroupDailySignal(db.Model):
    id, telegram_group_id (FK), date (Date)
    message_count (int), active_members (int)
    spam_score (float 0–10), conflict_score (float 0–10)
    questions_unanswered (int), top_topics (JSON list)
    sentiment (positive/neutral/negative)
    health_status (healthy/watch/critical)
    ai_summary (text ≤500 chars)
    created_at
```

#### Daily Briefing Format
```
Good morning [Name]! Here's your day:

📅 Meetings today: Team Sync at 3 PM, Investor Call at 5 PM
🔔 3 reminders due today
✅ 5 pending tasks
⚠️ Group alerts: Crypto Hub — spam spike detected (score 7.2)

Reply to me anytime to manage any of these.
```

#### Deliverable
Assistant contacts users proactively. Users have reason to open Telegram even without initiating. Engagement increases significantly.

---

### Phase 4 — Assistant Action Surface (Platform Operator)
**Goal:** Assistant can control the platform, not just read from it.  
**Duration:** ~2 weeks  
**Status:** ⬜ Pending

#### Tasks

| # | Task | File(s) | Status |
|---|---|---|---|
| 4.1 | Build `actions.py` action framework + registry | `backend/assistant/actions.py` | ⬜ Pending |
| 4.2 | Add platform operator intents to `process_message()` | `backend/assistant/personal_assistant.py` | ⬜ Pending |
| 4.3 | Add `group_picker` step to state machine | `backend/assistant/personal_assistant.py` | ⬜ Pending |

#### Action Registry
```python
ACTIONS = {
    "trigger_digest":     _action_trigger_digest,
    "post_announcement":  _action_post_announcement,
    "update_automod":     _action_update_automod,
    "enable_digest":      _action_enable_digest,
    "disable_digest":     _action_disable_digest,
    "create_auto_reply":  _action_create_auto_reply,
    "list_auto_replies":  _action_list_auto_replies,
    "get_group_stats":    _action_get_group_stats,
}
```

#### New Intents
- `trigger_digest` — "Send the digest for my Marketing group"
- `post_announcement` — "Post this message to my Gaming group"
- `update_automod` — "Enable strict mode for Crypto Hub"
- `list_auto_replies` — "What auto-replies do I have?"
- `create_auto_reply` — "When someone says 'rules', reply with our rules link"
- `get_group_stats` — "How is my Marketing group doing this week?"

#### Deliverable
User can say "send digest to my gaming group" or "enable anti-spam on Crypto Hub" and assistant does it. Key product differentiator — no other Telegram tool has a conversational ops interface.

---

### Phase 5 — Semantic Search & Knowledge Base
**Goal:** Notes, messages, and documents become searchable — not dead storage.  
**Duration:** ~2 weeks  
**Status:** ⬜ Pending

#### Tasks

| # | Task | File(s) | Status |
|---|---|---|---|
| 5.1 | Add pgvector + embedding columns via migration | `backend/models.py` + migration | ⬜ Pending |
| 5.2 | Build `embeddings.py` service + `semantic_search()` | `backend/assistant/embeddings.py` | ⬜ Pending |
| 5.3 | Add `search_notes` / `summarize_notes` intents | `backend/assistant/personal_assistant.py` | ⬜ Pending |

#### Embedding Targets
- `Note.embedding` — vector(768), set on creation/update
- `WorkspaceKnowledgeDocument.embedding` — vector(768), set on upload
- New `MessageChunk` model — chunked MessageBuffer for group message search

#### New Intents
- `search_notes` — "Find my notes about the API integration"
- `summarize_notes` — "Summarize everything I saved this week"
- `search_messages` — "What did members say about pricing?"

#### Deliverable
Notes and knowledge base become genuinely useful. Users save things knowing they can retrieve them intelligently.

---

### Phase 6 — Technical Refactors & Scale
**Goal:** Prepare for real user load without performance degradation.  
**Duration:** ~2 weeks  
**Status:** ⬜ Pending

#### Tasks

| # | Task | File(s) | Status |
|---|---|---|---|
| 6.1 | Split `personal_assistant.py` into handler modules | `backend/assistant/handlers/` | ⬜ Pending |
| 6.2 | Migrate AI calls to async `httpx` | `backend/assistant/` | ⬜ Pending |
| 6.3 | Add `session_id` + `feedback` columns to `BotDMMessage` | `backend/models.py` + migration | ⬜ Pending |
| 6.4 | Add `MessageBuffer` TTL cleanup scheduler task | `backend/scheduler.py` | ⬜ Pending |
| 6.5 | Add per-intent rate limits | `backend/routes/assistant.py` | ⬜ Pending |

#### Target Module Structure (Post-Refactor)
```
backend/assistant/
  ├── intent_router.py          # keyword + AI intent detection only
  ├── context_service.py        # AssistantContextService
  ├── state_machine.py          # _get/_save/_clear_state + _handle_continue_state
  ├── embeddings.py             # semantic search
  ├── actions.py                # platform operator actions
  ├── group_signal_extractor.py # hourly group intelligence pipeline
  ├── proactive.py              # briefings + alerts + nudges
  ├── handlers/
  │   ├── schedule.py           # meeting + reminder intents
  │   ├── notes.py              # note + link + task intents
  │   ├── intelligence.py       # group_query + upcoming_schedule
  │   ├── actions.py            # platform operator intents
  │   └── general.py            # general AI response
  └── personal_assistant.py     # thin coordinator (calls above modules)
```

#### BotDMMessage Schema Update
Add columns (non-breaking migration):
- `session_id` UUID nullable — groups related turns
- `intent_confidence` float nullable — routing confidence score
- `feedback` smallint nullable — -1 / 0 / 1 (thumbs down / none / up)

#### Per-Intent Rate Limits
```python
INTENT_RATE_LIMITS = {
    "group_query":       5,   # AI-heavy
    "general":          10,   # AI-heavy
    "schedule_meeting":  20,  # multi-step
    "upcoming_schedule": 30,  # DB-only
    "save_note":         60,  # DB-only
    "list_meetings":     60,  # DB-only
}
```

---

## Summary Scorecard

| Area | Current State | Target State (Post All Phases) |
|---|---|---|
| Context awareness | Ad-hoc per-handler | Unified AssistantContextService |
| Memory | None (stateless) | 8-turn short-term memory |
| Proactive intelligence | None | Daily briefing + event alerts |
| Group intelligence | Raw message dump → AI | Pre-computed GroupDailySignal |
| Action surface | CRUD only | Full platform operator |
| Semantic search | None | pgvector RAG on notes + messages |
| UI centrality | Buried widget | Persistent sidebar — primary UX |
| Telegram parity | Second-class | Full feature parity + proactive DMs |
| Feedback loop | None | Intent confidence + user feedback |
| Scalability | Sync blocking AI calls | Async + Celery queue |

---

## Timeline Overview

| Phase | Name | Duration | Key Deliverable |
|---|---|---|---|
| **1** | Foundation | ~2 weeks | Smart context, memory, reliable reminders |
| **2** | UI Repositioning | ~1.5 weeks | Persistent sidebar, always-visible assistant |
| **3** | Proactive Intelligence | ~2.5 weeks | Daily briefing, group alerts, nudges |
| **4** | Action Surface | ~2 weeks | Control platform via chat |
| **5** | Semantic Search | ~2 weeks | Searchable notes, knowledge base RAG |
| **6** | Refactors & Scale | ~2 weeks | Async, split files, schema cleanup |
| **Total** | | **~12 weeks** | Genuinely powerful, sticky AI ops assistant |

---

*Report generated: 2026-05-04 — Updated as phases complete.*
