"""Regression tests for: scheduled-message editing, per-group Team Access, bot slow-mode gate,
AI reply samples (must have no side effects) and the managed-members series.

Run from the repo root:  python -m pytest backend/tests/test_group_features_batch.py
Same harness as test_analytics_insights.py: in-memory SQLite, only the blueprints under test, no
Telegram / scheduler / AI provider.
"""
import asyncio
import os
from datetime import date, datetime, timedelta
from types import SimpleNamespace as NS

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-with-enough-length-1234")
os.environ.setdefault("ENCRYPTION_KEY", "Zm9vYmFyYmF6cXV4Zm9vYmFyYmF6cXV4Zm9vYmFyYmE=")
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from backend.models import (
    db, User, TelegramGroup, OfficialScheduledMessage, TelegramGroupAccess, TelegramGroupInvite,
    AIActivity, BotEvent,
)
from backend.routes.telegram_groups import tg_groups_bp
from backend.routes.group_team import group_team_bp
import backend.assistant.hub_models  # noqa: F401  (registers hub tables referenced by FKs)


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.delenv("GROUP_TEAM_ACCESS_ENABLED", raising=False)
    app = Flask(__name__)
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite://", JWT_SECRET_KEY=os.environ["JWT_SECRET_KEY"],
        JWT_TOKEN_LOCATION=["headers"], TESTING=True, SECRET_KEY="x",
        SQLALCHEMY_ENGINE_OPTIONS={"connect_args": {"check_same_thread": False}},
    )
    db.init_app(app)
    JWTManager(app)
    for bp in (tg_groups_bp, group_team_bp):
        app.register_blueprint(bp)
    with app.app_context():
        db.create_all()
        owner = User(email="o@x.io", full_name="Owner", auth_provider="email", subscription_tier="pro")
        mgr = User(email="m@x.io", full_name="Manager", auth_provider="email")
        viewer = User(email="v@x.io", full_name="Viewer", auth_provider="email")
        stranger = User(email="s@x.io", full_name="Stranger", auth_provider="email")
        db.session.add_all([owner, mgr, viewer, stranger])
        db.session.flush()
        ga = TelegramGroup(telegram_group_id="-100A", title="Group A", owner_user_id=owner.id, bot_status="active")
        gb = TelegramGroup(telegram_group_id="-100B", title="Group B", owner_user_id=owner.id, bot_status="active")
        db.session.add_all([ga, gb])
        db.session.commit()
        ids = dict(owner=owner.id, mgr=mgr.id, viewer=viewer.id, stranger=stranger.id)
        tokens = {k: create_access_token(identity=str(v)) for k, v in ids.items()}
    client = app.test_client()
    return NS(app=app, client=client, ids=ids, h=lambda who: {"Authorization": f"Bearer {tokens[who]}"})


def _future(hours=48):
    return (datetime.utcnow() + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M")


# ── Scheduled messages: edit ──────────────────────────────────────────────────

def _create_schedule(env, **extra):
    body = {"title": "Daily", "message_text": "hello", "send_at": _future(), "timezone": "UTC", **extra}
    r = env.client.post("/api/telegram-groups/-100A/scheduled-messages", json=body, headers=env.h("owner"))
    assert r.status_code == 201, r.get_json()
    return r.get_json()


def test_create_honours_the_timezone_the_form_sends(env):
    local = (datetime.utcnow() + timedelta(days=2)).replace(microsecond=0, second=0).strftime("%Y-%m-%dT%H:%M")
    m = _create_schedule(env, send_at=local, timezone="Asia/Karachi")
    stored = datetime.fromisoformat(m["send_at"].rstrip("Z"))
    assert stored == datetime.fromisoformat(local) - timedelta(hours=5)  # Karachi is UTC+5


def test_edit_updates_the_same_row_and_never_sends(env):
    m = _create_schedule(env, buttons=[[{"text": "Docs", "url": "https://x.y"}]], media_url="https://x.y/a.png")
    r = env.client.put(f"/api/telegram-groups/-100A/scheduled-messages/{m['id']}",
                       json={"message_text": "edited", "repeat_interval": 120}, headers=env.h("owner"))
    assert r.status_code == 200
    with env.app.app_context():
        rows = OfficialScheduledMessage.query.all()
        assert len(rows) == 1  # no duplicate / second job
        row = rows[0]
        assert row.id == m["id"] and row.message_text == "edited" and row.repeat_interval == 120
        assert row.is_sent is False
        assert row.buttons == [[{"text": "Docs", "url": "https://x.y"}]] and row.media_url == "https://x.y/a.png"
        assert row.send_at.isoformat() == m["send_at"].rstrip("Z")  # a text-only edit keeps the time


def test_edit_rejects_a_past_time_and_changes_nothing(env):
    m = _create_schedule(env)
    r = env.client.put(f"/api/telegram-groups/-100A/scheduled-messages/{m['id']}",
                       json={"message_text": "x", "send_at": "2020-01-01T10:00", "timezone": "UTC"}, headers=env.h("owner"))
    assert r.status_code == 400
    with env.app.app_context():
        row = OfficialScheduledMessage.query.get(m["id"])
        assert row.message_text == "hello" and row.send_at.isoformat() == m["send_at"].rstrip("Z")


def test_edit_of_a_sent_one_off_is_refused(env):
    m = _create_schedule(env)
    with env.app.app_context():
        row = OfficialScheduledMessage.query.get(m["id"])
        row.is_sent = True
        db.session.commit()
    r = env.client.put(f"/api/telegram-groups/-100A/scheduled-messages/{m['id']}", json={"message_text": "again"}, headers=env.h("owner"))
    assert r.status_code == 409 and r.get_json()["code"] == "ALREADY_SENT"


def test_edit_moves_the_time_forward_only_when_asked(env):
    m = _create_schedule(env)
    new_time = _future(72)
    r = env.client.put(f"/api/telegram-groups/-100A/scheduled-messages/{m['id']}",
                       json={"send_at": new_time, "timezone": "UTC"}, headers=env.h("owner"))
    assert r.status_code == 200
    assert r.get_json()["send_at"].startswith(new_time)


# ── Team Access ───────────────────────────────────────────────────────────────

def _invite_and_redeem(env, who, role):
    inv = env.client.post("/api/telegram-groups/-100A/team/invites", json={"role": role}, headers=env.h("owner"))
    assert inv.status_code == 201
    code = inv.get_json()["invite"]["code"]
    red = env.client.post("/api/group-team/redeem", json={"code": code}, headers=env.h(who))
    return code, red


def test_invite_is_single_use_and_group_scoped(env):
    code, red = _invite_and_redeem(env, "mgr", "manager")
    assert red.status_code == 200 and red.get_json()["group"]["telegram_group_id"] == "-100A"
    again = env.client.post("/api/group-team/redeem", json={"code": code}, headers=env.h("stranger"))
    assert again.status_code == 404  # already used


def test_expired_code_is_rejected(env):
    inv = env.client.post("/api/telegram-groups/-100A/team/invites", json={"role": "manager"}, headers=env.h("owner")).get_json()["invite"]
    with env.app.app_context():
        row = TelegramGroupInvite.query.get(inv["id"])
        row.expires_at = datetime.utcnow() - timedelta(minutes=1)
        db.session.commit()
    r = env.client.post("/api/group-team/redeem", json={"code": inv["code"]}, headers=env.h("stranger"))
    assert r.status_code == 404


def test_manager_can_manage_one_group_but_not_another_nor_the_team(env):
    _invite_and_redeem(env, "mgr", "manager")
    ok = env.client.get("/api/telegram-groups/-100A/scheduled-messages", headers=env.h("mgr"))
    assert ok.status_code == 200
    other_group = env.client.get("/api/telegram-groups/-100B/scheduled-messages", headers=env.h("mgr"))
    assert other_group.status_code == 404  # cross-group isolation: the owner's other group stays invisible
    team = env.client.get("/api/telegram-groups/-100A/team", headers=env.h("mgr"))
    assert team.status_code == 404  # only the owner manages the team


def test_viewer_is_read_only_including_schedule_edits(env):
    m = _create_schedule(env)
    _invite_and_redeem(env, "viewer", "viewer")
    assert env.client.get("/api/telegram-groups/-100A/scheduled-messages", headers=env.h("viewer")).status_code == 200
    r = env.client.put(f"/api/telegram-groups/-100A/scheduled-messages/{m['id']}", json={"message_text": "x"}, headers=env.h("viewer"))
    assert r.status_code == 403


def test_revoking_access_takes_effect_immediately(env):
    _invite_and_redeem(env, "mgr", "manager")
    assert env.client.get("/api/telegram-groups/-100A/scheduled-messages", headers=env.h("mgr")).status_code == 200
    r = env.client.delete(f"/api/telegram-groups/-100A/team/members/{env.ids['mgr']}", headers=env.h("owner"))
    assert r.status_code == 200
    assert env.client.get("/api/telegram-groups/-100A/scheduled-messages", headers=env.h("mgr")).status_code == 404


def test_kill_switch_locks_out_shared_people_but_not_the_owner(env, monkeypatch):
    _invite_and_redeem(env, "mgr", "manager")
    monkeypatch.setenv("GROUP_TEAM_ACCESS_ENABLED", "0")
    assert env.client.get("/api/telegram-groups/-100A/scheduled-messages", headers=env.h("mgr")).status_code == 404
    assert env.client.get("/api/telegram-groups/-100A/scheduled-messages", headers=env.h("owner")).status_code == 200
    r = env.client.get("/api/telegram-groups/-100A/team", headers=env.h("owner"))
    assert r.status_code == 503 and "temporarily disabled" in r.get_json()["error"]  # the exact message the UI shows


# ── AI reply sample: no side effects ──────────────────────────────────────────

def _patch_ai(monkeypatch, answer="Sure, it's on Friday."):
    from backend.bot_features import knowledge_base as kb
    from backend.assistant import ai_key_resolver as res

    async def fake_generate(self, question, context, key_config, group_name="", kb_settings=None):
        fake_generate.calls.append((question, context, kb_settings))
        return answer
    fake_generate.calls = []
    monkeypatch.setattr(kb.KnowledgeBaseSystem, "_generate_answer", fake_generate)
    monkeypatch.setattr(res, "resolve_ai_provider_for_group",
                        lambda *a, **k: {"provider": "openai", "api_key": "k", "model": "m", "source": "user"})
    return fake_generate


def test_ai_sample_returns_text_and_writes_nothing(env, monkeypatch):
    fake = _patch_ai(monkeypatch)
    body = {"question": "When is the AMA?", "sample_context": "AMA is Friday.", "personality": "friendly_community"}
    r = env.client.post("/api/telegram-groups/-100A/ai-reply-sample", json=body, headers=env.h("owner"))
    assert r.status_code == 200 and r.get_json()["answer"] == "Sure, it's on Friday."
    assert len(fake.calls) == 1 and "AMA is Friday." in fake.calls[0][1]
    with env.app.app_context():
        assert AIActivity.query.count() == 0       # not recorded as AI activity
        assert BotEvent.query.count() == 0         # not recorded as a group event
        assert OfficialScheduledMessage.query.count() == 0


def test_ai_sample_is_not_available_to_viewers_or_strangers(env, monkeypatch):
    fake = _patch_ai(monkeypatch)
    _invite_and_redeem(env, "viewer", "viewer")
    body = {"question": "q", "sample_context": "c"}
    assert env.client.post("/api/telegram-groups/-100A/ai-reply-sample", json=body, headers=env.h("viewer")).status_code == 403
    assert env.client.post("/api/telegram-groups/-100A/ai-reply-sample", json=body, headers=env.h("stranger")).status_code == 404
    assert fake.calls == []  # no provider call was made


def test_ai_sample_rejects_bad_input_before_calling_the_provider(env, monkeypatch):
    fake = _patch_ai(monkeypatch)
    url = "/api/telegram-groups/-100A/ai-reply-sample"
    assert env.client.post(url, json={"sample_context": "c"}, headers=env.h("owner")).status_code == 400
    assert env.client.post(url, json={"question": "q", "sample_context": "c", "personality": "nope"}, headers=env.h("owner")).status_code == 400
    assert fake.calls == []


def test_ai_sample_refuses_a_second_request_while_one_is_running(env, monkeypatch):
    from backend import ai_preview
    fake = _patch_ai(monkeypatch)
    assert ai_preview.claim(f"tg:{env.ids['owner']}:-100A")
    r = env.client.post("/api/telegram-groups/-100A/ai-reply-sample", json={"question": "q", "sample_context": "c"}, headers=env.h("owner"))
    assert r.status_code == 429 and fake.calls == []
    ai_preview.release(f"tg:{env.ids['owner']}:-100A")


# ── Slow mode gate ────────────────────────────────────────────────────────────

def test_bot_slow_mode_is_off_by_default_and_does_nothing_even_if_saved_enabled():
    from backend import platform_config as pc
    from backend.bot_features.moderation import ModerationSystem
    assert pc.DEFAULT_FLAGS["bot_slow_mode_enabled"]["enabled"] is False
    mod = ModerationSystem.__new__(ModerationSystem)
    calls = []

    class Bot:
        async def delete_message(self, **kw): calls.append(("delete", kw))
        async def restrict_chat_member(self, **kw): calls.append(("restrict", kw))
        async def send_message(self, **kw): calls.append(("send", kw))

    msg = NS(from_user=NS(id=5, username="u", first_name="U"), chat=NS(id=-100), message_id=1)
    settings = {"slow_mode": {"enabled": True, "seconds_between_messages": 60, "action": "restrict", "notify": True}}
    mod._slow_tracker = {f"{-100}:5": datetime.utcnow()}  # would be "too fast" if the feature were live
    mod._slow_warn_tracker = {}
    out = asyncio.run(mod.check_slow_mode(Bot(), msg, "hi", NS(id=1), settings))
    assert out is False and calls == []  # nothing deleted, restricted or announced


# ── Managed members series (pure) ─────────────────────────────────────────────

def _rows(*pts):
    return [NS(day=date(2026, 10, d), managed_members=m, verified_members=m // 10, groups_total=g) for d, m, g in pts]


def test_series_net_change_is_signed_chronological_and_never_absolute():
    from backend.member_series import build_member_series
    rows = _rows((7, 25000, 50), (8, 25100, 50), (9, 24767, 49), (10, 24735, 49))
    pts = build_member_series(rows, "7d", date(2026, 10, 10))["points"]
    assert [p["net_managed"] for p in pts] == [None, 100, -333, -32]  # first point has no baseline -> unavailable, not 0
    assert pts[2]["groups_delta"] == -1  # a group left the total the same day: surfaced, not hidden


def test_series_does_not_invent_missing_days_and_flags_the_gap():
    from backend.member_series import build_member_series
    rows = _rows((3, 100, 5), (8, 90, 5))
    pts = build_member_series(rows, "30d", date(2026, 10, 10))["points"]
    assert [p["period_start"] for p in pts] == ["2026-10-03", "2026-10-08"]
    assert pts[1]["net_managed"] == -10 and pts[1]["gap_days"] == 5


def test_series_empty_single_flat_and_one_day_ranges():
    from backend.member_series import build_member_series
    assert build_member_series([], "30d", date(2026, 10, 10))["points"] == []
    one = build_member_series(_rows((10, 50, 1)), "1d", date(2026, 10, 10))["points"]
    assert len(one) == 1 and one[0]["net_managed"] is None
    flat = build_member_series(_rows((9, 50, 1), (10, 50, 1)), "7d", date(2026, 10, 10))["points"]
    assert flat[-1]["net_managed"] == 0


def test_series_12m_uses_end_of_month_totals_and_net_between_month_ends():
    from backend.member_series import build_member_series
    rows = [NS(day=date(2026, 8, 20), managed_members=100, verified_members=1, groups_total=1),
            NS(day=date(2026, 8, 31), managed_members=120, verified_members=1, groups_total=1),
            NS(day=date(2026, 9, 15), managed_members=110, verified_members=1, groups_total=1),
            NS(day=date(2026, 9, 30), managed_members=150, verified_members=1, groups_total=1)]
    pts = build_member_series(rows, "12m", date(2026, 10, 10))["points"]
    by = {p["period_start"]: p for p in pts}
    assert by["2026-08-01"]["managed"] == 120 and by["2026-09-01"]["managed"] == 150
    assert by["2026-09-01"]["net_managed"] == 30


# ── Official bot: the async automod handler with the retired cooldown OFF ────

class _Msg(NS):
    """A Telegram Message stand-in: any attribute the handler probes that we did not set reads as None."""
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return None


_msg_ids = iter(range(1000, 10**9))   # real Telegram messages never share an id; the bots de-duplicate retries by id


def _official_msg(text="hello", uid=5):
    return _Msg(text=text, caption=None, chat_id=-100, chat=NS(id=-100, type="supergroup"), message_id=next(_msg_ids),
              from_user=NS(id=uid, username="u", first_name="U", is_bot=False), sender_chat=None,
              entities=[], caption_entities=[], forward_origin=None, forward_date=None, forward_from=None,
              forward_from_chat=None, reply_markup=None, is_automatic_forward=False, via_bot=None,
              photo=None, video=None, document=None, sticker=None, animation=None, audio=None, voice=None)


class _RecordingBot:
    def __init__(self):
        self.calls = []

    async def get_chat_member(self, *a, **k):
        return NS(status="member")

    async def delete_message(self, **kw): self.calls.append(("delete", kw))
    async def restrict_chat_member(self, **kw): self.calls.append(("restrict", kw))
    async def send_message(self, **kw): self.calls.append(("send", kw)); return NS(message_id=99)


def test_official_async_handler_slow_mode_off_cannot_delete_restrict_or_announce(monkeypatch):
    from backend import official_bot as ob
    executed = []

    async def fake_execute(bot, message, group_id, flask_app, rule, action, **kw):
        executed.append((rule, action))
    monkeypatch.setattr(ob, "_automod_execute", fake_execute)
    bot = _RecordingBot()
    cfg = {"slow_mode": {"enabled": True, "seconds_between_messages": 60, "action": "restrict", "notify": True,
                         "exempt_min_level": 0},
           "email_detection": {"enabled": True, "action": "delete"}}
    ob._official_slow_tracker.clear(); ob._official_slow_warn_tracker.clear()
    # Two messages back to back: the second would have been removed + restricted + announced by the old cooldown.
    first = asyncio.run(ob._automod_check(bot, _official_msg("hi"), cfg, "-100", None))
    second = asyncio.run(ob._automod_check(bot, _official_msg("hi again"), cfg, "-100", None))
    assert first is False and second is False
    assert bot.calls == [] and executed == []
    assert ob._official_slow_tracker == {}  # not even bookkeeping when the feature is off
    # Unrelated legitimate moderation keeps working on the very same config.
    blocked = asyncio.run(ob._automod_check(bot, _official_msg("mail me at a@b.co"), cfg, "-100", None))
    assert blocked is True and executed == [("email_detection", "delete")]


def test_official_async_handler_still_enforces_cooldown_only_when_flag_is_on(monkeypatch):
    """Control: proves the test above is meaningful (the gate, not a broken harness, is what stops it)."""
    from backend import official_bot as ob
    from backend import platform_config as pc
    monkeypatch.setattr(pc, "is_feature_enabled", lambda key, default=True: key == "bot_slow_mode_enabled")
    bot = _RecordingBot()
    cfg = {"slow_mode": {"enabled": True, "seconds_between_messages": 60, "action": "delete", "notify": False}}
    ob._official_slow_tracker.clear()
    assert asyncio.run(ob._automod_check(bot, _official_msg("a"), cfg, "-100", None)) is False
    assert asyncio.run(ob._automod_check(bot, _official_msg("b"), cfg, "-100", None)) is True
    assert [c[0] for c in bot.calls] == ["delete"]
    ob._official_slow_tracker.clear()


# ── Scheduling: legacy timezone records, boundary and failure cases ──────────

def _insert_schedule(env, **kw):
    base = dict(telegram_group_id="-100A", title="Old", message_text="orig", send_at=datetime.utcnow() + timedelta(hours=30),
                timezone="UTC", is_sent=False, created_at=datetime.utcnow())
    base.update(kw)
    with env.app.app_context():
        row = OfficialScheduledMessage(**base)
        db.session.add(row)
        db.session.commit()
        return row.id


def test_text_only_edit_of_a_legacy_non_utc_schedule_does_not_shift_it(env):
    stored = datetime.utcnow().replace(microsecond=0) + timedelta(hours=30)
    sid = _insert_schedule(env, timezone="Asia/Karachi", send_at=stored, created_at=datetime(2026, 9, 1))
    listed = env.client.get("/api/telegram-groups/-100A/scheduled-messages", headers=env.h("owner")).get_json()
    assert listed[0]["tz_review"] is True and listed[0]["send_at"] == stored.isoformat() + "Z"
    # the dialog re-sends the timezone with every save but no send_at when the time was not touched
    r = env.client.put(f"/api/telegram-groups/-100A/scheduled-messages/{sid}",
                       json={"message_text": "new text", "timezone": "Asia/Karachi", "title": "Old"}, headers=env.h("owner"))
    assert r.status_code == 200
    with env.app.app_context():
        assert OfficialScheduledMessage.query.get(sid).send_at == stored


def test_new_schedules_are_not_flagged_and_use_the_chosen_timezone(env, monkeypatch):
    from backend.utils import schedule_edit
    monkeypatch.setattr(schedule_edit, "TZ_FIX_CUTOFF", datetime.utcnow() - timedelta(hours=1))  # "after the fix shipped"
    m = _create_schedule(env, timezone="Asia/Karachi", send_at=(datetime.utcnow() + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M"))
    listed = env.client.get("/api/telegram-groups/-100A/scheduled-messages", headers=env.h("owner")).get_json()
    assert listed[0]["tz_review"] is False


def test_utc_and_sent_legacy_records_are_not_flagged():
    from backend.utils.schedule_edit import needs_tz_review
    old = datetime(2026, 9, 1)
    assert not needs_tz_review(NS(timezone="UTC", is_sent=False, created_at=old))
    assert not needs_tz_review(NS(timezone="Asia/Karachi", is_sent=True, created_at=old))
    assert needs_tz_review(NS(timezone="Asia/Karachi", is_sent=False, created_at=old))


def test_editing_a_schedule_that_is_already_due_changes_the_text_but_never_sends_or_moves_it(env):
    due = datetime.utcnow() - timedelta(seconds=20)  # the poller has not picked it up yet
    sid = _insert_schedule(env, send_at=due)
    r = env.client.put(f"/api/telegram-groups/-100A/scheduled-messages/{sid}", json={"message_text": "late edit"}, headers=env.h("owner"))
    assert r.status_code == 200
    with env.app.app_context():
        row = OfficialScheduledMessage.query.get(sid)
        assert row.message_text == "late edit" and row.send_at == due and row.is_sent is False
    # ...but it cannot be moved to another time in the past
    r = env.client.put(f"/api/telegram-groups/-100A/scheduled-messages/{sid}",
                       json={"send_at": (datetime.utcnow() - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"), "timezone": "UTC"}, headers=env.h("owner"))
    assert r.status_code == 400


def test_recurring_edit_keeps_the_next_occurrence_and_only_changes_what_was_asked(env):
    next_run = datetime.utcnow().replace(microsecond=0) + timedelta(hours=2)  # the poller already advanced it
    sid = _insert_schedule(env, send_at=next_run, repeat_interval=60)
    r = env.client.put(f"/api/telegram-groups/-100A/scheduled-messages/{sid}",
                       json={"message_text": "weekly update", "repeat_interval": 180}, headers=env.h("owner"))
    assert r.status_code == 200
    with env.app.app_context():
        row = OfficialScheduledMessage.query.get(sid)
        assert row.send_at == next_run and row.repeat_interval == 180 and row.message_text == "weekly update"


def test_a_failed_save_changes_nothing_at_all(env):
    sid = _insert_schedule(env, repeat_interval=60)
    r = env.client.put(f"/api/telegram-groups/-100A/scheduled-messages/{sid}",
                       json={"message_text": "half applied?", "title": "New title", "repeat_interval": 10}, headers=env.h("owner"))
    assert r.status_code == 400
    with env.app.app_context():
        row = OfficialScheduledMessage.query.get(sid)
        assert row.message_text == "orig" and row.title == "Old" and row.repeat_interval == 60


def test_clearing_the_repeat_makes_it_a_one_off_without_touching_the_time(env):
    t = datetime.utcnow().replace(microsecond=0) + timedelta(hours=5)
    sid = _insert_schedule(env, send_at=t, repeat_interval=120)
    r = env.client.put(f"/api/telegram-groups/-100A/scheduled-messages/{sid}", json={"repeat_interval": None}, headers=env.h("owner"))
    assert r.status_code == 200
    with env.app.app_context():
        row = OfficialScheduledMessage.query.get(sid)
        assert row.repeat_interval is None and row.send_at == t
