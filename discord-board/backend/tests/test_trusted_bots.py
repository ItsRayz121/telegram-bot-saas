"""Trusted bots API: identity, legacy data, add/remove one at a time. Discord is faked."""
import os
import sys
import tempfile

_DB = os.path.join(tempfile.mkdtemp(), "tb.db")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB}")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

OWNER, STRANGER, G = 9281, 9282, 9290
URL = "/api/guilds/%d/trusted-bots" % G
BOT_A, BOT_B, HUMAN = "111111111111111111", "222222222222222222", "333333333333333333"


@pytest.fixture(scope="module")
def world():
    import app as appmod
    import auth
    import protection
    from config import Config
    from database import SessionLocal, init_db
    from models import Guild, User, UserGuild
    init_db()
    db = SessionLocal()
    db.add_all([User(id=OWNER, username="o"), User(id=STRANGER, username="s")])
    db.flush()
    db.add(Guild(id=G, name="TB", owner_id=OWNER, plan="free"))
    db.flush()
    db.add(UserGuild(user_id=OWNER, guild_id=G, can_manage=True, is_owner=True))
    row = protection.get_or_create(db, G)
    row.extra = {"bot_policy": {"trusted_bot_ids": [f"{BOT_A}, {BOT_B}", 444444444444444444, BOT_A]}}  # legacy shapes
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
    users = {BOT_A: {"id": BOT_A, "username": "alpha", "bot": True},
             BOT_B: {"id": BOT_B, "username": "beta", "bot": True},
             HUMAN: {"id": HUMAN, "username": "human"}}
    monkeypatch.setattr(discord_api, "list_guild_bots", lambda gid, token=None: [users[BOT_A]])
    monkeypatch.setattr(discord_api, "get_user", lambda uid, token=None: users.get(str(uid)))


def test_legacy_ids_are_flattened_and_identified(world):
    d = world[OWNER].get(URL).get_json()
    got = {t["id"]: t["status"] for t in d["trusted"]}
    assert got == {BOT_A: "installed", BOT_B: "not_in_server", "444444444444444444": "unresolved"}
    assert d["installed"][0]["trusted"] is True


def test_add_validates_and_remove_touches_only_one(world):
    o = world[OWNER]
    assert o.post(URL, json={"id": "abc"}).status_code == 400
    assert o.post(URL, json={"id": HUMAN}).get_json()["error"] == "not_a_bot"
    assert o.post(URL, json={"id": "555555555555555555"}).get_json()["error"] == "unknown_user"
    r = o.delete(URL + "/" + BOT_B).get_json()
    assert BOT_B not in r["trusted_bot_ids"] and BOT_A in r["trusted_bot_ids"]
    assert BOT_B in o.post(URL, json={"id": BOT_B}).get_json()["trusted_bot_ids"]
    assert o.post(URL, json={"id": BOT_B}).get_json()["trusted_bot_ids"].count(BOT_B) == 1


def test_non_manager_refused(world):
    assert world[STRANGER].get(URL).status_code == 403
    assert world[STRANGER].delete(URL + "/" + BOT_A).status_code == 403
