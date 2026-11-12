"""Multiple submissions per member: cap, required count, and extra-submission XP."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from test_campaign_workspace import OWNER, client  # noqa: E402,F401

G = 9231
CID = 9731
CID_ONE = 9732


@pytest.fixture(scope="module", autouse=True)
def seed(client):
    from database import SessionLocal
    from models import Campaign, Guild, UserGuild
    db = SessionLocal()
    db.add(Guild(id=G, name="Multi server", owner_id=OWNER, plan="free"))
    db.flush()
    db.add(UserGuild(user_id=OWNER, guild_id=G, can_manage=True, is_owner=True))
    db.add(Campaign(id=CID, guild_id=G, title="Multi", type="content", status="active", reward_xp=10,
                    verification_mode="honor", one_per_user=False,
                    settings={"min_submissions": 2, "max_submissions": 3, "extra_submission_xp": 4}))
    db.add(Campaign(id=CID_ONE, guild_id=G, title="One", type="content", status="active", reward_xp=10,
                    verification_mode="honor", one_per_user=True))
    db.commit()
    db.close()
    SessionLocal.remove()


def test_limits_helper():
    import campaign_limits as cl
    from models import Campaign
    assert cl.limits(Campaign(one_per_user=True, type="content", settings={"max_submissions": 9})) == (1, 1)
    assert cl.limits(Campaign(one_per_user=False, type="raid", settings={})) == (1, 1)
    assert cl.limits(Campaign(one_per_user=False, type="content", settings={})) == (1, None)
    assert cl.limits(Campaign(one_per_user=False, type="content",
                              settings={"min_submissions": 5, "max_submissions": 3})) == (3, 3)


def test_clean_settings():
    import campaign_limits as cl
    assert cl.clean_settings({"min_submissions": "", "max_submissions": "4", "x": 1}) == {"max_submissions": 4, "x": 1}
    with pytest.raises(ValueError):
        cl.clean_settings({"min_submissions": 5, "max_submissions": 2})
    with pytest.raises(ValueError):
        cl.clean_settings({"max_submissions": "abc"})


def test_cap_and_xp_split():
    import campaign_runtime as cr
    # honor mode: each submission auto-verifies. Required 2 pay 10 each, the 3rd pays the extra 4.
    assert cr.create_submission(CID, 0, 501, "u501", "a") == ("verified", 10)
    assert cr.create_submission(CID, 0, 501, "u501", "b") == ("verified", 10)
    assert cr.create_submission(CID, 0, 501, "u501", "c") == ("verified", 4)
    assert cr.create_submission(CID, 0, 501, "u501", "d") == ("limit", 0)       # cap of 3
    assert cr.create_submission(CID, 0, 502, "u502", "a") == ("verified", 10)   # other member unaffected
    assert "2 / 2 required" not in cr.submission_progress(CID, 0, 502)
    assert "1 / 2 required" in cr.submission_progress(CID, 0, 502)


def test_one_per_user_unchanged():
    import campaign_runtime as cr
    assert cr.create_submission(CID_ONE, 0, 601, "u601", "a") == ("verified", 10)
    assert cr.create_submission(CID_ONE, 0, 601, "u601", "b") == ("duplicate", 0)
    assert cr.submission_progress(CID_ONE, 0, 601) == ""
