"""Guildizer 'Auto-verify on X (X API)' for content posts: upgrade-only, own handle only,
one post pays once. Run from discord-board/backend:  python -m pytest tests/test_x_api_post_verify.py"""
import os
import sys
import tempfile

_DB = os.path.join(tempfile.mkdtemp(), "xapi.db")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB}")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

G = 9731
URL = "https://x.com/alice/status/1234567890123"


@pytest.fixture()
def camp():
    from database import SessionLocal, init_db
    from models import Campaign, CampaignCustomField, CampaignSubmission, Guild
    init_db()
    db = SessionLocal()
    if db.get(Guild, G) is None:
        db.add(Guild(id=G, name="G", owner_id=1, plan="pro"))
        db.flush()
    c = Campaign(guild_id=G, title="C", type="content_submission", status="active", reward_xp=5,
                 verification_mode="x_api", platform="x", post_status="posted", one_per_user=False,
                 settings={"max_submissions": 5})
    db.add(c)
    db.flush()
    db.add(CampaignCustomField(campaign_id=c.id, key="handle", label="X username",
                               field_type="username", required=False, position=0))
    db.commit()
    cid = c.id
    db.close()
    SessionLocal.remove()
    yield cid
    db = SessionLocal()
    db.query(CampaignSubmission).filter(CampaignSubmission.campaign_id == cid).delete()
    db.commit()
    db.close()
    SessionLocal.remove()


def _go(cid, user, value, monkeypatch, verdict="verified", extra=None):
    import campaign_runtime as rt
    import twitter_verify
    calls = []
    monkeypatch.setattr(twitter_verify, "enabled", lambda owner=None: True)
    monkeypatch.setattr(twitter_verify, "verify_post",
                        lambda u, h, **kw: (calls.append((u, h)) or (verdict, None)))
    return rt.create_submission(cid, 0, user, f"u{user}", value, extra_fields=extra or {"handle": "@alice"}), calls


def test_verified_with_own_handle(camp, monkeypatch):
    (status, reward), calls = _go(camp, 21, URL, monkeypatch, extra={"handle": "@frank"})
    assert status == "verified" and reward == 5 and calls[0][1] == "frank"


def test_no_handle_never_uses_post_author(camp, monkeypatch):
    (status, _), calls = _go(camp, 22, URL, monkeypatch, extra={"other": "x"})
    assert status == "pending" and calls == []


def test_same_post_cannot_be_resent(camp, monkeypatch):
    h = {"handle": "@carol"}
    (s1, _), _ = _go(camp, 23, URL, monkeypatch, extra=h)
    (s2, _), calls = _go(camp, 23, URL, monkeypatch, extra=h)
    assert s1 == "verified" and s2 == "pending" and calls == []


def test_failed_unknown_and_kill_switch_stay_pending(camp, monkeypatch):
    for i, v in enumerate(("failed", "unknown")):
        (st, _), _ = _go(camp, 30 + i, f"https://x.com/alice/status/77777777{i}1", monkeypatch, v, extra={"handle": f"@dan{i}"})
        assert st == "pending"
    monkeypatch.setenv("X_API_VERIFY_ENABLED", "0")
    (st, _), calls = _go(camp, 40, "https://x.com/alice/status/8888888888", monkeypatch)
    assert st == "pending" and calls == []


def test_free_guild_stays_pending(camp, monkeypatch):
    from database import SessionLocal
    from models import Guild
    db = SessionLocal(); g = db.get(Guild, G); g.plan = "free"; db.commit(); db.close(); SessionLocal.remove()
    try:
        (st, _), calls = _go(camp, 50, URL, monkeypatch, extra={"handle": "@erin"})
        assert st == "pending" and calls == []
    finally:
        db = SessionLocal(); g = db.get(Guild, G); g.plan = "pro"; db.commit(); db.close(); SessionLocal.remove()
