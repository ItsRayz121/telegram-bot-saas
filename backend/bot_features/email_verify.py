"""Shared in-bot email verification + password setup (official and custom bots).

Lets a Telegram user optionally attach an email + password to their Telegizer
account so they can ALSO log in on the website — without breaking Telegram-only
login (the password is purely additive). The flow is never forced.

Conversation state lives in ``context.user_data`` (per-user, per-bot). A short-lived
6-digit code is held in memory keyed by Telegram user id (10-minute TTL). The user's
password message is deleted immediately and the password/code are never logged.

Both bot runners (``official_bot`` and ``bot_manager``) call into here so the flow
stays identical across every bot, per the bot-lineage rule.
"""
import logging
import re
import secrets
import time

import bcrypt
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

_log = logging.getLogger("email_verify")

# tg_user_id -> {"email", "pw_hash", "code", "expires", "attempts"}
_pending: dict = {}

_CODE_TTL = 600          # 10 minutes
_MAX_CODE_ATTEMPTS = 5
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# context.user_data key holding the current stage: "email" | "password" | "code"
_STAGE = "ev_stage"


def _back_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("« Back to Menu", callback_data="menu:main")]])


def is_active(context) -> bool:
    """True when this user is mid email-verification (so the text handler routes here)."""
    try:
        return bool(context.user_data.get(_STAGE))
    except Exception:
        return False


def _clear(context, tg_user_id=None):
    try:
        context.user_data.pop(_STAGE, None)
    except Exception:
        pass
    if tg_user_id is not None:
        _pending.pop(tg_user_id, None)


def cancel(context):
    """Abort any in-progress verification (e.g. user navigated away via a menu button)."""
    _clear(context)


async def start(update, context, flask_app, resolve_user):
    """Entry point from the `menu:email_verify` callback.

    resolve_user(tg_id) -> User | None  (each bot passes its own lookup).
    """
    chat_id = update.effective_chat.id
    tg_id = update.effective_user.id

    already_verified = False
    current_email = None
    if flask_app:
        try:
            with flask_app.app_context():
                u = resolve_user(tg_id)
                if u and getattr(u, "email_verified", False) and u.email:
                    already_verified = True
                    current_email = u.email
        except Exception as exc:
            _log.debug("email_verify start lookup failed: %s", exc)

    if already_verified:
        _clear(context, tg_id)
        await context.bot.send_message(
            chat_id,
            f"✅ *Email Verified*\n\nYour account email is `{current_email}`.\n\n"
            "You can log in on the website with this email and your password.",
            parse_mode="Markdown",
            reply_markup=_back_kb(),
        )
        return

    context.user_data[_STAGE] = "email"
    _pending.pop(tg_id, None)
    await context.bot.send_message(
        chat_id,
        "📧 *Email Verification* _(optional)_\n\n"
        "Add an email + password so you can also sign in on the website. "
        "Your Telegram login keeps working either way.\n\n"
        "*Step 1 of 3* — send me the email address you'd like to use:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✖️ Cancel", callback_data="menu:main"),
        ]]),
    )


async def handle_text(update, context, flask_app, resolve_user) -> bool:
    """Process an email/password/code message. Returns True if it was consumed."""
    stage = context.user_data.get(_STAGE)
    if not stage:
        return False

    chat_id = update.effective_chat.id
    tg_id = update.effective_user.id
    text = (update.message.text or "").strip()

    # ── Step 1: email ─────────────────────────────────────────────────────────
    if stage == "email":
        if not _EMAIL_RE.match(text):
            await context.bot.send_message(
                chat_id, "❌ That doesn't look like a valid email. Please send a valid address:",
            )
            return True
        email = text.lower()

        # Reject emails already owned by a *different* account up front (friendlier
        # than failing at the end). The final save re-checks atomically.
        conflict = False
        if flask_app:
            try:
                with flask_app.app_context():
                    from ..models import User
                    me = resolve_user(tg_id)
                    other = User.query.filter(User.email == email).first()
                    if other and (not me or other.id != me.id):
                        conflict = True
            except Exception as exc:
                _log.debug("email_verify email check failed: %s", exc)
        if conflict:
            await context.bot.send_message(
                chat_id,
                "⚠️ That email is already registered to another account.\n\n"
                "Log in on the website instead, or send a different email:",
            )
            return True

        _pending[tg_id] = {"email": email, "expires": time.time() + _CODE_TTL}
        context.user_data[_STAGE] = "password"
        await context.bot.send_message(
            chat_id,
            "*Step 2 of 3* — now send a password (min 8 characters).\n\n"
            "🔒 I'll delete your password message immediately for safety.",
            parse_mode="Markdown",
        )
        return True

    # ── Step 2: password ──────────────────────────────────────────────────────
    if stage == "password":
        # Delete the password message right away — never leave it in chat history.
        try:
            await context.bot.delete_message(chat_id, update.message.message_id)
        except Exception:
            pass

        pending = _pending.get(tg_id)
        if not pending:
            _clear(context, tg_id)
            await context.bot.send_message(
                chat_id, "⌛ That session expired. Tap *Email Verification* again.",
                parse_mode="Markdown", reply_markup=_back_kb(),
            )
            return True

        if len(text) < 8:
            await context.bot.send_message(
                chat_id, "❌ Password too short (min 8 characters). Send a longer one:",
            )
            return True
        if len(text) > 128:
            await context.bot.send_message(
                chat_id, "❌ Password too long (max 128 characters). Send a shorter one:",
            )
            return True

        pending["pw_hash"] = bcrypt.hashpw(text.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        code = f"{secrets.randbelow(900000) + 100000}"
        pending["code"] = code
        pending["expires"] = time.time() + _CODE_TTL
        pending["attempts"] = 0

        # Email the code (best-effort).
        sent = False
        if flask_app:
            try:
                with flask_app.app_context():
                    from ..notifications import send_verification_code_email
                    me = resolve_user(tg_id)
                    name = (getattr(me, "full_name", None)
                            or update.effective_user.first_name or "there")
                    sent = send_verification_code_email(pending["email"], name, code)
            except Exception as exc:
                _log.error("email_verify code send failed: %s", exc)

        context.user_data[_STAGE] = "code"
        if sent:
            await context.bot.send_message(
                chat_id,
                f"*Step 3 of 3* — I emailed a 6-digit code to `{pending['email']}`.\n\n"
                "Send the code here to finish (it expires in 10 minutes):",
                parse_mode="Markdown",
            )
        else:
            _clear(context, tg_id)
            await context.bot.send_message(
                chat_id,
                "❌ I couldn't send the verification email right now. Please try again later.",
                reply_markup=_back_kb(),
            )
        return True

    # ── Step 3: code ──────────────────────────────────────────────────────────
    if stage == "code":
        pending = _pending.get(tg_id)
        if not pending or pending.get("expires", 0) < time.time():
            _clear(context, tg_id)
            await context.bot.send_message(
                chat_id, "⌛ That code expired. Tap *Email Verification* to start again.",
                parse_mode="Markdown", reply_markup=_back_kb(),
            )
            return True

        pending["attempts"] = pending.get("attempts", 0) + 1
        if pending["attempts"] > _MAX_CODE_ATTEMPTS:
            _clear(context, tg_id)
            await context.bot.send_message(
                chat_id, "🚫 Too many attempts. Tap *Email Verification* to start again.",
                parse_mode="Markdown", reply_markup=_back_kb(),
            )
            return True

        if re.sub(r"\D", "", text) != pending["code"]:
            await context.bot.send_message(chat_id, "❌ Incorrect code. Try again:")
            return True

        # ── Verified — persist email + password, keep Telegram link intact ──────
        ok, err = _finalize(flask_app, resolve_user, tg_id, pending,
                            update.effective_user)
        _clear(context, tg_id)
        if ok:
            await context.bot.send_message(
                chat_id,
                f"✅ *Email verified!*\n\nYou can now sign in on the website with "
                f"`{pending['email']}` and your password. Your Telegram login still works too.",
                parse_mode="Markdown", reply_markup=_back_kb(),
            )
        else:
            await context.bot.send_message(
                chat_id, f"❌ {err or 'Could not save. Please try again later.'}",
                reply_markup=_back_kb(),
            )
        return True

    return False


def _finalize(flask_app, resolve_user, tg_id, pending, tg_user) -> tuple:
    """Persist email/password to the user (find-or-create). Returns (ok, error)."""
    if not flask_app:
        return False, "Service temporarily unavailable."
    try:
        with flask_app.app_context():
            from ..models import db, User
            email = pending["email"]
            pw_hash = pending["pw_hash"]

            me = resolve_user(tg_id)
            # Email must not belong to a *different* account.
            other = User.query.filter(User.email == email).first()
            if other and (not me or other.id != me.id):
                return False, "That email is already registered to another account."

            if me:
                me.email = email
                me.password_hash = pw_hash
                me.email_verified = True
                if me.auth_provider == "telegram":
                    me.auth_provider = "both"
                me.get_or_create_referral_code()
            else:
                me = User(
                    email=email,
                    password_hash=pw_hash,
                    full_name=(tg_user.first_name or "Telegram user"),
                    auth_provider="both",
                    email_verified=True,
                    telegram_user_id=str(tg_id),
                )
                me.get_or_create_referral_code()
                db.session.add(me)
            db.session.commit()
            return True, None
    except Exception as exc:
        _log.error("email_verify finalize failed (tg %s): %s", tg_id, exc)
        try:
            from ..models import db
            db.session.rollback()
        except Exception:
            pass
        return False, "Could not save. Please try again later."
