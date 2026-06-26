"""
Assistant Hub — SQLAlchemy models for all Sprint 1 tables.

All tables use UUID primary keys (stored as VARCHAR(36)) and
Integer foreign keys to users.id (which is an Integer PK in this project).

Fields marked ENCRYPTED in the spec are stored as-is here; the application
layer must encrypt/decrypt using backend.utils.encryption before write/read.
"""
import uuid
from datetime import datetime

from ..models import db


def _uuid():
    return str(uuid.uuid4())


# ── 1. Bot Identities ──────────────────────────────────────────────────────────

class HubBotIdentity(db.Model):
    __tablename__ = "hub_bot_identities"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    bot_type = db.Column(db.String(20), nullable=False)              # 'official' | 'custom'
    display_name = db.Column(db.String(100), nullable=False)
    telegram_bot_token = db.Column(db.Text)                          # NULL for official bot; ENCRYPTED
    telegram_bot_username = db.Column(db.String(100))                # NULL for official bot
    telegram_bot_id = db.Column(db.BigInteger)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    # Set when this hub identity was auto-mirrored from a Group Management CustomBot
    custom_bot_id = db.Column(db.Integer, db.ForeignKey("custom_bots.id", ondelete="SET NULL"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.Index("idx_hub_bot_identities_user", "user_id", "is_active"),
    )


# ── 2. Bot Settings ────────────────────────────────────────────────────────────

class HubBotSettings(db.Model):
    __tablename__ = "hub_bot_settings"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    bot_id = db.Column(db.String(36), db.ForeignKey("hub_bot_identities.id", ondelete="CASCADE"), nullable=False, unique=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Bot-specific — never inherited
    ai_personality_note = db.Column(db.Text)                         # max 200 chars
    response_language = db.Column(db.String(10), default="en")

    # Inheritable — NULL = inherit from official bot at runtime
    extraction_sensitivity = db.Column(db.String(10))                # minimal | standard | aggressive
    digest_enabled = db.Column(db.Boolean)
    digest_time = db.Column(db.Time)
    digest_format = db.Column(db.String(10))                         # compact | detailed
    notification_prefs = db.Column(db.JSON)

    # Community reply settings (custom bots only — controls hub_reply behaviour)
    reply_sensitivity = db.Column(db.String(10), default="medium")   # low | medium | high
    escalation_contact = db.Column(db.BigInteger)                    # Telegram user_id to DM when bot can't answer
    tone = db.Column(db.String(20), default="friendly")              # friendly | professional | neutral

    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


# ── 3. Assistant Hub Global (user-level) ──────────────────────────────────────

class AssistantHubGlobal(db.Model):
    __tablename__ = "assistant_hub_global"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    is_enabled = db.Column(db.Boolean, default=False, nullable=False)
    default_bot_id = db.Column(db.String(36), db.ForeignKey("hub_bot_identities.id", ondelete="SET NULL"))
    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


# ── 4. Connected Groups ────────────────────────────────────────────────────────

class HubConnectedGroup(db.Model):
    __tablename__ = "hub_connected_groups"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    bot_id = db.Column(db.String(36), db.ForeignKey("hub_bot_identities.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    telegram_group_id = db.Column(db.BigInteger, nullable=False)
    group_name = db.Column(db.String(255))
    category = db.Column(db.String(20), default="general")           # team | project | personal | community | general
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    pause_reason = db.Column(db.String(50))                          # NULL | 'user_paused' | 'plan_limit' | 'consent_missing' | 'error'
    active_mode_enabled = db.Column(db.Boolean, default=False, nullable=False)
    consent_confirmed_at = db.Column(db.DateTime(timezone=True))
    intro_sent = db.Column(db.Boolean, default=False, nullable=False)
    is_public_group = db.Column(db.Boolean, default=False, nullable=False)
    member_count_at_join = db.Column(db.Integer)
    silence_start = db.Column(db.Time)
    silence_end = db.Column(db.Time)
    extract_tasks = db.Column(db.Boolean, default=True, nullable=False)
    extract_reminders = db.Column(db.Boolean, default=True, nullable=False)
    extract_decisions = db.Column(db.Boolean, default=True, nullable=False)
    extract_meetings = db.Column(db.Boolean, default=True, nullable=False)
    last_batch_at = db.Column(db.DateTime(timezone=True))
    is_knowledge_channel = db.Column(db.Boolean, default=False, nullable=False)  # auto-capture all msgs → knowledge cards
    joined_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("bot_id", "telegram_group_id", name="uq_hub_cg_bot_group"),
        db.Index("idx_hub_connected_groups_bot", "bot_id", "is_active"),
        db.Index("idx_hub_connected_groups_user", "user_id"),
    )


# ── 5. Extraction Batches ──────────────────────────────────────────────────────

class HubExtractionBatch(db.Model):
    __tablename__ = "hub_extraction_batches"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    bot_id = db.Column(db.String(36), db.ForeignKey("hub_bot_identities.id"), nullable=False)
    group_id = db.Column(db.String(36), db.ForeignKey("hub_connected_groups.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    started_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    completed_at = db.Column(db.DateTime(timezone=True))
    message_count = db.Column(db.Integer, default=0, nullable=False)
    tokens_used = db.Column(db.Integer, default=0, nullable=False)
    model_used = db.Column(db.String(50))
    status = db.Column(db.String(20), default="pending", nullable=False)  # pending | complete | failed | empty | partial
    error_message = db.Column(db.Text)

    __table_args__ = (
        db.Index("idx_hub_extraction_batches_bot_group", "bot_id", "group_id", "started_at"),
    )


# ── 6. Extracted Intelligence ──────────────────────────────────────────────────

class HubTask(db.Model):
    __tablename__ = "hub_tasks"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    bot_id = db.Column(db.String(36), db.ForeignKey("hub_bot_identities.id", ondelete="CASCADE"), nullable=False)
    source_group_id = db.Column(db.String(36), db.ForeignKey("hub_connected_groups.id", ondelete="SET NULL"))
    title = db.Column(db.Text, nullable=False)                       # ENCRYPTED
    description = db.Column(db.Text)                                 # ENCRYPTED
    assignee_name = db.Column(db.String(100))
    due_date = db.Column(db.Date)
    due_time = db.Column(db.Time)
    priority = db.Column(db.String(10), default="normal", nullable=False)  # low | normal | high
    status = db.Column(db.String(20), default="pending", nullable=False)   # pending | confirmed | done | dismissed
    source = db.Column(db.String(20), default="extracted", nullable=False) # extracted | manual
    source_batch_id = db.Column(db.String(36), db.ForeignKey("hub_extraction_batches.id", ondelete="SET NULL"))
    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.Index("idx_hub_tasks_user_bot_status", "user_id", "bot_id", "status"),
        db.Index("idx_hub_tasks_user_group", "user_id", "source_group_id"),
    )


class HubReminder(db.Model):
    __tablename__ = "hub_reminders"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    bot_id = db.Column(db.String(36), db.ForeignKey("hub_bot_identities.id", ondelete="CASCADE"), nullable=False)
    source_group_id = db.Column(db.String(36), db.ForeignKey("hub_connected_groups.id", ondelete="SET NULL"))
    content = db.Column(db.Text, nullable=False)                     # ENCRYPTED
    remind_at = db.Column(db.DateTime(timezone=True), nullable=False)
    recurrence = db.Column(db.String(20))
    source = db.Column(db.String(20), default="extracted", nullable=False)
    source_batch_id = db.Column(db.String(36), db.ForeignKey("hub_extraction_batches.id", ondelete="SET NULL"))
    delivered_at = db.Column(db.DateTime(timezone=True))
    dismissed_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.Index("idx_hub_reminders_bot_remind_at", "bot_id", "remind_at"),
    )


class HubDecision(db.Model):
    __tablename__ = "hub_decisions"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    bot_id = db.Column(db.String(36), db.ForeignKey("hub_bot_identities.id", ondelete="CASCADE"), nullable=False)
    source_group_id = db.Column(db.String(36), db.ForeignKey("hub_connected_groups.id", ondelete="SET NULL"))
    content = db.Column(db.Text, nullable=False)                     # ENCRYPTED
    made_by = db.Column(db.String(100))
    source_batch_id = db.Column(db.String(36), db.ForeignKey("hub_extraction_batches.id", ondelete="SET NULL"))
    dismissed_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.Index("idx_hub_decisions_user_bot", "user_id", "bot_id"),
    )


class HubMeeting(db.Model):
    __tablename__ = "hub_meetings"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    bot_id = db.Column(db.String(36), db.ForeignKey("hub_bot_identities.id", ondelete="CASCADE"), nullable=False)
    source_group_id = db.Column(db.String(36), db.ForeignKey("hub_connected_groups.id", ondelete="SET NULL"))
    title = db.Column(db.String(255))                                # ENCRYPTED
    scheduled_at = db.Column(db.DateTime(timezone=True))
    participants = db.Column(db.JSON, default=list)                  # list of names
    meeting_url = db.Column(db.String(500), nullable=True)           # Zoom/Meet/Calendly link
    reminder_created = db.Column(db.Boolean, default=False, nullable=False)
    calendar_pushed = db.Column(db.Boolean, default=False, nullable=False)
    # Google Calendar event id, so edits/deletes here can update/remove that event
    # instead of orphaning a duplicate. NULL until first pushed.
    calendar_event_id = db.Column(db.String(255), nullable=True)
    # "extracted" (AI from chat) | "manual" (user added) | "calendar" (pulled from
    # Google Calendar reverse-sync). Lets the UI label origin and avoids the
    # reverse-sync re-importing meetings Echo itself pushed.
    source = db.Column(db.String(20), default="extracted", nullable=False)
    source_batch_id = db.Column(db.String(36), db.ForeignKey("hub_extraction_batches.id", ondelete="SET NULL"))
    dismissed_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.Index("idx_hub_meetings_bot_scheduled", "bot_id", "scheduled_at"),
    )


class HubNote(db.Model):
    __tablename__ = "hub_notes"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    bot_id = db.Column(db.String(36), db.ForeignKey("hub_bot_identities.id", ondelete="CASCADE"), nullable=False)
    source_group_id = db.Column(db.String(36), db.ForeignKey("hub_connected_groups.id", ondelete="SET NULL"))
    content = db.Column(db.Text, nullable=False)                     # ENCRYPTED
    tags = db.Column(db.JSON, default=list)
    source = db.Column(db.String(20), default="manual", nullable=False)
    source_batch_id = db.Column(db.String(36), db.ForeignKey("hub_extraction_batches.id", ondelete="SET NULL"))
    embedding = db.Column(db.Text)                                     # JSON-encoded float list for semantic search
    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


# ── 7. Digests ─────────────────────────────────────────────────────────────────

class HubDigest(db.Model):
    __tablename__ = "hub_digests"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    bot_id = db.Column(db.String(36), db.ForeignKey("hub_bot_identities.id", ondelete="SET NULL"))  # NULL = unified digest
    period = db.Column(db.String(20), default="daily", nullable=False)
    content = db.Column(db.Text)                                     # ENCRYPTED
    item_count = db.Column(db.Integer, default=0, nullable=False)
    groups_included = db.Column(db.JSON, default=list)               # list of group_id strings
    generated_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    delivered_at = db.Column(db.DateTime(timezone=True))
    delivery_method = db.Column(db.String(20), default="telegram_dm", nullable=False)


# ── 8. Templates ───────────────────────────────────────────────────────────────

class HubTemplate(db.Model):
    __tablename__ = "hub_templates"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    bot_id = db.Column(db.String(36), db.ForeignKey("hub_bot_identities.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)                     # ENCRYPTED; max 4096 chars
    use_count = db.Column(db.Integer, default=0, nullable=False)
    last_used_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("bot_id", "name", name="uq_hub_template_bot_name"),
        db.Index("idx_hub_templates_bot", "bot_id"),
    )


# ── 9. Memory System ───────────────────────────────────────────────────────────

class HubMemoryGlobal(db.Model):
    __tablename__ = "hub_memory_global"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    preferred_name = db.Column(db.String(100))
    company_name = db.Column(db.String(200))
    role = db.Column(db.String(200))
    timezone = db.Column(db.String(50), default="UTC", nullable=False)
    current_priorities = db.Column(db.JSON, default=list)
    free_notes = db.Column(db.Text)                                  # ENCRYPTED; max 500 chars
    updated_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class HubMemoryPerson(db.Model):
    __tablename__ = "hub_memory_people"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(200))
    notes = db.Column(db.Text)                                       # ENCRYPTED
    group_associations = db.Column(db.JSON, default=list)            # list of connected_group id strings
    source = db.Column(db.String(20), default="manual", nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.Index("idx_hub_memory_people_user", "user_id"),
    )


class HubMemoryProject(db.Model):
    __tablename__ = "hub_memory_projects"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(50))
    context_notes = db.Column(db.Text)                               # ENCRYPTED
    group_associations = db.Column(db.JSON, default=list)
    deadline = db.Column(db.Date)
    source = db.Column(db.String(20), default="manual", nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class HubMemoryGroupContext(db.Model):
    __tablename__ = "hub_memory_group_context"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    group_id = db.Column(db.String(36), db.ForeignKey("hub_connected_groups.id", ondelete="CASCADE"), nullable=False)
    context_notes = db.Column(db.Text)                               # ENCRYPTED
    key_members = db.Column(db.JSON, default=list)
    active_projects = db.Column(db.JSON, default=list)
    current_focus = db.Column(db.Text)                               # ENCRYPTED
    updated_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("user_id", "group_id", name="uq_hub_mgc_user_group"),
    )


class HubMemorySuggestion(db.Model):
    __tablename__ = "hub_memory_suggestions"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    bot_id = db.Column(db.String(36), db.ForeignKey("hub_bot_identities.id", ondelete="SET NULL"))
    suggestion_type = db.Column(db.String(20), nullable=False)       # person | project
    suggested_data = db.Column(db.JSON, nullable=False)
    source_batch_id = db.Column(db.String(36), db.ForeignKey("hub_extraction_batches.id", ondelete="SET NULL"))
    status = db.Column(db.String(20), default="pending", nullable=False)  # pending | approved | skipped
    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    resolved_at = db.Column(db.DateTime(timezone=True))

    __table_args__ = (
        db.Index("idx_hub_memory_suggestions_pending", "user_id", "status"),
    )


# ── 10. Knowledge Cards ────────────────────────────────────────────────────────

class HubKnowledgeCard(db.Model):
    __tablename__ = "hub_knowledge_cards"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    bot_id = db.Column(db.String(36), db.ForeignKey("hub_bot_identities.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = db.Column(db.String(100), nullable=False)                # ENCRYPTED
    content = db.Column(db.Text, nullable=False)                     # ENCRYPTED; max 2000 chars
    tags = db.Column(db.JSON, default=list)
    use_count = db.Column(db.Integer, default=0, nullable=False)
    last_used_at = db.Column(db.DateTime(timezone=True))
    embedding = db.Column(db.Text)                                    # JSON-encoded float list for semantic search
    source = db.Column(db.String(20), default="manual", nullable=False)  # manual | auto_capture
    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.Index("idx_hub_knowledge_cards_bot", "bot_id"),
    )


# ── 11. Automations ────────────────────────────────────────────────────────────

class HubSystemAutomation(db.Model):
    """Immutable seed records — pre-built automation definitions."""
    __tablename__ = "hub_system_automations"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    code = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    trigger_event = db.Column(db.String(50))
    action = db.Column(db.String(50))
    default_params = db.Column(db.JSON, default=dict)
    is_active = db.Column(db.Boolean, default=True, nullable=False)


class HubBotAutomationSetting(db.Model):
    """Per-bot toggle state; NULL = inherit from official bot."""
    __tablename__ = "hub_bot_automation_settings"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    bot_id = db.Column(db.String(36), db.ForeignKey("hub_bot_identities.id", ondelete="CASCADE"), nullable=False)
    automation_id = db.Column(db.String(36), db.ForeignKey("hub_system_automations.id"), nullable=False)
    is_enabled = db.Column(db.Boolean)                               # NULL = inherit from official bot
    custom_params = db.Column(db.JSON)                               # NULL = inherit

    __table_args__ = (
        db.UniqueConstraint("bot_id", "automation_id", name="uq_hub_bas_bot_auto"),
    )


# ── 12. Inbox Items ────────────────────────────────────────────────────────────

class HubInboxItem(db.Model):
    __tablename__ = "hub_inbox_items"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    bot_id = db.Column(db.String(36), db.ForeignKey("hub_bot_identities.id", ondelete="CASCADE"), nullable=False)
    item_type = db.Column(db.String(20), nullable=False)             # task | reminder | decision | meeting | note | suggestion
    item_id = db.Column(db.String(36), nullable=False)
    is_new = db.Column(db.Boolean, default=True, nullable=False)
    dismissed_at = db.Column(db.DateTime(timezone=True))
    confirmed_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("user_id", "item_type", "item_id", name="uq_hub_inbox_user_type_item"),
        db.Index("idx_hub_inbox_user_bot_new", "user_id", "bot_id", "is_new"),
    )


class HubFollowUp(db.Model):
    """
    Unresolved commitment extracted from group conversations.
    E.g. "John said he'd send the report by Friday" — no confirmation seen.
    """
    __tablename__ = "hub_follow_ups"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    bot_id = db.Column(db.String(36), db.ForeignKey("hub_bot_identities.id", ondelete="CASCADE"), nullable=False)
    source_group_id = db.Column(db.String(36), db.ForeignKey("hub_connected_groups.id", ondelete="CASCADE"))
    source_batch_id = db.Column(db.String(36))

    commitment = db.Column(db.Text, nullable=False)      # encrypted: what was promised
    committed_by = db.Column(db.String(100))             # person who made the commitment
    due_hint = db.Column(db.String(100))                 # "by Friday", "tomorrow", "next week" — raw hint from AI
    status = db.Column(db.String(20), default="open")   # open | resolved | dismissed
    resolved_at = db.Column(db.DateTime(timezone=True))
    dismissed_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.Index("idx_hub_followups_user_bot_status", "user_id", "bot_id", "status"),
    )
