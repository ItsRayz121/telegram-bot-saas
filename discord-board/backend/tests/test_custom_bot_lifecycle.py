"""Custom-bot lifecycle after Pro lapses (Guildizer).

Run from discord-board/backend:  python -m pytest tests/test_custom_bot_lifecycle.py
Throwaway SQLite database. Discord is never contacted: this only touches rows.
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta

_DB = os.path.join(tempfile.mkdtemp(), "lc.db")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB}")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

import custom_bot_lifecycle as lc  # noqa: E402

T0 = datetime(2026, 11, 1, 12, 0, 0)


def d(n):
    return T0 + timedelta(days=n)


# ── pure schedule ──────────────────────────────────────────────────────────────
def test_next_stage_follows_the_timeline():
    done = {}
    assert lc.next_stage(T0, done, d(0)) == "notice"
    done["notice"] = d(0)
    assert lc.next_stage(T0, done, d(4)) is None                  # reminder not due until day 5
    assert lc.next_stage(T0, done, d(5)) == "reminder"
    done["reminder"] = d(5)
    assert lc.next_stage(T0, done, d(6)) is None and lc.next_stage(T0, done, d(7)) == "pause"
    done["pause"] = d(7)
    assert lc.next_stage(T0, done, d(16)) is None and lc.next_stage(T0, done, d(17)) == "retention_reminder"
    done["retention_reminder"] = d(17)
    assert lc.next_stage(T0, done, d(21)) is None and lc.next_stage(T0, done, d(22)) == "delete"
    done["delete"] = d(22)
    assert lc.next_stage(T0, done, d(99)) is None


def test_a_long_outage_cannot_jump_straight_to_delete():
    """Tick switched off for 40 days, then back on: each stage still waits its minimum gap."""
    done, now, ran = {}, d(40), []
    for _ in range(20):
        st = lc.next_stage(T0, done, now)
        if st:
            done[st] = now
            ran.append((st, (now - d(40)).days))
        now += timedelta(days=1)
    assert [r[0] for r in ran] == ["notice", "reminder", "pause", "retention_reminder", "delete"]
    assert ran[0][1] == 0 and ran[1][1] >= 2 and ran[2][1] >= 4 and ran[3][1] >= 9 and ran[4][1] >= 14


# ── database behaviour ─────────────────────────────────────────────────────────
OWNER_PRO, OWNER_FREE = 9701, 9702
G_PRO, G_FREE = 9710, 9711


@pytest.fixture(scope="module", autouse=True)
def _world():
    from database import SessionLocal, init_db
    from models import Guild, User, UserGuild
    init_db()
    db = SessionLocal()
    db.add_all([User(id=OWNER_PRO, username="paid"), User(id=OWNER_FREE, username="lapsed")])
    db.flush()
    db.add_all([Guild(id=G_PRO, name="Paid", owner_id=OWNER_PRO, plan="pro", plan_expires_at=datetime.utcnow() + timedelta(days=30)),
                Guild(id=G_FREE, name="Free", owner_id=OWNER_FREE, plan="free")])
    db.flush()
    db.add_all([UserGuild(user_id=OWNER_PRO, guild_id=G_PRO, can_manage=True, is_owner=True),
                UserGuild(user_id=OWNER_FREE, guild_id=G_FREE, can_manage=True, is_owner=True)])
    db.commit()
    db.close()


@pytest.fixture()
def db():
    from database import SessionLocal
    s = SessionLocal()
    yield s
    s.rollback()
    s.close()
    SessionLocal.remove()


def make_bot(db, owner, uid, **kw):
    from models import CustomBot
    b = CustomBot(owner_user_id=owner, application_id=uid, bot_user_id=uid, bot_username=f"bot{uid}",
                  token_encrypted="x", status=kw.pop("status", "active"), **kw)
    db.add(b)
    db.commit()
    return b


def fresh(model, pk):
    from database import SessionLocal
    SessionLocal.remove()
    s = SessionLocal()
    try:
        row = s.get(model, pk)
        if row is not None:
            s.expunge(row)
        return row
    finally:
        s.close()


def notifications(owner):
    from database import SessionLocal
    from models import UserNotification
    SessionLocal.remove()
    s = SessionLocal()
    try:
        return [n.title for n in s.query(UserNotification).filter_by(user_id=owner).order_by(UserNotification.id).all()]
    finally:
        s.close()


def test_defaults_are_safe(monkeypatch):
    monkeypatch.delenv("CUSTOM_BOT_LIFECYCLE_DRY_RUN", raising=False)
    monkeypatch.delenv("CUSTOM_BOT_LIFECYCLE_ENABLED", raising=False)
    assert lc.dry_run() is True and lc.enabled() is True


def test_entitlement_matches_the_connect_rule(db):
    assert lc.owner_entitled(db, OWNER_PRO) is True
    assert lc.owner_entitled(db, OWNER_FREE) is False


def test_dry_run_changes_nothing(db, monkeypatch):
    from models import CustomBot, CustomBotLifecycleStage
    monkeypatch.setenv("CUSTOM_BOT_LIFECYCLE_DRY_RUN", "1")
    b = make_bot(db, OWNER_FREE, 9801, lapse_started_at=T0 - timedelta(days=60))
    bid = b.id
    before = notifications(OWNER_FREE)
    stats = lc.run_tick(now=T0)
    assert stats["dry_run"] is True and stats["notice"] >= 1
    row = fresh(CustomBot, bid)
    assert row.status == "active" and row.paused_at is None
    from database import SessionLocal
    s = SessionLocal()
    assert s.query(CustomBotLifecycleStage).filter_by(bot_id=bid).count() == 0
    s.close()
    assert notifications(OWNER_FREE) == before            # nothing was sent


def test_kill_switch_stops_the_whole_tick(db, monkeypatch):
    monkeypatch.setenv("CUSTOM_BOT_LIFECYCLE_DRY_RUN", "0")
    monkeypatch.setenv("CUSTOM_BOT_LIFECYCLE_ENABLED", "0")
    make_bot(db, OWNER_FREE, 9802, lapse_started_at=T0 - timedelta(days=60))
    assert lc.run_tick(now=T0)["checked"] == 0


def test_live_run_walks_the_stages_once_each_and_never_skips(db, monkeypatch):
    from models import CustomBot, Guild
    monkeypatch.setenv("CUSTOM_BOT_LIFECYCLE_DRY_RUN", "0")
    monkeypatch.delenv("CUSTOM_BOT_LIFECYCLE_ENABLED", raising=False)
    from database import SessionLocal
    s = SessionLocal()
    for b in s.query(CustomBot).all():          # isolate this test from the earlier bots
        s.delete(b)
    s.commit()
    s.close()
    SessionLocal.remove()

    db = SessionLocal()
    bot = make_bot(db, OWNER_FREE, 9810)
    db.query(Guild).filter(Guild.id == G_FREE).update({"custom_bot_id": bot.id})
    db.commit()
    bid = bot.id
    db.close()
    SessionLocal.remove()

    titles_before = len(notifications(OWNER_FREE))
    lc.run_tick(now=T0)                                          # day 0: lapse detected + notice
    row = fresh(CustomBot, bid)
    assert row.lapse_started_at == T0 and row.status == "active"
    lc.run_tick(now=T0)                                          # same moment again: nothing repeats
    assert len(notifications(OWNER_FREE)) == titles_before + 1
    lc.run_tick(now=d(3))                                        # not due yet
    assert len(notifications(OWNER_FREE)) == titles_before + 1
    lc.run_tick(now=d(5))                                        # reminder
    assert len(notifications(OWNER_FREE)) == titles_before + 2
    lc.run_tick(now=d(7))                                        # pause
    row = fresh(CustomBot, bid)
    assert row.status == "paused" and row.pause_reason == "pro_lapsed" and row.paused_at == d(7)
    assert row.needs_restart is False
    lc.run_tick(now=d(17))                                       # retention reminder, bot still there
    assert fresh(CustomBot, bid) is not None
    lc.run_tick(now=d(21))                                       # nothing yet
    assert fresh(CustomBot, bid) is not None
    stats = lc.run_tick(now=d(22))                               # delete
    assert stats["delete"] == 1
    assert fresh(CustomBot, bid) is None
    s = SessionLocal()
    assert s.get(Guild, G_FREE).custom_bot_id is None            # server falls back to the official bot
    s.close()
    SessionLocal.remove()
    names = notifications(OWNER_FREE)[titles_before:]
    assert len(names) == 5 and names[-1].endswith("was removed")


def test_an_owner_with_pro_is_never_touched(db, monkeypatch):
    from models import CustomBot
    monkeypatch.setenv("CUSTOM_BOT_LIFECYCLE_DRY_RUN", "0")
    b = make_bot(db, OWNER_PRO, 9820)
    bid = b.id
    for day in (0, 10, 30, 100):
        lc.run_tick(now=d(day))
    row = fresh(CustomBot, bid)
    assert row is not None and row.status == "active" and row.lapse_started_at is None


def test_regaining_pro_cancels_the_lapse_and_clears_the_stages(db, monkeypatch):
    from database import SessionLocal
    from models import CustomBot, CustomBotLifecycleStage, Guild
    monkeypatch.setenv("CUSTOM_BOT_LIFECYCLE_DRY_RUN", "0")
    b = make_bot(db, OWNER_FREE, 9830)
    bid = b.id
    lc.run_tick(now=d(0))
    lc.run_tick(now=d(5))
    s = SessionLocal()
    assert s.query(CustomBotLifecycleStage).filter_by(bot_id=bid).count() == 2
    s.query(Guild).filter(Guild.id == G_FREE).update({"plan": "pro", "plan_expires_at": datetime.utcnow() + timedelta(days=30)})
    s.commit()
    s.close()
    SessionLocal.remove()
    try:
        lc.run_tick(now=d(6))
        row = fresh(CustomBot, bid)
        assert row.lapse_started_at is None and row.status == "active"
        s = SessionLocal()
        assert s.query(CustomBotLifecycleStage).filter_by(bot_id=bid).count() == 0
        s.close()
    finally:
        s = SessionLocal()
        s.query(Guild).filter(Guild.id == G_FREE).update({"plan": "free", "plan_expires_at": None})
        s.commit()
        s.close()
        SessionLocal.remove()


def test_a_paused_bot_whose_owner_regains_pro_stays_paused_until_reactivated(db, monkeypatch):
    from database import SessionLocal
    from models import CustomBot, Guild
    monkeypatch.setenv("CUSTOM_BOT_LIFECYCLE_DRY_RUN", "0")
    b = make_bot(db, OWNER_FREE, 9840, status="paused", paused_at=d(0), lapse_started_at=d(-7))
    bid = b.id
    s = SessionLocal()
    s.query(Guild).filter(Guild.id == G_FREE).update({"plan": "pro", "plan_expires_at": datetime.utcnow() + timedelta(days=30)})
    s.commit()
    s.close()
    SessionLocal.remove()
    try:
        lc.run_tick(now=d(1))
        assert fresh(CustomBot, bid).status == "paused"        # never starts running on its own
    finally:
        s = SessionLocal()
        s.query(Guild).filter(Guild.id == G_FREE).update({"plan": "free", "plan_expires_at": None})
        s.commit()
        s.close()
        SessionLocal.remove()


# ── API: reactivate + paused bots cannot be revived by other endpoints ─────────
@pytest.fixture()
def client_free():
    import app as appmod
    import auth
    from config import Config
    c = appmod.app.test_client()
    c.set_cookie(Config.SESSION_COOKIE_NAME, auth._issue_session(OWNER_FREE))
    return c


def test_reactivate_needs_pro_and_a_paused_bot(client_free, monkeypatch):
    from database import SessionLocal
    from models import CustomBot, Guild
    s = SessionLocal()
    bot = make_bot(s, OWNER_FREE, 9850, status="paused", paused_at=d(0), pause_reason="pro_lapsed", lapse_started_at=d(-7))
    bid = bot.id
    s.close()
    SessionLocal.remove()
    r = client_free.post(f"/api/custom-bots/{bid}/reactivate")
    assert r.status_code == 402 and r.get_json()["error"] == "pro_required"
    assert fresh(CustomBot, bid).status == "paused"

    s = SessionLocal()
    s.query(Guild).filter(Guild.id == G_FREE).update({"plan": "pro", "plan_expires_at": datetime.utcnow() + timedelta(days=30)})
    s.commit()
    s.close()
    SessionLocal.remove()
    try:
        r = client_free.post(f"/api/custom-bots/{bid}/reactivate")
        assert r.status_code == 200 and r.get_json()["bot"]["status"] == "active"
        row = fresh(CustomBot, bid)
        assert row.needs_restart is True and row.paused_at is None and row.lapse_started_at is None
        assert client_free.post(f"/api/custom-bots/{bid}/reactivate").status_code == 400      # not paused any more
    finally:
        s = SessionLocal()
        s.query(Guild).filter(Guild.id == G_FREE).update({"plan": "free", "plan_expires_at": None})
        s.commit()
        s.close()
        SessionLocal.remove()


def test_reactivate_is_owner_only(client_free):
    from database import SessionLocal
    s = SessionLocal()
    bot = make_bot(s, OWNER_PRO, 9860, status="paused")
    bid = bot.id
    s.close()
    SessionLocal.remove()
    assert client_free.post(f"/api/custom-bots/{bid}/reactivate").status_code == 404


def test_replacing_the_token_does_not_unpause(client_free, monkeypatch):
    import custom_bots_api
    from models import CustomBot
    from database import SessionLocal
    s = SessionLocal()
    bot = make_bot(s, OWNER_FREE, 9870, status="paused")
    bid = bot.id
    s.close()
    SessionLocal.remove()
    monkeypatch.setattr(custom_bots_api.discord_api, "validate_bot_token", lambda t: {
        "bot_user_id": 9870, "application_id": 9870, "bot_username": "bot9870", "bot_avatar": None,
        "intents_members": True, "intents_message_content": True})
    r = client_free.post(f"/api/custom-bots/{bid}/token", json={"token": "abc.def.ghi"})
    assert r.status_code == 200
    assert fresh(CustomBot, bid).status == "paused"
