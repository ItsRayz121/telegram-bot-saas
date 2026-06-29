"""Campaign engagement endpoints.

  GET    /api/guilds/<id>/campaigns
  POST   /api/guilds/<id>/campaigns
  GET    /api/guilds/<id>/campaigns/<cid>
  PUT    /api/guilds/<id>/campaigns/<cid>
  DELETE /api/guilds/<id>/campaigns/<cid>
  POST   /api/guilds/<id>/campaigns/<cid>/post           # ask the bot to (re)post
  POST   /api/guilds/<id>/campaigns/<cid>/tasks
  PUT    /api/guilds/<id>/campaigns/<cid>/tasks/<tid>
  DELETE /api/guilds/<id>/campaigns/<cid>/tasks/<tid>
  GET    /api/guilds/<id>/campaigns/<cid>/submissions?status=
  POST   /api/guilds/<id>/campaigns/<cid>/submissions/<sid>/review  {action}
  GET    /api/guilds/<id>/campaigns/<cid>/leaderboard    # Pro only

Free guilds may keep one ACTIVE campaign; Pro is unlimited. Verifying a
submission grants the task/campaign reward via the XP ledger.
"""
from __future__ import annotations

from datetime import datetime

from flask import Blueprint, g, jsonify, request
from sqlalchemy import func
from sqlalchemy.orm.attributes import flag_modified

import leveling
import access
import twitter_verify
from auth import login_required
from crypto import decrypt_token, encrypt_token
from models import (
    CAMPAIGN_STATUSES,
    CAMPAIGN_TYPES,
    CAMPAIGN_VERIFICATION_MODES,
    Campaign,
    CampaignSubmission,
    CampaignTask,
    Guild,
    User,
    UserGuild,
)

campaigns_bp = Blueprint("campaigns", __name__)

FREE_ACTIVE_LIMIT = 1


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


def _parse_iso(value):
    """ISO-8601 string (optionally with trailing Z) -> naive UTC datetime, or None."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


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
    out = []
    for c in rows:
        d = c.to_dict(include_tasks=False)
        d["counts"] = _counts(c.id)
        d["task_count"] = len(c.tasks)
        out.append(d)
    # Owner-aware 3-state for the auto-verify chip (live | rejected | disabled).
    # The key is account-level, so this is identical across all the owner's guilds.
    x_status = "disabled"
    try:
        x_status = twitter_verify.autoverify_status(guild.owner_id)
    except Exception:
        pass
    return jsonify(campaigns=out, plan=guild.plan or "free", x_autoverify_status=x_status)


@campaigns_bp.post("/api/guilds/<int:guild_id>/campaigns")
@login_required
def create_campaign(guild_id: int):
    guild, err = _ctx(guild_id)
    if err:
        return err
    body = request.get_json(silent=True) or {}
    title = str(body.get("title", "")).strip()
    if not title:
        return jsonify(error="Title is required"), 400
    ctype = body.get("type") if body.get("type") in CAMPAIGN_TYPES else "proof_collection"
    vmode = body.get("verification_mode") if body.get("verification_mode") in CAMPAIGN_VERIFICATION_MODES else "manual"

    c = Campaign(
        guild_id=guild_id,
        type=ctype,
        title=title[:200],
        description=str(body.get("description") or "")[:2000],
        task_url=str(body.get("task_url") or "")[:2000] or None,
        verification_mode=vmode,
        reward_xp=_as_int(body.get("reward_xp", 0), 0, 0, 100000),
        reward_label=str(body.get("reward_label") or "")[:200] or None,
        one_per_user=bool(body.get("one_per_user", True)),
        channel_id=int(body["channel_id"]) if str(body.get("channel_id") or "").isdigit() else None,
        status="draft",
        settings=body["settings"] if isinstance(body.get("settings"), dict) else {},
    )
    g.db.add(c)
    g.db.commit()
    return jsonify(c.to_dict()), 201


@campaigns_bp.get("/api/guilds/<int:guild_id>/campaigns/<int:cid>")
@login_required
def get_campaign(guild_id: int, cid: int):
    guild, err = _ctx(guild_id)
    if err:
        return err
    c = _get_campaign(guild_id, cid)
    if c is None:
        return jsonify(error="not_found"), 404
    d = c.to_dict()
    d["counts"] = _counts(cid)
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

    if "title" in body and str(body["title"]).strip():
        c.title = str(body["title"]).strip()[:200]
    if "description" in body:
        c.description = str(body["description"] or "")[:2000]
    if "task_url" in body:
        c.task_url = str(body["task_url"] or "")[:2000] or None
    if "type" in body and body["type"] in CAMPAIGN_TYPES:
        c.type = body["type"]
    if "verification_mode" in body and body["verification_mode"] in CAMPAIGN_VERIFICATION_MODES:
        c.verification_mode = body["verification_mode"]
    if "reward_xp" in body:
        c.reward_xp = _as_int(body["reward_xp"], 0, 0, 100000)
    if "reward_label" in body:
        c.reward_label = str(body["reward_label"] or "")[:200] or None
    if "one_per_user" in body:
        c.one_per_user = bool(body["one_per_user"])
    if "channel_id" in body:
        v = body["channel_id"]
        c.channel_id = int(v) if str(v or "").isdigit() else None
    if "ends_at" in body:
        c.ends_at = _parse_iso(body["ends_at"])
    if "starts_at" in body:
        c.starts_at = _parse_iso(body["starts_at"])
    if isinstance(body.get("settings"), dict):
        # Merge so we never drop existing keys (winners, branding, etc.).
        merged = dict(c.settings or {})
        merged.update(body["settings"])
        c.settings = merged
        flag_modified(c, "settings")

    if "status" in body and body["status"] in CAMPAIGN_STATUSES:
        new_status = body["status"]
        if new_status == "active" and c.status != "active":
            if not guild.is_pro and _active_count(guild_id, exclude_id=cid) >= FREE_ACTIVE_LIMIT:
                return jsonify(error="plan_limit_reached",
                               message="Free plan allows one active campaign. Upgrade to Pro for more."), 402
            c.status = "active"
            if c.channel_id:
                c.needs_post = True   # bot posts the announcement with proof buttons
        else:
            c.status = new_status

    g.db.commit()
    return jsonify(c.to_dict())


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
        return jsonify(error="Task title is required"), 400
    order = (max((t.order for t in c.tasks), default=-1)) + 1
    t = CampaignTask(
        campaign_id=cid,
        order=order,
        title=title[:200],
        description=str(body.get("description") or "")[:2000],
        type=body.get("type") if body.get("type") in CAMPAIGN_TYPES else "social_task",
        task_url=str(body.get("task_url") or "")[:2000] or None,
        verification_mode=body.get("verification_mode") if body.get("verification_mode") in CAMPAIGN_VERIFICATION_MODES else "manual",
        reward_xp=_as_int(body.get("reward_xp", 0), 0, 0, 100000),
    )
    g.db.add(t)
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
    if "verification_mode" in body and body["verification_mode"] in CAMPAIGN_VERIFICATION_MODES:
        t.verification_mode = body["verification_mode"]
    if "reward_xp" in body:
        t.reward_xp = _as_int(body["reward_xp"], 0, 0, 100000)
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
    subs = q.order_by(CampaignSubmission.created_at.desc()).limit(500).all()
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
    action = (request.get_json(silent=True) or {}).get("action")
    if action not in ("verify", "reject"):
        return jsonify(error="action must be verify or reject"), 400

    if action == "reject":
        s.status = "rejected"
        s.reviewed_at = datetime.utcnow()
        s.reviewer_id = g.user_id
        g.db.commit()
        return jsonify(s.to_dict())

    # verify → grant the task/campaign reward once
    if s.status != "verified":
        reward = _reward_for(c, s.task_id)
        if reward > 0:
            leveling.add_xp(g.db, guild_id, s.user_id, reward, s.username, reason=f"campaign:{cid}")
        s.reward_granted = reward
        s.status = "verified"
        s.reviewed_at = datetime.utcnow()
        s.reviewer_id = g.user_id
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
        )
        .filter(CampaignSubmission.campaign_id == cid, CampaignSubmission.status == "verified")
        .group_by(CampaignSubmission.user_id)
        .order_by(func.sum(CampaignSubmission.reward_granted).desc(),
                  func.count(CampaignSubmission.id).desc())
        .limit(50)
        .all()
    )
    board = [
        {"rank": i, "user_id": str(uid), "username": uname,
         "verified": int(cnt), "xp_earned": int(xp)}
        for i, (uid, uname, cnt, xp) in enumerate(rows, start=1)
    ]
    return jsonify(leaderboard=board)


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
