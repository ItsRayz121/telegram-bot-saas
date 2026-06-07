"""
Automation workflow engine.

Called from bot event handlers with a trigger type and context data.
Evaluates conditions, executes actions, logs the execution.

Usage (async context — inside official_bot handlers):
    from .automation.engine import fire_trigger
    await fire_trigger(
        flask_app=flask_app,
        bot=context.bot,
        trigger_type="message_received",
        group_id=group_id,
        trigger_data={"text": message.text, "user_id": str(sender_id)},
    )
"""
import logging
from datetime import datetime, timedelta

_log = logging.getLogger(__name__)

# ── Condition evaluators ──────────────────────────────────────────────────────

def _check_conditions(conditions: list, trigger_data: dict) -> bool:
    """Return True if all conditions pass (AND logic)."""
    for cond in conditions:
        ctype = cond.get("type")
        params = cond.get("params", {})
        if ctype == "message_contains":
            keyword = (params.get("keyword") or "").lower()
            text = (trigger_data.get("text") or "").lower()
            if keyword and keyword not in text:
                return False
        elif ctype == "message_starts_with":
            keyword = (params.get("keyword") or "").lower()
            text = (trigger_data.get("text") or "").lower()
            if keyword and not text.startswith(keyword):
                return False
        # Unknown conditions pass through
    return True


# ── Action executors ──────────────────────────────────────────────────────────

async def _execute_action(bot, action: dict, workflow, trigger_data: dict, flask_app):
    atype = action.get("type")
    params = action.get("params", {})

    # Anti-ban governor (D7): every outbound send — DM, group post, forward —
    # is throttled and flood-aware, exactly like the forwarding runtime.
    from .anti_ban import get_governor
    governor = get_governor(bot)

    if atype == "send_dm" or atype == "notify_admin_dm":
        msg = params.get("message") or "Automation triggered."
        try:
            with flask_app.app_context():
                from ..models import TelegramGroup, User
                tg = TelegramGroup.query.filter_by(
                    telegram_group_id=workflow.source_group_id
                ).first()
                owner = User.query.get(tg.owner_user_id) if tg else None
                owner_tg_id = owner.telegram_user_id if owner else None
            # Send outside the app context, through the governor.
            if owner_tg_id:
                await governor.send(
                    owner_tg_id,
                    lambda: bot.send_message(chat_id=int(owner_tg_id), text=msg),
                )
        except Exception as exc:
            _log.debug("send_dm action failed: %s", exc)

    elif atype == "send_group_message":
        msg = params.get("message") or "Automated message."
        if workflow.source_group_id:
            try:
                await governor.send(
                    workflow.source_group_id,
                    lambda: bot.send_message(chat_id=workflow.source_group_id, text=msg),
                )
            except Exception as exc:
                _log.debug("send_group_message action failed: %s", exc)

    elif atype == "forward_message":
        dest = params.get("destination_id")
        if dest and trigger_data.get("message_id") and trigger_data.get("chat_id"):
            try:
                await governor.send(
                    dest,
                    lambda: bot.copy_message(
                        chat_id=dest,
                        from_chat_id=trigger_data["chat_id"],
                        message_id=int(trigger_data["message_id"]),
                    ),
                )
            except Exception as exc:
                _log.debug("forward_message action failed: %s", exc)

    elif atype == "create_reminder":
        text = params.get("text") or "Automated reminder"
        delay_minutes = int(params.get("delay_minutes", 60))
        try:
            with flask_app.app_context():
                from ..models import db, TelegramGroup, User, WorkspaceReminder
                tg = TelegramGroup.query.filter_by(
                    telegram_group_id=workflow.source_group_id
                ).first()
                owner = User.query.get(tg.owner_user_id) if tg else None
                if owner:
                    remind_at = datetime.utcnow() + timedelta(minutes=delay_minutes)
                    db.session.add(WorkspaceReminder(
                        owner_user_id=owner.id,
                        telegram_group_id=workflow.source_group_id,
                        reminder_text=text[:500],
                        remind_at=remind_at,
                    ))
                    db.session.commit()
        except Exception as exc:
            _log.debug("create_reminder action failed: %s", exc)

    elif atype == "ban_sender":
        user_id = trigger_data.get("user_id")
        if user_id and workflow.source_group_id:
            try:
                await bot.ban_chat_member(
                    chat_id=workflow.source_group_id, user_id=int(user_id)
                )
            except Exception as exc:
                _log.debug("ban_sender action failed: %s", exc)

    elif atype == "delete_message":
        msg_id = trigger_data.get("message_id")
        if msg_id and workflow.source_group_id:
            try:
                await bot.delete_message(
                    chat_id=workflow.source_group_id, message_id=int(msg_id)
                )
            except Exception as exc:
                _log.debug("delete_message action failed: %s", exc)


# ── Main entry point ──────────────────────────────────────────────────────────

async def fire_trigger(flask_app, bot, trigger_type: str, group_id: str,
                       trigger_data: dict | None = None):
    """
    Evaluate and execute all active workflows that match the trigger
    for the given group. Called from bot event handlers.
    """
    trigger_data = trigger_data or {}
    try:
        with flask_app.app_context():
            from ..models import db, AutomationWorkflow, AutomationExecution

            workflows = AutomationWorkflow.query.filter_by(
                source_group_id=group_id,
                is_active=True,
            ).all()

            for wf in workflows:
                if (wf.trigger or {}).get("type") != trigger_type:
                    continue

                # Condition check
                if not _check_conditions(wf.conditions or [], trigger_data):
                    db.session.add(AutomationExecution(
                        workflow_id=wf.id,
                        trigger_type=trigger_type,
                        source_group_id=group_id,
                        trigger_data=trigger_data,
                        status="skipped",
                    ))
                    db.session.commit()
                    continue

                # Execute all actions
                status = "success"
                error_msg = None
                for action in (wf.actions or []):
                    try:
                        await _execute_action(bot, action, wf, trigger_data, flask_app)
                    except Exception as exc:
                        status = "failed"
                        error_msg = str(exc)[:500]
                        _log.debug("Automation action failed wf=%s: %s", wf.id, exc)

                wf.run_count = (wf.run_count or 0) + 1
                wf.last_run_at = datetime.utcnow()
                db.session.add(AutomationExecution(
                    workflow_id=wf.id,
                    trigger_type=trigger_type,
                    source_group_id=group_id,
                    trigger_data=trigger_data,
                    status=status,
                    error_msg=error_msg,
                ))
                db.session.commit()

                # AI Activity (Automation chip) — best-effort, never breaks the run.
                from ..ai_activity import log_ai_activity
                log_ai_activity(
                    "official", str(group_id), "automation",
                    f"Workflow ran: {wf.name or ('#' + str(wf.id))}",
                    detail=f"trigger={trigger_type}; {len(wf.actions or [])} action(s)",
                    status="ok" if status == "success" else "failed",
                    source="workflow",
                )

    except Exception as exc:
        _log.debug("fire_trigger(%s) failed for group %s: %s", trigger_type, group_id, exc)
