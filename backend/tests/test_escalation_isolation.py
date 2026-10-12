"""Official-bot escalation endpoints must be scoped to groups the caller can access.

Run from the repo root:  python -m pytest backend/tests/test_escalation_isolation.py
"""
import os

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-with-enough-length-1234")
os.environ.setdefault("ENCRYPTION_KEY", "Zm9vYmFyYmF6cXV4Zm9vYmFyYmF6cXV4Zm9vYmFyYmE=")
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from backend.models import db, User, TelegramGroup, EscalationEvent
import backend.assistant.hub_models  # noqa: F401
from backend.routes.settings import settings_bp


@pytest.fixture()
def env():
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI="sqlite://", JWT_SECRET_KEY=os.environ["JWT_SECRET_KEY"],
                      JWT_TOKEN_LOCATION=["headers"], TESTING=True, SECRET_KEY="x",
                      SQLALCHEMY_ENGINE_OPTIONS={"connect_args": {"check_same_thread": False}})
    db.init_app(app)
    JWTManager(app)
    app.register_blueprint(settings_bp)
    with app.app_context():
        db.create_all()
        owner = User(email="o@x.io", full_name="Owner", auth_provider="email")
        stranger = User(email="s@x.io", full_name="Stranger", auth_provider="email")
        db.session.add_all([owner, stranger])
        db.session.flush()
        db.session.add(TelegramGroup(telegram_group_id="-100A", title="A", owner_user_id=owner.id, bot_status="active"))
        ev = EscalationEvent(telegram_group_id="-100A", bot_id=None, issue_type="ai_kb",
                             original_content="private customer question", status="pending")
        db.session.add(ev)
        db.session.commit()
        hdr = lambda u: {"Authorization": "Bearer " + create_access_token(identity=str(u.id))}
        return app.test_client(), hdr(owner), hdr(stranger), ev.id, app


def test_stranger_cannot_read_or_modify_escalations(env):
    client, owner, stranger, eid, app = env
    r = client.get("/api/telegram-groups/-100A/escalations", headers=stranger)
    # a JSON 404 from our handler, not Flask's HTML "no such route" page
    assert r.status_code == 404 and r.is_json and r.get_json()["error"] == "Not found"
    assert b"private customer question" not in r.data
    r = client.patch(f"/api/telegram-groups/-100A/escalations/{eid}", headers=stranger,
                     json={"status": "resolved", "admin_answer": "pwned"})
    assert r.status_code == 404 and r.is_json
    with app.app_context():
        ev = db.session.get(EscalationEvent, eid)
        assert ev.status == "pending" and ev.admin_answer is None


def test_owner_still_can_read_and_resolve(env):
    client, owner, _, eid, _ = env
    r = client.get("/api/telegram-groups/-100A/escalations", headers=owner)
    assert r.status_code == 200 and len(r.get_json()["escalations"]) == 1
    r = client.patch(f"/api/telegram-groups/-100A/escalations/{eid}", headers=owner,
                     json={"status": "resolved", "admin_answer": "done"})
    assert r.status_code == 200 and r.get_json()["status"] == "resolved"
