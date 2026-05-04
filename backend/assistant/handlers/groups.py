"""Group intelligence — structured AI report."""
from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timedelta

from ._ai import call_ai_text
from ._prompts import GROUP_ANALYSIS_SYSTEM

_log = logging.getLogger(__name__)


def handle_group_query(user_id: int, key_info: dict) -> dict:
    from ...models import TelegramGroup, MessageBuffer, GroupDailySignal
    from datetime import date

    groups = TelegramGroup.query.filter_by(owner_user_id=user_id, is_disabled=False).all()
    if not groups:
        return {
            "reply": (
                "You don't have any groups connected yet.\n\n"
                "Add @telegizer_bot to your Telegram group and link it in the dashboard to enable group intelligence."
            ),
            "intent": "group_query",
            "data": None,
        }

    # Prefer pre-computed signals (Phase 3) over raw MessageBuffer dump
    today = date.today()
    signal_lines = []
    for g in groups:
        sig = GroupDailySignal.query.filter_by(
            telegram_group_id=g.telegram_group_id, date=today
        ).first()
        if sig:
            health_emoji = {"healthy": "✅", "watch": "⚠️", "critical": "🚨"}.get(sig.health_status, "❓")
            line = (
                f"{health_emoji} *{g.title or g.telegram_group_id}*\n"
                f"  Status: {sig.health_status.capitalize()} | "
                f"Messages: {sig.message_count} | Members: {sig.active_members}\n"
                f"  Spam: {sig.spam_score:.1f}/10, Conflict: {sig.conflict_score:.1f}/10"
            )
            if sig.ai_summary:
                line += f"\n  _{sig.ai_summary}_"
            signal_lines.append(line)

    if signal_lines:
        return {
            "reply": "Group intelligence (today):\n\n" + "\n\n".join(signal_lines),
            "intent": "group_query",
            "data": {"groups_checked": len(groups), "from_signals": True},
            "suggestions": [
                {"label": "Refresh now", "value": "Any issues in my groups?"},
                {"label": "Group stats", "value": "Show group stats"},
            ],
        }

    # Fallback: live scan via MessageBuffer + AI
    cutoff = datetime.utcnow() - timedelta(hours=24)
    group_ids = [g.telegram_group_id for g in groups]
    msgs = (
        MessageBuffer.query
        .filter(MessageBuffer.telegram_group_id.in_(group_ids))
        .filter(MessageBuffer.created_at >= cutoff)
        .order_by(MessageBuffer.created_at.desc())
        .limit(300).all()
    )

    if not msgs:
        lines = [
            f"Group: {g.title or g.telegram_group_id}\nStatus: No recent activity\n"
            "Recommended action: Check if the bot is still active in this group."
            for g in groups
        ]
        return {"reply": "No messages found in your groups in the last 24h.\n\n" + "\n\n".join(lines),
                "intent": "group_query", "data": {"groups_checked": len(groups), "messages_scanned": 0}}

    group_title_map = {g.telegram_group_id: (g.title or g.telegram_group_id) for g in groups}
    context = "\n".join(
        f"[{group_title_map.get(m.telegram_group_id, m.telegram_group_id)}] "
        f"{m.sender_name or 'User'}: {m.message_text}"
        for m in reversed(msgs)
    )[:12000]

    prompt = (
        f"Analyze messages from {len(groups)} Telegram group(s) over the last 24 hours.\n"
        f"Groups: {', '.join(group_title_map.values())}\n\nMessages:\n{context}"
    )

    try:
        summary = call_ai_text(key_info, GROUP_ANALYSIS_SYSTEM, prompt)
    except Exception as exc:
        _log.warning("group_query AI call failed: %s", exc)
        group_counts = Counter(m.telegram_group_id for m in msgs)
        lines = [
            f"Group: {group_title_map.get(gid, gid)}\nStatus: Active\n"
            f"Issues: {count} messages in last 24h (AI analysis unavailable)"
            for gid, count in group_counts.items()
        ]
        return {"reply": "Group activity (last 24h):\n\n" + "\n\n".join(lines),
                "intent": "group_query", "data": {"groups_checked": len(groups), "messages_scanned": len(msgs)}}

    try:
        from ...integrations.dispatcher import fire_event
        fire_event(user_id, "group.issue.detected",
                   {"groups_checked": len(groups), "messages_scanned": len(msgs), "summary_preview": summary[:500]})
    except Exception:
        pass

    return {"reply": f"Group intelligence report (last 24h):\n\n{summary}",
            "intent": "group_query", "data": {"groups_checked": len(groups), "messages_scanned": len(msgs)}}
