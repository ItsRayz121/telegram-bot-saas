"""Managed-members time series for the admin Users charts (pure functions, no DB access)."""
# ── Managed-members series (admin "Users" charts) ─────────────────────────────
# Both charts read the daily snapshot table only (UTC days). Nothing is interpolated:
# a day with no snapshot has no point, and a change with no earlier snapshot is None
# ("unavailable"), never 0.
#
#   Total chart : "Managed members" = SUM(member_count) over active, non-disabled groups at the
#                 END of each period (last snapshot in that period). Current membership, not
#                 unique people ever seen.
#   Change chart: NET change = this period's end total minus the previous period's end total.
#                 It is a difference of snapshots, NOT a count of join/leave events: it also moves
#                 when a group enters/leaves scope (bot removed, group disabled or unlinked, access
#                 lost) or when Telegram's member_count is refreshed.
SERIES_RANGES = {"1d": (1, "day"), "7d": (7, "day"), "30d": (30, "day"), "12m": (365, "month")}


def _month_start(d):
    return d.replace(day=1)


def build_member_series(rows, range_key, today):
    """rows: objects with day, managed_members, verified_members, groups_total, ordered or not.

    Returns {range, bucket, timezone, points:[...], data_starts}. Each point:
      period_start, period_end (ISO dates), snapshot_day (the row the totals come from),
      managed, verified, groups_total,
      net_managed, net_verified, groups_delta  (None = unavailable),
      baseline_day (the snapshot the change is measured from), gap_days (days between the two
      snapshots; >1 means the change spans days with no snapshot),
      partial (period not finished or history starts mid-period).
    """
    from datetime import timedelta

    n_days, bucket = SERIES_RANGES[range_key]
    rows = sorted(rows, key=lambda r: r.day)
    data_starts = rows[0].day if rows else None
    window_start = today - timedelta(days=n_days - 1) if bucket == "day" else _month_start(today - timedelta(days=n_days))
    if bucket == "month" and window_start < _month_start(today - timedelta(days=n_days)):
        window_start = _month_start(today - timedelta(days=n_days))

    def key(d):
        return d if bucket == "day" else _month_start(d)

    # last snapshot of each period inside the window
    last_in = {}
    for r in rows:
        if r.day >= window_start and r.day <= today:
            last_in[key(r.day)] = r
    baseline = None  # last snapshot strictly before the window
    for r in rows:
        if r.day < window_start:
            baseline = r

    points, prev = [], baseline
    for period in sorted(last_in):
        r = last_in[period]
        if bucket == "day":
            p_end = period
            partial = (period == today)  # today's row is still being refreshed
        else:
            nxt = (period.replace(day=28) + timedelta(days=4)).replace(day=1)
            p_end = nxt - timedelta(days=1)
            partial = (period == _month_start(today)) or (data_starts is not None and data_starts > period)
        points.append({
            "period_start": period.isoformat(), "period_end": p_end.isoformat(),
            "snapshot_day": r.day.isoformat(),
            "managed": r.managed_members, "verified": r.verified_members, "groups_total": r.groups_total,
            "net_managed": (r.managed_members - prev.managed_members) if prev else None,
            "net_verified": (r.verified_members - prev.verified_members) if prev else None,
            "groups_delta": (r.groups_total - prev.groups_total) if prev else None,
            "baseline_day": prev.day.isoformat() if prev else None,
            "gap_days": (r.day - prev.day).days if prev else None,
            "partial": bool(partial),
        })
        prev = r
    return {
        "range": range_key, "bucket": bucket, "timezone": "UTC",
        "data_starts": data_starts.isoformat() if data_starts else None,
        "points": points,
    }
