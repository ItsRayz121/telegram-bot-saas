"""Self-pruning {key: monotonic_timestamp} map for in-process cooldowns.

Plain dicts used as cooldown trackers never shrink: one entry is kept for every
user (or campaign) that has ever triggered the cooldown, for the life of the
process. That is an unbounded structure that grows in step with the user base and
is only ever reclaimed by a redeploy.

Eviction here is behaviour-preserving by construction. Every caller reads the map
as `now - m.get(key, 0) < window` — so an entry older than `window` already fails
that test and is indistinguishable from a missing key. Dropping it therefore
cannot change a single decision the caller makes; it only stops us paying to
remember it.

Timestamps are `time.monotonic()` (not wall clock), matching the call sites.
"""

import time


class TTLMap:
    """A {key: timestamp} map that forgets entries older than `ttl` seconds.

    Pruning is amortised: a full scan runs at most every `prune_interval` seconds,
    and immediately if the map exceeds `max_entries` (a burst guard, so a flood of
    unique keys inside one interval can still not grow without bound).
    """

    __slots__ = ("_data", "_ttl", "_max_entries", "_prune_interval", "_next_prune")

    def __init__(self, ttl, max_entries=100_000, prune_interval=300.0):
        self._data = {}
        self._ttl = float(ttl)
        self._max_entries = int(max_entries)
        self._prune_interval = float(prune_interval)
        self._next_prune = time.monotonic() + self._prune_interval

    def get(self, key, default=0):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value
        now = time.monotonic()
        if now >= self._next_prune or len(self._data) > self._max_entries:
            self._prune(now)

    # Lets a leaking plain dict be swapped for a TTLMap without touching the
    # `m[key] = now` call sites that already read it via .get().
    __setitem__ = set

    def _prune(self, now):
        cutoff = now - self._ttl
        self._data = {k: v for k, v in self._data.items() if v > cutoff}
        self._next_prune = now + self._prune_interval

    def __len__(self):
        return len(self._data)
