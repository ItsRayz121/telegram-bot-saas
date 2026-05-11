"""
Global escalation service.

Any AI or Automation subsystem calls `trigger_escalation()` when it cannot
confidently handle a situation.  Admin DM replies are processed by
`handle_admin_reply()` which optionally feeds the answer back into the KB.

Issue types
-----------
  ai_kb       — KB auto-reply confidence below threshold
  ai_image    — image AI confidence below threshold
  automation  — scheduled post / poll / command execution failure
  command     — unknown/unrecognised bot command
  moderation  — moderation system uncertainty

Admin DM format
---------------
  [header message with metadata]
  [forwarded original message OR quoted text]

  The header message_id is stored in EscalationEvent.admin_dm_refs so that
  when an admin replies-to that header, we can match it back to the event.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# ── Helpers ───────────────────────────────────────────────────────────────────

_ISSUE_LABELS = {
    "ai_kb":      "🤖 AI Knowledge Base",
    "ai_image":   "🖼️ AI Image Review",
    "automation": "⚙️ Automation",
    "command":    "📌 Bot Command",
    "moderation": "🛡️ Moderation",
}

_ISSUE_EMOJI = {
    "ai_kb":      "🤖",
    "ai_image":   "🖼️",
    "automation": "⚙️",
    "command":    "📌",
    "moderation": "🛡️",
}

# Prefix embedded in the header DM so we can distinguish escalation replies
_ESCALATION_MARKER = "⚠️ *Escalation #"


def _get_escalation_settings(group_settings: dict) -> dict:
    """Return merged escalation config.  Global key wins; falls back to image_ai legacy."""
    esc = group_settings.get("escalation", {})
    if not esc.get("enabled") and not esc.get("admin_ids"):
        # backward-compat: inherit from image_ai if global not yet configured
        img = group_settings.get("image_ai", {})
        if img.get("escalation_enabled") and img.get("escalation_admin_ids"):
            return {
                "enabled": True,
                "admin_ids": img["escalation_admin_ids"],
                "types": ["ai_kb", "ai_image", "automation", "command"],
                "auto_learn": True,
            }
    return esc


# ── Core trigger ──────────────────────────────────────────────────────────────

async def trigger_escalation(
    bot,                          # telegram.Bot instance
    group_settings: dict,         # group.settings dict
    issue_type: str,              # see _ISSUE_LABELS keys
    original_content: str,        # question / command / caption
    context_data: dict,           # {confidence, group_name, user_id, username, thread_id, ...}
    app,                          # Flask app for DB context
    group_id: int | None = None,
    telegram_group_id: str | None = None,
    bot_id: int | None = None,
    original_message=None,        # telegram.Message to forward (optional)
) -> int | None:
    """
    Send escalation DMs to all configured admins and record the event.
    Returns the EscalationEvent.id, or None if escalation is skipped.
    """
    esc = _get_escalation_settings(group_settings)
    if not esc.get("enabled", False):
        return None

    active_types = esc.get("types", ["ai_kb", "ai_image", "automation", "command"])
    if issue_type not in active_types:
        return None

    admin_ids = esc.get("admin_ids", [])
    if not admin_ids:
        return None

    group_name = context_data.get("group_name", "Unknown group")
    user_id    = context_data.get("user_id", "")
    username   = context_data.get("username", "")
    confidence = context_data.get("confidence")
    thread_id  = context_data.get("thread_id")

    user_str = f"@{username}" if username else (str(user_id) if user_id else "Unknown")
    label    = _ISSUE_LABELS.get(issue_type, issue_type.replace("_", " ").title())

    # Record in DB first so we have an event id
    event_id = None
    with app.app_context():
        try:
            from ..models import db, EscalationEvent
            ev = EscalationEvent(
                group_id=group_id,
                telegram_group_id=str(telegram_group_id) if telegram_group_id else None,
                bot_id=bot_id,
                issue_type=issue_type,
                user_telegram_id=str(user_id) if user_id else None,
                user_username=username or None,
                original_content=original_content[:4000] if original_content else None,
                context_data=context_data,
                status="pending",
                admin_dm_refs=[],
            )
            db.session.add(ev)
            db.session.commit()
            event_id = ev.id
        except Exception as exc:
            logger.error("escalation: DB write failed: %s", exc)

    if event_id is None:
        return None

    # Build header message
    conf_str = f"{int(confidence * 100)}%" if confidence is not None else "N/A"
    preview  = (original_content or "")[:300]
    if len(original_content or "") > 300:
        preview += "…"

    header = (
        f"{_ESCALATION_MARKER}{event_id}* — {label}\n\n"
        f"👤 *User:* {user_str}\n"
        f"📍 *Group:* {group_name}\n"
        f"🏷️ *Issue:* {label}\n"
    )
    if confidence is not None:
        header += f"🎯 *Confidence:* {conf_str}\n"
    if thread_id:
        header += f"📂 *Thread ID:* {thread_id}\n"
    header += f"\n💬 *Content:*\n`{preview}`\n\n"
    header += "↩️ _Reply to this message with an answer to resolve & auto-learn._"

    dm_refs = []
    for admin_id in admin_ids:
        try:
            sent = await bot.send_message(
                chat_id=int(admin_id),
                text=header,
                parse_mode="Markdown",
            )
            dm_refs.append({"admin_id": str(admin_id), "msg_id": sent.message_id})

            # Forward original Telegram message if available
            if original_message:
                try:
                    await bot.forward_message(
                        chat_id=int(admin_id),
                        from_chat_id=original_message.chat_id,
                        message_id=original_message.message_id,
                    )
                except Exception:
                    pass
        except Exception as exc:
            logger.debug("escalation: DM to admin %s failed: %s", admin_id, exc)

    # Persist DM refs for reply matching
    with app.app_context():
        try:
            from ..models import db, EscalationEvent
            ev = EscalationEvent.query.get(event_id)
            if ev:
                ev.admin_dm_refs = dm_refs
                db.session.commit()
        except Exception as exc:
            logger.warning("escalation: failed to save dm_refs: %s", exc)

    logger.info("escalation: event #%s type=%s group=%s admins=%s",
                event_id, issue_type, telegram_group_id, len(dm_refs))
    return event_id


# ── Admin reply handler ───────────────────────────────────────────────────────

def handle_admin_reply(
    reply_text: str,
    admin_telegram_id: str,
    replied_to_message_id: int,
    app,
    bot_id: int | None = None,
) -> bool:
    """
    Call this when an admin sends a DM reply to the bot.  Detects whether the
    reply targets an escalation header, resolves the event, and optionally
    feeds the answer into the KB.

    Returns True if the reply was linked to an escalation event.
    """
    with app.app_context():
        try:
            from ..models import db, EscalationEvent
            from ..bot_features.knowledge_base import KnowledgeBaseSystem

            # Find event where admin_dm_refs contains the replied-to message id
            events = EscalationEvent.query.filter_by(status="pending").all()
            target_event = None
            for ev in events:
                refs = ev.admin_dm_refs or []
                for ref in refs:
                    if (str(ref.get("admin_id")) == str(admin_telegram_id)
                            and ref.get("msg_id") == replied_to_message_id):
                        target_event = ev
                        break
                if target_event:
                    break

            if not target_event:
                return False

            # Resolve
            target_event.status = "resolved"
            target_event.resolved_admin_telegram_id = str(admin_telegram_id)
            target_event.admin_answer = reply_text
            target_event.resolved_at = datetime.utcnow()
            db.session.commit()
            logger.info("escalation: event #%s resolved by admin %s",
                        target_event.id, admin_telegram_id)

            # Auto-learn into KB if enabled
            group_settings = {}
            if target_event.group_id:
                try:
                    from ..models import Group
                    grp = Group.query.get(target_event.group_id)
                    if grp:
                        group_settings = grp.settings or {}
                except Exception:
                    pass

            esc = _get_escalation_settings(group_settings)
            if esc.get("auto_learn", True) and target_event.original_content and reply_text:
                _auto_learn(target_event, reply_text, app)

            return True

        except Exception as exc:
            logger.error("escalation: handle_admin_reply failed: %s", exc)
            return False


def _auto_learn(event, answer: str, app) -> None:
    """Store escalation Q&A as a KB document for future auto-replies."""
    try:
        from ..models import db, EscalationEvent, KnowledgeDocument
        import json

        # Build a small markdown doc
        label = _ISSUE_LABELS.get(event.issue_type, event.issue_type)
        doc_text = (
            f"# Escalation Q&A [{label}]\n\n"
            f"**Question:** {event.original_content}\n\n"
            f"**Answer:** {answer}\n\n"
            f"*Learned from admin resolution on {datetime.utcnow().strftime('%Y-%m-%d')}*"
        )

        kd = KnowledgeDocument(
            group_id=event.group_id,
            title=f"[Auto-learned] {(event.original_content or '')[:80]}",
            source_type="escalation_learn",
            raw_text=doc_text,
            metadata_={
                "escalation_id": event.id,
                "issue_type": event.issue_type,
                "admin_id": event.resolved_admin_telegram_id,
            },
        )
        db.session.add(kd)

        # Mark event as learned
        event.learned = True
        db.session.commit()
        logger.info("escalation: auto-learned event #%s into KB", event.id)
    except Exception as exc:
        logger.warning("escalation: auto_learn failed: %s", exc)
