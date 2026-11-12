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
