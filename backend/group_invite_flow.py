"""Direct team invites: the owner picks a Telegram admin of the group, the bot DMs them
Accept / Reject buttons, and accepting creates the same TelegramGroupAccess row an access code does.

Only the official bot is supported (it is the bot that can read the group's admin list and DM
the invitee). Everything here is synchronous so both Flask routes and the bot handler can use it.

Kill switch: env GROUP_TEAM_DIRECT_INVITES_ENABLED=0 stops new direct invites and makes pending
ones unacceptable. Existing grants stay (they are governed by GROUP_TEAM_ACCESS_ENABLED).
"""
import logging
import os
import secrets
from datetime import datetime

import requests as _http

from .config import Config
from .models import (
    db, User, UserTelegramAccount, TelegramGroup, TelegramGroupAccess, TelegramGroupInvite, BotEvent,
)
from .group_access import team_access_enabled, resolve_group_record

logger = logging.getLogger(__name__)

_API = "https://api.telegram.org/bot{token}/{method}"
ADMIN_STATUSES = ("creator", "administrator")


def direct_invites_enabled() -> bool:
    if os.environ.get("GROUP_TEAM_DIRECT_INVITES_ENABLED", "1").strip().lower() in ("0", "false", "off", "no"):
        return False
    return team_access_enabled()


def _call(method, **params):
    token = Config.TELEGRAM_BOT_TOKEN
    if not token:
        return {"ok": False, "description": "Bot token not configured"}
    try:
        return _http.post(_API.format(token=token, method=method), json=params, timeout=10).json()
    except Exception as exc:  # network failure must not 500 a request
        logger.warning("telegram %s failed: %s", method, exc)
        return {"ok": False, "description": "Telegram is unreachable"}


def official_group(telegram_group_id):
    """The TelegramGroup row if this chat is managed by the official bot, else None."""
    tg = TelegramGroup.query.filter_by(telegram_group_id=str(telegram_group_id), is_disabled=False).first()
    if tg and (tg.linked_via_bot_type or "official") == "official":
        return tg
    return None


def chat_admins(telegram_group_id):
    """(admins, error). admins = [{user_id, username, name, status}] excluding bots."""
    res = _call("getChatAdministrators", chat_id=str(telegram_group_id))
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


def is_chat_admin(telegram_group_id, telegram_user_id) -> bool:
    res = _call("getChatMember", chat_id=str(telegram_group_id), user_id=int(telegram_user_id))
    return bool(res.get("ok")) and (res.get("result") or {}).get("status") in ADMIN_STATUSES


def invite_dm_text(group_title, owner_name, role):
    what = ("full control: settings, moderation, automations, forwarding and tasks"
            if role == "manager" else "view-only access to everything, no changes")
    return (f"👥 <b>Team invitation</b>\n\n"
            f"{_esc(owner_name)} invites you to {'manage' if role == 'manager' else 'view'} "
            f"<b>{_esc(group_title)}</b> on Telegizer as <b>{role.title()}</b> ({what}).\n\n"
            f"You will only get access to this one group. The invitation expires in 7 days.")


def _esc(s):
    return (str(s or "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def send_invite_dm(inv, group_title, owner_name):
    """DM the invitee. Returns (ok, error)."""
    res = _call(
        "sendMessage", chat_id=int(inv.invitee_telegram_id), parse_mode="HTML",
        text=invite_dm_text(group_title, owner_name, inv.role),
        reply_markup={"inline_keyboard": [[
            {"text": "✅ Accept", "callback_data": f"gti:a:{inv.id}"},
            {"text": "❌ Reject", "callback_data": f"gti:r:{inv.id}"},
        ]]})
    if res.get("ok"):
        return True, None
    return False, res.get("description") or "Could not message this person"


def _telegram_user(tg_id, username, first_name):
    """The Telegizer account for a Telegram id, created Telegram-only if none exists
    (same shape the Mini App auto-creates, so the Mini App later reuses it)."""
    tg_id = str(tg_id)
    user = User.query.filter_by(telegram_user_id=tg_id).first()
    if not user:
        acct = UserTelegramAccount.query.filter_by(telegram_user_id=tg_id).first()
        user = User.query.get(acct.user_id) if acct else None
    if user:
        return user
    user = User(
        telegram_user_id=tg_id, telegram_username=username, telegram_first_name=first_name or "",
        telegram_connected_at=datetime.utcnow(), full_name=(first_name or "").strip() or f"User {tg_id}",
        auth_provider="telegram", subscription_tier="free",
        referral_code=secrets.token_urlsafe(8)[:10], email_verified=False)
    db.session.add(user)
    db.session.flush()
    return user


def _pending(inv):
    return inv is not None and inv.used_by is None and inv.declined_at is None


def respond(invite_id, tg_user, accept):
    """Handle the invitee pressing Accept / Reject. Returns (status, info) where status is one of
    ok | declined | gone | not_you | disabled | not_admin | full, and info carries
    {group_title, role, owner_id, owner_tg, user_id, telegram_group_id} when known."""
    inv = TelegramGroupInvite.query.get(invite_id)
    if inv is None or not inv.invitee_telegram_id:
        return "gone", {}
    if inv.invitee_telegram_id != str(tg_user.id):
        return "not_you", {}
    group = resolve_group_record(inv.telegram_group_id)
    owner = User.query.get(inv.created_by)
    info = {"group_title": group.title if group else "the group", "role": inv.role,
            "owner_id": inv.created_by, "owner_tg": owner.telegram_user_id if owner else None,
            "telegram_group_id": inv.telegram_group_id}
    if not _pending(inv) or inv.expires_at <= datetime.utcnow() or not group or group.owner_user_id != inv.created_by:
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
    if not is_chat_admin(inv.telegram_group_id, tg_user.id):
        return "not_admin", info
    user = _telegram_user(tg_user.id, tg_user.username, tg_user.first_name)
    info["user_id"] = user.id
    if user.id == inv.created_by:
        return "gone", info
    claimed = TelegramGroupInvite.query.filter_by(id=inv.id, used_by=None, declined_at=None).update(
        {"used_by": user.id, "used_at": datetime.utcnow()}, synchronize_session=False)
    if claimed != 1:
        db.session.rollback()
        return "gone", info
    row = TelegramGroupAccess.query.filter_by(
        telegram_group_id=inv.telegram_group_id, user_id=user.id).first()
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
