"""SQLAlchemy engine/session for Guildizer. Self-contained — no Telegizer imports."""
import os
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker, scoped_session

from config import Config

# Normalize Railway's "postgres://" to the SQLAlchemy-friendly "postgresql://".
_url = Config.DATABASE_URL
if _url.startswith("postgres://"):
    _url = _url.replace("postgres://", "postgresql://", 1)

# Ensure the local sqlite instance folder exists for dev.
if _url.startswith("sqlite:///"):
    os.makedirs("instance", exist_ok=True)

engine = create_engine(_url, pool_pre_ping=True, future=True)
SessionLocal = scoped_session(sessionmaker(bind=engine, autoflush=False, future=True))
Base = declarative_base()


def init_db() -> None:
    """Create tables. Import models so they register on Base before create_all."""
    import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _self_heal_columns()


# Columns added to EXISTING tables after their first release. create_all only
# creates missing tables, so these are healed with additive ALTERs (the same
# self-heal pattern the settings layer uses for rows). Additive-only, idempotent.
_HEAL_COLUMNS = [
    ("guilds", "custom_bot_id", "INTEGER"),
    # Admin parity: platform-admin private notes on a user
    ("users", "admin_notes", "TEXT"),
    # Phase 15 CRM columns on members
    ("members", "last_seen", "TIMESTAMP"),
    ("members", "wallet", "VARCHAR(120)"),
    ("members", "admin_notes", "TEXT"),
    # Voice XP (Discord-native phase 2)
    ("members", "voice_minutes", "INTEGER"),
    # Scheduler embed builder (Discord-native phase 4)
    ("scheduled_messages", "embed", "JSON"),
    # Polls: post-later scheduling (draft / scheduled support)
    ("polls", "scheduled_at", "TIMESTAMP"),
    # KB file ingestion: extracted text + embedded chunks for semantic /ask
    ("knowledge_documents", "file_type", "VARCHAR(10)"),
    ("knowledge_documents", "content_text", "TEXT"),
    ("knowledge_documents", "chunks", "JSON"),
    # Auto-responses can double as AI knowledge for /ask
    ("auto_responses", "use_as_ai_knowledge", "BOOLEAN"),
    # Typed proof fields (Telegizer parity): text / url / uid / wallet / screenshot / …
    ("campaign_custom_fields", "field_type", "VARCHAR(20)"),
    # Campaign parity with Telegizer's CampaignManager: platform, caps, pinning,
    # post lifecycle, per-task proof fields, review reasons and dup flagging.
    ("campaign_custom_fields", "task_id", "INTEGER"),
    ("campaign_custom_fields", "example", "VARCHAR(200)"),
    ("campaign_custom_fields", "key", "VARCHAR(64)"),
    ("campaigns", "platform", "VARCHAR(40)"),
    ("campaigns", "max_participants", "INTEGER"),
    ("campaigns", "pin_message", "BOOLEAN"),
    ("campaigns", "needs_unpost", "BOOLEAN"),
    ("campaigns", "posted_at", "TIMESTAMP"),
    ("campaigns", "posted_channel_id", "BIGINT"),
    ("campaign_tasks", "platform", "VARCHAR(40)"),
    ("campaign_tasks", "reward_label", "VARCHAR(200)"),
    ("campaign_submissions", "file_url", "VARCHAR(500)"),
    ("campaign_submissions", "reviewer_name", "VARCHAR(120)"),
    ("campaign_submissions", "review_reason", "VARCHAR(500)"),
    ("campaign_submissions", "flagged", "BOOLEAN"),
    ("campaign_submissions", "flag_reason", "VARCHAR(255)"),
    ("campaign_submissions", "notify_status", "VARCHAR(16)"),
    ("campaign_submissions", "notify_error", "VARCHAR(255)"),
    # First-message verification: member passed the captcha once
    ("members", "verified", "BOOLEAN"),
    # Notification preferences (sound / web push opt-in / per-category mute)
    ("users", "notification_prefs", "JSON"),
    # Per-user UI prefs: open/closed state of collapsible settings cards
    ("users", "ui_preferences", "JSON"),
    # Account-level bring-your-own twitterapi.io key (X raid auto-verify), encrypted
    ("users", "twitter_api_key_encrypted", "TEXT"),
    # Notification & announcement system: multi-channel broadcast + delivery stats.
    ("admin_announcements", "channels", "VARCHAR(120)"),
    ("admin_announcements", "audience", "VARCHAR(50)"),
    ("admin_announcements", "delivered_count", "INTEGER"),
    ("admin_announcements", "failed_count", "INTEGER"),
    ("admin_announcements", "reach_count", "INTEGER"),
    ("admin_announcements", "sent_at", "TIMESTAMP"),
]


def _self_heal_columns() -> None:
    insp = inspect(engine)
    for table, column, ddl_type in _HEAL_COLUMNS:
        if not insp.has_table(table):
            continue
        existing = {c["name"] for c in insp.get_columns(table)}
        if column not in existing:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"))
