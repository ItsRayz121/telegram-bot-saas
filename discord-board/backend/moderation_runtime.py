"""Moderation DB helpers used by the bot and the API (no discord.py, no Flask).

Warning ladder, member reports, and scheduled actions (tempban expiry). Pure
functions over the session so they unit-test standalone — same pattern as
campaign_runtime.py.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from models import MemberWarning, ModReport, ScheduledModAction

LADDER_ACTIONS = {"timeout", "kick", "ban", "none"}


# --- warnings ------------------------------------------------------------------
def add_warning(db, guild_id: int, user_id: int, username: str | None,
                moderator_id: int | None, moderator_name: str | None,
                reason: str | None, ladder_cfg: dict,
                warn_ladder: dict | None = None) -> tuple[int, dict | None]:
    """Record a warning. Returns (active_warning_count, escalation_or_None).

    The escalation dict is {"action", "minutes", "at", "reset"}. With the
    multi-step warn_ladder enabled, the highest step the member's count has
    reached fires (each step counts warnings within its own window; warnings
    are NOT reset, so later steps stay reachable). Otherwise the legacy single
    threshold fires at max_warnings with reset=True — the caller performs the
    Discord-side action and clears warnings via clear_warnings.
    """
    db.add(MemberWarning(
        guild_id=guild_id, user_id=user_id, username=(username or "")[:120] or None,
        moderator_id=moderator_id, moderator_name=(moderator_name or "")[:120] or None,
        reason=(reason or "")[:300] or None,
    ))
    db.flush()
    window = max(0, int(ladder_cfg.get("window_hours", 0) or 0))
    count = warning_count(db, guild_id, user_id, window_hours=window)

    wl = warn_ladder or {}
    if wl.get("enabled") and wl.get("steps"):
        best = None
        for step in wl["steps"]:
            action = str(step.get("action") or "")
            if action not in LADDER_ACTIONS or action == "none":
                continue
            at = max(1, int(step.get("at", 0) or 0))
            step_window = max(0, int(step.get("window_hours", 0) or 0))
            step_count = (count if step_window == window
                          else warning_count(db, guild_id, user_id, window_hours=step_window))
            if step_count >= at and (best is None or at > best["at"]):
                best = {"action": action, "at": at,
                        "minutes": max(1, int(step.get("minutes") or 30)), "reset": False}
        return count, best

    max_warnings = max(1, int(ladder_cfg.get("max_warnings", 3)))
    action = str(ladder_cfg.get("action", "timeout"))
    if count >= max_warnings and action in LADDER_ACTIONS and action != "none":
        return count, {"action": action, "at": max_warnings,
                       "minutes": max(1, int(ladder_cfg.get("timeout_minutes") or 30)),
                       "reset": True}
    return count, None


def warning_count(db, guild_id: int, user_id: int, window_hours: int = 0) -> int:
    q = db.query(MemberWarning).filter(
        MemberWarning.guild_id == guild_id, MemberWarning.user_id == user_id)
    if window_hours > 0:
        q = q.filter(MemberWarning.created_at >= datetime.utcnow() - timedelta(hours=window_hours))
    return q.count()


def list_warnings(db, guild_id: int, user_id: int | None = None, limit: int = 50):
    q = db.query(MemberWarning).filter(MemberWarning.guild_id == guild_id)
    if user_id is not None:
        q = q.filter(MemberWarning.user_id == user_id)
    return q.order_by(MemberWarning.created_at.desc()).limit(limit).all()


def remove_latest_warning(db, guild_id: int, user_id: int) -> bool:
    row = (
        db.query(MemberWarning)
        .filter(MemberWarning.guild_id == guild_id, MemberWarning.user_id == user_id)
        .order_by(MemberWarning.created_at.desc())
        .first()
    )
    if row is None:
        return False
    db.delete(row)
    return True


def clear_warnings(db, guild_id: int, user_id: int) -> int:
    n = (
        db.query(MemberWarning)
        .filter(MemberWarning.guild_id == guild_id, MemberWarning.user_id == user_id)
        .delete()
    )
    return n


# --- reports ---------------------------------------------------------------------
def create_report(db, guild_id: int, *, reporter_id: int, reporter_name: str | None,
                  target_id: int | None, target_name: str | None,
                  channel_id: int | None = None, message_id: int | None = None,
                  message_excerpt: str | None = None, reason: str | None = None) -> ModReport:
    report = ModReport(
        guild_id=guild_id,
        reporter_id=reporter_id, reporter_name=(reporter_name or "")[:120] or None,
        target_id=target_id, target_name=(target_name or "")[:120] or None,
        channel_id=channel_id, message_id=message_id,
        message_excerpt=(message_excerpt or "")[:500] or None,
        reason=(reason or "")[:300] or None,
    )
    db.add(report)
    return report


def list_reports(db, guild_id: int, status: str | None = "open", limit: int = 50):
    q = db.query(ModReport).filter(ModReport.guild_id == guild_id)
    if status:
        q = q.filter(ModReport.status == status)
    return q.order_by(ModReport.created_at.desc()).limit(limit).all()


def review_report(db, guild_id: int, report_id: int, status: str, reviewer_id: int) -> ModReport | None:
    if status not in ("actioned", "dismissed"):
        return None
    report = db.get(ModReport, report_id)
    if report is None or report.guild_id != guild_id:
        return None
    report.status = status
    report.reviewed_by = reviewer_id
    report.reviewed_at = datetime.utcnow()
    return report


# --- scheduled actions (tempban expiry) --------------------------------------------
def schedule_unban(db, guild_id: int, user_id: int, username: str | None,
                   seconds: int, reason: str | None) -> ScheduledModAction:
    row = ScheduledModAction(
        guild_id=guild_id, user_id=user_id, username=(username or "")[:120] or None,
        action="unban", reason=(reason or "")[:300] or None,
        due_at=datetime.utcnow() + timedelta(seconds=max(60, seconds)),
    )
    db.add(row)
    return row


def due_actions(db, limit: int = 25):
    return (
        db.query(ScheduledModAction)
        .filter(ScheduledModAction.done.is_(False),
                ScheduledModAction.due_at <= datetime.utcnow())
        .order_by(ScheduledModAction.due_at)
        .limit(limit)
        .all()
    )


def mark_done(db, action_id: int) -> None:
    row = db.get(ScheduledModAction, action_id)
    if row is not None:
        row.done = True
