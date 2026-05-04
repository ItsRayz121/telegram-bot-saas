import logging
from datetime import datetime
from celery import Celery
from celery.schedules import crontab

logger = logging.getLogger(__name__)


def make_celery(app=None):
    import os
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    celery = Celery(
        "telegram_saas",
        broker=redis_url,
        backend=redis_url,
    )

    celery.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        beat_schedule={
            "send-scheduled-messages": {
                "task": "backend.scheduler.send_scheduled_messages",
                "schedule": 60.0,
            },
            "check-raid-reminders": {
                "task": "backend.scheduler.check_raid_reminders",
                "schedule": 300.0,
            },
            "send-scheduled-polls": {
                "task": "backend.scheduler.send_scheduled_polls",
                "schedule": 60.0,
            },
            "send-onboarding-emails": {
                "task": "backend.scheduler.send_onboarding_emails",
                "schedule": crontab(hour=10, minute=0),  # daily at 10:00 UTC
            },
            # ── Assistant proactive delivery (Phase 1) ──────────────────────
            "deliver-due-reminders": {
                "task": "backend.scheduler.deliver_due_reminders",
                "schedule": 60.0,   # every 1 minute
            },
            "send-meeting-prealerts": {
                "task": "backend.scheduler.send_meeting_prealerts",
                "schedule": 120.0,  # every 2 minutes
            },
            # ── Group intelligence pipeline (Phase 3) ──────────────────────
            "extract-group-signals": {
                "task": "backend.scheduler.extract_group_signals",
                "schedule": 7200.0,  # every 2 hours
            },
            "send-daily-briefings": {
                "task": "backend.scheduler.send_daily_briefings",
                "schedule": crontab(hour=8, minute=0),  # daily at 08:00 UTC
            },
            "check-group-health": {
                "task": "backend.scheduler.check_group_health",
                "schedule": 1800.0,  # every 30 minutes
            },
            "check-inactive-groups": {
                "task": "backend.scheduler.check_inactive_groups",
                "schedule": crontab(hour=9, minute=30),  # daily at 09:30 UTC
            },
            # ── Maintenance (Phase 6) ───────────────────────────────────────
            "cleanup-message-buffer": {
                "task": "backend.scheduler.cleanup_message_buffer",
                "schedule": crontab(hour=3, minute=0),  # daily at 03:00 UTC
            },
        },
    )

    if app:
        class ContextTask(celery.Task):
            def __call__(self, *args, **kwargs):
                with app.app_context():
                    return self.run(*args, **kwargs)
        celery.Task = ContextTask

    return celery


celery = make_celery()


@celery.task(name="backend.scheduler.send_scheduled_messages")
def send_scheduled_messages():
    # NOTE: Delivery is handled by the in-process _scheduler_loop in app.py which
    # has direct access to the running bot instances.  Celery workers run in a
    # separate process where bot_manager.active_bots is always empty, so sending
    # from here would silently skip every job.  This task is kept as a no-op so
    # the beat schedule does not produce errors if a Celery worker is started.
    logger.info("[celery:send_scheduled_messages] deferred to in-process scheduler")
    return

    try:  # pragma: no cover – unreachable; kept for reference
        from .app import create_app
        app = create_app()

        with app.app_context():
            from .models import db, ScheduledMessage, Group, Bot
            from .bot_manager import bot_manager
            import asyncio

            now = datetime.utcnow()
            pending = ScheduledMessage.query.filter(
                ScheduledMessage.send_at <= now,
                ScheduledMessage.is_sent == False,
            ).all()

            for msg in pending:
                group = Group.query.get(msg.group_id)
                if not group:
                    continue

                bot = Bot.query.get(group.bot_id)
                if not bot or not bot.is_active:
                    continue

                instance = bot_manager.active_bots.get(bot.id)
                if not instance or not instance.application:
                    continue

                async def _send(m=msg, g=group, b=instance):
                    try:
                        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

                        keyboard = None
                        if m.buttons:
                            rows = []
                            for row in m.buttons:
                                btn_row = []
                                for btn in row:
                                    if btn.get("url"):
                                        btn_row.append(InlineKeyboardButton(btn["text"], url=btn["url"]))
                                    else:
                                        btn_row.append(InlineKeyboardButton(btn["text"], callback_data=btn.get("callback_data", "noop")))
                                rows.append(btn_row)
                            keyboard = InlineKeyboardMarkup(rows)

                        send_kwargs = {
                            "chat_id": g.telegram_group_id,
                            "text": m.message_text,
                            "parse_mode": "Markdown",
                            "reply_markup": keyboard,
                            "disable_web_page_preview": not getattr(m, "link_preview_enabled", True),
                        }
                        if getattr(m, "topic_id", None):
                            send_kwargs["message_thread_id"] = m.topic_id
                        sent = await b.application.bot.send_message(**send_kwargs)

                        if m.pin_message:
                            await b.application.bot.pin_chat_message(
                                chat_id=g.telegram_group_id,
                                message_id=sent.message_id,
                            )

                        if m.auto_delete_after:
                            import asyncio as _asyncio
                            await _asyncio.sleep(m.auto_delete_after)
                            await b.application.bot.delete_message(
                                chat_id=g.telegram_group_id,
                                message_id=sent.message_id,
                            )
                    except Exception as e:
                        logger.error(f"Scheduled message send error: {e}")

                loop = instance.loop
                if loop and loop.is_running():
                    asyncio.run_coroutine_threadsafe(_send(), loop)

                if msg.repeat_interval:
                    from datetime import timedelta
                    msg.send_at = now + timedelta(minutes=msg.repeat_interval)
                    if msg.stop_date and msg.send_at > msg.stop_date:
                        msg.is_sent = True
                else:
                    msg.is_sent = True

            db.session.commit()
            logger.info(f"Processed {len(pending)} scheduled messages")

    except Exception as e:
        logger.error(f"send_scheduled_messages error: {e}")


@celery.task(name="backend.scheduler.send_scheduled_polls")
def send_scheduled_polls():
    logger.info("[celery:send_scheduled_polls] deferred to in-process scheduler")
    return

    try:  # pragma: no cover – unreachable; kept for reference
        from .app import create_app
        app = create_app()
        with app.app_context():
            from .models import db, Poll, Group, Bot
            from .bot_manager import bot_manager
            import asyncio

            now = datetime.utcnow()
            pending = Poll.query.filter(
                Poll.scheduled_at <= now,
                Poll.scheduled_at != None,
                Poll.is_sent == False,
            ).all()

            for poll in pending:
                group = Group.query.get(poll.group_id)
                if not group:
                    continue
                bot = Bot.query.get(group.bot_id)
                if not bot or not bot.is_active:
                    continue
                instance = bot_manager.active_bots.get(bot.id)
                if not instance or not instance.application:
                    continue

                async def _send(p=poll, g=group):
                    try:
                        kwargs = {
                            "chat_id": g.telegram_group_id,
                            "question": p.question,
                            "options": p.options,
                            "is_anonymous": p.is_anonymous,
                        }
                        if p.is_quiz:
                            kwargs["type"] = "quiz"
                            kwargs["correct_option_id"] = p.correct_option_index
                            if p.explanation:
                                kwargs["explanation"] = p.explanation
                        else:
                            kwargs["allows_multiple_answers"] = p.allows_multiple
                        await instance.application.bot.send_poll(**kwargs)
                    except Exception as e:
                        logger.error(f"Scheduled poll send error: {e}")

                loop = instance.loop
                if loop and loop.is_running():
                    asyncio.run_coroutine_threadsafe(_send(), loop)

                poll.is_sent = True

            db.session.commit()
    except Exception as e:
        logger.error(f"send_scheduled_polls error: {e}")


@celery.task(name="backend.scheduler.check_raid_reminders")
def check_raid_reminders():
    try:
        from .app import create_app
        app = create_app()

        with app.app_context():
            from .models import db, Raid, Group, Bot
            from .bot_manager import bot_manager
            import asyncio

            now = datetime.utcnow()
            active_raids = Raid.query.filter(
                Raid.is_active == True,
                Raid.ends_at > now,
                Raid.reminders_enabled == True,
            ).all()

            for raid in active_raids:
                time_left = (raid.ends_at - now).total_seconds() / 3600

                should_remind = False
                if 0.9 <= time_left <= 1.1:
                    should_remind = True
                elif 5.9 <= time_left <= 6.1:
                    should_remind = True

                if not should_remind:
                    continue

                group = Group.query.get(raid.group_id)
                if not group:
                    continue

                bot = Bot.query.get(group.bot_id)
                if not bot:
                    continue

                instance = bot_manager.active_bots.get(bot.id)
                if not instance:
                    continue

                time_str = "1 hour" if time_left <= 1.1 else "6 hours"
                goals_text = "\n".join(
                    f"• {goal}: {count}" for goal, count in raid.goals.items() if count > 0
                )
                reminder_text = (
                    f"⏰ *Raid Reminder* — {time_str} left!\n\n"
                    f"🐦 {raid.tweet_url}\n\n"
                    f"Goals:\n{goals_text}\n\n"
                    f"XP Reward: {raid.xp_reward} XP per goal completed"
                )

                async def _remind(txt=reminder_text, g=group, b=instance):
                    try:
                        await b.application.bot.send_message(
                            chat_id=g.telegram_group_id,
                            text=txt,
                            parse_mode="Markdown",
                        )
                    except Exception as e:
                        logger.error(f"Raid reminder error: {e}")

                loop = instance.loop
                if loop and loop.is_running():
                    asyncio.run_coroutine_threadsafe(_remind(), loop)

            expired = Raid.query.filter(
                Raid.is_active == True,
                Raid.ends_at <= now,
            ).all()

            for raid in expired:
                raid.is_active = False

            if expired:
                db.session.commit()

    except Exception as e:
        logger.error(f"check_raid_reminders error: {e}")


@celery.task(name="backend.scheduler.send_onboarding_emails")
def send_onboarding_emails():
    """Send day-3 and day-7 onboarding emails to users who haven't received them yet."""
    try:
        from .app import create_app
        app = create_app()

        with app.app_context():
            from .models import db, User
            from .notifications import send_onboarding_day3_email, send_onboarding_day7_email
            from datetime import timedelta

            now = datetime.utcnow()

            # Day-3: registered 3 days ago, onboarding_step < 2
            day3_cutoff = now - timedelta(days=3)
            day3_users = User.query.filter(
                User.created_at <= day3_cutoff,
                User.created_at > day3_cutoff - timedelta(hours=24),
                User.onboarding_emails_sent < 2,
                User.email_verified == True,
            ).all()
            for u in day3_users:
                try:
                    send_onboarding_day3_email(u.email, u.full_name or u.email.split("@")[0])
                    u.onboarding_emails_sent = max(u.onboarding_emails_sent or 0, 2)
                except Exception as exc:
                    logger.error("Day-3 email failed for %s: %s", u.email, exc)

            # Day-7: registered 7 days ago, onboarding_step < 3
            day7_cutoff = now - timedelta(days=7)
            day7_users = User.query.filter(
                User.created_at <= day7_cutoff,
                User.created_at > day7_cutoff - timedelta(hours=24),
                User.onboarding_emails_sent < 3,
                User.email_verified == True,
            ).all()
            for u in day7_users:
                try:
                    send_onboarding_day7_email(u.email, u.full_name or u.email.split("@")[0])
                    u.onboarding_emails_sent = max(u.onboarding_emails_sent or 0, 3)
                except Exception as exc:
                    logger.error("Day-7 email failed for %s: %s", u.email, exc)

            db.session.commit()
            logger.info("[celery:onboarding] day3=%d day7=%d", len(day3_users), len(day7_users))

    except Exception as e:
        logger.error(f"send_onboarding_emails error: {e}")


# ── Assistant proactive delivery helpers ──────────────────────────────────────

def _send_telegram_dm(telegram_user_id: str, text: str) -> bool:
    """Send a Telegram DM to a user via the platform bot. Returns True on success."""
    import os
    import requests as _r
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not bot_token or not telegram_user_id:
        return False
    try:
        resp = _r.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": telegram_user_id, "text": text, "parse_mode": "Markdown"},
            timeout=10,
        )
        return resp.ok
    except Exception as exc:
        logger.warning("_send_telegram_dm failed user=%s: %s", telegram_user_id, exc)
        return False


@celery.task(name="backend.scheduler.deliver_due_reminders")
def deliver_due_reminders():
    """
    Deliver WorkspaceReminder records whose remind_at has passed.
    Runs every 60 seconds. Marks delivered reminders so they aren't re-sent.
    """
    try:
        from .app import create_app
        app = create_app()
        with app.app_context():
            from .models import db, WorkspaceReminder, User, BotDMMessage
            from datetime import datetime, timedelta

            now = datetime.utcnow()
            # Grace window: deliver reminders up to 10 minutes late
            cutoff = now - timedelta(minutes=10)

            due = (
                WorkspaceReminder.query
                .filter(
                    WorkspaceReminder.remind_at <= now,
                    WorkspaceReminder.remind_at >= cutoff,
                    WorkspaceReminder.is_delivered == False,
                )
                .limit(50)
                .all()
            )

            if not due:
                return

            delivered = 0
            for reminder in due:
                user = User.query.get(reminder.owner_user_id)
                if not user:
                    reminder.is_delivered = True
                    continue

                text = f"🔔 *Reminder*\n\n{reminder.reminder_text}"
                sent = False

                # Try Telegram DM first (best experience)
                if user.telegram_user_id:
                    sent = _send_telegram_dm(user.telegram_user_id, text)

                # Log as BotDMMessage so it appears in web sidebar history
                try:
                    log = BotDMMessage(
                        user_id=user.id,
                        direction="out",
                        content=text,
                        intent="reminder_delivery",
                    )
                    db.session.add(log)
                except Exception:
                    pass

                reminder.is_delivered = True
                delivered += 1

            db.session.commit()
            if delivered:
                logger.info("[celery:reminders] delivered=%d", delivered)

    except Exception as exc:
        logger.error("deliver_due_reminders error: %s", exc)


@celery.task(name="backend.scheduler.send_meeting_prealerts")
def send_meeting_prealerts():
    """
    Send Telegram DM pre-alerts for meetings starting soon.
    Checks every 2 minutes. Sends alert when meeting is within its remind_before_minutes window.
    """
    try:
        from .app import create_app
        app = create_app()
        with app.app_context():
            from .models import db, Meeting, User, BotDMMessage
            from datetime import datetime, timedelta

            now = datetime.utcnow()

            # Find meetings whose alert window has just opened:
            # scheduled_at - remind_before_minutes is within the past 2 minutes
            # This means: remind_before_minutes ago <= now < scheduled_at
            meetings = Meeting.query.filter(
                Meeting.is_complete == False,
                Meeting.reminder_sent == False,
                Meeting.scheduled_at > now,
            ).all()

            alerted = 0
            for meeting in meetings:
                remind_mins = meeting.remind_before_minutes or 15
                alert_at = meeting.scheduled_at - timedelta(minutes=remind_mins)

                # Only fire if we're within the 2-minute polling window of alert_at
                if not (alert_at <= now <= alert_at + timedelta(minutes=2)):
                    continue

                user = User.query.get(meeting.owner_user_id)
                if not user:
                    meeting.reminder_sent = True
                    continue

                # Build alert text
                time_str = meeting.scheduled_at.strftime("%I:%M %p UTC")
                parts = [f"📅 *{meeting.title}* starts in {remind_mins} minutes ({time_str})"]
                if meeting.notes:
                    parts.append(f"📝 Notes: {meeting.notes[:150]}")
                if meeting.resources:
                    for r in (meeting.resources or [])[:2]:
                        parts.append(f"🔗 {r.get('value', '')[:80]}")
                text = "\n".join(parts)

                sent = False
                if user.telegram_user_id:
                    sent = _send_telegram_dm(user.telegram_user_id, text)

                # Log to BotDMMessage for sidebar visibility
                try:
                    log = BotDMMessage(
                        user_id=user.id,
                        direction="out",
                        content=text,
                        intent="meeting_prealert",
                    )
                    db.session.add(log)
                except Exception:
                    pass

                meeting.reminder_sent = True
                alerted += 1

            if alerted:
                db.session.commit()
                logger.info("[celery:meeting_prealerts] sent=%d", alerted)

    except Exception as exc:
        logger.error("send_meeting_prealerts error: %s", exc)


# ── Phase 3: Group intelligence pipeline ─────────────────────────────────────

@celery.task(name="backend.scheduler.extract_group_signals")
def extract_group_signals():
    """Run GroupSignalExtractor for all active groups. Runs every 2 hours."""
    try:
        from .assistant.group_signal_extractor import run_extraction
        run_extraction()
    except Exception as exc:
        logger.error("extract_group_signals error: %s", exc)


@celery.task(name="backend.scheduler.send_daily_briefings")
def send_daily_briefings():
    """Send a daily morning briefing DM to each active user via Telegram."""
    try:
        from .models import db, User, TelegramGroup, Meeting, WorkspaceReminder, GroupDailySignal
        from datetime import date, datetime, timedelta

        now = datetime.utcnow()
        today = date.today()
        tomorrow = today + timedelta(days=1)

        # Only users who have Telegram connected
        users = User.query.filter(User.telegram_user_id.isnot(None)).all()
        sent = 0
        for user in users:
            try:
                groups = TelegramGroup.query.filter_by(
                    owner_user_id=user.id, is_disabled=False
                ).all()

                # Today's meetings
                meetings = (
                    Meeting.query
                    .filter_by(user_id=user.id)
                    .filter(Meeting.scheduled_at >= datetime.combine(today, datetime.min.time()))
                    .filter(Meeting.scheduled_at < datetime.combine(tomorrow, datetime.min.time()))
                    .order_by(Meeting.scheduled_at.asc())
                    .limit(3)
                    .all()
                )

                # Due reminders today
                reminders = (
                    WorkspaceReminder.query
                    .filter_by(owner_user_id=user.id, is_delivered=False)
                    .filter(WorkspaceReminder.remind_at >= now)
                    .filter(WorkspaceReminder.remind_at < datetime.combine(tomorrow, datetime.min.time()))
                    .order_by(WorkspaceReminder.remind_at.asc())
                    .limit(3)
                    .all()
                )

                # Critical group signals
                critical_groups = []
                for g in groups:
                    sig = GroupDailySignal.query.filter_by(
                        telegram_group_id=g.telegram_group_id, date=today
                    ).first()
                    if sig and sig.health_status == "critical":
                        critical_groups.append((g.title, sig.ai_summary or sig.health_status))

                name = user.full_name.split()[0] if user.full_name else "there"
                lines = [f"☀️ Good morning, {name}! Here's your Telegizer briefing:"]

                if meetings:
                    lines.append(f"\n📅 Meetings today ({len(meetings)}):")
                    for m in meetings:
                        t = m.scheduled_at.strftime("%H:%M UTC") if m.scheduled_at else "TBD"
                        lines.append(f"  • {m.title} at {t}")
                else:
                    lines.append("\n📅 No meetings today")

                if reminders:
                    lines.append(f"\n🔔 Reminders due today ({len(reminders)}):")
                    for r in reminders:
                        t = r.remind_at.strftime("%H:%M UTC")
                        lines.append(f"  • {r.message[:60]} at {t}")

                if critical_groups:
                    lines.append("\n⚠️ Groups needing attention:")
                    for title, summary in critical_groups[:3]:
                        lines.append(f"  • {title}: {summary}")
                elif groups:
                    active = sum(1 for g in groups if g.bot_status == "active")
                    lines.append(f"\n👥 {len(groups)} group(s), {active} active — all looking healthy")

                lines.append("\nReply to me anytime to manage your workspace!")
                text = "\n".join(lines)

                if _send_telegram_dm(user.telegram_user_id, text):
                    sent += 1

            except Exception as exc:
                logger.warning("send_daily_briefings: user %s failed: %s", user.id, exc)
                continue

        logger.info("[celery:send_daily_briefings] sent=%d/%d", sent, len(users))

    except Exception as exc:
        logger.error("send_daily_briefings error: %s", exc)


@celery.task(name="backend.scheduler.check_group_health")
def check_group_health():
    """Alert users when a group's health status becomes critical. Runs every 30 min."""
    try:
        from .models import db, User, TelegramGroup, GroupDailySignal, BotDMMessage
        from datetime import date, datetime

        today = date.today()
        groups = TelegramGroup.query.filter_by(is_disabled=False).all()
        alerted = 0

        for group in groups:
            try:
                sig = GroupDailySignal.query.filter_by(
                    telegram_group_id=group.telegram_group_id, date=today
                ).first()
                if not sig or sig.health_status != "critical":
                    continue

                owner = User.query.get(group.owner_user_id) if group.owner_user_id else None
                if not owner or not owner.telegram_user_id:
                    continue

                # Rate-limit alerts — check if we already sent one today
                existing_alert = (
                    BotDMMessage.query
                    .filter_by(user_id=owner.id, intent="group_health_alert")
                    .filter(BotDMMessage.created_at >= datetime.utcnow().replace(hour=0, minute=0, second=0))
                    .filter(BotDMMessage.content.contains(group.title[:20]))
                    .first()
                )
                if existing_alert:
                    continue

                text = (
                    f"⚠️ Group Alert: *{group.title}*\n\n"
                    f"Status: {sig.health_status.upper()}\n"
                    f"Messages today: {sig.message_count} | Active members: {sig.active_members}\n"
                    f"Spam score: {sig.spam_score:.1f}/10 | Conflict score: {sig.conflict_score:.1f}/10\n"
                )
                if sig.ai_summary:
                    text += f"\n{sig.ai_summary}"

                _send_telegram_dm(owner.telegram_user_id, text)

                log = BotDMMessage(
                    user_id=owner.id,
                    direction="out",
                    content=text,
                    intent="group_health_alert",
                )
                db.session.add(log)
                alerted += 1

            except Exception as exc:
                logger.warning("check_group_health: group %s failed: %s", group.telegram_group_id, exc)
                continue

        if alerted:
            db.session.commit()
            logger.info("[celery:check_group_health] alerted=%d", alerted)

    except Exception as exc:
        logger.error("check_group_health error: %s", exc)


@celery.task(name="backend.scheduler.check_inactive_groups")
def check_inactive_groups():
    """Nudge users about groups with no activity in the last 7 days. Runs daily."""
    try:
        from .models import db, User, TelegramGroup, MessageBuffer, BotDMMessage
        from datetime import datetime, timedelta

        cutoff = datetime.utcnow() - timedelta(days=7)
        groups = TelegramGroup.query.filter_by(is_disabled=False, bot_status="active").all()
        nudged = 0

        for group in groups:
            try:
                recent = (
                    MessageBuffer.query
                    .filter_by(telegram_group_id=group.telegram_group_id)
                    .filter(MessageBuffer.created_at >= cutoff)
                    .first()
                )
                if recent:
                    continue  # Group is active

                owner = User.query.get(group.owner_user_id) if group.owner_user_id else None
                if not owner or not owner.telegram_user_id:
                    continue

                text = (
                    f"👋 Heads up: Your group *{group.title}* hasn't had any messages in 7+ days.\n\n"
                    "Consider posting an update or checking if the bot is still active in the group."
                )
                _send_telegram_dm(owner.telegram_user_id, text)

                log = BotDMMessage(
                    user_id=owner.id,
                    direction="out",
                    content=text,
                    intent="inactive_group_nudge",
                )
                db.session.add(log)
                nudged += 1

            except Exception as exc:
                logger.warning("check_inactive_groups: group %s failed: %s", group.telegram_group_id, exc)
                continue

        if nudged:
            db.session.commit()
            logger.info("[celery:check_inactive_groups] nudged=%d", nudged)

    except Exception as exc:
        logger.error("check_inactive_groups error: %s", exc)


@celery.task(name="backend.scheduler.cleanup_message_buffer")
def cleanup_message_buffer():
    """Delete MessageBuffer records older than 7 days. Runs nightly at 03:00 UTC."""
    try:
        from .models import db, MessageBuffer
        from datetime import datetime, timedelta

        cutoff = datetime.utcnow() - timedelta(days=7)
        deleted = MessageBuffer.query.filter(MessageBuffer.created_at < cutoff).delete()
        db.session.commit()
        logger.info("[celery:cleanup_message_buffer] deleted=%d rows older than 7d", deleted)
    except Exception as exc:
        logger.error("cleanup_message_buffer error: %s", exc)
