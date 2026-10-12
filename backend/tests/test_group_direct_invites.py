"""Direct team invites (bot DM Accept / Reject instead of an access code).

Run from the repo root:  python -m pytest backend/tests/test_group_direct_invites.py
In-memory SQLite; Telegram is faked by patching group_invite_flow._call.
"""
import os
from datetime import datetime, timedelta
from types import SimpleNamespace as NS

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-with-enough-length-1234")
os.environ.setdefault("ENCRYPTION_KEY", "Zm9vYmFyYmF6cXV4Zm9vYmFyYmF6cXV4Zm9vYmFyYmE=")
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from backend.models import (
    db, User, TelegramGroup, TelegramGroupAccess, TelegramGroupInvite, TelegramBotStarted,
)
from backend.routes.group_team import group_team_bp
from backend import group_invite_flow as flow
import backend.assistant.hub_models  # noqa: F401


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.delenv("GROUP_TEAM_ACCESS_ENABLED", raising=False)
    monkeypatch.delenv("GROUP_TEAM_DIRECT_INVITES_ENABLED", raising=False)
    from backend.middleware import rate_limit as _rl
    _rl._fallback_counts.clear()  # the in-process limiter is shared across tests
    sent, state = [], {"admin": True}

    def fake_call(method, **p):
        if method == "getChatAdministrators":
            return {"ok": True, "result": [
                {"status": "creator", "user": {"id": 1, "first_name": "Owner"}},
                {"status": "administrator", "user": {"id": 222, "first_name": "Ali", "username": "ali"}},
                {"status": "administrator", "user": {"id": 333, "first_name": "Sana"}},
                {"status": "administrator", "user": {"id": 999, "first_name": "Bot", "is_bot": True}},
            ]}
        if method == "getChatMember":
            return {"ok": True, "result": {"status": "administrator" if state["admin"] else "member"}}
        if method == "sendMessage":
            sent.append(p)
            return {"ok": True}
        return {"ok": False}
    monkeypatch.setattr(flow, "_call", fake_call)

    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI="sqlite://", JWT_SECRET_KEY=os.environ["JWT_SECRET_KEY"],
                      JWT_TOKEN_LOCATION=["headers"], TESTING=True, SECRET_KEY="x",
                      SQLALCHEMY_ENGINE_OPTIONS={"connect_args": {"check_same_thread": False}})
    db.init_app(app)
    JWTManager(app)
    app.register_blueprint(group_team_bp)
    with app.app_context():
        db.create_all()
        owner = User(email="o@x.io", full_name="Owner", auth_provider="email", telegram_user_id="1")
        db.session.add(owner)
        db.session.flush()
        db.session.add(TelegramGroup(telegram_group_id="-100A", title="Group A", owner_user_id=owner.id,
                                     bot_status="active", linked_via_bot_type="official"))
        db.session.add(TelegramGroup(telegram_group_id="-100C", title="Custom", owner_user_id=owner.id,
                                     bot_status="active", linked_via_bot_type="custom"))
        TelegramBotStarted.record("222")  # Ali started the bot, Sana did not
        db.session.commit()
        tok = create_access_token(identity=str(owner.id))
        oid = owner.id
    return NS(app=app, client=app.test_client(), sent=sent, state=state, oid=oid,
              h={"Authorization": f"Bearer {tok}"})


def _invite(env, tg="222", role="manager", gid="-100A"):
    return env.client.post(f"/api/telegram-groups/{gid}/team/invites/direct",
                           json={"telegram_user_id": tg, "role": role}, headers=env.h)


def _press(env, inv_id, tg_id, accept):
    with env.app.app_context():
        return flow.respond(inv_id, NS(id=tg_id, username="ali", first_name="Ali"), accept)


def test_admin_list_marks_who_can_be_dmed_and_skips_bots_and_owner(env):
    r = env.client.get("/api/telegram-groups/-100A/team/admins", headers=env.h).get_json()
    by = {a["user_id"]: a for a in r["admins"]}
    assert set(by) == {"222", "333"}
    assert by["222"]["can_dm"] is True and by["333"]["can_dm"] is False


def test_invite_sends_dm_with_buttons_and_hides_the_code(env):
    r = _invite(env)
    assert r.status_code == 201 and r.get_json()["invite"]["code"] is None
    assert env.sent and env.sent[0]["chat_id"] == 222
    cb = [b["callback_data"] for b in env.sent[0]["reply_markup"]["inline_keyboard"][0]]
    assert cb == [f"gti:a:{r.get_json()['invite']['id']}", f"gti:r:{r.get_json()['invite']['id']}"]
    team = env.client.get("/api/telegram-groups/-100A/team", headers=env.h).get_json()
    assert team["invites"] == [] and len(team["direct_invites"]) == 1  # not listed as an access code


def test_invite_refused_when_not_admin_not_started_duplicate_or_custom_bot(env):
    assert _invite(env, tg="555").status_code == 400          # not an admin
    assert _invite(env, tg="333").status_code == 409          # has not started the bot
    assert _invite(env).status_code == 201
    assert _invite(env).status_code == 409                    # already pending
    assert _invite(env, gid="-100C").status_code == 400       # custom-bot group unsupported


def test_accept_creates_the_grant_and_a_telegram_account(env):
    inv_id = _invite(env).get_json()["invite"]["id"]
    status, info = _press(env, inv_id, 222, True)
    assert status == "ok" and info["owner_tg"] == "1"
    with env.app.app_context():
        u = User.query.filter_by(telegram_user_id="222").first()
        row = TelegramGroupAccess.query.filter_by(telegram_group_id="-100A", user_id=u.id).first()
        assert row and row.role == "manager" and row.invited_by == env.oid
    assert _press(env, inv_id, 222, True)[0] == "gone"        # one use only


def test_accept_requires_the_invitee_and_a_current_admin(env):
    inv_id = _invite(env).get_json()["invite"]["id"]
    assert _press(env, inv_id, 333, True)[0] == "not_you"
    env.state["admin"] = False
    assert _press(env, inv_id, 222, True)[0] == "not_admin"
    with env.app.app_context():
        assert TelegramGroupAccess.query.count() == 0


def test_reject_expired_and_kill_switch_grant_nothing(env, monkeypatch):
    inv_id = _invite(env).get_json()["invite"]["id"]
    assert _press(env, inv_id, 222, False)[0] == "declined"
    assert _press(env, inv_id, 222, True)[0] == "gone"
    inv2 = _invite(env).get_json()["invite"]["id"]
    with env.app.app_context():
        TelegramGroupInvite.query.get(inv2).expires_at = datetime.utcnow() - timedelta(minutes=1)
        db.session.commit()
    assert _press(env, inv2, 222, True)[0] == "gone"
    inv3 = _invite(env).get_json()["invite"]["id"]
    monkeypatch.setenv("GROUP_TEAM_DIRECT_INVITES_ENABLED", "0")
    assert _press(env, inv3, 222, True)[0] == "disabled"
    assert _invite(env, tg="222").status_code == 503
    with env.app.app_context():
        assert TelegramGroupAccess.query.count() == 0


def test_a_direct_invite_code_cannot_be_redeemed_by_code(env):
    inv_id = _invite(env).get_json()["invite"]["id"]
    with env.app.app_context():
        code = TelegramGroupInvite.query.get(inv_id).code
        u = User(email="x@x.io", full_name="X", auth_provider="email")
        db.session.add(u)
        db.session.commit()
        tok = create_access_token(identity=str(u.id))
    r = env.client.post("/api/group-team/redeem", json={"code": code}, headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 404
