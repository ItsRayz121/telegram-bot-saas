import stripe
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..models import db, User
from ..config import Config
from ..middleware.rate_limit import rate_limit
from ..notifications import send_subscription_confirmation, send_subscription_cancelled, send_payment_failed

stripe.api_key = Config.STRIPE_SECRET_KEY

billing_bp = Blueprint("billing", __name__, url_prefix="/api/billing")


def _get_current_user():
    user_id = get_jwt_identity()
    return User.query.get(int(user_id))


@billing_bp.route("/plans", methods=["GET"])
def get_plans():
    return jsonify({"plans": Config.PLANS})


@billing_bp.route("/create-checkout-session", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def create_checkout_session():
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    data = request.get_json()
    tier = data.get("tier")
    if tier not in ("pro", "enterprise"):
        return jsonify({"error": "Invalid tier"}), 400
    price_id = Config.STRIPE_PRICE_IDS.get(tier)
    if not price_id:
        return jsonify({"error": "Price not configured"}), 500
    try:
        if not user.stripe_customer_id:
            customer = stripe.Customer.create(
                email=user.email,
                name=user.full_name,
                metadata={"user_id": str(user.id)},
            )
            user.stripe_customer_id = customer.id
            db.session.commit()
        session = stripe.checkout.Session.create(
            customer=user.stripe_customer_id,
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            mode="subscription",
            success_url=f"{Config.FRONTEND_URL}/dashboard?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{Config.FRONTEND_URL}/pricing",
            metadata={"user_id": str(user.id), "tier": tier},
        )
        return jsonify({"url": session.url, "session_id": session.id})
    except stripe.error.StripeError as e:
        return jsonify({"error": str(e.user_message)}), 400


@billing_bp.route("/webhook", methods=["POST"])
def stripe_webhook():
    payload = request.get_data()
    sig_header = request.headers.get("Stripe-Signature")
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, Config.STRIPE_WEBHOOK_SECRET
        )
    except (ValueError, stripe.error.SignatureVerificationError):
        return jsonify({"error": "Invalid webhook"}), 400

    event_type = event["type"]
    data = event["data"]["object"]

    if event_type == "checkout.session.completed":
        _handle_checkout_completed(data)
    elif event_type == "customer.subscription.updated":
        _handle_subscription_updated(data)
    elif event_type == "customer.subscription.deleted":
        _handle_subscription_deleted(data)
    elif event_type == "invoice.payment_failed":
        _handle_payment_failed(data)

    return jsonify({"status": "ok"})


def _handle_checkout_completed(session):
    user_id = session.get("metadata", {}).get("user_id")
    tier = session.get("metadata", {}).get("tier")
    if not user_id or not tier:
        return
    user = User.query.get(int(user_id))
    if not user:
        return
    subscription_id = session.get("subscription")
    user.subscription_tier = tier
    user.subscription_expires = datetime.utcnow() + timedelta(days=365)
    if subscription_id:
        user.stripe_subscription_id = subscription_id
    db.session.commit()
    try:
        send_subscription_confirmation(user.email, user.full_name, tier)
    except Exception:
        pass


def _handle_subscription_updated(subscription):
    customer_id = subscription.get("customer")
    user = User.query.filter_by(stripe_customer_id=customer_id).first()
    if not user:
        return
    status = subscription.get("status")
    if status == "active":
        current_period_end = subscription.get("current_period_end")
        if current_period_end:
            user.subscription_expires = datetime.utcfromtimestamp(current_period_end)
    elif status in ("canceled", "unpaid", "past_due"):
        user.subscription_tier = "free"
        user.subscription_expires = None
    db.session.commit()


def _handle_subscription_deleted(subscription):
    customer_id = subscription.get("customer")
    user = User.query.filter_by(stripe_customer_id=customer_id).first()
    if not user:
        return
    user.subscription_tier = "free"
    user.subscription_expires = None
    user.stripe_subscription_id = None
    db.session.commit()
    try:
        send_subscription_cancelled(user.email, user.full_name)
    except Exception:
        pass


def _handle_payment_failed(invoice):
    customer_id = invoice.get("customer")
    user = User.query.filter_by(stripe_customer_id=customer_id).first()
    if not user:
        return
    try:
        send_payment_failed(user.email, user.full_name)
    except Exception:
        pass


@billing_bp.route("/subscription", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def get_subscription():
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    subscription_data = {
        "tier": user.subscription_tier,
        "expires": user.subscription_expires.isoformat() if user.subscription_expires else None,
        "stripe_customer_id": user.stripe_customer_id,
        "stripe_subscription_id": user.stripe_subscription_id,
    }
    if user.stripe_subscription_id:
        try:
            sub = stripe.Subscription.retrieve(user.stripe_subscription_id)
            subscription_data["status"] = sub["status"]
            subscription_data["cancel_at_period_end"] = sub.get("cancel_at_period_end", False)
        except stripe.error.StripeError:
            pass
    return jsonify({"subscription": subscription_data})


@billing_bp.route("/cancel-subscription", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=5)
def cancel_subscription():
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    if not user.stripe_subscription_id:
        return jsonify({"error": "No active subscription"}), 400
    try:
        stripe.Subscription.modify(
            user.stripe_subscription_id,
            cancel_at_period_end=True,
        )
        return jsonify({"message": "Subscription will be cancelled at end of billing period"})
    except stripe.error.StripeError as e:
        return jsonify({"error": str(e.user_message)}), 400


@billing_bp.route("/portal", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=5)
def billing_portal():
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    if not user.stripe_customer_id:
        return jsonify({"error": "No billing account found"}), 400
    try:
        session = stripe.billing_portal.Session.create(
            customer=user.stripe_customer_id,
            return_url=f"{Config.FRONTEND_URL}/dashboard",
        )
        return jsonify({"url": session.url})
    except stripe.error.StripeError as e:
        return jsonify({"error": str(e.user_message)}), 400
