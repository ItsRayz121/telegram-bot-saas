"""Guildizer data models (Phase 0 stubs). Grows per phase; never references Telegram models."""
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship

from database import Base


class User(Base):
    """A dashboard user, identified by their Discord account."""

    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True)          # Discord user id (snowflake)
    username = Column(String(120))
    avatar = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)

    guilds = relationship("Guild", back_populates="owner")


class Guild(Base):
    """A Discord server ('guild') the bot has been added to."""

    __tablename__ = "guilds"

    id = Column(BigInteger, primary_key=True)          # Discord guild id (snowflake)
    name = Column(String(200))
    icon = Column(String(255))
    owner_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    bot_present = Column(Boolean, default=False)
    added_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="guilds")
