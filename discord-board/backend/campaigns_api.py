"""Campaign engagement endpoints.

  GET    /api/guilds/<id>/campaigns
  POST   /api/guilds/<id>/campaigns
  GET    /api/guilds/<id>/campaigns/<cid>
  PUT    /api/guilds/<id>/campaigns/<cid>                 # edits and/or {action}
  DELETE /api/guilds/<id>/campaigns/<cid>
  POST   /api/guilds/<id>/campaigns/<cid>/post            # ask the bot to (re)post
  DELETE /api/guilds/<id>/campaigns/<cid>/post            # ask the bot to delete it
  POST   /api/guilds/<id>/campaigns/<cid>/tasks
  PUT    /api/guilds/<id>/campaigns/<cid>/tasks/<tid>
  DELETE /api/guilds/<id>/campaigns/<cid>/tasks/<tid>
  GET    /api/guilds/<id>/campaigns/<cid>/submissions?status=
  POST   /api/guilds/<id>/campaigns/<cid>/submissions/<sid>/review  {action, reason}
  GET    /api/guilds/<id>/campaigns/<cid>/leaderboard     # Pro only

Mirrors Telegizer's engagement service: the same free-plan caps, the same
lifecycle verbs (publish/pause/reopen/close/archive), the same create payload
(campaign-level proof fields + sub-tasks with their own fields), and the same
structure lock once members have started submitting.

Free guilds may keep one ACTIVE campaign; Pro is unlimited. Verifying a
submission grants the task/campaign reward via the XP ledger.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from flask import Blueprint, g, jsonify, request
from sqlalchemy import func
from sqlalchemy.orm.attributes import flag_modified

import leveling
import access
import twitter_verify
from auth import login_required
from crypto import decrypt_token, encrypt_token
from models import (
    CAMPAIGN_FIELD_TYPES,
    CAMPAIGN_STATUSES,
    CAMPAIGN_TYPES,
    CAMPAIGN_VERIFICATION_MODES,
    Campaign,
    CampaignCustomField,
    CampaignSubmission,
    CampaignTask,
    Guild,
    User,
)

campaigns_bp = Blueprint("campaigns", __name__)

# ── Free-plan caps (mirror Telegizer's engagement.py) ─────────────────────────
FREE_ACTIVE_LIMIT = 1
FREE_MAX_CUSTOM_FIELDS = 3
# Hard platform cap, not a plan cap: a Discord modal allows 5 components and the
# proof input takes one, so at most 4 admin-defined fields can ever be shown.
MAX_CUSTOM_FIELDS = 4

# Valid lifecycle transitions for the PUT `action` verb.
_LIFECYCLE_ACTIONS = {
    "publish": "active",
    "pause": "paused",
    "reopen": "active",
    "close": "closed",
    "archive": "archived",
}

# Fields a PUT may edit directly (content edits, distinct from a lifecycle action).
_EDITABLE_FIELDS = {
    "title", "description", "task_url", "platform", "reward_xp", "reward_label",
    "starts_at", "ends_at", "max_participants", "one_per_user", "pin_message",
    "verification_mode", "settings", "channel_id",
}


class ApiError(Exception):
    """Client-facing error; the blueprint handler converts it to JSON."""

    def __init__(self, message, status=400, code=None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code


@campaigns_bp.errorhandler(ApiError)
def _handle_api_error(exc: ApiError):
    body = {"error": exc.message, "message": exc.message}
    if exc.code:
        body["code"] = exc.code
    return jsonify(body), exc.status


def _ctx(guild_id: int):
    """Return (guild, None) if the user manages it, else (None, error-response)."""
    if not access.can_manage_guild(g.db, g.user_id, guild_id):
        return None, (jsonify(error="forbidden"), 403)
    guild = g.db.get(Guild, guild_id)
    if guild is None:
        return None, (jsonify(error="not_found"), 404)
    return guild, None


def _get_campaign(guild_id: int, cid: int):
    c = g.db.get(Campaign, cid)
    if c is None or c.guild_id != guild_id:
        return None
    return c


def _as_int(value, default, lo, hi):
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


def _opt_int(value, name, *, minimum=None):
    """None/'' -> None; otherwise a validated int."""
    if value in (None, ""):
        return None
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise ApiError(f"{name} must be a number")
    if minimum is not None and n < minimum:
        raise ApiError(f"{name} must be >= {minimum}")
    return n


def _parse_iso(value):
    """ISO-8601 string (optionally with trailing Z) -> naive UTC datetime, or None."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


def _norm_platform(value):
    if not value:
        return None
    return str(value).strip().lower()[:40] or None


def _counts(cid: int) -> dict:
    rows = (
        g.db.query(CampaignSubmission.status, func.count(CampaignSubmission.id))
        .filter(CampaignSubmission.campaign_id == cid)
        .group_by(CampaignSubmission.status)
        .all()
    )
    by = {s: n for s, n in rows}
    return {
        "total": sum(by.values()),
        "pending": by.get("pending", 0),
        "verified": by.get("verified", 0),
        "rejected": by.get("rejected", 0),
    }


def _active_count(guild_id: int, exclude_id=None) -> int:
    q = g.db.query(Campaign).filter(
        Campaign.guild_id == guild_id, Campaign.status == "active"
    )
    if exclude_id:
        q = q.filter(Campaign.id != exclude_id)
    return q.count()


def _has_submissions(cid: int) -> bool:
    return (
        g.db.query(CampaignSubmission.id)
        .filter(CampaignSubmission.campaign_id == cid)
        .first()
        is not None
    )


# ── Proof fields & tasks ──────────────────────────────────────────────────────

def _validate_fields(fields_in, *, plan_is_pro: bool):
    """Validate raw proof-field dicts -> normalized kwargs. No DB writes."""
    if not isinstance(fields_in, list):
        raise ApiError("custom_fields must be a list")
    if len(fields_in) > MAX_CUSTOM_FIELDS:
        raise ApiError(
            f"Discord modals allow at most {MAX_CUSTOM_FIELDS} extra proof fields."
        )
    if not plan_is_pro and len(fields_in) > FREE_MAX_CUSTOM_FIELDS:
        raise ApiError(
            f"The free plan allows up to {FREE_MAX_CUSTOM_FIELDS} proof fields per "
            "campaign. Upgrade to Pro for more.",
            403, code="FEATURE_REQUIRES_PRO",
        )
    out, seen = [], set()
    for idx, raw in enumerate(fields_in):
        if not isinstance(raw, dict):
            raise ApiError("Each custom field must be an object")
        label = str(raw.get("label") or "").strip()
        if not label:
            raise ApiError("Each custom field needs a label")
        ftype = str(raw.get("field_type") or "text").strip()
        if ftype not in CAMPAIGN_FIELD_TYPES:
            raise ApiError(f"Invalid field_type: {ftype}")
        key = str(raw.get("key") or label).strip().lower().replace(" ", "_")[:64]
        if key in seen:
            key = f"{key}_{idx}"[:64]
        seen.add(key)
        example = str(raw.get("example") or "").strip()
        out.append(dict(
            key=key,
            label=label[:45],
            field_type=ftype,
            required=bool(raw.get("required", True)),
            example=(example[:200] or None),
            position=idx,
        ))
    return out


def _replace_custom_fields(campaign, fields_in, *, plan_is_pro: bool):
    """(Re)create the campaign-level proof fields. Caller commits."""
    for f in list(campaign.custom_fields):
        if f.task_id is None:
            g.db.delete(f)
    g.db.flush()
    for kw in _validate_fields(fields_in, plan_is_pro=plan_is_pro):
        g.db.add(CampaignCustomField(campaign_id=campaign.id, **kw))


def _replace_tasks(campaign, tasks_in, *, plan_is_pro: bool):
    """(Re)create sub-tasks and their proof fields. `None` leaves tasks untouched;
    an empty list clears them (back to a single-task campaign)."""
    if tasks_in is None:
        return
    if not isinstance(tasks_in, list):
        raise ApiError("tasks must be a list")
    if len(tasks_in) > 1 and not plan_is_pro:
        raise ApiError(
            "Multi-task campaigns require a Pro subscription.",
            403, code="FEATURE_REQUIRES_PRO",
        )
    if len(tasks_in) > 25:
        raise ApiError("A campaign can hold at most 25 tasks (Discord button limit).")

    existing = list(campaign.tasks)
    if existing:
        # Deleting a task orphans its submissions — refuse to replace tasks once
        # members have started submitting (data-loss guard, Telegizer parity).
        ids = [t.id for t in existing]
        clash = (
            g.db.query(CampaignSubmission.id)
            .filter(CampaignSubmission.task_id.in_(ids))
            .first()
        )
        if clash is not None:
            raise ApiError(
                "This campaign's tasks can't be changed after members have started "
                "submitting. Close it and create a new campaign instead."
            )
    for t in existing:
        for f in list(t.custom_fields):   # no delete-orphan on the task side
            g.db.delete(f)
        g.db.delete(t)
    g.db.flush()

    for idx, raw in enumerate(tasks_in):
        if not isinstance(raw, dict):
            raise ApiError("Each task must be an object")
        title = str(raw.get("title") or "").strip()
        if not title:
            raise ApiError("Each task needs a title")
        ttype = str(raw.get("type") or "social_task").strip()
        if ttype not in CAMPAIGN_TYPES:
            raise ApiError(f"Invalid task type: {ttype}")
        tmode = str(raw.get("verification_mode") or "manual").strip()
        if tmode not in CAMPAIGN_VERIFICATION_MODES:
            raise ApiError(f"Invalid verification_mode: {tmode}")
        task = CampaignTask(
            campaign_id=campaign.id,
            order=idx,
            title=title[:200],
            description=str(raw.get("description") or "")[:2000],
            type=ttype,
            platform=_norm_platform(raw.get("platform")),
            task_url=str(raw.get("task_url") or "")[:2000] or None,
            verification_mode=tmode,
            reward_xp=_as_int(raw.get("reward_xp", 0), 0, 0, 100000),
            reward_label=str(raw.get("reward_label") or "")[:200] or None,
        )
        g.db.add(task)
        g.db.flush()  # need task.id for its fields
        for kw in _validate_fields(raw.get("custom_fields") or [], plan_is_pro=plan_is_pro):
            g.db.add(CampaignCustomField(campaign_id=campaign.id, task_id=task.id, **kw))


def _check_gating(guild, *, status, verification_mode, platform, field_count,
                  task_count, settings, exclude_id=None):
    """Raise ApiError(403) when a free guild exceeds the free-plan limits."""
    if guild.is_pro:
        return
    if task_count > 1:
        raise ApiError("Multi-task campaigns require a Pro subscription.",
                       403, code="FEATURE_REQUIRES_PRO")
    if verification_mode == "link":
        raise ApiError("Link-validity verification requires a Pro subscription.",
                       403, code="FEATURE_REQUIRES_PRO")
    # 'auto' is free only for Discord itself (server-membership check), matching
    # Telegizer where 'auto' is free only for a Telegram channel join.
    if verification_mode == "auto" and platform not in (None, "", "discord"):
        raise ApiError(
            "Automatic verification for this platform requires a Pro subscription.",
            403, code="FEATURE_REQUIRES_PRO")
    if field_count > FREE_MAX_CUSTOM_FIELDS:
        raise ApiError(
            f"The free plan allows up to {FREE_MAX_CUSTOM_FIELDS} proof fields per "
            "campaign. Upgrade to Pro for more.",
            403, code="FEATURE_REQUIRES_PRO")
    if (settings or {}).get("auto_verify_x"):
        raise ApiError("Automatic X verification requires a Pro subscription.",
                       403, code="FEATURE_REQUIRES_PRO")
    if status == "active" and _active_count(guild.id, exclude_id=exclude_id) >= FREE_ACTIVE_LIMIT:
        raise ApiError(
            f"The free plan allows {FREE_ACTIVE_LIMIT} active campaign at a time. "
            "Close it or upgrade to Pro to run more.",
            402, code="FEATURE_REQUIRES_PRO")


def _serialize(c: Campaign, *, include_tasks=True) -> dict:
    d = c.to_dict(include_tasks=include_tasks)
    counts = _counts(c.id)
    d["counts"] = counts
    # Flat aliases so the table can read them without digging into `counts`.
    d["submissions_total"] = counts["total"]
    d["submissions_pending"] = counts["pending"]
    d["submissions_verified"] = counts["verified"]
    d["task_count"] = len(c.tasks)
    d["is_multitask"] = len(c.tasks) > 0
    return d


# --- campaign CRUD ------------------------------------------------------------
@campaigns_bp.get("/api/guilds/<int:guild_id>/campaigns")
@login_required
def list_campaigns(guild_id: int):
    guild, err = _ctx(guild_id)
    if err:
        return err
    rows = (
        g.db.query(Campaign)
        .filter(Campaign.guild_id == guild_id)
        .order_by(Campaign.created_at.desc())
        .all()
    )
    out = [_serialize(c, include_tasks=True) for c in rows]
    # Owner-aware 3-state for the auto-verify chip (live | rejected | disabled).
    # The key is account-level, so this is identical across all the owner's guilds.
    x_status = "disabled"
    try:
        x_status = twitter_verify.autoverify_status(guild.owner_id)
    except Exception:
        pass
    # `is_pro` is authoritative (it accounts for expiry); `plan` is the raw label.
    return jsonify(campaigns=out, plan=guild.plan or "free", is_pro=bool(guild.is_pro),
                   x_autoverify_status=x_status)


@campaigns_bp.post("/api/guilds/<int:guild_id>/campaigns")
@login_required
def create_campaign(guild_id: int):
    guild, err = _ctx(guild_id)
    if err:
        return err
    body = request.get_json(silent=True) or {}
    title = str(body.get("title", "")).strip()
    if not title:
        raise ApiError("Title is required")

    ctype = body.get("type") if body.get("type") in CAMPAIGN_TYPES else "proof_collection"
    vmode = (body.get("verification_mode") or "manual").strip()
    if vmode not in CAMPAIGN_VERIFICATION_MODES:
        raise ApiError(f"Invalid verification_mode: {vmode}")
    status = (body.get("status") or "draft").strip()
    if status not in ("draft", "active"):
        raise ApiError("Campaign can only be created as 'draft' or 'active'")

    platform = "x" if ctype == "raid" else _norm_platform(body.get("platform"))
    settings = body["settings"] if isinstance(body.get("settings"), dict) else {}
    fields_in = body.get("custom_fields") or []
    tasks_in = body.get("tasks")
    task_count = len(tasks_in) if isinstance(tasks_in, list) else 0

    _check_gating(guild, status=status, verification_mode=vmode, platform=platform,
                  field_count=len(fields_in) if isinstance(fields_in, list) else 0,
                  task_count=task_count, settings=settings)

    # Deadline: explicit ends_at wins; otherwise derive it from duration_hours.
    starts_at = _parse_iso(body.get("starts_at"))
    ends_at = _parse_iso(body.get("ends_at"))
    if not ends_at and body.get("duration_hours"):
        hours = _opt_int(body.get("duration_hours"), "duration_hours", minimum=1)
        if hours:
            ends_at = (starts_at or datetime.utcnow()) + timedelta(hours=hours)

    c = Campaign(
        guild_id=guild_id,
        type=ctype,
        platform=platform,
        title=title[:200],
        description=str(body.get("description") or "")[:2000],
        task_url=str(body.get("task_url") or "")[:2000] or None,
        verification_mode=vmode,
        reward_xp=_as_int(body.get("reward_xp", 0), 0, 0, 100000),
        reward_label=str(body.get("reward_label") or "")[:200] or None,
        max_participants=_opt_int(body.get("max_participants"), "max_participants", minimum=1),
        one_per_user=bool(body.get("one_per_user", True)),
        pin_message=bool(body.get("pin_message", False)),
        starts_at=starts_at,
        ends_at=ends_at,
        channel_id=int(body["channel_id"]) if str(body.get("channel_id") or "").isdigit() else None,
        status=status,
        settings=settings,
    )
    g.db.add(c)
    g.db.flush()  # need c.id for its fields / tasks

    _replace_custom_fields(c, fields_in, plan_is_pro=guild.is_pro)
    _replace_tasks(c, tasks_in, plan_is_pro=guild.is_pro)

    if c.status == "active" and c.channel_id:
        c.needs_post = True
    g.db.commit()
    return jsonify(_serialize(c)), 201


@campaigns_bp.get("/api/guilds/<int:guild_id>/campaigns/<int:cid>")
@login_required
def get_campaign(guild_id: int, cid: int):
    guild, err = _ctx(guild_id)
    if err:
        return err
    c = _get_campaign(guild_id, cid)
    if c is None:
        return jsonify(error="not_found"), 404
    d = _serialize(c)
    d["structure_locked"] = _has_submissions(cid)
    return jsonify(d)


@campaigns_bp.put("/api/guilds/<int:guild_id>/campaigns/<int:cid>")
@login_required
def update_campaign(guild_id: int, cid: int):
    guild, err = _ctx(guild_id)
    if err:
        return err
    c = _get_campaign(guild_id, cid)
    if c is None:
        return jsonify(error="not_found"), 404
    body = request.get_json(silent=True) or {}
    is_pro = guild.is_pro

    # Free-plan gates that apply to edits as well as creation.
    if isinstance(body.get("tasks"), list) and len(body["tasks"]) > 1 and not is_pro:
        raise ApiError("Multi-task campaigns require a Pro subscription.",
                       403, code="FEATURE_REQUIRES_PRO")
    if isinstance(body.get("settings"), dict) and body["settings"].get("auto_verify_x") and not is_pro:
        raise ApiError("Automatic X verification requires a Pro subscription.",
                       403, code="FEATURE_REQUIRES_PRO")
    if "title" in body and not str(body["title"] or "").strip():
        raise ApiError("Title is required")
    # Structure edits are refused once members have submitted (protects their data).
    # Checked before anything is mutated so a rejected edit changes nothing.
    if (isinstance(body.get("custom_fields"), list) or "tasks" in body) and _has_submissions(cid):
        raise ApiError(
            "This campaign has submissions, so its tasks and proof fields are locked. "
            "You can still edit the details, reward, deadline and visibility."
        )

    # Lifecycle verb (publish/pause/reopen/close/archive), Telegizer parity.
    action = body.get("action")
    if action is not None:
        if action not in _LIFECYCLE_ACTIONS:
            raise ApiError(f"Unknown action: {action}")
        new_status = _LIFECYCLE_ACTIONS[action]
        if new_status == "active" and c.status != "active" and not is_pro:
            if _active_count(guild_id, exclude_id=cid) >= FREE_ACTIVE_LIMIT:
                raise ApiError(
                    "Free plan allows one active campaign. Upgrade to Pro for more.",
                    402, code="FEATURE_REQUIRES_PRO")
        c.status = new_status
        if new_status == "active" and c.channel_id and c.post_status != "posted":
            c.needs_post = True

    for key in list(body.keys()):
        if key not in _EDITABLE_FIELDS:
            continue
        value = body[key]
        if key in ("starts_at", "ends_at"):
            setattr(c, key, _parse_iso(value))
        elif key == "reward_xp":
            c.reward_xp = _as_int(value, 0, 0, 100000)
        elif key == "max_participants":
            c.max_participants = _opt_int(value, "max_participants", minimum=1)
        elif key in ("one_per_user", "pin_message"):
            setattr(c, key, bool(value))
        elif key == "verification_mode":
            if value not in CAMPAIGN_VERIFICATION_MODES:
                raise ApiError(f"Invalid verification_mode: {value}")
            c.verification_mode = value
        elif key == "platform":
            c.platform = _norm_platform(value)
        elif key == "channel_id":
            c.channel_id = int(value) if str(value or "").isdigit() else None
        elif key == "settings":
            # Merge so we never drop existing keys (winners, branding, etc.).
            merged = dict(c.settings or {})
            merged.update(value or {})
            c.settings = merged
            flag_modified(c, "settings")
        elif key == "title":
            c.title = str(value).strip()[:200]
        elif key in ("description", "task_url", "reward_label"):
            setattr(c, key, (str(value).strip() or None) if value else None)

    if isinstance(body.get("custom_fields"), list):
        _replace_custom_fields(c, body["custom_fields"], plan_is_pro=is_pro)
    if "tasks" in body:
        _replace_tasks(c, body.get("tasks"), plan_is_pro=is_pro)

    # A pure content edit refreshes the live announcement so it reflects the new
    # title / reward / deadline / proof line.
    if action is None and c.status == "active" and c.channel_id and c.post_status == "posted":
        c.needs_post = True

    g.db.commit()
    return jsonify(_serialize(c))


@campaigns_bp.delete("/api/guilds/<int:guild_id>/campaigns/<int:cid>")
@login_required
def delete_campaign(guild_id: int, cid: int):
    guild, err = _ctx(guild_id)
    if err:
        return err
    c = _get_campaign(guild_id, cid)
    if c is None:
        return jsonify(error="not_found"), 404
    g.db.delete(c)
    g.db.commit()
    return jsonify(ok=True)


@campaigns_bp.post("/api/guilds/<int:guild_id>/campaigns/<int:cid>/post")
@login_required
def post_campaign(guild_id: int, cid: int):
    guild, err = _ctx(guild_id)
    if err:
        return err
    c = _get_campaign(guild_id, cid)
    if c is None:
        return jsonify(error="not_found"), 404
    if not c.channel_id:
        return jsonify(error="no_channel", message="Set an announcement channel first."), 400
    c.needs_post = True
    g.db.commit()
    return jsonify(ok=True, post_status="queued", campaign=_serialize(c))


@campaigns_bp.delete("/api/guilds/<int:guild_id>/campaigns/<int:cid>/post")
@login_required
def delete_campaign_post(guild_id: int, cid: int):
    """Ask the bot to delete the channel announcement. Submissions and rewards are
    kept, and the campaign can be posted again afterwards."""
    guild, err = _ctx(guild_id)
    if err:
        return err
    c = _get_campaign(guild_id, cid)
    if c is None:
        return jsonify(error="not_found"), 404
    if not c.message_id:
        return jsonify(error="not_posted", message="This campaign has no channel post."), 400
    c.needs_unpost = True
    c.needs_post = False
    g.db.commit()
    return jsonify(ok=True, post_status="queued")


# --- tasks --------------------------------------------------------------------
@campaigns_bp.post("/api/guilds/<int:guild_id>/campaigns/<int:cid>/tasks")
@login_required
def add_task(guild_id: int, cid: int):
    guild, err = _ctx(guild_id)
    if err:
        return err
    c = _get_campaign(guild_id, cid)
    if c is None:
        return jsonify(error="not_found"), 404
    body = request.get_json(silent=True) or {}
    title = str(body.get("title", "")).strip()
    if not title:
        raise ApiError("Task title is required")
    if len(c.tasks) >= 1 and not guild.is_pro:
        raise ApiError("Multi-task campaigns require a Pro subscription.",
                       403, code="FEATURE_REQUIRES_PRO")
    order = (max((t.order for t in c.tasks), default=-1)) + 1
    t = CampaignTask(
        campaign_id=cid,
        order=order,
        title=title[:200],
        description=str(body.get("description") or "")[:2000],
        type=body.get("type") if body.get("type") in CAMPAIGN_TYPES else "social_task",
        platform=_norm_platform(body.get("platform")),
        task_url=str(body.get("task_url") or "")[:2000] or None,
        verification_mode=body.get("verification_mode") if body.get("verification_mode") in CAMPAIGN_VERIFICATION_MODES else "manual",
        reward_xp=_as_int(body.get("reward_xp", 0), 0, 0, 100000),
        reward_label=str(body.get("reward_label") or "")[:200] or None,
    )
    g.db.add(t)
    g.db.flush()
    for kw in _validate_fields(body.get("custom_fields") or [], plan_is_pro=guild.is_pro):
        g.db.add(CampaignCustomField(campaign_id=cid, task_id=t.id, **kw))
    if c.status == "active" and c.channel_id:
        c.needs_post = True
    g.db.commit()
    return jsonify(t.to_dict()), 201


@campaigns_bp.put("/api/guilds/<int:guild_id>/campaigns/<int:cid>/tasks/<int:tid>")
@login_required
def update_task(guild_id: int, cid: int, tid: int):
    guild, err = _ctx(guild_id)
    if err:
        return err
    c = _get_campaign(guild_id, cid)
    if c is None:
        return jsonify(error="not_found"), 404
    t = g.db.get(CampaignTask, tid)
    if t is None or t.campaign_id != cid:
        return jsonify(error="not_found"), 404
    body = request.get_json(silent=True) or {}
    if "title" in body and str(body["title"]).strip():
        t.title = str(body["title"]).strip()[:200]
    if "description" in body:
        t.description = str(body["description"] or "")[:2000]
    if "task_url" in body:
        t.task_url = str(body["task_url"] or "")[:2000] or None
    if "platform" in body:
        t.platform = _norm_platform(body["platform"])
    if "verification_mode" in body and body["verification_mode"] in CAMPAIGN_VERIFICATION_MODES:
        t.verification_mode = body["verification_mode"]
    if "reward_xp" in body:
        t.reward_xp = _as_int(body["reward_xp"], 0, 0, 100000)
    if "reward_label" in body:
        t.reward_label = str(body["reward_label"] or "")[:200] or None
    if c.status == "active" and c.channel_id:
        c.needs_post = True
    g.db.commit()
    return jsonify(t.to_dict())


@campaigns_bp.delete("/api/guilds/<int:guild_id>/campaigns/<int:cid>/tasks/<int:tid>")
@login_required
def delete_task(guild_id: int, cid: int, tid: int):
    guild, err = _ctx(guild_id)
    if err:
        return err
    c = _get_campaign(guild_id, cid)
    if c is None:
        return jsonify(error="not_found"), 404
    t = g.db.get(CampaignTask, tid)
    if t is None or t.campaign_id != cid:
        return jsonify(error="not_found"), 404
    # Task-level fields have no delete-orphan cascade (Campaign owns it), so drop
    # them explicitly or they'd linger with a dangling task_id.
    for f in list(t.custom_fields):
        g.db.delete(f)
    g.db.delete(t)
    if c.status == "active" and c.channel_id:
        c.needs_post = True
    g.db.commit()
    return jsonify(ok=True)


# --- submissions --------------------------------------------------------------
@campaigns_bp.get("/api/guilds/<int:guild_id>/campaigns/<int:cid>/submissions")
@login_required
def list_submissions(guild_id: int, cid: int):
    guild, err = _ctx(guild_id)
    if err:
        return err
    c = _get_campaign(guild_id, cid)
    if c is None:
        return jsonify(error="not_found"), 404
    q = g.db.query(CampaignSubmission).filter(CampaignSubmission.campaign_id == cid)
    status = request.args.get("status")
    if status in ("pending", "verified", "rejected"):
        q = q.filter(CampaignSubmission.status == status)
    subs = q.order_by(CampaignSubmission.created_at.desc()).limit(1000).all()
    return jsonify(submissions=[s.to_dict() for s in subs])


@campaigns_bp.post("/api/guilds/<int:guild_id>/campaigns/<int:cid>/submissions/<int:sid>/review")
@login_required
def review_submission(guild_id: int, cid: int, sid: int):
    guild, err = _ctx(guild_id)
    if err:
        return err
    c = _get_campaign(guild_id, cid)
    if c is None:
        return jsonify(error="not_found"), 404
    s = g.db.get(CampaignSubmission, sid)
    if s is None or s.campaign_id != cid:
        return jsonify(error="not_found"), 404
    body = request.get_json(silent=True) or {}
    action = body.get("action")
    # "verify" is the legacy verb the old dashboard sent; keep it working.
    if action == "verify":
        action = "approve"
    if action not in ("approve", "reject"):
        raise ApiError("action must be approve or reject")

    reviewer = g.db.get(User, g.user_id)
    s.reviewed_at = datetime.utcnow()
    s.reviewer_id = g.user_id
    s.reviewer_name = (getattr(reviewer, "username", None) or str(g.user_id))[:120]
    s.review_reason = str(body.get("reason") or "")[:500] or None
    # Queue the outcome DM; the bot process drains this (the web dyno has no gateway).
    s.notify_status = "pending"

    if action == "reject":
        s.status = "rejected"
        g.db.commit()
        return jsonify(s.to_dict())

    # approve -> grant the task/campaign reward exactly once
    if s.status != "verified":
        reward = _reward_for(c, s.task_id)
        if reward > 0:
            leveling.add_xp(g.db, guild_id, s.user_id, reward, s.username, reason=f"campaign:{cid}")
        s.reward_granted = reward
        s.status = "verified"
    g.db.commit()
    return jsonify(s.to_dict())


def _reward_for(campaign: Campaign, task_id) -> int:
    if task_id:
        t = g.db.get(CampaignTask, task_id)
        if t is not None:
            return t.reward_xp or 0
    return campaign.reward_xp or 0


# --- Pro-gated campaign leaderboard -------------------------------------------
@campaigns_bp.get("/api/guilds/<int:guild_id>/campaigns/<int:cid>/leaderboard")
@login_required
def campaign_leaderboard(guild_id: int, cid: int):
    guild, err = _ctx(guild_id)
    if err:
        return err
    if not guild.is_pro:
        return jsonify(error="pro_required",
                       message="Campaign leaderboards are a Pro feature."), 402
    c = _get_campaign(guild_id, cid)
    if c is None:
        return jsonify(error="not_found"), 404
    rows = (
        g.db.query(
            CampaignSubmission.user_id,
            func.max(CampaignSubmission.username),
            func.count(CampaignSubmission.id),
            func.coalesce(func.sum(CampaignSubmission.reward_granted), 0),
            func.min(CampaignSubmission.reviewed_at),
        )
        .filter(CampaignSubmission.campaign_id == cid, CampaignSubmission.status == "verified")
        .group_by(CampaignSubmission.user_id)
        .order_by(func.sum(CampaignSubmission.reward_granted).desc(),
                  func.count(CampaignSubmission.id).desc())
        .limit(100)
        .all()
    )
    board = [
        {"rank": i, "user_id": str(uid), "username": uname,
         "verified": int(cnt), "verified_count": int(cnt), "xp_earned": int(xp),
         "first_verified_at": (first.isoformat() + "Z") if first else None}
        for i, (uid, uname, cnt, xp, first) in enumerate(rows, start=1)
    ]
    return jsonify(leaderboard=board, entries=board, total_participants=len(board),
                   reward_xp=c.reward_xp or 0)


# --- account-level bring-your-own twitterapi.io key ---------------------------
# Account-level (one key covers every guild the user manages), so no guild in the
# path. Lets heavy raid users verify on their own twitterapi.io credits.
def _mask(raw: str) -> str:
    if not raw:
        return ""
    return raw[:4] + "****" + raw[-4:] if len(raw) > 8 else "****"


@campaigns_bp.get("/api/account/x-verify-key")
@login_required
def get_x_verify_key():
    u = g.db.get(User, g.user_id)
    masked = None
    if u and getattr(u, "twitter_api_key_encrypted", None):
        raw = decrypt_token(u.twitter_api_key_encrypted)
        masked = _mask(raw) if raw else None
    status = "disabled"
    try:
        status = twitter_verify.autoverify_status(g.user_id)
    except Exception:
        pass
    return jsonify(configured=bool(masked), masked_key=masked, status=status,
                   using_own_key=bool(masked))


@campaigns_bp.post("/api/account/x-verify-key")
@login_required
def save_x_verify_key():
    body = request.get_json(silent=True) or {}
    api_key = str(body.get("api_key") or "").strip()
    if not api_key or "****" in api_key:
        return jsonify(error="Paste your twitterapi.io API key"), 400
    # Validate live before persisting so a bad key is caught here, not silently later.
    try:
        probe = twitter_verify._probe_key(api_key)
    except Exception:
        probe = "ok"
    if probe != "ok":
        reason = probe.replace("error:", "").strip() or "key was rejected"
        return jsonify(error=f"twitterapi.io rejected this key ({reason}). Double-check it and try again."), 400
    u = g.db.get(User, g.user_id)
    if u is None:
        return jsonify(error="not_found"), 404
    u.twitter_api_key_encrypted = encrypt_token(api_key)
    g.db.commit()
    return jsonify(configured=True, status="live", using_own_key=True,
                   message="twitterapi.io key saved — X auto-verify is live on your own credits.")


@campaigns_bp.delete("/api/account/x-verify-key")
@login_required
def delete_x_verify_key():
    u = g.db.get(User, g.user_id)
    if u is not None:
        u.twitter_api_key_encrypted = None
        g.db.commit()
    status = "disabled"
    try:
        status = twitter_verify.autoverify_status(g.user_id)
    except Exception:
        pass
    return jsonify(configured=False, status=status, using_own_key=False,
                   message="Removed. X auto-verify now uses the platform key (if available).")
