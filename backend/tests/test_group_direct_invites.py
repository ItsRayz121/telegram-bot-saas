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

from backend.config import Config
from backend.models import (
    db, User, UserTelegramAccount, TelegramGroup, TelegramGroupAccess, TelegramGroupInvite,
    TelegramBotStarted, CustomBotStarted, CustomBot, Bot, Group,
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
    monkeypatch.setattr(Config, "TELEGRAM_BOT_TOKEN", "111:official", raising=False)
    monkeypatch.setattr(Config, "TELEGRAM_BOT_USERNAME", "telegizer_bot", raising=False)
    sent, state = [], {"admin": True}

    def fake_call(token, method, **p):
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
            sent.append({**p, "_token": token})
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
        cb = CustomBot(owner_user_id=owner.id, bot_username="MyCustom_bot", status="active", bot_token_encrypted="x")
        cb.set_token("222:custom")
        db.session.add(cb)
        db.session.flush()
        db.session.add(TelegramGroup(telegram_group_id="-100C", title="Custom", owner_user_id=owner.id,
                                     bot_status="active", linked_via_bot_type="custom", linked_bot_id=cb.id))
        legacy = Bot(user_id=owner.id, bot_username="Legacy_bot", bot_token="x")
        legacy.set_token("333:legacy")
        db.session.add(legacy)
        db.session.flush()
        db.session.add(Group(bot_id=legacy.id, telegram_group_id="-100L", group_name="Legacy group"))
        TelegramBotStarted.record("222")  # Ali started the OFFICIAL bot, Sana did not
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
    assert env.sent and env.sent[0]["chat_id"] == 222 and env.sent[0]["_token"] == "111:official"
    cb = [b["callback_data"] for b in env.sent[0]["reply_markup"]["inline_keyboard"][0]]
    assert cb == [f"gti:a:{r.get_json()['invite']['id']}", f"gti:r:{r.get_json()['invite']['id']}"]
    team = env.client.get("/api/telegram-groups/-100A/team", headers=env.h).get_json()
    assert team["invites"] == [] and len(team["direct_invites"]) == 1  # not listed as an access code


def test_invite_refused_when_not_admin_not_started_or_duplicate(env):
    assert _invite(env, tg="555").status_code == 400          # not an admin
    assert _invite(env, tg="333").status_code == 409          # has not started the bot
    assert not env.sent                                       # ...and was never messaged
    assert _invite(env).status_code == 201
    assert _invite(env).status_code == 409                    # already pending


def test_custom_bot_group_uses_its_own_bot_token_and_its_own_started_list(env):
    # Ali started the OFFICIAL bot only: a custom-bot group must not message him.
    assert _invite(env, gid="-100C").status_code == 409 and not env.sent
    with env.app.app_context():
        CustomBotStarted.record("mycustom_bot", "222")
        db.session.commit()
    r = _invite(env, gid="-100C")
    assert r.status_code == 201 and env.sent[0]["_token"] == "222:custom"
    admins = env.client.get("/api/telegram-groups/-100C/team/admins", headers=env.h).get_json()
    assert admins["bot_username"] == "mycustom_bot" and admins["bot_official"] is False


def test_legacy_bot_group_works_too(env):
    with env.app.app_context():
        CustomBotStarted.record("legacy_bot", "222")
        db.session.commit()
    r = env.client.post("/api/telegram-groups/-100L/team/invites/direct",
                        json={"telegram_user_id": "222", "role": "viewer"}, headers=env.h)
    assert r.status_code == 201 and env.sent[0]["_token"] == "333:legacy"


def test_accept_through_a_custom_bot_grants_access(env):
    with env.app.app_context():
        CustomBotStarted.record("mycustom_bot", "222")
        db.session.commit()
    inv_id = _invite(env, gid="-100C", role="viewer").get_json()["invite"]["id"]
    status, _ = _press(env, inv_id, 222, True)
    assert status == "ok"
    with env.app.app_context():
        assert TelegramGroupAccess.query.filter_by(telegram_group_id="-100C", role="viewer").count() == 1


def test_owner_with_a_linked_second_telegram_account_cannot_invite_themselves(env):
    with env.app.app_context():
        db.session.add(UserTelegramAccount(user_id=env.oid, telegram_user_id="222"))
        db.session.commit()
    assert _invite(env).status_code == 400
    ids = [a["user_id"] for a in env.client.get("/api/telegram-groups/-100A/team/admins", headers=env.h).get_json()["admins"]]
    assert "222" not in ids


def test_a_banned_account_cannot_accept(env):
    inv_id = _invite(env).get_json()["invite"]["id"]
    with env.app.app_context():
        db.session.add(User(email="b@x.io", telegram_user_id="222", is_banned=True, auth_provider="telegram"))
        db.session.commit()
    assert _press(env, inv_id, 222, True)[0] == "gone"
    with env.app.app_context():
        assert TelegramGroupAccess.query.count() == 0


def test_accept_creates_the_grant_and_a_telegram_account(env):
    inv_id = _invite(env).get_json()["invite"]["id"]
    status, info = _press(env, inv_id, 222, True)
    assert status == "ok" and info["owner_tg_ids"] == {"1"}
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


def test_button_handler_answers_edits_message_and_only_notifies_a_started_owner(env):
    import asyncio
    with env.app.app_context():
        CustomBotStarted.record("mycustom_bot", "222")
        db.session.commit()
    inv_id = _invite(env, gid="-100C").get_json()["invite"]["id"]

    class Q:
        def __init__(self, data):
            self.data, self.answers, self.edits = data, [], []
        async def answer(self, *a, **k): self.answers.append((a, k))
        async def edit_message_text(self, text, **k): self.edits.append((text, k))

    class Bot_:
        def __init__(self): self.dms = []
        async def send_message(self, chat_id, text, **k): self.dms.append(chat_id)

    def press(data, uid=222):
        q, bot_ = Q(data), Bot_()
        upd = NS(callback_query=q, effective_user=NS(id=uid, username="ali", first_name="Ali", last_name=None))
        asyncio.run(flow.handle_invite_press(upd, NS(bot=bot_), env.app, bot_key="mycustom_bot", official=False))
        return q, bot_

    q, _ = press(f"gti:a:{inv_id}", uid=333)                      # someone else pressing it
    assert q.answers[0][1].get("show_alert") and not q.edits
    q, bot_ = press(f"gti:a:{inv_id}")
    assert "access to" in q.edits[0][0] and bot_.dms == []        # owner never started this bot -> not messaged
    with env.app.app_context():
        CustomBotStarted.record("mycustom_bot", "1")   # now the owner has started it
        CustomBotStarted.record("mycustom_bot", "333")
        db.session.commit()
    inv2 = _invite(env, gid="-100C", tg="333").get_json()["invite"]["id"]
    q, bot_ = press(f"gti:r:{inv2}", uid=333)
    assert "declined" in q.edits[0][0] and bot_.dms == [1]


# ── Team Access dashboard: invitation history, member mapping, resend ─────────

def _team(env, gid="-100A"):
    return env.client.get(f"/api/telegram-groups/{gid}/team", headers=env.h).get_json()


def test_history_reports_every_lifecycle_state_from_the_rows(env):
    with env.app.app_context():
        for tg in ("333", "444"):
            TelegramBotStarted.record(tg)
        db.session.commit()
    pending = _invite(env, tg="222").get_json()["invite"]["id"]
    declined = _invite(env, tg="333").get_json()["invite"]["id"]
    assert _press(env, declined, 333, False)[0] == "declined"
    with env.app.app_context():
        old = TelegramGroupInvite(telegram_group_id="-100A", role="viewer", created_by=env.oid,
                                  invitee_telegram_id="444", invitee_name="Old",
                                  expires_at=datetime.utcnow() - timedelta(days=1))
        db.session.add(old)
        db.session.commit()
    by = {i["invitee_telegram_id"]: i for i in _team(env)["invitations"]}
    assert by["222"]["status"] == "pending" and by["222"]["id"] == pending
    assert by["333"]["status"] == "declined" and by["333"]["declined_at"]
    assert by["444"]["status"] == "expired"
    assert all(i["code"] is None for i in by.values())
    # only genuinely open invites count as pending in the existing list
    assert [i["invitee_telegram_id"] for i in _team(env)["direct_invites"]] == ["222"]
    inv_id = by["222"]["id"]
    assert _press(env, inv_id, 222, True)[0] == "ok"
    acc = {i["invitee_telegram_id"]: i for i in _team(env)["invitations"]}["222"]
    assert acc["status"] == "accepted" and acc["used_at"] and acc["used_by"]


def test_admin_rows_carry_the_real_member_link_after_accept(env):
    inv_id = _invite(env).get_json()["invite"]["id"]
    before = {a["user_id"]: a for a in env.client.get("/api/telegram-groups/-100A/team/admins", headers=env.h).get_json()["admins"]}
    assert before["222"]["pending"] and before["222"]["member_user_id"] is None
    _press(env, inv_id, 222, True)
    after = {a["user_id"]: a for a in env.client.get("/api/telegram-groups/-100A/team/admins", headers=env.h).get_json()["admins"]}
    assert after["222"]["has_access"] and after["222"]["member_role"] == "manager" and after["222"]["member_user_id"]
    # revoke -> the access row is gone but the accepted invitation stays as history
    uid = after["222"]["member_user_id"]
    assert env.client.delete(f"/api/telegram-groups/-100A/team/members/{uid}", headers=env.h).status_code == 200
    again = {a["user_id"]: a for a in env.client.get("/api/telegram-groups/-100A/team/admins", headers=env.h).get_json()["admins"]}
    assert again["222"]["has_access"] is False
    assert _team(env)["invitations"][0]["status"] == "accepted"


def test_resend_sends_again_without_creating_anything(env):
    inv_id = _invite(env).get_json()["invite"]["id"]
    assert len(env.sent) == 1
    r = env.client.post(f"/api/telegram-groups/-100A/team/invites/{inv_id}/resend", headers=env.h)
    assert r.status_code == 200 and len(env.sent) == 2 and env.sent[1]["chat_id"] == 222
    cb = [b["callback_data"] for b in env.sent[1]["reply_markup"]["inline_keyboard"][0]]
    assert cb == [f"gti:a:{inv_id}", f"gti:r:{inv_id}"]
    with env.app.app_context():
        assert TelegramGroupInvite.query.count() == 1
    # immediate second click is throttled, nothing extra is sent
    r = env.client.post(f"/api/telegram-groups/-100A/team/invites/{inv_id}/resend", headers=env.h)
    assert r.status_code == 429 and len(env.sent) == 2


def test_resend_refuses_finished_unknown_foreign_and_disabled_invites(env, monkeypatch):
    declined = _invite(env).get_json()["invite"]["id"]
    _press(env, declined, 222, False)
    n = len(env.sent)
    url = lambda i, g="-100A": f"/api/telegram-groups/{g}/team/invites/{i}/resend"
    assert env.client.post(url(declined), headers=env.h).status_code == 409
    assert env.client.post(url(99999), headers=env.h).status_code == 404
    live = _invite(env).get_json()["invite"]["id"]
    n = len(env.sent)
    assert env.client.post(url(live, "-100C"), headers=env.h).status_code == 404  # other group
    monkeypatch.setenv("GROUP_TEAM_DIRECT_INVITES_ENABLED", "0")
    assert env.client.post(url(live), headers=env.h).status_code == 503
    assert len(env.sent) == n


def test_resend_is_owner_only_and_fails_cleanly_if_telegram_errors(env, monkeypatch):
    inv_id = _invite(env).get_json()["invite"]["id"]
    with env.app.app_context():
        u = User(email="m@x.io", full_name="M", auth_provider="email")
        db.session.add(u)
        db.session.commit()
        db.session.add(TelegramGroupAccess(telegram_group_id="-100A", user_id=u.id, role="manager", invited_by=env.oid))
        db.session.commit()
        tok = create_access_token(identity=str(u.id))
    r = env.client.post(f"/api/telegram-groups/-100A/team/invites/{inv_id}/resend",
                        headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 404                                   # managers cannot manage the team
    monkeypatch.setattr(flow, "_call", lambda *a, **k: {"ok": False, "description": "Forbidden: bot was blocked"})
    r = env.client.post(f"/api/telegram-groups/-100A/team/invites/{inv_id}/resend", headers=env.h)
    assert r.status_code == 502 and "blocked" in r.get_json()["error"]
    assert _team(env)["invitations"][0]["status"] == "pending"    # a failed send changes nothing


def test_resend_refuses_someone_who_has_not_started_the_bot_anymore(env):
    inv_id = _invite(env).get_json()["invite"]["id"]
    with env.app.app_context():
        TelegramBotStarted.query.filter_by(telegram_user_id="222").delete()
        db.session.commit()
    n = len(env.sent)
    r = env.client.post(f"/api/telegram-groups/-100A/team/invites/{inv_id}/resend", headers=env.h)
    assert r.status_code == 502 and len(env.sent) == n


def test_cancel_removes_a_pending_invite_but_never_an_accepted_one(env):
    inv_id = _invite(env).get_json()["invite"]["id"]
    assert env.client.delete(f"/api/telegram-groups/-100A/team/invites/{inv_id}", headers=env.h).status_code == 200
    assert _team(env)["invitations"] == []
    inv2 = _invite(env).get_json()["invite"]["id"]
    _press(env, inv2, 222, True)
    assert env.client.delete(f"/api/telegram-groups/-100A/team/invites/{inv2}", headers=env.h).status_code == 409
    assert _team(env)["invitations"][0]["status"] == "accepted"


def test_reinvite_after_decline_or_expiry_is_allowed(env):
    first = _invite(env).get_json()["invite"]["id"]
    _press(env, first, 222, False)
    assert _invite(env).status_code == 201
    hist = _team(env)["invitations"]
    assert [i["status"] for i in hist] == ["pending", "declined"]


# ── Double invites: the database allows only one pending invitation per person per group ──

def test_database_refuses_a_second_pending_invitation_for_the_same_person(env):
    from sqlalchemy.exc import IntegrityError
    _invite(env)
    with env.app.app_context():
        db.session.add(TelegramGroupInvite(telegram_group_id="-100A", role="viewer", created_by=env.oid,
                                           invitee_telegram_id="222", invitee_name="Ali"))
        with pytest.raises(IntegrityError):
            db.session.flush()
        db.session.rollback()
        # a different person, a different group, a declined or an accepted row are all still allowed
        db.session.add_all([
            TelegramGroupInvite(telegram_group_id="-100A", created_by=env.oid, invitee_telegram_id="333"),
            TelegramGroupInvite(telegram_group_id="-100C", created_by=env.oid, invitee_telegram_id="222"),
            TelegramGroupInvite(telegram_group_id="-100A", created_by=env.oid, invitee_telegram_id="222",
                                declined_at=datetime.utcnow()),
            TelegramGroupInvite(telegram_group_id="-100A", created_by=env.oid, invitee_telegram_id="222",
                                used_at=datetime.utcnow()),
        ])
        db.session.commit()


def test_a_race_that_slips_past_the_check_is_refused_cleanly_and_sends_nothing(env, monkeypatch):
    from backend.routes import group_team as gt
    assert _invite(env).status_code == 201
    n = len(env.sent)
    # simulate the second request having read "no pending invite" just before the first one committed
    class _Empty:
        def filter_by(self, **k): return self
        def first(self): return None
        def count(self): return 0
    monkeypatch.setattr(gt, "_open_invites", lambda *a, **k: _Empty())
    r = _invite(env)
    assert r.status_code == 409 and "already pending" in r.get_json()["error"]
    assert len(env.sent) == n                                   # nobody was messaged twice
    with env.app.app_context():
        assert TelegramGroupInvite.query.filter_by(invitee_telegram_id="222").count() == 1


def test_inviting_again_after_expiry_replaces_the_dead_invitation(env):
    first = _invite(env).get_json()["invite"]["id"]
    with env.app.app_context():
        TelegramGroupInvite.query.get(first).expires_at = datetime.utcnow() - timedelta(minutes=1)
        db.session.commit()
    r = _invite(env)
    assert r.status_code == 201
    with env.app.app_context():
        rows = TelegramGroupInvite.query.filter_by(invitee_telegram_id="222").all()
        assert len(rows) == 1 and rows[0].expires_at > datetime.utcnow() and rows[0].status() == "pending"


def test_failed_send_leaves_no_row_so_a_retry_works(env):
    env.sent.clear()
    orig = flow._call
    flow._call = lambda *a, **k: {"ok": False, "description": "Forbidden"} if a[1] == "sendMessage" else orig(*a, **k)
    try:
        assert _invite(env).status_code == 502
    finally:
        flow._call = orig
    assert _team(env)["invitations"] == []
    assert _invite(env).status_code == 201


def test_one_lock_per_group(env):
    from backend.routes import group_team as gt
    assert gt._group_lock("-100A") is gt._group_lock("-100A")
    assert gt._group_lock("-100A") is not gt._group_lock("-100C")


def test_two_simultaneous_invites_create_exactly_one_and_send_one_message(env, tmp_path):
    """Real threads against a file database (each thread its own connection)."""
    import threading
    app = Flask("race")
    app.config.update(SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path / 'race.db'}",
                      JWT_SECRET_KEY=os.environ["JWT_SECRET_KEY"], JWT_TOKEN_LOCATION=["headers"],
                      TESTING=True, SECRET_KEY="x")
    db.init_app(app)
    JWTManager(app)
    app.register_blueprint(group_team_bp, name="race_team")
    with app.app_context():
        db.create_all()
        owner = User(email="r@x.io", full_name="Owner", auth_provider="email", telegram_user_id="1")
        db.session.add(owner)
        db.session.flush()
        db.session.add(TelegramGroup(telegram_group_id="-100A", title="Group A", owner_user_id=owner.id,
                                     bot_status="active", linked_via_bot_type="official"))
        TelegramBotStarted.record("222")
        db.session.commit()
        h = {"Authorization": f"Bearer {create_access_token(identity=str(owner.id))}"}
    env.sent.clear()
    results, gate = [], threading.Barrier(2)

    def go():
        try:
            gate.wait()
            r = app.test_client().post("/api/telegram-groups/-100A/team/invites/direct",
                                       json={"telegram_user_id": "222", "role": "manager"}, headers=h)
            results.append(r.status_code)
        except Exception as exc:  # surface it instead of a silent short list
            results.append(repr(exc))

    threads = [threading.Thread(target=go) for _ in range(2)]
    [t.start() for t in threads]
    [t.join(timeout=30) for t in threads]
    assert sorted(results) == [201, 409]
    assert len([m for m in env.sent if m["chat_id"] == 222]) == 1
    with app.app_context():
        assert TelegramGroupInvite.query.filter_by(invitee_telegram_id="222").count() == 1
