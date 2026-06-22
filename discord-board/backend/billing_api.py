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
import access
from auth import login_required
from config import Config
from database import SessionLocal
from models import Guild, PromoCode, PromoCodeUsage, Subscription, UserGuild

log = logging.getLogger("guildizer.billing")
billing_bp = Blueprint("billing", __name__)


def _ctx(guild_id: int):
    if not access.can_manage_guild(g.db, g.user_id, guild_id):
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
    # Account-level plan: Pro is an account entitlement — if the owner holds Pro
    # on any of their servers, this one is Pro too (no separate per-server plan).
    # Unified subscription: a paid Telegizer plan (Pro/Enterprise) also grants
    # Guildizer Pro, so an owner who pays on telegizer.com never pays again here.
    from admin import telegizer_token_is_pro, telegizer_token_tier
    tg_tier = telegizer_token_tier()  # 'enterprise' | 'pro' | 'business' | 'free' | None
    account_pro = billing.account_is_pro(g.db, guild.owner_id) or telegizer_token_is_pro()
    is_pro = guild.is_pro or account_pro
    via_other = account_pro and not guild.is_pro
    # Surface the real Telegizer tier when Pro is inherited from a paid plan, so an
    # Enterprise/Business account shows its true plan name instead of "Pro".
    if not is_pro:
        plan = "free"
    elif tg_tier in ("enterprise", "business"):
        plan = tg_tier
    else:
        plan = "pro"
    return jsonify(
        plan=plan,
        tier=tg_tier,  # raw inherited Telegizer tier (None if not bridged)
        is_pro=is_pro,
        account_pro=account_pro,
        via_account=via_other,  # Pro inherited from another server on this account
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
            # The dashboard lives under the Guildizer section of the main frontend.
            success_url=f"{Config.FRONTEND_URL}{Config.GUILDIZER_FRONTEND_PATH}/servers/{guild_id}",
            cancel_url=f"{Config.FRONTEND_URL}{Config.GUILDIZER_FRONTEND_PATH}/servers/{guild_id}",
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
            # Defense-in-depth: the signature already authenticates the IPN, but
            # never activate on a price below what the subscription charges.
            try:
                paid = float(data.get("price_amount") or 0)
            except (TypeError, ValueError):
                paid = 0.0
            if paid and paid < (sub.amount or 0) * 0.99:
                log.warning("IPN for order %s reports price %.2f below expected %s — not activating",
                            order_id, paid, sub.amount)
            else:
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


@billing_bp.get("/api/guilds/<int:guild_id>/billing/history")
@login_required
def billing_history(guild_id: int):
    """Payment history + pending-invoice recovery (Phase 18). Subscriptions are
    the ledger: pending rows still expose their checkout for recovery."""
    guild, err = _ctx(guild_id)
    if err:
        return err
    rows = (
        g.db.query(Subscription)
        .filter(Subscription.guild_id == guild_id)
        .order_by(Subscription.created_at.desc())
        .limit(25)
        .all()
    )
    out = []
    for s in rows:
        out.append({
            "id": s.id,
            "plan": s.plan,
            "status": s.status,
            "amount": s.amount,
            "currency": (s.currency or "usd").upper(),
            "order_id": s.order_id,
            "created_at": s.created_at.isoformat() + "Z" if s.created_at else None,
        })
    return jsonify(history=out)


@billing_bp.post("/api/guilds/<int:guild_id>/billing/promo")
@login_required
def redeem_promo(guild_id: int):
    """Redeem a promo code -> free Pro days for this guild (Phase 18)."""
    from datetime import datetime, timedelta

    guild, err = _ctx(guild_id)
    if err:
        return err
    code = ((request.get_json(silent=True) or {}).get("code") or "").strip()
    if not code:
        return jsonify(error="code_required"), 400
    promo = g.db.query(PromoCode).filter(PromoCode.code == code).one_or_none()
    if (promo is None or not promo.enabled
            or (promo.expires_at and promo.expires_at <= datetime.utcnow())
            or (promo.used_count or 0) >= (promo.max_uses or 1)):
        return jsonify(error="invalid_code"), 404
    already = (
        g.db.query(PromoCodeUsage)
        .filter(PromoCodeUsage.promo_code_id == promo.id,
                PromoCodeUsage.guild_id == guild_id)
        .first()
    )
    if already is not None:
        return jsonify(error="already_redeemed_here"), 409

    days = max(1, promo.days_free or 0)
    base = guild.plan_expires_at if (guild.is_pro and guild.plan_expires_at) else datetime.utcnow()
    guild.plan = "pro"
    guild.plan_expires_at = base + timedelta(days=days)
    promo.used_count = (promo.used_count or 0) + 1
    g.db.add(PromoCodeUsage(promo_code_id=promo.id, guild_id=guild_id, user_id=g.user_id))
    access.notify(g.db, g.user_id, "Promo applied",
                  f"{days} days of Pro added to {guild.name}.", "info")
    g.db.commit()
    return jsonify(ok=True, days_added=days,
                   plan_expires_at=guild.plan_expires_at.isoformat() + "Z")
