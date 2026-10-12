"""Direct team invites: the owner picks a Telegram admin of the group, the bot that manages that
group DMs them Accept / Reject buttons, and accepting creates the same TelegramGroupAccess row an
access code does.

Works for groups managed by the official bot AND by the owner's custom bots (the DM is sent, and the
button press arrives, through whichever bot manages the group). Rule: a bot only ever messages a person
who has already pressed Start on THAT bot (TelegramBotStarted for the official bot, CustomBotStarted
for custom bots). Nobody who has not started the bot is ever contacted.

Kill switch: env GROUP_TEAM_DIRECT_INVITES_ENABLED=0 stops new direct invites and makes pending ones
unacceptable. Existing grants stay (they are governed by GROUP_TEAM_ACCESS_ENABLED).
"""
import html as _htmllib
import logging
import os
import secrets
from datetime import datetime
from types import SimpleNamespace

import requests as _http
from sqlalchemy.exc import IntegrityError

from .config import Config
from .models import (
    db, User, UserTelegramAccount, TelegramGroup, TelegramGroupAccess, TelegramGroupInvite,
    TelegramBotStarted, CustomBotStarted, CustomBot, Bot, Group, BotEvent,
)
from .group_access import team_access_enabled, resolve_group_record, norm_bot_key, OFFICIAL_KEY

logger = logging.getLogger(__name__)

_API = "https://api.telegram.org/bot{token}/{method}"
ADMIN_STATUSES = ("creator", "administrator")


def direct_invites_enabled() -> bool:
    if os.environ.get("GROUP_TEAM_DIRECT_INVITES_ENABLED", "1").strip().lower() in ("0", "false", "off", "no"):
        return False
    return team_access_enabled()


# ── Which bot manages a group ────────────────────────────────────────────────

def bot_for_chat(telegram_group_id, owner_id):
    """The bot that manages this chat for `owner_id`, as
    SimpleNamespace(key, username, token, official) or None.

    Official bot: TelegramGroup linked via the official bot. Custom bot: the CustomBot a TelegramGroup
    is linked to, else the legacy Bot a Group row belongs to. The bot must belong to the owner.
    """
    gid = str(telegram_group_id)
    tg = TelegramGroup.query.filter_by(telegram_group_id=gid, owner_user_id=owner_id, is_disabled=False).first()
    if tg and (tg.linked_via_bot_type or "official") == "official":
        if not Config.TELEGRAM_BOT_TOKEN:
            return None
        return SimpleNamespace(key=OFFICIAL_KEY, official=True, token=Config.TELEGRAM_BOT_TOKEN,
                               username=(Config.TELEGRAM_BOT_USERNAME or "").strip().lstrip("@"))
    if tg and tg.linked_bot_id:
        cb = CustomBot.query.get(tg.linked_bot_id)
        if cb and cb.owner_user_id == owner_id and norm_bot_key(cb.bot_username):
            return _custom_ns(cb.bot_username, cb)
    for grp, bot in (db.session.query(Group, Bot).join(Bot, Bot.id == Group.bot_id)
                     .filter(Group.telegram_group_id == gid, Bot.user_id == owner_id).all()):
        if norm_bot_key(bot.bot_username):
            return _custom_ns(bot.bot_username, bot)
    return None


def _custom_ns(username, record):
    try:
        token = record.get_token()
    except Exception:
        logger.warning("could not decrypt token for bot %s", username)
        return None
    return SimpleNamespace(key=norm_bot_key(username), official=False, token=token,
                           username=norm_bot_key(username))


def has_started(bot, telegram_user_id) -> bool:
    if bot.official:
        return TelegramBotStarted.has_started(str(telegram_user_id))
    return CustomBotStarted.has_started(bot.key, telegram_user_id)


def _call(token, method, **params):
    if not token:
        return {"ok": False, "description": "Bot token not configured"}
    try:
        return _http.post(_API.format(token=token, method=method), json=params, timeout=10).json()
    except Exception as exc:  # network failure must not 500 a request
        logger.warning("telegram %s failed: %s", method, exc)
        return {"ok": False, "description": "Telegram is unreachable"}


def chat_admins(bot, telegram_group_id):
    """(admins, error). admins = [{user_id, username, name, status}] excluding bots."""
    res = _call(bot.token, "getChatAdministrators", chat_id=str(telegram_group_id))
    if not res.get("ok"):
        return [], res.get("description") or "Telegram error"
    out = []
    for m in res.get("result", []):
        u = m.get("user", {})
        if u.get("is_bot") or not u.get("id"):
            continue
        name = " ".join(x for x in (u.get("first_name"), u.get("last_name")) if x).strip()
        out.append({"user_id": str(u["id"]), "username": u.get("username"),
                    "name": name or u.get("username") or str(u["id"]), "status": m.get("status")})
    return out, None


def is_chat_admin(bot, telegram_group_id, telegram_user_id) -> bool:
    res = _call(bot.token, "getChatMember", chat_id=str(telegram_group_id), user_id=int(telegram_user_id))
    return bool(res.get("ok")) and (res.get("result") or {}).get("status") in ADMIN_STATUSES


# ── Accounts ─────────────────────────────────────────────────────────────────

def user_for_telegram(tg_id):
    """Existing Telegizer account for a Telegram id (users column first, then linked accounts)."""
    tg_id = str(tg_id)
    user = User.query.filter_by(telegram_user_id=tg_id).first()
    if not user:
        acct = UserTelegramAccount.query.filter_by(telegram_user_id=tg_id).first()
        user = User.query.get(acct.user_id) if acct else None
    return user


def telegram_ids_of(user) -> set:
    """Every Telegram id linked to this account."""
    ids = {str(user.telegram_user_id)} if user.telegram_user_id else set()
    ids |= {str(a.telegram_user_id) for a in UserTelegramAccount.query.filter_by(user_id=user.id).all()}
    return ids


def _get_or_create_user(tg_id, username, first_name):
    """The Telegizer account for a Telegram id, created Telegram-only if none exists (same shape the
    Mini App auto-creates, so the Mini App later reuses it)."""
    user = user_for_telegram(tg_id)
    if user:
        return user
    user = User(
        telegram_user_id=str(tg_id), telegram_username=username, telegram_first_name=first_name or "",
        telegram_connected_at=datetime.utcnow(), full_name=(first_name or "").strip() or f"User {tg_id}",
        auth_provider="telegram", subscription_tier="free",
        referral_code=secrets.token_urlsafe(8)[:10], email_verified=False)
    try:
        with db.session.begin_nested():
            db.session.add(user)
            db.session.flush()
    except IntegrityError:  # another request created the same Telegram account first
        return User.query.filter_by(telegram_user_id=str(tg_id)).first()
    return user


# ── The invitation message ───────────────────────────────────────────────────

def _esc(s):
    return _htmllib.escape(str(s or ""))


def invite_dm_text(group_title, owner_name, role):
    what = ("full control: settings, moderation, automations, forwarding and tasks"
            if role == "manager" else "view-only access to everything, no changes")
    return (f"👥 <b>Team invitation</b>\n\n"
            f"{_esc(owner_name)} invites you to {'manage' if role == 'manager' else 'view'} "
            f"<b>{_esc(group_title)}</b> on Telegizer as <b>{role.title()}</b> ({what}).\n\n"
            f"You will only get access to this one group. The invitation expires in 7 days.")


def send_invite_dm(bot, inv, group_title, owner_name):
    """DM the invitee through the group's bot. Only ever called for people who started that bot.
    Returns (ok, error)."""
    if not has_started(bot, inv.invitee_telegram_id):
        return False, "They have not started this bot"
    res = _call(
        bot.token, "sendMessage", chat_id=int(inv.invitee_telegram_id), parse_mode="HTML",
        text=invite_dm_text(group_title, owner_name, inv.role),
        reply_markup={"inline_keyboard": [[
            {"text": "✅ Accept", "callback_data": f"gti:a:{inv.id}"},
            {"text": "❌ Reject", "callback_data": f"gti:r:{inv.id}"},
        ]]})
    if res.get("ok"):
        return True, None
    return False, res.get("description") or "Could not message this person"


# ── Pressing the buttons ─────────────────────────────────────────────────────

def _pending(inv):
    return inv is not None and inv.used_by is None and inv.declined_at is None


def respond(invite_id, tg_user, accept):
    """Handle the invitee pressing Accept / Reject. Returns (status, info); status is one of
    ok | declined | gone | not_you | disabled | not_admin, and info carries
    {group_title, role, owner_id, owner_tg_ids, telegram_group_id}."""
    inv = TelegramGroupInvite.query.get(invite_id)
    if inv is None or not inv.invitee_telegram_id:
        return "gone", {}
    if inv.invitee_telegram_id != str(tg_user.id):
        return "not_you", {}
    group = resolve_group_record(inv.telegram_group_id)
    owner = User.query.get(inv.created_by)
    info = {"group_title": group.title if group else "the group", "role": inv.role,
            "owner_id": inv.created_by, "owner_tg_ids": telegram_ids_of(owner) if owner else set(),
            "telegram_group_id": inv.telegram_group_id}
    if (not _pending(inv) or inv.expires_at <= datetime.utcnow()
            or not group or group.owner_user_id != inv.created_by):
        return "gone", info
    if not accept:
        inv.declined_at = datetime.utcnow()
        db.session.add(BotEvent(telegram_group_id=inv.telegram_group_id, event_type="group_team_declined",
                                message=f"Telegram user {tg_user.id} declined the invite",
                                metadata_={"telegram_user_id": str(tg_user.id), "role": inv.role}))
        db.session.commit()
        return "declined", info
    if not direct_invites_enabled():
        return "disabled", info
    bot = bot_for_chat(inv.telegram_group_id, inv.created_by)
    if bot is None or not is_chat_admin(bot, inv.telegram_group_id, tg_user.id):
        return "not_admin", info
    user = _get_or_create_user(tg_user.id, getattr(tg_user, "username", None), getattr(tg_user, "first_name", None))
    if user is None or user.is_banned or user.id == inv.created_by:
        db.session.rollback()
        return "gone", info
    claimed = TelegramGroupInvite.query.filter_by(id=inv.id, used_by=None, declined_at=None).update(
        {"used_by": user.id, "used_at": datetime.utcnow()}, synchronize_session=False)
    if claimed != 1:
        db.session.rollback()
        return "gone", info
    row = TelegramGroupAccess.query.filter_by(telegram_group_id=inv.telegram_group_id, user_id=user.id).first()
    if row:
        row.role, row.invited_by = inv.role, inv.created_by
    else:
        db.session.add(TelegramGroupAccess(telegram_group_id=inv.telegram_group_id, user_id=user.id,
                                           role=inv.role, invited_by=inv.created_by))
        db.session.add(BotEvent(telegram_group_id=inv.telegram_group_id, event_type="group_team_joined",
                                message=f"User {user.id} joined as {inv.role} (direct invite)",
                                metadata_={"user_id": user.id, "role": inv.role,
                                           "invited_by": inv.created_by, "via": "direct_invite"}))
    db.session.commit()
    return "ok", info


async def handle_invite_press(update, context, flask_app, *, bot_key, official):
    """Shared Accept / Reject callback (callback_data gti:<a|r>:<invite_id>) for the official bot and
    for custom bots. `bot_key` is OFFICIAL_KEY or the custom bot's lowercase username."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

    query = update.callback_query
    user = update.effective_user
    try:
        _, action, raw_id = query.data.split(":")
        invite_id = int(raw_id)
    except Exception:
        await query.answer()
        return
    if not flask_app:
        await query.answer("Service temporarily unavailable. Try again shortly.", show_alert=True)
        return
    try:
        with flask_app.app_context():
            status, info = respond(invite_id, user, accept=(action == "a"))
            owner_targets = []
            if status in ("ok", "declined"):
                # Tell the owner, but only through a bot they have started.
                for oid in info.get("owner_tg_ids", ()):
                    started = (TelegramBotStarted.has_started(oid) if official
                               else CustomBotStarted.has_started(bot_key, oid))
                    if started:
                        owner_targets.append(oid)
    except Exception:
        logger.exception("group invite response failed")
        try:
            db.session.rollback()
        except Exception:
            pass
        await query.answer("Something went wrong. Please try again.", show_alert=True)
        return

    if status == "not_you":
        await query.answer("This invitation is not for you.", show_alert=True)
        return
    await query.answer()

    title = _esc(info.get("group_title") or "the group")
    frontend = Config.FRONTEND_URL or "https://telegizer.com"
    notes = {
        "gone": "This invitation is no longer valid. Ask the group owner to send a new one.",
        "disabled": "Team invitations are paused right now. Please try again later.",
        "not_admin": "You are no longer an admin of this group, so the invitation cannot be accepted.",
        "declined": f"You declined the invitation to <b>{title}</b>.",
    }
    if status == "ok":
        rows = []
        official_un = (Config.TELEGRAM_BOT_USERNAME or "").strip().lstrip("@")
        if official:
            rows.append([InlineKeyboardButton("Open in Telegram", web_app=WebAppInfo(url=f"{frontend}/mini-app"))])
        elif official_un:  # the Mini App lives on the official bot
            rows.append([InlineKeyboardButton("Open in Telegram", url=f"https://t.me/{official_un}")])
        rows.append([InlineKeyboardButton("Open on website", url=f"{frontend}/groups")])
        text = (f"✅ You now have <b>{_esc(info['role'].title())}</b> access to <b>{title}</b>.\n\n"
                f"Open it in Telegram, or on the website by signing in with Telegram.")
        markup = InlineKeyboardMarkup(rows)
    else:
        text, markup = notes.get(status, notes["gone"]), None
    try:
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
    except Exception:
        pass

    who = _esc(" ".join(x for x in (user.first_name, user.last_name) if x) or "An admin")
    msg = (f"✅ {who} accepted your invitation to <b>{title}</b> as {info.get('role')}."
           if status == "ok" else f"❌ {who} declined your invitation to <b>{title}</b>.")
    for oid in owner_targets:
        try:
            await context.bot.send_message(int(oid), msg, parse_mode="HTML")
        except Exception:
            pass
