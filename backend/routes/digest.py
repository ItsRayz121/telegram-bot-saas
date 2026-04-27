"""
Telegram Report Digest — per-group settings, on-demand send, and scheduler helpers.

Digest config is stored inside group.settings["digest"] JSON to avoid a schema change:
{
  "daily": true,
  "weekly": false,
  "monthly": false,
  "last_daily": "2026-04-24T08:00:00",
  "last_weekly": "2026-04-20T08:00:00",
  "last_monthly": "2026-04-01T08:00:00",
  "recipients": {
    "owner_dm": false,
    "selected_admin_ids": [],
    "send_to_group": true,
    "group_topic_id": null
  }
}

Root-cause of previous digest error:
  InviteLinkJoin has no ORM relationship named "invite_link".
  The old .join(InviteLinkJoin.invite_link) raised AttributeError at runtime.
  Fixed by explicit join(InviteLink, InviteLink.id == InviteLinkJoin.invite_link_id)
  with a group_id filter so counts are scoped to the correct group.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func

from ..models import db, User, Bot, Group, AuditLog, ScheduledMessage, Poll, Member, InviteLinkJoin, InviteLink
from ..middleware.rate_limit import rate_limit

logger = logging.getLogger(__name__)

digest_bp = Blueprint("digest", __name__, url_prefix="/api/bots/<int:bot_id>/groups/<int:group_id>/digest")

# ── Auth helper ────────────────────────────────────────────────────────────────

def _get_group_or_404(bot_id, group_id):
    user_id = int(get_jwt_identity())
    bot = Bot.query.filter_by(id=bot_id, user_id=user_id).first()
    if not bot:
        return None, None
    group = Group.query.filter_by(id=group_id, bot_id=bot_id).first()
    return bot, group


def _mask_chat_id(chat_id) -> str:
    """Return a safe loggable form: keep sign + first 4 + last 2 digits."""
    s = str(chat_id)
    if len(s) <= 6:
        return s
    return s[:4] + "***" + s[-2:]


# ── Report data builder ────────────────────────────────────────────────────────

def _build_report_data(group_id: int, since: datetime) -> dict:
    """Aggregate report metrics for the period starting at `since` (UTC)."""

    action_counts = (
        db.session.query(AuditLog.action_type, func.count(AuditLog.id))
        .filter(AuditLog.group_id == group_id, AuditLog.timestamp >= since)
        .group_by(AuditLog.action_type)
        .all()
    )
    actions = {a: c for a, c in action_counts}
    spam_removed = actions.get("delete", 0) + actions.get("automod_delete", 0)
    users_warned = actions.get("warn", 0)
    users_banned = actions.get("ban", 0) + actions.get("tempban", 0)
    users_muted = actions.get("mute", 0) + actions.get("tempmute", 0)
    users_kicked = actions.get("kick", 0)

    scheduled_sent = ScheduledMessage.query.filter(
        ScheduledMessage.group_id == group_id,
        ScheduledMessage.is_sent == True,
        ScheduledMessage.send_at >= since,
    ).count()

    polls_sent = Poll.query.filter(
        Poll.group_id == group_id,
        Poll.is_sent == True,
        Poll.scheduled_at >= since,
    ).count()

    member_count = Member.query.filter_by(group_id=group_id).count()

    try:
        invite_joins = (
            db.session.query(func.count(InviteLinkJoin.id))
            .join(InviteLink, InviteLink.id == InviteLinkJoin.invite_link_id)
            .filter(
                InviteLink.group_id == group_id,
                InviteLinkJoin.joined_at >= since,
            )
            .scalar() or 0
        )
    except Exception as exc:
        logger.warning(f"[DIGEST] invite_joins query failed group={group_id}: {exc}")
        invite_joins = 0

    total_actions = sum(actions.values())

    return {
        "period_start": since.strftime("%Y-%m-%d %H:%M UTC"),
        "spam_removed": spam_removed,
        "users_warned": users_warned,
        "users_banned": users_banned,
        "users_muted": users_muted,
        "users_kicked": users_kicked,
        "total_mod_actions": total_actions,
        "scheduled_sent": scheduled_sent,
        "polls_sent": polls_sent,
        "member_count": member_count,
        "invite_joins": invite_joins,
    }


def _build_report_data_for_official(telegram_group_id: str, since: datetime) -> dict:
    """Like _build_report_data but uses telegram_group_id string (for official-bot groups)."""
    from ..models import BotEvent, OfficialMember, OfficialScheduledMessage, OfficialPoll
    gid = str(telegram_group_id)
    try:
        events = (
            db.session.query(BotEvent.event_type, func.count(BotEvent.id))
            .filter(
                BotEvent.telegram_group_id == gid,
                BotEvent.created_at >= since,
            )
            .group_by(BotEvent.event_type)
            .all()
        )
    except Exception:
        events = []
    counts = {e: c for e, c in events}

    # Mod actions — official_bot.py logs with "mod_" prefix
    spam_removed = counts.get("automod_action", 0) + counts.get("automod_delete", 0)
    users_warned = counts.get("mod_warn", 0)
    users_banned = counts.get("mod_ban", 0) + counts.get("mod_tempban", 0)
    users_muted = counts.get("mod_mute", 0) + counts.get("mod_tempmute", 0)
    users_kicked = counts.get("mod_kick", 0)
    total_mod_actions = spam_removed + users_warned + users_banned + users_muted + users_kicked

    try:
        member_count = OfficialMember.query.filter_by(telegram_group_id=gid).count()
    except Exception:
        member_count = counts.get("member_joined", 0)

    try:
        scheduled_sent = OfficialScheduledMessage.query.filter(
            OfficialScheduledMessage.telegram_group_id == gid,
            OfficialScheduledMessage.is_sent == True,
            OfficialScheduledMessage.send_at >= since,
        ).count()
    except Exception:
        scheduled_sent = 0

    try:
        polls_sent = OfficialPoll.query.filter(
            OfficialPoll.telegram_group_id == gid,
            OfficialPoll.is_sent == True,
            OfficialPoll.scheduled_at >= since,
        ).count()
    except Exception:
        polls_sent = 0

    return {
        "period_start": since.strftime("%Y-%m-%d %H:%M UTC"),
        "spam_removed": spam_removed,
        "users_warned": users_warned,
        "users_banned": users_banned,
        "users_muted": users_muted,
        "users_kicked": users_kicked,
        "total_mod_actions": total_mod_actions,
        "scheduled_sent": scheduled_sent,
        "polls_sent": polls_sent,
        "member_count": member_count,
        "invite_joins": counts.get("member_joined", 0),
    }


def _format_report_message(group_name: str, period_label: str, data: dict) -> str:
    lines = [
        f"📊 *{group_name} — {period_label} Report*",
        f"_{data['period_start']}_",
        "",
        "🛡 *Moderation*",
        f"  • Spam removed: {data['spam_removed']}",
        f"  • Users warned: {data['users_warned']}",
        f"  • Users banned: {data['users_banned']}",
        f"  • Users muted: {data['users_muted']}",
        f"  • Users kicked: {data['users_kicked']}",
        f"  • Total actions: {data['total_mod_actions']}",
        "",
        "📅 *Content*",
        f"  • Scheduled posts sent: {data['scheduled_sent']}",
        f"  • Polls/quizzes sent: {data['polls_sent']}",
        "",
        "👥 *Growth*",
        f"  • Members now: {data['member_count']}",
        f"  • Joined via invite links: {data['invite_joins']}",
        "",
        "⚡ Powered by Telegizer",
    ]
    return "\n".join(lines)


# ── Telegram helpers ───────────────────────────────────────────────────────────

async def _send_telegram_message(bot_token: str, chat_id, text: str, message_thread_id=None):
    import telegram
    bot = telegram.Bot(token=bot_token)
    kwargs = dict(
        chat_id=chat_id,
        text=text,
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )
    if message_thread_id:
        kwargs["message_thread_id"] = int(message_thread_id)
    await bot.send_message(**kwargs)


async def _preflight_check_group(bot_token: str, telegram_chat_id) -> dict:
    """
    Verify the bot can access the group. Returns:
      {"ok": True}
      {"ok": False, "reason": "not_found"|"forbidden"|"migrated", "new_chat_id": ...}
    """
    import telegram
    from telegram.error import BadRequest, Forbidden, ChatMigrated, TelegramError
    bot = telegram.Bot(token=bot_token)
    try:
        chat = await bot.get_chat(chat_id=telegram_chat_id)
        return {"ok": True, "chat": chat}
    except ChatMigrated as exc:
        return {"ok": False, "reason": "migrated", "new_chat_id": exc.new_chat_id}
    except (BadRequest, Forbidden) as exc:
        msg = str(exc).lower()
        if "not found" in msg or "chat not found" in msg or "invalid chat" in msg:
            return {"ok": False, "reason": "not_found", "detail": str(exc)}
        if "kicked" in msg or "blocked" in msg or "forbidden" in msg or "not a member" in msg:
            return {"ok": False, "reason": "forbidden", "detail": str(exc)}
        return {"ok": False, "reason": "telegram_error", "detail": str(exc)}
    except TelegramError as exc:
        return {"ok": False, "reason": "telegram_error", "detail": str(exc)}


def _mark_group_disconnected(group: Group, reason: str):
    """Mutate group.settings to record disconnected state. Caller must commit."""
    settings = dict(group.settings or {})
    settings["bot_status"] = "disconnected"
    settings["bot_status_reason"] = reason
    settings["bot_status_at"] = datetime.utcnow().isoformat()
    group.settings = settings


def _update_telegram_group_id(group: Group, new_chat_id):
    """Handle Telegram group migration — update stored telegram_group_id."""
    old = group.telegram_group_id
    try:
        group.telegram_group_id = str(new_chat_id)
        db.session.commit()
        logger.info(f"[DIGEST] group={group.id} migrated telegram_group_id {old} → {new_chat_id}")
    except Exception as exc:
        logger.warning(f"[DIGEST] failed to update telegram_group_id for group={group.id}: {exc}")
        db.session.rollback()


# ── Core send logic ────────────────────────────────────────────────────────────

def _do_send_report(group: Group, bot: Bot, period_label: str, since: datetime) -> dict:
    """
    Build and send a report to all configured recipients.

    Returns structured dict:
      {
        "sent":    [{"target": "group|owner_dm|admin:<id>", "description": "..."}],
        "skipped": [{"target": ..., "reason": "..."}],
        "failed":  [{"target": ..., "error": "..."}],
        "group_error": "user-facing string" | None,
      }
    """
    from ..bot_manager import bot_manager as _bm

    sent = []
    skipped = []
    failed = []
    group_error = None

    try:
        data = _build_report_data(group.id, since)
        text = _format_report_message(group.group_name or "Your Group", period_label, data)
    except Exception as exc:
        logger.error(f"[DIGEST] report_data build failed group={group.id}: {exc}")
        failed.append({"target": "all", "error": "Failed to build report data"})
        return {"sent": sent, "skipped": skipped, "failed": failed, "group_error": None}

    instance = _bm.active_bots.get(bot.id)

    def _run(coro):
        if instance and instance.loop and instance.loop.is_running():
            future = asyncio.run_coroutine_threadsafe(coro, instance.loop)
            future.result(timeout=15)
        else:
            asyncio.run(coro)

    recipients = (group.settings or {}).get("digest", {}).get("recipients", {})
    send_to_group = recipients.get("send_to_group", True)
    topic_id = recipients.get("group_topic_id")
    owner_dm = recipients.get("owner_dm", False)
    admin_ids = recipients.get("selected_admin_ids") or []

    tg_chat_id = group.telegram_group_id
    bot_username = bot.bot_username or f"bot_id={bot.id}"

    # ── Pre-flight: verify bot can still access the group ─────────────────────
    if send_to_group:
        try:
            preflight = _run_preflight_sync(bot.bot_token, tg_chat_id, instance)
        except Exception as exc:
            logger.warning(f"[DIGEST] preflight check error group={group.id} tg_chat={_mask_chat_id(tg_chat_id)}: {exc}")
            preflight = {"ok": True}  # attempt send anyway; errors caught below

        if isinstance(preflight, dict) and not preflight.get("ok"):
            reason = preflight.get("reason", "unknown")
            detail = preflight.get("detail", "")

            if reason == "migrated":
                new_chat_id = preflight.get("new_chat_id")
                _update_telegram_group_id(group, new_chat_id)
                tg_chat_id = str(new_chat_id)
                logger.info(
                    f"[DIGEST] group={group.id} bot={bot_username} migrated → {_mask_chat_id(tg_chat_id)}"
                )
            elif reason in ("not_found", "forbidden"):
                _mark_group_disconnected(group, reason)
                group_error = (
                    "Telegizer cannot access this group. "
                    "Please re-add the bot as admin and reconnect the group."
                )
                logger.warning(
                    f"[DIGEST] group inaccessible group={group.id} "
                    f"tg_chat={_mask_chat_id(group.telegram_group_id)} "
                    f"bot={bot_username} reason={reason}: {detail}"
                )
                skipped.append({"target": "group", "reason": group_error})
                send_to_group = False  # skip group send; still try DMs

    # ── Send to group (or topic) ───────────────────────────────────────────────
    if send_to_group:
        import telegram.error as tg_error
        try:
            _run(_send_telegram_message(bot.bot_token, tg_chat_id, text, topic_id))
            sent.append({"target": "group", "description": f"tg_chat={_mask_chat_id(tg_chat_id)}"})
            logger.info(
                f"[DIGEST] group send OK group={group.id} "
                f"tg_chat={_mask_chat_id(tg_chat_id)} bot={bot_username}"
            )
        except tg_error.ChatMigrated as exc:
            _update_telegram_group_id(group, exc.new_chat_id)
            try:
                _run(_send_telegram_message(bot.bot_token, str(exc.new_chat_id), text, topic_id))
                sent.append({"target": "group", "description": f"tg_chat={_mask_chat_id(exc.new_chat_id)} (migrated)"})
            except Exception as retry_exc:
                logger.error(
                    f"[DIGEST] group send failed after migration group={group.id} "
                    f"new_tg_chat={_mask_chat_id(exc.new_chat_id)} bot={bot_username}: {retry_exc}"
                )
                failed.append({"target": "group", "error": str(retry_exc)})
        except (tg_error.BadRequest, tg_error.Forbidden) as exc:
            detail = str(exc)
            msg_lower = detail.lower()
            if "not found" in msg_lower or "chat not found" in msg_lower:
                _mark_group_disconnected(group, "not_found")
                group_error = (
                    "Telegizer cannot access this group. "
                    "Please re-add the bot as admin and reconnect the group."
                )
                logger.warning(
                    f"[DIGEST] group send Not Found group={group.id} "
                    f"tg_chat={_mask_chat_id(tg_chat_id)} bot={bot_username}: {detail}"
                )
                skipped.append({"target": "group", "reason": group_error})
            elif "kicked" in msg_lower or "blocked" in msg_lower or "not a member" in msg_lower:
                _mark_group_disconnected(group, "bot_removed")
                group_error = (
                    "Telegizer cannot access this group. "
                    "Please re-add the bot as admin and reconnect the group."
                )
                logger.warning(
                    f"[DIGEST] group send bot removed group={group.id} "
                    f"tg_chat={_mask_chat_id(tg_chat_id)} bot={bot_username}: {detail}"
                )
                skipped.append({"target": "group", "reason": group_error})
            else:
                logger.error(
                    f"[DIGEST] group send failed group={group.id} "
                    f"tg_chat={_mask_chat_id(tg_chat_id)} bot={bot_username}: {detail}"
                )
                failed.append({"target": "group", "error": detail})
        except Exception as exc:
            logger.error(
                f"[DIGEST] group send failed group={group.id} "
                f"tg_chat={_mask_chat_id(tg_chat_id)} bot={bot_username}: {exc}"
            )
            failed.append({"target": "group", "error": str(exc)})

    # ── DM account owner ───────────────────────────────────────────────────────
    if owner_dm:
        try:
            from ..models import User as _User, TelegramBotStarted
            bot_obj = Bot.query.get(bot.id)
            owner = _User.query.get(bot_obj.user_id) if bot_obj else None
            if owner and owner.telegram_user_id:
                if TelegramBotStarted.has_started(owner.telegram_user_id):
                    _run(_send_telegram_message(bot.bot_token, owner.telegram_user_id, text))
                    sent.append({"target": "owner_dm", "description": f"user_id={owner.id}"})
                else:
                    skipped.append({"target": "owner_dm", "reason": "owner has not started bot"})
                    logger.info(f"[DIGEST] owner {owner.id} has not started bot — skipping DM")
            else:
                skipped.append({"target": "owner_dm", "reason": "owner has no Telegram linked"})
                logger.info(f"[DIGEST] owner has no telegram linked — skipping DM")
        except Exception as exc:
            logger.error(f"[DIGEST] owner DM failed group={group.id} bot={bot_username}: {exc}")
            failed.append({"target": "owner_dm", "error": str(exc)})

    # ── DM selected admins ─────────────────────────────────────────────────────
    for admin_id in admin_ids:
        target = f"admin:{admin_id}"
        try:
            from ..models import TelegramBotStarted
            if TelegramBotStarted.has_started(str(admin_id)):
                _run(_send_telegram_message(bot.bot_token, str(admin_id), text))
                sent.append({"target": target})
            else:
                skipped.append({"target": target, "reason": "admin has not started bot"})
                logger.info(f"[DIGEST] admin {admin_id} has not started bot — skipping DM")
        except Exception as exc:
            logger.error(f"[DIGEST] admin DM {admin_id} failed group={group.id} bot={bot_username}: {exc}")
            failed.append({"target": target, "error": str(exc)})

    return {"sent": sent, "skipped": skipped, "failed": failed, "group_error": group_error}


def _run_preflight_sync(bot_token: str, tg_chat_id, instance) -> dict:
    """Run preflight check on the bot's event loop if available, else new loop."""
    coro = _preflight_check_group(bot_token, tg_chat_id)
    if instance and instance.loop and instance.loop.is_running():
        future = asyncio.run_coroutine_threadsafe(coro, instance.loop)
        return future.result(timeout=10)
    else:
        return asyncio.run(coro)


# ── Routes ─────────────────────────────────────────────────────────────────────

@digest_bp.route("", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def get_digest(bot_id, group_id):
    bot, group = _get_group_or_404(bot_id, group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404

    digest = (group.settings or {}).get("digest", {})
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


@digest_bp.route("", methods=["PUT"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def update_digest(bot_id, group_id):
    bot, group = _get_group_or_404(bot_id, group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404

    data = request.get_json() or {}
    settings = dict(group.settings or {})
    digest = dict(settings.get("digest", {}))

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

    settings["digest"] = digest
    group.settings = settings
    db.session.commit()
    return jsonify({"digest": digest})


@digest_bp.route("/send-now", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=5)
def send_now(bot_id, group_id):
    bot, group = _get_group_or_404(bot_id, group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404
    if not bot.is_active:
        return jsonify({"error": "Bot is not active"}), 400

    data = request.get_json() or {}
    period = data.get("period", "weekly")  # daily | weekly | monthly

    period_config = {
        "daily":   ("Daily",   timedelta(days=1)),
        "weekly":  ("Weekly",  timedelta(days=7)),
        "monthly": ("Monthly", timedelta(days=30)),
    }
    label, delta = period_config.get(period, ("Weekly", timedelta(days=7)))
    since = datetime.utcnow() - delta

    result = _do_send_report(group, bot, f"{label} Report", since)

    sent = result.get("sent", [])
    skipped = result.get("skipped", [])
    failed = result.get("failed", [])
    group_error = result.get("group_error")

    if not sent:
        # Persist any group state mutations (e.g. bot_status=disconnected)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

        error_msg = (
            group_error
            or "Failed to send report — check that bot is active in the group and recipients have started @telegizer_bot"
        )
        return jsonify({
            "error": error_msg,
            "sent": sent,
            "skipped": skipped,
            "failed": failed,
        }), 502

    # At least one recipient received the digest — update last_sent timestamp
    settings = dict(group.settings or {})
    digest = dict(settings.get("digest", {}))
    digest[f"last_{period}"] = datetime.utcnow().isoformat()
    settings["digest"] = digest
    group.settings = settings
    db.session.commit()

    return jsonify({
        "status": "sent",
        "sent": sent,
        "skipped": skipped,
        "failed": failed,
        **({"warning": group_error} if group_error else {}),
    })


# ── Scheduler helper (called from app.py) ─────────────────────────────────────

def run_digest_scheduler(app):
    """Called every 60 s from _scheduler_loop. Sends due digest reports."""
    now = datetime.utcnow()
    with app.app_context():
        groups = Group.query.all()
        for group in groups:
            digest = (group.settings or {}).get("digest", {})
            if not any([digest.get("daily"), digest.get("weekly"), digest.get("monthly")]):
                continue

            bot = Bot.query.get(group.bot_id)
            if not bot or not bot.is_active:
                continue

            _check_and_send(group, bot, now, "daily",   timedelta(days=1),  timedelta(hours=23))
            _check_and_send(group, bot, now, "weekly",  timedelta(days=7),  timedelta(hours=23))
            _check_and_send(group, bot, now, "monthly", timedelta(days=30), timedelta(hours=23))

            db.session.commit()


def _check_and_send(group, bot, now, key, period_delta, tolerance):
    digest = (group.settings or {}).get("digest", {})
    if not digest.get(key):
        return

    last_key = f"last_{key}"
    last_sent_str = digest.get(last_key)
    if last_sent_str:
        try:
            last_sent = datetime.fromisoformat(last_sent_str)
            if now - last_sent < period_delta - tolerance:
                return
        except Exception:
            pass

    label_map = {"daily": "Daily", "weekly": "Weekly", "monthly": "Monthly"}
    result = _do_send_report(group, bot, f"{label_map[key]} Report", now - period_delta)
    if result.get("sent"):
        settings = dict(group.settings or {})
        d = dict(settings.get("digest", {}))
        d[last_key] = now.isoformat()
        settings["digest"] = d
        group.settings = settings
        logger.info(
            f"[DIGEST] Sent {key} report for group={group.id} "
            f"sent={len(result['sent'])} skipped={len(result['skipped'])} failed={len(result['failed'])}"
        )
    elif result.get("group_error"):
        logger.warning(
            f"[DIGEST] Skipped {key} report for group={group.id}: {result['group_error']}"
        )
