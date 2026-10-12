"""The platform-AI daily quota must be enforced in TOKENS, not just in requests.

Regression: with Redis up, the per-user check INCR'd a counter by 1 per request and compared it with the
token limit (200,000 on Pro), so the token ledger (workspace_ai_tokens_today) was never consulted.

Run from the repo root:  python -m pytest backend/tests/test_ai_token_quota.py
"""
import os

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-with-enough-length-1234")
os.environ.setdefault("ENCRYPTION_KEY", "Zm9vYmFyYmF6cXV4Zm9vYmFyYmF6cXV4Zm9vYmFyYmE=")
os.environ.setdefault("DATABASE_URL", "sqlite://")

from datetime import datetime

import pytest
from flask import Flask

from backend.models import db, User
import backend.assistant.hub_models  # noqa: F401
from backend.assistant import ai_key_resolver as kr


@pytest.fixture()
def env(monkeypatch):
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI="sqlite://", TESTING=True, SECRET_KEY="x",
                      SQLALCHEMY_ENGINE_OPTIONS={"connect_args": {"check_same_thread": False}})
    db.init_app(app)
    # Redis "up" and under its request-count limit; no spend circuit; a platform key exists.
    monkeypatch.setattr(kr, "_redis_check_and_increment", lambda uid, limit: True)
    monkeypatch.setattr(kr, "_check_platform_cost_circuit", lambda: None)
    from backend import secret_vault
    monkeypatch.setattr(secret_vault, "get_secret", lambda name: "sk-platform")
    monkeypatch.delenv("AI_TOKEN_QUOTA_ENFORCE", raising=False)
    with app.app_context():
        db.create_all()
        u = User(email="p@x.io", full_name="Pro", auth_provider="email", subscription_tier="pro")
        u.workspace_ai_tokens_reset_at = datetime.utcnow()
        db.session.add(u)
        db.session.commit()
        yield u


def test_token_ledger_over_limit_blocks_even_when_redis_is_up(env):
    env.workspace_ai_tokens_today = 200_000
    db.session.commit()
    with pytest.raises(kr.QuotaExceededError):
        kr.get_workspace_ai_key(env)


def test_under_limit_still_resolves_the_platform_key(env):
    env.workspace_ai_tokens_today = 199_999
    db.session.commit()
    assert kr.get_workspace_ai_key(env)["source"] == "platform"


def test_kill_switch_restores_request_count_only_behaviour(env, monkeypatch):
    env.workspace_ai_tokens_today = 900_000
    db.session.commit()
    monkeypatch.setenv("AI_TOKEN_QUOTA_ENFORCE", "0")
    assert kr.get_workspace_ai_key(env)["source"] == "platform"


def test_free_tier_still_gets_the_upgrade_message(env):
    env.subscription_tier = "free"
    db.session.commit()
    with pytest.raises(kr.QuotaExceededError, match="Free plan"):
        kr.get_workspace_ai_key(env)
