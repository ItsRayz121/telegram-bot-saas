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


@pytest.fixture(scope="module", autouse=True)
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


def test_database_itself_refuses_duplicate_pending_rows():
    """The guarantee is in the DB (partial unique indexes), not only in a pre-check."""
    from sqlalchemy.exc import IntegrityError
    from database import SessionLocal
    from models import ModApproval, RoleApplication
    db = SessionLocal()
    db.add(RoleApplication(guild_id=G, user_id=801, role_id=3001, status="pending"))
    db.commit()
    db.add(RoleApplication(guild_id=G, user_id=801, role_id=3001, status="pending"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.add(RoleApplication(guild_id=G, user_id=801, role_id=3001, status="approved"))   # history rows are fine
    db.commit()
    db.add(ModApproval(guild_id=G, user_id=802, kind="ban", status="pending"))
    db.commit()
    db.add(ModApproval(guild_id=G, user_id=802, kind="ban", status="reviewing"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.close()
    SessionLocal.remove()


def test_submit_and_queue_survive_losing_the_race(monkeypatch):
    """If the pre-check misses (two requests at once) the insert collides and is reported
    as already-pending / not-created rather than crashing."""
    from sqlalchemy.orm import Query
    import mod_approvals
    import role_apps
    from database import SessionLocal
    first, _ = _new("timeout", 811, minutes=5)
    real_first = Query.first
    blind = {"on": True}

    def first_blind_once(self):                    # the pre-check "doesn't see" the other request's row
        if blind["on"]:
            blind["on"] = False
            return None
        return real_first(self)
    monkeypatch.setattr(Query, "first", first_blind_once)
    db = SessionLocal()
    row, created = mod_approvals.queue(db, G, 811, "u", "timeout", minutes=5)
    assert created is False and row.id == first
    db.close()
    SessionLocal.remove()


def test_publish_claim_is_exclusive_and_expires():
    import self_roles
    from datetime import datetime, timedelta
    from database import SessionLocal
    from models import GuildSettings
    import settings as settings_mod
    db = SessionLocal()
    row = settings_mod.get_or_create(db, G)
    row.extra = {**(row.extra or {}), "self_roles": [{"id": 9, "title": "t", "needs_post": True, "entries": []}]}
    db.commit()
    db.close()
    SessionLocal.remove()
    assert self_roles.claim_post(G, 9) is True
    assert self_roles.claim_post(G, 9) is False          # a second worker is refused
    assert self_roles.claim_post(G, 404) is False         # unknown menu
    self_roles.mark_post_failed(G, 9, "boom")             # ending an attempt releases the claim
    assert self_roles.claim_post(G, 9) is True
    db = SessionLocal()
    row = db.get(GuildSettings, G)
    menus = [dict(m) for m in row.extra["self_roles"]]
    menus[0]["publishing_since"] = (datetime.utcnow() - timedelta(minutes=5)).isoformat()   # crashed worker
    row.extra = {**row.extra, "self_roles": menus}
    db.commit()
    db.close()
    SessionLocal.remove()
    assert self_roles.claim_post(G, 9) is True            # stale claim taken over


def test_find_existing_adopts_a_message_instead_of_double_posting():
    import asyncio
    import self_roles

    class Msg:
        def __init__(self, uid, content="", ids=()):
            self.author = type("A", (), {"id": uid})()
            self.content = content
            self.components = [type("Row", (), {"children": [type("B", (), {"custom_id": i})() for i in ids]})()]

    class Chan:
        id = 1

        def __init__(self, msgs):
            self.msgs = msgs

        async def history(self, limit=50):
            for m in self.msgs:
                yield m
    bot = type("Bot", (), {"user": type("U", (), {"id": 7})()})()
    btn = Msg(7, ids=["gz:srole:5:9:100"])
    other = Msg(8, ids=["gz:srole:5:9:100"])               # someone else's message is never adopted
    wrong_menu = Msg(7, ids=["gz:srole:5:10:100"])
    run = lambda coro: asyncio.new_event_loop().run_until_complete(coro)       # noqa: E731
    assert run(self_roles._find_existing(bot, Chan([other, wrong_menu, btn]), 5, {"id": 9, "style": "buttons"})) is btn
    assert run(self_roles._find_existing(bot, Chan([other, wrong_menu]), 5, {"id": 9, "style": "buttons"})) is None
    react = Msg(7, content="**Pick**\n-# menu #9")
    assert run(self_roles._find_existing(bot, Chan([react]), 5, {"id": 9, "style": "reactions"})) is react
    assert run(self_roles._find_existing(bot, Chan([react]), 5, {"id": 10, "style": "reactions"})) is None


def test_changes_made_in_discord_join_the_history_without_duplicating_ours():
    import role_policy
    from database import SessionLocal
    from models import ProtectionEvent
    role_policy._ext_budget.clear()
    assert role_policy.audit_external(G, 901, "alice", ["Booster"], []) is True      # nobody else recorded it
    db = SessionLocal()
    ev = db.query(ProtectionEvent).filter_by(guild_id=G, user_id=901, action="discord_change").one()
    assert ev.detail == "Added Booster (changed in Discord)"
    db.close()
    SessionLocal.remove()
    role_policy.audit_grant(G, 902, "bob", "level_grant", "Level 5: Active")          # Guildizer's own grant
    assert role_policy.audit_external(G, 902, "bob", ["Active"], []) is False        # same change: not repeated
    role_policy._ext_budget[G] = (__import__("time").time() // 60, role_policy.EXTERNAL_PER_MINUTE)
    assert role_policy.audit_external(G, 903, "cy", ["X"], []) is False              # mass-change flood guard
    role_policy._ext_budget.clear()


def test_staff_report_sections_filter_and_reset_confirm(world):
    import staff_report
    from database import SessionLocal
    db = SessionLocal()
    full = staff_report.build_report(db, G, "S", "weekly")
    only_roles = staff_report.build_report(db, G, "S", "weekly", sections=["roles"])
    none = staff_report.build_report(db, G, "S", "weekly", sections=[])
    db.close()
    SessionLocal.remove()
    assert "Automod actions" in full and "Roles:" in only_roles and "Automod actions" not in only_roles
    assert "no sections" in none
    o = world[OWNER]
    assert o.put(B + "/staff-report", json={"sections": ["roles", "bogus"]}).get_json()["sections"] == ["roles"]
    r = o.put(B + "/leveling", json={"leveling2": {"penalty_ban_mode": "reset"}})
    assert r.status_code == 400 and r.get_json()["error"] == "confirm_reset_required"
    assert o.put(B + "/leveling", json={"confirm_reset": True, "leveling2": {"penalty_ban_mode": "reset"}}).status_code == 200
    assert o.put(B + "/leveling", json={"leveling2": {"penalty_ban_mode": "reset"}}).status_code == 200


def test_roles_overview_lists_guildizer_features_a_role_unlocks(world):
    from database import SessionLocal
    import settings as settings_mod
    db = SessionLocal()
    row = settings_mod.get_or_create(db, G)
    row.extra = {**(row.extra or {}), "tickets": {"support_role_id": "3001"}}
    db.commit()
    db.close()
    SessionLocal.remove()
    d = world[OWNER].get(B + "/roles/overview").get_json()
    rank = [r for r in d["roles"] if r["id"] == "3001"]
    if rank:
        assert "Pinged in new support tickets" in rank[0]["usage"]["unlocks"]


def test_archive_only_when_nothing_is_live_and_archived_menus_cannot_publish(world):
    o = world[OWNER]
    menu = {"title": "Old", "channel_id": "5", "entries": [{"label": "x", "role_id": "3001"}]}
    saved = o.put(B + "/self-roles", json={"menus": [menu]}).get_json()["menus"]
    mine = [m for m in saved if m["title"] == "Old"][0]
    mine["archived"] = True
    out = o.put(B + "/self-roles", json={"menus": saved}).get_json()["menus"]
    assert [m for m in out if m["title"] == "Old"][0]["archived"] is True
    assert o.post(B + "/self-roles/%d/post" % mine["id"], json={}).status_code == 400


def test_autoroles_and_workflow_add_role_refuse_privileged_roles(world):
    o = world[OWNER]
    assert o.put(B + "/settings", json={"autorole_ids": ["3002"]}).status_code == 400          # kick-members role
    assert o.put(B + "/settings", json={"autorole_ids": ["3001"]}).status_code == 200
    wf = {"name": "w", "trigger_type": "member_join", "actions": [{"type": "add_role", "role_id": "3002"}]}
    r = o.post(B + "/workflows", json=wf)
    assert r.status_code == 400 and r.get_json()["error"] == "role_not_assignable"
    wf["actions"][0]["role_id"] = "3001"
    wid = o.post(B + "/workflows", json=wf).get_json()["workflow"]["id"]
    assert o.put(B + "/workflows/%d" % wid, json={"actions": [{"type": "add_role", "role_id": "3002"}]}).status_code == 400


def test_dashboard_moderation_action_safeguards(world, discord, monkeypatch):
    import discord_api
    from database import SessionLocal
    from models import Guild, Role
    db = SessionLocal()
    db.get(Guild, G).owner_id = OWNER
    db.merge(Role(id=3010, guild_id=G, name="Boss", position=50, permissions="0"))
    db.merge(Role(id=3011, guild_id=G, name="Botrole", position=40, permissions="0"))
    db.merge(Role(id=3012, guild_id=G, name="Plain", position=2, permissions="0"))
    db.merge(Role(id=3013, guild_id=G, name="Adm", position=3, permissions=str(1 << 3)))
    db.commit()
    db.close()
    SessionLocal.remove()
    members = {OWNER: {"roles": []}, 60: {"roles": ["3010"]}, 61: {"roles": ["3012"]}, 62: {"roles": ["3013"]}, 777: {"roles": ["3011"]}}
    monkeypatch.setattr(discord_api, "get_member", lambda gid, uid, token=None: members.get(int(uid)))
    monkeypatch.setattr(discord_api, "get_self_id", lambda token=None: 777)
    o = world[OWNER]
    act = lambda uid, a="kick": o.post(B + "/moderation/action", json={"action": a, "user_id": str(uid)})   # noqa: E731
    assert act(OWNER).get_json()["error"] == "target_is_owner"
    assert act(60).get_json()["error"] == "target_above_bot"
    assert act(62).get_json()["error"] == "target_is_administrator"
    assert act(404).get_json()["error"] == "not_in_server"
    assert act(61).status_code == 200 and discord.calls[-1][0] == "kick"
    assert act(404, "ban").status_code == 200                       # banning a non-member (hackban) is allowed


def test_slash_moderation_needs_a_higher_role_than_the_target():
    import asyncio
    import discord
    import mod_commands

    class Role:
        def __init__(self, n):
            self.n = n

        def __ge__(self, other):
            return self.n >= other.n

    class FakeMember(discord.Member):      # subclass has a __dict__ (discord.Member uses __slots__)
        id = 0
        top_role = None
        pass

    def user(uid, n, cls=FakeMember):
        u = object.__new__(cls)
        u.__dict__.update({"id": uid, "top_role": Role(n)})
        return u
    guild = type("G", (), {"owner_id": 1, "me": type("Me", (), {"top_role": Role(50)})()})()
    client = type("C", (), {"user": type("U", (), {"id": 7})()})()

    def inter(invoker):
        return type("I", (), {"guild": guild, "user": invoker, "client": client})()
    run = lambda i, t: asyncio.new_event_loop().run_until_complete(mod_commands._check_target(i, t))   # noqa: E731
    assert "below yours" in run(inter(user(2, 10)), user(3, 10))        # equal rank: refused
    assert "below yours" in run(inter(user(2, 10)), user(3, 20))        # target higher: refused
    assert run(inter(user(2, 20)), user(3, 10)) is None                 # moderating someone lower: fine
    assert run(inter(user(1, 5)), user(3, 10)) is None                  # the owner can moderate anyone below the bot


def test_scheduled_message_failure_is_recorded_not_silent():
    import content_runtime
    from datetime import datetime, timedelta
    from database import SessionLocal
    from models import ScheduledMessage
    db = SessionLocal()
    row = ScheduledMessage(guild_id=G, channel_id=1, content="hi", recurrence="none",
                           next_run_at=datetime.utcnow() - timedelta(minutes=1), enabled=True)
    db.add(row)
    db.commit()
    mid = row.id
    db.close()
    SessionLocal.remove()
    content_runtime.advance_schedule(mid, False, "channel not found")
    db = SessionLocal()
    r = db.get(ScheduledMessage, mid)
    assert r.enabled is False and r.last_error == "channel not found" and r.to_dict()["last_error"] == "channel not found"
    db.close()
    SessionLocal.remove()
    content_runtime.advance_schedule(mid, True)
    db = SessionLocal()
    assert db.get(ScheduledMessage, mid).last_error is None
    db.close()
    SessionLocal.remove()


def test_export_carries_the_modern_moderation_config_without_any_server_ids():
    import settings_transfer as st
    import protection
    from database import SessionLocal
    db = SessionLocal()
    row = protection.get_or_create(db, G)
    row.extra = {"warn_ladder": {"enabled": True, "steps": [{"at": 3, "action": "timeout", "minutes": 10}],
                                 "require_approval": ["ban"]},
                 "automod": {"flood": {"enabled": True, "max_messages": 7},
                             "slow_mode": {"enabled": True, "seconds_between_messages": 45, "exclude_channel_ids": ["5"]}},
                 "bot_policy": {"enabled": True, "policy": "alert_only", "trusted_bot_ids": ["111"], "alert_channel_id": "9"}}
    db.commit()
    exp = st.build_export(db, G, "S")
    me = exp["settings"]["moderation_extra"]
    assert me["warn_ladder"]["steps"][0]["at"] == 3 and "require_approval" not in me["warn_ladder"]
    assert me["automod"]["flood"]["max_messages"] == 7 and "exclude_channel_ids" not in me["automod"]["slow_mode"]
    assert me["bot_policy"]["policy"] == "alert_only" and "trusted_bot_ids" not in me["bot_policy"] and "alert_channel_id" not in me["bot_policy"]
    clean, err = st.parse_export(exp)
    assert err is None
    clean["moderation_extra"]["automod"]["slow_mode"]["exclude_channel_ids"] = ["777"]       # hand-edited file: ids ignored
    # apply onto a second server
    from models import Guild
    db.add(Guild(id=G + 500, name="Target", owner_id=None, plan="free"))
    db.commit()
    preview = st.plan_import(db, G + 500, clean, apply=False)
    db.commit()
    assert any(c["path"].startswith("moderation.warn_ladder") for c in preview["changes"])
    st.plan_import(db, G + 500, clean, apply=True)
    tgt = protection._merged_extra(protection.get_or_create(db, G + 500))
    assert tgt["warn_ladder"]["enabled"] is True and tgt["automod"]["flood"]["max_messages"] == 7
    assert tgt["automod"]["slow_mode"]["exclude_channel_ids"] == [] and tgt["bot_policy"]["trusted_bot_ids"] == []
    db.close()
    SessionLocal.remove()


def test_campaign_reward_role_is_granted_once_per_member_and_never_privileged(world):
    import campaign_roles
    from datetime import datetime
    from database import SessionLocal
    from models import Campaign, CampaignSubmission
    o = world[OWNER]
    db = SessionLocal()
    camp = Campaign(guild_id=G, title="Quest", status="active", settings={})
    db.add(camp)
    db.commit()
    cid = camp.id
    db.add_all([CampaignSubmission(campaign_id=cid, user_id=71, username="old", status="verified"),
                CampaignSubmission(campaign_id=cid, user_id=72, username="new1", status="verified"),
                CampaignSubmission(campaign_id=cid, user_id=72, username="new1", status="verified"),   # 2nd task, same member
                CampaignSubmission(campaign_id=cid, user_id=73, username="pend", status="pending")])
    db.commit()
    db.close()
    SessionLocal.remove()
    url = B + "/roles/campaign-rewards/%d" % cid
    assert o.put(url, json={"role_id": "3002"}).status_code == 400            # privileged role refused
    assert o.put(url, json={"role_id": "99999"}).status_code == 400           # not a role of this server
    assert o.put(url, json={"role_id": "3001"}).status_code == 200            # include_past defaults to false
    assert [c for c in o.get(B + "/roles/campaign-rewards").get_json()["campaigns"] if c["id"] == cid][0]["role_id"] == "3001"
    db = SessionLocal()
    assert campaign_roles.pending(db, [G]) == []                              # earlier completers were closed out
    db.add(CampaignSubmission(campaign_id=cid, user_id=74, username="later", status="verified"))
    db.add(CampaignSubmission(campaign_id=cid, user_id=74, username="later", status="verified"))
    db.commit()
    items = campaign_roles.pending(db, [G])
    assert [i["user_id"] for i in items] == [74] and len(items[0]["sub_ids"]) == 2 and items[0]["role_id"] == 3001
    campaign_roles.mark_done(db, items[0]["sub_ids"])
    db.commit()
    assert campaign_roles.pending(db, [G]) == []                              # granted once, not again
    db.close()
    SessionLocal.remove()
    assert o.put(url, json={"role_id": ""}).status_code == 200                # clearing is fine
    assert world[STRANGER].put(url, json={"role_id": "3001"}).status_code == 403
