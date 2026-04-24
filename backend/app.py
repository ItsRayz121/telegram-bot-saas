import os
import threading
import logging
from datetime import datetime, timedelta
from flask import Flask, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from sqlalchemy import text
from .config import Config
from .models import db
from .routes.auth import auth_bp
from .routes.bots import bots_bp
from .routes.settings import settings_bp
from .routes.billing import billing_bp
from .routes.analytics import analytics_bp
from .routes.admin import admin_bp
from .routes.knowledge import knowledge_bp
from .routes.polls import polls_bp
from .routes.webhooks import webhooks_bp
from .routes.invites import invites_bp
from .routes.api_keys import api_keys_bp
from .bot_manager import BotManager

_scheduler_log = logging.getLogger(__name__)

bot_manager = BotManager()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    CORS(app,
         origins="*",
         allow_headers=["Content-Type", "Authorization"],
         methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"])
    db.init_app(app)
    JWTManager(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(bots_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(billing_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(knowledge_bp)
    app.register_blueprint(polls_bp)
    app.register_blueprint(webhooks_bp)
    app.register_blueprint(invites_bp)
    app.register_blueprint(api_keys_bp)

    app.bot_manager = bot_manager

    @app.route("/health")
    def health():
        db_ok = False
        try:
            db.session.execute(text("SELECT 1"))
            db_ok = True
        except Exception:
            pass
        return jsonify({
            "status": "ok",
            "db": "connected" if db_ok else "error",
            "version": "2026-04-22-v5",
        })

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(500)
    def server_error(e):
        return jsonify({"error": "Internal server error"}), 500

    with app.app_context():
        db.create_all()
        _run_migrations()

    # Start bots in a background thread after a short delay so Gunicorn can
    # pass its healthcheck before bot polling (which may contact Telegram and
    # hold DB connections) begins.
    def _deferred_bot_start():
        import time
        time.sleep(5)
        with app.app_context():
            _restart_active_bots(app)

    threading.Thread(target=_deferred_bot_start, daemon=True).start()

    # In-process scheduler: runs every 60 s inside the web process so that
    # scheduled messages and polls are delivered even when no separate Celery
    # worker is running on Railway.
    threading.Thread(target=_scheduler_loop, args=(app,), daemon=True).start()

    return app


def _run_migrations():
    """Add any missing columns to existing tables without dropping data.
    Uses plain ALTER TABLE (no IF NOT EXISTS) so it works on both PostgreSQL
    and SQLite — duplicate-column errors are silently caught and ignored.
    """
    migrations = [
        "ALTER TABLE groups ADD COLUMN telegram_member_count INTEGER DEFAULT 0",
        # Invite link creator tracking
        "ALTER TABLE invite_links ADD COLUMN created_by_user_id INTEGER",
        "ALTER TABLE invite_links ADD COLUMN created_by_telegram_id VARCHAR(255)",
        "ALTER TABLE invite_links ADD COLUMN created_by_username VARCHAR(255)",
        # Scheduled messages extra columns added in later commits
        "ALTER TABLE scheduled_messages ADD COLUMN topic_id BIGINT",
        "ALTER TABLE scheduled_messages ADD COLUMN auto_delete_after INTEGER",
        "ALTER TABLE scheduled_messages ADD COLUMN link_preview_enabled BOOLEAN DEFAULT TRUE",
        # User API keys extra columns
        "ALTER TABLE user_api_keys ADD COLUMN base_url VARCHAR(500)",
        "ALTER TABLE user_api_keys ADD COLUMN model_name VARCHAR(255)",
        "ALTER TABLE user_api_keys ADD COLUMN updated_at TIMESTAMP",
        # Backfill NULL updated_at for rows added before the column existed
        "UPDATE user_api_keys SET updated_at = created_at WHERE updated_at IS NULL",
        # Wallet submission columns
        "ALTER TABLE members ADD COLUMN wallet_address VARCHAR(500)",
        "ALTER TABLE members ADD COLUMN wallet_submitted_at TIMESTAMP",
        # Timezone support
        "ALTER TABLE scheduled_messages ADD COLUMN timezone VARCHAR(50) DEFAULT 'UTC'",
        "ALTER TABLE polls ADD COLUMN timezone VARCHAR(50) DEFAULT 'UTC'",
        # Dedicated timezone column on groups (previously only in settings JSON)
        "ALTER TABLE groups ADD COLUMN timezone VARCHAR(50) DEFAULT 'UTC'",
    ]
    try:
        with db.engine.connect() as conn:
            for sql in migrations:
                try:
                    conn.execute(text(sql))
                    conn.commit()
                except Exception:
                    # Column already exists or table not yet created — safe to skip
                    try:
                        conn.rollback()
                    except Exception:
                        pass
    except Exception:
        pass


def _restart_active_bots(app):
    from .models import Bot
    try:
        active_bots = Bot.query.filter_by(is_active=True).all()
        for bot in active_bots:
            bot_manager.start_bot(bot.id, bot.bot_token, app)
    except Exception:
        pass


def _scheduler_loop(app):
    import time
    time.sleep(15)  # Wait for bots to fully start
    while True:
        try:
            with app.app_context():
                _run_scheduled_messages()
                _run_scheduled_polls()
        except Exception as exc:
            _scheduler_log.error(f"Scheduler loop error: {exc}")
        time.sleep(60)


def _run_scheduled_messages():
    import asyncio
    from .models import db, ScheduledMessage, Group, Bot

    # Acquire a PostgreSQL session-level advisory lock so that only one
    # gunicorn worker (or Railway instance) processes scheduled messages at
    # a time. This is a safety net — the Procfile already enforces --workers 1.
    # pg_try_advisory_xact_lock holds for the duration of the current
    # transaction; it is released automatically on commit/rollback.
    # On SQLite or if the DB is unreachable, this is silently skipped.
    try:
        locked = db.session.execute(
            text("SELECT pg_try_advisory_xact_lock(2001)")
        ).scalar()
        if not locked:
            _scheduler_log.debug("[SCHEDULER] Skipping scheduled messages — another worker holds the lock")
            return
    except Exception:
        pass  # Non-PostgreSQL DB (e.g. SQLite in dev) — proceed without lock

    now = datetime.utcnow()
    pending = ScheduledMessage.query.filter(
        ScheduledMessage.send_at <= now,
        ScheduledMessage.is_sent == False,
    ).all()

    if pending:
        _scheduler_log.info(f"[SCHEDULER] {len(pending)} scheduled message(s) due at {now.strftime('%Y-%m-%d %H:%M:%S')} UTC")

    for msg in pending:
        group = Group.query.get(msg.group_id)
        if not group:
            _scheduler_log.warning(f"[SCHEDULER] msg id={msg.id} skipped — group {msg.group_id} not found")
            continue
        bot = Bot.query.get(group.bot_id)
        if not bot or not bot.is_active:
            _scheduler_log.warning(f"[SCHEDULER] msg id={msg.id} skipped — bot not active for group {group.id}")
            continue
        instance = bot_manager.active_bots.get(bot.id)
        if not instance or not instance.application:
            _scheduler_log.warning(
                f"[SCHEDULER] msg id={msg.id} title='{msg.title}' skipped — "
                f"bot {bot.id} not running (active_bots={list(bot_manager.active_bots.keys())})"
            )
            continue

        # Effective timezone: per-item → group.timezone column → settings JSON → UTC
        effective_tz = (
            msg.timezone
            or group.timezone
            or (group.settings or {}).get("timezone", "UTC")
            or "UTC"
        )
        _scheduler_log.info(
            f"[SCHEDULER] Sending msg id={msg.id} title='{msg.title}' "
            f"tz={effective_tz} send_at_utc={msg.send_at} group={group.id}"
        )

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
                    import asyncio as _as
                    await _as.sleep(m.auto_delete_after)
                    await b.application.bot.delete_message(
                        chat_id=g.telegram_group_id,
                        message_id=sent.message_id,
                    )
            except Exception as exc:
                _scheduler_log.error(f"Scheduled message {m.id} send error: {exc}")

        loop = instance.loop
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(_send(), loop)

        if msg.repeat_interval:
            msg.send_at = now + timedelta(minutes=msg.repeat_interval)
            if msg.stop_date and msg.send_at > msg.stop_date:
                msg.is_sent = True
        else:
            msg.is_sent = True

    if pending:
        db.session.commit()
        _scheduler_log.info(f"[SCHEDULER] Finished processing {len(pending)} scheduled messages")


def _run_scheduled_polls():
    import asyncio
    from .models import db, Poll, Group, Bot

    # Same advisory lock pattern as _run_scheduled_messages — different lock ID.
    try:
        locked = db.session.execute(
            text("SELECT pg_try_advisory_xact_lock(2002)")
        ).scalar()
        if not locked:
            _scheduler_log.debug("[SCHEDULER] Skipping scheduled polls — another worker holds the lock")
            return
    except Exception:
        pass

    now = datetime.utcnow()
    pending = Poll.query.filter(
        Poll.scheduled_at <= now,
        Poll.scheduled_at != None,
        Poll.is_sent == False,
    ).all()

    if pending:
        _scheduler_log.info(f"[SCHEDULER] {len(pending)} scheduled poll(s) due at {now.strftime('%Y-%m-%d %H:%M:%S')} UTC")

    for poll in pending:
        group = Group.query.get(poll.group_id)
        if not group:
            _scheduler_log.warning(f"[SCHEDULER] poll id={poll.id} skipped — group {poll.group_id} not found")
            continue
        bot = Bot.query.get(group.bot_id)
        if not bot or not bot.is_active:
            _scheduler_log.warning(f"[SCHEDULER] poll id={poll.id} skipped — bot not active for group {group.id}")
            continue
        instance = bot_manager.active_bots.get(bot.id)
        if not instance or not instance.application:
            _scheduler_log.warning(
                f"[SCHEDULER] poll id={poll.id} skipped — "
                f"bot {bot.id} not running (active_bots={list(bot_manager.active_bots.keys())})"
            )
            continue

        effective_tz = (
            poll.timezone
            or group.timezone
            or (group.settings or {}).get("timezone", "UTC")
            or "UTC"
        )
        _scheduler_log.info(
            f"[SCHEDULER] Sending poll id={poll.id} q='{poll.question[:40]}' "
            f"tz={effective_tz} scheduled_at_utc={poll.scheduled_at} group={group.id}"
        )

        async def _send(p=poll, g=group, b=instance):
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
                await b.application.bot.send_poll(**kwargs)
            except Exception as exc:
                _scheduler_log.error(f"Scheduled poll {p.id} send error: {exc}")

        loop = instance.loop
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(_send(), loop)

        poll.is_sent = True

    if pending:
        db.session.commit()
        _scheduler_log.info(f"[SCHEDULER] Finished processing {len(pending)} scheduled polls")


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
