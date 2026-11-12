"""Per-task X auto-verify (Guildizer): settings are cleaned, Pro-gated, and the submit
path only ever upgrades to verified on a positive match.

Run from discord-board/backend:  python -m pytest tests/test_task_x_autoverify.py
"""
import os
import sys
import tempfile

_DB = os.path.join(tempfile.mkdtemp(), "tx.db")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB}")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

G = 9720


def test_clean_task_settings():
    from campaigns_api import _clean_task_settings as clean, _tasks_want_autoverify as want
    out = clean({"auto_verify_x": True, "raid_goals": {"retweets": "5", "likes": 0, "bogus": 3}}, "raid", "x")
    assert out == {"auto_verify_x": True, "raid_goals": {"retweets": 5}}
    assert clean({"auto_verify_x": True, "raid_goals": {"retweets": 5}, "k": 1}, "proof_collection", None) == {"k": 1}
    assert "auto_verify_x" not in clean({"auto_verify_x": True}, "social_task", "discord")
    assert clean(None, "raid", "x") == {}
    assert want([{"settings": {"auto_verify_x": True}}]) and not want([{"settings": {}}]) and not want(None)


@pytest.fixture()
def seeded():
    from database import SessionLocal, init_db
    from models import Campaign, CampaignSubmission, CampaignTask, Guild
    init_db()
    db = SessionLocal()
    if db.get(Guild, G) is None:
        db.add(Guild(id=G, name="G", owner_id=1, plan="pro"))
        db.flush()
    c = Campaign(guild_id=G, title="Multi", type="social_task", status="active",
                 reward_xp=0, post_status="posted", settings={})
    db.add(c)
    db.flush()
    t = CampaignTask(campaign_id=c.id, order=0, title="RT", type="raid", platform="x",
                     task_url="https://x.com/p/status/1234567890123", verification_mode="manual",
                     reward_xp=7, settings={"auto_verify_x": True, "raid_goals": {"retweets": 2}})
    db.add(t)
    db.commit()
    ids = (c.id, t.id)
    db.close()
    SessionLocal.remove()
    yield ids
    db = SessionLocal()
    db.query(CampaignSubmission).filter(CampaignSubmission.campaign_id == ids[0]).delete()
    db.commit()
    db.close()
    SessionLocal.remove()


def _go(seeded, monkeypatch, user, result, extra=None):
    import campaign_runtime as rt
    import twitter_verify
    calls = []
    monkeypatch.setattr(twitter_verify, "enabled", lambda owner=None: True)

    def fake(url, goals, handle, **kw):
        calls.append((url, goals, handle))
        return {"overall": result}
    monkeypatch.setattr(twitter_verify, "verify_raid", fake)
    cid, tid = seeded
    return rt.create_submission(cid, tid, user, f"u{user}", "proof", extra_fields=extra or {"handle": "@alice"}), calls


def test_positive_match_verifies_and_pays(seeded, monkeypatch):
    (status, reward), calls = _go(seeded, monkeypatch, 11, "verified")
    assert (status, reward) == ("verified", 7)
    assert calls[0][1] == {"retweets": 2} and calls[0][2] == "alice"


def test_uncertain_stays_pending_and_kill_switch(seeded, monkeypatch):
    (status, reward), _ = _go(seeded, monkeypatch, 12, "pending")
    assert (status, reward) == ("pending", 0)
    monkeypatch.setenv("TASK_X_AUTOVERIFY_ENABLED", "0")
    (status, _r), calls = _go(seeded, monkeypatch, 13, "verified")
    assert status == "pending" and calls == []


def test_non_pro_server_never_auto_verifies(seeded, monkeypatch):
    from database import SessionLocal
    from models import Guild
    db = SessionLocal()
    db.get(Guild, G).plan = "free"
    db.commit()
    db.close()
    SessionLocal.remove()
    try:
        (status, _r), calls = _go(seeded, monkeypatch, 14, "verified")
        assert status == "pending" and calls == []
    finally:
        db = SessionLocal()
        db.get(Guild, G).plan = "pro"
        db.commit()
        db.close()
        SessionLocal.remove()
