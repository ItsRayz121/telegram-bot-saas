import os
import uuid
import threading
import logging
import logging.config
from datetime import datetime, timedelta
from flask import Flask, jsonify, g, request
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from sqlalchemy import text
from .config import Config
from .models import db
from .routes.auth import auth_bp


def _configure_logging():
    """Set up structured JSON logging for production."""
    try:
        from pythonjsonlogger import jsonlogger
        handler = logging.StreamHandler()
        fmt = jsonlogger.JsonFormatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%SZ",
        )
        handler.setFormatter(fmt)
        root = logging.getLogger()
        root.handlers = [handler]
        root.setLevel(logging.INFO)
    except ImportError:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )


_configure_logging()
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
from .routes.referrals import referrals_bp
from .routes.digest import digest_bp, run_digest_scheduler
from .routes.notifications import notifications_bp
from .bot_manager import BotManager

_scheduler_log = logging.getLogger(__name__)

bot_manager = BotManager()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Lock CORS to explicit origins in production; allow * only in development.
    # Set FRONTEND_URL and/or ALLOWED_ORIGINS (comma-separated) in Railway env.
    import os as _os
    _allowed_origins_env = _os.environ.get("ALLOWED_ORIGINS", "")
    _allowed = [o.strip() for o in _allowed_origins_env.split(",") if o.strip()]
    if not _allowed:
        _frontend_url = _os.environ.get("FRONTEND_URL", "http://localhost:3000")
        _allowed = [_frontend_url]
        # Also allow localhost variants in development
        if "localhost" in _frontend_url or "127.0.0.1" in _frontend_url:
            _allowed += [
                "http://localhost:3000",
                "http://localhost:5000",
                "http://127.0.0.1:3000",
            ]
    CORS(app,
         origins=_allowed,
         allow_headers=["Content-Type", "Authorization"],
         methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
         supports_credentials=True)
    db.init_app(app)
    jwt = JWTManager(app)

    @jwt.token_in_blocklist_loader
    def _check_token_revoked(jwt_header, jwt_payload):
        from .routes.auth import is_token_revoked
        return is_token_revoked(jwt_payload)

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
    app.register_blueprint(referrals_bp)
    app.register_blueprint(digest_bp)
    app.register_blueprint(notifications_bp)

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

    @app.before_request
    def _assign_request_id():
        g.request_id = str(uuid.uuid4())[:8]

    def _err(msg, code, http_status, **extra):
        body = {"error": msg, "code": code, "request_id": getattr(g, "request_id", "")}
        body.update(extra)
        return jsonify(body), http_status

    @app.errorhandler(400)
    def bad_request(e):
        return _err("Bad request", "BAD_REQUEST", 400)

    @app.errorhandler(401)
    def unauthorized(e):
        return _err("Authentication required", "UNAUTHORIZED", 401)

    @app.errorhandler(403)
    def forbidden(e):
        return _err("Forbidden", "FORBIDDEN", 403)

    @app.errorhandler(404)
    def not_found(e):
        return _err("Not found", "NOT_FOUND", 404)

    @app.errorhandler(405)
    def method_not_allowed(e):
        return _err("Method not allowed", "METHOD_NOT_ALLOWED", 405)

    @app.errorhandler(422)
    def unprocessable(e):
        return _err("Unprocessable entity", "UNPROCESSABLE", 422)

    @app.errorhandler(429)
    def too_many_requests(e):
        return _err("Too many requests — please slow down", "RATE_LIMITED", 429)

    @app.errorhandler(500)
    def server_error(e):
        error_id = str(uuid.uuid4())[:8]
        _scheduler_log.error("Unhandled 500 error_id=%s path=%s: %s", error_id, request.path, e, exc_info=True)
        return jsonify({
            "error": "An unexpected error occurred. Please try again.",
            "code": "INTERNAL_ERROR",
            "error_id": error_id,
        }), 500

    with app.app_context():
        db.create_all()
        _run_migrations()
        _run_referral_migrations()
        _run_bot_token_encryption_migration()
        _run_payment_history_migration()
        _run_index_migrations()

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


def _run_referral_migrations():
    """Add referral_code column to users if it doesn't exist yet."""
    migrations = [
        "ALTER TABLE users ADD COLUMN referral_code VARCHAR(16)",
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_referral_code ON users (referral_code)",
    ]
    try:
        with db.engine.connect() as conn:
            for sql in migrations:
                try:
                    conn.execute(text(sql))
                    conn.commit()
                except Exception:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
    except Exception:
        pass


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
        # Billing period for annual vs monthly subscriptions
        "ALTER TABLE payment_history ADD COLUMN billing_period VARCHAR(10) DEFAULT 'monthly'",
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


def _run_index_migrations():
    """Add performance indexes for high-traffic queries."""
    indexes = [
        "CREATE INDEX IF NOT EXISTS ix_audit_logs_timestamp ON audit_logs (timestamp DESC)",
        "CREATE INDEX IF NOT EXISTS ix_audit_logs_group_ts ON audit_logs (group_id, timestamp DESC)",
        "CREATE INDEX IF NOT EXISTS ix_audit_logs_action ON audit_logs (action_type)",
        "CREATE INDEX IF NOT EXISTS ix_members_group_xp ON members (group_id, xp DESC)",
        "CREATE INDEX IF NOT EXISTS ix_members_joined_at ON members (joined_at)",
        "CREATE INDEX IF NOT EXISTS ix_scheduled_messages_send_at ON scheduled_messages (send_at) WHERE is_sent = FALSE",
        "CREATE INDEX IF NOT EXISTS ix_scheduled_messages_is_sent ON scheduled_messages (is_sent)",
        "CREATE INDEX IF NOT EXISTS ix_polls_scheduled_at ON polls (scheduled_at) WHERE is_sent = FALSE",
        "CREATE INDEX IF NOT EXISTS ix_payment_history_user_id ON payment_history (user_id)",
        "CREATE INDEX IF NOT EXISTS ix_referrals_referrer ON referrals (referrer_user_id)",
    ]
    try:
        with db.engine.connect() as conn:
            for sql in indexes:
                try:
                    conn.execute(text(sql))
                    conn.commit()
                except Exception:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
    except Exception:
        pass


def _run_payment_history_migration():
    """Create payment_history table and add indexes if they don't exist."""
    migrations = [
        """CREATE TABLE IF NOT EXISTS payment_history (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            provider VARCHAR(50) NOT NULL,
            payment_id VARCHAR(255),
            plan VARCHAR(50) NOT NULL,
            amount_usd INTEGER,
            currency VARCHAR(10),
            status VARCHAR(30) NOT NULL DEFAULT 'confirmed',
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            confirmed_at TIMESTAMP,
            metadata JSONB
        )""",
        "CREATE INDEX IF NOT EXISTS ix_payment_history_user_created ON payment_history (user_id, created_at DESC)",
    ]
    try:
        with db.engine.connect() as conn:
            for sql in migrations:
                try:
                    conn.execute(text(sql))
                    conn.commit()
                except Exception:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
    except Exception:
        pass


def _run_bot_token_encryption_migration():
    """Add bot_token_hash column and encrypt any plain-text bot tokens on startup."""
    from .utils.encryption import encrypt_value, hash_token, decrypt_value
    column_migrations = [
        "ALTER TABLE bots ADD COLUMN bot_token_hash VARCHAR(64)",
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_bots_bot_token_hash ON bots (bot_token_hash)",
    ]
    try:
        with db.engine.connect() as conn:
            for sql in column_migrations:
                try:
                    conn.execute(text(sql))
                    conn.commit()
                except Exception:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
    except Exception:
        pass

    # Encrypt any existing plain-text tokens and populate hashes.
    try:
        from .models import Bot
        bots = Bot.query.all()
        changed = False
        for bot in bots:
            plain = decrypt_value(bot.bot_token)
            need_encrypt = plain == bot.bot_token  # decrypt returned unchanged → was plain
            need_hash = not bot.bot_token_hash
            if need_encrypt or need_hash:
                if need_encrypt:
                    bot.bot_token = encrypt_value(plain) or plain
                bot.bot_token_hash = hash_token(plain)
                changed = True
        if changed:
            db.session.commit()
            _scheduler_log.info("[MIGRATION] Bot token encryption applied to existing rows")
    except Exception as exc:
        _scheduler_log.error(f"[MIGRATION] Bot token encryption failed: {exc}")
        try:
            db.session.rollback()
        except Exception:
            pass


def _restart_active_bots(app):
    from .models import Bot
    try:
        active_bots = Bot.query.filter_by(is_active=True).all()
        for bot in active_bots:
            bot_manager.start_bot(bot.id, bot.get_token(), app)
    except Exception:
        pass


def _scheduler_loop(app):
    import time
    _last_expiry_check = [0]
    time.sleep(15)  # Wait for bots to fully start
    while True:
        try:
            with app.app_context():
                _run_scheduled_messages()
                _run_scheduled_polls()
                # Check subscription expiry warnings every 6 hours
                now_ts = time.time()
                if now_ts - _last_expiry_check[0] > 6 * 3600:
                    _last_expiry_check[0] = now_ts
                    _run_expiry_notifications()
            try:
                run_digest_scheduler(app)
            except Exception as exc:
                _scheduler_log.error(f"Digest scheduler error: {exc}")
        except Exception as exc:
            _scheduler_log.error(f"Scheduler loop error: {exc}")
        time.sleep(60)


def _run_expiry_notifications():
    """Send in-app expiry warning notifications at 5-day and 1-day marks."""
    from .models import User, UserNotification
    from .routes.notifications import create_notification
    now = datetime.utcnow()
    five_days = now + timedelta(days=5)
    one_day = now + timedelta(days=1)
    try:
        expiring_soon = User.query.filter(
            User.subscription_expires.isnot(None),
            User.subscription_tier != "free",
            User.subscription_expires > now,
            User.subscription_expires <= five_days,
        ).all()
        for user in expiring_soon:
            days_left = (user.subscription_expires - now).days
            notif_type = "plan_expiring_1d" if days_left <= 1 else "plan_expiring_5d"
            # Avoid duplicate notifications within 12 hours
            recent = UserNotification.query.filter(
                UserNotification.user_id == user.id,
                UserNotification.type == notif_type,
                UserNotification.created_at >= now - timedelta(hours=12),
            ).first()
            if recent:
                continue
            label = "tomorrow" if days_left <= 1 else f"in {days_left} days"
            create_notification(
                user.id, notif_type,
                "Subscription Expiring Soon",
                f"Your {user.subscription_tier.capitalize()} plan expires {label} "
                f"({user.subscription_expires.strftime('%Y-%m-%d')}). Renew now to avoid interruption.",
                {"expires": user.subscription_expires.isoformat(), "days_left": days_left},
            )
    except Exception as exc:
        _scheduler_log.error(f"Expiry notification error: {exc}")


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
