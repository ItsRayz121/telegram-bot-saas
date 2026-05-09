# ASSISTANT HUB — PRIVACY & TRUST ARCHITECTURE
**Version:** 2.0  
**Status:** Final — Ready for Sprint 1  
**Change from v1.0:** Public group warning added to consent flow. Downgrade behavior documented (auto-pause, data preserved). Shared bot token privacy implications noted.

---

## 1. PRIVACY PHILOSOPHY

Privacy is a product feature, not a compliance checkbox.

The Assistant Hub processes private group conversations. This means:
- Users are trusting the system with their business communications
- Other group members may not know the bot exists
- Extracted data may contain sensitive business intelligence

Every default setting must protect a user who never reads the privacy documentation. Privacy must be built into the architecture, not bolted on afterward.

Core privacy commitments:
1. Observation does not begin without explicit user consent
2. Raw conversation content is never stored permanently
3. Users can see, export, and delete everything the system holds about them
4. Other group members cannot be profiled without the owner's deliberate action
5. The system stores what was extracted, not what was said

---

## 2. CONSENT ARCHITECTURE

### 2.1 Consent Flow (Mandatory — Cannot Be Bypassed)

```
STEP 1
User adds bot to a Telegram group
        │
        ▼
STEP 2
Bot immediately sends a DM to the user who added it:

  ────────────────────────────────────────────────
  You've added me to [GroupName].

  Before I start observing, here's what happens:
  • I'll analyze messages to surface tasks, reminders, 
    and meetings
  • Raw messages are deleted after [retention window]
  • Extracted items are stored in your Telegizer account
  • Other group members won't be notified automatically

  Do you want me to start observing this group?

  [✓ Start Observing]   [✗ Cancel — Remove Me]
  ────────────────────────────────────────────────
        │
        ▼
STEP 2.5 — Public Group Warning (if detected)

  If group is public (has public username) OR member count > 500:
  ────────────────────────────────────────────────
  Note: This looks like a public or large group.

  Assistant Hub is designed for private team groups.
  Public group management works best via Group Management.

  You can still connect it, but results may vary.

  [Connect Anyway]   [Cancel]
  ────────────────────────────────────────────────
  This is a warning only — does not block connection.
  is_public_group and member_count_at_join stored for audit.

STEP 3 — User responds

  If CANCEL:
    Bot leaves the group automatically
    No data is written to the database

  If START (or Connect Anyway):
    connected_groups record is created
    consent_confirmed_at is set to NOW()
    Observation begins
        │
        ▼
STEP 4 — Introduction prompt (optional, user-controlled)

  Bot sends second DM:
  ────────────────────────────────────────────────
  Do you want to let the group know I'm here?
  
  This is recommended — it lets other members know 
  their messages are being analyzed.
  
  [✓ Send Brief Introduction]   [Skip]
  ────────────────────────────────────────────────

  If SEND:
    Bot sends to group:
    "Hi, I'm Telegizer Assistant. I'll help [FirstName] 
    track tasks and meetings from this group. I won't 
    respond to messages unless @mentioned."

  If SKIP:
    intro_sent remains FALSE — logged for audit
    No group message sent
```

### 2.2 Consent Record

The `consent_confirmed_at` timestamp in `connected_groups` is immutable once set. It is the legal record of when observation was authorized. It cannot be updated — only the row can be deleted (disconnecting the group).

### 2.3 Re-Consent Requirements

Re-consent is required if:
- The user's plan changes in a way that expands data retention (longer retention = new consent)
- The product adds a new data type to extraction that wasn't covered in original consent
- The bot is removed and re-added to the same group

---

## 2.4 PLAN DOWNGRADE BEHAVIOR

When a user downgrades to a lower plan, the following happens automatically:

1. System calculates which groups exceed the new plan limit (ordered by `last_batch_at` ascending — least recently active paused first)
2. Excess groups are set: `is_active = false`, `pause_reason = 'plan_limit'`
3. Extraction stops immediately for paused groups
4. All existing extracted data for paused groups remains fully visible in the dashboard
5. User receives a DM: "Your plan changed. [N] groups have been paused. Visit your Hub to manage which groups stay active."
6. User can reactivate a paused group by pausing a different active group first (swap model)

**What is never deleted on downgrade:**
- Extracted tasks, reminders, decisions, meetings, notes
- Memory entries
- Templates and knowledge cards
- Digests within retention window

**What stops on downgrade:**
- New extraction for paused groups
- New DM alerts from paused groups
- Digest contributions from paused groups

---

## 3. DATA RETENTION ARCHITECTURE

### 3.1 Retention Tiers

| Data Type | Default Retention | Configurable | Maximum |
|---|---|---|---|
| Raw message buffer (Redis) | 72 hours | YES (24h / 48h / 72h) | 72 hours |
| Extracted tasks | Until user deletes | NO | No limit |
| Extracted reminders | Until user deletes | NO | No limit |
| Extracted decisions | Until user deletes | NO | No limit |
| Extracted meetings | Until user deletes | NO | No limit |
| Notes | Until user deletes | NO | No limit |
| AI-generated digests | 90 days | NO | 90 days |
| Extraction batch logs | 180 days | NO | 180 days |
| Memory entries | Until user deletes | NO | No limit |
| Knowledge cards | Until user deletes | NO | No limit |
| Dismissed inbox items | 30 days after dismissal | NO | 30 days |

### 3.2 Retention Enforcement

```javascript
// Daily cron job — runs at 03:00 UTC
async function enforceRetention() {
  // Digest purge
  await db.query(`DELETE FROM digests WHERE generated_at < NOW() - INTERVAL '90 days'`);
  
  // Batch log purge
  await db.query(`DELETE FROM extraction_batches WHERE completed_at < NOW() - INTERVAL '180 days'`);
  
  // Dismissed inbox items purge
  await db.query(`DELETE FROM inbox_items WHERE dismissed_at < NOW() - INTERVAL '30 days'`);
  
  // Redis TTL is set on write — no action needed here
}
```

### 3.3 Why 72 Hours for Raw Buffer

Telegram's Terms of Service prohibit storing message content beyond what is operationally necessary. 72 hours covers the longest practical batch window while remaining defensible under ToS. Extracted structured data (tasks, decisions) is the user's own derived data product — not Telegram's message content — placing it in a legally distinct category.

---

## 4. USER CONTROL SYSTEM

All of the following must be available in the dashboard under Settings → Privacy & Data. All operations must complete within 30 seconds or provide a download link within 5 minutes for large exports.

### 4.1 View All Extracted Data
User can browse all extracted items across all groups from the dashboard. Nothing is hidden from the user who owns the data.

### 4.2 Export All Data (JSON)
One-click full export. Includes:
- All tasks, reminders, decisions, meetings, notes
- All templates
- All memory entries (global, people, projects, group contexts)
- All knowledge cards
- Connected group metadata (names, categories, settings)
- Digest history (if within retention window)

Does NOT include:
- Raw message content (never stored permanently)
- Other users' data
- System/audit logs

### 4.3 Pause Observation
User can pause observation on any connected group without disconnecting the bot. While paused:
- Bot remains in the group (no announcement)
- No new messages are buffered
- No new extractions run
- Existing data is preserved

Resumed via dashboard toggle.

### 4.4 Delete Data From One Group
Deletes all extracted items whose `source_group_id` matches the selected group. Includes tasks, reminders, decisions, meetings, notes, inbox items. Does not delete the connected_group record itself (bot remains connected). Does not affect memory entries or knowledge cards (those are user-authored, not group-sourced).

### 4.5 Disconnect a Group
Removes `connected_groups` record. Bot leaves the group. User is prompted:
- "Also delete all extracted data from this group?" [Yes] [No — keep extracted data]

### 4.6 Delete All Assistant Data
Deletes all Assistant Hub data for the user. Does not delete the main Telegizer account. Includes:
- All extracted items from all groups
- All digests
- All memory entries
- All knowledge cards
- All templates
- All connected group records (bot leaves all groups)
- `assistant_hub_settings` record

Implemented as a cascading delete from `assistant_hub_settings`. Must require explicit confirmation (type "DELETE" or similar).

### 4.7 Retention Window Configuration
User selects raw buffer retention: 24h / 48h / 72h. Shorter is more private. Setting takes effect on next buffer write. Existing buffer entries are not retroactively shortened.

---

## 5. ENCRYPTION ARCHITECTURE

### 5.1 At-Rest Encryption

All user content fields (message-derived or user-authored) are encrypted at the application layer before database write.

```
Encryption: AES-256-GCM
Key storage: AWS Secrets Manager (or equivalent) — not in database
Key structure: One master key per user (derived from user_id + secret salt)
IV: Random 96-bit, stored as prefix to ciphertext
Format stored in DB: base64(iv + ciphertext + auth_tag)
```

Fields that are encrypted:
- `tasks.title`, `tasks.description`
- `reminders.content`
- `decisions.content`
- `meetings.title`
- `notes.content`
- `templates.content`
- `knowledge_cards.title`, `knowledge_cards.content`
- `memory_global.free_notes`
- `memory_people.notes`
- `memory_projects.context_notes`
- `memory_group_context.context_notes`, `memory_group_context.current_focus`
- `digests.content`

Fields that are NOT encrypted (search/filter keys):
- `tasks.status`, `tasks.due_date`, `tasks.priority`
- `memory_people.name`, `memory_people.role`
- `connected_groups.telegram_group_id`, `connected_groups.group_name`
- All `id`, `user_id`, `created_at` fields

### 5.2 In-Transit Encryption

- All API communication: TLS 1.3
- Telegram webhook: HTTPS endpoint with secret token validation
- Database connections: SSL required
- Redis connections: TLS required

### 5.3 Log Sanitization

- Telegram group IDs in logs: hashed (SHA-256)
- Telegram user IDs in logs: hashed (SHA-256)
- Message content: never written to logs
- Extracted content: never written to logs (only item IDs and counts)

---

## 6. TELEGRAM TOS COMPLIANCE

### 6.1 What Is Stored

| Data | Stored | Duration | Justification |
|---|---|---|---|
| Raw message text | YES (Redis only) | 72h max | Required for batch extraction — operational necessity |
| Sender Telegram ID | YES (Redis only) | 72h max | Required to filter bots/system messages |
| Sender display name | YES (Redis only) | 72h max | Required for extraction context |
| Extracted task titles | YES (PostgreSQL) | User-controlled | User's own derived data product |
| Extracted reminder content | YES (PostgreSQL) | User-controlled | User's own derived data product |
| Message IDs | YES (PostgreSQL) | Per batch log TTL | Audit trail — no content |

### 6.2 What Is Never Stored

- Full conversation history
- Media, files, or attachments
- Voice message content
- Location data
- Contact cards shared in groups

### 6.3 Bot Behavior Requirements Per Telegram ToS

- Bot only reads messages in groups where it has been explicitly added
- Bot does not scrape public groups
- Bot does not use Telegram's unauthorized data access methods
- Bot complies with rate limits (30 messages/second API limit)
- Bot uses webhook or polling within authorized rate parameters

---

## 7. GDPR / PRIVACY LAW CONSIDERATIONS

### 7.1 Legal Basis for Processing

The legal basis for processing private group messages is **legitimate interest + consent**:
- User explicitly consents to observation (consent flow)
- User is the data controller for their own groups
- Processing serves the user's stated productivity purposes

### 7.2 Data Subject Rights

| Right | Implementation |
|---|---|
| Right to access | Export all data (Section 4.2) |
| Right to erasure | Delete all data (Section 4.6) |
| Right to portability | JSON export (Section 4.2) |
| Right to rectification | All extracted items editable in dashboard |
| Right to restrict processing | Pause observation (Section 4.3) |

### 7.3 Third-Party Members of Groups

Other members of connected groups may have rights under GDPR if their messages are processed. Mitigations:
- User is encouraged to send group introduction (transparency)
- Only extracted structured data is retained, not individual messages
- Sender names in extracted items are treated as pseudonymous identifiers

### 7.4 Data Processing Agreement (DPA)

For Business plan users with teams, provide a standard DPA upon request documenting:
- What data is processed
- How long it is retained
- Sub-processors (OpenAI, cloud provider)
- Security measures

---

## 8. OPENAI DATA HANDLING

Messages are sent to OpenAI's API for extraction processing. Mitigations:

- OpenAI's API (not ChatGPT) does not use API data for training by default
- Include `X-OpenAI-Opt-Out-Training: true` header (or equivalent current mechanism)
- Do not send Telegram user IDs to OpenAI — send sender names only
- Do not include group IDs or user account identifiers in prompts
- Batch message content is the minimal set needed for extraction

For Business plan, document OpenAI as a sub-processor in the DPA.

---

## 9. INCIDENT RESPONSE

### 9.1 Data Breach Protocol

If unauthorized access to user data is detected:
1. Immediately disable affected user accounts
2. Revoke and rotate encryption keys for affected users
3. Notify affected users within 72 hours (GDPR requirement)
4. Notify relevant supervisory authorities if >250 users affected
5. Delete and re-encrypt affected data with new keys after investigation

### 9.2 User-Reported Privacy Concerns

Direct contact for privacy concerns: [privacy email to be configured]
Response SLA: 48 hours acknowledgment, 30 days resolution.

---

## 10. PRIVACY-SAFE DEFAULTS SUMMARY

| Setting | Default | Reason |
|---|---|---|
| Observation | OFF (requires consent) | Explicit opt-in required |
| Group introduction | User must choose | No silent observation by default |
| Active Mode (@mention replies) | OFF | No bot speaking without choice |
| Raw buffer retention | 72 hours | Shortest practical window |
| Memory suggestions | Delivered for approval | Never auto-saved |
| Digest | OFF until configured | No output without configuration |
| Export | Available immediately | Always accessible |
| Deletion | One-click, immediate | No friction on deletion |
