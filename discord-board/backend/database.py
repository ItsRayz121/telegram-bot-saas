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
    # Phase 15 CRM columns on members
    ("members", "last_seen", "TIMESTAMP"),
    ("members", "wallet", "VARCHAR(120)"),
    ("members", "admin_notes", "TEXT"),
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
