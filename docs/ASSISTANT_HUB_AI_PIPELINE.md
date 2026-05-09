# ASSISTANT HUB — AI PIPELINE SPECIFICATION
**Version:** 2.0  
**Status:** Final — Ready for Sprint 1  
**Change from v1.0:** Shared @telegizer_bot token routing documented. Public group detection added to message filter. Lazy record creation noted in pipeline entry point.

---

## 1. DESIGN PRINCIPLES

- AI is called in batches, never per-message
- All AI outputs are validated against a schema before being stored
- Invalid outputs are silently discarded and logged — never surfaced to users as errors
- GPT-4o-mini for extraction (cost), GPT-4o for on-demand summarization (quality)
- No streaming in the extraction pipeline — synchronous calls inside workers
- Human memory approval is mandatory — AI never writes to memory automatically
- Extraction is not summarization — we extract structured data, not narratives
- Summaries are built from extracted structured data, not from raw messages

---

## 2. PIPELINE OVERVIEW

```
[Telegram Message Arrives via @telegizer_bot webhook]
          │
          ▼
[Module Router — runs before any processing]
  ├─ Is this group in Module A (connected_groups with moderation config)? → MODULE A HANDLER
  ├─ Is this group in Assistant Hub (connected_groups with bot_id)? → ASSISTANT HUB PIPELINE
  ├─ Both? → run both pipelines independently
  └─ Neither? → DISCARD
          │
          ▼
[ASSISTANT HUB MESSAGE FILTER]
  ├─ Not a connected Assistant Hub group → DISCARD
  ├─ Group is_active = false (paused or plan_limit) → DISCARD
  ├─ Bot command (/assist) → COMMAND HANDLER
  └─ Regular message → continue
          │
          ▼
[Immediate Trigger Detection]
  ├─ Contains date/time pattern? → PRIORITY QUEUE
  ├─ Contains trigger keywords? → PRIORITY QUEUE
  ├─ Contains @bot mention? → MENTION HANDLER
  └─ None → STANDARD BUFFER
          │
          ▼
[Redis Buffer]
  ├─ Priority queue → immediate extraction (within 2 min)
  └─ Standard buffer → batch extraction (every 30 min)
          │
          ▼
[Extraction Worker]
  ├─ Pull messages from buffer
  ├─ Build prompt with memory context
  ├─ Call GPT-4o-mini
  ├─ Validate JSON output
  ├─ Write to PostgreSQL
  └─ Trigger notification decision
          │
          ▼
[Notification Decision]
  ├─ Urgent items → immediate Telegram DM
  └─ Non-urgent → queue for daily digest
```

---

## 3. EXTRACTION PIPELINE (CORE)

### 3.1 Batch Trigger

- Standard: cron every 30 minutes, processes all groups with buffered messages
- Immediate: triggered by priority queue when urgent message detected
- Max messages per batch per group: 500 (older messages dropped)
- Empty buffer = no AI call made (cost control)

### 3.2 Pre-Processing (Before AI Call)

```javascript
// 1. Pull messages from Redis buffer for this group
const messages = await redis.lrange(`assistant:buffer:${groupId}`, 0, -1);
if (messages.length === 0) return; // skip — no AI call

// 2. Pre-parse dates/times with lightweight parser (reduces AI token load)
const parsed = messages.map(m => ({
  ...m,
  detected_datetime: chronoParse(m.content) // chrono-node
}));

// 3. Build memory context string
const memoryContext = buildMemoryContext(userId, groupId);
// Returns: "User: Fazal, Founder at CreatorX. Group: CreatorX Team. 
//           Members: Ahmed (Marketing), Sara (Partnerships)."

// 4. Clear buffer atomically
await redis.del(`assistant:buffer:${groupId}`);
```

### 3.3 Extraction Prompt

```
SYSTEM:
You are an intelligent meeting assistant. Extract structured information 
from the following group conversation. Return valid JSON only. 
Do not hallucinate. If a field is unknown, use null.

Context about this user and team:
{memoryContext}

Extract the following from the conversation:
- tasks: array of {title, assignee (name only or null), due_date (ISO 8601 or null), priority (low/normal/high)}
- reminders: array of {content, remind_at (ISO 8601 or null)}
- decisions: array of {content, made_by (name or null)}
- meetings: array of {title, scheduled_at (ISO 8601 or null), participants (name array)}
- important_notes: array of {content}

Rules:
- Only extract items clearly present in the conversation
- Do not infer or assume details not explicitly stated
- If nothing relevant exists, return empty arrays
- Return JSON only, no explanation text

USER:
Conversation from {groupName} on {date}:

{formattedMessages}
```

### 3.4 Message Formatting for Prompt

```
[14:23] Ahmed: Can you finalize the investor deck by Thursday?
[14:24] Sara: I'll handle the partnership section
[14:25] Fazal: Let's set up a call tomorrow at 3pm to review
[14:26] Ahmed: Agreed. Also don't forget to send the invoice to Acme today
```

Sender names are included. Telegram user IDs are not included (unnecessary token use + privacy).

### 3.5 Expected JSON Output Schema

```json
{
  "tasks": [
    {
      "title": "Finalize investor deck",
      "assignee": null,
      "due_date": "2026-05-14",
      "priority": "normal"
    },
    {
      "title": "Send invoice to Acme",
      "assignee": "Ahmed",
      "due_date": "2026-05-09",
      "priority": "high"
    }
  ],
  "reminders": [],
  "decisions": [
    {
      "content": "Sara will handle the partnership section of the deck",
      "made_by": "Sara"
    }
  ],
  "meetings": [
    {
      "title": "Investor deck review call",
      "scheduled_at": "2026-05-10T15:00:00Z",
      "participants": ["Ahmed", "Sara", "Fazal"]
    }
  ],
  "important_notes": []
}
```

### 3.6 Output Validation

```javascript
const schema = {
  tasks: [{ title: 'string', assignee: 'string|null', due_date: 'string|null', priority: 'string' }],
  reminders: [{ content: 'string', remind_at: 'string|null' }],
  decisions: [{ content: 'string', made_by: 'string|null' }],
  meetings: [{ title: 'string', scheduled_at: 'string|null', participants: 'array' }],
  important_notes: [{ content: 'string' }]
};

// If output fails validation:
// - Log the raw output and batch ID
// - Do not throw an error visible to user
// - Mark batch status as 'partial'
// - Store whatever valid items were parsed
```

### 3.7 Post-Extraction: Automation Triggers

After validation and storage, check enabled automations:

```javascript
for (const meeting of extracted.meetings) {
  if (userAutomations.meeting_reminder) {
    createReminder(userId, meeting.title, meeting.scheduled_at - 60min);
  }
}

for (const task of extracted.tasks) {
  if (task.due_date && userAutomations.deadline_alert) {
    sendImmediateDM(userId, `New task with deadline: ${task.title} — Due ${task.due_date}`);
  }
}
```

---

## 4. MEMORY CONTEXT INJECTION

### 4.1 Context Builder

```javascript
function buildMemoryContext(userId, groupId) {
  const global = await db.memory_global.findOne({ user_id: userId });
  const groupCtx = await db.memory_group_context.findOne({ user_id: userId, group_id: groupId });
  const people = await db.memory_people.findAll({ user_id: userId });
  const projects = await db.memory_projects.findAll({ user_id: userId, status: 'active' });

  let context = '';
  if (global.preferred_name) context += `User: ${global.preferred_name}`;
  if (global.company_name) context += `, ${global.role} at ${global.company_name}`;
  if (groupCtx?.current_focus) context += `. This group focus: ${groupCtx.current_focus}`;
  if (people.length) context += `. Team: ${people.map(p => `${p.name} (${p.role})`).join(', ')}`;
  if (projects.length) context += `. Active projects: ${projects.map(p => p.name).join(', ')}`;

  return context.trim() || 'No additional context available.';
}
```

### 4.2 Memory Injection Token Budget

Memory context is capped at 400 tokens. If context exceeds this:
- Trim people list to most recently active (by `last_seen` heuristic from prior extractions)
- Trim projects to deadline-soonest
- Always preserve global context and group focus

---

## 5. MEMORY SUGGESTION PIPELINE (V1.5)

### 5.1 Name Frequency Analysis

After each extraction batch, run a lightweight name counter:

```javascript
// Count name occurrences across all task assignees, decision makers, meeting participants
const nameCounts = countNamesInExtraction(extracted);

// Compare against existing memory_people for this user
const knownNames = await getKnownPeopleNames(userId);

for (const [name, count] of Object.entries(nameCounts)) {
  if (count >= 3 && !knownNames.includes(name)) {
    // Queue a suggestion — not delivered immediately
    await db.memory_suggestions.create({
      user_id: userId,
      suggestion_type: 'person',
      suggested_data: { name, notes: '', group_associations: [groupId] },
      source_batch_id: batchId
    });
  }
}
```

Suggestions are delivered bundled with the daily digest, not as immediate DMs.

### 5.2 Suggestion Delivery Format (in digest)

```
MEMORY SUGGESTIONS
──────────────────
I noticed Ahmed appears frequently in task assignments. 
Want to add them to your team memory?

[+ Add Ahmed] [Skip] [Don't ask about Ahmed]
```

---

## 6. ON-DEMAND SUMMARY PIPELINE (V1.5)

Triggered when user sends a query to the bot via DM.

### 6.1 Query Classification

```javascript
function classifyQuery(text) {
  // Rule-based, no AI call needed for classification
  if (/meeting|call|schedule/i.test(text)) return 'meetings_query';
  if (/task|todo|pending/i.test(text)) return 'tasks_query';
  if (/reminder/i.test(text)) return 'reminders_query';
  if (/decision/i.test(text)) return 'decisions_query';
  if (/summar|recap|overview/i.test(text)) return 'summary_request';
  if (/what.*said|who.*said/i.test(text)) return 'knowledge_query'; // KB lookup
  return 'general_query';
}
```

### 6.2 Data Queries (No AI Call)

For meetings_query, tasks_query, reminders_query, decisions_query:
- Pull directly from PostgreSQL
- Format structured response
- No AI model call needed

```
User: "What meetings are scheduled tomorrow?"
Response: "Tomorrow (May 10):
• Investor deck review — 3:00 PM (CreatorX Team)
• No other meetings found."
```

### 6.3 Summary Requests (GPT-4o)

For summary_request:
- Pull extracted items from requested period
- Build structured input from database rows (not raw messages)
- Call GPT-4o to generate narrative summary

```
SYSTEM: 
You are a concise executive assistant. Summarize the following extracted 
items from the user's team groups into a brief, readable recap. 
Group by source group. Use plain language. Max 300 words.

USER:
Items from the past 7 days:
{structuredExtractedItems}
```

### 6.4 Knowledge Card Queries (V1.5 — No AI for Retrieval)

```javascript
async function answerFromKnowledgeCards(userId, query) {
  const cards = await db.knowledge_cards.findAll({ user_id: userId });
  
  // Keyword matching
  const queryWords = query.toLowerCase().split(/\s+/);
  const matches = cards.filter(card => {
    const cardWords = `${card.title} ${card.tags.join(' ')}`.toLowerCase();
    return queryWords.some(word => cardWords.includes(word) && word.length > 3);
  });

  if (matches.length === 0) return null;
  
  // Use best match (most keyword overlaps)
  const best = matches[0];
  
  // AI call only to format the answer naturally
  const response = await openai.chat({
    model: 'gpt-4o-mini',
    messages: [
      { role: 'system', content: 'Answer the question using only the provided context. Be concise (max 2 sentences). Do not add information not in the context.' },
      { role: 'user', content: `Context: ${best.content}\n\nQuestion: ${query}` }
    ]
  });
  
  await db.knowledge_cards.increment('use_count', { where: { id: best.id } });
  return response.choices[0].message.content;
}
```

---

## 7. IMMEDIATE TRIGGER DETECTION

Run synchronously on every incoming message before buffering:

```javascript
const TRIGGER_PATTERNS = [
  /\b(tomorrow|today|monday|tuesday|wednesday|thursday|friday)\b/i,
  /\b(\d{1,2}(am|pm|:\d{2}))\b/i,
  /\b(remind me|don't forget|deadline|due|schedule|meeting|call)\b/i,
];

function hasImmediateTrigger(messageText) {
  return TRIGGER_PATTERNS.some(pattern => pattern.test(messageText));
}
```

Messages with triggers are added to the priority queue instead of the standard buffer. The priority queue processor runs every 2 minutes instead of every 30 minutes.

---

## 8. MODEL SELECTION & COST CONTROLS

| Use Case | Model | Reason |
|---|---|---|
| Batch extraction | gpt-4o-mini | Low cost, sufficient for structured JSON extraction |
| On-demand summarization | gpt-4o | Higher quality, used rarely |
| Knowledge card formatting | gpt-4o-mini | Short output, no need for top model |
| Query classification | Rule-based | No model call — zero cost |
| Data queries (tasks, meetings) | No model | Direct database query |

### Token Budget Per Extraction Call

```
System prompt + memory context:  ~400 tokens
Group messages (30min average):  ~800 tokens
Extraction JSON output:          ~300 tokens
────────────────────────────────────────────
Total per call:                  ~1,500 tokens
Cost at gpt-4o-mini pricing:     ~$0.00075 per call
```

### Daily Cost Ceiling Per User (Worst Case)

```
20 connected groups × 48 batch calls/day = 960 calls/day
960 × $0.00075 = $0.72/day/user (max active)
Realistic (50% quiet groups):  ~$0.35/day/user
Monthly (30 days):             ~$10.50/user/month (max)
```

Pro plan at $29/month leaves viable margin. Free plan group limit of 3 keeps cost to ~$1.57/month/user.

### Hard Limits

```javascript
const DAILY_LIMITS = {
  free: 50,    // extraction calls per day
  pro: 500,
  business: Infinity
};

// Enforced at worker level — check before each extraction call
const todayCount = await redis.get(`extract:count:${userId}:${today}`);
if (todayCount >= DAILY_LIMITS[userPlan]) {
  // Skip extraction, log skip, do NOT notify user unless they hit limit multiple days in a row
  return;
}
```

---

## 9. WHAT AI MUST NEVER DO

- Speak in a group without explicit @mention (V1.5+ with Active Mode enabled)
- Permanently store raw conversation text anywhere
- Auto-write to memory without user approval
- Generate responses it cannot ground in extracted data or knowledge cards
- Make unsolicited decisions (create tasks, set reminders) without being triggered
- Summarize raw messages into narratives (always summarize extracted structured data)
- Answer questions with "I think..." or speculative language — if it doesn't know, it says so
- Attempt to answer from group conversation history (only from extracted items and knowledge cards)

---

## 10. FUTURE AI CAPABILITIES (V2)

### Follow-up Detection
After extraction, check if prior extracted items contain unresolved promises:

```
Extraction from 3 days ago: Decision — "Ahmed will send the report by Friday"
Today's extraction: No mention of report resolved
→ Flag for user: "Follow-up pending: Ahmed's report was due Friday — no update found"
```

### Unanswered Question Detection
If extracted item type becomes "question" (V2 entity type):
Track question timestamp. If 24h passes with no answer in same group → DM alert.

### Embedding Migration (V2 — Conditional)
Only add pgvector when:
- 20%+ of Pro users hit knowledge card limits
- AND usage data shows active card retrieval

Migration path:
1. Add `embedding vector(1536)` to `knowledge_cards` table
2. Run background job to embed all existing cards
3. Switch `answerFromKnowledgeCards` to cosine similarity retrieval
4. No other infrastructure change needed — stays in PostgreSQL
