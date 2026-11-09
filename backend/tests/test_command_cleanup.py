"""Auto-delete of the bot's command replies. Run: python -m pytest backend/tests/test_command_cleanup.py
Telegram is faked; no network, no database (settings lookup is patched)."""
import asyncio
from types import SimpleNamespace as NS

import pytest

from backend import command_cleanup as cc


def test_command_name_parsing():
    assert cc.command_name("/rank") == "rank"
    assert cc.command_name("/Leaderboard@MyBot extra words") == "leaderboard"
    assert cc.command_name("hello") is None and cc.command_name(None) is None and cc.command_name("/") is None


def test_delays_default_to_keeping_everything():
    assert cc.delays_from_settings({}, "rank") == (0, False)
    assert cc.delays_from_settings(None, "rank") == (0, False)


def test_rank_commands_use_their_own_delay_and_fall_back_to_the_general_one():
    ac = {"command_reply_delete_seconds": 60, "rank_reply_delete_seconds": 10, "delete_commands": True}
    assert cc.delays_from_settings(ac, "rank") == (10, True)
    assert cc.delays_from_settings(ac, "leaderboard") == (10, True)
    assert cc.delays_from_settings(ac, "help") == (60, True)
    assert cc.delays_from_settings({"command_reply_delete_seconds": 60}, "xp") == (60, False)


def test_moderation_and_setup_commands_are_never_touched():
    ac = {"command_reply_delete_seconds": 5}
    for c in ("ban", "mute", "warn", "purge", "start", "linkgroup", "unwarn"):
        assert cc.delays_from_settings(ac, c) == (0, False)


def test_bad_or_huge_values_are_clamped():
    assert cc.delays_from_settings({"command_reply_delete_seconds": "abc"}, "help")[0] == 0
    assert cc.delays_from_settings({"command_reply_delete_seconds": -5}, "help")[0] == 0
    assert cc.delays_from_settings({"command_reply_delete_seconds": 10**9}, "help")[0] == cc.MAX_SECONDS


class FakeBot:
    def __init__(self):
        self.deleted = []

    async def delete_message(self, chat_id, message_id):
        self.deleted.append((chat_id, message_id))


def make_cmd(text, chat_type="supergroup", bot=None):
    return NS(text=text, chat=NS(id=-100, type=chat_type), message_id=11, get_bot=lambda: bot)


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    monkeypatch.delenv("COMMAND_AUTODELETE_ENABLED", raising=False)
    real_sleep = asyncio.sleep
    monkeypatch.setattr(cc.asyncio, "sleep", lambda s: real_sleep(0))


def run_reply(monkeypatch, settings, text="/rank", chat_type="supergroup"):
    monkeypatch.setattr(cc, "_auto_clean_for_chat", lambda chat_id: settings)
    bot = FakeBot()

    async def go():
        await cc.after_reply(make_cmd(text, chat_type, bot), NS(message_id=22))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
    asyncio.run(go())
    return bot.deleted


def test_reply_and_command_are_deleted_after_the_delay(monkeypatch):
    got = run_reply(monkeypatch, {"rank_reply_delete_seconds": 5, "delete_commands": True})
    assert sorted(got) == [(-100, 11), (-100, 22)]


def test_only_the_reply_goes_when_delete_commands_is_off(monkeypatch):
    assert run_reply(monkeypatch, {"rank_reply_delete_seconds": 5}) == [(-100, 22)]


def test_nothing_happens_by_default_in_private_chats_or_for_non_commands(monkeypatch):
    assert run_reply(monkeypatch, {}) == []
    assert run_reply(monkeypatch, {"rank_reply_delete_seconds": 5}, chat_type="private") == []
    assert run_reply(monkeypatch, {"rank_reply_delete_seconds": 5}, text="gm everyone") == []


def test_kill_switch_stops_all_deletion(monkeypatch):
    monkeypatch.setenv("COMMAND_AUTODELETE_ENABLED", "0")
    assert run_reply(monkeypatch, {"rank_reply_delete_seconds": 5, "delete_commands": True}) == []


def test_a_failing_settings_lookup_never_breaks_the_reply(monkeypatch):
    def boom(chat_id):
        raise RuntimeError("db down")
    monkeypatch.setattr(cc, "_auto_clean_for_chat", boom)
    asyncio.run(cc.after_reply(make_cmd("/rank", bot=FakeBot()), NS(message_id=22)))  # must not raise


def test_install_wraps_reply_methods_once_and_returns_the_sent_message(monkeypatch):
    monkeypatch.setattr(cc, "_auto_clean_for_chat", lambda c: {"command_reply_delete_seconds": 5})
    monkeypatch.setitem(cc._state, "installed", False)
    bot = FakeBot()

    class FakeMessage:
        text, chat, message_id = "/help", NS(id=-100, type="group"), 11
        def get_bot(self): return bot
        async def reply_text(self, text): return NS(message_id=33, text=text)

    cc.install(None, message_cls=FakeMessage)
    cc.install(None, message_cls=FakeMessage)              # second call must not double-wrap

    async def go():
        sent = await FakeMessage().reply_text("hi")
        pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        while pending:                       # the cleanup runs in the background, after the reply
            await asyncio.gather(*pending)
            pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        return sent
    sent = asyncio.run(go())
    assert sent.message_id == 33 and bot.deleted == [(-100, 33)]


# ── command scope: bots that answer with bot.send_message, and commands that send no reply ──

def _drain():
    async def go():
        for _ in range(4):
            await asyncio.sleep(0)
        pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        while pending:
            await asyncio.gather(*pending)
            pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    return go


def _scoped(monkeypatch, settings, text="/xp", chat_type="supergroup", send_to=-100):
    """Run a fake CommandHandler whose callback answers through Bot.send_message."""
    monkeypatch.setattr(cc, "_auto_clean_for_chat", lambda chat_id: settings)
    deleted = []

    class FakeBotCls:
        async def delete_message(self, chat_id, message_id): deleted.append((chat_id, message_id))
        async def send_message(self, chat_id, text): return NS(message_id=50)

    class FakeHandler:
        async def handle_update(self, update, *a, **k):
            await bot.send_message(chat_id=send_to, text="answer")
            return "handled"

    cc._install_send_hooks(FakeBotCls)
    cc._install_command_scope(FakeHandler)
    bot = FakeBotCls()
    msg = NS(text=text, chat=NS(id=-100, type=chat_type), message_id=11, get_bot=lambda: bot)

    async def go():
        out = await FakeHandler().handle_update(NS(effective_message=msg))
        await _drain()()
        return out
    assert asyncio.run(go()) == "handled"
    assert cc._current.get() is None            # never leaks past the handler
    return deleted


def test_bot_send_message_replies_are_deleted_too(monkeypatch):
    assert _scoped(monkeypatch, {"rank_reply_delete_seconds": 5}) == [(-100, 50)]


def test_command_message_goes_even_when_the_reply_is_kept(monkeypatch):
    got = _scoped(monkeypatch, {"delete_commands": True})
    assert got == [(-100, 11)]                  # reply kept (delay 0), command removed after the short default


def test_messages_to_other_chats_and_other_commands_are_untouched(monkeypatch):
    assert _scoped(monkeypatch, {"rank_reply_delete_seconds": 5}, send_to=999) == []
    assert _scoped(monkeypatch, {"command_reply_delete_seconds": 5}, text="/ban") == []
    assert _scoped(monkeypatch, {}) == []
