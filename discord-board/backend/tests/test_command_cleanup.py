"""Per-command reply cleanup (Guildizer). Run from discord-board/backend:
    python -m pytest tests/test_command_cleanup.py
Throwaway SQLite database; Discord is never contacted (the delete call is faked)."""
import asyncio
import os
import sys
import tempfile
from datetime import datetime, timedelta
from types import SimpleNamespace as NS

os.environ.setdefault("DATABASE_URL", "sqlite:///" + os.path.join(tempfile.mkdtemp(), "cc.db"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

import command_cleanup as cc  # noqa: E402

OWNER, STRANGER = 8801, 8802
GA, GB = 8810, 8811          # two servers: settings must never mix


@pytest.fixture(scope="module")
def world():
    import app as appmod
    import auth
    from config import Config
    from database import SessionLocal, init_db
    from models import Guild, GuildSettings, User, UserGuild
    init_db()
    db = SessionLocal()
    db.add_all([User(id=OWNER, username="o"), User(id=STRANGER, username="s")])
    db.flush()
    for gid in (GA, GB):
        db.add(Guild(id=gid, name=f"G{gid}", owner_id=OWNER, plan="free"))
    db.flush()
    db.add_all([UserGuild(user_id=OWNER, guild_id=gid, can_manage=True, is_owner=True) for gid in (GA, GB)])
    db.add_all([GuildSettings(guild_id=GA, extra={}), GuildSettings(guild_id=GB, extra={})])
    db.commit()
    db.close()

    def client(uid):
        c = appmod.app.test_client()
        c.set_cookie(Config.SESSION_COOKIE_NAME, auth._issue_session(uid))
        return c
    return {OWNER: client(OWNER), STRANGER: client(STRANGER)}


@pytest.fixture(autouse=True)
def clean(monkeypatch, world):
    monkeypatch.delenv("COMMAND_AUTODELETE_ENABLED", raising=False)
    from database import SessionLocal, init_db
    from models import CommandCleanupJob, GuildSettings
    init_db()
    db = SessionLocal()
    db.query(CommandCleanupJob).delete()
    for gid in (GA, GB):
        gs = db.get(GuildSettings, gid)
        if gs:
            gs.extra = {}
    db.commit(); db.close(); SessionLocal.remove()


def jobs():
    from database import SessionLocal
    from models import CommandCleanupJob
    db = SessionLocal()
    try:
        return [(j.id, j.guild_id, j.command, j.bot_ref, j.status, j.deliver_at, j.token, j.last_error)
                for j in db.query(CommandCleanupJob).order_by(CommandCleanupJob.id).all()]
    finally:
        db.close(); SessionLocal.remove()


def make_overdue():
    from database import SessionLocal
    from models import CommandCleanupJob
    db = SessionLocal()
    db.query(CommandCleanupJob).update({"deliver_at": datetime.utcnow() - timedelta(seconds=1)})
    db.commit(); db.close(); SessionLocal.remove()


def set_extra(gid, extra):
    from database import SessionLocal
    from models import GuildSettings
    db = SessionLocal()
    db.get(GuildSettings, gid).extra = extra
    db.commit(); db.close(); SessionLocal.remove()


def inter(gid, app_id=555, token="tok"):
    return NS(guild_id=gid, application_id=app_id, token=token)


def sched(gid, command, **kw):
    return asyncio.run(cc.schedule_for_interaction(inter(gid, **kw), command))


# ── configuration ───────────────────────────────────────────────────────────────

def test_legacy_delays_still_apply_until_a_row_is_saved():
    extra = {"leveling2": {"command_reply_delete_after_seconds": 60, "leaderboard_delete_after_seconds": 20}}
    assert cc.resolve_row(extra, "ask") == {"delete_command": False, "delete_reply": True, "seconds": 60, "enabled": True}
    assert cc.resolve_row(extra, "leaderboard")["seconds"] == 20
    assert cc.resolve_row({}, "rank")["delete_reply"] is False


def test_rows_validate_and_delete_command_is_never_enabled():
    assert cc.normalize_row({"seconds": 10, "delete_command": True})["delete_command"] is False
    for bad in (0, -3, cc.MAX_SECONDS + 1, "x", None):
        with pytest.raises(ValueError):
            cc.normalize_row({"seconds": bad})


def test_apply_table_only_changes_submitted_rows_and_rejects_unknown_commands():
    a = cc.apply_table({}, [{"command": "/rank", "seconds": 10}, {"command": "/leaderboard", "seconds": 60, "delete_reply": False}])
    b = cc.apply_table(a, [{"command": "/rank", "seconds": 15}])
    assert b["command_table"]["rank"]["seconds"] == 15 and b["command_table"]["leaderboard"]["seconds"] == 60
    assert b["command_table"]["leaderboard"]["delete_reply"] is False
    with pytest.raises(ValueError):
        cc.apply_table({}, [{"command": "/nope"}])       # unknown commands are rejected
    assert cc.apply_table({}, [{"command": "/hello", "seconds": 5}], custom_names=["hello"])["command_table"]["hello"]


# ── scheduling / independence ───────────────────────────────────────────────────

def test_job_is_scheduled_at_the_configured_deadline_per_command_and_server():
    set_extra(GA, {"command_table": {"rank": {"delete_reply": True, "seconds": 10, "enabled": True},
                                     "leaderboard": {"delete_reply": True, "seconds": 60, "enabled": True}}})
    set_extra(GB, {"command_table": {"rank": {"delete_reply": True, "seconds": 120, "enabled": True}}})
    now = datetime.utcnow()
    for gid, cmd in ((GA, "rank"), (GA, "leaderboard"), (GB, "rank")):
        assert sched(gid, cmd) is not None
    by = {(j[1], j[2]): (j[5] - now).total_seconds() for j in jobs()}
    assert 9 < by[(GA, "rank")] < 12 and 59 < by[(GA, "leaderboard")] < 62 and 119 < by[(GB, "rank")] < 122


def test_nothing_scheduled_when_reply_deletion_is_off_or_kill_switch(monkeypatch):
    assert sched(GA, "rank") is None                                     # nothing configured
    set_extra(GA, {"command_table": {"rank": {"delete_reply": False, "seconds": 30, "enabled": True}}})
    assert sched(GA, "rank") is None
    set_extra(GA, {"command_table": {"rank": {"delete_reply": True, "seconds": 30, "enabled": True}}})
    monkeypatch.setenv("COMMAND_AUTODELETE_ENABLED", "0")
    assert sched(GA, "rank") is None and jobs() == []
    assert asyncio.run(cc.schedule_for_interaction(inter(None), "rank")) is None      # DMs


def test_official_and_custom_bots_get_their_own_identity_on_the_job():
    set_extra(GA, {"command_table": {"rank": {"delete_reply": True, "seconds": 30, "enabled": True}}})
    sched(GA, "rank", app_id=111)
    sched(GA, "rank", app_id=222)
    assert [j[3] for j in jobs()] == ["111", "222"]


# ── execution, races, recovery ──────────────────────────────────────────────────

class Deleter:
    def __init__(self, outcome="done"):
        self.calls, self.outcome = [], outcome

    async def __call__(self, app_id, token):
        self.calls.append((app_id, token))
        return self.outcome


def test_job_runs_only_when_due_and_only_once():
    set_extra(GA, {"command_table": {"rank": {"delete_reply": True, "seconds": 30, "enabled": True}}})
    jid = sched(GA, "rank")
    d = Deleter()

    async def go():
        await cc.execute(jid, d)            # not due: nothing
        assert d.calls == []
        make_overdue()
        await asyncio.gather(cc.execute(jid, d), cc.execute(jid, d))   # two workers race for it
    asyncio.run(go())
    assert d.calls == [("555", "tok")]
    (j,) = jobs()
    assert j[4] == "done" and j[6] is None           # interaction token wiped after use


def test_pending_jobs_are_recovered_after_a_restart(monkeypatch):
    set_extra(GA, {"command_table": {"rank": {"delete_reply": True, "seconds": 30, "enabled": True}}})
    sched(GA, "rank", app_id=111)
    sched(GA, "rank", app_id=222)
    make_overdue()
    d = Deleter()
    monkeypatch.setattr(cc, "_delete_original", d)           # the "new process" uses the real executor path
    assert asyncio.run(cc.sweep_once("111")) == 1            # only this bot's jobs
    assert d.calls == [("111", "tok")]
    assert [j[4] for j in jobs()] == ["done", "pending"]


def test_expired_interactions_and_flaky_network_are_handled():
    set_extra(GA, {"command_table": {"rank": {"delete_reply": True, "seconds": 30, "enabled": True}}})
    j1, j2 = sched(GA, "rank"), sched(GA, "rank")
    make_overdue()
    asyncio.run(cc.execute(j1, Deleter("expired")))
    asyncio.run(cc.execute(j2, Deleter("retry")))
    st = {j[0]: j for j in jobs()}
    assert st[j1][4] == "failed" and "expired" in st[j1][7]
    assert st[j2][4] == "pending" and st[j2][5] > datetime.utcnow()          # backed off, will retry
    make_overdue()
    asyncio.run(cc.execute(j2, Deleter("skip")))                                # ephemeral: left alone
    assert {j[0]: j for j in jobs()}[j2][4] == "done"


def test_kill_switch_stops_execution(monkeypatch):
    set_extra(GA, {"command_table": {"rank": {"delete_reply": True, "seconds": 30, "enabled": True}}})
    jid = sched(GA, "rank")
    make_overdue()
    monkeypatch.setenv("COMMAND_AUTODELETE_ENABLED", "0")
    d = Deleter()
    asyncio.run(cc.execute(jid, d))
    assert d.calls == [] and jobs()[0][4] == "pending"


def test_ephemeral_reply_is_skipped_by_the_http_executor(monkeypatch):
    class Resp:
        def __init__(self, status, body=None):
            self.status, self._b = status, body or {}
        async def json(self, content_type=None): return self._b
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

    class Session:
        def __init__(self, flags): self.flags, self.deleted = flags, False
        def get(self, url): return Resp(200, {"flags": self.flags})
        def delete(self, url):
            self.deleted = True
            return Resp(204)
    private, public = Session(64), Session(0)
    assert asyncio.run(cc._delete_original("1", "t", session=private)) == "skip" and not private.deleted
    assert asyncio.run(cc._delete_original("1", "t", session=public)) == "done" and public.deleted


# ── status switch + API ─────────────────────────────────────────────────────────

def test_status_off_is_visible_to_the_command_gate():
    set_extra(GA, {"command_table": {"rank": {"delete_reply": True, "seconds": 30, "enabled": False}}})
    assert cc.command_enabled(GA, "rank") is False and cc.command_enabled(GA, "ask") is True
    assert cc.command_enabled(GB, "rank") is True and cc.command_enabled(None, "rank") is True


def test_api_roundtrip_isolation_and_permissions(world):
    owner, stranger = world[OWNER], world[STRANGER]
    url = lambda g: f"/api/guilds/{g}/command-table"
    assert stranger.get(url(GA)).status_code == 403
    assert stranger.put(url(GA), json={"commands": []}).status_code == 403

    got = owner.get(url(GA)).get_json()
    assert got["limits"]["can_delete_command"] is False and got["limits"]["max_seconds"] == cc.MAX_SECONDS
    rows = {r["command"]: r for r in got["commands"]}
    assert rows["/rank"]["delete_reply"] is False and rows["/rank"]["configured"] is False

    put = owner.put(url(GA), json={"commands": [
        {"command": "/rank", "delete_reply": True, "seconds": 10, "enabled": True},
        {"command": "/leaderboard", "delete_reply": True, "seconds": 60, "enabled": False}]})
    assert put.status_code == 200
    again = {r["command"]: r for r in owner.get(url(GA)).get_json()["commands"]}      # "reload"
    assert again["/rank"]["seconds"] == 10 and again["/leaderboard"]["seconds"] == 60
    assert again["/leaderboard"]["enabled"] is False and again["/ask"]["configured"] is False
    other = {r["command"]: r for r in owner.get(url(GB)).get_json()["commands"]}
    assert other["/rank"]["seconds"] == 30 and other["/rank"]["configured"] is False   # other server untouched

    assert owner.put(url(GA), json={"commands": [{"command": "/rank", "seconds": 0}]}).status_code == 400
    assert owner.put(url(GA), json={"commands": [{"command": "/nope"}]}).status_code == 400
    assert cc.resolve_row(__import__("database").SessionLocal().get(__import__("models").GuildSettings, GA).extra, "rank")["seconds"] == 10
    # the backend executor now uses the saved value for future invocations
    assert 9 < (jobs_after(GA, "rank")) < 12


def jobs_after(gid, command):
    now = datetime.utcnow()
    asyncio.run(cc.schedule_for_interaction(inter(gid), command))
    return (jobs()[-1][5] - now).total_seconds()
