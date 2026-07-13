import hmac
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
from .routes.engagement_public import engagement_public_bp
from .routes.api_keys import api_keys_bp
from .routes.referrals import referrals_bp
from .routes.digest import digest_bp, run_digest_scheduler
from .routes.notifications import notifications_bp
from .routes.ui_prefs import ui_prefs_bp
from .routes.totp import totp_bp
from .routes.telegram_groups import tg_groups_bp
from .routes.custom_bots import custom_bots_bp
from .routes.custom_commands import custom_commands_bp
from .routes.bot_group_commands import bot_group_commands_bp
from .routes.telegram_account import telegram_account_bp
from .routes.official_settings import official_settings_bp
from .routes.workspace import workspace_bp
from .routes.forwarding import forwarding_bp
from .routes.telegram_webapp import miniapp_bp
from .routes.automations import automations_bp
from .routes.channels import channels_bp
from .routes.directory import directory_bp
from .routes.crm import crm_bp
from .routes.custom_bot_crm import custom_bot_crm_bp
from .routes.marketplace import marketplace_bp
from .routes.notes import notes_bp
from .routes.assistant import assistant_bp
from .routes.tasks import tasks_bp
from .routes.knowledge_workspace import knowledge_ws_bp
from .routes.assistant_bots import assistant_bots_bp
from .routes.telegram_updates import telegram_updates_bp
from .routes.meetings import meetings_bp
from .routes.integration_webhooks import integration_webhooks_bp
from .routes.hub import hub_bp
from .routes.platform_stats import platform_stats_bp
from .routes.calendar import calendar_bp
from .routes.team import team_bp
from .routes.blog import blog_bp
from .routes.chat import support_bp
from .assistant import hub_models as _hub_models_import  # noqa: F401 — ensures models registered with db.create_all()
from .bot_manager import BotManager
from .official_bot import start_official_bot
from .echo_bot import start_echo_bot

_scheduler_log = logging.getLogger(__name__)

bot_manager = BotManager()

# ── Graceful shutdown — stops all polling threads before the process exits ────
# Railway rolling deploys start the new container before killing the old one.
# Without a clean shutdown, Telegram holds the long-poll session open and the
# new container receives 409 Conflict errors for up to 60 seconds.
import atexit as _atexit
import signal as _signal


_shutdown_done = False


def _graceful_bot_shutdown(*_):
    """Stop all custom bot pollers/webhook listeners and unblock retry sleeps.

    Idempotent: atexit + the SIGTERM handler can both fire, but the work runs
    once. Stops polling first (so Telegram releases the long-poll session and
    the daemon threads finish their `finally` cleanup) which prevents the
    "cannot schedule new futures after interpreter shutdown" teardown race.
    """
    global _shutdown_done
    if _shutdown_done:
        return
    _shutdown_done = True
    try:
        from .integrations.dispatcher import signal_shutdown
        signal_shutdown()
    except Exception:
        pass
    try:
        bot_manager.stop_all(timeout_per_bot=8)
    except Exception as exc:
        logging.getLogger("shutdown").error("Graceful bot shutdown error: %s", exc)
    # Official + Echo bots run their own daemon-thread loops — stop them too so
    # they unwind cleanly instead of being abandoned on interpreter teardown.
    try:
        from .official_bot import stop_official_bot
        stop_official_bot(timeout=6)
    except Exception:
        pass
    try:
        from .echo_bot import stop_echo_bot
        stop_echo_bot(timeout=6)
    except Exception:
        pass


def _sigterm_handler(signum, frame):
    """SIGTERM: drain bots, then hand control back to the PREVIOUS handler.

    Critical for gunicorn: installing our own handler at import time replaces
    gunicorn's worker SIGTERM handler. If we don't chain back to it, the worker
    never exits on SIGTERM, gunicorn SIGKILLs it after --graceful-timeout, and
    the hard kill abandons the polling threads mid-await (the RuntimeError). By
    invoking the saved handler we let gunicorn shut the worker down cleanly.
    """
    _graceful_bot_shutdown()
    if callable(_prev_sigterm) and _prev_sigterm not in (_signal.SIG_DFL, _signal.SIG_IGN):
        try:
            _prev_sigterm(signum, frame)
            return
        except Exception:
            pass
    # No usable previous handler — exit cleanly so the process actually stops.
    raise SystemExit(0)


_atexit.register(_graceful_bot_shutdown)
# Also handle SIGTERM directly (gunicorn / Railway send this on graceful restart).
# Save the previous handler so we can chain back to it (see _sigterm_handler).
_prev_sigterm = _signal.SIG_DFL
try:
    _prev_sigterm = _signal.getsignal(_signal.SIGTERM)
    _signal.signal(_signal.SIGTERM, _sigterm_handler)
except (OSError, ValueError):
    pass  # SIGTERM cannot be set in some environments (Windows dev)


def _init_sentry():
    """Initialize Sentry error monitoring if SENTRY_DSN is configured."""
    dsn = os.environ.get("SENTRY_DSN", "")
    if not dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
        sentry_sdk.init(
            dsn=dsn,
            integrations=[FlaskIntegration(), SqlalchemyIntegration()],
            traces_sample_rate=0.1,
            send_default_pii=False,
        )
        _scheduler_log.info("Sentry initialized")
    except ImportError:
        _scheduler_log.warning("sentry-sdk not installed; Sentry disabled")
    except Exception as exc:
        _scheduler_log.warning("Sentry init failed: %s", exc)


_init_sentry()


# Set once the bots + scheduler thread are running, so a nested create_app() (or a
# second gunicorn import) can never start a duplicate set.
_BACKGROUND_THREADS_STARTED = False


def create_app():
    # Reuse the live app when we're already inside an app context.
    #
    # Every job in scheduler.py opens with `app = create_app()`. That was written
    # for a standalone Celery worker, but the jobs now also run inside the web
    # process via _scheduler_loop. Building a second Flask app there would re-run
    # every migration, start a duplicate set of Telegram bots, and spawn another
    # _scheduler_loop — per job, per tick. Returning the live app keeps the jobs
    # working unchanged in both places, and gives them the real bot_manager
    # instances (a fresh app's active_bots is always empty, so sends silently
    # no-op).
    from flask import has_app_context, current_app
    if has_app_context():
        return current_app._get_current_object()

    app = Flask(__name__)
    app.config.from_object(Config)

    # Hard cap on incoming request body size — prevents file-upload abuse and
    # memory exhaustion on any endpoint (Flask default is 16 MB, no cap).
    app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB (1-D-04)

    # JWT cookie configuration (1-D-01)
    import os as _jwt_os
    _is_prod_jwt = "postgres" in _jwt_os.environ.get("DATABASE_URL", "")
    app.config["JWT_TOKEN_LOCATION"] = ["headers", "cookies"]
    app.config["JWT_ACCESS_COOKIE_NAME"] = "access_token"
    app.config["JWT_REFRESH_COOKIE_NAME"] = "refresh_token"
    app.config["JWT_COOKIE_SECURE"] = _is_prod_jwt
    app.config["JWT_COOKIE_SAMESITE"] = "Strict"
    app.config["JWT_COOKIE_CSRF_PROTECT"] = False  # using own CSRF (1-D-02)

    # Never expose DEBUG mode in production — overrides any accidental env setting.
    import os as _os_debug
    app.config["DEBUG"] = _os_debug.environ.get("FLASK_DEBUG", "0") == "1" and \
        "postgres" not in _os_debug.environ.get("DATABASE_URL", "")

    # Lock CORS to explicit origins in production; allow localhost only in development.
    # Set FRONTEND_URL and/or ALLOWED_ORIGINS (comma-separated) in Railway env.
    import os as _os
    _allowed_origins_env = _os.environ.get("ALLOWED_ORIGINS", "")
    _allowed = [o.strip() for o in _allowed_origins_env.split(",") if o.strip()]
    _is_prod_db = "postgres" in _os.environ.get("DATABASE_URL", "")
    if not _allowed:
        _frontend_url = _os.environ.get("FRONTEND_URL", "http://localhost:3000")
        _allowed = [_frontend_url]
        # Only add localhost variants in development (non-postgres DB)
        if not _is_prod_db and ("localhost" in _frontend_url or "127.0.0.1" in _frontend_url):
            _allowed += [
                "http://localhost:3000",
                "http://localhost:5000",
                "http://127.0.0.1:3000",
            ]
    # Production safety: strip any localhost/127.0.0.1 origins that slipped in
    if _is_prod_db:
        _prod_allowed = [o for o in _allowed if "localhost" not in o and "127.0.0.1" not in o]
        if len(_prod_allowed) < len(_allowed):
            _scheduler_log.error(
                "[CORS] Removed localhost origins from allow-list in production. "
                "Set ALLOWED_ORIGINS or FRONTEND_URL to your production domain in Railway. "
                "Removed: %s", [o for o in _allowed if o not in _prod_allowed]
            )
        _allowed = _prod_allowed if _prod_allowed else _allowed  # never go empty
    # Startup assertion: reject wildcard or empty CORS config in production
    if _is_prod_db:
        if not _allowed:
            raise RuntimeError("CORS misconfiguration: ALLOWED_ORIGINS is empty in production. "
                               "Set ALLOWED_ORIGINS or FRONTEND_URL in Railway env.")
        _wildcards = [o for o in _allowed if "*" in o]
        if _wildcards:
            raise RuntimeError(f"CORS misconfiguration: wildcard origins not allowed in production: {_wildcards}")
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
    app.register_blueprint(engagement_public_bp)
    app.register_blueprint(api_keys_bp)
    app.register_blueprint(referrals_bp)
    app.register_blueprint(digest_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(ui_prefs_bp)
    app.register_blueprint(totp_bp)
    app.register_blueprint(tg_groups_bp)
    app.register_blueprint(custom_bots_bp)
    app.register_blueprint(custom_commands_bp)
    app.register_blueprint(bot_group_commands_bp)
    app.register_blueprint(telegram_account_bp)
    app.register_blueprint(official_settings_bp)
    app.register_blueprint(workspace_bp)
    app.register_blueprint(forwarding_bp)
    app.register_blueprint(miniapp_bp)
    app.register_blueprint(automations_bp)
    app.register_blueprint(channels_bp)
    app.register_blueprint(directory_bp)
    app.register_blueprint(crm_bp)
    app.register_blueprint(custom_bot_crm_bp)
    app.register_blueprint(marketplace_bp)
    app.register_blueprint(notes_bp)
    app.register_blueprint(assistant_bp)
    app.register_blueprint(tasks_bp)
    app.register_blueprint(knowledge_ws_bp)
    app.register_blueprint(assistant_bots_bp)
    app.register_blueprint(telegram_updates_bp)
    app.register_blueprint(meetings_bp)
    app.register_blueprint(integration_webhooks_bp)
    app.register_blueprint(hub_bp)
    app.register_blueprint(platform_stats_bp)
    app.register_blueprint(calendar_bp)
    app.register_blueprint(team_bp)
    app.register_blueprint(blog_bp)
    app.register_blueprint(support_bp)

    app.bot_manager = bot_manager

    # ── Custom bot Telegram webhook receiver ──────────────────────────────────
    @app.route("/api/telegram/custom/<int:bot_id>", methods=["POST"])
    def custom_bot_webhook_update(bot_id):
        """Receive Telegram updates for a custom bot running in webhook mode.

        Telegram sends X-Telegram-Bot-Api-Secret-Token header; we validate it
        against the per-bot webhook_secret stored in the DB before routing.
        """
        from .models import Bot
        secret_header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        bot_rec = Bot.query.get(bot_id)
        if not bot_rec or not bot_rec.webhook_secret:
            return jsonify({"error": "not found"}), 404
        if not hmac.compare_digest(secret_header, bot_rec.webhook_secret):
            return jsonify({"error": "forbidden"}), 403

        update_data = request.get_json(silent=True) or {}
        bot_manager.route_update(bot_id, update_data)
        return "", 200

    @app.route("/health")
    @app.route("/api/health")
    def health():
        db_ok = False
        try:
            db.session.execute(text("SELECT 1"))
            db_ok = True
        except Exception:
            pass
        bot_ok = getattr(app, "official_bot_instance", None) is not None
        return jsonify({
            "status": "ok",
            "db": "connected" if db_ok else "error",
            "db_status": "ok" if db_ok else "outage",
            "bot_status": "ok" if bot_ok else "degraded",
            "email_status": "ok",
            "version": Config.VERSION,
        })

    @app.route("/ready")
    def ready():
        """Kubernetes/Railway readiness probe — only 200 when all dependencies are up."""
        checks = {}
        ok = True

        # DB check
        try:
            db.session.execute(text("SELECT 1"))
            checks["db"] = "ok"
        except Exception as exc:
            checks["db"] = f"error: {exc}"
            ok = False

        # Redis check (non-fatal — app degrades gracefully without Redis)
        try:
            import redis as _redis
            r = _redis.from_url(Config.REDIS_URL, socket_connect_timeout=1)
            r.ping()
            checks["redis"] = "ok"
        except Exception:
            checks["redis"] = "unavailable"
            # Redis failure is a warning, not a fatal readiness failure

        status_code = 200 if ok else 503
        return jsonify({"ready": ok, "checks": checks}), status_code

    # ── Email verification gate ────────────────────────────────────────────────
    # All /api/ routes require email_verified=True except the whitelist below.
    # This is a server-side hard block — frontend routing is defence-in-depth.
    _VERIFY_EXEMPT_EXACT = frozenset({
        '/api/auth/login',
        '/api/auth/register',
        '/api/auth/logout',
        '/api/auth/verify-email',
        '/api/auth/resend-verification',
        '/api/auth/forgot-password',
        '/api/auth/reset-password',
        '/api/auth/verify-totp-login',
        '/api/auth/me',       # needed to fetch verification status on load
        '/health',
        '/ready',
    })
    _VERIFY_EXEMPT_PREFIX = ('/api/auth/2fa/',)  # 2FA setup (pre-verification OK)

    @app.before_request
    def _enforce_email_verification():
        path = request.path
        if path in _VERIFY_EXEMPT_EXACT:
            return None
        if path.startswith(_VERIFY_EXEMPT_PREFIX):
            return None
        if not path.startswith('/api/'):
            return None
        # Optionally parse JWT — does not raise if absent/invalid
        try:
            from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity, get_jwt
            verify_jwt_in_request(optional=True)
            uid = get_jwt_identity()
            if not uid:
                return None  # Unauthenticated — let the route return its own 401

            claims = get_jwt()
            scope = claims.get("scope")

            # Block totp_pending tokens from any endpoint except 2FA completion
            if scope == "totp_pending" and path != "/api/auth/verify-totp-login":
                return jsonify({
                    "error": "Two-factor authentication is required to access this resource.",
                    "code": "TOTP_REQUIRED",
                }), 403

            # Block email_verify_pending tokens from any endpoint except verify/resend
            _EMAIL_VERIFY_ALLOWED = {"/api/auth/verify-email", "/api/auth/resend-verification"}
            if scope == "email_verify_pending" and path not in _EMAIL_VERIFY_ALLOWED:
                return jsonify({
                    "error": "Please verify your email address before accessing this feature.",
                    "code": "EMAIL_NOT_VERIFIED",
                }), 403

            from .models import User as _User
            user = _User.query.get(int(uid))
            if user and not user.email_verified and scope != "email_verify_pending":
                # Telegram-only users authenticated via initData — no email to verify.
                is_telegram_only = user.auth_provider == "telegram" and not user.email
                if not is_telegram_only:
                    return jsonify({
                        "error": "Please verify your email address before accessing this feature. "
                                 "Check your inbox for the verification link.",
                        "code": "EMAIL_NOT_VERIFIED",
                    }), 403
        except Exception:
            pass  # Bad/missing token — route handles its own auth check
        return None

    # Maintenance mode: when enabled in platform config, non-admin API traffic is
    # paused with a 503. Auth, admin panel, billing, bot-ingestion and webhook
    # endpoints stay open so admins can manage the platform and bots keep working.
    # Inbound bot ingestion + webhook receivers MUST stay open during maintenance,
    # or Telegram/payment providers will retry and eventually disable the webhook.
    # Custom bots POST to /api/telegram/custom/<id> (bot_manager), hub bots to
    # /api/hub/webhook[/<id>], plus per-bot /api/tg-update/<hash>.
    _MAINT_EXEMPT_PREFIX = (
        '/api/auth/', '/api/admin/', '/api/billing/', '/api/integrations/',
        '/api/tg-update/', '/api/telegram/', '/api/webhooks/',
        '/api/hub/webhook', '/api/telegram-groups/webhook-trigger',
    )
    _MAINT_EXEMPT_EXACT = {
        '/health', '/ready', '/api/platform/config', '/api/platform-stats',
        '/api/platform/proof',
        '/api/official-bot-update', '/api/echo-bot-update', '/api/auth/me',
    }

    @app.before_request
    def _enforce_maintenance_mode():
        path = request.path
        if not path.startswith('/api/'):
            return None
        if path in _MAINT_EXEMPT_EXACT or path.startswith(_MAINT_EXEMPT_PREFIX):
            return None
        try:
            from .platform_config import is_maintenance_enabled, maintenance_message
            if not is_maintenance_enabled():
                return None
            # Admins bypass maintenance so they can still operate the panel.
            from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
            verify_jwt_in_request(optional=True)
            uid = get_jwt_identity()
            if uid:
                from .models import User
                from . import admin_rbac as rbac
                if rbac.is_admin(User.query.get(int(uid))):
                    return None
            return jsonify({"error": maintenance_message(), "code": "MAINTENANCE_MODE"}), 503
        except Exception:
            return None  # never let the gate itself break the app

    @app.before_request
    def _assign_request_id():
        g.request_id = str(uuid.uuid4())[:8]

    @app.before_request
    def _validate_origin():
        """Reject cross-origin state-changing requests from unexpected origins.

        SPA uses Authorization header so pure CSRF is low-risk, but origin
        validation provides defence-in-depth against CSRF via browser quirks.
        Only checked on state-changing methods; GET/HEAD/OPTIONS are skipped.
        """
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return None
        origin = request.headers.get("Origin") or request.headers.get("Referer", "")
        if not origin:
            return None  # Non-browser clients (curl, backend-to-backend) have no Origin
        # Build allowed origins from the same list CORS uses
        import os as _os_origin
        _ao_env = _os_origin.environ.get("ALLOWED_ORIGINS", "")
        _ao_list = [o.strip() for o in _ao_env.split(",") if o.strip()]
        if not _ao_list:
            _ao_list = [_os_origin.environ.get("FRONTEND_URL", "http://localhost:3000")]
        if not any(origin.startswith(o) for o in _ao_list):
            # Log the unexpected origin for monitoring; don't block non-browser API calls
            _scheduler_log.warning("[ORIGIN] Unexpected origin=%s path=%s", origin, request.path)
        return None

    # 1-D-02: enforce the CSRF double-submit check for COOKIE-authenticated
    # state-changing requests. Previously validate_csrf() existed but was never
    # wired in — the frontend sent X-CSRF-Token on every request and nothing
    # verified it. Scope:
    #   - only when an access_token cookie is present AND there is no
    #     Authorization header (Bearer flows — TMA, API clients — are immune
    #     to CSRF and carry no cookies worth protecting)
    #   - webhook receivers are exempt (no browser cookies are ever sent there)
    #   - login/register/refresh are exempt: they establish the session that
    #     issues the CSRF cookie in the first place
    _CSRF_EXEMPT_PREFIX = (
        '/api/billing/crypto/webhook', '/api/billing/lemon-squeezy/webhook',
        '/api/webhooks/', '/api/telegram/', '/api/tg-update/',
        '/api/hub/webhook', '/api/official-bot-update', '/api/echo-bot-update',
        '/api/integrations/',
    )
    _CSRF_EXEMPT_EXACT = {
        '/api/auth/login', '/api/auth/register', '/api/auth/refresh',
        '/api/auth/verify-totp-login', '/api/auth/forgot-password',
        '/api/auth/reset-password', '/api/auth/verify-email',
        '/api/miniapp/auth',
    }

    @app.before_request
    def _enforce_csrf():
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return None
        path = request.path
        if not path.startswith('/api/'):
            return None
        if path in _CSRF_EXEMPT_EXACT or path.startswith(_CSRF_EXEMPT_PREFIX):
            return None
        if request.headers.get("Authorization"):
            return None  # Bearer-authenticated — not a CSRF vector
        if not request.cookies.get("access_token"):
            return None  # no auth cookie — nothing to ride on
        import hmac as _hmac
        cookie_token = request.cookies.get("csrf_token", "")
        header_token = request.headers.get("X-CSRF-Token", "")
        if not cookie_token or not header_token or not _hmac.compare_digest(cookie_token, header_token):
            return jsonify({
                "error": "CSRF validation failed. Please refresh the page and try again.",
                "code": "CSRF_FAILED",
            }), 403
        return None

    # 1-D-04: tighter size limit for webhook endpoints
    @app.before_request
    def _limit_webhook_size():
        webhook_paths = ["/api/billing/crypto/webhook", "/api/billing/lemon-squeezy/webhook", "/api/webhooks/"]
        if any(request.path.startswith(p) for p in webhook_paths):
            if request.content_length and request.content_length > 65536:  # 64 KB
                abort(413, "Request too large")

    @app.after_request
    def _add_security_headers(response):
        """Attach security headers to every response (1-D-03)."""
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'none'; frame-ancestors 'none';",
        )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

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
        _run_security_migrations()
        _run_anti_abuse_migrations()
        _run_official_bot_migrations()
        _run_telegram_connect_migrations()
        _run_stability_migrations()
        _fix_custom_bot_group_types()
        # Self-healing custom-bot reconciliation: auto-create missing custom_bots
        # twins, link + activate custom-bot groups. Guarantees future custom bots
        # show up and count with no manual fix scripts. Best-effort.
        try:
            from .bot_links import reconcile_custom_bots
            _res = reconcile_custom_bots(db)
            if any(_res.values()):
                logging.getLogger("migrations").info("reconcile_custom_bots: %s", _res)
        except Exception as _e:
            logging.getLogger("migrations").debug("reconcile_custom_bots skipped: %s", _e)
        _run_phase3_migrations()
        _run_phase4_migrations()
        _run_phase5_migrations()
        _run_phase6_migrations()
        _run_engagement_extras_migration()
        _run_smart_links_migration()
        _run_workspace_migrations()
        _run_marketplace_migrations()
        _backfill_group_defaults()
        _run_token_hash_hmac_migration()
        _run_assistant_bot_migration()
        _run_assistant_spaces_migration()
        _run_linked_telegram_accounts_migration()
        _run_onboarding_emails_migration()
        _run_assistant_v2_migrations()
        _run_xp_period_migrations()
        _run_user_columns_migration()
        _run_scheduled_job_runs_migration()

        # Encryption self-check — must run after all migrations so tokens exist
        from .utils.encryption import startup_encryption_selfcheck
        startup_encryption_selfcheck(app)

    # Start bots in a background thread after a short delay so Gunicorn can
    # pass its healthcheck before bot polling (which may contact Telegram and
    # hold DB connections) begins.
    def _deferred_bot_start():
        import time
        _bot_log = logging.getLogger("bot_start")

        # Initial delay lets Gunicorn pass its health check before bot polling starts.
        time.sleep(5)

        # --- Restart user custom bots with exponential backoff ---
        _max_attempts = 5
        for _attempt in range(1, _max_attempts + 1):
            try:
                with app.app_context():
                    _restart_active_bots(app)
                _bot_log.info("Custom bots restarted successfully (attempt %d)", _attempt)
                break
            except Exception as exc:
                _bot_log.error(
                    "Custom bot restart failed (attempt %d/%d): %s",
                    _attempt, _max_attempts, exc, exc_info=True,
                )
                try:
                    import sentry_sdk
                    sentry_sdk.capture_exception(exc)
                except Exception:
                    pass
                if _attempt < _max_attempts:
                    _backoff = min(60, 5 * (2 ** (_attempt - 1)))  # 5s, 10s, 20s, 40s, 60s
                    _bot_log.info("Retrying custom bot restart in %ds…", _backoff)
                    time.sleep(_backoff)
                else:
                    _bot_log.critical(
                        "Custom bot restart permanently failed after %d attempts — "
                        "bots are NOT running. Check TELEGRAM_BOT_TOKEN and DB connectivity.",
                        _max_attempts,
                    )

        # --- Start official Telegizer shared bot with retry ---
        for _attempt in range(1, _max_attempts + 1):
            try:
                start_official_bot(app)
                _bot_log.info("Official bot started successfully (attempt %d)", _attempt)
                break
            except Exception as exc:
                _bot_log.error(
                    "Official bot start failed (attempt %d/%d): %s",
                    _attempt, _max_attempts, exc, exc_info=True,
                )
                try:
                    import sentry_sdk
                    sentry_sdk.capture_exception(exc)
                except Exception:
                    pass
                if _attempt < _max_attempts:
                    _backoff = min(120, 10 * (2 ** (_attempt - 1)))  # 10s, 20s, 40s, 80s, 120s
                    _bot_log.info("Retrying official bot start in %ds…", _backoff)
                    time.sleep(_backoff)
                else:
                    _bot_log.critical(
                        "Official bot start permanently failed after %d attempts — "
                        "TELEGRAM_BOT_TOKEN may be invalid or Telegram API unreachable.",
                        _max_attempts,
                    )

        # --- Start Telegizer Echo assistant bot with retry ---
        for _attempt in range(1, _max_attempts + 1):
            try:
                start_echo_bot(app)
                _bot_log.info("Echo bot started successfully (attempt %d)", _attempt)
                break
            except Exception as exc:
                _bot_log.error(
                    "Echo bot start failed (attempt %d/%d): %s",
                    _attempt, _max_attempts, exc, exc_info=True,
                )
                try:
                    import sentry_sdk
                    sentry_sdk.capture_exception(exc)
                except Exception:
                    pass
                if _attempt < _max_attempts:
                    _backoff = min(120, 10 * (2 ** (_attempt - 1)))
                    _bot_log.info("Retrying Echo bot start in %ds…", _backoff)
                    time.sleep(_backoff)
                else:
                    _bot_log.critical(
                        "Echo bot start permanently failed after %d attempts — "
                        "ECHO_BOT_TOKEN may be invalid or Telegram API unreachable.",
                        _max_attempts,
                    )

    # Start the bots and the scheduler at most once per process, and never at all
    # when DISABLE_BACKGROUND_THREADS is set (used by any standalone worker, CLI
    # or migration process that only needs an app context, not a live bot).
    global _BACKGROUND_THREADS_STARTED
    if os.environ.get("DISABLE_BACKGROUND_THREADS", "").strip().lower() in ("1", "true", "yes"):
        return app
    if _BACKGROUND_THREADS_STARTED:
        return app
    _BACKGROUND_THREADS_STARTED = True

    threading.Thread(target=_deferred_bot_start, daemon=True).start()

    # In-process scheduler: runs every 60 s inside the web process. This is now the
    # only scheduler — the Celery worker service is idled (see railway.worker.toml),
    # and every job that used to run on Celery beat is registered in _scheduler_loop.
    threading.Thread(target=_scheduler_loop, args=(app,), daemon=True).start()

    return app


def _run_official_bot_migrations():
    """Create tables for the official Telegizer shared bot ecosystem."""
    stmts = [
        """CREATE TABLE IF NOT EXISTS telegram_groups (
            id SERIAL PRIMARY KEY,
            telegram_group_id VARCHAR(255) UNIQUE NOT NULL,
            title VARCHAR(255) NOT NULL,
            username VARCHAR(255),
            invite_link VARCHAR(500),
            owner_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            linked_via_bot_type VARCHAR(20) NOT NULL DEFAULT 'official',
            linked_bot_id INTEGER,
            bot_status VARCHAR(20) NOT NULL DEFAULT 'pending',
            bot_permissions JSONB,
            linked_at TIMESTAMP,
            last_activity TIMESTAMP,
            is_disabled BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )""",
        "CREATE INDEX IF NOT EXISTS ix_telegram_groups_tg_id ON telegram_groups (telegram_group_id)",
        "CREATE INDEX IF NOT EXISTS ix_telegram_groups_owner ON telegram_groups (owner_user_id)",
        """CREATE TABLE IF NOT EXISTS telegram_group_link_codes (
            id SERIAL PRIMARY KEY,
            code VARCHAR(16) UNIQUE NOT NULL,
            telegram_group_id VARCHAR(255) NOT NULL REFERENCES telegram_groups(telegram_group_id) ON DELETE CASCADE,
            telegram_group_title VARCHAR(255),
            created_by_telegram_user_id VARCHAR(255) NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            used_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )""",
        "CREATE INDEX IF NOT EXISTS ix_tg_link_codes_code ON telegram_group_link_codes (code)",
        """CREATE TABLE IF NOT EXISTS custom_bots (
            id SERIAL PRIMARY KEY,
            owner_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            bot_name VARCHAR(255),
            bot_username VARCHAR(255) NOT NULL,
            bot_token_encrypted TEXT NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'active',
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )""",
        "CREATE INDEX IF NOT EXISTS ix_custom_bots_owner ON custom_bots (owner_user_id)",
        """CREATE TABLE IF NOT EXISTS custom_commands (
            id SERIAL PRIMARY KEY,
            telegram_group_id VARCHAR(255) NOT NULL REFERENCES telegram_groups(telegram_group_id) ON DELETE CASCADE,
            command VARCHAR(64) NOT NULL,
            response_type VARCHAR(20) NOT NULL DEFAULT 'text',
            response_text TEXT NOT NULL,
            action_type VARCHAR(50),
            buttons JSONB,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE(telegram_group_id, command)
        )""",
        "CREATE INDEX IF NOT EXISTS ix_custom_commands_group ON custom_commands (telegram_group_id)",
        """CREATE TABLE IF NOT EXISTS bot_events (
            id SERIAL PRIMARY KEY,
            telegram_group_id VARCHAR(255) REFERENCES telegram_groups(telegram_group_id) ON DELETE SET NULL,
            event_type VARCHAR(50) NOT NULL,
            message TEXT,
            metadata JSONB,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )""",
        "CREATE INDEX IF NOT EXISTS ix_bot_events_group ON bot_events (telegram_group_id)",
        "CREATE INDEX IF NOT EXISTS ix_bot_events_type ON bot_events (event_type)",
        "CREATE INDEX IF NOT EXISTS ix_bot_events_created ON bot_events (created_at DESC)",
        # FK for telegram_groups.linked_bot_id (added after custom_bots table exists)
        "ALTER TABLE telegram_groups ADD CONSTRAINT fk_tg_linked_bot FOREIGN KEY (linked_bot_id) REFERENCES custom_bots(id) ON DELETE SET NULL",
    ]
    try:
        with db.engine.connect() as conn:
            for sql in stmts:
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


def _run_stability_migrations():
    """Phase-2 stability fixes: unique group constraint and last_active backfill."""
    _mig_log = logging.getLogger("migrations")
    stmts = [
        # UNIQUE(bot_id, telegram_group_id): remove duplicates first (keep lowest id),
        # then create the unique index.  Both steps are idempotent.
        """
        DELETE FROM groups
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM groups
            GROUP BY bot_id, telegram_group_id
        )
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_bot_telegram_group
        ON groups (bot_id, telegram_group_id)
        """,
        # Backfill last_active for running bots that never had it set.
        # Sets it to created_at so get_health_status() returns 'warning' or
        # 'error' rather than 'unknown', giving admins a meaningful dashboard.
        """
        UPDATE bots
        SET last_active = created_at
        WHERE is_active = TRUE AND last_active IS NULL
        """,
    ]
    try:
        with db.engine.connect() as conn:
            for sql in stmts:
                try:
                    conn.execute(text(sql))
                    conn.commit()
                except Exception as exc:
                    _mig_log.warning("stability migration stmt failed: %s", exc)
                    try:
                        conn.rollback()
                    except Exception:
                        pass
    except Exception as exc:
        _mig_log.warning("stability migrations failed: %s", exc)


def _run_phase3_migrations():
    """Phase-3: add missing columns to official_members to match Member model."""
    stmts = [
        "ALTER TABLE official_members ADD COLUMN IF NOT EXISTS last_xp_at TIMESTAMP",
        "ALTER TABLE official_members ADD COLUMN IF NOT EXISTS role VARCHAR(100) NOT NULL DEFAULT 'member'",
        "ALTER TABLE official_members ADD COLUMN IF NOT EXISTS warnings INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE official_members ADD COLUMN IF NOT EXISTS is_verified BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE official_members ADD COLUMN IF NOT EXISTS is_muted BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE official_members ADD COLUMN IF NOT EXISTS mute_until TIMESTAMP",
        "ALTER TABLE official_members ADD COLUMN IF NOT EXISTS wallet_address VARCHAR(500)",
        "ALTER TABLE official_members ADD COLUMN IF NOT EXISTS wallet_submitted_at TIMESTAMP",
    ]
    try:
        with db.engine.connect() as conn:
            for sql in stmts:
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


def _run_phase4_migrations():
    """Phase-4: create official_scheduled_messages and official_polls tables."""
    stmts = [
        """CREATE TABLE IF NOT EXISTS official_scheduled_messages (
            id SERIAL PRIMARY KEY,
            telegram_group_id VARCHAR(255) NOT NULL REFERENCES telegram_groups(telegram_group_id) ON DELETE CASCADE,
            title VARCHAR(255) NOT NULL,
            message_text TEXT NOT NULL,
            media_url VARCHAR(500),
            buttons JSONB,
            send_at TIMESTAMP NOT NULL,
            repeat_interval INTEGER,
            stop_date TIMESTAMP,
            pin_message BOOLEAN NOT NULL DEFAULT FALSE,
            auto_delete_after INTEGER,
            link_preview_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            topic_id BIGINT,
            timezone VARCHAR(50) NOT NULL DEFAULT 'UTC',
            is_sent BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )""",
        "CREATE INDEX IF NOT EXISTS ix_official_scheduled_messages_group ON official_scheduled_messages (telegram_group_id)",
        """CREATE TABLE IF NOT EXISTS official_polls (
            id SERIAL PRIMARY KEY,
            telegram_group_id VARCHAR(255) NOT NULL REFERENCES telegram_groups(telegram_group_id) ON DELETE CASCADE,
            question VARCHAR(500) NOT NULL,
            options JSONB NOT NULL,
            correct_option_index INTEGER,
            is_quiz BOOLEAN NOT NULL DEFAULT FALSE,
            is_anonymous BOOLEAN NOT NULL DEFAULT TRUE,
            allows_multiple BOOLEAN NOT NULL DEFAULT FALSE,
            explanation VARCHAR(200),
            scheduled_at TIMESTAMP,
            timezone VARCHAR(50) DEFAULT 'UTC',
            is_sent BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )""",
        "CREATE INDEX IF NOT EXISTS ix_official_polls_group ON official_polls (telegram_group_id)",
    ]
    try:
        with db.engine.connect() as conn:
            for sql in stmts:
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


def _run_phase5_migrations():
    """Phase-5: add telegram_group_id to auto_responses, knowledge_documents, invite_links,
    and user_api_keys. Also relax group_id NOT NULL on those tables so official-bot rows can omit it."""
    stmts = [
        "ALTER TABLE auto_responses ADD COLUMN IF NOT EXISTS telegram_group_id VARCHAR(255)",
        "CREATE INDEX IF NOT EXISTS ix_auto_responses_tgid ON auto_responses (telegram_group_id)",
        "ALTER TABLE auto_responses ALTER COLUMN group_id DROP NOT NULL",
        "ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS telegram_group_id VARCHAR(255)",
        "CREATE INDEX IF NOT EXISTS ix_knowledge_documents_tgid ON knowledge_documents (telegram_group_id)",
        "ALTER TABLE knowledge_documents ALTER COLUMN group_id DROP NOT NULL",
        "ALTER TABLE invite_links ADD COLUMN IF NOT EXISTS telegram_group_id VARCHAR(255)",
        "CREATE INDEX IF NOT EXISTS ix_invite_links_tgid ON invite_links (telegram_group_id)",
        "ALTER TABLE invite_links ALTER COLUMN group_id DROP NOT NULL",
        "ALTER TABLE user_api_keys ADD COLUMN IF NOT EXISTS telegram_group_id VARCHAR(255)",
        "CREATE INDEX IF NOT EXISTS ix_user_api_keys_tgid ON user_api_keys (telegram_group_id)",
        "ALTER TABLE user_api_keys ALTER COLUMN group_id DROP NOT NULL",
    ]
    try:
        with db.engine.connect() as conn:
            for sql in stmts:
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


def _run_phase6_migrations():
    """Phase-6: add is_admin cache columns to official_members; create pending_verifications table."""
    stmts = [
        "ALTER TABLE official_members ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE official_members ADD COLUMN IF NOT EXISTS is_admin_cached_at TIMESTAMP",
        """
        CREATE TABLE IF NOT EXISTS pending_verifications (
            id SERIAL PRIMARY KEY,
            chat_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            method VARCHAR(20) NOT NULL,
            msg_id INTEGER,
            answer VARCHAR(500),
            expires_at TIMESTAMP NOT NULL,
            kick_on_fail BOOLEAN DEFAULT TRUE,
            max_attempts INTEGER DEFAULT 3,
            attempts INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW(),
            CONSTRAINT uq_pending_verification UNIQUE (chat_id, user_id)
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_pending_verif_expires ON pending_verifications (expires_at)",
    ]
    _mig_log = logging.getLogger("migrations")
    try:
        with db.engine.connect() as conn:
            for sql in stmts:
                try:
                    conn.execute(text(sql))
                    conn.commit()
                except Exception as exc:
                    _mig_log.warning("phase6 migration stmt failed: %s", exc)
                    try:
                        conn.rollback()
                    except Exception:
                        pass
    except Exception as exc:
        _mig_log.warning("phase6 migrations failed: %s", exc)


def _run_engagement_extras_migration():
    """Engagement campaigns: group-post delivery tracking, proof examples, and
    post-review DM notify result. Additive + idempotent (Railway-safe)."""
    _mig_log = logging.getLogger("migrations")
    stmts = [
        "ALTER TABLE engagement_campaigns ADD COLUMN IF NOT EXISTS post_status VARCHAR(16) NOT NULL DEFAULT 'none'",
        "ALTER TABLE engagement_campaigns ADD COLUMN IF NOT EXISTS post_error TEXT",
        "ALTER TABLE engagement_campaigns ADD COLUMN IF NOT EXISTS posted_at TIMESTAMP",
        "ALTER TABLE engagement_custom_fields ADD COLUMN IF NOT EXISTS example VARCHAR(255)",
        "ALTER TABLE engagement_submissions ADD COLUMN IF NOT EXISTS notify_status VARCHAR(16) NOT NULL DEFAULT 'none'",
        "ALTER TABLE engagement_submissions ADD COLUMN IF NOT EXISTS notify_error VARCHAR(255)",
    ]
    try:
        with db.engine.connect() as conn:
            for sql in stmts:
                try:
                    conn.execute(text(sql))
                    conn.commit()
                except Exception as exc:
                    _mig_log.warning("engagement-extras migration stmt failed: %s", exc)
                    try:
                        conn.rollback()
                    except Exception:
                        pass
    except Exception as exc:
        _mig_log.warning("engagement-extras migrations failed: %s", exc)


def _run_smart_links_migration():
    """Add Smart Links columns to auto_responses table."""
    _mig_log = logging.getLogger("migrations")
    stmts = [
        "ALTER TABLE auto_responses ADD COLUMN IF NOT EXISTS response_type VARCHAR(20) NOT NULL DEFAULT 'auto_response'",
        "ALTER TABLE auto_responses ADD COLUMN IF NOT EXISTS link_label VARCHAR(100)",
        "ALTER TABLE auto_responses ADD COLUMN IF NOT EXISTS link_url VARCHAR(2000)",
        "ALTER TABLE auto_responses ADD COLUMN IF NOT EXISTS owner_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL",
        "ALTER TABLE auto_responses ADD COLUMN IF NOT EXISTS scope VARCHAR(20) NOT NULL DEFAULT 'group'",
        "CREATE INDEX IF NOT EXISTS ix_auto_responses_owner ON auto_responses (owner_user_id) WHERE owner_user_id IS NOT NULL",
        "CREATE INDEX IF NOT EXISTS ix_auto_responses_scope ON auto_responses (scope, response_type) WHERE is_enabled = TRUE",
    ]
    try:
        with db.engine.connect() as conn:
            for sql in stmts:
                try:
                    conn.execute(text(sql))
                    conn.commit()
                except Exception as exc:
                    _mig_log.warning("smart_links migration stmt failed: %s", exc)
                    try:
                        conn.rollback()
                    except Exception:
                        pass
    except Exception as exc:
        _mig_log.warning("smart_links migrations failed: %s", exc)


def _run_workspace_migrations():
    """Create workspace_reminders and message_buffers tables."""
    _mig_log = logging.getLogger("migrations")
    stmts = [
        """CREATE TABLE IF NOT EXISTS workspace_reminders (
            id SERIAL PRIMARY KEY,
            owner_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            telegram_group_id VARCHAR(255),
            original_message TEXT,
            reminder_text VARCHAR(500) NOT NULL,
            remind_at TIMESTAMP NOT NULL,
            is_delivered BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )""",
        "CREATE INDEX IF NOT EXISTS ix_workspace_reminders_owner ON workspace_reminders (owner_user_id)",
        "CREATE INDEX IF NOT EXISTS ix_workspace_reminders_remind_at ON workspace_reminders (remind_at) WHERE is_delivered = FALSE",
        """CREATE TABLE IF NOT EXISTS message_buffers (
            id SERIAL PRIMARY KEY,
            telegram_group_id VARCHAR(255) NOT NULL,
            sender_user_id VARCHAR(255) NOT NULL,
            sender_name VARCHAR(255),
            message_text TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )""",
        "CREATE INDEX IF NOT EXISTS ix_message_buffers_group ON message_buffers (telegram_group_id)",
        "CREATE INDEX IF NOT EXISTS ix_message_buffers_created ON message_buffers (created_at)",
    ]
    try:
        with db.engine.connect() as conn:
            for sql in stmts:
                try:
                    conn.execute(text(sql))
                    conn.commit()
                except Exception as exc:
                    _mig_log.warning("workspace migration stmt failed: %s", exc)
                    try:
                        conn.rollback()
                    except Exception:
                        pass
    except Exception as exc:
        _mig_log.warning("workspace migrations failed: %s", exc)


def _run_marketplace_migrations():
    """Add marketplace/directory/CRM columns and tables introduced alongside the
    B2B Partnership Marketplace feature.  All statements are idempotent."""
    _mig_log = logging.getLogger("migrations")
    stmts = [
        # ── directory_listings: new pricing/partnership columns ─────────────────
        "ALTER TABLE directory_listings ADD COLUMN IF NOT EXISTS accepts_partnerships BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE directory_listings ADD COLUMN IF NOT EXISTS price_per_post FLOAT",
        "ALTER TABLE directory_listings ADD COLUMN IF NOT EXISTS price_per_week FLOAT",
        "ALTER TABLE directory_listings ADD COLUMN IF NOT EXISTS pricing_notes VARCHAR(512)",
        # ── official_members: CRM columns ───────────────────────────────────────
        "ALTER TABLE official_members ADD COLUMN IF NOT EXISTS crm_tags JSON",
        "ALTER TABLE official_members ADD COLUMN IF NOT EXISTS crm_notes TEXT",
        "ALTER TABLE official_members ADD COLUMN IF NOT EXISTS engagement_score INTEGER",
        # ── channels: TCS columns (table created by db.create_all, but add cols if table pre-existed) ─
        "ALTER TABLE channels ADD COLUMN IF NOT EXISTS tcs_score INTEGER",
        "ALTER TABLE channels ADD COLUMN IF NOT EXISTS tcs_grade VARCHAR(2)",
        "ALTER TABLE channels ADD COLUMN IF NOT EXISTS tcs_breakdown JSON",
        "ALTER TABLE channels ADD COLUMN IF NOT EXISTS tcs_computed_at TIMESTAMP",
        # ── partnership_deals table ──────────────────────────────────────────────
        """CREATE TABLE IF NOT EXISTS partnership_deals (
            id SERIAL PRIMARY KEY,
            listing_id INTEGER NOT NULL REFERENCES directory_listings(id) ON DELETE CASCADE,
            buyer_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            seller_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title VARCHAR(255) NOT NULL,
            requirements TEXT,
            budget_usd FLOAT NOT NULL,
            platform_fee_pct FLOAT NOT NULL DEFAULT 10.0,
            net_seller_amount FLOAT NOT NULL,
            deadline_at TIMESTAMP,
            status VARCHAR(30) NOT NULL DEFAULT 'pending',
            payment_status VARCHAR(30) NOT NULL DEFAULT 'unpaid',
            payment_currency VARCHAR(20),
            payment_id VARCHAR(255),
            pay_address VARCHAR(500),
            deliverable TEXT,
            dispute_reason TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )""",
        "CREATE INDEX IF NOT EXISTS ix_partnership_deals_buyer ON partnership_deals (buyer_user_id)",
        "CREATE INDEX IF NOT EXISTS ix_partnership_deals_seller ON partnership_deals (seller_user_id)",
        "CREATE INDEX IF NOT EXISTS ix_partnership_deals_listing ON partnership_deals (listing_id)",
        "CREATE INDEX IF NOT EXISTS ix_partnership_deals_status ON partnership_deals (status)",
        # ── deal_messages table ──────────────────────────────────────────────────
        """CREATE TABLE IF NOT EXISTS deal_messages (
            id SERIAL PRIMARY KEY,
            deal_id INTEGER NOT NULL REFERENCES partnership_deals(id) ON DELETE CASCADE,
            sender_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            body TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )""",
        "CREATE INDEX IF NOT EXISTS ix_deal_messages_deal ON deal_messages (deal_id)",
        "CREATE INDEX IF NOT EXISTS ix_deal_messages_created ON deal_messages (created_at)",
    ]
    try:
        with db.engine.connect() as conn:
            for sql in stmts:
                try:
                    conn.execute(text(sql))
                    conn.commit()
                except Exception as exc:
                    _mig_log.warning("marketplace migration stmt failed: %s", exc)
                    try:
                        conn.rollback()
                    except Exception:
                        pass
    except Exception as exc:
        _mig_log.warning("marketplace migrations failed: %s", exc)


def _run_assistant_spaces_migration():
    """Create assistant_spaces table if it doesn't exist. Additive only."""
    _mig_log = logging.getLogger("migrations")
    try:
        with db.engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS assistant_spaces (
                    id SERIAL PRIMARY KEY,
                    assistant_bot_id INTEGER NOT NULL REFERENCES assistant_bots(id) ON DELETE CASCADE,
                    telegram_chat_id VARCHAR(255) NOT NULL,
                    chat_title VARCHAR(255),
                    chat_type VARCHAR(30) NOT NULL DEFAULT 'unknown',
                    first_seen_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    last_seen_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    CONSTRAINT uq_assistant_space UNIQUE (assistant_bot_id, telegram_chat_id)
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_assistant_spaces_bot ON assistant_spaces (assistant_bot_id)"))
            conn.commit()
    except Exception as exc:
        _mig_log.warning("assistant_spaces migration failed: %s", exc)


def _run_linked_telegram_accounts_migration():
    """Create user_telegram_accounts junction table. Additive only."""
    _mig_log = logging.getLogger("migrations")
    try:
        with db.engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS user_telegram_accounts (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    telegram_user_id VARCHAR(255) NOT NULL UNIQUE,
                    telegram_username VARCHAR(255),
                    telegram_first_name VARCHAR(255),
                    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
                    linked_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    CONSTRAINT uq_user_telegram UNIQUE (user_id, telegram_user_id)
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_user_telegram_accounts_user_id ON user_telegram_accounts (user_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_user_telegram_accounts_tg_id ON user_telegram_accounts (telegram_user_id)"))
            conn.commit()
    except Exception as exc:
        _mig_log.warning("user_telegram_accounts migration failed: %s", exc)


def _run_onboarding_emails_migration():
    """Add onboarding_emails_sent column to users table. Additive only."""
    _mig_log = logging.getLogger("migrations")
    try:
        with db.engine.connect() as conn:
            conn.execute(text("""
                ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarding_emails_sent INTEGER NOT NULL DEFAULT 0
            """))
            conn.commit()
    except Exception as exc:
        _mig_log.warning("onboarding_emails_sent migration failed: %s", exc)


def _run_assistant_bot_migration():
    """Create assistant_bots table if it doesn't exist. Additive only."""
    _mig_log = logging.getLogger("migrations")
    try:
        with db.engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS assistant_bots (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                    bot_token VARCHAR(512) NOT NULL,
                    bot_username VARCHAR(255),
                    bot_name VARCHAR(255),
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_assistant_bots_user_id ON assistant_bots (user_id)"))
            conn.commit()
    except Exception as exc:
        _mig_log.warning("assistant_bot migration failed: %s", exc)


def _run_assistant_v2_migrations():
    """Add enriched fields to meetings, reminders, and tasks for v2 assistant."""
    _mig_log = logging.getLogger("migrations")
    stmts = [
        # Meetings — extended fields
        "ALTER TABLE meetings ADD COLUMN duration_minutes INTEGER",
        "ALTER TABLE meetings ADD COLUMN location VARCHAR(500)",
        "ALTER TABLE meetings ADD COLUMN related_person VARCHAR(255)",
        "ALTER TABLE meetings ADD COLUMN project VARCHAR(255)",
        "ALTER TABLE meetings ADD COLUMN agenda TEXT",
        "ALTER TABLE meetings ADD COLUMN prep_notes TEXT",
        "ALTER TABLE meetings ADD COLUMN expected_outcome TEXT",
        "ALTER TABLE meetings ADD COLUMN followup_required BOOLEAN DEFAULT FALSE",
        "ALTER TABLE meetings ADD COLUMN followup_at TIMESTAMP",
        # Reminders — extended fields
        "ALTER TABLE workspace_reminders ADD COLUMN priority VARCHAR(10) DEFAULT 'medium'",
        "ALTER TABLE workspace_reminders ADD COLUMN recurrence VARCHAR(20)",
        "ALTER TABLE workspace_reminders ADD COLUMN related_person VARCHAR(255)",
        "ALTER TABLE workspace_reminders ADD COLUMN notes TEXT",
        # Tasks — extended fields
        "ALTER TABLE tasks ADD COLUMN related_person VARCHAR(255)",
        "ALTER TABLE tasks ADD COLUMN project VARCHAR(255)",
        "ALTER TABLE tasks ADD COLUMN estimated_minutes INTEGER",
    ]
    try:
        with db.engine.connect() as conn:
            for sql in stmts:
                try:
                    conn.execute(text(sql))
                    conn.commit()
                except Exception:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
        _mig_log.info("assistant_v2 migrations complete")
    except Exception as exc:
        _mig_log.warning("assistant_v2 migrations failed: %s", exc)


def _run_scheduled_job_runs_migration():
    """Ledger of when each scheduled job last ran.

    The scheduler's in-memory `_last_*` timestamps reset to 0 on every deploy, which
    is harmless for a health check but would re-fire the daily jobs — including the
    renewal, lifecycle and onboarding email blasts — on each redeploy. Persisting
    last_run_at makes the daily jobs fire once per day no matter how often we ship.
    """
    _mig_log = logging.getLogger("migrations")
    stmt = """
        CREATE TABLE IF NOT EXISTS scheduled_job_runs (
            job_name    VARCHAR(120) PRIMARY KEY,
            last_run_at TIMESTAMP NOT NULL
        )
    """
    try:
        with db.engine.connect() as conn:
            conn.execute(text(stmt))
            conn.commit()
        _mig_log.info("scheduled_job_runs migration complete")
    except Exception as exc:
        _mig_log.error("scheduled_job_runs migration failed: %s", exc)


# Claim a job for this tick: insert the row, or update it only if it is older than
# :cutoff. RETURNING is non-empty exactly when we won the claim.
#
# The comparison is done in SQL, not Python, on purpose: it keeps the whole check
# atomic (two overlapping ticks cannot both claim the same job) and it does not
# depend on the driver decoding TIMESTAMP into a datetime.
_JOB_CLAIM_SQL = text(
    "INSERT INTO scheduled_job_runs (job_name, last_run_at) VALUES (:job, :now) "
    "ON CONFLICT (job_name) DO UPDATE SET last_run_at = :now "
    "WHERE scheduled_job_runs.last_run_at < :cutoff "
    "RETURNING job_name"
)


def _claim_job(app, job_name, cutoff, now):
    """True if this tick won the claim on *job_name*. Fails CLOSED — on a DB error we
    skip the tick rather than risk double-sending a customer email."""
    try:
        with app.app_context(), db.engine.connect() as conn:
            won = conn.execute(
                _JOB_CLAIM_SQL, {"job": job_name, "now": now, "cutoff": cutoff}
            ).fetchone()
            conn.commit()
            return won is not None
    except Exception as exc:
        _scheduler_log.error("[SCHEDULER] job claim failed for %s: %s", job_name, exc)
        return False


def _job_due(app, job_name, interval_seconds):
    """True if *job_name* has not run in the last *interval_seconds*."""
    now = datetime.utcnow()
    return _claim_job(app, job_name, now - timedelta(seconds=interval_seconds), now)


def _job_due_daily(app, job_name, hour, minute=0):
    """True once per UTC day, on or after hour:minute.

    Preserves the exact times the old Celery beat crontab used (renewal reminders at
    09:00 UTC, and so on) instead of drifting to 'whenever the process last restarted'.
    """
    now = datetime.utcnow()
    if (now.hour, now.minute) < (hour, minute):
        return False
    today_at_target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return _claim_job(app, job_name, today_at_target, now)


def _run_xp_period_migrations():
    """Add xp_1d/xp_7d/xp_30d period snapshot columns to members and official_members."""
    _mig_log = logging.getLogger("migrations")
    stmts = [
        "ALTER TABLE official_members ADD COLUMN IF NOT EXISTS xp_1d INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE official_members ADD COLUMN IF NOT EXISTS xp_7d INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE official_members ADD COLUMN IF NOT EXISTS xp_30d INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE members ADD COLUMN IF NOT EXISTS xp_1d INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE members ADD COLUMN IF NOT EXISTS xp_7d INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE members ADD COLUMN IF NOT EXISTS xp_30d INTEGER NOT NULL DEFAULT 0",
    ]
    try:
        with db.engine.connect() as conn:
            for sql in stmts:
                try:
                    conn.execute(text(sql))
                    conn.commit()
                except Exception:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
        _mig_log.info("xp_period migrations complete")
    except Exception as exc:
        _mig_log.warning("xp_period migrations failed: %s", exc)


def _run_user_columns_migration():
    """Self-healing user-table columns that previously only lived in migrate.py.

    Most important: onboarding_tour_completed. When this column was missing on a
    deploy that never ran migrate.py, the product-tour 'completed' write 500'd
    silently, so the flag never persisted and the tour kept re-appearing whenever
    localStorage was cleared (notably inside the Telegram webview). Applying it at
    startup makes persistence reliable everywhere.
    """
    _mig_log = logging.getLogger("migrations")
    stmts = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarding_tour_completed BOOLEAN NOT NULL DEFAULT FALSE",
    ]
    try:
        with db.engine.connect() as conn:
            for sql in stmts:
                try:
                    conn.execute(text(sql))
                    conn.commit()
                except Exception:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
        _mig_log.info("user_columns migrations complete")
    except Exception as exc:
        _mig_log.warning("user_columns migrations failed: %s", exc)


def _backfill_group_defaults():
    """Idempotent backfill: ensure every TelegramGroup has all top-level default
    sections introduced in group_defaults._DEFAULTS.  Groups created before a
    new section was added will silently receive it; existing values are never
    overwritten.  Safe to run on every startup."""
    _mig_log = logging.getLogger("migrations")
    try:
        from .group_defaults import fill_missing_defaults
        from .models import TelegramGroup
        with db.engine.connect() as _conn:
            # Quick check: does the settings column exist yet?
            _conn.execute(text("SELECT settings FROM telegram_groups LIMIT 0"))
        with db.session.begin_nested() if False else db.session.no_autoflush:
            groups = TelegramGroup.query.all()
            patched = 0
            for tg in groups:
                if fill_missing_defaults(tg):
                    patched += 1
            if patched:
                db.session.commit()
                _mig_log.info("backfill_group_defaults: patched %d group(s)", patched)
    except Exception as exc:
        try:
            db.session.rollback()
        except Exception:
            pass
        _mig_log.debug("backfill_group_defaults skipped: %s", exc)


def _fix_custom_bot_group_types():
    """One-time data fix: correct telegram_groups rows that were stored as
    linked_via_bot_type='official' but actually belong to a user's custom bot.

    Correlation: old Bot.bot_username matches CustomBot.bot_username (same owner).
    For every Group in the old system whose telegram_group_id exists in
    telegram_groups with the wrong type, update linked_via_bot_type and
    linked_bot_id to the correct CustomBot row.
    """
    try:
        with db.engine.connect() as conn:
            conn.execute(text("""
                UPDATE telegram_groups AS tg
                SET linked_via_bot_type = 'custom',
                    linked_bot_id       = cb.id
                FROM custom_bots  cb
                JOIN bots         b  ON LOWER(b.bot_username) = LOWER(cb.bot_username)
                                    AND b.user_id = cb.owner_user_id
                                    AND b.bot_username IS NOT NULL
                JOIN groups       g  ON g.bot_id = b.id
                                    AND g.telegram_group_id = tg.telegram_group_id
                WHERE tg.linked_via_bot_type = 'official'
                  AND tg.linked_bot_id       IS NULL
            """))
            conn.commit()
    except Exception:
        try:
            with db.engine.connect() as conn:
                conn.rollback()
        except Exception:
            pass


def _run_telegram_connect_migrations():
    """Add Telegram account linkage columns to users and create telegram_connect_codes table."""
    stmts = [
        # Telegram identity columns on users
        "ALTER TABLE users ADD COLUMN telegram_user_id VARCHAR(255)",
        "ALTER TABLE users ADD COLUMN telegram_username VARCHAR(255)",
        "ALTER TABLE users ADD COLUMN telegram_first_name VARCHAR(255)",
        "ALTER TABLE users ADD COLUMN telegram_connected_at TIMESTAMP",
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_telegram_user_id ON users (telegram_user_id)",
        # One-time connect codes
        """CREATE TABLE IF NOT EXISTS telegram_connect_codes (
            id SERIAL PRIMARY KEY,
            code VARCHAR(64) UNIQUE NOT NULL,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at TIMESTAMP NOT NULL,
            used_at TIMESTAMP,
            telegram_user_id VARCHAR(255),
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )""",
        "CREATE INDEX IF NOT EXISTS ix_tg_connect_codes_code ON telegram_connect_codes (code)",
        "CREATE INDEX IF NOT EXISTS ix_tg_connect_codes_user ON telegram_connect_codes (user_id)",
    ]
    try:
        with db.engine.connect() as conn:
            for sql in stmts:
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


def _run_anti_abuse_migrations():
    """Add anti-abuse columns and tables introduced in v7."""
    stmts = [
        # New User columns: hashed identifiers + suspicious flag
        "ALTER TABLE users ADD COLUMN signup_ip_hash VARCHAR(64)",
        "ALTER TABLE users ADD COLUMN device_fingerprint_hash VARCHAR(64)",
        "ALTER TABLE users ADD COLUMN is_suspicious BOOLEAN DEFAULT FALSE",
        "CREATE INDEX IF NOT EXISTS ix_users_signup_ip_hash ON users (signup_ip_hash)",
        "CREATE INDEX IF NOT EXISTS ix_users_device_fingerprint_hash ON users (device_fingerprint_hash)",
        # New Referral columns: status lifecycle + overlap flags
        "ALTER TABLE referrals ADD COLUMN status VARCHAR(20) DEFAULT 'pending'",
        "ALTER TABLE referrals ADD COLUMN ip_match BOOLEAN DEFAULT FALSE",
        "ALTER TABLE referrals ADD COLUMN device_match BOOLEAN DEFAULT FALSE",
        # Backfill existing referrals to 'approved' so pre-anti-abuse records still count for rewards
        "UPDATE referrals SET status = 'approved' WHERE status IS NULL OR status = 'pending'",
        # suspicious_activities table
        """CREATE TABLE IF NOT EXISTS suspicious_activities (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            event_type VARCHAR(50) NOT NULL,
            ip_hash VARCHAR(64),
            device_hash VARCHAR(64),
            reason VARCHAR(255) NOT NULL,
            event_metadata JSONB,
            reviewed BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )""",
        "CREATE INDEX IF NOT EXISTS ix_suspicious_activities_created_at ON suspicious_activities (created_at DESC)",
        "CREATE INDEX IF NOT EXISTS ix_suspicious_activities_event_type ON suspicious_activities (event_type)",
        "CREATE INDEX IF NOT EXISTS ix_suspicious_activities_user_id ON suspicious_activities (user_id)",
    ]
    try:
        with db.engine.connect() as conn:
            for sql in stmts:
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
        # Live Telegram member-count reconciliation timestamp
        "ALTER TABLE telegram_groups ADD COLUMN member_count_synced_at TIMESTAMP",
        # Critical-admin-action resolution tracking (Phase 8) — so a resolved
        # critical action stops counting against the dashboard "needs attention".
        "ALTER TABLE admin_audit_logs ADD COLUMN resolved_at TIMESTAMP",
        "ALTER TABLE admin_audit_logs ADD COLUMN resolved_by INTEGER",
        "CREATE INDEX IF NOT EXISTS ix_admin_audit_sev_resolved ON admin_audit_logs (severity, resolved_at)",
        # Platform-admin free-text notes on the user detail page
        "ALTER TABLE users ADD COLUMN admin_notes TEXT",
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
        # Email verification
        "ALTER TABLE users ADD COLUMN email_verified BOOLEAN DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN email_verification_token VARCHAR(64)",
        "ALTER TABLE users ADD COLUMN email_verification_expires TIMESTAMP",
        # Brute-force login protection
        "ALTER TABLE users ADD COLUMN failed_login_attempts INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN locked_until TIMESTAMP",
        # 2FA / TOTP
        "ALTER TABLE users ADD COLUMN totp_secret VARCHAR(255)",
        "ALTER TABLE users ADD COLUMN totp_enabled BOOLEAN DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN totp_backup_codes JSONB",
        # DB-backed JWT revocation fallback
        """CREATE TABLE IF NOT EXISTS revoked_tokens (
            id SERIAL PRIMARY KEY,
            jti VARCHAR(64) UNIQUE NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )""",
        "CREATE INDEX IF NOT EXISTS ix_revoked_tokens_jti ON revoked_tokens (jti)",
        "CREATE INDEX IF NOT EXISTS ix_users_email_verification_token ON users (email_verification_token)",
        # Full settings panel for official bot groups
        "ALTER TABLE telegram_groups ADD COLUMN settings JSONB NOT NULL DEFAULT '{}'",
        "ALTER TABLE telegram_groups ADD COLUMN timezone VARCHAR(50) DEFAULT 'UTC'",
        # Official-group feature tables (Phase 2 — full parity with custom bots)
        """CREATE TABLE IF NOT EXISTS official_raids (
            id SERIAL PRIMARY KEY,
            telegram_group_id VARCHAR(255) NOT NULL REFERENCES telegram_groups(telegram_group_id) ON DELETE CASCADE,
            tweet_url VARCHAR(500) NOT NULL,
            goals JSONB NOT NULL DEFAULT '{}',
            duration_hours INTEGER NOT NULL DEFAULT 24,
            xp_reward INTEGER NOT NULL DEFAULT 100,
            pin_message BOOLEAN NOT NULL DEFAULT TRUE,
            reminders_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            ends_at TIMESTAMP NOT NULL,
            participants JSONB NOT NULL DEFAULT '[]'
        )""",
        "CREATE INDEX IF NOT EXISTS ix_official_raids_telegram_group_id ON official_raids (telegram_group_id)",
        """CREATE TABLE IF NOT EXISTS official_webhook_integrations (
            id SERIAL PRIMARY KEY,
            telegram_group_id VARCHAR(255) NOT NULL REFERENCES telegram_groups(telegram_group_id) ON DELETE CASCADE,
            name VARCHAR(100) NOT NULL,
            webhook_token VARCHAR(64) UNIQUE NOT NULL,
            description VARCHAR(255),
            message_template TEXT NOT NULL DEFAULT '📡 *{name}\n\n{payload}',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )""",
        "CREATE INDEX IF NOT EXISTS ix_official_webhook_integrations_group ON official_webhook_integrations (telegram_group_id)",
        "CREATE INDEX IF NOT EXISTS ix_official_webhook_integrations_token ON official_webhook_integrations (webhook_token)",
        """CREATE TABLE IF NOT EXISTS official_reported_messages (
            id SERIAL PRIMARY KEY,
            telegram_group_id VARCHAR(255) NOT NULL REFERENCES telegram_groups(telegram_group_id) ON DELETE CASCADE,
            reporter_user_id VARCHAR(255) NOT NULL,
            reporter_username VARCHAR(100),
            reported_user_id VARCHAR(255),
            reported_username VARCHAR(100),
            reason VARCHAR(500),
            status VARCHAR(20) NOT NULL DEFAULT 'open',
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )""",
        "CREATE INDEX IF NOT EXISTS ix_official_reported_messages_group ON official_reported_messages (telegram_group_id)",
        "CREATE INDEX IF NOT EXISTS ix_official_reported_messages_created ON official_reported_messages (created_at)",
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


def _run_security_migrations():
    """Dedicated migration for security-related columns and tables added in v6."""
    stmts = [
        # revoked_tokens table (DB fallback JWT blocklist)
        """CREATE TABLE IF NOT EXISTS revoked_tokens (
            id SERIAL PRIMARY KEY,
            jti VARCHAR(64) UNIQUE NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )""",
        "CREATE INDEX IF NOT EXISTS ix_revoked_tokens_jti ON revoked_tokens (jti)",
        # Purge expired revoked tokens to keep the table small
        "DELETE FROM revoked_tokens WHERE expires_at < NOW()",
    ]
    try:
        with db.engine.connect() as conn:
            for sql in stmts:
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


def _run_token_hash_hmac_migration():
    """Re-hash all bot_token_hash values from plain SHA-256 to HMAC-SHA256.

    hash_token() now uses HMAC-SHA256 keyed with ENCRYPTION_KEY.  Any rows
    hashed under the old plain SHA-256 scheme won't match lookups any more,
    so on first startup after the upgrade we decrypt every token and re-hash it.
    We detect old-scheme hashes by computing both values and checking for a
    mismatch (idempotent — runs harmlessly on subsequent restarts).
    """
    from .models import Bot
    from .utils.encryption import decrypt_value, hash_token as _hmac_hash, DecryptionError

    try:
        bots = Bot.query.filter(Bot.bot_token_hash.isnot(None)).all()
        changed = False
        for bot in bots:
            try:
                plain = decrypt_value(bot.bot_token)
            except DecryptionError:
                _scheduler_log.error("[MIGRATION] Cannot decrypt token for bot %s — skipping re-hash", bot.id)
                continue
            if not plain:
                continue
            expected_hmac = _hmac_hash(plain)
            if bot.bot_token_hash != expected_hmac:
                bot.bot_token_hash = expected_hmac
                changed = True
        if changed:
            db.session.commit()
            _scheduler_log.info("[MIGRATION] Re-hashed bot tokens to HMAC-SHA256")
    except Exception as exc:
        _scheduler_log.error("[MIGRATION] token_hash HMAC migration failed: %s", exc)
        try:
            db.session.rollback()
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
    # Detection: DecryptionError means the stored value is plaintext (pre-encryption era).
    try:
        from .models import Bot
        from .utils.encryption import DecryptionError as _DecryptionError
        bots = Bot.query.all()
        changed = False
        for bot in bots:
            try:
                plain = decrypt_value(bot.bot_token)
                # Successfully decrypted — only re-hash if hash is missing or stale
                if not bot.bot_token_hash:
                    bot.bot_token_hash = hash_token(plain)
                    changed = True
            except _DecryptionError:
                # Value is likely a legacy plaintext token — encrypt it now
                plain = bot.bot_token
                if plain and ":" in plain:
                    bot.bot_token = encrypt_value(plain)
                    bot.bot_token_hash = hash_token(plain)
                    changed = True
                else:
                    _scheduler_log.error("[MIGRATION] Bot %s has unrecoverable token — skipping", bot.id)
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
    """Start all user-added bots EXCEPT the official Telegizer bot token.
    The official token is managed exclusively by official_bot.py — if
    bot_manager also starts it we get a Telegram Conflict (two pollers)
    and official_bot.py loses, so the old /start handler takes over."""
    from .models import Bot
    from .config import Config
    from .utils.encryption import hash_token as _hash

    official_hash = _hash(Config.TELEGRAM_BOT_TOKEN) if Config.TELEGRAM_BOT_TOKEN else None
    try:
        active_bots = Bot.query.filter_by(is_active=True).all()
        for bot in active_bots:
            if official_hash and bot.bot_token_hash == official_hash:
                _scheduler_log.info(
                    "[BOT_MANAGER] Skipping bot id=%s — token matches TELEGRAM_BOT_TOKEN "
                    "(handled by official_bot.py)", bot.id
                )
                continue
            bot_manager.start_bot(bot.id, bot.get_token(), app)
    except Exception as exc:
        _scheduler_log.error("[BOT_MANAGER] _restart_active_bots error: %s", exc)


def _watchdog_bots(app):
    """Detect dead custom bot threads and restart them automatically."""
    from .models import Bot
    from .config import Config
    from .utils.encryption import hash_token as _hash

    official_hash = _hash(Config.TELEGRAM_BOT_TOKEN) if Config.TELEGRAM_BOT_TOKEN else None
    with app.app_context():
        active_bots = Bot.query.filter_by(is_active=True).all()
        for bot in active_bots:
            if official_hash and bot.bot_token_hash == official_hash:
                continue  # managed by official_bot.py
            if not bot_manager.is_running(bot.id):
                _scheduler_log.warning(
                    "[WATCHDOG] Bot %s (@%s) thread dead — restarting", bot.id, bot.bot_username
                )
                try:
                    bot_manager.start_bot(bot.id, bot.get_token(), app)
                except Exception as exc:
                    _scheduler_log.error("[WATCHDOG] Failed to restart bot %s: %s", bot.id, exc)


def _run_official_group_digests(app):
    """Send daily/weekly digests for official bot groups whose interval has elapsed."""
    import asyncio as _asyncio
    from .models import TelegramGroup
    from .official_bot import _runner, _send_official_digest

    bot = None
    loop = None
    if _runner and _runner.application:
        bot = _runner.application.bot
        loop = _runner.loop
    if not bot or not loop or not loop.is_running():
        return

    now = datetime.utcnow()
    with app.app_context():
        groups = TelegramGroup.query.filter(
            TelegramGroup.owner_user_id.isnot(None),
            TelegramGroup.is_disabled == False,
            TelegramGroup.bot_status == "active",
        ).all()
        for tg in groups:
            digest_cfg = (tg.settings or {}).get("digest", {})
            if not digest_cfg:
                continue
            try:
                if digest_cfg.get("daily"):
                    last = digest_cfg.get("last_daily")
                    last_dt = datetime.fromisoformat(last) if last else None
                    if not last_dt or (now - last_dt).total_seconds() >= 86400:
                        fut = _asyncio.run_coroutine_threadsafe(
                            _send_official_digest(bot, tg, days=1), loop
                        )
                        fut.result(timeout=15)
                        settings = dict(tg.settings)
                        settings["digest"] = dict(digest_cfg)
                        settings["digest"]["last_daily"] = now.isoformat()
                        tg.settings = settings
                        from .models import db
                        db.session.commit()

                if digest_cfg.get("weekly"):
                    last = digest_cfg.get("last_weekly")
                    last_dt = datetime.fromisoformat(last) if last else None
                    if not last_dt or (now - last_dt).total_seconds() >= 604800:
                        fut = _asyncio.run_coroutine_threadsafe(
                            _send_official_digest(bot, tg, days=7), loop
                        )
                        fut.result(timeout=15)
                        settings = dict(tg.settings)
                        settings["digest"] = dict(digest_cfg)
                        settings["digest"]["last_weekly"] = now.isoformat()
                        tg.settings = settings
                        from .models import db
                        db.session.commit()

                if digest_cfg.get("monthly"):
                    last = digest_cfg.get("last_monthly")
                    last_dt = datetime.fromisoformat(last) if last else None
                    if not last_dt or (now - last_dt).total_seconds() >= 2_592_000:  # 30 days
                        fut = _asyncio.run_coroutine_threadsafe(
                            _send_official_digest(bot, tg, days=30), loop
                        )
                        fut.result(timeout=15)
                        settings = dict(tg.settings)
                        settings["digest"] = dict(digest_cfg)
                        settings["digest"]["last_monthly"] = now.isoformat()
                        tg.settings = settings
                        from .models import db
                        db.session.commit()
            except Exception as exc:
                _scheduler_log.warning(
                    "[DIGEST] Telegram delivery failed for group %s: %s — attempting email fallback",
                    tg.telegram_group_id, exc,
                )
                # Email fallback: notify the group owner so the digest is not silently lost
                try:
                    from .models import User
                    owner = User.query.get(tg.owner_user_id)
                    if owner and owner.email:
                        from .notifications import send_email
                        from flask import current_app
                        group_name = tg.name or tg.telegram_group_id
                        send_email(
                            owner.email,
                            f"Telegizer Digest — {group_name} (delivery failed)",
                            f"<p>Hi {owner.full_name},</p>"
                            f"<p>We were unable to deliver the AI digest for <strong>{group_name}</strong> "
                            f"to Telegram. Please ensure the bot is still a member of the group "
                            f"and has permission to send messages.</p>"
                            f"<p>Error: {exc}</p>",
                        )
                except Exception as mail_exc:
                    _scheduler_log.error("[DIGEST] Email fallback also failed for group %s: %s",
                                         tg.telegram_group_id, mail_exc)


def _run_retention_sweep(app):
    """Daily: archive expiring xp_events into xp_monthly, then cap the append-only
    tables (audit_logs, feature_usage_events, ...) that otherwise grow forever.

    Dry-run by default (RETENTION_DRY_RUN=1): it reports the row counts it *would*
    remove and removes nothing. See backend/retention.py.
    """
    with app.app_context():
        from .retention import run_retention_sweep
        run_retention_sweep(app)


def _run_bot_event_cleanup(retention_days=90):
    """Delete BotEvent rows older than retention_days to prevent unbounded table growth."""
    try:
        from .models import BotEvent
        cutoff = datetime.utcnow() - timedelta(days=retention_days)
        deleted = BotEvent.query.filter(BotEvent.created_at < cutoff).delete(synchronize_session=False)
        db.session.commit()
        if deleted:
            logging.getLogger("scheduler").info("BotEvent retention: deleted %d rows older than %d days", deleted, retention_days)
    except Exception as exc:
        logging.getLogger("scheduler").error("BotEvent retention cleanup failed: %s", exc)
        try:
            db.session.rollback()
        except Exception:
            pass


def _deliver_reminders(app):
    """Send due workspace reminders as Telegram DMs to group owners."""
    import asyncio as _asyncio
    from .models import WorkspaceReminder, User, TelegramBotStarted
    from .official_bot import _runner

    bot = None
    loop = None
    if _runner and _runner.application:
        bot = _runner.application.bot
        loop = _runner.loop
    if not bot or not loop or not loop.is_running():
        return

    now = datetime.utcnow()
    with app.app_context():
        due = WorkspaceReminder.query.filter(
            WorkspaceReminder.remind_at <= now,
            WorkspaceReminder.is_delivered == False,
        ).all()
        for reminder in due:
            user = User.query.get(reminder.owner_user_id)
            if not user:
                reminder.is_delivered = True
                continue

            delivered_via_telegram = False

            # Attempt Telegram DM delivery — check UserTelegramAccount primary first,
            # then fall back to legacy User.telegram_user_id field.
            from .models import UserTelegramAccount as _UTA
            _primary = _UTA.query.filter_by(user_id=user.id, is_primary=True).first()
            _tg_id = (_primary.telegram_user_id if _primary else None) or user.telegram_user_id
            if _tg_id and bot and loop and loop.is_running():
                if TelegramBotStarted.has_started(_tg_id):
                    try:
                        msg_text = f"⏰ *Reminder*\n\n{reminder.reminder_text}"
                        if reminder.telegram_group_id:
                            msg_text += f"\n\n_From group {reminder.telegram_group_id}_"
                        fut = _asyncio.run_coroutine_threadsafe(
                            bot.send_message(
                                chat_id=int(_tg_id),
                                text=msg_text,
                                parse_mode="Markdown",
                            ),
                            loop,
                        )
                        fut.result(timeout=10)
                        delivered_via_telegram = True
                    except Exception as exc:
                        _scheduler_log.error(
                            "Telegram reminder delivery failed for user %s: %s", user.id, exc
                        )

            # Email fallback: send if Telegram delivery was not possible/successful.
            if not delivered_via_telegram:
                try:
                    from .notifications import send_email
                    subject = "Telegizer Reminder"
                    frontend_url = app.config["FRONTEND_URL"]
                    group_line = (
                        f"<p style='color:#888;font-size:13px'>From group {reminder.telegram_group_id}</p>"
                        if reminder.telegram_group_id else ""
                    )
                    html = (
                        f"<h2 style='margin:0 0 8px'>⏰ Reminder</h2>"
                        f"<p>{reminder.reminder_text}</p>"
                        f"{group_line}"
                        f"<hr style='border:none;border-top:1px solid #eee;margin:16px 0'>"
                        f"<p style='color:#888;font-size:12px'>"
                        f"You can manage your reminders in the "
                        f"<a href='{frontend_url}/workspace/reminders'>Telegizer dashboard</a>."
                        f"</p>"
                    )
                    send_email(user.email, subject, html)
                    _scheduler_log.info(
                        "Reminder delivered via email fallback for user %s (reminder %s)",
                        user.id, reminder.id,
                    )
                except Exception as exc:
                    _scheduler_log.error(
                        "Email reminder fallback also failed for user %s (reminder %s): %s",
                        user.id, reminder.id, exc,
                    )
                    # Keep is_delivered=False so we retry on the next scheduler tick.
                    # Reminders older than 24h are force-expired to avoid infinite loops.
                    age_hours = (now - reminder.remind_at).total_seconds() / 3600
                    if age_hours < 24:
                        continue

            reminder.is_delivered = True

        try:
            from .models import db
            db.session.commit()
        except Exception:
            pass


def _deliver_meeting_reminders(app):
    """Send Telegram DMs (or email fallback) for meetings whose reminder window is due."""
    import asyncio as _asyncio
    from .models import Meeting, User, TelegramBotStarted
    from .official_bot import _runner

    bot = None
    loop = None
    if _runner and _runner.application:
        bot = _runner.application.bot
        loop = _runner.loop
    if not bot or not loop or not loop.is_running():
        return

    now = datetime.utcnow()
    with app.app_context():
        from .models import db
        meetings = Meeting.query.filter(
            Meeting.is_complete == False,
            Meeting.reminder_sent == False,
            Meeting.scheduled_at > now,
        ).all()

        for meeting in meetings:
            remind_at = meeting.scheduled_at - timedelta(minutes=meeting.remind_before_minutes)
            if now < remind_at:
                continue

            user = User.query.get(meeting.owner_user_id)
            if not user:
                meeting.reminder_sent = True
                continue

            participants = ""
            if meeting.participants:
                participants = f"\n👥 With: {', '.join(meeting.participants)}"

            msg_text = (
                f"📅 *Meeting in {meeting.remind_before_minutes} minutes*\n\n"
                f"*{meeting.title}*\n"
                f"🕒 {meeting.scheduled_at.strftime('%b %d, %H:%M UTC')}"
                f"{participants}"
            )

            delivered = False
            from .models import UserTelegramAccount as _UTA2
            _mprimary = _UTA2.query.filter_by(user_id=user.id, is_primary=True).first()
            _mtg_id = (_mprimary.telegram_user_id if _mprimary else None) or user.telegram_user_id
            if _mtg_id and TelegramBotStarted.has_started(_mtg_id):
                try:
                    fut = _asyncio.run_coroutine_threadsafe(
                        bot.send_message(chat_id=int(_mtg_id), text=msg_text, parse_mode="Markdown"),
                        loop,
                    )
                    fut.result(timeout=10)
                    delivered = True
                except Exception as exc:
                    _scheduler_log.warning("Meeting reminder TG delivery failed user=%s: %s", user.id, exc)

            if not delivered:
                try:
                    from .notifications import send_email
                    frontend_url = app.config["FRONTEND_URL"]
                    html = (
                        f"<h2>📅 Meeting in {meeting.remind_before_minutes} minutes</h2>"
                        f"<p><strong>{meeting.title}</strong><br>"
                        f"{meeting.scheduled_at.strftime('%b %d, %H:%M UTC')}{participants.replace(chr(10), '<br>')}</p>"
                        f"<p><a href='{frontend_url}/assistant'>View in dashboard</a></p>"
                    )
                    send_email(user.email, f"Meeting Reminder: {meeting.title}", html)
                except Exception as exc:
                    _scheduler_log.warning("Meeting reminder email fallback failed user=%s: %s", user.id, exc)

            meeting.reminder_sent = True

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()


def _run_scheduled_automations(app):
    """Fire 'scheduled' automation workflows whose cron expression is due.

    Supports simple cron patterns via basic interval matching.  We avoid a
    full cron library dependency: instead we store the next_run_at on the
    workflow and re-schedule after each execution.  The scheduler calls this
    every 60 s so granularity is one minute.
    """
    import asyncio as _asyncio
    from .models import db, AutomationWorkflow, AutomationExecution
    from .official_bot import get_official_bot_loop

    bot_obj, loop = get_official_bot_loop()
    if not bot_obj or not loop or not loop.is_running():
        return

    now = datetime.utcnow()
    with app.app_context():
        # Find all active scheduled workflows whose next_run_at is due.
        # We store next_run_at in last_run_at — None means never run yet (run immediately).
        workflows = AutomationWorkflow.query.filter(
            AutomationWorkflow.is_active == True,
            AutomationWorkflow.trigger.op("->>")(
                db.literal("type")
            ) == "scheduled",
        ).all()

        for wf in workflows:
            trigger_params = (wf.trigger or {}).get("params", {})
            # interval_minutes: how often to run (default 60)
            try:
                interval = max(1, int(trigger_params.get("interval_minutes", 60)))
            except (TypeError, ValueError):
                interval = 60

            # Decide if it's time to run
            if wf.last_run_at is not None:
                elapsed = (now - wf.last_run_at).total_seconds() / 60
                if elapsed < interval:
                    continue

            trigger_data = {
                "scheduled_at": now.isoformat(),
                "group_id": wf.source_group_id,
            }

            async def _fire(wf_id=wf.id, wf_obj=wf, td=trigger_data):
                try:
                    with app.app_context():
                        from .models import db, AutomationWorkflow, AutomationExecution
                        from .automation.engine import _execute_action, _check_conditions
                        wf_fresh = AutomationWorkflow.query.get(wf_id)
                        if not wf_fresh or not wf_fresh.is_active:
                            return
                        status = "success"
                        error_msg = None
                        for action in (wf_fresh.actions or []):
                            try:
                                await _execute_action(bot_obj, action, wf_fresh, td, app)
                            except Exception as exc:
                                status = "failed"
                                error_msg = str(exc)[:500]
                        wf_fresh.run_count = (wf_fresh.run_count or 0) + 1
                        wf_fresh.last_run_at = datetime.utcnow()
                        db.session.add(AutomationExecution(
                            workflow_id=wf_id,
                            trigger_type="scheduled",
                            source_group_id=wf_fresh.source_group_id,
                            trigger_data=td,
                            status=status,
                            error_msg=error_msg,
                        ))
                        db.session.commit()

                        if wf_fresh.source_group_id:
                            from .ai_activity import log_ai_activity
                            log_ai_activity(
                                "official", str(wf_fresh.source_group_id), "automation",
                                f"Scheduled workflow ran: {wf_fresh.name or ('#' + str(wf_id))}",
                                detail=f"{len(wf_fresh.actions or [])} action(s)",
                                status="ok" if status == "success" else "failed",
                                source="workflow",
                            )
                except Exception as exc:
                    _scheduler_log.debug("Scheduled automation wf=%s error: %s", wf_id, exc)

            _asyncio.run_coroutine_threadsafe(_fire(), loop)


def _run_member_count_sync(app):
    """Reconcile TelegramGroup.member_count to live Telegram counts.

    Runs in the web process (where tokens + the bot live). The 6h per-process
    gate in the scheduler loop bounds this; getChatMemberCount is a read, so the
    worst case (both Gunicorn workers sweeping the same window) is a handful of
    duplicate, idempotent reads — harmless.
    """
    try:
        with app.app_context():
            from .member_sync import sync_member_counts
            summary = sync_member_counts()
            _scheduler_log.info(
                "member-count sync: synced=%s failed=%s total=%s",
                summary.get("synced"), summary.get("failed"), summary.get("total"),
            )
    except Exception as exc:
        _scheduler_log.error("member-count sync failed: %s", exc)


def _cleanup_message_buffers(app):
    """Delete MessageBuffer rows older than 48 hours."""
    from .models import MessageBuffer
    cutoff = datetime.utcnow() - timedelta(hours=48)
    try:
        with app.app_context():
            from .models import db
            deleted = MessageBuffer.query.filter(MessageBuffer.created_at < cutoff).delete(synchronize_session=False)
            db.session.commit()
            if deleted:
                _scheduler_log.debug("MessageBuffer cleanup: deleted %d rows", deleted)
    except Exception as exc:
        _scheduler_log.debug("MessageBuffer cleanup failed: %s", exc)


def _cleanup_revoked_tokens():
    """Delete expired rows from revoked_tokens to prevent unbounded table growth.

    Called once per day from the scheduler. Uses raw SQL for efficiency since
    this table is not managed by SQLAlchemy ORM in the normal session lifecycle.
    """
    from sqlalchemy import text
    try:
        db.session.execute(text("DELETE FROM revoked_tokens WHERE expires_at < NOW()"))
        db.session.commit()
        _scheduler_log.info("revoked_tokens: expired rows pruned")
    except Exception as exc:
        _scheduler_log.warning("revoked_tokens cleanup failed: %s", exc)
        try:
            db.session.rollback()
        except Exception:
            pass


def _run_task_with_timeout(fn, *args, timeout=30, label="task", flask_app=None):
    """Run *fn* in a worker thread; push an app context in the thread if flask_app is given.

    All errors and timeouts are logged and captured to Sentry so scheduler failures
    surface in alerting rather than disappearing silently into log files.
    """
    import concurrent.futures

    def _run():
        if flask_app is not None:
            with flask_app.app_context():
                return fn(*args)
        return fn(*args)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_run)
        try:
            future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            msg = f"[SCHEDULER] {label} timed out after {timeout}s"
            _scheduler_log.warning(msg)
            try:
                import sentry_sdk
                sentry_sdk.capture_message(msg, level="warning", extras={"job": label, "timeout": timeout})
            except Exception:
                pass
        except Exception as exc:
            _scheduler_log.error("[SCHEDULER] %s error: %s", label, exc, exc_info=True)
            try:
                import sentry_sdk
                with sentry_sdk.push_scope() as scope:
                    scope.set_tag("scheduler_job", label)
                    sentry_sdk.capture_exception(exc)
            except Exception:
                pass


def _run_hub_priority_extraction(app):
    """Assistant Hub: extract from groups that have time-sensitive (priority)
    buffered messages.

    Runs IN-PROCESS inside the web service — where Redis, the DB and the Echo bot
    already live — instead of via a Celery task that calls create_app() (which
    would boot the entire bot fleet inside the worker and hang). The per-group
    Redis lock inside run_extraction makes this safe even if a Celery worker also
    fires the same job.
    """
    from .assistant.hub_message_router import get_groups_with_buffered_messages
    from .assistant.hub_extraction import run_extraction
    pairs = get_groups_with_buffered_messages(priority_only=True)
    for bot_id, group_id in pairs:
        try:
            run_extraction(bot_id, group_id, app)
        except Exception as exc:
            _scheduler_log.error("hub priority extraction bot=%s group=%s: %s", bot_id, group_id, exc)
    if pairs:
        _scheduler_log.info("[SCHEDULER] hub priority extraction processed %d group(s)", len(pairs))


def _run_hub_batch_extraction(app):
    """Assistant Hub: standard extraction pass over ALL groups with buffered
    messages (in-process; see _run_hub_priority_extraction)."""
    from .assistant.hub_message_router import get_groups_with_buffered_messages
    from .assistant.hub_extraction import run_extraction
    pairs = get_groups_with_buffered_messages(priority_only=False)
    for bot_id, group_id in pairs:
        try:
            run_extraction(bot_id, group_id, app)
        except Exception as exc:
            _scheduler_log.error("hub batch extraction bot=%s group=%s: %s", bot_id, group_id, exc)
    if pairs:
        _scheduler_log.info("[SCHEDULER] hub batch extraction processed %d group(s)", len(pairs))


def _run_hub_reminder_delivery(app):
    """Assistant Hub: deliver reminders due soon (in-process). Sends via
    Config.TELEGRAM_BOT_TOKEN + safe_send_message, so no bot loop is needed —
    see _run_hub_priority_extraction for why this lives in the web process."""
    from .assistant.hub_digest import deliver_due_reminders
    sent = deliver_due_reminders(app)
    if sent:
        _scheduler_log.info("[SCHEDULER] hub reminder delivery sent=%d", sent)


def _run_hub_digests(app):
    """Assistant Hub: send daily digests whose configured time has passed (in-process)."""
    from .assistant.hub_digest import deliver_all_due_digests
    sent = deliver_all_due_digests(app)
    if sent:
        _scheduler_log.info("[SCHEDULER] hub digests sent=%d", sent)


def _run_calendar_auto_sync(app):
    """For users who enabled auto-sync, push newly extracted dated meetings to
    their Google Calendar. Idempotent via the calendar_pushed flag; a small batch
    per user keeps each tick well within the task timeout."""
    with app.app_context():
        from .models import GoogleCalendarToken
        from .routes.calendar import sync_pending_meetings_for_user

        try:
            rows = GoogleCalendarToken.query.filter_by(auto_sync_meetings=True).all()
        except Exception as exc:
            _scheduler_log.debug("calendar auto-sync: token query failed: %s", exc)
            return
        pushed = 0
        failed = 0
        for row in rows:
            res = sync_pending_meetings_for_user(row.user_id)
            pushed += res.get("pushed", 0)
            failed += res.get("failed", 0)
        # Always log the tally (debug when idle) so we can tell "nothing to do" from
        # "tried and failed" when a user reports meetings not syncing.
        if pushed or failed:
            _scheduler_log.info(
                "[SCHEDULER] calendar auto-sync tokens=%d pushed=%d failed=%d",
                len(rows), pushed, failed,
            )
        else:
            _scheduler_log.debug(
                "[SCHEDULER] calendar auto-sync idle tokens=%d", len(rows)
            )


def _run_calendar_reverse_sync(app):
    """For users who enabled it, pull upcoming timed Google Calendar events INTO
    Echo Meetings (+ Telegram reminders). Idempotent; dedups by event id."""
    with app.app_context():
        from .models import GoogleCalendarToken
        from .routes.calendar import pull_calendar_events_for_user

        try:
            rows = GoogleCalendarToken.query.filter_by(pull_events=True).all()
        except Exception as exc:
            _scheduler_log.debug("calendar reverse-sync: token query failed: %s", exc)
            return
        imported = updated = removed = 0
        for row in rows:
            res = pull_calendar_events_for_user(row.user_id)
            imported += res.get("imported", 0)
            updated += res.get("updated", 0)
            removed += res.get("removed", 0)
        if imported or updated or removed:
            _scheduler_log.info(
                "[SCHEDULER] calendar reverse-sync tokens=%d imported=%d updated=%d removed=%d",
                len(rows), imported, updated, removed,
            )
        else:
            _scheduler_log.debug("[SCHEDULER] calendar reverse-sync idle tokens=%d", len(rows))


# ── Jobs migrated off the Celery beat schedule ────────────────────────────────────
# The celery-worker service is idled (see railway.worker.toml). It was a second
# always-on container, and every task in it opened with create_app() — which re-ran
# the migrations, started a duplicate set of Telegram bots and spawned another copy
# of this loop, once per task. That is what ran up the Railway GB-minute bill.
#
# The task bodies in scheduler.py are UNCHANGED and still Celery-decorated, so the
# worker can be switched back on at any time; nothing schedules them there any more.
# Intervals and UTC times below are exactly the ones the old beat schedule used.
#
# Deliberately NOT listed (the loop already does this work — listing them would
# double-run it): send_scheduled_messages, send_scheduled_polls, the four hub_* tasks
# (all no-ops), deliver_due_reminders (-> _deliver_reminders), send_meeting_prealerts
# (-> _deliver_meeting_reminders) and cleanup_message_buffer (-> _cleanup_message_buffers,
# which purges at 48h, stricter than the task's 72h).
_CELERY_INTERVAL_JOBS = [
    ("retry_pending_unbans", 60),
    ("expire_pending_verifications", 300),
    ("check_raid_reminders", 300),
    ("check_campaign_lifecycle", 300),
    ("check_group_health", 1800),
    ("recover_missed_payments", 1800),
    ("recompute_xp_periods", 1800),
    ("reconcile_pending_groups_task", 3600),
    ("extract_group_signals", 7200),
    ("ping_all_bots", 21600),
]

_CELERY_DAILY_JOBS = [
    ("expire_trials", 0, 30),
    ("downgrade_expired_subscriptions", 1, 0),
    ("hub_enforce_retention", 3, 15),
    ("scan_fraud_alerts", 7, 0),
    ("send_daily_briefings", 8, 0),
    ("send_renewal_reminders", 9, 0),
    ("check_inactive_groups", 9, 30),
    ("send_onboarding_emails", 10, 0),
    ("send_lifecycle_emails", 10, 0),
]


def _run_hard_delete_sweep(app):
    """GDPR Art. 17: purge accounts soft-deleted more than 30 days ago.

    This replaces `hard_delete_user.apply_async(countdown=30*86400)`, which parked the
    job in Redis for a month — a Redis restart or eviction meant the deletion silently
    never ran. A sweep over User.deleted_at survives anything short of losing the DB.

    hard_delete_user anonymises the row in place (it does not drop it) and leaves
    deleted_at set, so filter out rows it has already processed or the sweep would
    re-purge the same users every day.
    """
    from .models import User
    from .scheduler import hard_delete_user

    with app.app_context():
        cutoff = datetime.utcnow() - timedelta(days=30)
        stale = User.query.filter(
            User.deleted_at.isnot(None),
            User.deleted_at <= cutoff,
            User.email.notlike("deleted_%@deleted.invalid"),
        ).all()
        for user in stale:
            try:
                hard_delete_user(user.id)
            except Exception as exc:
                _scheduler_log.error("[SCHEDULER] hard_delete_user(%s) failed: %s", user.id, exc)
        if stale:
            _scheduler_log.info("[SCHEDULER] hard-delete sweep purged=%d", len(stale))


def _run_celery_jobs(app):
    """Run the jobs that used to live on the Celery beat schedule."""
    from . import scheduler as _sched

    for name, interval in _CELERY_INTERVAL_JOBS:
        job = getattr(_sched, name, None)
        if job is not None and _job_due(app, name, interval):
            _run_task_with_timeout(job, timeout=150, label=name, flask_app=app)

    for name, hour, minute in _CELERY_DAILY_JOBS:
        job = getattr(_sched, name, None)
        if job is not None and _job_due_daily(app, name, hour, minute):
            _run_task_with_timeout(job, timeout=300, label=name, flask_app=app)

    # Hourly, not daily: the old apply_async(countdown=30*86400) fired at exactly the
    # 30-day mark, and we promise the user "removed within 30 days". A daily sweep
    # could land up to 24h late and overshoot that; hourly keeps it tight.
    if _job_due(app, "hard_delete_sweep", 3600):
        _run_task_with_timeout(_run_hard_delete_sweep, app, timeout=300, label="hard_delete_sweep")


def _scheduler_loop(app):
    import time
    _last_expiry_check = [0]
    _last_heartbeat = [0]
    _last_watchdog = [0]
    _last_official_digest = [0]
    _last_event_cleanup = [0]
    _last_buffer_cleanup = [0]
    _last_token_cleanup = [0]
    _last_member_sync = [0]
    _last_hub_priority = [0]
    _last_hub_batch = [0]
    _last_hub_reminders = [0]
    _last_hub_digests = [0]
    _last_calendar_sync = [0]
    _last_calendar_pull = [0]
    time.sleep(15)  # Wait for bots to fully start
    while True:
        try:
            now_ts = time.time()
            # Each task gets its own app context inside its worker thread.
            # app.app_context() is thread-local — it does NOT propagate to ThreadPoolExecutor threads.
            _run_task_with_timeout(_run_scheduled_messages, timeout=30, label="_run_scheduled_messages", flask_app=app)
            _run_task_with_timeout(_run_scheduled_polls, timeout=30, label="_run_scheduled_polls", flask_app=app)
            _run_task_with_timeout(_run_official_scheduled_messages, timeout=30, label="_run_official_scheduled_messages", flask_app=app)
            _run_task_with_timeout(_run_official_scheduled_polls, timeout=30, label="_run_official_scheduled_polls", flask_app=app)
            # Check subscription expiry warnings every 6 hours
            if now_ts - _last_expiry_check[0] > 6 * 3600:
                _last_expiry_check[0] = now_ts
                _run_task_with_timeout(_run_expiry_notifications, timeout=30, label="_run_expiry_notifications", flask_app=app)
            # Bot health heartbeat every 5 minutes
            if now_ts - _last_heartbeat[0] > 300:
                _last_heartbeat[0] = now_ts
                _run_task_with_timeout(bot_manager.heartbeat, app, timeout=30, label="bot_heartbeat")
            # Bot watchdog: restart dead threads every 2 minutes
            if now_ts - _last_watchdog[0] > 120:
                _last_watchdog[0] = now_ts
                _run_task_with_timeout(_watchdog_bots, app, timeout=30, label="_watchdog_bots")
            # BotEvent retention: purge rows older than 90 days, once per day
            if now_ts - _last_event_cleanup[0] > 86400:
                _last_event_cleanup[0] = now_ts
                _run_task_with_timeout(_run_bot_event_cleanup, timeout=30, label="_run_bot_event_cleanup", flask_app=app)
            # Retention sweep (xp_events roll-up + the other append-only tables): once
            # per day. Gated on scheduled_job_runs rather than an in-memory counter so a
            # redeploy cannot re-fire it, and batched internally so it never long-locks.
            if _job_due(app, "retention_sweep", 86400):
                _run_task_with_timeout(_run_retention_sweep, app, timeout=600, label="_run_retention_sweep")
            # Revoked token TTL cleanup: once per day
            if now_ts - _last_token_cleanup[0] > 86400:
                _last_token_cleanup[0] = now_ts
                _run_task_with_timeout(_cleanup_revoked_tokens, timeout=30, label="_cleanup_revoked_tokens", flask_app=app)
                _run_task_with_timeout(_cleanup_pending_verifications, timeout=30, label="_cleanup_pending_verifications", flask_app=app)
            _run_task_with_timeout(run_digest_scheduler, app, timeout=90, label="run_digest_scheduler")
            # Official group digest: check every 30 minutes
            if now_ts - _last_official_digest[0] > 1800:
                _last_official_digest[0] = now_ts
                _run_task_with_timeout(_run_official_group_digests, app, timeout=90, label="_run_official_group_digests")
            # Workspace reminder delivery: every 60s (already in loop)
            _run_task_with_timeout(_deliver_reminders, app, timeout=30, label="_deliver_reminders")
            # Meeting reminder delivery: every 60s
            _run_task_with_timeout(_deliver_meeting_reminders, app, timeout=30, label="_deliver_meeting_reminders")
            # Scheduled automations: check every 60s
            _run_task_with_timeout(_run_scheduled_automations, app, timeout=30, label="_run_scheduled_automations")
            # Engagement campaign group-post retry: every 60s
            _run_task_with_timeout(_run_campaign_post_retry, timeout=90, label="_run_campaign_post_retry", flask_app=app)
            # Message buffer cleanup: every 6 hours
            if now_ts - _last_buffer_cleanup[0] > 21600:
                _last_buffer_cleanup[0] = now_ts
                _run_task_with_timeout(_cleanup_message_buffers, app, timeout=30, label="_cleanup_message_buffers")
            # Live Telegram member-count reconciliation: every 6 hours
            if now_ts - _last_member_sync[0] > 21600:
                _last_member_sync[0] = now_ts
                _run_task_with_timeout(_run_member_count_sync, app, timeout=120, label="_run_member_count_sync")
            # Assistant Hub (Echo) extraction — runs in-process so it works without a
            # separate Celery worker. Priority (time-sensitive) every 2 min, full
            # sweep every 30 min. Lock-guarded per group inside run_extraction.
            if now_ts - _last_hub_priority[0] > 120:
                _last_hub_priority[0] = now_ts
                _run_task_with_timeout(_run_hub_priority_extraction, app, timeout=150, label="_run_hub_priority_extraction")
            if now_ts - _last_hub_batch[0] > 1800:
                _last_hub_batch[0] = now_ts
                _run_task_with_timeout(_run_hub_batch_extraction, app, timeout=150, label="_run_hub_batch_extraction")
            # Hub reminder delivery every 5 min; daily digests checked every 10 min.
            if now_ts - _last_hub_reminders[0] > 300:
                _last_hub_reminders[0] = now_ts
                _run_task_with_timeout(_run_hub_reminder_delivery, app, timeout=60, label="_run_hub_reminder_delivery")
            if now_ts - _last_hub_digests[0] > 600:
                _last_hub_digests[0] = now_ts
                _run_task_with_timeout(_run_hub_digests, app, timeout=90, label="_run_hub_digests")
            # Google Calendar auto-sync of new Echo meetings: every 5 min
            if now_ts - _last_calendar_sync[0] > 300:
                _last_calendar_sync[0] = now_ts
                _run_task_with_timeout(_run_calendar_auto_sync, app, timeout=90, label="_run_calendar_auto_sync")
            # Reverse sync (Google Calendar → Echo meetings + reminders): every 15 min
            if now_ts - _last_calendar_pull[0] > 900:
                _last_calendar_pull[0] = now_ts
                _run_task_with_timeout(_run_calendar_reverse_sync, app, timeout=120, label="_run_calendar_reverse_sync")
            # Jobs that used to run on the Celery beat schedule. Gated on the
            # scheduled_job_runs table, not in-memory counters, so a redeploy cannot
            # re-fire the daily email blasts.
            _run_celery_jobs(app)
        except Exception as exc:
            # During a redeploy/restart the process gets SIGTERM and the
            # interpreter starts tearing down. A scheduler tick mid-shutdown
            # can't spin up its ThreadPoolExecutor and Python raises
            # "cannot schedule new futures after interpreter shutdown". That's
            # routine shutdown noise on the dying container — exit the loop
            # quietly instead of paging us with a false high-priority alert.
            if "interpreter shutdown" in str(exc) or "cannot schedule new futures" in str(exc):
                break
            _scheduler_log.error(f"Scheduler loop error: {exc}")
        time.sleep(60)


def _run_campaign_post_retry():
    """Auto-(re)post active Engagement Campaigns that haven't reached the group yet.

    The campaign-create request posts immediately, but if the bot loop wasn't
    ready in that web worker (or Telegram hiccuped) the post is recorded as
    'failed'/'none'. This runs in the web process — where the official/custom bot
    loops actually live — and retries delivery. An atomic status claim prevents
    the two Gunicorn workers from double-posting the same campaign.
    """
    from .models import EngagementCampaign
    from . import engagement_telegram as et
    now = datetime.utcnow()
    try:
        # Small batch per tick so the loop always finishes within the task
        # timeout (a kill mid-send could otherwise leave a row stuck in 'posting').
        candidates = EngagementCampaign.query.filter(
            EngagementCampaign.status == "active",
            EngagementCampaign.post_status.in_(["none", "failed"]),
        ).order_by(EngagementCampaign.created_at.asc()).limit(8).all()
    except Exception as exc:
        _scheduler_log.debug("campaign post-retry query failed: %s", exc)
        return
    for c in candidates:
        if c.ends_at and c.ends_at <= now:
            continue  # already expired — lifecycle job will close it
        try:
            # Atomic claim: only the worker that flips none/failed → posting sends.
            claimed = db.session.execute(
                text(
                    "UPDATE engagement_campaigns SET post_status='posting' "
                    "WHERE id=:id AND post_status IN ('none','failed')"
                ),
                {"id": c.id},
            ).rowcount
            db.session.commit()
        except Exception:
            db.session.rollback()
            continue
        if not claimed:
            continue
        try:
            db.session.refresh(c)
            et.publish_campaign(c)  # records 'posted' or 'failed'
        except Exception:
            _scheduler_log.exception("campaign post-retry failed for %s", c.id)
            try:
                db.session.rollback()
            except Exception:
                pass


def _cleanup_pending_verifications():
    """Delete expired pending_verifications rows (stale CAPTCHA/quiz prompts)."""
    from .models import PendingVerification
    try:
        deleted = PendingVerification.query.filter(
            PendingVerification.expires_at < datetime.utcnow()
        ).delete(synchronize_session=False)
        if deleted:
            db.session.commit()
            _scheduler_log.info("[CLEANUP] Deleted %d expired pending_verifications", deleted)
    except Exception as exc:
        _scheduler_log.error("[CLEANUP] pending_verifications cleanup error: %s", exc)
        try:
            db.session.rollback()
        except Exception:
            pass


def _run_expiry_notifications():
    """Send in-app + email expiry warning notifications at 5-day, 1-day, and day-of marks."""
    from .models import User, UserNotification
    from .routes.notifications import create_notification
    from .notifications import send_subscription_expiry_warning, send_subscription_expired
    now = datetime.utcnow()
    five_days = now + timedelta(days=5)
    grace_end = now - timedelta(days=3)  # subscriptions expired up to 3 days ago (grace period)
    try:
        # Warn: expiring in next 5 days
        expiring_soon = User.query.filter(
            User.subscription_expires.isnot(None),
            User.subscription_tier != "free",
            User.subscription_expires > now,
            User.subscription_expires <= five_days,
        ).all()
        for user in expiring_soon:
            days_left = max(0, (user.subscription_expires - now).days)
            notif_type = "plan_expiring_1d" if days_left <= 1 else "plan_expiring_5d"
            recent = UserNotification.query.filter(
                UserNotification.user_id == user.id,
                UserNotification.type == notif_type,
                UserNotification.created_at >= now - timedelta(hours=12),
            ).first()
            if recent:
                continue
            label = "tomorrow" if days_left <= 1 else f"in {days_left} days"
            expires_str = user.subscription_expires.strftime("%Y-%m-%d")
            create_notification(
                user.id, notif_type,
                "Subscription Expiring Soon",
                f"Your {user.subscription_tier.capitalize()} plan expires {label} "
                f"({expires_str}). Renew now to avoid interruption.",
                {"expires": user.subscription_expires.isoformat(), "days_left": days_left},
            )
            try:
                send_subscription_expiry_warning(
                    user.email, user.full_name, user.subscription_tier,
                    expires_str, max(1, days_left),
                )
                _scheduler_log.info(
                    "Sent expiry warning email to user %d (%s) — %d days left",
                    user.id, user.email, days_left,
                )
            except Exception as email_exc:
                _scheduler_log.error("Failed to send expiry warning email to user %d: %s", user.id, email_exc)

        # Day-of-expiry: send once when subscription has just lapsed (within 3-day grace window)
        just_expired = User.query.filter(
            User.subscription_expires.isnot(None),
            User.subscription_tier != "free",
            User.subscription_expires <= now,
            User.subscription_expires > grace_end,
        ).all()
        for user in just_expired:
            recent = UserNotification.query.filter(
                UserNotification.user_id == user.id,
                UserNotification.type == "plan_expired",
                UserNotification.created_at >= now - timedelta(hours=12),
            ).first()
            if recent:
                continue
            create_notification(
                user.id, "plan_expired",
                "Subscription Expired",
                f"Your {user.subscription_tier.capitalize()} plan has expired. "
                f"You have a 3-day grace period. Renew to avoid service interruption.",
                {},
            )
            try:
                send_subscription_expired(user.email, user.full_name, user.subscription_tier)
                _scheduler_log.info("Sent expired email to user %d", user.id)
            except Exception as email_exc:
                _scheduler_log.error("Failed to send expired email to user %d: %s", user.id, email_exc)
    except Exception as exc:
        _scheduler_log.error("Expiry notification error: %s", exc, exc_info=True)


def _run_official_scheduled_messages():
    """Deliver due OfficialScheduledMessage rows via the official bot."""
    import asyncio
    from .models import db, OfficialScheduledMessage

    try:
        locked = db.session.execute(
            text("SELECT pg_try_advisory_xact_lock(2003)")
        ).scalar()
        if not locked:
            return
    except Exception:
        pass

    now = datetime.utcnow()
    pending = OfficialScheduledMessage.query.filter(
        OfficialScheduledMessage.send_at <= now,
        OfficialScheduledMessage.is_sent == False,
    ).all()

    if not pending:
        return

    from .official_bot import get_official_bot_loop
    bot_obj, loop = get_official_bot_loop()
    if not bot_obj or not loop or not loop.is_running():
        _scheduler_log.warning("[SCHEDULER] Official bot loop not running — skipping official scheduled messages")
        return

    _scheduler_log.info("[SCHEDULER] %d official scheduled message(s) due", len(pending))

    for msg in pending:
        async def _send(m=msg):
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
                    "chat_id": m.telegram_group_id,
                    "text": m.message_text,
                    "parse_mode": "Markdown",
                    "reply_markup": keyboard,
                    "disable_web_page_preview": not getattr(m, "link_preview_enabled", True),
                }
                if m.topic_id:
                    send_kwargs["message_thread_id"] = m.topic_id
                sent = await bot_obj.send_message(**send_kwargs)
                if m.pin_message:
                    await bot_obj.pin_chat_message(chat_id=m.telegram_group_id, message_id=sent.message_id)
                if m.auto_delete_after:
                    import asyncio as _as
                    await _as.sleep(m.auto_delete_after)
                    await bot_obj.delete_message(chat_id=m.telegram_group_id, message_id=sent.message_id)
            except Exception as exc:
                _scheduler_log.error("Official scheduled message %s send error: %s", m.id, exc)

        asyncio.run_coroutine_threadsafe(_send(), loop)

        from .ai_activity import log_ai_activity
        log_ai_activity(
            "official", str(msg.telegram_group_id), "automation",
            f"Scheduled message sent: {msg.title or 'untitled'}",
            detail=(msg.message_text or "")[:200],
            source="scheduled_message", commit=False,
        )

        if msg.repeat_interval:
            msg.send_at = now + timedelta(minutes=msg.repeat_interval)
            if msg.stop_date and msg.send_at > msg.stop_date:
                msg.is_sent = True
        else:
            msg.is_sent = True

    db.session.commit()
    _scheduler_log.info("[SCHEDULER] Finished processing %d official scheduled messages", len(pending))


def _run_official_scheduled_polls():
    """Deliver due OfficialPoll rows via the official bot."""
    import asyncio
    from .models import db, OfficialPoll

    try:
        locked = db.session.execute(
            text("SELECT pg_try_advisory_xact_lock(2004)")
        ).scalar()
        if not locked:
            return
    except Exception:
        pass

    now = datetime.utcnow()
    pending = OfficialPoll.query.filter(
        OfficialPoll.scheduled_at <= now,
        OfficialPoll.scheduled_at != None,
        OfficialPoll.is_sent == False,
    ).all()

    if not pending:
        return

    from .official_bot import get_official_bot_loop
    bot_obj, loop = get_official_bot_loop()
    if not bot_obj or not loop or not loop.is_running():
        _scheduler_log.warning("[SCHEDULER] Official bot loop not running — skipping official scheduled polls")
        return

    _scheduler_log.info("[SCHEDULER] %d official poll(s) due", len(pending))

    for poll in pending:
        async def _send(p=poll):
            try:
                kwargs = {
                    "chat_id": p.telegram_group_id,
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
                await bot_obj.send_poll(**kwargs)
            except Exception as exc:
                _scheduler_log.error("Official poll %s send error: %s", p.id, exc)

        asyncio.run_coroutine_threadsafe(_send(), loop)
        poll.is_sent = True

        from .ai_activity import log_ai_activity
        log_ai_activity(
            "official", str(poll.telegram_group_id), "automation",
            "Scheduled poll sent",
            detail=(poll.question or "")[:200],
            source="scheduled_poll", commit=False,
        )

    db.session.commit()
    _scheduler_log.info("[SCHEDULER] Finished processing %d official polls", len(pending))


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
        with bot_manager._lock:
            instance = bot_manager.active_bots.get(bot.id)
        if not instance or not instance.application:
            _scheduler_log.warning(
                f"[SCHEDULER] msg id={msg.id} title='{msg.title}' skipped — "
                f"bot {bot.id} not running"
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

        from .ai_activity import log_ai_activity
        log_ai_activity(
            "custom", str(group.id), "automation",
            f"Scheduled message sent: {msg.title or 'untitled'}",
            detail=(msg.message_text or "")[:200],
            source="scheduled_message", commit=False,
        )

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
        with bot_manager._lock:
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

        from .ai_activity import log_ai_activity
        log_ai_activity(
            "custom", str(group.id), "automation",
            "Scheduled poll sent",
            detail=(poll.question or "")[:200],
            source="scheduled_poll", commit=False,
        )

    if pending:
        db.session.commit()
        _scheduler_log.info(f"[SCHEDULER] Finished processing {len(pending)} scheduled polls")


app = create_app()

# ── Redis startup probe ───────────────────────────────────────────────────────
# Runs once per gunicorn worker at import time so Railway logs show clearly
# whether Redis is reachable.  Never raises — a missing Redis is non-fatal
# (rate limiter degrades to in-process fallback).
def _probe_redis():
    _log = logging.getLogger("startup")
    redis_url = app.config.get("REDIS_URL", "")
    if not redis_url:
        _log.warning(
            "[REDIS] REDIS_URL is not set — rate limiting will use in-process "
            "fallback (not shared across workers). Add REDIS_URL in Railway to "
            "enable full rate limiting."
        )
        return
    try:
        import redis as _redis_lib
        r = _redis_lib.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2)
        r.ping()
        info = r.info("server")
        _log.info(
            "[REDIS] Connected OK — version=%s mode=%s",
            info.get("redis_version", "?"),
            info.get("redis_mode", "standalone"),
        )
    except Exception as _e:
        _log.error(
            "[REDIS] Connection FAILED — %s. Rate limiting will fall back to "
            "in-process counter. Check REDIS_URL in Railway environment.",
            _e,
        )

_probe_redis()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
