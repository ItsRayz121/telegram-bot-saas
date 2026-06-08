import logging
from datetime import datetime
import requests as _http
from flask import Blueprint, request, jsonify, Response
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..models import db, User, Bot, Group, Member, AuditLog, ScheduledMessage, Raid, AutoResponse, ReportedMessage, TelegramBotStarted, UserTelegramAccount, EscalationEvent
from ..middleware.rate_limit import rate_limit
from .. import engagement as eng

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
        # Annotate escalation admin DM eligibility (has the admin started the bot?)
        escalation_dm_status = {}
        try:
            admin_ids = (group.settings or {}).get("escalation", {}).get("admins", [])
            for admin_id in admin_ids:
                if admin_id:
                    started = TelegramBotStarted.query.filter_by(
                        telegram_user_id=str(admin_id).lstrip("@")
                    ).first()
                    escalation_dm_status[str(admin_id)] = started is not None
        except Exception:
            pass
        return jsonify({"settings": group.settings, "group": group.to_dict(), "escalation_dm_status": escalation_dm_status})
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
        search = request.args.get("q", "") or request.args.get("search", "")
        role_filter = request.args.get("role", "")
        is_verified = request.args.get("is_verified", "")
        has_wallet = request.args.get("has_wallet", "")
        has_warnings = request.args.get("has_warnings", "")
        is_muted = request.args.get("is_muted", "")
        sort_by = request.args.get("sort_by", "xp")
        sort_dir = request.args.get("sort_dir", "desc")
        period = request.args.get("period", "all")

        # When sorting by XP and a time period is set, sort by the period column instead
        _period_col_names = {"1d": "xp_1d", "7d": "xp_7d", "30d": "xp_30d"}
        if period != "all" and sort_by == "xp":
            sort_by = _period_col_names.get(period, "xp")

        query = Member.query.filter_by(group_id=group.id)
        if search:
            query = query.filter(
                (Member.username.ilike(f"%{search}%")) |
                (Member.first_name.ilike(f"%{search}%"))
            )
        if role_filter:
            query = query.filter(Member.role == role_filter)
        if is_verified:
            query = query.filter(Member.is_verified == (is_verified.lower() == "true"))
        if has_wallet:
            if has_wallet.lower() == "true":
                query = query.filter(Member.wallet_address.isnot(None), Member.wallet_address != "")
            else:
                query = query.filter(
                    (Member.wallet_address.is_(None)) | (Member.wallet_address == "")
                )
        if has_warnings:
            if has_warnings.lower() == "true":
                query = query.filter(Member.warnings > 0)
        if is_muted:
            query = query.filter(Member.is_muted == (is_muted.lower() == "true"))

        _sort_map = {
            "xp": Member.xp, "level": Member.level, "first_name": Member.first_name,
            "joined_at": Member.joined_at, "warnings": Member.warnings, "role": Member.role,
            "is_verified": Member.is_verified, "wallet_address": Member.wallet_address,
            "xp_1d": Member.xp_1d, "xp_7d": Member.xp_7d, "xp_30d": Member.xp_30d,
        }
        sort_col = _sort_map.get(sort_by, Member.xp)
        query = query.order_by(sort_col.desc() if sort_dir == "desc" else sort_col.asc())
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


@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/ai-activity", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def get_custom_ai_activity(bot_id, group_id):
    """AI Activity metrics + timeline for a custom-bot group."""
    try:
        user = _get_current_user()
        if not user:
            return jsonify({"error": "User not found"}), 404
        bot, group, err = _get_bot_and_group(user, bot_id, group_id)
        if err:
            return err
        from ..ai_activity import activity_summary
        page = request.args.get("page", 1, type=int)
        category = request.args.get("category") or None
        return jsonify(activity_summary("custom", group.id, page=page, category=category))
    except Exception as e:
        logger.error(f"get_custom_ai_activity error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/ai-status", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def get_custom_ai_status(bot_id, group_id):
    """AI Status panel for a custom-bot group."""
    try:
        user = _get_current_user()
        if not user:
            return jsonify({"error": "User not found"}), 404
        bot, group, err = _get_bot_and_group(user, bot_id, group_id)
        if err:
            return err
        from ..ai_activity import ai_status
        from ..models import KnowledgeDocument, WebhookIntegration, UserApiKey
        from ..config import Config

        s = group.settings or {}
        smart = s.get("smart_mod", {}) or {}
        moderation_enabled = bool(
            smart.get("enabled") or s.get("ai_moderation") or s.get("smart_spam_detection")
        )
        integrations_connected = WebhookIntegration.query.filter_by(
            group_id=group.id, is_active=True
        ).first() is not None
        kb_configured = KnowledgeDocument.query.filter_by(group_id=group.id).first() is not None
        provider_connected = bool(Config.OPENAI_API_KEY) or UserApiKey.query.filter_by(
            user_id=user.id, is_active=True
        ).first() is not None
        return jsonify(ai_status(
            "custom", group.id,
            moderation_enabled=moderation_enabled,
            integrations_connected=integrations_connected,
            kb_configured=kb_configured,
            provider_connected=provider_connected,
        ))
    except Exception as e:
        logger.error(f"get_custom_ai_status error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/forum-topics", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def get_custom_bot_forum_topics(bot_id, group_id):
    """Return cached forum topics for a custom-bot group."""
    try:
        user = _get_current_user()
        if not user:
            return jsonify({"error": "User not found"}), 404
        bot, group, err = _get_bot_and_group(user, bot_id, group_id)
        if err:
            return err
        from ..models import GroupForumTopic
        topics = (
            GroupForumTopic.query
            .filter_by(telegram_group_id=str(group.telegram_group_id))
            .order_by(GroupForumTopic.name)
            .all()
        )
        return jsonify({"topics": [t.to_dict() for t in topics]})
    except Exception as e:
        logger.error(f"get_custom_bot_forum_topics error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/leaderboard", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def get_custom_bot_leaderboard(bot_id, group_id):
    """XP leaderboard for custom-bot groups (reads from Member table, not OfficialMember)."""
    try:
        user = _get_current_user()
        if not user:
            return jsonify({"error": "User not found"}), 404
        bot, group, err = _get_bot_and_group(user, bot_id, group_id)
        if err:
            return err
        limit = min(request.args.get("limit", 20, type=int), 100)
        period = request.args.get("period", "all")
        has_wallet_filter = request.args.get("has_wallet")

        period_col_map = {
            "1d": Member.xp_1d,
            "7d": Member.xp_7d,
            "30d": Member.xp_30d,
        }
        sort_col = period_col_map.get(period, Member.xp)

        members_q = Member.query.filter_by(group_id=group.id)
        if period != "all":
            members_q = members_q.filter(sort_col > 0)
        if has_wallet_filter == "true":
            members_q = members_q.filter(
                Member.wallet_address.isnot(None),
                Member.wallet_address != "",
            )
        members = members_q.order_by(sort_col.desc()).limit(limit).all()
        return jsonify({"members": [m.to_dict() for m in members]})
    except Exception as e:
        logger.error(f"get_custom_bot_leaderboard error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/warnings", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def get_custom_bot_warnings(bot_id, group_id):
    """Active warnings for custom-bot groups (reads warn entries from AuditLog)."""
    try:
        user = _get_current_user()
        if not user:
            return jsonify({"error": "User not found"}), 404
        bot, group, err = _get_bot_and_group(user, bot_id, group_id)
        if err:
            return err
        target_user_id = request.args.get("user_id")
        q = AuditLog.query.filter_by(group_id=group.id, action_type="warn")
        if target_user_id:
            q = q.filter_by(target_user_id=str(target_user_id))
        logs = q.order_by(AuditLog.timestamp.desc()).limit(200).all()
        # Shape into the same structure the frontend expects from OfficialWarning
        warnings = [
            {
                "id": log.id,
                "telegram_group_id": str(group.telegram_group_id),
                "target_user_id": log.target_user_id,
                "target_username": log.target_username,
                "moderator_user_id": log.moderator_id,
                "moderator_username": log.moderator_username,
                "reason": log.reason,
                "message_text": (log.extra_data or {}).get("message_text"),
                "active": True,
                "created_at": log.timestamp.isoformat(),
                "total_warnings": (log.extra_data or {}).get("total_warnings"),
            }
            for log in logs
        ]
        return jsonify({"warnings": warnings})
    except Exception as e:
        logger.error(f"get_custom_bot_warnings error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/warnings/<int:warning_id>", methods=["DELETE"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def delete_custom_bot_warning(bot_id, group_id, warning_id):
    try:
        user = _get_current_user()
        if not user:
            return jsonify({"error": "User not found"}), 404
        bot, group, err = _get_bot_and_group(user, bot_id, group_id)
        if err:
            return err
        log = AuditLog.query.filter_by(id=warning_id, group_id=group.id, action_type="warn").first_or_404()
        member = Member.query.filter_by(
            group_id=group.id,
            telegram_user_id=str(log.target_user_id),
        ).first()
        if member and (member.warnings or 0) > 0:
            member.warnings -= 1
        db.session.delete(log)
        db.session.commit()
        return jsonify({"message": "Warning removed"}), 200
    except Exception as e:
        logger.error(f"delete_custom_bot_warning error: {e}", exc_info=True)
        db.session.rollback()
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


# ── Engagement Campaigns (custom-bot lineage) ────────────────────────────────
# Thin wrappers — all logic lives in backend/engagement.py so the official-bot
# lineage (routes/telegram_groups.py) shares identical behavior.

def _eng_err(e: "eng.EngagementError"):
    body, status = e.to_response()
    return jsonify(body), status


@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/campaigns", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def list_engagement_campaigns(bot_id, group_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    _, group, err = _get_bot_and_group(user, bot_id, group_id)
    if err:
        return err
    campaigns = eng.list_campaigns("custom", group_id=group.id, status=request.args.get("status"))
    return jsonify({"campaigns": campaigns})


@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/campaigns", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=15)
def create_engagement_campaign(bot_id, group_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    _, group, err = _get_bot_and_group(user, bot_id, group_id)
    if err:
        return err
    try:
        campaign = eng.create_campaign(
            user, request.get_json() or {},
            scope="custom", owner_user_id=user.id, group_id=group.id,
        )
        return jsonify({"campaign": campaign.to_dict(include_analytics=True)}), 201
    except eng.EngagementError as e:
        db.session.rollback()
        return _eng_err(e)
    except Exception as e:
        logger.error(f"create_engagement_campaign error: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({"error": "Failed to create campaign"}), 500


@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/campaigns/<int:campaign_id>", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def get_engagement_campaign(bot_id, group_id, campaign_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    _, group, err = _get_bot_and_group(user, bot_id, group_id)
    if err:
        return err
    try:
        c = eng.get_campaign(campaign_id, "custom", group_id=group.id)
        return jsonify({"campaign": c.to_dict(include_analytics=True)})
    except eng.EngagementError as e:
        return _eng_err(e)


@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/campaigns/<int:campaign_id>", methods=["PATCH"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def update_engagement_campaign(bot_id, group_id, campaign_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    _, group, err = _get_bot_and_group(user, bot_id, group_id)
    if err:
        return err
    try:
        c = eng.get_campaign(campaign_id, "custom", group_id=group.id)
        c = eng.update_campaign(c, request.get_json() or {}, user=user)
        return jsonify({"campaign": c.to_dict(include_analytics=True)})
    except eng.EngagementError as e:
        db.session.rollback()
        return _eng_err(e)
    except Exception as e:
        logger.error(f"update_engagement_campaign error: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({"error": "Failed to update campaign"}), 500


@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/campaigns/<int:campaign_id>/post", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=15)
def post_engagement_campaign(bot_id, group_id, campaign_id):
    """Manually (re)post the campaign announcement to the group (retry action)."""
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    _, group, err = _get_bot_and_group(user, bot_id, group_id)
    if err:
        return err
    try:
        c = eng.get_campaign(campaign_id, "custom", group_id=group.id)
        c = eng.repost_campaign(c)
        return jsonify({"campaign": c.to_dict(include_analytics=True)})
    except eng.EngagementError as e:
        db.session.rollback()
        return _eng_err(e)
    except Exception as e:
        logger.error(f"post_engagement_campaign error: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({"error": "Failed to post campaign"}), 500


@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/campaigns/<int:campaign_id>/submissions", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def list_engagement_submissions(bot_id, group_id, campaign_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    _, group, err = _get_bot_and_group(user, bot_id, group_id)
    if err:
        return err
    try:
        c = eng.get_campaign(campaign_id, "custom", group_id=group.id)
        return jsonify({"submissions": eng.list_submissions(c, status=request.args.get("status"))})
    except eng.EngagementError as e:
        return _eng_err(e)


@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/campaigns/<int:campaign_id>/submissions/<int:submission_id>/review", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def review_engagement_submission(bot_id, group_id, campaign_id, submission_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    _, group, err = _get_bot_and_group(user, bot_id, group_id)
    if err:
        return err
    data = request.get_json() or {}
    try:
        c = eng.get_campaign(campaign_id, "custom", group_id=group.id)
        sub = eng.review_submission(
            c, submission_id, data.get("action"),
            reviewed_by=user.id, reason=data.get("reason"),
        )
        return jsonify({"submission": sub.to_dict()})
    except eng.EngagementError as e:
        db.session.rollback()
        return _eng_err(e)


@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/member-submissions/<tg_user_id>", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def member_submission_history_custom(bot_id, group_id, tg_user_id):
    """All campaign submissions by one member in this group (submission history)."""
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    _, group, err = _get_bot_and_group(user, bot_id, group_id)
    if err:
        return err
    subs = eng.list_user_submissions("custom", tg_user_id, group_id=group.id)
    return jsonify({"submissions": subs})


@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/campaigns/<int:campaign_id>/leaderboard", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def engagement_campaign_leaderboard(bot_id, group_id, campaign_id):
    """Ranked participant board for a campaign (premium — gated on owner plan)."""
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    _, group, err = _get_bot_and_group(user, bot_id, group_id)
    if err:
        return err
    try:
        c = eng.get_campaign(campaign_id, "custom", group_id=group.id)
        return jsonify(eng.campaign_leaderboard(
            c,
            limit=request.args.get("limit", eng.LEADERBOARD_DEFAULT_LIMIT),
            offset=request.args.get("offset", 0),
        ))
    except eng.EngagementError as e:
        return _eng_err(e)


@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/campaigns/<int:campaign_id>/submissions/export", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def export_engagement_submissions(bot_id, group_id, campaign_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    _, group, err = _get_bot_and_group(user, bot_id, group_id)
    if err:
        return err
    try:
        c = eng.get_campaign(campaign_id, "custom", group_id=group.id)
        csv_text = eng.submissions_csv(c)
        return Response(
            csv_text, mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename=campaign_{c.id}_submissions.csv"},
        )
    except eng.EngagementError as e:
        return _eng_err(e)


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
        if "use_as_ai_knowledge" in data:
            ar.use_as_ai_knowledge = bool(data["use_as_ai_knowledge"])
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

    # Demote current primary, promote selected account — do NOT overwrite User.telegram_user_id
    # (that legacy field is only used as a fallback; multi-account lookup goes via UserTelegramAccount)
    UserTelegramAccount.query.filter_by(user_id=user_id, is_primary=True).update({"is_primary": False})
    account.is_primary = True

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.error("set_primary_telegram_account error: %s", exc)
        return jsonify({"error": "Could not update primary account"}), 500

    return jsonify({"account": account.to_dict(), "message": "Primary account updated"})


# ── Command Routing / Topic Access Control (custom bots) ──────────────────────

_ROUTABLE_COMMANDS = ["/xp", "/rank", "/leaderboard", "/level", "/rules", "/help", "/stats"]


@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/command-routing", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def get_custom_command_routing(bot_id, group_id):
    try:
        user = _get_current_user()
        if not user:
            return jsonify({"error": "User not found"}), 404
        bot, group, err = _get_bot_and_group(user, bot_id, group_id)
        if err:
            return err
        routing = (group.settings or {}).get("command_routing", {
            "topics": [], "commands": {}, "restricted_reply": "silent",
            "restricted_message": "⚠️ This command is only available in the {topic} topic.",
        })
        return jsonify({"routing": routing, "routable_commands": _ROUTABLE_COMMANDS})
    except Exception as e:
        logger.error(f"get_custom_command_routing error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/command-routing", methods=["PUT"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def update_custom_command_routing(bot_id, group_id):
    try:
        from sqlalchemy.orm.attributes import flag_modified
        user = _get_current_user()
        if not user:
            return jsonify({"error": "User not found"}), 404
        bot, group, err = _get_bot_and_group(user, bot_id, group_id)
        if err:
            return err
        data = request.get_json() or {}

        current = dict(group.settings or {})
        routing = dict(current.get("command_routing", {}))

        if "commands" in data and isinstance(data["commands"], dict):
            existing_cmds = dict(routing.get("commands") or {})
            for cmd, rule in data["commands"].items():
                if not isinstance(rule, dict):
                    continue
                scope = rule.get("scope", "all_group")
                if scope not in ("all_group", "specific_topics", "disabled"):
                    continue
                topic_ids = [str(t) for t in (rule.get("topic_ids") or [])]
                existing_cmds[cmd] = {"scope": scope, "topic_ids": topic_ids}
            routing["commands"] = existing_cmds

        if "restricted_reply" in data:
            val = data["restricted_reply"]
            if val in ("silent", "message"):
                routing["restricted_reply"] = val

        if "restricted_message" in data and isinstance(data["restricted_message"], str):
            routing["restricted_message"] = data["restricted_message"][:300]

        current["command_routing"] = routing
        group.settings = current
        flag_modified(group, "settings")
        db.session.commit()
        return jsonify({"routing": routing, "message": "Command routing updated"})
    except Exception as e:
        logger.error(f"update_custom_command_routing error: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

# ── Escalation endpoints ──────────────────────────────────────────────────────

@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/escalations", methods=["GET"])
@jwt_required()
def list_escalations(bot_id, group_id):
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "Not found"}), 404
    bot = Bot.query.filter_by(id=bot_id, owner_user_id=user_id).first()
    if not bot:
        return jsonify({"error": "Not found"}), 404
    group = Group.query.filter_by(id=group_id, bot_id=bot_id).first()
    if not group:
        return jsonify({"error": "Not found"}), 404
    status = request.args.get("status")
    q = EscalationEvent.query.filter_by(group_id=group_id)
    if status:
        q = q.filter_by(status=status)
    events = q.order_by(EscalationEvent.created_at.desc()).limit(100).all()
    return jsonify({"escalations": [e.to_dict() for e in events]})


@settings_bp.route("/telegram-groups/<telegram_group_id>/escalations", methods=["GET"])
@jwt_required()
def list_official_escalations(telegram_group_id):
    user_id = int(get_jwt_identity())
    status = request.args.get("status")
    q = EscalationEvent.query.filter_by(telegram_group_id=str(telegram_group_id), bot_id=None)
    if status:
        q = q.filter_by(status=status)
    events = q.order_by(EscalationEvent.created_at.desc()).limit(100).all()
    return jsonify({"escalations": [e.to_dict() for e in events]})


@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/escalations/<int:event_id>", methods=["PATCH"])
@jwt_required()
def patch_escalation(bot_id, group_id, event_id):
    user_id = int(get_jwt_identity())
    bot = Bot.query.filter_by(id=bot_id, owner_user_id=user_id).first()
    if not bot:
        return jsonify({"error": "Not found"}), 404
    ev = EscalationEvent.query.get(event_id)
    if not ev or ev.group_id != group_id:
        return jsonify({"error": "Not found"}), 404
    data = request.get_json(silent=True) or {}
    if "status" in data and data["status"] in ("pending", "resolved", "ignored"):
        ev.status = data["status"]
        if data["status"] == "resolved" and not ev.resolved_at:
            ev.resolved_at = datetime.utcnow()
    if "admin_answer" in data:
        ev.admin_answer = str(data["admin_answer"])[:4000]
    db.session.commit()
    return jsonify(ev.to_dict())


@settings_bp.route("/telegram-groups/<telegram_group_id>/escalations/<int:event_id>", methods=["PATCH"])
@jwt_required()
def patch_official_escalation(telegram_group_id, event_id):
    ev = EscalationEvent.query.get(event_id)
    if not ev or ev.telegram_group_id != str(telegram_group_id):
        return jsonify({"error": "Not found"}), 404
    data = request.get_json(silent=True) or {}
    if "status" in data and data["status"] in ("pending", "resolved", "ignored"):
        ev.status = data["status"]
        if data["status"] == "resolved" and not ev.resolved_at:
            ev.resolved_at = datetime.utcnow()
    if "admin_answer" in data:
        ev.admin_answer = str(data["admin_answer"])[:4000]
    db.session.commit()
    return jsonify(ev.to_dict())


# ══════════════════════════════════════════════════════════════════════════════
# GDPR: Data Export (Right to Portability — GDPR Art. 20)
# ══════════════════════════════════════════════════════════════════════════════

@settings_bp.route("/settings/export-data", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=2)
def export_data():
    """Queue a GDPR data export. User receives an email with their data within 24 hours.
    Rate-limited to 1 export per 24 hours per user via Redis.
    """
    user = User.query.get(int(get_jwt_identity()))
    if not user:
        return jsonify({"error": "User not found"}), 404

    # 24-hour rate limit per user via Redis
    try:
        import redis as _redis
        from flask import current_app
        from datetime import date as _date
        r = _redis.from_url(
            current_app.config.get("REDIS_URL", "redis://localhost:6379/0"),
            socket_connect_timeout=1, socket_timeout=1,
        )
        r_key = f"gdpr_export:{user.id}:{_date.today().isoformat()}"
        if r.exists(r_key):
            return jsonify({"error": "Export already requested today. Check your email."}), 429
        r.setex(r_key, 86400, 1)
    except Exception:
        pass  # Redis down — allow through

    try:
        from ..scheduler import generate_gdpr_export
        generate_gdpr_export.delay(user.id)
    except Exception as exc:
        logger.error("Failed to queue GDPR export for user %s: %s", user.id, exc)
        return jsonify({"error": "Failed to queue export. Please try again."}), 500

    return jsonify({"message": "Export requested. You will receive an email with your data within 24 hours."})


# ══════════════════════════════════════════════════════════════════════════════
# GDPR: Account Deletion (Right to Erasure — GDPR Art. 17)
# ══════════════════════════════════════════════════════════════════════════════

@settings_bp.route("/settings/delete-account", methods=["POST"])
@jwt_required()
def delete_account():
    """Soft-delete the user's account. Hard deletion of PII is scheduled 30 days later.

    Requires current password. If 2FA is enabled, also requires a TOTP code.
    """
    user = User.query.get(int(get_jwt_identity()))
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json(silent=True) or {}
    password = data.get("password", "")
    if not password or not user.check_password(password):
        return jsonify({"error": "Invalid password"}), 403

    # Require TOTP code if 2FA is enabled
    if getattr(user, "totp_enabled", False):
        totp_code = data.get("totp_code", "").strip()
        if not totp_code:
            return jsonify({"error": "TOTP code required", "requires_totp": True}), 403
        try:
            import pyotp
            from ..utils.encryption import decrypt_value
            secret = decrypt_value(user.totp_secret_encrypted) if user.totp_secret_encrypted else None
            if not secret or not pyotp.TOTP(secret).verify(totp_code, valid_window=1):
                return jsonify({"error": "Invalid TOTP code"}), 403
        except Exception as exc:
            logger.error("TOTP verification failed for account deletion user=%s: %s", user.id, exc)
            return jsonify({"error": "TOTP verification failed"}), 500

    # Soft-delete: mark account, suspend access immediately
    user.deleted_at = datetime.utcnow()
    user.is_suspended = True

    # Stop all bots immediately
    try:
        from ..bot_manager import bot_manager
        for bot in Bot.query.filter_by(user_id=user.id).all():
            try:
                bot_manager.stop_bot(bot.id)
            except Exception:
                pass
    except Exception as exc:
        logger.warning("Could not stop bots on account deletion user=%s: %s", user.id, exc)

    db.session.commit()

    # Schedule hard deletion in 30 days
    try:
        from ..scheduler import hard_delete_user
        hard_delete_user.apply_async(args=[user.id], countdown=30 * 86400)
    except Exception as exc:
        logger.error("Failed to schedule hard deletion for user %s: %s", user.id, exc)

    # Revoke the current JWT by adding it to the blacklist
    try:
        from flask_jwt_extended import get_jwt
        from flask import current_app
        import redis as _redis
        jti = get_jwt().get("jti", "")
        if jti:
            r = _redis.from_url(
                current_app.config.get("REDIS_URL", "redis://localhost:6379/0"),
                socket_connect_timeout=1, socket_timeout=1,
            )
            r.setex(f"jwt_blocklist:{jti}", 86400 * 30, 1)
    except Exception:
        pass

    return jsonify({"message": "Account deletion scheduled. Your data will be permanently removed within 30 days."})
