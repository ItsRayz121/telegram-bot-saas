"""Continuous raids (Telegram): original tweets only, 12 h polling, one fetch per handle,
baseline on first check, caps, Pro only, one X account per owner.

Run from the repo root:  python -m pytest backend/tests/test_raid_auto.py
"""
import os
import random
from datetime import datetime, timedelta

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-with-enough-length-1234")
os.environ.setdefault("ENCRYPTION_KEY", "Zm9vYmFyYmF6cXV4Zm9vYmFyYmF6cXV4Zm9vYmFyYmE=")
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from flask import Flask

from backend.models import db, User, TelegramGroup, RaidAutomation, EngagementCampaign
import backend.assistant.hub_models  # noqa: F401
from backend import raid_auto as ra

TPL = {"goals": {"likes": {"min": 10, "max": 20}, "retweets": 5}, "action_xp": {"like": 1}, "duration_hours": 24}


@pytest.fixture()
def ctx():
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI="sqlite://", TESTING=True, SECRET_KEY="x",
                      SQLALCHEMY_ENGINE_OPTIONS={"connect_args": {"check_same_thread": False}})
    db.init_app(app)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()


def _user(email, tier="pro"):
    u = User(email=email, full_name="O", auth_provider="email", subscription_tier=tier)
    db.session.add(u)
    db.session.flush()
    return u


def _auto(user, gid="-100A", handle="elyon", last=None, template=None, **kw):
    db.session.add(TelegramGroup(telegram_group_id=gid, title="G" + gid, owner_user_id=user.id, bot_status="active"))
    row = RaidAutomation(owner_user_id=user.id, lineage="official", telegram_group_id=gid, x_handle=handle,
                         template=ra.validate_template(template or TPL), last_tweet_id=last, **kw)
    db.session.add(row)
    db.session.commit()
    return row


def tw(i, text="gm", **kw):
    now = datetime.utcnow().strftime("%a %b %d %H:%M:%S +0000 %Y")
    return dict({"id": str(i), "text": text, "createdAt": now}, **kw)


class Spawner:
    def __init__(self):
        self.calls = []

    def __call__(self, auto, tweet, now, rng):
        self.calls.append(int(tweet["id"]))


def test_template_goals_are_fixed_or_a_random_range():
    t = ra.validate_template(TPL)
    assert t["goals"] == {"likes": {"min": 10, "max": 20}, "retweets": {"min": 5, "max": 5}}
    for seed in range(30):
        g = ra.resolve_goals(t, random.Random(seed))
        assert 10 <= g["likes"] <= 20 and g["retweets"] == 5
    assert ra.validate_template({"goals": {"likes": {"min": 30, "max": 10}}})["goals"]["likes"] == {"min": 10, "max": 30}
    with pytest.raises(ra.AutoError):
        ra.validate_template({"goals": {}})
    assert "_recent" not in ra.public_template(t)


def test_only_original_posts_count():
    assert ra.is_original(tw(1))
    assert not ra.is_original(tw(1, isReply=True))
    assert not ra.is_original(tw(1, inReplyToId="9"))
    assert not ra.is_original(tw(1, retweeted_tweet={"id": "9"}))
    assert not ra.is_original(tw(1, text="RT @someone: hi"))
    assert not ra.is_original(tw(1, quoted_tweet={"id": "9"}))
    assert ra.is_original(tw(1, quoted_tweet={"id": "9"}), include_quotes=True)
    assert ra.normalize_handle("https://x.com/Elyon_Chain?s=1") == "elyon_chain"
    assert ra.normalize_handle("not a handle!!") is None


def test_first_check_is_a_baseline_and_never_raids_old_posts(ctx):
    a = _auto(_user("a@x.io"))
    sp = Spawner()
    assert ra.process(a, [tw(100), tw(101)], spawner=sp) == 0
    assert a.last_tweet_id == "101" and sp.calls == []
    assert a.next_poll_at - a.last_polled_at == timedelta(hours=12)          # next look in 12 hours


def test_new_original_tweets_start_raids_and_noise_is_ignored(ctx):
    a = _auto(_user("b@x.io"), last="100")
    sp = Spawner()
    batch = [tw(101, isReply=True), tw(102), tw(103, retweeted_tweet={"id": "1"}), tw(104, "pinned old", createdAt="Mon Jan 01 00:00:00 +0000 2018"),
             tw(105), tw(99, "older than baseline")]
    assert ra.process(a, batch, spawner=sp) == 2
    assert sp.calls == [102, 105] and a.last_tweet_id == "105" and a.raids_started == 2
    assert ra.process(a, batch, spawner=sp) == 0                               # same batch again: nothing new


def test_daily_cap_and_per_check_cap(ctx):
    tpl = dict(TPL, max_per_day=2)
    a = _auto(_user("c@x.io"), last="1", template=tpl)
    sp = Spawner()
    assert ra.process(a, [tw(i) for i in range(2, 8)], spawner=sp) == 2       # 5 new, but MAX_PER_POLL = 2
    assert sp.calls == [6, 7]                                                  # the newest two
    sp2 = Spawner()
    assert ra.process(a, [tw(20), tw(21)], spawner=sp2) == 0                   # daily cap (2) already used
    assert a.last_tweet_id == "21"


def test_free_owner_never_starts_raids(ctx):
    a = _auto(_user("free@x.io", tier="free"), last="1")
    sp = Spawner()
    assert ra.process(a, [tw(2)], spawner=sp) == 0 and sp.calls == []
    assert "Pro or Enterprise" in a.last_error


def test_one_provider_call_per_handle_and_12h_schedule(ctx):
    u1, u2 = _user("d1@x.io"), _user("d2@x.io")
    a1 = _auto(u1, gid="-100B", handle="elyon", last="1")
    a2 = _auto(u2, gid="-100C", handle="elyon", last="1")
    a3 = _auto(_user("d3@x.io"), gid="-100D", handle="other", last="1")
    calls = []

    def fetcher(handle, key):
        calls.append(handle)
        return "ok", [tw(5)], None
    sp = Spawner()
    stats = ra.run_due(fetcher=fetcher, spawner=sp)
    assert sorted(calls) == ["elyon", "other"]                                 # 2 calls for 3 groups
    assert stats == {"fetched": 2, "started": 3}
    assert ra.run_due(fetcher=fetcher, spawner=sp) == {"fetched": 0, "started": 0}   # nothing due for 12 h
    assert a1.next_poll_at > datetime.utcnow() + timedelta(hours=11)


def test_a_failed_fetch_retries_in_an_hour_and_the_error_is_kept(ctx):
    a = _auto(_user("e@x.io"), last="1")
    ra.run_due(fetcher=lambda h, k: ("retry", [], "provider down"), spawner=Spawner())
    assert a.last_error == "provider down"
    assert timedelta(minutes=50) < a.next_poll_at - datetime.utcnow() < timedelta(minutes=70)
    ra.run_due(now=datetime.utcnow() + timedelta(hours=2), fetcher=lambda h, k: ("fatal", [], "key rejected"), spawner=Spawner())
    assert a.next_poll_at > datetime.utcnow() + timedelta(hours=10)            # fatal: wait the full interval


def test_kill_switch(ctx, monkeypatch):
    _auto(_user("k@x.io"), last="1")
    monkeypatch.setenv("RAID_AUTO_ENABLED", "0")
    called = []
    assert ra.run_due(fetcher=lambda h, k: called.append(1) or ("ok", [], None)) == {"fetched": 0, "started": 0}
    assert called == []


def test_check_now_is_limited_to_once_an_hour(ctx):
    a = _auto(_user("n@x.io"), last="1")
    out = ra.check_now(a, fetcher=lambda h, k: ("ok", [tw(2)], None), spawner=Spawner())
    assert out["started"] == 1
    with pytest.raises(ra.AutoError) as e:
        ra.check_now(a, fetcher=lambda h, k: ("ok", [], None), spawner=Spawner())
    assert e.value.status == 429


def test_one_x_account_per_owner_and_pro_only(ctx):
    u = _user("o@x.io")
    db.session.add_all([TelegramGroup(telegram_group_id=g, title=g, owner_user_id=u.id, bot_status="active") for g in ("-1", "-2")])
    db.session.commit()
    ra.upsert(u, lineage="official", telegram_group_id="-1", x_handle="@Elyon", template=TPL)
    ra.upsert(u, lineage="official", telegram_group_id="-2", x_handle="elyon", template=TPL)        # same account: fine
    with pytest.raises(ra.AutoError) as e:
        ra.upsert(u, lineage="official", telegram_group_id="-2", x_handle="@other", template=TPL)
    assert e.value.status == 409 and "One X account per owner" in e.value.message
    with pytest.raises(ra.AutoError) as e:
        ra.upsert(_user("free2@x.io", tier="free"), lineage="official", telegram_group_id="-9", x_handle="x", template=TPL)
    assert e.value.status == 403
    with pytest.raises(ra.AutoError):
        ra.upsert(u, lineage="official", telegram_group_id="-1", x_handle="not a handle", template=TPL)


def test_a_real_raid_campaign_is_created_for_a_new_tweet(ctx):
    u = _user("real@x.io")
    a = _auto(u, gid="-100R", last="1")
    started = ra.process(a, [tw(7, "We just shipped v2 https://t.co/abc")], rng=random.Random(1))
    assert started == 1
    c = EngagementCampaign.query.filter_by(telegram_group_id="-100R").one()
    assert c.type == "raid" and c.status == "active" and c.task_url == "https://x.com/elyon/status/7"
    assert c.title == "Raid: We just shipped v2" and c.settings["auto_raid"] == a.id
    assert 10 <= c.settings["raid_goals"]["likes"] <= 20 and c.settings["raid_goals"]["retweets"] == 5


# ── API ──────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def api():
    from flask_jwt_extended import JWTManager, create_access_token
    from backend.routes.engagement_workspace import workspace_official_bp
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI="sqlite://", JWT_SECRET_KEY=os.environ["JWT_SECRET_KEY"],
                      JWT_TOKEN_LOCATION=["headers"], TESTING=True, SECRET_KEY="x",
                      SQLALCHEMY_ENGINE_OPTIONS={"connect_args": {"check_same_thread": False}})
    db.init_app(app)
    JWTManager(app)
    app.register_blueprint(workspace_official_bp)
    with app.app_context():
        db.create_all()
        owner, free, stranger = _user("ao@x.io"), _user("af@x.io", tier="free"), _user("as@x.io")
        for g, u in (("-100G", owner), ("-100F", free)):
            db.session.add(TelegramGroup(telegram_group_id=g, title=g, owner_user_id=u.id, bot_status="active"))
        db.session.commit()
        hdr = lambda u: {"Authorization": "Bearer " + create_access_token(identity=str(u.id))}
        yield app.test_client(), {"owner": hdr(owner), "free": hdr(free), "stranger": hdr(stranger)}
        db.session.remove()


BODY = {"x_handle": "@Elyon", "enabled": True, "template": TPL}
U = "/api/telegram-groups/-100G/engagement/raid-auto"


def test_api_save_read_check_and_remove(api):
    c, h = api
    r = c.get(U, headers=h["owner"]).get_json()
    assert r["automation"] is None and r["can_edit"] and r["is_paid"] and r["limits"]["interval_hours"] == 12
    r = c.put(U, json=BODY, headers=h["owner"])
    assert r.status_code == 200 and r.get_json()["automation"]["x_handle"] == "elyon"
    assert "_recent" not in r.get_json()["automation"]["template"]
    assert c.put(U, json=dict(BODY, x_handle="@another"), headers=h["owner"]).status_code in (200,)   # same group, same owner: changes account
    # a second group of the same owner cannot follow a different account
    db.session.add(TelegramGroup(telegram_group_id="-100H", title="H", owner_user_id=int(db.session.query(User).filter_by(email="ao@x.io").one().id), bot_status="active"))
    db.session.commit()
    r = c.put("/api/telegram-groups/-100H/engagement/raid-auto", json=dict(BODY, x_handle="@third"), headers=h["owner"])
    assert r.status_code == 409 and "One X account per owner" in r.get_json()["error"]
    row = RaidAutomation.query.filter_by(telegram_group_id="-100G").one()
    row.last_polled_at = datetime.utcnow()
    db.session.commit()
    r = c.post(U + "/check", headers=h["owner"])
    assert r.status_code == 429                                                          # polled a moment ago
    assert c.delete(U, headers=h["owner"]).get_json()["automation"] is None
    assert RaidAutomation.query.filter_by(telegram_group_id="-100G").count() == 0


def test_api_pro_only_and_group_access(api):
    c, h = api
    assert c.put("/api/telegram-groups/-100F/engagement/raid-auto", json=BODY, headers=h["free"]).status_code == 403
    assert c.get(U, headers=h["stranger"]).status_code == 404                           # not their group
    assert c.put(U, json={"x_handle": "@x", "template": {"goals": {}}}, headers=h["owner"]).status_code == 400


# ── changing "raid lasts" while a raid is running ───────────────────────────────

def _running_raid(auto, hours_ago=10, status="active", auto_id=True):
    c = EngagementCampaign(telegram_group_id=auto.telegram_group_id, owner_user_id=auto.owner_user_id, type="raid",
                           title="Raid: x", status=status, task_url="https://x.com/elyon/status/1",
                           created_at=datetime.utcnow() - timedelta(hours=hours_ago),
                           ends_at=datetime.utcnow() + timedelta(hours=14),
                           settings={"auto_raid": auto.id} if auto_id else {})
    db.session.add(c)
    db.session.commit()
    return c


def test_changing_the_duration_updates_running_raids_from_their_own_start(ctx):
    u = _user("dur@x.io")
    a = _auto(u, gid="-100D1", last="1")
    running, closed, manual = _running_raid(a), _running_raid(a, status="closed"), _running_raid(a, auto_id=False)
    closed_end, manual_end = closed.ends_at, manual.ends_at
    row = ra.upsert(u, lineage="official", telegram_group_id="-100D1", x_handle="elyon", template=dict(TPL, duration_hours=48))
    assert row.updated_raids == 1
    db.session.refresh(running)
    assert abs((running.ends_at - (running.created_at + timedelta(hours=48))).total_seconds()) < 5   # start + 48 h
    db.session.refresh(closed); db.session.refresh(manual)
    assert closed.ends_at == closed_end and manual.ends_at == manual_end                              # untouched
    # saving the same duration again changes nothing
    assert ra.upsert(u, lineage="official", telegram_group_id="-100D1", x_handle="elyon",
                     template=dict(TPL, duration_hours=48)).updated_raids == 0


def test_shortening_below_the_time_already_run_gives_a_one_hour_grace(ctx):
    u = _user("dur2@x.io")
    a = _auto(u, gid="-100D2", last="1", template=dict(TPL, duration_hours=24))
    running = _running_raid(a, hours_ago=10)
    ra.upsert(u, lineage="official", telegram_group_id="-100D2", x_handle="elyon", template=dict(TPL, duration_hours=6))
    db.session.refresh(running)
    left = running.ends_at - datetime.utcnow()
    assert timedelta(minutes=55) < left < timedelta(minutes=65)                                       # 6 h < 10 h elapsed -> ends in ~1 h
