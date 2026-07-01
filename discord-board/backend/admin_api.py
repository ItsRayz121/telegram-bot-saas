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
    AdminAuditLog,
    AITokenUsage,
    Campaign,
    CampaignSubmission,
    Guild,
    GuildDailyStat,
    InviteJoin,
    Member,
    MemberWarning,
    ModReport,
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
    top_members = (
        g.db.query(Member)
        .filter(Member.guild_id == guild_id)
        .order_by(Member.xp.desc())
        .limit(20).all()
    )
    campaign_rows = (
        g.db.query(Campaign)
        .filter(Campaign.guild_id == guild_id)
        .order_by(Campaign.created_at.desc())
        .limit(20).all()
    )
    campaign_list = [
        {"id": c.id, "title": c.title, "type": c.type, "status": c.status,
         "submissions": _count(CampaignSubmission, CampaignSubmission.campaign_id == c.id)}
        for c in campaign_rows
    ]
    owner = g.db.get(User, gd.owner_id) if gd.owner_id else None
    return jsonify(
        guild={**gd.to_dict(), "owner_id": str(gd.owner_id) if gd.owner_id else None},
        owner=({"id": str(owner.id), "username": owner.username,
                "avatar_url": owner.avatar_url()} if owner else None),
        members=_count(Member, Member.guild_id == guild_id),
        campaigns=_count(Campaign, Campaign.guild_id == guild_id),
        submissions=_count(CampaignSubmission, CampaignSubmission.campaign_id.in_(
            g.db.query(Campaign.id).filter(Campaign.guild_id == guild_id)
        )),
        protection_events=_count(ProtectionEvent, ProtectionEvent.guild_id == guild_id),
        recent_events=[e.to_dict() for e in recent],
        top_members=[m.to_dict() for m in top_members],
        campaign_list=campaign_list,
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
    from admin import audit
    audit(g.db, g.user_id, "plan_set", str(guild_id), f"plan={plan}")
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

    # AI usage ledger rollup for this user.
    ai_totals = (
        g.db.query(func.coalesce(func.sum(AITokenUsage.input_tokens), 0),
                   func.coalesce(func.sum(AITokenUsage.output_tokens), 0),
                   func.count(AITokenUsage.id))
        .filter(AITokenUsage.user_id == user_id)
        .one()
    )

    # Risk signals — warnings issued + protection events triggered.
    warnings = (
        g.db.query(MemberWarning)
        .filter(MemberWarning.user_id == user_id)
        .order_by(MemberWarning.created_at.desc())
        .limit(25).all()
    )
    prot = (
        g.db.query(ProtectionEvent)
        .filter(ProtectionEvent.user_id == user_id)
        .order_by(ProtectionEvent.created_at.desc())
        .limit(25).all()
    )

    # Campaign proof submissions by this user.
    sub_counts = dict(
        g.db.query(CampaignSubmission.status, func.count(CampaignSubmission.id))
        .filter(CampaignSubmission.user_id == user_id)
        .group_by(CampaignSubmission.status).all()
    )

    # Admin audit entries naming this user (as actor or target).
    audit_rows = (
        g.db.query(AdminAuditLog)
        .filter((AdminAuditLog.admin_id == user_id) | (AdminAuditLog.target == str(user_id)))
        .order_by(AdminAuditLog.created_at.desc())
        .limit(25).all()
    )

    return jsonify(
        user={**u.to_dict(),
              "last_login_at": u.last_login_at.isoformat() + "Z" if u.last_login_at else None,
              "created_at": u.created_at.isoformat() + "Z" if u.created_at else None,
              "admin_notes": u.admin_notes},
        memberships=memberships,
        ai_usage={"input_tokens": int(ai_totals[0]), "output_tokens": int(ai_totals[1]),
                  "calls": int(ai_totals[2])},
        warnings=[w.to_dict() for w in warnings],
        protection_events=[{**e.to_dict(), "guild_id": str(e.guild_id)} for e in prot],
        submissions={
            "verified": int(sub_counts.get("verified", 0)),
            "pending": int(sub_counts.get("pending", 0)),
            "rejected": int(sub_counts.get("rejected", 0)),
            "total": int(sum(sub_counts.values())),
        },
        audit=[r.to_dict() for r in audit_rows],
    )


@admin_bp.post("/api/admin/users/<int:user_id>/notes")
@admin_required
def set_user_notes(user_id: int):
    """Save the platform-admin private notes on a user."""
    from admin import audit
    u = g.db.get(User, user_id)
    if u is None:
        return jsonify(error="not_found"), 404
    body = request.get_json(silent=True) or {}
    u.admin_notes = (str(body.get("notes") or "")).strip()[:4000] or None
    audit(g.db, g.user_id, "user_notes", str(user_id))
    g.db.commit()
    return jsonify(ok=True, admin_notes=u.admin_notes)


@admin_bp.get("/api/admin/referrals")
@admin_required
def referrals():
    """Invite/referral attribution: top inviters by attributed joins + recent joins."""
    from models import InviteLink
    days = _as_int(request.args.get("days", 30), 30, 1, 180)
    since = datetime.utcnow() - timedelta(days=days)
    top = (
        g.db.query(InviteJoin.inviter_id,
                   func.max(InviteJoin.inviter_name),
                   func.count(InviteJoin.id))
        .filter(InviteJoin.inviter_id.isnot(None))
        .group_by(InviteJoin.inviter_id)
        .order_by(func.count(InviteJoin.id).desc())
        .limit(15).all()
    )
    recent = (
        g.db.query(InviteJoin)
        .order_by(InviteJoin.created_at.desc())
        .limit(20).all()
    )
    return jsonify(
        links_total=_count(InviteLink),
        joins_total=_count(InviteJoin),
        joins_window=_count(InviteJoin, InviteJoin.created_at >= since),
        window_days=days,
        top_inviters=[
            {"inviter_id": str(iid), "inviter_name": name, "joins": int(c)}
            for iid, name, c in top
        ],
        recent=[{**j.to_dict(), "guild_id": str(j.guild_id)} for j in recent],
    )


SUSPICIOUS_CATEGORIES = ("raid", "spam", "nsfw", "csam", "lockdown_join",
                         "join_gate", "manual_lockdown")


@admin_bp.get("/api/admin/suspicious")
@admin_required
def suspicious():
    """Abuse/raid signals from ProtectionEvent — top offending users + recent
    events in the suspicious categories."""
    days = _as_int(request.args.get("days", 14), 14, 1, 90)
    since = datetime.utcnow() - timedelta(days=days)
    base = g.db.query(ProtectionEvent).filter(
        ProtectionEvent.category.in_(SUSPICIOUS_CATEGORIES),
        ProtectionEvent.created_at >= since,
    )
    offenders = (
        g.db.query(ProtectionEvent.user_id,
                   func.max(ProtectionEvent.username),
                   func.count(ProtectionEvent.id))
        .filter(ProtectionEvent.category.in_(SUSPICIOUS_CATEGORIES),
                ProtectionEvent.created_at >= since,
                ProtectionEvent.user_id.isnot(None))
        .group_by(ProtectionEvent.user_id)
        .order_by(func.count(ProtectionEvent.id).desc())
        .limit(15).all()
    )
    recent = base.order_by(ProtectionEvent.created_at.desc()).limit(30).all()
    by_category = dict(
        g.db.query(ProtectionEvent.category, func.count(ProtectionEvent.id))
        .filter(ProtectionEvent.category.in_(SUSPICIOUS_CATEGORIES),
                ProtectionEvent.created_at >= since)
        .group_by(ProtectionEvent.category).all()
    )
    return jsonify(
        window_days=days,
        total=int(sum(by_category.values())),
        by_category={k: int(v) for k, v in by_category.items()},
        top_offenders=[
            {"user_id": str(uid), "username": name, "events": int(c)}
            for uid, name, c in offenders
        ],
        recent=[{**e.to_dict(), "guild_id": str(e.guild_id)} for e in recent],
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


@admin_bp.get("/api/admin/campaigns/<int:campaign_id>")
@admin_required
def campaign_detail(campaign_id: int):
    """One campaign: definition + submission funnel + recent submissions."""
    c = g.db.get(Campaign, campaign_id)
    if c is None:
        return jsonify(error="not_found"), 404
    gd = g.db.get(Guild, c.guild_id)
    counts = dict(
        g.db.query(CampaignSubmission.status, func.count(CampaignSubmission.id))
        .filter(CampaignSubmission.campaign_id == campaign_id)
        .group_by(CampaignSubmission.status).all()
    )
    recent = (
        g.db.query(CampaignSubmission)
        .filter(CampaignSubmission.campaign_id == campaign_id)
        .order_by(CampaignSubmission.created_at.desc())
        .limit(25).all()
    )
    return jsonify(
        campaign=c.to_dict(include_tasks=True),
        guild={"id": str(c.guild_id), "name": gd.name if gd else None},
        submissions={
            "verified": int(counts.get("verified", 0)),
            "pending": int(counts.get("pending", 0)),
            "rejected": int(counts.get("rejected", 0)),
            "total": int(sum(counts.values())),
        },
        recent=[s.to_dict() for s in recent],
    )


@admin_bp.get("/api/admin/event-log")
@admin_required
def event_log():
    """Merged platform event timeline: protection actions + feature-usage events."""
    from models import FeatureUsageEvent
    limit = _as_int(request.args.get("limit", 60), 60, 10, 200)
    prot = (
        g.db.query(ProtectionEvent)
        .order_by(ProtectionEvent.created_at.desc())
        .limit(limit).all()
    )
    feat = (
        g.db.query(FeatureUsageEvent)
        .order_by(FeatureUsageEvent.created_at.desc())
        .limit(limit).all()
    )
    items = [
        {"kind": "protection", "id": f"p{e.id}", "label": e.category or "event",
         "detail": f"{e.action or '—'}{' · ' + e.detail if e.detail else ''}",
         "guild_id": str(e.guild_id),
         "created_at": e.created_at.isoformat() + "Z" if e.created_at else None}
        for e in prot
    ] + [
        {"kind": "feature", "id": f"f{e.id}", "label": e.feature,
         "detail": "command run",
         "guild_id": str(e.guild_id) if e.guild_id else None,
         "created_at": e.created_at.isoformat() + "Z" if e.created_at else None}
        for e in feat
    ]
    items.sort(key=lambda x: x["created_at"] or "", reverse=True)
    return jsonify(events=items[:limit])


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


# --- Phase 2 (admin parity): Overview category data ---
def _month_floor(dt: datetime) -> datetime:
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _month_prev(dt: datetime) -> datetime:
    return dt.replace(year=dt.year - 1, month=12) if dt.month == 1 else dt.replace(month=dt.month - 1)


def _month_next(dt: datetime) -> datetime:
    return dt.replace(year=dt.year + 1, month=1) if dt.month == 12 else dt.replace(month=dt.month + 1)


@admin_bp.get("/api/admin/revenue")
@admin_required
def revenue():
    """Subscription revenue rollup. `amount` is whole USD per period; MRR
    normalizes every active subscription to a 30-day month."""
    active = g.db.query(Subscription).filter(Subscription.status == "active").all()

    def _mrr(sub) -> float:
        days = sub.period_days or 30
        return (sub.amount or 0) * 30.0 / days if days else 0.0

    mrr = sum(_mrr(s) for s in active)
    total_all_time = int(
        g.db.query(func.coalesce(func.sum(Subscription.amount), 0))
        .filter(Subscription.status == "active")
        .scalar() or 0
    )

    def _gross(since, until=None) -> int:
        q = g.db.query(func.coalesce(func.sum(Subscription.amount), 0)).filter(
            Subscription.status == "active", Subscription.activated_at >= since)
        if until is not None:
            q = q.filter(Subscription.activated_at < until)
        return int(q.scalar() or 0)

    month_start = _month_floor(datetime.utcnow())
    prev_start = _month_prev(month_start)

    months, cursor = [], month_start
    for _ in range(6):
        months.append(cursor)
        cursor = _month_prev(cursor)
    trend = [{"month": m.strftime("%b"), "revenue": _gross(m, _month_next(m))}
             for m in reversed(months)]

    recent = (
        g.db.query(Subscription)
        .filter(Subscription.status == "active")
        .order_by(Subscription.created_at.desc())
        .limit(10)
        .all()
    )
    return jsonify(
        mrr=round(mrr, 2), arr=round(mrr * 12, 2),
        this_month=_gross(month_start), last_month=_gross(prev_start, month_start),
        total_all_time=total_all_time, active_count=len(active),
        monthly_trend=trend,
        recent=[{**s.to_dict(), "guild_id": str(s.guild_id)} for s in recent],
    )


@admin_bp.get("/api/admin/growth")
@admin_required
def growth():
    """Platform-wide daily activity series (messages / joins / leaves) summed
    across all guilds, for the trailing window."""
    days = _as_int(request.args.get("days", 30), 30, 1, 180)
    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = (
        g.db.query(
            GuildDailyStat.day,
            func.coalesce(func.sum(GuildDailyStat.messages), 0),
            func.coalesce(func.sum(GuildDailyStat.joins), 0),
            func.coalesce(func.sum(GuildDailyStat.leaves), 0),
        )
        .filter(GuildDailyStat.day >= cutoff)
        .group_by(GuildDailyStat.day)
        .order_by(GuildDailyStat.day)
        .all()
    )
    return jsonify(days=days, series=[
        {"day": d, "messages": int(m), "joins": int(j), "leaves": int(l)}
        for d, m, j, l in rows
    ])


@admin_bp.get("/api/admin/reports")
@admin_required
def reports():
    """Moderation report queue (ModReport) with per-status counts."""
    status = request.args.get("status")
    limit = _as_int(request.args.get("limit", 100), 100, 1, 500)
    q = g.db.query(ModReport)
    if status in ("open", "actioned", "dismissed"):
        q = q.filter(ModReport.status == status)
    rows = q.order_by(ModReport.created_at.desc()).limit(limit).all()
    counts = dict(
        g.db.query(ModReport.status, func.count(ModReport.id))
        .group_by(ModReport.status).all()
    )
    return jsonify(
        reports=[{**r.to_dict(), "guild_id": str(r.guild_id)} for r in rows],
        counts={
            "open": int(counts.get("open", 0)),
            "actioned": int(counts.get("actioned", 0)),
            "dismissed": int(counts.get("dismissed", 0)),
            "total": int(sum(counts.values())),
        },
    )


@admin_bp.get("/api/admin/proof-metrics")
@admin_required
def proof_metrics():
    """Campaign proof-submission funnel: verified / pending / rejected, approval
    rate, rewards granted, and the latest submissions."""
    days = _as_int(request.args.get("days", 30), 30, 1, 180)
    since = datetime.utcnow() - timedelta(days=days)
    counts = dict(
        g.db.query(CampaignSubmission.status, func.count(CampaignSubmission.id))
        .group_by(CampaignSubmission.status).all()
    )
    verified = int(counts.get("verified", 0))
    rejected = int(counts.get("rejected", 0))
    pending = int(counts.get("pending", 0))
    total = int(sum(counts.values()))
    reviewed = verified + rejected
    rewards = int(
        g.db.query(func.coalesce(func.sum(CampaignSubmission.reward_granted), 0)).scalar() or 0
    )
    window = int(
        g.db.query(func.count(CampaignSubmission.id))
        .filter(CampaignSubmission.created_at >= since).scalar() or 0
    )
    recent = (
        g.db.query(CampaignSubmission)
        .order_by(CampaignSubmission.created_at.desc())
        .limit(15).all()
    )
    return jsonify(
        days=days, total=total, verified=verified, rejected=rejected, pending=pending,
        approval_rate=round(verified / reviewed * 100, 1) if reviewed else 0.0,
        rewards_granted=rewards, submissions_window=window,
        recent=[s.to_dict() for s in recent],
    )


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
    from admin import audit
    audit(g.db, g.user_id, "promo_create", code, f"days={days} uses={max_uses}")
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
    from admin import audit
    audit(g.db, g.user_id, "promo_disable", row.code)
    g.db.commit()
    return jsonify(ok=True)


# --- Phase 19: roles, audit log, fleet health, usage & AI analytics, GDPR purge ---
@admin_bp.get("/api/admin/roles")
@admin_required
def admin_roles():
    from models import AdminRole
    rows = g.db.query(AdminRole).order_by(AdminRole.created_at).all()
    return jsonify(roles=[r.to_dict() for r in rows],
                   env_super_ids=[str(i) for i in sorted(__import__("config").Config.ADMIN_USER_IDS)])


@admin_bp.post("/api/admin/roles")
@admin_required
def grant_role():
    from admin import audit, is_super
    from models import AdminRole, User
    if not is_super(g.user_id):
        return jsonify(error="super_admin_required"), 403
    body = request.get_json(silent=True) or {}
    uid = str(body.get("user_id") or "").strip()
    role = body.get("role") if body.get("role") in ("support", "super") else "support"
    if not uid.isdigit():
        return jsonify(error="discord_user_id_required"), 400
    uid = int(uid)
    row = g.db.get(AdminRole, uid)
    if row is None:
        user = g.db.get(User, uid)
        row = AdminRole(user_id=uid, username=(user.username if user else None),
                        role=role, granted_by=g.user_id)
        g.db.add(row)
    else:
        row.role = role
    audit(g.db, g.user_id, "role_grant", str(uid), f"role={role}")
    g.db.commit()
    return jsonify(role=row.to_dict()), 201


@admin_bp.delete("/api/admin/roles/<int:user_id>")
@admin_required
def revoke_role(user_id: int):
    from admin import audit, is_super
    from models import AdminRole
    if not is_super(g.user_id):
        return jsonify(error="super_admin_required"), 403
    row = g.db.get(AdminRole, user_id)
    if row is None:
        return jsonify(error="not_found"), 404
    g.db.delete(row)
    audit(g.db, g.user_id, "role_revoke", str(user_id))
    g.db.commit()
    return jsonify(ok=True)


@admin_bp.get("/api/admin/audit-log")
@admin_required
def audit_log():
    from models import AdminAuditLog
    rows = (
        g.db.query(AdminAuditLog)
        .order_by(AdminAuditLog.created_at.desc())
        .limit(100)
        .all()
    )
    return jsonify(entries=[r.to_dict() for r in rows])


@admin_bp.get("/api/admin/fleet")
@admin_required
def fleet():
    """White-label fleet health: every custom bot + recent health events."""
    from models import BotHealthEvent, CustomBot, Guild
    bots = g.db.query(CustomBot).order_by(CustomBot.created_at).limit(100).all()
    out = []
    for b in bots:
        linked = g.db.query(Guild).filter(Guild.custom_bot_id == b.id).count()
        data = b.to_dict()
        data["linked_guild_count"] = linked
        out.append(data)
    events = (
        g.db.query(BotHealthEvent)
        .order_by(BotHealthEvent.created_at.desc())
        .limit(50)
        .all()
    )
    return jsonify(bots=out, events=[e.to_dict() for e in events])


@admin_bp.get("/api/admin/custom-bots/<int:bot_id>")
@admin_required
def custom_bot_detail(bot_id: int):
    """Full drill-down for one white-label bot: owner, linked servers, health
    history + a daily connect/disconnect/error series for the chart."""
    from models import BotHealthEvent, CustomBot, Guild
    b = g.db.get(CustomBot, bot_id)
    if b is None:
        return jsonify(error="not_found"), 404
    owner = g.db.get(User, b.owner_user_id) if b.owner_user_id else None
    linked = (
        g.db.query(Guild).filter(Guild.custom_bot_id == bot_id)
        .order_by(Guild.member_count.desc()).all()
    )
    events = (
        g.db.query(BotHealthEvent)
        .filter(BotHealthEvent.custom_bot_id == bot_id)
        .order_by(BotHealthEvent.created_at.desc())
        .limit(80).all()
    )
    # 14-day daily rollup by event type, for the recharts area/line.
    since = datetime.utcnow() - timedelta(days=14)
    daily: dict[str, dict] = {}
    for e in events:
        if not e.created_at or e.created_at < since:
            continue
        day = e.created_at.strftime("%Y-%m-%d")
        slot = daily.setdefault(day, {"day": day, "connect": 0, "disconnect": 0, "error": 0})
        if e.event in ("error", "auth_failed"):
            slot["error"] += 1
        elif e.event == "disconnect":
            slot["disconnect"] += 1
        elif e.event == "connect":
            slot["connect"] += 1
    errors = [e for e in events if e.event in ("error", "auth_failed")]
    return jsonify(
        bot=b.to_dict(),
        owner=({"id": str(owner.id), "username": owner.username,
                "avatar_url": owner.avatar_url()} if owner else None),
        linked_guilds=[
            {"id": str(gd.id), "name": gd.name, "member_count": gd.member_count, "plan": gd.plan}
            for gd in linked
        ],
        events=[e.to_dict() for e in events],
        errors=[e.to_dict() for e in errors[:25]],
        daily=[daily[d] for d in sorted(daily)],
    )


@admin_bp.post("/api/admin/custom-bots/<int:bot_id>/status")
@admin_required
def set_custom_bot_status(bot_id: int):
    """Platform-admin enable/disable of a white-label bot. Flags needs_restart so
    the fleet worker picks up the change."""
    from admin import audit
    from models import CustomBot
    b = g.db.get(CustomBot, bot_id)
    if b is None:
        return jsonify(error="not_found"), 404
    body = request.get_json(silent=True) or {}
    status = body.get("status")
    if status not in ("active", "disabled"):
        return jsonify(error="status must be active or disabled"), 400
    b.status = status
    b.needs_restart = True
    audit(g.db, g.user_id, "custom_bot_status", str(bot_id), f"status={status}")
    g.db.commit()
    return jsonify(b.to_dict())


@admin_bp.get("/api/admin/diagnostics")
@admin_required
def diagnostics():
    """Connectivity / intents health rollup for the Bots & Servers diagnostics tab."""
    from models import BotHealthEvent, CustomBot
    bots = g.db.query(CustomBot).all()
    by_status = {"active": 0, "disabled": 0, "error": 0}
    intents_issues = 0
    for b in bots:
        by_status[b.status] = by_status.get(b.status, 0) + 1
        if b.status == "active" and not (b.intents_members and b.intents_message_content):
            intents_issues += 1
    since = datetime.utcnow() - timedelta(days=7)
    recent_errors = (
        g.db.query(BotHealthEvent)
        .filter(BotHealthEvent.event.in_(("error", "auth_failed")),
                BotHealthEvent.created_at >= since)
        .order_by(BotHealthEvent.created_at.desc())
        .limit(25).all()
    )
    return jsonify(
        guilds_total=_count(Guild),
        guilds_with_bot=_count(Guild, Guild.bot_present.is_(True)),
        guilds_without_bot=_count(Guild, Guild.bot_present.is_(False)),
        custom_bots_total=len(bots),
        custom_bots_by_status=by_status,
        intents_issues=intents_issues,
        recent_errors=[e.to_dict() for e in recent_errors],
    )


@admin_bp.get("/api/admin/feature-usage")
@admin_required
def feature_usage():
    from models import FeatureUsageEvent
    days = _as_int(request.args.get("days", 14), 14, 1, 90)
    since = datetime.utcnow() - timedelta(days=days)
    by_feature = (
        g.db.query(FeatureUsageEvent.feature, func.count(FeatureUsageEvent.id))
        .filter(FeatureUsageEvent.created_at >= since)
        .group_by(FeatureUsageEvent.feature)
        .order_by(func.count(FeatureUsageEvent.id).desc())
        .limit(40)
        .all()
    )
    total = (
        g.db.query(FeatureUsageEvent)
        .filter(FeatureUsageEvent.created_at >= since)
        .count()
    )
    return jsonify(days=days, total=total,
                   features=[{"feature": f, "count": c} for f, c in by_feature])


@admin_bp.get("/api/admin/ai-usage")
@admin_required
def ai_usage():
    from models import AITokenUsage
    days = _as_int(request.args.get("days", 30), 30, 1, 90)
    since = datetime.utcnow() - timedelta(days=days)
    totals = (
        g.db.query(func.coalesce(func.sum(AITokenUsage.input_tokens), 0),
                   func.coalesce(func.sum(AITokenUsage.output_tokens), 0),
                   func.count(AITokenUsage.id))
        .filter(AITokenUsage.created_at >= since)
        .one()
    )
    top_guilds = (
        g.db.query(AITokenUsage.guild_id,
                   func.sum(AITokenUsage.input_tokens + AITokenUsage.output_tokens))
        .filter(AITokenUsage.created_at >= since, AITokenUsage.guild_id.isnot(None))
        .group_by(AITokenUsage.guild_id)
        .order_by(func.sum(AITokenUsage.input_tokens + AITokenUsage.output_tokens).desc())
        .limit(10)
        .all()
    )
    # Daily token series (bucketed in Python to stay DB-agnostic across sqlite/pg).
    rows = (
        g.db.query(AITokenUsage.created_at, AITokenUsage.input_tokens, AITokenUsage.output_tokens)
        .filter(AITokenUsage.created_at >= since)
        .all()
    )
    buckets: dict[str, dict] = {}
    for created, inp, out in rows:
        if not created:
            continue
        day = created.strftime("%Y-%m-%d")
        slot = buckets.setdefault(day, {"day": day, "input": 0, "output": 0})
        slot["input"] += int(inp or 0)
        slot["output"] += int(out or 0)
    series = [buckets[d] for d in sorted(buckets)]
    return jsonify(days=days, input_tokens=int(totals[0]), output_tokens=int(totals[1]),
                   calls=int(totals[2]), series=series,
                   top_guilds=[{"guild_id": str(gid), "tokens": int(t)} for gid, t in top_guilds])


@admin_bp.get("/api/admin/ai-health")
@admin_required
def ai_health():
    """AI provider health for the admin panel. Returns a config snapshot (which
    provider/chain/keys/models are active, no network call). Pass ?ping=1 to also
    fire one live tiny call and report which provider answered + latency.

    NB: this runs in the WEB service, so the AI env vars (GUILDIZER_AI_PROVIDER,
    OPENROUTER_API_KEY, OPENAI_API_KEY, ...) must also be set here for it to
    reflect what the bot worker sees."""
    import ai
    data = ai.status()
    if request.args.get("ping") in ("1", "true", "yes"):
        data["ping"] = ai.probe()
    return jsonify(data)


# --- Phase 6 (admin parity): Platform Settings ---
@admin_bp.get("/api/admin/config")
@admin_required
def admin_config():
    """Non-secret configuration snapshot (pricing, AI, URLs, session). Never
    returns secret values — see /api/admin/secrets for is-set booleans."""
    from config import Config
    return jsonify(
        pricing={"pro_price_usd": Config.PRO_PRICE_USD, "pro_period_days": Config.PRO_PERIOD_DAYS,
                 "currency": "usd", "provider": "nowpayments"},
        ai={"provider": Config.AI_PROVIDER, "text_model": Config.AI_MODEL or "(provider default)",
            "vision_model": Config.VISION_MODEL, "max_tokens": Config.AI_MAX_TOKENS},
        urls={"frontend": Config.FRONTEND_URL, "backend": Config.BACKEND_URL,
              "guildizer_path": Config.GUILDIZER_FRONTEND_PATH,
              "redirect_uri": Config.DISCORD_REDIRECT_URI},
        discord={"client_id": Config.DISCORD_CLIENT_ID or None,
                 "bot_permissions": Config.DISCORD_BOT_PERMISSIONS or "(default)"},
        session={"cookie_name": Config.SESSION_COOKIE_NAME, "secure": Config.SESSION_COOKIE_SECURE,
                 "samesite": Config.SESSION_COOKIE_SAMESITE, "max_age_days": Config.SESSION_MAX_AGE // 86400},
        admins={"env_super_ids": [str(i) for i in sorted(Config.ADMIN_USER_IDS)]},
    )


@admin_bp.get("/api/admin/secrets")
@admin_required
def admin_secrets():
    """is-set booleans for every secret — never the values. Super-admin only."""
    from admin import is_super
    from config import Config
    if not is_super(g.user_id):
        return jsonify(error="super_admin_required"), 403
    keys = {
        "DISCORD_BOT_TOKEN": Config.DISCORD_BOT_TOKEN,
        "DISCORD_CLIENT_SECRET": Config.DISCORD_CLIENT_SECRET,
        "OPENAI_API_KEY": Config.OPENAI_API_KEY,
        "OPENROUTER_API_KEY": Config.OPENROUTER_API_KEY,
        "ANTHROPIC_API_KEY": Config.ANTHROPIC_API_KEY,
        "NOWPAYMENTS_API_KEY": Config.NOWPAYMENTS_API_KEY,
        "NOWPAYMENTS_IPN_SECRET": Config.NOWPAYMENTS_IPN_SECRET,
        "GUILDIZER_ENCRYPTION_KEY": Config.ENCRYPTION_KEY,
        "FLASK_SECRET_KEY": "" if Config.SECRET_KEY == "dev-secret-change-me" else Config.SECRET_KEY,
        "DATABASE_URL": Config.DATABASE_URL,
    }
    return jsonify(secrets=[{"key": k, "set": bool(v)} for k, v in keys.items()])


@admin_bp.get("/api/admin/system")
@admin_required
def admin_system():
    """Web/worker/DB health, version, and core counts."""
    from sqlalchemy import text

    from config import Config
    db_ok, dialect = True, "unknown"
    try:
        g.db.execute(text("SELECT 1"))
        dialect = g.db.get_bind().dialect.name
    except Exception:  # pragma: no cover - defensive
        db_ok = False
    try:
        import ai
        ai_status = ai.status()
    except Exception:  # pragma: no cover
        ai_status = {"configured": False, "chain": []}
    return jsonify(
        db={"ok": db_ok, "dialect": dialect,
            "guilds": _count(Guild), "users": _count(User), "members": _count(Member)},
        ai={"configured": bool(ai_status.get("configured")), "provider": Config.AI_PROVIDER,
            "chain": ai_status.get("chain", [])},
        billing={"nowpayments_configured": bool(Config.NOWPAYMENTS_API_KEY)},
        bot={"token_set": bool(Config.DISCORD_BOT_TOKEN)},
        time_utc=datetime.utcnow().isoformat() + "Z",
    )


# --- Phase 7 (admin parity): Compliance & Comms — announcements ---
@admin_bp.get("/api/admin/announcements")
@admin_required
def list_announcements():
    from models import AdminAnnouncement
    rows = (
        g.db.query(AdminAnnouncement)
        .order_by(AdminAnnouncement.created_at.desc())
        .limit(100).all()
    )
    return jsonify(announcements=[r.to_dict() for r in rows])


_ANN_CHANNELS = ("banner", "inapp")


def _announcement_audience_users(db, audience: str):
    """User rows in the audience. Guildizer audiences are coarse (all) since a
    user can manage guilds on mixed tiers; kept for parity with Telegizer."""
    from models import User
    return db.query(User).all()


def _reach_breakdown(db, audience: str) -> dict:
    from web_push import get_prefs
    users = _announcement_audience_users(db, audience)
    total = len(users)
    opted_in = sum(1 for u in users if get_prefs(u).get("announcements", True))
    return {"total": total, "inapp": opted_in, "banner": opted_in}


@admin_bp.get("/api/admin/announcements/reach")
@admin_required
def announcement_reach():
    return jsonify(reach=_reach_breakdown(g.db, request.args.get("audience", "all")))


@admin_bp.post("/api/admin/announcements")
@admin_required
def create_announcement():
    from datetime import datetime
    from admin import audit
    from access import notify
    from web_push import get_prefs
    from models import AdminAnnouncement, User
    body = request.get_json(silent=True) or {}
    title = (str(body.get("title") or "")).strip()[:200]
    if not title:
        return jsonify(error="title_required"), 400
    level = body.get("level") if body.get("level") in ("info", "warning", "critical") else "info"
    audience = body.get("audience") if body.get("audience") in ("all", "free", "pro") else "all"

    channels = body.get("channels")
    if not channels:
        channels = ["banner"]  # legacy default
    channels = [c for c in channels if c in _ANN_CHANNELS]
    if not channels:
        return jsonify(error="no_valid_channel"), 400

    text = (str(body.get("body") or "")).strip()[:2000]
    row = AdminAnnouncement(
        title=title, body=text, level=level,
        active=("banner" in channels), audience=audience,
        channels=",".join(channels), created_by=g.user_id,
    )
    g.db.add(row)
    g.db.flush()

    users = _announcement_audience_users(g.db, audience)
    opted_in = [u for u in users if get_prefs(u).get("announcements", True)]
    row.reach_count = len(opted_in)
    delivered = 0
    if "inapp" in channels:
        kind = "error" if level == "critical" else ("warning" if level == "warning" else "info")
        for u in opted_in:
            notify(g.db, u.id, title, text, kind=kind)
            delivered += 1
    row.delivered_count = delivered
    row.sent_at = datetime.utcnow()

    audit(g.db, g.user_id, "announce_create", title, f"level={level} ch={','.join(channels)}")
    g.db.commit()
    return jsonify(announcement=row.to_dict()), 201


@admin_bp.post("/api/admin/announcements/<int:aid>/toggle")
@admin_required
def toggle_announcement(aid: int):
    from models import AdminAnnouncement
    row = g.db.get(AdminAnnouncement, aid)
    if row is None:
        return jsonify(error="not_found"), 404
    row.active = not row.active
    g.db.commit()
    return jsonify(announcement=row.to_dict())


@admin_bp.post("/api/admin/announcements/<int:aid>/retire")
@admin_required
def retire_announcement(aid: int):
    """Take a live banner down without deleting the announcement or its stats."""
    from models import AdminAnnouncement
    row = g.db.get(AdminAnnouncement, aid)
    if row is None:
        return jsonify(error="not_found"), 404
    row.active = False
    g.db.commit()
    return jsonify(announcement=row.to_dict())


@admin_bp.delete("/api/admin/announcements/<int:aid>")
@admin_required
def delete_announcement(aid: int):
    from admin import audit
    from models import AdminAnnouncement
    row = g.db.get(AdminAnnouncement, aid)
    if row is None:
        return jsonify(error="not_found"), 404
    g.db.delete(row)
    audit(g.db, g.user_id, "announce_delete", str(aid))
    g.db.commit()
    return jsonify(ok=True)


@admin_bp.post("/api/admin/users/<int:user_id>/purge")
@admin_required
def purge_user(user_id: int):
    """GDPR purge (Phase 19 compliance): delete the user's personal data.
    Guild-level rows they administered stay (they belong to the server), but
    their username is anonymized wherever it appears in those rows."""
    from admin import audit, is_super
    from models import (CampaignSubmission, CustomBot, Guild, GuildTeamMember,
                        InviteJoin, Member, MemberWarning, ModReport, Note,
                        ProtectionEvent, Reminder, Task, User, UserGuild,
                        UserNotification)
    if not is_super(g.user_id):
        return jsonify(error="super_admin_required"), 403

    counts = {}
    for model, col in ((Reminder, Reminder.user_id), (Note, Note.user_id),
                       (Task, Task.user_id), (UserNotification, UserNotification.user_id),
                       (GuildTeamMember, GuildTeamMember.user_id),
                       (UserGuild, UserGuild.user_id), (Member, Member.user_id)):
        counts[model.__tablename__] = g.db.query(model).filter(col == user_id).delete()

    # Guild-owned records stay, but usernames are personal data — anonymize.
    anonymized = 0
    for model, id_col, name_col in (
        (MemberWarning, MemberWarning.user_id, "username"),
        (MemberWarning, MemberWarning.moderator_id, "moderator_name"),
        (CampaignSubmission, CampaignSubmission.user_id, "username"),
        (ProtectionEvent, ProtectionEvent.user_id, "username"),
        (InviteJoin, InviteJoin.inviter_id, "inviter_name"),
        (InviteJoin, InviteJoin.joiner_id, "joiner_name"),
        (ModReport, ModReport.reporter_id, "reporter_name"),
        (ModReport, ModReport.target_id, "target_name"),
    ):
        anonymized += g.db.query(model).filter(id_col == user_id).update(
            {name_col: None}, synchronize_session=False)
    counts["usernames_anonymized"] = anonymized

    bots = g.db.query(CustomBot).filter(CustomBot.owner_user_id == user_id).all()
    for b in bots:
        g.db.query(Guild).filter(Guild.custom_bot_id == b.id).update({"custom_bot_id": None})
        g.db.delete(b)
    counts["custom_bots"] = len(bots)
    user = g.db.get(User, user_id)
    if user is not None:
        g.db.delete(user)
        counts["users"] = 1
    audit(g.db, g.user_id, "user_purge", str(user_id),
          ", ".join(f"{k}={v}" for k, v in counts.items() if v))
    g.db.commit()
    return jsonify(ok=True, purged=counts)
