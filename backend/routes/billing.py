import hashlib
import hmac
import json
import logging
import requests
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy.exc import IntegrityError
from ..models import db, User, ProcessedPayment, PaymentHistory, PendingInvoice
from ..config import Config
from ..middleware.rate_limit import rate_limit
from ..notifications import send_subscription_confirmation, send_subscription_cancelled

logger = logging.getLogger(__name__)

billing_bp = Blueprint("billing", __name__, url_prefix="/api/billing")

_TIER_DURATION_MONTHLY = 30
_TIER_DURATION_ANNUAL = 365
_TIER_PRICES_USD = {"pro": {"monthly": 9, "annual": 90}, "enterprise": {"monthly": 49, "annual": 470}}


def _get_current_user():
    return User.query.get(int(get_jwt_identity()))


def _admin_upgrade(user, tier):
    user.subscription_tier = tier
    user.subscription_expires = None
    db.session.commit()
    return jsonify({"admin_upgrade": True, "tier": tier, "message": f"Plan switched to {tier}"})


def _activate_subscription(user, tier, provider="unknown", payment_id=None,
                           amount_usd=None, currency="USD", billing_period="monthly"):
    user.subscription_tier = tier
    now = datetime.utcnow()
    duration_days = _TIER_DURATION_ANNUAL if billing_period == "annual" else _TIER_DURATION_MONTHLY
    user.subscription_expires = now + timedelta(days=duration_days)
    default_amount = _TIER_PRICES_USD.get(tier, {}).get(billing_period, 0)
    record = PaymentHistory(
        user_id=user.id,
        provider=provider,
        payment_id=payment_id,
        plan=tier,
        billing_period=billing_period,
        amount_usd=(amount_usd or default_amount) * 100,
        currency=currency,
        status="confirmed",
        confirmed_at=now,
    )
    db.session.add(record)
    db.session.commit()
    try:
        from ..routes.notifications import create_notification
        create_notification(
            user.id, "payment_confirmed",
            f"{tier.capitalize()} Plan Activated",
            f"Your {tier.capitalize()} subscription is active until {user.subscription_expires.strftime('%Y-%m-%d')}.",
        )
    except Exception:
        pass
    try:
        expires_str = user.subscription_expires.strftime("%Y-%m-%d")
        send_subscription_confirmation(user.email, user.full_name, tier, expires_str)
    except Exception:
        pass


def _claim_dedup(dedup_key: str) -> bool:
    """Atomically claim a dedup key. Returns True if this call is the first to
    claim it (i.e. the caller should proceed), False if it was already claimed
    (duplicate — skip processing).

    Uses the UNIQUE constraint on ProcessedPayment.payment_id so that concurrent
    webhooks race at the DB level; the loser gets an IntegrityError and returns False.
    """
    try:
        db.session.add(ProcessedPayment(payment_id=dedup_key))
        db.session.flush()   # raises IntegrityError immediately if duplicate
        return True
    except IntegrityError:
        db.session.rollback()
        return False


# ─── Plans ────────────────────────────────────────────────────────────────────

@billing_bp.route("/plans", methods=["GET"])
def get_plans():
    return jsonify({"plans": Config.PLANS})


# ─── Billing history ──────────────────────────────────────────────────────────

@billing_bp.route("/history", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def billing_history():
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    page = max(1, min(int(request.args.get("page", 1)), 500))
    per_page = min(50, int(request.args.get("per_page", 20)))
    q = PaymentHistory.query.filter_by(user_id=user.id).order_by(
        PaymentHistory.created_at.desc()
    )
    total = q.count()
    records = q.offset((page - 1) * per_page).limit(per_page).all()
    return jsonify({
        "history": [r.to_dict() for r in records],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    })


# ─── Subscription status ──────────────────────────────────────────────────────

@billing_bp.route("/subscription", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def get_subscription():
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    hard_expired = (
        user.subscription_expires is not None
        and datetime.utcnow() > user.subscription_expires
        and user.subscription_tier != "free"
    )
    # Grace period: subscription_active includes 3-day window after hard expiry
    in_grace = hard_expired and user.subscription_active
    return jsonify({
        "subscription": {
            "tier": user.subscription_tier,
            "expires": user.subscription_expires.isoformat() if user.subscription_expires else None,
            "is_expired": hard_expired,
            "in_grace_period": in_grace,
            "is_active": user.subscription_active,
        }
    })




# ─── Cancel subscription ──────────────────────────────────────────────────────

@billing_bp.route("/subscription", methods=["DELETE"])
@jwt_required()
@rate_limit(requests_per_minute=5)
def cancel_subscription():
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    if user.subscription_tier == "free":
        return jsonify({"error": "No active paid subscription to cancel"}), 400

    prev_tier = user.subscription_tier
    user.subscription_tier = "free"
    user.subscription_expires = None
    record = PaymentHistory(
        user_id=user.id,
        provider="manual",
        payment_id=None,
        plan=prev_tier,
        billing_period=None,
        amount_usd=0,
        currency="USD",
        status="cancelled",
        confirmed_at=datetime.utcnow(),
    )
    db.session.add(record)
    db.session.commit()
    try:
        send_subscription_cancelled(user.email, user.full_name)
    except Exception:
        pass
    logger.info("[BILLING] User %d cancelled %s subscription", user.id, prev_tier)
    return jsonify({"message": "Subscription cancelled. You have been moved to the Free plan."})


# ─── NOWPayments (crypto) ─────────────────────────────────────────────────────

@billing_bp.route("/crypto/checkout", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def crypto_checkout():
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json() or {}
    tier = data.get("tier")
    if tier not in ("pro", "enterprise"):
        return jsonify({"error": "Invalid tier. Must be 'pro' or 'enterprise'"}), 400

    billing_period = "annual" if data.get("annual") else "monthly"

    if user.email in Config.ADMIN_EMAILS:
        return _admin_upgrade(user, tier)

    # Block flagged accounts from initiating payments — prevents monetising
    # referral fraud or other abuse before manual review clears the flag.
    if user.is_suspicious:
        logger.warning("[BILLING] Blocked checkout for suspicious user %d", user.id)
        return jsonify({
            "error": "Your account has been flagged for review. "
                     "Please contact support@telegizer.xyz to resolve this before upgrading.",
            "code": "ACCOUNT_FLAGGED",
        }), 403

    if not Config.NOWPAYMENTS_API_KEY:
        return jsonify({"error": "Crypto payments are not configured yet."}), 503

    amount = _TIER_PRICES_USD[tier][billing_period]
    period_label = "1 Year" if billing_period == "annual" else "1 Month"

    try:
        resp = requests.post(
            "https://api.nowpayments.io/v1/invoice",
            headers={
                "x-api-key": Config.NOWPAYMENTS_API_KEY,
                "Content-Type": "application/json",
            },
            json={
                "price_amount": amount,
                "price_currency": "usd",
                "order_description": f"Telegizer {tier.capitalize()} Plan - {period_label}",
                "success_url": f"{Config.FRONTEND_URL}/payment/success",
                "cancel_url": f"{Config.FRONTEND_URL}/payment/success?status=failed",
                "ipn_callback_url": f"{Config.BACKEND_URL}/api/billing/crypto/webhook",
                "is_fixed_rate": True,
                "is_fee_paid_by_user": False,
            },
            timeout=15,
        )
        resp.raise_for_status()
        result = resp.json()
        invoice_url = result.get("invoice_url")
        nowpayments_invoice_id = str(result.get("id") or result.get("invoice_id") or "")
        if not invoice_url or not nowpayments_invoice_id:
            logger.error(f"[NOWPAYMENTS] Unexpected response: {result}")
            return jsonify({"error": "Failed to get payment URL. Please try again."}), 502

        # Persist a server-side record BEFORE returning the URL.
        # The IPN handler will look up user_id from this row — never from the order string.
        pending = PendingInvoice(
            invoice_id=nowpayments_invoice_id,
            user_id=user.id,
            tier=tier,
            billing_period=billing_period,
            amount_usd=amount,
        )
        db.session.add(pending)
        db.session.commit()
        logger.info("[NOWPAYMENTS] Created pending invoice %s for user %d (%s/%s)",
                    nowpayments_invoice_id, user.id, tier, billing_period)

        return jsonify({"url": invoice_url})
    except requests.RequestException as e:
        logger.error(f"[NOWPAYMENTS] Checkout error for user {user.id}: {e}")
        return jsonify({"error": "Failed to create crypto payment. Please try again."}), 502


@billing_bp.route("/crypto/webhook", methods=["POST"])
def crypto_webhook():
    payload = request.get_data()
    sig = request.headers.get("x-nowpayments-sig", "")

    if not Config.NOWPAYMENTS_IPN_SECRET:
        logger.error("[NOWPAYMENTS] NOWPAYMENTS_IPN_SECRET is not configured — rejecting all webhooks")
        return jsonify({"error": "Webhook not configured"}), 503

    if not sig:
        logger.warning("[NOWPAYMENTS] Missing x-nowpayments-sig header — rejecting webhook")
        return jsonify({"error": "Missing signature"}), 400
    try:
        body = json.loads(payload)
        sorted_body = json.dumps(body, sort_keys=True, separators=(",", ":"))
        expected = hmac.new(
            Config.NOWPAYMENTS_IPN_SECRET.encode(),
            sorted_body.encode(),
            hashlib.sha512,
        ).hexdigest()
        if not hmac.compare_digest(expected, sig):
            logger.warning("[NOWPAYMENTS] Invalid webhook signature")
            return jsonify({"error": "Invalid signature"}), 400
    except Exception as e:
        logger.error(f"[NOWPAYMENTS] Webhook verify error: {e}")
        return jsonify({"error": "Verification error"}), 400

    # Parse payload BEFORE writing any dedup record
    try:
        data = json.loads(payload)
    except Exception:
        return jsonify({"error": "Invalid JSON"}), 400

    payment_status = data.get("payment_status", "")
    order_id = data.get("order_id", "")
    raw_payment_id = data.get("payment_id")

    # Reject webhooks with a missing payment_id — without it we cannot deduplicate
    # and a retry would activate the subscription twice.
    if not raw_payment_id:
        logger.warning("[NOWPAYMENTS] Webhook missing payment_id — rejecting to prevent duplicate activation")
        return jsonify({"error": "payment_id is required"}), 400
    payment_id = str(raw_payment_id)

    # Handle refunds — downgrade user if NOWPayments reports a full refund
    if payment_status in ("refunded", "partially_refunded"):
        logger.warning("[NOWPAYMENTS] Refund received for payment_id=%s order=%s", payment_id, order_id)
        try:
            # Prefer server-side lookup; fall back to parsing order_id for legacy invoices
            pending_ref = PendingInvoice.query.filter_by(invoice_id=order_id).first()
            if pending_ref:
                refund_user_id = pending_ref.user_id
            else:
                parts = order_id.split("_")
                refund_user_id = int(parts[1])
            refund_user = User.query.get(refund_user_id)
            if refund_user and refund_user.subscription_tier != "free":
                prev = refund_user.subscription_tier
                refund_user.subscription_tier = "free"
                refund_user.subscription_expires = None
                refund_record = PaymentHistory(
                    user_id=refund_user.id,
                    provider="nowpayments",
                    payment_id=payment_id,
                    plan=prev,
                    billing_period=None,
                    amount_usd=0,
                    currency="USD",
                    status="refunded",
                    confirmed_at=datetime.utcnow(),
                )
                db.session.add(refund_record)
                db.session.commit()
                logger.info("[NOWPAYMENTS] Downgraded user %d to free after refund", refund_user_id)
        except Exception as exc:
            logger.error("[NOWPAYMENTS] Refund handling error: %s", exc)
        return jsonify({"status": "ok"})

    # Only activate on confirmed/finished payments
    if payment_status not in ("finished", "confirmed"):
        logger.info(f"[NOWPAYMENTS] Ignoring status '{payment_status}' for order {order_id}")
        return jsonify({"status": "ok"})

    # Timestamp validation — reject IPNs older than 1 hour to prevent replays
    # after a DB restore or ProcessedPayment table purge.
    webhook_ts = data.get("created_at") or data.get("updated_at")
    if webhook_ts:
        try:
            from datetime import timezone
            ts = datetime.fromisoformat(str(webhook_ts).replace("Z", "+00:00"))
            if ts.tzinfo:
                ts = ts.astimezone(timezone.utc).replace(tzinfo=None)
            age_seconds = (datetime.utcnow() - ts).total_seconds()
            if age_seconds > 3600:
                logger.warning("[NOWPAYMENTS] Stale IPN (age=%.0fs) for payment_id=%s — ignoring", age_seconds, payment_id)
                return jsonify({"status": "stale"}), 200
        except Exception as ts_exc:
            logger.warning("[NOWPAYMENTS] Could not parse IPN timestamp %r: %s", webhook_ts, ts_exc)

    # Resolve user_id from server-side PendingInvoice (order_id = invoice_id).
    # This prevents tampered order strings from crediting an arbitrary user.
    pending = PendingInvoice.query.filter_by(invoice_id=order_id).first()
    if pending:
        user = User.query.get(pending.user_id)
        tier = pending.tier
        billing_period = pending.billing_period
        expected_usd = float(pending.amount_usd)
        logger.info("[NOWPAYMENTS] Resolved user %d from PendingInvoice for invoice %s", pending.user_id, order_id)
    else:
        # Fallback for legacy invoices created before PendingInvoice was added.
        # Parse order_id string — but ONLY if the invoice_id lookup found nothing.
        try:
            parts = order_id.split("_")
            user_id = int(parts[1])
            tier = parts[2]
            if tier not in ("pro", "enterprise"):
                raise ValueError("Invalid tier")
            billing_period = parts[3] if len(parts) >= 5 and parts[3] in ("monthly", "annual") else "monthly"
        except Exception:
            logger.warning("[NOWPAYMENTS] Could not resolve order_id: %s — no PendingInvoice found", order_id)
            return jsonify({"status": "ok"})
        user = User.query.get(user_id)
        expected_usd = _TIER_PRICES_USD.get(tier, {}).get(billing_period)

    if not user:
        logger.warning("[NOWPAYMENTS] User not found for order %s", order_id)
        return jsonify({"status": "ok"})

    # Idempotency: atomic INSERT — second delivery for same payment_id gets
    # IntegrityError from UNIQUE constraint and is safely skipped.
    if not _claim_dedup(payment_id):
        logger.info(f"[NOWPAYMENTS] Duplicate webhook for payment_id={payment_id} — skipping")
        return jsonify({"status": "ok"})

    price_usd = data.get("price_amount")
    pay_currency = str(data.get("pay_currency") or "USD").upper()
    try:
        amount_usd_dollars = float(price_usd) if price_usd else None
        if amount_usd_dollars is not None and amount_usd_dollars <= 0:
            amount_usd_dollars = None
    except Exception:
        amount_usd_dollars = None

    # Server-side price validation — 1% tolerance for crypto conversion rounding.
    # Any more than that indicates a price-manipulation attempt.
    if expected_usd and amount_usd_dollars is not None:
        min_acceptable = expected_usd * 0.99
        if amount_usd_dollars < min_acceptable:
            logger.error(
                "[NOWPAYMENTS] Price mismatch for order %s: paid $%.2f, expected $%.2f for %s/%s — rejecting",
                order_id, amount_usd_dollars, expected_usd, tier, billing_period,
            )
            return jsonify({"error": "Payment amount does not match plan price"}), 400

    # Mark pending invoice processed atomically with the subscription activation
    if pending and not pending.processed:
        pending.processed = True

    _activate_subscription(user, tier, provider="nowpayments",
                           payment_id=payment_id, amount_usd=amount_usd_dollars,
                           currency=pay_currency, billing_period=billing_period)
    logger.info("[NOWPAYMENTS] Upgraded user %d to %s (status=%s)", user.id, tier, payment_status)
    return jsonify({"status": "ok"})
