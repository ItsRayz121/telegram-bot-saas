"""B2B Partnership Marketplace — deal flow between brands and community owners."""
import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..models import db, PartnershipDeal, DealMessage, DirectoryListing, User
from ..config import Config
from ..middleware.rate_limit import rate_limit

_log = logging.getLogger(__name__)

marketplace_bp = Blueprint("marketplace", __name__)

PLATFORM_FEE_PCT = 10.0  # 10% platform fee


def _get_user():
    return User.query.get(int(get_jwt_identity()))


def _enrich_deal(deal, current_user_id):
    """Add buyer/seller names and messages to deal dict."""
    d = deal.to_dict()
    buyer = User.query.get(deal.buyer_user_id)
    seller = User.query.get(deal.seller_user_id)
    d["buyer_name"] = buyer.full_name if buyer else "Unknown"
    d["seller_name"] = seller.full_name if seller else "Unknown"
    d["is_buyer"] = deal.buyer_user_id == current_user_id
    d["is_seller"] = deal.seller_user_id == current_user_id
    listing = DirectoryListing.query.get(deal.listing_id) if deal.listing_id else None
    d["listing_title"] = listing.title if listing else None
    d["listing_type"] = listing.listing_type if listing else None
    d["messages"] = [m.to_dict() for m in deal.messages.all()]
    return d


# ── Browse marketplace (public with auth check for contact) ──────────────────

@marketplace_bp.route("/api/marketplace", methods=["GET"])
def browse():
    q = DirectoryListing.query.filter_by(is_public=True, accepts_partnerships=True)

    category = request.args.get("category")
    if category:
        q = q.filter_by(category=category)

    listing_type = request.args.get("type")
    if listing_type in ("channel", "group"):
        q = q.filter_by(listing_type=listing_type)

    search = (request.args.get("q") or "").strip()
    if search:
        like = f"%{search}%"
        q = q.filter(db.or_(
            DirectoryListing.title.ilike(like),
            DirectoryListing.description.ilike(like),
        ))

    max_price = request.args.get("max_price", type=float)
    if max_price:
        q = q.filter(
            db.or_(
                DirectoryListing.price_per_post <= max_price,
                DirectoryListing.price_per_week <= max_price,
            )
        )

    sort = request.args.get("sort", "members")
    if sort == "price_asc":
        q = q.order_by(DirectoryListing.price_per_post.asc().nullslast())
    elif sort == "tcs":
        q = q.order_by(DirectoryListing.tcs_score.desc().nullslast())
    else:
        q = q.order_by(DirectoryListing.is_featured.desc(), DirectoryListing.member_count.desc())

    page = request.args.get("page", 1, type=int)
    per_page = 18
    total = q.count()
    listings = q.offset((page - 1) * per_page).limit(per_page).all()

    return jsonify({
        "listings": [l.to_dict() for l in listings],
        "total": total,
        "page": page,
        "pages": max(1, (total + per_page - 1) // per_page),
    })


# ── Deal CRUD ─────────────────────────────────────────────────────────────────

@marketplace_bp.route("/api/marketplace/deals", methods=["GET"])
@jwt_required()
def list_deals():
    user = _get_user()
    role = request.args.get("role", "all")  # buyer | seller | all
    q = PartnershipDeal.query.filter(
        db.or_(
            PartnershipDeal.buyer_user_id == user.id,
            PartnershipDeal.seller_user_id == user.id,
        )
    )
    if role == "buyer":
        q = q.filter_by(buyer_user_id=user.id)
    elif role == "seller":
        q = q.filter_by(seller_user_id=user.id)

    status = request.args.get("status")
    if status:
        q = q.filter_by(status=status)

    deals = q.order_by(PartnershipDeal.created_at.desc()).limit(50).all()
    return jsonify([_enrich_deal(d, user.id) for d in deals])


@marketplace_bp.route("/api/marketplace/deals/<int:did>", methods=["GET"])
@jwt_required()
def get_deal(did):
    user = _get_user()
    deal = PartnershipDeal.query.get_or_404(did)
    if deal.buyer_user_id != user.id and deal.seller_user_id != user.id:
        return jsonify({"error": "Not authorized"}), 403
    return jsonify(_enrich_deal(deal, user.id))


@marketplace_bp.route("/api/marketplace/deals", methods=["POST"])
@jwt_required()
def create_deal():
    user = _get_user()
    data = request.get_json() or {}

    listing_id = data.get("listing_id")
    if not listing_id:
        return jsonify({"error": "listing_id required"}), 400

    listing = DirectoryListing.query.filter_by(id=listing_id, is_public=True, accepts_partnerships=True).first()
    if not listing:
        return jsonify({"error": "Listing not found or not accepting partnerships"}), 404

    if listing.user_id == user.id:
        return jsonify({"error": "You cannot send a deal request to your own listing"}), 400

    title = (data.get("title") or "").strip()
    requirements = (data.get("requirements") or "").strip()
    budget_usd = data.get("budget_usd")
    deadline_days = data.get("deadline_days", 7)
    currency = data.get("currency", "USDT")

    if not title:
        return jsonify({"error": "title is required"}), 400

    try:
        budget_usd = float(budget_usd)
    except (TypeError, ValueError):
        return jsonify({"error": "budget_usd must be a number"}), 400
    if not (5 <= budget_usd <= 50000):
        return jsonify({"error": "Budget must be between $5 and $50,000"}), 400

    try:
        deadline_days = int(deadline_days)
    except (TypeError, ValueError):
        deadline_days = 7
    if not (1 <= deadline_days <= 365):
        return jsonify({"error": "deadline_days must be between 1 and 365"}), 400

    net_seller = round(budget_usd * (1 - PLATFORM_FEE_PCT / 100), 2)

    deal = PartnershipDeal(
        buyer_user_id=user.id,
        seller_user_id=listing.user_id,
        listing_id=listing.id,
        title=title,
        requirements=requirements or None,
        budget_usd=budget_usd,
        platform_fee_pct=PLATFORM_FEE_PCT,
        net_seller_amount=net_seller,
        status="pending",
        payment_status="unpaid",
        payment_currency=currency,
        deadline_at=datetime.utcnow() + timedelta(days=deadline_days),
    )
    db.session.add(deal)

    # Auto-message from buyer
    if requirements:
        db.session.flush()
        msg = DealMessage(deal_id=deal.id, sender_user_id=user.id,
                          body=f"**Brief:**\n{requirements}")
        db.session.add(msg)

    db.session.commit()
    return jsonify(_enrich_deal(deal, user.id)), 201


# ── Deal state transitions ────────────────────────────────────────────────────

def _deal_transition(did, allowed_statuses, new_status, extra_fn=None):
    user = _get_user()
    deal = PartnershipDeal.query.get_or_404(did)
    if deal.status not in allowed_statuses:
        return jsonify({"error": f"Deal is {deal.status}, cannot perform this action"}), 400
    deal.status = new_status
    if extra_fn:
        extra_fn(deal)
    db.session.commit()
    return jsonify(_enrich_deal(deal, user.id))


@marketplace_bp.route("/api/marketplace/deals/<int:did>/accept", methods=["POST"])
@jwt_required()
def accept_deal(did):
    user = _get_user()
    deal = PartnershipDeal.query.get_or_404(did)
    if deal.seller_user_id != user.id:
        return jsonify({"error": "Only the seller can accept"}), 403
    if deal.status != "pending":
        return jsonify({"error": f"Deal is {deal.status}"}), 400
    deal.status = "accepted"
    deal.accepted_at = datetime.utcnow()
    msg = DealMessage(deal_id=deal.id, sender_user_id=user.id,
                      body="I've accepted this deal. Please proceed with payment to get started.")
    db.session.add(msg)
    db.session.commit()
    return jsonify(_enrich_deal(deal, user.id))


@marketplace_bp.route("/api/marketplace/deals/<int:did>/decline", methods=["POST"])
@jwt_required()
def decline_deal(did):
    user = _get_user()
    deal = PartnershipDeal.query.get_or_404(did)
    if deal.seller_user_id != user.id:
        return jsonify({"error": "Only the seller can decline"}), 403
    if deal.status not in ("pending",):
        return jsonify({"error": f"Deal is {deal.status}"}), 400
    data = request.get_json() or {}
    reason = (data.get("reason") or "").strip()
    deal.status = "declined"
    if reason:
        msg = DealMessage(deal_id=deal.id, sender_user_id=user.id,
                          body=f"I've declined this request. Reason: {reason}")
        db.session.add(msg)
    db.session.commit()
    return jsonify(_enrich_deal(deal, user.id))


@marketplace_bp.route("/api/marketplace/deals/<int:did>/pay", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=5)
def initiate_payment(did):
    """Create a NOWPayments invoice for the deal."""
    user = _get_user()
    deal = PartnershipDeal.query.get_or_404(did)
    if deal.buyer_user_id != user.id:
        return jsonify({"error": "Only the buyer can pay"}), 403
    if deal.status != "accepted":
        return jsonify({"error": "Deal must be accepted before payment"}), 400
    if deal.payment_status in ("paid", "released"):
        return jsonify({"error": "Already paid"}), 400

    import requests as _http
    from ..config import Config

    api_key = Config.NOWPAYMENTS_API_KEY
    if not api_key:
        return jsonify({"error": "Payment provider not configured"}), 503

    data = request.get_json() or {}
    currency = data.get("currency", deal.payment_currency or "USDT")

    try:
        resp = _http.post(
            "https://api.nowpayments.io/v1/payment",
            json={
                "price_amount": deal.budget_usd,
                "price_currency": "usd",
                "pay_currency": currency.lower(),
                "order_id": f"deal_{deal.id}",
                "order_description": f"Partnership deal: {deal.title}",
                "ipn_callback_url": f"{Config.BACKEND_URL}/api/marketplace/webhook",
            },
            headers={"x-api-key": api_key},
            timeout=15,
        )
        resp.raise_for_status()
        payment_data = resp.json()
    except Exception as e:
        _log.error("NOWPayments deal payment error for deal %s user %s: %s", deal.id, user.id, e)
        return jsonify({"error": "Payment provider unavailable. Please try again."}), 502

    deal.payment_id = payment_data.get("payment_id")
    deal.payment_address = payment_data.get("pay_address")
    deal.payment_currency = currency
    deal.payment_status = "awaiting"
    db.session.commit()

    return jsonify({
        **_enrich_deal(deal, user.id),
        "pay_address": payment_data.get("pay_address"),
        "pay_amount": payment_data.get("pay_amount"),
        "pay_currency": currency,
        "payment_id": payment_data.get("payment_id"),
    })


@marketplace_bp.route("/api/marketplace/webhook", methods=["POST"])
def payment_webhook():
    """NOWPayments IPN — mark deal as paid when payment confirmed."""
    payload = request.get_data()
    sig = request.headers.get("x-nowpayments-sig", "")

    if not Config.NOWPAYMENTS_IPN_SECRET:
        _log.error("[MARKETPLACE_WEBHOOK] NOWPAYMENTS_IPN_SECRET not configured — rejecting")
        return jsonify({"error": "Webhook not configured"}), 503

    if not sig:
        _log.warning("[MARKETPLACE_WEBHOOK] Missing signature")
        return jsonify({"error": "Missing signature"}), 400

    try:
        body_obj = json.loads(payload)
        sorted_body = json.dumps(body_obj, sort_keys=True, separators=(",", ":"))
        expected = hmac.new(
            Config.NOWPAYMENTS_IPN_SECRET.encode(),
            sorted_body.encode(),
            hashlib.sha512,
        ).hexdigest()
        if not hmac.compare_digest(expected, sig):
            _log.warning("[MARKETPLACE_WEBHOOK] Invalid signature")
            return jsonify({"error": "Invalid signature"}), 400
    except Exception as e:
        _log.error("[MARKETPLACE_WEBHOOK] Signature verification error: %s", e)
        return jsonify({"error": "Verification error"}), 400

    data = body_obj
    order_id = data.get("order_id", "")
    payment_status = data.get("payment_status", "")

    if not order_id.startswith("deal_"):
        return jsonify({"ok": True})

    try:
        deal_id = int(order_id.replace("deal_", ""))
    except ValueError:
        return jsonify({"ok": True})

    if payment_status in ("confirmed", "finished"):
        webhook_payment_id = str(data.get("payment_id") or "")
        deal = PartnershipDeal.query.get(deal_id)
        if not deal:
            return jsonify({"ok": True})

        # Verify the payment_id in the webhook matches the one we stored when the
        # buyer initiated payment.  Without this check, a correctly-signed but
        # unrelated webhook could advance any deal in `awaiting` state.
        if deal.payment_id and webhook_payment_id and deal.payment_id != webhook_payment_id:
            _log.warning(
                "[MARKETPLACE_WEBHOOK] payment_id mismatch for deal %s: stored=%s webhook=%s",
                deal.id, deal.payment_id, webhook_payment_id,
            )
            return jsonify({"ok": True})

        if deal.payment_status == "awaiting":
            deal.payment_status = "paid"
            deal.status = "in_progress"
            deal.paid_at = datetime.utcnow()
            db.session.commit()
            _log.info("[MARKETPLACE_WEBHOOK] Deal %s marked paid (payment_id=%s)", deal.id, webhook_payment_id)

    return jsonify({"ok": True})


@marketplace_bp.route("/api/marketplace/deals/<int:did>/deliver", methods=["POST"])
@jwt_required()
def deliver_deal(did):
    user = _get_user()
    deal = PartnershipDeal.query.get_or_404(did)
    if deal.seller_user_id != user.id:
        return jsonify({"error": "Only the seller can mark as delivered"}), 403
    if deal.status != "in_progress":
        return jsonify({"error": "Deal must be in progress to deliver"}), 400

    data = request.get_json() or {}
    deliverable = (data.get("deliverable") or "").strip()
    if not deliverable:
        return jsonify({"error": "Describe what you delivered"}), 400

    deal.status = "delivered"
    deal.deliverable = deliverable
    deal.delivered_at = datetime.utcnow()
    msg = DealMessage(deal_id=deal.id, sender_user_id=user.id,
                      body=f"**Delivered!**\n{deliverable}")
    db.session.add(msg)
    db.session.commit()
    return jsonify(_enrich_deal(deal, user.id))


@marketplace_bp.route("/api/marketplace/deals/<int:did>/complete", methods=["POST"])
@jwt_required()
def complete_deal(did):
    user = _get_user()
    deal = PartnershipDeal.query.get_or_404(did)
    if deal.buyer_user_id != user.id:
        return jsonify({"error": "Only the buyer can confirm completion"}), 403
    if deal.status != "delivered":
        return jsonify({"error": "Deal must be delivered first"}), 400
    deal.status = "completed"
    deal.payment_status = "released"
    deal.completed_at = datetime.utcnow()
    msg = DealMessage(deal_id=deal.id, sender_user_id=user.id,
                      body="Deal completed! Payment released. Thanks for the partnership.")
    db.session.add(msg)
    db.session.commit()
    return jsonify(_enrich_deal(deal, user.id))


@marketplace_bp.route("/api/marketplace/deals/<int:did>/dispute", methods=["POST"])
@jwt_required()
def dispute_deal(did):
    user = _get_user()
    deal = PartnershipDeal.query.get_or_404(did)
    if deal.buyer_user_id != user.id:
        return jsonify({"error": "Only the buyer can dispute"}), 403
    if deal.status not in ("delivered", "in_progress"):
        return jsonify({"error": "Can only dispute in-progress or delivered deals"}), 400

    data = request.get_json() or {}
    reason = (data.get("reason") or "").strip()
    deal.status = "disputed"
    if reason:
        msg = DealMessage(deal_id=deal.id, sender_user_id=user.id,
                          body=f"**Dispute raised:**\n{reason}\n\nTelegizer support will review this.")
        db.session.add(msg)
    db.session.commit()
    return jsonify(_enrich_deal(deal, user.id))


@marketplace_bp.route("/api/marketplace/deals/<int:did>/cancel", methods=["POST"])
@jwt_required()
def cancel_deal(did):
    user = _get_user()
    deal = PartnershipDeal.query.get_or_404(did)
    if deal.buyer_user_id != user.id and deal.seller_user_id != user.id:
        return jsonify({"error": "Not authorized"}), 403
    if deal.status not in ("pending", "accepted"):
        return jsonify({"error": "Can only cancel pending or accepted deals"}), 400
    deal.status = "cancelled"
    db.session.commit()
    return jsonify(_enrich_deal(deal, user.id))


# ── Deal messages ─────────────────────────────────────────────────────────────

@marketplace_bp.route("/api/marketplace/deals/<int:did>/messages", methods=["POST"])
@jwt_required()
def send_message(did):
    user = _get_user()
    deal = PartnershipDeal.query.get_or_404(did)
    if deal.buyer_user_id != user.id and deal.seller_user_id != user.id:
        return jsonify({"error": "Not authorized"}), 403

    data = request.get_json() or {}
    body = (data.get("body") or "").strip()
    if not body:
        return jsonify({"error": "Message body required"}), 400

    msg = DealMessage(deal_id=deal.id, sender_user_id=user.id, body=body)
    db.session.add(msg)
    db.session.commit()
    return jsonify(msg.to_dict()), 201


# ── Update listing pricing (seller sets their rates) ─────────────────────────

@marketplace_bp.route("/api/marketplace/listing/<int:lid>/pricing", methods=["PATCH"])
@jwt_required()
def update_pricing(lid):
    user = _get_user()
    listing = DirectoryListing.query.filter_by(id=lid, user_id=user.id).first_or_404()
    data = request.get_json() or {}

    if "accepts_partnerships" in data:
        listing.accepts_partnerships = bool(data["accepts_partnerships"])
    if "price_per_post" in data:
        v = data["price_per_post"]
        listing.price_per_post = float(v) if v else None
    if "price_per_week" in data:
        v = data["price_per_week"]
        listing.price_per_week = float(v) if v else None
    if "pricing_notes" in data:
        listing.pricing_notes = (data["pricing_notes"] or "").strip() or None

    db.session.commit()
    return jsonify(listing.to_dict(include_contact=True))
