import hashlib
import hmac
import json
import logging
import requests
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..models import db, User
from ..config import Config
from ..middleware.rate_limit import rate_limit
from ..notifications import send_subscription_confirmation, send_subscription_cancelled

logger = logging.getLogger(__name__)

billing_bp = Blueprint("billing", __name__, url_prefix="/api/billing")

_TIER_DURATION_DAYS = 30
_TIER_PRICES_USD = {"pro": 9, "enterprise": 49}


def _get_current_user():
    return User.query.get(int(get_jwt_identity()))


def _admin_upgrade(user, tier):
    user.subscription_tier = tier
    user.subscription_expires = None
    db.session.commit()
    return jsonify({"admin_upgrade": True, "tier": tier, "message": f"Plan switched to {tier}"})


def _activate_subscription(user, tier):
    user.subscription_tier = tier
    user.subscription_expires = datetime.utcnow() + timedelta(days=_TIER_DURATION_DAYS)
    db.session.commit()
    try:
        expires_str = user.subscription_expires.strftime("%Y-%m-%d")
        send_subscription_confirmation(user.email, user.full_name, tier, expires_str)
    except Exception:
        pass


# ─── Plans ────────────────────────────────────────────────────────────────────

@billing_bp.route("/plans", methods=["GET"])
def get_plans():
    return jsonify({"plans": Config.PLANS})


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
                            "custom": {"user_id": str(user.id), "tier": tier},
                        },
                        "product_options": {
                            "redirect_url": f"{Config.FRONTEND_URL}/dashboard?payment=success",
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
            _activate_subscription(user, tier)
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

    if user.email in Config.ADMIN_EMAILS:
        return _admin_upgrade(user, tier)

    if not Config.NOWPAYMENTS_API_KEY:
        return jsonify({"error": "Crypto payments are not configured yet."}), 503

    amount = _TIER_PRICES_USD[tier]
    order_id = f"user_{user.id}_{tier}_{int(datetime.utcnow().timestamp())}"

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
                "order_description": f"BotForge {tier.capitalize()} Plan - 1 Month",
                "success_url": f"{Config.FRONTEND_URL}/dashboard?payment=success",
                "cancel_url": f"{Config.FRONTEND_URL}/pricing",
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

    if Config.NOWPAYMENTS_IPN_SECRET and sig:
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

    # Only activate on confirmed/finished payments
    if payment_status not in ("finished", "confirmed"):
        logger.info(f"[NOWPAYMENTS] Ignoring status '{payment_status}' for order {order_id}")
        return jsonify({"status": "ok"})

    # order_id format: user_{id}_{tier}_{timestamp}
    try:
        parts = order_id.split("_")
        user_id = int(parts[1])
        tier = parts[2]
        if tier not in ("pro", "enterprise"):
            raise ValueError("Invalid tier")
    except Exception:
        logger.warning(f"[NOWPAYMENTS] Could not parse order_id: {order_id}")
        return jsonify({"status": "ok"})

    user = User.query.get(user_id)
    if not user:
        logger.warning(f"[NOWPAYMENTS] User {user_id} not found for order {order_id}")
        return jsonify({"status": "ok"})

    _activate_subscription(user, tier)
    logger.info(f"[NOWPAYMENTS] Upgraded user {user_id} to {tier} (status={payment_status})")
    return jsonify({"status": "ok"})
