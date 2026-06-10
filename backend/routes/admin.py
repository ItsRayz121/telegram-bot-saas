from datetime import datetime, timedelta
from functools import wraps
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
import json
import logging
from ..models import (
    db, User, Bot, Group, Member, SuspiciousActivity, Referral,
    TelegramGroup, CustomBot, BotEvent, BotHealthEvent, AdminAuditLog, DirectoryListing,
    PaymentHistory, SubscriptionRenewal, UserNotification, AdminAnnouncement,
    ReportedMessage, OfficialReportedMessage,
    AutomationWorkflow, WorkspaceReminder, Note, Channel, KnowledgeDocument,
    PromoCode, PromoCodeUsage, OfficialMember,
)
from ..config import Config
from ..middleware.rate_limit import rate_limit
from .. import admin_rbac as rbac

_log = logging.getLogger("admin")

admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")

# Keys never written to the audit-log payload, even after sanitisation. Matched
# case-insensitively. Extend this as new secret-bearing fields are added.
_AUDIT_SECRET_KEYS = {
    "password", "token", "api_key", "api_key_encrypted", "secret",
    "bot_token", "ipn_secret", "webhook_secret", "smtp_password",
    "client_secret", "value", "new_secret", "old_secret",
}


def _get_current_user():
    user_id = get_jwt_identity()
    return User.query.get(int(user_id))


def _write_audit(user, severity="info"):
    """Record an admin action. Best-effort: never blocks the request."""
    try:
        body = request.get_json(silent=True) or {}
        sanitised = {k: v for k, v in body.items() if k.lower() not in _AUDIT_SECRET_KEYS}
        log = AdminAuditLog(
            admin_id=user.id,
            action=request.endpoint or "",
            method=request.method,
            path=request.path,
            payload_json=json.dumps(sanitised) if sanitised else None,
            ip_address=request.remote_addr,
            severity=severity,
        )
        db.session.add(log)
        db.session.commit()
    except Exception:
        db.session.rollback()


def _build_admin_decorator(permission=None):
    """Factory for the admin gate. ``permission=None`` ⇒ any admin role is allowed
    (backwards-compatible with the old @admin_required). A permission key ⇒ the
    caller's role must grant it. Every allowed call is audit-logged."""
    def wrapper(f):
        @wraps(f)
        @jwt_required()
        def decorated(*args, **kwargs):
            user = _get_current_user()
            if not user:
                _log.warning("admin gate: JWT resolved but user not found — route=%s", request.path)
                return jsonify({"error": "User not found"}), 404

            if not rbac.is_admin(user):
                _log.warning("admin gate: access denied — email=%s route=%s reason=not_admin",
                             user.email, request.path)
                return jsonify({"error": "Admin access required", "reason": "not_in_allowlist"}), 403

            if Config.ENFORCE_ADMIN_2FA and not user.totp_enabled:
                _log.warning("admin gate: access denied — email=%s route=%s reason=2fa_required",
                             user.email, request.path)
                return jsonify({
                    "error": "Admin accounts must have 2FA enabled",
                    "reason": "2fa_required",
                }), 403

            if permission and not rbac.has_permission(user, permission):
                _log.warning("admin gate: permission denied — email=%s role=%s perm=%s route=%s",
                             user.email, rbac.resolve_admin_role(user), permission, request.path)
                return jsonify({
                    "error": "You do not have permission to perform this action.",
                    "reason": "missing_permission",
                    "required_permission": permission,
                }), 403

            severity = "info" if request.method == "GET" else "notice"
            _write_audit(user, severity)
            return f(*args, **kwargs)
        return decorated
    return wrapper


def admin_required(f):
    """Allow any admin role. Use require_permission(...) for scoped routes."""
    return _build_admin_decorator(None)(f)


def require_permission(permission):
    """Decorator factory — require a specific RBAC permission key."""
    return _build_admin_decorator(permission)


# ── User Management ────────────────────────────────────────────────────────────

@admin_bp.route("/users", methods=["GET"])
@require_permission(rbac.P_USERS_VIEW)
@rate_limit(requests_per_minute=60)
def list_users():
    """Paginated user list with real backend search, filtering and sorting.

    Search spans name, email, Telegram username, Telegram ID and numeric user ID
    (an all-digits query also matches the user PK). Sort options that rank by
    revenue / groups / referrals are backed by aggregate sub-queries so the
    ordering is correct across the whole table, not just the current page.
    """
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 100)
    search = (request.args.get("search", "") or "").strip()
    tier = request.args.get("tier", "")
    status = request.args.get("status", "")
    auth_provider = request.args.get("auth_provider", "")   # email | telegram | both
    verified = request.args.get("verified", "")             # yes | no  (email verified)
    joined_after = request.args.get("joined_after", "")     # ISO date
    joined_before = request.args.get("joined_before", "")   # ISO date
    sort = request.args.get("sort", "created_at")           # created_at|email|revenue|groups|referrals
    order = request.args.get("order", "desc")               # asc | desc

    query = User.query

    if search:
        like = f"%{search}%"
        conds = [
            User.email.ilike(like),
            User.full_name.ilike(like),
            User.telegram_username.ilike(like),
            User.telegram_user_id.ilike(like),
        ]
        if search.isdigit():
            conds.append(User.id == int(search))
        query = query.filter(db.or_(*conds))

    if tier in ("free", "pro", "enterprise"):
        query = query.filter(User.subscription_tier == tier)

    if status == "banned":
        query = query.filter(User.is_banned == True)  # noqa: E712
    elif status == "active":
        query = query.filter(User.is_banned == False)  # noqa: E712
    elif status == "suspicious":
        query = query.filter(User.is_suspicious == True)  # noqa: E712

    if auth_provider in ("email", "telegram", "both"):
        query = query.filter(User.auth_provider == auth_provider)

    if verified == "yes":
        query = query.filter(User.email_verified == True)  # noqa: E712
    elif verified == "no":
        query = query.filter(User.email_verified == False)  # noqa: E712

    def _parse_date(s):
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
        except (ValueError, AttributeError):
            return None

    if joined_after:
        d = _parse_date(joined_after)
        if d:
            query = query.filter(User.created_at >= d)
    if joined_before:
        d = _parse_date(joined_before)
        if d:
            query = query.filter(User.created_at < d)

    descending = order != "asc"

    # Sorts that need an aggregate join. Each sub-query is grouped by user_id so
    # the outer join stays 1:1 and pagination remains correct.
    if sort == "revenue":
        rev_sq = (
            db.session.query(
                PaymentHistory.user_id.label("uid"),
                db.func.coalesce(db.func.sum(PaymentHistory.amount_usd), 0).label("rev"),
            )
            .filter(PaymentHistory.status == "confirmed")
            .group_by(PaymentHistory.user_id)
            .subquery()
        )
        query = query.outerjoin(rev_sq, rev_sq.c.uid == User.id)
        col = db.func.coalesce(rev_sq.c.rev, 0)
        query = query.order_by(col.desc() if descending else col.asc())
    elif sort == "groups":
        grp_sq = (
            db.session.query(
                TelegramGroup.owner_user_id.label("uid"),
                db.func.count(TelegramGroup.id).label("cnt"),
            )
            .filter(TelegramGroup.owner_user_id.isnot(None))
            .group_by(TelegramGroup.owner_user_id)
            .subquery()
        )
        query = query.outerjoin(grp_sq, grp_sq.c.uid == User.id)
        col = db.func.coalesce(grp_sq.c.cnt, 0)
        query = query.order_by(col.desc() if descending else col.asc())
    elif sort == "referrals":
        ref_sq = (
            db.session.query(
                Referral.referrer_user_id.label("uid"),
                db.func.count(Referral.id).label("cnt"),
            )
            .group_by(Referral.referrer_user_id)
            .subquery()
        )
        query = query.outerjoin(ref_sq, ref_sq.c.uid == User.id)
        col = db.func.coalesce(ref_sq.c.cnt, 0)
        query = query.order_by(col.desc() if descending else col.asc())
    elif sort == "email":
        query = query.order_by(User.email.desc() if descending else User.email.asc())
    else:  # created_at (default)
        query = query.order_by(User.created_at.desc() if descending else User.created_at.asc())

    paginated = query.paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        "users": [u.to_dict() for u in paginated.items],
        "total": paginated.total,
        "pages": paginated.pages,
        "page": page,
        "per_page": per_page,
        "sort": sort,
        "order": order,
    })


@admin_bp.route("/users/<int:user_id>", methods=["GET"])
@require_permission(rbac.P_USERS_VIEW)
@rate_limit(requests_per_minute=60)
def get_user(user_id):
    """Full audit profile for one user — everything the admin panel can derive
    from existing tables. Fields we don't yet track are returned as null with a
    `not_tracked` marker so the UI can honestly show "Not tracked yet" rather
    than fabricate data.
    """
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    user_data = user.to_dict()

    # ── Auth source & verification ─────────────────────────────────────────────
    user_data["auth"] = {
        "provider": user.auth_provider or "email",
        "has_password": bool(user.password_hash),
        "email_linked": bool(user.email),
        "telegram_linked": bool(user.telegram_user_id),
        "telegram_user_id": user.telegram_user_id,
        "telegram_connected_at": user.telegram_connected_at.isoformat() if user.telegram_connected_at else None,
        "email_verified": bool(user.email_verified),
        "telegram_verified": bool(user.telegram_user_id),
        "two_factor_enabled": bool(user.totp_enabled),
        "recovery_email": None, "recovery_email_not_tracked": True,
        "signup_source": (user.auth_provider or "email"),
    }

    # ── Subscription & revenue ─────────────────────────────────────────────────
    payments = PaymentHistory.query.filter_by(user_id=user_id)\
        .order_by(PaymentHistory.created_at.desc()).limit(25).all()
    user_data["recent_payments"] = [p.to_dict() for p in payments]
    revenue_cents = db.session.query(
        db.func.coalesce(db.func.sum(PaymentHistory.amount_usd), 0)
    ).filter(PaymentHistory.user_id == user_id, PaymentHistory.status == "confirmed").scalar() or 0
    user_data["revenue"] = {
        "lifetime_usd": round(revenue_cents / 100, 2),
        "payment_count": PaymentHistory.query.filter_by(user_id=user_id, status="confirmed").count(),
        "trial_used": bool(user.trial_used),
        "trial_ends_at": user.trial_ends_at.isoformat() if user.trial_ends_at else None,
        "subscription_expires_at": (user.subscription_expires_at or user.subscription_expires).isoformat()
            if (user.subscription_expires_at or user.subscription_expires) else None,
    }

    # ── Referrals (referrer + referrals made) ──────────────────────────────────
    referred_row = Referral.query.filter_by(referred_user_id=user_id).first()
    referrer = None
    if referred_row:
        ru = User.query.get(referred_row.referrer_user_id)
        referrer = {
            "user_id": referred_row.referrer_user_id,
            "email": ru.email if ru else None,
            "name": ru.full_name if ru else None,
            "status": referred_row.status,
            "created_at": referred_row.created_at.isoformat(),
        }
    made = Referral.query.filter_by(referrer_user_id=user_id)\
        .order_by(Referral.created_at.desc()).limit(50).all()
    referrals_made = []
    for r in made:
        invitee = User.query.get(r.referred_user_id)
        referrals_made.append({
            "referred_user_id": r.referred_user_id,
            "email": invitee.email if invitee else None,
            "status": r.status,
            "ip_match": r.ip_match, "device_match": r.device_match,
            "rewards_given": r.rewards_given,
            "created_at": r.created_at.isoformat(),
        })
    user_data["referrer"] = referrer
    user_data["referrals_made"] = referrals_made
    user_data["referral_stats"] = {
        "total": len(referrals_made),
        "approved": sum(1 for r in referrals_made if r["status"] == "approved"),
        "pending": sum(1 for r in referrals_made if r["status"] == "pending"),
    }

    # ── Groups: owned (linked by this user) + where they're a TG admin ─────────
    owned_groups = TelegramGroup.query.filter_by(owner_user_id=user_id)\
        .order_by(TelegramGroup.created_at.desc()).all()
    user_data["owned_groups"] = [{
        "telegram_group_id": g.telegram_group_id, "title": g.title,
        "bot_status": g.bot_status, "member_count": g.member_count,
        "linked_via_bot_type": g.linked_via_bot_type,
        "linked_at": g.linked_at.isoformat() if g.linked_at else None,
    } for g in owned_groups]
    admin_of = []
    if user.telegram_user_id:
        admin_rows = OfficialMember.query.filter_by(
            telegram_user_id=str(user.telegram_user_id), is_admin=True
        ).limit(50).all()
        for m in admin_rows:
            tg = TelegramGroup.query.filter_by(telegram_group_id=m.telegram_group_id).first()
            admin_of.append({
                "telegram_group_id": m.telegram_group_id,
                "title": tg.title if tg else m.telegram_group_id,
                "role": m.role,
            })
    user_data["admin_of_groups"] = admin_of

    # ── Bots (custom + legacy) ─────────────────────────────────────────────────
    custom_bots = CustomBot.query.filter_by(owner_user_id=user_id).all()
    user_data["custom_bots"] = [{
        "id": b.id, "bot_username": b.bot_username, "bot_name": b.bot_name,
        "status": getattr(b, "status", None),
        "created_at": b.created_at.isoformat() if b.created_at else None,
    } for b in custom_bots]
    user_data["bots"] = [b.to_dict() for b in user.bots]  # legacy table

    # ── Official-bot usage (derived from OfficialMember rows for this TG id) ────
    if user.telegram_user_id:
        member_rows = OfficialMember.query.filter_by(telegram_user_id=str(user.telegram_user_id)).all()
        user_data["official_bot_usage"] = {
            "groups_active_in": len(member_rows),
            "total_messages": sum(m.message_count or 0 for m in member_rows),
            "total_xp": sum(m.xp or 0 for m in member_rows),
            "warnings": sum(m.warnings or 0 for m in member_rows),
            "last_message_at": max(
                (m.last_message_at for m in member_rows if m.last_message_at), default=None
            ).isoformat() if any(m.last_message_at for m in member_rows) else None,
        }
    else:
        user_data["official_bot_usage"] = None  # no linked Telegram identity

    # AI / Echo usage is group-scoped (AIActivity has no user FK), so it can't be
    # reliably attributed to one website user yet.
    user_data["echo_usage_not_tracked"] = True
    user_data["ai_cost_usd_today"] = float(user.ai_cost_usd_today or 0)

    # ── Risk score (derived, 0–100) ────────────────────────────────────────────
    suspicious = SuspiciousActivity.query.filter_by(user_id=user_id)\
        .order_by(SuspiciousActivity.created_at.desc()).limit(20).all()
    risk = 0
    risk += 25 if user.is_suspicious else 0
    risk += min(20, (user.chargeback_count or 0) * 10)
    risk += min(20, len(suspicious) * 5)
    risk += sum(8 for r in referrals_made if r["ip_match"] or r["device_match"])
    risk += 15 if user.is_banned else 0
    risk = min(100, risk)
    user_data["risk"] = {
        "score": risk,
        "level": "high" if risk >= 60 else "medium" if risk >= 25 else "low",
        "is_suspicious": bool(user.is_suspicious),
        "chargeback_count": user.chargeback_count or 0,
        "suspicious_event_count": len(suspicious),
    }
    user_data["suspicious_events"] = [s.to_dict() for s in suspicious[:5]]

    # ── Admin actions taken against this user ──────────────────────────────────
    # Match the exact /users/<id> path segment (not a LIKE prefix, so user 12
    # never matches /users/123) plus any structured target reference.
    admin_actions = AdminAuditLog.query.filter(
        db.or_(
            db.and_(AdminAuditLog.target_type == "user", AdminAuditLog.target_id == str(user_id)),
            AdminAuditLog.path.like(f"%/users/{user_id}"),
            AdminAuditLog.path.like(f"%/users/{user_id}/%"),
        )
    ).order_by(AdminAuditLog.created_at.desc()).limit(25).all()
    user_data["admin_actions"] = [a.to_dict() for a in admin_actions]
    user_data["admin_notes"] = user.admin_notes or ""
    user_data["ban_reason"] = user.ban_reason

    # ── Activity timeline (merged, newest first) ───────────────────────────────
    timeline = [{"type": "signup", "at": user.created_at.isoformat(), "label": "Account created"}]
    if user.telegram_connected_at:
        timeline.append({"type": "telegram_linked", "at": user.telegram_connected_at.isoformat(),
                         "label": f"Linked Telegram @{user.telegram_username or user.telegram_user_id}"})
    for p in payments[:10]:
        timeline.append({"type": "payment", "at": p.created_at.isoformat(),
                         "label": f"{p.status} payment · {p.plan} · {p.provider}"})
    for r in made[:10]:
        timeline.append({"type": "referral", "at": r.created_at.isoformat(),
                         "label": f"Referred a user ({r.status})"})
    for s in suspicious[:10]:
        timeline.append({"type": "suspicious", "at": s.created_at.isoformat(),
                         "label": f"Suspicious: {s.reason}"})
    for a in admin_actions[:10]:
        timeline.append({"type": "admin_action", "at": a.created_at.isoformat(),
                         "label": f"Admin: {a.action}"})
    timeline.sort(key=lambda x: x["at"], reverse=True)
    user_data["timeline"] = timeline[:40]

    # ── AI/Token usage (from the ledger, attributed to this user) ──────────────
    try:
        from ..models import AITokenUsage
        from sqlalchemy import func
        row = db.session.query(
            func.coalesce(func.sum(AITokenUsage.input_tokens), 0),
            func.coalesce(func.sum(AITokenUsage.output_tokens), 0),
            func.coalesce(func.sum(AITokenUsage.total_tokens), 0),
            func.coalesce(func.sum(AITokenUsage.cost_usd), 0),
            func.count(AITokenUsage.id),
        ).filter(AITokenUsage.user_ref == str(user.id)).one()
        user_data["ai_usage"] = {
            "input_tokens": int(row[0] or 0), "output_tokens": int(row[1] or 0),
            "total_tokens": int(row[2] or 0), "cost_usd": round(float(row[3] or 0), 4),
            "calls": int(row[4] or 0),
        }
    except Exception:
        user_data["ai_usage"] = None

    return jsonify({"user": user_data})


@admin_bp.route("/users/<int:user_id>/subscription", methods=["PUT"])
@require_permission(rbac.P_USERS_MANAGE)
@rate_limit(requests_per_minute=30)
def update_subscription(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    data = request.get_json()
    tier = data.get("tier")
    if tier not in ("free", "pro", "enterprise"):
        return jsonify({"error": "Invalid tier"}), 400
    user.subscription_tier = tier
    if tier == "free":
        user.subscription_expires = None
    else:
        expires_str = data.get("expires")
        if expires_str:
            try:
                user.subscription_expires = datetime.fromisoformat(expires_str.replace("Z", "+00:00"))
            except ValueError:
                return jsonify({"error": "Invalid expires format"}), 400
    db.session.commit()
    return jsonify({"user": user.to_dict(), "message": "Subscription updated"})


@admin_bp.route("/users/<int:user_id>/notes", methods=["PUT"])
@require_permission(rbac.P_USERS_MANAGE)
@rate_limit(requests_per_minute=30)
def update_user_notes(user_id):
    """Save platform-admin free-text notes for a user (user detail page)."""
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    data = request.get_json() or {}
    notes = data.get("notes", "")
    if notes is not None and len(notes) > 10000:
        return jsonify({"error": "Notes too long (max 10000 chars)"}), 400
    user.admin_notes = notes or None
    db.session.commit()
    return jsonify({"message": "Notes saved", "admin_notes": user.admin_notes or ""})


@admin_bp.route("/users/<int:user_id>/ban", methods=["POST"])
@require_permission(rbac.P_USERS_MANAGE)
@rate_limit(requests_per_minute=30)
def ban_user(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    if rbac.is_admin(user):
        return jsonify({"error": "Cannot ban an admin"}), 403
    data = request.get_json() or {}
    user.is_banned = True
    user.ban_reason = data.get("reason", "Violation of terms of service")
    db.session.commit()
    return jsonify({"message": "User banned", "user": user.to_dict()})


@admin_bp.route("/users/<int:user_id>/unban", methods=["POST"])
@require_permission(rbac.P_USERS_MANAGE)
@rate_limit(requests_per_minute=30)
def unban_user(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    user.is_banned = False
    user.ban_reason = None
    db.session.commit()
    return jsonify({"message": "User unbanned", "user": user.to_dict()})


@admin_bp.route("/users/<int:user_id>", methods=["DELETE"])
@require_permission(rbac.P_USERS_DELETE)
@rate_limit(requests_per_minute=10)
def delete_user(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    if rbac.is_admin(user):
        return jsonify({"error": "Cannot delete an admin"}), 403
    db.session.delete(user)
    db.session.commit()
    return jsonify({"message": "User deleted"})


# ── Platform Stats ─────────────────────────────────────────────────────────────

@admin_bp.route("/stats", methods=["GET"])
@require_permission(rbac.P_ANALYTICS_VIEW)
@rate_limit(requests_per_minute=30)
def get_stats():
    total_users = User.query.count()
    total_bots = Bot.query.count()
    total_groups = Group.query.count()
    # Total Members = real Telegram membership summed across active linked groups
    # (reconciled by the member-count sync job), NOT the count of tracked-member
    # rows the bot happened to witness. Matches the "members protected" proof metric.
    total_members = db.session.query(
        db.func.coalesce(db.func.sum(TelegramGroup.member_count), 0)
    ).filter(
        TelegramGroup.bot_status == "active",
        TelegramGroup.is_disabled == False,  # noqa: E712
    ).scalar() or 0
    member_count_synced_at = db.session.query(
        db.func.min(TelegramGroup.member_count_synced_at)
    ).filter(
        TelegramGroup.bot_status == "active",
        TelegramGroup.is_disabled == False,  # noqa: E712
        TelegramGroup.member_count_synced_at.isnot(None),
    ).scalar()
    tracked_member_rows = Member.query.count()
    active_bots = Bot.query.filter_by(is_active=True).count()
    free_users = User.query.filter_by(subscription_tier="free").count()
    pro_users = User.query.filter_by(subscription_tier="pro").count()
    enterprise_users = User.query.filter_by(subscription_tier="enterprise").count()
    banned_users = User.query.filter_by(is_banned=True).count()
    verified_users = User.query.filter_by(email_verified=True).count()

    # New signups in last 7 and 30 days
    now = datetime.utcnow()
    new_7d = User.query.filter(User.created_at >= now - timedelta(days=7)).count()
    new_30d = User.query.filter(User.created_at >= now - timedelta(days=30)).count()

    return jsonify({
        "stats": {
            "total_users": total_users,
            "free_users": free_users,
            "pro_users": pro_users,
            "enterprise_users": enterprise_users,
            "banned_users": banned_users,
            "verified_users": verified_users,
            "new_users_7d": new_7d,
            "new_users_30d": new_30d,
            "total_bots": total_bots,
            "active_bots": active_bots,
            "total_groups": total_groups,
            "total_members": int(total_members),
            "total_members_synced_at": member_count_synced_at.isoformat() if member_count_synced_at else None,
            "tracked_member_rows": tracked_member_rows,
        }
    })


def _compute_mrr(now):
    """REAL paid-subscription MRR. Returns (mrr_cents:int, contributors:list).

    Source of truth is PaymentHistory (one row per real payment webhook). We
    take each user's most recent confirmed, non-zero payment and, if it is still
    inside its billing window, count its monthly-normalized value. This
    intentionally IGNORES subscription_tier, so free, trial, promo ($0), and
    admin / manual grants (which never create a paid PaymentHistory row), plus
    expired/lapsed plans, can never inflate MRR. No paid rows → MRR = $0.
    """
    monthly_window = timedelta(days=35)
    annual_window = timedelta(days=370)
    paid_rows = (
        PaymentHistory.query
        .filter(
            PaymentHistory.status == "confirmed",
            PaymentHistory.amount_usd.isnot(None),
            PaymentHistory.amount_usd > 0,
        )
        .order_by(PaymentHistory.user_id.asc(), PaymentHistory.created_at.desc())
        .all()
    )
    latest_paid_by_user: dict = {}
    for p in paid_rows:
        if p.user_id not in latest_paid_by_user:
            latest_paid_by_user[p.user_id] = p  # first seen = most recent (created_at desc)

    mrr_cents = 0.0
    contributors: list = []
    for uid, p in latest_paid_by_user.items():
        period = (p.billing_period or "monthly").lower()
        is_annual = period in ("annual", "yearly", "year")
        window = annual_window if is_annual else monthly_window
        if (now - p.created_at) > window:
            continue  # last payment older than its billing window → lapsed
        monthly_value = (p.amount_usd / 12.0) if is_annual else float(p.amount_usd)
        mrr_cents += monthly_value
        u = User.query.get(uid)
        contributors.append({
            "user_id": uid,
            "email": (u.email if u else None),
            "tier": (u.subscription_tier if u else None),
            "plan": p.plan,
            "provider": p.provider,
            "billing_period": period,
            "amount_usd": round((p.amount_usd or 0) / 100, 2),
            "monthly_value_usd": round(monthly_value / 100, 2),
            "last_payment_at": p.created_at.isoformat(),
        })
    return round(mrr_cents), contributors


@admin_bp.route("/revenue", methods=["GET"])
@require_permission(rbac.P_ANALYTICS_VIEW)
@rate_limit(requests_per_minute=30)
def get_revenue():
    """MRR, ARR, new revenue this month, and all-time totals from PaymentHistory."""
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # All-time confirmed revenue (amount_usd is in cents)
    all_payments = PaymentHistory.query.filter_by(status="confirmed").all()
    total_revenue_cents = sum(p.amount_usd or 0 for p in all_payments)

    # Revenue this month
    month_payments = PaymentHistory.query.filter(
        PaymentHistory.status == "confirmed",
        PaymentHistory.created_at >= month_start,
    ).all()
    month_revenue_cents = sum(p.amount_usd or 0 for p in month_payments)

    # Revenue last month
    last_month_start = (month_start - timedelta(days=1)).replace(day=1)
    last_month_payments = PaymentHistory.query.filter(
        PaymentHistory.status == "confirmed",
        PaymentHistory.created_at >= last_month_start,
        PaymentHistory.created_at < month_start,
    ).all()
    last_month_revenue_cents = sum(p.amount_usd or 0 for p in last_month_payments)

    # MRR / ARR — REAL paid subscriptions only. See _compute_mrr() for the rules.
    mrr_cents, revenue_contributors = _compute_mrr(now)
    arr_cents = mrr_cents * 12

    # Tier head-counts — informational only, NOT used for revenue.
    pro_count = User.query.filter_by(subscription_tier="pro").count()
    enterprise_count = User.query.filter_by(subscription_tier="enterprise").count()

    # Payment method breakdown
    nowpayments_count = PaymentHistory.query.filter_by(provider="nowpayments", status="confirmed").count()
    lemonsqueezy_count = PaymentHistory.query.filter_by(provider="lemonsqueezy", status="confirmed").count()

    # Monthly revenue trend (last 6 months)
    trend = []
    for i in range(5, -1, -1):
        m_start = (now.replace(day=1) - timedelta(days=i * 30)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        m_end_raw = m_start.replace(month=m_start.month % 12 + 1) if m_start.month < 12 else m_start.replace(year=m_start.year + 1, month=1)
        m_rev = db.session.query(db.func.sum(PaymentHistory.amount_usd)).filter(
            PaymentHistory.status == "confirmed",
            PaymentHistory.created_at >= m_start,
            PaymentHistory.created_at < m_end_raw,
        ).scalar() or 0
        trend.append({
            "month": m_start.strftime("%b %Y"),
            "revenue": round(m_rev / 100, 2),
        })

    # Churn: users whose paid subscription expired in the last 30 / 60 days and are now on free tier
    thirty_days_ago = now - timedelta(days=30)
    sixty_days_ago = now - timedelta(days=60)
    churned_30d = User.query.filter(
        User.subscription_expires_at.isnot(None),
        User.subscription_expires_at.between(thirty_days_ago, now),
        User.subscription_tier == "free",
    ).count()
    churned_60d = User.query.filter(
        User.subscription_expires_at.isnot(None),
        User.subscription_expires_at.between(sixty_days_ago, now),
        User.subscription_tier == "free",
    ).count()
    churn_30d_prev = churned_60d - churned_30d  # churned in 30-60d window

    # Cohort funnel: user counts by tier, grouped by registration month (last 6 months)
    six_months_ago = now - timedelta(days=180)
    cohort_rows = db.session.execute(db.text(
        "SELECT DATE_TRUNC('month', created_at) AS month, subscription_tier, COUNT(*) AS cnt "
        "FROM users "
        "WHERE created_at >= :since "
        "GROUP BY 1, 2 "
        "ORDER BY 1"
    ), {"since": six_months_ago}).fetchall()

    cohort_map: dict = {}
    for row in cohort_rows:
        m_key = row[0].strftime("%b %Y") if row[0] else "?"
        tier = row[1] or "free"
        cnt = int(row[2])
        if m_key not in cohort_map:
            cohort_map[m_key] = {"month": m_key, "free": 0, "pro": 0, "enterprise": 0}
        if tier in cohort_map[m_key]:
            cohort_map[m_key][tier] += cnt
    cohort = list(cohort_map.values())

    return jsonify({
        "revenue": {
            "mrr": round(mrr_cents / 100, 2),
            "arr": round(arr_cents / 100, 2),
            "total_all_time": round(total_revenue_cents / 100, 2),
            "this_month": round(month_revenue_cents / 100, 2),
            "last_month": round(last_month_revenue_cents / 100, 2),
            "pro_subscribers": pro_count,
            "enterprise_subscribers": enterprise_count,
            "paying_subscribers": len(revenue_contributors),
            "nowpayments_count": nowpayments_count,
            "lemonsqueezy_count": lemonsqueezy_count,
            "monthly_trend": trend,
            "churned_30d": churned_30d,
            "churned_30d_prev": churn_30d_prev,
            "cohort": cohort,
            # Exact rows that make up MRR — auditable in the admin panel.
            "contributing_subscriptions": revenue_contributors,
        }
    })


@admin_bp.route("/health", methods=["GET"])
@require_permission(rbac.P_HEALTH_VIEW)
@rate_limit(requests_per_minute=30)
def platform_health():
    """Check DB, Redis, and Celery health for the admin dashboard."""
    checks = {}

    # Database
    try:
        db.session.execute(db.text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {str(e)[:80]}"

    # Redis
    try:
        from flask import current_app
        redis_client = getattr(current_app, "_redis_client", None)
        if redis_client is None:
            try:
                import redis as _redis
                r = _redis.from_url(Config.REDIS_URL or "redis://localhost:6379/0", socket_timeout=2)
                r.ping()
                checks["redis"] = "ok"
            except Exception as re:
                checks["redis"] = f"error: {str(re)[:80]}"
        else:
            redis_client.ping()
            checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {str(e)[:80]}"

    # Celery — check for a recent heartbeat key in Redis
    try:
        import redis as _redis
        r = _redis.from_url(Config.REDIS_URL or "redis://localhost:6379/0", socket_timeout=2)
        # Celery workers write a heartbeat key; fall back to "unknown" gracefully
        heartbeat = r.get("celery:heartbeat")
        checks["celery"] = "ok" if heartbeat else "unknown"
    except Exception:
        checks["celery"] = "unknown"

    overall = "ok" if all(v == "ok" or v == "unknown" for v in checks.values()) else "degraded"

    # Recent error count from DB (last hour)
    try:
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        recent_admin_actions = AdminAuditLog.query.filter(
            AdminAuditLog.created_at >= one_hour_ago
        ).count()
        checks["admin_actions_last_hour"] = recent_admin_actions
    except Exception:
        checks["admin_actions_last_hour"] = 0

    return jsonify({
        "status": overall,
        "checks": checks,
        "timestamp": datetime.utcnow().isoformat(),
    })


@admin_bp.route("/my-plan", methods=["PUT"])
@admin_required
@rate_limit(requests_per_minute=30)
def set_own_plan():
    user = _get_current_user()
    data = request.get_json()
    tier = data.get("tier")
    if tier not in ("free", "pro", "enterprise"):
        return jsonify({"error": "Invalid tier. Must be free, pro, or enterprise"}), 400
    user.subscription_tier = tier
    user.subscription_expires = None
    db.session.commit()
    return jsonify({"user": user.to_dict(), "message": f"Plan switched to {tier}"}), 200


# ── Suspicious Activity ────────────────────────────────────────────────────────

@admin_bp.route("/suspicious", methods=["GET"])
@require_permission(rbac.P_FRAUD_VIEW)
@rate_limit(requests_per_minute=30)
def list_suspicious():
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 100)
    event_type = request.args.get("event_type", "")
    reviewed = request.args.get("reviewed", "")

    query = SuspiciousActivity.query.order_by(SuspiciousActivity.created_at.desc())
    if event_type:
        query = query.filter(SuspiciousActivity.event_type == event_type)
    if reviewed == "true":
        query = query.filter(SuspiciousActivity.reviewed == True)
    elif reviewed == "false":
        query = query.filter(SuspiciousActivity.reviewed == False)

    paginated = query.paginate(page=page, per_page=per_page, error_out=False)

    items = []
    for evt in paginated.items:
        d = evt.to_dict()
        if evt.user_id:
            u = User.query.get(evt.user_id)
            d["user_email"] = u.email if u else None
        else:
            d["user_email"] = None
        items.append(d)

    return jsonify({
        "events": items,
        "total": paginated.total,
        "pages": paginated.pages,
        "page": page,
    })


@admin_bp.route("/suspicious/<int:event_id>/dismiss", methods=["POST"])
@require_permission(rbac.P_MODERATION_MANAGE)
@rate_limit(requests_per_minute=30)
def dismiss_suspicious(event_id):
    event = SuspiciousActivity.query.get(event_id)
    if not event:
        return jsonify({"error": "Event not found"}), 404
    event.reviewed = True
    db.session.commit()
    return jsonify({"message": "Event dismissed", "event": event.to_dict()})


# ── Referrals ──────────────────────────────────────────────────────────────────

@admin_bp.route("/referrals", methods=["GET"])
@require_permission(rbac.P_REFERRALS_MANAGE)
@rate_limit(requests_per_minute=30)
def list_referrals():
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 100)
    status = request.args.get("status", "")

    query = Referral.query.order_by(Referral.created_at.desc())
    if status:
        query = query.filter(Referral.status == status)

    paginated = query.paginate(page=page, per_page=per_page, error_out=False)

    items = []
    for ref in paginated.items:
        d = ref.to_dict()
        referrer = User.query.get(ref.referrer_user_id)
        referred = User.query.get(ref.referred_user_id)
        d["referrer_email"] = referrer.email if referrer else None
        d["referred_email"] = referred.email if referred else None
        d["referred_email_verified"] = referred.email_verified if referred else None
        items.append(d)

    return jsonify({
        "referrals": items,
        "total": paginated.total,
        "pages": paginated.pages,
        "page": page,
    })


@admin_bp.route("/referrals/<int:referral_id>/status", methods=["POST"])
@require_permission(rbac.P_REFERRALS_MANAGE)
@rate_limit(requests_per_minute=30)
def update_referral_status(referral_id):
    referral = Referral.query.get(referral_id)
    if not referral:
        return jsonify({"error": "Referral not found"}), 404

    data = request.get_json() or {}
    new_status = data.get("status", "")
    if new_status not in ("approved", "rejected", "suspicious", "pending"):
        return jsonify({"error": "status must be one of: approved, rejected, suspicious, pending"}), 400

    old_status = referral.status
    referral.status = new_status
    db.session.commit()

    if new_status == "approved" and old_status != "approved":
        try:
            from flask import current_app
            from ..routes.referrals import _apply_referral_rewards
            _app = current_app._get_current_object()
            _referrer_id = referral.referrer_user_id

            import threading

            def _reward():
                try:
                    with _app.app_context():
                        r = User.query.get(_referrer_id)
                        if r:
                            _apply_referral_rewards(r)
                except Exception:
                    pass

            threading.Thread(target=_reward, daemon=True).start()
        except Exception:
            pass

    return jsonify({"message": f"Referral status updated to {new_status}", "referral": referral.to_dict()})


# ── Bots ───────────────────────────────────────────────────────────────────────

@admin_bp.route("/bots", methods=["GET"])
@require_permission(rbac.P_BOTS_VIEW)
@rate_limit(requests_per_minute=30)
def list_all_bots():
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 100)
    query = Bot.query.order_by(Bot.created_at.desc())
    paginated = query.paginate(page=page, per_page=per_page, error_out=False)
    bots_data = []
    for bot in paginated.items:
        bd = bot.to_dict()
        bd["owner_email"] = bot.owner.email if bot.owner else None
        bots_data.append(bd)
    return jsonify({
        "bots": bots_data,
        "total": paginated.total,
        "pages": paginated.pages,
        "page": page,
        "per_page": per_page,
    })


# ── Official Bot Ecosystem ─────────────────────────────────────────────────────

@admin_bp.route("/telegram-groups", methods=["GET"])
@require_permission(rbac.P_GROUPS_VIEW)
@rate_limit(requests_per_minute=30)
def admin_list_telegram_groups():
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 200)
    search = request.args.get("search", "")
    status = request.args.get("status", "")
    bot_type = request.args.get("bot_type", "")        # official | custom
    visibility = request.args.get("visibility", "")    # public | private
    min_members = request.args.get("min_members", type=int)
    recent = request.args.get("recent", "")            # "1" → added in last 7 days
    health = request.args.get("health", "")            # disabled | warning

    query = TelegramGroup.query
    if search:
        query = query.filter(
            TelegramGroup.title.ilike(f"%{search}%") |
            TelegramGroup.telegram_group_id.ilike(f"%{search}%") |
            TelegramGroup.username.ilike(f"%{search}%")
        )
    if status == "inactive":
        # No recent activity (or never active) — a useful operational filter.
        cutoff = datetime.utcnow() - timedelta(days=14)
        query = query.filter(
            db.or_(TelegramGroup.last_activity.is_(None), TelegramGroup.last_activity < cutoff)
        )
    elif status:
        query = query.filter(TelegramGroup.bot_status == status)
    if bot_type in ("official", "custom"):
        query = query.filter(TelegramGroup.linked_via_bot_type == bot_type)
    if visibility == "public":
        query = query.filter(TelegramGroup.username.isnot(None))
    elif visibility == "private":
        query = query.filter(TelegramGroup.username.is_(None))
    if min_members:
        query = query.filter(TelegramGroup.member_count >= min_members)
    if recent == "1":
        query = query.filter(TelegramGroup.created_at >= datetime.utcnow() - timedelta(days=7))
    if health == "disabled":
        query = query.filter(TelegramGroup.is_disabled == True)  # noqa: E712
    elif health == "warning":
        query = query.filter(TelegramGroup.bot_status.in_(("removed", "disabled")))

    query = query.order_by(TelegramGroup.created_at.desc())
    paginated = query.paginate(page=page, per_page=per_page, error_out=False)

    owner_ids = {tg.owner_user_id for tg in paginated.items if tg.owner_user_id}
    owners_by_id = {}
    if owner_ids:
        for u in User.query.filter(User.id.in_(owner_ids)).all():
            owners_by_id[u.id] = u

    result = []
    for tg in paginated.items:
        d = tg.to_dict()
        owner = owners_by_id.get(tg.owner_user_id) if tg.owner_user_id else None
        d["owner_email"] = owner.email if owner else None
        d["owner_name"] = owner.full_name if owner else None
        d["command_count"] = len(tg.custom_commands)
        result.append(d)

    return jsonify({
        "groups": result,
        "total": paginated.total,
        "pages": paginated.pages,
        "page": page,
    })


@admin_bp.route("/telegram-groups/stats", methods=["GET"])
@require_permission(rbac.P_GROUPS_VIEW)
@rate_limit(requests_per_minute=30)
def admin_telegram_group_stats():
    total = TelegramGroup.query.count()
    active = TelegramGroup.query.filter_by(bot_status="active").count()
    pending = TelegramGroup.query.filter_by(bot_status="pending").count()
    removed = TelegramGroup.query.filter_by(bot_status="removed").count()
    disabled = TelegramGroup.query.filter_by(is_disabled=True).count()
    # Count bots across BOTH tables (legacy `bots` + new `custom_bots`),
    # deduped by username, so this matches the unified admin bot list.
    from ..models import Bot
    _custom_usernames = {
        u for (u,) in db.session.query(CustomBot.bot_username).all() if u
    }
    _legacy_usernames = {
        u for (u,) in db.session.query(Bot.bot_username).all() if u
    }
    custom_bots_count = CustomBot.query.count()
    legacy_only = len(_legacy_usernames - _custom_usernames)
    total_custom_bots = custom_bots_count + legacy_only
    total_users_with_groups = db.session.query(
        TelegramGroup.owner_user_id
    ).filter(
        TelegramGroup.owner_user_id.isnot(None)
    ).distinct().count()

    return jsonify({
        "stats": {
            "total_linked_groups": total,
            "active_groups": active,
            "pending_groups": pending,
            "removed_groups": removed,
            "disabled_groups": disabled,
            "total_custom_bots": total_custom_bots,
            "users_using_bot": total_users_with_groups,
        }
    })


@admin_bp.route("/telegram-groups/<group_id>/disable", methods=["POST"])
@require_permission(rbac.P_GROUPS_MANAGE)
@rate_limit(requests_per_minute=10)
def admin_disable_group(group_id):
    tg = TelegramGroup.query.filter_by(telegram_group_id=group_id).first()
    if not tg:
        return jsonify({"error": "Group not found"}), 404
    tg.is_disabled = True
    tg.bot_status = "disabled"
    db.session.commit()
    return jsonify({"message": "Group disabled", "group": tg.to_dict()})


@admin_bp.route("/telegram-groups/<group_id>/unlink", methods=["POST"])
@require_permission(rbac.P_GROUPS_MANAGE)
@rate_limit(requests_per_minute=10)
def admin_unlink_group(group_id):
    tg = TelegramGroup.query.filter_by(telegram_group_id=group_id).first()
    if not tg:
        return jsonify({"error": "Group not found"}), 404
    tg.owner_user_id = None
    tg.bot_status = "pending"
    tg.linked_at = None
    db.session.commit()

    ev = BotEvent(
        telegram_group_id=tg.telegram_group_id,
        event_type="admin_unlinked",
        message="Admin force-unlinked group",
    )
    db.session.add(ev)
    db.session.commit()

    return jsonify({"message": "Group unlinked by admin", "group": tg.to_dict()})


@admin_bp.route("/telegram-groups/<group_id>/reconcile", methods=["POST"])
@require_permission(rbac.P_GROUPS_MANAGE)
@rate_limit(requests_per_minute=20)
def admin_reconcile_group(group_id):
    """P5: manually run the pending→active promotion check on one group.

    Promotes it if eligible (owner + recent activity + bot present); otherwise
    returns the concrete reason it stays pending. Same logic as the hourly job.
    """
    from ..group_status import evaluate_pending, _has_recent_activity, reconcile_group
    tg = TelegramGroup.query.filter_by(telegram_group_id=group_id).first()
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    if tg.bot_status != "pending":
        return jsonify({
            "promoted": False,
            "reason": f"Group is already '{tg.bot_status}', nothing to do.",
            "group": tg.to_dict(),
        })

    reason = reconcile_group(tg)
    if reason:
        db.session.add(BotEvent(
            telegram_group_id=tg.telegram_group_id,
            event_type="group_auto_activated",
            message=f"Admin reconcile promoted pending→active: {reason}",
        ))
        db.session.commit()
        return jsonify({"promoted": True, "reason": reason, "group": tg.to_dict()})

    # Not eligible — return the why.
    _, why = evaluate_pending(tg, _has_recent_activity(tg))
    return jsonify({"promoted": False, "reason": why, "group": tg.to_dict()})


@admin_bp.route("/telegram-groups/sync-members", methods=["POST"])
@require_permission(rbac.P_GROUPS_MANAGE)
@rate_limit(requests_per_minute=4)
def admin_sync_member_counts():
    """Reconcile member_count for all active groups against live Telegram counts.

    Read-only Telegram calls (getChatMemberCount), throttled per the anti-ban
    rule. Runs synchronously so the admin sees the result; capped to keep the
    request bounded.
    """
    from ..member_sync import sync_member_counts
    data = request.get_json(silent=True) or {}
    limit = data.get("limit")
    summary = sync_member_counts(limit=limit)
    return jsonify(summary)


@admin_bp.route("/telegram-groups/<group_id>/sync-members", methods=["POST"])
@require_permission(rbac.P_GROUPS_MANAGE)
@rate_limit(requests_per_minute=20)
def admin_sync_group_members(group_id):
    """Reconcile a single group's member_count against the live Telegram count."""
    from ..member_sync import sync_member_counts
    tg = TelegramGroup.query.filter_by(telegram_group_id=group_id).first()
    if not tg:
        return jsonify({"error": "Group not found"}), 404
    summary = sync_member_counts(group_ids=[group_id])
    tg = TelegramGroup.query.filter_by(telegram_group_id=group_id).first()
    return jsonify({**summary, "group": tg.to_dict() if tg else None})


@admin_bp.route("/telegram-groups/<group_id>/events", methods=["GET"])
@require_permission(rbac.P_GROUPS_VIEW)
@rate_limit(requests_per_minute=30)
def admin_group_events(group_id):
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 200)
    paginated = BotEvent.query.filter_by(
        telegram_group_id=group_id
    ).order_by(BotEvent.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return jsonify({
        "events": [e.to_dict() for e in paginated.items],
        "total": paginated.total,
        "pages": paginated.pages,
        "page": page,
    })


@admin_bp.route("/telegram-groups/<group_id>/detail", methods=["GET"])
@require_permission(rbac.P_GROUPS_VIEW)
@rate_limit(requests_per_minute=60)
def admin_group_detail(group_id):
    """Comprehensive audit profile for one linked group.

    Aggregates ownership, bot/permissions, moderation throughput (from the
    FeatureUsageEvent spine + OfficialWarning), AI activity, member admin/mute
    counts, health/errors and a proof-metrics subset. Everything is real DB
    data; anything not tracked is omitted or flagged rather than faked.
    """
    from ..models import (
        OfficialWarning, OfficialMember, AIActivity, FeatureUsageEvent, BotHealthEvent,
    )
    tg = TelegramGroup.query.filter_by(telegram_group_id=group_id).first()
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    data = tg.to_dict()

    # ── Ownership / who-connected / managed-by ─────────────────────────────────
    owner = User.query.get(tg.owner_user_id) if tg.owner_user_id else None
    managed_by = "Official Telegizer bot"
    managed_bot_username = None
    if tg.linked_via_bot_type == "custom" and tg.linked_bot_id:
        cb = CustomBot.query.get(tg.linked_bot_id)
        if cb:
            managed_by = f"Custom bot @{cb.bot_username}"
            managed_bot_username = cb.bot_username
    data["ownership"] = {
        # Group Owner = the Telegizer account that linked/registered the group.
        "owner_user_id": tg.owner_user_id,
        "owner_email": owner.email if owner else None,
        "owner_name": owner.full_name if owner else None,
        # Connected By = best available is the same linking account.
        "connected_by": owner.email if owner else None,
        "managed_by_bot": managed_by,
        "managed_bot_username": managed_bot_username,
        "linked_via_bot_type": tg.linked_via_bot_type,
        # Telegram-side owner/admin is not synced from the API yet.
        "telegram_owner_not_synced": True,
    }
    data["visibility"] = "public" if tg.username else "private"

    # ── Members & admins ───────────────────────────────────────────────────────
    member_q = OfficialMember.query.filter_by(telegram_group_id=group_id)
    data["members"] = {
        "member_count": tg.member_count,
        "member_count_synced_at": tg.member_count_synced_at.isoformat() if tg.member_count_synced_at else None,
        "tracked_members": member_q.count(),
        "admin_count": member_q.filter_by(is_admin=True).count(),
        "muted_count": member_q.filter_by(is_muted=True).count(),
    }

    # ── Moderation / feature throughput (FeatureUsageEvent spine) ──────────────
    usage_rows = (
        db.session.query(
            FeatureUsageEvent.feature,
            db.func.coalesce(db.func.sum(FeatureUsageEvent.count), 0),
        )
        .filter(FeatureUsageEvent.group_ref == group_id)
        .group_by(FeatureUsageEvent.feature)
        .all()
    )
    usage = {feat: int(c) for feat, c in usage_rows}
    warnings_count = OfficialWarning.query.filter_by(telegram_group_id=group_id).count()
    data["moderation"] = {
        "by_feature": usage,
        "spam_deleted": usage.get("spam", 0) + usage.get("automod", 0),
        "links_blocked": usage.get("link", 0),
        "warnings_issued": max(warnings_count, usage.get("warn", 0)),
        "muted": usage.get("mute", 0),
        "banned": usage.get("ban", 0),
        "kicked": usage.get("kick", 0),
        "commands_used": usage.get("command", 0),
        "total_actions": sum(usage.values()),
    }

    # ── AI activity ────────────────────────────────────────────────────────────
    ai_rows = (
        db.session.query(AIActivity.category, db.func.count(AIActivity.id))
        .filter(AIActivity.group_ref == group_id)
        .group_by(AIActivity.category)
        .all()
    )
    ai_by_cat = {cat: int(c) for cat, c in ai_rows}
    data["ai_usage"] = {"by_category": ai_by_cat, "total": sum(ai_by_cat.values())}

    # ── Health & recent errors (scoped to this group) ──────────────────────────
    err_q = BotHealthEvent.query.filter(BotHealthEvent.ref == group_id)
    recent_errors = err_q.order_by(BotHealthEvent.created_at.desc()).limit(10).all()
    now = datetime.utcnow()
    data["health"] = {
        "bot_status": tg.bot_status,
        "is_disabled": tg.is_disabled,
        "last_activity": tg.last_activity.isoformat() if tg.last_activity else None,
        "errors_24h": err_q.filter(BotHealthEvent.created_at >= now - timedelta(days=1)).count(),
        "errors_7d": err_q.filter(BotHealthEvent.created_at >= now - timedelta(days=7)).count(),
        "recent_errors": [e.to_dict() for e in recent_errors],
    }

    # ── Recent events timeline ─────────────────────────────────────────────────
    events = BotEvent.query.filter_by(telegram_group_id=group_id)\
        .order_by(BotEvent.created_at.desc()).limit(15).all()
    data["recent_events"] = [e.to_dict() for e in events]

    # ── Proof-metrics subset (group-level) ─────────────────────────────────────
    data["proof_metrics"] = {
        "members_protected": tg.member_count,
        "spam_deleted": data["moderation"]["spam_deleted"],
        "links_blocked": data["moderation"]["links_blocked"],
        "warnings_issued": data["moderation"]["warnings_issued"],
        "moderation_actions": data["moderation"]["total_actions"],
        "ai_checks": data["ai_usage"]["total"],
    }
    data["command_count"] = len(tg.custom_commands)

    return jsonify({"group": data})


# ── Custom Bots ────────────────────────────────────────────────────────────────

@admin_bp.route("/custom-bots", methods=["GET"])
@require_permission(rbac.P_BOTS_VIEW)
@rate_limit(requests_per_minute=30)
def admin_list_custom_bots():
    """Unified bot list — UNIONs the new `custom_bots` table and the legacy
    `bots` table so the admin count matches what users actually have.

    The dashboard's "Community Bots" widget reads the legacy `bots` table while
    MyBots reads `custom_bots`; previously this admin endpoint read only
    `custom_bots`, so a user with legacy bots showed a lower count here. Every
    row is tagged with `source` ("custom" | "legacy") so the two are clearly
    distinguishable while still reconciling to one total.
    """
    from ..models import Bot

    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 100)

    # Cache owner lookups across both tables.
    _owner_cache: dict = {}

    def _owner(uid):
        if uid not in _owner_cache:
            _owner_cache[uid] = User.query.get(uid)
        return _owner_cache[uid]

    combined = []

    # New custom bots.
    for bot in CustomBot.query.all():
        d = bot.to_dict()
        d["source"] = "custom"
        owner = _owner(bot.owner_user_id)
        d["owner_email"] = owner.email if owner else None
        d["owner_tier"] = owner.subscription_tier if owner else None
        d["_sort"] = bot.created_at
        combined.append(d)

    # Legacy bots — normalize to the same shape.
    seen_usernames = {b.get("bot_username") for b in combined if b.get("bot_username")}
    for bot in Bot.query.all():
        # Skip a legacy row if the same bot already appears as a custom bot.
        if bot.bot_username and bot.bot_username in seen_usernames:
            continue
        owner = _owner(bot.user_id)
        combined.append({
            "id": bot.id,
            "source": "legacy",
            "bot_username": bot.bot_username,
            "bot_name": bot.bot_name,
            "status": bot.get_health_status(),
            "linked_groups_count": len(bot.groups),
            "created_at": bot.created_at.isoformat() if bot.created_at else None,
            "owner_email": owner.email if owner else None,
            "owner_tier": owner.subscription_tier if owner else None,
            "_sort": bot.created_at,
        })

    # Sort newest-first and paginate in Python over the merged list.
    combined.sort(key=lambda b: b.get("_sort") or datetime.min, reverse=True)
    for b in combined:
        b.pop("_sort", None)

    total = len(combined)
    start = (page - 1) * per_page
    result = combined[start:start + per_page]
    pages = (total + per_page - 1) // per_page if per_page else 1

    return jsonify({
        "bots": result,
        "total": total,
        "pages": pages,
        "page": page,
        "counts": {
            "custom_bots": CustomBot.query.count(),
            "legacy_bots": Bot.query.count(),
            "unified_total": total,
        },
    })


# ── Diagnostics (read-only) ────────────────────────────────────────────────────

@admin_bp.route("/diagnostics", methods=["GET"])
@require_permission(rbac.P_HEALTH_VIEW)
@rate_limit(requests_per_minute=20)
def admin_diagnostics():
    """One read-only snapshot that makes the audit findings auditable in-panel.

    Performs NO mutations and NO live Telegram/AI calls — every fact is derived
    from the database so it is safe to hit repeatedly. Sections:
      • revenue   — exact rows that make up MRR (P4)
      • bots      — counts from `bots` + `custom_bots`, reconciled (P6)
      • groups    — per-group "why pending" reason from DB facts (P5)
      • ai        — AI feature availability per official / custom / Echo (P2)
      • health    — bot liveness/health facts (P1)
    """
    from ..models import Bot, MessageBuffer, UserApiKey
    now = datetime.utcnow()

    # ── Revenue (P4) — exact contributing rows ──
    mrr_cents, contributors = _compute_mrr(now)
    revenue = {
        "mrr_usd": round(mrr_cents / 100, 2),
        "arr_usd": round(mrr_cents * 12 / 100, 2),
        "paying_subscribers": len(contributors),
        "tier_headcount": {
            "pro": User.query.filter_by(subscription_tier="pro").count(),
            "enterprise": User.query.filter_by(subscription_tier="enterprise").count(),
        },
        "note": "MRR counts ONLY real PaymentHistory cash rows in-window. Tier head-counts are shown for contrast and are NOT revenue.",
        "contributing_rows": contributors,
    }

    # ── Bots (P6) — reconcile the two tables ──
    custom_total = CustomBot.query.count()
    legacy_total = Bot.query.count()
    custom_usernames = {u for (u,) in db.session.query(CustomBot.bot_username).all() if u}
    legacy_usernames = {u for (u,) in db.session.query(Bot.bot_username).all() if u}
    legacy_only = len(legacy_usernames - custom_usernames)
    bots = {
        "custom_bots_table": custom_total,
        "legacy_bots_table": legacy_total,
        "in_both_tables_same_username": len(custom_usernames & legacy_usernames),
        "unified_distinct_total": custom_total + legacy_only,
        "note": "Dashboard 'Community Bots' reads the legacy `bots` table; MyBots/admin read `custom_bots`. Unified total is the real distinct count.",
    }

    # ── Groups (P5) — DB-derived "why pending" ──
    pending_groups = (
        TelegramGroup.query.filter_by(bot_status="pending")
        .order_by(TelegramGroup.created_at.desc())
        .limit(100)
        .all()
    )
    seven_days_ago = now - timedelta(days=7)
    group_rows = []
    for g in pending_groups:
        last_msg = (
            MessageBuffer.query
            .filter_by(telegram_group_id=g.telegram_group_id)
            .order_by(MessageBuffer.created_at.desc())
            .first()
        )
        has_recent_activity = bool(last_msg and last_msg.created_at >= seven_days_ago)
        has_owner = g.owner_user_id is not None
        # Single source of truth — same logic the hourly auto-promote job uses.
        from ..group_status import evaluate_pending
        will_promote, reason = evaluate_pending(g, has_recent_activity)
        group_rows.append({
            "telegram_group_id": g.telegram_group_id,
            "title": g.title,
            "has_owner": has_owner,
            "linked_bot_id": g.linked_bot_id,
            "linked_at": g.linked_at.isoformat() if g.linked_at else None,
            "last_activity_at": last_msg.created_at.isoformat() if last_msg else None,
            "has_recent_activity_7d": has_recent_activity,
            "will_auto_promote": will_promote,
            "why_pending": reason,
        })
    groups = {
        "pending_count": TelegramGroup.query.filter_by(bot_status="pending").count(),
        "active_count": TelegramGroup.query.filter_by(bot_status="active").count(),
        "rows": group_rows,
    }

    # ── AI availability (P2) ──
    platform_key = bool(getattr(Config, "PLATFORM_OPENROUTER_API_KEY", None))
    workspace_key_owners = (
        db.session.query(UserApiKey.user_id)
        .filter_by(scope="workspace", is_active=True)
        .distinct().count()
    )
    ai = {
        "official_bot": {
            "ai_moderation_wired": False,
            "mode": "rule_based_only",
            "note": "Official bot runs inline rule-based AutoMod (bad-words + rate spam). Optional Smart AI Moderation is the planned P2 add-on; UI must not claim AI is active unless configured + enabled.",
        },
        "custom_bots": {
            "ai_moderation_wired": True,
            "total_bots": custom_total + legacy_only,
            "owners_with_workspace_ai_key": workspace_key_owners,
            "platform_ai_key_configured": platform_key,
            "note": "AI relevance fires only when smart_mod.ai_enabled + group_topic set AND an AI key resolves (workspace key or platform key). Owner lookup now covers both Bot and CustomBot (P2 fix).",
        },
        "echo": {
            "ai_wired": True,
            "platform_ai_key_configured": platform_key,
            "owners_with_workspace_ai_key": workspace_key_owners,
            "note": "Echo handlers (replies, digests, notes, tasks, memory, search) are AI-key-gated. End-to-end correctness needs a runtime with a live key.",
        },
    }

    # ── Health / liveness facts (P1) ──
    since_24h = now - timedelta(hours=24)
    legacy_health = {}
    for b in Bot.query.all():
        s = b.get_health_status()
        legacy_health[s] = legacy_health.get(s, 0) + 1
    custom_health = {}
    for (st, cnt) in (
        db.session.query(CustomBot.status, db.func.count(CustomBot.id))
        .group_by(CustomBot.status).all()
    ):
        custom_health[st or "unknown"] = cnt
    errors_by_scope = {
        scope: cnt for (scope, cnt) in (
            db.session.query(BotHealthEvent.scope, db.func.count(BotHealthEvent.id))
            .filter(
                BotHealthEvent.created_at >= since_24h,
                db.or_(BotHealthEvent.severity != "info", BotHealthEvent.severity.is_(None)),
            )
            .group_by(BotHealthEvent.scope).all()
        )
    }
    health = {
        "legacy_bots_by_status": legacy_health,
        "custom_bots_by_status": custom_health,
        "errors_24h_by_scope": errors_by_scope,
        "note": "Liveness here is derived from last_active age + recorded errors. Scheduled getMe pings + escalation come with the P1 Bot Health Center.",
    }

    return jsonify({
        "generated_at": now.isoformat(),
        "revenue": revenue,
        "bots": bots,
        "groups": groups,
        "ai": ai,
        "health": health,
    })


# ── Bot Health ─────────────────────────────────────────────────────────────────

@admin_bp.route("/bot-health", methods=["GET"])
@require_permission(rbac.P_HEALTH_VIEW)
@rate_limit(requests_per_minute=30)
def admin_bot_health():
    """Health overview: official bot + paginated custom bots with 24h error counts.

    Errors come from the bot_health_events table (populated as failures happen).
    Liveness is verified on demand via POST /bot-health/ping.
    """
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 25, type=int), 100)
    since = datetime.utcnow() - timedelta(hours=24)

    # Real failures only: deployment/restart noise (severity='info') is excluded
    # from outage counts. Legacy rows (severity NULL) still count. (Part 6/7)
    _real_failure = db.or_(BotHealthEvent.severity != "info", BotHealthEvent.severity.is_(None))

    # One grouped query → {ref: count} for all custom-bot errors in the window.
    counts_by_ref = {}
    try:
        rows = (
            db.session.query(BotHealthEvent.ref, db.func.count(BotHealthEvent.id))
            .filter(BotHealthEvent.created_at >= since, BotHealthEvent.scope == "custom", _real_failure)
            .group_by(BotHealthEvent.ref)
            .all()
        )
        counts_by_ref = {ref: cnt for ref, cnt in rows}
    except Exception as e:
        _log.warning("bot-health custom counts failed: %s", e)

    # Last error timestamp per custom bot (most recent per ref).
    last_err_by_ref = {}
    try:
        err_rows = (
            BotHealthEvent.query.filter(BotHealthEvent.scope == "custom")
            .order_by(BotHealthEvent.created_at.desc())
            .limit(500)
            .all()
        )
        for r in err_rows:
            if r.ref and r.ref not in last_err_by_ref:
                last_err_by_ref[r.ref] = r.created_at.isoformat()
    except Exception as e:
        _log.warning("bot-health last-error lookup failed: %s", e)

    # Official bot summary.
    official = {"error_count_24h": 0, "last_error": None}
    try:
        official["error_count_24h"] = BotHealthEvent.query.filter(
            BotHealthEvent.scope.in_(["official", "ai"]),
            BotHealthEvent.created_at >= since,
            _real_failure,
        ).count()
        # Only surface a "last error" that is a REAL failure inside the same 24h
        # window as the count. A stale pre-fix crash (e.g. an old forward_date
        # AttributeError) must not haunt the card once it's resolved and no new
        # failures have occurred. errors_24h == 0  ⇒  no last_error shown.
        last = (
            BotHealthEvent.query.filter(
                BotHealthEvent.scope.in_(["official", "ai"]),
                BotHealthEvent.created_at >= since,
                _real_failure,
            )
            .order_by(BotHealthEvent.created_at.desc())
            .first()
        )
        if last:
            official["last_error"] = {
                "detail": last.detail,
                "category": last.category,
                "ref": last.ref,
                "created_at": last.created_at.isoformat(),
            }
    except Exception as e:
        _log.warning("bot-health official summary failed: %s", e)

    # Query the Bot model — the canonical list shown on the user dashboard
    # (every community/custom bot has a Bot row used by the polling engine).
    paginated = Bot.query.order_by(Bot.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    bots = []
    owner_ids = {b.user_id for b in paginated.items if b.user_id}
    owners = {}
    if owner_ids:
        for u in User.query.filter(User.id.in_(owner_ids)).all():
            owners[u.id] = u
    for b in paginated.items:
        owner = owners.get(b.user_id)
        bots.append({
            "id": b.id,
            "bot_username": b.bot_username,
            "bot_name": b.bot_name,
            "owner_email": owner.email if owner else None,
            "status": b.get_health_status(),      # active | idle | offline | unreachable
            "is_active": b.is_active,
            "error_count_24h": int(counts_by_ref.get(str(b.id), 0)),
            "last_error_at": last_err_by_ref.get(str(b.id)),
            "last_active": b.last_active.isoformat() if b.last_active else None,
        })

    total_errors_24h = 0
    try:
        total_errors_24h = BotHealthEvent.query.filter(
            BotHealthEvent.created_at >= since, _real_failure
        ).count()
    except Exception:
        pass

    return jsonify({
        "official": official,
        "custom_bots": bots,
        "total": paginated.total,
        "pages": paginated.pages,
        "page": page,
        "totals": {
            "total_custom_bots": paginated.total,
            "errors_24h": total_errors_24h,
        },
    })


@admin_bp.route("/bot-health/ping", methods=["POST"])
@require_permission(rbac.P_BOTS_MANAGE)
@rate_limit(requests_per_minute=30)
def admin_bot_health_ping():
    """Active reachability test — calls Telegram getMe with the bot's real token."""
    import httpx

    data = request.get_json() or {}
    scope = data.get("scope")
    bot_id = data.get("id")

    token = None
    bot_row = None
    if scope == "official":
        token = Config.TELEGRAM_BOT_TOKEN
        if not token:
            return jsonify({"ok": False, "error": "TELEGRAM_BOT_TOKEN not set"}), 200
    elif scope == "custom":
        bot_row = Bot.query.get(bot_id)
        if not bot_row:
            return jsonify({"error": "Bot not found"}), 404
        try:
            token = bot_row.get_token()
        except Exception as e:
            return jsonify({"ok": False, "error": f"Token decrypt failed: {e}"}), 200
    else:
        return jsonify({"error": "Invalid scope"}), 400

    try:
        resp = httpx.get(f"https://api.telegram.org/bot{token}/getMe", timeout=8.0)
        body = resp.json()
        if resp.status_code == 200 and body.get("ok"):
            username = body.get("result", {}).get("username")
            # Note: a reachable token does NOT mean the bot is enabled — is_active
            # may still be False (owner stopped it). We report reachability only and
            # don't auto-flip is_active to avoid silently restarting a stopped bot.
            return jsonify({"ok": True, "username": username, "is_active": bot_row.is_active if bot_row else True})
        err = body.get("description") or f"HTTP {resp.status_code}"
        if bot_row is not None:
            from ..health import record_bot_error
            record_bot_error("custom", bot_row.id, "handler", f"getMe: {err}")
        return jsonify({"ok": False, "error": err})
    except Exception as e:
        if bot_row is not None:
            from ..health import record_bot_error
            record_bot_error("custom", bot_row.id, "handler", f"getMe: {e}")
        return jsonify({"ok": False, "error": str(e)[:200]})


@admin_bp.route("/bot-health/errors", methods=["GET"])
@require_permission(rbac.P_HEALTH_VIEW)
@rate_limit(requests_per_minute=60)
def admin_bot_health_errors():
    """Recent error rows for drill-down, optionally filtered by scope/ref."""
    scope = request.args.get("scope")
    ref = request.args.get("ref")
    limit = min(request.args.get("limit", 50, type=int), 200)

    q = BotHealthEvent.query
    if scope:
        q = q.filter(BotHealthEvent.scope == scope)
    if ref:
        q = q.filter(BotHealthEvent.ref == str(ref))
    rows = q.order_by(BotHealthEvent.created_at.desc()).limit(limit).all()
    return jsonify({"errors": [r.to_dict() for r in rows]})


# ── Bot Health Center (P1) ─────────────────────────────────────────────────────

@admin_bp.route("/bot-health-center", methods=["GET"])
@require_permission(rbac.P_HEALTH_VIEW)
@rate_limit(requests_per_minute=30)
def admin_bot_health_center():
    """Rolled-up health grades + per-bot state from the scheduled ping job."""
    from ..models import BotHealthState
    states = BotHealthState.query.order_by(BotHealthState.health_grade.asc()).all()
    grades = ["healthy", "warning", "critical", "inactive", "archived"]
    summary = {g: 0 for g in grades}
    for s in states:
        summary[s.health_grade] = summary.get(s.health_grade, 0) + 1

    owner_ids = {s.owner_user_id for s in states if s.owner_user_id}
    owners = {u.id: u for u in User.query.filter(User.id.in_(owner_ids)).all()} if owner_ids else {}

    rows = []
    for s in states:
        d = s.to_dict()
        owner = owners.get(s.owner_user_id)
        d["owner_email"] = owner.email if owner else None
        rows.append(d)

    return jsonify({
        "summary": summary,
        "total_monitored": len(states),
        "bots": rows,
        "note": "State is refreshed by the scheduled getMe ping job (every 6h). Use 'Run check now' to refresh on demand.",
    })


@admin_bp.route("/bot-health-center/run", methods=["POST"])
@require_permission(rbac.P_BOTS_MANAGE)
@rate_limit(requests_per_minute=4)
def admin_bot_health_center_run():
    """Manually run the health-check sweep now (admins) — pings every bot."""
    from ..bot_health_monitor import run_health_checks
    try:
        from ..scheduler import _send_telegram_dm
    except Exception:
        _send_telegram_dm = None
    summary = run_health_checks(db, send_dm=_send_telegram_dm)
    return jsonify({"message": "Health check complete", "summary": summary})


# ── AI self-test (P2) — real end-to-end calls ──────────────────────────────────

@admin_bp.route("/ai-selftest", methods=["POST"])
@require_permission(rbac.P_AI_MANAGE)
@rate_limit(requests_per_minute=4)
def admin_ai_selftest():
    """Actually exercise each AI path with the configured platform key and report
    Working / Broken / Not Connected. This turns the static availability audit
    into a real end-to-end test runnable in any environment that has a key."""
    from .. import secret_vault as _sv
    platform_key = _sv.get_secret("PLATFORM_OPENROUTER_API_KEY")
    features = [
        "Chat / Echo AI (replies, digests, summaries)",
        "AI moderation (relevance / anti-promo)",
        "Embeddings (Notes / Knowledge AI search)",
    ]
    if not platform_key:
        return jsonify({
            "tested_with": "none",
            "results": [{
                "feature": f, "status": "not_connected",
                "detail": "No platform AI key (PLATFORM_OPENROUTER_API_KEY) set. Users with their own workspace key are unaffected.",
            } for f in features],
        })

    key_info = {
        "provider": "openrouter", "api_key": platform_key,
        "model": "openai/gpt-4o-mini", "base_url": "https://openrouter.ai/api/v1",
    }
    results = []

    # 1. Chat / Echo AI — real completion through the digest helper.
    try:
        from ..assistant.digest_ai import generate_ai_summary
        out = generate_ai_summary(
            [{"sender": "Alice", "text": "We shipped the new pricing page today."},
             {"sender": "Bob", "text": "Conversions are up 12%."}],
            "openrouter", platform_key, "openai/gpt-4o-mini", "https://openrouter.ai/api/v1",
        )
        results.append({"feature": features[0],
                        "status": "working" if out else "broken",
                        "detail": (out[:200] if out else "Call returned no text.")})
    except Exception as exc:
        results.append({"feature": features[0], "status": "broken", "detail": str(exc)[:200]})

    # 2. AI moderation — real verdict on a clearly promotional sample.
    try:
        from ..bot_features.moderation import ModerationSystem
        verdict, _reason = ModerationSystem._call_ai_moderation(
            "🚀 JOIN MY PUMP GROUP! 100x guaranteed — DM me for the link now!!!",
            "A support group for new parents", "Parenting Chat", key_info,
        )
        if verdict and verdict != "ok":
            detail = f"verdict={verdict} — flagged promotional spam correctly"
            status = "working"
        elif verdict == "ok":
            detail = "verdict=ok — call succeeded (model was lenient on the sample)"
            status = "working"
        else:
            detail, status = "No verdict returned.", "broken"
        results.append({"feature": features[1], "status": status, "detail": detail})
    except Exception as exc:
        results.append({"feature": features[1], "status": "broken", "detail": str(exc)[:200]})

    # 3. Embeddings — needs an OpenAI-compatible embeddings key.
    try:
        from ..assistant.embedding_service import generate_embedding, _get_platform_openai_key
        emb_key = _get_platform_openai_key()
        if not emb_key:
            results.append({"feature": features[2], "status": "not_connected",
                            "detail": "No OpenAI-compatible embeddings key configured."})
        else:
            vec = generate_embedding("telegizer bot health check", emb_key)
            results.append({"feature": features[2],
                            "status": "working" if vec else "broken",
                            "detail": (f"vector dim={len(vec)}" if vec else "Embedding call returned nothing.")})
    except Exception as exc:
        results.append({"feature": features[2], "status": "broken", "detail": str(exc)[:200]})

    return jsonify({"tested_with": "platform_key", "results": results})


@admin_bp.route("/custom-bots/<int:bot_id>/disable", methods=["POST"])
@require_permission(rbac.P_BOTS_MANAGE)
@rate_limit(requests_per_minute=10)
def admin_disable_custom_bot(bot_id):
    bot = CustomBot.query.get(bot_id)
    if not bot:
        return jsonify({"error": "Bot not found"}), 404
    bot.status = "inactive"
    db.session.commit()
    return jsonify({"message": "Custom bot disabled", "bot": bot.to_dict()})


@admin_bp.route("/custom-bots/<int:bot_id>/enable", methods=["POST"])
@require_permission(rbac.P_BOTS_MANAGE)
@rate_limit(requests_per_minute=10)
def admin_enable_custom_bot(bot_id):
    bot = CustomBot.query.get(bot_id)
    if not bot:
        return jsonify({"error": "Bot not found"}), 404
    bot.status = "active"
    db.session.commit()
    return jsonify({"message": "Custom bot enabled", "bot": bot.to_dict()})


@admin_bp.route("/custom-bots/<int:bot_id>/ping", methods=["POST"])
@require_permission(rbac.P_BOTS_MANAGE)
@rate_limit(requests_per_minute=20)
def admin_ping_custom_bot(bot_id):
    """Active getMe reachability test for a CustomBot, rolled into BotHealthState.

    Distinct from /bot-health/ping (which targets the legacy `bots` table); this
    pings the new custom_bots row and updates the same state the 6h monitor uses,
    so manual + scheduled checks stay consistent.
    """
    from ..models import BotHealthState, BotHealthEvent
    from ..bot_health_monitor import _ping_telegram, grade_for
    bot = CustomBot.query.get(bot_id)
    if not bot:
        return jsonify({"error": "Bot not found"}), 404
    try:
        token = bot.get_token()
    except Exception as e:
        return jsonify({"ok": False, "error": f"Token decrypt failed: {e}"}), 200

    now = datetime.utcnow()
    ok, detail = _ping_telegram(token) if token else (False, "no token")

    state = BotHealthState.query.filter_by(scope="custom", ref=str(bot.id)).first()
    if not state:
        state = BotHealthState(scope="custom", ref=str(bot.id))
        db.session.add(state)
    state.bot_username = bot.bot_username
    state.owner_user_id = bot.owner_user_id
    state.last_ping_at = now
    if ok:
        state.consecutive_failures = 0
        state.last_successful_ping = now
        state.last_error = None
    else:
        state.consecutive_failures = (state.consecutive_failures or 0) + 1
        state.last_failed_ping = now
        state.last_error = detail
        try:
            from ..error_classification import classify_error
            err_class, severity, _ = classify_error(detail)
            db.session.add(BotHealthEvent(scope="custom", ref=str(bot.id), category="ping",
                                          detail=str(detail)[:500], severity=severity,
                                          error_class=err_class, created_at=now))
        except Exception:
            pass
    state.health_grade = grade_for(state.consecutive_failures, state.last_successful_ping, now)
    db.session.commit()

    return jsonify({"ok": ok, "username": bot.bot_username, "grade": state.health_grade,
                    "error": None if ok else detail})


@admin_bp.route("/custom-bots/<int:bot_id>/detail", methods=["GET"])
@require_permission(rbac.P_BOTS_VIEW)
@rate_limit(requests_per_minute=60)
def admin_custom_bot_detail(bot_id):
    """Full profile for one custom bot — identity, owner, connected groups,
    members managed, health, feature usage and config status (never the token).
    """
    from ..models import BotHealthState, FeatureUsageEvent
    bot = CustomBot.query.get(bot_id)
    if not bot:
        return jsonify({"error": "Bot not found"}), 404

    data = bot.to_dict()  # never includes the token (include_token defaults False)

    # ── Owner ──────────────────────────────────────────────────────────────────
    owner = User.query.get(bot.owner_user_id)
    data["owner"] = {
        "user_id": bot.owner_user_id,
        "email": owner.email if owner else None,
        "name": owner.full_name if owner else None,
        "telegram_username": owner.telegram_username if owner else None,
        "tier": owner.subscription_tier if owner else None,
    }

    # ── Connected groups + members managed ─────────────────────────────────────
    # Single source of truth shared with the user dashboard: resolves BOTH the new
    # TelegramGroup.linked_bot_id lineage AND the legacy bots/groups tables (matched
    # by username). Previously this read only linked_bot_id, so a bot whose groups
    # live in the legacy tables showed "No connected groups" here while the user
    # dashboard correctly showed them.
    from ..bot_links import connected_groups_summary
    summary = connected_groups_summary(bot)
    data["connected_groups"] = summary["connected_groups"]
    data["groups_count"] = summary["groups_count"]
    data["members_managed"] = summary["members_managed"]

    # ── Health (per-bot getMe ping state + error log) ──────────────────────────
    now = datetime.utcnow()
    state = BotHealthState.query.filter_by(scope="custom", ref=str(bot.id)).first()
    err_q = BotHealthEvent.query.filter(BotHealthEvent.scope == "custom", BotHealthEvent.ref == str(bot.id))
    recent_errors = err_q.order_by(BotHealthEvent.created_at.desc()).limit(10).all()
    data["health"] = {
        "grade": state.health_grade if state else "unknown",
        "consecutive_failures": state.consecutive_failures if state else 0,
        "last_ping_at": state.last_ping_at.isoformat() if state and state.last_ping_at else None,
        "last_successful_ping": state.last_successful_ping.isoformat() if state and state.last_successful_ping else None,
        "last_error": state.last_error if state else None,
        "errors_24h": err_q.filter(BotHealthEvent.created_at >= now - timedelta(days=1)).count(),
        "errors_7d": err_q.filter(BotHealthEvent.created_at >= now - timedelta(days=7)).count(),
        "recent_errors": [e.to_dict() for e in recent_errors],
    }

    # ── Feature usage attributed to this bot (bot_ref) ─────────────────────────
    usage_rows = (
        db.session.query(FeatureUsageEvent.feature, db.func.coalesce(db.func.sum(FeatureUsageEvent.count), 0))
        .filter(FeatureUsageEvent.bot_ref == str(bot.id))
        .group_by(FeatureUsageEvent.feature)
        .all()
    )
    usage = {feat: int(c) for feat, c in usage_rows}
    data["feature_usage"] = {
        "by_feature": usage,
        "total": sum(usage.values()),
        "note": "Per-bot usage attribution is partial — group-level moderation counts appear in each group's detail.",
    }

    # ── AI/Token usage attributed to this bot ──────────────────────────────────
    # Match by bot_ref (direct, set by the recorder) OR any of the bot's connected
    # group refs (covers rows logged before bot_ref was populated). Either side
    # alone could miss rows, so OR them for the most complete attribution.
    try:
        from ..models import AITokenUsage
        from sqlalchemy import or_ as _or
        grefs = [str(g.telegram_group_id) for g in groups if g.telegram_group_id]
        conds = [AITokenUsage.bot_ref == str(bot.id)]
        if grefs:
            conds.append(AITokenUsage.group_ref.in_(grefs))
        arow = db.session.query(
            db.func.coalesce(db.func.sum(AITokenUsage.input_tokens), 0),
            db.func.coalesce(db.func.sum(AITokenUsage.output_tokens), 0),
            db.func.coalesce(db.func.sum(AITokenUsage.total_tokens), 0),
            db.func.coalesce(db.func.sum(AITokenUsage.cost_usd), 0),
            db.func.count(AITokenUsage.id),
        ).filter(_or(*conds)).one()
        data["ai_usage"] = {
            "input_tokens": int(arow[0] or 0), "output_tokens": int(arow[1] or 0),
            "total_tokens": int(arow[2] or 0), "cost_usd": round(float(arow[3] or 0), 4),
            "calls": int(arow[4] or 0),
        }
    except Exception:
        data["ai_usage"] = None

    # ── Config / token status (status only — secret never exposed) ─────────────
    data["config"] = {
        "token_configured": bool(bot.bot_token_encrypted),
        "status": bot.status,
        "created_at": bot.created_at.isoformat() if bot.created_at else None,
        "updated_at": bot.updated_at.isoformat() if bot.updated_at else None,
    }

    # Revenue is not attributed per-bot (bots aren't sold individually).
    data["revenue_not_tracked"] = True

    return jsonify({"bot": data})


# ── Directory Moderation ───────────────────────────────────────────────────────

@admin_bp.route("/directory/pending", methods=["GET"])
@require_permission(rbac.P_MODERATION_VIEW)
@rate_limit(requests_per_minute=60)
def list_pending_directory():
    pending = DirectoryListing.query.filter_by(moderation_status="pending").order_by(
        DirectoryListing.created_at.asc()
    ).all()
    return jsonify({"listings": [l.to_dict(include_contact=True) for l in pending], "total": len(pending)})


@admin_bp.route("/directory", methods=["GET"])
@require_permission(rbac.P_MODERATION_VIEW)
@rate_limit(requests_per_minute=60)
def list_all_directory():
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 20, type=int), 100)
    status_filter = request.args.get("status", "")
    query = DirectoryListing.query
    if status_filter:
        query = query.filter(DirectoryListing.moderation_status == status_filter)
    query = query.order_by(DirectoryListing.created_at.desc())
    paginated = query.paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        "listings": [l.to_dict(include_contact=True) for l in paginated.items],
        "total": paginated.total,
        "pages": paginated.pages,
        "page": page,
    })


@admin_bp.route("/directory/<int:lid>/moderate", methods=["POST"])
@require_permission(rbac.P_MODERATION_MANAGE)
@rate_limit(requests_per_minute=30)
def moderate_directory_listing(lid):
    listing = DirectoryListing.query.get(lid)
    if not listing:
        return jsonify({"error": "Listing not found"}), 404
    data = request.get_json() or {}
    action = data.get("action")
    if action not in ("approve", "reject"):
        return jsonify({"error": "action must be 'approve' or 'reject'"}), 400
    listing.moderation_status = "approved" if action == "approve" else "rejected"
    db.session.commit()
    return jsonify({"listing": listing.to_dict(include_contact=True)})


# ── Announcements ──────────────────────────────────────────────────────────────

@admin_bp.route("/announcements", methods=["GET"])
@require_permission(rbac.P_ANNOUNCEMENTS_MANAGE)
@rate_limit(requests_per_minute=30)
def list_announcements():
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 20, type=int), 100)
    paginated = AdminAnnouncement.query.order_by(
        AdminAnnouncement.created_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        "announcements": [a.to_dict() for a in paginated.items],
        "total": paginated.total,
        "pages": paginated.pages,
        "page": page,
    })


@admin_bp.route("/announcements", methods=["POST"])
@require_permission(rbac.P_ANNOUNCEMENTS_MANAGE)
@rate_limit(requests_per_minute=10)
def create_announcement():
    admin_user = _get_current_user()
    data = request.get_json() or {}

    title = (data.get("title") or "").strip()
    body = (data.get("body") or "").strip()
    if not title or not body:
        return jsonify({"error": "title and body are required"}), 400
    if len(title) > 200:
        return jsonify({"error": "title must be under 200 characters"}), 400

    audience = data.get("audience", "all")
    if audience not in ("all", "free", "pro", "enterprise", "with_bots"):
        return jsonify({"error": "Invalid audience"}), 400

    channel = data.get("channel", "inapp")
    if channel not in ("inapp", "email", "both"):
        return jsonify({"error": "Invalid channel"}), 400

    announcement_type = data.get("announcement_type", "info")
    if announcement_type not in ("info", "warning", "critical"):
        return jsonify({"error": "Invalid announcement_type"}), 400

    announcement = AdminAnnouncement(
        admin_id=admin_user.id,
        title=title,
        body=body,
        audience=audience,
        channel=channel,
        announcement_type=announcement_type,
    )
    db.session.add(announcement)
    db.session.flush()  # get the ID before sending

    # Build recipient query
    recipient_query = User.query.filter_by(is_banned=False)
    if audience == "free":
        recipient_query = recipient_query.filter_by(subscription_tier="free")
    elif audience == "pro":
        recipient_query = recipient_query.filter_by(subscription_tier="pro")
    elif audience == "enterprise":
        recipient_query = recipient_query.filter_by(subscription_tier="enterprise")
    elif audience == "with_bots":
        from ..models import Bot as BotModel
        bot_user_ids = db.session.query(BotModel.owner_id).distinct()
        recipient_query = recipient_query.filter(User.id.in_(bot_user_ids))

    recipients = recipient_query.all()
    delivered = 0

    # Deliver in-app notifications
    if channel in ("inapp", "both"):
        for user in recipients:
            notif = UserNotification(
                user_id=user.id,
                type=f"announcement_{announcement_type}",
                title=title,
                message=body,
            )
            db.session.add(notif)
            delivered += 1

    announcement.sent = True
    announcement.sent_at = datetime.utcnow()
    announcement.delivered_count = delivered
    db.session.commit()

    # Email delivery via Celery (fire and forget)
    if channel in ("email", "both"):
        try:
            from ..tasks import send_announcement_emails
            send_announcement_emails.delay(announcement.id, [u.id for u in recipients])
        except Exception:
            pass  # Email task is best-effort; in-app delivery already done

    return jsonify({
        "announcement": announcement.to_dict(),
        "delivered_count": delivered,
        "message": f"Announcement sent to {delivered} users",
    }), 201


@admin_bp.route("/announcements/<int:ann_id>", methods=["DELETE"])
@require_permission(rbac.P_ANNOUNCEMENTS_MANAGE)
@rate_limit(requests_per_minute=10)
def delete_announcement(ann_id):
    ann = AdminAnnouncement.query.get(ann_id)
    if not ann:
        return jsonify({"error": "Announcement not found"}), 404
    db.session.delete(ann)
    db.session.commit()
    return jsonify({"message": "Announcement deleted"})


# ── Audit Logs ─────────────────────────────────────────────────────────────────

@admin_bp.route("/audit-logs", methods=["GET"])
@require_permission(rbac.P_AUDIT_VIEW)
@rate_limit(requests_per_minute=30)
def list_audit_logs():
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 100)
    admin_id_filter = request.args.get("admin_id", type=int)
    method_filter = request.args.get("method", "")

    query = AdminAuditLog.query.order_by(AdminAuditLog.created_at.desc())
    if admin_id_filter:
        query = query.filter(AdminAuditLog.admin_id == admin_id_filter)
    if method_filter:
        query = query.filter(AdminAuditLog.method == method_filter.upper())

    paginated = query.paginate(page=page, per_page=per_page, error_out=False)

    # Enrich with admin email (batch load)
    admin_ids = {log.admin_id for log in paginated.items}
    admins = {u.id: u.email for u in User.query.filter(User.id.in_(admin_ids)).all()} if admin_ids else {}

    items = []
    for log in paginated.items:
        d = log.to_dict()
        d["admin_email"] = admins.get(log.admin_id, "unknown")
        items.append(d)

    return jsonify({
        "logs": items,
        "total": paginated.total,
        "pages": paginated.pages,
        "page": page,
    })


# ── Unified Event Log ───────────────────────────────────────────────────────────

@admin_bp.route("/event-log", methods=["GET"])
@require_permission(rbac.P_AUDIT_VIEW)
@rate_limit(requests_per_minute=30)
def unified_event_log():
    """One merged, filterable timeline across admin actions, bot/group events,
    bot-health errors, payments and referrals.

    Each source is bounded (most-recent rows only) then merged + sorted in
    Python — fine for an operator timeline and avoids a heavyweight SQL UNION
    across schemas. Normalised shape: {source, type, actor, target, message,
    severity, at}.
    """
    source = request.args.get("source", "all")
    search = (request.args.get("search", "") or "").strip().lower()
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 100)
    cap = 400  # per-source fetch ceiling

    want = (lambda s: source in ("all", s))
    events = []

    if want("admin"):
        rows = AdminAuditLog.query.order_by(AdminAuditLog.created_at.desc()).limit(cap).all()
        admin_ids = {r.admin_id for r in rows}
        emails = {u.id: u.email for u in User.query.filter(User.id.in_(admin_ids)).all()} if admin_ids else {}
        for r in rows:
            events.append({
                "source": "admin", "type": r.action, "actor": emails.get(r.admin_id, f"admin#{r.admin_id}"),
                "target": (f"{r.target_type}:{r.target_id}" if r.target_type else None),
                "message": f"{r.method} {r.path}", "severity": r.severity or "info",
                "at": r.created_at.isoformat(),
            })

    if want("bots") or want("groups"):
        rows = BotEvent.query.order_by(BotEvent.created_at.desc()).limit(cap).all()
        for r in rows:
            events.append({
                "source": "group", "type": r.event_type, "actor": "bot",
                "target": r.telegram_group_id, "message": r.message, "severity": "info",
                "at": r.created_at.isoformat(),
            })

    if want("health"):
        rows = BotHealthEvent.query.order_by(BotHealthEvent.created_at.desc()).limit(cap).all()
        for r in rows:
            events.append({
                "source": "health", "type": r.error_class or r.category, "actor": f"{r.scope}:{r.ref}",
                "target": r.ref, "message": r.detail, "severity": r.severity or "warning",
                "at": r.created_at.isoformat(),
            })

    if want("payments"):
        rows = PaymentHistory.query.order_by(PaymentHistory.created_at.desc()).limit(cap).all()
        uid_set = {r.user_id for r in rows}
        emails = {u.id: u.email for u in User.query.filter(User.id.in_(uid_set)).all()} if uid_set else {}
        for r in rows:
            events.append({
                "source": "payment", "type": f"{r.status}_{r.plan}", "actor": emails.get(r.user_id, f"user#{r.user_id}"),
                "target": r.provider, "message": f"{r.plan} {r.billing_period or ''} · {(r.amount_usd or 0)/100:.2f} {r.currency or 'USD'}".strip(),
                "severity": "info" if r.status == "confirmed" else "warning",
                "at": r.created_at.isoformat(),
            })

    if want("referrals"):
        rows = Referral.query.order_by(Referral.created_at.desc()).limit(cap).all()
        for r in rows:
            events.append({
                "source": "referral", "type": f"referral_{r.status}", "actor": f"user#{r.referrer_user_id}",
                "target": f"user#{r.referred_user_id}",
                "message": f"status={r.status}" + (" · ip_match" if r.ip_match else "") + (" · device_match" if r.device_match else ""),
                "severity": "warning" if (r.ip_match or r.device_match) else "info",
                "at": r.created_at.isoformat(),
            })

    if search:
        def _hit(e):
            return any(search in str(e.get(f) or "").lower() for f in ("type", "actor", "target", "message", "source"))
        events = [e for e in events if _hit(e)]

    events.sort(key=lambda e: e["at"], reverse=True)
    total = len(events)
    start = (page - 1) * per_page
    items = events[start:start + per_page]
    pages = (total + per_page - 1) // per_page if per_page else 1

    return jsonify({
        "events": items, "total": total, "pages": pages, "page": page,
        "note": "Each source is capped at the 400 most-recent rows before merging.",
    })


@admin_bp.route("/bot-health/clear/<scope>/<ref>", methods=["POST"])
@require_permission(rbac.P_BOTS_MANAGE)
@rate_limit(requests_per_minute=20)
def admin_clear_bot_health(scope, ref):
    """Resolve/clear a bot's error state after a fix: reset the rolled-up health
    state to healthy. The append-only BotHealthEvent log is preserved.
    """
    from ..models import BotHealthState
    state = BotHealthState.query.filter_by(scope=scope, ref=str(ref)).first()
    if not state:
        return jsonify({"error": "No health state for that bot"}), 404
    state.consecutive_failures = 0
    state.last_error = None
    state.health_grade = "healthy"
    state.last_alert_grade = None
    db.session.commit()
    # NB: the require_permission decorator already audit-logs this call.
    return jsonify({"message": "Health state cleared", "state": state.to_dict()})


# ── Reported Messages ──────────────────────────────────────────────────────────

@admin_bp.route("/reports", methods=["GET"])
@require_permission(rbac.P_MODERATION_VIEW)
@rate_limit(requests_per_minute=30)
def list_reports():
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 100)
    status_filter = request.args.get("status", "")  # open | resolved | ""
    source_filter = request.args.get("source", "")  # custom | official | ""

    custom_reports = []
    official_reports = []

    if source_filter in ("", "custom"):
        q = ReportedMessage.query.order_by(ReportedMessage.created_at.desc())
        if status_filter:
            q = q.filter(ReportedMessage.status == status_filter)
        custom_reports = q.all()

    if source_filter in ("", "official"):
        q = OfficialReportedMessage.query.order_by(OfficialReportedMessage.created_at.desc())
        if status_filter:
            q = q.filter(OfficialReportedMessage.status == status_filter)
        official_reports = q.all()

    combined = []
    for r in custom_reports:
        combined.append({
            "id": r.id,
            "source": "custom",
            "group_id": r.group_id,
            "group_name": r.group.name if hasattr(r, "group") and r.group else None,
            "reporter_user_id": str(r.reporter_user_id),
            "reported_user_id": str(r.reported_user_id),
            "reason": r.reason,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })
    for r in official_reports:
        combined.append({
            "id": r.id,
            "source": "official",
            "group_id": r.telegram_group_id,
            "group_name": None,
            "reporter_user_id": str(r.reporter_user_id),
            "reported_user_id": str(r.reported_user_id),
            "reason": r.reason,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })

    combined.sort(key=lambda x: x["created_at"] or "", reverse=True)

    total = len(combined)
    start = (page - 1) * per_page
    page_items = combined[start: start + per_page]

    return jsonify({
        "reports": page_items,
        "total": total,
        "pages": max(1, (total + per_page - 1) // per_page),
        "page": page,
    })


@admin_bp.route("/reports/<string:source>/<int:report_id>/resolve", methods=["POST"])
@require_permission(rbac.P_MODERATION_MANAGE)
@rate_limit(requests_per_minute=30)
def resolve_report(source, report_id):
    if source == "custom":
        report = ReportedMessage.query.get(report_id)
    elif source == "official":
        report = OfficialReportedMessage.query.get(report_id)
    else:
        return jsonify({"error": "source must be 'custom' or 'official'"}), 400

    if not report:
        return jsonify({"error": "Report not found"}), 404

    report.status = "resolved"
    db.session.commit()
    return jsonify({"message": "Report resolved"})


# ── Feature Adoption ───────────────────────────────────────────────────────────

@admin_bp.route("/feature-adoption", methods=["GET"])
@require_permission(rbac.P_ANALYTICS_VIEW)
@rate_limit(requests_per_minute=30)
def feature_adoption():
    total_users = User.query.count() or 1

    def _pct(n):
        return round(n / total_users * 100, 1)

    custom_bots = db.session.query(db.func.count(db.func.distinct(CustomBot.owner_user_id))).scalar() or 0
    linked_groups = db.session.query(db.func.count(db.func.distinct(TelegramGroup.owner_user_id))).scalar() or 0
    workflows = db.session.query(db.func.count(db.func.distinct(AutomationWorkflow.owner_user_id))).scalar() or 0
    reminders = db.session.query(db.func.count(db.func.distinct(WorkspaceReminder.owner_user_id))).scalar() or 0
    notes = db.session.query(db.func.count(db.func.distinct(Note.user_id))).scalar() or 0
    channels = db.session.query(db.func.count(db.func.distinct(Channel.user_id))).scalar() or 0
    # KnowledgeDocument links to groups (group_id), not users directly — count distinct groups with docs
    knowledge_docs = db.session.query(db.func.count(db.func.distinct(KnowledgeDocument.group_id))).filter(KnowledgeDocument.group_id.isnot(None)).scalar() or 0
    totp_enabled = User.query.filter(User.totp_enabled == True).count() or 0  # noqa: E712
    telegram_linked = User.query.filter(User.telegram_user_id.isnot(None)).count() or 0

    features = [
        {"feature": "Custom Bots", "users": custom_bots, "pct": _pct(custom_bots)},
        {"feature": "Linked Groups", "users": linked_groups, "pct": _pct(linked_groups)},
        {"feature": "Automation Workflows", "users": workflows, "pct": _pct(workflows)},
        {"feature": "Smart Reminders", "users": reminders, "pct": _pct(reminders)},
        {"feature": "Notes", "users": notes, "pct": _pct(notes)},
        {"feature": "Channels", "users": channels, "pct": _pct(channels)},
        {"feature": "Knowledge Docs (groups)", "users": knowledge_docs, "pct": _pct(knowledge_docs)},
        {"feature": "2FA Enabled", "users": totp_enabled, "pct": _pct(totp_enabled)},
        {"feature": "Telegram Linked", "users": telegram_linked, "pct": _pct(telegram_linked)},
    ]
    features.sort(key=lambda x: x["users"], reverse=True)

    return jsonify({"total_users": total_users, "features": features})


# ── Feature Usage (Telegizer Bot / Echo) ───────────────────────────────────────

@admin_bp.route("/feature-usage", methods=["GET"])
@require_permission(rbac.P_ANALYTICS_VIEW)
@rate_limit(requests_per_minute=30)
def feature_usage():
    """Real feature-usage analytics from the FeatureUsageEvent spine.

    ?view=bot  → Telegizer bot (official + custom lineages)
    ?view=echo → Echo assistant (AIActivity + echo-scoped usage)
    """
    from ..feature_usage import usage_overview, echo_overview
    view = request.args.get("view", "bot")
    if view == "echo":
        return jsonify({"view": "echo", **echo_overview()})
    return jsonify({"view": "bot", **usage_overview(["official", "custom"])})


# ── Critical admin actions (open/resolved triage) ──────────────────────────────

@admin_bp.route("/critical-actions", methods=["GET"])
@require_permission(rbac.P_AUDIT_VIEW)
@rate_limit(requests_per_minute=30)
def list_critical_actions():
    """Recent critical admin actions with open/resolved status.

    `status` ∈ {open, resolved, all} (default open). Returns counts so the
    dashboard badge can show unresolved-only while the tab can show everything.
    """
    status = (request.args.get("status") or "open").lower()
    page = max(1, request.args.get("page", 1, type=int) or 1)
    per_page = min(100, max(1, request.args.get("per_page", 50, type=int) or 50))

    base = AdminAuditLog.query.filter(AdminAuditLog.severity == "critical")
    q = base
    if status == "open":
        q = q.filter(AdminAuditLog.resolved_at.is_(None))
    elif status == "resolved":
        q = q.filter(AdminAuditLog.resolved_at.isnot(None))

    total = q.count()
    rows = (q.order_by(AdminAuditLog.created_at.desc())
            .offset((page - 1) * per_page).limit(per_page).all())

    admin_ids = {r.admin_id for r in rows} | {r.resolved_by for r in rows if r.resolved_by}
    emails = {u.id: u.email for u in User.query.filter(User.id.in_(admin_ids)).all()} if admin_ids else {}

    items = []
    for r in rows:
        d = r.to_dict()
        d["admin_email"] = emails.get(r.admin_id)
        d["resolved_by_email"] = emails.get(r.resolved_by) if r.resolved_by else None
        items.append(d)

    return jsonify({
        "actions": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
        "open_count": base.filter(AdminAuditLog.resolved_at.is_(None)).count(),
        "resolved_count": base.filter(AdminAuditLog.resolved_at.isnot(None)).count(),
    })


@admin_bp.route("/critical-actions/<int:action_id>/resolve", methods=["POST"])
@require_permission(rbac.P_AUDIT_VIEW)
@rate_limit(requests_per_minute=30)
def resolve_critical_action(action_id):
    """Mark a critical action resolved (or reopen it with ?reopen=true)."""
    row = AdminAuditLog.query.get(action_id)
    if not row or (row.severity != "critical"):
        return jsonify({"error": "Critical action not found"}), 404

    body = request.get_json(silent=True) or {}
    reopen = (request.args.get("reopen") == "true") or (body.get("reopen") is True)
    user = _get_current_user()
    if reopen:
        row.resolved_at = None
        row.resolved_by = None
        msg = "Critical action reopened"
    else:
        row.resolved_at = datetime.utcnow()
        row.resolved_by = user.id if user else None
        msg = "Critical action resolved"
    db.session.commit()
    return jsonify({"message": msg, "action": row.to_dict()})


# ── Proof Metrics (public-stats source) ─────────────────────────────────────────

@admin_bp.route("/proof-metrics", methods=["GET"])
@require_permission(rbac.P_ANALYTICS_VIEW)
@rate_limit(requests_per_minute=30)
def proof_metrics():
    """Platform-wide proof metrics + which are flagged public for the landing page."""
    from ..feature_usage import compute_proof_metrics
    from .. import platform_config as pc
    public_keys = pc.get_setting("proof_public_metrics", None)
    return jsonify(compute_proof_metrics(public_keys))


@admin_bp.route("/proof-metrics/sync-members", methods=["POST"])
@require_permission(rbac.P_CONFIG_MANAGE)
@rate_limit(requests_per_minute=4)
def proof_metrics_sync_members():
    """Reconcile TelegramGroup.member_count to live Telegram counts on demand.

    The same reconciliation the 6h background job runs, exposed so an admin can
    force "members protected" to refresh immediately (e.g. right after migrate.py)
    instead of waiting for the next sweep. Throttled hard — it makes one Telegram
    read per group.
    """
    from ..member_sync import sync_member_counts
    limit = request.args.get("limit", type=int)
    try:
        summary = sync_member_counts(limit=limit)
    except Exception as exc:  # never 500 the admin UI over a sync attempt
        _log.warning("on-demand member sync failed: %s", exc)
        return jsonify({"error": f"Member sync failed: {exc}"}), 502
    return jsonify(summary)


@admin_bp.route("/proof-metrics/public", methods=["PUT"])
@require_permission(rbac.P_CONFIG_MANAGE)
@rate_limit(requests_per_minute=20)
def update_proof_public():
    """Set which proof-metric keys are safe to show publicly (super/admin only)."""
    from .. import platform_config as pc
    data = request.get_json() or {}
    keys = data.get("keys")
    if not isinstance(keys, list):
        return jsonify({"error": "keys must be a list"}), 400
    keys = [str(k) for k in keys][:40]
    user = _get_current_user()
    pc.set_setting("proof_public_metrics", keys, user_id=user.id if user else None)
    # NB: the require_permission decorator already audit-logs this call.
    return jsonify({"message": "Public proof metrics updated", "keys": keys})


# ── Fraud Detection ────────────────────────────────────────────────────────────

@admin_bp.route("/fraud/clusters", methods=["GET"])
@require_permission(rbac.P_FRAUD_VIEW)
@rate_limit(requests_per_minute=20)
def fraud_clusters():
    """Multi-accounting detection: find ip_hash or device_hash shared by 2+ distinct users."""

    def _enrich_users(user_id_list):
        if not user_id_list:
            return []
        users = User.query.filter(User.id.in_(user_id_list)).all()
        return [{"id": u.id, "email": u.email, "tier": u.subscription_tier, "banned": u.is_banned} for u in users]

    # Step 1: find hashes with 2+ distinct users (no array_agg — avoids pg array type issues)
    ip_hash_rows = db.session.execute(db.text(
        "SELECT ip_hash, COUNT(DISTINCT user_id) AS cnt "
        "FROM suspicious_activities "
        "WHERE ip_hash IS NOT NULL AND user_id IS NOT NULL "
        "GROUP BY ip_hash HAVING COUNT(DISTINCT user_id) >= 2 "
        "ORDER BY cnt DESC LIMIT 30"
    )).fetchall()

    device_hash_rows = db.session.execute(db.text(
        "SELECT device_hash, COUNT(DISTINCT user_id) AS cnt "
        "FROM suspicious_activities "
        "WHERE device_hash IS NOT NULL AND user_id IS NOT NULL "
        "GROUP BY device_hash HAVING COUNT(DISTINCT user_id) >= 2 "
        "ORDER BY cnt DESC LIMIT 30"
    )).fetchall()

    clusters = []

    # Step 2: for each hash, fetch the distinct user_ids separately
    for row in ip_hash_rows:
        h = row[0]
        cnt = int(row[1])
        uid_rows = db.session.execute(db.text(
            "SELECT DISTINCT user_id FROM suspicious_activities "
            "WHERE ip_hash = :h AND user_id IS NOT NULL LIMIT 20"
        ), {"h": h}).fetchall()
        uid_list = [int(r[0]) for r in uid_rows]
        clusters.append({
            "type": "ip_hash",
            "hash_prefix": str(h)[:12],
            "user_count": cnt,
            "users": _enrich_users(uid_list),
        })

    for row in device_hash_rows:
        h = row[0]
        cnt = int(row[1])
        uid_rows = db.session.execute(db.text(
            "SELECT DISTINCT user_id FROM suspicious_activities "
            "WHERE device_hash = :h AND user_id IS NOT NULL LIMIT 20"
        ), {"h": h}).fetchall()
        uid_list = [int(r[0]) for r in uid_rows]
        clusters.append({
            "type": "device_hash",
            "hash_prefix": str(h)[:12],
            "user_count": cnt,
            "users": _enrich_users(uid_list),
        })

    clusters.sort(key=lambda x: x["user_count"], reverse=True)
    return jsonify({"clusters": clusters, "total": len(clusters)})


@admin_bp.route("/fraud/referral-farming", methods=["GET"])
@require_permission(rbac.P_FRAUD_VIEW)
@rate_limit(requests_per_minute=20)
def fraud_referral_farming():
    """Detect referral farming: referrers with many referrals where referred users share suspicious signals."""
    # Find referrers with 3+ referrals
    farming_rows = db.session.execute(db.text(
        "SELECT referrer_user_id, COUNT(*) AS cnt, "
        "SUM(CASE WHEN status = 'suspicious' THEN 1 ELSE 0 END) AS suspicious_count "
        "FROM referrals "
        "GROUP BY referrer_user_id HAVING COUNT(*) >= 3 "
        "ORDER BY suspicious_count DESC, cnt DESC LIMIT 50"
    )).fetchall()

    suspects = []
    for row in farming_rows:
        referrer = db.session.get(User, int(row[0]))
        if not referrer:
            continue
        total_refs = int(row[1])
        suspicious_refs = int(row[2] or 0)
        sa_count = SuspiciousActivity.query.filter_by(user_id=referrer.id).count()
        suspects.append({
            "referrer_id": referrer.id,
            "referrer_email": referrer.email,
            "referrer_tier": referrer.subscription_tier,
            "referrer_banned": referrer.is_banned,
            "total_referrals": total_refs,
            "suspicious_referrals": suspicious_refs,
            "referrer_suspicious_events": sa_count,
            "risk_score": suspicious_refs * 3 + sa_count,
        })

    suspects.sort(key=lambda x: x["risk_score"], reverse=True)
    return jsonify({"suspects": suspects, "total": len(suspects)})


@admin_bp.route("/fraud/payment-anomalies", methods=["GET"])
@require_permission(rbac.P_FRAUD_VIEW)
@rate_limit(requests_per_minute=20)
def fraud_payment_anomalies():
    """Detect payment anomalies: multiple payments in 24h, duplicate amounts, unusual amounts."""
    anomalies = []

    # Users with 2+ confirmed payments on the same calendar day
    dupe_rows = db.session.execute(db.text(
        "SELECT user_id, DATE(created_at) AS pay_date, COUNT(*) AS cnt "
        "FROM payment_history "
        "WHERE status = 'confirmed' "
        "GROUP BY user_id, DATE(created_at) HAVING COUNT(*) >= 2 "
        "ORDER BY cnt DESC LIMIT 30"
    )).fetchall()

    for row in dupe_rows:
        user = db.session.get(User, int(row[0]))
        if not user:
            continue
        anomalies.append({
            "type": "multiple_payments_same_day",
            "user_id": user.id,
            "user_email": user.email,
            "user_tier": user.subscription_tier,
            "date": str(row[1]),
            "payment_count": int(row[2]),
            "risk": "high" if int(row[2]) >= 4 else "medium",
        })

    # Payments outside normal price range (not $9 / $49 / $90 / $490)
    valid_amounts = [900, 4900, 9000, 49000]
    odd_payments = PaymentHistory.query.filter(
        PaymentHistory.status == "confirmed",
        PaymentHistory.amount_usd.isnot(None),
        PaymentHistory.amount_usd.notin_(valid_amounts),
        PaymentHistory.amount_usd > 0,
    ).order_by(PaymentHistory.created_at.desc()).limit(20).all()

    for p in odd_payments:
        user = db.session.get(User, p.user_id)
        anomalies.append({
            "type": "unusual_amount",
            "user_id": p.user_id,
            "user_email": user.email if user else None,
            "user_tier": user.subscription_tier if user else None,
            "amount_usd": p.amount_usd,
            "provider": p.provider,
            "date": p.created_at.isoformat() if p.created_at else None,
            "risk": "medium",
        })

    return jsonify({"anomalies": anomalies, "total": len(anomalies)})


# ── Chargeback Tracking ────────────────────────────────────────────────────────

@admin_bp.route("/fraud/chargebacks", methods=["GET"])
@require_permission(rbac.P_FRAUD_VIEW)
@rate_limit(requests_per_minute=20)
def fraud_chargebacks():
    """List users with recorded chargebacks, ordered by count descending."""
    users = (
        User.query
        .filter(User.chargeback_count > 0)
        .order_by(User.chargeback_count.desc())
        .limit(100)
        .all()
    )
    return jsonify({
        "chargebacks": [
            {
                "id": u.id,
                "email": u.email,
                "full_name": u.full_name,
                "tier": u.subscription_tier,
                "chargeback_count": u.chargeback_count,
                "created_at": u.created_at.isoformat() if u.created_at else None,
                "is_banned": u.is_banned,
                "is_suspended": u.is_suspended,
            }
            for u in users
        ],
        "total": len(users),
    })


@admin_bp.route("/fraud/chargebacks/<int:user_id>/increment", methods=["POST"])
@require_permission(rbac.P_BILLING_MANAGE)
@rate_limit(requests_per_minute=20)
def increment_chargeback(user_id):
    """Manually record a chargeback against a user."""
    admin_user = _get_current_user()
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    user.chargeback_count = (user.chargeback_count or 0) + 1
    audit = AdminAuditLog(
        admin_id=admin_user.id,
        action="chargeback_recorded",
        method="POST",
        path=f"/api/admin/fraud/chargebacks/{user_id}/increment",
        payload_json=json.dumps({"user_id": user_id, "new_count": user.chargeback_count}),
        ip_address=request.remote_addr,
    )
    db.session.add(audit)
    db.session.commit()
    return jsonify({"user_id": user_id, "chargeback_count": user.chargeback_count})


# ── Promo Codes ────────────────────────────────────────────────────────────────

@admin_bp.route("/promo-codes", methods=["GET"])
@require_permission(rbac.P_BILLING_VIEW)
@rate_limit(requests_per_minute=30)
def list_promo_codes():
    codes = PromoCode.query.order_by(PromoCode.created_at.desc()).all()
    return jsonify({"promo_codes": [c.to_dict() for c in codes]})


@admin_bp.route("/promo-codes", methods=["POST"])
@require_permission(rbac.P_BILLING_MANAGE)
@rate_limit(requests_per_minute=20)
def create_promo_code():
    admin_user = _get_current_user()
    data = request.get_json() or {}

    code = (data.get("code") or "").strip().upper()
    if not code:
        return jsonify({"error": "code is required"}), 400
    if PromoCode.query.filter_by(code=code).first():
        return jsonify({"error": "A code with this name already exists."}), 409

    discount_type = data.get("discount_type", "percent")
    if discount_type not in ("percent", "fixed", "trial_days"):
        return jsonify({"error": "discount_type must be percent, fixed, or trial_days"}), 400

    try:
        discount_value = float(data.get("discount_value", 0))
        if discount_value <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"error": "discount_value must be a positive number"}), 400

    valid_until = None
    if data.get("valid_until"):
        try:
            valid_until = datetime.fromisoformat(data["valid_until"].replace("Z", "+00:00"))
        except ValueError:
            return jsonify({"error": "Invalid valid_until format"}), 400

    promo = PromoCode(
        code=code,
        discount_type=discount_type,
        discount_value=discount_value,
        applicable_plans=data.get("applicable_plans") or None,
        max_uses=data.get("max_uses") or None,
        max_uses_per_user=int(data.get("max_uses_per_user") or 1),
        valid_until=valid_until,
        is_active=bool(data.get("is_active", True)),
        is_influencer_code=bool(data.get("is_influencer_code", False)),
        influencer_name=data.get("influencer_name") or None,
        label=data.get("label") or None,
        created_by_user_id=admin_user.id,
    )
    db.session.add(promo)
    db.session.commit()
    return jsonify({"promo_code": promo.to_dict()}), 201


@admin_bp.route("/promo-codes/<int:code_id>", methods=["PUT"])
@require_permission(rbac.P_BILLING_MANAGE)
@rate_limit(requests_per_minute=20)
def update_promo_code(code_id):
    promo = PromoCode.query.get(code_id)
    if not promo:
        return jsonify({"error": "Promo code not found"}), 404

    data = request.get_json() or {}
    if "is_active" in data:
        promo.is_active = bool(data["is_active"])
    if "discount_value" in data:
        promo.discount_value = float(data["discount_value"])
    if "discount_type" in data:
        promo.discount_type = data["discount_type"]
    if "max_uses" in data:
        promo.max_uses = data["max_uses"] or None
    if "valid_until" in data:
        if data["valid_until"]:
            try:
                promo.valid_until = datetime.fromisoformat(data["valid_until"].replace("Z", "+00:00"))
            except ValueError:
                return jsonify({"error": "Invalid valid_until format"}), 400
        else:
            promo.valid_until = None
    if "label" in data:
        promo.label = data["label"] or None
    if "influencer_name" in data:
        promo.influencer_name = data["influencer_name"] or None
    if "is_influencer_code" in data:
        promo.is_influencer_code = bool(data["is_influencer_code"])
    if "applicable_plans" in data:
        promo.applicable_plans = data["applicable_plans"] or None

    db.session.commit()
    return jsonify({"promo_code": promo.to_dict()})


@admin_bp.route("/promo-codes/<int:code_id>", methods=["DELETE"])
@require_permission(rbac.P_BILLING_MANAGE)
@rate_limit(requests_per_minute=20)
def delete_promo_code(code_id):
    promo = PromoCode.query.get(code_id)
    if not promo:
        return jsonify({"error": "Promo code not found"}), 404
    promo.is_active = False
    db.session.commit()
    return jsonify({"message": "Promo code deactivated."})


@admin_bp.route("/promo-codes/<int:code_id>/usage", methods=["GET"])
@require_permission(rbac.P_BILLING_VIEW)
@rate_limit(requests_per_minute=30)
def promo_code_usage(code_id):
    promo = PromoCode.query.get(code_id)
    if not promo:
        return jsonify({"error": "Promo code not found"}), 404
    usages = PromoCodeUsage.query.filter_by(promo_code_id=code_id).order_by(
        PromoCodeUsage.used_at.desc()
    ).limit(100).all()
    return jsonify({
        "code": promo.code,
        "uses_count": promo.uses_count,
        "usages": [u.to_dict() for u in usages],
    })


# ── Gift Subscription ──────────────────────────────────────────────────────────

@admin_bp.route("/users/<int:user_id>/gift-subscription", methods=["POST"])
@require_permission(rbac.P_USERS_GIFT)
@rate_limit(requests_per_minute=10)
def gift_subscription(user_id):
    """Grant a user a free subscription without payment."""
    admin_user = _get_current_user()
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json() or {}
    tier = data.get("tier", "pro")
    if tier not in ("pro", "enterprise"):
        return jsonify({"error": "tier must be pro or enterprise"}), 400

    duration_days = int(data.get("duration_days", 30))
    if duration_days < 1 or duration_days > 3650:
        return jsonify({"error": "duration_days must be between 1 and 3650"}), 400

    note = data.get("note") or ""

    now = datetime.utcnow()
    # Extend from existing expiry if subscription is still active
    base = user.subscription_expires if (
        user.subscription_expires and user.subscription_expires > now
        and user.subscription_tier == tier
    ) else now
    expires = base + timedelta(days=duration_days)

    user.subscription_tier = tier
    user.subscription_expires = expires
    user.subscription_expires_at = expires
    user.subscription_grace_until = expires + timedelta(days=7)

    renewal = SubscriptionRenewal(
        user_id=user.id,
        plan=tier,
        interval="gift",
        amount_usd=0,
        payment_id=f"gift-by-admin-{admin_user.id}",
        expires_at=expires,
    )
    db.session.add(renewal)

    history = PaymentHistory(
        user_id=user.id,
        provider="manual",
        payment_id=f"gift-admin-{admin_user.id}-{int(now.timestamp())}",
        plan=tier,
        billing_period="gift",
        amount_usd=0,
        currency="USD",
        status="confirmed",
        confirmed_at=now,
        metadata_={"gifted_by": admin_user.id, "note": note, "duration_days": duration_days},
    )
    db.session.add(history)

    audit = AdminAuditLog(
        admin_id=admin_user.id,
        action="gift_subscription",
        method="POST",
        path=f"/api/admin/users/{user_id}/gift-subscription",
        payload_json=json.dumps({"tier": tier, "duration_days": duration_days, "note": note}),
        ip_address=request.remote_addr,
    )
    db.session.add(audit)
    db.session.commit()

    try:
        from ..routes.notifications import create_notification
        create_notification(
            user.id, "payment_confirmed",
            f"🎁 {tier.capitalize()} Plan Gifted!",
            f"An admin has gifted you a {tier.capitalize()} subscription valid until {expires.strftime('%Y-%m-%d')}.",
        )
    except Exception:
        pass

    _log.info("[ADMIN] Gifted %s to user %d for %d days by admin %d", tier, user_id, duration_days, admin_user.id)
    return jsonify({
        "message": f"Gifted {tier} for {duration_days} days.",
        "user": user.to_dict(),
        "expires_at": expires.isoformat(),
    })


# ── Roles & Access (RBAC management — Super Admin only) ─────────────────────────

@admin_bp.route("/roles/matrix", methods=["GET"])
@require_permission(rbac.P_ROLES_MANAGE)
@rate_limit(requests_per_minute=30)
def roles_matrix():
    """Return the role→permission matrix plus the caller's own role/permissions."""
    me = _get_current_user()
    return jsonify({
        "roles": rbac.role_matrix(),
        "all_permissions": rbac.ALL_PERMISSIONS,
        "super_only": sorted(rbac.SUPER_ONLY),
        "me": {
            "role": rbac.resolve_admin_role(me),
            "permissions": sorted(rbac.get_permissions(me)),
        },
    })


@admin_bp.route("/roles/admins", methods=["GET"])
@require_permission(rbac.P_ROLES_MANAGE)
@rate_limit(requests_per_minute=30)
def list_admins():
    """List every account with admin access: explicit-role users plus the
    env-allowlist bootstrap super-admins (which have no DB role of their own)."""
    rows = []
    seen = set()

    # Users with an explicit admin_role column.
    for u in User.query.filter(User.admin_role.isnot(None)).all():
        role = rbac.resolve_admin_role(u)
        if not role:
            continue
        seen.add(u.id)
        rows.append({
            "id": u.id,
            "email": u.email,
            "full_name": u.full_name,
            "role": role,
            "source": "explicit",
            "is_bootstrap": bool(u.email and u.email.lower() in Config.ADMIN_EMAILS),
            "totp_enabled": bool(u.totp_enabled),
        })

    # Bootstrap super-admins from ADMIN_EMAILS that don't have an explicit role.
    for email in Config.ADMIN_EMAILS:
        u = User.query.filter(db.func.lower(User.email) == email).first()
        if u and u.id in seen:
            continue
        rows.append({
            "id": u.id if u else None,
            "email": email,
            "full_name": u.full_name if u else None,
            "role": rbac.SUPER_ADMIN,
            "source": "env_allowlist",
            "is_bootstrap": True,
            "totp_enabled": bool(u.totp_enabled) if u else False,
            "registered": u is not None,
        })

    rows.sort(key=lambda r: (r["role"] != rbac.SUPER_ADMIN, (r["email"] or "")))
    return jsonify({"admins": rows, "total": len(rows)})


@admin_bp.route("/roles/admins/<int:user_id>", methods=["PUT"])
@require_permission(rbac.P_ROLES_MANAGE)
@rate_limit(requests_per_minute=20)
def set_admin_role(user_id):
    """Grant, change, or revoke a user's admin role.

    Body: {"role": "support" | ... | null}. null/empty revokes admin access.
    Guardrails:
      • You cannot change your own role (prevents accidental self-lockout).
      • Env-allowlist (bootstrap) admins are managed via ADMIN_EMAILS, not here.
    """
    me = _get_current_user()
    if user_id == me.id:
        return jsonify({"error": "You cannot change your own admin role."}), 400

    target = User.query.get(user_id)
    if not target:
        return jsonify({"error": "User not found"}), 404

    if target.email and target.email.lower() in Config.ADMIN_EMAILS:
        return jsonify({
            "error": "This account is a bootstrap super-admin (in ADMIN_EMAILS). "
                     "Manage it via the ADMIN_EMAILS environment variable.",
        }), 400

    data = request.get_json() or {}
    new_role = (data.get("role") or "").strip().lower() or None
    if new_role is not None and new_role not in rbac.ROLES:
        return jsonify({"error": f"role must be one of: {', '.join(rbac.ROLES)} (or null to revoke)"}), 400

    # Defence-in-depth: only a super admin may grant super_admin (this endpoint is
    # already super-only via P_ROLES_MANAGE, but guard against future matrix edits).
    if new_role == rbac.SUPER_ADMIN and not rbac.is_super_admin(me):
        return jsonify({"error": "Only a super admin can grant the super_admin role."}), 403

    old_role = target.admin_role
    target.admin_role = new_role

    audit = AdminAuditLog(
        admin_id=me.id,
        action="set_admin_role",
        method="PUT",
        path=f"/api/admin/roles/admins/{user_id}",
        ip_address=request.remote_addr,
        severity="critical",
        target_type="user",
        target_id=str(user_id),
        old_value=old_role,
        new_value=new_role,
    )
    db.session.add(audit)
    db.session.commit()

    _log.info("[ADMIN] %s set admin_role of user %d: %s → %s", me.email, user_id, old_role, new_role)
    return jsonify({
        "message": (f"Role set to {rbac.ROLE_LABELS[new_role]}." if new_role else "Admin access revoked."),
        "user": {"id": target.id, "email": target.email, "role": new_role},
    })


@admin_bp.route("/roles/lookup", methods=["GET"])
@require_permission(rbac.P_ROLES_MANAGE)
@rate_limit(requests_per_minute=60)
def lookup_admin_candidate():
    """Look up a registered user by email so the invite UI can confirm the
    account exists and show who it is before a role is granted."""
    email = (request.args.get("email") or "").strip().lower()
    if not email:
        return jsonify({"error": "email is required"}), 400
    u = User.query.filter(db.func.lower(User.email) == email).first()
    if not u:
        return jsonify({"found": False, "error": "This email is not registered yet."}), 404
    return jsonify({
        "found": True,
        "user": {
            "id": u.id,
            "email": u.email,
            "full_name": u.full_name,
            "plan": (u.subscription_tier or "free").upper(),
            "auth_source": u.auth_provider or "email",
            "current_role": rbac.resolve_admin_role(u),
            "is_bootstrap": bool(u.email and u.email.lower() in Config.ADMIN_EMAILS),
        },
    })


@admin_bp.route("/roles/admins/invite", methods=["POST"])
@require_permission(rbac.P_ROLES_MANAGE)
@rate_limit(requests_per_minute=20)
def invite_admin_by_email():
    """Grant an admin role to an existing user, addressed by email.

    A role is never created for an unregistered email — the person must already
    have a Telegizer account. Env-allowlist (bootstrap) admins stay locked.
    Audit-logged the same way as set_admin_role.
    """
    me = _get_current_user()
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    new_role = (data.get("role") or "").strip().lower() or None

    if not email:
        return jsonify({"error": "email is required"}), 400
    if new_role is None or new_role not in rbac.ROLES:
        return jsonify({"error": f"role must be one of: {', '.join(rbac.ROLES)}"}), 400
    if new_role == rbac.SUPER_ADMIN and not rbac.is_super_admin(me):
        return jsonify({"error": "Only a super admin can grant the super_admin role."}), 403

    target = User.query.filter(db.func.lower(User.email) == email).first()
    if not target:
        return jsonify({"error": "This email is not registered yet."}), 404
    if target.id == me.id:
        return jsonify({"error": "You cannot change your own admin role."}), 400
    if target.email and target.email.lower() in Config.ADMIN_EMAILS:
        return jsonify({
            "error": "This account is a bootstrap super-admin (in ADMIN_EMAILS). "
                     "Manage it via the ADMIN_EMAILS environment variable.",
        }), 400

    old_role = target.admin_role
    target.admin_role = new_role

    db.session.add(AdminAuditLog(
        admin_id=me.id,
        action="invite_admin_role",
        method="POST",
        path="/api/admin/roles/admins/invite",
        ip_address=request.remote_addr,
        severity="critical",
        target_type="user",
        target_id=str(target.id),
        old_value=old_role,
        new_value=new_role,
    ))
    db.session.commit()

    _log.info("[ADMIN] %s invited user %s (%d) as admin: %s → %s",
              me.email, target.email, target.id, old_role, new_role)
    return jsonify({
        "message": f"{target.email} is now {rbac.ROLE_LABELS[new_role]}.",
        "user": {"id": target.id, "email": target.email, "full_name": target.full_name, "role": new_role},
    })


# ── Platform Configuration & Feature Flags (Super Admin only) ───────────────────

@admin_bp.route("/platform-config", methods=["GET"])
@require_permission(rbac.P_CONFIG_MANAGE)
@rate_limit(requests_per_minute=30)
def get_platform_config():
    from .. import platform_config as pc
    return jsonify(pc.admin_config())


@admin_bp.route("/platform-config/settings", methods=["PUT"])
@require_permission(rbac.P_CONFIG_MANAGE)
@rate_limit(requests_per_minute=20)
def update_platform_settings():
    """Bulk-update platform settings. Body: {"settings": {key: value, ...}}."""
    from .. import platform_config as pc
    me = _get_current_user()
    data = request.get_json() or {}
    updates = data.get("settings") or {}
    if not isinstance(updates, dict):
        return jsonify({"error": "settings must be an object"}), 400

    unknown = [k for k in updates if k not in pc.SETTING_KEYS]
    if unknown:
        return jsonify({"error": f"Unknown setting key(s): {', '.join(unknown)}"}), 400

    changed = []
    for key, value in updates.items():
        old = pc.get_setting(key)
        if old == value:
            continue
        pc.set_setting(key, value, user_id=me.id)
        changed.append(key)
        sev = "critical" if key == "maintenance_mode" else "notice"
        db.session.add(AdminAuditLog(
            admin_id=me.id, action="update_platform_setting", method="PUT",
            path="/api/admin/platform-config/settings", ip_address=request.remote_addr,
            severity=sev, target_type="setting", target_id=key,
            old_value=json.dumps(old)[:500] if old is not None else None,
            new_value=json.dumps(value)[:500] if value is not None else None,
        ))
    db.session.commit()
    return jsonify({"message": f"Updated {len(changed)} setting(s).", "changed": changed, **pc.admin_config()})


@admin_bp.route("/feature-flags/<key>", methods=["PUT"])
@require_permission(rbac.P_CONFIG_MANAGE)
@rate_limit(requests_per_minute=20)
def update_feature_flag(key):
    from .. import platform_config as pc
    me = _get_current_user()
    if key not in pc.FLAG_KEYS:
        return jsonify({"error": f"Unknown feature flag: {key}"}), 400
    data = request.get_json() or {}
    if "enabled" not in data:
        return jsonify({"error": "enabled is required"}), 400
    old = pc.is_feature_enabled(key)
    new = bool(data["enabled"])
    pc.set_feature_flag(key, new, user_id=me.id)
    db.session.add(AdminAuditLog(
        admin_id=me.id, action="update_feature_flag", method="PUT",
        path=f"/api/admin/feature-flags/{key}", ip_address=request.remote_addr,
        severity="notice", target_type="feature_flag", target_id=key,
        old_value=str(old), new_value=str(new),
    ))
    db.session.commit()
    return jsonify({"message": f"Feature '{key}' {'enabled' if new else 'disabled'}.", **pc.admin_config()})


# ── Secret & API-Key Vault (Super Admin only) ──────────────────────────────────

@admin_bp.route("/secrets", methods=["GET"])
@require_permission(rbac.P_SECRETS_MANAGE)
@rate_limit(requests_per_minute=30)
def list_secrets():
    """Masked status of every managed platform secret. Never returns plaintext."""
    from .. import secret_vault as sv
    return jsonify({"secrets": sv.status()})


@admin_bp.route("/secrets/<name>", methods=["PUT"])
@require_permission(rbac.P_SECRETS_MANAGE)
@rate_limit(requests_per_minute=20)
def set_secret(name):
    """Set/rotate a secret. Body: {"value": "..."}. The value is encrypted at rest
    and never echoed back or written to the audit log (only its masked hint)."""
    from .. import secret_vault as sv
    me = _get_current_user()
    if name not in sv.SECRET_NAMES:
        return jsonify({"error": "Unknown secret"}), 404
    data = request.get_json(silent=True) or {}
    value = data.get("value")
    try:
        masked = sv.set_secret(name, value, user_id=me.id)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    # Audit WITHOUT the secret value — only the masked hint is recorded.
    db.session.add(AdminAuditLog(
        admin_id=me.id, action="set_platform_secret", method="PUT",
        path=f"/api/admin/secrets/{name}", ip_address=request.remote_addr,
        severity="critical", target_type="secret", target_id=name,
        old_value=None, new_value=f"set ({masked})",
    ))
    db.session.commit()
    _log.info("[ADMIN] %s set platform secret %s", me.email, name)
    return jsonify({"message": f"{name} updated.", "secrets": sv.status()})


@admin_bp.route("/secrets/<name>", methods=["DELETE"])
@require_permission(rbac.P_SECRETS_MANAGE)
@rate_limit(requests_per_minute=20)
def delete_secret(name):
    """Clear the DB override so the secret falls back to the environment value."""
    from .. import secret_vault as sv
    me = _get_current_user()
    if name not in sv.SECRET_NAMES:
        return jsonify({"error": "Unknown secret"}), 404
    sv.clear_secret(name, user_id=me.id)
    db.session.add(AdminAuditLog(
        admin_id=me.id, action="clear_platform_secret", method="DELETE",
        path=f"/api/admin/secrets/{name}", ip_address=request.remote_addr,
        severity="critical", target_type="secret", target_id=name,
        old_value="db_override", new_value="env_fallback",
    ))
    db.session.commit()
    return jsonify({"message": f"{name} cleared — using environment value.", "secrets": sv.status()})


@admin_bp.route("/secrets/<name>/test", methods=["POST"])
@require_permission(rbac.P_SECRETS_MANAGE)
@rate_limit(requests_per_minute=10)
def test_secret(name):
    """Test connectivity for a secret. Body may include {"value": "..."} to test a
    candidate before saving; otherwise the stored/resolved value is used."""
    from .. import secret_vault as sv
    if name not in sv.SECRET_NAMES:
        return jsonify({"error": "Unknown secret"}), 404
    data = request.get_json(silent=True) or {}
    ok, message = sv.test_secret(name, value=data.get("value"))
    return jsonify({"ok": ok, "message": message})


# ── AI Management (ai.manage) ──────────────────────────────────────────────────

@admin_bp.route("/ai-config", methods=["GET"])
@require_permission(rbac.P_AI_MANAGE)
@rate_limit(requests_per_minute=30)
def get_ai_config():
    """AI settings + live usage analytics (today's platform spend, top token users)."""
    from .. import ai_config
    from .. import platform_config as pc
    from datetime import date

    spend_today = 0.0
    try:
        import redis as _redis
        r = _redis.from_url(Config.REDIS_URL or "redis://localhost:6379/0", socket_timeout=2)
        spend_today = round(float(r.get(f"platform_ai_spend:{date.today().isoformat()}") or 0), 4)
    except Exception:
        spend_today = None  # Redis unavailable

    top = (
        User.query.filter(User.workspace_ai_tokens_today > 0)
        .order_by(User.workspace_ai_tokens_today.desc()).limit(10).all()
    )
    cap = ai_config.daily_spend_cap()

    # Provider balances + presets (best-effort — never block the settings page).
    balances, presets, budget = [], [], {}
    try:
        from .. import ai_providers
        balances = ai_providers.get_balances()
        presets = ai_providers.MODEL_PRESETS
        budget = ai_providers.budget_status()
    except Exception as e:
        import logging
        logging.getLogger("admin").warning("ai_providers snapshot failed: %s", e)

    return jsonify({
        "settings": ai_config.all_settings(),
        "ai_features_enabled": pc.is_feature_enabled("ai_features_enabled"),
        "presets": presets,
        "balances": balances,
        "budget": budget,
        "usage": {
            "spend_today_usd": spend_today,
            "daily_cap_usd": cap,
            "spend_pct": (round(spend_today / cap * 100, 1) if (spend_today is not None and cap) else None),
            "top_token_users": [
                {"id": u.id, "email": u.email, "tier": u.subscription_tier,
                 "tokens_today": u.workspace_ai_tokens_today or 0}
                for u in top
            ],
        },
    })


@admin_bp.route("/ai-config", methods=["PUT"])
@require_permission(rbac.P_AI_MANAGE)
@rate_limit(requests_per_minute=20)
def update_ai_config():
    """Update AI settings. Body: {"settings": {key: value, ...}}."""
    from .. import ai_config
    me = _get_current_user()
    updates = (request.get_json() or {}).get("settings") or {}
    unknown = [k for k in updates if k not in ai_config.AI_KEYS]
    if unknown:
        return jsonify({"error": f"Unknown AI setting(s): {', '.join(unknown)}"}), 400
    changed = []
    for key, value in updates.items():
        old = ai_config.get(key)
        try:
            new = ai_config.set_value(key, value, user_id=me.id)
        except (ValueError, TypeError):
            return jsonify({"error": f"Invalid value for {key}"}), 400
        if old != new:
            changed.append(key)
            db.session.add(AdminAuditLog(
                admin_id=me.id, action="update_ai_config", method="PUT",
                path="/api/admin/ai-config", ip_address=request.remote_addr,
                severity="notice", target_type="ai_setting", target_id=key,
                old_value=str(old), new_value=str(new),
            ))
    db.session.commit()
    return jsonify({"message": f"Updated {len(changed)} setting(s).", "settings": ai_config.all_settings()})


# ── AI Usage ledger analytics (ai.manage) ─────────────────────────────────────

@admin_bp.route("/ai-usage", methods=["GET"])
@require_permission(rbac.P_AI_MANAGE)
@rate_limit(requests_per_minute=30)
def get_ai_usage():
    """Token/cost analytics from the AITokenUsage ledger.

    Query params: range=today|7d|30d|1y|all (default 30d). Returns totals, a daily
    series, and breakdowns by feature / model / provider / user / group, plus
    top-N expensive lists — so the admin can trace User→Group→Bot→Feature→Model→
    Tokens→Cost.
    """
    from ..models import AITokenUsage
    from sqlalchemy import func
    from datetime import datetime, timedelta

    rng = (request.args.get("range") or "30d").lower()
    now = datetime.utcnow()
    since = None
    if rng == "today":
        since = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif rng == "7d":
        since = now - timedelta(days=7)
    elif rng == "1y":
        since = now - timedelta(days=365)
    elif rng == "all":
        since = None
    else:
        rng = "30d"
        since = now - timedelta(days=30)

    cols = (
        func.coalesce(func.sum(AITokenUsage.input_tokens), 0),
        func.coalesce(func.sum(AITokenUsage.output_tokens), 0),
        func.coalesce(func.sum(AITokenUsage.total_tokens), 0),
        func.coalesce(func.sum(AITokenUsage.cost_usd), 0),
        func.count(AITokenUsage.id),
    )

    def _filtered_agg(query):
        if since is not None:
            query = query.filter(AITokenUsage.created_at >= since)
        return query

    tin, tout, ttot, tcost, tcalls = _filtered_agg(db.session.query(*cols)).one()
    totals = {
        "input_tokens": int(tin or 0), "output_tokens": int(tout or 0),
        "total_tokens": int(ttot or 0), "cost_usd": round(float(tcost or 0), 4),
        "calls": int(tcalls or 0),
    }

    def _group(col, limit=None, label="key"):
        q = db.session.query(
            col,
            func.coalesce(func.sum(AITokenUsage.total_tokens), 0),
            func.coalesce(func.sum(AITokenUsage.cost_usd), 0),
            func.count(AITokenUsage.id),
        )
        if since is not None:
            q = q.filter(AITokenUsage.created_at >= since)
        q = q.filter(col.isnot(None)).group_by(col).order_by(func.sum(AITokenUsage.cost_usd).desc())
        if limit:
            q = q.limit(limit)
        return [
            {label: row[0], "total_tokens": int(row[1] or 0),
             "cost_usd": round(float(row[2] or 0), 4), "calls": int(row[3] or 0)}
            for row in q.all()
        ]

    # Daily series (cost + tokens).
    dq = db.session.query(
        func.date(AITokenUsage.created_at),
        func.coalesce(func.sum(AITokenUsage.cost_usd), 0),
        func.coalesce(func.sum(AITokenUsage.total_tokens), 0),
    )
    if since is not None:
        dq = dq.filter(AITokenUsage.created_at >= since)
    dq = dq.group_by(func.date(AITokenUsage.created_at)).order_by(func.date(AITokenUsage.created_at))
    daily = [
        {"date": str(d), "cost_usd": round(float(c or 0), 4), "total_tokens": int(t or 0)}
        for d, c, t in dq.all()
    ]

    # by_user — attach email for cost-by-email.
    by_user = _group(AITokenUsage.user_ref, limit=15, label="user_ref")
    if by_user:
        emap = {}
        urefs = [u["user_ref"] for u in by_user]
        try:
            erows = db.session.query(AITokenUsage.user_ref, func.max(AITokenUsage.email)).filter(
                AITokenUsage.user_ref.in_(urefs)).group_by(AITokenUsage.user_ref).all()
            emap = {r[0]: r[1] for r in erows}
        except Exception:
            emap = {}
        for u in by_user:
            u["email"] = emap.get(u["user_ref"])

    return jsonify({
        "range": rng,
        "totals": totals,
        "daily": daily,
        "by_feature": _group(AITokenUsage.feature, label="feature"),
        "by_model": _group(AITokenUsage.model, limit=15, label="model"),
        "by_provider": _group(AITokenUsage.provider, label="provider"),
        "by_user": by_user,
        "by_group": _group(AITokenUsage.group_ref, limit=15, label="group_ref"),
    })


# ── Pricing (Super Admin only) ─────────────────────────────────────────────────

@admin_bp.route("/pricing", methods=["GET"])
@require_permission(rbac.P_PRICING_MANAGE)
@rate_limit(requests_per_minute=30)
def get_pricing():
    from .. import billing_config
    return jsonify({"prices": billing_config.get_tier_prices(), "plans": billing_config.get_plans()})


@admin_bp.route("/pricing", methods=["PUT"])
@require_permission(rbac.P_PRICING_MANAGE)
@rate_limit(requests_per_minute=20)
def update_pricing():
    """Update one or more tier prices (USD). Body: {"prices": {"pro": {"monthly": 9, ...}}}.
    All consumers (checkout, webhook verification, /plans) read the same resolver,
    so display, charge and verification stay consistent."""
    from .. import billing_config
    me = _get_current_user()
    prices = (request.get_json() or {}).get("prices") or {}
    changed = []
    for tier, periods in prices.items():
        if tier not in billing_config.TIERS or not isinstance(periods, dict):
            return jsonify({"error": f"Invalid tier: {tier}"}), 400
        for period, usd in periods.items():
            if period not in billing_config.PERIODS:
                return jsonify({"error": f"Invalid period: {period}"}), 400
            old = billing_config.get_tier_prices().get(tier, {}).get(period)
            try:
                new = billing_config.set_tier_price(tier, period, usd, user_id=me.id)
            except (ValueError, TypeError):
                return jsonify({"error": f"Invalid price for {tier}/{period}"}), 400
            if old != new:
                changed.append(f"{tier}/{period}")
                db.session.add(AdminAuditLog(
                    admin_id=me.id, action="update_pricing", method="PUT",
                    path="/api/admin/pricing", ip_address=request.remote_addr,
                    severity="critical", target_type="price", target_id=f"{tier}/{period}",
                    old_value=str(old), new_value=str(new),
                ))
    db.session.commit()
    return jsonify({
        "message": f"Updated {len(changed)} price(s).", "changed": changed,
        "prices": billing_config.get_tier_prices(), "plans": billing_config.get_plans(),
    })


# ── Campaigns (platform-wide moderation view) ──────────────────────────────────

_ADMIN_CAMPAIGN_ACTIONS = {"pause", "close", "archive"}  # safe stop-actions (no TG post)


@admin_bp.route("/campaigns", methods=["GET"])
@require_permission(rbac.P_CAMPAIGNS_VIEW)
@rate_limit(requests_per_minute=30)
def admin_list_campaigns():
    """Campaign oversight: filterable list + scope/status overview counts.

    Global admin is an OVERSIGHT surface — campaigns are owned/managed inside
    their group (official = platform/official campaigns with a telegram_group_id;
    custom = customer group campaigns with a Group.id). Filters: scope
    (official|custom), status, owner (email substring), group (group ref).
    """
    from ..models import EngagementCampaign, EngagementSubmission
    from sqlalchemy import or_, cast, String
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 100)
    status = request.args.get("status", "")
    scope = (request.args.get("scope", "") or "").lower()
    owner = (request.args.get("owner", "") or "").strip()
    group = (request.args.get("group", "") or "").strip()

    q = EngagementCampaign.query
    if status:
        q = q.filter(EngagementCampaign.status == status)
    if scope == "official":
        q = q.filter(EngagementCampaign.telegram_group_id.isnot(None))
    elif scope == "custom":
        q = q.filter(EngagementCampaign.telegram_group_id.is_(None))
    if owner:
        owner_ids_match = [u.id for u in User.query.filter(User.email.ilike(f"%{owner}%")).limit(200).all()]
        q = q.filter(EngagementCampaign.owner_user_id.in_(owner_ids_match or [-1]))
    if group:
        q = q.filter(or_(
            EngagementCampaign.telegram_group_id == group,
            cast(EngagementCampaign.group_id, String) == group,
        ))
    q = q.order_by(EngagementCampaign.created_at.desc())
    paginated = q.paginate(page=page, per_page=per_page, error_out=False)

    # ── Overview counts (whole table — oversight summary, not just this page) ──
    overview = {"by_status": {}, "by_scope": {"official": 0, "custom": 0}, "total": 0}
    try:
        for st, cnt in (db.session.query(EngagementCampaign.status, db.func.count(EngagementCampaign.id))
                        .group_by(EngagementCampaign.status).all()):
            overview["by_status"][st or "unknown"] = int(cnt)
            overview["total"] += int(cnt)
        overview["by_scope"]["official"] = EngagementCampaign.query.filter(
            EngagementCampaign.telegram_group_id.isnot(None)).count()
        overview["by_scope"]["custom"] = overview["total"] - overview["by_scope"]["official"]
    except Exception:
        pass

    owner_ids = {c.owner_user_id for c in paginated.items if c.owner_user_id}
    owners = {u.id: u for u in User.query.filter(User.id.in_(owner_ids)).all()} if owner_ids else {}

    # One grouped query for submission counts on this page.
    ids = [c.id for c in paginated.items]
    counts = {}
    if ids:
        for cid, cnt in (
            db.session.query(EngagementSubmission.campaign_id, db.func.count(EngagementSubmission.id))
            .filter(EngagementSubmission.campaign_id.in_(ids))
            .group_by(EngagementSubmission.campaign_id).all()
        ):
            counts[cid] = cnt

    rows = []
    for c in paginated.items:
        owner = owners.get(c.owner_user_id)
        rows.append({
            "id": c.id,
            "title": c.title,
            "type": c.type,
            "status": c.status,
            "scope": "official" if c.telegram_group_id else "custom",
            "group_ref": c.telegram_group_id or (str(c.group_id) if c.group_id else None),
            "owner_email": owner.email if owner else None,
            "owner_tier": owner.subscription_tier if owner else None,
            "reward_xp": c.reward_xp,
            "submission_count": counts.get(c.id, 0),
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "ends_at": c.ends_at.isoformat() if c.ends_at else None,
        })

    return jsonify({"campaigns": rows, "total": paginated.total, "pages": paginated.pages,
                    "page": page, "overview": overview})


@admin_bp.route("/campaigns/<int:campaign_id>/action", methods=["POST"])
@require_permission(rbac.P_CAMPAIGNS_MANAGE)
@rate_limit(requests_per_minute=20)
def admin_campaign_action(campaign_id):
    """Apply a moderation stop-action (pause/close/archive) to any campaign."""
    from ..models import EngagementCampaign
    from .. import engagement as eng
    me = _get_current_user()
    c = EngagementCampaign.query.get(campaign_id)
    if not c:
        return jsonify({"error": "Campaign not found"}), 404
    action = (request.get_json() or {}).get("action")
    if action not in _ADMIN_CAMPAIGN_ACTIONS:
        return jsonify({"error": f"action must be one of: {', '.join(sorted(_ADMIN_CAMPAIGN_ACTIONS))}"}), 400
    old_status = c.status
    try:
        eng.update_campaign(c, {"action": action}, user=me)
    except Exception as e:
        return jsonify({"error": str(e)[:200]}), 400
    db.session.add(AdminAuditLog(
        admin_id=me.id, action="campaign_moderation", method="POST",
        path=f"/api/admin/campaigns/{campaign_id}/action", ip_address=request.remote_addr,
        severity="notice", target_type="campaign", target_id=str(campaign_id),
        old_value=old_status, new_value=c.status,
    ))
    db.session.commit()
    return jsonify({"message": f"Campaign {action}d.", "id": c.id, "status": c.status})


@admin_bp.route("/campaigns/<int:campaign_id>/submissions", methods=["GET"])
@require_permission(rbac.P_CAMPAIGNS_VIEW)
@rate_limit(requests_per_minute=30)
def admin_campaign_submissions(campaign_id):
    from ..models import EngagementCampaign
    from .. import engagement as eng
    c = EngagementCampaign.query.get(campaign_id)
    if not c:
        return jsonify({"error": "Campaign not found"}), 404
    status = request.args.get("status") or None
    subs = eng.list_submissions(c, status=status, limit=500)
    return jsonify({"submissions": [s.to_dict() for s in subs], "total": len(subs)})


# ── Support & Compliance ───────────────────────────────────────────────────────

@admin_bp.route("/compliance/requests", methods=["GET"])
@require_permission(rbac.P_MODERATION_VIEW)
@rate_limit(requests_per_minute=30)
def admin_compliance_requests():
    """GDPR export/delete request queue."""
    from ..models import ComplianceRequest
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 100)
    status = request.args.get("status", "")
    req_type = request.args.get("type", "")

    q = ComplianceRequest.query
    if status:
        q = q.filter(ComplianceRequest.status == status)
    if req_type in ("export", "delete"):
        q = q.filter(ComplianceRequest.request_type == req_type)
    q = q.order_by(ComplianceRequest.requested_at.desc())
    paginated = q.paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        "requests": [r.to_dict() for r in paginated.items],
        "total": paginated.total, "pages": paginated.pages, "page": page,
    })


@admin_bp.route("/compliance/requests/<int:req_id>/resolve", methods=["POST"])
@require_permission(rbac.P_MODERATION_MANAGE)
@rate_limit(requests_per_minute=20)
def admin_resolve_compliance(req_id):
    from ..models import ComplianceRequest
    me = _get_current_user()
    req = ComplianceRequest.query.get(req_id)
    if not req:
        return jsonify({"error": "Request not found"}), 404
    data = request.get_json() or {}
    new_status = data.get("status", "completed")
    if new_status not in ("completed", "cancelled", "pending"):
        return jsonify({"error": "status must be completed, cancelled, or pending"}), 400
    req.status = new_status
    req.handled_by = me.id
    req.handled_at = datetime.utcnow()
    if data.get("note"):
        req.note = data["note"]
    db.session.add(AdminAuditLog(
        admin_id=me.id, action="resolve_compliance_request", method="POST",
        path=f"/api/admin/compliance/requests/{req_id}/resolve", ip_address=request.remote_addr,
        severity="notice", target_type="compliance_request", target_id=str(req_id),
        new_value=new_status,
    ))
    db.session.commit()
    return jsonify({"message": f"Request marked {new_status}.", "request": req.to_dict()})


@admin_bp.route("/compliance/tos", methods=["GET"])
@require_permission(rbac.P_MODERATION_VIEW)
@rate_limit(requests_per_minute=30)
def admin_compliance_tos():
    """Current ToS/privacy versions + acceptance stats."""
    from .. import platform_config as pc
    tos_version = pc.get_setting("tos_version")
    privacy_version = pc.get_setting("privacy_version")
    total = User.query.filter(User.deleted_at.is_(None)).count()
    on_current = User.query.filter(
        User.deleted_at.is_(None), User.tos_version_accepted == tos_version
    ).count()
    return jsonify({
        "tos_version": tos_version,
        "privacy_version": privacy_version,
        "users_total": total,
        "users_on_current_tos": on_current,
        "users_outdated_tos": max(0, total - on_current),
        "note": "Edit versions in Configuration (compliance category). Re-acceptance enforcement is not automated.",
    })


# ── System Health & DevOps (health.view) ───────────────────────────────────────

def _describe_schedule(sched):
    """Human-readable label for a Celery beat schedule entry."""
    try:
        from celery.schedules import crontab
        if isinstance(sched, crontab):
            return f"cron {sched._orig_minute} {sched._orig_hour} * * {sched._orig_day_of_week}"
        secs = float(sched)
        if secs % 3600 == 0:
            return f"every {int(secs // 3600)}h"
        if secs % 60 == 0:
            return f"every {int(secs // 60)}m"
        return f"every {int(secs)}s"
    except Exception:
        return str(sched)


@admin_bp.route("/system", methods=["GET"])
@require_permission(rbac.P_HEALTH_VIEW)
@rate_limit(requests_per_minute=20)
def admin_system():
    """Consolidated DevOps snapshot: version, service health, environment checklist,
    scheduled jobs and 24h error counts. No secret values are ever returned."""
    import os
    import platform as _platform
    from .. import secret_vault as sv

    now = datetime.utcnow()

    # ── Version / runtime ──
    runtime = {
        "app_version": Config.VERSION,
        "python": _platform.python_version(),
        "platform": _platform.system(),
        "webhook_mode": bool(getattr(Config, "CUSTOM_BOT_WEBHOOK_BASE_URL", "")),
        "enforce_admin_2fa": bool(getattr(Config, "ENFORCE_ADMIN_2FA", False)),
        "generated_at": now.isoformat(),
    }

    # ── Services ──
    services = {}
    try:
        db.session.execute(db.text("SELECT 1"))
        services["database"] = "ok"
    except Exception as e:
        services["database"] = f"error: {str(e)[:60]}"

    redis_client = None
    try:
        import redis as _redis
        redis_client = _redis.from_url(Config.REDIS_URL or "redis://localhost:6379/0", socket_timeout=2)
        redis_client.ping()
        services["redis"] = "ok"
    except Exception as e:
        services["redis"] = f"error: {str(e)[:60]}"
        redis_client = None

    # Celery heartbeat + queue depth (best-effort).
    queue_depth = None
    if redis_client is not None:
        try:
            services["celery"] = "ok" if redis_client.get("celery:heartbeat") else "unknown"
        except Exception:
            services["celery"] = "unknown"
        try:
            queue_depth = redis_client.llen("celery")  # default queue key
        except Exception:
            queue_depth = None
    else:
        services["celery"] = "unknown"

    # ── Environment checklist (booleans only — never values) ──
    def _set(name):
        return bool(sv.get_secret(name))
    environment = {
        "telegram_bot_token": _set("TELEGRAM_BOT_TOKEN"),
        "echo_bot_token": _set("ECHO_BOT_TOKEN"),
        "platform_ai_key": _set("PLATFORM_OPENROUTER_API_KEY") or _set("OPENAI_API_KEY"),
        "email_provider": bool(getattr(Config, "EMAIL_PROVIDER", "")),
        "nowpayments": _set("NOWPAYMENTS_API_KEY"),
        "lemonsqueezy": _set("LS_API_KEY"),
        "google_oauth": _set("GOOGLE_CLIENT_SECRET"),
    }

    # ── Scheduled jobs (from the Celery beat schedule) ──
    jobs = []
    try:
        from ..scheduler import celery as _celery
        for name, cfg in (_celery.conf.beat_schedule or {}).items():
            jobs.append({
                "name": name,
                "task": (cfg.get("task") or "").replace("backend.scheduler.", ""),
                "schedule": _describe_schedule(cfg.get("schedule")),
            })
        jobs.sort(key=lambda j: j["name"])
    except Exception as e:
        _log.warning("system: beat schedule read failed: %s", e)

    # ── 24h errors ──
    since = now - timedelta(hours=24)
    errors = {"bot_health_24h": 0, "critical_admin_actions_24h": 0}
    try:
        errors["bot_health_24h"] = BotHealthEvent.query.filter(
            BotHealthEvent.created_at >= since,
            db.or_(BotHealthEvent.severity != "info", BotHealthEvent.severity.is_(None)),
        ).count()
    except Exception:
        pass
    try:
        # Count only UNRESOLVED critical actions — a resolved one is handled and
        # must not keep inflating the "needs attention" badge.
        errors["critical_admin_actions_24h"] = AdminAuditLog.query.filter(
            AdminAuditLog.created_at >= since,
            AdminAuditLog.severity == "critical",
            AdminAuditLog.resolved_at.is_(None),
        ).count()
        errors["critical_admin_actions_open"] = AdminAuditLog.query.filter(
            AdminAuditLog.severity == "critical",
            AdminAuditLog.resolved_at.is_(None),
        ).count()
    except Exception:
        pass

    overall = "ok" if all(v == "ok" for v in services.values()) else (
        "degraded" if any(str(v).startswith("error") for v in services.values()) else "ok"
    )

    return jsonify({
        "status": overall,
        "runtime": runtime,
        "services": services,
        "queue_depth": queue_depth,
        "environment": environment,
        "scheduled_jobs": jobs,
        "errors": errors,
    })
