"""Per-task X auto-verify settings and the one-handle-one-account rule.

Run from the repo root:  python -m pytest backend/tests/test_task_x_autoverify.py
"""
import os

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-with-enough-length-1234")
os.environ.setdefault("ENCRYPTION_KEY", "Zm9vYmFyYmF6cXV4Zm9vYmFyYmF6cXV4Zm9vYmFyYmE=")
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from flask import Flask

from backend.models import db, User, EngagementCampaign, EngagementTask, EngagementCustomField
import backend.assistant.hub_models  # noqa: F401
from backend import engagement as eng


@pytest.fixture()
def ctx():
    app = Flask(__name__)
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite://", TESTING=True, SECRET_KEY="x",
        SQLALCHEMY_ENGINE_OPTIONS={"connect_args": {"check_same_thread": False}},
    )
    db.init_app(app)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()


def test_clean_task_settings_keeps_only_x_capable_options():
    clean = eng._clean_task_settings
    out = clean({"auto_verify_x": True, "raid_goals": {"retweets": "5", "likes": 0, "bogus": 9}}, "raid", "x")
    assert out == {"auto_verify_x": True, "raid_goals": {"retweets": 5}}
    # not an X task -> the X options are dropped, other keys survive
    out = clean({"auto_verify_x": True, "raid_goals": {"retweets": 5}, "note": "hi"}, "proof_collection", None)
    assert out == {"note": "hi"}
    # X social task keeps them; a non-X social task does not
    assert clean({"auto_verify_x": True}, "social_task", "x")["auto_verify_x"] is True
    assert "auto_verify_x" not in clean({"auto_verify_x": True}, "social_task", "discord")
    # garbage never raises
    assert clean(None, "raid", "x") == {}
    assert clean({"raid_goals": {"retweets": "abc"}}, "raid", "x") == {}


def test_tasks_want_autoverify():
    assert eng._tasks_want_autoverify([{"settings": {"auto_verify_x": True}}])
    assert not eng._tasks_want_autoverify([{"settings": {}}, {"title": "x"}])
    assert not eng._tasks_want_autoverify(None)


def _campaign(owner_id, task_settings, ttype="raid", platform="x"):
    c = EngagementCampaign(telegram_group_id="-100A", owner_user_id=owner_id, type="social_task",
                           title="Multi", status="active", settings={})
    db.session.add(c)
    db.session.flush()
    t = EngagementTask(campaign_id=c.id, order=0, title="Raid it", type=ttype, platform=platform,
                       task_url="https://x.com/proj/status/1234567890123", verification_mode="manual",
                       settings=task_settings)
    db.session.add(t)
    db.session.flush()
    db.session.add(EngagementCustomField(task_id=t.id, key="x", label="Your X @username",
                                         field_type="username", required=False, order=0))
    db.session.commit()
    return c, t


def _submit(c, t, uid, answers, monkeypatch, result):
    from backend import twitter_verify
    monkeypatch.setattr(twitter_verify, "enabled", lambda owner=None: True)
    calls = []

    def fake(shim, handle, **kw):
        calls.append((shim, handle))
        return {"overall": result}
    monkeypatch.setattr(twitter_verify, "verify_raid", fake)
    sub, err = eng.create_submission(c, telegram_user_id=uid, answers=answers, task_id=t.id)
    return sub, err, calls


def test_task_auto_verify_upgrades_on_positive_match(ctx, monkeypatch):
    u = User(email="o@x.io", full_name="O", auth_provider="email")
    db.session.add(u); db.session.flush()
    c, t = _campaign(u.id, {"auto_verify_x": True, "raid_goals": {"retweets": 3}})
    sub, err, calls = _submit(c, t, 111, {"x": "@alice"}, monkeypatch, "verified")
    assert err is None and sub.status == "verified"
    shim, handle = calls[0]
    assert handle == "alice" and shim.settings["raid_goals"] == {"retweets": 3}
    assert shim.task_url.endswith("1234567890123")
    # the typed handle was remembered for next time
    assert eng.get_social_handle(111, "x") == "alice"


def test_task_auto_verify_never_rejects_and_respects_off_and_kill_switch(ctx, monkeypatch):
    u = User(email="o2@x.io", full_name="O", auth_provider="email")
    db.session.add(u); db.session.flush()
    c, t = _campaign(u.id, {"auto_verify_x": True, "raid_goals": {"retweets": 3}})
    sub, _, _ = _submit(c, t, 112, {"x": "@bob"}, monkeypatch, "pending")
    assert sub.status == "pending"                      # uncertain -> manual review
    monkeypatch.setenv("TASK_X_AUTOVERIFY_ENABLED", "0")
    sub, _, calls = _submit(c, t, 113, {"x": "@cara"}, monkeypatch, "verified")
    assert sub.status == "pending" and calls == []      # kill switch -> no API call
    monkeypatch.delenv("TASK_X_AUTOVERIFY_ENABLED")
    c2, t2 = _campaign(u.id, {"raid_goals": {"retweets": 3}})   # switch off
    sub, _, calls = _submit(c2, t2, 114, {"x": "@dan"}, monkeypatch, "verified")
    assert sub.status == "pending" and calls == []


def test_blank_field_uses_saved_handle(ctx, monkeypatch):
    u = User(email="o3@x.io", full_name="O", auth_provider="email")
    db.session.add(u); db.session.flush()
    c, t = _campaign(u.id, {"auto_verify_x": True, "raid_goals": {"retweets": 3}})
    eng.set_social_handle(120, "@saved_one", "x")
    sub, _, calls = _submit(c, t, 120, {}, monkeypatch, "verified")
    assert sub.status == "verified" and calls[0][1] == "saved_one"


def test_one_handle_one_account(ctx, monkeypatch):
    assert eng.set_social_handle(201, "@Farmer", "x") == "Farmer"
    assert eng.set_social_handle(202, "@farmer", "x") == eng.HANDLE_TAKEN     # case-insensitive
    assert eng.set_social_handle(201, "@Farmer2", "x") == "Farmer2"           # own change is fine
    assert eng.get_social_handle(202, "x") is None
    monkeypatch.setenv("SOCIAL_HANDLE_UNIQUE", "0")
    assert eng.set_social_handle(202, "@Farmer2", "x") == "Farmer2"           # kill switch


def test_typed_handle_owned_by_another_account_is_not_auto_verified(ctx, monkeypatch):
    u = User(email="o4@x.io", full_name="O", auth_provider="email")
    db.session.add(u); db.session.flush()
    c, t = _campaign(u.id, {"auto_verify_x": True, "raid_goals": {"retweets": 3}})
    eng.set_social_handle(300, "@owner_of_it", "x")
    sub, _, calls = _submit(c, t, 301, {"x": "@owner_of_it"}, monkeypatch, "verified")
    assert sub.status == "pending" and calls == []
