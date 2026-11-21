// Pure helpers for the scheduled-message form. No network, no React: unit-testable.
// The server remains the source of truth; these only give the person early, honest feedback.

// UTC instant -> the 'YYYY-MM-DDTHH:mm' wall time in `tz`, the format a datetime-local input expects.
export function utcToLocalInput(iso, tz) {
  if (!iso) return '';
  try {
    const parts = new Intl.DateTimeFormat('en-CA', {
      timeZone: tz, hourCycle: 'h23', year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit',
    }).formatToParts(new Date(iso)).reduce((a, p) => ({ ...a, [p.type]: p.value }), {});
    return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
  } catch {
    return '';
  }
}

// 'YYYY-MM-DDTHH:mm' typed as wall time in `tz` -> the UTC instant (ISO), or null. Mirrors the server's conversion.
export function wallToUtcIso(wall, tz) {
  if (!wall) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(wall);
  if (!m) return null;
  const guess = Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]);
  // Date.UTC rolls impossible dates over (Feb 30 -> Mar 2); refuse them instead of scheduling a date nobody typed.
  const chk = new Date(guess);
  if (chk.getUTCMonth() !== +m[2] - 1 || chk.getUTCDate() !== +m[3] || +m[4] > 23 || +m[5] > 59) return null;
  try {
    const offsetAt = (t) => {
      const p = new Intl.DateTimeFormat('en-CA', { timeZone: tz, hourCycle: 'h23', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' })
        .formatToParts(new Date(t)).reduce((a, x) => ({ ...a, [x.type]: x.value }), {});
      return Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour, +p.minute, +p.second) - t;
    };
    let t = guess - offsetAt(guess);
    t = guess - offsetAt(t);
    return new Date(t).toISOString();
  } catch { return null; }
}

// "in 3 hours" / "in 2 days 4 hours" / "in 5 minutes" for a future instant, or null if not in the future.
export function relativeFromNow(iso, now = Date.now()) {
  if (!iso) return null;
  const ms = new Date(iso).getTime() - now;
  if (!Number.isFinite(ms) || ms <= 0) return null;
  const min = Math.round(ms / 60000);
  if (min < 1) return 'in under a minute';
  if (min < 60) return `in ${min} minute${min === 1 ? '' : 's'}`;
  const hours = Math.floor(min / 60);
  if (hours < 24) {
    const rest = min % 60;
    return `in ${hours} hour${hours === 1 ? '' : 's'}${rest ? ` ${rest} min` : ''}`;
  }
  const days = Math.floor(hours / 24);
  const h = hours % 24;
  return `in ${days} day${days === 1 ? '' : 's'}${h ? ` ${h} hour${h === 1 ? '' : 's'}` : ''}`;
}

// 1440 -> "day", 60 -> "hour", 90 -> "90 minutes". Used as: `Every ${formatInterval(n)}`.
export function formatInterval(minutes) {
  const n = Number(minutes);
  if (!Number.isFinite(n) || n <= 0) return '';
  if (n % 10080 === 0) return n === 10080 ? 'week' : `${n / 10080} weeks`;
  if (n % 1440 === 0) return n === 1440 ? 'day' : `${n / 1440} days`;
  if (n % 60 === 0) return n === 60 ? 'hour' : `${n / 60} hours`;
  return n === 1 ? 'minute' : `${n} minutes`;
}

// Problems with the schedule form that the person can fix before saving.
// Returns { errors: [], warnings: [], iso } — errors block saving, warnings do not.
// `timeChanged` is false when editing without touching the time (a stored time that has
// since slipped into the past is the server's business, not a form error).
export function checkSchedule({ send_at, stop_date, timezone, repeat_interval, timeChanged = true }, now = Date.now()) {
  const errors = [];
  const warnings = [];
  const iso = wallToUtcIso(send_at, timezone);
  if (send_at && !iso) errors.push('That date and time could not be read. Pick it again.');
  if (iso && timeChanged) {
    if (new Date(iso).getTime() <= now) errors.push('This time is in the past. Pick a time in the future.');
    // A wall time skipped by a daylight-saving jump: the round trip lands on a different clock time.
    const back = utcToLocalInput(iso, timezone);
    if (back && back !== send_at.slice(0, 16)) {
      warnings.push(`${send_at.slice(11, 16)} does not exist in ${timezone} on that date (clocks change). It will be sent at ${back.slice(11, 16)} instead.`);
    }
  }
  if (repeat_interval !== '' && repeat_interval != null) {
    const n = Number(repeat_interval);
    if (!Number.isFinite(n) || n < 0 || !Number.isInteger(n)) errors.push('Repeat interval must be a whole number of minutes (0 for once).');
  }
  if (stop_date) {
    const stopIso = wallToUtcIso(stop_date, timezone);
    if (!stopIso) errors.push('The stop date could not be read.');
    else if (iso && new Date(stopIso).getTime() <= new Date(iso).getTime()) errors.push('Stop date must be after the first send time.');
    else if (!repeat_interval || Number(repeat_interval) === 0) warnings.push('A stop date only matters when the message repeats.');
  }
  return { errors, warnings, iso };
}
