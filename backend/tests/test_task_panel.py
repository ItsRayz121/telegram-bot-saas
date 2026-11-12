"""Button-driven task flow: short picker labels (no XP), link + Verify panel, live X check,
retry cooldown, hand-off to the admins after a few misses, Telegram join check.

Run from the repo root:  python -m pytest backend/tests/test_task_panel.py
"""
import asyncio
import os
from types import SimpleNamespace

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-with-enough-length-1234")
os.environ.setdefault("ENCRYPTION_KEY", "Zm9vYmFyYmF6cXV4Zm9vYmFyYmF6cXV4Zm9vYmFyYmE=")
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from flask import Flask

from backend.models import db, User, TelegramGroup, EngagementCampaign, EngagementTask, EngagementSubmission
import backend.assistant.hub_models  # noqa: F401
from backend import engagement as eng
from backend import engagement_bot as eb


@pytest.fixture()
def app():
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI="sqlite://", TESTING=True, SECRET_KEY="x",
                      SQLALCHEMY_ENGINE_OPTIONS={"connect_args": {"check_same_thread": False}})
    db.init_app(app)
    with app.app_context():
        db.create_all()
        eb._task_verify_state.clear()
        yield app
        db.session.remove()


def _campaign(tasks):
    owner = User(email=f"o{len(tasks)}@x.io", full_name="O", auth_provider="email")
    db.session.add(owner)
    db.session.flush()
    db.session.add(TelegramGroup(telegram_group_id="-100P", title="G", owner_user_id=owner.id, bot_status="active"))
    c = EngagementCampaign(telegram_group_id="-100P", owner_user_id=owner.id, type="social_task",
                           title="One time tasks", status="active", settings={})
    db.session.add(c)
    db.session.flush()
    out = []
    for i, kw in enumerate(tasks):
        t = EngagementTask(campaign_id=c.id, order=i, **kw)
        db.session.add(t)
        db.session.flush()
        out.append(t)
    db.session.commit()
    return c, out


X_TASK = dict(title="Follow the official Elyon Chain X account:", type="social_task", platform="x",
              task_url="https://x.com/ElyonChain", verification_mode="manual", reward_xp=5,
              settings={"auto_verify_x": True, "raid_goals": {"follows": 1}})
JOIN_TASK = dict(title="Join the official Elyon Chain Telegram channel:", type="social_task",
                 platform="telegram", task_url="https://t.me/elyon", verification_mode="auto", reward_xp=5,
                 settings={})


class FakeMsg:
    def __init__(self):
        self.sent, self.edited = [], []

    async def reply_text(self, text, **kw):
        self.sent.append((text, kw))

    async def edit_text(self, text, **kw):
        self.edited.append((text, kw))


class FakeQuery:
    def __init__(self, data, uid=500):
        self.data, self.message, self.from_user = data, FakeMsg(), SimpleNamespace(id=uid, username="u500")
        self.answers = []

    async def answer(self, text=None, show_alert=False):
        self.answers.append((text, show_alert))


def _buttons(kb):
    return [(b.text, getattr(b, "url", None), getattr(b, "callback_data", None))
            for row in kb.inline_keyboard for b in row]


def test_picker_uses_short_labels_without_xp(app):
    c, tasks = _campaign([X_TASK, JOIN_TASK])
    labels = [b.text for row in eb._task_picker(c, set()).inline_keyboard for b in row]
    assert labels == ["🐦 Follow on X", "✈️ Join Telegram channel"]
    assert all("XP" not in l and "(" not in l for l in labels)
    done = [b.text for row in eb._task_picker(c, {tasks[0].id}).inline_keyboard for b in row]
    assert done[0].startswith("✅ ")


def test_panel_has_a_link_button_then_verify(app, monkeypatch):
    c, (xt, jt) = _campaign([X_TASK, JOIN_TASK])
    text, kb = eb._task_panel(c, xt, "x", "alice")
    b = _buttons(kb)
    assert b[0] == ("🐦 Open on X", "https://x.com/ElyonChain", None)
    assert b[1][2] == f"engtv_{c.id}_{xt.id}" and "@alice" in text
    assert any(x[2] == f"engh_{c.id}_{xt.id}" for x in b)                 # change username
    _, kb2 = eb._task_panel(c, jt, "join", chat_url="https://t.me/elyon")
    assert _buttons(kb2)[0][1] == "https://t.me/elyon" and _buttons(kb2)[1][2].startswith("engtv_")


def _run_verify(app, query, monkeypatch, overall, ctx_bot=None):
    from backend import twitter_verify
    monkeypatch.setattr(twitter_verify, "enabled", lambda owner=None: True)
    monkeypatch.setattr(twitter_verify, "verify_raid",
                        lambda shim, handle, **kw: {"overall": overall, "results": {"follows": {"status": "verified" if overall == "verified" else "failed"}}})
    ctx = SimpleNamespace(bot=ctx_bot, user_data={})
    asyncio.run(eb._handle_task_verify(query, ctx, query.data, flask_app=app, lineage="official", bot_id=None))
    return ctx


def test_x_verify_success_pays_xp_once(app, monkeypatch):
    c, (xt, _jt) = _campaign([X_TASK, JOIN_TASK])
    eng.set_social_handle(500, "@alice", "x")
    q = FakeQuery(f"engtv_{c.id}_{xt.id}")
    _run_verify(app, q, monkeypatch, "verified")
    assert any("Verified" in t and "+5 XP" in t for t, _ in q.message.sent)
    sub = EngagementSubmission.query.filter_by(campaign_id=c.id, task_id=xt.id, telegram_user_id="500").one()
    assert sub.status == "verified"
    q2 = FakeQuery(f"engtv_{c.id}_{xt.id}")
    _run_verify(app, q2, monkeypatch, "verified")
    assert q2.answers[-1] == ("Already verified ✅", True)                  # no second submission / XP
    assert EngagementSubmission.query.filter_by(task_id=xt.id).count() == 1


def test_x_verify_retry_cooldown_then_handed_to_admins(app, monkeypatch):
    c, (xt, _jt) = _campaign([X_TASK, JOIN_TASK])
    eng.set_social_handle(501, "@bob", "x")
    q1 = FakeQuery(f"engtv_{c.id}_{xt.id}", uid=501)
    _run_verify(app, q1, monkeypatch, "pending")
    assert "Not detected yet (1/3)" in q1.message.edited[0][0]
    assert EngagementSubmission.query.filter_by(task_id=xt.id).count() == 0   # nothing created yet
    q2 = FakeQuery(f"engtv_{c.id}_{xt.id}", uid=501)                           # too soon
    _run_verify(app, q2, monkeypatch, "pending")
    assert "Please wait" in q2.answers[-1][0]
    for _ in range(2):                                                         # two more real tries
        eb._task_verify_state[(501, xt.id)] = (eb._task_verify_state[(501, xt.id)][0], 0.0001)
        qn = FakeQuery(f"engtv_{c.id}_{xt.id}", uid=501)
        _run_verify(app, qn, monkeypatch, "pending")
    sub = EngagementSubmission.query.filter_by(task_id=xt.id, telegram_user_id="501").one()
    assert sub.status == "pending"                                             # left for review, never rejected
    assert any("sent to the admins" in t for t, _ in qn.message.sent)


def test_x_verify_asks_for_the_handle_once_when_none_is_saved(app, monkeypatch):
    c, (xt, _jt) = _campaign([X_TASK, JOIN_TASK])
    q = FakeQuery(f"engtv_{c.id}_{xt.id}", uid=502)
    ctx = _run_verify(app, q, monkeypatch, "verified")
    assert "@username" in q.message.sent[0][0]
    assert ctx.user_data["eng_handle"]["tid"] == xt.id                         # comes back to this task


def test_join_verify_uses_the_bot_membership_check(app, monkeypatch):
    c, (_xt, jt) = _campaign([X_TASK, JOIN_TASK])
    from backend import engagement_verify
    result = {"ok": False}

    async def fake_join(bot, chat, uid):
        return "member" if result["ok"] else "not_member"
    monkeypatch.setattr(engagement_verify, "check_telegram_join", fake_join)
    q = FakeQuery(f"engtv_{c.id}_{jt.id}", uid=503)
    ctx = SimpleNamespace(bot=None, user_data={})
    asyncio.run(eb._handle_task_verify(q, ctx, q.data, flask_app=app, lineage="official", bot_id=None))
    assert "don't appear to be a member" in q.answers[-1][0]
    assert EngagementSubmission.query.filter_by(task_id=jt.id).count() == 0
    result["ok"] = True
    q = FakeQuery(f"engtv_{c.id}_{jt.id}", uid=503)
    asyncio.run(eb._handle_task_verify(q, ctx, q.data, flask_app=app, lineage="official", bot_id=None))
    assert EngagementSubmission.query.filter_by(task_id=jt.id, status="verified").count() == 1


def test_panel_kind_only_for_username_only_tasks(app, monkeypatch):
    from backend import twitter_verify
    monkeypatch.setattr(twitter_verify, "enabled", lambda owner=None: True)
    c, (xt, jt) = _campaign([X_TASK, JOIN_TASK])
    assert eng.task_panel_kind(c, xt) == "x" and eng.task_panel_kind(c, jt) == "join"
    from backend.models import EngagementCustomField
    db.session.add(EngagementCustomField(task_id=jt.id, key="w", label="Wallet", field_type="wallet",
                                         required=True, order=0))
    db.session.commit()
    assert eng.task_panel_kind(c, jt) is None                                  # needs typed proof -> old flow
    monkeypatch.setattr(twitter_verify, "enabled", lambda owner=None: False)
    assert eng.task_panel_kind(c, xt) is None                                  # no API key -> old flow


# ── which chat is checked, and what happens when the bot cannot look ─────────────

def test_chat_is_taken_from_a_public_t_me_link():
    from backend.engagement_verify import telegram_chat_from_url as chat
    assert chat("https://t.me/ElyonChannel") == "@ElyonChannel"
    assert chat("t.me/Elyon_Chat/123") == "@Elyon_Chat"
    assert chat("https://telegram.me/Elyon_Chat?x=1") == "@Elyon_Chat"
    for bad in ("https://t.me/+AbCdEf123", "https://t.me/joinchat/xyz", "https://x.com/Elyon", "", None):
        assert chat(bad) is None


def test_verify_chat_precedence(app):
    c, (xt, jt) = _campaign([X_TASK, dict(JOIN_TASK, task_url="https://t.me/ElyonChannel")])
    assert eb._verify_chat_ref(c, "official", jt) == "@ElyonChannel"          # the linked channel
    jt.settings = {"verify_chat": "@Explicit"}
    assert eb._verify_chat_ref(c, "official", jt) == "@Explicit"              # explicit setting wins
    plain = SimpleNamespace(task_url="https://example.com", settings={})
    assert eb._verify_chat_ref(c, "official", plain) == "-100P"                # else the campaign's own group


class _Bot:
    def __init__(self, status=None, error=None):
        self.status, self.error = status, error

    async def get_chat_member(self, chat_id, user_id):
        if self.error:
            raise Exception(self.error)
        return SimpleNamespace(status=self.status, is_member=True)


def test_membership_check_is_tri_state():
    from backend.engagement_verify import check_telegram_join as check
    run = lambda bot, ref="@c": asyncio.run(check(bot, ref, 1))
    assert run(_Bot("member")) == "member" and run(_Bot("administrator")) == "member"
    assert run(_Bot("left")) == "not_member" and run(_Bot("kicked")) == "not_member"
    assert run(_Bot(error="Bad Request: user not found")) == "not_member"
    for err in ("Bad Request: chat not found", "Forbidden: bot is not a member of the channel chat",
                "Bad Request: member list is inaccessible", "timed out"):
        assert run(_Bot(error=err)) == "cannot_check"                          # never "not a member"
    assert run(_Bot("member"), ref=None) == "cannot_check"


def test_join_task_goes_to_review_when_the_bot_cannot_see_the_chat(app, monkeypatch):
    c, (_xt, jt) = _campaign([X_TASK, JOIN_TASK])
    q = FakeQuery(f"engtv_{c.id}_{jt.id}", uid=520)
    ctx = SimpleNamespace(bot=_Bot(error="Bad Request: chat not found"), user_data={})
    asyncio.run(eb._handle_task_verify(q, ctx, q.data, flask_app=app, lineage="official", bot_id=None))
    assert any("sent to the admins" in t for t, _ in q.message.sent)
    sub = EngagementSubmission.query.filter_by(task_id=jt.id, telegram_user_id="520").one()
    assert sub.status == "pending"                                             # not blocked, not auto-verified
    q2 = FakeQuery(f"engtv_{c.id}_{jt.id}", uid=521)
    ctx2 = SimpleNamespace(bot=_Bot("left"), user_data={})
    asyncio.run(eb._handle_task_verify(q2, ctx2, q2.data, flask_app=app, lineage="official", bot_id=None))
    assert "don't appear to be a member" in q2.answers[-1][0]                  # really not joined
