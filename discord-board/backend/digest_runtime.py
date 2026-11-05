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
    "tz": "UTC",             # IANA zone name: hour / weekday / "the 1st" are read in this zone
    "send_now": False,       # one-shot flag set by the dashboard's "Send now" button
    "last_error": None,      # why the last post failed (None = fine)
}

_CADENCE_LABEL = {"daily": "Daily", "weekly": "Weekly", "monthly": "Monthly"}


def local_now(cfg: dict, utc_now: datetime | None = None) -> datetime:
    """Naive datetime in the digest's own time zone (UTC when unset / unknown)."""
    from datetime import timezone
    utc_now = utc_now or datetime.utcnow()
    name = str(cfg.get("tz") or "UTC")
    try:
        from zoneinfo import ZoneInfo
        return utc_now.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(name)).replace(tzinfo=None)
    except Exception:  # noqa: BLE001 - unknown zone / no tzdata: fall back to UTC
        return utc_now


def rezone_last_day(digest: dict) -> None:
    """After the time zone changed, re-express `last_day` (a date in the OLD zone) in the new
    one from the exact UTC moment of the last post, so the next digest can't fire a day early/late."""
    raw = digest.get("last_posted_utc")
    if not raw:
        return
    try:
        digest["last_day"] = local_now(digest, datetime.fromisoformat(raw)).strftime("%Y-%m-%d")
    except ValueError:
        pass


def valid_tz(name: str) -> bool:
    try:
        from zoneinfo import ZoneInfo
        ZoneInfo(name)
        return True
    except Exception:  # noqa: BLE001
        return False


def _cadence_due(cfg: dict, now: datetime) -> bool:
    """True if a digest of this cadence should post at `now` (caller has already
    checked it wasn't posted today). Weekly / monthly also CATCH UP: if the bot was down on the
    scheduled day, the digest still goes out on the next day(s) instead of being skipped."""
    cadence = cfg.get("cadence") or "daily"
    last = None
    try:
        last = datetime.strptime(str(cfg.get("last_day")), "%Y-%m-%d") if cfg.get("last_day") else None
    except ValueError:
        last = None
    if cadence == "weekly":
        try:
            target = max(0, min(6, int(cfg.get("weekday", 0))))
        except (TypeError, ValueError):
            target = 0
        return now.weekday() == target or (last is not None and (now - last).days >= 8)
    if cadence == "monthly":
        if now.day == 1:
            return True
        # missed the 1st (bot down): still send within the first 3 days if this month's is outstanding
        return last is not None and now.day <= 3 and (last.year, last.month) != (now.year, now.month)
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
    utc_now = datetime.utcnow()
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
            if not cfg["channel_id"]:
                continue
            label = _CADENCE_LABEL.get(cfg.get("cadence") or "daily", "Daily")
            if cfg.get("send_now"):                       # dashboard "Send now": bypasses the schedule once
                out.append({"guild_id": row.guild_id, "channel_id": int(cfg["channel_id"]), "label": label, "manual": True})
                continue
            if not cfg["enabled"]:
                continue
            now = local_now(cfg, utc_now)                 # hour / weekday / day-of-month in the chosen zone
            today = now.strftime("%Y-%m-%d")
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
            out.append({"guild_id": row.guild_id, "channel_id": int(cfg["channel_id"]), "label": label})
    finally:
        db.close()
        SessionLocal.remove()
    return out


def mark_posted(guild_id: int, error: str | None = None) -> None:
    db = SessionLocal()
    try:
        row = db.get(GuildSettings, guild_id)
        if row is None:
            return
        extra = dict(row.extra or {})
        digest = dict(extra.get("digest") or {})
        digest["last_day"] = local_now(digest).strftime("%Y-%m-%d")
        digest["last_posted_utc"] = datetime.utcnow().isoformat()       # lets a later zone change re-express last_day
        digest["send_now"] = False
        digest["last_error"] = error          # shown on the dashboard card; cleared by the next good post
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
