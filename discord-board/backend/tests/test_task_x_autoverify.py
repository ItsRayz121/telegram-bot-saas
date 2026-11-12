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
    from models import Campaign, CampaignCustomField, CampaignSubmission, CampaignTask, Guild
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
    db.flush()
    db.add(CampaignCustomField(campaign_id=c.id, task_id=t.id, key="handle", label="Your X @username",
                               field_type="username", required=True, position=0))
    db.add(CampaignCustomField(campaign_id=c.id, task_id=t.id, key="uid", label="Exchange UID",
                               field_type="uid", required=False, position=1))
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


def test_other_fields_are_never_taken_as_the_handle(seeded, monkeypatch):
    import social_handles
    # only a UID was typed (no handle field): nothing to verify, nothing saved
    (status, _r), calls = _go(seeded, monkeypatch, 15, "verified", extra={"uid": "12345"})
    assert status == "pending" and calls == []
    assert social_handles.get_handle(15) is None


def _pending(seeded, user, age_s, fields=None):
    from datetime import datetime, timedelta
    from database import SessionLocal
    from models import CampaignSubmission
    cid, tid = seeded
    db = SessionLocal()
    sub = CampaignSubmission(campaign_id=cid, task_id=tid, user_id=user, username=f"u{user}",
                             status="pending", proof={"value": "p", "fields": fields or {"handle": "@late"}},
                             created_at=datetime.utcnow() - timedelta(seconds=age_s))
    db.add(sub)
    db.commit()
    sid = sub.id
    db.close()
    SessionLocal.remove()
    return sid


def _status(sid):
    from database import SessionLocal
    from models import CampaignSubmission
    db = SessionLocal()
    row = db.get(CampaignSubmission, sid)
    out = (row.status, row.reward_granted)
    db.close()
    SessionLocal.remove()
    return out


def _patch_x(monkeypatch, result):
    import twitter_verify
    calls = []
    monkeypatch.setattr(twitter_verify, "enabled", lambda owner=None: True)
    monkeypatch.setattr(twitter_verify, "verify_raid",
                        lambda url, goals, handle, **kw: calls.append(handle) or {"overall": result})
    return calls


def test_recheck_upgrades_and_pays_once(seeded, monkeypatch):
    import campaign_runtime as rt
    sid = _pending(seeded, 31, 240)
    calls = _patch_x(monkeypatch, "verified")
    assert rt.recheck_pending_x_tasks() == 1
    assert _status(sid) == ("verified", 7) and calls == ["late"]
    assert rt.recheck_pending_x_tasks() == 0              # not checked or paid again


def test_recheck_never_rejects_and_respects_window_and_kill_switch(seeded, monkeypatch):
    import campaign_runtime as rt
    new, old, unsure_ok = _pending(seeded, 32, 10), _pending(seeded, 33, 3 * 3600), _pending(seeded, 34, 240)
    calls = _patch_x(monkeypatch, "pending")
    assert rt.recheck_pending_x_tasks() == 0
    assert [_status(i)[0] for i in (new, old, unsure_ok)] == ["pending"] * 3
    assert calls == ["late"]                               # only the eligible one was checked
    monkeypatch.setenv("TASK_X_AUTOVERIFY_ENABLED", "0")
    calls.clear()
    assert rt.recheck_pending_x_tasks() == 0 and calls == []


def test_follow_target_is_read_from_a_profile_link():
    from twitter_verify import extract_author_handle as who
    assert who("https://x.com/ElyonChain") == "ElyonChain"
    assert who("https://x.com/proj/status/1234567890123") == "proj"
    assert who("https://x.com/home") is None and who("https://x.com/i/status/1") is None and who(None) is None
