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
            # ── Verification expiry cleanup ────────────────────────────────
            "expire-pending-verifications": {
                "task": "backend.scheduler.expire_pending_verifications",
                "schedule": 300.0,  # every 5 minutes
            },
            # ── 1-C-03: Pending unban retry ────────────────────────────────
            "retry-pending-unbans": {
                "task": "backend.scheduler.retry_pending_unbans",
                "schedule": 60.0,   # every 1 minute
            },
            # ── 1-A-03: Subscription expiry downgrade ──────────────────────
            "downgrade-expired-subscriptions": {
                "task": "backend.scheduler.downgrade_expired_subscriptions",
                "schedule": crontab(hour=1, minute=0),  # daily at 01:00 UTC
            },
            # ── 1-A-04: Renewal reminder emails ───────────────────────────
            "send-renewal-reminders": {
                "task": "backend.scheduler.send_renewal_reminders",
                "schedule": crontab(hour=9, minute=0),  # daily at 09:00 UTC
            },
            # ── Maintenance (Phase 6) ───────────────────────────────────────
            "cleanup-message-buffer": {
                "task": "backend.scheduler.cleanup_message_buffer",
                "schedule": crontab(hour=3, minute=0),  # daily at 03:00 UTC
            },
            # ── 1-I-01: Payment recovery ────────────────────────────────────
            "recover-missed-payments": {
                "task": "backend.scheduler.recover_missed_payments",
                "schedule": 1800.0,  # every 30 minutes
            },
            # ── 2-D-01: Trial expiry ─────────────────────────────────────────
            "expire-trials": {
                "task": "backend.scheduler.expire_trials",
                "schedule": crontab(hour=0, minute=30),  # daily at 00:30 UTC
            },
            # ── 2-C-01: Lifecycle email campaigns ────────────────────────────
            "send-lifecycle-emails": {
                "task": "backend.scheduler.send_lifecycle_emails",
                "schedule": crontab(hour=10, minute=0),  # daily at 10:00 UTC
            },
            # ── Assistant Hub retention enforcement ───────────────────────────
            "hub-enforce-retention": {
                "task": "backend.scheduler.hub_enforce_retention",
                "schedule": crontab(hour=3, minute=15),  # daily at 03:15 UTC
            },
            # ── Assistant Hub extraction pipeline ─────────────────────────────
            "hub-batch-extraction": {
                "task": "backend.scheduler.hub_run_batch_extraction",
                "schedule": 1800.0,   # every 30 minutes
            },
            "hub-priority-extraction": {
                "task": "backend.scheduler.hub_run_priority_extraction",
                "schedule": 120.0,    # every 2 minutes
            },
            # ── Assistant Hub notification delivery ───────────────────────────
            "hub-deliver-reminders": {
                "task": "backend.scheduler.hub_deliver_due_reminders",
                "schedule": 300.0,    # every 5 minutes
            },
            "hub-send-daily-digests": {
                "task": "backend.scheduler.hub_send_daily_digests",
                "schedule": 600.0,    # every 10 minutes (checks if digest time reached per user)
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
                        send_kw = {
                            "chat_id": g.telegram_group_id,
                            "text": txt,
                            "parse_mode": "Markdown",
                        }
                        topic_id = (g.settings or {}).get("default_topic_id") if g.is_forum else None
                        if topic_id:
                            send_kw["message_thread_id"] = int(topic_id)
                        await b.application.bot.send_message(**send_kw)
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
                        lines.append(f"  • {r.reminder_text[:60]} at {t}")

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
    """Delete MessageBuffer records older than 72 hours per privacy policy. Runs nightly at 03:00 UTC."""
    try:
        from .models import db, MessageBuffer
        from datetime import datetime, timedelta

        cutoff = datetime.utcnow() - timedelta(hours=72)
        deleted = MessageBuffer.query.filter(MessageBuffer.created_at < cutoff).delete()
        db.session.commit()
        logger.info("[celery:cleanup_message_buffer] deleted=%d rows older than 72h", deleted)
    except Exception as exc:
        logger.error("cleanup_message_buffer error: %s", exc)


@celery.task(name="backend.scheduler.expire_pending_verifications")
def expire_pending_verifications():
    """
    Find expired pending verifications, kick the user if kick_on_fail is set,
    delete the challenge message, and remove the DB row. Runs every 5 minutes.
    """
    try:
        from .models import db, PendingVerification
        from datetime import datetime
        import asyncio
        import telegram

        now = datetime.utcnow()
        expired = PendingVerification.query.filter(
            PendingVerification.expires_at <= now
        ).all()

        if not expired:
            return

        from .app import create_app as _ca
        _app = _ca()

        async def _process(records):
            for rec in records:
                try:
                    bot = telegram.Bot(token=_get_bot_token_for_chat(rec.chat_id, _app))
                except Exception:
                    continue

                # Delete challenge message from group
                if rec.msg_id and rec.auto_delete_on_timeout:
                    try:
                        await bot.delete_message(chat_id=rec.chat_id, message_id=rec.msg_id)
                    except Exception as e:
                        logger.debug("expire_verif: delete msg failed chat=%s msg=%s: %s",
                                     rec.chat_id, rec.msg_id, e)

                # Kick the user if configured
                if rec.kick_on_fail:
                    try:
                        await bot.ban_chat_member(chat_id=rec.chat_id, user_id=rec.user_id)
                        await bot.unban_chat_member(chat_id=rec.chat_id, user_id=rec.user_id)
                        logger.info("expire_verif: kicked user=%s from chat=%s", rec.user_id, rec.chat_id)
                    except Exception as e:
                        logger.warning("expire_verif: kick failed chat=%s user=%s: %s",
                                       rec.chat_id, rec.user_id, e)

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_process(expired))
        finally:
            loop.close()

        # Remove expired rows
        ids = [r.id for r in expired]
        PendingVerification.query.filter(PendingVerification.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()
        logger.info("[celery:expire_pending_verifications] expired=%d", len(ids))

    except Exception as exc:
        logger.error("expire_pending_verifications error: %s", exc, exc_info=True)


@celery.task(name="backend.scheduler.retry_pending_unbans")
def retry_pending_unbans():
    """1-C-03: Run every minute. Unban users whose temp ban has expired."""
    try:
        from .app import create_app
        app = create_app()
        with app.app_context():
            from .models import db, PendingUnban
            import os
            import telegram as _tg
            from datetime import datetime

            now = datetime.utcnow()
            pending = PendingUnban.query.filter(
                PendingUnban.success == False,
                PendingUnban.unban_at <= now,
                PendingUnban.retry_count < 5,
            ).all()

            if not pending:
                return

            bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
            if not bot_token:
                logger.warning("[retry_pending_unbans] TELEGRAM_BOT_TOKEN not set")
                return

            import asyncio

            async def _process(records):
                bot = _tg.Bot(token=bot_token)
                for record in records:
                    try:
                        await bot.unban_chat_member(
                            chat_id=record.telegram_chat_id,
                            user_id=record.telegram_user_id,
                            only_if_banned=True,
                        )
                        record.success = True
                    except Exception as exc:
                        record.retry_count += 1
                        record.last_attempt_at = now
                        logger.warning("Unban retry %d failed chat=%s user=%s: %s",
                                       record.retry_count, record.telegram_chat_id,
                                       record.telegram_user_id, exc)

            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(_process(pending))
            finally:
                loop.close()

            db.session.commit()
            success_count = sum(1 for r in pending if r.success)
            logger.info("[celery:retry_pending_unbans] processed=%d success=%d", len(pending), success_count)

    except Exception as exc:
        logger.error("retry_pending_unbans error: %s", exc)


@celery.task(name="backend.scheduler.downgrade_expired_subscriptions")
def downgrade_expired_subscriptions():
    """1-A-03: Daily 01:00 UTC. Downgrade users whose grace period has passed."""
    try:
        from .app import create_app
        app = create_app()
        with app.app_context():
            from .models import db, User, UserNotification
            from datetime import datetime

            now = datetime.utcnow()
            expired = User.query.filter(
                User.subscription_tier != "free",
                User.subscription_grace_until.isnot(None),
                User.subscription_grace_until < now,
            ).all()

            for user in expired:
                user.subscription_tier = "free"
                user.subscription_expires_at = None
                user.subscription_grace_until = None
                user.subscription_expires = None
                db.session.add(UserNotification(
                    user_id=user.id,
                    type="subscription_expired",
                    title="Subscription Expired",
                    message="Your Pro subscription has expired. Upgrade to restore access.",
                ))

            db.session.commit()
            logger.info("[celery:downgrade_expired_subscriptions] downgraded=%d", len(expired))
    except Exception as exc:
        logger.error("downgrade_expired_subscriptions error: %s", exc)


@celery.task(name="backend.scheduler.send_renewal_reminders")
def send_renewal_reminders():
    """1-A-04: Daily 09:00 UTC. Send renewal reminder emails at 7, 3, and 1 day before expiry."""
    try:
        from .app import create_app
        app = create_app()
        with app.app_context():
            from .models import db, User
            from .notifications import send_subscription_expiry_warning
            from datetime import datetime, timedelta, date

            today = datetime.utcnow().date()
            for days_before in [7, 3, 1]:
                target_date = today + timedelta(days=days_before)
                users = User.query.filter(
                    User.subscription_tier != "free",
                    db.func.date(User.subscription_expires_at) == target_date,
                ).all()
                for user in users:
                    try:
                        expires_str = user.subscription_expires_at.strftime("%Y-%m-%d")
                        send_subscription_expiry_warning(
                            user.email,
                            user.full_name or user.email.split("@")[0],
                            user.subscription_tier,
                            expires_str,
                            days_before,
                        )
                    except Exception as exc:
                        logger.error("renewal reminder failed user=%s days=%d: %s", user.id, days_before, exc)

            logger.info("[celery:send_renewal_reminders] done")
    except Exception as exc:
        logger.error("send_renewal_reminders error: %s", exc)


@celery.task(name="backend.scheduler.recover_missed_payments")
def recover_missed_payments():
    """
    1-I-01: Re-check stale unprocessed NOWPayments invoices every 30 minutes.
    Covers the case where the IPN was not delivered (server downtime, network error).
    """
    try:
        from .models import db, User, PendingInvoice, ProcessedPayment
        from .config import Config
        from .routes.billing import _activate_subscription, _claim_dedup
        import requests as _req
        from datetime import timedelta
        from sqlalchemy.exc import IntegrityError

        if not Config.NOWPAYMENTS_API_KEY:
            return

        cutoff = datetime.utcnow() - timedelta(minutes=5)
        stale = PendingInvoice.query.filter(
            PendingInvoice.processed == False,  # noqa: E712
            PendingInvoice.created_at < cutoff,
        ).all()

        recovered = 0
        for invoice in stale:
            try:
                resp = _req.get(
                    f"https://api.nowpayments.io/v1/invoice/{invoice.invoice_id}",
                    headers={"x-api-key": Config.NOWPAYMENTS_API_KEY},
                    timeout=10,
                )
                if not resp.ok:
                    continue
                data = resp.json()
                status = data.get("status", data.get("payment_status", ""))
                if status not in ("finished", "confirmed"):
                    continue

                dedup_key = f"np:invoice:{invoice.invoice_id}:recovery"
                if not _claim_dedup(dedup_key):
                    invoice.processed = True
                    db.session.commit()
                    continue

                user = User.query.get(invoice.user_id)
                if not user:
                    continue

                try:
                    amount = float(invoice.amount_usd) if invoice.amount_usd else None
                except Exception:
                    amount = None

                invoice.processed = True
                _activate_subscription(
                    user,
                    invoice.tier or "pro",
                    provider="nowpayments_recovery",
                    payment_id=str(invoice.invoice_id),
                    amount_usd=amount,
                    billing_period=invoice.billing_period or "monthly",
                )
                recovered += 1
                logger.info("[recover_missed_payments] Recovered invoice %s for user %d", invoice.invoice_id, user.id)
            except Exception as exc:
                logger.error("[recover_missed_payments] Error for invoice %s: %s", invoice.invoice_id, exc)

        if recovered:
            logger.info("[recover_missed_payments] Total recovered=%d", recovered)
    except Exception as exc:
        logger.error("recover_missed_payments error: %s", exc)


@celery.task(name="backend.scheduler.expire_trials")
def expire_trials():
    """2-D-01: Downgrade users whose 14-day Pro trial has ended without a paid subscription."""
    try:
        from .models import db, User
        from .notifications import send_subscription_expired
        now = datetime.utcnow()
        expired = User.query.filter(
            User.trial_ends_at != None,  # noqa: E711
            User.trial_ends_at < now,
            User.subscription_tier == "pro",
            User.subscription_expires_at == None,  # noqa: E711 — not a paid subscriber
        ).all()
        for user in expired:
            user.subscription_tier = "free"
            user.trial_ends_at = None
            try:
                send_subscription_expired(user.email, user.full_name or user.email.split("@")[0], "Pro Trial")
            except Exception as exc:
                logger.debug("trial expiry email failed user=%s: %s", user.id, exc)
        if expired:
            db.session.commit()
            logger.info("[expire_trials] downgraded=%d", len(expired))
    except Exception as exc:
        logger.error("expire_trials error: %s", exc)


@celery.task(name="backend.scheduler.send_lifecycle_emails")
def send_lifecycle_emails():
    """2-C-01: Daily lifecycle email campaigns at 10:00 UTC."""
    try:
        from .models import db, User, TelegramGroup, Bot
        from .notifications import (
            send_onboarding_day3_email, send_onboarding_day7_email,
            send_subscription_expired,
        )
        from datetime import timedelta
        now = datetime.utcnow()

        def _window(days):
            return now - timedelta(days=days + 1), now - timedelta(days=days)

        # Day 1 — no bot connected yet
        lo, hi = _window(1)
        day1 = User.query.filter(
            User.email_verified == True,  # noqa: E712
            User.created_at.between(lo, hi),
        ).all()
        for u in day1:
            has_bot = Bot.query.filter_by(user_id=u.id).first()
            if not has_bot:
                try:
                    send_onboarding_day3_email(u.email, u.full_name or u.email.split("@")[0])
                except Exception as exc:
                    logger.debug("day1_no_bot email failed user=%s: %s", u.id, exc)

        # Day 3 — no group linked
        lo, hi = _window(3)
        day3 = User.query.filter(
            User.created_at.between(lo, hi),
        ).all()
        for u in day3:
            has_group = TelegramGroup.query.filter_by(owner_user_id=u.id).first()
            if not has_group:
                try:
                    send_onboarding_day7_email(u.email, u.full_name or u.email.split("@")[0])
                except Exception as exc:
                    logger.debug("day3_no_group email failed user=%s: %s", u.id, exc)

        # Day 14 — on free tier (trial ended), Pro feature showcase
        lo, hi = _window(14)
        day14 = User.query.filter(
            User.subscription_tier == "free",
            User.trial_used == True,  # noqa: E712
            User.created_at.between(lo, hi),
        ).all()
        for u in day14:
            try:
                send_subscription_expired(u.email, u.full_name or u.email.split("@")[0], "Pro Trial")
            except Exception as exc:
                logger.debug("day14_upgrade email failed user=%s: %s", u.id, exc)

        logger.info("[lifecycle_emails] day1=%d day3=%d day14=%d", len(day1), len(day3), len(day14))
    except Exception as exc:
        logger.error("send_lifecycle_emails error: %s", exc)


@celery.task(name="backend.scheduler.hub_enforce_retention")
def hub_enforce_retention():
    """Assistant Hub: daily data retention enforcement at 03:15 UTC."""
    try:
        from .assistant.hub_retention import enforce_retention
        enforce_retention()
    except Exception as exc:
        logger.error("hub_enforce_retention error: %s", exc)


@celery.task(name="backend.scheduler.hub_run_batch_extraction")
def hub_run_batch_extraction():
    """Assistant Hub: standard extraction — all groups with buffered messages (every 30 min)."""
    try:
        from .assistant.hub_message_router import get_groups_with_buffered_messages
        from .assistant.hub_extraction import run_extraction
        from .app import create_app
        flask_app = create_app()
        pairs = get_groups_with_buffered_messages(priority_only=False)
        for bot_id, group_id in pairs:
            try:
                run_extraction(bot_id, group_id, flask_app)
            except Exception as exc:
                logger.error("hub_run_batch_extraction bot=%s group=%s: %s", bot_id, group_id, exc)
        logger.info("hub_run_batch_extraction: processed %d groups", len(pairs))
    except Exception as exc:
        logger.error("hub_run_batch_extraction error: %s", exc)


@celery.task(name="backend.scheduler.hub_run_priority_extraction")
def hub_run_priority_extraction():
    """Assistant Hub: priority extraction — groups with urgent messages (every 2 min)."""
    try:
        from .assistant.hub_message_router import get_groups_with_buffered_messages
        from .assistant.hub_extraction import run_extraction
        from .app import create_app
        flask_app = create_app()
        pairs = get_groups_with_buffered_messages(priority_only=True)
        for bot_id, group_id in pairs:
            try:
                run_extraction(bot_id, group_id, flask_app)
            except Exception as exc:
                logger.error("hub_run_priority_extraction bot=%s group=%s: %s", bot_id, group_id, exc)
        logger.info("hub_run_priority_extraction: processed %d priority groups", len(pairs))
    except Exception as exc:
        logger.error("hub_run_priority_extraction error: %s", exc)


@celery.task(name="backend.scheduler.hub_deliver_due_reminders")
def hub_deliver_due_reminders():
    """Assistant Hub: deliver reminders due within next 5 minutes (every 5 min)."""
    try:
        from .assistant.hub_digest import deliver_due_reminders
        from .app import create_app
        flask_app = create_app()
        sent = deliver_due_reminders(flask_app)
        if sent:
            logger.info("hub_deliver_due_reminders: sent=%d", sent)
    except Exception as exc:
        logger.error("hub_deliver_due_reminders error: %s", exc)


@celery.task(name="backend.scheduler.hub_send_daily_digests")
def hub_send_daily_digests():
    """Assistant Hub: send daily digests to users whose configured time has passed (every 10 min)."""
    try:
        from .assistant.hub_digest import deliver_all_due_digests
        from .app import create_app
        flask_app = create_app()
        sent = deliver_all_due_digests(flask_app)
        if sent:
            logger.info("hub_send_daily_digests: sent=%d digests", sent)
    except Exception as exc:
        logger.error("hub_send_daily_digests error: %s", exc)


def _get_bot_token_for_chat(chat_id, app):
    """Return the decrypted bot token for whichever bot manages this chat. Raises if not found."""
    with app.app_context():
        from .models import Group, Bot, CustomBot, TelegramGroup
        # Check custom bot runner
        group = Group.query.filter_by(telegram_group_id=str(chat_id)).first()
        if group:
            bot = Bot.query.get(group.bot_id)
            if bot:
                return bot.get_token()
        # Check official bot
        import os
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        if token:
            return token
    raise ValueError(f"No bot token found for chat_id={chat_id}")
