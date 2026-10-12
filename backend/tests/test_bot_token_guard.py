"""A bot whose Telegram token is rejected stops retrying and goes offline.

Run from the repo root:  python -m pytest backend/tests/test_bot_token_guard.py
In-memory SQLite; the Telegram polling call is faked.
"""
import os
import threading

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-with-enough-length-1234")
os.environ.setdefault("ENCRYPTION_KEY", "Zm9vYmFyYmF6cXV4Zm9vYmFyYmF6cXV4Zm9vYmFyYmE=")
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from flask import Flask
from telegram.error import Conflict, InvalidToken, NetworkError

from backend import bot_manager as bm
from backend import bot_token_guard as guard
from backend.models import Bot, CustomBot, User, db
import backend.assistant.hub_models  # noqa: F401


@pytest.fixture()
def app():
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI="sqlite://", TESTING=True, SECRET_KEY="x",
                      SQLALCHEMY_ENGINE_OPTIONS={"connect_args": {"check_same_thread": False}})
    db.init_app(app)
    with app.app_context():
        db.create_all()
        user = User(email="o@example.com", password_hash="x", full_name="Owner")
        db.session.add(user)
        db.session.flush()
        bot = Bot(user_id=user.id, bot_token="enc", bot_username="mybot", is_active=True)
        twin = CustomBot(owner_user_id=user.id, bot_username="mybot",
                         bot_token_encrypted="enc", status="active")
        db.session.add_all([bot, twin])
        db.session.commit()
        app.bot_id, app.twin_id = bot.id, twin.id
    return app


def _instance(app, errors):
    """A BotInstance whose polling raises each error in turn, then exits cleanly."""
    inst = bm.BotInstance.__new__(bm.BotInstance)
    inst.bot_id = app.bot_id
    inst.token = "123:abc"
    inst.app_context = app
    inst._stop_event = threading.Event()
    inst.calls = 0
    inst.health = []
    queue = list(errors)

    async def fake_polling():
        inst.calls += 1
        if queue:
            raise queue.pop(0)

    inst._start_polling = fake_polling
    inst._record_health_error = inst.health.append
    return inst


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    import time
    monkeypatch.setattr(time, "sleep", lambda s: None)


def test_token_rejection_is_recognised_without_depending_on_unauthorized():
    assert guard.is_token_rejection(InvalidToken("rejected"))
    assert not guard.is_token_rejection(NetworkError("timeout"))
    assert not guard.is_token_rejection(Conflict("other poller"))


def test_backoff_grows_and_is_capped():
    assert [guard.backoff_seconds(n) for n in (1, 2, 3, 4, 5, 9)] == [10, 20, 40, 60, 60, 60]


def test_rejected_token_stops_after_the_limit_and_goes_offline(app):
    inst = _instance(app, [InvalidToken("rejected")] * 20)
    inst._run_bot()
    assert inst.calls == guard.TOKEN_REJECT_LIMIT  # not 10, not forever
    with app.app_context():
        assert db.session.get(Bot, app.bot_id).is_active is False
        assert db.session.get(CustomBot, app.twin_id).status == "error"
    assert any("taken offline" in h for h in inst.health)


def test_a_transient_rejection_does_not_take_the_bot_offline(app):
    inst = _instance(app, [InvalidToken("blip"), InvalidToken("blip")])
    inst._run_bot()
    assert inst.calls == 3  # two rejections, then a clean run
    with app.app_context():
        assert db.session.get(Bot, app.bot_id).is_active is True


def test_only_consecutive_rejections_count(app):
    errs = [InvalidToken("x")] * 4 + [NetworkError("blip")] + [InvalidToken("x")] * 4
    inst = _instance(app, errs)
    inst._run_bot()
    with app.app_context():
        assert db.session.get(Bot, app.bot_id).is_active is True


def test_kill_switch_keeps_the_bot_flagged_active(app, monkeypatch):
    monkeypatch.setenv("BOT_TOKEN_AUTO_OFFLINE", "0")
    inst = _instance(app, [InvalidToken("rejected")] * 20)
    inst._run_bot()
    assert inst.calls == guard.TOKEN_REJECT_LIMIT
    with app.app_context():
        assert db.session.get(Bot, app.bot_id).is_active is True


def test_conflict_handling_is_reachable_again(app):
    inst = _instance(app, [Conflict("another instance")])
    inst._run_bot()
    assert inst.calls == 2
    assert not inst.health  # a conflict is retried quietly, not recorded as a crash
