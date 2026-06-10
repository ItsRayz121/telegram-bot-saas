"""SQLAlchemy engine/session for Guildizer. Self-contained — no Telegizer imports."""
import os
from sqlalchemy import create_engine
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
