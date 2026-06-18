"""Scheduled messages / polls / auto-responses dashboard endpoints (Phase 12).

  GET/POST           /api/guilds/<id>/scheduled-messages
  PUT/DELETE         /api/guilds/<id>/scheduled-messages/<mid>
  GET/POST           /api/guilds/<id>/polls
  DELETE             /api/guilds/<id>/polls/<pid>        (pending only)
  GET/POST           /api/guilds/<id>/auto-responses
  PUT/DELETE         /api/guilds/<id>/auto-responses/<rid>

All require session + can_manage. The bot picks work up from the DB
(next_run_at / needs_post) — no direct bot calls.
"""
from __future__ import annotations

from datetime import datetime

from flask import Blueprint, g, jsonify, request

import access
import plan_limits
from auth import login_required
from models import AutoResponse, Guild, GuildEvent, Poll, ScheduledMessage, UserGuild

content_bp = Blueprint("content", __name__)

RECURRENCES = {"none", "hourly", "daily", "weekly"}


def _manage_or_403(guild_id: int):
    return access.manage_or_403(g.db, g.user_id, guild_id)


def _parse_dt(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


def _clean_url(value) -> str | None:
    url = str(value or "").strip()[:512]
    return url if url.startswith(("http://", "https://")) else None


def _clean_embed(value) -> dict | None:
    """Sanitize the optional embed dict (Phase 4 embed builder). Returns None
    when no renderable field survives, so empty builders store nothing."""
    if not isinstance(value, dict):
        return None
    out = {}
    if str(value.get("title") or "").strip():
        out["title"] = str(value["title"]).strip()[:256]
    if str(value.get("description") or "").strip():
        out["description"] = str(value["description"]).strip()[:4000]
    color = str(value.get("color") or "").strip().lstrip("#")
    if len(color) == 6:
        try:
            out["color"] = f"#{int(color, 16):06x}"
        except ValueError:
            pass
    for key in ("image_url", "thumbnail_url"):
        url = _clean_url(value.get(key))
        if url:
            out[key] = url
    if str(value.get("footer") or "").strip():
        out["footer"] = str(value["footer"]).strip()[:2048]
    # color alone renders as an invisible sliver — require real content
    return out if set(out) - {"color"} else None


# --- scheduled messages -------------------------------------------------------------
@content_bp.get("/api/guilds/<int:guild_id>/scheduled-messages")
@login_required
def list_scheduled(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    rows = (
        g.db.query(ScheduledMessage)
        .filter(ScheduledMessage.guild_id == guild_id)
        .order_by(ScheduledMessage.next_run_at)
        .limit(100)
        .all()
    )
    return jsonify(messages=[r.to_dict() for r in rows])


@content_bp.post("/api/guilds/<int:guild_id>/scheduled-messages")
@login_required
def create_scheduled(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    count = (g.db.query(ScheduledMessage)
             .filter(ScheduledMessage.guild_id == guild_id).count())
    cap = plan_limits.limit(g.db, guild_id, "scheduled_messages")
    if count >= cap:
        return plan_limits.limit_response("scheduled_messages", cap)
    body = request.get_json(silent=True) or {}
    content = str(body.get("content") or "").strip()[:2000]
    embed = _clean_embed(body.get("embed"))
    channel_id = body.get("channel_id")
    next_run = _parse_dt(body.get("next_run_at"))
    if (not content and not embed) or not (channel_id and str(channel_id).isdigit()) or next_run is None:
        return jsonify(error="content_channel_and_time_required"), 400
    recurrence = body.get("recurrence") if body.get("recurrence") in RECURRENCES else "none"
    row = ScheduledMessage(
        guild_id=guild_id, channel_id=int(channel_id), content=content, embed=embed,
        recurrence=recurrence, next_run_at=next_run, created_by=g.user_id,
    )
    g.db.add(row)
    g.db.commit()
    return jsonify(message=row.to_dict()), 201


@content_bp.put("/api/guilds/<int:guild_id>/scheduled-messages/<int:mid>")
@login_required
def update_scheduled(guild_id: int, mid: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = g.db.get(ScheduledMessage, mid)
    if row is None or row.guild_id != guild_id:
        return jsonify(error="not_found"), 404
    body = request.get_json(silent=True) or {}
    if "content" in body:
        row.content = str(body["content"] or "").strip()[:2000]
    if "embed" in body:
        row.embed = _clean_embed(body["embed"])
    if not (row.content or row.embed):
        return jsonify(error="content_or_embed_required"), 400
    if body.get("channel_id") and str(body["channel_id"]).isdigit():
        row.channel_id = int(body["channel_id"])
    if body.get("recurrence") in RECURRENCES:
        row.recurrence = body["recurrence"]
    if "next_run_at" in body:
        dt = _parse_dt(body["next_run_at"])
        if dt is not None:
            row.next_run_at = dt
    if "enabled" in body:
        row.enabled = bool(body["enabled"])
    g.db.commit()
    return jsonify(message=row.to_dict())


@content_bp.delete("/api/guilds/<int:guild_id>/scheduled-messages/<int:mid>")
@login_required
def delete_scheduled(guild_id: int, mid: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = g.db.get(ScheduledMessage, mid)
    if row is None or row.guild_id != guild_id:
        return jsonify(error="not_found"), 404
    g.db.delete(row)
    g.db.commit()
    return jsonify(ok=True)


# --- Discord scheduled events (Phase 4 native) ----------------------------------------
EVENT_TYPES = {"external", "voice", "stage"}


@content_bp.get("/api/guilds/<int:guild_id>/events")
@login_required
def list_events(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    rows = (
        g.db.query(GuildEvent)
        .filter(GuildEvent.guild_id == guild_id)
        .order_by(GuildEvent.start_at.desc())
        .limit(50)
        .all()
    )
    return jsonify(events=[r.to_dict() for r in rows])


@content_bp.post("/api/guilds/<int:guild_id>/events")
@login_required
def create_event(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    body = request.get_json(silent=True) or {}
    name = str(body.get("name") or "").strip()[:100]
    entity_type = body.get("entity_type") if body.get("entity_type") in EVENT_TYPES else "external"
    start_at = _parse_dt(body.get("start_at"))
    end_at = _parse_dt(body.get("end_at")) if body.get("end_at") else None
    channel_id = body.get("channel_id")
    location = str(body.get("location") or "").strip()[:200]

    if not name or start_at is None:
        return jsonify(error="name_and_start_required"), 400
    if start_at <= datetime.utcnow():
        return jsonify(error="start_must_be_in_future"), 400
    if entity_type in ("voice", "stage") and not (channel_id and str(channel_id).isdigit()):
        return jsonify(error="channel_required_for_voice_events"), 400
    if entity_type == "external" and not location:
        return jsonify(error="location_required_for_external_events"), 400
    if end_at is not None and end_at <= start_at:
        end_at = None

    try:
        remind = max(0, min(1440, int(body.get("remind_minutes", 15))))
    except (TypeError, ValueError):
        remind = 15
    reminder_channel = body.get("reminder_channel_id")

    row = GuildEvent(
        guild_id=guild_id, name=name,
        description=str(body.get("description") or "").strip()[:1000],
        entity_type=entity_type,
        channel_id=int(channel_id) if channel_id and str(channel_id).isdigit() else None,
        location=location or None,
        start_at=start_at, end_at=end_at,
        remind_minutes=remind,
        reminder_channel_id=(int(reminder_channel)
                             if reminder_channel and str(reminder_channel).isdigit() else None),
        created_by=g.user_id,
    )
    g.db.add(row)
    g.db.commit()
    return jsonify(event=row.to_dict()), 201


@content_bp.delete("/api/guilds/<int:guild_id>/events/<int:eid>")
@login_required
def delete_event(guild_id: int, eid: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = g.db.get(GuildEvent, eid)
    if row is None or row.guild_id != guild_id:
        return jsonify(error="not_found"), 404
    if row.status == "created" and row.discord_event_id:
        # The bot owns the Discord-side delete; flag it and keep the row until done.
        row.needs_delete = True
        row.needs_create = False
        g.db.commit()
        return jsonify(event=row.to_dict())
    g.db.delete(row)
    g.db.commit()
    return jsonify(ok=True)


# --- polls ----------------------------------------------------------------------------
@content_bp.get("/api/guilds/<int:guild_id>/polls")
@login_required
def list_polls(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    rows = (
        g.db.query(Poll)
        .filter(Poll.guild_id == guild_id)
        .order_by(Poll.created_at.desc())
        .limit(50)
        .all()
    )
    return jsonify(polls=[r.to_dict() for r in rows])


def _poll_fields(body):
    """Validate & normalise the editable poll fields shared by create/edit."""
    question = str(body.get("question") or "").strip()[:300]
    answers = [str(a).strip()[:55] for a in (body.get("answers") or []) if str(a).strip()][:10]
    channel_id = body.get("channel_id")
    if not question or len(answers) < 2 or not (channel_id and str(channel_id).isdigit()):
        return None, (jsonify(error="question_two_answers_and_channel_required"), 400)
    try:
        duration = max(1, min(768, int(body.get("duration_hours", 24))))
    except (TypeError, ValueError):
        duration = 24
    return {
        "question": question, "answers": answers, "channel_id": int(channel_id),
        "duration_hours": duration, "multiselect": bool(body.get("multiselect")),
    }, None


def _poll_schedule(body):
    """Resolve post mode → (status, needs_post, scheduled_at).

    mode: 'now' (default) posts on the next bot tick; 'schedule' waits until
    scheduled_at; 'draft' is parked until the user posts it.
    """
    mode = str(body.get("mode") or "now").lower()
    if mode == "draft":
        return "draft", False, None
    if mode == "schedule":
        when = _parse_dt(body.get("scheduled_at"))
        if when and when > datetime.utcnow():
            return "scheduled", True, when
    return "pending", True, None


@content_bp.post("/api/guilds/<int:guild_id>/polls")
@login_required
def create_poll(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    body = request.get_json(silent=True) or {}
    fields, ferr = _poll_fields(body)
    if ferr:
        return ferr
    status, needs_post, scheduled_at = _poll_schedule(body)
    row = Poll(
        guild_id=guild_id, created_by=g.user_id,
        status=status, needs_post=needs_post, scheduled_at=scheduled_at, **fields,
    )
    g.db.add(row)
    g.db.commit()
    return jsonify(poll=row.to_dict()), 201


@content_bp.put("/api/guilds/<int:guild_id>/polls/<int:pid>")
@login_required
def update_poll(guild_id: int, pid: int):
    """Edit an unposted poll (draft / pending / scheduled) or change its post mode."""
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = g.db.get(Poll, pid)
    if row is None or row.guild_id != guild_id:
        return jsonify(error="not_found"), 404
    if row.status not in ("draft", "pending", "scheduled"):
        return jsonify(error="poll_already_posted"), 409
    body = request.get_json(silent=True) or {}
    fields, ferr = _poll_fields(body)
    if ferr:
        return ferr
    for k, v in fields.items():
        setattr(row, k, v)
    if "mode" in body:
        row.status, row.needs_post, row.scheduled_at = _poll_schedule(body)
    g.db.commit()
    return jsonify(poll=row.to_dict())


@content_bp.post("/api/guilds/<int:guild_id>/polls/<int:pid>/post")
@login_required
def post_poll_now(guild_id: int, pid: int):
    """Push a draft/scheduled poll live on the next bot tick."""
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = g.db.get(Poll, pid)
    if row is None or row.guild_id != guild_id:
        return jsonify(error="not_found"), 404
    if row.status not in ("draft", "scheduled"):
        return jsonify(error="not_postable"), 409
    row.status, row.needs_post, row.scheduled_at = "pending", True, None
    g.db.commit()
    return jsonify(poll=row.to_dict())


@content_bp.post("/api/guilds/<int:guild_id>/polls/<int:pid>/end")
@login_required
def end_poll(guild_id: int, pid: int):
    """Close a live poll early — the bot finalises it on the next tick."""
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = g.db.get(Poll, pid)
    if row is None or row.guild_id != guild_id:
        return jsonify(error="not_found"), 404
    if row.status != "open":
        return jsonify(error="poll_not_live"), 409
    row.ends_at = datetime.utcnow()
    g.db.commit()
    return jsonify(poll=row.to_dict())


@content_bp.delete("/api/guilds/<int:guild_id>/polls/<int:pid>")
@login_required
def delete_poll(guild_id: int, pid: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = g.db.get(Poll, pid)
    if row is None or row.guild_id != guild_id:
        return jsonify(error="not_found"), 404
    if row.status == "open":
        return jsonify(error="poll_is_live"), 409
    g.db.delete(row)
    g.db.commit()
    return jsonify(ok=True)


# --- auto-responses ----------------------------------------------------------------------
@content_bp.get("/api/guilds/<int:guild_id>/auto-responses")
@login_required
def list_responses(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    rows = (
        g.db.query(AutoResponse)
        .filter(AutoResponse.guild_id == guild_id)
        .order_by(AutoResponse.created_at)
        .limit(100)
        .all()
    )
    return jsonify(responses=[r.to_dict() for r in rows])


@content_bp.post("/api/guilds/<int:guild_id>/auto-responses")
@login_required
def create_response(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    count = (g.db.query(AutoResponse)
             .filter(AutoResponse.guild_id == guild_id).count())
    cap = plan_limits.limit(g.db, guild_id, "auto_responses")
    if count >= cap:
        return plan_limits.limit_response("auto_responses", cap)
    body = request.get_json(silent=True) or {}
    trigger = str(body.get("trigger") or "").strip()[:120]
    response = str(body.get("response") or "").strip()[:2000]
    if not trigger or not response:
        return jsonify(error="trigger_and_response_required"), 400
    try:
        cooldown = max(1, min(3600, int(body.get("cooldown_seconds", 30))))
    except (TypeError, ValueError):
        cooldown = 30
    row = AutoResponse(
        guild_id=guild_id, trigger=trigger, response=response,
        match_type=body.get("match_type") if body.get("match_type") in ("contains", "exact") else "contains",
        cooldown_seconds=cooldown,
        use_as_ai_knowledge=bool(body.get("use_as_ai_knowledge")),
    )
    g.db.add(row)
    g.db.commit()
    return jsonify(response=row.to_dict()), 201


@content_bp.put("/api/guilds/<int:guild_id>/auto-responses/<int:rid>")
@login_required
def update_response(guild_id: int, rid: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = g.db.get(AutoResponse, rid)
    if row is None or row.guild_id != guild_id:
        return jsonify(error="not_found"), 404
    body = request.get_json(silent=True) or {}
    if "trigger" in body and str(body["trigger"]).strip():
        row.trigger = str(body["trigger"]).strip()[:120]
    if "response" in body and str(body["response"]).strip():
        row.response = str(body["response"]).strip()[:2000]
    if body.get("match_type") in ("contains", "exact"):
        row.match_type = body["match_type"]
    if "cooldown_seconds" in body:
        try:
            row.cooldown_seconds = max(1, min(3600, int(body["cooldown_seconds"])))
        except (TypeError, ValueError):
            pass
    if "enabled" in body:
        row.enabled = bool(body["enabled"])
    if "use_as_ai_knowledge" in body:
        row.use_as_ai_knowledge = bool(body["use_as_ai_knowledge"])
    g.db.commit()
    return jsonify(response=row.to_dict())


@content_bp.delete("/api/guilds/<int:guild_id>/auto-responses/<int:rid>")
@login_required
def delete_response(guild_id: int, rid: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = g.db.get(AutoResponse, rid)
    if row is None or row.guild_id != guild_id:
        return jsonify(error="not_found"), 404
    g.db.delete(row)
    g.db.commit()
    return jsonify(ok=True)
