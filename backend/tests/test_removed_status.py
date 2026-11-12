"""removed_status_map: kicked/banned shows, unban/rejoin/expired temp-ban clears it."""
from datetime import datetime, timedelta
from types import SimpleNamespace

from backend.analytics_insights import removed_status_map


class _FakeScope:
    scope = "custom"
    key = 1


def test_logic_via_pure_cases():
    # The decision rules, exercised through the public helper with a stubbed model.
    import backend.analytics_insights as ai

    now = datetime.utcnow()
    m = lambda uid, last=None: SimpleNamespace(telegram_user_id=uid, last_message_at=last)

    class Row:
        def __init__(self, uid, act, ts, dur=None):
            self.target_user_id, self.action_type, self.timestamp = uid, act, ts
            self.extra_data = {"duration_minutes": dur} if dur else {}

    class Col:
        def __getattr__(self, n): return self
        def __eq__(self, o): return True
        def in_(self, o): return True
        def desc(self): return self

    class Q:
        def __init__(self, rows): self.rows = rows
        def filter(self, *a, **k): return self
        def order_by(self, *a, **k): return self
        def limit(self, *a, **k): return self
        def all(self): return self.rows

    def run(rows, members):
        class A:
            group_id = target_user_id = action_type = timestamp = Col()
            query = Q(rows)
        import backend.models as models
        orig = models.AuditLog
        models.AuditLog = A
        try:
            return removed_status_map(_FakeScope(), members)
        finally:
            models.AuditLog = orig

    kicked = run([Row("1", "kick", now - timedelta(hours=1))], [m("1")])
    assert kicked["1"]["status"] == "kicked"
    assert run([Row("1", "ban", now)], [m("1")])["1"]["status"] == "banned"
    # newest event wins: unban after ban => not removed
    assert run([Row("1", "unban", now), Row("1", "ban", now - timedelta(hours=2))], [m("1")]) == {}
    # active after the kick => rejoined
    assert run([Row("1", "kick", now - timedelta(hours=2))], [m("1", now)]) == {}
    # expired temp-ban
    assert run([Row("1", "tempban", now - timedelta(days=3), 1440)], [m("1")]) == {}
    assert run([Row("1", "tempban", now - timedelta(hours=1), 1440)], [m("1")])["1"]["status"] == "banned"
    # a failure never raises
    assert removed_status_map(None, [m("1")]) == {}


def test_stored_flag_wins_and_rejoin_clears():
    from datetime import datetime, timedelta
    from types import SimpleNamespace
    from backend.analytics_insights import removed_status_map

    class Sc:
        scope = "custom"
        key = 1

    import backend.models as models

    class Q:
        def filter(self, *a, **k): return self
        def order_by(self, *a, **k): return self
        def limit(self, *a, **k): return self
        def all(self): return []

    class Col:
        def __getattr__(self, n): return self
        def __eq__(self, o): return True
        def in_(self, o): return True
        def desc(self): return self

    class A:
        group_id = target_user_id = action_type = timestamp = Col()
        query = Q()

    now = datetime.utcnow()
    orig = models.AuditLog
    models.AuditLog = A
    try:
        left = SimpleNamespace(telegram_user_id="1", last_message_at=None,
                               removed_at=now - timedelta(hours=1), removed_reason="left")
        back = SimpleNamespace(telegram_user_id="2", last_message_at=now,
                               removed_at=now - timedelta(hours=1), removed_reason="kicked")
        res = removed_status_map(Sc(), [left, back])
        assert res["1"]["status"] == "left" and "2" not in res
    finally:
        models.AuditLog = orig


def test_record_service_message_and_kill_switch(monkeypatch):
    from types import SimpleNamespace
    import backend.member_presence as mp

    row = SimpleNamespace(removed_at=None, removed_reason=None)
    monkeypatch.setattr(mp, "_row", lambda scope, key, uid: row)
    import backend.models as models
    committed = []
    monkeypatch.setattr(models.db.session, "commit", lambda: committed.append(1))

    user = SimpleNamespace(id=5, is_bot=False)
    admin = SimpleNamespace(id=9, is_bot=False)
    mp.record_service_message("custom", 1, SimpleNamespace(left_chat_member=user, from_user=admin, new_chat_members=None))
    assert row.removed_reason == "kicked" and row.removed_at is not None

    mp.record_service_message("custom", 1, SimpleNamespace(left_chat_member=user, from_user=user, new_chat_members=None))
    assert row.removed_reason == "left"

    mp.record_service_message("custom", 1, SimpleNamespace(left_chat_member=None, from_user=user, new_chat_members=[user]))
    assert row.removed_at is None

    monkeypatch.setenv("MEMBER_LEAVE_TRACKING", "0")
    mp.record_service_message("custom", 1, SimpleNamespace(left_chat_member=user, from_user=admin, new_chat_members=None))
    assert row.removed_at is None
