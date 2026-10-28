"""GET /api/bots/<id>/groups lists private groups too (but not 1:1 chats).

Run from the repo root:  python -m pytest backend/tests/test_bot_groups_list.py
"""
import os

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-with-enough-length-1234")
os.environ.setdefault("ENCRYPTION_KEY", "Zm9vYmFyYmF6cXV4Zm9vYmFyYmF6cXV4Zm9vYmFyYmE=")
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("DISABLE_BACKGROUND_THREADS", "1")

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from backend.models import db, User, Bot, Group
from backend.routes.bots import bots_bp
import backend.assistant.hub_models  # noqa: F401


@pytest.fixture()
def env():
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI="sqlite://", JWT_SECRET_KEY=os.environ["JWT_SECRET_KEY"],
                      JWT_TOKEN_LOCATION=["headers"], TESTING=True, SECRET_KEY="x",
                      SQLALCHEMY_ENGINE_OPTIONS={"connect_args": {"check_same_thread": False}})
    db.init_app(app)
    JWTManager(app)
    app.register_blueprint(bots_bp, url_prefix="/api/bots")
    with app.app_context():
        db.create_all()
        u = User(email="a@x.io", full_name="A", auth_provider="email")
        db.session.add(u)
        db.session.flush()
        b = Bot(user_id=u.id, bot_token="x", bot_username="a_bot")
        db.session.add(b)
        db.session.flush()
        for i, (name, uname, ctype) in enumerate([
            ("public", "pubgroup", "supergroup"),
            ("private", "", "supergroup"),
            ("unknown", None, "group"),
            ("dm", "", "private"),
        ]):
            db.session.add(Group(bot_id=b.id, telegram_group_id=str(-100 - i), group_name=name,
                                 chat_username=uname, chat_type=ctype))
        db.session.commit()
        hdr = {"Authorization": "Bearer " + create_access_token(identity=str(u.id))}
        yield app.test_client(), hdr, b.id


def test_private_groups_listed_dms_not(env):
    client, hdr, bot_id = env
    r = client.get(f"/api/bots/{bot_id}/groups", headers=hdr)
    assert r.status_code == 200
    names = {g["group_name"] for g in r.get_json()["groups"]}
    assert names == {"public", "private", "unknown"}
