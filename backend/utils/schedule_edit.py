"""Shared validation for editing a scheduled message (official and custom-bot groups).

Delivery is a DB poll on ``send_at`` / ``is_sent`` (no separate queued job), so an edit is one
row update: there is never an old and a new job. These rules keep an edit from sending or
replaying anything:
  * a one-off that has been sent (or a repeating series that has finished) cannot be edited;
  * a *changed* send time must be in the future;
  * fields not present in the request are left untouched (media, buttons, topic survive).
"""
from datetime import datetime, timezone as _stdtz
from zoneinfo import ZoneInfo

MIN_REPEAT, MAX_REPEAT = 60, 525600

# Official-bot schedules saved BEFORE this instant stored the wall time the person typed as if it were UTC,
# ignoring the timezone picker (custom-bot schedules always converted). Their stored send_at is left exactly
# as it is - it is what the scheduler will use - but they are flagged so an admin can check the time reads right.
TZ_FIX_CUTOFF = datetime(2026, 10, 11, 7, 11, 0)


def needs_tz_review(msg) -> bool:
    """Read-only: a still-pending official schedule with a non-UTC timezone that predates the fix."""
    tz = (getattr(msg, "timezone", None) or "UTC").strip()
    created = getattr(msg, "created_at", None)
    return bool(not msg.is_sent and tz.upper() not in ("UTC", "ETC/UTC", "GMT")
                and created is not None and created < TZ_FIX_CUTOFF)


class ScheduleEditError(Exception):
    def __init__(self, message, status=400, code=None):
        super().__init__(message)
        self.message, self.status, self.code = message, status, code


def to_naive_utc(value, tz_name):
    """'2026-10-12T10:00' (wall time in tz_name) or an ISO string with an offset -> naive UTC."""
    s = str(value).strip()
    if not s:
        raise ValueError("empty")
    has_offset = s.endswith("Z") or (len(s) > 10 and ("+" in s[10:] or "-" in s[11:]))
    if has_offset:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.astimezone(_stdtz.utc).replace(tzinfo=None)
    if len(s) == 16:
        s += ":00"
    try:
        zone = ZoneInfo(tz_name)
    except Exception:
        raise ScheduleEditError("Unknown timezone")
    return datetime.fromisoformat(s).replace(tzinfo=zone).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def apply_edit(msg, data, now=None):
    """Validate ``data`` and apply it to ``msg`` (a row already locked by the caller).

    Raises ScheduleEditError; the caller rolls back, so a rejected edit changes nothing.
    """
    now = now or datetime.utcnow()
    if msg.is_sent:
        raise ScheduleEditError(
            "This message has already been sent (or its repeat series has finished), so it can no longer "
            "be edited. Create a new scheduled message instead.", 409, "ALREADY_SENT")

    tz_name = (data.get("timezone") or msg.timezone or "UTC").strip() or "UTC"
    try:
        ZoneInfo(tz_name)
    except Exception:
        raise ScheduleEditError("Unknown timezone")

    if "title" in data:
        title = (data.get("title") or "").strip()
        if not title:
            raise ScheduleEditError("title cannot be empty")
        msg.title = title
    if "message_text" in data:
        text = (data.get("message_text") or "").strip()
        if not text:
            raise ScheduleEditError("message_text cannot be empty")
        msg.message_text = text

    if "repeat_interval" in data:
        raw = data.get("repeat_interval")
        if raw in (None, "", 0, "0"):
            msg.repeat_interval = None
        else:
            try:
                rep = int(raw)
            except (TypeError, ValueError):
                raise ScheduleEditError("repeat_interval must be an integer (minutes)")
            if rep < MIN_REPEAT:
                raise ScheduleEditError("repeat_interval must be at least 60 minutes")
            if rep > MAX_REPEAT:
                raise ScheduleEditError("repeat_interval must be at most 525600 minutes (1 year)")
            msg.repeat_interval = rep

    if data.get("send_at"):
        try:
            new_send = to_naive_utc(data["send_at"], tz_name)
        except ValueError:
            raise ScheduleEditError("Invalid send_at format")
        if new_send != msg.send_at:
            if new_send <= now:
                raise ScheduleEditError(
                    "The new send time must be in the future. Editing never sends immediately or "
                    "replays a past time.")
            msg.send_at = new_send

    if "stop_date" in data:
        if data.get("stop_date"):
            try:
                msg.stop_date = to_naive_utc(data["stop_date"], tz_name)
            except ValueError:
                raise ScheduleEditError("Invalid stop_date format")
        else:
            msg.stop_date = None

    msg.timezone = tz_name
    for field in ("media_url", "buttons", "pin_message", "auto_delete_after",
                  "link_preview_enabled", "topic_id"):
        if field in data:
            value = data[field]
            if field == "auto_delete_after" and value in ("", 0, "0"):
                value = None
            setattr(msg, field, value)
