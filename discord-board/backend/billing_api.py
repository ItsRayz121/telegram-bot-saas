"""Billing endpoints + NOWPayments IPN webhook.

  GET  /api/guilds/<id>/billing            -> plan + pricing (session)
  POST /api/guilds/<id>/billing/checkout   -> create invoice, return checkout URL
  POST /webhooks/nowpayments               -> IPN (no auth; HMAC-verified)

The webhook is the only thing that grants Pro: it verifies the signature, finds
the pending subscription by order_id, and on a paid status flips the guild.
"""
from __future__ import annotations

import logging
import time

import requests
from flask import Blueprint, g, jsonify, request

import billing
import nowpayments
from auth import login_required
from config import Config
from database import SessionLocal
from models import Guild, Subscription, UserGuild

log = logging.getLogger("guildizer.billing")
billing_bp = Blueprint("billing", __name__)


def _ctx(guild_id: int):
    membership = g.db.get(UserGuild, {"user_id": g.user_id, "guild_id": guild_id})
    if membership is None or not membership.can_manage:
        return None, (jsonify(error="forbidden"), 403)
    guild = g.db.get(Guild, guild_id)
    if guild is None:
        return None, (jsonify(error="not_found"), 404)
    return guild, None


@billing_bp.get("/api/guilds/<int:guild_id>/billing")
@login_required
def billing_status(guild_id: int):
    guild, err = _ctx(guild_id)
    if err:
        return err
    # lazily downgrade if the Pro period lapsed
    if billing.expire_if_due(g.db, guild):
        g.db.commit()
    return jsonify(
        plan=guild.plan or "free",
        is_pro=guild.is_pro,
        plan_expires_at=guild.plan_expires_at.isoformat() + "Z" if guild.plan_expires_at else None,
        pricing=billing.pricing(),
        configured=nowpayments.is_configured(),
    )


@billing_bp.post("/api/guilds/<int:guild_id>/billing/checkout")
@login_required
def checkout(guild_id: int):
    guild, err = _ctx(guild_id)
    if err:
        return err
    if not nowpayments.is_configured():
        return jsonify(error="billing_unconfigured",
                       message="Payments aren't configured yet."), 503

    order_id = f"gz-{guild_id}-{int(time.time())}"
    sub = Subscription(
        guild_id=guild_id,
        user_id=g.user_id,
        plan="pro",
        status="pending",
        order_id=order_id,
        amount=int(Config.PRO_PRICE_USD),
        currency="usd",
        period_days=Config.PRO_PERIOD_DAYS,
    )
    g.db.add(sub)
    g.db.commit()

    try:
        result = nowpayments.create_invoice(
            order_id=order_id,
            amount=Config.PRO_PRICE_USD,
            currency="usd",
            ipn_url=f"{Config.BACKEND_URL}/webhooks/nowpayments",
            success_url=f"{Config.FRONTEND_URL}/servers/{guild_id}",
            cancel_url=f"{Config.FRONTEND_URL}/servers/{guild_id}",
        )
    except requests.RequestException:
        log.exception("NOWPayments invoice creation failed")
        sub.status = "failed"
        g.db.commit()
        return jsonify(error="provider_error", message="Could not start checkout."), 502

    invoice_url = result.get("invoice_url")
    sub.invoice_id = str(result.get("id") or result.get("invoice_id") or "") or None
    g.db.commit()
    if not invoice_url:
        return jsonify(error="provider_error", message="No checkout URL returned."), 502
    return jsonify(invoice_url=invoice_url)


@billing_bp.post("/webhooks/nowpayments")
def nowpayments_ipn():
    raw = request.get_data()
    sig = request.headers.get("x-nowpayments-sig", "")
    if not nowpayments.verify_ipn(raw, sig):
        log.warning("Rejected NOWPayments IPN: bad signature")
        return jsonify(error="bad_signature"), 401

    data = request.get_json(silent=True) or {}
    status = data.get("payment_status", "")
    order_id = data.get("order_id") or ""
    payment_id = str(data.get("payment_id") or "") or None

    db = SessionLocal()
    try:
        sub = db.query(Subscription).filter(Subscription.order_id == order_id).first()
        if sub is None:
            log.warning("IPN for unknown order_id %s", order_id)
            return jsonify(ok=True), 200  # 200 so NOWPayments stops retrying

        if payment_id:
            sub.payment_id = payment_id

        if status in nowpayments.PAID_STATUSES and sub.status != "active":
            guild = db.get(Guild, sub.guild_id)
            if guild is not None:
                billing.activate_pro(db, guild, sub)
                log.info("Activated Pro for guild %s via order %s", sub.guild_id, order_id)
        elif status in ("failed", "expired", "refunded"):
            if sub.status != "active":
                sub.status = "failed"
        db.commit()
        return jsonify(ok=True), 200
    finally:
        db.close()
        SessionLocal.remove()
