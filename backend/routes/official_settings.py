import logging
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy.orm.attributes import flag_modified

from ..models import db, User, TelegramGroup
from ..middleware.rate_limit import rate_limit
from .settings import _check_gated_settings, _deep_merge

logger = logging.getLogger(__name__)
official_settings_bp = Blueprint("official_settings", __name__, url_prefix="/api/official-groups")


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
