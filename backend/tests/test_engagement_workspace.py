"""Tests for the campaign workspace endpoints, the review guard and the CSV export.

Run from the repo root:  python -m pytest backend/tests/test_engagement_workspace.py
"""
import os
from datetime import datetime, timedelta

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-with-enough-length-1234")
os.environ.setdefault("ENCRYPTION_KEY", "Zm9vYmFyYmF6cXV4Zm9vYmFyYmF6cXV4Zm9vYmFyYmE=")
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from backend.models import (
    db, User, TelegramGroup, OfficialMember, EngagementCampaign, EngagementSubmission,
)
import backend.assistant.hub_models  # noqa: F401
from backend.routes.engagement_workspace import workspace_official_bp, workspace_custom_bp
from backend.routes.telegram_groups import tg_groups_bp
from backend.routes.settings import settings_bp
from backend import engagement as eng


@pytest.fixture()
def env():
    app = Flask(__name__)
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite://", JWT_SECRET_KEY=os.environ["JWT_SECRET_KEY"],
        JWT_TOKEN_LOCATION=["headers"], TESTING=True, SECRET_KEY="x",
        SQLALCHEMY_ENGINE_OPTIONS={"connect_args": {"check_same_thread": False}},
    )
    db.init_app(app)
    JWTManager(app)
    for bp in (workspace_official_bp, workspace_custom_bp, tg_groups_bp, settings_bp):
        app.register_blueprint(bp)
    with app.app_context():
        db.create_all()
        owner = User(email="o@x.io", full_name="Owner", auth_provider="email")
        other = User(email="x@x.io", full_name="Stranger", auth_provider="email")
        db.session.add_all([owner, other])
        db.session.flush()
        ga = TelegramGroup(telegram_group_id="-100A", title="RupChain Community", owner_user_id=owner.id, bot_status="active")
        gb = TelegramGroup(telegram_group_id="-100B", title="CWF Discussion", owner_user_id=other.id, bot_status="active")
        db.session.add_all([ga, gb])
        db.session.flush()
        now = datetime.utcnow()

        def camp(group, title, status="active", ends=None, **kw):
            c = EngagementCampaign(telegram_group_id=group, owner_user_id=owner.id, type=kw.pop("type", "proof_collection"),
                                   title=title, status=status, ends_at=ends, settings=kw.pop("settings", {}), **kw)
            db.session.add(c)
            db.session.flush()
            return c

        c1 = camp("-100A", "Wallet drop", ends=now + timedelta(hours=5), max_participants=10, post_status="posted")
        c2 = camp("-100A", "Raid the tweet", type="raid", post_status="failed", post_error="bot lacks rights",
                  settings={"raid_goals": {"retweets": 5}})
        c3 = camp("-100A", "Old closed one", status="closed")
        cx = camp("-100B", "Other group campaign")

        def sub(c, uid, status, hours_ago=1, **kw):
            s = EngagementSubmission(campaign_id=c.id, telegram_user_id=uid, telegram_username=kw.pop("username", None),
                                     scope="official", status=status, payload=kw.pop("payload", {"wallet": "0xabc"}),
                                     created_at=now - timedelta(hours=hours_ago), **kw)
            db.session.add(s)
            db.session.flush()
            return s

        sub(c1, "0001", "pending", hours_ago=60, username="=cmd|calc")      # stale + formula-injection name
        sub(c1, "0002", "pending", hours_ago=2)
        sub(c1, "0003", "verified", hours_ago=30, reviewed_by=str(owner.id), reviewed_at=now - timedelta(hours=29))
        sub(c1, "0003", "verified", hours_ago=5, payload={"wallet": "0xdef"})      # same person approved twice -> 1 unique
        sub(c2, "0004", "rejected", hours_ago=10, reviewed_by=str(owner.id), reviewed_at=now - timedelta(hours=9))
        sub(c2, "0005", "verified", hours_ago=3, payload={"actions": {"retweet": {"status": "verified"}}})
        sub(c3, "0006", "pending", hours_ago=100)                                   # closed campaign stays reviewable
        sub(cx, "0099", "pending", hours_ago=1)                                      # other group: must never leak
        db.session.commit()
        ids = dict(owner=owner.id, other=other.id, c1=c1.id, c2=c2.id, c3=c3.id, cx=cx.id)
    client = app.test_client()
    with app.app_context():
        h = {"Authorization": "Bearer " + create_access_token(identity=str(ids["owner"]))}
        ho = {"Authorization": "Bearer " + create_access_token(identity=str(ids["other"]))}
    yield client, h, ho, ids, app


def get(client, h, url):
    r = client.get(url, headers=h)
    return r.status_code, r.get_json()


B = "/api/telegram-groups/-100A/engagement"


def test_group_boundary(env):
    client, h, ho, ids, _ = env
    for path in ("overview", "campaigns", "queue", f"campaigns/{ids['c1']}/summary", f"campaigns/{ids['c1']}/activity"):
        assert client.get(f"{B}/{path}", headers=ho).status_code == 404            # not their group
        assert client.get(f"/api/telegram-groups/-100B/engagement/{path}", headers=h).status_code == 404
    assert client.get(f"{B}/overview").status_code == 401
    # a campaign id from the other group is not reachable through this group
    assert client.get(f"{B}/campaigns/{ids['cx']}/summary", headers=h).status_code == 404
    code, q = get(client, h, f"{B}/queue?status=all&per_page=100")
    assert all(i["telegram_user_id"] != "0099" for i in q["items"])
    assert all(c["title"] != "Other group campaign" for c in q["campaigns"])


def test_overview_counts_and_attention(env):
    client, h, _, ids, _ = env
    code, o = get(client, h, f"{B}/overview?days=30")
    t = o["totals"]
    assert t["active_campaigns"] == 2 and t["campaigns_total"] == 3
    assert t["pending_review"] == 3                       # includes the closed campaign's pending item
    assert t["approved_submissions"] == 3                 # submissions, each counted once ...
    assert t["approved_unique_participants"] == 2         # ... people deduplicated separately (0003 twice)
    kinds = {a["kind"] for a in o["attention"]}
    assert {"post_failed", "stale_reviews", "ending_soon"} <= kinds
    stale = next(a for a in o["attention"] if a["kind"] == "stale_reviews")
    assert stale["count"] == 2                            # 60h and 100h old, over the 48h threshold
    assert sum(p["submitted"] for p in o["series"]) == 7 and sum(p["decisions"] for p in o["series"]) == 2
    row = next(r for r in o["running"] if r["title"] == "Wallet drop")
    assert row["progress"]["participants"] == {"done": 1, "target": 10}   # unique approved people vs participant target
    raid = next(r for r in o["running"] if r["title"] == "Raid the tweet")
    assert raid["progress"]["actions"] == [{"goal": "retweets", "action": "retweet", "done": 1, "target": 5}]
    assert "participants" not in raid["progress"]                         # no participant target -> no fake bar


def test_directory_filters_sort_and_pagination(env):
    client, h, *_ = env
    code, d = get(client, h, f"{B}/campaigns?per_page=2&sort=pending&dir=desc")
    assert d["total"] == 3 and d["pages"] == 2 and len(d["campaigns"]) == 2
    assert d["campaigns"][0]["title"] == "Wallet drop" and d["campaigns"][0]["pending"] == 2
    assert d["campaigns"][0]["submitted"] == 4 and d["campaigns"][0]["approved"] == 2
    code, d = get(client, h, f"{B}/campaigns?status=closed")
    assert [c["title"] for c in d["campaigns"]] == ["Old closed one"]
    code, d = get(client, h, f"{B}/campaigns?q=raid&type=raid")
    assert [c["title"] for c in d["campaigns"]] == ["Raid the tweet"]
    assert d["status_counts"] == {"active": 2, "closed": 1}


def test_queue_filters_and_labels(env):
    client, h, _, ids, _ = env
    code, q = get(client, h, f"{B}/queue")
    assert q["total"] == 3 and q["pending_total"] == 3
    assert [i["telegram_user_id"] for i in q["items"]] == ["0006", "0001", "0002"]   # oldest first
    assert all("file_id" not in i for i in q["items"])
    closed = q["items"][0]
    assert closed["campaign_status"] == "closed"                                     # still reviewable
    code, q = get(client, h, f"{B}/queue?campaign_id={ids['c1']}&status=verified")
    assert {i["verification_source"] for i in q["items"]} == {"admin", "automatic"}
    code, q = get(client, h, f"{B}/queue?q=0002")
    assert q["total"] == 1


def test_stale_review_is_refused_and_does_not_double_reward(env):
    client, h, _, ids, app = env
    with app.app_context():
        pend = EngagementSubmission.query.filter_by(campaign_id=ids["c1"], telegram_user_id="0002").first().id
    url = f"/api/telegram-groups/-100A/campaigns/{ids['c1']}/submissions/{pend}/review"
    r1 = client.post(url, headers=h, json={"action": "approve", "expected_status": "pending"})
    assert r1.status_code == 200 and r1.get_json()["submission"]["status"] == "verified"
    # a second admin (or a retry) still holding the old "pending" view is refused
    r2 = client.post(url, headers=h, json={"action": "reject", "reason": "late", "expected_status": "pending"})
    assert r2.status_code == 409 and r2.get_json()["code"] == "STALE_SUBMISSION"
    with app.app_context():
        s = EngagementSubmission.query.get(pend)
        assert s.status == "verified" and s.review_reason is None          # unchanged by the loser
    # without expected_status the legacy behaviour is untouched
    r3 = client.post(url, headers=h, json={"action": "reject", "reason": "changed my mind"})
    assert r3.status_code == 200


def test_cannot_review_another_groups_submission(env):
    client, h, _, ids, app = env
    with app.app_context():
        sid = EngagementSubmission.query.filter_by(campaign_id=ids["cx"]).first().id
    r = client.post(f"/api/telegram-groups/-100A/campaigns/{ids['cx']}/submissions/{sid}/review",
                    headers=h, json={"action": "approve", "expected_status": "pending"})
    assert r.status_code == 404
    with app.app_context():
        assert EngagementSubmission.query.get(sid).status == "pending"


def test_csv_export_is_safe_filtered_and_named(env):
    client, h, _, ids, _ = env
    r = client.get(f"/api/telegram-groups/-100A/campaigns/{ids['c1']}/submissions/export?status=pending", headers=h)
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert body.startswith("﻿")
    assert "'=cmd|calc" in body and ",=cmd|calc" not in body                 # formula neutralised
    assert '=""0001""' in body and '=""0002""' in body                        # ids written as text: leading zeros kept
    assert "0003" not in body                                                 # filter honoured (verified rows excluded)
    cd = r.headers["Content-Disposition"]
    assert "rupchain-community_wallet-drop_submissions_pending_" in cd and cd.endswith(".csv")
    r = client.get(f"/api/telegram-groups/-100A/campaigns/{ids['c1']}/submissions/export", headers=h)
    assert r.get_data(as_text=True).count("\n") >= 5                          # all rows when unfiltered


def test_preview_uses_real_message_builder_and_writes_nothing(env):
    client, h, _, ids, app = env
    before = None
    with app.app_context():
        before = (EngagementCampaign.query.count(), EngagementSubmission.query.count())
    r = client.post(f"{B}/preview", headers=h, json={
        "type": "raid", "title": "Raid <now>", "task_url": "https://x.com/a/status/1", "duration_hours": 24,
        "reward_xp": 25, "reward_label": "NFT", "settings": {"raid_goals": {"likes": 50, "retweets": 20}},
    })
    assert r.status_code == 200
    d = r.get_json()
    assert "Raid &lt;now&gt;" in d["html"] and "Goals" in d["html"] and "0/50 Likes" in d["html"]
    assert "XP:</b> 25" in d["html"] and any(b["text"] == "🔁 Join Raid" for row in d["buttons"] for b in row)
    with app.app_context():
        assert (EngagementCampaign.query.count(), EngagementSubmission.query.count()) == before


def test_campaign_summary_and_activity(env):
    client, h, _, ids, _ = env
    code, s = get(client, h, f"{B}/campaigns/{ids['c1']}/summary")
    assert s["counts"] == {"submitted": 4, "pending": 2, "approved": 2, "rejected": 0, "flagged": 0}
    assert s["people"] == {"submitted_unique": 3, "approved_unique": 1}
    assert s["verification_sources"] == {"admin": 1, "automatic": 1}
    assert s["oldest_pending_hours"] >= 59
    code, a = get(client, h, f"{B}/campaigns/{ids['c1']}/activity")
    kinds = [e["kind"] for e in a["events"]]
    assert kinds.count("submitted") == 4 and kinds.count("approved") == 1
