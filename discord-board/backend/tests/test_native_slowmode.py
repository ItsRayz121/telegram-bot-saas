"""Bulk native Slowmode: live read, multi-channel apply, per-channel outcomes, guild isolation.

Run from discord-board/backend:  python -m pytest tests/test_native_slowmode.py
Discord is faked; nothing leaves the machine.
"""
import os
import sys
import tempfile

_DB = os.path.join(tempfile.mkdtemp(), "slow.db")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB}")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

OWNER, STRANGER = 9181, 9182
G = 9190
URL = "/api/guilds/%d/native-slowmode" % G


class _Resp:
    def __init__(self, status, headers=None):
        self.status_code = status
        self.headers = headers or {}


class _HTTPErr(Exception):
    def __init__(self, status):
        super().__init__(str(status))
        self.response = _Resp(status)


@pytest.fixture(scope="module")
def world():
    import app as appmod
    import auth
    from config import Config
    from database import SessionLocal, init_db
    from models import Guild, User, UserGuild
    init_db()
    db = SessionLocal()
    db.add_all([User(id=OWNER, username="o"), User(id=STRANGER, username="s")])
    db.flush()
    g = Guild(id=G, name="Slow", owner_id=OWNER, plan="free")
    db.add(g)
    db.flush()
    db.add(UserGuild(user_id=OWNER, guild_id=G, can_manage=True, is_owner=True))
    db.commit()
    db.close()

    def client_for(uid):
        c = appmod.app.test_client()
        c.set_cookie(Config.SESSION_COOKIE_NAME, auth._issue_session(uid))
        return c
    return {OWNER: client_for(OWNER), STRANGER: client_for(STRANGER)}


@pytest.fixture()
def discord(monkeypatch):
    import discord_api
    import team_direct
    from models import Guild
    state = {"1": 0, "2": 30, "3": 0}
    fail = {}
    calls = []
    monkeypatch.setattr(Guild, "is_served", property(lambda self: True), raising=False)
    monkeypatch.setattr(team_direct, "bot_token_for", lambda db, guild: "tok")
    monkeypatch.setattr(discord_api, "get_guild_channels", lambda gid, token=None: [
        {"id": "1", "name": "general", "type": 0, "rate_limit_per_user": state["1"], "position": 1},
        {"id": "2", "name": "chat", "type": 0, "rate_limit_per_user": state["2"], "position": 2},
        {"id": "3", "name": "vc", "type": 2, "rate_limit_per_user": state["3"], "position": 3},
        {"id": "4", "name": "forum", "type": 15, "rate_limit_per_user": 0, "position": 4},
    ])

    def fake_set(cid, secs, reason=None, token=None):
        calls.append((str(cid), secs))
        if str(cid) in fail:
            raise _HTTPErr(fail[str(cid)])
        state[str(cid)] = secs
    monkeypatch.setattr(discord_api, "set_channel_slowmode", fake_set)
    return type("D", (), {"state": state, "fail": fail, "calls": calls})


def test_live_read_lists_only_supported_types(world, discord):
    r = world[OWNER].get(URL)
    assert r.status_code == 200
    got = {c["id"]: c["seconds"] for c in r.get_json()["channels"]}
    assert got == {"1": 0, "2": 30, "3": 0}          # forum excluded, live value for #chat


def test_bulk_apply_then_independent_off(world, discord):
    r = world[OWNER].post(URL, json={"channel_ids": ["1", "3"], "seconds": 60})
    assert r.status_code == 200 and all(x["ok"] for x in r.get_json()["results"])
    assert discord.state["1"] == 60 and discord.state["3"] == 60
    r = world[OWNER].post(URL, json={"channel_ids": ["1"], "seconds": 0})
    assert r.status_code == 200 and discord.state["1"] == 0 and discord.state["3"] == 60


def test_partial_failure_is_reported_and_retry_is_safe(world, discord):
    discord.fail["2"] = 403
    r = world[OWNER].post(URL, json={"channel_ids": ["1", "2"], "seconds": 10})
    assert r.status_code == 207
    res = {x["channel_id"]: x for x in r.get_json()["results"]}
    assert res["1"]["ok"] and res["2"] == {"channel_id": "2", "name": "chat", "ok": False,
                                           "error": "missing_permission"}
    discord.fail.clear()
    n = len(discord.calls)
    r = world[OWNER].post(URL, json={"channel_ids": ["1", "2"], "seconds": 10})
    assert r.status_code == 200
    assert len(discord.calls) == n + 1             # #general already 10s → not re-sent


def test_foreign_channel_is_refused_and_input_validated(world, discord):
    r = world[OWNER].post(URL, json={"channel_ids": ["999"], "seconds": 5})
    assert r.get_json()["results"][0]["error"] == "not_in_server" and not discord.calls
    assert world[OWNER].post(URL, json={"channel_ids": ["1"], "seconds": 99999}).status_code == 400
    assert world[OWNER].post(URL, json={"channel_ids": ["x"], "seconds": 5}).status_code == 400
    assert world[OWNER].post(URL, json={"channel_id": "1", "seconds": 5}).status_code == 200  # legacy body


def test_non_manager_is_refused(world, discord):
    assert world[STRANGER].get(URL).status_code == 403
    assert world[STRANGER].post(URL, json={"channel_ids": ["1"], "seconds": 5}).status_code == 403


def test_log_channel_check_flags_public_channels(world, discord, monkeypatch):
    import discord_api
    from database import SessionLocal
    from models import Role
    db = SessionLocal()
    db.add(Role(id=G, guild_id=G, name="@everyone", permissions=str(1 << 10)))   # everyone can view
    db.commit()
    db.close()
    monkeypatch.setattr(discord_api, "get_guild_channels", lambda gid, token=None: [
        {"id": "70", "type": 0, "name": "staff-logs", "permission_overwrites": [
            {"id": str(G), "type": 0, "allow": "0", "deny": str(1 << 10)}]},
        {"id": "71", "type": 0, "name": "general", "permission_overwrites": []},
        {"id": "72", "type": 2, "name": "vc", "permission_overwrites": []}])
    c = world[OWNER]
    chk = "/api/guilds/%d/log-channel/check" % G
    assert c.post(chk, json={"channel_id": "70"}).get_json()["public"] is False
    assert c.post(chk, json={"channel_id": "71"}).get_json()["public"] is True
    assert c.post(chk, json={"channel_id": "72"}).status_code == 400
    assert c.post(chk, json={"channel_id": "99"}).status_code == 404
    assert world[STRANGER].post(chk, json={"channel_id": "70"}).status_code == 403


def test_server_wide_slow_mode_exclusions():
    import slow_mode
    cfg = {"automod": {"slow_mode": {"enabled": True, "exclude_channel_ids": ["5"], "exclude_role_ids": ["9"]}}}
    assert slow_mode.is_excluded(cfg, 5)                              # excluded channel
    assert slow_mode.is_excluded(cfg, 6, role_ids=[1, 9])             # excluded role
    assert slow_mode.is_excluded(cfg, 77, log_channel_ids=[77])       # staff log channel (default on)
    assert not slow_mode.is_excluded(cfg, 6, role_ids=[1])
    cfg["automod"]["slow_mode"]["exclude_log_channels"] = False
    assert not slow_mode.is_excluded(cfg, 77, log_channel_ids=[77])
    assert not slow_mode.is_excluded({"automod": {"slow_mode": {"enabled": False, "exclude_channel_ids": ["5"]}}}, 5)
