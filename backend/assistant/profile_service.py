"""
UserAssistantProfile — learns from user actions to personalise suggestions.

Call record_action() after each successful assistant action. The profile is
updated in-place; callers must be inside a Flask app context with an active
DB session (the caller commits, not this module).
"""
from __future__ import annotations

import logging
from datetime import datetime

_log = logging.getLogger(__name__)


def get_or_create(user_id: int):
    from ..models import db, UserAssistantProfile
    profile = UserAssistantProfile.query.filter_by(user_id=user_id).first()
    if not profile:
        profile = UserAssistantProfile(user_id=user_id)
        db.session.add(profile)
    return profile


def record_action(user_id: int, intent: str, data: dict | None = None) -> None:
    """Update learned preferences after a successful assistant action."""
    try:
        from ..models import db
        profile = get_or_create(user_id)

        if intent == "schedule_meeting":
            profile.meetings_created = (profile.meetings_created or 0) + 1
            iso = (data or {}).get("scheduled_at") or (data or {}).get("_resolved_iso")
            if iso:
                try:
                    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
                    hist = list(profile.meeting_hour_histogram or [0] * 24)
                    if len(hist) < 24:
                        hist = hist + [0] * (24 - len(hist))
                    hist[dt.hour] += 1
                    profile.meeting_hour_histogram = hist
                    profile.preferred_meeting_hour = hist.index(max(hist))
                except Exception:
                    pass

        elif intent == "create_reminder":
            profile.reminders_created = (profile.reminders_created or 0) + 1
            minutes = (data or {}).get("reminder_minutes")
            if minutes and int(minutes) > 0:
                hist = dict(profile.reminder_minutes_histogram or {})
                key = str(int(minutes))
                hist[key] = hist.get(key, 0) + 1
                profile.reminder_minutes_histogram = hist
                best = max(hist, key=hist.get)
                profile.preferred_reminder_minutes = int(best)

        elif intent == "save_note":
            profile.notes_saved = (profile.notes_saved or 0) + 1

        elif intent == "create_task":
            profile.tasks_created = (profile.tasks_created or 0) + 1

        db.session.flush()
    except Exception as exc:
        _log.warning("profile_service.record_action failed: %s", exc)


def get_preferences(user_id: int) -> dict:
    """Return learned defaults for pre-filling assistant suggestions."""
    try:
        from ..models import UserAssistantProfile
        profile = UserAssistantProfile.query.filter_by(user_id=user_id).first()
        if not profile:
            return {}
        return {
            "preferred_meeting_hour": profile.preferred_meeting_hour,
            "preferred_reminder_minutes": profile.preferred_reminder_minutes,
            "most_active_groups": profile.most_active_groups or [],
        }
    except Exception:
        return {}
