"""
Assistant Action Surface — platform operations the assistant can trigger.

Each action is a callable registered in ACTION_REGISTRY.
Actions receive (user, args: dict) and return {"reply": str, "data": dict|None}.
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

_log = logging.getLogger(__name__)

# ── Registry ──────────────────────────────────────────────────────────────────

ACTION_REGISTRY: dict[str, Callable] = {}


def register(name: str):
    """Decorator: @register("action_name")"""
    def decorator(fn: Callable) -> Callable:
        ACTION_REGISTRY[name] = fn
        return fn
    return decorator


def run_action(name: str, user, args: dict) -> dict:
    """Dispatch an action by name. Returns {"reply", "data", "intent"}."""
    fn = ACTION_REGISTRY.get(name)
    if not fn:
        return {"reply": f"I don't know how to do '{name}' yet.", "data": None, "intent": "unknown"}
    try:
        result = fn(user, args)
        result.setdefault("intent", name)
        return result
    except Exception as exc:
        _log.warning("Action %s failed for user %s: %s", name, user.id, exc)
        return {"reply": "That action failed — please try again.", "data": None, "intent": name}


# ── Actions ───────────────────────────────────────────────────────────────────

@register("trigger_digest")
def trigger_digest(user, args: dict) -> dict:
    """Manually trigger a digest for one or all of the user's groups."""
    from ..models import db, TelegramGroup, DigestLog
    from datetime import datetime

    group_id = args.get("group_id")
    groups = TelegramGroup.query.filter_by(owner_user_id=user.id, is_disabled=False).all()

    if group_id:
        groups = [g for g in groups if g.telegram_group_id == str(group_id)]

    if not groups:
        return {"reply": "No matching group found. Which group would you like to digest?", "data": None}

    triggered = []
    for group in groups[:3]:  # cap to 3 to avoid abuse
        try:
            from ..tasks.digest import send_daily_digest
            send_daily_digest.delay(group.telegram_group_id)
            triggered.append(group.title)
        except Exception as exc:
            _log.warning("trigger_digest: group %s failed: %s", group.telegram_group_id, exc)

    if not triggered:
        return {"reply": "Failed to trigger digest. Please check that your groups have recent messages.", "data": None}

    names = ", ".join(triggered)
    return {
        "reply": f"✅ Digest triggered for: {names}. It will be sent to the group shortly.",
        "data": {"triggered_groups": triggered},
    }


@register("post_announcement")
def post_announcement(user, args: dict) -> dict:
    """Post an announcement message to one of the user's groups."""
    from ..models import TelegramGroup
    from ..config import Config
    import requests as _r

    group_id = args.get("group_id")
    text = (args.get("text") or "").strip()

    if not text:
        return {"reply": "What would you like the announcement to say?", "data": None}

    groups = TelegramGroup.query.filter_by(owner_user_id=user.id, is_disabled=False).all()
    if group_id:
        groups = [g for g in groups if g.telegram_group_id == str(group_id)]

    if not groups:
        return {"reply": "No matching group found.", "data": None}

    if len(groups) > 1:
        names = "\n".join(f"  • {g.title} (ID: {g.telegram_group_id})" for g in groups[:5])
        return {
            "reply": f"Which group should I post to?\n{names}\n\nReply with the group name or ID.",
            "data": {"action": "post_announcement", "pending_group_pick": True, "groups": [g.telegram_group_id for g in groups]},
        }

    group = groups[0]
    bot_token = Config.TELEGRAM_BOT_TOKEN
    try:
        resp = _r.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": group.telegram_group_id, "text": text, "parse_mode": "Markdown"},
            timeout=10,
        )
        resp.raise_for_status()
    except Exception as exc:
        _log.warning("post_announcement: send failed: %s", exc)
        return {"reply": "Failed to send the announcement. Make sure the bot is still active in the group.", "data": None}

    return {
        "reply": f"✅ Announcement posted to *{group.title}*.",
        "data": {"group_id": group.telegram_group_id, "group_title": group.title},
    }


@register("get_group_stats")
def get_group_stats(user, args: dict) -> dict:
    """Return today's stats for a group (or all groups)."""
    from ..models import TelegramGroup, GroupDailySignal
    from datetime import date

    groups = TelegramGroup.query.filter_by(owner_user_id=user.id, is_disabled=False).all()
    if not groups:
        return {"reply": "You have no connected groups.", "data": None}

    today = date.today()
    lines = ["📊 *Group Stats — Today*\n"]
    stats_data = []

    for g in groups[:5]:
        sig = GroupDailySignal.query.filter_by(
            telegram_group_id=g.telegram_group_id, date=today
        ).first()

        if sig:
            health_emoji = {"healthy": "✅", "watch": "⚠️", "critical": "🚨"}.get(sig.health_status, "❓")
            lines.append(
                f"{health_emoji} *{g.title}*\n"
                f"  Messages: {sig.message_count} | Members active: {sig.active_members}\n"
                f"  Spam: {sig.spam_score:.1f}/10 | Conflict: {sig.conflict_score:.1f}/10\n"
                + (f"  _{sig.ai_summary}_\n" if sig.ai_summary else "")
            )
            stats_data.append(sig.to_dict())
        else:
            lines.append(f"❓ *{g.title}* — no signal data yet (analysis runs every 2h)")

    return {
        "reply": "\n".join(lines),
        "data": {"groups": stats_data},
    }


@register("list_auto_replies")
def list_auto_replies(user, args: dict) -> dict:
    """Show recent auto-reply activity for the user's groups."""
    from ..models import AutoReplyLog, TelegramGroup
    from datetime import datetime, timedelta

    group_ids = [
        g.telegram_group_id
        for g in TelegramGroup.query.filter_by(owner_user_id=user.id, is_disabled=False).all()
    ]
    if not group_ids:
        return {"reply": "No groups connected. Add @telegizer_bot to a group first.", "data": None}

    cutoff = datetime.utcnow() - timedelta(days=7)
    logs = (
        AutoReplyLog.query
        .filter(AutoReplyLog.telegram_group_id.in_(group_ids))
        .filter(AutoReplyLog.triggered_at >= cutoff)
        .order_by(AutoReplyLog.triggered_at.desc())
        .limit(10)
        .all()
    )

    if not logs:
        return {
            "reply": "No auto-reply activity in the last 7 days. Set up SmartLinks in Automations → Auto-Reply.",
            "data": None,
        }

    lines = ["🤖 *Recent Auto-Reply Triggers (last 7 days)*\n"]
    for log in logs:
        ts = log.triggered_at.strftime("%b %d %H:%M") if log.triggered_at else "?"
        trigger = log.trigger_text or "unknown"
        lines.append(f"• [{ts}] `{trigger}` fired in group {log.telegram_group_id}")

    return {
        "reply": "\n".join(lines),
        "data": {"recent_triggers": len(logs)},
    }


@register("update_automod")
def update_automod(user, args: dict) -> dict:
    """Enable or disable automod for a group."""
    from ..models import db, TelegramGroup

    group_id = args.get("group_id")
    enable = args.get("enable", True)  # True = enable, False = disable

    groups = TelegramGroup.query.filter_by(owner_user_id=user.id, is_disabled=False).all()
    if group_id:
        groups = [g for g in groups if g.telegram_group_id == str(group_id)]

    if not groups:
        return {"reply": "No matching group found.", "data": None}

    updated = []
    for group in groups[:3]:
        settings = group.settings or {}
        automod = settings.get("automod", {})
        automod["enabled"] = bool(enable)
        settings["automod"] = automod
        group.settings = settings
        updated.append(group.title)

    db.session.commit()
    verb = "enabled" if enable else "disabled"
    return {
        "reply": f"✅ Automod {verb} for: {', '.join(updated)}.",
        "data": {"updated_groups": updated, "enabled": enable},
    }
