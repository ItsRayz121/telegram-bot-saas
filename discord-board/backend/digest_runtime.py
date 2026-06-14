"""Daily server digest (Phase 16). Config lives in GuildSettings.extra["digest"];
the bot's content_loop posts once per day after the configured UTC hour. Stats
come from GuildDailyStat; an AI polish is applied when configured (plain stats
otherwise).
"""
from __future__ import annotations

import logging
from datetime import datetime

from database import SessionLocal
from models import GuildDailyStat, GuildSettings, Member

log = logging.getLogger("guildizer.digest")

DIGEST_DEFAULTS = {
    "enabled": False, "channel_id": None, "hour_utc": 18,
    # Phase 3 parity — cadence. daily | weekly | monthly. `weekday` (0=Mon..6=Sun)
    # is only used for weekly; monthly posts on the 1st. last_day = the date we
    # last posted (period de-dupe is derived from it).
    "cadence": "daily", "weekday": 0, "last_day": None,
}

_CADENCE_LABEL = {"daily": "Daily", "weekly": "Weekly", "monthly": "Monthly"}


def _cadence_due(cfg: dict, now: datetime) -> bool:
    """True if a digest of this cadence should post at `now` (caller has already
    checked it wasn't posted today)."""
    cadence = cfg.get("cadence") or "daily"
    if cadence == "weekly":
        try:
            target = max(0, min(6, int(cfg.get("weekday", 0))))
        except (TypeError, ValueError):
            target = 0
        return now.weekday() == target
    if cadence == "monthly":
        return now.day == 1
    return True  # daily


def get_config(guild_id: int) -> dict:
    db = SessionLocal()
    try:
        row = db.get(GuildSettings, guild_id)
        stored = ((row.extra or {}).get("digest") or {}) if row else {}
        return {**DIGEST_DEFAULTS, **stored}
    finally:
        db.close()
        SessionLocal.remove()


def due_guilds(served_guild_ids: list[int]) -> list[dict]:
    """Guilds whose digest should post now: enabled, channel set, hour reached,
    not yet posted today."""
    if not served_guild_ids:
        return []
    now = datetime.utcnow()
    today = now.strftime("%Y-%m-%d")
    out = []
    db = SessionLocal()
    try:
        rows = (
            db.query(GuildSettings)
            .filter(GuildSettings.guild_id.in_(served_guild_ids))
            .all()
        )
        for row in rows:
            cfg = {**DIGEST_DEFAULTS, **((row.extra or {}).get("digest") or {})}
            if not (cfg["enabled"] and cfg["channel_id"]):
                continue
            try:
                hour = int(cfg.get("hour_utc", 18))
            except (TypeError, ValueError):
                hour = 18
            if now.hour < hour:
                continue
            if cfg.get("last_day") == today:
                continue
            if not _cadence_due(cfg, now):
                continue
            out.append({"guild_id": row.guild_id, "channel_id": int(cfg["channel_id"]),
                        "label": _CADENCE_LABEL.get(cfg.get("cadence") or "daily", "Daily")})
    finally:
        db.close()
        SessionLocal.remove()
    return out


def mark_posted(guild_id: int) -> None:
    db = SessionLocal()
    try:
        row = db.get(GuildSettings, guild_id)
        if row is None:
            return
        extra = dict(row.extra or {})
        digest = dict(extra.get("digest") or {})
        digest["last_day"] = datetime.utcnow().strftime("%Y-%m-%d")
        extra["digest"] = digest
        row.extra = extra
        db.commit()
    finally:
        db.close()
        SessionLocal.remove()


def build_stats_text(guild_id: int, guild_name: str, label: str = "Daily") -> str:
    """Plain digest body from today's rollups + top chatter."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    db = SessionLocal()
    try:
        stat = db.get(GuildDailyStat, {"guild_id": guild_id, "day": today})
        messages = stat.messages if stat else 0
        joins = stat.joins if stat else 0
        leaves = stat.leaves if stat else 0
        midnight = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        actives = (
            db.query(Member)
            .filter(Member.guild_id == guild_id, Member.last_seen >= midnight)
            .count()
        )
        top = (
            db.query(Member)
            .filter(Member.guild_id == guild_id, Member.last_seen >= midnight)
            .order_by(Member.messages.desc())
            .first()
        )
        lines = [
            f"📊 **{label} digest — {guild_name}** ({today})",
            f"• {messages} messages from {actives} active member(s)",
            f"• {joins} joined · {leaves} left",
        ]
        if top is not None and (top.messages or 0) > 0:
            lines.append(f"• Most active: {top.username or top.user_id}")
        return "\n".join(lines)
    finally:
        db.close()
        SessionLocal.remove()
