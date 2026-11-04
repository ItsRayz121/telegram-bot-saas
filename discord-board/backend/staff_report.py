"""Weekly / monthly STAFF report, posted to the private mod-log channel.

Role-agnostic and built only from records Guildizer really keeps (protection_events:
automod actions, warnings, bans, role grants, approvals) - no invented metrics. The
destination is the server's existing mod-log channel; with none set, nothing is posted.
Config: GuildSettings.extra["staff_report"] = {enabled, cadence, weekday, hour_utc, last_period}.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta

from database import SessionLocal
from models import GuildSettings, ModApproval, ProtectionEvent, RoleApplication

DEFAULTS = {"enabled": False, "cadence": "weekly", "weekday": 0, "hour_utc": 9, "last_period": None}
_LABEL = {"weekly": "Weekly", "monthly": "Monthly"}


def period_key(cadence: str, now: datetime) -> str:
    if cadence == "monthly":
        return now.strftime("%Y-%m")
    iso = now.isocalendar()
    return "%d-W%02d" % (iso[0], iso[1])


def is_due(cfg: dict, now: datetime) -> bool:
    """Pure: enabled, past the configured hour, on the right day, and this period not yet sent."""
    if not cfg.get("enabled"):
        return False
    cadence = cfg.get("cadence") if cfg.get("cadence") in _LABEL else "weekly"
    try:
        if now.hour < int(cfg.get("hour_utc", 9)):
            return False
        if cadence == "weekly" and now.weekday() != max(0, min(6, int(cfg.get("weekday", 0)))):
            return False
    except (TypeError, ValueError):
        return False
    if cadence == "monthly" and now.day != 1:
        return False
    return cfg.get("last_period") != period_key(cadence, now)


def due_guilds(served_ids: list[int], now: datetime | None = None) -> list[dict]:
    now = now or datetime.utcnow()
    if not served_ids:
        return []
    out = []
    db = SessionLocal()
    try:
        for row in db.query(GuildSettings).filter(GuildSettings.guild_id.in_(served_ids)).all():
            cfg = {**DEFAULTS, **((row.extra or {}).get("staff_report") or {})}
            if is_due(cfg, now):
                out.append({"guild_id": row.guild_id, "cadence": cfg["cadence"] if cfg["cadence"] in _LABEL else "weekly"})
    finally:
        db.close()
        SessionLocal.remove()
    return out


def mark_sent(guild_id: int, cadence: str, now: datetime | None = None) -> None:
    now = now or datetime.utcnow()
    db = SessionLocal()
    try:
        row = db.get(GuildSettings, guild_id)
        if row is None:
            return
        extra = dict(row.extra or {})
        cfg = dict(extra.get("staff_report") or {})
        cfg["last_period"] = period_key(cadence, now)
        extra["staff_report"] = cfg
        row.extra = extra
        db.commit()
    finally:
        db.close()
        SessionLocal.remove()


def build_report(db, guild_id: int, guild_name: str, cadence: str, now: datetime | None = None) -> str:
    now = now or datetime.utcnow()
    since = now - timedelta(days=30 if cadence == "monthly" else 7)
    ev = db.query(ProtectionEvent).filter(ProtectionEvent.guild_id == guild_id,
                                          ProtectionEvent.created_at >= since).all()
    by_action = Counter((e.category, e.action) for e in ev)

    def n(category, *actions):
        return sum(c for (cat, act), c in by_action.items() if cat == category and (not actions or act in actions))
    automod = sum(c for (cat, act), c in by_action.items()
                  if cat not in ("role_policy", "approval", "bot_policy", "moderation") and act in
                  ("deleted", "warned", "timeout", "kick", "ban", "restricted"))
    spam = n("spam") + n("raid") + n("lockdown_join")
    pending_apps = db.query(RoleApplication).filter_by(guild_id=guild_id, status="pending").count()
    pending_appr = db.query(ModApproval).filter(ModApproval.guild_id == guild_id,
                                                ModApproval.status.in_(("pending", "reviewing"))).count()
    lines = [
        "🛡️ **%s staff report — %s** (%s → %s UTC)" % (_LABEL[cadence], guild_name, since.strftime("%b %d"), now.strftime("%b %d")),
        "• Automod actions: %d (spam / raid events: %d)" % (automod, spam),
        "• Warnings recorded: %d · bans: %d · kicks: %d" % (n("warning"), sum(c for (_, a), c in by_action.items() if a == "ban"),
                                                      sum(c for (_, a), c in by_action.items() if a == "kick")),
        "• Roles: %d level rewards · %d self-selected · %d staff grants · %d applications decided" % (
            n("role_policy", "level_grant"), n("role_policy", "self_grant"), n("role_policy", "staff_grant", "staff_revoke"),
            n("role_policy", "app_approved", "app_rejected")),
        "• Waiting on staff: %d role application(s), %d held action(s)" % (pending_apps, pending_appr),
    ]
    return "\n".join(lines)
