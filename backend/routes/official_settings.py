import logging
import requests as _http
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy.orm.attributes import flag_modified

from ..models import db, User, TelegramGroup, TelegramBotStarted
from ..middleware.rate_limit import rate_limit
from .settings import _check_gated_settings, _deep_merge
from ..config import Config

logger = logging.getLogger(__name__)
official_settings_bp = Blueprint("official_settings", __name__, url_prefix="/api/official-groups")

_TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"

# All permissions the bot can hold with human labels and feature mappings
_PERMISSION_DEFS = [
    ("can_delete_messages",   "Delete messages",      "AutoMod deletion"),
    ("can_restrict_members",  "Restrict / mute users","Mute & verification"),
    ("can_ban_members",       "Ban users",             "Ban actions"),
    ("can_pin_messages",      "Pin messages",          "Pinned announcements"),
    ("can_manage_topics",     "Manage topics",         "Forum/topic verification"),
    ("can_manage_chat",       "Manage chat",           "Admin rights management"),
    ("can_invite_users",      "Invite users",          "Invite link tools"),
    ("can_promote_members",   "Add admins",            "Grant admin rights"),
    ("can_change_info",       "Change group info",     "Group info updates"),
    ("is_anonymous",          "Anonymous admin",       "Anonymised actions"),
]


def _get_current_user():
    user_id = get_jwt_identity()
    return User.query.get(int(user_id))


def _get_official_group(user, group_id):
    tg = TelegramGroup.query.filter_by(
        telegram_group_id=group_id,
        owner_user_id=user.id,
    ).first()
    if not tg:
        return None, (jsonify({"error": "Group not found"}), 404)
    return tg, None


def _group_to_dict(tg):
    return {
        "id": tg.id,
        "group_name": tg.title,
        "title": tg.title,
        "telegram_group_id": tg.telegram_group_id,
        "bot_type": "official",
        "member_count": 0,
        "timezone": tg.timezone or "UTC",
        "bot_status": tg.bot_status,
        "bot_permissions": tg.bot_permissions,
    }


def _tg_api(method: str, token: str, **params):
    """Call Telegram Bot API synchronously. Returns response JSON dict."""
    url = _TELEGRAM_API.format(token=token, method=method)
    resp = _http.get(url, params=params, timeout=10)
    return resp.json()


@official_settings_bp.route("/<group_id>/settings", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def get_official_settings(group_id):
    try:
        user = _get_current_user()
        if not user:
            return jsonify({"error": "User not found"}), 404
        tg, err = _get_official_group(user, group_id)
        if err:
            return err
        return jsonify({"settings": tg.settings or {}, "group": _group_to_dict(tg)})
    except Exception as e:
        logger.error(f"get_official_settings error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@official_settings_bp.route("/<group_id>/settings", methods=["PUT"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def update_official_settings(group_id):
    try:
        user = _get_current_user()
        if not user:
            return jsonify({"error": "User not found"}), 404
        tg, err = _get_official_group(user, group_id)
        if err:
            return err
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        gated_err = _check_gated_settings(user, data)
        if gated_err:
            return gated_err
        current = dict(tg.settings or {})
        _deep_merge(current, data)
        tg.settings = current
        flag_modified(tg, "settings")
        if "timezone" in data and isinstance(data.get("timezone"), str):
            tg.timezone = data["timezone"].strip() or "UTC"
        db.session.commit()
        return jsonify({"settings": tg.settings, "timezone": tg.timezone or "UTC", "message": "Settings updated"})
    except Exception as e:
        logger.error(f"update_official_settings error: {e}", exc_info=True)
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify({"error": str(e)}), 500


@official_settings_bp.route("/<group_id>/admins", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def get_group_admins(group_id):
    """
    Fetch current Telegram admins for this group and annotate each with
    whether they have started @telegizer_bot (i.e. can receive a private DM).
    """
    try:
        user = _get_current_user()
        if not user:
            return jsonify({"error": "User not found"}), 404
        tg, err = _get_official_group(user, group_id)
        if err:
            return err

        token = Config.TELEGRAM_BOT_TOKEN
        if not token:
            return jsonify({"error": "Bot token not configured"}), 500

        result = _tg_api("getChatAdministrators", token, chat_id=group_id)
        if not result.get("ok"):
            return jsonify({"error": result.get("description", "Telegram API error"), "admins": []}), 200

        admins = []
        for member in result.get("result", []):
            u = member.get("user", {})
            uid = str(u.get("id", ""))
            can_dm = TelegramBotStarted.has_started(uid) if uid else False
            admins.append({
                "user_id": uid,
                "username": u.get("username"),
                "first_name": u.get("first_name", ""),
                "last_name": u.get("last_name", ""),
                "is_bot": bool(u.get("is_bot")),
                "status": member.get("status"),  # creator | administrator
                "can_dm": can_dm,
            })

        # Filter out bots from the selectable list
        admins = [a for a in admins if not a["is_bot"]]
        return jsonify({"admins": admins})

    except Exception as e:
        logger.error(f"get_group_admins error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@official_settings_bp.route("/<group_id>/permissions", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def get_bot_permissions(group_id):
    """
    Fetch live bot member status from Telegram and return a structured
    permissions map with human labels and related feature descriptions.
    Also updates the cached bot_permissions column on TelegramGroup.
    """
    try:
        user = _get_current_user()
        if not user:
            return jsonify({"error": "User not found"}), 404
        tg, err = _get_official_group(user, group_id)
        if err:
            return err

        token = Config.TELEGRAM_BOT_TOKEN
        if not token:
            return jsonify({"error": "Bot token not configured"}), 500

        # Get bot's own user_id first
        me_result = _tg_api("getMe", token)
        if not me_result.get("ok"):
            return jsonify({"error": "Could not fetch bot info"}), 500
        bot_id_tg = me_result["result"]["id"]

        result = _tg_api("getChatMember", token, chat_id=group_id, user_id=bot_id_tg)
        if not result.get("ok"):
            return jsonify({
                "error": result.get("description", "Bot is not a member of this group"),
                "permissions": [],
                "score": 0,
                "total": len(_PERMISSION_DEFS),
            }), 200

        member = result["result"]
        if member.get("status") not in ("administrator", "creator"):
            return jsonify({
                "error": "Bot is not an administrator — promote it to see permissions",
                "permissions": [],
                "score": 0,
                "total": len(_PERMISSION_DEFS),
            }), 200

        perms_out = []
        granted = 0
        cached = {}
        for key, label, feature in _PERMISSION_DEFS:
            has = bool(member.get(key, False))
            if has:
                granted += 1
            perms_out.append({
                "key": key,
                "label": label,
                "feature": feature,
                "granted": has,
            })
            cached[key] = has

        # Persist the refreshed permissions cache
        tg.bot_permissions = cached
        db.session.commit()

        return jsonify({
            "permissions": perms_out,
            "score": granted,
            "total": len(_PERMISSION_DEFS),
            "status": member.get("status"),
        })

    except Exception as e:
        logger.error(f"get_bot_permissions error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500
