"""Continuous raids (Guildizer): same rules as Telegizer - original tweets only, 12 h polling, one
fetch per handle, baseline first, caps, Pro only, one X account per person, 1 h manual check.

Run from discord-board/backend:  python -m pytest tests/test_raid_auto.py
"""
import os
import random
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from test_campaign_workspace import OWNER, client  # noqa: E402,F401

PRO, FREE, PRO2 = 9740, 9741, 9742
TPL = {"goals": {"likes": {"min": 10, "max": 20}, "retweets": 5}, "action_xp": {"like": 1}, "duration_hours": 24}


@pytest.fixture(scope="module", autouse=True)
def seed(client):
    from database import SessionLocal
    from models import Guild, UserGuild
    db = SessionLocal()
    for gid, plan in ((PRO, "pro"), (FREE, "free"), (PRO2, "pro")):
        db.add(Guild(id=gid, name=f"G{gid}", owner_id=OWNER, plan=plan))
        db.flush()
        db.add(UserGuild(user_id=OWNER, guild_id=gid, can_manage=True, is_owner=True))
    db.commit()
    db.close()
    SessionLocal.remove()


@pytest.fixture(autouse=True)
def clean():
    from database import SessionLocal
    from models import Campaign, RaidAutomation
    yield
    db = SessionLocal()
    db.query(Campaign).filter(Campaign.guild_id.in_([PRO, FREE, PRO2])).delete(synchronize_session=False)
    db.query(RaidAutomation).delete()
    db.commit()
    db.close()
    SessionLocal.remove()


def tw(i, text="gm", **kw):
    return dict({"id": str(i), "text": text, "createdAt": datetime.utcnow().strftime("%a %b %d %H:%M:%S +0000 %Y")}, **kw)


def _auto(guild=PRO, handle="elyon", last=None, template=None, user=OWNER):
    import raid_auto as ra
    from database import SessionLocal
    from models import RaidAutomation
    db = SessionLocal()
    row = RaidAutomation(guild_id=guild, user_id=user, channel_id=555, x_handle=handle,
                         template=ra.validate_template(template or TPL), last_tweet_id=last)
    db.add(row)
    db.commit()
    rid = row.id
    db.close()
    SessionLocal.remove()
    return rid


def _row(rid):
    from database import SessionLocal
    from models import RaidAutomation
    db = SessionLocal()
    return db, db.get(RaidAutomation, rid)


class Spawner:
    def __init__(self):
        self.calls = []

    def __call__(self, db, auto, tweet, now, rng):
        self.calls.append(int(tweet["id"]))


def _process(rid, tweets, spawner=None):
    import raid_auto as ra
    db, a = _row(rid)
    try:
        return ra.process(db, a, tweets, spawner=spawner or Spawner()), a.last_tweet_id, a.last_error
    finally:
        db.close()


def test_template_and_tweet_rules():
    import raid_auto as ra
    t = ra.validate_template(TPL)
    assert t["goals"] == {"likes": {"min": 10, "max": 20}, "retweets": {"min": 5, "max": 5}}
    assert all(10 <= ra.resolve_goals(t, random.Random(s))["likes"] <= 20 for s in range(30))
    with pytest.raises(ra.AutoError):
        ra.validate_template({"goals": {}})
    assert ra.is_original(tw(1)) and not ra.is_original(tw(1, isReply=True))
    assert not ra.is_original(tw(1, retweeted_tweet={"id": "2"})) and not ra.is_original(tw(1, text="RT @a: x"))
    assert not ra.is_original(tw(1, quoted_tweet={"id": "2"})) and ra.is_original(tw(1, quoted_tweet={"id": "2"}), True)


def test_baseline_then_original_tweets_only_with_caps():
    rid = _auto()
    assert _process(rid, [tw(100)])[:2] == (0, "100")                           # baseline: no raid
    sp = Spawner()
    batch = [tw(101, isReply=True), tw(102), tw(103, retweeted_tweet={"id": "1"}), tw(104, createdAt="Mon Jan 01 00:00:00 +0000 2018"), tw(105)]
    n, last, _ = _process(rid, batch, sp)
    assert n == 2 and sp.calls == [102, 105] and last == "105"
    sp2 = Spawner()
    assert _process(rid, [tw(106), tw(107)], sp2)[0] == 0                         # daily cap (2) used up


def test_free_server_never_starts_raids():
    rid = _auto(guild=FREE, last="1")
    sp = Spawner()
    n, _, err = _process(rid, [tw(2)], sp)
    assert n == 0 and sp.calls == [] and "Pro" in err


def test_one_call_per_handle_and_the_12h_schedule():
    import raid_auto as ra
    a1, a2 = _auto(PRO, "elyon", "1"), _auto(PRO2, "elyon", "1", user=OWNER + 1)
    calls = []

    def fetcher(handle, key):
        calls.append(handle)
        return "ok", [tw(5)], None
    assert ra.run_due(fetcher=fetcher, spawner=Spawner()) == {"fetched": 1, "started": 2}   # 1 call, 2 servers
    assert ra.run_due(fetcher=fetcher, spawner=Spawner()) == {"fetched": 0, "started": 0}
    db, a = _row(a1)
    assert a.next_poll_at > datetime.utcnow() + timedelta(hours=11)
    db.close()
    ra.run_due(now=datetime.utcnow() + timedelta(hours=13), fetcher=lambda h, k: ("retry", [], "down"), spawner=Spawner())
    db, a = _row(a1)
    assert a.last_error == "down" and a.next_poll_at < datetime.utcnow() + timedelta(hours=14 + 1) \
        and a.next_poll_at > datetime.utcnow() + timedelta(hours=13)
    db.close()


def test_kill_switch_and_manual_check_limit(monkeypatch):
    import raid_auto as ra
    rid = _auto(last="1")
    monkeypatch.setenv("RAID_AUTO_ENABLED", "0")
    assert ra.run_due(fetcher=lambda h, k: pytest.fail("must not call")) == {"fetched": 0, "started": 0}
    monkeypatch.delenv("RAID_AUTO_ENABLED")
    db, a = _row(rid)
    out = ra.check_now(db, a, fetcher=lambda h, k: ("ok", [tw(2)], None), spawner=Spawner())
    assert out["started"] == 1
    with pytest.raises(ra.AutoError) as e:
        ra.check_now(db, a, fetcher=lambda h, k: ("ok", [], None), spawner=Spawner())
    assert e.value.status == 429
    db.close()


def test_a_real_campaign_is_created_and_queued_for_posting():
    import raid_auto as ra
    from models import Campaign
    rid = _auto(last="1")
    db, a = _row(rid)
    assert ra.process(db, a, [tw(7, "We just shipped v2 https://t.co/abc")], rng=random.Random(1)) == 1
    c = db.query(Campaign).filter(Campaign.guild_id == PRO).one()
    assert c.type == "raid" and c.status == "active" and c.channel_id == 555 and c.needs_post
    assert c.task_url == "https://x.com/elyon/status/7" and c.title == "Raid: We just shipped v2"
    assert 10 <= c.settings["raid_goals"]["likes"] <= 20 and c.ends_at > datetime.utcnow() + timedelta(hours=23)
    db.close()


# ── API ──────────────────────────────────────────────────────────────────────────

def _url(g):
    return f"/api/guilds/{g}/raid-auto"


BODY = {"x_handle": "@Elyon", "channel_id": "555", "enabled": True, "template": TPL}


def test_api_save_read_check_remove_and_rules(client):
    r = client.get(_url(PRO)).get_json()
    assert r["automation"] is None and r["is_paid"] and r["limits"]["interval_hours"] == 12
    r = client.put(_url(PRO), json=BODY)
    assert r.status_code == 200 and r.get_json()["automation"]["x_handle"] == "elyon"
    assert "_recent" not in r.get_json()["automation"]["template"]
    r = client.put(_url(PRO2), json=dict(BODY, x_handle="@third"))                 # same person, other account
    assert r.status_code == 409 and "One X account per owner" in r.get_json()["error"]
    assert client.put(_url(PRO2), json=dict(BODY, channel_id="")).status_code == 400
    assert client.put(_url(PRO), json=dict(BODY, template={"goals": {}})).status_code == 400
    assert client.put(_url(FREE), json=BODY).status_code == 403                    # Pro only
    from database import SessionLocal
    from models import RaidAutomation
    db = SessionLocal()
    row = db.query(RaidAutomation).filter(RaidAutomation.guild_id == PRO).one()
    row.last_polled_at = datetime.utcnow()
    db.commit()
    db.close()
    assert client.post(_url(PRO) + "/check").status_code == 429                    # polled a moment ago
    assert client.delete(_url(PRO)).get_json()["automation"] is None
