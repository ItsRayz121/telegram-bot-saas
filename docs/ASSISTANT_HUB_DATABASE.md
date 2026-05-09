# ASSISTANT HUB — DATABASE ARCHITECTURE
**Version:** 3.0  
**Status:** Final — Ready for Sprint 1  
**Database:** PostgreSQL (primary) + Redis (ephemeral buffer)  
**Change from v2.0:** Lazy record creation — no records pre-created at deploy. `pause_reason` added to `connected_groups`. Plan names aligned to real Telegizer plans (Free/Pro/Enterprise). Shared @telegizer_bot token documented. Public group warning field added.

---

## 1. DESIGN PRINCIPLES

- Raw conversation content is never stored permanently
- Extracted intelligence (tasks, reminders, decisions) is stored until user deletes it
- All content fields containing user data are encrypted at rest (AES-256)
- Every extracted item carries `bot_id` + `source_group_id` for full traceability
- Memory is always user-authored or user-approved — never auto-written
- Global memory (people, projects) is user-scoped and shared across all bots
- Settings are bot-scoped with inheritance from official bot to custom bots
- Schema is append-only where possible; hard deletes only on explicit user request

---

## 2. THREE-TIER OWNERSHIP MODEL

```
USER LEVEL (user_id)
  - Account, billing, plan
  - Global memory (shared across all bots)
  - Unified inbox (aggregated view)
  - Export / delete controls

BOT LEVEL (bot_id → user_id)
  - Bot identity (display name, Telegram token)
  - AI personality, extraction sensitivity, language
  - Digest settings, notification preferences
  - Templates (bot-specific)
  - Knowledge cards (bot-specific)
  - Automation toggle state (inheritable)
  - Connected groups list

GROUP LEVEL (group_id → bot_id → user_id)
  - Extracted tasks, reminders, decisions, meetings, notes
  - Group metadata (name, category, overrides)
  - Consent record (per bot-in-group combination)
```

---

## 3. COMPLETE SCHEMA

### 3.1 Bot Identities

```sql
-- LAZY CREATION: records are NOT created at deploy or on account creation.
-- Created on first user interaction with the Hub page (official bot) or
-- when user connects a custom bot (V1.5+).
-- The Hub UI is visible before these records exist — frontend handles null state gracefully.
bot_identities
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid()
  user_id               UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE
  bot_type              VARCHAR(20) NOT NULL              -- 'official' | 'custom'
  display_name          VARCHAR(100) NOT NULL
  telegram_bot_token    TEXT ENCRYPTED                   -- NULL for official bot (uses shared @telegizer_bot token)
  telegram_bot_username VARCHAR(100)                     -- NULL for official bot (@telegizer_bot)
  telegram_bot_id       BIGINT                           -- Telegram's internal bot ID
  is_active             BOOLEAN DEFAULT TRUE
  created_at            TIMESTAMPTZ DEFAULT NOW()

-- One official bot per user (enforced at application layer)
-- Unlimited custom bots per plan (plan-gated at application layer)
```

### 3.2 Bot Settings

```sql
-- Inheritable settings: NULL = inherit from official bot at runtime
-- Bot-specific settings: always set, never inherited
assistant_bot_settings
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid()
  bot_id                UUID NOT NULL REFERENCES bot_identities(id) ON DELETE CASCADE
  user_id               UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE

  -- Bot-specific (never inherited — always explicit)
  ai_personality_note   TEXT                             -- max 200 chars
  response_language     VARCHAR(10) DEFAULT 'en'

  -- Inheritable (NULL = inherit from official bot)
  extraction_sensitivity VARCHAR(10) DEFAULT NULL        -- minimal | standard | aggressive
  digest_enabled        BOOLEAN DEFAULT NULL
  digest_time           TIME DEFAULT NULL
  digest_format         VARCHAR(10) DEFAULT NULL         -- compact | detailed
  notification_prefs    JSONB DEFAULT NULL

  created_at            TIMESTAMPTZ DEFAULT NOW()
  updated_at            TIMESTAMPTZ DEFAULT NOW()
  UNIQUE(bot_id)
```

### 3.3 Assistant Hub Global Settings (User-Level)

```sql
-- Replaces old assistant_hub_settings
-- Covers account-wide preferences not tied to a specific bot
assistant_hub_global
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid()
  user_id               UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE
  is_enabled            BOOLEAN DEFAULT FALSE            -- has user activated Assistant Hub?
  default_bot_id        UUID REFERENCES bot_identities(id) ON DELETE SET NULL
  created_at            TIMESTAMPTZ DEFAULT NOW()
  updated_at            TIMESTAMPTZ DEFAULT NOW()
  UNIQUE(user_id)
```

---

### 3.4 Connected Groups

```sql
connected_groups
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid()
  bot_id                UUID NOT NULL REFERENCES bot_identities(id) ON DELETE CASCADE
  user_id               UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE
  telegram_group_id     BIGINT NOT NULL
  group_name            VARCHAR(255)
  category              VARCHAR(20) DEFAULT 'general'   -- team | project | personal | community | general
  is_active             BOOLEAN DEFAULT TRUE
  pause_reason          VARCHAR(50)                      -- NULL | 'user_paused' | 'plan_limit' | 'consent_missing' | 'error'
  active_mode_enabled   BOOLEAN DEFAULT FALSE            -- @mention replies (V1.5)
  consent_confirmed_at  TIMESTAMPTZ
  intro_sent            BOOLEAN DEFAULT FALSE
  is_public_group       BOOLEAN DEFAULT FALSE            -- detected at join time via Telegram API
  member_count_at_join  INTEGER                          -- stored at join for public group warning logic
  silence_start         TIME
  silence_end           TIME
  extract_tasks         BOOLEAN DEFAULT TRUE
  extract_reminders     BOOLEAN DEFAULT TRUE
  extract_decisions     BOOLEAN DEFAULT TRUE
  extract_meetings      BOOLEAN DEFAULT TRUE
  last_batch_at         TIMESTAMPTZ
  joined_at             TIMESTAMPTZ DEFAULT NOW()

  -- Same Telegram group can be connected to multiple bots (e.g., official + custom)
  -- Application layer warns user if same group is connected to two bots
  UNIQUE(bot_id, telegram_group_id)
```

---

### 3.5 Message Buffer (Redis — Ephemeral)

```
Key:   assistant:buffer:{bot_id}:{group_id}
Type:  Redis List
TTL:   72 hours (user-configurable to 24h or 48h)
Max:   500 entries (LTRIM on write)

Each entry (JSON):
{
  "telegram_message_id": 12345,
  "sender_name": "Ahmed",
  "content": "...",
  "timestamp": "2026-05-09T14:23:00Z",
  "has_trigger": false
}
```

Key includes `bot_id` so multiple bots monitoring the same group maintain separate buffers.

---

### 3.6 Extraction Batches

```sql
extraction_batches
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid()
  bot_id                UUID NOT NULL REFERENCES bot_identities(id)
  group_id              UUID NOT NULL REFERENCES connected_groups(id)
  user_id               UUID NOT NULL REFERENCES users(id)
  started_at            TIMESTAMPTZ DEFAULT NOW()
  completed_at          TIMESTAMPTZ
  message_count         INTEGER DEFAULT 0
  tokens_used           INTEGER DEFAULT 0
  model_used            VARCHAR(50)
  status                VARCHAR(20) DEFAULT 'pending'   -- pending | complete | failed | empty | partial
  error_message         TEXT
```

---

### 3.7 Extracted Intelligence

All extracted data tables include `bot_id` for context-switcher filtering.

```sql
tasks
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid()
  user_id               UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE
  bot_id                UUID NOT NULL REFERENCES bot_identities(id) ON DELETE CASCADE
  source_group_id       UUID REFERENCES connected_groups(id) ON DELETE SET NULL
  title                 TEXT NOT NULL ENCRYPTED
  description           TEXT ENCRYPTED
  assignee_name         VARCHAR(100)
  due_date              DATE
  due_time              TIME
  priority              VARCHAR(10) DEFAULT 'normal'    -- low | normal | high
  status                VARCHAR(20) DEFAULT 'pending'   -- pending | confirmed | done | dismissed
  source                VARCHAR(20) DEFAULT 'extracted' -- extracted | manual
  source_batch_id       UUID REFERENCES extraction_batches(id) ON DELETE SET NULL
  created_at            TIMESTAMPTZ DEFAULT NOW()
  updated_at            TIMESTAMPTZ DEFAULT NOW()

reminders
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid()
  user_id               UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE
  bot_id                UUID NOT NULL REFERENCES bot_identities(id) ON DELETE CASCADE
  source_group_id       UUID REFERENCES connected_groups(id) ON DELETE SET NULL
  content               TEXT NOT NULL ENCRYPTED
  remind_at             TIMESTAMPTZ NOT NULL
  recurrence            VARCHAR(20)
  source                VARCHAR(20) DEFAULT 'extracted'
  source_batch_id       UUID REFERENCES extraction_batches(id) ON DELETE SET NULL
  delivered_at          TIMESTAMPTZ
  dismissed_at          TIMESTAMPTZ
  created_at            TIMESTAMPTZ DEFAULT NOW()

decisions
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid()
  user_id               UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE
  bot_id                UUID NOT NULL REFERENCES bot_identities(id) ON DELETE CASCADE
  source_group_id       UUID REFERENCES connected_groups(id) ON DELETE SET NULL
  content               TEXT NOT NULL ENCRYPTED
  made_by               VARCHAR(100)
  source_batch_id       UUID REFERENCES extraction_batches(id) ON DELETE SET NULL
  dismissed_at          TIMESTAMPTZ
  created_at            TIMESTAMPTZ DEFAULT NOW()

meetings
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid()
  user_id               UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE
  bot_id                UUID NOT NULL REFERENCES bot_identities(id) ON DELETE CASCADE
  source_group_id       UUID REFERENCES connected_groups(id) ON DELETE SET NULL
  title                 VARCHAR(255) ENCRYPTED
  scheduled_at          TIMESTAMPTZ
  participants          TEXT[]
  reminder_created      BOOLEAN DEFAULT FALSE
  calendar_pushed       BOOLEAN DEFAULT FALSE
  source_batch_id       UUID REFERENCES extraction_batches(id) ON DELETE SET NULL
  dismissed_at          TIMESTAMPTZ
  created_at            TIMESTAMPTZ DEFAULT NOW()

notes
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid()
  user_id               UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE
  bot_id                UUID NOT NULL REFERENCES bot_identities(id) ON DELETE CASCADE
  source_group_id       UUID REFERENCES connected_groups(id) ON DELETE SET NULL
  content               TEXT NOT NULL ENCRYPTED
  tags                  TEXT[] DEFAULT '{}'
  source                VARCHAR(20) DEFAULT 'manual'
  source_batch_id       UUID REFERENCES extraction_batches(id) ON DELETE SET NULL
  created_at            TIMESTAMPTZ DEFAULT NOW()
  updated_at            TIMESTAMPTZ DEFAULT NOW()
```

---

### 3.8 Digests

```sql
digests
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid()
  user_id               UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE
  bot_id                UUID REFERENCES bot_identities(id) ON DELETE SET NULL  -- NULL = unified digest
  period                VARCHAR(20) DEFAULT 'daily'
  content               TEXT ENCRYPTED
  item_count            INTEGER DEFAULT 0
  groups_included       UUID[]
  generated_at          TIMESTAMPTZ DEFAULT NOW()
  delivered_at          TIMESTAMPTZ
  delivery_method       VARCHAR(20) DEFAULT 'telegram_dm'
```

---

### 3.9 Templates (Bot-Scoped)

```sql
templates
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid()
  bot_id                UUID NOT NULL REFERENCES bot_identities(id) ON DELETE CASCADE
  user_id               UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE
  name                  VARCHAR(100) NOT NULL
  content               TEXT NOT NULL ENCRYPTED          -- max 4096 chars
  use_count             INTEGER DEFAULT 0
  last_used_at          TIMESTAMPTZ
  created_at            TIMESTAMPTZ DEFAULT NOW()
  updated_at            TIMESTAMPTZ DEFAULT NOW()
  UNIQUE(bot_id, name)
```

---

### 3.10 Memory System (User-Scoped — Shared Across All Bots)

```sql
-- Global user context (shared)
memory_global
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid()
  user_id               UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE
  preferred_name        VARCHAR(100)
  company_name          VARCHAR(200)
  role                  VARCHAR(200)
  timezone              VARCHAR(50) DEFAULT 'UTC'
  current_priorities    TEXT[]
  free_notes            TEXT ENCRYPTED                   -- max 500 chars
  updated_at            TIMESTAMPTZ DEFAULT NOW()
  UNIQUE(user_id)

-- People (user-scoped, shared across bots)
memory_people
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid()
  user_id               UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE
  name                  VARCHAR(100) NOT NULL
  role                  VARCHAR(200)
  notes                 TEXT ENCRYPTED
  group_associations    UUID[]                           -- connected_group IDs
  source                VARCHAR(20) DEFAULT 'manual'
  created_at            TIMESTAMPTZ DEFAULT NOW()
  updated_at            TIMESTAMPTZ DEFAULT NOW()

-- Projects (user-scoped, shared across bots)
memory_projects
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid()
  user_id               UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE
  name                  VARCHAR(200) NOT NULL
  status                VARCHAR(50)
  context_notes         TEXT ENCRYPTED
  group_associations    UUID[]
  deadline              DATE
  source                VARCHAR(20) DEFAULT 'manual'
  created_at            TIMESTAMPTZ DEFAULT NOW()
  updated_at            TIMESTAMPTZ DEFAULT NOW()

-- Group context (group-level, but still user-owned)
memory_group_context
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid()
  user_id               UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE
  group_id              UUID NOT NULL REFERENCES connected_groups(id) ON DELETE CASCADE
  context_notes         TEXT ENCRYPTED
  key_members           TEXT[]
  active_projects       TEXT[]
  current_focus         TEXT ENCRYPTED
  updated_at            TIMESTAMPTZ DEFAULT NOW()
  UNIQUE(user_id, group_id)

-- Memory suggestions (pending user approval)
memory_suggestions
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid()
  user_id               UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE
  bot_id                UUID REFERENCES bot_identities(id) ON DELETE SET NULL
  suggestion_type       VARCHAR(20) NOT NULL             -- person | project
  suggested_data        JSONB NOT NULL
  source_batch_id       UUID REFERENCES extraction_batches(id)
  status                VARCHAR(20) DEFAULT 'pending'    -- pending | approved | skipped
  created_at            TIMESTAMPTZ DEFAULT NOW()
  resolved_at           TIMESTAMPTZ
```

---

### 3.11 Knowledge Cards (Bot-Scoped)

```sql
knowledge_cards
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid()
  bot_id                UUID NOT NULL REFERENCES bot_identities(id) ON DELETE CASCADE
  user_id               UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE
  title                 VARCHAR(100) NOT NULL ENCRYPTED
  content               TEXT NOT NULL ENCRYPTED          -- max 2000 chars
  tags                  TEXT[] DEFAULT '{}'
  use_count             INTEGER DEFAULT 0
  last_used_at          TIMESTAMPTZ
  created_at            TIMESTAMPTZ DEFAULT NOW()
  updated_at            TIMESTAMPTZ DEFAULT NOW()

-- V2 only: embedding column when pgvector needed
-- embedding            vector(1536)
```

---

### 3.12 Automations (Bot-Scoped with Inheritance)

```sql
-- System-defined pre-built automations (immutable)
system_automations
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid()
  code                  VARCHAR(50) UNIQUE NOT NULL
  name                  VARCHAR(100) NOT NULL
  description           TEXT
  trigger_event         VARCHAR(50)
  action                VARCHAR(50)
  default_params        JSONB DEFAULT '{}'
  is_active             BOOLEAN DEFAULT TRUE

-- Bot-level toggle state (NULL = inherit from official bot)
bot_automation_settings
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid()
  bot_id                UUID NOT NULL REFERENCES bot_identities(id) ON DELETE CASCADE
  automation_id         UUID NOT NULL REFERENCES system_automations(id)
  is_enabled            BOOLEAN DEFAULT NULL             -- NULL = inherit from official bot
  custom_params         JSONB DEFAULT NULL               -- NULL = inherit
  UNIQUE(bot_id, automation_id)
```

---

### 3.13 Inbox State

```sql
inbox_items
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid()
  user_id               UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE
  bot_id                UUID NOT NULL REFERENCES bot_identities(id) ON DELETE CASCADE
  item_type             VARCHAR(20) NOT NULL             -- task | reminder | decision | meeting | note | suggestion
  item_id               UUID NOT NULL
  is_new                BOOLEAN DEFAULT TRUE
  dismissed_at          TIMESTAMPTZ
  confirmed_at          TIMESTAMPTZ
  created_at            TIMESTAMPTZ DEFAULT NOW()
  UNIQUE(user_id, item_type, item_id)
```

---

## 4. INHERITANCE RESOLUTION (Runtime)

Settings for a bot are never read directly from `assistant_bot_settings` without going through the resolver. The resolver is the single access point.

```javascript
async function getEffectiveSettings(botId) {
  const bot = await db.bot_identities.findOne({ id: botId });
  const botSettings = await db.assistant_bot_settings.findOne({ bot_id: botId });

  // Official bot: resolve NULLs against hardcoded system defaults
  if (bot.bot_type === 'official') {
    return {
      ai_personality_note:    botSettings.ai_personality_note ?? '',
      response_language:      botSettings.response_language ?? 'en',
      extraction_sensitivity: botSettings.extraction_sensitivity ?? 'standard',
      digest_enabled:         botSettings.digest_enabled ?? false,
      digest_time:            botSettings.digest_time ?? '21:00:00',
      digest_format:          botSettings.digest_format ?? 'compact',
      notification_prefs:     botSettings.notification_prefs ?? {},
    };
  }

  // Custom bot: inherit NULLs from official bot
  const officialBot = await db.bot_identities.findOne({
    user_id: bot.user_id,
    bot_type: 'official'
  });
  const officialSettings = await getEffectiveSettings(officialBot.id);

  return {
    ai_personality_note:    botSettings.ai_personality_note ?? '',        // never inherited
    response_language:      botSettings.response_language ?? 'en',        // never inherited
    extraction_sensitivity: botSettings.extraction_sensitivity ?? officialSettings.extraction_sensitivity,
    digest_enabled:         botSettings.digest_enabled ?? officialSettings.digest_enabled,
    digest_time:            botSettings.digest_time ?? officialSettings.digest_time,
    digest_format:          botSettings.digest_format ?? officialSettings.digest_format,
    notification_prefs:     botSettings.notification_prefs ?? officialSettings.notification_prefs,
  };
}
```

---

## 5. INDEXES

```sql
-- Core query paths
CREATE INDEX idx_bot_identities_user ON bot_identities(user_id, is_active);
CREATE INDEX idx_connected_groups_bot ON connected_groups(bot_id, is_active);
CREATE INDEX idx_connected_groups_user ON connected_groups(user_id);
CREATE INDEX idx_tasks_user_bot_status ON tasks(user_id, bot_id, status);
CREATE INDEX idx_tasks_user_group ON tasks(user_id, source_group_id);
CREATE INDEX idx_reminders_bot_remind_at ON reminders(bot_id, remind_at) WHERE delivered_at IS NULL;
CREATE INDEX idx_decisions_user_bot ON decisions(user_id, bot_id);
CREATE INDEX idx_meetings_bot_scheduled ON meetings(bot_id, scheduled_at);
CREATE INDEX idx_inbox_user_bot_new ON inbox_items(user_id, bot_id, is_new) WHERE dismissed_at IS NULL;
CREATE INDEX idx_templates_bot ON templates(bot_id);
CREATE INDEX idx_knowledge_cards_bot ON knowledge_cards(bot_id);
CREATE INDEX idx_extraction_batches_bot_group ON extraction_batches(bot_id, group_id, started_at DESC);
CREATE INDEX idx_memory_people_user ON memory_people(user_id);
CREATE INDEX idx_memory_suggestions_pending ON memory_suggestions(user_id, status) WHERE status = 'pending';
```

---

## 6. PLAN LIMITS (Enforced at API Layer)

Plan names match real Telegizer plan names. Limits enforced on write — never on read.
Downgrade: excess groups auto-paused (`pause_reason = 'plan_limit'`), data never deleted.

| Resource | Free | Pro | Enterprise |
|---|---|---|---|
| Custom assistant bots | 0 | 2 | Unlimited |
| Connected groups (official bot) | 2 | 10 | Unlimited |
| Connected groups (per custom bot) | — | 5 | Unlimited |
| Knowledge cards (per bot) | 10 | 50 | Unlimited |
| Templates (per bot) | 5 | 30 | Unlimited |
| Memory people entries | 5 | 50 | Unlimited |
| Memory project entries | 3 | 30 | Unlimited |
| Extraction calls/day (total across all bots) | 30 | 300 | Unlimited |
| Digest history retention | 30 days | 90 days | 90 days |

---

## 7. DATA RETENTION

```sql
-- Daily cron (unchanged from v1.0)
DELETE FROM digests WHERE generated_at < NOW() - INTERVAL '90 days';
DELETE FROM extraction_batches WHERE completed_at < NOW() - INTERVAL '180 days';
DELETE FROM inbox_items WHERE dismissed_at < NOW() - INTERVAL '30 days';
-- Redis TTL handles raw buffer automatically
```

---

## 8. DATA EXPORT FORMAT

```json
{
  "exported_at": "2026-05-09T14:00:00Z",
  "user_id": "...",
  "bots": [
    {
      "bot_id": "...",
      "bot_type": "official",
      "display_name": "Telegizer Official",
      "settings": { ... },
      "templates": [ ... ],
      "knowledge_cards": [ ... ],
      "connected_groups": [
        {
          "group_id": "...",
          "group_name": "CreatorX Team",
          "tasks": [ ... ],
          "reminders": [ ... ],
          "decisions": [ ... ],
          "meetings": [ ... ],
          "notes": [ ... ]
        }
      ]
    },
    {
      "bot_id": "...",
      "bot_type": "custom",
      "display_name": "CreatorX Bot",
      "..."
    }
  ],
  "memory": {
    "global": { ... },
    "people": [ ... ],
    "projects": [ ... ],
    "group_contexts": [ ... ]
  }
}
```

Raw message content is never included — it is not stored permanently.
