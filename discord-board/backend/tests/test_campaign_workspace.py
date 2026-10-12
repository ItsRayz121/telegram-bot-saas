"""Campaign workspace endpoints + the review guard (Guildizer).

Run from discord-board/backend:  python -m pytest tests/test_campaign_workspace.py
Throwaway SQLite database and a forged session cookie; nothing is posted to Discord.
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta

_DB = os.path.join(tempfile.mkdtemp(), "ws.db")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB}")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

OWNER, OUTSIDER = 9201, 9202
G, G2 = 9210, 9211
NOW = datetime.utcnow()


@pytest.fixture(scope="module")
def client():
    import app as appmod
    import auth
    from config import Config
    from database import SessionLocal, init_db
    from models import Campaign, CampaignSubmission, CampaignTask, Guild, User, UserGuild
    init_db()
    db = SessionLocal()
    db.add_all([User(id=OWNER, username="reviewer"), User(id=OUTSIDER, username="outsider")])
    db.flush()
    db.add_all([Guild(id=G, name="Main", owner_id=OWNER, plan="free"),
                Guild(id=G2, name="Other", owner_id=OUTSIDER, plan="free")])
    db.flush()
    db.add(UserGuild(user_id=OWNER, guild_id=G, can_manage=True, is_owner=True))
    db.add(UserGuild(user_id=OUTSIDER, guild_id=G2, can_manage=True, is_owner=True))
    a = Campaign(id=9301, guild_id=G, title="Alpha quiz", type="proof_collection", status="active",
                 reward_xp=50, ends_at=NOW + timedelta(hours=5), post_status="posted", max_participants=10,
                 created_at=NOW - timedelta(days=3))
    b = Campaign(id=9302, guild_id=G, title="Beta raid", type="raid", status="active", reward_xp=10,
                 post_status="failed", post_error="missing permission", ends_at=None,
                 created_at=NOW - timedelta(days=2), settings={"auto_verify_x": True})
    c = Campaign(id=9303, guild_id=G, title="Gamma done", type="proof_collection", status="closed",
                 reward_xp=5, post_status="posted", created_at=NOW - timedelta(days=1))
    other = Campaign(id=9399, guild_id=G2, title="Other server", type="proof_collection", status="active",
                     post_status="posted", reward_xp=1)
    db.add_all([a, b, c, other])
    db.flush()
    db.add(CampaignTask(id=9401, campaign_id=9301, order=0, title="Follow us", reward_xp=20))
    db.flush()
    old = NOW - timedelta(hours=60)
    db.add_all([
        # 9301: pending (old, flagged), pending (new), verified (admin), verified same user again, rejected
        CampaignSubmission(id=9501, campaign_id=9301, user_id=1, username="ann", status="pending",
                           created_at=old, flagged=True, flag_reason="same wallet"),
        CampaignSubmission(id=9502, campaign_id=9301, user_id=2, username="bob", status="pending",
                           created_at=NOW - timedelta(hours=1)),
        CampaignSubmission(id=9503, campaign_id=9301, user_id=3, username="cy", status="verified",
                           created_at=NOW - timedelta(hours=30), reviewed_at=NOW - timedelta(hours=28),
                           reviewer_id=OWNER, reviewer_name="reviewer", reward_granted=50, task_id=9401),
        CampaignSubmission(id=9504, campaign_id=9301, user_id=3, username="cy", status="verified",
                           created_at=NOW - timedelta(hours=20), reviewed_at=NOW - timedelta(hours=19),
                           reviewer_id=OWNER, reviewer_name="reviewer", reward_granted=50),
        CampaignSubmission(id=9505, campaign_id=9301, user_id=4, username="di", status="rejected",
                           created_at=NOW - timedelta(hours=10), reviewed_at=NOW - timedelta(hours=9),
                           reviewer_id=OWNER, reviewer_name="reviewer", review_reason="blurry"),
        # 9302: auto-verified by the X check (no reviewer)
        CampaignSubmission(id=9506, campaign_id=9302, user_id=5, username="ed", status="verified",
                           created_at=NOW - timedelta(hours=3), reviewed_at=NOW - timedelta(hours=3),
                           reward_granted=10),
        # another server's submission must never leak
        CampaignSubmission(id=9599, campaign_id=9399, user_id=9, username="zed", status="pending",
                           created_at=NOW - timedelta(hours=100)),
    ])
    db.commit()
    db.close()
    cl = appmod.app.test_client()
    cl.set_cookie(Config.SESSION_COOKIE_NAME, auth._issue_session(OWNER))
    return cl


def url(path):
    return f"/api/guilds/{G}/campaign-workspace/{path}"


# ── access ─────────────────────────────────────────────────────────────────────
def test_requires_login_and_server_access(client):
    import app as appmod
    anon = appmod.app.test_client()
    assert anon.get(url("overview")).status_code == 401
    assert client.get(f"/api/guilds/{G2}/campaign-workspace/overview").status_code == 403


# ── overview ───────────────────────────────────────────────────────────────────
def test_overview_counts_are_honest_and_scoped(client):
    d = client.get(url("overview")).get_json()
    t = d["totals"]
    assert t["pending_review"] == 2                       # the other server's pending is not here
    assert t["approved_submissions"] == 3                 # each submission counts once
    assert t["approved_unique_participants"] == 2         # cy (twice) + ed counted as people once
    assert t["rejected_submissions"] == 1
    assert t["active_campaigns"] == 2 and t["campaigns_total"] == 3
    kinds = {a["kind"] for a in d["attention"]}
    assert {"post_failed", "stale_reviews", "flagged_pending", "ending_soon"} <= kinds
    assert "other" not in str(d).lower() or "Other server" not in str(d)
    assert [r["id"] for r in d["running"]][0] == 9301     # nearest deadline first
    running = {r["id"]: r for r in d["running"]}
    assert running[9301]["progress"]["participants"] == {"done": 1, "target": 10}


def test_overview_series_keeps_submissions_and_decisions_apart(client):
    d = client.get(url("overview?days=7")).get_json()
    assert len(d["series"]) == 7
    assert d["series_totals"]["submitted"] == 6           # by created_at (6 in this server within 7 days)
    assert d["series_totals"]["decisions"] == 4           # by reviewed_at: 3 admin + the X auto row has one too
    assert client.get(url("overview?days=5")).get_json()["days"] == 30    # unsupported ranges fall back


# ── directory ──────────────────────────────────────────────────────────────────
def test_directory_filters_sorts_and_paginates(client):
    d = client.get(url("campaigns")).get_json()
    assert d["total"] == 3 and {c["id"] for c in d["campaigns"]} == {9301, 9302, 9303}
    assert all(c["id"] != 9399 for c in d["campaigns"])
    assert client.get(url("campaigns?q=beta")).get_json()["total"] == 1
    assert client.get(url("campaigns?status=closed")).get_json()["campaigns"][0]["id"] == 9303
    assert client.get(url("campaigns?type=raid")).get_json()["total"] == 1
    asc = [c["id"] for c in client.get(url("campaigns?sort=ends_at&dir=asc")).get_json()["campaigns"]]
    assert asc[0] == 9301 and set(asc[1:]) == {9302, 9303}            # no deadline sorts last
    desc = [c["id"] for c in client.get(url("campaigns?sort=ends_at&dir=desc")).get_json()["campaigns"]]
    assert desc[0] == 9301                                            # still before the no-deadline ones
    by_pending = [c["id"] for c in client.get(url("campaigns?sort=pending&dir=desc")).get_json()["campaigns"]]
    assert by_pending[0] == 9301
    p = client.get(url("campaigns?per_page=2&page=2")).get_json()
    assert len(p["campaigns"]) == 1 and p["pages"] == 2
    c = next(x for x in client.get(url("campaigns")).get_json()["campaigns"] if x["id"] == 9301)
    assert c["counts"] == {"total": 5, "pending": 2, "verified": 2, "rejected": 1}
    assert client.get(url("campaigns?sort=; drop table")).status_code == 200      # unknown sort is ignored


# ── queue ──────────────────────────────────────────────────────────────────────
def test_queue_defaults_to_oldest_pending_first_and_marks_waiting_long(client):
    d = client.get(url("queue")).get_json()
    assert [s["id"] for s in d["submissions"]] == [9501, 9502]
    first = d["submissions"][0]
    assert first["waiting_long"] is True and first["flagged"] is True and first["campaign_title"] == "Alpha quiz"
    assert d["submissions"][1]["waiting_long"] is False
    assert all(s["id"] != 9599 for s in d["submissions"])
    assert [s["id"] for s in client.get(url("queue?sort=newest")).get_json()["submissions"]] == [9502, 9501]


def test_queue_filters(client):
    assert [s["id"] for s in client.get(url("queue?flagged=true")).get_json()["submissions"]] == [9501]
    assert [s["id"] for s in client.get(url("queue?q=bob")).get_json()["submissions"]] == [9502]
    assert [s["id"] for s in client.get(url("queue?q=2")).get_json()["submissions"]] == [9502]       # by user id
    rows = client.get(url("queue?status=verified")).get_json()["submissions"]
    by_id = {r["id"]: r for r in rows}
    assert by_id[9503]["verification_source"] == "admin"
    assert by_id[9506]["verification_source"] == "api"                                              # X auto-verify, no reviewer
    assert client.get(url("queue?campaign_id=9302&status=verified")).get_json()["total"] == 1
    assert client.get(url("queue?campaign_id=9399")).get_json()["total"] == 0                      # other server's campaign
    assert client.get(url("queue?per_page=1&page=2")).get_json()["submissions"][0]["id"] == 9502


# ── one campaign ───────────────────────────────────────────────────────────────
def test_campaign_summary_and_activity(client):
    s = client.get(url("campaigns/9301/summary")).get_json()
    assert s["counts"] == {"total": 5, "pending": 2, "verified": 2, "rejected": 1, "flagged_pending": 1}
    assert s["approved_unique_participants"] == 1 and s["xp_granted"] == 100
    assert s["verification_sources"] == {"admin": 2}
    assert s["by_task"] == [{"task_id": 9401, "title": "Follow us", "submitted": 1, "approved": 1, "pending": 0}]
    assert s["avg_review_hours"] is not None and s["reviewers"][0] == {"name": "reviewer", "decisions": 3}
    assert s["progress"]["participants"] == {"done": 1, "target": 10}
    a = client.get(url("campaigns/9301/activity")).get_json()["events"]
    kinds = {e["kind"] for e in a}
    assert {"submitted", "approved", "rejected"} <= kinds
    assert [e["at"] for e in a] == sorted([e["at"] for e in a], reverse=True)


def test_other_servers_campaign_is_a_404(client):
    assert client.get(url("campaigns/9399/summary")).status_code == 404
    assert client.get(url("campaigns/9399/activity")).status_code == 404


# ── review guard ───────────────────────────────────────────────────────────────
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


def test_guarded_approve_grants_once_and_second_reviewer_gets_409(client):
    before = xp_of(2)
    r = review(client, 9301, 9502, action="approve", expected_status="pending")
    assert r.status_code == 200 and r.get_json()["status"] == "verified"
    assert xp_of(2) == before + 50
    # a second reviewer still looking at "pending" is told it is stale, and nothing happens
    r2 = review(client, 9301, 9502, action="reject", expected_status="pending", reason="late")
    assert r2.status_code == 409
    body = r2.get_json()
    assert body["error"] == "STALE_SUBMISSION" and body["current_status"] == "verified"
    assert xp_of(2) == before + 50
    d = client.get(f"/api/guilds/{G}/campaigns/9301/submissions").get_json()["submissions"]
    row = next(x for x in d if x["id"] == 9502)
    assert row["status"] == "verified" and row["review_reason"] is None


def test_guarded_reject_records_reason_and_queues_the_dm(client):
    r = review(client, 9301, 9501, action="reject", expected_status="pending", reason="duplicate wallet")
    assert r.status_code == 200
    j = r.get_json()
    assert j["status"] == "rejected" and j["review_reason"] == "duplicate wallet" and j["notify_status"] == "pending"
    assert j["reviewed_by"] == "reviewer"
    assert xp_of(1) == 0                                   # rejecting never grants


def test_re_approving_an_already_verified_row_does_not_pay_again(client):
    before = xp_of(3)
    r = review(client, 9301, 9503, action="approve", expected_status="verified")
    assert r.status_code == 200
    assert xp_of(3) == before


def test_invalid_expected_status_and_missing_rows(client):
    assert review(client, 9301, 9503, action="approve", expected_status="bogus").status_code == 400
    assert review(client, 9301, 99999, action="approve", expected_status="pending").status_code == 404
    assert review(client, 9301, 9599, action="approve", expected_status="pending").status_code == 404   # other campaign's row


def test_legacy_callers_without_expected_status_behave_as_before(client):
    r = review(client, 9302, 9506, action="approve")                 # already verified: unchanged semantics
    assert r.status_code == 200 and r.get_json()["status"] == "verified"
    r = review(client, 9301, 9505, action="verify")                  # the old verb still works
    assert r.status_code == 200 and r.get_json()["status"] == "verified"
