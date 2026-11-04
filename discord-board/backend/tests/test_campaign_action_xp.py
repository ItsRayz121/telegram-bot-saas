"""Per-action XP for raids (settings.action_xp): pays only passed actions, exactly once,
tops up later, honours legacy rows and the CAMPAIGN_ACTION_XP_ENABLED kill switch."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from test_campaign_workspace import OWNER, client  # noqa: E402,F401

G = 9212          # its own server so campaign/queue counts in other modules are unaffected

CID = 9701
GOALS = {"likes": 10, "retweets": 10, "follows": 5}
AXP = {"like": 5, "retweet": 10, "follow": 25, "comment": 99}     # comment is not targeted -> ignored


def ok(s):
    return {"status": s}


@pytest.fixture(scope="module", autouse=True)
def seed(client):
    from database import SessionLocal
    from models import Campaign, CampaignSubmission, Guild, UserGuild
    db = SessionLocal()
    db.add(Guild(id=G, name="XP server", owner_id=OWNER, plan="free"))
    db.flush()
    db.add(UserGuild(user_id=OWNER, guild_id=G, can_manage=True, is_owner=True))
    db.add(Campaign(id=CID, guild_id=G, title="XP raid", type="raid", status="active", reward_xp=50,
                    post_status="posted", settings={"raid_goals": GOALS, "action_xp": AXP}))
    db.flush()
    rows = [
        # 9801: like + retweet passed, follow failed      -> 15 now
        (9801, 801, {"like": ok("verified"), "retweet": ok("verified"), "follow": ok("failed")}, 0, False),
        # 9802: nothing passed                             -> 0
        (9802, 802, {"like": ok("failed"), "retweet": ok("failed"), "follow": ok("failed")}, 0, False),
        # 9803: legacy, already paid the flat 50 before per-action tracking existed -> 0
        (9803, 803, {"like": ok("verified")}, 50, True),
        # 9804: manual actions (admin accepts by approving) -> 5 + 10 + 25
        (9804, 804, {"like": ok("manual"), "retweet": ok("manual"), "follow": ok("manual")}, 0, False),
        (9805, 805, {"like": ok("verified"), "retweet": ok("verified"), "follow": ok("verified")}, 0, False),
    ]
    for sid, uid, acts, granted, legacy in rows:
        db.add(CampaignSubmission(id=sid, campaign_id=CID, user_id=uid, username=f"u{uid}",
                                  status="verified" if legacy else "pending", proof={"actions": acts},
                                  reward_granted=granted))
    db.commit()
    db.close()
    SessionLocal.remove()


def review(client, cid, sid, **body):
    return client.post(f"/api/guilds/{G}/campaigns/{cid}/submissions/{sid}/review", json=body)


def xp_of(user_id):
    from database import SessionLocal
    from models import Member
    db = SessionLocal()
    try:
        m = db.get(Member, {"guild_id": G, "user_id": user_id})
        return (m.xp or 0) if m else 0
    finally:
        db.close()
        SessionLocal.remove()


def approve(client, sid, expected="pending"):
    r = review(client, CID, sid, action="approve", expected_status=expected)
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def proof_of(sid):
    from database import SessionLocal
    from models import CampaignSubmission
    db = SessionLocal()
    try:
        return dict(db.get(CampaignSubmission, sid).proof or {})
    finally:
        db.close()
        SessionLocal.remove()


def set_actions(sid, acts):
    from database import SessionLocal
    from models import CampaignSubmission
    from sqlalchemy.orm.attributes import flag_modified
    db = SessionLocal()
    s = db.get(CampaignSubmission, sid)
    p = dict(s.proof or {})
    p["actions"] = acts
    s.proof = p
    flag_modified(s, "proof")
    db.commit()
    db.close()
    SessionLocal.remove()


def test_only_passed_actions_are_paid_and_recorded(client):
    j = approve(client, 9801)
    assert j["reward_granted"] == 15 and xp_of(801) == 15
    assert proof_of(9801)["xp_awarded"] == {"like": 5, "retweet": 10}


def test_approving_again_never_pays_twice(client):
    approve(client, 9801, expected="verified")
    approve(client, 9801, expected="verified")
    assert xp_of(801) == 15


def test_top_up_pays_only_the_newly_passed_action(client):
    set_actions(9801, {"like": ok("verified"), "retweet": ok("verified"), "follow": ok("verified")})
    approve(client, 9801, expected="verified")
    assert xp_of(801) == 40 and proof_of(9801)["xp_awarded"]["follow"] == 25
    approve(client, 9801, expected="verified")
    assert xp_of(801) == 40


def test_nothing_passed_pays_nothing(client):
    j = approve(client, 9802)
    assert j["status"] == "verified" and xp_of(802) == 0 and "xp_awarded" not in proof_of(9802)


def test_legacy_flat_paid_row_is_not_paid_again(client):
    approve(client, 9803, expected="verified")
    assert xp_of(803) == 0


def test_manual_actions_are_paid_when_admin_approves(client):
    approve(client, 9804)
    assert xp_of(804) == 40


def test_workspace_reports_effective_xp(client):
    s = client.get(f"/api/guilds/{G}/campaign-workspace/campaigns/{CID}/summary").get_json()
    assert s["rewards"]["xp_per_approval"] == 40 and s["rewards"]["action_xp"] == {"like": 5, "retweet": 10, "follow": 25}


def test_kill_switch_falls_back_to_flat_reward(client, monkeypatch):
    monkeypatch.setenv("CAMPAIGN_ACTION_XP_ENABLED", "0")
    j = approve(client, 9805)
    assert j["reward_granted"] == 50 and xp_of(805) == 50
    s = client.get(f"/api/guilds/{G}/campaign-workspace/campaigns/{CID}/summary").get_json()
    assert s["rewards"]["xp_per_approval"] == 50


def test_pay_action_xp_is_idempotent_for_the_bot_path(client):
    """The bot's verify flow calls pay_action_xp directly; a double tap must not double-pay."""
    import campaign_rewards as cr
    from database import SessionLocal
    from models import Campaign, CampaignSubmission
    db = SessionLocal()
    try:
        c = db.get(Campaign, CID)
        s = CampaignSubmission(campaign_id=CID, user_id=810, username="u810", status="verified",
                               proof={"actions": {"like": ok("verified"), "retweet": ok("verified")}})
        db.add(s)
        db.flush()
        assert cr.pay_action_xp(db, c, s, 810, "u810") == 15
        assert cr.pay_action_xp(db, c, s, 810, "u810") == 0
        db.commit()
        assert cr.effective_reward(c) == 40
    finally:
        db.close()
        SessionLocal.remove()
    assert xp_of(810) == 15


def test_bot_panel_top_up_after_admin_approval(client):
    """Admin approved a raid with manual actions; the member later passes the like in the panel:
    only the like is paid, and tapping Verify again pays nothing more."""
    from datetime import datetime, timedelta
    import campaign_runtime as rt
    from database import SessionLocal
    from models import CampaignSubmission
    db = SessionLocal()
    db.add(CampaignSubmission(
        id=9820, campaign_id=CID, user_id=820, username="u820", status="verified", reward_granted=35,
        proof={"actions": {"retweet": ok("manual"), "follow": ok("manual"),
                           "like": {"opened_at": (datetime.utcnow() - timedelta(hours=1)).isoformat()}},
               "xp_awarded": {"retweet": 10, "follow": 25}}))
    db.commit()
    db.close()
    SessionLocal.remove()
    r = rt.verify_user_action(CID, 820, "u820", "like", None)
    assert r["status"] == "verified"
    assert xp_of(820) == 5 and proof_of(9820)["xp_awarded"] == {"retweet": 10, "follow": 25, "like": 5}
    rt.verify_user_action(CID, 820, "u820", "like", None)
    assert xp_of(820) == 5
