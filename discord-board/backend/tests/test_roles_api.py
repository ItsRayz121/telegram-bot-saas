"""Roles overview/members/create + privileged-role guards. Discord is faked."""
import os
import sys
import tempfile

os.environ.setdefault("DATABASE_URL", "sqlite:///" + os.path.join(tempfile.mkdtemp(), "roles.db"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

OWNER, STRANGER, G = 9581, 9582, 9590
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
    db.add(Guild(id=G, name="R", owner_id=OWNER, plan="free"))
    db.flush()
    db.add(UserGuild(user_id=OWNER, guild_id=G, can_manage=True, is_owner=True))
    db.add_all([
        Role(id=G, guild_id=G, name="@everyone", position=0, permissions="0"),
        Role(id=1001, guild_id=G, name="Verified", position=2, permissions="0"),
        Role(id=1002, guild_id=G, name="Creator", position=3, permissions="0"),
        Role(id=1003, guild_id=G, name="Admin", position=9, permissions=str(1 << 3)),
        Role(id=1004, guild_id=G, name="BotRole", position=4, permissions="0", managed=True),
    ])
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
    import roles_api
    import team_direct
    from models import Guild
    roles_api._cache.clear()
    monkeypatch.setattr(Guild, "is_served", property(lambda self: True), raising=False)
    monkeypatch.setattr(team_direct, "bot_token_for", lambda db, guild: "tok")

    def mem(uid, roles, bot=False):
        return {"user": {"id": str(uid), "username": "u%d" % uid, "bot": bot}, "roles": [str(r) for r in roles]}
    members = [mem(1, [1001, 1002]), mem(2, [1001]), mem(3, [1001]), mem(4, [], bot=True)]
    monkeypatch.setattr(discord_api, "list_guild_members", lambda gid, token=None, max_pages=10: (members, True))
    made = {}

    def create(gid, name, color=0, token=None, reason=None, **opts):
        made["n"] = made.get("n", 0) + 1
        return {"id": str(5000 + made["n"]), "name": name, "color": color, "position": 1, "permissions": "0"}
    monkeypatch.setattr(discord_api, "create_role", create)


def test_overview_counts_and_flags(world):
    d = world[OWNER].get(B + "/roles/overview").get_json()
    by = {r["name"]: r for r in d["roles"]}
    assert d["status"] == "complete" and d["totals"] == {"members": 3, "bots": 1}
    assert by["Verified"]["member_count"] == 3 and by["Creator"]["member_count"] == 1
    assert by["Admin"]["privileged"] and not by["Admin"]["assignable"]
    assert by["BotRole"]["category"] == "integration"
    assert by["@everyone"]["member_count"] == 3


def test_unavailable_is_not_zero(world, monkeypatch):
    import discord_api
    import roles_api

    def boom(*a, **k):
        raise RuntimeError("no intent")
    roles_api._cache.clear()
    monkeypatch.setattr(discord_api, "list_guild_members", boom)
    d = world[OWNER].get(B + "/roles/overview").get_json()
    assert d["status"] == "unavailable" and all(r["member_count"] is None for r in d["roles"])


def test_members_drilldown_search_and_page(world):
    d = world[OWNER].get(B + "/roles/1001/members?limit=2").get_json()
    assert d["total"] == 3 and len(d["members"]) == 2
    d = world[OWNER].get(B + "/roles/1001/members?q=u2").get_json()
    assert [m["id"] for m in d["members"]] == ["2"]
    assert world[OWNER].get(B + "/roles/99999/members").status_code == 404


def test_non_manager_refused(world):
    assert world[STRANGER].get(B + "/roles/overview").status_code == 403
    assert world[STRANGER].get(B + "/roles/1001/members").status_code == 403
    assert world[STRANGER].post(B + "/roles/create", json={"name": "X"}).status_code == 403


def test_create_role_and_duplicate_guard(world):
    r = world[OWNER].post(B + "/roles/create", json={"name": "Active Contributor", "color": "#5865F2"})
    assert r.status_code == 201 and r.get_json()["role"]["name"] == "Active Contributor"
    assert world[OWNER].post(B + "/roles/create", json={"name": "active contributor"}).status_code == 409
    assert world[OWNER].post(B + "/roles/create", json={"name": "@everyone"}).status_code == 400


def test_privileged_roles_rejected_server_side(world):
    menu = {"title": "t", "channel_id": "1", "entries": [{"label": "Ambassador", "role_id": "1003"}]}
    r = world[OWNER].put(B + "/self-roles", json={"menus": [menu]})
    assert r.status_code == 400 and r.get_json()["roles"] == {"1003": "privileged_role"}
    menu["entries"][0]["role_id"] = "1001"
    assert world[OWNER].put(B + "/self-roles", json={"menus": [menu]}).status_code == 200
    r = world[OWNER].put(B + "/leveling", json={"leveling2": {"role_rewards": [{"level": 5, "role_id": "1003"}]}})
    assert r.status_code == 400
    r = world[OWNER].put(B + "/leveling", json={"leveling2": {"role_rewards": [{"level": 5, "role_id": "1002"}]}})
    assert r.status_code == 200


def test_self_role_status_lifecycle(world):
    from datetime import datetime, timedelta
    o = world[OWNER]
    menu = {"title": "Pick", "channel_id": "123", "entries": [{"label": "V", "role_id": "1001"}]}
    d = o.put(B + "/self-roles", json={"menus": [menu]}).get_json()["menus"][0]
    assert d["status"] == "draft"
    mid = d["id"]
    when = (datetime.utcnow() + timedelta(hours=2)).isoformat() + "Z"
    assert o.post(B + "/self-roles/%d/post" % mid, json={"post_at": when}).status_code == 200
    assert o.get(B + "/self-roles").get_json()["menus"][0]["status"] == "scheduled"
    assert o.delete(B + "/self-roles/%d/post" % mid).get_json()["cancelled"] is True
    assert o.get(B + "/self-roles").get_json()["menus"][0]["status"] == "draft"
    assert o.post(B + "/self-roles/%d/post" % mid, json={}).status_code == 200
    assert o.get(B + "/self-roles").get_json()["menus"][0]["status"] == "publishing"
    # the bot publishes it, then it is unpublished
    import self_roles
    self_roles.mark_posted(G, mid, 777, 123)
    m = o.get(B + "/self-roles").get_json()["menus"][0]
    assert m["status"] == "published" and m["posted_channel_id"] == "123"
    assert o.put(B + "/self-roles", json={"menus": [{**menu, "id": mid, "title": "Edited"}]}).get_json()["menus"][0]["message_id"] == "777"
    self_roles.mark_deleted(G, mid)
    assert o.get(B + "/self-roles").get_json()["menus"][0]["status"] == "unpublished"


def test_logout_revokes_a_copied_session_cookie():
    import app as appmod
    import auth
    from config import Config
    from database import SessionLocal
    from models import User
    uid = 9588
    db = SessionLocal()
    db.add(User(id=uid, username="rev"))
    db.commit()
    db.close()
    token = auth._issue_session(uid, 0)

    def client():
        c = appmod.app.test_client()
        c.set_cookie(Config.SESSION_COOKIE_NAME, token)
        return c
    assert client().get("/auth/me").status_code == 200
    assert client().post("/auth/logout").status_code == 200
    assert client().get("/auth/me").status_code == 401        # same cookie, now dead


def test_role_history_lists_audit_events(world):
    import role_policy
    role_policy.audit_grant(G, 4242, "someone", "level_grant", "Level 5: Active")
    d = world[OWNER].get(B + "/roles/history").get_json()
    hit = [e for e in d["events"] if e["user_id"] == "4242"]
    assert hit and hit[0]["source"] == "Level reward" and "Level 5" in hit[0]["detail"]
    assert world[OWNER].get(B + "/roles/history?user_id=1").get_json()["total"] >= 0
    assert world[STRANGER].get(B + "/roles/history").status_code == 403
