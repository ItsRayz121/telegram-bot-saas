"""Role applications: offer list, submit rules, race-safe final review, staff grants."""
import os
import sys
import tempfile

os.environ.setdefault("DATABASE_URL", "sqlite:///" + os.path.join(tempfile.mkdtemp(), "apps.db"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

OWNER, STRANGER, G = 9681, 9682, 9690
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
    db.add(Guild(id=G, name="A", owner_id=OWNER, plan="free"))
    db.flush()
    db.add(UserGuild(user_id=OWNER, guild_id=G, can_manage=True, is_owner=True))
    db.add_all([Role(id=2001, guild_id=G, name="Official Creator", permissions="0"),
                Role(id=2002, guild_id=G, name="Admin", permissions=str(1 << 3))])
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
    calls = []
    fail = {}

    def fake(gid, uid, rid, add, token=None, reason=None):
        if fail.get("code"):
            e = RuntimeError("x")
            e.response = type("R", (), {"status_code": fail["code"]})()
            raise e
        calls.append((uid, rid, add))
    monkeypatch.setattr(discord_api, "set_member_role", fake)
    return type("D", (), {"calls": calls, "fail": fail})


def _submit(uid, rid):
    from database import SessionLocal
    import role_apps
    db = SessionLocal()
    res = role_apps.submit(db, G, uid, "u%d" % uid, rid, "my channel link")
    db.commit()
    db.close()
    SessionLocal.remove()
    return res[0]


def test_config_refuses_privileged_and_submit_needs_an_offered_role(world):
    o = world[OWNER]
    assert o.put(B + "/roles/applications/config", json={"roles": [{"role_id": "2002"}]}).status_code == 400
    assert _submit(1, 2001) == "not_offered"                       # not offered yet
    assert o.put(B + "/roles/applications/config", json={"roles": [{"role_id": "2001", "label": "Creator"}]}).status_code == 200
    assert _submit(1, 2001) == "ok" and _submit(1, 2001) == "already_pending"


def test_approve_grants_once_and_review_is_final(world, discord):
    o = world[OWNER]
    apps = o.get(B + "/roles/applications").get_json()["applications"]
    assert len(apps) == 1 and apps[0]["role_name"] == "Official Creator"
    aid = apps[0]["id"]
    r = o.post(B + "/roles/applications/%d/review" % aid, json={"decision": "approve"})
    assert r.status_code == 200 and discord.calls == [(1, 2001, True)]
    assert o.post(B + "/roles/applications/%d/review" % aid, json={"decision": "approve"}).status_code == 409
    assert len(discord.calls) == 1


def test_failed_grant_keeps_application_pending(world, discord):
    o = world[OWNER]
    assert _submit(2, 2001) == "ok"
    aid = [a for a in o.get(B + "/roles/applications").get_json()["applications"]][0]["id"]
    discord.fail["code"] = 403
    r = o.post(B + "/roles/applications/%d/review" % aid, json={"decision": "approve"})
    assert r.status_code == 502 and r.get_json()["error"] == "missing_permission"
    assert o.get(B + "/roles/applications").get_json()["applications"][0]["status"] == "pending"
    discord.fail.clear()
    assert o.post(B + "/roles/applications/%d/review" % aid, json={"decision": "reject", "note": "no"}).status_code == 200


def test_staff_grant_blocks_privileged_and_strangers(world, discord):
    o = world[OWNER]
    assert o.put(B + "/roles/2001/members/55").status_code == 200 and discord.calls[-1] == (55, 2001, True)
    assert o.delete(B + "/roles/2001/members/55").status_code == 200 and discord.calls[-1] == (55, 2001, False)
    assert o.put(B + "/roles/2002/members/55").status_code == 400
    assert world[STRANGER].put(B + "/roles/2001/members/55").status_code == 403
    assert world[STRANGER].get(B + "/roles/applications").status_code == 403
