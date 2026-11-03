"""Guildizer team access: viewer role, kill switches, direct (DM) invites.

Run from discord-board/backend:  python -m pytest tests/test_team_access.py
Throwaway SQLite database and forged session cookies; Discord is never contacted (DM send is patched).
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta

_DB = os.path.join(tempfile.mkdtemp(), "team.db")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB}")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

OWNER, VIEWER, MANAGER, STRANGER, ALICE, BOB = 9971, 9972, 9973, 9974, 9975, 9976
G = 9980
H = "/api/guilds/%d/team" % G


@pytest.fixture(scope="module")
def world():
    import app as appmod
    import auth
    from config import Config
    from database import SessionLocal, init_db
    from models import Guild, GuildTeamMember, Member, User, UserGuild
    init_db()
    db = SessionLocal()
    db.add_all([User(id=u, username=n) for u, n in
                ((OWNER, "owner"), (VIEWER, "vera"), (MANAGER, "max"), (STRANGER, "stan"),
                 (ALICE, "alice_member"), (BOB, "bob_member"))])
    db.flush()
    db.add(Guild(id=G, name="Team Server", owner_id=OWNER, plan="free"))
    db.flush()
    db.add(UserGuild(user_id=OWNER, guild_id=G, can_manage=True, is_owner=True))
    db.add_all([GuildTeamMember(guild_id=G, user_id=VIEWER, username="vera", role="viewer"),
                GuildTeamMember(guild_id=G, user_id=MANAGER, username="max", role="manager")])
    db.add_all([Member(guild_id=G, user_id=ALICE, username="alice_member"),
                Member(guild_id=G, user_id=BOB, username="bob_member"),
                Member(guild_id=G, user_id=OWNER, username="owner")])
    db.commit()
    db.close()

    def client_for(uid):
        c = appmod.app.test_client()
        c.set_cookie(Config.SESSION_COOKIE_NAME, auth._issue_session(uid))
        return c
    return {u: client_for(u) for u in (OWNER, VIEWER, MANAGER, STRANGER)}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.delenv("GUILD_TEAM_ACCESS_ENABLED", raising=False)
    monkeypatch.delenv("GUILD_TEAM_DIRECT_INVITES_ENABLED", raising=False)


@pytest.fixture()
def dm(monkeypatch):
    import team_direct
    sent = []
    result = {"ok": True}

    def fake(token, user_id, payload):
        sent.append((user_id, payload))
        return (True, None) if result["ok"] else (False, "They have DMs from server members turned off.")
    monkeypatch.setattr(team_direct, "send_dm", fake)
    monkeypatch.setattr(team_direct, "bot_token_for", lambda db, guild: "tok")
    return type("DM", (), {"sent": sent, "result": result})


def _clean_invites():
    from database import SessionLocal
    from models import GuildTeamMember, TeamInvite
    db = SessionLocal()
    db.query(TeamInvite).delete()
    db.query(GuildTeamMember).filter(GuildTeamMember.user_id.in_((ALICE, BOB))).delete(synchronize_session=False)
    db.commit()
    db.close()
    SessionLocal.remove()


# ── viewer is read-only ────────────────────────────────────────────────────────
def test_viewer_can_read_but_not_write_and_never_sees_codes(world):
    owner, viewer = world[OWNER], world[VIEWER]
    assert owner.post(H + "/invites", json={"role": "manager"}).status_code == 201
    r = viewer.get(H)
    assert r.status_code == 200
    d = r.get_json()
    assert d["your_role"] == "viewer" and d["invites"] == [] and d["direct_invites"] == []
    assert viewer.post(H + "/invites", json={"role": "manager"}).status_code == 403
    assert viewer.delete(H + "/members/%d" % MANAGER).status_code == 403
    assert viewer.patch(H + "/members/%d" % MANAGER, json={"role": "viewer"}).status_code == 403
    assert owner.get(H).get_json()["invites"]          # the owner still sees the code
    _clean_invites()


def test_manager_can_write_and_a_stranger_gets_nothing(world):
    assert world[MANAGER].post(H + "/invites", json={"role": "viewer"}).status_code == 201
    assert world[STRANGER].get(H).status_code == 403
    _clean_invites()


def test_viewer_is_read_only_on_other_endpoints_too(world):
    assert world[VIEWER].get("/api/guilds/%d" % G).status_code == 200
    assert world[VIEWER].post("/api/guilds/%d/resync" % G).status_code == 403


# ── kill switch ────────────────────────────────────────────────────────────────
def test_kill_switch_locks_out_team_seats_but_not_discord_managers(world, monkeypatch):
    monkeypatch.setenv("GUILD_TEAM_ACCESS_ENABLED", "0")
    assert world[VIEWER].get(H).status_code == 403
    assert world[MANAGER].get(H).status_code == 403
    assert world[OWNER].get(H).status_code == 200
    assert world[OWNER].post(H + "/invites", json={"role": "manager"}).status_code == 503
    assert world[STRANGER].post("/api/team/redeem", json={"code": "x"}).status_code == 503
    assert world[OWNER].get(H).get_json()["enabled"] is False


# ── access codes carry a role ──────────────────────────────────────────────────
def test_a_viewer_code_creates_a_viewer_seat(world):
    code = world[OWNER].post(H + "/invites", json={"role": "viewer"}).get_json()["invite"]["code"]
    assert world[STRANGER].post("/api/team/redeem", json={"code": code}).status_code == 200
    seat = [m for m in world[OWNER].get(H).get_json()["members"] if m["user_id"] in (STRANGER, str(STRANGER))]
    assert seat and seat[0]["role"] == "viewer"
    assert world[STRANGER].post(H + "/invites", json={}).status_code == 403     # now a read-only viewer
    from database import SessionLocal
    from models import GuildTeamMember
    db = SessionLocal()
    db.query(GuildTeamMember).filter_by(guild_id=G, user_id=STRANGER).delete()
    db.commit(); db.close(); SessionLocal.remove()
    _clean_invites()


def test_bad_role_is_refused(world):
    assert world[OWNER].post(H + "/invites", json={"role": "admin"}).status_code == 400
    assert world[OWNER].post(H + "/invites/direct", json={"role": "admin", "discord_user_id": str(ALICE)}).status_code == 400


# ── direct invites ─────────────────────────────────────────────────────────────
def test_candidates_search_members_and_skip_managers(world):
    owner = world[OWNER]
    names = {m["username"] for m in owner.get(H + "/candidates?q=member").get_json()["members"]}
    assert names == {"alice_member", "bob_member"}
    assert owner.get(H + "/candidates?q=a").get_json()["members"] == []         # too short
    assert owner.get(H + "/candidates?q=owner").get_json()["members"] == []     # yourself is not offered


def test_direct_invite_sends_dm_with_buttons_and_hides_the_code(world, dm):
    r = world[OWNER].post(H + "/invites/direct", json={"discord_user_id": str(ALICE), "role": "viewer"})
    assert r.status_code == 201
    inv = r.get_json()["invite"]
    assert inv["code"] is None and inv["direct"] and inv["status"] == "pending" and inv["role"] == "viewer"
    user_id, payload = dm.sent[0]
    assert user_id == ALICE
    ids = [b["custom_id"] for b in payload["components"][0]["components"]]
    assert ids == ["gti:a:%d" % inv["id"], "gti:r:%d" % inv["id"]]
    d = world[OWNER].get(H).get_json()
    assert d["invites"] == [] and len(d["direct_invites"]) == 1                # not listed as an access code
    assert world[OWNER].post(H + "/invites/direct", json={"discord_user_id": str(ALICE)}).status_code == 409
    _clean_invites()


def test_direct_invite_refusals_and_failed_dm_leaves_no_row(world, dm):
    owner = world[OWNER]
    assert owner.post(H + "/invites/direct", json={"discord_user_id": "123"}).status_code == 400            # not a member
    assert owner.post(H + "/invites/direct", json={"discord_user_id": str(OWNER)}).status_code == 400       # yourself
    assert owner.post(H + "/invites/direct", json={"discord_user_id": "abc"}).status_code == 400
    assert world[VIEWER].post(H + "/invites/direct", json={"discord_user_id": str(ALICE)}).status_code == 403
    dm.result["ok"] = False
    r = owner.post(H + "/invites/direct", json={"discord_user_id": str(BOB)})
    assert r.status_code == 502 and "DMs" in r.get_json()["message"]
    assert owner.get(H).get_json()["direct_invites"] == []
    dm.result["ok"] = True
    assert owner.post(H + "/invites/direct", json={"discord_user_id": str(BOB)}).status_code == 201          # retry works
    _clean_invites()


def test_direct_invites_have_their_own_kill_switch(world, dm, monkeypatch):
    monkeypatch.setenv("GUILD_TEAM_DIRECT_INVITES_ENABLED", "0")
    r = world[OWNER].post(H + "/invites/direct", json={"discord_user_id": str(ALICE)})
    assert r.status_code == 503 and not dm.sent
    assert world[OWNER].get(H).get_json()["direct_enabled"] is False


def test_a_direct_invite_cannot_be_redeemed_by_code(world, dm):
    from database import SessionLocal
    from models import TeamInvite
    world[OWNER].post(H + "/invites/direct", json={"discord_user_id": str(ALICE)})
    db = SessionLocal()
    code = db.query(TeamInvite).filter(TeamInvite.invitee_discord_id == ALICE).one().code
    db.close(); SessionLocal.remove()
    assert world[STRANGER].post("/api/team/redeem", json={"code": code}).status_code == 404
    _clean_invites()


def test_owner_can_change_a_member_role(world):
    assert world[OWNER].patch(H + "/members/%d" % MANAGER, json={"role": "viewer"}).status_code == 200
    assert world[MANAGER].post(H + "/invites", json={}).status_code == 403
    assert world[OWNER].patch(H + "/members/%d" % MANAGER, json={"role": "manager"}).status_code == 200
    assert world[OWNER].patch(H + "/members/1", json={"role": "viewer"}).status_code == 404
    assert world[OWNER].patch(H + "/members/%d" % MANAGER, json={"role": "boss"}).status_code == 400


# ── the button press ───────────────────────────────────────────────────────────
def _invite(world, dm, who=ALICE, role="manager"):
    return world[OWNER].post(H + "/invites/direct", json={"discord_user_id": str(who), "role": role}).get_json()["invite"]["id"]


def _respond(inv_id, uid, accept=True):
    import team_direct
    from database import SessionLocal
    db = SessionLocal()
    try:
        return team_direct.respond(db, inv_id, uid, "alice", accept)
    finally:
        db.close(); SessionLocal.remove()


def test_accept_creates_the_seat_once(world, dm):
    inv = _invite(world, dm, role="viewer")
    status, info = _respond(inv, ALICE)
    assert status == "ok" and info["role"] == "viewer"
    seat = [m for m in world[OWNER].get(H).get_json()["members"] if m["user_id"] in (ALICE, str(ALICE))]
    assert seat and seat[0]["role"] == "viewer"
    status, info = _respond(inv, ALICE)
    assert status == "gone" and info["reason"] == "accepted"
    _clean_invites()


def test_only_the_invitee_can_answer_and_decline_grants_nothing(world, dm):
    inv = _invite(world, dm)
    assert _respond(inv, BOB)[0] == "not_you"
    assert _respond(inv, ALICE, accept=False)[0] == "declined"
    assert _respond(inv, ALICE)[0] == "gone"
    d = world[OWNER].get(H).get_json()
    assert [i["status"] for i in d["invitations"]] == ["declined"] and d["direct_invites"] == []
    assert not [m for m in d["members"] if m["user_id"] in (ALICE, str(ALICE))]
    _clean_invites()


def test_expired_and_kill_switched_invites_grant_nothing(world, dm, monkeypatch):
    from database import SessionLocal
    from models import TeamInvite
    inv = _invite(world, dm)
    db = SessionLocal()
    db.get(TeamInvite, inv).expires_at = datetime.utcnow() - timedelta(minutes=1)
    db.commit(); db.close(); SessionLocal.remove()
    status, info = _respond(inv, ALICE)
    assert status == "gone" and info["reason"] == "expired"
    _clean_invites()
    inv2 = _invite(world, dm, who=BOB)
    monkeypatch.setenv("GUILD_TEAM_DIRECT_INVITES_ENABLED", "0")
    assert _respond(inv2, BOB)[0] == "disabled"
    _clean_invites()


def test_reply_text_explains_each_outcome():
    import team_direct as td
    assert "expired" in td.reply_text("gone", {"reason": "expired"})
    assert "already accepted" in td.reply_text("gone", {"reason": "accepted"})
    assert "not for you" in td.reply_text("not_you", {})
    assert "Viewer" in td.reply_text("ok", {"role": "viewer", "guild_name": "S"})
    assert "no longer valid" in td.reply_text("gone", {})
