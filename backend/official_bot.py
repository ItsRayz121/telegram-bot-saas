"""
Official Telegizer shared bot.

Key design decisions:
- flask_app (not app_context) stored in bot_data; every handler creates
  a FRESH with flask_app.app_context() per call.
- /start connect_<code>: links Telegram user ID to website account, then
  auto-links any pending groups created by this Telegram user.
- /linkgroup: if the running user already has a linked website account,
  the group is linked directly (no code exchange needed).  Otherwise
  a TLG-XXXXXXXX code is generated and DMed privately.
- on_private_text: accepts bot tokens from linked users when
  context.user_data["awaiting_bot_token"] is True.  The token message
  is deleted immediately and rate-limited to 3 attempts per 10 min.
- Tokens and codes are never logged.
"""

import asyncio
import logging
import random
import re
import threading
from datetime import datetime, timedelta

import requests as _http

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand, ChatPermissions, WebAppInfo
from telegram.constants import ChatType, ParseMode
from telegram.error import Forbidden, BadRequest
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ChatMemberHandler, ContextTypes, filters,
)
try:
    from telegram.ext import MessageReactionHandler as _MsgReactionHandler
    _REACTION_HANDLER_AVAILABLE = True
except ImportError:
    _REACTION_HANDLER_AVAILABLE = False

from .config import Config
from .group_defaults import apply_group_defaults, fill_missing_defaults
from .bot_features.group_context import GroupContext
from .bot_features.welcome import WelcomeSystem
from .bot_features.moderation import (
    normalize_homoglyphs,
    URL_PATTERN as _URL_RE,
    TELEGRAM_LINK_PATTERN as _TELEGRAM_LINK_RE,
    EMAIL_PATTERN as _EMAIL_RE,
    EMOJI_PATTERN as _EMOJI_RE,
    LANGUAGE_RANGES as _LANG_RANGES,
)
from .bot_features.levels import level_from_xp as _level_from_xp, xp_for_level as _xp_for_level

_log = logging.getLogger(__name__)

# ─── Meeting link detection patterns (compiled once at module load) ───────────
_MEETING_URL_RE = re.compile(
    r"https?://(?:"
    r"(?:[\w-]+\.)?zoom\.us/[jJwW]/[\w?=&%-]+"
    r"|meet\.google\.com/[a-z]{3}-[a-z]{4}-[a-z]{3}"
    r"|teams\.microsoft\.com/l/meetup-join/[\w%./!@#$^&*()_+=-]+"
    r"|(?:[\w-]+\.)?calendly\.com/[\w/-]+"
    r"|(?:[\w-]+\.)?webex\.com/meet/[\w/-]+"
    r"|goto(?:meeting|webinar)\.com/join/\d+"
    r")",
    re.IGNORECASE,
)
_MEETING_PLATFORM_MAP = [
    ("zoom",        re.compile(r"zoom\.us", re.I)),
    ("meet",        re.compile(r"meet\.google\.com", re.I)),
    ("teams",       re.compile(r"teams\.microsoft\.com", re.I)),
    ("calendly",    re.compile(r"calendly\.com", re.I)),
    ("webex",       re.compile(r"webex\.com", re.I)),
    ("gotomeeting", re.compile(r"gotomeeting\.com|gotowebinar\.com", re.I)),
]

# ─── Telegram ToS outgoing rate limiter ──────────────────────────────────────
# Telegram's Bot API allows at most 20 messages/second globally, but for a
# single group the recommended limit is much lower. We enforce 20 msg/min
# per group to stay well under ToS limits and avoid getting the shared bot
# banned for flooding.

_OUTGOING_RATE_LIMIT = 20   # messages per minute per group


def _can_send_to_group(group_id: str, limit: int = _OUTGOING_RATE_LIMIT) -> bool:
    """Return True if we are under the per-group outgoing rate limit.

    Uses Redis INCR + EXPIRE for an atomic sliding-window check. Falls back
    to True (allow) when Redis is unavailable so messages are never silently
    dropped due to a Redis outage.
    """
    try:
        import redis as _redis
        r = _redis.from_url(
            Config.REDIS_URL or "redis://localhost:6379/0",
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        key = f"bot_send_rate:{group_id}"
        count = r.incr(key)
        if count == 1:
            r.expire(key, 60)
        if count > limit:
            _log.warning(
                "[OfficialBot] Per-group send rate limit hit for group=%s (count=%d > %d/min) — skipping",
                group_id, count, limit,
            )
            return False
        return True
    except Exception:
        return True  # Redis down — allow (degrade gracefully)


def _user_by_tg_id(tg_id: str):
    """Two-step lookup: legacy User.telegram_user_id first, then UserTelegramAccount junction table.
    Always use this instead of User.query.filter_by(telegram_user_id=...) directly.
    """
    from .models import User, UserTelegramAccount
    user = User.query.filter_by(telegram_user_id=str(tg_id)).first()
    if not user:
        acct = UserTelegramAccount.query.filter_by(telegram_user_id=str(tg_id)).first()
        if acct:
            user = User.query.get(acct.user_id)
    return user


# ─── In-process verification state ───────────────────────────────────────────
# Key: "{chat_id}:{user_id}" → {method, msg_id, answer, expires_at, ...}
# Phase 3 item 15: move to Redis/DB for persistence across restarts.
_pending_verifications: dict = {}

# ─── DM mode state ────────────────────────────────────────────────────────────
# Tracks whether each user is in "assistant" mode or "menu" mode in private chat.
# Resets to "menu" on bot restart (intentional — safe default).
# Key: telegram user_id (int) → "menu" | "assistant"
_dm_modes: dict[int, str] = {}


def _get_dm_mode(user_id: int) -> str:
    return _dm_modes.get(user_id, "menu")


def _set_dm_mode(user_id: int, mode: str) -> None:
    _dm_modes[user_id] = mode


def _save_pending_verification(flask_app, chat_id: int, user_id: int, pending: dict):
    """Write-through: persist a pending verification to the DB."""
    if not flask_app:
        return
    try:
        with flask_app.app_context():
            from .models import db, PendingVerification
            row = PendingVerification.query.filter_by(
                chat_id=chat_id, user_id=user_id
            ).first()
            if not row:
                row = PendingVerification(chat_id=chat_id, user_id=user_id)
                db.session.add(row)
            row.method = pending.get("method", "button")
            row.msg_id = pending.get("msg_id")
            row.answer = str(pending.get("answer", "")) if pending.get("answer") is not None else None
            row.expires_at = pending["expires_at"]
            row.kick_on_fail = bool(pending.get("kick_on_fail", True))
            row.max_attempts = int(pending.get("max_attempts", 3))
            row.attempts = int(pending.get("attempts", 0))
            db.session.commit()
    except Exception as exc:
        _log.debug("_save_pending_verification failed: %s", exc)


def _remove_pending_verification(flask_app, chat_id: int, user_id: int):
    """Delete a pending verification from DB."""
    if not flask_app:
        return
    try:
        with flask_app.app_context():
            from .models import db, PendingVerification
            PendingVerification.query.filter_by(
                chat_id=chat_id, user_id=user_id
            ).delete()
            db.session.commit()
    except Exception as exc:
        _log.debug("_remove_pending_verification failed: %s", exc)


def _load_pending_verifications_from_db(flask_app):
    """On startup: load non-expired verifications from DB into memory dict."""
    if not flask_app:
        return
    try:
        with flask_app.app_context():
            from .models import PendingVerification
            rows = PendingVerification.query.filter(
                PendingVerification.expires_at > datetime.utcnow()
            ).all()
            for row in rows:
                key = f"{row.chat_id}:{row.user_id}"
                _pending_verifications[key] = {
                    "method": row.method,
                    "msg_id": row.msg_id,
                    "answer": row.answer,
                    "expires_at": row.expires_at,
                    "kick_on_fail": row.kick_on_fail,
                    "max_attempts": row.max_attempts,
                    "attempts": row.attempts,
                }
            _log.info("[OfficialBot] Restored %d pending verifications from DB", len(rows))
    except Exception as exc:
        _log.warning("[OfficialBot] Failed to load pending verifications from DB: %s", exc)

# ─── AutoMod patterns — imported from bot_features/moderation.py ─────────────
# _URL_RE, _TELEGRAM_LINK_RE, _EMAIL_RE, _EMOJI_RE, _LANG_RANGES are imported above.
# Spam rate tracker — {"{chat_id}:{user_id}": [datetime, ...]}
_spam_tracker: dict = {}
# Per-(chat,user) cooldown for the OPTIONAL Smart AI Moderation layer.
_official_ai_cooldown: dict = {}

# Default word list for word-method verification
_DEFAULT_VERIFY_WORDS = [
    ("python", "What programming language is named after a snake?"),
    ("blue",   "What color is the sky on a clear day?"),
    ("five",   "How many fingers are on one hand? (write the word)"),
    ("moon",   "What orbits the Earth at night and reflects sunlight?"),
    ("water",  "What liquid do humans drink to stay alive?"),
]


# ─── Tiny DB helpers ──────────────────────────────────────────────────────────

def _log_event(flask_app, group_id, event_type, message=None, meta=None):
    try:
        with flask_app.app_context():
            from .models import db, BotEvent
            db.session.add(BotEvent(
                telegram_group_id=str(group_id) if group_id else None,
                event_type=event_type,
                message=message,
                metadata_=meta or {},
            ))
            db.session.commit()
    except Exception as exc:
        _log.debug("BotEvent log failed (%s): %s", event_type, exc)


def _upsert_group(flask_app, group_id: str, title: str, username=None):
    try:
        with flask_app.app_context():
            from .models import db, TelegramGroup
            tg = TelegramGroup.query.filter_by(telegram_group_id=group_id).first()
            if not tg:
                tg = TelegramGroup(
                    telegram_group_id=group_id, title=title,
                    username=username, bot_status="pending",
                )
                fill_missing_defaults(tg)
                db.session.add(tg)
            else:
                tg.title = title
                # Fill in any setting sections added since this group was first seen.
                fill_missing_defaults(tg)
            db.session.commit()
    except Exception as exc:
        _log.debug("_upsert_group failed: %s", exc)


async def _refresh_permissions(bot, group_id: str, flask_app):
    """Fetch live bot permissions from Telegram and persist them to the DB cache."""
    try:
        me = await bot.get_chat_member(chat_id=int(group_id), user_id=bot.id)
        # Mirror _PERMISSION_DEFS in official_settings.py — only real Telegram API fields.
        perms = {
            "can_delete_messages":    getattr(me, "can_delete_messages",    False) or False,
            "can_restrict_members":   getattr(me, "can_restrict_members",   False) or False,
            "can_pin_messages":       getattr(me, "can_pin_messages",       False) or False,
            "can_manage_chat":        getattr(me, "can_manage_chat",        False) or False,
            "can_invite_users":       getattr(me, "can_invite_users",       False) or False,
            "can_promote_members":    getattr(me, "can_promote_members",    False) or False,
            "can_change_info":        getattr(me, "can_change_info",        False) or False,
            "can_manage_video_chats": getattr(me, "can_manage_video_chats", False) or False,
        }
        with flask_app.app_context():
            from .models import db, TelegramGroup
            tg = TelegramGroup.query.filter_by(telegram_group_id=group_id).first()
            if tg:
                tg.bot_permissions = perms
                tg.bot_status = "active"
                db.session.commit()
        return perms
    except Exception as exc:
        _log.debug("_refresh_permissions failed for group %s: %s", group_id, exc)
        return {}


def _bot_username():
    raw = Config.TELEGRAM_BOT_USERNAME or "telegizer_bot"
    return raw.strip().lstrip("@").split("/")[-1]


def _frontend():
    return Config.FRONTEND_URL or "https://telegizer.com"


# ─── /start ───────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != ChatType.PRIVATE:
        return

    flask_app = context.bot_data.get("flask_app")
    user = update.effective_user
    first = user.first_name or "there"
    frontend = _frontend()
    bot_un = _bot_username()
    args = context.args or []

    _log.info("[OfficialBot] /start from tg_user=%s username=%s args=%s flask_app=%s",
              user.id, user.username, args, "ok" if flask_app else "MISSING")

    # ── Record that this user has started the bot (enables private DMs) ───────
    if flask_app:
        try:
            with flask_app.app_context():
                from .models import db, TelegramBotStarted
                TelegramBotStarted.record(user.id)
                db.session.commit()
        except Exception as _exc:
            _log.debug("TelegramBotStarted.record failed: %s", _exc)

    # ── Handle ?start=connect_<code> deep-link ────────────────────────────────
    if args and args[0].startswith("connect_"):
        code = args[0][len("connect_"):]
        if flask_app:
            await _handle_account_connect(update, context, user, flask_app, frontend, bot_un, code)
        else:
            await update.message.reply_text("⚠️ Service temporarily unavailable. Try again shortly.")
        return

    # ── Handle ?start=ref_<code> referral deep-link ───────────────────────────
    # The account doesn't exist yet (it's auto-created when the Mini App opens), so
    # stash the referral code keyed by Telegram user ID for miniapp_auth to consume.
    if flask_app and args and args[0].startswith("ref_"):
        ref_code = args[0][len("ref_"):].strip()
        if ref_code:
            try:
                with flask_app.app_context():
                    from .models import db, TelegramBotStarted
                    # Ignore if this user already has an account (returning user, not a new referral)
                    if not _user_by_tg_id(user.id):
                        TelegramBotStarted.set_pending_referral(user.id, ref_code)
                        db.session.commit()
            except Exception as _exc:
                _log.debug("pending referral capture failed: %s", _exc)

    # ── Regular /start: companion hub ────────────────────────────────────────
    pending_groups = []
    is_linked = False
    tg_username_on_account = None

    if flask_app:
        try:
            with flask_app.app_context():
                from .models import TelegramConnectCode, TelegramGroup, User
                website_user = _user_by_tg_id(user.id)
                is_linked = website_user is not None
                if website_user:
                    tg_username_on_account = website_user.email

                codes = TelegramConnectCode.query if False else None  # unused path below
                from .models import TelegramGroupLinkCode
                codes = TelegramGroupLinkCode.query.filter_by(
                    created_by_telegram_user_id=str(user.id),
                    used_at=None,
                ).filter(
                    TelegramGroupLinkCode.expires_at > datetime.utcnow()
                ).all()
                for c in codes:
                    tg = TelegramGroup.query.filter_by(
                        telegram_group_id=c.telegram_group_id
                    ).first()
                    if tg and not tg.owner_user_id:
                        pending_groups.append({
                            "title": tg.title,
                            "code": c.code,
                            "group_id": tg.telegram_group_id,
                        })
        except Exception as exc:
            _log.debug("cmd_start context fetch failed: %s", exc)

    text = (
        f"👋 *Welcome, {first}! I'm your Telegizer control center.*\n\n"
        "Here's what I can do:\n\n"
        "🏘️ *Group Management*\n"
        "• Add groups, set up automod, welcome messages\n"
        "• Track XP, run verification flows\n"
        "• Schedule announcements & digests\n\n"
        "🤖 *Bot Control*\n"
        "• Connect your own Telegram bot\n"
        "• Configure custom commands & auto-replies\n\n"
        "🧠 *AI + Automation*\n"
        "• AI assistant that watches your groups\n"
        "• Smart reminders, meeting capture, task tracking\n\n"
        "Just tap a button below or type a command."
    )

    keyboard = [
        # Row 0 — primary CTA: open Mini App (Telegram-first auth, zero friction)
        [
            InlineKeyboardButton("🚀 Open Telegizer App", web_app=WebAppInfo(url=f"{frontend}/mini-app")),
        ],
    ]

    if pending_groups:
        keyboard.append([
            InlineKeyboardButton(
                f"⚠️ {len(pending_groups)} Group(s) Awaiting Setup",
                callback_data="menu:pending_groups",
            )
        ])

    keyboard += [
        # Row 1 — core group actions
        [
            InlineKeyboardButton("➕ Add Group", callback_data="menu:add_group"),
            InlineKeyboardButton("📋 My Groups", callback_data="menu:my_groups"),
        ],
        # Row 2 — bot management
        [
            InlineKeyboardButton("🤖 My Bots", callback_data="menu:my_bots"),
            InlineKeyboardButton("🔌 Connect Own Bot", callback_data="menu:connect_bot"),
        ],
        # Row 3 — power features
        [
            InlineKeyboardButton("🧠 AI Assistant", callback_data="menu:ai_assistant"),
            InlineKeyboardButton("⚡ Automations", url=f"{frontend}/workspace/automations"),
        ],
        # Row 4 — utility
        [
            InlineKeyboardButton("💬 Support", callback_data="menu:support"),
            InlineKeyboardButton("⚙️ Quick Settings", callback_data="qs:groups"),
        ],
    ]

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def _handle_account_connect(update, context, user, flask_app, frontend, bot_un, code):
    """Process /start connect_<code>: link Telegram identity to website account."""
    _log.info("[OfficialBot] account_connect attempt tg_user=%s code_prefix=%s", user.id, code[:8])
    linked_email = None
    error_msg = None
    auto_linked_groups = []

    try:
        with flask_app.app_context():
            from .models import db, TelegramConnectCode, User, TelegramGroup, TelegramGroupLinkCode

            tc = TelegramConnectCode.query.filter_by(code=code, used_at=None).filter(
                TelegramConnectCode.expires_at > datetime.utcnow()
            ).first()

            if not tc:
                error_msg = "❌ This link has expired or already been used.\n\nGenerate a new one from *Settings → Connect Telegram* on the website."
            else:
                # Check if this Telegram account is already linked to a different user
                from .models import UserTelegramAccount
                tg_id_str = str(user.id)
                existing = User.query.filter_by(telegram_user_id=tg_id_str).first()
                existing_linked = UserTelegramAccount.query.filter_by(telegram_user_id=tg_id_str).first()
                already_other_user = (
                    (existing and existing.id != tc.user_id) or
                    (existing_linked and existing_linked.user_id != tc.user_id)
                )
                if already_other_user:
                    error_msg = "❌ This Telegram account is already linked to a different Telegizer account.\n\nDisconnect it first from Settings on the website."
                else:
                    website_user = User.query.get(tc.user_id)
                    if not website_user:
                        error_msg = "❌ Website account not found."
                    else:
                        # Backfill legacy primary columns on first connect
                        if not website_user.telegram_user_id:
                            website_user.telegram_user_id = tg_id_str
                            website_user.telegram_username = user.username
                            website_user.telegram_first_name = user.first_name
                            website_user.telegram_connected_at = datetime.utcnow()

                        # Upsert into UserTelegramAccount for all accounts (primary + additional)
                        is_primary = not bool(
                            UserTelegramAccount.query.filter_by(user_id=website_user.id).first()
                        )
                        if not existing_linked or existing_linked.user_id != website_user.id:
                            new_linked = UserTelegramAccount(
                                user_id=website_user.id,
                                telegram_user_id=tg_id_str,
                                telegram_username=user.username,
                                telegram_first_name=user.first_name,
                                is_primary=is_primary,
                            )
                            db.session.add(new_linked)

                        tc.used_at = datetime.utcnow()
                        tc.telegram_user_id = tg_id_str
                        linked_email = website_user.email
                        _log.info("[OfficialBot] account_connect success tg_user=%s linked_to_user_id=%s email=%s",
                                  user.id, website_user.id, linked_email)

                        # Auto-link any pending groups this Telegram user created
                        pending_codes = TelegramGroupLinkCode.query.filter_by(
                            created_by_telegram_user_id=str(user.id),
                            used_at=None,
                        ).filter(
                            TelegramGroupLinkCode.expires_at > datetime.utcnow()
                        ).all()
                        for pc in pending_codes:
                            tg = TelegramGroup.query.filter_by(
                                telegram_group_id=pc.telegram_group_id,
                                owner_user_id=None,
                            ).first()
                            if tg:
                                tg.owner_user_id = website_user.id
                                tg.bot_status = "active"
                                tg.linked_at = datetime.utcnow()
                                tg.linked_via_bot_type = "official"
                                tg.group_context = "group_management"
                                pc.used_at = datetime.utcnow()
                                auto_linked_groups.append(tg.title)

                        db.session.commit()
    except Exception as exc:
        _log.error("Account connect failed for tg user %s: %s", user.id, exc)
        error_msg = "❌ An error occurred. Please try again."

    if error_msg:
        await update.message.reply_text(
            error_msg,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🖥️ Go to Settings", url=f"{frontend}/settings")],
            ]),
        )
        return

    lines = [
        f"✅ *Telegram connected successfully.*\n\n"
        f"Your Telegram is now linked with your Telegizer account ({linked_email}).\n\n"
        f"• Groups added by you will belong to your account\n"
        f"• Custom bot tokens sent here are saved under your account\n"
        f"• My Groups / My Bots in this bot show only your data"
    ]
    if auto_linked_groups:
        lines.append(f"\n\n🔗 *Auto-linked {len(auto_linked_groups)} pending group(s):*")
        for title in auto_linked_groups[:5]:
            lines.append(f"• {title}")

    await update.message.reply_text(
        "".join(lines),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 My Groups", url=f"{frontend}/my-groups")],
            [InlineKeyboardButton("🖥️ Open Dashboard", url=frontend)],
        ]),
    )

    _log_event(flask_app, None, "telegram_account_connected",
               f"tg user {user.id} linked to {linked_email}",
               {"telegram_user_id": str(user.id)})


# ─── /help ────────────────────────────────────────────────────────────────────

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_un = _bot_username()
    frontend = _frontend()
    await update.message.reply_text(
        "*Telegizer Help*\n\n"
        "*How to link your account:*\n"
        f"1. Go to {frontend}/settings → Connect Telegram\n"
        "2. Click the link to open this bot\n"
        "3. Your Telegram is now linked!\n\n"
        "*How to link a group:*\n"
        f"1. Add @{bot_un} to your Telegram group as admin\n"
        "2. Run `/linkgroup` inside the group\n"
        "3. If your account is linked, the group links automatically\n"
        "4. Otherwise, paste the code at Dashboard → Add Group\n\n"
        "*Group commands:*\n"
        "`/linkgroup` — start the link flow (run in group)\n"
        "`/status` — check bot status & permissions\n\n"
        "*Private commands:*\n"
        "`/start` — open companion hub\n\n"
        "*Support:*\n"
        "📢 [Official Channel](https://t.me/telegizer)\n"
        "👥 [Community Group](https://t.me/telegizer_community)\n"
        "✉️ fazalelahi5577@gmail.com\n\n"
        f"Dashboard: {frontend}",
        parse_mode=ParseMode.MARKDOWN,
    )


# ─── 1-B-05: Bot permissions extractor ───────────────────────────────────────

def extract_bot_permissions(bot_member) -> dict:
    """Extract and score bot permissions from a ChatMember object."""
    perms = {
        "can_delete_messages":  getattr(bot_member, "can_delete_messages", False),
        "can_restrict_members": getattr(bot_member, "can_restrict_members", False),
        "can_ban_users":        getattr(bot_member, "can_restrict_members", False),
        "can_pin_messages":     getattr(bot_member, "can_pin_messages", False),
        "can_invite_users":     getattr(bot_member, "can_invite_users", False),
        "can_change_info":      getattr(bot_member, "can_change_info", False),
        "can_manage_chat":      getattr(bot_member, "can_manage_chat", False),
        "can_send_messages":    True,
    }
    score = sum(1 for v in perms.values() if v) / len(perms) * 100
    perms["permission_score"] = int(score)
    if score == 100:
        perms["access_tier"] = "Full Access"
    elif score >= 50:
        perms["access_tier"] = "Partial Access"
    else:
        perms["access_tier"] = "Limited Access"
    return perms


# ─── /linkgroup ───────────────────────────────────────────────────────────────

async def cmd_linkgroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Group-only. If the running user has a linked website account the group is
    linked directly.  Otherwise a private code is generated and DMed.
    """
    chat = update.effective_chat
    user = update.effective_user
    flask_app = context.bot_data.get("flask_app")
    frontend = _frontend()

    if chat.type == ChatType.PRIVATE:
        await update.message.reply_text(
            "⚠️ Use `/linkgroup` *inside your Telegram group*, not here.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if not flask_app:
        await update.message.reply_text("⚠️ Service temporarily unavailable. Try again shortly.")
        return

    try:
        cm = await context.bot.get_chat_member(chat.id, user.id)
        if cm.status not in ("creator", "administrator"):
            await update.message.reply_text("❌ Only group admins can link this group.")
            return
    except Exception:
        pass

    # ── 1-B-03: Dashboard-first flow — /linkgroup TLG-XXXXXXXX ────────────────
    args = context.args or []
    if args and args[0].upper().startswith("TLG-"):
        code = args[0].upper()
        with flask_app.app_context():
            from .models import db, TelegramGroup, TelegramGroupLinkCode
            from datetime import datetime

            link_code = TelegramGroupLinkCode.query.filter_by(code=code, used=False).first()
            if not link_code or not link_code.user_id:
                await update.message.reply_text(
                    "❌ Invalid or expired code. Generate a new one at telegizer.com",
                )
                return
            if link_code.expires_at < datetime.utcnow():
                await update.message.reply_text(
                    "❌ This code has expired. Generate a new one at telegizer.com",
                )
                return

            existing = TelegramGroup.query.filter_by(
                telegram_group_id=str(chat.id)
            ).first()
            if existing and existing.owner_user_id:
                await update.message.reply_text("⚠️ This group is already linked to a Telegizer account.")
                return

            # Get bot permissions
            bot_perms = {}
            try:
                bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
                bot_perms = extract_bot_permissions(bot_member)
            except Exception:
                pass

            member_count = 0
            try:
                member_count = await context.bot.get_chat_member_count(chat.id)
            except Exception:
                pass

            if existing:
                existing.owner_user_id = link_code.user_id
                existing.bot_status = "active"
                existing.linked_at = datetime.utcnow()
                existing.linked_via_bot_type = "official"
                existing.bot_permissions = bot_perms
                existing.member_count = member_count
                group = existing
            else:
                group = TelegramGroup(
                    telegram_group_id=str(chat.id),
                    title=chat.title or "Untitled",
                    username=chat.username,
                    owner_user_id=link_code.user_id,
                    bot_status="active",
                    linked_at=datetime.utcnow(),
                    linked_via_bot_type="official",
                    bot_permissions=bot_perms,
                    member_count=member_count,
                    is_forum=getattr(chat, "is_forum", False),
                    settings={},
                )
                from .group_defaults import fill_missing_defaults
                fill_missing_defaults(group)
                db.session.add(group)

            link_code.used = True
            link_code.used_at = datetime.utcnow()
            db.session.commit()

        await update.message.reply_text(
            f"✅ *{chat.title}* is now linked to your Telegizer dashboard!\n\n"
            f"🔗 [Open Dashboard]({_frontend()}/official-groups)\n\n"
            "Your bot features are now active. Configure them at telegizer.com",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    # ── End dashboard-first flow (fall through to bot-generated code flow) ───────

    group_id = str(chat.id)
    group_title = chat.title or "Untitled Group"
    bot_un = _bot_username()

    _log.info("[OfficialBot] /linkgroup from tg_user=%s group=%s (%s)", user.id, group_id, group_title)

    # -- Gather everything needed inside one context block --------------------
    already_linked = False
    linked_user_id = None   # if Telegram account is already linked to website
    code = None             # set when falling back to code flow
    _limit_hit = None       # set to (max_groups, tier) when group limit exceeded
    _limit_tier = None

    with flask_app.app_context():
        from .models import db, TelegramGroup, TelegramGroupLinkCode, User

        # SELECT ... FOR UPDATE prevents two concurrent /linkgroup calls on the
        # same group from both seeing owner_user_id=None and double-linking.
        tg = TelegramGroup.query.filter_by(
            telegram_group_id=group_id
        ).with_for_update().first()
        if not tg:
            tg = TelegramGroup(
                telegram_group_id=group_id, title=group_title,
                username=chat.username, bot_status="pending",
            )
            fill_missing_defaults(tg)
            db.session.add(tg)
            db.session.flush()
        else:
            fill_missing_defaults(tg)

        if tg.owner_user_id and tg.bot_status == "active":
            already_linked = True
            db.session.commit()
        else:
            # Check if this Telegram user has a linked website account
            website_user = _user_by_tg_id(user.id)

            if website_user:
                # Enforce per-tier official group limit before auto-linking
                max_groups = Config.MAX_OFFICIAL_GROUPS.get(website_user.subscription_tier, 3)
                if max_groups != -1:
                    current_count = TelegramGroup.query.filter_by(
                        owner_user_id=website_user.id, is_disabled=False
                    ).count()
                    if current_count >= max_groups:
                        db.session.commit()
                        # Respond outside the context block (set flag)
                        linked_user_id = None
                        _limit_hit = max_groups
                        _limit_tier = website_user.subscription_tier
                    else:
                        _limit_hit = None
                        _limit_tier = None
                else:
                    _limit_hit = None
                    _limit_tier = None

                if _limit_hit is None:
                    # Auto-link: no code exchange needed
                    tg.owner_user_id = website_user.id
                    tg.bot_status = "active"
                    tg.linked_at = datetime.utcnow()
                    tg.linked_via_bot_type = "official"
                    # Expire any leftover codes for this group from this user
                    TelegramGroupLinkCode.query.filter_by(
                        telegram_group_id=group_id,
                        created_by_telegram_user_id=str(user.id),
                        used_at=None,
                    ).update({"expires_at": datetime.utcnow()})
                    db.session.commit()
                    linked_user_id = website_user.id
            else:
                # Code flow
                TelegramGroupLinkCode.query.filter_by(
                    telegram_group_id=group_id,
                    used_at=None,
                ).filter(
                    TelegramGroupLinkCode.expires_at > datetime.utcnow()
                ).update({"expires_at": datetime.utcnow()})

                code = TelegramGroupLinkCode.generate_code()
                while TelegramGroupLinkCode.query.filter_by(code=code).first():
                    code = TelegramGroupLinkCode.generate_code()

                link_code = TelegramGroupLinkCode(
                    code=code,
                    telegram_group_id=group_id,
                    telegram_group_title=group_title,
                    created_by_telegram_user_id=str(user.id),
                    expires_at=datetime.utcnow() + timedelta(minutes=15),
                )
                db.session.add(link_code)
                db.session.commit()

    # -- Send Telegram messages outside the DB context -------------------------
    if _limit_hit is not None:
        await update.message.reply_text(
            f"⚠️ Your {_limit_tier.capitalize()} plan allows {_limit_hit} linked group(s).\n\n"
            f"Upgrade to Pro for unlimited groups at {_frontend()}/billing",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if already_linked:
        await update.message.reply_text(
            "✅ This group is already linked to a Telegizer account.\n"
            "Use `/status` to view details.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if linked_user_id:
        # Auto-linked — minimal group message + DM confirmation
        await update.message.reply_text(
            f"✅ *{group_title}* has been linked to your Telegizer account.\n\n"
            "View it in your dashboard.",
            parse_mode=ParseMode.MARKDOWN,
        )
        try:
            await context.bot.send_message(
                chat_id=user.id,
                text=(
                    f"✅ *Group linked!*\n\n"
                    f"*{group_title}* is now in your dashboard.\n"
                    f"[Open My Groups]({frontend}/my-groups)"
                ),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📋 My Groups", url=f"{frontend}/my-groups")],
                ]),
            )
        except Exception:
            pass
        _log_event(flask_app, group_id, "group_auto_linked",
                   f"Auto-linked by tg user {user.id}",
                   {"telegram_user_id": str(user.id), "website_user_id": linked_user_id})
        return

    # Code flow: post non-revealing group message + DM the code
    _log_event(flask_app, group_id, "link_code_generated",
               f"Code generated by tg user {user.id}",
               {"telegram_user_id": str(user.id)})

    await update.message.reply_text(
        f"✅ *Link request created.*\n\n"
        f"Open @{bot_un} privately to complete secure setup.\n"
        "_Your verification code will only be shown there._",
        parse_mode=ParseMode.MARKDOWN,
    )

    private_text = (
        f"🔐 *Your Group Link Code*\n\n"
        f"Group: *{group_title}*\n\n"
        f"Verification code:\n"
        f"`{code}`\n\n"
        f"⏱ Expires in *15 minutes* — single use only.\n\n"
        f"Paste this code at:\n"
        f"{frontend}/my-groups\n\n"
        f"_Or connect your Telegram account at Settings to skip codes in future._"
    )

    try:
        await context.bot.send_message(
            chat_id=user.id,
            text=private_text,
            parse_mode=ParseMode.MARKDOWN,
        )
    except (Forbidden, BadRequest):
        try:
            await context.bot.send_message(
                chat_id=chat.id,
                text=(
                    f"⚠️ @{user.username or user.first_name}, I couldn't DM you the code.\n\n"
                    f"Please start a private chat with @{bot_un} first, "
                    "then run `/linkgroup` again here."
                ),
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception:
            pass
    except Exception as exc:
        _log.warning("DM code failed for user %s: %s", user.id, exc)


# ─── /status ──────────────────────────────────────────────────────────────────

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    flask_app = context.bot_data.get("flask_app")

    if chat.type == ChatType.PRIVATE:
        await update.message.reply_text(
            "Use `/status` *inside your Telegram group*.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    group_id = str(chat.id)
    perms = {}
    if flask_app:
        perms = await _refresh_permissions(context.bot, group_id, flask_app)

    tg = None
    if flask_app:
        try:
            with flask_app.app_context():
                from .models import TelegramGroup
                tg = TelegramGroup.query.filter_by(telegram_group_id=group_id).first()
        except Exception:
            pass

    if not tg:
        bot_un = _bot_username()
        await update.message.reply_text(
            "ℹ️ This group is not yet registered.\n"
            f"Run `/linkgroup` here, then open @{bot_un} privately.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    linked = "✅ Linked to dashboard" if tg.owner_user_id else "⏳ Not linked — run /linkgroup"
    missing = [k for k, v in (perms or {}).items() if not v]
    perm_line = "✅ All permissions granted" if not missing else f"⚠️ Missing: {', '.join(missing)}"

    await update.message.reply_text(
        f"*Telegizer Status — {chat.title}*\n\n"
        f"🔗 {linked}\n"
        f"🤖 Bot: {tg.linked_via_bot_type.capitalize()}\n"
        f"🛡️ Permissions: {perm_line}"
        + ("\n\n_Grant admin rights to enable all features._" if missing else ""),
        parse_mode=ParseMode.MARKDOWN,
    )


# ─── Assistant suggestion keyboard helpers ────────────────────────────────────

def _build_suggestion_keyboard(suggestions: list | None) -> InlineKeyboardMarkup | None:
    """
    Build an InlineKeyboardMarkup from a list of {"label": str, "value": str|None}.
    Items with value=None are "Custom…" prompts that dismiss the keyboard.
    Returns None (no keyboard) when suggestions is empty/None.
    """
    if not suggestions:
        return None
    rows = []
    row = []
    for s in suggestions:
        label = s.get("label", "")
        value = s.get("value")
        if value is None:
            # Custom input sentinel — just closes the keyboard, user types freely
            cb = "assist_custom"
        else:
            # Encode: assist_pick:<value> (value max 50 chars to stay within 64-byte limit)
            cb = f"assist_pick:{value[:50]}"
        row.append(InlineKeyboardButton(label, callback_data=cb))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows) if rows else None


async def on_assistant_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles inline button taps from assistant suggestion keyboards.
    Feeds the tapped value back into process_message() as if the user typed it.
    """
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    flask_app = context.bot_data.get("flask_app")
    tg_user = query.from_user
    chat_id = query.message.chat_id

    if data == "assist_custom":
        await query.edit_message_reply_markup(reply_markup=None)
        await context.bot.send_message(chat_id=chat_id, text="Go ahead — type your response:")
        return

    if not data.startswith("assist_pick:"):
        return

    value = data[len("assist_pick:"):]
    if not value or not flask_app:
        return

    # __done__ sentinel — just close the keyboard silently
    if value == "__done__":
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        return

    if Config.ECHO_BOT_TOKEN:
        _echo_un = Config.ECHO_BOT_USERNAME or "Telegizer Echo"
        try:
            await query.edit_message_reply_markup(reply_markup=None)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"For AI assistance, message @{_echo_un}.",
            )
        except Exception:
            pass
        return

    try:
        await query.edit_message_reply_markup(reply_markup=None)

        with flask_app.app_context():
            from .models import User as _User, BotDMMessage as _BotDM, db as _db
            from .assistant.personal_assistant import process_message as _process_message

            _u = _User.query.filter_by(telegram_user_id=str(tg_user.id)).first()
            if not _u:
                return

            _db.session.add(_BotDM(user_id=_u.id, direction="in", content=value[:4000], intent="assistant_pick"))
            _db.session.commit()

            _result = _process_message(user_id=_u.id, message=value)
            _reply_text = _result.get("reply") or "Got it!"

            _db.session.add(_BotDM(user_id=_u.id, direction="out", content=_reply_text[:4000], intent=_result.get("intent", "general")))
            _db.session.commit()

            # Show selected value as user echo (skip internal sentinels)
            if value not in ("__skip__", "__done__"):
                await context.bot.send_message(chat_id=chat_id, text=f"▶ {value}")

            _keyboard = _build_suggestion_keyboard(_result.get("suggestions"))
            await context.bot.send_message(
                chat_id=chat_id,
                text=_reply_text,
                reply_markup=_keyboard,
            )
    except Exception as exc:
        _log.warning("on_assistant_pick failed: %s", exc)


# ─── Private message handler (bot token submission) ───────────────────────────

async def on_private_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles free-text in private chat: note capture shortcut + bot token submission."""
    if update.effective_chat.type != ChatType.PRIVATE:
        return

    flask_app = context.bot_data.get("flask_app")
    user = update.effective_user
    message = update.message
    frontend = _frontend()

    # ── Note capture shortcut ─────────────────────────────────────────────────
    _raw = (message.text or "").strip()
    _low = _raw.lower()
    _NOTE_STARTS = ("note this", "save this", "remember this", "note:", "save:")
    if any(_low == s or _low.startswith(s) for s in _NOTE_STARTS):
        content = None
        if message.reply_to_message and message.reply_to_message.text:
            content = message.reply_to_message.text
        else:
            for _pfx in ("note:", "save:"):
                if _low.startswith(_pfx):
                    content = _raw[len(_pfx):].strip()
                    break
        if not content:
            content = _raw
        if content and flask_app:
            try:
                with flask_app.app_context():
                    from .models import User as _User, Note as _Note, db as _db
                    _u = _user_by_tg_id(user.id)
                    if _u:
                        _db.session.add(_Note(user_id=_u.id, content=content[:5000], source="bot", tags=[]))
                        _db.session.commit()
                        await message.reply_text("✓ Saved to your notes.")
                    else:
                        await message.reply_text(
                            "⚠️ Connect your Telegram account on telegizer.com first to save notes."
                        )
            except Exception as _exc:
                _log.warning("Note capture failed: %s", _exc)
        return

    # ── Reminder intent detection ─────────────────────────────────────────────
    _REMINDER_PATS = re.compile(
        r"\b(remind me|set a reminder|reminder for|don.t let me forget|remind|reminder)\b",
        re.IGNORECASE,
    )
    if _REMINDER_PATS.search(_raw) and flask_app:
        try:
            with flask_app.app_context():
                from .models import (
                    User as _User, BotDMMessage as _BotDM,
                    PendingReminderState as _PRS, db as _db,
                )
                _u = _user_by_tg_id(user.id)
                if not _u:
                    await message.reply_text(
                        "⚠️ Connect your Telegram account on the website first."
                    )
                else:
                    # Strip trigger phrase to get the subject
                    _subject = _REMINDER_PATS.sub("", _raw).strip().strip(",. ") or _raw
                    _expires = datetime.utcnow() + timedelta(minutes=10)
                    # Upsert pending state (one per user)
                    _prs = _PRS.query.filter_by(user_id=_u.id).first()
                    if _prs:
                        _prs.subject = _subject[:500]
                        _prs.remind_at = None
                        _prs.expires_at = _expires
                    else:
                        _prs = _PRS(user_id=_u.id, subject=_subject[:500], expires_at=_expires)
                        _db.session.add(_prs)
                    # Log inbound DM
                    _db.session.add(_BotDM(user_id=_u.id, direction="in", content=_raw[:4000], intent="reminder"))
                    _db.session.commit()
                    # Ask when
                    _kb = InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton("30 min", callback_data="remind_time:30m"),
                            InlineKeyboardButton("1 hour", callback_data="remind_time:1h"),
                            InlineKeyboardButton("2 hours", callback_data="remind_time:2h"),
                        ],
                        [
                            InlineKeyboardButton("Today 6 pm", callback_data="remind_time:today18"),
                            InlineKeyboardButton("Tomorrow 9 am", callback_data="remind_time:tmr9"),
                        ],
                    ])
                    _reply = f"⏰ Got it! When should I remind you?\n\n*{_subject[:200]}*"
                    _sent = await message.reply_text(_reply, parse_mode=ParseMode.MARKDOWN, reply_markup=_kb)
                    # Log outbound DM
                    _db.session.add(_BotDM(user_id=_u.id, direction="out", content=_reply[:4000], intent="reminder"))
                    _db.session.commit()
        except Exception as _exc:
            _log.warning("Reminder intent failed: %s", _exc)
        return

    # ── Mode gate: only route to AI if user has activated assistant mode ─────
    # Users in "menu" mode get a nudge to open the menu instead of spamming AI.
    if _get_dm_mode(user.id) != "assistant":
        if Config.ECHO_BOT_TOKEN:
            _echo_un = Config.ECHO_BOT_USERNAME or "Telegizer Echo"
            await message.reply_text(
                f"I handle community management.\n\n"
                f"For AI assistance, message @{_echo_un}.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"Open @{_echo_un}", url=f"https://t.me/{_echo_un}")],
                    [InlineKeyboardButton("📋 My Groups", callback_data="menu:my_groups"),
                     InlineKeyboardButton("⚙️ Settings", callback_data="qs:groups")],
                ]),
            )
        else:
            await message.reply_text(
                "Use the menu to navigate, or tap *AI Assistant* to chat with AI.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🧠 AI Assistant", callback_data="menu:ai_assistant")],
                    [InlineKeyboardButton("📋 My Groups", callback_data="menu:my_groups"),
                     InlineKeyboardButton("⚙️ Settings", callback_data="qs:groups")],
                ]),
            )
        return

    # ── AI assistant routing — only reached when mode == "assistant" ──────────
    if flask_app and _raw:
        _BOT_TOKEN_RE = re.compile(r'\d{9,10}:[A-Za-z0-9_-]{35,}')
        _safe_raw = _BOT_TOKEN_RE.sub("[REDACTED_BOT_TOKEN]", _raw)
        _looks_like_token = bool(_BOT_TOKEN_RE.search(_raw))

        # Don't route bot-token-shaped messages through the assistant.
        # Also covers the case where awaiting_bot_token was lost after a bot restart —
        # if the message pattern matches a Telegram bot token, skip the assistant entirely.
        if not context.user_data.get("awaiting_bot_token") and not _looks_like_token:
            # When Echo is configured Telegizer is community-management only.
            # Redirect any free-text AI conversation to Echo.
            if Config.ECHO_BOT_TOKEN:
                _echo_un = Config.ECHO_BOT_USERNAME or "Telegizer Echo"
                try:
                    await message.reply_text(
                        f"I handle community management for your groups.\n\n"
                        f"For AI conversations, message @{_echo_un}.",
                    )
                except Exception:
                    pass
                return

            _reply_text = None
            _keyboard = None
            _unlinked = False
            try:
                with flask_app.app_context():
                    from .models import User as _User, BotDMMessage as _BotDM, db as _db
                    from .assistant.personal_assistant import process_message as _process_message

                    _u = _user_by_tg_id(user.id)
                    if _u:
                        # Clear any expired PendingReminderState so it can't corrupt future sessions
                        try:
                            from .models import PendingReminderState as _PRS
                            _expired = _PRS.query.filter(
                                _PRS.user_id == _u.id,
                                _PRS.expires_at < datetime.utcnow(),
                            ).first()
                            if _expired:
                                _db.session.delete(_expired)
                                _db.session.commit()
                        except Exception:
                            _db.session.rollback()
                        try:
                            _db.session.add(_BotDM(user_id=_u.id, direction="in", content=_safe_raw[:4000], intent="assistant"))
                            _db.session.commit()
                        except Exception:
                            _db.session.rollback()

                        _result = _process_message(user_id=_u.id, message=_safe_raw)
                        _reply_text = _result.get("reply") or "I'm not sure how to help with that."

                        try:
                            _db.session.add(_BotDM(user_id=_u.id, direction="out", content=_reply_text[:4000], intent=_result.get("intent", "general")))
                            _db.session.commit()
                        except Exception:
                            _db.session.rollback()

                        _keyboard = _build_suggestion_keyboard(_result.get("suggestions"))
                    else:
                        _unlinked = True
            except Exception as _exc:
                _log.warning("Assistant DM process_message failed: %s", _exc, exc_info=True)

            # Send reply OUTSIDE the app_context block to isolate Telegram API errors
            if _unlinked:
                try:
                    await message.reply_text(
                        "👋 Hi! To use the Telegizer assistant, connect your Telegram account at telegizer.com/settings.\n\n"
                        "Once linked, I can schedule meetings, save notes, set reminders, and more!",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("🔗 Connect Account", url=f"{frontend}/settings"),
                        ]]),
                    )
                except Exception as _exc:
                    _log.warning("Unlinked user reply failed: %s", _exc)
            elif _reply_text:
                # Convert AI markdown (**bold** etc.) to Telegram HTML
                _html = re.sub(r'\*\*([^*\n]+?)\*\*', r'<b>\1</b>', _reply_text)
                _html = re.sub(r'\*([^*\n]+?)\*', r'<i>\1</i>', _html)
                _html = re.sub(r'^#{1,3}\s+(.+)$', r'<b>\1</b>', _html, flags=re.MULTILINE)
                try:
                    await message.reply_text(_html, parse_mode=ParseMode.HTML, reply_markup=_keyboard)
                except Exception:
                    # Strip all formatting and send plain text as last resort
                    try:
                        _plain = re.sub(r'<[^>]+>', '', _html)
                        await message.reply_text(_plain, reply_markup=_keyboard)
                    except Exception as _exc:
                        _log.warning("Assistant DM send failed: %s", _exc)
            else:
                try:
                    await message.reply_text("I had trouble with that. Please try again in a moment.")
                except Exception:
                    pass
            return

    # ── Bot token submission ──────────────────────────────────────────────────
    # If the message looks like a bot token (even after a bot restart that wiped context.user_data),
    # treat it as a token submission attempt.
    _BOT_TOKEN_RE2 = re.compile(r'\d{9,10}:[A-Za-z0-9_-]{35,}')
    _is_token_msg = bool(_BOT_TOKEN_RE2.search(_raw or ""))
    if not context.user_data.get("awaiting_bot_token") and not _is_token_msg:
        return  # nothing left to handle

    # Rate limit: 10 failed attempts per 10 minutes (only failed attempts count)
    now = datetime.utcnow()
    attempts = [t for t in context.user_data.get("bot_token_attempts", [])
                if (now - t).total_seconds() < 600]
    if len(attempts) >= 10:
        await message.reply_text(
            "⚠️ Too many failed attempts. Please wait 10 minutes before trying again."
        )
        return

    token = (message.text or "").strip()

    # Basic format check — token stays visible in chat on failure so user can retry
    if ":" not in token or len(token) < 30:
        context.user_data["bot_token_attempts"] = attempts + [now]
        await message.reply_text(
            "❌ Invalid token format. Expected: `1234567890:AAAA...`\n\nPlease try again.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel_bot_token")],
            ]),
        )
        return

    # Only users with linked website accounts may submit tokens
    website_user_id = None
    website_tier = "free"
    if flask_app:
        try:
            with flask_app.app_context():
                from .models import User
                u = _user_by_tg_id(user.id)
                if u:
                    website_user_id = u.id
                    website_tier = u.subscription_tier
        except Exception:
            pass

    if not website_user_id:
        await message.reply_text(
            "❌ Your Telegram account is not linked to a Telegizer account.\n\n"
            "Go to *Settings → Connect Telegram* on the website first.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🖥️ Go to Settings", url=f"{frontend}/settings")],
            ]),
        )
        return

    # Verify token with Telegram — keep message visible until we know it's valid
    bot_name = None
    bot_username_verified = None
    try:
        resp = _http.get(
            f"https://api.telegram.org/bot{token}/getMe",
            timeout=10,
        )
        result = resp.json()
        if not result.get("ok"):
            context.user_data["bot_token_attempts"] = attempts + [now]
            await message.reply_text(
                "❌ Telegram rejected this token. Please check it is correct and try again.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ Cancel", callback_data="cancel_bot_token")],
                ]),
            )
            return
        tg_data = result.get("result", {})
        bot_name = tg_data.get("first_name")
        bot_username_verified = tg_data.get("username")
    except Exception as exc:
        context.user_data["bot_token_attempts"] = attempts + [now]
        await message.reply_text("❌ Could not reach Telegram to verify the token. Please try again.")
        return

    # Pre-flight: check bot limits
    pre_error = None
    if flask_app:
        try:
            with flask_app.app_context():
                from .models import CustomBot, User as _User
                u = _User.query.get(website_user_id)
                max_bots = Config.MAX_CUSTOM_BOTS.get(u.subscription_tier, 0)
                current_count = CustomBot.query.filter_by(owner_user_id=website_user_id).count()
                if current_count >= max_bots:
                    pre_error = (
                        f"❌ Your *{u.subscription_tier}* plan allows {max_bots} bot(s). "
                        "Upgrade to connect more."
                    )
                else:
                    dup = CustomBot.query.filter_by(bot_username=bot_username_verified).first()
                    if dup:
                        pre_error = f"ℹ️ @{bot_username_verified} is already connected to a Telegizer account."
        except Exception as exc:
            _log.error("Bot token pre-flight failed (tg user %s): %s", user.id, exc)
            pre_error = "❌ Could not verify quota. Please try again."

    if pre_error:
        context.user_data["awaiting_bot_token"] = False
        await message.reply_text(
            pre_error,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🖥️ Open Dashboard", url=f"{frontend}/my-bots")],
                [InlineKeyboardButton("« Back to Menu", callback_data="menu:main")],
            ]),
        )
        return

    # ✅ Token is valid and quota is fine — NOW delete it from chat history
    try:
        await message.delete()
    except Exception:
        pass

    # Store pending token and ask for confirmation — never log the raw token
    context.user_data["pending_bot_token"] = token
    context.user_data["pending_bot_name"] = bot_name
    context.user_data["pending_bot_username"] = bot_username_verified
    context.user_data["awaiting_bot_token"] = False  # stop re-reading plain text

    await context.bot.send_message(
        chat_id=user.id,
        text=(
            f"🗑️ Token deleted from chat for security.\n\n"
            f"🤖 *Confirm bot connection*\n\n"
            f"Name: *{bot_name}*\n"
            f"Username: @{bot_username_verified}\n\n"
            f"Connect this bot to your Telegizer account?"
        ),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Confirm", callback_data="confirm_bot_token"),
                InlineKeyboardButton("❌ Cancel",  callback_data="cancel_bot_token"),
            ]
        ]),
    )


# ─── Inline keyboard callbacks ────────────────────────────────────────────────

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    flask_app = context.bot_data.get("flask_app")
    frontend = _frontend()
    user = update.effective_user
    bot_un = _bot_username()

    # ── official bot verification callbacks ───────────────────────────────────
    if data.startswith("v:"):
        await _handle_verification_callback(update, context)
        return


    await query.answer()

    # ── AI Assistant quick-action buttons ─────────────────────────────────────
    if data.startswith("ai:"):
        if Config.ECHO_BOT_TOKEN:
            _echo_un = Config.ECHO_BOT_USERNAME or "Telegizer Echo"
            await query.edit_message_text(
                f"AI features are handled by @{_echo_un}.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("« Back", callback_data="menu:main"),
                ]]),
            )
            return
        _ai_messages = {
            "ai:analyze_day":   "Analyze my day",
            "ai:schedule":      "What's on my schedule?",
            "ai:group_health":  "Any issues in my groups?",
            "ai:remind":        "Remind me",
        }
        _ai_msg = _ai_messages.get(data)
        if _ai_msg and flask_app:
            try:
                with flask_app.app_context():
                    from .models import User as _User
                    from .assistant.personal_assistant import process_message as _pm
                    _wu = _user_by_tg_id(user.id)
                    if _wu:
                        _result = _pm(_wu.id, _ai_msg)
                        _reply = _result.get("reply") or "I'm here — just type your question!"
                        await query.edit_message_text(
                            _reply,
                            parse_mode=ParseMode.MARKDOWN,
                            reply_markup=InlineKeyboardMarkup([
                                [InlineKeyboardButton("« Back to Menu", callback_data="menu:main")],
                            ]),
                        )
                        return
            except Exception as _e:
                _log.warning("AI quick-action failed: %s", _e)
        await query.edit_message_text(
            "Just type your message below and I'll respond! 👇",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("« Back", callback_data="menu:main")],
            ]),
        )
        return

    # ── remind_time: user picked when ────────────────────────────────────────
    if data.startswith("remind_time:"):
        _slot = data.split(":", 1)[1]
        if flask_app:
            try:
                with flask_app.app_context():
                    from .models import User as _User, PendingReminderState as _PRS, BotDMMessage as _BotDM, db as _db
                    _u = _user_by_tg_id(user.id)
                    _prs = _PRS.query.filter_by(user_id=_u.id).first() if _u else None
                    if not _u or not _prs:
                        await query.edit_message_text("⚠️ Session expired. Please start over.")
                        return
                    _now = datetime.utcnow()
                    if _slot == "30m":
                        _t = _now + timedelta(minutes=30)
                    elif _slot == "1h":
                        _t = _now + timedelta(hours=1)
                    elif _slot == "2h":
                        _t = _now + timedelta(hours=2)
                    elif _slot == "today18":
                        _t = _now.replace(hour=18, minute=0, second=0, microsecond=0)
                        if _t <= _now:
                            _t += timedelta(days=1)
                    else:  # tmr9
                        _t = (_now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
                    _prs.remind_at = _t
                    _db.session.commit()
                    _kb = InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton("Once", callback_data="remind_freq:1"),
                            InlineKeyboardButton("2× (15 min early too)", callback_data="remind_freq:2"),
                            InlineKeyboardButton("3× (30/15/0)", callback_data="remind_freq:3"),
                        ],
                    ])
                    _msg = f"How many times should I remind you?\n\n*{_prs.subject[:200]}*\nat {_t.strftime('%H:%M UTC')}"
                    await query.edit_message_text(_msg, parse_mode=ParseMode.MARKDOWN, reply_markup=_kb)
                    _db.session.add(_BotDM(user_id=_u.id, direction="out", content=_msg[:4000], intent="reminder"))
                    _db.session.commit()
            except Exception as _exc:
                _log.warning("remind_time callback failed: %s", _exc)
        return

    # ── remind_freq: user picked frequency → create WorkspaceReminder(s) ─────
    if data.startswith("remind_freq:"):
        _freq = int(data.split(":", 1)[1])
        if flask_app:
            try:
                with flask_app.app_context():
                    from .models import (
                        User as _User, PendingReminderState as _PRS,
                        WorkspaceReminder as _WR, BotDMMessage as _BotDM, db as _db,
                    )
                    _u = _user_by_tg_id(user.id)
                    _prs = _PRS.query.filter_by(user_id=_u.id).first() if _u else None
                    if not _u or not _prs or not _prs.remind_at:
                        await query.edit_message_text("⚠️ Session expired. Please start over.")
                        return
                    _base = _prs.remind_at
                    _offsets = {1: [timedelta(0)], 2: [timedelta(minutes=-15), timedelta(0)], 3: [timedelta(minutes=-30), timedelta(minutes=-15), timedelta(0)]}
                    for _off in _offsets.get(_freq, [timedelta(0)]):
                        _fire = _base + _off
                        if _fire > datetime.utcnow():
                            _db.session.add(_WR(
                                owner_user_id=_u.id,
                                reminder_text=_prs.subject,
                                remind_at=_fire,
                                is_delivered=False,
                            ))
                    _db.session.delete(_prs)
                    _db.session.commit()
                    _confirm = f"✅ Reminder set for *{_base.strftime('%H:%M UTC')}*!\n\n_{_prs.subject[:200]}_"
                    await query.edit_message_text(_confirm, parse_mode=ParseMode.MARKDOWN)
                    _db.session.add(_BotDM(user_id=_u.id, direction="out", content=_confirm[:4000], intent="reminder"))
                    _db.session.commit()
            except Exception as _exc:
                _log.warning("remind_freq callback failed: %s", _exc)
        return

    # ── cancel bot token submission ───────────────────────────────────────────
    if data == "cancel_bot_token":
        context.user_data["awaiting_bot_token"] = False
        context.user_data.pop("pending_bot_token", None)
        context.user_data.pop("pending_bot_username", None)
        context.user_data.pop("pending_bot_name", None)
        await _render_main_menu(query, user, flask_app, frontend)
        return

    # ── confirm bot token (after confirmation prompt) ─────────────────────────
    if data == "confirm_bot_token":
        token = context.user_data.pop("pending_bot_token", None)
        bot_name = context.user_data.pop("pending_bot_name", None)
        bot_username_verified = context.user_data.pop("pending_bot_username", None)

        if not token or not bot_username_verified:
            await query.answer("Session expired. Please try again.", show_alert=True)
            await _render_main_menu(query, user, flask_app, frontend)
            return

        website_user_id = None
        if flask_app:
            try:
                with flask_app.app_context():
                    from .models import User as _User
                    u = _user_by_tg_id(user.id)
                    if u:
                        website_user_id = u.id
            except Exception:
                pass

        if not website_user_id:
            await query.answer("Account not linked.", show_alert=True)
            return

        save_error = None
        if flask_app:
            try:
                with flask_app.app_context():
                    from .models import db, CustomBot, User as _User
                    u = _User.query.get(website_user_id)
                    max_bots = Config.MAX_CUSTOM_BOTS.get(u.subscription_tier, 0)
                    current_count = CustomBot.query.filter_by(owner_user_id=website_user_id).count()
                    if current_count >= max_bots:
                        save_error = f"❌ Bot limit reached for your plan."
                    else:
                        dup = CustomBot.query.filter_by(bot_username=bot_username_verified).first()
                        if dup:
                            save_error = f"ℹ️ @{bot_username_verified} already connected."
                        else:
                            cb = CustomBot(
                                owner_user_id=website_user_id,
                                bot_name=bot_name,
                                bot_username=bot_username_verified,
                                status="active",
                            )
                            cb.set_token(token)
                            db.session.add(cb)
                            db.session.commit()
                            _log_event(flask_app, None, "custom_bot_added_via_telegram",
                                       f"@{bot_username_verified} confirmed by tg user {user.id}",
                                       {"bot_username": bot_username_verified, "telegram_user_id": str(user.id)})
            except Exception as exc:
                _log.error("Bot confirm-save failed (tg user %s): %s", user.id, exc)
                save_error = "❌ Failed to save. Please try the website dashboard."

        if save_error:
            await query.edit_message_text(
                save_error,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🖥️ Open Dashboard", url=f"{frontend}/my-bots")],
                    [InlineKeyboardButton("« Back", callback_data="menu:main")],
                ]),
            )
            return

        await query.edit_message_text(
            f"✅ *@{bot_username_verified} connected!*\n\n"
            f"*{bot_name}* is now powered by Telegizer. View it in My Bots.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🤖 View My Bots", url=f"{frontend}/my-bots")],
                [InlineKeyboardButton("« Back to Menu", callback_data="menu:main")],
            ]),
        )
        return

    # ── account info ──────────────────────────────────────────────────────────
    if data == "menu:account_info":
        tg_email = None
        if flask_app:
            try:
                with flask_app.app_context():
                    from .models import User
                    u = _user_by_tg_id(user.id)
                    if u:
                        tg_email = u.email
            except Exception:
                pass
        text = (
            f"✅ *Account Connected*\n\n"
            f"Your Telegram is linked to: `{tg_email}`\n\n"
            f"Groups you add will appear in your dashboard automatically."
        ) if tg_email else (
            "ℹ️ No Telegizer account linked.\n\n"
            f"Visit {frontend}/settings to connect."
        )
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🖥️ Open Dashboard", url=frontend)],
                [InlineKeyboardButton("⚙️ Settings", url=f"{frontend}/settings")],
                [InlineKeyboardButton("« Back", callback_data="menu:main")],
            ]),
        )
        return

    # ── pending_groups ────────────────────────────────────────────────────────
    if data == "menu:pending_groups":
        pending = []
        if flask_app:
            try:
                with flask_app.app_context():
                    from .models import TelegramGroupLinkCode, TelegramGroup
                    codes = TelegramGroupLinkCode.query.filter_by(
                        created_by_telegram_user_id=str(user.id),
                        used_at=None,
                    ).filter(
                        TelegramGroupLinkCode.expires_at > datetime.utcnow()
                    ).all()
                    for c in codes:
                        tg = TelegramGroup.query.filter_by(
                            telegram_group_id=c.telegram_group_id
                        ).first()
                        if tg and not tg.owner_user_id:
                            pending.append({"title": tg.title, "code": c.code})
            except Exception:
                pass

        if not pending:
            text = (
                "✅ *No groups awaiting setup.*\n\n"
                "All your groups are already linked, or your codes have expired.\n"
                "Run `/linkgroup` in a group to generate a new code."
            )
            keyboard = [[InlineKeyboardButton("« Back", callback_data="menu:main")]]
        else:
            lines = ["*Groups Awaiting Setup*\n"]
            for p in pending:
                lines.append(f"• *{p['title']}*")
            lines.append("\nTap a group to see its code.")
            text = "\n".join(lines)

            code_buttons = [
                [InlineKeyboardButton(
                    f"📋 {p['title']}",
                    callback_data=f"show_code:{p['code']}",
                )]
                for p in pending[:5]
            ]
            keyboard = code_buttons + [
                [InlineKeyboardButton("🖥️ Open Dashboard", url=f"{frontend}/my-groups")],
                [InlineKeyboardButton("➕ Add Another Group", callback_data="menu:add_group")],
                [InlineKeyboardButton("« Back", callback_data="menu:main")],
            ]

        await query.edit_message_text(
            text, parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    # ── show individual code ──────────────────────────────────────────────────
    elif data.startswith("show_code:"):
        code = data.split(":", 1)[1]
        valid = False
        group_title = ""
        if flask_app:
            try:
                with flask_app.app_context():
                    from .models import TelegramGroupLinkCode
                    lc = TelegramGroupLinkCode.query.filter_by(
                        code=code,
                        created_by_telegram_user_id=str(user.id),
                        used_at=None,
                    ).filter(
                        TelegramGroupLinkCode.expires_at > datetime.utcnow()
                    ).first()
                    if lc:
                        valid = True
                        group_title = lc.telegram_group_title or ""
            except Exception:
                pass

        if not valid:
            await query.edit_message_text(
                "⚠️ This code has expired or already been used. "
                "Run `/linkgroup` in the group again.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("« Back", callback_data="menu:pending_groups")]
                ]),
            )
            return

        await query.edit_message_text(
            f"🔐 *Link Code for {group_title}*\n\n"
            f"`{code}`\n\n"
            f"Paste this at:\n{frontend}/my-groups\n\n"
            "_Single use · expires in 15 min_",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🖥️ Open Dashboard", url=f"{frontend}/my-groups")],
                [InlineKeyboardButton("« Back", callback_data="menu:pending_groups")],
            ]),
        )

    # ── my_groups ─────────────────────────────────────────────────────────────
    elif data == "menu:my_groups":
        groups = []
        is_linked = False
        if flask_app:
            try:
                with flask_app.app_context():
                    from .models import User, TelegramGroup
                    wu = _user_by_tg_id(user.id)
                    is_linked = wu is not None
                    if wu:
                        groups = TelegramGroup.query.filter_by(
                            owner_user_id=wu.id, is_disabled=False,
                        ).order_by(TelegramGroup.linked_at.desc()).limit(10).all()
                        groups = [{"title": g.title, "status": g.bot_status,
                                   "group_id": g.telegram_group_id,
                                   "cmd_count": len(g.custom_commands)} for g in groups]
            except Exception:
                pass

        if not is_linked:
            await query.edit_message_text(
                "📋 *My Groups*\n\n"
                "Connect your Telegizer website account to see your groups here.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔗 Connect Account", url=f"{frontend}/settings")],
                    [InlineKeyboardButton("« Back", callback_data="menu:main")],
                ]),
            )
            return

        if not groups:
            text = (
                "📋 *My Groups*\n\n"
                "You have no linked groups yet.\n"
                "Add the bot to a group and run `/linkgroup` to get started."
            )
            keyboard = [
                [InlineKeyboardButton("➕ Add Group", callback_data="menu:add_group")],
                [InlineKeyboardButton("🖥️ Open Dashboard", url=f"{frontend}/my-groups")],
                [InlineKeyboardButton("« Back", callback_data="menu:main")],
            ]
        else:
            status_icon = {"active": "🟢", "pending": "🟡", "removed": "🔴", "disabled": "⛔"}
            lines = ["📋 *My Linked Groups*\n"]
            for g in groups:
                icon = status_icon.get(g["status"], "⚪")
                cmd_txt = f" · {g['cmd_count']} cmd" if g["cmd_count"] else ""
                lines.append(f"{icon} *{g['title']}*{cmd_txt}")
            text = "\n".join(lines)
            keyboard = [
                [InlineKeyboardButton("🖥️ Manage on Dashboard", url=f"{frontend}/my-groups")],
                [InlineKeyboardButton("➕ Add Another Group", callback_data="menu:add_group")],
                [InlineKeyboardButton("« Back", callback_data="menu:main")],
            ]

        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    # ── add_group ─────────────────────────────────────────────────────────────
    elif data == "menu:add_group":
        add_url = f"https://t.me/{bot_un}?startgroup=setup"
        await query.edit_message_text(
            "*Add Group to Telegizer*\n\n"
            "1️⃣ Add the bot to your group using the button below\n"
            "2️⃣ In the group, run `/linkgroup`\n"
            "3️⃣ If your account is connected, it links automatically\n"
            "   Otherwise paste the code from here into the Dashboard",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Add Bot to Group", url=add_url)],
                [InlineKeyboardButton("🖥️ Dashboard → Add Group", url=f"{frontend}/my-groups")],
                [InlineKeyboardButton("« Back", callback_data="menu:main")],
            ]),
        )

    # ── advanced ──────────────────────────────────────────────────────────────
    elif data == "menu:advanced":
        # Advanced Options now only contains Settings — My Bots and Connect Own Bot
        # are surfaced on the main menu directly.
        await query.edit_message_text(
            "*Settings*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⚙️ Account Settings", url=f"{frontend}/settings")],
                [InlineKeyboardButton("« Back", callback_data="menu:main")],
            ]),
        )

    elif data == "menu:my_bots":
        custom_bots_list = []
        is_linked = False
        if flask_app:
            try:
                with flask_app.app_context():
                    from .models import User, CustomBot
                    wu = _user_by_tg_id(user.id)
                    is_linked = wu is not None
                    if wu:
                        custom_bots_list = CustomBot.query.filter_by(
                            owner_user_id=wu.id,
                        ).order_by(CustomBot.created_at.desc()).limit(10).all()
                        custom_bots_list = [{"username": b.bot_username, "name": b.bot_name,
                                             "status": b.status,
                                             "groups": len(b.linked_groups)} for b in custom_bots_list]
            except Exception:
                pass

        if not is_linked:
            await query.edit_message_text(
                "🤖 *My Bots*\n\n"
                "Connect your Telegizer website account to see your bots here.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔗 Connect Account", url=f"{frontend}/settings")],
                    [InlineKeyboardButton("« Back", callback_data="menu:main")],
                ]),
            )
            return

        status_icon = {"active": "🟢", "inactive": "🟡", "error": "🔴"}
        lines = [
            "🤖 *My Bots*\n",
            "🟢 *Official Telegizer Bot* (shared · always active)",
        ]
        if custom_bots_list:
            lines.append("\n*Custom Bots:*")
            for b in custom_bots_list:
                icon = status_icon.get(b["status"], "⚪")
                grp_txt = f" · {b['groups']} group{'s' if b['groups'] != 1 else ''}" if b["groups"] else ""
                lines.append(f"{icon} @{b['username']}{grp_txt}")
        else:
            lines.append("\n_No custom bots connected yet._")

        await query.edit_message_text(
            "\n".join(lines),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🖥️ Manage Bots", url=f"{frontend}/my-bots")],
                [InlineKeyboardButton("🔌 Connect Own Bot", callback_data="menu:connect_bot")],
                [InlineKeyboardButton("« Back", callback_data="menu:main")],
            ]),
        )

    elif data == "menu:connect_bot":
        # Check website account is linked before accepting a token
        is_linked = False
        if flask_app:
            try:
                with flask_app.app_context():
                    from .models import User
                    u = _user_by_tg_id(user.id)
                    is_linked = u is not None
            except Exception:
                pass

        if not is_linked:
            await query.edit_message_text(
                "*Connect Your Own Bot*\n\n"
                "⚠️ You need to link your Telegram account to a Telegizer website account first.\n\n"
                "Go to *Settings → Connect Telegram* on the website, then come back here.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🖥️ Go to Settings", url=f"{frontend}/settings")],
                    [InlineKeyboardButton("« Back", callback_data="menu:main")],
                ]),
            )
            return

        context.user_data["awaiting_bot_token"] = True
        await query.edit_message_text(
            "*Connect Your Own Bot*\n\n"
            "Paste your *BotFather token* in the next message.\n\n"
            "⚠️ Your message will be deleted immediately after processing.\n"
            "Format: `1234567890:AAAA...`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel_bot_token")],
            ]),
        )

    elif data == "menu:support":
        await query.edit_message_text(
            "*Telegizer Support*\n\n"
            "Here's how to get help:\n\n"
            "📢 *Official Channel* — product updates & announcements\n"
            "👥 *Community Group* — get help from other users\n"
            "✉️ *Email Support* — fazalelahi5577@gmail.com",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 Official Channel", url="https://t.me/telegizer")],
                [InlineKeyboardButton("👥 Community Group", url="https://t.me/telegizer_community")],
                [InlineKeyboardButton("✉️ Email Support", url="https://mail.google.com/mail/?view=cm&to=fazalelahi5577@gmail.com&su=Telegizer+Support")],
                [InlineKeyboardButton("« Back", callback_data="menu:main")],
            ]),
        )

    elif data == "menu:ai_assistant":
        if Config.ECHO_BOT_TOKEN:
            _echo_un = Config.ECHO_BOT_USERNAME or "Telegizer Echo"
            await query.edit_message_text(
                f"🧠 *AI Assistant*\n\n"
                f"AI features are handled by @{_echo_un}.\n\n"
                f"Open Echo to chat, set reminders, manage tasks, and more.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"Open @{_echo_un}", url=f"https://t.me/{_echo_un}")],
                    [InlineKeyboardButton("« Back to Menu", callback_data="menu:main")],
                ]),
            )
            return
        _set_dm_mode(query.from_user.id, "assistant")
        await query.edit_message_text(
            "🧠 *AI Assistant — Active*\n\n"
            "I'm your AI co-pilot. Just type anything naturally right here.\n\n"
            "*Productivity:*\n"
            "• \"Schedule a meeting with Ahmed Friday 3pm\"\n"
            "• \"Remind me to send the proposal tomorrow morning\"\n"
            "• \"Create task: review analytics report — high priority\"\n\n"
            "*Workspace:*\n"
            "• \"What's happening in my groups?\"\n"
            "• \"Analyze my day\"\n"
            "• \"Any issues I should fix?\"\n\n"
            "Type freely — I'll reply below. Tap *Back to Menu* when done.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🧠 Analyze My Day", callback_data="ai:analyze_day"),
                    InlineKeyboardButton("📅 My Schedule", callback_data="ai:schedule"),
                ],
                [
                    InlineKeyboardButton("👥 Group Health", callback_data="ai:group_health"),
                    InlineKeyboardButton("⏰ Set Reminder", callback_data="ai:remind"),
                ],
                [InlineKeyboardButton("« Back to Menu", callback_data="menu:exit_assistant")],
            ]),
        )

    elif data == "menu:exit_assistant":
        _set_dm_mode(query.from_user.id, "menu")
        _frontend_url = _frontend()
        await query.edit_message_text(
            "👋 *Telegizer Main Menu*\n\n"
            "AI assistant mode is off. Choose an option or use /start anytime.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("➕ Add Group", callback_data="menu:add_group"),
                    InlineKeyboardButton("📋 My Groups", callback_data="menu:my_groups"),
                ],
                [
                    InlineKeyboardButton("🧠 AI Assistant", callback_data="menu:ai_assistant"),
                    InlineKeyboardButton("⚡ Automations", url=f"{_frontend_url}/workspace/automations"),
                ],
                [
                    InlineKeyboardButton("💬 Support", callback_data="menu:support"),
                    InlineKeyboardButton("⚙️ Quick Settings", callback_data="qs:groups"),
                ],
            ]),
        )

    elif data == "menu:main":
        await _render_main_menu(query, user, flask_app, frontend)

    elif data.startswith("qs:"):
        await _handle_qs_callback(query, user, data, flask_app, frontend)


# ── Quick Settings inline toggle panel ────────────────────────────────────────

_QS_FEATURES = [
    ("automod",       "automod.enabled",                   "🛡 AutoMod"),
    ("verification",  "verification.enabled",              "✅ Verification"),
    ("welcome",       "welcome.enabled",                   "👋 Welcome Messages"),
    ("levels",        "levels.enabled",                    "📊 XP / Levels"),
    ("ai_reply",      "knowledge_base.auto_reply_enabled", "🤖 AI Auto-Reply"),
]


def _qs_get(settings: dict, dotkey: str) -> bool:
    val = settings
    for k in dotkey.split("."):
        val = val.get(k, {}) if isinstance(val, dict) else {}
    return bool(val)


def _qs_set(settings: dict, dotkey: str, value: bool) -> dict:
    import copy
    s = copy.deepcopy(settings) if settings else {}
    keys = dotkey.split(".")
    node = s
    for k in keys[:-1]:
        node = node.setdefault(k, {})
    node[keys[-1]] = value
    return s


def _qs_toggle_keyboard(group_id: int, settings: dict, frontend: str) -> InlineKeyboardMarkup:
    rows = []
    for feat_key, dotkey, label in _QS_FEATURES:
        on = _qs_get(settings, dotkey)
        state = "🟢 ON" if on else "🔴 OFF"
        rows.append([InlineKeyboardButton(
            f"{label}  {state}",
            callback_data=f"qs:toggle:{group_id}:{feat_key}",
        )])
    rows.append([InlineKeyboardButton("🌐 Full Settings on Web", url=f"{frontend}/groups/{group_id}")])
    rows.append([InlineKeyboardButton("« Back", callback_data="menu:main")])
    return InlineKeyboardMarkup(rows)


async def _handle_qs_callback(query, user, data: str, flask_app, frontend: str):
    parts = data.split(":")

    if data == "qs:groups":
        groups = []
        if flask_app:
            try:
                with flask_app.app_context():
                    from .models import TelegramGroup
                    wu = _user_by_tg_id(user.id)
                    if wu:
                        gs = TelegramGroup.query.filter_by(
                            owner_user_id=wu.id, is_disabled=False,
                        ).order_by(TelegramGroup.linked_at.desc()).limit(10).all()
                        groups = [{"id": g.id, "title": g.title or f"Group {g.id}"} for g in gs]
            except Exception as exc:
                _log.warning("qs:groups load failed: %s", exc)

        if not groups:
            await query.edit_message_text(
                "⚙️ *Quick Settings*\n\nNo groups linked yet.\n"
                "Add @TelegizerBot to a group and run /linkgroup first.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("« Back", callback_data="menu:main")],
                ]),
            )
            return

        if len(groups) == 1:
            await _handle_qs_callback(query, user, f"qs:group:{groups[0]['id']}", flask_app, frontend)
            return

        rows = [[InlineKeyboardButton(g["title"], callback_data=f"qs:group:{g['id']}")] for g in groups]
        rows.append([InlineKeyboardButton("« Back", callback_data="menu:main")])
        await query.edit_message_text(
            "⚙️ *Quick Settings*\n\nChoose a group to configure:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(rows),
        )
        return

    if len(parts) == 3 and parts[1] == "group":
        group_id = int(parts[2])
        settings = {}
        title = ""
        if flask_app:
            try:
                with flask_app.app_context():
                    from .models import TelegramGroup
                    g = TelegramGroup.query.get(group_id)
                    if not g:
                        await query.edit_message_text("⚠️ Group not found.")
                        return
                    settings = dict(g.settings or {})
                    title = g.title or f"Group {group_id}"
            except Exception as exc:
                _log.warning("qs:group load failed: %s", exc)
                await query.edit_message_text("⚠️ Could not load group settings.")
                return

        await query.edit_message_text(
            f"⚙️ *Quick Settings — {title}*\n\nTap any feature to toggle it on/off instantly:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_qs_toggle_keyboard(group_id, settings, frontend),
        )
        return

    if len(parts) == 4 and parts[1] == "toggle":
        group_id = int(parts[2])
        feat_key = parts[3]
        dotkey = next((d for k, d, _ in _QS_FEATURES if k == feat_key), None)
        if not dotkey:
            await query.answer("Unknown feature.", show_alert=True)
            return

        new_val = False
        settings = {}
        title = ""
        if flask_app:
            try:
                with flask_app.app_context():
                    from .models import db, TelegramGroup
                    from sqlalchemy.orm.attributes import flag_modified
                    g = TelegramGroup.query.get(group_id)
                    if not g:
                        await query.answer("Group not found.", show_alert=True)
                        return
                    settings = dict(g.settings or {})
                    new_val = not _qs_get(settings, dotkey)
                    g.settings = _qs_set(settings, dotkey, new_val)
                    flag_modified(g, "settings")
                    db.session.commit()
                    settings = dict(g.settings)
                    title = g.title or f"Group {group_id}"
            except Exception as exc:
                _log.warning("qs:toggle failed: %s", exc)
                await query.answer("Failed to save. Try again.", show_alert=True)
                return

        label = next((l for k, _, l in _QS_FEATURES if k == feat_key), feat_key)
        await query.answer(f"{label} {'enabled' if new_val else 'disabled'}")
        await query.edit_message_text(
            f"⚙️ *Quick Settings — {title}*\n\nTap any feature to toggle it on/off instantly:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_qs_toggle_keyboard(group_id, settings, frontend),
        )
        return

    await query.answer("Unknown action.", show_alert=True)


async def _render_main_menu(query, user, flask_app, frontend):
    pending_count = 0
    is_linked = False
    if flask_app:
        try:
            with flask_app.app_context():
                from .models import TelegramGroupLinkCode, TelegramGroup, User
                wu = _user_by_tg_id(user.id)
                is_linked = wu is not None
                codes = TelegramGroupLinkCode.query.filter_by(
                    created_by_telegram_user_id=str(user.id),
                    used_at=None,
                ).filter(
                    TelegramGroupLinkCode.expires_at > datetime.utcnow()
                ).all()
                for c in codes:
                    tg = TelegramGroup.query.filter_by(
                        telegram_group_id=c.telegram_group_id
                    ).first()
                    if tg and not tg.owner_user_id:
                        pending_count += 1
        except Exception:
            pass

    keyboard = []
    if is_linked:
        keyboard.append([InlineKeyboardButton("✅ Account Connected", callback_data="menu:account_info")])
    else:
        keyboard.append([InlineKeyboardButton("🔗 Connect Website Account", url=f"{frontend}/settings")])

    if pending_count:
        keyboard.append([
            InlineKeyboardButton(
                f"⚠️ {pending_count} Group(s) Awaiting Setup",
                callback_data="menu:pending_groups",
            )
        ])

    keyboard += [
        [
            InlineKeyboardButton("➕ Add Group", callback_data="menu:add_group"),
            InlineKeyboardButton("📋 My Groups", callback_data="menu:my_groups"),
        ],
        [
            InlineKeyboardButton("🤖 My Bots", callback_data="menu:my_bots"),
            InlineKeyboardButton("🔌 Connect Own Bot", callback_data="menu:connect_bot"),
        ],
        [
            InlineKeyboardButton("🧠 AI Assistant", callback_data="menu:ai_assistant"),
            InlineKeyboardButton("⚡ Automations", url=f"{frontend}/workspace/automations"),
        ],
        [
            InlineKeyboardButton("💬 Support", callback_data="menu:support"),
            InlineKeyboardButton("⚙️ Quick Settings", callback_data="qs:groups"),
        ],
    ]
    await query.edit_message_text(
        "*Telegizer — Telegram Growth & Management Hub*\n\nWhat would you like to do?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ─── Group membership events ──────────────────────────────────────────────────

async def on_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    flask_app = context.bot_data.get("flask_app")
    chat = update.effective_chat
    if not chat or chat.type == ChatType.PRIVATE:
        return

    my_member = update.my_chat_member
    if not my_member:
        return

    new_status = my_member.new_chat_member.status
    group_id = str(chat.id)
    group_title = chat.title or "Untitled Group"
    added_by = str(my_member.from_user.id) if my_member.from_user else None
    bot_un = _bot_username()

    if new_status in ("member", "administrator"):
        _upsert_group(flask_app, group_id, group_title, chat.username)
        _log_event(flask_app, group_id, "bot_added",
                   f"Bot added to {group_title}",
                   {"added_by_telegram_id": added_by})
        if flask_app:
            await _refresh_permissions(context.bot, group_id, flask_app)

        auto_linked = False
        limit_hit = False

        # Try to auto-link the group when the adder has a linked website account.
        if flask_app and added_by:
            try:
                with flask_app.app_context():
                    from .models import db, TelegramGroup, TelegramGroupLinkCode
                    from datetime import datetime as _dt
                    website_user = _user_by_tg_id(added_by)
                    if website_user:
                        max_groups = Config.MAX_OFFICIAL_GROUPS.get(website_user.subscription_tier, 3)
                        current_count = TelegramGroup.query.filter_by(
                            owner_user_id=website_user.id, is_disabled=False
                        ).count()
                        if max_groups != -1 and current_count >= max_groups:
                            limit_hit = True
                            try:
                                await context.bot.send_message(
                                    chat_id=int(added_by),
                                    text=(
                                        f"⚠️ *Group limit reached*\n\n"
                                        f"You've added the bot to *{group_title}* but your "
                                        f"{website_user.subscription_tier.capitalize()} plan allows "
                                        f"{max_groups} linked group(s).\n\n"
                                        f"To link this group, upgrade your plan or unlink an "
                                        f"existing group from the dashboard."
                                    ),
                                    parse_mode=ParseMode.MARKDOWN,
                                )
                            except Exception:
                                pass
                        else:
                            tg = TelegramGroup.query.filter_by(telegram_group_id=group_id).first()
                            if tg:
                                tg.owner_user_id = website_user.id
                                tg.bot_status = "active"
                                tg.linked_at = _dt.utcnow()
                                tg.linked_via_bot_type = "official"
                                TelegramGroupLinkCode.query.filter_by(
                                    telegram_group_id=group_id,
                                    created_by_telegram_user_id=str(added_by),
                                    used_at=None,
                                ).update({"expires_at": _dt.utcnow()})
                                db.session.commit()
                                auto_linked = True
                                _log_event(flask_app, group_id, "group_auto_linked",
                                           f"Group auto-linked to user {website_user.id}",
                                           {"telegram_user_id": added_by})
            except Exception as exc:
                _log.debug("Auto-link on join failed: %s", exc)

        if auto_linked:
            try:
                await chat.send_message(
                    f"✅ *Group linked!*\n\n"
                    f"This group is now connected to your Telegizer account. "
                    f"Open the dashboard to configure it.",
                    parse_mode=ParseMode.MARKDOWN,
                )
            except Exception as exc:
                _log.debug("Auto-link welcome failed: %s", exc)
        else:
            try:
                await chat.send_message(
                    f"✅ *Telegizer connected.*\n\n"
                    f"Run `/linkgroup` here, then open @{bot_un} privately to complete setup.",
                    parse_mode=ParseMode.MARKDOWN,
                )
            except Exception as exc:
                _log.debug("Group welcome failed: %s", exc)

    elif new_status in ("left", "kicked"):
        if flask_app:
            try:
                with flask_app.app_context():
                    from .models import db, TelegramGroup
                    tg = TelegramGroup.query.filter_by(telegram_group_id=group_id).first()
                    if tg:
                        tg.bot_status = "removed"
                        db.session.commit()
            except Exception:
                pass
        _log_event(flask_app, group_id, "bot_removed", f"Bot removed from {group_title}")


# ─── Group message handler (last_activity + custom commands) ──────────────────

async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    message = update.message
    flask_app = context.bot_data.get("flask_app")
    if not chat or chat.type == ChatType.PRIVATE or not message or not flask_app:
        return

    group_id = str(chat.id)
    text = (message.text or "").strip()

    thread_id = getattr(message, "message_thread_id", None)

    tg = None
    try:
        with flask_app.app_context():
            from .models import db, TelegramGroup
            from sqlalchemy.orm.attributes import flag_modified
            tg = TelegramGroup.query.filter_by(telegram_group_id=group_id).first()
            if tg:
                tg.last_activity = datetime.utcnow()
                # Passively discover forum topics from any message.
                if thread_id and _capture_topic_official(tg, thread_id, None):
                    flag_modified(tg, "settings")
                db.session.commit()
    except Exception:
        pass

    if text.startswith("/"):
        cmd_raw = text.split()[0].lstrip("/").split("@")[0].lower()
        cmd_data = None
        try:
            with flask_app.app_context():
                from .models import CustomCommand
                obj = CustomCommand.query.filter_by(
                    telegram_group_id=group_id,
                    command=cmd_raw,
                    enabled=True,
                ).first()
                if obj:
                    cmd_data = {
                        "text": obj.response_text,
                        "type": obj.response_type,
                        "buttons": obj.buttons,
                    }
        except Exception:
            pass

        if cmd_data:
            if not _routing_allowed(tg, f"/{cmd_raw}", thread_id):
                await _routing_reject(update, tg, f"/{cmd_raw}")
                return
            keyboard = None
            if cmd_data["buttons"]:
                rows = [
                    [InlineKeyboardButton(b["text"], url=b["url"])
                     for b in row if b.get("url")]
                    for row in cmd_data["buttons"]
                ]
                rows = [r for r in rows if r]
                if rows:
                    keyboard = InlineKeyboardMarkup(rows)
            try:
                await message.reply_text(
                    cmd_data["text"],
                    parse_mode=ParseMode.MARKDOWN if cmd_data["type"] == "markdown" else None,
                    reply_markup=keyboard,
                )
                _log_event(flask_app, group_id, "command_triggered",
                           f"/{cmd_raw}", {"command": cmd_raw})
            except Exception as exc:
                _log.debug("Custom command reply failed: %s", exc)
                try:
                    from .health import record_bot_error
                    record_bot_error("official", group_id, "command",
                                     f"/{cmd_raw}: {exc}")
                except Exception:
                    pass

    # Word-method verification: check if message is a verification answer
    if not text.startswith("/"):
        sender_id = message.from_user.id if message.from_user else None
        if sender_id:
            vkey = f"{group_id}:{sender_id}"
            vpending = _pending_verifications.get(vkey)
            if vpending and vpending.get("method") == "word":
                expected = vpending.get("answer", "")
                if text.strip().lower() == expected:
                    try:
                        await message.delete()
                    except Exception:
                        pass
                    await _complete_verification(context.bot, None, int(group_id), sender_id, vpending, flask_app, word_mode=True, user=message.from_user)
                    return
                else:
                    vpending["attempts"] = vpending.get("attempts", 0) + 1
                    max_att = vpending.get("max_attempts", 3)
                    if vpending["attempts"] >= max_att:
                        await _fail_verification(context.bot, int(group_id), sender_id, vpending, flask_app)
                    # Wrong answer — silently delete and wait
                    try:
                        await message.delete()
                    except Exception:
                        pass
                    return

    # Auto-responses + Smart Links — check triggers for non-command messages
    if not text.startswith("/") and flask_app:
        try:
            with flask_app.app_context():
                from .models import AutoResponse, TelegramGroup
                # Group-scoped auto-responses and smart links
                responses = AutoResponse.query.filter_by(
                    telegram_group_id=group_id, is_enabled=True
                ).all()
                # User-scoped smart links (scope='user') for the group owner
                tg_group = TelegramGroup.query.filter_by(telegram_group_id=group_id).first()
                if tg_group:
                    user_links = AutoResponse.query.filter_by(
                        owner_user_id=tg_group.owner_user_id,
                        scope="user",
                        response_type="smart_link",
                        is_enabled=True,
                    ).all()
                    # Merge, group-scoped first so they take priority
                    seen_ids = {ar.id for ar in responses}
                    responses = list(responses) + [ar for ar in user_links if ar.id not in seen_ids]

                for ar in responses:
                    # Smart links may have comma-separated trigger phrases
                    trigger_phrases = [p.strip() for p in ar.trigger_text.split(",") if p.strip()] \
                        if ar.response_type == "smart_link" else [ar.trigger_text]

                    matched = False
                    for t in trigger_phrases:
                        check = text if ar.is_case_sensitive else text.lower()
                        trigger = t if ar.is_case_sensitive else t.lower()
                        if ar.match_type == "exact":
                            matched = check == trigger
                        elif ar.match_type == "starts_with":
                            matched = check.startswith(trigger)
                        else:
                            matched = trigger in check
                        if matched:
                            break

                    if matched:
                        # Smart links reply with link_url if set, else response_text
                        reply = (ar.link_url or ar.response_text) if ar.response_type == "smart_link" else ar.response_text
                        try:
                            await message.reply_text(reply)
                        except Exception:
                            pass
                        # Log the trigger
                        try:
                            from .models import AutoReplyLog, db as _db
                            log_user_id = ar.owner_user_id or (tg_group.owner_user_id if tg_group else None)
                            if log_user_id:
                                _db.session.add(AutoReplyLog(
                                    user_id=log_user_id,
                                    auto_response_id=ar.id,
                                    telegram_group_id=group_id,
                                    trigger_text=ar.trigger_text,
                                    message_text=(text or "")[:500],
                                ))
                                _db.session.commit()
                        except Exception:
                            pass
                        break
        except Exception as exc:
            _log.debug("Auto-response check failed: %s", exc)

    # Multimodal image AI
    if flask_app and (message.photo or message.document) and message.from_user and not message.from_user.is_bot:
        try:
            with flask_app.app_context():
                from .models import TelegramGroup as _TGImg
                _tg_img = _TGImg.query.filter_by(telegram_group_id=group_id).first()
                if _tg_img:
                    _img_cfg = (_tg_img.settings or {}).get("image_ai", {})
                    if _img_cfg.get("enabled", False):
                        from .bot_features.image_ai import maybe_handle_image
                        from .bot_features.knowledge_base import KnowledgeBaseSystem
                        _kb_sys = KnowledgeBaseSystem(flask_app)
                        _key_cfg = _kb_sys._load_group_api_key(None, group_id)
                        _api_key = _key_cfg["api_key"] if _key_cfg else None
                        _base_url = _key_cfg.get("base_url") if _key_cfg else None
                        _grp_name = _tg_img.name or _tg_img.title or "this community"
                        _kb_cfg = (_tg_img.settings or {}).get("knowledge_base", {})
                        await maybe_handle_image(
                            bot=context.bot,
                            message=message,
                            group_id=None,
                            telegram_group_id=group_id,
                            image_settings=_img_cfg,
                            kb_settings=_kb_cfg,
                            group_name=_grp_name,
                            app=flask_app,
                            api_key=_api_key,
                            base_url=_base_url,
                        )
        except Exception as _img_exc:
            _log.debug("image_ai error in on_message: %s", _img_exc)

    # Social / human-like appreciation replies
    if text and not text.startswith("/") and flask_app and message.from_user and not message.from_user.is_bot:
        try:
            with flask_app.app_context():
                from .models import TelegramGroup as _TGSocial
                _tg_social = _TGSocial.query.filter_by(telegram_group_id=group_id).first()
                if _tg_social:
                    _social_cfg = (_tg_social.settings or {}).get("social_replies", {})
                    _kb_cfg = (_tg_social.settings or {}).get("knowledge_base", {})
                    if _social_cfg.get("enabled", False):
                        from .bot_features.social_reply import maybe_handle_social_reply
                        await maybe_handle_social_reply(
                            bot=context.bot,
                            message=message,
                            group_id=group_id,
                            user_id=str(message.from_user.id),
                            social_settings=_social_cfg,
                            kb_settings=_kb_cfg,
                        )
        except Exception as _se:
            _log.debug("social_reply error: %s", _se)

    # Message buffering for AI Daily Digest (opt-in per group)
    if text and not text.startswith("/") and flask_app:
        try:
            with flask_app.app_context():
                from .models import TelegramGroup, MessageBuffer, db as _db
                _tg_buf = TelegramGroup.query.filter_by(telegram_group_id=group_id).first()
                _settings = _tg_buf.settings or {} if _tg_buf else {}
                if _tg_buf and _settings.get("ai_message_storage_enabled") and _settings.get("assistant", {}).get("ai_digest_enabled"):
                    sender = message.from_user
                    sender_name = None
                    if sender:
                        sender_name = sender.first_name or sender.username or str(sender.id)
                    _db.session.add(MessageBuffer(
                        telegram_group_id=group_id,
                        sender_user_id=str(sender.id) if sender else "unknown",
                        sender_name=sender_name,
                        message_text=text[:2000],
                    ))
                    _db.session.commit()
        except Exception:
            pass

    # Meeting link capture — detect Zoom/Meet/Teams/Calendly/Webex URLs in group messages
    if text and flask_app:
        _meeting_urls = _MEETING_URL_RE.findall(text)
        if _meeting_urls:
            try:
                with flask_app.app_context():
                    from .models import GroupMeetingLink, TelegramGroup, db as _mdb
                    _mtg_grp = TelegramGroup.query.filter_by(telegram_group_id=group_id).first()
                    if _mtg_grp and _mtg_grp.owner_user_id:
                        for _url in _meeting_urls[:5]:  # cap at 5 per message
                            _platform = "other"
                            for _name, _pat in _MEETING_PLATFORM_MAP:
                                if _pat.search(_url):
                                    _platform = _name
                                    break
                            _poster = message.from_user.username if message.from_user else None
                            _mdb.session.add(GroupMeetingLink(
                                owner_user_id=_mtg_grp.owner_user_id,
                                telegram_group_id=group_id,
                                group_title=group_title,
                                url=_url,
                                platform=_platform,
                                context_text=(text or "")[:500],
                                posted_by_username=_poster,
                            ))
                        _mdb.session.commit()
            except Exception as _me:
                _log.debug("Meeting link capture failed: %s", _me)

    # Reminder auto-detection: "remind me to X in Y / tomorrow / on Friday"
    if text and not text.startswith("/") and flask_app:
        _REMIND_PATTERNS = [
            r"remind me to (.+?) in (\d+)\s*(hour|hr|h|minute|min|m|day|d)s?",
            r"remind me to (.+?) tomorrow",
            r"remind me about (.+?) in (\d+)\s*(hour|hr|h|minute|min|m|day|d)s?",
            r"remind me about (.+?) tomorrow",
        ]
        _detected_reminder = None
        _detected_delta = None
        text_lower = text.lower()
        for pat in _REMIND_PATTERNS:
            m = re.search(pat, text_lower)
            if m:
                groups = m.groups()
                subject = groups[0].strip()
                if "tomorrow" in pat:
                    _detected_delta = timedelta(hours=24)
                else:
                    count, unit = int(groups[1]), groups[2]
                    if unit in ("day", "d"):
                        _detected_delta = timedelta(days=count)
                    elif unit in ("hour", "hr", "h"):
                        _detected_delta = timedelta(hours=count)
                    else:
                        _detected_delta = timedelta(minutes=count)
                _detected_reminder = subject
                break

        if _detected_reminder and _detected_delta and _detected_delta.total_seconds() >= 60:
            try:
                with flask_app.app_context():
                    from .models import db, TelegramGroup, User as DBUser, WorkspaceReminder
                    _tg_r = TelegramGroup.query.filter_by(telegram_group_id=group_id).first()
                    _owner_r = DBUser.query.get(_tg_r.owner_user_id) if _tg_r and _tg_r.owner_user_id else None
                    if not _owner_r:
                        _sender_r = message.from_user
                        if _sender_r:
                            _owner_r = DBUser.query.filter_by(telegram_user_id=str(_sender_r.id)).first()
                    if _owner_r:
                        _remind_at_r = datetime.utcnow() + _detected_delta
                        db.session.add(WorkspaceReminder(
                            owner_user_id=_owner_r.id,
                            telegram_group_id=group_id,
                            original_message=text[:500],
                            reminder_text=_detected_reminder[:500],
                            remind_at=_remind_at_r,
                        ))
                        db.session.commit()
                        try:
                            await message.reply_text(
                                f"📝 Reminder saved! I'll DM you about: _{_detected_reminder}_",
                                parse_mode=ParseMode.MARKDOWN,
                            )
                        except Exception:
                            pass
            except Exception as exc:
                _log.debug("Auto-reminder detection failed: %s", exc)

    # Automation workflows — message_received trigger
    if text and flask_app:
        try:
            from .automation.engine import fire_trigger as _fire_trigger
            await _fire_trigger(
                flask_app=flask_app,
                bot=context.bot,
                trigger_type="message_received",
                group_id=group_id,
                trigger_data={
                    "text": text,
                    "user_id": str(message.from_user.id) if message.from_user else None,
                    "chat_id": group_id,
                    "message_id": message.message_id,
                },
            )
        except Exception as _ae:
            _log.debug("Automation fire_trigger failed: %s", _ae)

    # Message forwarding rules — copy matching messages to destination chats
    if text and flask_app:
        try:
            with flask_app.app_context():
                from .models import ForwardRule, ForwardLog, db as _db_fwd
                fwd_rules = ForwardRule.query.filter_by(
                    source_group_id=group_id, is_active=True
                ).all()
                for rule in fwd_rules:
                    # Keyword filter (empty = forward everything)
                    if rule.keyword_filter:
                        keywords = [k.strip().lower() for k in rule.keyword_filter.split(",") if k.strip()]
                        txt_lower = text.lower()
                        if rule.match_type == "starts_with":
                            matched = any(txt_lower.startswith(k) for k in keywords)
                        else:
                            matched = any(k in txt_lower for k in keywords)
                        if not matched:
                            continue

                    source_text_snippet = text[:500]

                    if rule.require_approval:
                        _db_fwd.session.add(ForwardLog(
                            rule_id=rule.id,
                            source_chat_id=group_id,
                            source_message_id=message.message_id,
                            source_text=source_text_snippet,
                            destination_id=rule.destination_id,
                            status="pending_approval",
                        ))
                        _db_fwd.session.commit()
                    else:
                        try:
                            if rule.prefix_text or rule.suffix_text:
                                parts = []
                                if rule.prefix_text:
                                    parts.append(rule.prefix_text)
                                parts.append(text)
                                if rule.suffix_text:
                                    parts.append(rule.suffix_text)
                                await context.bot.send_message(
                                    chat_id=rule.destination_id,
                                    text="\n".join(parts),
                                )
                            else:
                                await context.bot.copy_message(
                                    chat_id=rule.destination_id,
                                    from_chat_id=group_id,
                                    message_id=message.message_id,
                                )
                            rule.forward_count = (rule.forward_count or 0) + 1
                            _db_fwd.session.add(ForwardLog(
                                rule_id=rule.id,
                                source_chat_id=group_id,
                                source_message_id=message.message_id,
                                source_text=source_text_snippet,
                                destination_id=rule.destination_id,
                                status="forwarded",
                            ))
                            _db_fwd.session.commit()
                        except Exception as fwd_exc:
                            _db_fwd.session.add(ForwardLog(
                                rule_id=rule.id,
                                source_chat_id=group_id,
                                source_message_id=message.message_id,
                                source_text=source_text_snippet,
                                destination_id=rule.destination_id,
                                status="failed",
                                error_msg=str(fwd_exc)[:500],
                            ))
                            _db_fwd.session.commit()
                            _log.debug("Forward failed for rule %s: %s", rule.id, fwd_exc)
        except Exception as exc:
            _log.debug("Forward rule check failed: %s", exc)

    # AutoMod — runs on every non-command group message
    if not text.startswith("/"):
        am_cfg = {}
        try:
            with flask_app.app_context():
                from .models import TelegramGroup
                tg_obj = TelegramGroup.query.filter_by(
                    telegram_group_id=group_id, is_disabled=False
                ).first()
                if tg_obj:
                    am_cfg = (tg_obj.settings or {}).get("automod", {})
        except Exception:
            pass

        if am_cfg.get("enabled"):
            if await _automod_check(context.bot, message, am_cfg, group_id, flask_app):
                return

        # Award XP for non-command messages
        if message.from_user and flask_app:
            old_level = None
            lvl_cfg = {}
            try:
                with flask_app.app_context():
                    from .models import OfficialMember, TelegramGroup
                    tg_xp = TelegramGroup.query.filter_by(telegram_group_id=group_id).first()
                    if tg_xp and (tg_xp.settings or {}).get("levels", {}).get("enabled"):
                        lvl_cfg = (tg_xp.settings or {}).get("levels", {})
                        m_xp = OfficialMember.query.filter_by(
                            telegram_group_id=group_id,
                            telegram_user_id=str(message.from_user.id),
                        ).first()
                        if m_xp:
                            old_level = m_xp.level
            except Exception:
                pass

            await _award_xp(flask_app, group_id, message.from_user)

            if old_level is not None:
                try:
                    with flask_app.app_context():
                        from .models import OfficialMember
                        m_xp2 = OfficialMember.query.filter_by(
                            telegram_group_id=group_id,
                            telegram_user_id=str(message.from_user.id),
                        ).first()
                        if m_xp2 and m_xp2.level > old_level:
                            tpl = lvl_cfg.get(
                                "level_up_message",
                                "🎉 {name} just reached Level {level}! Keep it up 🚀",
                            )
                            _u = message.from_user
                            _first = _u.first_name or ""
                            _last  = _u.last_name  or ""
                            _uname = _u.username   or ""
                            if _first and _last:
                                _display = f"{_first} {_last}"
                            elif _uname:
                                _display = f"@{_uname}"
                            else:
                                _display = _first or "User"
                            lvl_up_text = tpl.format(
                                name=_display,
                                first_name=_first or "User",
                                username=f"@{_uname}" if _uname else _first,
                                level=m_xp2.level,
                                user_id=_u.id,
                            )
                            lvl_up_msg = await context.bot.send_message(
                                chat_id=chat.id,
                                text=lvl_up_text,
                            )
                            asyncio.get_running_loop().call_later(
                                15, lambda: asyncio.ensure_future(
                                    _safe_delete(context.bot, chat.id, lvl_up_msg.message_id)
                                )
                            )
                except Exception:
                    pass

    # ── Assistant Hub: buffer this message for extraction ─────────────────────
    # Only buffer here when Echo is not configured. When ECHO_BOT_TOKEN is set,
    # Echo handles buffering — doing it here too would double-buffer every message
    # and consume extraction quota twice for groups that have both bots present.
    if not Config.ECHO_BOT_TOKEN:
        try:
            from .assistant.hub_message_router import buffer_hub_message
            buffer_hub_message(flask_app, chat.id, message)
        except Exception:
            pass

    # ── Assistant Hub: @mention reply engine ──────────────────────────────────
    msg_text = update.effective_message.text if update.effective_message else None
    if msg_text and flask_app:
        try:
            bot_username = context.bot.username
            if bot_username and f"@{bot_username}" in msg_text:
                from .assistant.hub_models import HubBotIdentity, HubConnectedGroup
                from .assistant.hub_reply import handle_mention_async
                with flask_app.app_context():
                    group_rec = HubConnectedGroup.query.filter_by(
                        telegram_group_id=chat.id,
                        is_active=True,
                    ).first()
                    if group_rec and group_rec.consent_confirmed_at:
                        bot_rec = HubBotIdentity.query.filter_by(
                            id=group_rec.bot_id, is_active=True
                        ).first()
                        if bot_rec:
                            token = Config.TELEGRAM_BOT_TOKEN
                            asyncio.ensure_future(handle_mention_async(
                                bot_token=token,
                                bot_username=bot_username,
                                message_text=msg_text,
                                chat_id=chat.id,
                                message_id=update.effective_message.message_id,
                                bot_id=group_rec.bot_id,
                                user_id=bot_rec.user_id,
                                flask_app=flask_app,
                            ))
        except Exception as _exc:
            _log.debug("hub_reply mention handler error: %s", _exc)


# ─── New member join handler ──────────────────────────────────────────────────

async def on_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Fires when any member's status changes in the group.
    Handles new member joins: logs the event and triggers verification if enabled.
    """
    flask_app = context.bot_data.get("flask_app")
    chat_member = update.chat_member
    if not chat_member:
        return

    chat = update.effective_chat
    if not chat or chat.type == ChatType.PRIVATE:
        return

    old_status = chat_member.old_chat_member.status if chat_member.old_chat_member else "left"
    new_status = chat_member.new_chat_member.status

    # Handle bans/kicks separately for automation
    is_banned = (
        new_status in ("kicked", "banned")
        and old_status not in ("kicked", "banned")
    )

    # Only handle new joins (left/kicked/banned → member/restricted)
    is_new_join = (
        old_status in ("left", "kicked", "banned")
        and new_status in ("member", "restricted")
    )

    user = chat_member.new_chat_member.user
    group_id = str(chat.id)

    if is_banned and flask_app:
        try:
            from .automation.engine import fire_trigger as _fire_trigger_ban
            await _fire_trigger_ban(
                flask_app=flask_app,
                bot=context.bot,
                trigger_type="member_banned",
                group_id=group_id,
                trigger_data={"user_id": str(user.id), "username": user.username},
            )
        except Exception:
            pass

    if not is_new_join:
        return

    _log.info(
        "[OfficialBot] New member: user_id=%s name=%s group=%s (%s)",
        user.id, user.first_name, group_id, chat.title,
    )

    _log_event(flask_app, group_id, "member_joined",
               f"{user.first_name} (id={user.id}) joined",
               {"telegram_user_id": str(user.id)})

    if not flask_app:
        return

    # Automation workflows — member_joined trigger
    try:
        from .automation.engine import fire_trigger as _fire_trigger_join
        await _fire_trigger_join(
            flask_app=flask_app,
            bot=context.bot,
            trigger_type="member_joined",
            group_id=group_id,
            trigger_data={"user_id": str(user.id), "first_name": user.first_name, "username": user.username},
        )
    except Exception:
        pass

    # Single query: increment member count AND build GroupContext for feature dispatch.
    group_ctx = None
    try:
        with flask_app.app_context():
            from .models import db, TelegramGroup
            tg = TelegramGroup.query.filter_by(telegram_group_id=group_id).first()
            if tg:
                tg.member_count = (tg.member_count or 0) + 1
                db.session.commit()
                if not tg.is_disabled:
                    group_ctx = GroupContext.from_telegram_group(tg)
    except Exception as exc:
        _log.error("[OfficialBot] Failed to load group on new member: %s", exc)
        return

    if not group_ctx:
        return

    v_cfg = group_ctx.settings.get("verification", {})
    _log.info(
        "[OfficialBot] Group %s verification.enabled=%s method=%s",
        group_id, v_cfg.get("enabled", False), v_cfg.get("method", "button"),
    )

    if v_cfg.get("enabled", False):
        await _start_verification(context.bot, chat, user, v_cfg, flask_app, group_id)
    elif group_ctx.settings.get("welcome", {}).get("enabled", True):
        try:
            if _can_send_to_group(str(chat.id)):
                await WelcomeSystem(flask_app).send_welcome(context.bot, chat.id, user, group_ctx)
        except Exception as _we:
            _log.debug("[OfficialBot] Welcome on join failed: %s", _we)


# ─── Verification helpers ─────────────────────────────────────────────────────

async def _start_verification(bot, chat, user, v_cfg, flask_app, group_id):
    """Restrict and challenge a newly joined user."""
    chat_id = chat.id
    user_id = user.id
    key = f"{chat_id}:{user_id}"
    method = v_cfg.get("method", "button")
    timeout = int(v_cfg.get("timeout_seconds", 300))

    # Restrict immediately
    try:
        await bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=ChatPermissions(can_send_messages=False),
        )
        _log.info("[OfficialBot] Restricted new member %s in group %s", user_id, chat_id)
    except Exception as exc:
        _log.warning("[OfficialBot] Cannot restrict member %s in %s: %s", user_id, chat_id, exc)
        return

    msg = None
    answer = None

    try:
        if method == "math":
            a = random.randint(1, 20)
            b = random.randint(1, 20)
            answer = a + b
            wrong_set: set = set()
            while len(wrong_set) < 3:
                w = answer + random.randint(-5, 5)
                if w != answer and w > 0:
                    wrong_set.add(w)
            options = [answer] + list(wrong_set)[:3]
            random.shuffle(options)
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(str(o), callback_data=f"v:{chat_id}:{user_id}:m:{o}:{answer}")
                    for o in options[:2]
                ],
                [
                    InlineKeyboardButton(str(o), callback_data=f"v:{chat_id}:{user_id}:m:{o}:{answer}")
                    for o in options[2:]
                ],
            ])
            msg = await bot.send_message(
                chat_id=chat_id,
                text=(
                    f"🔢 Welcome {user.first_name}!\n\n"
                    f"Solve to verify: *{a} + {b} = ?*\n"
                    f"You have {timeout}s."
                ),
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN,
            )
        elif method == "word":
            word_list = v_cfg.get("word_list") or _DEFAULT_VERIFY_WORDS
            if word_list and isinstance(word_list[0], (list, tuple)):
                pair = random.choice(word_list)
                answer = str(pair[0]).lower().strip()
                question = str(pair[1])
            else:
                pair = random.choice(_DEFAULT_VERIFY_WORDS)
                answer, question = pair[0], pair[1]
            msg = await bot.send_message(
                chat_id=chat_id,
                text=(
                    f"🔤 Welcome {user.first_name}!\n\n"
                    f"Type the answer to verify: *{question}*\n"
                    f"You have {timeout} seconds."
                ),
                parse_mode=ParseMode.MARKDOWN,
            )
        else:
            # Default: button
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "✅ I am human — Click to verify",
                    callback_data=f"v:{chat_id}:{user_id}:b",
                )
            ]])
            msg = await bot.send_message(
                chat_id=chat_id,
                text=(
                    f"👋 Welcome {user.first_name}!\n\n"
                    f"Click the button below to verify you're human.\n"
                    f"You have {timeout} seconds."
                ),
                reply_markup=keyboard,
            )
    except Exception as exc:
        _log.error("[OfficialBot] Failed to send verification challenge: %s", exc)
        return

    _pending_verifications[key] = {
        "method": method,
        "msg_id": msg.message_id if msg else None,
        "answer": answer,
        "expires_at": datetime.utcnow() + timedelta(seconds=timeout),
        "kick_on_fail": bool(v_cfg.get("kick_on_fail", True)),
        "max_attempts": int(v_cfg.get("max_attempts", 3)),
        "attempts": 0,
        "auto_delete_on_timeout": bool(v_cfg.get("auto_delete_on_timeout", True)),
    }
    _save_pending_verification(flask_app, chat_id, user_id, _pending_verifications[key])

    asyncio.get_running_loop().call_later(
        timeout,
        lambda: asyncio.ensure_future(_verification_timeout(bot, chat_id, user_id)),
    )

    _log.info(
        "[OfficialBot] Verification challenge sent: user=%s group=%s method=%s timeout=%ds",
        user_id, chat_id, method, timeout,
    )
    _log_event(flask_app, group_id, "verification_started",
               f"User {user_id} ({user.first_name}) challenged",
               {"telegram_user_id": str(user_id), "method": method})


async def _handle_verification_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle v: prefixed callback_data for official bot verification."""
    query = update.callback_query
    data = query.data  # "v:{chat_id}:{user_id}:b" or "v:{chat_id}:{user_id}:m:{chosen}:{correct}"
    flask_app = context.bot_data.get("flask_app")

    parts = data.split(":")
    try:
        chat_id = int(parts[1])
        user_id_target = int(parts[2])
        vtype = parts[3]
    except (IndexError, ValueError):
        await query.answer()
        return

    actual_user_id = update.effective_user.id
    if actual_user_id != user_id_target:
        await query.answer("This verification is not for you.", show_alert=True)
        return

    key = f"{chat_id}:{user_id_target}"
    pending = _pending_verifications.get(key)

    if not pending:
        await query.answer("Verification already completed or expired.")
        return

    if datetime.utcnow() > pending["expires_at"]:
        await query.answer("Verification expired!", show_alert=True)
        await _fail_verification(context.bot, chat_id, user_id_target, pending, flask_app)
        return

    verified = False
    if vtype == "b":
        verified = True
    elif vtype == "m":
        try:
            chosen = int(parts[4])
            correct = int(parts[5])
            verified = (chosen == correct)
        except (IndexError, ValueError):
            verified = False

    if verified:
        await _complete_verification(context.bot, query, chat_id, user_id_target, pending, flask_app, user=query.from_user)
    else:
        pending["attempts"] += 1
        max_att = pending["max_attempts"]
        if pending["attempts"] >= max_att:
            await query.answer(f"❌ Too many wrong answers. Removing you.", show_alert=True)
            await _fail_verification(context.bot, chat_id, user_id_target, pending, flask_app)
        else:
            remaining = max_att - pending["attempts"]
            await query.answer(f"❌ Wrong! {remaining} attempt(s) left.")


async def _complete_verification(bot, query, chat_id, user_id, pending, flask_app, word_mode=False, user=None):
    key = f"{chat_id}:{user_id}"
    group_id = str(chat_id)
    try:
        await bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
            ),
        )
        if pending.get("msg_id"):
            try:
                await bot.delete_message(chat_id=chat_id, message_id=pending["msg_id"])
            except Exception:
                pass
        if not word_mode and query is not None:
            await query.answer("✅ Verified! Welcome!")
        first_name = (
            query.from_user.first_name
            if (not word_mode and query is not None and query.from_user)
            else f"User {user_id}"
        )
        try:
            notif = await bot.send_message(
                chat_id=chat_id,
                text=f"✅ {first_name} verified and joined!",
            )
            asyncio.get_running_loop().call_later(
                8, lambda: asyncio.ensure_future(_safe_delete(bot, chat_id, notif.message_id))
            )
        except Exception:
            pass
        _log.info("[OfficialBot] User %s verified in group %s", user_id, chat_id)
        _log_event(flask_app, group_id, "verification_passed",
                   f"User {user_id} passed verification",
                   {"telegram_user_id": str(user_id)})
        if flask_app:
            try:
                with flask_app.app_context():
                    from .models import db, OfficialMember
                    m = OfficialMember.query.filter_by(
                        telegram_group_id=group_id,
                        telegram_user_id=str(user_id),
                    ).first()
                    if m:
                        m.is_verified = True
                        db.session.commit()
            except Exception as _ve:
                _log.debug("[OfficialBot] Failed to set is_verified: %s", _ve)
        # Send welcome message now that the user is unrestricted
        if flask_app and user is not None:
            try:
                grp_ctx = None
                with flask_app.app_context():
                    from .models import TelegramGroup
                    _tg_w = TelegramGroup.query.filter_by(
                        telegram_group_id=group_id, is_disabled=False
                    ).first()
                    if _tg_w and (_tg_w.settings or {}).get("welcome", {}).get("enabled", True):
                        grp_ctx = GroupContext.from_telegram_group(_tg_w)
                if grp_ctx and _can_send_to_group(str(chat_id)):
                    await WelcomeSystem(flask_app).send_welcome(bot, chat_id, user, grp_ctx)
            except Exception as _we:
                _log.debug("[OfficialBot] Post-verification welcome failed: %s", _we)
    except Exception as exc:
        _log.error("[OfficialBot] Complete verification error user=%s: %s", user_id, exc)
    finally:
        _pending_verifications.pop(key, None)
        _remove_pending_verification(flask_app, chat_id, user_id)


async def _fail_verification(bot, chat_id, user_id, pending, flask_app):
    key = f"{chat_id}:{user_id}"
    group_id = str(chat_id)
    try:
        if pending.get("kick_on_fail", True):
            # 1-C-02: temp ban + write PendingUnban; scheduler retries unban after 1h
            await bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
            _log.info("[OfficialBot] Temp-banned unverified user %s from group %s", user_id, chat_id)
            if flask_app:
                try:
                    with flask_app.app_context():
                        from .models import db, PendingUnban
                        from datetime import timedelta
                        db.session.add(PendingUnban(
                            telegram_chat_id=chat_id,
                            telegram_user_id=user_id,
                            unban_at=datetime.utcnow() + timedelta(hours=1),
                        ))
                        db.session.commit()
                except Exception as db_exc:
                    _log.warning("PendingUnban write failed: %s", db_exc)
        if pending.get("msg_id"):
            try:
                await bot.delete_message(chat_id=chat_id, message_id=pending["msg_id"])
            except Exception:
                pass
        _log_event(flask_app, group_id, "verification_failed",
                   f"User {user_id} failed verification",
                   {"telegram_user_id": str(user_id), "kick": pending.get("kick_on_fail", True)})
    except Exception as exc:
        _log.error("[OfficialBot] Fail verification error user=%s: %s", user_id, exc)
    finally:
        _pending_verifications.pop(key, None)
        _remove_pending_verification(flask_app, chat_id, user_id)


async def _verification_timeout(bot, chat_id, user_id):
    key = f"{chat_id}:{user_id}"
    pending = _pending_verifications.get(key)
    if not pending:
        return
    if datetime.utcnow() <= pending["expires_at"]:
        return
    _log.info("[OfficialBot] Verification timed out: user=%s group=%s", user_id, chat_id)

    if pending.get("kick_on_fail", True):
        # Full fail: kick + delete message
        await _fail_verification(bot, chat_id, user_id, pending, None)
    else:
        # Restrict-only: just auto-delete the challenge message if enabled
        if pending.get("auto_delete_on_timeout", True) and pending.get("msg_id"):
            try:
                await bot.delete_message(chat_id=chat_id, message_id=pending["msg_id"])
            except Exception:
                pass
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=f"⏰ Verification timed out for user {user_id}. They remain restricted until manually verified.",
            )
        except Exception:
            pass
        _pending_verifications.pop(key, None)


async def _safe_delete(bot, chat_id, message_id):
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass


# ─── AutoMod helper ───────────────────────────────────────────────────────────

def _msg_preview(msg, max_len=500):
    """Return a best-effort text preview of a Telegram message before deletion."""
    text = (msg.text or msg.caption or "").strip()
    if not text:
        entities = list(msg.entities or []) + list(msg.caption_entities or [])
        urls = [getattr(e, "url", None) for e in entities if getattr(e, "url", None)]
        if urls:
            text = "  ".join(urls[:3])
    if not text:
        if getattr(msg, "photo", None):          text = "📷 Photo"
        elif getattr(msg, "video", None):        text = "🎥 Video"
        elif getattr(msg, "voice", None):        text = "🎤 Voice message"
        elif getattr(msg, "audio", None):        text = "🎵 Audio"
        elif getattr(msg, "document", None):     text = "📄 Document"
        elif getattr(msg, "sticker", None):
            emoji = getattr(msg.sticker, "emoji", "") or ""
            text = f"🎴 Sticker {emoji}".strip()
        elif getattr(msg, "animation", None):    text = "🎞️ GIF"
        elif getattr(msg, "video_note", None):   text = "📹 Video note"
        elif getattr(msg, "contact", None):      text = "📞 Contact"
        elif getattr(msg, "location", None):     text = "📍 Location"
        elif getattr(msg, "poll", None):         text = "📊 Poll"
    if not text:
        return None
    return (text[: max_len - 1] + "…") if len(text) >= max_len else text


async def _automod_execute(bot, message, group_id: str, flask_app, rule: str, action: str,
                           mute_minutes: int = 5, notify_seconds: int = 10):
    """Delete the offending message and apply the configured action."""
    chat_id = message.chat_id
    user_id = message.from_user.id
    username = message.from_user.username if message.from_user else None
    first_name = (message.from_user.first_name or "User") if message.from_user else "User"
    rule_label = rule.replace("_", " ")
    msg_text = _msg_preview(message)

    try:
        await bot.delete_message(chat_id=chat_id, message_id=message.message_id)
    except Exception:
        pass

    async def _timed_notify(text):
        try:
            nm = await bot.send_message(chat_id=chat_id, text=text)
            asyncio.get_running_loop().call_later(
                notify_seconds,
                lambda: asyncio.ensure_future(_safe_delete(bot, chat_id, nm.message_id)),
            )
        except Exception:
            pass

    if action in ("delete", "warn"):
        await _timed_notify(f"⚠️ {first_name}, your message was removed: {rule_label}.")
    elif action == "mute":
        try:
            await bot.restrict_chat_member(
                chat_id=chat_id, user_id=user_id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=datetime.utcnow() + timedelta(minutes=mute_minutes),
            )
            await _timed_notify(f"🔇 {first_name} muted {mute_minutes}min: {rule_label}.")
        except Exception as exc:
            _log.warning("[OfficialBot] AutoMod mute failed: %s", exc)
    elif action == "ban":
        try:
            await bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
        except Exception as exc:
            _log.warning("[OfficialBot] AutoMod ban failed: %s", exc)
    elif action == "kick":
        try:
            await bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
            await bot.unban_chat_member(chat_id=chat_id, user_id=user_id)
        except Exception as exc:
            _log.warning("[OfficialBot] AutoMod kick failed: %s", exc)

    _log.info("[OfficialBot] AutoMod: group=%s user=%s rule=%s action=%s", group_id, user_id, rule, action)
    meta = {
        "target_user_id": str(user_id),
        "target_username": username or "",
        "moderator_username": "AutoMod",
        "rule": rule,
        "action": action,
    }
    if msg_text:
        meta["message_text"] = msg_text
    _log_event(flask_app, group_id, "automod_action",
               f"User {user_id}: {rule} → {action}", meta)


async def _automod_check(bot, message, am_cfg: dict, group_id: str, flask_app) -> bool:
    """Apply all configured automod rules. Returns True if message was blocked."""
    text = (message.text or message.caption or "").strip()
    chat_id = message.chat_id
    user_id = message.from_user.id if message.from_user else None
    if not user_id:
        return False

    # Skip admins/creator
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        if member.status in ("creator", "administrator"):
            return False
    except Exception:
        pass

    # Normalize homoglyphs so all subsequent text checks use the normalized form
    if am_cfg.get("homoglyphs", {}).get("enabled") and text:
        text = normalize_homoglyphs(text)

    # ── 1. Bad words ─────────────────────────────────────────────────────────
    bw_cfg = am_cfg.get("bad_words", {})
    if bw_cfg.get("enabled") and text:
        words = bw_cfg.get("words", [])
        text_lower = text.lower()
        for w in words:
            if w.lower() in text_lower:
                await _automod_execute(bot, message, group_id, flask_app,
                                       "bad_words", bw_cfg.get("action", "delete"))
                return True

    # ── 2. Spam detection ────────────────────────────────────────────────────
    spam_cfg = am_cfg.get("spam", {})
    if spam_cfg.get("enabled"):
        skey = f"{chat_id}:{user_id}"
        now = datetime.utcnow()
        window = spam_cfg.get("time_window_seconds", 10)
        max_msgs = spam_cfg.get("max_messages", 5)
        _spam_tracker.setdefault(skey, [])
        _spam_tracker[skey] = [t for t in _spam_tracker[skey] if (now - t).total_seconds() < window]
        _spam_tracker[skey].append(now)
        if len(_spam_tracker[skey]) > max_msgs:
            _spam_tracker[skey] = []
            await _automod_execute(bot, message, group_id, flask_app,
                                   "spam", spam_cfg.get("action", "mute"),
                                   mute_minutes=spam_cfg.get("mute_duration_minutes", 10))
            return True

    # ── 3. External links ────────────────────────────────────────────────────
    ext_cfg = am_cfg.get("external_links", {})
    if ext_cfg.get("enabled") and text and _URL_RE.search(text):
        whitelist = ext_cfg.get("whitelist", [])
        urls = _URL_RE.findall(text)
        blocked = any(not any(a in u for a in whitelist) for u in urls)
        if blocked:
            await _automod_execute(bot, message, group_id, flask_app,
                                   "external_links", ext_cfg.get("action", "delete"))
            return True

    # ── 4. Telegram links ────────────────────────────────────────────────────
    tl_cfg = am_cfg.get("telegram_links", {})
    if tl_cfg.get("enabled") and text and _TELEGRAM_LINK_RE.search(text):
        await _automod_execute(bot, message, group_id, flask_app,
                               "telegram_links", tl_cfg.get("action", "delete"))
        return True

    # ── 5. Caps lock ─────────────────────────────────────────────────────────
    caps_cfg = am_cfg.get("caps_lock", {})
    if caps_cfg.get("enabled") and text:
        min_len = caps_cfg.get("min_length", 10)
        threshold = caps_cfg.get("threshold_percent", caps_cfg.get("threshold", 70))
        letters = [c for c in text if c.isalpha()]
        if len(letters) >= min_len:
            ratio = sum(1 for c in letters if c.isupper()) / len(letters) * 100
            if ratio >= threshold:
                await _automod_execute(bot, message, group_id, flask_app,
                                       "caps_lock", caps_cfg.get("action", "delete"))
                return True

    # ── 6. Excessive emojis ──────────────────────────────────────────────────
    em_cfg = am_cfg.get("excessive_emojis", {})
    if em_cfg.get("enabled") and text:
        count = len(_EMOJI_RE.findall(text))
        if count > em_cfg.get("max_emojis", 10):
            await _automod_execute(bot, message, group_id, flask_app,
                                   "excessive_emojis", em_cfg.get("action", "delete"))
            return True

    # ── 7. Forwarded messages ────────────────────────────────────────────────
    fwd_cfg = am_cfg.get("forwarded_messages", {})
    if fwd_cfg.get("enabled") and (message.forward_date or message.forward_from or message.forward_from_chat):
        await _automod_execute(bot, message, group_id, flask_app,
                               "forwarded_messages", fwd_cfg.get("action", "delete"))
        return True

    # ── 8. Email detection ───────────────────────────────────────────────────
    mail_cfg = am_cfg.get("email_detection", {})
    if mail_cfg.get("enabled") and text and _EMAIL_RE.search(text):
        await _automod_execute(bot, message, group_id, flask_app,
                               "email_detection", mail_cfg.get("action", "delete"))
        return True

    # ── 9. Language filter ───────────────────────────────────────────────────
    lang_cfg = am_cfg.get("language_filter", {})
    if lang_cfg.get("enabled") and text:
        for lang in lang_cfg.get("languages", []):
            pattern = _LANG_RANGES.get(lang)
            if pattern and pattern.search(text):
                await _automod_execute(bot, message, group_id, flask_app,
                                       "language_filter", lang_cfg.get("action", "delete"))
                return True

    # ── 10. Bot mentions ─────────────────────────────────────────────────────
    bm_cfg = am_cfg.get("bot_mentions", {})
    if bm_cfg.get("enabled"):
        entities = message.entities or []
        for entity in entities:
            if str(entity.type) in ("MessageEntityType.MENTION", "mention"):
                mention = text[entity.offset: entity.offset + entity.length].lstrip("@")
                if mention.lower().endswith("bot"):
                    await _automod_execute(bot, message, group_id, flask_app,
                                           "bot_mentions", bm_cfg.get("action", "delete"))
                    return True

    # ── 11. Spoiler content ──────────────────────────────────────────────────
    sp_cfg = am_cfg.get("spoiler_content", {})
    if sp_cfg.get("enabled"):
        entities = message.entities or message.caption_entities or []
        for entity in entities:
            if str(entity.type) in ("MessageEntityType.SPOILER", "spoiler"):
                await _automod_execute(bot, message, group_id, flask_app,
                                       "spoiler_content", sp_cfg.get("action", "delete"))
                return True

    # ── Media-type checks ────────────────────────────────────────────────────
    _media_checks = [
        ("contact_sharing",  message.contact is not None),
        ("location_sharing", message.location is not None),
        ("voice_notes",      message.voice is not None),
        ("video_notes",      message.video_note is not None),
        ("file_attachments", message.document is not None),
        ("photos",           bool(message.photo)),
        ("videos",           message.video is not None),
        ("stickers",         message.sticker is not None),
    ]
    for rule_key, present in _media_checks:
        mc = am_cfg.get(rule_key, {})
        if mc.get("enabled") and present:
            await _automod_execute(bot, message, group_id, flask_app,
                                   rule_key, mc.get("action", "delete"))
            return True

    # ── Smart AI Moderation (OPTIONAL — off by default) ──────────────────────
    # The official bot is rule-based by default. AI relevance/promo moderation
    # runs ONLY when an admin explicitly enables Smart AI Moderation, sets a
    # group topic, AND a workspace AI key resolves. Otherwise it silently no-ops
    # so we never act as if AI is on when it isn't.
    sm_cfg = am_cfg.get("smart_mod", {})
    if (sm_cfg.get("enabled") and sm_cfg.get("ai_enabled") and text
            and len((sm_cfg.get("group_topic") or "").strip()) > 0
            and len(text.split()) >= 10):
        if await _official_ai_moderation(bot, message, text, group_id, sm_cfg, flask_app):
            return True

    return False


async def _official_ai_moderation(bot, message, text, group_id, sm_cfg, flask_app) -> bool:
    """Optional Smart AI Moderation for official-bot groups. Returns True if the
    message was blocked. No-ops (returns False) unless an AI key resolves for the
    group owner — so the default experience stays rule-based."""
    user_id = message.from_user.id if message.from_user else None
    if not user_id:
        return False
    # Per-user cooldown so we don't spend tokens on every message.
    key = (message.chat_id, user_id)
    rate = sm_cfg.get("ai_rate_limit_seconds", 30)
    now = datetime.utcnow()
    last = _official_ai_cooldown.get(key)
    if last and (now - last).total_seconds() < rate:
        return False
    _official_ai_cooldown[key] = now

    topic = (sm_cfg.get("group_topic") or "").strip()
    key_info = None
    try:
        with flask_app.app_context():
            from .models import TelegramGroup, User
            from .assistant.ai_key_resolver import get_workspace_ai_key
            tg = TelegramGroup.query.filter_by(telegram_group_id=str(group_id)).first()
            owner = User.query.get(tg.owner_user_id) if (tg and tg.owner_user_id) else None
            if not owner:
                return False
            key_info = get_workspace_ai_key(owner)
            if not key_info.get("api_key"):
                return False  # AI not configured → stay rule-based, silently
    except Exception as exc:
        _log.debug("[OfficialBot] Smart AI key resolve failed: %s", exc)
        return False

    try:
        from .bot_features.moderation import ModerationSystem
        import asyncio as _aio
        loop = _aio.get_running_loop()
        verdict, _reason = await loop.run_in_executor(
            None, ModerationSystem._call_ai_moderation,
            text, topic, (message.chat.title or ""), key_info,
        )
    except Exception as exc:
        _log.debug("[OfficialBot] Smart AI moderation call failed: %s", exc)
        return False

    if verdict in ("promotional", "irrelevant"):
        await _automod_execute(bot, message, group_id, flask_app,
                               "smart_ai", sm_cfg.get("action", "delete"))
        return True
    return False


# ─── Shared helpers for moderation ───────────────────────────────────────────

async def _apply_xp_penalty(flask_app, group_id: str, user_id: int, action: str):
    """Deduct XP per the group's levels.xp_penalty_<action> setting."""
    penalty_key = f"xp_penalty_{action}"
    try:
        with flask_app.app_context():
            from .models import TelegramGroup, OfficialMember, db
            tg = TelegramGroup.query.filter_by(telegram_group_id=group_id).first()
            if not tg:
                return
            penalty = (tg.settings or {}).get("levels", {}).get(penalty_key, 0)
            if not penalty:
                return
            m = OfficialMember.query.filter_by(
                telegram_group_id=group_id,
                telegram_user_id=str(user_id),
            ).first()
            if m:
                m.xp = max(0, (m.xp or 0) + penalty)  # penalty values are negative
                m.xp_1d  = max(0, (m.xp_1d  or 0) + penalty)
                m.xp_7d  = max(0, (m.xp_7d  or 0) + penalty)
                m.xp_30d = max(0, (m.xp_30d or 0) + penalty)
                db.session.commit()
    except Exception as exc:
        _log.debug("[OfficialBot] XP penalty (%s) failed: %s", action, exc)


async def _check_warn_escalation(bot, chat_id: int, group_id: str,
                                  target_id: int, target_name: str,
                                  warn_count: int, flask_app):
    """Apply escalation or max-warnings action when warn count crosses a threshold."""
    mod = {}
    try:
        with flask_app.app_context():
            from .models import TelegramGroup
            tg = TelegramGroup.query.filter_by(telegram_group_id=group_id).first()
            if tg:
                mod = (tg.settings or {}).get("moderation", {})
    except Exception as exc:
        _log.debug("[OfficialBot] Warn escalation settings load failed: %s", exc)
        return

    max_warnings = mod.get("max_warnings", 3)
    warning_action = mod.get("warning_action", "mute")
    mute_duration = mod.get("mute_duration_minutes", 60)

    async def _act(action, duration_min=mute_duration, label=""):
        try:
            if action == "mute":
                until = datetime.utcnow() + timedelta(minutes=duration_min)
                await bot.restrict_chat_member(
                    chat_id=chat_id, user_id=target_id,
                    permissions=ChatPermissions(can_send_messages=False),
                    until_date=until,
                )
                notif = await bot.send_message(
                    chat_id=chat_id,
                    text=f"🔇 {target_name} muted {duration_min}min{label}.",
                )
            elif action in ("ban", "kick"):
                await bot.ban_chat_member(chat_id=chat_id, user_id=target_id)
                if action == "kick":
                    await bot.unban_chat_member(chat_id=chat_id, user_id=target_id)
                icon = "🚫" if action == "ban" else "👢"
                notif = await bot.send_message(
                    chat_id=chat_id,
                    text=f"{icon} {target_name} {action}ned{label}.",
                )
            else:
                return
            asyncio.get_running_loop().call_later(
                15, lambda: asyncio.ensure_future(_safe_delete(bot, chat_id, notif.message_id))
            )
        except Exception as exc:
            _log.warning("[OfficialBot] Warn escalation action %s failed: %s", action, exc)

    if mod.get("escalation_enabled"):
        steps = sorted(mod.get("escalation_steps", []),
                       key=lambda s: s.get("at_warning", 99), reverse=True)
        for step in steps:
            if warn_count >= step.get("at_warning", 99):
                await _act(
                    step.get("action", "mute"),
                    step.get("duration_minutes", mute_duration),
                    f" (escalation at {warn_count} warnings)",
                )
                return
    elif warn_count >= max_warnings:
        await _act(warning_action, mute_duration, f" (reached {max_warnings} warnings)")


# ─── Moderation commands ─────────────────────────────────────────────────────

def _is_group_chat(update: Update) -> bool:
    return update.effective_chat and update.effective_chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)


# ── Command routing helpers (official bot) ────────────────────────────────────

def _routing_allowed(tg_group, command: str, thread_id) -> bool:
    """Check command_routing config. Returns True if command is allowed in this thread."""
    settings = (tg_group.settings or {}) if tg_group else {}
    routing = settings.get("command_routing")
    if not routing:
        return True
    commands_cfg = routing.get("commands") or {}
    cmd_rule = commands_cfg.get(command) or commands_cfg.get(command.lstrip("/"))
    if not cmd_rule:
        return True
    scope = cmd_rule.get("scope", "all_group")
    if scope == "all_group":
        return True
    if scope == "disabled":
        return False
    allowed_ids = [str(t) for t in (cmd_rule.get("topic_ids") or [])]
    if not allowed_ids:
        return False
    return str(thread_id) in allowed_ids if thread_id is not None else False


async def _routing_reject(update, tg_group, command: str):
    """Send rejection reply or stay silent based on restricted_reply setting."""
    settings = (tg_group.settings or {}) if tg_group else {}
    routing = settings.get("command_routing") or {}
    if routing.get("restricted_reply", "silent") != "message":
        return
    msg_tpl = routing.get(
        "restricted_message",
        "⚠️ This command is only available in the {topic} topic.",
    )
    commands_cfg = routing.get("commands") or {}
    cmd_rule = commands_cfg.get(command) or commands_cfg.get(command.lstrip("/")) or {}
    topic_ids = cmd_rule.get("topic_ids") or []
    topics = routing.get("topics") or []
    topic_names = [
        t["name"] for t in topics if str(t.get("thread_id")) in [str(x) for x in topic_ids]
    ]
    topic_label = ", ".join(topic_names) if topic_names else "a specific topic"
    try:
        await update.message.reply_text(msg_tpl.format(topic=topic_label))
    except Exception:
        pass


def _capture_topic_official(tg_group, thread_id, topic_name=None) -> bool:
    """Upsert a known forum topic into tg_group.settings['command_routing']['topics']
    and into the group_forum_topics DB table.

    Returns True if settings was mutated (caller must flag_modified + commit).
    The DB upsert is best-effort and does not affect the return value.
    """
    if not tg_group or thread_id is None:
        return False
    settings = tg_group.settings or {}
    routing = settings.setdefault("command_routing", {
        "topics": [], "commands": {}, "restricted_reply": "silent",
        "restricted_message": "⚠️ This command is only available in the {topic} topic.",
    })
    topics = routing.setdefault("topics", [])
    tid = str(thread_id)
    name = topic_name or f"Topic {tid}"
    settings_mutated = False
    for t in topics:
        if str(t.get("thread_id")) == tid:
            if topic_name and t.get("name") != topic_name:
                t["name"] = topic_name
                settings_mutated = True
            break
    else:
        topics.append({"thread_id": tid, "name": name})
        settings_mutated = True

    # Persist to group_forum_topics table (best-effort)
    try:
        from .models import db as _db, GroupForumTopic
        from datetime import datetime as _dt
        tg_id = str(tg_group.telegram_group_id)
        existing = GroupForumTopic.query.filter_by(
            telegram_group_id=tg_id, thread_id=int(thread_id)
        ).first()
        if existing:
            existing.last_seen_at = _dt.utcnow()
            if topic_name and existing.name != topic_name:
                existing.name = topic_name
        else:
            _db.session.add(GroupForumTopic(
                telegram_group_id=tg_id,
                thread_id=int(thread_id),
                name=name,
            ))
    except Exception:
        pass

    return settings_mutated


async def _resolve_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Return (user_id, username, display_name) for the moderation target.
    Priority: replied-to message > first @mention arg.
    Returns (None, None, None) if no target found.
    """
    msg = update.message
    if msg and msg.reply_to_message and msg.reply_to_message.from_user:
        u = msg.reply_to_message.from_user
        return u.id, u.username or "", u.first_name or str(u.id)

    for entity in (msg.entities or []):
        if str(entity.type) in ("MessageEntityType.MENTION", "mention"):
            text = msg.text or ""
            mention = text[entity.offset: entity.offset + entity.length].lstrip("@")
            try:
                chat = await context.bot.get_chat(f"@{mention}")
                return chat.id, mention, chat.first_name or mention
            except Exception:
                pass
        elif str(entity.type) in ("MessageEntityType.TEXT_MENTION", "text_mention"):
            u = entity.user
            if u:
                return u.id, u.username or "", u.first_name or str(u.id)

    return None, None, None


async def _require_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Return True if the command sender is a group admin or creator.

    Uses a 5-minute DB cache on OfficialMember.is_admin to avoid a Telegram
    API call on every moderation command.
    """
    flask_app = context.bot_data.get("flask_app")
    chat_id = str(update.effective_chat.id)
    user_id = str(update.effective_user.id)
    _CACHE_TTL = 300  # seconds

    if flask_app:
        try:
            with flask_app.app_context():
                from .models import OfficialMember
                member = OfficialMember.query.filter_by(
                    telegram_group_id=chat_id,
                    telegram_user_id=user_id,
                ).first()
                if member and member.is_admin_cached_at:
                    age = (datetime.utcnow() - member.is_admin_cached_at).total_seconds()
                    if age < _CACHE_TTL:
                        return member.is_admin
        except Exception:
            pass

    # Cache miss or stale — fetch from Telegram API
    try:
        me = await context.bot.get_chat_member(
            update.effective_chat.id, update.effective_user.id
        )
        is_admin = me.status in ("creator", "administrator")
    except Exception:
        return False

    # Update DB cache asynchronously (best-effort)
    if flask_app:
        try:
            with flask_app.app_context():
                from .models import db, OfficialMember
                member = OfficialMember.query.filter_by(
                    telegram_group_id=chat_id,
                    telegram_user_id=user_id,
                ).first()
                if member:
                    member.is_admin = is_admin
                    member.is_admin_cached_at = datetime.utcnow()
                    db.session.commit()
        except Exception:
            pass

    return is_admin


def _parse_duration(args: list, default_minutes: int = 60) -> int:
    """Parse an optional duration like '30m', '2h', '1d' from command args. Returns minutes."""
    for arg in args:
        arg = arg.lower()
        try:
            if arg.endswith("d"):
                return int(arg[:-1]) * 1440
            elif arg.endswith("h"):
                return int(arg[:-1]) * 60
            elif arg.endswith("m"):
                return int(arg[:-1])
            elif arg.isdigit():
                return int(arg)
        except ValueError:
            pass
    return default_minutes


def _parse_reason(args: list) -> str:
    reason_parts = [a for a in args if not any(a.lower().endswith(s) for s in ("m", "h", "d")) and not a.isdigit() and not a.startswith("@")]
    return " ".join(reason_parts) if reason_parts else "No reason given"


async def cmd_warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_group_chat(update):
        return
    if not await _require_admin(update, context):
        await update.message.reply_text("⛔ Admins only.")
        return

    flask_app = context.bot_data.get("flask_app")
    group_id = str(update.effective_chat.id)
    target_id, target_username, target_name = await _resolve_target(update, context)
    if not target_id:
        await update.message.reply_text("❌ Reply to a user or mention them to warn.")
        return

    args = context.args or []
    reason = _parse_reason(args)

    warn_count = 1
    if flask_app:
        try:
            with flask_app.app_context():
                from .models import db, OfficialMember, OfficialWarning
                replied_text = None
                if update.message and update.message.reply_to_message:
                    rt = update.message.reply_to_message
                    replied_text = (rt.text or rt.caption or "")[:500] or None
                w = OfficialWarning(
                    telegram_group_id=group_id,
                    target_user_id=str(target_id),
                    target_username=target_username or "",
                    moderator_user_id=str(update.effective_user.id),
                    moderator_username=update.effective_user.username or "",
                    reason=reason,
                    message_text=replied_text,
                )
                db.session.add(w)
                db.session.commit()
                warn_count = OfficialWarning.query.filter_by(
                    telegram_group_id=group_id,
                    target_user_id=str(target_id),
                    active=True,
                ).count()
                m = OfficialMember.query.filter_by(
                    telegram_group_id=group_id,
                    telegram_user_id=str(target_id),
                ).first()
                if m:
                    m.warnings = warn_count
                    db.session.commit()
        except Exception as _e:
            _log.warning("[OfficialBot] Failed to save warning: %s", _e)

    _log_event(flask_app, group_id, "mod_warn",
               f"{target_name} warned by {update.effective_user.first_name}: {reason}",
               {"target_user_id": str(target_id),
                "moderator_id": str(update.effective_user.id), "reason": reason})

    warn_msg = await update.message.reply_text(
        f"⚠️ {target_name} has been warned.\n"
        f"Reason: {reason}\n"
        f"Warning #{warn_count}"
    )
    asyncio.get_running_loop().call_later(
        30, lambda: asyncio.ensure_future(_safe_delete(context.bot, update.effective_chat.id, warn_msg.message_id))
    )
    if flask_app:
        await _apply_xp_penalty(flask_app, group_id, target_id, "warn")
        await _check_warn_escalation(
            context.bot, update.effective_chat.id, group_id,
            target_id, target_name, warn_count, flask_app,
        )


async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_group_chat(update):
        return
    if not await _require_admin(update, context):
        await update.message.reply_text("⛔ Admins only.")
        return

    flask_app = context.bot_data.get("flask_app")
    group_id = str(update.effective_chat.id)
    chat_id = update.effective_chat.id
    target_id, target_username, target_name = await _resolve_target(update, context)
    if not target_id:
        await update.message.reply_text("❌ Reply to a user or mention them to ban.")
        return

    args = context.args or []
    reason = _parse_reason(args)

    try:
        await context.bot.ban_chat_member(chat_id=chat_id, user_id=target_id)
        _log_event(flask_app, group_id, "mod_ban",
                   f"{target_name} banned by {update.effective_user.first_name}: {reason}",
                   {"target_user_id": str(target_id), "moderator_id": str(update.effective_user.id), "reason": reason})
        ban_msg = await update.message.reply_text(f"🚫 {target_name} has been banned.\nReason: {reason}")
        asyncio.get_running_loop().call_later(
            15, lambda: asyncio.ensure_future(_safe_delete(context.bot, chat_id, ban_msg.message_id))
        )
        if flask_app:
            await _apply_xp_penalty(flask_app, group_id, target_id, "ban")
    except Exception as exc:
        await update.message.reply_text(f"❌ Failed to ban: {exc}")


async def cmd_kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_group_chat(update):
        return
    if not await _require_admin(update, context):
        await update.message.reply_text("⛔ Admins only.")
        return

    flask_app = context.bot_data.get("flask_app")
    group_id = str(update.effective_chat.id)
    chat_id = update.effective_chat.id
    target_id, target_username, target_name = await _resolve_target(update, context)
    if not target_id:
        await update.message.reply_text("❌ Reply to a user or mention them to kick.")
        return

    args = context.args or []
    reason = _parse_reason(args)

    try:
        await context.bot.ban_chat_member(chat_id=chat_id, user_id=target_id)
        await context.bot.unban_chat_member(chat_id=chat_id, user_id=target_id)
        _log_event(flask_app, group_id, "mod_kick",
                   f"{target_name} kicked by {update.effective_user.first_name}: {reason}",
                   {"target_user_id": str(target_id), "moderator_id": str(update.effective_user.id), "reason": reason})
        kick_msg = await update.message.reply_text(f"👢 {target_name} has been kicked.\nReason: {reason}")
        asyncio.get_running_loop().call_later(
            15, lambda: asyncio.ensure_future(_safe_delete(context.bot, chat_id, kick_msg.message_id))
        )
        if flask_app:
            await _apply_xp_penalty(flask_app, group_id, target_id, "kick")
    except Exception as exc:
        await update.message.reply_text(f"❌ Failed to kick: {exc}")


async def cmd_mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_group_chat(update):
        return
    if not await _require_admin(update, context):
        await update.message.reply_text("⛔ Admins only.")
        return

    flask_app = context.bot_data.get("flask_app")
    group_id = str(update.effective_chat.id)
    chat_id = update.effective_chat.id
    target_id, target_username, target_name = await _resolve_target(update, context)
    if not target_id:
        await update.message.reply_text("❌ Reply to a user or mention them to mute.")
        return

    args = context.args or []
    duration_min = _parse_duration(args, default_minutes=60)
    reason = _parse_reason(args)
    until = datetime.utcnow() + timedelta(minutes=duration_min)

    try:
        await context.bot.restrict_chat_member(
            chat_id=chat_id, user_id=target_id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until,
        )
        _log_event(flask_app, group_id, "mod_mute",
                   f"{target_name} muted {duration_min}min by {update.effective_user.first_name}: {reason}",
                   {"target_user_id": str(target_id), "moderator_id": str(update.effective_user.id),
                    "duration_minutes": duration_min, "reason": reason})
        if flask_app:
            try:
                with flask_app.app_context():
                    from .models import db, OfficialMember
                    m = OfficialMember.query.filter_by(
                        telegram_group_id=group_id,
                        telegram_user_id=str(target_id),
                    ).first()
                    if m:
                        m.is_muted = True
                        m.mute_until = until
                        db.session.commit()
            except Exception as _e:
                _log.debug("[OfficialBot] Failed to set mute on member: %s", _e)
        mute_msg = await update.message.reply_text(
            f"🔇 {target_name} muted for {duration_min} min.\nReason: {reason}"
        )
        asyncio.get_running_loop().call_later(
            15, lambda: asyncio.ensure_future(_safe_delete(context.bot, chat_id, mute_msg.message_id))
        )
        if flask_app:
            await _apply_xp_penalty(flask_app, group_id, target_id, "mute")
    except Exception as exc:
        await update.message.reply_text(f"❌ Failed to mute: {exc}")


async def cmd_unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_group_chat(update):
        return
    if not await _require_admin(update, context):
        await update.message.reply_text("⛔ Admins only.")
        return

    flask_app = context.bot_data.get("flask_app")
    group_id = str(update.effective_chat.id)
    chat_id = update.effective_chat.id
    target_id, target_username, target_name = await _resolve_target(update, context)
    if not target_id:
        await update.message.reply_text("❌ Reply to a user or mention them to unmute.")
        return

    try:
        await context.bot.restrict_chat_member(
            chat_id=chat_id, user_id=target_id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
            ),
        )
        _log_event(flask_app, group_id, "mod_unmute",
                   f"{target_name} unmuted by {update.effective_user.first_name}",
                   {"target_user_id": str(target_id), "moderator_id": str(update.effective_user.id)})
        if flask_app:
            try:
                with flask_app.app_context():
                    from .models import db, OfficialMember
                    m = OfficialMember.query.filter_by(
                        telegram_group_id=group_id,
                        telegram_user_id=str(target_id),
                    ).first()
                    if m:
                        m.is_muted = False
                        m.mute_until = None
                        db.session.commit()
            except Exception as _e:
                _log.debug("[OfficialBot] Failed to clear mute on member: %s", _e)
        await update.message.reply_text(f"🔊 {target_name} has been unmuted.")
    except Exception as exc:
        await update.message.reply_text(f"❌ Failed to unmute: {exc}")


async def cmd_tempban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_group_chat(update):
        return
    if not await _require_admin(update, context):
        await update.message.reply_text("⛔ Admins only.")
        return

    flask_app = context.bot_data.get("flask_app")
    group_id = str(update.effective_chat.id)
    chat_id = update.effective_chat.id
    target_id, target_username, target_name = await _resolve_target(update, context)
    if not target_id:
        await update.message.reply_text("❌ Reply to a user or mention them to temp-ban.")
        return

    args = context.args or []
    duration_min = _parse_duration(args, default_minutes=1440)
    reason = _parse_reason(args)
    until = datetime.utcnow() + timedelta(minutes=duration_min)

    try:
        await context.bot.ban_chat_member(chat_id=chat_id, user_id=target_id, until_date=until)
        hours = duration_min // 60
        label = f"{hours}h" if hours else f"{duration_min}m"
        _log_event(flask_app, group_id, "mod_tempban",
                   f"{target_name} temp-banned {label} by {update.effective_user.first_name}: {reason}",
                   {"target_user_id": str(target_id), "moderator_id": str(update.effective_user.id),
                    "duration_minutes": duration_min, "reason": reason})
        tb_msg = await update.message.reply_text(
            f"⛔ {target_name} temp-banned for {label}.\nReason: {reason}"
        )
        asyncio.get_running_loop().call_later(
            15, lambda: asyncio.ensure_future(_safe_delete(context.bot, chat_id, tb_msg.message_id))
        )
    except Exception as exc:
        await update.message.reply_text(f"❌ Failed to temp-ban: {exc}")


async def cmd_purge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete the last N messages in the group (max 100). Usage: /purge [N]"""
    if not _is_group_chat(update):
        return
    if not await _require_admin(update, context):
        await update.message.reply_text("⛔ Admins only.")
        return

    flask_app = context.bot_data.get("flask_app")
    group_id = str(update.effective_chat.id)
    chat_id = update.effective_chat.id
    args = context.args or []
    try:
        n = min(int(args[0]), 100) if args else 10
    except ValueError:
        n = 10

    # Delete the /purge command message itself
    trigger_msg_id = update.message.message_id
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=trigger_msg_id)
    except Exception:
        pass

    # Delete the N messages before the purge command
    deleted = 0
    for mid in range(trigger_msg_id - 1, max(trigger_msg_id - n - 1, 0), -1):
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=mid)
            deleted += 1
        except Exception:
            pass

    _log_event(flask_app, group_id, "mod_purge",
               f"{deleted} messages purged by {update.effective_user.first_name}",
               {"moderator_id": str(update.effective_user.id), "count": deleted})

    try:
        notif = await context.bot.send_message(chat_id=chat_id, text=f"🗑️ Purged {deleted} messages.")
        asyncio.get_running_loop().call_later(
            5, lambda: asyncio.ensure_future(_safe_delete(context.bot, chat_id, notif.message_id))
        )
    except Exception:
        pass


async def _award_xp(flask_app, group_id: str, user, xp_gain: int = None):
    """Award XP to a user and update their level. Silently fails."""
    try:
        with flask_app.app_context():
            from .models import db, OfficialMember, TelegramGroup
            tg = TelegramGroup.query.filter_by(
                telegram_group_id=group_id, is_disabled=False
            ).first()
            if not tg:
                return
            lvl_settings = (tg.settings or {}).get("levels", {})
            if not lvl_settings.get("enabled", False):
                return

            # Use per-group xp_per_message setting; fall back to 10.
            if xp_gain is None:
                xp_gain = int(lvl_settings.get("xp_per_message", 10))

            m = OfficialMember.query.filter_by(
                telegram_group_id=group_id,
                telegram_user_id=str(user.id),
            ).first()
            if not m:
                m = OfficialMember(
                    telegram_group_id=group_id,
                    telegram_user_id=str(user.id),
                    username=user.username,
                    first_name=user.first_name,
                )
                db.session.add(m)

            now = datetime.utcnow()
            cooldown = int(lvl_settings.get("xp_cooldown_seconds", 60))
            if m.last_xp_at and (now - m.last_xp_at).total_seconds() < cooldown:
                # Still in cooldown — count message but skip XP
                m.message_count = (m.message_count or 0) + 1
                m.last_message_at = now
                db.session.commit()
                return

            old_level = m.level
            m.xp = (m.xp or 0) + xp_gain
            m.xp_1d  = (m.xp_1d  or 0) + xp_gain
            m.xp_7d  = (m.xp_7d  or 0) + xp_gain
            m.xp_30d = (m.xp_30d or 0) + xp_gain
            m.message_count = (m.message_count or 0) + 1
            m.last_message_at = now
            m.last_xp_at = now
            m.level = _level_from_xp(m.xp)
            db.session.commit()

            # Level-up notification
            if m.level > old_level:
                try:
                    from telegram import Bot as _Bot
                    pass  # bot is not available here; notification handled in on_message
                except Exception:
                    pass
    except Exception as exc:
        _log.debug("[OfficialBot] XP award failed: %s", exc)


async def cmd_xp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show XP and level for self or a mentioned user."""
    if not _is_group_chat(update):
        return

    flask_app = context.bot_data.get("flask_app")
    group_id = str(update.effective_chat.id)
    thread_id = getattr(update.message, "message_thread_id", None)

    tg_group = None
    if flask_app:
        try:
            with flask_app.app_context():
                from .models import TelegramGroup
                tg_group = TelegramGroup.query.filter_by(telegram_group_id=group_id).first()
        except Exception:
            pass
    if not _routing_allowed(tg_group, "/xp", thread_id):
        await _routing_reject(update, tg_group, "/xp")
        return

    target_id, _, target_name = await _resolve_target(update, context)
    if not target_id:
        target_id = update.effective_user.id
        target_name = update.effective_user.first_name or "You"

    xp = 0
    level = 1
    rank = None
    if flask_app:
        try:
            with flask_app.app_context():
                from .models import OfficialMember
                m = OfficialMember.query.filter_by(
                    telegram_group_id=group_id,
                    telegram_user_id=str(target_id),
                ).first()
                if m:
                    xp = m.xp
                    level = m.level
                    # Rank = position by XP desc
                    rank = OfficialMember.query.filter_by(
                        telegram_group_id=group_id,
                    ).filter(OfficialMember.xp > xp).count() + 1
        except Exception:
            pass

    next_level_xp = _xp_for_level(level + 1)
    bar_filled = min(int((xp % 100) / 10), 10)
    bar = "█" * bar_filled + "░" * (10 - bar_filled)

    text = (
        f"⭐ *{target_name}*\n"
        f"Level: {level}  |  XP: {xp}\n"
        f"[{bar}]\n"
        f"Next level: {next_level_xp} XP"
    )
    if rank:
        text += f"\nRank: #{rank} in this group"

    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def cmd_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show top 10 members by XP in the group."""
    if not _is_group_chat(update):
        return

    flask_app = context.bot_data.get("flask_app")
    group_id = str(update.effective_chat.id)
    thread_id = getattr(update.message, "message_thread_id", None)

    tg_group = None
    if flask_app:
        try:
            with flask_app.app_context():
                from .models import TelegramGroup
                tg_group = TelegramGroup.query.filter_by(telegram_group_id=group_id).first()
        except Exception:
            pass
    if not _routing_allowed(tg_group, "/leaderboard", thread_id):
        await _routing_reject(update, tg_group, "/leaderboard")
        return

    leaders = []
    if flask_app:
        try:
            with flask_app.app_context():
                from .models import OfficialMember
                leaders = OfficialMember.query.filter_by(
                    telegram_group_id=group_id,
                ).order_by(OfficialMember.xp.desc()).limit(10).all()
        except Exception:
            pass

    if not leaders:
        await update.message.reply_text("📊 No XP data yet — levels must be enabled in group settings.")
        return

    medals = ["🥇", "🥈", "🥉"] + ["🏅"] * 7
    lines = ["*📊 Group Leaderboard*\n"]
    for i, m in enumerate(leaders):
        name = m.first_name or m.username or f"User {m.telegram_user_id}"
        lines.append(f"{medals[i]} {name} — Lv.{m.level} ({m.xp} XP)")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def cmd_warnings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show warning count for a user."""
    if not _is_group_chat(update):
        return
    flask_app = context.bot_data.get("flask_app")
    group_id = str(update.effective_chat.id)
    target_id, _, target_name = await _resolve_target(update, context)
    if not target_id:
        await update.message.reply_text("❌ Reply to a user or mention them.")
        return

    count = 0
    if flask_app:
        try:
            with flask_app.app_context():
                from .models import OfficialWarning
                count = OfficialWarning.query.filter_by(
                    telegram_group_id=group_id,
                    target_user_id=str(target_id),
                    active=True,
                ).count()
        except Exception:
            pass

    await update.message.reply_text(f"⚠️ {target_name} has {count} active warning(s) in this group.")


# ─── Additional commands (Phase 2) ───────────────────────────────────────────

async def cmd_tempmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mute a user for a specified duration. Usage: /tempmute [@user] [30m|2h] [reason]"""
    if not _is_group_chat(update):
        return
    if not await _require_admin(update, context):
        await update.message.reply_text("⛔ Admins only.")
        return
    flask_app = context.bot_data.get("flask_app")
    group_id = str(update.effective_chat.id)
    chat_id = update.effective_chat.id
    target_id, target_username, target_name = await _resolve_target(update, context)
    if not target_id:
        await update.message.reply_text("❌ Reply to or mention a user.")
        return
    args = context.args or []
    duration_min = _parse_duration(args, default_minutes=30)
    reason = _parse_reason(args)
    until = datetime.utcnow() + timedelta(minutes=duration_min)
    try:
        await context.bot.restrict_chat_member(
            chat_id=chat_id, user_id=target_id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until,
        )
        _log_event(flask_app, group_id, "mod_tempmute",
                   f"{target_name} temp-muted {duration_min}min: {reason}",
                   {"target_user_id": str(target_id), "duration_minutes": duration_min})
        msg = await update.message.reply_text(
            f"🔇 {target_name} muted for {duration_min} min.\nReason: {reason}"
        )
        asyncio.get_running_loop().call_later(
            15, lambda: asyncio.ensure_future(_safe_delete(context.bot, chat_id, msg.message_id))
        )
        if flask_app:
            await _apply_xp_penalty(flask_app, group_id, target_id, "mute")
    except Exception as exc:
        await update.message.reply_text(f"❌ Failed to mute: {exc}")


async def cmd_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all current group admins."""
    if not _is_group_chat(update):
        return
    try:
        admins = await context.bot.get_chat_administrators(update.effective_chat.id)
        lines = ["👮 *Group Admins*\n"]
        for a in admins:
            name = a.user.first_name or a.user.username or str(a.user.id)
            title_str = f" ({a.custom_title})" if getattr(a, "custom_title", None) else ""
            lines.append(f"• {name}{title_str}")
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
    except Exception as exc:
        await update.message.reply_text(f"❌ Could not fetch admins: {exc}")


async def cmd_roles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show configured level-based roles for this group."""
    if not _is_group_chat(update):
        return
    flask_app = context.bot_data.get("flask_app")
    group_id = str(update.effective_chat.id)
    roles = []
    if flask_app:
        try:
            with flask_app.app_context():
                from .models import TelegramGroup
                tg = TelegramGroup.query.filter_by(telegram_group_id=group_id).first()
                if tg:
                    roles = (tg.settings or {}).get("levels", {}).get("roles", [])
        except Exception:
            pass
    if not roles:
        await update.message.reply_text("No level roles configured for this group.")
        return
    lines = ["🎖 *Level Roles*\n"]
    for r in sorted(roles, key=lambda x: x.get("level", 0)):
        lines.append(f"Level {r['level']}+ → {r['name']}")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def _show_rank(update: Update, context: ContextTypes.DEFAULT_TYPE, target_id=None):
    """Shared logic for /rank and /me."""
    flask_app = context.bot_data.get("flask_app")
    group_id = str(update.effective_chat.id)
    target_name = update.effective_user.first_name or "You"
    if target_id is None:
        tgt_id, _, tgt_name = await _resolve_target(update, context)
        if not tgt_id:
            tgt_id = update.effective_user.id
            tgt_name = target_name
        target_id, target_name = tgt_id, tgt_name
    xp, level, rank = 0, 1, None
    role_name = ""
    if flask_app:
        try:
            with flask_app.app_context():
                from .models import OfficialMember, TelegramGroup
                m = OfficialMember.query.filter_by(
                    telegram_group_id=group_id,
                    telegram_user_id=str(target_id),
                ).first()
                if m:
                    xp, level = m.xp, m.level
                    role_name = getattr(m, "role", "") or ""
                    rank = OfficialMember.query.filter_by(
                        telegram_group_id=group_id,
                    ).filter(OfficialMember.xp > xp).count() + 1
                tg = TelegramGroup.query.filter_by(telegram_group_id=group_id).first()
                if tg:
                    for r in sorted(
                        (tg.settings or {}).get("levels", {}).get("roles", []),
                        key=lambda x: x.get("level", 0),
                        reverse=True,
                    ):
                        if level >= r.get("level", 0):
                            role_name = r.get("name", role_name)
                            break
        except Exception:
            pass
    bar_filled = min(int((xp % 100) / 10), 10)
    bar = "█" * bar_filled + "░" * (10 - bar_filled)
    next_xp = max(xp + 1, ((xp // 100) + 1) * 100)
    text = (
        f"🏅 *{target_name}*\n"
        f"Level: {level}{' — ' + role_name if role_name else ''}\n"
        f"XP: {xp:,}  [{bar}]\n"
        f"Next level: {next_xp:,} XP"
    )
    if rank:
        text += f"\nRank: #{rank} in this group"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def cmd_rank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show rank and level for self or a mentioned user."""
    if not _is_group_chat(update):
        return

    flask_app = context.bot_data.get("flask_app")
    group_id = str(update.effective_chat.id)
    thread_id = getattr(update.message, "message_thread_id", None)
    tg_group = None
    if flask_app:
        try:
            with flask_app.app_context():
                from .models import TelegramGroup
                tg_group = TelegramGroup.query.filter_by(telegram_group_id=group_id).first()
        except Exception:
            pass
    if not _routing_allowed(tg_group, "/rank", thread_id):
        await _routing_reject(update, tg_group, "/rank")
        return

    await _show_rank(update, context)


async def cmd_me(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show your own rank and level."""
    if not _is_group_chat(update):
        return
    await _show_rank(update, context, target_id=update.effective_user.id)


async def cmd_whois(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show detailed info about a user (admins only)."""
    if not _is_group_chat(update):
        return
    if not await _require_admin(update, context):
        await update.message.reply_text("⛔ Admins only.")
        return
    flask_app = context.bot_data.get("flask_app")
    group_id = str(update.effective_chat.id)
    target_id, _, target_name = await _resolve_target(update, context)
    if not target_id:
        await update.message.reply_text("❌ Reply to a user or mention them.")
        return
    xp, level, warnings_count, first_name = 0, 1, 0, target_name
    role, is_muted, mute_until, is_verified, wallet = "member", False, None, False, None
    if flask_app:
        try:
            with flask_app.app_context():
                from .models import OfficialMember, OfficialWarning
                m = OfficialMember.query.filter_by(
                    telegram_group_id=group_id,
                    telegram_user_id=str(target_id),
                ).first()
                if m:
                    xp, level = m.xp, m.level
                    first_name = m.first_name or target_name
                    role = getattr(m, "role", "member") or "member"
                    is_muted = getattr(m, "is_muted", False)
                    mute_until = getattr(m, "mute_until", None)
                    is_verified = getattr(m, "is_verified", False)
                    wallet = getattr(m, "wallet_address", None)
                warnings_count = OfficialWarning.query.filter_by(
                    telegram_group_id=group_id,
                    target_user_id=str(target_id),
                    active=True,
                ).count()
        except Exception:
            pass
    mute_str = ""
    if is_muted:
        mute_str = f"\nMuted: ✅" + (f" until {mute_until.strftime('%Y-%m-%d %H:%M')} UTC" if mute_until else "")
    wallet_str = f"\nWallet: `{wallet}`" if wallet else ""
    await update.message.reply_text(
        f"🔍 *{first_name}*\n"
        f"ID: `{target_id}`\n"
        f"Role: {role} | Level: {level} | XP: {xp:,}\n"
        f"Active warnings: {warnings_count}\n"
        f"Verified: {'✅' if is_verified else '❌'}"
        f"{mute_str}{wallet_str}",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set or view your wallet address. Usage: /wallet <address>"""
    flask_app = context.bot_data.get("flask_app")
    user = update.effective_user
    args = context.args or []

    if not flask_app:
        await update.message.reply_text("❌ Service unavailable.")
        return

    if args:
        # Set wallet
        address = args[0].strip()
        if len(address) > 500:
            await update.message.reply_text("❌ Address too long (max 500 chars).")
            return
        group_id = str(update.effective_chat.id) if _is_group_chat(update) else None
        try:
            with flask_app.app_context():
                from .models import db, OfficialMember
                if group_id:
                    m = OfficialMember.query.filter_by(
                        telegram_group_id=group_id,
                        telegram_user_id=str(user.id),
                    ).first()
                else:
                    m = OfficialMember.query.filter_by(
                        telegram_user_id=str(user.id),
                    ).first()
                if m:
                    m.wallet_address = address
                    m.wallet_submitted_at = datetime.utcnow()
                    db.session.commit()
                    await update.message.reply_text("✅ Wallet address saved.")
                else:
                    await update.message.reply_text("❌ No membership record found. Send a message in the group first.")
        except Exception as _e:
            _log.error("[OfficialBot] wallet save error: %s", _e)
            await update.message.reply_text("❌ Failed to save wallet.")
    else:
        # View wallet
        group_id = str(update.effective_chat.id) if _is_group_chat(update) else None
        wallet = None
        try:
            with flask_app.app_context():
                from .models import OfficialMember
                if group_id:
                    m = OfficialMember.query.filter_by(
                        telegram_group_id=group_id,
                        telegram_user_id=str(user.id),
                    ).first()
                else:
                    m = OfficialMember.query.filter_by(
                        telegram_user_id=str(user.id),
                    ).first()
                if m:
                    wallet = getattr(m, "wallet_address", None)
        except Exception:
            pass
        if wallet:
            await update.message.reply_text(
                f"💳 Your wallet address:\n`{wallet}`",
                parse_mode=ParseMode.MARKDOWN,
            )
        else:
            await update.message.reply_text("No wallet address set. Use /wallet <address> to set one.")


async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Report a user to group admins."""
    if not _is_group_chat(update):
        return
    flask_app = context.bot_data.get("flask_app")
    group_id = str(update.effective_chat.id)
    chat_id = update.effective_chat.id
    reporter = update.effective_user
    target_id, _, target_name = await _resolve_target(update, context)
    if not target_id:
        await update.message.reply_text("❌ Reply to a message to report the user.")
        return
    reason = " ".join(context.args) if context.args else "No reason given"
    report_text = (
        f"🚨 *User Reported*\n"
        f"Reported: {target_name} (`{target_id}`)\n"
        f"By: {reporter.first_name} (`{reporter.id}`)\n"
        f"Reason: {reason}"
    )
    try:
        notif = await update.message.reply_text(report_text, parse_mode=ParseMode.MARKDOWN)
        asyncio.get_running_loop().call_later(
            60, lambda: asyncio.ensure_future(_safe_delete(context.bot, chat_id, notif.message_id))
        )
    except Exception as exc:
        _log.debug("[OfficialBot] Report send failed: %s", exc)
    _log_event(flask_app, group_id, "user_reported",
               f"{target_name} reported by {reporter.first_name}: {reason}",
               {"target_user_id": str(target_id), "reporter_id": str(reporter.id)})
    if flask_app:
        try:
            with flask_app.app_context():
                from .models import db, OfficialReportedMessage
                rpt = OfficialReportedMessage(
                    telegram_group_id=group_id,
                    reporter_user_id=str(reporter.id),
                    reporter_username=reporter.username,
                    reported_user_id=str(target_id) if target_id else None,
                    reported_username=target_name,
                    reason=reason,
                    status="open",
                )
                db.session.add(rpt)
                db.session.commit()
        except Exception as exc:
            _log.debug("[OfficialBot] OfficialReportedMessage save failed: %s", exc)


async def cmd_removewarning(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove the most recent warning from a user."""
    if not _is_group_chat(update):
        return
    if not await _require_admin(update, context):
        await update.message.reply_text("⛔ Admins only.")
        return
    flask_app = context.bot_data.get("flask_app")
    group_id = str(update.effective_chat.id)
    target_id, _, target_name = await _resolve_target(update, context)
    if not target_id:
        await update.message.reply_text("❌ Reply to a user or mention them.")
        return
    removed = False
    if flask_app:
        try:
            with flask_app.app_context():
                from .models import db, OfficialWarning
                last_warn = (
                    OfficialWarning.query
                    .filter_by(telegram_group_id=group_id,
                               target_user_id=str(target_id), active=True)
                    .order_by(OfficialWarning.created_at.desc())
                    .first()
                )
                if last_warn:
                    last_warn.active = False
                    db.session.commit()
                    removed = True
                    # Sync warnings counter on OfficialMember
                    from .models import OfficialMember
                    m = OfficialMember.query.filter_by(
                        telegram_group_id=group_id,
                        telegram_user_id=str(target_id),
                    ).first()
                    if m:
                        remaining = OfficialWarning.query.filter_by(
                            telegram_group_id=group_id,
                            target_user_id=str(target_id),
                            active=True,
                        ).count()
                        m.warnings = remaining
                        db.session.commit()
        except Exception as _e:
            _log.warning("[OfficialBot] removewarning error: %s", _e)
    if removed:
        await update.message.reply_text(f"✅ Removed last warning from {target_name}.")
    else:
        await update.message.reply_text(f"ℹ️ {target_name} has no active warnings.")


async def cmd_groupinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show group statistics."""
    if not _is_group_chat(update):
        return
    flask_app = context.bot_data.get("flask_app")
    group_id = str(update.effective_chat.id)
    chat = update.effective_chat
    member_count, total_xp, warning_count = 0, 0, 0
    if flask_app:
        try:
            with flask_app.app_context():
                from .models import OfficialMember, OfficialWarning, db
                from sqlalchemy import func
                member_count = OfficialMember.query.filter_by(telegram_group_id=group_id).count()
                total_xp = (
                    db.session.query(func.sum(OfficialMember.xp))
                    .filter(OfficialMember.telegram_group_id == group_id)
                    .scalar() or 0
                )
                warning_count = OfficialWarning.query.filter_by(
                    telegram_group_id=group_id, active=True
                ).count()
        except Exception:
            pass
    try:
        tg_count = await context.bot.get_chat_member_count(chat.id)
    except Exception:
        tg_count = member_count
    await update.message.reply_text(
        f"ℹ️ *{chat.title}*\n"
        f"Members: {tg_count:,}\n"
        f"Tracked XP members: {member_count:,}\n"
        f"Total XP awarded: {total_xp:,}\n"
        f"Active warnings: {warning_count}\n"
        f"Type: {chat.type}",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_auditlog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show recent moderation events (admins only)."""
    if not _is_group_chat(update):
        return
    if not await _require_admin(update, context):
        await update.message.reply_text("⛔ Admins only.")
        return
    flask_app = context.bot_data.get("flask_app")
    group_id = str(update.effective_chat.id)
    entries = []
    if flask_app:
        try:
            with flask_app.app_context():
                from .models import BotEvent
                rows = (
                    BotEvent.query
                    .filter(
                        BotEvent.telegram_group_id == group_id,
                        BotEvent.event_type.in_([
                            "mod_ban", "mod_kick", "mod_mute", "mod_tempmute",
                            "mod_warn", "mod_tempban", "automod_action",
                            "user_reported",
                        ]),
                    )
                    .order_by(BotEvent.created_at.desc())
                    .limit(10)
                    .all()
                )
                entries = [
                    {
                        "ts": r.created_at.strftime("%m/%d %H:%M"),
                        "type": r.event_type.replace("mod_", "").upper(),
                        "msg": (r.message or "")[:80],
                    }
                    for r in rows
                ]
        except Exception:
            pass
    if not entries:
        await update.message.reply_text("📋 No recent moderation events.")
        return
    lines = ["📋 *Recent Moderation Log*\n"]
    for e in entries:
        lines.append(f"[{e['ts']}] {e['type']}: {e['msg']}")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


# ─── /ask — Knowledge Base Q&A ────────────────────────────────────────────────

async def cmd_ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Answer a question from the group's knowledge base."""
    if not _is_group_chat(update):
        await update.message.reply_text("Use /ask in a group where the bot is active.")
        return
    flask_app = context.bot_data.get("flask_app")
    group_id = str(update.effective_chat.id)
    question = " ".join(context.args).strip() if context.args else ""
    if not question:
        await update.message.reply_text("Usage: /ask <your question>")
        return

    thinking_msg = await update.message.reply_text("🔍 Searching knowledge base…")
    try:
        from .bot_features.knowledge_base import KnowledgeBaseSystem
        kb = KnowledgeBaseSystem(flask_app)
        answer, confidence = await kb.answer_question(
            question=question,
            group_id=None,
            telegram_group_id=group_id,
        )
    except Exception as exc:
        _log.error("cmd_ask error: %s", exc)
        answer, confidence = None, 0.0

    try:
        await thinking_msg.delete()
    except Exception:
        pass

    CONFIDENCE_THRESHOLD = 0.35
    if not answer or confidence < CONFIDENCE_THRESHOLD:
        await update.message.reply_text(
            "❓ I couldn't find a confident answer in the knowledge base. "
            "Try rephrasing or ask an admin."
        )
        return

    await update.message.reply_text(
        f"💡 *Answer:*\n{answer}",
        parse_mode=ParseMode.MARKDOWN,
    )


# ─── /invitelink — Create a Telegram invite link ──────────────────────────────

async def cmd_remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /remind <time> <text>
    time: 30m | 2h | 1d | tomorrow
    Example: /remind 2h Follow up with Alice about the proposal
    """
    chat = update.effective_chat
    message = update.message
    flask_app = context.bot_data.get("flask_app")
    if not message or not flask_app:
        return

    user = message.from_user
    if not user:
        return

    args = (message.text or "").split(None, 2)  # ['/remind', <time>, <text>]
    if len(args) < 3:
        await message.reply_text(
            "Usage: `/remind <time> <text>`\n"
            "Time examples: `30m`, `2h`, `1d`, `tomorrow`\n"
            "Example: `/remind 2h Follow up with Alice`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    time_str = args[1].lower()
    reminder_text = args[2].strip()

    # Parse time offset
    delta = None
    if time_str == "tomorrow":
        delta = timedelta(hours=24)
    elif time_str.endswith("m"):
        try:
            delta = timedelta(minutes=int(time_str[:-1]))
        except ValueError:
            pass
    elif time_str.endswith("h"):
        try:
            delta = timedelta(hours=int(time_str[:-1]))
        except ValueError:
            pass
    elif time_str.endswith("d"):
        try:
            delta = timedelta(days=int(time_str[:-1]))
        except ValueError:
            pass

    if delta is None or delta.total_seconds() < 60:
        await message.reply_text("Invalid time. Use `30m`, `2h`, `1d`, or `tomorrow`.", parse_mode=ParseMode.MARKDOWN)
        return

    if delta.total_seconds() > 30 * 86400:
        await message.reply_text("Maximum reminder time is 30 days.")
        return

    remind_at = datetime.utcnow() + delta

    try:
        with flask_app.app_context():
            from .models import db, TelegramGroup, User as DBUser
            group_id = str(chat.id) if chat and chat.type != "private" else None

            # Find the group owner (must be linked)
            owner = None
            if group_id:
                tg = TelegramGroup.query.filter_by(telegram_group_id=group_id).first()
                if tg and tg.owner_user_id:
                    owner = DBUser.query.get(tg.owner_user_id)

            # Fallback: find user by telegram_user_id
            if not owner:
                owner = _user_by_tg_id(user.id)

            if not owner:
                await message.reply_text("⚠️ Reminders only work for linked accounts. Connect your Telegram at telegizer.com/settings")
                return

            from .models import WorkspaceReminder
            reminder = WorkspaceReminder(
                owner_user_id=owner.id,
                telegram_group_id=group_id,
                original_message=message.text,
                reminder_text=reminder_text[:500],
                remind_at=remind_at,
            )
            db.session.add(reminder)
            db.session.commit()

        time_label = (
            "tomorrow" if time_str == "tomorrow"
            else f"in {time_str}"
        )
        await message.reply_text(
            f"⏰ Got it! I'll remind you {time_label}:\n_{reminder_text}_",
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as exc:
        _log.warning("cmd_remind failed: %s", exc)
        await message.reply_text("Sorry, couldn't save the reminder. Try again.")


async def cmd_assist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /assist [template_name] — dispatch a Hub template into the current group.

    Looks up the template by name for the bot identity connected to this group.
    If found: sends template content and increments use_count.
    If not found: replies with a helpful error.
    If no name given: lists available template names.
    """
    # When Echo is configured it owns /assist — Telegizer silently steps back
    # to avoid double-responses in groups that have both bots.
    if Config.ECHO_BOT_TOKEN:
        return

    if not _is_group_chat(update):
        return

    message = update.message
    chat = update.effective_chat
    flask_app = context.bot_data.get("flask_app")
    if not flask_app or not message:
        return

    # Extract template name from command args
    args = (message.text or "").split(maxsplit=1)
    template_name = args[1].strip() if len(args) > 1 else ""

    group_id = str(chat.id)

    try:
        with flask_app.app_context():
            from .assistant.hub_models import HubConnectedGroup, HubTemplate
            from .models import db

            # Find the connected group record for this Telegram group
            connected = HubConnectedGroup.query.filter_by(
                telegram_group_id=chat.id,
                is_active=True,
            ).filter(
                HubConnectedGroup.consent_confirmed_at.isnot(None)
            ).first()

            if not connected:
                return  # group not in Hub — silently ignore

            if not template_name:
                # List available template names
                templates = HubTemplate.query.filter_by(
                    bot_id=connected.bot_id, user_id=connected.user_id
                ).order_by(HubTemplate.name.asc()).all()
                if not templates:
                    await message.reply_text(
                        "No templates yet. Create some at your Telegizer dashboard."
                    )
                else:
                    names = "\n".join(f"• /assist {t.name}" for t in templates)
                    await message.reply_text(f"Available templates:\n{names}")
                return

            # Look up the template by name (case-insensitive)
            template = HubTemplate.query.filter(
                HubTemplate.bot_id == connected.bot_id,
                HubTemplate.user_id == connected.user_id,
                db.func.lower(HubTemplate.name) == template_name.lower(),
            ).first()

            if not template:
                await message.reply_text(
                    f"Template '{template_name}' not found. Check your dashboard."
                )
                return

            # Send template content
            await message.reply_text(template.content)

            # Increment use_count
            template.use_count = (template.use_count or 0) + 1
            template.last_used_at = datetime.utcnow()
            db.session.commit()

    except Exception as exc:
        _log.debug("cmd_assist error group=%s: %s", group_id, exc)


async def cmd_invitelink(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate a Telegram invite link for this group (admins only)."""
    if not _is_group_chat(update):
        return
    if not await _require_admin(update, context):
        await update.message.reply_text("⛔ Admins only.")
        return

    flask_app = context.bot_data.get("flask_app")
    group_id = str(update.effective_chat.id)
    name = " ".join(context.args).strip()[:32] if context.args else "Bot invite"

    try:
        tg_link_obj = await context.bot.create_chat_invite_link(
            chat_id=update.effective_chat.id,
            name=name,
        )
        link_url = tg_link_obj.invite_link
    except Exception as exc:
        await update.message.reply_text(f"❌ Could not create invite link: {exc}")
        return

    # Persist to DB
    if flask_app:
        try:
            with flask_app.app_context():
                from .models import db, InviteLink
                lnk = InviteLink(
                    telegram_group_id=group_id,
                    name=name,
                    telegram_invite_link=link_url,
                )
                db.session.add(lnk)
                db.session.commit()
        except Exception as exc:
            _log.warning("invitelink db persist failed: %s", exc)

    await update.message.reply_text(
        f"🔗 *Invite Link Created*\n\nName: _{name}_\nLink: {link_url}",
        parse_mode=ParseMode.MARKDOWN,
    )


# ─── Service-message auto-clean ───────────────────────────────────────────────

async def on_service_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete Telegram service messages (joins, leaves, etc.) per auto_clean settings."""
    message = update.message
    if not message:
        return
    flask_app = context.bot_data.get("flask_app")
    if not flask_app:
        return
    chat = update.effective_chat
    if not chat or chat.type == ChatType.PRIVATE:
        return
    group_id = str(chat.id)

    auto_clean = {}
    tg_svc = None
    try:
        with flask_app.app_context():
            from .models import db, TelegramGroup
            from sqlalchemy.orm.attributes import flag_modified
            tg_svc = TelegramGroup.query.filter_by(
                telegram_group_id=group_id, is_disabled=False
            ).first()
            if tg_svc:
                auto_clean = (tg_svc.settings or {}).get("auto_clean", {})
                # Capture/update forum topics for dashboard topic selectors.
                if message.forum_topic_created and message.message_thread_id:
                    topic_name = getattr(message.forum_topic_created, "name", None)
                    if _capture_topic_official(tg_svc, message.message_thread_id, topic_name):
                        flag_modified(tg_svc, "settings")
                        db.session.commit()
                elif (message.forum_topic_closed or message.forum_topic_reopened) and message.message_thread_id:
                    is_closed = bool(message.forum_topic_closed)
                    from .models import GroupForumTopic
                    row = GroupForumTopic.query.filter_by(
                        telegram_group_id=group_id,
                        thread_id=int(message.message_thread_id),
                    ).first()
                    if row and row.is_closed != is_closed:
                        row.is_closed = is_closed
                        db.session.commit()
                elif message.forum_topic_edited and message.message_thread_id:
                    new_name = getattr(message.forum_topic_edited, "name", None)
                    if new_name and _capture_topic_official(tg_svc, message.message_thread_id, new_name):
                        flag_modified(tg_svc, "settings")
                        db.session.commit()
    except Exception:
        return

    if not auto_clean.get("enabled", False):
        return

    should_delete = False
    if auto_clean.get("delete_joins") and message.new_chat_members:
        should_delete = True
    elif auto_clean.get("delete_leaves") and message.left_chat_member:
        should_delete = True
    elif auto_clean.get("delete_photo_changes") and message.new_chat_photo:
        should_delete = True
    elif auto_clean.get("delete_pinned_messages") and message.pinned_message:
        should_delete = True
    elif auto_clean.get("delete_game_scores") and message.game_short_name:
        should_delete = True
    elif auto_clean.get("delete_voice_chat_events") and (
        message.video_chat_started or message.video_chat_ended
        or message.video_chat_scheduled or message.video_chat_participants_invited
    ):
        should_delete = True
    elif auto_clean.get("delete_forum_events") and (
        message.forum_topic_created or message.forum_topic_closed
        or message.forum_topic_reopened or message.forum_topic_edited
    ):
        should_delete = True

    if should_delete:
        try:
            await context.bot.delete_message(
                chat_id=chat.id, message_id=message.message_id
            )
        except Exception:
            pass


# ─── Reaction XP handler ─────────────────────────────────────────────────────

async def on_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Award XP when a member adds a reaction to a message."""
    reaction = update.message_reaction
    if not reaction or not reaction.new_reaction:
        return
    user = reaction.user
    if not user or user.is_bot:
        return
    flask_app = context.bot_data.get("flask_app")
    if not flask_app:
        return
    group_id = str(reaction.chat.id)
    try:
        with flask_app.app_context():
            from .models import TelegramGroup, OfficialMember, db
            tg = TelegramGroup.query.filter_by(
                telegram_group_id=group_id, is_disabled=False
            ).first()
            if not tg:
                return
            lvl = (tg.settings or {}).get("levels", {})
            if not lvl.get("enabled", False):
                return
            xp_amount = int(lvl.get("xp_per_reaction", 10))
            if xp_amount <= 0:
                return
            m = OfficialMember.query.filter_by(
                telegram_group_id=group_id,
                telegram_user_id=str(user.id),
            ).first()
            if not m:
                m = OfficialMember(
                    telegram_group_id=group_id,
                    telegram_user_id=str(user.id),
                    username=user.username,
                    first_name=user.first_name,
                )
                db.session.add(m)
            m.xp = (m.xp or 0) + xp_amount
            m.xp_1d  = (m.xp_1d  or 0) + xp_amount
            m.xp_7d  = (m.xp_7d  or 0) + xp_amount
            m.xp_30d = (m.xp_30d or 0) + xp_amount
            m.level = _level_from_xp(m.xp)
            db.session.commit()
    except Exception as exc:
        _log.debug("[OfficialBot] Reaction XP failed: %s", exc)


async def on_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Capture channel posts and view-count updates for analytics.

    Handles both channel_post (new post) and edited_channel_post (view/reaction updates).
    Telegram re-sends edited_channel_post as view counts grow — without this we would
    always store the initial view count (often 1).
    """
    # edited_channel_post carries updated view/reaction counts; treat identically
    msg = update.channel_post or update.edited_channel_post
    if not msg:
        return
    flask_app = context.bot_data.get("flask_app")
    if not flask_app:
        return
    channel_tg_id = str(msg.chat.id)
    is_edit = update.edited_channel_post is not None
    try:
        with flask_app.app_context():
            from .models import db, Channel, ChannelPost
            ch = Channel.query.filter_by(telegram_channel_id=channel_tg_id).first()
            if not ch:
                # Channel post arrived but this channel is not tracked — ignore silently
                return

            # Determine media type (only meaningful for new posts, but harmless to compute)
            has_media = False
            media_type = None
            if msg.photo:
                has_media, media_type = True, "photo"
            elif msg.video:
                has_media, media_type = True, "video"
            elif msg.document:
                has_media, media_type = True, "document"
            elif msg.poll:
                has_media, media_type = True, "poll"
            elif msg.sticker:
                has_media, media_type = True, "sticker"
            elif msg.animation:
                has_media, media_type = True, "gif"

            text = msg.text or msg.caption or ""
            preview = text[:297] + "…" if len(text) > 300 else text

            existing = ChannelPost.query.filter_by(
                channel_id=ch.id, message_id=msg.message_id
            ).first()
            if existing:
                # Always take the higher value — Telegram sends increasing counts
                existing.views = max(existing.views, msg.views or 0)
                existing.forwards = max(existing.forwards, msg.forward_count or 0)
                existing.last_updated = datetime.utcnow()
            else:
                post = ChannelPost(
                    channel_id=ch.id,
                    message_id=msg.message_id,
                    text_preview=preview or None,
                    views=msg.views or 0,
                    forwards=msg.forward_count or 0,
                    has_media=has_media,
                    media_type=media_type,
                    posted_at=msg.date or datetime.utcnow(),
                )
                db.session.add(post)

            ch.bot_status = "active"
            db.session.commit()
            _log.info(
                "[OfficialBot] channel_post %s: channel=%s msg_id=%d views=%d",
                "updated" if existing else "captured",
                channel_tg_id, msg.message_id, msg.views or 0,
            )
    except Exception as exc:
        _log.warning("[OfficialBot] channel_post capture failed: %s", exc)


# ─── OfficialBotRunner ────────────────────────────────────────────────────────

class OfficialBotRunner:
    def __init__(self):
        self.application = None
        self._app = None  # PTB Application — used by the webhook route
        self.loop = None
        self._thread = None
        self._running = False
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    def start(self, flask_app):
        token = Config.TELEGRAM_BOT_TOKEN
        if not token:
            _log.warning(
                "[OfficialBot] TELEGRAM_BOT_TOKEN not set — official bot disabled. "
                "Set TELEGRAM_BOT_TOKEN in Railway → Variables."
            )
            return
        with self._lock:
            if self._running:
                _log.info("[OfficialBot] Already running, skipping duplicate start.")
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run_loop, args=(flask_app,),
                daemon=True, name="telegizer-official-bot",
            )
            self._thread.start()
            self._running = True
            _log.info(
                "[OfficialBot] Thread started. token_prefix=%s… username=%s",
                token[:12], Config.TELEGRAM_BOT_USERNAME,
            )

    def _run_loop(self, flask_app):
        """Webhook bot loop with exponential-backoff auto-restart on crash."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        base_delay = 5
        max_delay = 300
        attempt = 0

        while not self._stop_event.is_set():
            try:
                _log.info("[OfficialBot] Starting webhook mode (attempt %d)…", attempt)
                self.loop.run_until_complete(self._poll(flask_app))
                _log.info("[OfficialBot] Bot finished cleanly — exiting restart loop.")
                break
            except Exception as exc:
                _log.error(
                    "[OfficialBot] Crash on attempt %d: %s",
                    attempt, exc, exc_info=True,
                )

            if self._stop_event.is_set():
                break

            delay = min(base_delay * (2 ** attempt), max_delay)
            _log.info("[OfficialBot] Restarting in %ds…", delay)
            if self._stop_event.wait(timeout=delay):
                break
            attempt += 1

        with self._lock:
            self._running = False
        _log.info("[OfficialBot] Thread exited")

    async def _poll(self, flask_app):
        _load_pending_verifications_from_db(flask_app)
        self.application = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()
        # Re-register timeout handlers for verifications restored from DB
        loop = asyncio.get_event_loop()
        for _vkey, _vpending in list(_pending_verifications.items()):
            _vc, _vu = _vkey.split(":", 1)
            _vremaining = max(1.0, (_vpending["expires_at"] - datetime.utcnow()).total_seconds())
            loop.call_later(
                _vremaining,
                lambda _c=int(_vc), _u=int(_vu): asyncio.ensure_future(
                    _verification_timeout(self.application.bot, _c, _u)
                ),
            )
        self.application.bot_data["flask_app"] = flask_app
        # Expose the PTB Application so the webhook route can forward updates
        self._app = self.application
        flask_app.official_bot_instance = self

        a = self.application
        a.add_handler(CommandHandler("start", cmd_start))
        a.add_handler(CommandHandler("help", cmd_help))
        a.add_handler(CommandHandler("linkgroup", cmd_linkgroup))
        a.add_handler(CommandHandler("status", cmd_status))
        # Moderation commands
        a.add_handler(CommandHandler("warn",     cmd_warn))
        a.add_handler(CommandHandler("ban",      cmd_ban))
        a.add_handler(CommandHandler("kick",     cmd_kick))
        a.add_handler(CommandHandler("mute",     cmd_mute))
        a.add_handler(CommandHandler("unmute",   cmd_unmute))
        a.add_handler(CommandHandler("tempban",  cmd_tempban))
        a.add_handler(CommandHandler("purge",    cmd_purge))
        a.add_handler(CommandHandler("warnings",       cmd_warnings))
        a.add_handler(CommandHandler("xp",             cmd_xp))
        a.add_handler(CommandHandler("leaderboard",    cmd_leaderboard))
        # Phase 2 commands
        a.add_handler(CommandHandler("tempmute",       cmd_tempmute))
        a.add_handler(CommandHandler("admins",         cmd_admins))
        a.add_handler(CommandHandler("roles",          cmd_roles))
        a.add_handler(CommandHandler("rank",           cmd_rank))
        a.add_handler(CommandHandler("me",             cmd_me))
        a.add_handler(CommandHandler("whois",          cmd_whois))
        a.add_handler(CommandHandler("report",         cmd_report))
        a.add_handler(CommandHandler("removewarning",  cmd_removewarning))
        a.add_handler(CommandHandler("unwarn",         cmd_removewarning))
        a.add_handler(CommandHandler("groupinfo",      cmd_groupinfo))
        a.add_handler(CommandHandler("auditlog",       cmd_auditlog))
        a.add_handler(CommandHandler("wallet",         cmd_wallet))
        a.add_handler(CommandHandler("mywallet",       cmd_wallet))
        a.add_handler(CommandHandler("ask",            cmd_ask))
        a.add_handler(CommandHandler("invitelink",     cmd_invitelink))
        a.add_handler(CommandHandler("remind",         cmd_remind))
        a.add_handler(CommandHandler("assist",         cmd_assist))
        a.add_handler(CallbackQueryHandler(on_assistant_pick, pattern=r"^assist_"))
        a.add_handler(CallbackQueryHandler(callback_handler))
        # Bot's own membership changes (added/removed from groups)
        a.add_handler(ChatMemberHandler(on_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
        # Any member's status changes — used for new-member join events
        a.add_handler(ChatMemberHandler(on_chat_member, ChatMemberHandler.CHAT_MEMBER))
        # Service messages (joins/leaves/pins etc.) for auto-clean
        a.add_handler(
            MessageHandler(
                (filters.ChatType.GROUP | filters.ChatType.SUPERGROUP) & filters.StatusUpdate.ALL,
                on_service_message,
            )
        )
        # Reaction XP
        if _REACTION_HANDLER_AVAILABLE:
            a.add_handler(_MsgReactionHandler(on_reaction))
        # Private text: bot token submission (must come before group message handler)
        a.add_handler(
            MessageHandler(
                filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND,
                on_private_text,
            )
        )
        a.add_handler(
            MessageHandler(
                (filters.ChatType.GROUP | filters.ChatType.SUPERGROUP) & filters.ALL,
                on_message,
            )
        )
        # Channel post analytics capture
        a.add_handler(
            MessageHandler(
                filters.ChatType.CHANNEL & filters.ALL,
                on_channel_post,
            )
        )

        # Rate-limit / flood error handler — respects Telegram RetryAfter
        async def _error_handler(update, context):
            import asyncio
            from telegram.error import RetryAfter, TimedOut, NetworkError
            exc = context.error
            if isinstance(exc, RetryAfter):
                _log.warning("[OfficialBot] Flood control: retry after %ss", exc.retry_after)
                await asyncio.sleep(exc.retry_after)
            elif isinstance(exc, (TimedOut, NetworkError)):
                _log.warning("[OfficialBot] Network error (transient): %s", exc)
            else:
                _log.error("[OfficialBot] Unhandled update error: %s", exc, exc_info=exc)
                try:
                    chat_id = None
                    if update is not None and getattr(update, "effective_chat", None):
                        chat_id = str(update.effective_chat.id)
                    from .health import record_bot_error
                    with flask_app.app_context():
                        record_bot_error("official", chat_id or "official", "handler", str(exc))
                except Exception:
                    pass

        a.add_error_handler(_error_handler)

        _log.info("[OfficialBot] Initializing application...")
        await a.initialize()
        await a.start()
        try:
            await a.bot.set_my_commands([
                BotCommand("start",    "Open companion hub"),
                BotCommand("help",     "Setup guide"),
                BotCommand("linkgroup","Link this group (use in group)"),
                BotCommand("status",   "Check bot status (use in group)"),
                BotCommand("warn",     "Warn a user (admins only)"),
                BotCommand("ban",      "Ban a user (admins only)"),
                BotCommand("kick",     "Kick a user (admins only)"),
                BotCommand("mute",     "Mute a user (admins only)"),
                BotCommand("unmute",   "Unmute a user (admins only)"),
                BotCommand("tempban",  "Temp-ban a user (admins only)"),
                BotCommand("purge",    "Delete last N messages (admins only)"),
                BotCommand("warnings",    "Check a user's warnings"),
                BotCommand("xp",         "Check your XP and level"),
                BotCommand("leaderboard","Top members by XP"),
            ])
        except Exception as exc:
            _log.warning("[OfficialBot] set_my_commands: %s", exc)
        # 1-E-02: Set bot description/branding
        try:
            await a.bot.set_my_description(
                "Telegizer — the all-in-one Telegram community platform. "
                "Moderation, welcome messages, AI digests, XP levels and more. "
                "Visit telegizer.com to connect your group."
            )
            await a.bot.set_my_short_description("All-in-one Telegram community manager")
        except Exception as exc:
            _log.warning("[OfficialBot] set_my_description: %s", exc)
        # Register the webhook with Telegram so updates are POSTed to our endpoint
        # rather than using long-polling (more efficient, scales to any concurrency).
        webhook_url = f"{Config.BACKEND_URL}/api/official-bot-update"
        secret_token = getattr(Config, "TELEGRAM_WEBHOOK_SECRET", None) or Config.SECRET_KEY[:32]
        allowed_updates = [
            "message", "edited_message",
            "channel_post", "edited_channel_post",
            "callback_query",
            "my_chat_member", "chat_member", "chat_join_request",
            "message_reaction", "message_reaction_count",
        ]
        try:
            await a.bot.set_webhook(
                url=webhook_url,
                secret_token=secret_token,
                allowed_updates=allowed_updates,
                drop_pending_updates=True,
            )
            _log.info("[OfficialBot] Webhook registered at %s", webhook_url)
        except Exception as exc:
            _log.error("[OfficialBot] Failed to register webhook: %s", exc)
            raise

        _log.info("[OfficialBot] Webhook mode active — bot is live.")
        # Wait until stop is requested; updates arrive via HTTP webhook.
        try:
            while not self._stop_event.is_set():
                await asyncio.sleep(60)
        except asyncio.CancelledError:
            pass
        finally:
            _log.info("[OfficialBot] Shutting down webhook bot...")
            try:
                await a.bot.delete_webhook()
            except Exception:
                pass
            for _coro in (a.stop(), a.shutdown()):
                try:
                    await _coro
                except Exception:
                    pass


async def _send_official_digest(bot, tg, days: int = 7):
    """Send a stats digest respecting recipient settings. Must be called with an active app context."""
    group_id = tg.telegram_group_id
    since = datetime.utcnow() - timedelta(days=days)

    try:
        from .models import BotEvent, OfficialWarning, OfficialMember, OfficialScheduledMessage, OfficialPoll, User, TelegramBotStarted

        joins = BotEvent.query.filter(
            BotEvent.telegram_group_id == group_id,
            BotEvent.event_type == "member_joined",
            BotEvent.created_at >= since,
        ).count()

        automod = BotEvent.query.filter(
            BotEvent.telegram_group_id == group_id,
            BotEvent.event_type == "automod_action",
            BotEvent.created_at >= since,
        ).count()

        warns = OfficialWarning.query.filter(
            OfficialWarning.telegram_group_id == group_id,
            OfficialWarning.created_at >= since,
        ).count()

        bans = BotEvent.query.filter(
            BotEvent.telegram_group_id == group_id,
            BotEvent.event_type.in_(["mod_ban", "mod_tempban"]),
            BotEvent.created_at >= since,
        ).count()

        commands = BotEvent.query.filter(
            BotEvent.telegram_group_id == group_id,
            BotEvent.event_type == "command_triggered",
            BotEvent.created_at >= since,
        ).count()

        scheduled_sent = OfficialScheduledMessage.query.filter(
            OfficialScheduledMessage.telegram_group_id == group_id,
            OfficialScheduledMessage.is_sent == True,
            OfficialScheduledMessage.send_at >= since,
        ).count()

        polls_sent = OfficialPoll.query.filter(
            OfficialPoll.telegram_group_id == group_id,
            OfficialPoll.is_sent == True,
            OfficialPoll.scheduled_at >= since,
        ).count()

        top_members = OfficialMember.query.filter_by(
            telegram_group_id=group_id,
        ).order_by(OfficialMember.xp.desc()).limit(3).all()

        member_count = OfficialMember.query.filter_by(telegram_group_id=group_id).count()

        lines = [
            f"📊 *{tg.title} — {days}-Day Digest*\n",
            f"👥 Members tracked: {member_count} (+{joins} new)",
            f"🛡️ AutoMod actions: {automod}",
            f"⚠️ Warnings issued: {warns}",
            f"🚫 Bans: {bans}",
            f"💬 Commands used: {commands}",
        ]

        if scheduled_sent or polls_sent:
            lines.append(f"📅 Scheduled posts sent: {scheduled_sent}")
            lines.append(f"📊 Polls sent: {polls_sent}")

        if top_members:
            lines.append("\n🏆 *Top Members*")
            medals = ["🥇", "🥈", "🥉"]
            for i, m in enumerate(top_members):
                name = m.first_name or m.username or f"User {m.telegram_user_id}"
                lines.append(f"{medals[i]} {name} — Lv.{m.level} ({m.xp} XP)")

        lines.append(f"\n_Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC_")

        # AI summary — only if admin enabled it and has an API key configured
        try:
            if (tg.settings or {}).get("assistant", {}).get("ai_digest_enabled"):
                from .assistant.digest_ai import get_group_ai_summary
                ai_summary = get_group_ai_summary(group_id)
                if ai_summary:
                    lines.append(f"\n🤖 *AI Summary*\n{ai_summary}")
        except Exception as ai_exc:
            _log.debug("AI digest summary failed for group %s: %s", group_id, ai_exc)

        text = "\n".join(lines)

        # Read recipients config — fall back to group delivery if not configured
        recipients = (tg.settings or {}).get("digest", {}).get("recipients", {})
        send_to_group = recipients.get("send_to_group", True)
        topic_id = recipients.get("group_topic_id")
        owner_dm = recipients.get("owner_dm", False)
        admin_ids = recipients.get("selected_admin_ids") or []

        async def _send_msg(chat_id, thread_id=None):
            kwargs: dict = {"chat_id": chat_id, "text": text, "parse_mode": ParseMode.MARKDOWN}
            if thread_id:
                kwargs["message_thread_id"] = int(thread_id)
            await bot.send_message(**kwargs)

        if send_to_group:
            try:
                is_forum = getattr(tg, "is_forum", False)
                resolved_topic = topic_id or ((tg.settings or {}).get("default_topic_id") or 1 if is_forum else None)
                await _send_msg(int(group_id), resolved_topic)
            except Exception as exc:
                _log.error("[OfficialBot] Digest group send failed for group %s: %s", group_id, exc)

        if owner_dm and tg.owner_user_id:
            owner = User.query.get(tg.owner_user_id)
            if owner and owner.telegram_user_id and TelegramBotStarted.has_started(str(owner.telegram_user_id)):
                try:
                    await _send_msg(int(owner.telegram_user_id))
                except Exception as exc:
                    _log.error("[OfficialBot] Digest owner DM failed for group %s: %s", group_id, exc)
            else:
                _log.info("[OfficialBot] Owner has not started bot or no telegram_user_id — skipping DM for group %s", group_id)

        for admin_id in admin_ids:
            if TelegramBotStarted.has_started(str(admin_id)):
                try:
                    await _send_msg(int(admin_id))
                except Exception as exc:
                    _log.error("[OfficialBot] Digest admin DM failed admin=%s group=%s: %s", admin_id, group_id, exc)
            else:
                _log.info("[OfficialBot] Admin %s has not started bot — skipping DM for group %s", admin_id, group_id)

    except Exception as exc:
        _log.error("[OfficialBot] Digest send failed for group %s: %s", group_id, exc)
        raise


_runner = OfficialBotRunner()


def start_official_bot(flask_app):
    _runner.start(flask_app)


def get_official_bot_loop():
    """Return (bot, loop) for use by the scheduler. Returns (None, None) if not running."""
    if _runner.application and _runner.loop and _runner.loop.is_running():
        return _runner.application.bot, _runner.loop
    return None, None


def _get_bot(flask_app=None):
    """Return the live bot object, or None if not running."""
    bot, _ = get_official_bot_loop()
    return bot
