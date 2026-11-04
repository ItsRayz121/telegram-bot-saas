"""Approval queue (severe ladder actions, level ranks) + review-bug regressions. Discord is faked."""
import os
import sys
import tempfile
from datetime import datetime, timedelta

os.environ.setdefault("DATABASE_URL", "sqlite:///" + os.path.join(tempfile.mkdtemp(), "appr.db"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

OWNER, STRANGER, G = 9781, 9782, 9790
B = "/api/guilds/%d" % G


@pytest.fixture(scope="module")
def world():
    import app as appmod
    import auth
    from config import Config
    from database import SessionLocal, init_db
    from models import Guild, Role, User, UserGuild
    init_db()
    db = SessionLocal()
    db.add_all([User(id=OWNER, username="o"), User(id=STRANGER, username="s")])
    db.flush()
    db.add(Guild(id=G, name="Ap", owner_id=OWNER, plan="free"))
    db.flush()
    db.add(UserGuild(user_id=OWNER, guild_id=G, can_manage=True, is_owner=True))
    db.add_all([Role(id=3001, guild_id=G, name="Rank", permissions="0"),
                Role(id=3002, guild_id=G, name="Mod", permissions=str(1 << 1))])
    db.commit()
    db.close()

    def c(uid):
        cl = appmod.app.test_client()
        cl.set_cookie(Config.SESSION_COOKIE_NAME, auth._issue_session(uid))
        return cl
    return {OWNER: c(OWNER), STRANGER: c(STRANGER)}


@pytest.fixture(autouse=True)
def discord(monkeypatch):
    import discord_api
    import team_direct
    from models import Guild
    monkeypatch.setattr(Guild, "is_served", property(lambda self: True), raising=False)
    monkeypatch.setattr(team_direct, "bot_token_for", lambda db, guild: "tok")
    calls, fail = [], {}

    def rec(name):
        def f(*a, **k):
            if fail.get("code"):
                e = RuntimeError("x")
                e.response = type("R", (), {"status_code": fail["code"]})()
                raise e
            calls.append((name,) + tuple(a[1:3]))
        return f
    monkeypatch.setattr(discord_api, "kick_member", rec("kick"))
    monkeypatch.setattr(discord_api, "ban_member", rec("ban"))
    monkeypatch.setattr(discord_api, "timeout_member", rec("timeout"))
    monkeypatch.setattr(discord_api, "set_member_role", rec("role"))
    return type("D", (), {"calls": calls, "fail": fail})


def _new(kind, user=1, **kw):
    from database import SessionLocal
    import mod_approvals
    db = SessionLocal()
    row, created = mod_approvals.queue(db, G, user, "u", kind, **kw)
    db.commit()
    rid = row.id
    db.close()
    SessionLocal.remove()
    return rid, created


def test_queue_dedupes_and_gate_is_opt_in():
    import mod_approvals
    assert not mod_approvals.needs_approval({}, "ban")
    assert mod_approvals.needs_approval({"require_approval": ["ban"]}, "ban")
    assert not mod_approvals.needs_approval({"require_approval": ["ban"]}, "kick")
    a, c1 = _new("ban", 11)
    b, c2 = _new("ban", 11)
    assert a == b and c1 and not c2


def test_approve_executes_once_and_review_is_final(world, discord):
    o = world[OWNER]
    rid, _ = _new("kick", 21)
    assert o.post(B + "/approvals/%d/review" % rid, json={"decision": "approve"}).status_code == 200
    assert discord.calls == [("kick", 21)] or discord.calls[-1][0] == "kick"
    n = len(discord.calls)
    assert o.post(B + "/approvals/%d/review" % rid, json={"decision": "approve"}).status_code == 409
    assert len(discord.calls) == n


def test_failed_execution_stays_pending_and_can_retry(world, discord):
    o = world[OWNER]
    rid, _ = _new("ban", 31)
    discord.fail["code"] = 403
    r = o.post(B + "/approvals/%d/review" % rid, json={"decision": "approve"})
    assert r.status_code == 502 and r.get_json()["error"] == "missing_permission"
    row = [a for a in o.get(B + "/approvals").get_json()["approvals"] if a["id"] == rid][0]
    assert row["status"] == "pending" and row["result_error"] == "missing_permission"
    discord.fail.clear()
    assert o.post(B + "/approvals/%d/review" % rid, json={"decision": "approve"}).status_code == 200


def test_stale_claim_is_taken_over(world, discord):
    from database import SessionLocal
    from models import ModApproval
    rid, _ = _new("kick", 41)
    db = SessionLocal()
    row = db.get(ModApproval, rid)
    row.status, row.reviewed_at = "reviewing", datetime.utcnow() - timedelta(minutes=5)   # crashed reviewer
    db.commit()
    db.close()
    SessionLocal.remove()
    assert world[OWNER].post(B + "/approvals/%d/review" % rid, json={"decision": "reject"}).status_code == 200


def test_rank_approval_refuses_a_privileged_role(world, discord):
    rid, _ = _new("rank", 51, role_id=3002)
    r = world[OWNER].post(B + "/approvals/%d/review" % rid, json={"decision": "approve"})
    assert r.status_code == 400 and not [c for c in discord.calls if c[0] == "role"]
    ok_id, _ = _new("rank", 52, role_id=3001)
    assert world[OWNER].post(B + "/approvals/%d/review" % ok_id, json={"decision": "approve"}).status_code == 200
    again, created = _new("rank", 52, role_id=3001)       # already asked about this member+role
    assert not created


def test_settings_and_authorization(world):
    o = world[OWNER]
    assert o.put(B + "/approvals/settings", json={"require_approval": ["ban", "nonsense"], "rank_approval": True}).status_code == 200
    s = o.get(B + "/approvals").get_json()["settings"]
    assert s == {"require_approval": ["ban"], "rank_approval": True}
    assert world[STRANGER].get(B + "/approvals").status_code == 403
    assert world[STRANGER].post(B + "/approvals/1/review", json={"decision": "approve"}).status_code == 403


def test_replace_policy_needs_a_held_top_role():
    import level_roles
    rw = [{"level": 1, "role_id": "11"}, {"level": 5, "role_id": "55"}]
    assert level_roles.top_role_ids(7, rw) == {55}
    assert level_roles.top_role_ids(1, rw) == {11}


def test_already_saved_self_role_entries_do_not_block_saves(world):
    from database import SessionLocal
    from models import GuildSettings, Role
    db = SessionLocal()
    db.merge(Role(id=3003, guild_id=G, name="Old", permissions="0"))
    db.commit()
    o = world[OWNER]
    menu = {"title": "m", "channel_id": "1", "entries": [{"label": "x", "role_id": "3003"}]}
    mid = o.put(B + "/self-roles", json={"menus": [menu]}).get_json()["menus"][0]["id"]
    r = db.get(Role, 3003)
    r.permissions = str(1 << 3)                 # the role LATER gained Administrator
    db.commit()
    db.close()
    SessionLocal.remove()
    menu.update(id=mid, title="renamed")
    assert o.put(B + "/self-roles", json={"menus": [menu]}).status_code == 200      # old entry still saves
    new = {"title": "n", "channel_id": "1", "entries": [{"label": "y", "role_id": "3003"}]}
    assert o.put(B + "/self-roles", json={"menus": [menu, new]}).status_code == 200   # same id is "already saved"


def test_staff_report_schedule_and_content(world):
    from datetime import datetime
    import staff_report
    from database import SessionLocal
    import protection
    mon = datetime(2026, 11, 2, 10, 0)           # a Monday after 09:00 UTC
    cfg = {"enabled": True, "cadence": "weekly", "weekday": 0, "hour_utc": 9, "last_period": None}
    assert staff_report.is_due(cfg, mon)
    assert not staff_report.is_due({**cfg, "last_period": staff_report.period_key("weekly", mon)}, mon)   # sent already
    assert not staff_report.is_due(cfg, datetime(2026, 11, 3, 10, 0))                                       # Tuesday
    assert not staff_report.is_due(cfg, datetime(2026, 11, 2, 8, 0))                                        # too early
    assert not staff_report.is_due({**cfg, "enabled": False}, mon)
    assert staff_report.is_due({**cfg, "cadence": "monthly"}, datetime(2026, 11, 1, 10, 0))
    db = SessionLocal()
    protection.log_event(db, G, "role_policy", "level_grant", user_id=1, detail="Level 5")
    protection.log_event(db, G, "spam", "deleted", user_id=2)
    db.commit()
    text = staff_report.build_report(db, G, "Srv", "weekly")
    db.close()
    SessionLocal.remove()
    assert "1 level rewards" in text and "Automod actions: 1" in text


def test_staff_report_settings_api(world):
    o = world[OWNER]
    r = o.put(B + "/staff-report", json={"enabled": True, "cadence": "monthly", "hour_utc": 99, "weekday": 3})
    assert r.status_code == 200 and r.get_json()["cadence"] == "monthly" and r.get_json()["hour_utc"] == 23
    assert o.get(B + "/staff-report").get_json()["enabled"] is True
    assert world[STRANGER].put(B + "/staff-report", json={"enabled": False}).status_code == 403
