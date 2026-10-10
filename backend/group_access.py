"""Per-group dashboard access for Telegram groups.

Single source of truth for "may this user touch this group?". The owner
(TelegramGroup.owner_user_id) always may. Anyone else needs a
TelegramGroupAccess row for that exact group; viewers are read-only.

Kill switch: set GROUP_TEAM_ACCESS_ENABLED=0 to ignore every shared-access row
(owners are unaffected). Takes effect on the next request, no deploy needed.
"""
import os

from flask import jsonify, make_response, request, abort

from .models import TelegramGroup, TelegramGroupAccess

_READ_METHODS = ("GET", "HEAD", "OPTIONS")


def team_access_enabled() -> bool:
    return os.environ.get("GROUP_TEAM_ACCESS_ENABLED", "1").strip().lower() not in ("0", "false", "off", "no")


def get_access_role(user_id: int, group: TelegramGroup):
    """'owner' | 'manager' | 'viewer' | None."""
    if group.owner_user_id == user_id:
        return "owner"
    if not team_access_enabled():
        return None
    row = TelegramGroupAccess.query.filter_by(
        telegram_group_id=group.telegram_group_id, user_id=user_id
    ).first()
    return row.role if row else None


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
    return [(g, by_id[g.telegram_group_id]) for g in groups if g.owner_user_id != user_id]
