"""When a campaign ends: new submissions stop, the announcement switches to its ended form, and
"My submission" stays. Covers the closing job selection, the post edit, and the button.

Run from discord-board/backend:  python -m pytest tests/test_campaign_ended.py
"""
import asyncio
import os
import sys
import tempfile
from datetime import datetime, timedelta

_DB = os.path.join(tempfile.mkdtemp(), "end.db")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB}")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

G = 9750


@pytest.fixture(autouse=True)
def world():
    from database import SessionLocal, init_db
    from models import Campaign, CampaignSubmission, CampaignTask, Guild
    init_db()
    db = SessionLocal()
    if db.get(Guild, G) is None:
        db.add(Guild(id=G, name="G", owner_id=1, plan="pro"))
    db.commit()
    db.close()
    yield
    db = SessionLocal()
    ids = [c.id for c in db.query(Campaign).filter(Campaign.guild_id == G).all()]
    db.query(CampaignSubmission).filter(CampaignSubmission.campaign_id.in_(ids)).delete(synchronize_session=False)
    db.query(CampaignTask).filter(CampaignTask.campaign_id.in_(ids)).delete(synchronize_session=False)
    db.query(Campaign).filter(Campaign.guild_id == G).delete(synchronize_session=False)
    db.commit()
    db.close()
    SessionLocal.remove()


def _campaign(ends_in_h=-1, status="active", posted_days_ago=0, settings=None, tasks=0):
    from database import SessionLocal
    from models import Campaign, CampaignTask
    db = SessionLocal()
    c = Campaign(guild_id=G, type="proof_collection", title="Tasks", status=status, channel_id=555, message_id=777,
                 post_status="posted", posted_at=datetime.utcnow() - timedelta(days=posted_days_ago),
                 ends_at=datetime.utcnow() + timedelta(hours=ends_in_h), settings=settings or {})
    db.add(c)
    db.flush()
    for i in range(tasks):
        db.add(CampaignTask(campaign_id=c.id, order=i, title=f"Task {i + 1}", reward_xp=5))
    db.commit()
    cid = c.id
    db.close()
    SessionLocal.remove()
    return cid


def _status(cid):
    from database import SessionLocal
    from models import Campaign
    db = SessionLocal()
    c = db.get(Campaign, cid)
    out = (c.status, bool((c.settings or {}).get("_post_closed")))
    db.close()
    SessionLocal.remove()
    return out


def test_the_closing_job_picks_expired_and_recently_closed_posts_only():
    import campaign_runtime as rt
    expired = _campaign(ends_in_h=-1)
    running = _campaign(ends_in_h=5)
    closed_recent = _campaign(ends_in_h=-30, status="closed", posted_days_ago=2)
    closed_old = _campaign(ends_in_h=-30 * 24, status="closed", posted_days_ago=90)         # never swept
    done = _campaign(ends_in_h=-3, status="closed", posted_days_ago=1, settings={"_post_closed": True})
    got = {cid for cid, _g in rt.campaigns_to_close()}
    assert got == {expired, closed_recent}
    assert running not in got and closed_old not in got and done not in got
    rt.mark_closed(expired, flag_post=True)
    assert _status(expired) == ("closed", True) and _status(running) == ("active", False)
    assert expired not in {cid for cid, _g in rt.campaigns_to_close()}


def test_ended_campaigns_refuse_new_submissions_but_keep_my_submission():
    import campaign_runtime as rt
    cid = _campaign(ends_in_h=-1, tasks=2)
    assert rt.submit_context(cid, 0) is None                           # the button's context: closed
    assert rt.create_submission(cid, 0, 11, "u11", "proof") == ("closed", 0)
    info = rt.my_submissions(cid, 11)
    assert info["open"] is False and info["lines"] == ["⬜ Task 1: not done", "⬜ Task 2: not done"]


def test_my_submission_lists_each_task_with_its_status():
    import campaign_runtime as rt
    from database import SessionLocal
    from models import CampaignSubmission, CampaignTask
    cid = _campaign(ends_in_h=5, tasks=3)
    db = SessionLocal()
    t = db.query(CampaignTask).filter(CampaignTask.campaign_id == cid).order_by(CampaignTask.order).all()
    db.add_all([CampaignSubmission(campaign_id=cid, task_id=t[0].id, user_id=12, username="u", status="verified", reward_granted=5, proof={}),
                CampaignSubmission(campaign_id=cid, task_id=t[1].id, user_id=12, username="u", status="pending", proof={})])
    db.commit()
    db.close()
    lines = rt.my_submissions(cid, 12)["lines"]
    assert lines == ["✅ Task 1: verified (+5 XP)", "🕓 Task 2: waiting for review", "⬜ Task 3: not done"]
    assert rt.my_submissions(cid, 99)["lines"] == ["⬜ Task 1: not done", "⬜ Task 2: not done", "⬜ Task 3: not done"]


def _labels(view):
    return [getattr(i, "item", i).label for i in view.children]


def test_the_ended_post_has_only_my_submission_and_a_live_post_has_it_too():
    import campaign_runtime as rt
    import campaign_views as cv
    live = _campaign(ends_in_h=5, tasks=2)
    ended = _campaign(ends_in_h=-1, tasks=2)

    async def build(cid):
        data = rt.load_for_post(cid)
        return _labels(cv.build_view(data))
    assert "📋 My submission" in asyncio.run(build(live)) and len(asyncio.run(build(live))) == 3
    assert asyncio.run(build(ended)) == ["📋 My submission"]
    full = _campaign(ends_in_h=5, tasks=25)
    assert len(asyncio.run(build(full))) == 25                         # Discord's limit is respected


def test_close_post_edits_in_place_and_flags_it():
    import campaign_runtime as rt
    import campaign_views as cv
    cid = _campaign(ends_in_h=-1, tasks=2)
    seen = {}

    class Msg:
        async def edit(self, embed=None, view=None):
            seen["footer"], seen["buttons"] = embed.footer.text, _labels(view)

        async def unpin(self):
            seen["unpinned"] = True

    class Chan:
        async def fetch_message(self, mid):
            seen["fetched"] = mid
            return Msg()

    class Bot:
        user = type("U", (), {"name": "Guildizer"})()

        def get_guild(self, gid):
            return object()

        def get_channel(self, chid):
            return Chan()
    assert asyncio.run(cv.close_post(Bot(), cid)) is True
    assert seen["fetched"] == 777 and "has ended" in seen["footer"] and seen["buttons"] == ["📋 My submission"]
    assert _status(cid) == ("closed", True)
    assert rt.campaigns_to_close() == []                               # handled once, not edited again

    class OtherBot(Bot):
        def get_guild(self, gid):
            return None
    other = _campaign(ends_in_h=-1)
    assert asyncio.run(cv.close_post(OtherBot(), other)) is False      # another bot serves that server: untouched
    assert _status(other) == ("active", False)


def test_the_my_submission_button_answers_privately():
    import campaign_views as cv
    cid = _campaign(ends_in_h=-1, tasks=1)
    sent = {}

    class Resp:
        async def send_message(self, text, ephemeral=False):
            sent["text"], sent["ephemeral"] = text, ephemeral

    class Inter:
        user = type("U", (), {"id": 31})()
        response = Resp()

    async def go():
        await cv.MySubmissionButton(cid).callback(Inter())
    asyncio.run(go())
    assert sent["ephemeral"] and "(ended)" in sent["text"] and "Task 1: not done" in sent["text"]
