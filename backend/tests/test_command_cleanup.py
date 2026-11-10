"""Per-command cleanup (Telegram): configuration, persisted jobs, scheduling, recovery, isolation.
Run: python -m pytest backend/tests/test_command_cleanup.py
Telegram is faked; the job store is the REAL DbStore on an in-memory SQLite database."""
import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace as NS

import pytest
from flask import Flask

from backend import command_cleanup as cc
from backend import command_table as ct
from backend.models import db, CommandCleanupJob


# ── configuration ───────────────────────────────────────────────────────────────

def test_command_name_parsing():
    assert cc.command_name("/rank") == "rank"
    assert cc.command_name("/Leaderboard@MyBot extra words") == "leaderboard"
    assert cc.command_name("hello") is None and cc.command_name(None) is None and cc.command_name("/") is None


def test_unsaved_groups_keep_their_old_behaviour():
    assert cc.resolve_row({}, "xp") == {"delete_command": False, "delete_reply": False, "seconds": 30, "enabled": True}
    legacy = {"auto_clean": {"rank_reply_delete_seconds": 10, "command_reply_delete_seconds": 60, "delete_commands": True}}
    assert cc.resolve_row(legacy, "rank") == {"delete_command": True, "delete_reply": True, "seconds": 10, "enabled": True}
    assert cc.resolve_row(legacy, "help")["seconds"] == 60
    assert cc.resolve_row({"auto_clean": {"delete_commands": True}}, "xp")["delete_reply"] is False


def test_saved_row_wins_over_legacy_and_commands_are_independent():
    s = {"auto_clean": {"rank_reply_delete_seconds": 99},
         "command_table": {"xp": {"delete_command": True, "delete_reply": True, "seconds": 10, "enabled": True},
                           "rank": {"delete_command": False, "delete_reply": True, "seconds": 45, "enabled": True}}}
    assert cc.resolve_row(s, "xp")["seconds"] == 10
    assert cc.resolve_row(s, "rank") == {"delete_command": False, "delete_reply": True, "seconds": 45, "enabled": True}
    assert cc.resolve_row(s, "leaderboard")["seconds"] == 99      # untouched row falls back to legacy


def test_role_is_an_alias_of_roles():
    assert cc.canon("/role") == "roles"
    s = {"command_table": {"roles": {"delete_command": True, "delete_reply": True, "seconds": 7, "enabled": True}}}
    assert cc.resolve_row(s, "role")["seconds"] == 7


@pytest.mark.parametrize("bad", [0, -1, 86401, "abc", None])
def test_invalid_seconds_are_rejected(bad):
    with pytest.raises(ValueError):
        cc.normalize_row({"seconds": bad})


def test_status_off_disables_the_command():
    s = {"command_table": {"xp": {"enabled": False, "seconds": 30, "delete_command": True, "delete_reply": True}}}
    assert cc.is_command_enabled(s, "/xp") is False and cc.is_command_enabled(s, "rank") is True
    from backend.bot_manager import _is_command_allowed
    assert _is_command_allowed(s, "/xp", None) is False and _is_command_allowed(s, "/rank", None) is True


def test_apply_table_changes_only_the_submitted_command():
    base = ct.apply_table({}, [{"command": "/xp", "seconds": 10}, {"command": "/rank", "seconds": 45, "delete_command": False}])
    assert base["command_table"]["xp"]["seconds"] == 10
    again = ct.apply_table(base, [{"command": "/xp", "seconds": 20, "scope": "specific_topics", "topic_ids": [5]}])
    assert again["command_table"]["xp"]["seconds"] == 20
    assert again["command_table"]["rank"] == {"delete_command": False, "delete_reply": True, "seconds": 45, "enabled": True}
    assert again["command_routing"]["commands"]["/xp"] == {"scope": "specific_topics", "topic_ids": ["5"]}
    rows = {r["command"]: r for r in ct.build_table(again)["commands"]}
    assert rows["/xp"]["seconds"] == 20 and rows["/rank"]["seconds"] == 45 and rows["/leaderboard"]["configured"] is False
    with pytest.raises(ValueError):
        ct.apply_table({}, [{"command": "/nope"}])
    with pytest.raises(ValueError):
        ct.apply_table({}, [{"command": "/xp", "seconds": 0}])


# ── persisted jobs ──────────────────────────────────────────────────────────────

class FakeBot:
    def __init__(self, bot_id="111", fail=None):
        self.token = f"{bot_id}:SECRET"
        self.deleted, self.fail = [], fail or {}

    async def delete_message(self, chat_id, message_id):
        err = self.fail.get(message_id)
        if err:
            raise err
        self.deleted.append((chat_id, message_id))


@pytest.fixture
def env(monkeypatch):
    monkeypatch.delenv("COMMAND_AUTODELETE_ENABLED", raising=False)
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI="sqlite://", SQLALCHEMY_TRACK_MODIFICATIONS=False)
    db.init_app(app)
    with app.app_context():
        CommandCleanupJob.__table__.create(db.engine)
    monkeypatch.setitem(cc._state, "app", app)
    monkeypatch.setitem(cc._state, "store", None)
    monkeypatch.setitem(cc._state, "identity", {})
    settings = {}
    monkeypatch.setattr(cc, "_settings_for_chat", lambda chat_id, bot=None: settings.get(str(chat_id), {}))

    def jobs():
        with app.app_context():
            return [(j.id, j.command, j.scope_id, j.bot_ref, list(j.message_ids), j.status, j.deliver_at, j.last_error)
                    for j in CommandCleanupJob.query.order_by(CommandCleanupJob.id).all()]

    def make_overdue():
        with app.app_context():
            CommandCleanupJob.query.update({"deliver_at": datetime.utcnow() - timedelta(seconds=1)})
            db.session.commit()
    return NS(app=app, settings=settings, jobs=jobs, make_overdue=make_overdue)


def row(**kw):
    return {"delete_command": True, "delete_reply": True, "seconds": 30, "enabled": True, **kw}


def table(**cmds):
    return {"command_table": cmds}


async def run_command(bot, cmd="/xp", chat=-100, replies=(50,), cmd_id=11):
    """Drive the real command scope: _begin -> reply(ies) through the send hook -> finish."""
    class FakeBotCls:
        token = bot.token
        async def send_message(self, chat_id, text):
            return NS(message_id=replies[self.n]) if False else None
    msg = NS(text=cmd, chat=NS(id=chat, type="supergroup"), message_id=cmd_id, get_bot=lambda: bot)
    state = await cc._begin(NS(effective_message=msg))
    if state is None:
        return None
    for rid in replies:
        await cc._register(state, [rid])
    if not replies:
        await cc._register(state, None)
    return state


def test_both_toggles_one_job_one_deadline(env):
    env.settings["-100"] = table(xp=row(seconds=30))
    bot = FakeBot()
    before = datetime.utcnow()
    asyncio.run(run_command(bot, replies=(50, 51)))
    (jid, cmd, scope, ref, ids, status, due, _), = env.jobs()
    assert (cmd, scope, ref, status) == ("xp", "-100", "111", "pending")
    assert ids == [11, 50, 51]
    assert timedelta(seconds=29) < due - before < timedelta(seconds=32)


def test_only_selected_message_types_are_deleted(env):
    env.settings["-100"] = table(xp=row(delete_command=False), rank=row(delete_reply=False), help=row(delete_command=False, delete_reply=False))
    bot = FakeBot()
    asyncio.run(run_command(bot, "/xp"))
    asyncio.run(run_command(bot, "/rank", replies=(60,), cmd_id=12))
    asyncio.run(run_command(bot, "/help", replies=(70,), cmd_id=13))
    ids = {j[1]: j[4] for j in env.jobs()}
    assert ids == {"xp": [50], "rank": [12]}          # help: both off -> no job at all


def test_command_without_reply_uses_completion_time(env):
    env.settings["-100"] = table(xp=row(seconds=5))
    asyncio.run(run_command(FakeBot(), replies=()))
    assert [j[4] for j in env.jobs()] == [[11]]


def test_commands_have_independent_delays_and_chats_and_bots_are_isolated(env):
    env.settings["-100"] = table(xp=row(seconds=10), rank=row(seconds=60))
    env.settings["-200"] = table(xp=row(seconds=600))
    a, b = FakeBot("111"), FakeBot("222")
    now = datetime.utcnow()
    asyncio.run(run_command(a, "/xp", -100))
    asyncio.run(run_command(a, "/rank", -100))
    asyncio.run(run_command(b, "/xp", -200))
    by = {(j[1], j[2], j[3]): (j[6] - now).total_seconds() for j in env.jobs()}
    assert 9 < by[("xp", "-100", "111")] < 12
    assert 59 < by[("rank", "-100", "111")] < 62
    assert 599 < by[("xp", "-200", "222")] < 602


def test_disabled_or_default_setups_schedule_nothing(env):
    assert asyncio.run(run_command(FakeBot())) is None          # no table, no legacy settings
    env.settings["-100"] = table(start=row())
    assert asyncio.run(run_command(FakeBot(), "/start")) is None     # setup flows are never touched


def test_kill_switch_stops_everything(env, monkeypatch):
    env.settings["-100"] = table(xp=row())
    monkeypatch.setenv("COMMAND_AUTODELETE_ENABLED", "0")
    assert asyncio.run(run_command(FakeBot())) is None


def test_job_runs_at_the_deadline_with_the_sending_bot(env):
    env.settings["-100"] = table(xp=row(seconds=30))
    bot = FakeBot()
    asyncio.run(run_command(bot))
    async def go():
        await cc._execute(bot, 1)               # not due yet: nothing happens
        assert bot.deleted == []
        env.make_overdue()
        await cc._execute(bot, 1)
        await cc._execute(bot, 1)               # a second worker racing for the same job: nothing
    asyncio.run(go())
    assert bot.deleted == [(-100, 11), (-100, 50)]
    assert env.jobs()[0][5] == "done"


def test_pending_jobs_survive_a_restart_and_the_sweeper_runs_them(env):
    env.settings["-100"] = table(xp=row(seconds=30))
    asyncio.run(run_command(FakeBot("111")))
    env.make_overdue()
    cc._state["store"] = None                     # "restart": brand new process state
    other, bot = FakeBot("222"), FakeBot("111")
    async def go():
        assert await cc.sweep_once(other) == 0    # another bot's jobs are not ours
        assert await cc.sweep_once(bot) == 1
    asyncio.run(go())
    assert bot.deleted == [(-100, 11), (-100, 50)] and other.deleted == []


def test_crashed_worker_lease_expires_and_job_is_recovered(env):
    env.settings["-100"] = table(xp=row())
    asyncio.run(run_command(FakeBot()))
    env.make_overdue()
    store = cc._store()
    assert store.claim(1) is not None and store.claim(1) is None      # claimed: nobody else can take it
    with env.app.app_context():
        CommandCleanupJob.query.update({"claimed_until": datetime.utcnow() - timedelta(seconds=1)})
        db.session.commit()
    bot = FakeBot()
    asyncio.run(cc.sweep_once(bot))
    assert bot.deleted == [(-100, 11), (-100, 50)]


def test_missing_delete_right_is_recorded_and_does_not_raise(env):
    from telegram.error import BadRequest
    env.settings["-100"] = table(xp=row())
    bot = FakeBot(fail={11: BadRequest("Not enough rights to delete a message"), 50: BadRequest("Not enough rights")})
    asyncio.run(run_command(bot))
    env.make_overdue()
    asyncio.run(cc._execute(bot, 1))
    j, = env.jobs()
    assert j[5] == "failed" and "Delete messages" in j[7]


def test_already_deleted_messages_are_fine_and_network_errors_retry(env):
    from telegram.error import BadRequest, NetworkError
    env.settings["-100"] = table(xp=row())
    bot = FakeBot(fail={11: BadRequest("Message to delete not found"), 50: NetworkError("boom")})
    asyncio.run(run_command(bot))
    env.make_overdue()
    asyncio.run(cc._execute(bot, 1))
    j, = env.jobs()
    assert j[5] == "pending" and j[4] == [50]           # only the retryable one is left
    env.make_overdue()
    bot.fail = {}
    asyncio.run(cc._execute(bot, 1))
    assert env.jobs()[0][5] == "done" and bot.deleted == [(-100, 50)]


def test_a_late_reply_gets_its_own_short_job(env):
    env.settings["-100"] = table(xp=row())
    bot = FakeBot()
    async def go():
        state = await run_command(bot, replies=(50,))
        env.make_overdue()
        await cc._execute(bot, 1)               # first job ran
        await cc._register(state, [51])         # the handler sends one more message afterwards
    asyncio.run(go())
    jobs = env.jobs()
    assert [j[4] for j in jobs] == [[], [51]] or [j[4] for j in jobs][1] == [51]
    assert jobs[1][5] == "pending"


def test_same_chat_two_bots_use_their_own_group_row(env, monkeypatch):
    """Custom bot -> its Group row, official -> TelegramGroup: resolved by the bot identity."""
    seen = []
    monkeypatch.setattr(cc, "_settings_for_chat", lambda chat_id, bot=None: seen.append(cc._bot_ref(bot)) or {})
    cc._row_for(-100, "xp", FakeBot("111"))
    cc._row_for(-100, "xp", FakeBot("222"))
    assert seen == ["111", "222"]


def test_install_wraps_reply_methods_once_and_returns_the_sent_message(env):
    env.settings["-100"] = table(help=row(seconds=5))
    cc._state["installed"] = False
    bot = FakeBot()

    class FakeMessage:
        text, chat, message_id = "/help", NS(id=-100, type="group"), 11
        def get_bot(self): return bot
        async def reply_text(self, text): return NS(message_id=33, text=text)

    cc.install(None, message_cls=FakeMessage)
    cc.install(None, message_cls=FakeMessage)              # second call must not double-wrap

    async def go():
        sent = await FakeMessage().reply_text("hi")
        pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task() and t.get_coro().__name__ == "after_reply"]
        await asyncio.gather(*pending)
        return sent
    assert asyncio.run(go()).message_id == 33
    assert [j[4] for j in env.jobs()] == [[11, 33]]
    cc._state["installed"] = False


def test_scope_via_bot_send_message_and_no_leak(env):
    env.settings["-100"] = table(xp=row(seconds=5))
    sent_log = []

    class FakeBotCls:
        token = "111:X"
        async def send_message(self, chat_id, text): return NS(message_id=50)

    class FakeHandler:
        async def handle_update(self, update, *a, **k):
            await bot.send_message(chat_id=update.send_to, text="answer")
            return "handled"

    cc._install_send_hooks(FakeBotCls)
    cc._install_command_scope(FakeHandler)
    bot = FakeBotCls()
    msg = NS(text="/xp", chat=NS(id=-100, type="supergroup"), message_id=11, get_bot=lambda: bot)

    async def go(send_to):
        return await FakeHandler().handle_update(NS(effective_message=msg, send_to=send_to))
    assert asyncio.run(go(-100)) == "handled"
    assert [j[4] for j in env.jobs()] == [[11, 50]] and cc._current.get() is None
    asyncio.run(go(999))                                   # reply to another chat: only the command is cleaned
    assert [j[4] for j in env.jobs()][1] == [11]


# ── generic gate: Status + topic access apply to every command ────────────────────

def test_gate_blocks_status_off_and_wrong_topic_for_any_command():
    s = {"command_table": {"ban": {"enabled": False, "seconds": 30, "delete_command": False, "delete_reply": False}},
         "command_routing": {"commands": {"/verify": {"scope": "specific_topics", "topic_ids": ["7"]}}}}
    assert cc.blocked_by_table(s, "ban", None) is True
    assert cc.blocked_by_table(s, "kick", None) is False
    assert cc.blocked_by_table(s, "verify", 7) is False and cc.blocked_by_table(s, "verify", 8) is True
    assert cc.blocked_by_table(s, "verify", None) is True


def test_gate_never_touches_setup_or_self_gated_commands():
    s = {"command_table": {"start": {"enabled": False}, "xp": {"enabled": False}}}
    assert cc.blocked_by_table(s, "start", None) is False and cc.blocked_by_table(s, "xp", None) is False


def test_table_lists_moderation_and_verify_commands():
    names = {r["command"] for r in ct.build_table({})["commands"]}
    assert {"/verify", "/ban", "/warn", "/mute", "/kick"} <= names
    assert ct.apply_table({}, [{"command": "/ban", "seconds": 5, "enabled": False}])["command_table"]["ban"]["enabled"] is False
    assert ct.build_table({}, ["hello"])["commands"][-1]["command"] == "/hello"
    assert ct.apply_table({}, [{"command": "/hello", "seconds": 5}], ["hello"])["command_table"]["hello"]


def test_custom_bot_group_custom_commands_are_listed():
    assert ct.build_table({}, ["promo"])["commands"][-1] == {**ct.build_table({}, ["promo"])["commands"][-1], "command": "/promo", "module": "Custom commands"}
    assert ct.bot_group_command_names(-1) == []     # no app context / no rows: fails safe to empty


# ── the gate as the bot runs it: a real (fake-Telegram) update through _gated ─────

def _upd(text, thread=None, chat_type="supergroup"):
    msg = NS(text=text, chat=NS(id=-100, type=chat_type), message_thread_id=thread,
             is_topic_message=thread is not None, get_bot=lambda: NS(token="1:x"))
    return NS(effective_message=msg)


def test_gated_end_to_end(monkeypatch):
    settings = {"command_table": {"ban": {"enabled": False, "seconds": 30, "delete_command": False, "delete_reply": False}},
                "command_routing": {"commands": {"/verify": {"scope": "specific_topics", "topic_ids": ["7"]}}}}
    monkeypatch.setattr(cc, "_settings_for_chat", lambda chat_id, bot=None: settings)
    run = lambda u: asyncio.run(cc._gated(u))
    assert run(_upd("/ban@MyBot x")) is True            # Status off -> ignored
    assert run(_upd("/kick")) is False                  # untouched command runs
    assert run(_upd("/verify", thread=7)) is False and run(_upd("/verify", thread=9)) is True
    assert run(_upd("/ban", chat_type="private")) is False   # DMs never gated
    assert run(_upd("/start")) is False and run(_upd("hello")) is False
    monkeypatch.setenv("COMMAND_GATE_ENABLED", "0")
    assert run(_upd("/ban")) is False                   # kill switch
    monkeypatch.setenv("COMMAND_GATE_ENABLED", "1")
    monkeypatch.setattr(cc, "_settings_for_chat", lambda *a, **k: 1 / 0)
    assert run(_upd("/ban")) is False                   # errors fail open
