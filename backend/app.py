import os
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
        return jsonify({"status": "ok"})

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(500)
    def server_error(e):
        return jsonify({"error": "Internal server error"}), 500

    with app.app_context():
        db.create_all()
        _run_migrations()
        _restart_active_bots(app)

    return app


def _run_migrations():
    """Add any missing columns to existing tables without dropping data."""
    migrations = [
        "ALTER TABLE groups ADD COLUMN IF NOT EXISTS telegram_member_count INTEGER DEFAULT 0",
        # Invite link creator tracking
        "ALTER TABLE invite_links ADD COLUMN IF NOT EXISTS created_by_user_id INTEGER",
        "ALTER TABLE invite_links ADD COLUMN IF NOT EXISTS created_by_telegram_id VARCHAR(255)",
        "ALTER TABLE invite_links ADD COLUMN IF NOT EXISTS created_by_username VARCHAR(255)",
        # Scheduled messages — topic_id added later
        "ALTER TABLE scheduled_messages ADD COLUMN IF NOT EXISTS topic_id BIGINT",
        "ALTER TABLE scheduled_messages ADD COLUMN IF NOT EXISTS auto_delete_after INTEGER",
        "ALTER TABLE scheduled_messages ADD COLUMN IF NOT EXISTS link_preview_enabled BOOLEAN DEFAULT TRUE",
        # User API keys table columns
        "ALTER TABLE user_api_keys ADD COLUMN IF NOT EXISTS base_url VARCHAR(500)",
        "ALTER TABLE user_api_keys ADD COLUMN IF NOT EXISTS model_name VARCHAR(255)",
        "ALTER TABLE user_api_keys ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW()",
    ]
    try:
        with db.engine.connect() as conn:
            for sql in migrations:
                try:
                    conn.execute(text(sql))
                except Exception:
                    pass
            conn.commit()
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


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
