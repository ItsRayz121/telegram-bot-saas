import os
import sys
import tempfile

os.environ.setdefault("DATABASE_URL", "sqlite:///" + os.path.join(tempfile.mkdtemp(), "xp.db"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import leveling  # noqa: E402


def test_compute():
    c = leveling.compute_penalty
    assert c(200, "fixed", 1) == 1 and c(3, "fixed", 50) == 3          # floors at what they have
    assert c(200, "percent", 10) == 20 and c(15, "percent", 10) == 2    # 1.5 rounds half up
    assert c(200, "percent", 250) == 200                                # capped at 100%
    assert c(200, "reset", 0) == 200 and c(0, "reset", 0) == 0
    assert c(200, "none", 99) == 0 and c(200, "fixed", 0) == 0


def test_apply_and_ledger():
    from database import SessionLocal, init_db
    from models import Guild, GuildSettings, Member, XpEvent
    init_db()
    db = SessionLocal()
    db.add(Guild(id=9490, name="x", owner_id=None, plan="free"))
    db.flush()
    db.add(GuildSettings(guild_id=9490, levels_enabled=True, extra={"leveling2": {
        "penalty_warn": 1, "penalty_kick": 10, "penalty_kick_mode": "percent",
        "penalty_ban": 5, "penalty_ban_mode": "reset"}}))
    db.add(Member(guild_id=9490, user_id=1, xp=200, level=3))
    db.commit()
    assert leveling.apply_penalty(db, 9490, 1, "u", "warn") == 1          # legacy fixed
    assert leveling.apply_penalty(db, 9490, 1, "u", "kick") == 20         # 10% of 199 → 20
    assert leveling.apply_penalty(db, 9490, 1, "u", "timeout") == 0       # disabled
    assert leveling.apply_penalty(db, 9490, 1, "u", "ban") == 179         # reset
    assert leveling.apply_penalty(db, 9490, 1, "u", "ban") == 0           # nothing left, no debit
    db.flush()
    m = db.get(Member, {"guild_id": 9490, "user_id": 1})
    assert m.xp == 0 and m.level == 1
    assert [e.amount for e in db.query(XpEvent).filter_by(guild_id=9490).order_by(XpEvent.id)] == [-1, -20, -179]


def test_replace_policy_drops_only_lower_ranks():
    import level_roles
    rw = [{"level": 1, "role_id": "11"}, {"level": 5, "role_id": "55"}, {"level": 10, "role_id": "1010"}]
    assert level_roles.superseded_role_ids(7, rw) == [11]
    assert level_roles.superseded_role_ids(10, rw) == [11, 55]
    assert level_roles.superseded_role_ids(1, rw) == []


def test_penalty_key_makes_a_retried_event_free():
    from database import SessionLocal, init_db
    from models import Guild, GuildSettings, Member
    init_db()
    db = SessionLocal()
    db.add(Guild(id=9491, name="x", owner_id=None, plan="free"))
    db.flush()
    db.add(GuildSettings(guild_id=9491, levels_enabled=True, extra={"leveling2": {"penalty_kick": 10}}))
    db.add(Member(guild_id=9491, user_id=1, xp=100, level=2))
    db.commit()
    assert leveling.apply_penalty(db, 9491, 1, "u", "kick", key="m1") == 10
    assert leveling.apply_penalty(db, 9491, 1, "u", "kick", key="m1") == 0      # same event retried
    assert leveling.apply_penalty(db, 9491, 1, "u", "kick", key="m2") == 10     # a new event is charged
    assert db.get(Member, {"guild_id": 9491, "user_id": 1}).xp == 80


def test_ladder_protection_rules():
    import bot_core

    class P:
        administrator = False

    def member(uid, top, admin=False):
        perms = P()
        perms.administrator = admin
        return type("M", (), {"id": uid, "guild_permissions": perms, "top_role": top})()
    guild = type("G", (), {"owner_id": 1, "me": type("Me", (), {"top_role": 10})()})()
    assert bot_core.ladder_protected(guild, member(1, 1)) == "server owner"
    assert bot_core.ladder_protected(guild, member(2, 1, admin=True)) == "administrator"
    assert bot_core.ladder_protected(guild, member(3, 10)) == "role at or above Guildizer's"
    assert bot_core.ladder_protected(guild, member(4, 5)) is None
