"""Level-role sync, paragraph-safe AI replies, and the hardened rank card (Guildizer).

Run from discord-board/backend:  python -m pytest tests/test_level_roles_and_replies.py
Throwaway SQLite database; no Discord connection (guild/member objects are fakes).
"""
import asyncio
import os
import sys
import tempfile
from datetime import datetime, timedelta

_DB = os.path.join(tempfile.mkdtemp(), "lr.db")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB}")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

import level_roles as lr  # noqa: E402
import rank_card  # noqa: E402
import reply_split  # noqa: E402

LADDER = [{"level": 5, "role_id": "105"}, {"level": 1, "role_id": "101"}, {"level": 10, "role_id": "110"},
          {"level": "x", "role_id": "bad"}, {"level": 3, "role_id": "oops"}, "junk"]


# ── pure ladder maths ──────────────────────────────────────────────────────────
def test_ladder_is_cleaned_and_sorted():
    assert lr.valid_rewards(LADDER) == [(1, 101), (5, 105), (10, 110)]
    assert lr.min_reward_level(LADDER) == 1 and lr.min_reward_level([]) is None


def test_due_roles_are_cumulative():
    assert lr.due_role_ids(1, LADDER) == [101]
    assert lr.due_role_ids(7, LADDER) == [101, 105]
    assert lr.due_role_ids(99, LADDER) == [101, 105, 110]
    assert lr.due_role_ids(None, LADDER) == [101]


# ── candidates query ───────────────────────────────────────────────────────────
G, G2 = 9910, 9911
NOW = datetime.utcnow()


@pytest.fixture(scope="module", autouse=True)
def _world():
    from database import SessionLocal, init_db
    from models import Guild, GuildSettings, Member, User
    init_db()
    db = SessionLocal()
    db.add(User(id=9901, username="o"))
    db.flush()
    db.add_all([Guild(id=G, name="A", owner_id=9901), Guild(id=G2, name="B", owner_id=9901)])
    db.flush()
    db.add(GuildSettings(guild_id=G, levels_enabled=True, extra={"leveling2": {"role_rewards": [
        {"level": 1, "role_id": "101"}, {"level": 5, "role_id": "105"}]}}))
    for uid, lvl, age in ((1, 1, 1), (2, 6, 1), (3, 12, 500), (4, 6, 1)):
        db.add(Member(guild_id=G, user_id=uid, level=lvl, xp=lvl * 100, updated_at=NOW - timedelta(minutes=age)))
    db.add(Member(guild_id=G2, user_id=1, level=50, xp=1, updated_at=NOW))
    db.commit()
    db.close()


@pytest.fixture()
def db():
    from database import SessionLocal
    s = SessionLocal()
    yield s
    s.close()
    SessionLocal.remove()


def test_candidates_filters_by_server_level_age_and_cursor(db):
    rw = [{"level": 5, "role_id": "105"}]
    assert [u for u, _ in lr.candidates(db, G, rw)] == [2, 3, 4]               # level>=5, this server only
    assert [u for u, _ in lr.candidates(db, G, rw, since=NOW - timedelta(minutes=10))] == [2, 4]
    assert [u for u, _ in lr.candidates(db, G, rw, after_user_id=2)] == [3, 4]  # resync cursor
    assert len(lr.candidates(db, G, rw, limit=1)) == 1
    assert lr.candidates(db, G, []) == []


# ── the sweep ──────────────────────────────────────────────────────────────────
class FakeRole:
    """Like discord.Role: equal when the ids are equal."""
    def __init__(self, i):
        self.id = i

    def __eq__(self, other):
        return getattr(other, "id", None) == self.id

    def __hash__(self):
        return hash(self.id)


class FakeMember:
    def __init__(self, uid, have=()):
        self.id, self.roles, self.added = uid, [FakeRole(r) for r in have], []

    async def add_roles(self, *roles, reason=None):
        self.added += [r.id for r in roles]
        self.roles += list(roles)


class FakeGuild:
    def __init__(self, gid, members):
        self.id = gid
        self._m = {m.id: m for m in members}
        self._roles = {101: FakeRole(101), 105: FakeRole(105), 110: FakeRole(110)}

    def get_member(self, uid):
        return self._m.get(uid)

    def get_role(self, rid):
        return self._roles.get(rid)


def make_core(monkeypatch):
    import bot_core

    async def no_sleep(*a, **k):
        return None
    monkeypatch.setattr(bot_core.asyncio, "sleep", no_sleep)
    bot_core._role_sync_state.clear()
    return type("Core", (bot_core.CoreMixin,), {"__init__": lambda self: None})()


def run(coro):
    return asyncio.run(coro)


def test_sweep_grants_missing_reward_roles_only(monkeypatch):
    core = make_core(monkeypatch)
    m2 = FakeMember(2, have=[101])           # level 6 -> needs 105 (has 101)
    m4 = FakeMember(4, have=[101, 105])      # already complete
    m1 = FakeMember(1)                       # level 1, holds nothing -> needs the level-1 role
    guild = FakeGuild(G, [m1, m2, m4])
    run(core._sync_level_roles(guild))
    assert m2.added == [105] and m4.added == []
    assert m1.added == [101]
    assert not hasattr(m2, "removed")


def test_sweep_never_removes_roles(monkeypatch):
    core = make_core(monkeypatch)
    low = FakeMember(2, have=[101, 105, 110])      # holds MORE than the ladder gives at level 6
    guild = FakeGuild(G, [low])
    run(core._sync_level_roles(guild))
    assert {r.id for r in low.roles} == {101, 105, 110}


def test_incremental_sweep_ignores_stale_rows_but_resync_covers_everyone(monkeypatch):
    from database import SessionLocal
    from models import GuildSettings
    core = make_core(monkeypatch)
    old = FakeMember(3)                            # level 12, row 500 minutes old
    guild = FakeGuild(G, [old])
    run(core._sync_level_roles(guild))
    assert old.added == []                          # outside the 10-minute incremental window
    s = SessionLocal()
    row = s.get(GuildSettings, G)
    extra = dict(row.extra)
    extra["leveling2"] = {**extra["leveling2"], "roles_resync_at": "2026-10-12T00:00:00"}
    row.extra = extra
    s.commit()
    s.close()
    SessionLocal.remove()
    run(core._sync_level_roles(guild))              # full resync: everyone at/above the lowest reward
    assert sorted(old.added) == [101, 105]
    s = SessionLocal()
    assert "roles_resync_at" not in (s.get(GuildSettings, G).extra or {}).get("leveling2", {})   # flag cleared
    s.close()
    SessionLocal.remove()


def test_levels_off_or_no_ladder_does_nothing(monkeypatch):
    core = make_core(monkeypatch)
    m = FakeMember(2)
    run(core._sync_level_roles(FakeGuild(G2, [m])))     # server B has no settings row
    assert m.added == []


# ── API: ladder edits flag a resync ────────────────────────────────────────────
@pytest.fixture()
def client():
    import app as appmod
    import auth
    from config import Config
    from database import SessionLocal
    from models import UserGuild
    s = SessionLocal()
    if s.get(UserGuild, {"user_id": 9901, "guild_id": G}) is None:
        s.add(UserGuild(user_id=9901, guild_id=G, can_manage=True, is_owner=True))
        s.commit()
    s.close()
    SessionLocal.remove()
    c = appmod.app.test_client()
    c.set_cookie(Config.SESSION_COOKIE_NAME, auth._issue_session(9901))
    return c


def test_editing_the_ladder_flags_a_resync_and_unchanged_save_does_not(client):
    url = f"/api/guilds/{G}/leveling"
    ladder = [{"level": 1, "role_id": "101"}, {"level": 5, "role_id": "105"}, {"level": 20, "role_id": "120"}]
    r = client.put(url, json={"leveling2": {"role_rewards": ladder}})
    assert r.status_code == 200
    from database import SessionLocal
    from models import GuildSettings
    s = SessionLocal()
    flag = s.get(GuildSettings, G).extra["leveling2"].get("roles_resync_at")
    assert flag
    s.close()
    SessionLocal.remove()
    # saving the same ladder again must not re-flag
    from sqlalchemy.orm.attributes import flag_modified
    s = SessionLocal()
    row = s.get(GuildSettings, G)
    l2 = dict(row.extra["leveling2"]); l2.pop("roles_resync_at")
    row.extra = {**row.extra, "leveling2": l2}
    flag_modified(row, "extra")
    s.commit()
    s.close()
    SessionLocal.remove()
    client.put(url, json={"leveling2": {"role_rewards": ladder}})
    s = SessionLocal()
    assert "roles_resync_at" not in s.get(GuildSettings, G).extra["leveling2"]
    s.close()
    SessionLocal.remove()


def test_manual_resync_endpoint(client):
    r = client.post(f"/api/guilds/{G}/leveling/resync-roles")
    assert r.status_code == 200
    from database import SessionLocal
    from models import GuildSettings
    s = SessionLocal()
    assert s.get(GuildSettings, G).extra["leveling2"]["roles_resync_at"]
    s.close()
    SessionLocal.remove()
    assert client.post(f"/api/guilds/{G2}/leveling/resync-roles").status_code == 403


# ── reply splitting ────────────────────────────────────────────────────────────
def test_short_reply_is_one_part_and_empty_is_none():
    assert reply_split.split_reply("hello") == ["hello"]
    assert reply_split.split_reply("   ") == []


def test_long_reply_splits_on_paragraphs_and_loses_nothing():
    paras = [("Paragraph %d. " % i) + ("word " * 120).strip() for i in range(6)]
    text = "\n\n".join(paras)
    parts = reply_split.split_reply(text, limit=1900, max_parts=5)
    assert all(0 < len(p) <= 1900 for p in parts) and len(parts) >= 2
    assert "\n\n".join(parts).replace("\n\n", " ").split() == text.replace("\n\n", " ").split()
    assert all(p.startswith("Paragraph") for p in parts)            # cut between paragraphs, not inside one


def test_split_prefers_sentence_then_space_then_hard_cut():
    sentences = " ".join(["This is a sentence number %d." % i for i in range(200)])
    for p in reply_split.split_reply(sentences, limit=500, max_parts=20):
        assert p.endswith(".")                                       # never ends mid-sentence
    blob = "x" * 4000
    assert [len(p) for p in reply_split.split_reply(blob, limit=1900, max_parts=5)] == [1900, 1900, 200]


def test_overlong_answer_is_marked_not_silently_dropped():
    parts = reply_split.split_reply("word " * 3000, limit=1900, max_parts=3)
    assert len(parts) == 3 and parts[-1].endswith("…") and all(len(p) <= 1900 for p in parts)


# ── rank card ──────────────────────────────────────────────────────────────────
def render(**kw):
    base = dict(username="Member", avatar_bytes=None, level=3, xp=250, rank=2, into_level=50, need_for_level=100)
    base.update(kw)
    return rank_card.render(**base)


def test_card_renders_for_normal_and_extreme_values():
    from PIL import Image
    import io
    for kw in ({}, dict(username="W" * 200, level=999999, xp=10 ** 12, rank=10 ** 9, into_level=10 ** 11, need_for_level=10 ** 12)):
        png = render(**kw)
        assert png and Image.open(io.BytesIO(png)).size == (rank_card.W, rank_card.H)


def test_fit_font_shrinks_then_ellipsizes():
    from PIL import Image, ImageDraw
    d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    f, t = rank_card.fit_font(d, "short", 600, 40, bold=True)
    assert t == "short"
    f, t = rank_card.fit_font(d, "W" * 80, 200, 40, bold=True)
    assert t.endswith("…") and d.textlength(t, font=f) <= 200


def test_busy_renderer_returns_none_instead_of_piling_up(monkeypatch):
    monkeypatch.setattr(rank_card, "_RENDER_WAIT_SECONDS", 0.05)
    assert rank_card._RENDER_SLOTS.acquire(timeout=1) and rank_card._RENDER_SLOTS.acquire(timeout=1)
    try:
        assert render() is None
    finally:
        rank_card._RENDER_SLOTS.release()
        rank_card._RENDER_SLOTS.release()
    assert render() is not None
