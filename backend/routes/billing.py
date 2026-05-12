import hashlib
import hmac
import json
import logging
import requests
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy.exc import IntegrityError
from ..models import db, User, ProcessedPayment, PaymentHistory, PendingInvoice, SubscriptionRenewal
from ..config import Config
from ..middleware.rate_limit import rate_limit
from ..notifications import send_subscription_confirmation, send_subscription_cancelled

logger = logging.getLogger(__name__)

billing_bp = Blueprint("billing", __name__, url_prefix="/api/billing")

_TIER_DURATION_MONTHLY = 30
_TIER_DURATION_ANNUAL = 365
_TIER_PRICES_USD = {"pro": {"monthly": 19, "annual": 152}, "enterprise": {"monthly": 49, "annual": 392}}


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
    expires = now + timedelta(days=duration_days)
    user.subscription_expires = expires
    # 1-A-01: populate extended lifecycle fields
    user.subscription_expires_at  = expires
    user.subscription_grace_until = expires + timedelta(days=7)
    user.subscription_interval    = billing_period
    default_amount = _TIER_PRICES_USD.get(tier, {}).get(billing_period, 0)
    # 1-A-02: renewal audit record
    renewal = SubscriptionRenewal(
        user_id=user.id,
        plan=tier,
        interval=billing_period,
        amount_usd=amount_usd or default_amount,
        payment_id=payment_id,
        expires_at=expires,
    )
    db.session.add(renewal)
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
    tenure_days = (datetime.utcnow() - user.created_at).days
    logger.info("[BILLING] User %d cancelled %s subscription", user.id, prev_tier)
    return jsonify({
        "message": "Subscription cancelled. You have been moved to the Free plan.",
        "plan": prev_tier,
        "tenure_days": tenure_days,
    })


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
                     "Please contact support@telegizer.com to resolve this before upgrading.",
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


# ─── Lemon Squeezy card payments (1-H-01) ─────────────────────────────────────

_LS_VARIANT_MAP: dict | None = None  # built lazily from Config


def _ls_variant_map() -> dict:
    """Maps (tier, interval) → variant_id string."""
    global _LS_VARIANT_MAP
    if _LS_VARIANT_MAP is None:
        _LS_VARIANT_MAP = {
            ("pro",        "monthly"): Config.LS_PRO_MONTHLY_VARIANT_ID,
            ("pro",        "annual"):  Config.LS_PRO_YEARLY_VARIANT_ID,
            ("enterprise", "monthly"): Config.LS_ENTERPRISE_MONTHLY_VARIANT_ID,
            ("enterprise", "annual"):  Config.LS_ENTERPRISE_YEARLY_VARIANT_ID,
        }
    return _LS_VARIANT_MAP


@billing_bp.route("/lemon-squeezy/checkout", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def ls_create_checkout():
    """Create a Lemon Squeezy checkout session and return the hosted checkout URL."""
    if not Config.LS_API_KEY or not Config.LS_STORE_ID:
        return jsonify({"error": "Card payments are not configured"}), 503

    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    body = request.get_json(silent=True) or {}
    tier = body.get("tier", "pro")
    interval = body.get("interval", "monthly")

    if tier not in ("pro", "enterprise"):
        return jsonify({"error": "Invalid plan"}), 400
    if interval not in ("monthly", "annual"):
        return jsonify({"error": "Invalid interval"}), 400

    variant_id = _ls_variant_map().get((tier, interval))
    if not variant_id:
        return jsonify({"error": f"Variant not configured for {tier}/{interval}"}), 503

    payload = {
        "data": {
            "type": "checkouts",
            "attributes": {
                "checkout_data": {
                    "email": user.email,
                    "custom": {
                        "user_id":  str(user.id),
                        "tier":     tier,
                        "interval": interval,
                    },
                },
                "product_options": {
                    "redirect_url": f"{Config.FRONTEND_URL}/billing?payment=success",
                },
            },
            "relationships": {
                "store":   {"data": {"type": "stores",   "id": str(Config.LS_STORE_ID)}},
                "variant": {"data": {"type": "variants", "id": str(variant_id)}},
            },
        }
    }

    try:
        resp = requests.post(
            "https://api.lemonsqueezy.com/v1/checkouts",
            headers={
                "Authorization": f"Bearer {Config.LS_API_KEY}",
                "Accept":        "application/vnd.api+json",
                "Content-Type":  "application/vnd.api+json",
            },
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        checkout_url = data["data"]["attributes"]["url"]
        logger.info("[LS] Checkout created for user %d tier=%s interval=%s", user.id, tier, interval)
        return jsonify({"checkout_url": checkout_url}), 200
    except requests.HTTPError as e:
        logger.error("[LS] Checkout creation failed: %s — %s", e, resp.text[:500])
        return jsonify({"error": "Failed to create checkout session"}), 502
    except Exception as e:
        logger.error("[LS] Checkout error: %s", e)
        return jsonify({"error": "Internal error"}), 500


@billing_bp.route("/lemon-squeezy/webhook", methods=["POST"])
def ls_webhook():
    """Handle Lemon Squeezy order webhooks."""
    raw_body = request.get_data()
    signature = request.headers.get("X-Signature", "")

    if not Config.LS_WEBHOOK_SECRET:
        logger.error("[LS] Webhook received but LS_WEBHOOK_SECRET not configured")
        return jsonify({"error": "Webhook not configured"}), 500

    expected = hmac.new(
        Config.LS_WEBHOOK_SECRET.encode(),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        logger.warning("[LS] Invalid webhook signature")
        return jsonify({"error": "Invalid signature"}), 400

    try:
        event = json.loads(raw_body)
    except Exception:
        return jsonify({"error": "Bad JSON"}), 400

    event_name = event.get("meta", {}).get("event_name", "")
    if event_name not in ("order_created",):
        return jsonify({"status": "ignored"}), 200

    order = event.get("data", {}).get("attributes", {})
    if order.get("status") != "paid":
        return jsonify({"status": "not_paid"}), 200

    custom = event.get("meta", {}).get("custom_data", {})
    user_id = custom.get("user_id")
    tier     = custom.get("tier", "pro")
    interval = custom.get("interval", "monthly")

    if not user_id:
        logger.error("[LS] Webhook missing user_id in custom_data")
        return jsonify({"error": "Missing user_id"}), 400

    user = User.query.get(int(user_id))
    if not user:
        logger.error("[LS] Webhook user_id %s not found", user_id)
        return jsonify({"error": "User not found"}), 404

    order_id = str(event.get("data", {}).get("id", ""))
    dedup_key = f"ls:{order_id}"
    if not _claim_dedup(dedup_key):
        logger.info("[LS] Duplicate webhook for order %s — skipped", order_id)
        return jsonify({"status": "duplicate"}), 200

    amount_usd = None
    try:
        cents = order.get("total")
        if cents:
            amount_usd = int(cents) / 100
    except Exception:
        pass

    # Server-side amount validation — prevent paying $1 to activate a $49 plan.
    expected_usd = _TIER_PRICES_USD.get(tier, {}).get(interval)
    if expected_usd and amount_usd is not None:
        if amount_usd < expected_usd * 0.99:
            logger.error(
                "[LS] Price mismatch for order %s: paid $%.2f, expected $%.2f for %s/%s — rejecting",
                order_id, amount_usd, expected_usd, tier, interval,
            )
            return jsonify({"error": "Payment amount does not match plan price"}), 400

    _activate_subscription(
        user, tier,
        provider="lemonsqueezy",
        payment_id=order_id,
        amount_usd=amount_usd,
        currency="USD",
        billing_period=interval,
    )
    logger.info("[LS] Upgraded user %d to %s/%s via order %s", user.id, tier, interval, order_id)
    return jsonify({"status": "ok"}), 200


# ─── Payment recovery (1-I-02) ────────────────────────────────────────────────

@billing_bp.route("/verify-payment", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=5)
def verify_payment():
    """
    Manually re-check the most recent NOWPayments pending invoice for the current user.
    Returns { upgraded: true, plan } if successful, or { upgraded: false, status }.
    """
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    pending = (
        PendingInvoice.query
        .filter(PendingInvoice.user_id == user.id, PendingInvoice.processed == False)  # noqa: E712
        .order_by(PendingInvoice.created_at.desc())
        .first()
    )
    if not pending:
        return jsonify({"upgraded": False, "status": "no_pending_invoice"}), 200

    if not Config.NOWPAYMENTS_API_KEY:
        return jsonify({"upgraded": False, "status": "crypto_not_configured"}), 200

    try:
        resp = requests.get(
            f"https://api.nowpayments.io/v1/invoice/{pending.invoice_id}",
            headers={"x-api-key": Config.NOWPAYMENTS_API_KEY},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error("[verify-payment] NOWPayments API error: %s", e)
        return jsonify({"upgraded": False, "status": "api_error"}), 200

    # NOWPayments invoice status
    status = data.get("status", data.get("payment_status", "unknown"))
    if status in ("finished", "confirmed", "partially_paid"):
        dedup_key = f"np:invoice:{pending.invoice_id}:verify"
        if not _claim_dedup(dedup_key):
            return jsonify({"upgraded": True, "plan": user.subscription_tier}), 200

        tier     = pending.tier or "pro"
        interval = pending.billing_period or "monthly"
        try:
            amount = float(pending.amount_usd) if pending.amount_usd else None
        except Exception:
            amount = None

        pending.processed = True
        _activate_subscription(
            user, tier,
            provider="nowpayments_recovery",
            payment_id=str(pending.invoice_id),
            amount_usd=amount,
            billing_period=interval,
        )
        logger.info("[verify-payment] Recovered payment for user %d invoice %s", user.id, pending.invoice_id)
        return jsonify({"upgraded": True, "plan": tier}), 200

    return jsonify({"upgraded": False, "status": status}), 200
