"""
Assistant Hub — Extraction worker.

run_extraction(bot_id, group_id, flask_app) pulls messages from Redis,
calls GPT-4o-mini, validates JSON output, writes extracted items to
PostgreSQL, and triggers post-extraction automation checks.

Daily call limit enforcement:
  Redis key: assistant:extract:count:{user_id}:{YYYY-MM-DD}
  Free plan: 50 calls/day  |  Pro: 500  |  Enterprise: unlimited

Extraction lock (prevents concurrent workers on same group):
  Redis key: assistant:lock:{bot_id}:{group_id}   TTL 90 seconds
"""
import json
import logging
import os
import re
from datetime import datetime, date, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

_log = logging.getLogger(__name__)


def _resolve_tz(tz_name):
    """IANA name → tzinfo, or None (treat as UTC) on any failure."""
    if not tz_name or ZoneInfo is None:
        return None
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return None


def _user_timezone(user_id) -> str:
    """The user's configured Hub timezone (IANA name), defaulting to UTC."""
    from .hub_models import HubMemoryGlobal
    mg = HubMemoryGlobal.query.filter_by(user_id=user_id).first()
    return (mg.timezone if mg and mg.timezone else "UTC") or "UTC"

# ── Daily limits per plan ──────────────────────────────────────────────────────
_DAILY_LIMITS = {"free": 50, "pro": 500, "enterprise": 999_999}

# ── Output schema validation ───────────────────────────────────────────────────
_ARRAY_FIELDS = ("tasks", "reminders", "decisions", "meetings", "important_notes", "follow_ups")

# ── Meeting reminder ladder ─────────────────────────────────────────────────────
# Multiple nudges per meeting so it isn't forgotten. (minutes_before, lead label).
_MEETING_REMINDER_LADDER = (
    (1440, "in 1 day"),
    (180, "in 3 hours"),
    (60, "in 1 hour"),
    (10, "in 10 minutes"),
)


def _meeting_reminder_enabled(bot_id) -> bool:
    """Whether the 'meeting_reminder' automation is on for this bot (default on)."""
    from .hub_models import HubSystemAutomation, HubBotAutomationSetting
    auto = HubSystemAutomation.query.filter_by(code="meeting_reminder", is_active=True).first()
    if not auto:
        return False
    setting = HubBotAutomationSetting.query.filter_by(bot_id=bot_id, automation_id=auto.id).first()
    if setting and setting.is_enabled is not None:
        return setting.is_enabled
    return bool((auto.default_params or {}).get("default_enabled", True))


def rebuild_meeting_reminders(meeting, tz_name: str | None = None) -> int:
    """(Re)build the Telegram reminder ladder for ONE HubMeeting, keyed by
    meeting_id so it's idempotent on edit/re-sync. Used for manual + reverse-synced
    meetings (the extraction path builds its own ladder inline). Respects the
    meeting_reminder automation toggle and only schedules still-future offsets.
    The caller commits."""
    from .hub_models import HubReminder
    from .hub_crypto import _dec
    from ..models import db

    # Wipe any prior ladder for this meeting first (idempotent rebuild).
    HubReminder.query.filter_by(meeting_id=meeting.id).delete()
    if not meeting.scheduled_at:
        return 0
    if not _meeting_reminder_enabled(meeting.bot_id):
        return 0

    scheduled_at = meeting.scheduled_at
    if scheduled_at.tzinfo is not None:
        scheduled_at = scheduled_at.astimezone(timezone.utc).replace(tzinfo=None)

    tz = _resolve_tz(tz_name or _user_timezone(meeting.user_id))
    raw_title = (_dec(meeting.title) or "").strip()
    label = raw_title if (raw_title and raw_title.lower() != "meeting") else "Meeting"
    local_start = scheduled_at.replace(tzinfo=timezone.utc).astimezone(tz) if tz else scheduled_at
    when = local_start.strftime("%b %d, %H:%M")

    now = datetime.utcnow()
    created = 0
    for minutes_before, lead_label in _MEETING_REMINDER_LADDER:
        remind_at = scheduled_at - timedelta(minutes=minutes_before)
        if remind_at < now:
            continue
        db.session.add(HubReminder(
            user_id=meeting.user_id,
            bot_id=meeting.bot_id,
            source_group_id=meeting.source_group_id,
            content=f"{label} {lead_label} (starts {when})",
            remind_at=remind_at,
            source="meeting",
            meeting_id=meeting.id,
        ))
        created += 1
    return created


def run_extraction(bot_id: str, group_id: str, flask_app) -> dict:
    """
    Main entry point. Safe to call from Celery workers.
    Returns a summary dict for logging.
    """
    try:
        with flask_app.app_context():
            return _run(bot_id, group_id)
    except Exception as exc:
        _log.error("hub_extraction: unhandled error bot=%s group=%s: %s", bot_id, group_id, exc)
        return {"status": "error", "error": str(exc)}


def _run(bot_id: str, group_id: str) -> dict:
    import redis as _redis_module
    from ..assistant.hub_models import (
        HubConnectedGroup, HubBotIdentity, HubExtractionBatch,
        HubTask, HubReminder, HubDecision, HubMeeting, HubNote, HubInboxItem,
        HubMemoryGlobal, HubMemoryPerson, HubMemoryProject, HubMemoryGroupContext,
        HubBotSettings,
    )
    from ..models import db, User

    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    r = _redis_module.from_url(redis_url, decode_responses=True)

    # ── Acquire extraction lock ───────────────────────────────────────────────
    lock_key = f"assistant:lock:{bot_id}:{group_id}"
    acquired = r.set(lock_key, "1", nx=True, ex=90)
    if not acquired:
        return {"status": "locked"}

    try:
        return _do_extract(bot_id, group_id, r)
    finally:
        r.delete(lock_key)


def _has_ai_key(user) -> bool:
    """Lightweight, side-effect-free check for whether ANY AI key will resolve for
    this user — a personal/workspace key OR the platform OpenRouter key. Mirrors the
    resolution order of resolve_ai_provider_for_group WITHOUT its quota-increment
    side effect (so it's safe to call on every extraction tick)."""
    try:
        from ..models import UserApiKey
        from .. import secret_vault as _sv
        if UserApiKey.query.filter_by(user_id=user.id, is_active=True).first():
            return True
        if _sv.get_secret("PLATFORM_OPENROUTER_API_KEY"):
            return True
    except Exception as exc:
        _log.debug("hub_extraction: _has_ai_key check failed: %s", exc)
        # On error, assume a key may exist so we don't wrongly block extraction.
        return True
    return False


def _do_extract(bot_id: str, group_id: str, r) -> dict:
    import redis as _redis_module
    from ..assistant.hub_models import (
        HubConnectedGroup, HubBotIdentity, HubExtractionBatch,
        HubTask, HubReminder, HubDecision, HubMeeting, HubNote, HubInboxItem,
        HubMemoryGlobal, HubMemoryPerson, HubMemoryProject, HubMemoryGroupContext,
        HubBotSettings,
    )
    from ..models import db, User
    from ..config import Config

    # ── Load group record ─────────────────────────────────────────────────────
    group = HubConnectedGroup.query.get(group_id)
    if not group or not group.is_active or not group.consent_confirmed_at:
        return {"status": "skip", "reason": "group inactive or no consent"}

    user = User.query.get(group.user_id)
    if not user:
        return {"status": "skip", "reason": "user not found"}

    # The user's Hub timezone drives both how the AI interprets relative times
    # ("in 1 hour") and how stored UTC datetimes are localised for display/DMs.
    tz_name = _user_timezone(group.user_id)

    # ── AI key pre-check ──────────────────────────────────────────────────────
    # Extraction only advances last_batch_at after a SUCCESSFUL AI call. If no key
    # resolves, bail BEFORE consuming the buffer so the messages aren't lost — they
    # stay queued and process automatically the moment a key is configured. Logged
    # loudly so "Last activity: never" explains itself in the logs.
    if not _has_ai_key(user):
        buffered = r.llen(f"assistant:buffer:{bot_id}:{group_id}")
        _log.warning(
            "[hub] extraction SKIPPED — no AI key for user=%s. %s message(s) left "
            "buffered (not lost). Add a key in Settings → AI or set "
            "PLATFORM_OPENROUTER_API_KEY, then they'll process automatically.",
            group.user_id, buffered,
        )
        return {"status": "no_ai_key", "buffered": buffered}

    # ── Daily limit check ─────────────────────────────────────────────────────
    plan = getattr(user, "subscription_tier", "free") or "free"
    today_str = date.today().isoformat()
    count_key = f"assistant:extract:count:{group.user_id}:{today_str}"
    daily_count = int(r.get(count_key) or 0)
    limit = _DAILY_LIMITS.get(plan, 50)
    if daily_count >= limit:
        _log.info("hub_extraction: daily limit reached user=%s plan=%s", group.user_id, plan)
        return {"status": "limit_reached"}

    # ── Pull messages from buffer ──────────────────────────────────────────────
    buffer_key = f"assistant:buffer:{bot_id}:{group_id}"
    raw_messages = r.lrange(buffer_key, 0, -1)
    # TEMP DIAGNOSTIC: how many buffered messages this extraction run found. If
    # this logs >0 but no items appear, the AI call/key is the problem (the next
    # log line will be "OpenAI call failed").
    _log.info("[hub] hub_extraction run: bot=%s group=%s buffered=%d plan=%s",
              bot_id, group_id, len(raw_messages), plan)
    if not raw_messages:
        return {"status": "empty"}

    # Atomically clear the buffer (messages we're about to process)
    r.delete(buffer_key)
    r.delete(f"assistant:priority:{bot_id}:{group_id}")

    messages = []
    for raw in raw_messages:
        try:
            messages.append(json.loads(raw))
        except json.JSONDecodeError:
            pass

    if not messages:
        return {"status": "empty"}

    # ── Create batch record ───────────────────────────────────────────────────
    batch = HubExtractionBatch(
        bot_id=bot_id,
        group_id=group_id,
        user_id=group.user_id,
        message_count=len(messages),
        status="pending",
    )
    db.session.add(batch)
    db.session.flush()  # get batch.id

    try:
        result = _call_openai(
            user=user,
            group=group,
            messages=messages,
            bot_id=bot_id,
            r=r,
            tz_name=tz_name,
        )
    except Exception as exc:
        batch.status = "failed"
        batch.error_message = str(exc)[:500]
        batch.completed_at = datetime.utcnow()
        db.session.commit()
        _log.error("hub_extraction: OpenAI call failed batch=%s: %s", batch.id, exc)
        return {"status": "error", "error": str(exc)}

    # ── Validate output ───────────────────────────────────────────────────────
    validated, tokens_used, model_used = result
    batch.tokens_used = tokens_used
    batch.model_used = model_used

    # ── Write extracted items ─────────────────────────────────────────────────
    counts = _write_items(validated, group, bot_id, batch.id, db, tz_name)

    # Mark batch complete
    total_items = sum(counts.values())
    batch.status = "complete" if total_items > 0 else "empty"
    batch.completed_at = datetime.utcnow()
    group.last_batch_at = datetime.utcnow()

    # Increment daily extraction counter (expires at midnight UTC + 1 day)
    pipe = r.pipeline()
    pipe.incr(count_key)
    pipe.expireat(count_key, int((datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).timestamp()))
    pipe.execute()

    db.session.commit()

    # ── Post-extraction automation triggers ───────────────────────────────────
    _run_automation_triggers(validated, group, bot_id, batch.id, db, tz_name)

    # ── Immediate Google Calendar push ────────────────────────────────────────
    # If the owner enabled auto-sync, push the dated meetings we just created right
    # away instead of waiting for the 5-min scheduler tick. Best-effort: the helper
    # never raises and records any failure on the token for the UI to surface.
    if counts.get("meetings"):
        try:
            from ..routes.calendar import sync_pending_meetings_for_user
            sync_pending_meetings_for_user(group.user_id)
        except Exception as exc:
            _log.warning("post-extraction calendar push failed group=%s: %s", group_id, exc)

    _log.info(
        "hub_extraction: batch=%s group=%s tasks=%d reminders=%d decisions=%d meetings=%d",
        batch.id, group_id, counts.get("tasks", 0), counts.get("reminders", 0),
        counts.get("decisions", 0), counts.get("meetings", 0),
    )
    return {"status": "complete", "counts": counts, "tokens": tokens_used}


def _call_openai(user, group, messages: list, bot_id: str, r, tz_name: str = "UTC") -> tuple:
    """Returns (validated_dict, tokens_used, model_used)."""
    from openai import OpenAI
    from .ai_key_resolver import resolve_ai_provider_for_group, QuotaExceededError, record_token_usage

    try:
        # group.id is the Hub connected-group UUID — NOT the integer telegram_groups.id
        # that UserApiKey.group_id expects. Passing the UUID as group_id makes Postgres
        # reject the query ("invalid input syntax for type integer"), which aborts the
        # whole transaction and silently kills every extraction. Match on the Telegram
        # chat id instead (string column), then fall through to workspace/platform key.
        key_config = resolve_ai_provider_for_group(
            user.id, telegram_group_id=group.telegram_group_id
        )
    except QuotaExceededError:
        raise RuntimeError("Daily AI quota exceeded")

    if not key_config.get("api_key"):
        raise RuntimeError("No AI API key configured")

    client_kwargs = {"api_key": key_config["api_key"]}
    if key_config.get("base_url"):
        client_kwargs["base_url"] = key_config["base_url"]
    client = OpenAI(**client_kwargs)
    model = key_config.get("model") or "gpt-4o-mini"
    _key_source = key_config.get("source", "unknown")

    memory_context = _build_memory_context(user.id, group.id)
    formatted = _format_messages(messages)
    group_name = group.group_name or f"Group {group.telegram_group_id}"
    tz = _resolve_tz(tz_name)
    now_local = datetime.now(tz) if tz else datetime.utcnow()

    system_prompt = (
        "You are an intelligent meeting assistant. Extract structured information "
        "from the following group conversation. Return valid JSON only. "
        "Do not hallucinate. If a field is unknown, use null.\n\n"
        f"Context about this user and team:\n{memory_context}\n\n"
        "Extract the following from the conversation:\n"
        "- tasks: array of {title, assignee (name only or null), due_date (ISO 8601 date or null), priority (low/normal/high)}\n"
        "- reminders: array of {content, remind_at (ISO 8601 datetime or null)}\n"
        "- decisions: array of {content, made_by (name or null)}\n"
        "- meetings: array of {title, scheduled_at (ISO 8601 datetime or null), participants (name array), meeting_url (Zoom/Meet/Calendly/Teams URL found in the message or null)}\n"
        "- important_notes: array of {content}\n"
        "- follow_ups: array of {commitment, committed_by (name or null), due_hint (e.g. 'by Friday', 'tomorrow', null)}\n"
        "  A follow_up is a commitment or promise made by someone that has NOT been confirmed as done in this conversation.\n"
        "  Examples: 'I'll send the report tomorrow', 'John will follow up on the client', 'We need to review this before Thursday'.\n"
        "  Do NOT include items that were already confirmed or completed in the same conversation.\n\n"
        "Rules:\n"
        "- Only extract items clearly present in the conversation\n"
        "- Do not infer or assume details not explicitly stated\n"
        "- If nothing relevant exists, return empty arrays\n"
        "- Return JSON only, no explanation text"
    )

    user_prompt = (
        f"Conversation from {group_name}.\n"
        f"The user's current local date and time is "
        f"{now_local.strftime('%Y-%m-%d %H:%M')} (timezone {tz_name}).\n"
        f"Resolve all relative times (\"in 1 hour\", \"tomorrow 3pm\", \"Friday\") "
        f"against that, and output every date/time as ISO 8601 in the user's local "
        f"timezone ({tz_name}).\n\n{formatted}"
    )

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
        max_tokens=1000,
        response_format={"type": "json_object"},
    )

    tokens_used = resp.usage.total_tokens if resp.usage else 0
    model_used = resp.model or model
    if _key_source == "platform":
        record_token_usage(user, tokens_used)
    raw_json = resp.choices[0].message.content or "{}"

    validated = _validate_output(raw_json)
    return validated, tokens_used, model_used


def _format_messages(messages: list) -> str:
    lines = []
    for m in messages:
        ts = m.get("ts", "")
        # Format: [HH:MM] Sender: text
        try:
            dt = datetime.fromisoformat(ts)
            time_str = dt.strftime("%H:%M")
        except (ValueError, TypeError):
            time_str = "?"
        lines.append(f"[{time_str}] {m.get('sender', '?')}: {m.get('text', '')}")
    return "\n".join(lines)


def _build_memory_context(user_id: int, group_id: str) -> str:
    from ..assistant.hub_models import (
        HubMemoryGlobal, HubMemoryPerson, HubMemoryProject, HubMemoryGroupContext,
    )

    parts = []

    mg = HubMemoryGlobal.query.filter_by(user_id=user_id).first()
    if mg:
        who = mg.preferred_name or ""
        if mg.role and mg.company_name:
            who += f", {mg.role} at {mg.company_name}"
        elif mg.company_name:
            who += f" at {mg.company_name}"
        if who:
            parts.append(f"User: {who}")
        if mg.current_priorities:
            parts.append(f"Priorities: {', '.join(str(p) for p in mg.current_priorities[:3])}")

    gc = HubMemoryGroupContext.query.filter_by(user_id=user_id, group_id=group_id).first()
    if gc and gc.current_focus:
        parts.append(f"This group focus: {gc.current_focus}")

    people = HubMemoryPerson.query.filter_by(user_id=user_id).limit(10).all()
    if people:
        team = ", ".join(
            f"{p.name} ({p.role})" if p.role else p.name
            for p in people
        )
        parts.append(f"Team: {team}")

    projects = HubMemoryProject.query.filter_by(user_id=user_id).filter(
        HubMemoryProject.status.in_(["active", "in progress", None])
    ).limit(5).all()
    if projects:
        parts.append(f"Active projects: {', '.join(p.name for p in projects)}")

    context = ". ".join(parts).strip()

    # Cap at ~400 tokens (~1600 chars)
    if len(context) > 1600:
        context = context[:1600]

    return context or "No additional context available."


def _validate_output(raw_json: str) -> dict:
    """Validate and normalise the AI JSON output. Returns a safe dict."""
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        # Try to extract JSON substring if model prepended text
        m = re.search(r'\{.*\}', raw_json, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group())
            except json.JSONDecodeError:
                return {f: [] for f in _ARRAY_FIELDS}
        else:
            return {f: [] for f in _ARRAY_FIELDS}

    if not isinstance(data, dict):
        return {f: [] for f in _ARRAY_FIELDS}

    result = {}
    for field in _ARRAY_FIELDS:
        raw = data.get(field, [])
        result[field] = raw if isinstance(raw, list) else []

    return result


def _write_items(validated: dict, group, bot_id: str, batch_id: str, db, tz_name: str = "UTC") -> dict:
    from ..assistant.hub_models import (
        HubTask, HubReminder, HubDecision, HubMeeting, HubNote, HubInboxItem, HubFollowUp,
    )
    tz = _resolve_tz(tz_name)
    # Import once at the top — _enc is used by EVERY item type below (tasks,
    # reminders, decisions, meetings, notes, follow-ups). It used to be imported
    # inside the tasks loop, so a message that produced only a meeting/reminder
    # (no task) left _enc unbound → "cannot access local variable '_enc'", which
    # crashed extraction for every scheduling/meeting message.
    from ..assistant.hub_crypto import _enc

    counts = {"tasks": 0, "reminders": 0, "decisions": 0, "meetings": 0, "notes": 0, "follow_ups": 0}
    user_id = group.user_id

    def _add_inbox(item_type: str, item_id: str):
        try:
            inbox = HubInboxItem(
                user_id=user_id,
                bot_id=bot_id,
                item_type=item_type,
                item_id=item_id,
                is_new=True,
            )
            db.session.add(inbox)
        except Exception:
            pass

    # Tasks
    for t in validated.get("tasks", []):
        if not isinstance(t, dict) or not t.get("title"):
            continue
        if not group.extract_tasks:
            continue
        due = _parse_date(t.get("due_date"))
        priority = t.get("priority", "normal")
        if priority not in ("low", "normal", "high"):
            priority = "normal"
        task = HubTask(
            user_id=user_id,
            bot_id=bot_id,
            source_group_id=group.id,
            title=_enc(str(t["title"])[:500]),
            assignee_name=str(t.get("assignee", "") or "")[:100] or None,
            due_date=due,
            priority=priority,
            status="pending",
            source="extracted",
            source_batch_id=batch_id,
        )
        db.session.add(task)
        db.session.flush()
        _add_inbox("task", task.id)
        counts["tasks"] += 1

    # Reminders
    for rem in validated.get("reminders", []):
        if not isinstance(rem, dict) or not rem.get("content"):
            continue
        if not group.extract_reminders:
            continue
        remind_at = _parse_datetime(rem.get("remind_at"), tz) or (datetime.utcnow() + timedelta(hours=24))
        reminder = HubReminder(
            user_id=user_id,
            bot_id=bot_id,
            source_group_id=group.id,
            content=_enc(str(rem["content"])[:500]),
            remind_at=remind_at,
            source="extracted",
            source_batch_id=batch_id,
        )
        db.session.add(reminder)
        db.session.flush()
        _add_inbox("reminder", reminder.id)
        counts["reminders"] += 1

    # Decisions
    for dec in validated.get("decisions", []):
        if not isinstance(dec, dict) or not dec.get("content"):
            continue
        if not group.extract_decisions:
            continue
        decision = HubDecision(
            user_id=user_id,
            bot_id=bot_id,
            source_group_id=group.id,
            content=_enc(str(dec["content"])[:1000]),
            made_by=str(dec.get("made_by", "") or "")[:100] or None,
            source_batch_id=batch_id,
        )
        db.session.add(decision)
        db.session.flush()
        _add_inbox("decision", decision.id)
        counts["decisions"] += 1

    # Meetings
    for mtg in validated.get("meetings", []):
        if not isinstance(mtg, dict):
            continue
        if not group.extract_meetings:
            continue
        title = str(mtg.get("title", "") or "Meeting")[:255]
        scheduled_at = _parse_datetime(mtg.get("scheduled_at"), tz)
        participants = mtg.get("participants", [])
        if not isinstance(participants, list):
            participants = []
        participants = [str(p) for p in participants[:20]]
        raw_url = mtg.get("meeting_url") or ""
        meeting_url = str(raw_url)[:500] if raw_url and raw_url.startswith("http") else None
        meeting = HubMeeting(
            user_id=user_id,
            bot_id=bot_id,
            source_group_id=group.id,
            title=_enc(title),
            scheduled_at=scheduled_at,
            participants=participants,
            meeting_url=meeting_url,
            source_batch_id=batch_id,
        )
        db.session.add(meeting)
        db.session.flush()
        _add_inbox("meeting", meeting.id)
        counts["meetings"] += 1

    # Important notes
    for note_item in validated.get("important_notes", []):
        if not isinstance(note_item, dict) or not note_item.get("content"):
            continue
        note = HubNote(
            user_id=user_id,
            bot_id=bot_id,
            source_group_id=group.id,
            content=_enc(str(note_item["content"])[:2000]),
            source="extracted",
            source_batch_id=batch_id,
        )
        db.session.add(note)
        db.session.flush()
        _add_inbox("note", note.id)
        counts["notes"] += 1

    # Follow-ups (unresolved commitments)
    for fu in validated.get("follow_ups", []):
        if not isinstance(fu, dict) or not fu.get("commitment"):
            continue
        followup = HubFollowUp(
            user_id=user_id,
            bot_id=bot_id,
            source_group_id=group.id,
            source_batch_id=batch_id,
            commitment=_enc(str(fu["commitment"])[:500]),
            committed_by=str(fu.get("committed_by", "") or "")[:100] or None,
            due_hint=str(fu.get("due_hint", "") or "")[:100] or None,
            status="open",
        )
        db.session.add(followup)
        db.session.flush()
        _add_inbox("follow_up", followup.id)
        counts["follow_ups"] += 1

    return counts


def _run_automation_triggers(validated: dict, group, bot_id: str, batch_id: str, db, tz_name: str = "UTC") -> None:
    """
    Post-extraction: check enabled automations and create follow-up items.
    Currently handles: meeting_reminder, deadline_alert.
    """
    try:
        from ..assistant.hub_models import HubReminder, HubBotAutomationSetting, HubSystemAutomation
        user_id = group.user_id
        tz = _resolve_tz(tz_name)

        # Determine which automations are enabled for this bot
        def _is_enabled(code: str) -> bool:
            auto = HubSystemAutomation.query.filter_by(code=code, is_active=True).first()
            if not auto:
                return False
            setting = HubBotAutomationSetting.query.filter_by(
                bot_id=bot_id, automation_id=auto.id
            ).first()
            if setting and setting.is_enabled is not None:
                return setting.is_enabled
            # Fall back to seed default_enabled flag stored in default_params
            return bool((auto.default_params or {}).get("default_enabled", True))

        # Meeting reminders: a ladder of nudges before each meeting so it isn't
        # missed (1 day / 3 hours / 1 hour / 10 minutes before). Only offsets that
        # are still in the future get a reminder; delivery is handled by the
        # throttled, anti-ban-safe HubReminder delivery job.
        if _is_enabled("meeting_reminder"):
            now = datetime.utcnow()
            for mtg in validated.get("meetings", []):
                scheduled_at = _parse_datetime(mtg.get("scheduled_at"), tz)
                if not scheduled_at:
                    continue
                # Build a clean label. mtg.get("title", "Meeting") would return a
                # literal None when the AI emits {"title": null}, which previously
                # rendered as "Meeting in 1 hour: None" in the Hub, DMs and digest.
                raw_title = str(mtg.get("title") or "").strip()
                label = raw_title if (raw_title and raw_title.lower() != "meeting") else "Meeting"
                # Stamp the meeting's start time (in the user's local timezone) so
                # reminders are distinguishable even when several meetings share the
                # generic "Meeting" title. scheduled_at is naive UTC.
                local_start = (
                    scheduled_at.replace(tzinfo=timezone.utc).astimezone(tz)
                    if tz else scheduled_at
                )
                when = local_start.strftime("%b %d, %H:%M")
                for minutes_before, lead_label in _MEETING_REMINDER_LADDER:
                    remind_at = scheduled_at - timedelta(minutes=minutes_before)
                    if remind_at < now:
                        continue  # this lead time has already passed
                    reminder = HubReminder(
                        user_id=user_id,
                        bot_id=bot_id,
                        source_group_id=group.id,
                        content=f"{label} {lead_label} (starts {when})",
                        remind_at=remind_at,
                        source="extracted",
                        source_batch_id=batch_id,
                    )
                    db.session.add(reminder)

        # Deadline alerts: DM immediately for tasks with due_date
        if _is_enabled("deadline_alert"):
            urgent_tasks = [
                t for t in validated.get("tasks", [])
                if isinstance(t, dict) and t.get("due_date") and t.get("title")
            ]
            if urgent_tasks:
                _send_deadline_alert_dm(user_id, urgent_tasks, bot_id=bot_id)

        # High-priority task alert: DM for high-priority tasks
        if _is_enabled("high_priority_alert"):
            hp_tasks = [
                t for t in validated.get("tasks", [])
                if isinstance(t, dict) and t.get("priority") == "high" and t.get("title")
            ]
            if hp_tasks:
                _send_deadline_alert_dm(user_id, hp_tasks, subject="🔴 High-priority tasks extracted:", bot_id=bot_id)

        # Follow-up reminder: create a reminder 2 days from now for each open follow-up
        if _is_enabled("follow_up_reminder"):
            auto = HubSystemAutomation.query.filter_by(code="follow_up_reminder").first()
            offset_days = 2
            if auto and auto.default_params:
                offset_days = int(auto.default_params.get("offset_days", 2))
            for fu in validated.get("follow_ups", []):
                if not isinstance(fu, dict) or not fu.get("commitment"):
                    continue
                remind_at = datetime.utcnow() + timedelta(days=offset_days)
                commitment_text = str(fu["commitment"])[:300]
                by = fu.get("committed_by")
                label = f"Follow-up: {commitment_text}"
                if by:
                    label = f"Follow-up ({by}): {commitment_text}"
                reminder = HubReminder(
                    user_id=user_id,
                    bot_id=bot_id,
                    source_group_id=group.id,
                    content=label[:500],
                    remind_at=remind_at,
                    source="extracted",
                    source_batch_id=batch_id,
                )
                db.session.add(reminder)

        # Decision log: save each decision as a Note
        if _is_enabled("decision_digest"):
            from ..assistant.hub_models import HubNote
            for dec in validated.get("decisions", []):
                if not isinstance(dec, dict) or not dec.get("content"):
                    continue
                content = str(dec["content"])[:2000]
                by = dec.get("made_by")
                note_text = f"Decision: {content}"
                if by:
                    note_text = f"Decision by {by}: {content}"
                note = HubNote(
                    user_id=user_id,
                    bot_id=bot_id,
                    source_group_id=group.id,
                    content=note_text,
                    source="extracted",
                    source_batch_id=batch_id,
                )
                db.session.add(note)

        db.session.commit()

    except Exception as exc:
        _log.debug("hub_extraction: automation trigger error: %s", exc)


def _send_deadline_alert_dm(user_id: int, tasks: list, subject: str = "⚠️ *New tasks with deadlines extracted:*\n", bot_id: str = None) -> None:
    """Send an immediate Telegram DM for tasks with deadlines or high-priority tasks."""
    try:
        from ..models import User, UserTelegramAccount
        from .hub_token import resolve_hub_send_token

        user = User.query.get(user_id)
        if not user:
            return

        # Find linked Telegram account
        tg_account = UserTelegramAccount.query.filter_by(user_id=user_id).first()
        tg_id = (tg_account.telegram_user_id if tg_account else None) or getattr(user, "telegram_user_id", None)
        if not tg_id:
            return

        # Assistant-lineage DM — send via Echo / the custom assistant bot, not the
        # group-management bot.
        bot_token = resolve_hub_send_token(bot_id)
        if not bot_token:
            return

        lines = [subject]
        for t in tasks[:5]:
            lines.append(f"• {t['title']} — due {t['due_date']}")
        text = "\n".join(lines)

        from ..telegram_safe import safe_send_message
        safe_send_message(bot_token, tg_id, text, parse_mode="Markdown")
    except Exception as exc:
        _log.debug("hub_extraction: deadline alert DM failed: %s", exc)


# ── Date/time parsers ─────────────────────────────────────────────────────────

def _parse_date(value) -> "date | None":
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def _parse_datetime(value, tz=None) -> "datetime | None":
    """Parse an AI-emitted datetime into NAIVE UTC for storage.

    The AI is told the current local time and asked to emit datetimes in the
    user's local timezone. ``tz`` (a tzinfo) is that timezone:
    - tz-aware input → converted to UTC.
    - naive input + tz given → interpreted as local wall-clock, then → UTC.
    - naive input + no tz → assumed already UTC (legacy behaviour).
    """
    if not value:
        return None
    try:
        s = str(value)
        # Accept YYYY-MM-DD as a date → noon local (so it lands on the right day).
        if len(s) == 10:
            dt = datetime.fromisoformat(s).replace(hour=12, minute=0)
        else:
            s = s.replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    if tz is not None:
        return dt.replace(tzinfo=tz).astimezone(timezone.utc).replace(tzinfo=None)
    return dt
