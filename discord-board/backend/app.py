"""Guildizer Flask API (Phase 0).

Standalone web service for the dashboard. Runs separately from the Discord bot
(see bot.py). Zero imports from the Telegizer codebase.
"""
from flask import Flask, jsonify
from flask_cors import CORS

from auth import auth_bp
from config import Config
from database import init_db
from guilds_api import guilds_bp
from leveling_api import leveling_bp
from protection_api import protection_bp
from settings_api import settings_bp


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = Config.SECRET_KEY

    # Allow the Vite dev server + (later) the production dashboard.
    CORS(app, resources={r"/*": {"origins": [Config.FRONTEND_URL]}}, supports_credentials=True)

    init_db()

    app.register_blueprint(auth_bp)
    app.register_blueprint(guilds_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(protection_bp)
    app.register_blueprint(leveling_bp)

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
