"""Campaign preview endpoint + notice builders (Discord service).

Run from discord-board/backend:  python -m pytest tests/test_campaign_preview.py
Uses a throwaway SQLite file and a forged session cookie; no Discord, no bot, nothing is posted.
"""
import os
import sys
import tempfile

_DB = os.path.join(tempfile.mkdtemp(), "t.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_DB}"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402


@pytest.fixture(scope="module")
def client():
    import app as appmod
    import auth
    from config import Config
    from database import SessionLocal, init_db
    from models import Campaign, Guild, User, UserGuild
    init_db()
    db = SessionLocal()
    db.add_all([User(id=1, username="owner"), User(id=2, username="stranger"),
                Guild(id=100, name="G", owner_id=1, plan="free"), Guild(id=200, name="Other", owner_id=2)])
    db.flush()
    db.add(UserGuild(user_id=1, guild_id=100, can_manage=True, is_owner=True))
    db.commit()
    before = db.query(Campaign).count()
    db.close()
    c = appmod.app.test_client()
    c.set_cookie(Config.SESSION_COOKIE_NAME, auth._issue_session(1))
    c.campaigns_before = before
    return c


def test_preview_builds_the_real_embed_and_writes_nothing(client):
    from database import SessionLocal
    from models import Campaign
    r = client.post("/api/guilds/100/campaigns/preview", json={
        "title": "Launch quiz", "description": "Win XP", "type": "proof_collection",
        "verification_mode": "manual", "reward_xp": 50, "duration_hours": 24,
        "tasks": [{"title": "Follow us", "reward_xp": 10}],
    })
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body["embed"]["title"] == "Launch quiz"
    assert any(f["name"] == "Follow us" for f in body["embed"]["fields"])
    assert any("Ends" in f["name"] for f in body["embed"]["fields"])
    assert body["buttons"] == ["Submit: Follow us"]
    assert [n["key"] for n in body["notices"]] == ["approved", "rejected"]
    assert "approved" in body["notices"][0]["text"] and "rejected" in body["notices"][1]["text"]
    db = SessionLocal()
    assert db.query(Campaign).count() == client.campaigns_before  # nothing was created
    db.close()


def test_preview_requires_login_and_guild_access(client):
    import app as appmod
    anon = appmod.app.test_client()
    assert anon.post("/api/guilds/100/campaigns/preview", json={"title": "x"}).status_code == 401
    assert client.post("/api/guilds/200/campaigns/preview", json={"title": "x"}).status_code == 403  # someone else's server


def test_x_raid_preview_uses_the_action_button_and_goals(client):
    r = client.post("/api/guilds/100/campaigns/preview", json={
        "title": "Raid", "type": "raid", "platform": "x", "task_url": "https://x.com/a/status/1",
        "settings": {"raid_goals": {"likes": 20}}})
    body = r.get_json()
    assert body["buttons"] == ["\U0001f426 Start raid"]
    assert any("Raid goals" in f["name"] for f in body["embed"]["fields"])


def test_review_notice_text_matches_the_dm_the_bot_sends():
    import campaign_views as cv
    assert cv.review_notice_text({"status": "verified", "title": "T", "reward": 5}) == "\u2705 Your submission for **T** was approved \u2014 +5 XP!"
    assert cv.review_notice_text({"status": "verified", "title": "T", "reward": 0}) == "\u2705 Your submission for **T** was approved!"
    assert cv.review_notice_text({"status": "rejected", "title": "T", "reason": "blurry", "allow_resubmit": True}) == \
        "\u274c Your submission for **T** was rejected.\n> blurry\nYou can submit again."
