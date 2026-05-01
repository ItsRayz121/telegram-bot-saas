import logging
from datetime import datetime
import requests as _http
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..models import db, User, Bot, Group, Member, AuditLog, ScheduledMessage, Raid, AutoResponse, ReportedMessage, TelegramBotStarted, UserTelegramAccount
from ..middleware.rate_limit import rate_limit

_PAID_TIERS = {"pro", "enterprise"}


def _require_paid(user, feature="This feature"):
    """Return a 403 response tuple if user lacks a valid paid subscription, else None."""
    if user.subscription_tier not in _PAID_TIERS:
        return (
            jsonify({
                "error": f"{feature} requires a Pro or Enterprise subscription.",
                "code": "FEATURE_REQUIRES_PRO",
                "feature": feature,
                "upgrade_url": "/pricing",
            }),
            403,
        )
    if not user.subscription_active:
        return (
            jsonify({
                "error": "Your subscription has expired. Please renew to continue using this feature.",
                "code": "SUBSCRIPTION_EXPIRED",
                "upgrade_url": "/pricing",
            }),
            403,
        )
    return None


# Top-level section keys where {"enabled": true} inside triggers the gate.
# These are the actual key names used in TelegramGroup.settings JSON.
_GATED_SECTIONS = {
    "verification",        # member join verification
    "levels",              # XP / levelling system
    "raids",               # Twitter/X raid coordinator
    "knowledge_base",      # AI knowledge base + /ask command
    "webhooks",            # incoming webhook integrations
    "scheduled_messages",  # scheduler
    "assistant",           # AI digest
}

# Direct boolean/flag keys — any truthy value means enabling.
_GATED_KEYS = {
    "advanced_automod", "extended_automod", "analytics_enabled",
    "raids_enabled", "ai_enabled", "knowledge_base_enabled",
    "digest_enabled", "scheduled_messages_enabled", "verification_enabled",
    "ai_moderation", "smart_spam_detection", "link_analysis",
    "content_classification", "advanced_filters",
}

# Enterprise-only feature keys
_ENTERPRISE_ONLY_KEYS = {
    "white_label", "custom_branding", "api_access", "priority_support",
}

# Human-readable labels for gated feature names shown in upgrade prompts
_FEATURE_LABELS = {
    "verification": "Member Verification",
    "levels": "XP & Levels System",
    "raids": "Raid Coordinator",
    "knowledge_base": "AI Knowledge Base",
    "webhooks": "Webhook Integrations",
    "scheduled_messages": "Scheduled Messages",
    "assistant": "AI Assistant / Digest",
}


def _check_gated_settings(user, incoming_data: dict, _depth: int = 0):
    """Walk the settings payload and return 403 if a free/expired user tries
    to enable any Pro-gated feature. Depth-limited to 10 to prevent DoS.

    Two gate types:
    - _GATED_SECTIONS: top-level section keys; gated when nested 'enabled' is True.
    - _GATED_KEYS: flat boolean keys; gated when the value is truthy.
    """
    if _depth > 10:
        return None

    is_paid = user.subscription_tier in _PAID_TIERS
    is_expired = is_paid and not user.subscription_active
    is_enterprise = user.subscription_tier == "enterprise" and not is_expired

    def _403_pro(key):
        label = _FEATURE_LABELS.get(key, key)
        return (
            jsonify({
                "error": f"{label} requires a Pro or Enterprise subscription.",
                "code": "FEATURE_REQUIRES_PRO",
                "feature": key,
                "feature_label": label,
                "upgrade_url": "/pricing",
            }),
            403,
        )

    def _403_enterprise(key):
        label = _FEATURE_LABELS.get(key, key)
        return (
            jsonify({
                "error": f"{label} requires an Enterprise subscription.",
                "code": "FEATURE_REQUIRES_ENTERPRISE",
                "feature": key,
                "feature_label": label,
                "upgrade_url": "/pricing",
            }),
            403,
        )

    if is_paid and not is_expired:
        # Active paid user — only block enterprise-only keys for non-enterprise
        if not is_enterprise:
            for key, value in incoming_data.items():
                if key in _ENTERPRISE_ONLY_KEYS and value:
                    return _403_enterprise(key)
                if isinstance(value, dict):
                    err = _check_gated_settings(user, value, _depth + 1)
                    if err:
                        return err
        return None

    # Free or expired — gate both section enablement and direct flag keys
    for key, value in incoming_data.items():
        # Section gate: {"verification": {"enabled": true, ...}}
        if key in _GATED_SECTIONS and isinstance(value, dict) and value.get("enabled"):
            return _403_pro(key)
        # Direct key gate: {"raids_enabled": true}
        if key in _GATED_KEYS and value:
            return _403_pro(key)
        # Enterprise keys
        if key in _ENTERPRISE_ONLY_KEYS and value:
            return _403_enterprise(key)
        # Recurse into nested dicts
        if isinstance(value, dict):
            err = _check_gated_settings(user, value, _depth + 1)
            if err:
                return err
    return None

logger = logging.getLogger(__name__)
settings_bp = Blueprint("settings", __name__, url_prefix="/api")


def _deep_merge(base: dict, override: dict):
    """Recursively merge override into base in-place, preserving nested dicts."""
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def _get_current_user():
    user_id = get_jwt_identity()
    return User.query.get(int(user_id))


def _get_bot_and_group(user, bot_id, group_id):
    bot = Bot.query.filter_by(id=bot_id, user_id=user.id).first()
    if not bot:
        return None, None, (jsonify({"error": "Bot not found"}), 404)
    group = Group.query.filter_by(id=group_id, bot_id=bot.id).first()
    if not group:
        return bot, None, (jsonify({"error": "Group not found"}), 404)
    return bot, group, None


@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/settings", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def get_group_settings(bot_id, group_id):
    try:
        user = _get_current_user()
        if not user:
            return jsonify({"error": "User not found"}), 404
        bot, group, err = _get_bot_and_group(user, bot_id, group_id)
        if err:
            return err
        return jsonify({"settings": group.settings, "group": group.to_dict()})
    except Exception as e:
        logger.error(f"get_group_settings error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/settings", methods=["PUT"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def update_group_settings(bot_id, group_id):
    try:
        user = _get_current_user()
        if not user:
            return jsonify({"error": "User not found"}), 404
        bot, group, err = _get_bot_and_group(user, bot_id, group_id)
        if err:
            return err
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        gated_err = _check_gated_settings(user, data)
        if gated_err:
            return gated_err
        current = dict(group.settings or {})
        _deep_merge(current, data)
        group.settings = current
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(group, "settings")
        # Keep the dedicated timezone column in sync so it's queryable directly.
        if "timezone" in data and isinstance(data.get("timezone"), str):
            group.timezone = data["timezone"].strip() or "UTC"
        db.session.commit()
        return jsonify({"settings": group.settings, "timezone": group.timezone or "UTC", "message": "Settings updated"})
    except Exception as e:
        logger.error(f"update_group_settings error: {e}", exc_info=True)
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify({"error": str(e)}), 500


@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/admins", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def get_group_admins(bot_id, group_id):
    """Fetch current Telegram admins and annotate with @telegizer_bot DM ability."""
    try:
        user = _get_current_user()
        if not user:
            return jsonify({"error": "User not found"}), 404
        bot, group, err = _get_bot_and_group(user, bot_id, group_id)
        if err:
            return err

        try:
            token = bot.get_token()
        except Exception:
            return jsonify({"error": "Could not decrypt bot token"}), 500

        resp = _http.get(
            f"https://api.telegram.org/bot{token}/getChatAdministrators",
            params={"chat_id": group.telegram_group_id},
            timeout=10,
        ).json()

        if not resp.get("ok"):
            return jsonify({"error": resp.get("description", "Telegram API error"), "admins": []}), 200

        admins = []
        for member in resp.get("result", []):
            u = member.get("user", {})
            uid = str(u.get("id", ""))
            if u.get("is_bot"):
                continue
            admins.append({
                "user_id": uid,
                "username": u.get("username"),
                "first_name": u.get("first_name", ""),
                "status": member.get("status"),
                "can_dm": TelegramBotStarted.has_started(uid) if uid else False,
            })
        return jsonify({"admins": admins})
    except Exception as e:
        logger.error(f"get_group_admins error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/members", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def get_members(bot_id, group_id):
    try:
        user = _get_current_user()
        if not user:
            return jsonify({"error": "User not found"}), 404
        bot, group, err = _get_bot_and_group(user, bot_id, group_id)
        if err:
            return err
        page = request.args.get("page", 1, type=int)
        per_page = min(request.args.get("per_page", 50, type=int), 100)
        search = request.args.get("search", "")
        query = Member.query.filter_by(group_id=group.id)
        if search:
            query = query.filter(
                (Member.username.ilike(f"%{search}%")) |
                (Member.first_name.ilike(f"%{search}%"))
            )
        query = query.order_by(Member.xp.desc())
        paginated = query.paginate(page=page, per_page=per_page, error_out=False)
        return jsonify({
            "members": [m.to_dict() for m in paginated.items],
            "total": paginated.total,
            "pages": paginated.pages,
            "page": page,
            "per_page": per_page,
        })
    except Exception as e:
        logger.error(f"get_members error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/audit-logs", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def get_audit_logs(bot_id, group_id):
    try:
        user = _get_current_user()
        if not user:
            return jsonify({"error": "User not found"}), 404
        bot, group, err = _get_bot_and_group(user, bot_id, group_id)
        if err:
            return err
        page = request.args.get("page", 1, type=int)
        per_page = min(request.args.get("per_page", 50, type=int), 100)
        action_type = request.args.get("action_type", "")
        query = AuditLog.query.filter_by(group_id=group.id)
        if action_type:
            query = query.filter_by(action_type=action_type)
        query = query.order_by(AuditLog.timestamp.desc())
        paginated = query.paginate(page=page, per_page=per_page, error_out=False)
        return jsonify({
            "logs": [log.to_dict() for log in paginated.items],
            "total": paginated.total,
            "pages": paginated.pages,
            "page": page,
            "per_page": per_page,
        })
    except Exception as e:
        logger.error(f"get_audit_logs error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/scheduled-messages", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def get_scheduled_messages(bot_id, group_id):
    try:
        user = _get_current_user()
        if not user:
            return jsonify({"error": "User not found"}), 404
        bot, group, err = _get_bot_and_group(user, bot_id, group_id)
        if err:
            return err
        messages = ScheduledMessage.query.filter_by(group_id=group.id).order_by(ScheduledMessage.send_at).all()
        return jsonify({"scheduled_messages": [m.to_dict() for m in messages]})
    except Exception as e:
        logger.error(f"get_scheduled_messages error for group {group_id}: {e}", exc_info=True)
        return jsonify({"error": f"Failed to load scheduled messages: {str(e)}"}), 500


@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/scheduled-messages", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def create_scheduled_message(bot_id, group_id):
    try:
        user = _get_current_user()
        if not user:
            return jsonify({"error": "User not found"}), 404
        bot, group, err = _get_bot_and_group(user, bot_id, group_id)
        if err:
            return err
        sub_err = _require_paid(user, "Scheduled messages")
        if sub_err:
            return sub_err
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        required = ["title", "message_text", "send_at"]
        for field in required:
            if not data.get(field):
                return jsonify({"error": f"{field} is required"}), 400
        # Authoritative source: groups.timezone column, then settings JSON fallback.
        group_default_tz = (
            group.timezone
            or (group.settings or {}).get("timezone", "UTC")
            or "UTC"
        )
        tz_name = (data.get("timezone") or group_default_tz).strip() or "UTC"

        def _parse_dt_tz(s, tz=tz_name):
            """Convert a datetime string to a naive UTC datetime.

            If the string already carries a UTC offset (ISO 8601 with Z or +HH:MM)
            it is converted directly to UTC.  Otherwise the string is treated as
            local time in *tz* and converted accordingly.
            """
            from zoneinfo import ZoneInfo
            s = str(s).strip()
            has_tz_info = s.endswith("Z") or (
                "T" in s and ("+" in s[10:] or s.count("-") > 2)
            )
            if has_tz_info:
                s = s.replace("Z", "+00:00")
                if len(s) == 16:
                    s += ":00"
                dt = datetime.fromisoformat(s)
                if dt.tzinfo is not None:
                    from datetime import timezone as _stdtz
                    dt = dt.astimezone(_stdtz.utc).replace(tzinfo=None)
                return dt
            # Plain local datetime — apply given timezone
            if len(s) == 16:
                s += ":00"
            try:
                zone = ZoneInfo(tz)
            except Exception:
                zone = ZoneInfo("UTC")
            local_dt = datetime.fromisoformat(s).replace(tzinfo=zone)
            return local_dt.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

        try:
            send_at = _parse_dt_tz(data["send_at"])
        except ValueError:
            return jsonify({"error": "Invalid send_at format"}), 400
        stop_date = None
        if data.get("stop_date"):
            try:
                stop_date = _parse_dt_tz(data["stop_date"])
            except ValueError:
                return jsonify({"error": "Invalid stop_date format"}), 400
        _repeat = data.get("repeat_interval")
        if _repeat is not None:
            try:
                _repeat = int(_repeat)
                if _repeat < 60:
                    return jsonify({"error": "repeat_interval must be at least 60 minutes"}), 400
                if _repeat > 525600:
                    return jsonify({"error": "repeat_interval must be at most 525600 minutes (1 year)"}), 400
            except (TypeError, ValueError):
                return jsonify({"error": "repeat_interval must be an integer (minutes)"}), 400
        msg = ScheduledMessage(
            group_id=group.id,
            title=data["title"],
            message_text=data["message_text"],
            media_url=data.get("media_url"),
            buttons=data.get("buttons"),
            send_at=send_at,
            repeat_interval=_repeat,
            stop_date=stop_date,
            pin_message=data.get("pin_message", False),
            auto_delete_after=data.get("auto_delete_after"),
            link_preview_enabled=data.get("link_preview_enabled", True),
            topic_id=data.get("topic_id"),
            timezone=tz_name,
        )
        db.session.add(msg)
        db.session.commit()
        return jsonify({"scheduled_message": msg.to_dict(), "message": "Scheduled message created"}), 201
    except Exception as e:
        logger.error(f"create_scheduled_message error for group {group_id}: {e}", exc_info=True)
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify({"error": str(e)}), 500


@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/scheduled-messages/<int:msg_id>", methods=["DELETE"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def delete_scheduled_message(bot_id, group_id, msg_id):
    try:
        user = _get_current_user()
        if not user:
            return jsonify({"error": "User not found"}), 404
        bot, group, err = _get_bot_and_group(user, bot_id, group_id)
        if err:
            return err
        msg = ScheduledMessage.query.filter_by(id=msg_id, group_id=group.id).first()
        if not msg:
            return jsonify({"error": "Scheduled message not found"}), 404
        db.session.delete(msg)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"delete_scheduled_message error: {e}", exc_info=True)
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify({"error": str(e)}), 500


@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/raids", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=5)
def create_raid(bot_id, group_id):
    try:
        user = _get_current_user()
        if not user:
            return jsonify({"error": "User not found"}), 404
        bot, group, err = _get_bot_and_group(user, bot_id, group_id)
        if err:
            return err
        if user.subscription_tier == "free":
            return jsonify({"error": "Raids require a Pro or Enterprise subscription"}), 403
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        if not data.get("tweet_url"):
            return jsonify({"error": "tweet_url is required"}), 400
        duration_hours = data.get("duration_hours", 24)
        from datetime import timedelta
        ends_at = datetime.utcnow().replace(microsecond=0) + timedelta(hours=duration_hours)
        raid = Raid(
            group_id=group.id,
            tweet_url=data["tweet_url"],
            goals=data.get("goals", {}),
            duration_hours=duration_hours,
            xp_reward=data.get("xp_reward", 100),
            pin_message=data.get("pin_message", True),
            reminders_enabled=data.get("reminders_enabled", True),
            is_active=True,
            ends_at=ends_at,
            participants={},
        )
        db.session.add(raid)
        db.session.commit()
        return jsonify({"raid": raid.to_dict(), "message": "Raid created"}), 201
    except Exception as e:
        logger.error(f"create_raid error: {e}", exc_info=True)
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify({"error": str(e)}), 500


# ── Auto-Responses ──────────────────────────────────────────────────────────

@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/auto-responses", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def get_auto_responses(bot_id, group_id):
    try:
        user = _get_current_user()
        if not user:
            return jsonify({"error": "User not found"}), 404
        bot, group, err = _get_bot_and_group(user, bot_id, group_id)
        if err:
            return err
        responses = AutoResponse.query.filter_by(group_id=group.id).order_by(AutoResponse.created_at).all()
        return jsonify({"auto_responses": [r.to_dict() for r in responses]})
    except Exception as e:
        logger.error(f"get_auto_responses error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/auto-responses", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def create_auto_response(bot_id, group_id):
    try:
        user = _get_current_user()
        if not user:
            return jsonify({"error": "User not found"}), 404
        bot, group, err = _get_bot_and_group(user, bot_id, group_id)
        if err:
            return err
        data = request.get_json()
        if not data or not data.get("trigger_text") or not data.get("response_text"):
            return jsonify({"error": "trigger_text and response_text are required"}), 400
        ar = AutoResponse(
            group_id=group.id,
            trigger_text=data["trigger_text"],
            response_text=data["response_text"],
            match_type=data.get("match_type", "contains"),
            is_case_sensitive=data.get("is_case_sensitive", False),
            is_enabled=data.get("is_enabled", True),
        )
        db.session.add(ar)
        db.session.commit()
        return jsonify({"auto_response": ar.to_dict(), "message": "Auto-response created"}), 201
    except Exception as e:
        logger.error(f"create_auto_response error: {e}", exc_info=True)
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify({"error": str(e)}), 500


@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/auto-responses/<int:ar_id>", methods=["PUT"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def update_auto_response(bot_id, group_id, ar_id):
    try:
        user = _get_current_user()
        if not user:
            return jsonify({"error": "User not found"}), 404
        bot, group, err = _get_bot_and_group(user, bot_id, group_id)
        if err:
            return err
        ar = AutoResponse.query.filter_by(id=ar_id, group_id=group.id).first()
        if not ar:
            return jsonify({"error": "Auto-response not found"}), 404
        data = request.get_json() or {}
        if "trigger_text" in data:
            ar.trigger_text = data["trigger_text"]
        if "response_text" in data:
            ar.response_text = data["response_text"]
        if "match_type" in data:
            ar.match_type = data["match_type"]
        if "is_case_sensitive" in data:
            ar.is_case_sensitive = data["is_case_sensitive"]
        if "is_enabled" in data:
            ar.is_enabled = data["is_enabled"]
        db.session.commit()
        return jsonify({"auto_response": ar.to_dict(), "message": "Updated"})
    except Exception as e:
        logger.error(f"update_auto_response error: {e}", exc_info=True)
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify({"error": str(e)}), 500


@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/auto-responses/<int:ar_id>", methods=["DELETE"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def delete_auto_response(bot_id, group_id, ar_id):
    try:
        user = _get_current_user()
        if not user:
            return jsonify({"error": "User not found"}), 404
        bot, group, err = _get_bot_and_group(user, bot_id, group_id)
        if err:
            return err
        ar = AutoResponse.query.filter_by(id=ar_id, group_id=group.id).first()
        if not ar:
            return jsonify({"error": "Auto-response not found"}), 404
        db.session.delete(ar)
        db.session.commit()
        return jsonify({"message": "Deleted"})
    except Exception as e:
        logger.error(f"delete_auto_response error: {e}", exc_info=True)
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify({"error": str(e)}), 500


# ── Reports ─────────────────────────────────────────────────────────────────

@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/reports", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def get_reports(bot_id, group_id):
    try:
        user = _get_current_user()
        if not user:
            return jsonify({"error": "User not found"}), 404
        bot, group, err = _get_bot_and_group(user, bot_id, group_id)
        if err:
            return err
        status_filter = request.args.get("status", "")
        query = ReportedMessage.query.filter_by(group_id=group.id)
        if status_filter:
            query = query.filter_by(status=status_filter)
        reports = query.order_by(ReportedMessage.created_at.desc()).all()
        return jsonify({"reports": [r.to_dict() for r in reports]})
    except Exception as e:
        logger.error(f"get_reports error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/reports/<int:report_id>/resolve", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def resolve_report(bot_id, group_id, report_id):
    try:
        user = _get_current_user()
        if not user:
            return jsonify({"error": "User not found"}), 404
        bot, group, err = _get_bot_and_group(user, bot_id, group_id)
        if err:
            return err
        report = ReportedMessage.query.filter_by(id=report_id, group_id=group.id).first()
        if not report:
            return jsonify({"error": "Report not found"}), 404
        report.status = "resolved"
        db.session.commit()
        return jsonify({"report": report.to_dict(), "message": "Report resolved"})
    except Exception as e:
        logger.error(f"resolve_report error: {e}", exc_info=True)
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify({"error": str(e)}), 500


# ── Linked Telegram Accounts ─────────────────────────────────────────────────

logger = logging.getLogger(__name__)


@settings_bp.route("/account/telegram-accounts", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def list_telegram_accounts():
    """List all Telegram accounts linked to the current user."""
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    accounts = UserTelegramAccount.query.filter_by(user_id=user_id).order_by(
        UserTelegramAccount.is_primary.desc(), UserTelegramAccount.linked_at
    ).all()
    # Also surface the legacy primary account stored directly on the User model
    # if it hasn't been migrated to the junction table yet.
    primary_ids = {a.telegram_user_id for a in accounts}
    legacy = []
    if user.telegram_user_id and user.telegram_user_id not in primary_ids:
        legacy = [{
            "id": None,
            "telegram_user_id": user.telegram_user_id,
            "telegram_username": user.telegram_username,
            "telegram_first_name": user.telegram_first_name,
            "is_primary": True,
            "linked_at": user.telegram_connected_at.isoformat() if user.telegram_connected_at else None,
        }]
    return jsonify({"accounts": legacy + [a.to_dict() for a in accounts]})


@settings_bp.route("/account/telegram-accounts", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def add_telegram_account():
    """Link an additional Telegram account.

    The official bot sends a /connect command that POSTs the Telegram user ID
    here after verifying the user's one-time token. The frontend also calls this
    directly when the bot confirms the link via the deep-link flow.
    """
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json(silent=True) or {}
    tg_id = str(data.get("telegram_user_id", "")).strip()
    tg_username = data.get("telegram_username", "")
    tg_first_name = data.get("telegram_first_name", "")

    if not tg_id:
        return jsonify({"error": "telegram_user_id is required"}), 400

    # Check if this Telegram ID is already linked to another user account
    existing_user = User.query.filter_by(telegram_user_id=tg_id).first()
    if existing_user and existing_user.id != user_id:
        return jsonify({"error": "This Telegram account is already linked to a different user"}), 409

    existing_linked = UserTelegramAccount.query.filter_by(telegram_user_id=tg_id).first()
    if existing_linked and existing_linked.user_id != user_id:
        return jsonify({"error": "This Telegram account is already linked to a different user"}), 409
    if existing_linked and existing_linked.user_id == user_id:
        return jsonify({"account": existing_linked.to_dict(), "message": "Already linked"}), 200

    # Count existing linked accounts — cap at reasonable limit to prevent abuse
    count = UserTelegramAccount.query.filter_by(user_id=user_id).count()
    if user.telegram_user_id:
        count += 1  # include legacy primary
    if count >= 10:
        return jsonify({"error": "Maximum 10 Telegram accounts per user"}), 400

    is_primary = not bool(user.telegram_user_id) and count == 0
    account = UserTelegramAccount(
        user_id=user_id,
        telegram_user_id=tg_id,
        telegram_username=tg_username,
        telegram_first_name=tg_first_name,
        is_primary=is_primary,
    )
    db.session.add(account)

    # Backfill the legacy primary columns on first link
    if is_primary and not user.telegram_user_id:
        user.telegram_user_id = tg_id
        user.telegram_username = tg_username
        user.telegram_first_name = tg_first_name
        user.telegram_connected_at = datetime.utcnow()

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.error("add_telegram_account error: %s", exc)
        return jsonify({"error": "Could not link account"}), 500

    return jsonify({"account": account.to_dict(), "message": "Telegram account linked"}), 201


@settings_bp.route("/account/telegram-accounts/<int:account_id>", methods=["DELETE"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def remove_telegram_account(account_id):
    """Unlink a Telegram account from the current user."""
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    account = UserTelegramAccount.query.filter_by(id=account_id, user_id=user_id).first()
    if not account:
        return jsonify({"error": "Account not found"}), 404

    was_primary = account.is_primary
    db.session.delete(account)

    if was_primary:
        # Promote the next linked account to primary
        next_acct = UserTelegramAccount.query.filter_by(user_id=user_id).order_by(
            UserTelegramAccount.linked_at
        ).first()
        if next_acct:
            next_acct.is_primary = True
            user.telegram_user_id = next_acct.telegram_user_id
            user.telegram_username = next_acct.telegram_username
            user.telegram_first_name = next_acct.telegram_first_name
        else:
            user.telegram_user_id = None
            user.telegram_username = None
            user.telegram_first_name = None
            user.telegram_connected_at = None

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.error("remove_telegram_account error: %s", exc)
        return jsonify({"error": "Could not unlink account"}), 500

    return jsonify({"message": "Telegram account unlinked"})


@settings_bp.route("/account/telegram-accounts/<int:account_id>/set-primary", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def set_primary_telegram_account(account_id):
    """Set a linked Telegram account as the primary one."""
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    account = UserTelegramAccount.query.filter_by(id=account_id, user_id=user_id).first()
    if not account:
        return jsonify({"error": "Account not found"}), 404

    # Demote current primary
    UserTelegramAccount.query.filter_by(user_id=user_id, is_primary=True).update({"is_primary": False})
    account.is_primary = True
    user.telegram_user_id = account.telegram_user_id
    user.telegram_username = account.telegram_username
    user.telegram_first_name = account.telegram_first_name

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.error("set_primary_telegram_account error: %s", exc)
        return jsonify({"error": "Could not update primary account"}), 500

    return jsonify({"account": account.to_dict(), "message": "Primary account updated"})
