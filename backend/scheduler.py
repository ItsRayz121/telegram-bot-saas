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
    try:
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
    try:
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
