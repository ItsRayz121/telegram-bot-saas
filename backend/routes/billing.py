import hashlib
import hmac
import json
import logging
import requests
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..models import db, User, ProcessedPayment, PaymentHistory
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
    page = max(1, int(request.args.get("page", 1)))
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
    is_expired = (
        user.subscription_expires is not None
        and datetime.utcnow() > user.subscription_expires
        and user.subscription_tier != "free"
    )
    return jsonify({
        "subscription": {
            "tier": user.subscription_tier,
            "expires": user.subscription_expires.isoformat() if user.subscription_expires else None,
            "is_expired": is_expired,
            "is_active": not is_expired,
        }
    })


# ─── Lemon Squeezy (card / bank) ─────────────────────────────────────────────

@billing_bp.route("/lemon/checkout", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def lemon_checkout():
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

    if not Config.LS_API_KEY or not Config.LS_STORE_ID:
        return jsonify({"error": "Card payments are not configured yet. Please use crypto."}), 503

    variant_id = Config.LS_PRO_VARIANT_ID if tier == "pro" else Config.LS_ENTERPRISE_VARIANT_ID
    if not variant_id:
        return jsonify({"error": f"Lemon Squeezy variant not configured for tier '{tier}'"}), 503

    try:
        resp = requests.post(
            "https://api.lemonsqueezy.com/v1/checkouts",
            headers={
                "Authorization": f"Bearer {Config.LS_API_KEY}",
                "Accept": "application/vnd.api+json",
                "Content-Type": "application/vnd.api+json",
            },
            json={
                "data": {
                    "type": "checkouts",
                    "attributes": {
                        "checkout_data": {
                            "email": user.email,
                            "name": user.full_name,
                            "custom": {"user_id": str(user.id), "tier": tier, "billing_period": billing_period},
                        },
                        "product_options": {
                            "redirect_url": f"{Config.FRONTEND_URL}/payment/success",
                        },
                    },
                    "relationships": {
                        "store": {"data": {"type": "stores", "id": str(Config.LS_STORE_ID)}},
                        "variant": {"data": {"type": "variants", "id": str(variant_id)}},
                    },
                }
            },
            timeout=15,
        )
        resp.raise_for_status()
        checkout_url = resp.json()["data"]["attributes"]["url"]
        return jsonify({"url": checkout_url})
    except requests.RequestException as e:
        logger.error(f"[LEMONSQUEEZY] Checkout error for user {user.id}: {e}")
        return jsonify({"error": "Failed to create checkout. Please try again."}), 502


@billing_bp.route("/lemon/webhook", methods=["POST"])
def lemon_webhook():
    payload = request.get_data()
    sig = request.headers.get("X-Signature", "")

    if Config.LS_WEBHOOK_SECRET:
        if not sig:
            logger.warning("[LEMONSQUEEZY] Missing X-Signature header — rejecting webhook")
            return jsonify({"error": "Missing signature"}), 400
        expected = hmac.new(
            Config.LS_WEBHOOK_SECRET.encode(), payload, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, sig):
            logger.warning("[LEMONSQUEEZY] Invalid webhook signature")
            return jsonify({"error": "Invalid signature"}), 400

    try:
        event = json.loads(payload)
    except Exception:
        return jsonify({"error": "Invalid JSON"}), 400

    event_name = event.get("meta", {}).get("event_name", "")
    custom = event.get("meta", {}).get("custom_data", {})
    user_id = custom.get("user_id")
    tier = custom.get("tier")

    if event_name == "order_created" and user_id and tier:
        user = User.query.get(int(user_id))
        if user and tier in ("pro", "enterprise"):
            order_id = str(event.get("data", {}).get("id", ""))
            bp = custom.get("billing_period", "monthly")
            if bp not in ("monthly", "annual"):
                bp = "monthly"

            # Idempotency: skip duplicate webhook deliveries for the same order
            dedup_key = f"ls_{order_id}" if order_id else None
            if dedup_key:
                if ProcessedPayment.query.filter_by(payment_id=dedup_key).first():
                    logger.info(f"[LEMONSQUEEZY] Duplicate webhook for order {order_id} — skipping")
                    return jsonify({"status": "ok"})
                db.session.add(ProcessedPayment(payment_id=dedup_key))
                db.session.flush()

            _activate_subscription(user, tier, provider="lemonsqueezy",
                                   payment_id=order_id, currency="USD", billing_period=bp)
            logger.info(f"[LEMONSQUEEZY] Upgraded user {user_id} to {tier}")

    elif event_name in ("subscription_expired", "subscription_cancelled") and user_id:
        user = User.query.get(int(user_id))
        if user:
            user.subscription_tier = "free"
            user.subscription_expires = None
            db.session.commit()
            try:
                send_subscription_cancelled(user.email, user.full_name)
            except Exception:
                pass
            logger.info(f"[LEMONSQUEEZY] Downgraded user {user_id} to free ({event_name})")

    return jsonify({"status": "ok"})


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

    if not Config.NOWPAYMENTS_API_KEY:
        return jsonify({"error": "Crypto payments are not configured yet."}), 503

    amount = _TIER_PRICES_USD[tier][billing_period]
    period_label = "1 Year" if billing_period == "annual" else "1 Month"
    order_id = f"user_{user.id}_{tier}_{billing_period}_{int(datetime.utcnow().timestamp())}"

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
                "order_id": order_id,
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
        if not invoice_url:
            logger.error(f"[NOWPAYMENTS] No invoice_url in response: {result}")
            return jsonify({"error": "Failed to get payment URL. Please try again."}), 502
        return jsonify({"url": invoice_url})
    except requests.RequestException as e:
        logger.error(f"[NOWPAYMENTS] Checkout error for user {user.id}: {e}")
        return jsonify({"error": "Failed to create crypto payment. Please try again."}), 502


@billing_bp.route("/crypto/webhook", methods=["POST"])
def crypto_webhook():
    payload = request.get_data()
    sig = request.headers.get("x-nowpayments-sig", "")

    if Config.NOWPAYMENTS_IPN_SECRET:
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

    try:
        data = json.loads(payload)
    except Exception:
        return jsonify({"error": "Invalid JSON"}), 400

    payment_status = data.get("payment_status", "")
    order_id = data.get("order_id", "")
    payment_id = str(data.get("payment_id", ""))

    # Only activate on confirmed/finished payments
    if payment_status not in ("finished", "confirmed"):
        logger.info(f"[NOWPAYMENTS] Ignoring status '{payment_status}' for order {order_id}")
        return jsonify({"status": "ok"})

    # Idempotency: reject duplicate webhook deliveries for the same payment
    if payment_id:
        if ProcessedPayment.query.filter_by(payment_id=payment_id).first():
            logger.info(f"[NOWPAYMENTS] Duplicate webhook for payment_id={payment_id} — skipping")
            return jsonify({"status": "ok"})
        db.session.add(ProcessedPayment(payment_id=payment_id))
        db.session.flush()

    # order_id formats:
    #   legacy:  user_{id}_{tier}_{timestamp}            (4 parts)
    #   current: user_{id}_{tier}_{billing_period}_{ts}  (5 parts)
    try:
        parts = order_id.split("_")
        user_id = int(parts[1])
        tier = parts[2]
        if tier not in ("pro", "enterprise"):
            raise ValueError("Invalid tier")
        billing_period = parts[3] if len(parts) >= 5 and parts[3] in ("monthly", "annual") else "monthly"
    except Exception:
        logger.warning(f"[NOWPAYMENTS] Could not parse order_id: {order_id}")
        db.session.rollback()
        return jsonify({"status": "ok"})

    user = User.query.get(user_id)
    if not user:
        logger.warning(f"[NOWPAYMENTS] User {user_id} not found for order {order_id}")
        db.session.rollback()
        return jsonify({"status": "ok"})

    # price_amount is the requested USD amount; pay_currency is the crypto used
    price_usd = data.get("price_amount")
    pay_currency = str(data.get("pay_currency") or "USD").upper()
    try:
        amount_usd_dollars = int(float(price_usd)) if price_usd else None
    except Exception:
        amount_usd_dollars = None
    _activate_subscription(user, tier, provider="nowpayments",
                           payment_id=payment_id, amount_usd=amount_usd_dollars,
                           currency=pay_currency, billing_period=billing_period)
    logger.info(f"[NOWPAYMENTS] Upgraded user {user_id} to {tier} (status={payment_status})")
    return jsonify({"status": "ok"})
