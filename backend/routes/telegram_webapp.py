"""
Telegram Mini App authentication and email-linking endpoints.

Auth flow:
  POST /api/miniapp/auth   { "init_data": "<raw initData string>" }
    1. Validate Telegram HMAC signature using bot token.
    2. Look up user by telegram_user_id (fast path on users table).
       If not found, check UserTelegramAccount junction table and backfill.
       If still not found, auto-create a Telegram-only account (no email needed).
    3. Issue JWT. Return user, groups, referral_link, email_linked.

  GET  /api/miniapp/me      (JWT-auth) — return current user + groups

Email-linking flow (optional "Protect your account"):
  POST /api/miniapp/link-email/request  { "email": "..." }
    — Send 6-digit OTP to the email. Detects merge case.

  POST /api/miniapp/link-email/verify   { "otp": "123456", "password": "..." }
    — Validate OTP, set password, link email. Handles account merge.
"""
import hashlib
import hmac
import json
import logging
import re
import secrets
import threading
import time
import urllib.parse
from datetime import datetime, timedelta

import bcrypt
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import (
    create_access_token, create_refresh_token, jwt_required, get_jwt_identity,
)

from ..models import db, User, TelegramGroup, UserTelegramAccount, Referral, TelegramBotStarted
from ..config import Config
from ..middleware.rate_limit import rate_limit
from ..middleware.csrf import generate_csrf_token


def _set_miniapp_cookies(response, access_token: str, refresh_token: str = None):
    """Set the same httpOnly auth cookies as normal login so the full dashboard works."""
    is_prod = "postgres" in (current_app.config.get("SQLALCHEMY_DATABASE_URI") or "")
    secure = current_app.config.get("JWT_COOKIE_SECURE", is_prod)
    response.set_cookie(
        "access_token", access_token,
        httponly=True, secure=secure, samesite="Strict",
        max_age=86400,
    )
    if refresh_token:
        response.set_cookie(
            "refresh_token", refresh_token,
            httponly=True, secure=secure, samesite="Strict",
            path="/api/auth/refresh",
            max_age=2592000,
        )
    response.set_cookie(
        "csrf_token", generate_csrf_token(),
        httponly=False, secure=secure, samesite="Strict",
    )
    return response

miniapp_bp = Blueprint("miniapp", __name__, url_prefix="/api/miniapp")
_log = logging.getLogger(__name__)

_MAX_AGE_SECONDS = 3600  # reject initData older than 1 hour
_OTP_EXPIRY_MINUTES = 10


# ── initData validation ────────────────────────────────────────────────────────

def _verify_init_data(init_data: str, bot_token: str) -> tuple[dict | None, str | None]:
    """
    Validate Telegram WebApp initData HMAC.
    Returns (parsed_dict, None) on success or (None, reason_string) on failure.
    """
    try:
        params = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
        received_hash = params.pop("hash", None)
        if not received_hash:
            return None, "missing_hash"

        data_check = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))

        # HMAC key = HMAC-SHA256("WebAppData", bot_token)
        secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        expected = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(expected, received_hash):
            return None, "hmac_mismatch"

        auth_date = int(params.get("auth_date", 0))
        if time.time() - auth_date > _MAX_AGE_SECONDS:
            return None, f"expired_{int(time.time() - auth_date)}s"

        result = dict(params)
        if "user" in result:
            result["user"] = json.loads(result["user"])
        return result, None
    except Exception as exc:
        _log.warning("initData verification exception: %s", exc)
        return None, f"exception:{exc}"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _user_groups(user: User):
    groups = TelegramGroup.query.filter_by(
        owner_user_id=user.id, is_disabled=False
    ).order_by(TelegramGroup.created_at.desc()).all()
    return [
        {
            "id": g.id,
            "telegram_group_id": g.telegram_group_id,
            "name": g.title or f"Group {g.telegram_group_id}",
            "bot_status": g.bot_status,
            "member_count": g.member_count,
        }
        for g in groups
    ]


def _resolve_referral_code(parsed: dict, tg_id: str) -> str | None:
    """Find the referral code for a brand-new Telegram user, from either source:
    1. `start_param` in initData (Mini App launched via startapp=ref_<code>), or
    2. the code stashed by the bot's `/start ref_<code>` handler.
    """
    sp = (parsed.get("start_param") or "").strip()
    if sp.startswith("ref_"):
        code = sp[len("ref_"):].strip()
        if code:
            return code
    return TelegramBotStarted.consume_pending_referral(tg_id)


def _trigger_referral_rewards_async(app, referrer_id: int, referred_first_name: str):
    """Apply referral milestone rewards for the referrer in a background thread."""
    def _reward():
        try:
            with app.app_context():
                from ..routes.referrals import _apply_referral_rewards
                from ..notifications import send_referral_conversion_email
                r = User.query.get(referrer_id)
                if not r:
                    return
                _apply_referral_rewards(r)
                if r.email:  # referrer may be Telegram-only (no email to notify)
                    total = Referral.query.filter_by(
                        referrer_user_id=r.id, status="approved"
                    ).count()
                    try:
                        send_referral_conversion_email(
                            r.email,
                            r.full_name.split()[0] if r.full_name else r.email,
                            referred_first_name,
                            total,
                        )
                    except Exception as exc:
                        _log.debug("referral conversion email failed: %s", exc)
        except Exception as exc:
            _log.error("telegram referral reward failed for referrer=%s: %s", referrer_id, exc)

    threading.Thread(target=_reward, daemon=True).start()


def _attribute_telegram_referral(new_user: User, ref_code: str):
    """Create + approve a Referral for a newly auto-created Telegram user.

    Telegram's HMAC-verified identity (phone-backed account) is the anti-abuse
    gate, so the referral is approved immediately — unlike email signup, which
    defers approval until the email is verified. Self-referrals and duplicates
    are skipped; the admin referral-farming detector catches bulk abuse.
    """
    referrer = User.query.filter_by(referral_code=ref_code).first()
    if not referrer or referrer.id == new_user.id:
        return
    if Referral.query.filter_by(referred_user_id=new_user.id).first():
        return

    db.session.add(Referral(
        referrer_user_id=referrer.id,
        referred_user_id=new_user.id,
        referral_code=ref_code,
        status="approved",
    ))
    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        _log.warning("telegram referral attribution failed: %s", exc)
        return

    _log.info("miniapp_auth: referral attributed referrer=%s referred=%s code=%s",
              referrer.id, new_user.id, ref_code)
    referred_first = (new_user.full_name or "Someone").split()[0] if new_user.full_name else "Someone"
    _trigger_referral_rewards_async(current_app._get_current_object(), referrer.id, referred_first)


def _send_otp_email_async(app, to_email: str, otp: str, is_merge: bool, display_name: str):
    """Send OTP email in a background thread (non-blocking)."""
    from ..notifications import send_email

    subject = "Your Telegizer verification code"
    if is_merge:
        body_text = (
            f"Hi,\n\n"
            f"Someone is trying to link their Telegram account to this email address on Telegizer.\n\n"
            f"Your verification code is: {otp}\n\n"
            f"This code expires in {_OTP_EXPIRY_MINUTES} minutes.\n\n"
            f"If you didn't request this, you can safely ignore this email.\n\n"
            f"— Telegizer"
        )
        body_html = (
            f"<p>Hi,</p>"
            f"<p>Someone is trying to link their Telegram account to this email address on Telegizer.</p>"
            f"<p><strong>Your verification code: <span style='font-size:1.4em;letter-spacing:4px'>{otp}</span></strong></p>"
            f"<p>This code expires in {_OTP_EXPIRY_MINUTES} minutes.</p>"
            f"<p>If you didn't request this, you can safely ignore this email.</p>"
            f"<p>— Telegizer</p>"
        )
    else:
        name = display_name or "there"
        body_text = (
            f"Hi {name},\n\n"
            f"To secure your Telegizer account, enter this code:\n\n"
            f"{otp}\n\n"
            f"This code expires in {_OTP_EXPIRY_MINUTES} minutes.\n\n"
            f"— Telegizer"
        )
        body_html = (
            f"<p>Hi {name},</p>"
            f"<p>To secure your Telegizer account, enter this verification code:</p>"
            f"<p><strong style='font-size:1.4em;letter-spacing:4px'>{otp}</strong></p>"
            f"<p>This code expires in {_OTP_EXPIRY_MINUTES} minutes.</p>"
            f"<p>— Telegizer</p>"
        )

    def _send():
        try:
            with app.app_context():
                send_email(to_email, subject, body_html, body_text)
        except Exception as exc:
            _log.error("OTP email failed to %s: %s", to_email, exc)

    threading.Thread(target=_send, daemon=True).start()


def _send_verification_email_async(app, user_email: str, full_name: str, token: str):
    """Send email verification link after email is linked (non-blocking)."""
    from ..notifications import send_verification_email

    def _send():
        try:
            with app.app_context():
                send_verification_email(user_email, full_name or "", token)
        except Exception as exc:
            _log.error("Verification email failed for %s: %s", user_email, exc)

    threading.Thread(target=_send, daemon=True).start()


# ── Auth ───────────────────────────────────────────────────────────────────────

@miniapp_bp.route("/auth", methods=["POST"])
@rate_limit(requests_per_minute=20)
def miniapp_auth():
    data = request.get_json() or {}
    init_data = (data.get("init_data") or "").strip()

    if not init_data:
        return jsonify({"error": "init_data is required"}), 400

    bot_token = (Config.TELEGRAM_BOT_TOKEN or "").strip()
    if not bot_token:
        return jsonify({"error": "Bot not configured"}), 503

    parsed, fail_reason = _verify_init_data(init_data, bot_token)
    if not parsed:
        _log.warning("miniapp_auth: initData verification failed reason=%s ip=%s",
                     fail_reason, request.remote_addr)
        if fail_reason and "expired" in fail_reason:
            return jsonify({"error": "Session expired — please reopen the app"}), 401
        if fail_reason == "hmac_mismatch":
            return jsonify({"error": "Invalid authentication — are you using the correct bot?"}), 401
        return jsonify({"error": "Invalid or expired session"}), 401

    tg_user = parsed.get("user", {})
    tg_id = str(tg_user.get("id", ""))
    if not tg_id:
        return jsonify({"error": "No user in initData"}), 400

    # ── 1. Fast lookup on users.telegram_user_id ──────────────────────────────
    user = User.query.filter_by(telegram_user_id=tg_id).first()
    created = False

    # ── 2. Check junction table (old link flow) and backfill if found ─────────
    if not user:
        uta = UserTelegramAccount.query.filter_by(telegram_user_id=tg_id).first()
        if uta:
            user = User.query.get(uta.user_id)
            if user and not user.telegram_user_id:
                user.telegram_user_id = tg_id
                user.telegram_username = tg_user.get("username")
                user.telegram_first_name = tg_user.get("first_name", "")
                user.telegram_connected_at = datetime.utcnow()
                if user.email and user.auth_provider == "email":
                    user.auth_provider = "both"
                try:
                    db.session.commit()
                except Exception:
                    db.session.rollback()

    # ── 3. Auto-create Telegram-only account (zero-friction onboarding) ───────
    if not user:
        first = tg_user.get("first_name", "")
        last = tg_user.get("last_name", "")
        display_name = (first + " " + last).strip() or f"User {tg_id}"
        ref_code = secrets.token_urlsafe(8)[:10]
        user = User(
            telegram_user_id=tg_id,
            telegram_username=tg_user.get("username"),
            telegram_first_name=first,
            telegram_connected_at=datetime.utcnow(),
            full_name=display_name,
            auth_provider="telegram",
            subscription_tier="free",
            referral_code=ref_code,
            email_verified=False,
        )
        db.session.add(user)
        try:
            db.session.commit()
            created = True
        except Exception:
            db.session.rollback()
            # Race condition: another request created the same tg_id simultaneously
            user = User.query.filter_by(telegram_user_id=tg_id).first()
            if not user:
                _log.error("miniapp_auth: failed to create user for tg_id=%s", tg_id)
                return jsonify({"error": "Account creation failed — please try again"}), 500
        if created:
            _log.info("miniapp_auth: auto-created tg user_id=%s tg_id=%s", user.id, tg_id)

    if user.is_banned:
        return jsonify({"error": "Account suspended"}), 403

    # ── Referral attribution (new Telegram signups only) ──────────────────────
    if created:
        ref_code = _resolve_referral_code(parsed, tg_id)
        if ref_code:
            _attribute_telegram_referral(user, ref_code)

    # Refresh Telegram display name if it changed
    tg_username_now = tg_user.get("username")
    tg_first_now = tg_user.get("first_name", "")
    if user.telegram_username != tg_username_now or user.telegram_first_name != tg_first_now:
        user.telegram_username = tg_username_now
        user.telegram_first_name = tg_first_now
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

    bot_username = (Config.TELEGRAM_BOT_USERNAME or "TelegizerBot").strip().lstrip("@")
    referral_code = user.referral_code or user.get_or_create_referral_code()
    referral_link = f"https://t.me/{bot_username}?start=ref_{referral_code}"

    _log.info("miniapp_auth: ok user_id=%s tg_id=%s provider=%s", user.id, tg_id, user.auth_provider)
    token = create_access_token(identity=str(user.id))
    refresh_token = create_refresh_token(identity=str(user.id))
    resp = jsonify({
        "token": token,
        "user": user.to_dict(),
        "groups": _user_groups(user),
        "referral_link": referral_link,
        "email_linked": bool(user.email),
    })
    _set_miniapp_cookies(resp, token, refresh_token)
    return resp


# ── Me ─────────────────────────────────────────────────────────────────────────

@miniapp_bp.route("/me", methods=["GET"])
@jwt_required()
def miniapp_me():
    user = User.query.get(int(get_jwt_identity()))
    if not user:
        return jsonify({"error": "User not found"}), 404

    bot_username = (Config.TELEGRAM_BOT_USERNAME or "TelegizerBot").strip().lstrip("@")
    referral_code = user.referral_code or user.get_or_create_referral_code()
    return jsonify({
        "user": user.to_dict(),
        "groups": _user_groups(user),
        "referral_link": f"https://t.me/{bot_username}?start=ref_{referral_code}",
        "email_linked": bool(user.email),
    })


# ── Email linking: step 1 — request OTP ───────────────────────────────────────

@miniapp_bp.route("/link-email/request", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=5)
def link_email_request():
    user = User.query.get(int(get_jwt_identity()))
    if not user:
        return jsonify({"error": "User not found"}), 404

    if user.email:
        return jsonify({"error": "An email is already linked to this account"}), 400

    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()

    if not email:
        return jsonify({"error": "Email is required"}), 400
    if len(email) > 255:
        return jsonify({"error": "Email too long"}), 400
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$", email):
        return jsonify({"error": "Invalid email format"}), 400

    # Check if this email already belongs to another account
    existing = User.query.filter(
        User.email == email,
        User.id != user.id,
    ).first()
    is_merge = bool(existing)

    otp = str(secrets.randbelow(900000) + 100000)  # 6-digit
    otp_hash = hashlib.sha256(otp.encode()).hexdigest()

    user.email_link_pending = email
    user.email_link_otp_hash = otp_hash
    user.email_link_otp_expires = datetime.utcnow() + timedelta(minutes=_OTP_EXPIRY_MINUTES)
    db.session.commit()

    _send_otp_email_async(
        current_app._get_current_object(),
        email,
        otp,
        is_merge=is_merge,
        display_name=user.full_name or user.telegram_first_name or "",
    )

    _log.info("link_email_request: user_id=%s email=%s is_merge=%s", user.id, email, is_merge)
    return jsonify({
        "status": "otp_sent",
        "merge": is_merge,
        "expires_in": _OTP_EXPIRY_MINUTES * 60,
    }), 200


# ── Email linking: step 2 — verify OTP + set password ─────────────────────────

@miniapp_bp.route("/link-email/verify", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def link_email_verify():
    user = User.query.get(int(get_jwt_identity()))
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json() or {}
    otp = (data.get("otp") or "").strip()
    password = data.get("password") or ""

    if not user.email_link_otp_hash or not user.email_link_pending:
        return jsonify({"error": "No pending email link request — start with /link-email/request"}), 400

    if datetime.utcnow() > user.email_link_otp_expires:
        return jsonify({"error": "OTP has expired — please request a new code"}), 400

    otp_hash = hashlib.sha256(otp.encode()).hexdigest()
    if not hmac.compare_digest(otp_hash, user.email_link_otp_hash):
        return jsonify({"error": "Invalid verification code"}), 400

    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400
    if len(password) > 128:
        return jsonify({"error": "Password too long (max 128 characters)"}), 400

    target_email = user.email_link_pending

    # ── Merge case: email already belongs to an existing account ──────────────
    existing = User.query.filter(
        User.email == target_email,
        User.id != user.id,
    ).first()

    if existing:
        # Transfer Telegram identity from the ghost (auto-created) account onto the
        # existing email account. Then transfer every user-owned resource before
        # deleting the ghost — covering all 38 tables that reference users.id.
        ghost_id = user.id
        target_id = existing.id

        existing.telegram_user_id = user.telegram_user_id
        existing.telegram_username = user.telegram_username
        existing.telegram_first_name = user.telegram_first_name
        existing.telegram_connected_at = user.telegram_connected_at
        existing.auth_provider = "both"

        # ── models.py tables ─────────────────────────────────────────────────
        # telegram_groups (owner_user_id, no CASCADE — must transfer explicitly)
        TelegramGroup.query.filter_by(owner_user_id=ghost_id).update({"owner_user_id": target_id})

        # user_telegram_accounts (CASCADE — but delete explicitly so the identity
        # lives on existing.telegram_user_id rather than a duplicate junction row)
        UserTelegramAccount.query.filter_by(user_id=ghost_id).delete()

        # telegram_group_link_codes (nullable user_id — transfer to keep history intact)
        from ..models import (
            TelegramConnectCode, Bot, UserApiKey, InviteLink,
            WorkspaceReminder, AutomationWorkflow, ForwardRule,
            Note, Task, BotDMMessage, AssistantConversationState,
            PendingReminderState, AutoReplyLog, WorkspaceKnowledgeDocument,
            DigestLog, Meeting, UserNotification,
            PendingInvoice, PaymentHistory, SubscriptionRenewal,
            PromoCodeUsage, CustomBot, Channel, DirectoryListing,
            PartnershipDeal, DealMessage, IntegrationWebhook,
            UserAssistantProfile, GoogleCalendarToken,
            AdminAuditLog, AssistantBot, TelegramGroupLinkCode,
            SuspiciousActivity,
        )
        from ..assistant.hub_models import (
            HubBotIdentity, HubBotSettings, HubConnectedGroup,
            HubExtractionBatch, HubTask, HubReminder, HubDecision,
            HubMeeting, HubNote, HubDigest, HubTemplate,
            HubMemoryGlobal, HubMemoryPerson, HubMemoryProject,
            HubMemoryGroupContext, HubMemorySuggestion,
            HubKnowledgeCard, HubInboxItem, HubFollowUp,
        )

        # bots (SQLAlchemy cascade="all, delete-orphan" on User.bots — must transfer
        # before delete so ORM doesn't cascade-delete rows we just reassigned)
        Bot.query.filter_by(user_id=ghost_id).update({"user_id": target_id})
        db.session.expire(user, ["bots"])

        # Tables with owner_user_id FK (no CASCADE — must transfer)
        WorkspaceReminder.query.filter_by(owner_user_id=ghost_id).update({"owner_user_id": target_id})
        AutomationWorkflow.query.filter_by(owner_user_id=ghost_id).update({"owner_user_id": target_id})
        ForwardRule.query.filter_by(owner_user_id=ghost_id).update({"owner_user_id": target_id})
        Meeting.query.filter_by(owner_user_id=ghost_id).update({"owner_user_id": target_id})
        CustomBot.query.filter_by(owner_user_id=ghost_id).update({"owner_user_id": target_id})

        # Tables with user_id FK (no CASCADE — must transfer)
        UserApiKey.query.filter_by(user_id=ghost_id).update({"user_id": target_id})
        Note.query.filter_by(user_id=ghost_id).update({"user_id": target_id})
        Task.query.filter_by(user_id=ghost_id).update({"user_id": target_id})
        BotDMMessage.query.filter_by(user_id=ghost_id).update({"user_id": target_id})
        AutoReplyLog.query.filter_by(user_id=ghost_id).update({"user_id": target_id})
        WorkspaceKnowledgeDocument.query.filter_by(user_id=ghost_id).update({"user_id": target_id})
        DigestLog.query.filter_by(user_id=ghost_id).update({"user_id": target_id})
        UserNotification.query.filter_by(user_id=ghost_id).update({"user_id": target_id})
        PendingInvoice.query.filter_by(user_id=ghost_id).update({"user_id": target_id})
        PaymentHistory.query.filter_by(user_id=ghost_id).update({"user_id": target_id})
        SubscriptionRenewal.query.filter_by(user_id=ghost_id).update({"user_id": target_id})
        PromoCodeUsage.query.filter_by(user_id=ghost_id).update({"user_id": target_id})

        # Referrals — two FKs (referrer_user_id, referred_user_id), a unique
        # referred_user_id, and a unique (referrer, referred) pair. Drop self-referrals
        # and rows that would collide with the target's existing referrals, then transfer
        # the survivors. Deletes are flushed first so the bulk UPDATEs can't hit a
        # unique-constraint violation mid-flush.
        target_has_referrer = Referral.query.filter_by(referred_user_id=target_id).first() is not None
        # (a) ghost as the referred party (1:1): keep target's existing referrer if any,
        #     and never let the referrer end up referring the merged target itself.
        gr = Referral.query.filter_by(referred_user_id=ghost_id).first()
        if gr and (target_has_referrer or gr.referrer_user_id == target_id):
            db.session.delete(gr)
        # (b) ghost as the referrer: drop rows that would self-refer or duplicate target's.
        for r in Referral.query.filter_by(referrer_user_id=ghost_id).all():
            collides = Referral.query.filter_by(
                referrer_user_id=target_id, referred_user_id=r.referred_user_id
            ).first()
            if r.referred_user_id == target_id or collides:
                db.session.delete(r)
        db.session.flush()
        Referral.query.filter_by(referred_user_id=ghost_id).update({"referred_user_id": target_id})
        Referral.query.filter_by(referrer_user_id=ghost_id).update({"referrer_user_id": target_id})

        # AssistantConversationState and PendingReminderState are 1:1 (unique on user_id).
        # Delete ghost rows — existing account may already have one, conflict would occur.
        AssistantConversationState.query.filter_by(user_id=ghost_id).delete()
        PendingReminderState.query.filter_by(user_id=ghost_id).delete()

        # Nullable FK tables — transfer to keep attribution
        InviteLink.query.filter_by(created_by_user_id=ghost_id).update({"created_by_user_id": target_id})
        TelegramGroupLinkCode.query.filter_by(user_id=ghost_id).update({"user_id": target_id})
        TelegramConnectCode.query.filter_by(user_id=ghost_id).delete()  # ephemeral, safe to drop
        SuspiciousActivity.query.filter_by(user_id=ghost_id).update({"user_id": target_id})

        # CASCADE tables — these auto-delete when ghost is deleted, but transfer
        # first to preserve data the user accumulated before linking email.
        # Channels have unique telegram_channel_id constraint — only transfer if
        # the existing account does NOT already have the same channel.
        ghost_channel_ids = {c.telegram_channel_id for c in Channel.query.filter_by(user_id=ghost_id).all()}
        existing_channel_ids = {c.telegram_channel_id for c in Channel.query.filter_by(user_id=target_id).all()}
        for ch_id in ghost_channel_ids - existing_channel_ids:
            Channel.query.filter_by(user_id=ghost_id, telegram_channel_id=ch_id).update({"user_id": target_id})
        # Channels that exist on both sides: drop ghost's copy (duplicate)
        for ch_id in ghost_channel_ids & existing_channel_ids:
            Channel.query.filter_by(user_id=ghost_id, telegram_channel_id=ch_id).delete()

        DirectoryListing.query.filter_by(user_id=ghost_id).update({"user_id": target_id})
        PartnershipDeal.query.filter_by(buyer_user_id=ghost_id).update({"buyer_user_id": target_id})
        PartnershipDeal.query.filter_by(seller_user_id=ghost_id).update({"seller_user_id": target_id})
        DealMessage.query.filter_by(sender_user_id=ghost_id).update({"sender_user_id": target_id})
        IntegrationWebhook.query.filter_by(user_id=ghost_id).update({"user_id": target_id})
        GoogleCalendarToken.query.filter_by(user_id=ghost_id).delete()  # OAuth — re-auth needed

        # AssistantBot is 1:1 per user (unique constraint). Transfer if existing has none.
        ghost_abot = AssistantBot.query.filter_by(user_id=ghost_id).first()
        existing_abot = AssistantBot.query.filter_by(user_id=target_id).first()
        if ghost_abot:
            if not existing_abot:
                ghost_abot.user_id = target_id
            else:
                db.session.delete(ghost_abot)  # existing account's bot takes precedence

        # UserAssistantProfile is 1:1. Transfer if existing has none.
        ghost_prof = UserAssistantProfile.query.filter_by(user_id=ghost_id).first()
        existing_prof = UserAssistantProfile.query.filter_by(user_id=target_id).first()
        if ghost_prof:
            if not existing_prof:
                ghost_prof.user_id = target_id
            else:
                db.session.delete(ghost_prof)

        # Hub models (all CASCADE) — transfer to preserve any data from Mini App use
        HubBotIdentity.query.filter_by(user_id=ghost_id).update({"user_id": target_id})
        HubBotSettings.query.filter_by(user_id=ghost_id).update({"user_id": target_id})
        HubConnectedGroup.query.filter_by(user_id=ghost_id).update({"user_id": target_id})
        HubExtractionBatch.query.filter_by(user_id=ghost_id).update({"user_id": target_id})
        HubTask.query.filter_by(user_id=ghost_id).update({"user_id": target_id})
        HubReminder.query.filter_by(user_id=ghost_id).update({"user_id": target_id})
        HubDecision.query.filter_by(user_id=ghost_id).update({"user_id": target_id})
        HubMeeting.query.filter_by(user_id=ghost_id).update({"user_id": target_id})
        HubNote.query.filter_by(user_id=ghost_id).update({"user_id": target_id})
        HubDigest.query.filter_by(user_id=ghost_id).update({"user_id": target_id})
        HubTemplate.query.filter_by(user_id=ghost_id).update({"user_id": target_id})
        HubKnowledgeCard.query.filter_by(user_id=ghost_id).update({"user_id": target_id})
        HubInboxItem.query.filter_by(user_id=ghost_id).update({"user_id": target_id})
        HubFollowUp.query.filter_by(user_id=ghost_id).update({"user_id": target_id})

        # Hub memory tables are 1:1 per user — transfer if existing has none, else drop
        for GhostModel, ghost_attr in [
            (HubMemoryGlobal, "user_id"),
            (HubMemoryPerson, "user_id"),
            (HubMemoryProject, "user_id"),
            (HubMemoryGroupContext, "user_id"),
            (HubMemorySuggestion, "user_id"),
        ]:
            ghost_rows = GhostModel.query.filter_by(user_id=ghost_id).all()
            existing_rows = GhostModel.query.filter_by(user_id=target_id).all()
            if ghost_rows and not existing_rows:
                GhostModel.query.filter_by(user_id=ghost_id).update({"user_id": target_id})
            elif ghost_rows:
                GhostModel.query.filter_by(user_id=ghost_id).delete()

        # Now it is safe to delete the ghost user — all FK references resolved
        db.session.flush()
        db.session.delete(user)
        db.session.flush()

        try:
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            _log.error("link_email_verify merge failed: %s", exc)
            return jsonify({"error": "Account merge failed — please try again"}), 500

        new_token = create_access_token(identity=str(existing.id))
        new_refresh = create_refresh_token(identity=str(existing.id))
        _log.info("link_email_verify: merged tg_id=%s into existing user_id=%s",
                  existing.telegram_user_id, existing.id)
        merge_resp = jsonify({
            "status": "merged",
            "token": new_token,
            "user": existing.to_dict(),
            "groups": _user_groups(existing),
        })
        _set_miniapp_cookies(merge_resp, new_token, new_refresh)
        return merge_resp, 200

    # ── Normal case: link email to the current Telegram-only account ──────────
    pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    user.email = target_email
    user.password_hash = pw_hash
    user.email_verified = False
    user.auth_provider = "both"
    user.email_link_otp_hash = None
    user.email_link_otp_expires = None
    user.email_link_pending = None

    # Generate and store email verification token
    verification_token = user.generate_verification_token()

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        _log.error("link_email_verify commit failed: %s", exc)
        return jsonify({"error": "Failed to save email — please try again"}), 500

    # Send verification email (non-blocking)
    _send_verification_email_async(
        current_app._get_current_object(),
        target_email,
        user.full_name or "",
        verification_token,
    )

    _log.info("link_email_verify: linked email=%s to user_id=%s", target_email, user.id)
    return jsonify({
        "status": "linked",
        "user": user.to_dict(),
    }), 200
