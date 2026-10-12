"""Analytics summaries + list extensions (Guildizer).

Run from discord-board/backend:  python -m pytest tests/test_analytics_insights.py
Throwaway SQLite database and a forged session cookie. Nothing is sent to Discord.
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta

_DB = os.path.join(tempfile.mkdtemp(), "an.db")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB}")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

ME, OTHER = 9601, 9602
G, G2 = 9610, 9611
NOW = datetime.utcnow()


@pytest.fixture(scope="module")
def client():
    import app as appmod
    import auth
    from config import Config
    from database import SessionLocal, init_db
    from models import (AITokenUsage, FeatureUsageEvent, Guild, GuildDailyStat, Member, MemberWarning,
                        ProtectionEvent, User, UserGuild)
    init_db()
    db = SessionLocal()
    db.add_all([User(id=ME, username="admin"), User(id=OTHER, username="other")])
    db.flush()
    db.add_all([Guild(id=G, name="Main <b>", owner_id=ME, plan="free"),
                Guild(id=G2, name="Other", owner_id=OTHER, plan="free")])
    db.flush()
    db.add(UserGuild(user_id=ME, guild_id=G, can_manage=True, is_owner=True))
    db.add_all([
        Member(guild_id=G, user_id=1, username="ann", xp=500, level=12, messages=90, last_seen=NOW - timedelta(hours=2), verified=True, wallet="0xabc"),
        Member(guild_id=G, user_id=2, username="bob", xp=500, level=3, messages=10, last_seen=NOW - timedelta(days=3)),
        Member(guild_id=G, user_id=3, username="cy", xp=100, level=1, messages=1, last_seen=NOW - timedelta(days=40)),
        Member(guild_id=G, user_id=4, username="di", xp=50, level=60, messages=0, last_seen=None),
        Member(guild_id=G2, user_id=1, username="leak", xp=9999, level=99, messages=5, last_seen=NOW),
    ])
    db.add_all([
        MemberWarning(guild_id=G, user_id=2, username="bob", moderator_id=None, reason="automod", created_at=NOW - timedelta(days=1)),
        MemberWarning(guild_id=G, user_id=2, username="bob", moderator_id=ME, moderator_name="admin", reason="rude", created_at=NOW - timedelta(days=2)),
        MemberWarning(guild_id=G, user_id=3, username="cy", moderator_id=ME, moderator_name="admin", reason="spam", created_at=NOW - timedelta(days=60)),
        MemberWarning(guild_id=G2, user_id=1, username="leak", moderator_id=None, reason="x"),
    ])
    db.add_all([
        ProtectionEvent(guild_id=G, category="smart_mod", action="deleted", user_id=2, username="bob", created_at=NOW - timedelta(hours=3)),
        ProtectionEvent(guild_id=G, category="smart_mod", action="none", user_id=2, username="bob", created_at=NOW - timedelta(hours=2)),
        ProtectionEvent(guild_id=G, category="invite", action="deleted", user_id=3, username="cy", created_at=NOW - timedelta(days=2)),
        ProtectionEvent(guild_id=G, category="moderation", action="ban", user_id=3, username="cy", created_at=NOW - timedelta(days=40)),
        ProtectionEvent(guild_id=G2, category="invite", action="deleted", user_id=7, username="leak", created_at=NOW),
    ])
    db.add_all([
        AITokenUsage(guild_id=G, model="m1", input_tokens=100, output_tokens=20, created_at=NOW - timedelta(hours=1)),
        AITokenUsage(guild_id=G, model="m1", input_tokens=50, output_tokens=10, created_at=NOW - timedelta(days=3)),
        AITokenUsage(guild_id=G, model="m2", input_tokens=5, output_tokens=5, created_at=NOW - timedelta(days=45)),
        AITokenUsage(guild_id=G2, model="m1", input_tokens=999, output_tokens=999, created_at=NOW),
        FeatureUsageEvent(guild_id=G, feature="ai_kb_reply", created_at=NOW - timedelta(hours=1)),
        FeatureUsageEvent(guild_id=G, feature="giveaway", created_at=NOW - timedelta(hours=1)),
        GuildDailyStat(guild_id=G, day=NOW.strftime("%Y-%m-%d"), messages=12, joins=2, leaves=1),
    ])
    db.commit()
    db.close()
    cl = appmod.app.test_client()
    cl.set_cookie(Config.SESSION_COOKIE_NAME, auth._issue_session(ME))
    return cl


def u(path):
    return f"/api/guilds/{G}/{path}"


def test_access(client):
    import app as appmod
    assert appmod.app.test_client().get(u("insights/members")).status_code == 401
    assert client.get(f"/api/guilds/{G2}/insights/members").status_code == 403


def test_members_summary_covers_every_member_of_this_server_only(client):
    d = client.get(u("insights/members")).get_json()
    assert d["total"] == 4 and d["total_xp"] == 1150           # the other server's member is not counted
    assert d["active"] == {"24h": 1, "7d": 2, "30d": 2}
    assert d["never_seen"] == 1 and d["verified"] == 1 and d["with_wallet"] == 1
    assert d["with_warnings"] == 2                              # bob and cy, each counted once
    assert d["level_distribution"] == [{"label": "1-4", "count": 2}, {"label": "5-9", "count": 0},
                                       {"label": "10-19", "count": 1}, {"label": "20-49", "count": 0},
                                       {"label": "50+", "count": 1}]       # in reading order, not alphabetical


def test_audit_summary_groups_and_separates_ai_from_rules(client):
    d = client.get(u("insights/audit?days=30")).get_json()
    assert d["total"] == 3                                      # the 40-day-old and other-server events are out
    cats = {c["category"]: c["count"] for c in d["by_category"]}
    assert cats == {"smart_mod": 2, "invite": 1}
    assert d["ai_events"] == 2 and d["rule_events"] == 1
    assert d["most_actioned_members"][0] == {"user_id": "2", "username": "bob", "count": 2}
    assert {"category": "smart_mod", "action": "deleted", "count": 1} in d["grouped"]
    assert len(d["series"]) == 30
    assert client.get(u("insights/audit?days=90")).get_json()["total"] == 4
    assert client.get(u("insights/audit?days=3")).get_json()["days"] == 30     # unsupported range falls back


def test_warnings_summary(client):
    d = client.get(u("insights/warnings?days=30")).get_json()
    assert d["total"] == 3 and d["members_warned"] == 2 and d["recent"] == 2
    assert d["from_automod"] == 1 and d["from_moderators"] == 2
    assert d["repeat_offenders"] == 1
    assert d["top_warned"][0] == {"user_id": "2", "username": "bob", "count": 2}
    assert d["by_moderator"] == [{"name": "admin", "count": 2}]


def test_ai_summary(client):
    d = client.get(u("insights/ai?days=30")).get_json()
    assert d["requests"] == 2 and d["tokens_in"] == 150 and d["tokens_out"] == 30
    assert d["by_model"] == [{"model": "m1", "requests": 2}]
    assert d["moderation_decisions"] == 2 and d["moderation_removals"] == 1 and d["moderation_no_action"] == 1
    assert d["feature_usage"] == {"ai_kb_reply": 1}


def test_digest_preview_builds_the_real_text_and_sends_nothing(client):
    d = client.get(u("insights/digest-preview?label=Weekly")).get_json()
    assert d["label"] == "Weekly" and d["text"].startswith("📊 **Weekly digest")
    assert "12 messages" in d["text"] and "2 joined" in d["text"]
    assert "Report Report" not in d["text"]
    assert client.get(u("insights/digest-preview?label=Hourly")).get_json()["label"] == "Daily"


def test_members_list_paging_filter_and_flags(client):
    d = client.get(u("members?limit=2&sort=xp")).get_json()
    assert d["total"] == 4 and d["total_matching"] == 4 and len(d["members"]) == 2
    # equal XP (ann/bob) is ordered by id, the same on every page
    assert [m["user_id"] for m in d["members"]] == ["1", "2"]
    page2 = client.get(u("members?limit=2&offset=2&sort=xp")).get_json()
    assert [m["user_id"] for m in page2["members"]] == ["3", "4"]
    w = client.get(u("members?has_warnings=1")).get_json()
    assert w["total_matching"] == 2 and w["total"] == 4
    bob = next(m for m in w["members"] if m["user_id"] == "2")
    assert bob["has_active_warnings"] is True and bob["active_warnings"] == 2
    ann = next(m for m in client.get(u("members")).get_json()["members"] if m["user_id"] == "1")
    assert ann["has_active_warnings"] is False
    # every matching member can be walked page by page (what "export all" does)
    seen, off = [], 0
    while True:
        p = client.get(u(f"members?limit=1&offset={off}")).get_json()
        if not p["members"]:
            break
        seen += [m["user_id"] for m in p["members"]]
        off += 1
    assert sorted(seen) == ["1", "2", "3", "4"]


def test_audit_events_filters_and_total(client):
    d = client.get(u("protection/events?limit=2")).get_json()
    assert d["total"] == 4 and len(d["events"]) == 2
    assert client.get(u("protection/events?days=30")).get_json()["total"] == 3
    assert client.get(u("protection/events?category=smart_mod")).get_json()["total"] == 2
    assert client.get(u("protection/events?limit=2&offset=2")).get_json()["events"][0]["category"] in ("invite", "moderation")
    assert client.get(u("protection/events?days=abc")).status_code == 200


def test_leaderboard_total_ranked_and_stable_ties(client):
    d = client.get(u("leaderboard?limit=2")).get_json()
    assert d["total_ranked"] == 4
    assert [r["user_id"] for r in d["leaderboard"]] == ["1", "2"]      # ann/bob tie on XP, id decides
    assert [r["rank"] for r in d["leaderboard"]] == [1, 2]
