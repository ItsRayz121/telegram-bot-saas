import asyncio
import logging
import requests as _http
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func
from sqlalchemy.orm.attributes import flag_modified

from ..models import db, User, TelegramGroup, TelegramBotStarted, BotEvent
from ..middleware.rate_limit import rate_limit
from .settings import _check_gated_settings, _deep_merge
from ..config import Config

logger = logging.getLogger(__name__)
official_settings_bp = Blueprint("official_settings", __name__, url_prefix="/api/official-groups")

_TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"

# Permissions the bot can hold — only real Telegram Bot API fields from getChatMember.
# Removed: can_ban_members (not a real field; restriction covers banning),
#           is_anonymous (admin preference, not a grantable permission),
#           can_manage_topics (only applies to Forum supergroups).
_PERMISSION_DEFS = [
    ("can_delete_messages",    "Delete messages",       "AutoMod deletion"),
    ("can_restrict_members",   "Restrict / mute / ban", "Mute, kick & verification"),
    ("can_pin_messages",       "Pin messages",           "Pinned announcements"),
    ("can_manage_chat",        "Manage chat",            "Admin rights management"),
    ("can_invite_users",       "Invite users",           "Invite link tools"),
    ("can_promote_members",    "Add admins",             "Grant admin rights"),
    ("can_change_info",        "Change group info",      "Group info updates"),
    ("can_manage_video_chats", "Manage video chats",     "Voice chats & live streams"),
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


# ── Official Group Digest ──────────────────────────────────────────────────────

@official_settings_bp.route("/<group_id>/digest", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def get_official_digest(group_id):
    try:
        user = _get_current_user()
        if not user:
            return jsonify({"error": "User not found"}), 404
        tg, err = _get_official_group(user, group_id)
        if err:
            return err
        digest = (tg.settings or {}).get("digest", {})
        recipients = digest.get("recipients", {})
        return jsonify({
            "digest": {
                "daily": bool(digest.get("daily")),
                "weekly": bool(digest.get("weekly")),
                "monthly": bool(digest.get("monthly")),
                "last_daily": digest.get("last_daily"),
                "last_weekly": digest.get("last_weekly"),
                "last_monthly": digest.get("last_monthly"),
                "recipients": {
                    "owner_dm": bool(recipients.get("owner_dm", False)),
                    "selected_admin_ids": recipients.get("selected_admin_ids") or [],
                    "send_to_group": bool(recipients.get("send_to_group", True)),
                    "group_topic_id": recipients.get("group_topic_id"),
                },
            }
        })
    except Exception as e:
        logger.error(f"get_official_digest error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@official_settings_bp.route("/<group_id>/digest", methods=["PUT"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def update_official_digest(group_id):
    try:
        user = _get_current_user()
        if not user:
            return jsonify({"error": "User not found"}), 404
        tg, err = _get_official_group(user, group_id)
        if err:
            return err
        data = request.get_json() or {}
        current = dict(tg.settings or {})
        digest = dict(current.get("digest", {}))

        for key in ("daily", "weekly", "monthly"):
            if key in data:
                digest[key] = bool(data[key])

        if "recipients" in data and isinstance(data["recipients"], dict):
            rec = data["recipients"]
            existing_rec = dict(digest.get("recipients", {}))
            if "owner_dm" in rec:
                existing_rec["owner_dm"] = bool(rec["owner_dm"])
            if "selected_admin_ids" in rec:
                existing_rec["selected_admin_ids"] = [str(x) for x in (rec["selected_admin_ids"] or [])]
            if "send_to_group" in rec:
                existing_rec["send_to_group"] = bool(rec["send_to_group"])
            if "group_topic_id" in rec:
                existing_rec["group_topic_id"] = int(rec["group_topic_id"]) if rec["group_topic_id"] else None
            digest["recipients"] = existing_rec

        current["digest"] = digest
        tg.settings = current
        flag_modified(tg, "settings")
        db.session.commit()
        return jsonify({"digest": digest})
    except Exception as e:
        logger.error(f"update_official_digest error: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@official_settings_bp.route("/<group_id>/digest/send-now", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=5)
def send_official_digest_now(group_id):
    """Send a digest report now for an official-bot group using TELEGRAM_BOT_TOKEN."""
    try:
        user = _get_current_user()
        if not user:
            return jsonify({"error": "User not found"}), 404
        tg, err = _get_official_group(user, group_id)
        if err:
            return err

        token = Config.TELEGRAM_BOT_TOKEN
        if not token:
            return jsonify({"error": "Official bot token not configured"}), 500

        data = request.get_json() or {}
        period = data.get("period", "weekly")
        period_config = {
            "daily":   ("Daily Report",   timedelta(days=1)),
            "weekly":  ("Weekly Report",  timedelta(days=7)),
            "monthly": ("Monthly Report", timedelta(days=30)),
        }
        label, delta = period_config.get(period, ("Weekly Report", timedelta(days=7)))
        since = datetime.utcnow() - delta

        ok = _do_send_official_report(tg, token, user, label, since)
        if not ok:
            return jsonify({"error": "Failed to send report — ensure bot is active in the group and recipients have started @telegizer_bot"}), 502

        current = dict(tg.settings or {})
        digest = dict(current.get("digest", {}))
        digest[f"last_{period}"] = datetime.utcnow().isoformat()
        current["digest"] = digest
        tg.settings = current
        flag_modified(tg, "settings")
        db.session.commit()
        return jsonify({"status": "sent"})
    except Exception as e:
        logger.error(f"send_official_digest_now error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


def _do_send_official_report(tg: TelegramGroup, bot_token: str, owner_user: User, period_label: str, since: datetime) -> bool:
    """Build and send a digest report for an official-bot group."""
    from ..routes.digest import _build_report_data_for_official, _format_report_message

    try:
        data = _build_report_data_for_official(tg.telegram_group_id, since)
        text = _format_report_message(tg.title or "Your Group", period_label, data)
        recipients = (tg.settings or {}).get("digest", {}).get("recipients", {})
        send_to_group = recipients.get("send_to_group", True)
        topic_id = recipients.get("group_topic_id")
        owner_dm = recipients.get("owner_dm", False)
        admin_ids = recipients.get("selected_admin_ids") or []
        sent_any = False

        async def _send(chat_id, thread_id=None):
            import telegram
            bot = telegram.Bot(token=bot_token)
            kwargs = dict(chat_id=chat_id, text=text, parse_mode="Markdown", disable_web_page_preview=True)
            if thread_id:
                kwargs["message_thread_id"] = int(thread_id)
            await bot.send_message(**kwargs)

        def _run(coro):
            asyncio.run(coro)

        if send_to_group:
            try:
                _run(_send(tg.telegram_group_id, topic_id))
                sent_any = True
            except Exception as exc:
                logger.error(f"[DIGEST-official] group send failed group={tg.id}: {exc}")

        if owner_dm and owner_user.telegram_user_id:
            try:
                if TelegramBotStarted.has_started(owner_user.telegram_user_id):
                    _run(_send(owner_user.telegram_user_id))
                    sent_any = True
                else:
                    logger.info(f"[DIGEST-official] owner {owner_user.id} has not started bot — skipping DM")
            except Exception as exc:
                logger.error(f"[DIGEST-official] owner DM failed: {exc}")

        for admin_id in admin_ids:
            try:
                if TelegramBotStarted.has_started(str(admin_id)):
                    _run(_send(str(admin_id)))
                    sent_any = True
                else:
                    logger.info(f"[DIGEST-official] admin {admin_id} has not started bot — skipping DM")
            except Exception as exc:
                logger.error(f"[DIGEST-official] admin DM {admin_id} failed: {exc}")

        return sent_any
    except Exception as exc:
        logger.error(f"[DIGEST-official] Send failed group={tg.id}: {exc}")
        return False


# ── Official Group Analytics ───────────────────────────────────────────────────

@official_settings_bp.route("/<group_id>/analytics", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def get_official_group_analytics(group_id):
    """
    Returns analytics for a single official-bot group based on BotEvents.
    Days param: 7 | 14 | 30 (default 30, max 90).
    """
    try:
        user = _get_current_user()
        if not user:
            return jsonify({"error": "User not found"}), 404
        tg, err = _get_official_group(user, group_id)
        if err:
            return err

        days = min(request.args.get("days", 30, type=int), 90)
        cutoff = datetime.utcnow() - timedelta(days=days)

        # Event counts by type
        event_rows = (
            db.session.query(BotEvent.event_type, func.count(BotEvent.id))
            .filter(
                BotEvent.telegram_group_id == group_id,
                BotEvent.created_at >= cutoff,
            )
            .group_by(BotEvent.event_type)
            .all()
        )
        events_by_type = {et: cnt for et, cnt in event_rows}

        # Daily join events
        daily_joins = []
        for i in range(min(days, 30)):
            day = datetime.utcnow() - timedelta(days=days - i - 1)
            day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day.replace(hour=23, minute=59, second=59, microsecond=999999)
            cnt = BotEvent.query.filter(
                BotEvent.telegram_group_id == group_id,
                BotEvent.event_type.in_(["member_joined", "verification_passed"]),
                BotEvent.created_at >= day_start,
                BotEvent.created_at <= day_end,
            ).count()
            daily_joins.append({"date": day_start.strftime("%Y-%m-%d"), "joins": cnt})

        # Recent events (last 20)
        recent_events = BotEvent.query.filter(
            BotEvent.telegram_group_id == group_id,
            BotEvent.created_at >= cutoff,
        ).order_by(BotEvent.created_at.desc()).limit(20).all()

        return jsonify({
            "analytics": {
                "days": days,
                "summary": {
                    "total_events": sum(events_by_type.values()),
                    "member_joins": events_by_type.get("member_joined", 0),
                    "verifications_passed": events_by_type.get("verification_passed", 0),
                    "verifications_failed": events_by_type.get("verification_failed", 0),
                    "automod_actions": events_by_type.get("automod_action", 0),
                    "commands_used": events_by_type.get("command_triggered", 0),
                    "messages_handled": events_by_type.get("message_processed", 0),
                },
                "events_by_type": events_by_type,
                "daily_joins": daily_joins,
                "recent_events": [
                    {
                        "id": e.id,
                        "event_type": e.event_type,
                        "message": e.message,
                        "created_at": e.created_at.isoformat(),
                    }
                    for e in recent_events
                ],
            }
        })
    except Exception as e:
        logger.error(f"get_official_group_analytics error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@official_settings_bp.route("/analytics/overview", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def get_official_analytics_overview():
    """
    User-level aggregate analytics across ALL of this user's official-bot groups.
    """
    try:
        user = _get_current_user()
        if not user:
            return jsonify({"error": "User not found"}), 404

        days = min(request.args.get("days", 30, type=int), 90)
        cutoff = datetime.utcnow() - timedelta(days=days)

        groups = TelegramGroup.query.filter_by(
            owner_user_id=user.id, is_disabled=False
        ).all()
        group_ids = [g.telegram_group_id for g in groups]

        if not group_ids:
            return jsonify({
                "analytics": {
                    "total_groups": 0,
                    "total_events": 0,
                    "summary": {},
                    "top_groups": [],
                }
            })

        event_rows = (
            db.session.query(BotEvent.event_type, func.count(BotEvent.id))
            .filter(
                BotEvent.telegram_group_id.in_(group_ids),
                BotEvent.created_at >= cutoff,
            )
            .group_by(BotEvent.event_type)
            .all()
        )
        events_by_type = {et: cnt for et, cnt in event_rows}

        # Top groups by event count
        top_group_rows = (
            db.session.query(BotEvent.telegram_group_id, func.count(BotEvent.id).label("cnt"))
            .filter(
                BotEvent.telegram_group_id.in_(group_ids),
                BotEvent.created_at >= cutoff,
            )
            .group_by(BotEvent.telegram_group_id)
            .order_by(func.count(BotEvent.id).desc())
            .limit(5)
            .all()
        )
        group_title_map = {g.telegram_group_id: g.title for g in groups}
        top_groups = [
            {"group_id": gid, "title": group_title_map.get(gid, gid), "events": cnt}
            for gid, cnt in top_group_rows
        ]

        return jsonify({
            "analytics": {
                "days": days,
                "total_groups": len(groups),
                "summary": {
                    "total_events": sum(events_by_type.values()),
                    "member_joins": events_by_type.get("member_joined", 0),
                    "verifications_passed": events_by_type.get("verification_passed", 0),
                    "automod_actions": events_by_type.get("automod_action", 0),
                    "commands_used": events_by_type.get("command_triggered", 0),
                },
                "events_by_type": events_by_type,
                "top_groups": top_groups,
            }
        })
    except Exception as e:
        logger.error(f"get_official_analytics_overview error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500
