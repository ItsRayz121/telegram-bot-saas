"""Public directory view/contact counters: atomic, 404 for unknown/private, rate limited.

Run from the repo root:  python -m pytest backend/tests/test_public_counters.py
"""
import os

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-with-enough-length-1234")
os.environ.setdefault("ENCRYPTION_KEY", "Zm9vYmFyYmF6cXV4Zm9vYmFyYmF6cXV4Zm9vYmFyYmE=")
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager

from backend.models import db, User, DirectoryListing
import backend.assistant.hub_models  # noqa: F401
from backend.routes.directory import directory_bp
from backend.middleware import rate_limit as rl


@pytest.fixture()
def env(monkeypatch):
    rl._fallback_counts.clear()
    monkeypatch.setattr(rl, "_get_redis", lambda: None)   # force the in-process limiter
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI="sqlite://", JWT_SECRET_KEY=os.environ["JWT_SECRET_KEY"],
                      TESTING=True, SECRET_KEY="x",
                      SQLALCHEMY_ENGINE_OPTIONS={"connect_args": {"check_same_thread": False}})
    db.init_app(app)
    JWTManager(app)
    app.register_blueprint(directory_bp)
    with app.app_context():
        db.create_all()
        u = User(email="o@x.io", full_name="O", auth_provider="email")
        db.session.add(u)
        db.session.flush()
        mk = lambda **kw: DirectoryListing(user_id=u.id, listing_type="group", title="T", category="Crypto",
                                           telegram_link="https://t.me/x", **kw)
        pub, priv = mk(is_public=True), mk(is_public=False)
        db.session.add_all([pub, priv])
        db.session.commit()
        ids = (pub.id, priv.id)
    return app.test_client(), ids, app


def test_counters_increment_and_hide_private(env):
    client, (pub, priv), app = env
    assert client.post(f"/api/directory/{pub}/view").status_code == 200
    assert client.post(f"/api/directory/{pub}/view").status_code == 200
    assert client.post(f"/api/directory/{pub}/contact").status_code == 200
    assert client.post(f"/api/directory/{priv}/view").status_code == 404
    assert client.post("/api/directory/9999/contact").status_code == 404
    with app.app_context():
        row = db.session.get(DirectoryListing, pub)
        assert (row.view_count, row.contact_count) == (2, 1)
        assert (db.session.get(DirectoryListing, priv).view_count or 0) == 0


def test_counters_are_rate_limited(env):
    client, (pub, _), app = env
    codes = [client.post(f"/api/directory/{pub}/contact").status_code for _ in range(14)]
    assert codes[:10] == [200] * 10 and set(codes[10:]) == {429}
    with app.app_context():
        assert db.session.get(DirectoryListing, pub).contact_count == 10   # throttled hits never wrote
