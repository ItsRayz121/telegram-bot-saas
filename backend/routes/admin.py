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
    PromoCode, PromoCodeUsage,
)
from ..config import Config
from ..middleware.rate_limit import rate_limit

_log = logging.getLogger("admin")

admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")


def _get_current_user():
    user_id = get_jwt_identity()
    return User.query.get(int(user_id))


def admin_required(f):
    @wraps(f)
    @jwt_required()
    def decorated(*args, **kwargs):
        user = _get_current_user()
        if not user:
            _log.warning("admin_required: JWT resolved but user not found — route=%s", request.path)
            return jsonify({"error": "User not found"}), 404

        if user.email.lower() not in Config.ADMIN_EMAILS:
            _log.warning(
                "admin_required: access denied — email=%s route=%s reason=not_in_allowlist",
                user.email, request.path,
            )
            return jsonify({"error": "Admin access required", "reason": "not_in_allowlist"}), 403

        if Config.ENFORCE_ADMIN_2FA and not user.totp_enabled:
            _log.warning(
                "admin_required: access denied — email=%s route=%s reason=2fa_required",
                user.email, request.path,
            )
            return jsonify({
                "error": "Admin accounts must have 2FA enabled",
                "reason": "2fa_required",
            }), 403

        _log.info("admin_required: access granted — email=%s route=%s method=%s", user.email, request.path, request.method)

        try:
            body = request.get_json(silent=True) or {}
            sanitised = {k: v for k, v in body.items() if k not in {"password", "token", "api_key"}}
            log = AdminAuditLog(
                admin_id=user.id,
                action=request.endpoint or "",
                method=request.method,
                path=request.path,
                payload_json=json.dumps(sanitised) if sanitised else None,
                ip_address=request.remote_addr,
            )
            db.session.add(log)
            db.session.commit()
        except Exception:
            db.session.rollback()
        return f(*args, **kwargs)
    return decorated


# ── User Management ────────────────────────────────────────────────────────────

@admin_bp.route("/users", methods=["GET"])
@admin_required
@rate_limit(requests_per_minute=60)
def list_users():
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 100)
    search = request.args.get("search", "")
    tier = request.args.get("tier", "")
    status = request.args.get("status", "")

    query = User.query
    if search:
        query = query.filter(
            (User.email.ilike(f"%{search}%")) |
            (User.full_name.ilike(f"%{search}%"))
        )
    if tier in ("free", "pro", "enterprise"):
        query = query.filter(User.subscription_tier == tier)
    if status == "banned":
        query = query.filter(User.is_banned == True)
    elif status == "active":
        query = query.filter(User.is_banned == False)
    elif status == "suspicious":
        query = query.filter(User.is_suspicious == True)

    query = query.order_by(User.created_at.desc())
    paginated = query.paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        "users": [u.to_dict() for u in paginated.items],
        "total": paginated.total,
        "pages": paginated.pages,
        "page": page,
        "per_page": per_page,
    })


@admin_bp.route("/users/<int:user_id>", methods=["GET"])
@admin_required
@rate_limit(requests_per_minute=60)
def get_user(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    user_data = user.to_dict()
    user_data["bots"] = [b.to_dict() for b in user.bots]
    # Recent payment history
    payments = PaymentHistory.query.filter_by(user_id=user_id)\
        .order_by(PaymentHistory.created_at.desc()).limit(10).all()
    user_data["recent_payments"] = [p.to_dict() for p in payments]
    # Recent suspicious activity
    suspicious = SuspiciousActivity.query.filter_by(user_id=user_id)\
        .order_by(SuspiciousActivity.created_at.desc()).limit(5).all()
    user_data["suspicious_events"] = [s.to_dict() for s in suspicious]
    return jsonify({"user": user_data})


@admin_bp.route("/users/<int:user_id>/subscription", methods=["PUT"])
@admin_required
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


@admin_bp.route("/users/<int:user_id>/ban", methods=["POST"])
@admin_required
@rate_limit(requests_per_minute=30)
def ban_user(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    if user.email in Config.ADMIN_EMAILS:
        return jsonify({"error": "Cannot ban an admin"}), 403
    data = request.get_json() or {}
    user.is_banned = True
    user.ban_reason = data.get("reason", "Violation of terms of service")
    db.session.commit()
    return jsonify({"message": "User banned", "user": user.to_dict()})


@admin_bp.route("/users/<int:user_id>/unban", methods=["POST"])
@admin_required
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
@admin_required
@rate_limit(requests_per_minute=10)
def delete_user(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    if user.email in Config.ADMIN_EMAILS:
        return jsonify({"error": "Cannot delete an admin"}), 403
    db.session.delete(user)
    db.session.commit()
    return jsonify({"message": "User deleted"})


# ── Platform Stats ─────────────────────────────────────────────────────────────

@admin_bp.route("/stats", methods=["GET"])
@admin_required
@rate_limit(requests_per_minute=30)
def get_stats():
    total_users = User.query.count()
    total_bots = Bot.query.count()
    total_groups = Group.query.count()
    total_members = Member.query.count()
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
            "total_members": total_members,
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
@admin_required
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
@admin_required
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
@admin_required
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
@admin_required
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
@admin_required
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
@admin_required
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
@admin_required
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
@admin_required
@rate_limit(requests_per_minute=30)
def admin_list_telegram_groups():
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 200)
    search = request.args.get("search", "")
    status = request.args.get("status", "")

    query = TelegramGroup.query
    if search:
        query = query.filter(
            TelegramGroup.title.ilike(f"%{search}%") |
            TelegramGroup.telegram_group_id.ilike(f"%{search}%")
        )
    if status:
        query = query.filter(TelegramGroup.bot_status == status)
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
@admin_required
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
@admin_required
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
@admin_required
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
@admin_required
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


@admin_bp.route("/telegram-groups/<group_id>/events", methods=["GET"])
@admin_required
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


# ── Custom Bots ────────────────────────────────────────────────────────────────

@admin_bp.route("/custom-bots", methods=["GET"])
@admin_required
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
@admin_required
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
            .filter(BotHealthEvent.created_at >= since_24h)
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
@admin_required
@rate_limit(requests_per_minute=30)
def admin_bot_health():
    """Health overview: official bot + paginated custom bots with 24h error counts.

    Errors come from the bot_health_events table (populated as failures happen).
    Liveness is verified on demand via POST /bot-health/ping.
    """
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 25, type=int), 100)
    since = datetime.utcnow() - timedelta(hours=24)

    # One grouped query → {ref: count} for all custom-bot errors in the window.
    counts_by_ref = {}
    try:
        rows = (
            db.session.query(BotHealthEvent.ref, db.func.count(BotHealthEvent.id))
            .filter(BotHealthEvent.created_at >= since, BotHealthEvent.scope == "custom")
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
        ).count()
        last = (
            BotHealthEvent.query.filter(BotHealthEvent.scope.in_(["official", "ai"]))
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
            BotHealthEvent.created_at >= since
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
@admin_required
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
@admin_required
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
@admin_required
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
@admin_required
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
@admin_required
@rate_limit(requests_per_minute=4)
def admin_ai_selftest():
    """Actually exercise each AI path with the configured platform key and report
    Working / Broken / Not Connected. This turns the static availability audit
    into a real end-to-end test runnable in any environment that has a key."""
    platform_key = getattr(Config, "PLATFORM_OPENROUTER_API_KEY", None)
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
@admin_required
@rate_limit(requests_per_minute=10)
def admin_disable_custom_bot(bot_id):
    bot = CustomBot.query.get(bot_id)
    if not bot:
        return jsonify({"error": "Bot not found"}), 404
    bot.status = "inactive"
    db.session.commit()
    return jsonify({"message": "Custom bot disabled", "bot": bot.to_dict()})


# ── Directory Moderation ───────────────────────────────────────────────────────

@admin_bp.route("/directory/pending", methods=["GET"])
@admin_required
@rate_limit(requests_per_minute=60)
def list_pending_directory():
    pending = DirectoryListing.query.filter_by(moderation_status="pending").order_by(
        DirectoryListing.created_at.asc()
    ).all()
    return jsonify({"listings": [l.to_dict(include_contact=True) for l in pending], "total": len(pending)})


@admin_bp.route("/directory", methods=["GET"])
@admin_required
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
@admin_required
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
@admin_required
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
@admin_required
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
@admin_required
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
@admin_required
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


# ── Reported Messages ──────────────────────────────────────────────────────────

@admin_bp.route("/reports", methods=["GET"])
@admin_required
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
@admin_required
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
@admin_required
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


# ── Fraud Detection ────────────────────────────────────────────────────────────

@admin_bp.route("/fraud/clusters", methods=["GET"])
@admin_required
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
@admin_required
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
@admin_required
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
@admin_required
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
@admin_required
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
@admin_required
@rate_limit(requests_per_minute=30)
def list_promo_codes():
    codes = PromoCode.query.order_by(PromoCode.created_at.desc()).all()
    return jsonify({"promo_codes": [c.to_dict() for c in codes]})


@admin_bp.route("/promo-codes", methods=["POST"])
@admin_required
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
@admin_required
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
@admin_required
@rate_limit(requests_per_minute=20)
def delete_promo_code(code_id):
    promo = PromoCode.query.get(code_id)
    if not promo:
        return jsonify({"error": "Promo code not found"}), 404
    promo.is_active = False
    db.session.commit()
    return jsonify({"message": "Promo code deactivated."})


@admin_bp.route("/promo-codes/<int:code_id>/usage", methods=["GET"])
@admin_required
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
@admin_required
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
