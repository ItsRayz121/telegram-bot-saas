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
