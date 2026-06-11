"""Platform admin API (admin_required). Read-only drill-downs over every guild,
plus a manual plan grant/revoke. Usage analytics are derived from existing
tables — no separate tracking spine.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from flask import Blueprint, g, jsonify, request
from sqlalchemy import func

from admin import admin_required
from models import (
    Campaign,
    CampaignSubmission,
    Guild,
    Member,
    ProtectionEvent,
    Subscription,
    User,
    UserGuild,
    XpEvent,
)

admin_bp = Blueprint("admin", __name__)


def _count(model, *filters) -> int:
    q = g.db.query(func.count()).select_from(model)
    for f in filters:
        q = q.filter(f)
    return q.scalar() or 0


def _as_int(value, default, lo, hi):
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


@admin_bp.get("/api/admin/overview")
@admin_required
def overview():
    return jsonify(
        guilds_total=_count(Guild),
        guilds_with_bot=_count(Guild, Guild.bot_present.is_(True)),
        guilds_pro=_count(Guild, Guild.plan == "pro"),
        users_total=_count(User),
        members_total=_count(Member),
        campaigns_total=_count(Campaign),
        campaigns_active=_count(Campaign, Campaign.status == "active"),
        submissions_total=_count(CampaignSubmission),
        submissions_verified=_count(CampaignSubmission, CampaignSubmission.status == "verified"),
        protection_events_total=_count(ProtectionEvent),
        xp_events_total=_count(XpEvent),
        subscriptions_active=_count(Subscription, Subscription.status == "active"),
    )


@admin_bp.get("/api/admin/guilds")
@admin_required
def guilds():
    limit = _as_int(request.args.get("limit", 100), 100, 1, 500)
    rows = g.db.query(Guild).order_by(Guild.member_count.desc()).limit(limit).all()
    return jsonify(guilds=[
        {**gd.to_dict(), "owner_id": str(gd.owner_id) if gd.owner_id else None}
        for gd in rows
    ])


@admin_bp.get("/api/admin/guilds/<int:guild_id>")
@admin_required
def guild_detail(guild_id: int):
    gd = g.db.get(Guild, guild_id)
    if gd is None:
        return jsonify(error="not_found"), 404
    recent = (
        g.db.query(ProtectionEvent)
        .filter(ProtectionEvent.guild_id == guild_id)
        .order_by(ProtectionEvent.created_at.desc())
        .limit(20)
        .all()
    )
    return jsonify(
        guild={**gd.to_dict(), "owner_id": str(gd.owner_id) if gd.owner_id else None},
        members=_count(Member, Member.guild_id == guild_id),
        campaigns=_count(Campaign, Campaign.guild_id == guild_id),
        submissions=_count(CampaignSubmission, CampaignSubmission.campaign_id.in_(
            g.db.query(Campaign.id).filter(Campaign.guild_id == guild_id)
        )),
        protection_events=_count(ProtectionEvent, ProtectionEvent.guild_id == guild_id),
        recent_events=[e.to_dict() for e in recent],
    )


@admin_bp.post("/api/admin/guilds/<int:guild_id>/plan")
@admin_required
def set_plan(guild_id: int):
    gd = g.db.get(Guild, guild_id)
    if gd is None:
        return jsonify(error="not_found"), 404
    body = request.get_json(silent=True) or {}
    plan = body.get("plan")
    if plan not in ("free", "pro"):
        return jsonify(error="plan must be free or pro"), 400
    gd.plan = plan
    if plan == "pro":
        days = _as_int(body.get("days", 30), 30, 1, 3650)
        gd.plan_expires_at = datetime.utcnow() + timedelta(days=days)
    else:
        gd.plan_expires_at = None
    g.db.commit()
    return jsonify(gd.to_dict())


@admin_bp.get("/api/admin/users")
@admin_required
def users():
    limit = _as_int(request.args.get("limit", 100), 100, 1, 500)
    rows = g.db.query(User).order_by(User.last_login_at.desc()).limit(limit).all()
    out = []
    for u in rows:
        out.append({
            **u.to_dict(),
            "memberships": _count(UserGuild, UserGuild.user_id == u.id),
            "last_login_at": u.last_login_at.isoformat() + "Z" if u.last_login_at else None,
        })
    return jsonify(users=out)


@admin_bp.get("/api/admin/users/<int:user_id>")
@admin_required
def user_detail(user_id: int):
    u = g.db.get(User, user_id)
    if u is None:
        return jsonify(error="not_found"), 404
    rows = (
        g.db.query(UserGuild, Guild)
        .join(Guild, UserGuild.guild_id == Guild.id)
        .filter(UserGuild.user_id == user_id)
        .all()
    )
    memberships = [
        {"guild_id": str(gd.id), "name": gd.name, "can_manage": bool(m.can_manage),
         "is_owner": bool(m.is_owner), "plan": gd.plan}
        for m, gd in rows
    ]
    return jsonify(
        user={**u.to_dict(), "last_login_at": u.last_login_at.isoformat() + "Z" if u.last_login_at else None},
        memberships=memberships,
    )


@admin_bp.get("/api/admin/campaigns")
@admin_required
def campaigns():
    limit = _as_int(request.args.get("limit", 100), 100, 1, 500)
    rows = g.db.query(Campaign).order_by(Campaign.created_at.desc()).limit(limit).all()
    out = []
    for c in rows:
        out.append({
            "id": c.id, "guild_id": str(c.guild_id), "title": c.title,
            "type": c.type, "status": c.status,
            "submissions": _count(CampaignSubmission, CampaignSubmission.campaign_id == c.id),
        })
    return jsonify(campaigns=out)


@admin_bp.get("/api/admin/events")
@admin_required
def events():
    limit = _as_int(request.args.get("limit", 100), 100, 1, 500)
    rows = (
        g.db.query(ProtectionEvent)
        .order_by(ProtectionEvent.created_at.desc())
        .limit(limit)
        .all()
    )
    return jsonify(events=[{**e.to_dict(), "guild_id": str(e.guild_id)} for e in rows])


@admin_bp.get("/api/admin/promo-codes")
@admin_required
def admin_list_promos():
    from models import PromoCode
    rows = g.db.query(PromoCode).order_by(PromoCode.created_at.desc()).limit(100).all()
    return jsonify(codes=[r.to_dict() for r in rows])


@admin_bp.post("/api/admin/promo-codes")
@admin_required
def admin_create_promo():
    import secrets as _secrets

    from models import PromoCode
    body = request.get_json(silent=True) or {}
    code = (str(body.get("code") or "").strip().upper()
            or f"GZ-{_secrets.token_hex(4).upper()}")[:40]
    if g.db.query(PromoCode).filter(PromoCode.code == code).first() is not None:
        return jsonify(error="code_exists"), 409
    try:
        days = max(1, min(365, int(body.get("days_free", 30))))
        max_uses = max(1, min(10000, int(body.get("max_uses", 1))))
    except (TypeError, ValueError):
        return jsonify(error="invalid_numbers"), 400
    row = PromoCode(code=code, days_free=days, max_uses=max_uses)
    g.db.add(row)
    g.db.commit()
    return jsonify(code=row.to_dict()), 201


@admin_bp.delete("/api/admin/promo-codes/<int:pid>")
@admin_required
def admin_delete_promo(pid: int):
    from models import PromoCode
    row = g.db.get(PromoCode, pid)
    if row is None:
        return jsonify(error="not_found"), 404
    row.enabled = False
    g.db.commit()
    return jsonify(ok=True)
