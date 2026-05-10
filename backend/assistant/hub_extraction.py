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
from datetime import datetime, date, timedelta

_log = logging.getLogger(__name__)

# ── Daily limits per plan ──────────────────────────────────────────────────────
_DAILY_LIMITS = {"free": 50, "pro": 500, "enterprise": 999_999}

# ── Output schema validation ───────────────────────────────────────────────────
_ARRAY_FIELDS = ("tasks", "reminders", "decisions", "meetings", "important_notes", "follow_ups")


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
    counts = _write_items(validated, group, bot_id, batch.id, db)

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
    _run_automation_triggers(validated, group, bot_id, batch.id, db)

    _log.info(
        "hub_extraction: batch=%s group=%s tasks=%d reminders=%d decisions=%d meetings=%d",
        batch.id, group_id, counts.get("tasks", 0), counts.get("reminders", 0),
        counts.get("decisions", 0), counts.get("meetings", 0),
    )
    return {"status": "complete", "counts": counts, "tokens": tokens_used}


def _call_openai(user, group, messages: list, bot_id: str, r) -> tuple:
    """Returns (validated_dict, tokens_used, model_used)."""
    from openai import OpenAI
    from .ai_key_resolver import resolve_ai_provider_for_group, QuotaExceededError, record_token_usage

    try:
        key_config = resolve_ai_provider_for_group(user.id, group_id=group.id)
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
    today = datetime.utcnow().strftime("%Y-%m-%d")

    system_prompt = (
        "You are an intelligent meeting assistant. Extract structured information "
        "from the following group conversation. Return valid JSON only. "
        "Do not hallucinate. If a field is unknown, use null.\n\n"
        f"Context about this user and team:\n{memory_context}\n\n"
        "Extract the following from the conversation:\n"
        "- tasks: array of {title, assignee (name only or null), due_date (ISO 8601 date or null), priority (low/normal/high)}\n"
        "- reminders: array of {content, remind_at (ISO 8601 datetime or null)}\n"
        "- decisions: array of {content, made_by (name or null)}\n"
        "- meetings: array of {title, scheduled_at (ISO 8601 datetime or null), participants (name array)}\n"
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

    user_prompt = f"Conversation from {group_name} on {today}:\n\n{formatted}"

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


def _write_items(validated: dict, group, bot_id: str, batch_id: str, db) -> dict:
    from ..assistant.hub_models import (
        HubTask, HubReminder, HubDecision, HubMeeting, HubNote, HubInboxItem, HubFollowUp,
    )

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
        from ..assistant.hub_crypto import _enc
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
        remind_at = _parse_datetime(rem.get("remind_at")) or (datetime.utcnow() + timedelta(hours=24))
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
        scheduled_at = _parse_datetime(mtg.get("scheduled_at"))
        participants = mtg.get("participants", [])
        if not isinstance(participants, list):
            participants = []
        participants = [str(p) for p in participants[:20]]
        meeting = HubMeeting(
            user_id=user_id,
            bot_id=bot_id,
            source_group_id=group.id,
            title=_enc(title),
            scheduled_at=scheduled_at,
            participants=participants,
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


def _run_automation_triggers(validated: dict, group, bot_id: str, batch_id: str, db) -> None:
    """
    Post-extraction: check enabled automations and create follow-up items.
    Currently handles: meeting_reminder, deadline_alert.
    """
    try:
        from ..assistant.hub_models import HubReminder, HubBotAutomationSetting, HubSystemAutomation
        user_id = group.user_id

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

        # Meeting reminders: create reminder 60 min before each meeting
        if _is_enabled("meeting_reminder"):
            for mtg in validated.get("meetings", []):
                scheduled_at = _parse_datetime(mtg.get("scheduled_at"))
                if not scheduled_at:
                    continue
                remind_at = scheduled_at - timedelta(minutes=60)
                if remind_at < datetime.utcnow():
                    continue  # already past
                title = str(mtg.get("title", "Meeting"))[:200]
                reminder = HubReminder(
                    user_id=user_id,
                    bot_id=bot_id,
                    source_group_id=group.id,
                    content=f"Meeting in 1 hour: {title}",
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
                _send_deadline_alert_dm(user_id, urgent_tasks)

        # High-priority task alert: DM for high-priority tasks
        if _is_enabled("high_priority_alert"):
            hp_tasks = [
                t for t in validated.get("tasks", [])
                if isinstance(t, dict) and t.get("priority") == "high" and t.get("title")
            ]
            if hp_tasks:
                _send_deadline_alert_dm(user_id, hp_tasks, subject="🔴 High-priority tasks extracted:")

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


def _send_deadline_alert_dm(user_id: int, tasks: list, subject: str = "⚠️ *New tasks with deadlines extracted:*\n") -> None:
    """Send an immediate Telegram DM for tasks with deadlines or high-priority tasks."""
    try:
        from ..models import User, UserTelegramAccount
        from ..config import Config
        import requests

        user = User.query.get(user_id)
        if not user:
            return

        # Find linked Telegram account
        tg_account = UserTelegramAccount.query.filter_by(user_id=user_id).first()
        tg_id = (tg_account.telegram_user_id if tg_account else None) or getattr(user, "telegram_user_id", None)
        if not tg_id:
            return

        bot_token = Config.TELEGRAM_BOT_TOKEN
        if not bot_token:
            return

        lines = [subject]
        for t in tasks[:5]:
            lines.append(f"• {t['title']} — due {t['due_date']}")
        text = "\n".join(lines)

        requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": tg_id, "text": text, "parse_mode": "Markdown"},
            timeout=10,
        )
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


def _parse_datetime(value) -> "datetime | None":
    if not value:
        return None
    try:
        s = str(value)
        # Accept YYYY-MM-DD as date → noon UTC
        if len(s) == 10:
            return datetime.fromisoformat(s).replace(hour=12, minute=0)
        # Strip Z suffix
        s = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        # Strip timezone info (store as naive UTC)
        return dt.replace(tzinfo=None)
    except (ValueError, TypeError):
        return None
