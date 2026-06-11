"""Guildizer Flask API (Phase 0).

Standalone web service for the dashboard. Runs separately from the Discord bot
(see bot.py). Zero imports from the Telegizer codebase.
"""
from urllib.parse import urlparse

from flask import Flask, jsonify, request
from flask_cors import CORS

from admin_api import admin_bp
from auth import auth_bp
from automation_api import automation_bp
from billing_api import billing_bp
from campaigns_api import campaigns_bp
from config import Config
from content_api import content_bp
from crm_api import crm_bp
from custom_bots_api import custom_bots_bp
from database import init_db
from growth_api import growth_bp
from guilds_api import guilds_bp
from knowledge_api import knowledge_bp
from leveling_api import leveling_bp
from protection_api import protection_bp
from settings_api import settings_bp
from team_api import team_bp


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = Config.SECRET_KEY

    # Allow the Vite dev server + (later) the production dashboard.
    CORS(app, resources={r"/*": {"origins": [Config.FRONTEND_URL]}}, supports_credentials=True)

    # CSRF defense-in-depth: state-changing requests from a browser must come
    # from our own frontend. Server-to-server callers (NOWPayments IPN, inbound
    # webhooks) send no Origin header, so they pass untouched.
    _allowed_origin = urlparse(Config.FRONTEND_URL).netloc.lower()

    @app.before_request
    def _reject_cross_site_writes():
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return None
        origin = request.headers.get("Origin")
        if not origin:
            return None
        if urlparse(origin).netloc.lower() != _allowed_origin:
            return jsonify(error="cross_origin_rejected"), 403
        return None

    init_db()

    app.register_blueprint(auth_bp)
    app.register_blueprint(guilds_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(protection_bp)
    app.register_blueprint(leveling_bp)
    app.register_blueprint(campaigns_bp)
    app.register_blueprint(billing_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(custom_bots_bp)
    app.register_blueprint(content_bp)
    app.register_blueprint(automation_bp)
    app.register_blueprint(growth_bp)
    app.register_blueprint(crm_bp)
    app.register_blueprint(knowledge_bp)
    app.register_blueprint(team_bp)

    @app.get("/")
    def root():
        return jsonify(service="guildizer-api", status="ok")

    @app.get("/health")
    def health():
        return jsonify(
            service="guildizer-api",
            status="healthy",
            discord_client_id=Config.DISCORD_CLIENT_ID or None,
        )

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=Config.PORT, debug=True)
