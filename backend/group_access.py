"""Per-group dashboard access for Telegram groups.

Single source of truth for "may this user touch this group?". The owner
(TelegramGroup.owner_user_id) always may. Anyone else needs a
TelegramGroupAccess row for that exact group; viewers are read-only.

Covers both worlds a Telegram group can live in:
  * TelegramGroup  (official bot, and custom bots linked via the new system)
  * Group under Bot (legacy custom-bot runner, /api/bots/<bot_id>/groups/<id>/...)
Access rows are keyed by the Telegram chat id, so one grant works for both.

Kill switch: Admin panel -> Configuration -> Feature flags ->
"group_team_access_enabled" (off = every shared person is locked out; owners are
unaffected). The env var GROUP_TEAM_ACCESS_ENABLED=0 does the same and wins.
"""
import os
import re

from flask import jsonify, make_response, request, abort, g as flask_g

from types import SimpleNamespace

from .models import db, Bot, Group, TelegramGroup, TelegramGroupAccess

_READ_METHODS = ("GET", "HEAD", "OPTIONS")


def team_access_enabled() -> bool:
    if os.environ.get("GROUP_TEAM_ACCESS_ENABLED", "1").strip().lower() in ("0", "false", "off", "no"):
        return False
    try:
        from . import platform_config as pc
        return bool(pc.is_feature_enabled("group_team_access_enabled"))
    except Exception:
        return True  # a config lookup failure must not lock people out


def get_access_role(user_id: int, group: TelegramGroup):
    """'owner' | 'manager' | 'viewer' | None."""
    if group.owner_user_id == user_id:
        return "owner"
    if not team_access_enabled():
        return None
    row = TelegramGroupAccess.query.filter_by(
        telegram_group_id=group.telegram_group_id, user_id=user_id
    ).first()
    # The grant only counts while the person who issued it still owns the group.
    return row.role if row and row.invited_by == group.owner_user_id else None


def get_group_for_user(user_id: int, group_id, *, owner_only: bool = False, check_disabled: bool = True):
    """Return the TelegramGroup the user may access, else None.

    - owner_only: reserved for unlinking, API keys and team management.
    - Viewers get a 403 on any non-read request (never a silent write).
    """
    q = TelegramGroup.query.filter_by(telegram_group_id=str(group_id))
    if check_disabled:
        q = q.filter_by(is_disabled=False)
    group = q.first()
    if not group:
        return None
    role = get_access_role(user_id, group)
    if role is None:
        return None
    if owner_only and role != "owner":
        abort(make_response(jsonify({"error": "Only the group owner can do this"}), 403))
    if role == "viewer" and request.method not in _READ_METHODS:
        abort(make_response(jsonify({"error": "You have view-only access to this group"}), 403))
    return group


def shared_groups_for_user(user_id: int):
    """[(TelegramGroup, role)] for groups shared with this user (not owned)."""
    if not team_access_enabled():
        return []
    rows = TelegramGroupAccess.query.filter_by(user_id=user_id).all()
    if not rows:
        return []
    by_id = {r.telegram_group_id: r.role for r in rows}
    groups = TelegramGroup.query.filter(
        TelegramGroup.telegram_group_id.in_(list(by_id)),
        TelegramGroup.is_disabled == False,  # noqa: E712
    ).all()
    issuer = {r.telegram_group_id: r.invited_by for r in rows}
    return [(g, by_id[g.telegram_group_id]) for g in groups
            if g.owner_user_id != user_id and issuer.get(g.telegram_group_id) == g.owner_user_id]


def _deny(msg, code=403):
    abort(make_response(jsonify({"error": msg}), code))


def get_legacy_bot_group(user_id: int, bot_id: int, group_id: int, *, owner_only: bool = False):
    """(bot, group) for /api/bots/<bot_id>/groups/<group_id>/... routes.

    The bot owner behaves exactly as before (group may be None if it doesn't
    belong to the bot). Anyone else needs a TelegramGroupAccess row for that
    group's Telegram chat id; viewers are read-only; owner_only blocks shared users.
    """
    bot = Bot.query.get(bot_id)
    if not bot:
        return None, None
    group = Group.query.filter_by(id=group_id, bot_id=bot.id).first()
    if bot.user_id == user_id:
        return bot, group
    if not group or not team_access_enabled():
        return None, None
    row = TelegramGroupAccess.query.filter_by(
        telegram_group_id=group.telegram_group_id, user_id=user_id).first()
    if not row or row.invited_by != bot.user_id:
        return None, None
    if owner_only:
        _deny("Only the group owner can do this")
    if row.role == "viewer" and request.method not in _READ_METHODS:
        _deny("You have view-only access to this group")
    return bot, group


def resolve_group_record(telegram_group_id):
    """Find a linked group by Telegram chat id in either system.

    Returns SimpleNamespace(telegram_group_id, title, owner_user_id) or None.
    """
    gid = str(telegram_group_id)
    tg = TelegramGroup.query.filter_by(telegram_group_id=gid, is_disabled=False).first()
    if tg and tg.owner_user_id:
        return SimpleNamespace(telegram_group_id=gid, title=tg.title, owner_user_id=tg.owner_user_id)
    for grp in Group.query.filter_by(telegram_group_id=gid).all():
        bot = Bot.query.get(grp.bot_id)
        if bot:
            return SimpleNamespace(telegram_group_id=gid, title=grp.group_name or "Group",
                                   owner_user_id=bot.user_id)
    return None


def owned_group_record(user_id: int, telegram_group_id):
    """Group record only if this user is the OWNER (not just a shared manager)."""
    rec = resolve_group_record(telegram_group_id)
    if rec and rec.owner_user_id == user_id:
        return rec
    # a user may own it through the legacy system while TelegramGroup names someone else
    gid = str(telegram_group_id)
    for grp in Group.query.filter_by(telegram_group_id=gid).all():
        bot = Bot.query.get(grp.bot_id)
        if bot and bot.user_id == user_id:
            return SimpleNamespace(telegram_group_id=gid, title=grp.group_name or "Group", owner_user_id=user_id)
    return None


def plan_user(user, owner_user_id):
    """The user whose subscription governs a group.

    For a shared manager this is the group OWNER, so plan limits and paid
    features follow the group, not whoever is clicking (a Pro friend must not
    unlock Pro features on a free owner's group, and vice versa).
    """
    from .models import User
    if owner_user_id and owner_user_id != user.id:
        return User.query.get(owner_user_id) or user
    return user


# ── Resource-level sharing (rules, workflows, links, tasks, notes) ───────────
# Some group things are stored against the owner's account (owner_user_id) and
# only point at a group. A shared person may use one only when EVERY chat it
# touches was granted to them by that same owner, and the owner still owns it.

def grants_by_owner(user_id: int) -> dict:
    """{owner_id: {chat_id: role}} for valid, enabled grants this user holds."""
    if not team_access_enabled():
        return {}
    cache = getattr(flask_g, "_grants_cache", None)
    if cache is None:
        cache = flask_g._grants_cache = {}
    if user_id in cache:
        return cache[user_id]
    rows = TelegramGroupAccess.query.filter_by(user_id=user_id).all()
    out: dict = {}
    if rows:
        chats = list({r.telegram_group_id for r in rows})
        live = set()
        for tg in TelegramGroup.query.filter(
                TelegramGroup.telegram_group_id.in_(chats),
                TelegramGroup.is_disabled == False,  # noqa: E712
                TelegramGroup.owner_user_id.isnot(None)).all():
            live.add((tg.owner_user_id, tg.telegram_group_id))
        for grp, bot in (db.session.query(Group, Bot)
                         .join(Bot, Bot.id == Group.bot_id)
                         .filter(Group.telegram_group_id.in_(chats)).all()):
            live.add((bot.user_id, grp.telegram_group_id))
        for r in rows:
            if r.invited_by != user_id and (r.invited_by, r.telegram_group_id) in live:
                out.setdefault(r.invited_by, {})[r.telegram_group_id] = r.role
    cache[user_id] = out
    return out


def role_on_chats(user_id: int, owner_id, chats) -> "str | None":
    """'owner' | 'manager' | 'viewer' | None for a resource owned by owner_id
    that touches `chats`. Never aborts."""
    if owner_id is None:
        return None
    if user_id == owner_id:
        return "owner"
    chats = [str(c) for c in chats if c]
    granted = grants_by_owner(user_id).get(owner_id, {})
    if not chats or any(c not in granted for c in chats):
        return None
    return "viewer" if any(granted[c] == "viewer" for c in chats) else "manager"


def resource_role(user_id: int, owner_id, chats, *, write=None) -> "str | None":
    """Like role_on_chats, but a viewer attempting a write gets a clean 403."""
    role = role_on_chats(user_id, owner_id, chats)
    if role == "viewer":
        is_write = (request.method not in _READ_METHODS) if write is None else write
        if is_write:
            _deny("You have view-only access to this group")
    return role


def shared_owner_for_chats(user_id: int, chats):
    """The single owner who granted MANAGER access on every one of `chats`, else None."""
    chats = [str(c) for c in chats if c]
    if not chats:
        return None
    for owner_id, granted in grants_by_owner(user_id).items():
        if all(granted.get(c) == "manager" for c in chats):
            return owner_id
    return None


def owned_chat_ids(user_id: int) -> set:
    """Telegram chat ids this user owns (official-system and legacy custom bots)."""
    ids = {g.telegram_group_id for g in TelegramGroup.query.filter_by(
        owner_user_id=user_id, is_disabled=False).all()}
    bot_ids = [b.id for b in Bot.query.filter_by(user_id=user_id).all()]
    if bot_ids:
        ids |= {g.telegram_group_id for g in Group.query.filter(Group.bot_id.in_(bot_ids)).all()}
    return ids


def group_scope(user_id: int):
    """(readable_chat_ids, writable_chat_ids) = owned + granted."""
    owned = owned_chat_ids(user_id)
    read, write = set(owned), set(owned)
    for granted in grants_by_owner(user_id).values():
        for chat, role in granted.items():
            read.add(chat)
            if role == "manager":
                write.add(chat)
    return read, write


def may_tag_group(user_id: int, group_id) -> bool:
    """May this user attach `group_id` to a task/note? Ids that belong to nobody
    we know about stay allowed (personal); another owner's group needs write access."""
    if not group_id:
        return True
    gid = str(group_id)
    if gid in group_scope(user_id)[1]:
        return True
    rec = resolve_group_record(gid)
    return rec is None  # known group of someone else -> refuse

# ── Central request guard ─────────────────────────────────────────────────────
# Several legacy handlers wrap everything in `try/except Exception`, which would
# swallow the 403 raised by the helpers above and turn it into a 500. This runs
# before the handler so viewer / owner-only rules always answer a clean 403.
_LEGACY_PATH = re.compile(r"^/api/bots/(\d+)/groups/(\d+)(/.*)?$")
_OFFICIAL_PATH = re.compile(r"^/api/(?:telegram-groups|official-groups)/([^/]+)(/.*)?$")
_OWNER_ONLY_PREFIXES = ("/api-key",)  # AI provider keys (covers /api-key and /api-keys)


def _forbid(msg):
    return make_response(jsonify({"error": msg}), 403)


def _guard_group_access():
    write = request.method not in _READ_METHODS
    m = _LEGACY_PATH.match(request.path)
    if m:
        rest = m.group(3) or ""
        key = ("legacy", int(m.group(1)), int(m.group(2)))
    else:
        m = _OFFICIAL_PATH.match(request.path)
        if not m:
            return None
        rest = m.group(2) or ""
        key = ("official", m.group(1))
    owner_only = rest.startswith(_OWNER_ONLY_PREFIXES)
    if not (write or owner_only):
        return None
    try:
        from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
        verify_jwt_in_request(optional=True)
        ident = get_jwt_identity()
        if ident is None:
            return None
        user_id = int(ident)
    except Exception:
        return None  # the handler's own auth decorator answers 401
    if not team_access_enabled():
        return None  # shared people already get 404 from the helpers

    if key[0] == "legacy":
        bot = Bot.query.get(key[1])
        group = Group.query.filter_by(id=key[2], bot_id=key[1]).first() if bot else None
        if not bot or not group or bot.user_id == user_id:
            return None
        gtid, owner_id = group.telegram_group_id, bot.user_id
    else:
        group = TelegramGroup.query.filter_by(telegram_group_id=key[1]).first()
        if not group or not group.owner_user_id or group.owner_user_id == user_id:
            return None
        gtid, owner_id = group.telegram_group_id, group.owner_user_id

    row = TelegramGroupAccess.query.filter_by(telegram_group_id=gtid, user_id=user_id).first()
    if not row or row.invited_by != owner_id:
        return None  # no valid grant: the handler answers 404
    if owner_only:
        return _forbid("Only the group owner can do this")
    if write and row.role == "viewer":
        return _forbid("You have view-only access to this group")
    return None


def register_group_access_guard(app):
    app.before_request(_guard_group_access)


def revoke_group_access(telegram_group_id, owner_user_id=None) -> int:
    """Drop every team grant and open access code for a chat (called when the
    owner unlinks / disconnects it, so a later relink never revives old access).

    Does not commit; the caller's commit applies it. If owner_user_id is given,
    only that owner's grants are removed (another owner's bot may share the chat).
    """
    from .models import TelegramGroupInvite
    gid = str(telegram_group_id)
    q = TelegramGroupAccess.query.filter_by(telegram_group_id=gid)
    iq = TelegramGroupInvite.query.filter_by(telegram_group_id=gid)
    if owner_user_id is not None:
        q = q.filter_by(invited_by=owner_user_id)
        iq = iq.filter_by(created_by=owner_user_id)
    n = q.delete(synchronize_session=False)
    iq.delete(synchronize_session=False)
    return n
