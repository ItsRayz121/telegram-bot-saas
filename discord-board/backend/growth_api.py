"""Growth endpoints (Phase 14): campaign custom fields, referral tracking,
public proof feed.

  GET/POST   /api/guilds/<id>/campaigns/<cid>/fields
  DELETE     /api/guilds/<id>/campaigns/<cid>/fields/<fid>
  GET        /api/guilds/<id>/referrals            (leaderboard + recent + config)
  PUT        /api/guilds/<id>/referrals/settings   {xp_per_referral}
  GET        /api/public/guilds/<id>/proof-feed    (verified submissions; no auth)
"""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request
from sqlalchemy import func

from auth import login_required
from database import SessionLocal
from models import (
    Campaign,
    CampaignCustomField,
    CampaignSubmission,
    Guild,
    GuildSettings,
    InviteJoin,
    UserGuild,
)

growth_bp = Blueprint("growth", __name__)

MAX_FIELDS = 4


def _manage_or_403(guild_id: int):
    membership = g.db.get(UserGuild, {"user_id": g.user_id, "guild_id": guild_id})
    if membership is None or not membership.can_manage:
        return False, (jsonify(error="forbidden"), 403)
    if g.db.get(Guild, guild_id) is None:
        return False, (jsonify(error="not_found"), 404)
    return True, None


def _own_campaign(guild_id: int, cid: int) -> Campaign | None:
    c = g.db.get(Campaign, cid)
    return c if c is not None and c.guild_id == guild_id else None


# --- campaign custom fields ----------------------------------------------------------
@growth_bp.get("/api/guilds/<int:guild_id>/campaigns/<int:cid>/fields")
@login_required
def list_fields(guild_id: int, cid: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    if _own_campaign(guild_id, cid) is None:
        return jsonify(error="not_found"), 404
    rows = (
        g.db.query(CampaignCustomField)
        .filter(CampaignCustomField.campaign_id == cid)
        .order_by(CampaignCustomField.position)
        .all()
    )
    return jsonify(fields=[r.to_dict() for r in rows])


@growth_bp.post("/api/guilds/<int:guild_id>/campaigns/<int:cid>/fields")
@login_required
def create_field(guild_id: int, cid: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    if _own_campaign(guild_id, cid) is None:
        return jsonify(error="not_found"), 404
    count = g.db.query(CampaignCustomField).filter(CampaignCustomField.campaign_id == cid).count()
    if count >= MAX_FIELDS:
        return jsonify(error="field_limit_reached", limit=MAX_FIELDS), 403
    body = request.get_json(silent=True) or {}
    label = str(body.get("label") or "").strip()[:45]
    if not label:
        return jsonify(error="label_required"), 400
    row = CampaignCustomField(
        campaign_id=cid, label=label,
        required=bool(body.get("required", True)), position=count,
    )
    g.db.add(row)
    g.db.commit()
    return jsonify(field=row.to_dict()), 201


@growth_bp.delete("/api/guilds/<int:guild_id>/campaigns/<int:cid>/fields/<int:fid>")
@login_required
def delete_field(guild_id: int, cid: int, fid: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = g.db.get(CampaignCustomField, fid)
    if row is None or row.campaign_id != cid or _own_campaign(guild_id, cid) is None:
        return jsonify(error="not_found"), 404
    g.db.delete(row)
    g.db.commit()
    return jsonify(ok=True)


# --- referrals --------------------------------------------------------------------------
@growth_bp.get("/api/guilds/<int:guild_id>/referrals")
@login_required
def referrals(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    top = (
        g.db.query(InviteJoin.inviter_id, InviteJoin.inviter_name,
                   func.count(InviteJoin.id).label("joins"))
        .filter(InviteJoin.guild_id == guild_id, InviteJoin.inviter_id.isnot(None))
        .group_by(InviteJoin.inviter_id, InviteJoin.inviter_name)
        .order_by(func.count(InviteJoin.id).desc())
        .limit(20)
        .all()
    )
    recent = (
        g.db.query(InviteJoin)
        .filter(InviteJoin.guild_id == guild_id)
        .order_by(InviteJoin.created_at.desc())
        .limit(25)
        .all()
    )
    settings = g.db.get(GuildSettings, guild_id)
    ref_cfg = ((settings.extra or {}).get("referrals") or {}) if settings else {}
    return jsonify(
        leaderboard=[{"inviter_id": str(uid), "inviter_name": name, "joins": joins}
                     for uid, name, joins in top],
        recent=[r.to_dict() for r in recent],
        xp_per_referral=int(ref_cfg.get("xp_per_referral", 0) or 0),
    )


@growth_bp.put("/api/guilds/<int:guild_id>/referrals/settings")
@login_required
def referral_settings(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    body = request.get_json(silent=True) or {}
    try:
        xp = max(0, min(1000, int(body.get("xp_per_referral", 0))))
    except (TypeError, ValueError):
        return jsonify(error="invalid_xp"), 400
    settings = g.db.get(GuildSettings, guild_id)
    if settings is None:
        return jsonify(error="not_found"), 404
    extra = dict(settings.extra or {})
    extra["referrals"] = {**(extra.get("referrals") or {}), "xp_per_referral": xp}
    settings.extra = extra
    g.db.commit()
    return jsonify(xp_per_referral=xp)


# --- public proof feed (no auth — only verified, minimal data) ----------------------------
@growth_bp.get("/api/public/guilds/<int:guild_id>/proof-feed")
def proof_feed(guild_id: int):
    db = SessionLocal()
    try:
        rows = (
            db.query(CampaignSubmission, Campaign.title)
            .join(Campaign, CampaignSubmission.campaign_id == Campaign.id)
            .filter(Campaign.guild_id == guild_id,
                    CampaignSubmission.status == "verified")
            .order_by(CampaignSubmission.reviewed_at.desc())
            .limit(50)
            .all()
        )
        feed = []
        for sub, title in rows:
            name = sub.username or "member"
            feed.append({
                "campaign": title,
                "username": name[:2] + "***" if len(name) > 2 else name,  # privacy mask
                "reward_xp": sub.reward_granted or 0,
                "verified_at": sub.reviewed_at.isoformat() + "Z" if sub.reviewed_at else None,
            })
        return jsonify(feed=feed)
    finally:
        db.close()
        SessionLocal.remove()
