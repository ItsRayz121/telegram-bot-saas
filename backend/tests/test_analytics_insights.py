"""Tests for the Analytics insight endpoints (members / audit / warnings / digest).

Run from the repo root:  python -m pytest backend/tests/test_analytics_insights.py

Uses an in-memory SQLite database and a tiny Flask app that mounts only the
blueprints under test - no Telegram, no scheduler, no AI provider.
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
    db, User, TelegramGroup, OfficialMember, OfficialWarning, BotEvent,
    Bot, Group, Member, AuditLog, XpEvent, AIActivity,
)
from backend.routes.analytics_insights import insights_official_bp, insights_custom_bp
from backend.routes.telegram_groups import tg_groups_bp
from backend.routes.settings import settings_bp
import backend.assistant.hub_models  # noqa: F401  (registers hub tables referenced by FKs)


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
    for bp in (insights_official_bp, insights_custom_bp, tg_groups_bp, settings_bp):
        app.register_blueprint(bp)
    with app.app_context():
        db.create_all()
        owner = User(email="o@x.io", full_name="Owner", auth_provider="email")
        other = User(email="x@x.io", full_name="Stranger", auth_provider="email")
        db.session.add_all([owner, other])
        db.session.flush()

        now = datetime.utcnow()
        # official group A (owned) and group B (someone else's)
        ga = TelegramGroup(telegram_group_id="-100A", title="Group A", owner_user_id=owner.id, bot_status="active")
        gb = TelegramGroup(telegram_group_id="-100B", title="Group B", owner_user_id=other.id, bot_status="active")
        db.session.add_all([ga, gb])
        db.session.flush()
        mem = {}
        for uid, name, xp, joined in [("1", "Ann", 500, 3), ("2", "Bob", 300, 40), ("3", "Cy", 300, 1), ("4", "Di", 0, 2)]:
            m = OfficialMember(telegram_group_id="-100A", telegram_user_id=uid, username=name.lower(),
                               first_name=name, xp=xp, level=1, joined_at=now - timedelta(days=joined),
                               last_message_at=now - timedelta(days=joined if joined < 10 else 20))
            db.session.add(m)
            mem[uid] = m
        db.session.add(OfficialMember(telegram_group_id="-100B", telegram_user_id="9", username="secret",
                                      first_name="Secret", xp=999, level=1))
        db.session.flush()
        # XP ledger: Ann +40 an hour ago, Cy +10 three days ago
        db.session.add_all([
            XpEvent(scope="official", member_id=mem["1"].id, amount=40, reason="message", created_at=now - timedelta(hours=1)),
            XpEvent(scope="official", member_id=mem["3"].id, amount=10, reason="message", created_at=now - timedelta(days=3)),
        ])

        def warn(uid, reason, mod="mod1", active=True, days=1, group="-100A"):
            db.session.add(OfficialWarning(telegram_group_id=group, target_user_id=uid, target_username=None,
                                           moderator_user_id="77", moderator_username=mod, reason=reason,
                                           active=active, created_at=now - timedelta(days=days)))

        warn("2", "spam link t.me/abc")
        warn("2", "spam link t.me/abc", days=2)
        warn("2", "bad word", mod="AutoMod", days=3)
        warn("2", "old", active=False, days=5)
        warn("1", "off-topic message")
        warn("9", "should never be visible", group="-100B")

        # audit events: user 2 got 3 identical automod purges (rule "link") and a ban
        for i in range(3):
            db.session.add(BotEvent(
                telegram_group_id="-100A", event_type="automod_action", message="User 2: link -> warn",
                metadata_={"target_user_id": "2", "target_username": "bob", "moderator_username": "AutoMod",
                           "rule": "link", "action": "warn", "message_text": f"msg {i}"},
                created_at=now - timedelta(hours=i + 1)))
        db.session.add(BotEvent(
            telegram_group_id="-100A", event_type="mod_ban", message="x",
            metadata_={"target_user_id": "2", "moderator_username": "Owner", "moderator_id": "5", "reason": "repeat"},
            created_at=now - timedelta(minutes=5)))
        db.session.add(BotEvent(
            telegram_group_id="-100A", event_type="mod_warn", message="x",
            metadata_={"target_user_id": "1", "moderator_id": "5", "reason": "off topic"},
            created_at=now - timedelta(days=2)))
        db.session.add(BotEvent(telegram_group_id="-100B", event_type="mod_ban", message="x",
                                metadata_={"target_user_id": "9"}, created_at=now))

        # custom-bot group
        bot = Bot(user_id=owner.id, bot_token="enc", bot_token_hash="h1", bot_username="mybot")
        db.session.add(bot)
        db.session.flush()
        cg = Group(bot_id=bot.id, telegram_group_id="-200C", group_name="Custom C", settings={})
        db.session.add(cg)
        db.session.flush()
        db.session.add(Member(group_id=cg.id, telegram_user_id="7", username="zed", first_name="Zed", xp=50, level=1))
        for i in range(2):
            db.session.add(AuditLog(group_id=cg.id, action_type="warn", target_user_id="7", target_username="zed",
                                    moderator_id="5", moderator_username="Owner", reason="spam",
                                    timestamp=now - timedelta(hours=i + 1)))
        db.session.add(AuditLog(group_id=cg.id, action_type="automod_delete", target_user_id="7", target_username="zed",
                                moderator_id="automod", moderator_username="AutoMod", reason="link", timestamp=now))
        for st in ("ok", "ok", "failed", "skipped"):
            db.session.add(AIActivity(scope="official", group_ref="-100A", category="knowledge", action="a",
                                      status=st, created_at=now - timedelta(hours=1)))
        db.session.commit()
        ids = dict(owner=owner.id, other=other.id, bot=bot.id, cg=cg.id)
    client = app.test_client()
    with app.app_context():
        hdr = {"Authorization": "Bearer " + create_access_token(identity=str(ids["owner"]))}
        hdr_other = {"Authorization": "Bearer " + create_access_token(identity=str(ids["other"]))}
    yield client, hdr, hdr_other, ids, app


def get(client, hdr, url):
    r = client.get(url, headers=hdr)
    return r.status_code, r.get_json()


def test_group_boundary_is_enforced(env):
    client, hdr, hdr_other, ids, _ = env
    for kind in ("members", "audit-summary", "audit-groups", "warnings-summary", "warnings-members",
                 "ai-overview", "digest-preview", "member/2"):
        # the stranger cannot read group A, the owner cannot read group B
        assert client.get(f"/api/telegram-groups/-100A/insights/{kind}", headers=hdr_other).status_code == 404
        assert client.get(f"/api/telegram-groups/-100B/insights/{kind}", headers=hdr).status_code == 404
    assert client.get("/api/telegram-groups/-100A/insights/members").status_code == 401


def test_members_summary_covers_whole_group(env):
    client, hdr, *_ = env
    code, d = get(client, hdr, "/api/telegram-groups/-100A/insights/members?period=7d")
    assert code == 200
    assert d["total_members"] == 4                      # group B's member is excluded
    assert d["new_members"] == 3                        # joined within 7d: Ann(3), Cy(1), Di(2)
    assert d["members_with_active_warnings"] == 2       # users 1 and 2
    assert d["members_with_multiple_warnings"] == 1     # only user 2 (3 active)
    assert d["repeat_warned"][0]["user_id"] == "2" and d["repeat_warned"][0]["warnings"] == 3
    assert d["top_contributors"][0]["user_id"] == "1" and d["top_contributors"][0]["xp"] == 40
    code, d = get(client, hdr, "/api/telegram-groups/-100A/insights/members?period=all")
    assert d["new_members"] is None and d["active_members"] is None   # unknown, not zero


def test_audit_groups_reconcile_with_events(env):
    client, hdr, *_ = env
    code, s = get(client, hdr, "/api/telegram-groups/-100A/insights/audit-summary?days=30")
    code, g = get(client, hdr, "/api/telegram-groups/-100A/insights/audit-groups?days=30")
    assert s["total_actions"] == 5 == g["total_events"]
    assert sum(x["count"] for x in g["groups"]) == s["total_actions"]
    assert s["unique_members"] == 2 and s["automatic"] == 3 and s["manual"] == 2
    top = g["groups"][0]
    assert top["user_id"] == "2" and top["action"] == "purge" and top["count"] == 3
    assert top["reason_label"] == "link" and len(top["events"]) == 3
    # "show all" returns exactly `count` events for that group
    code, ev = get(client, hdr, "/api/telegram-groups/-100A/insights/audit-group-events?days=30&user_id=2&action=purge&label=link")
    assert ev["total"] == top["count"]
    # the /warn command (mod_warn) must be visible in the log now
    assert any(x["action"] == "warn" and x["user_id"] == "1" for x in g["groups"])
    code, rep = get(client, hdr, "/api/telegram-groups/-100A/insights/audit-groups?days=30&min_count=2")
    assert [x["count"] for x in rep["groups"]] == [3]


def test_warning_counts_are_consistent(env):
    client, hdr, *_ = env
    code, s = get(client, hdr, "/api/telegram-groups/-100A/insights/warnings-summary?days=30")
    assert s["active_records"] == 4 and s["members_with_active"] == 2 and s["members_with_multiple"] == 1
    assert s["issued_in_period"] == 5 and s["removed_in_period"] == 1     # includes the removed one
    code, m = get(client, hdr, "/api/telegram-groups/-100A/insights/warnings-members")
    assert sum(x["active_warnings"] for x in m["members"]) == s["active_records"]
    assert m["total"] == s["members_with_active"]
    code, m2 = get(client, hdr, "/api/telegram-groups/-100A/insights/warnings-members?min_count=2")
    assert [x["user_id"] for x in m2["members"]] == ["2"]
    assert sum(r["count"] for r in s["by_reason"]) == s["active_records"]
    # the existing list endpoint reports the same active total
    code, lst = get(client, hdr, "/api/telegram-groups/-100A/warnings")
    assert lst["active_total"] == s["active_records"]


def test_member_context_and_isolation(env):
    client, hdr, *_ = env
    code, c = get(client, hdr, "/api/telegram-groups/-100A/insights/member/2")
    assert c["in_group"] and c["active_warnings"] == 3 and len(c["warnings"]) == 4
    assert c["moderation_event_total"] == 4
    code, c = get(client, hdr, "/api/telegram-groups/-100A/insights/member/9")   # belongs to group B
    assert c["in_group"] is False and c["warnings"] == [] and c["moderation_events"] == []


def test_leaderboard_is_stable_and_labelled(env):
    client, hdr, *_ = env
    code, d = get(client, hdr, "/api/telegram-groups/-100A/leaderboard?limit=50")
    ids = [m["telegram_user_id"] for m in d["members"]]
    assert ids[0] == "1" and ids[1:3] == ["2", "3"]          # equal XP: stable by id
    assert d["total_ranked"] == 4 and d["members"][0]["xp_week_ledger"] == 40
    code, d = get(client, hdr, "/api/telegram-groups/-100A/leaderboard?period=7d")
    assert [m["telegram_user_id"] for m in d["members"]] == ["1", "3"] and d["total_ranked"] == 2


def test_ai_overview_reports_only_recorded_statuses(env):
    client, hdr, *_ = env
    code, d = get(client, hdr, "/api/telegram-groups/-100A/insights/ai-overview?days=30")
    assert d["total"] == 4 and d["by_status"] == {"ok": 2, "failed": 1, "skipped": 1}
    assert "pending" not in d["by_status"]


def test_custom_bot_lineage(env):
    client, hdr, hdr_other, ids, _ = env
    base = f"/api/bots/{ids['bot']}/groups/{ids['cg']}/insights"
    code, s = get(client, hdr, base + "/audit-summary?days=30")
    assert code == 200 and s["total_actions"] == 3 and s["automatic"] == 1 and s["manual"] == 2
    code, g = get(client, hdr, base + "/audit-groups?days=30")
    assert sum(x["count"] for x in g["groups"]) == 3
    code, w = get(client, hdr, base + "/warnings-summary")
    assert w["active_records"] == 2 and w["removed_in_period"] is None     # custom deletes on removal
    assert client.get(base + "/members", headers=hdr_other).status_code == 404
    code, d = get(client, hdr, base + "/digest-preview?period=weekly")
    assert code == 200 and "Weekly Report" in d["variants"][0]["text"]


def test_digest_preview_has_no_side_effects(env):
    client, hdr, _, _, app = env
    code, d = get(client, hdr, "/api/telegram-groups/-100A/insights/digest-preview?period=daily")
    assert code == 200 and [v["id"] for v in d["variants"]] == ["manual", "scheduled"]
    assert "Daily Report" in d["variants"][0]["text"] and "Group A" in d["variants"][1]["text"]
    with app.app_context():
        assert (TelegramGroup.query.filter_by(telegram_group_id="-100A").first().settings or {}).get("digest") is None


def test_member_list_warning_filter_matches_records(env):
    client, hdr, _, ids, _ = env
    code, d = get(client, hdr, "/api/telegram-groups/-100A/members?has_active_warnings=true&per_page=100")
    assert sorted(m["telegram_user_id"] for m in d["members"]) == ["1", "2"] and d["total"] == 2
    by = {m["telegram_user_id"]: m["active_warnings"] for m in d["members"]}
    assert by == {"1": 1, "2": 3}
    code, d = get(client, hdr, "/api/telegram-groups/-100A/members?per_page=100")
    assert d["total"] == 4 and {m["telegram_user_id"]: m["active_warnings"] for m in d["members"]}["4"] == 0
    code, d = get(client, hdr, f"/api/bots/{ids['bot']}/groups/{ids['cg']}/members?has_active_warnings=true")
    assert [m["telegram_user_id"] for m in d["members"]] == ["7"] and d["members"][0]["active_warnings"] == 2
