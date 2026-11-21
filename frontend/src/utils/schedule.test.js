import { wallToUtcIso, utcToLocalInput, relativeFromNow, formatInterval, checkSchedule } from './schedule';

const NOW = Date.parse('2026-03-01T12:00:00Z');

describe('wallToUtcIso / utcToLocalInput', () => {
  test('converts a wall time in a zone to UTC and back', () => {
    expect(wallToUtcIso('2026-07-01T09:00', 'America/New_York')).toBe('2026-07-01T13:00:00.000Z'); // EDT, UTC-4
    expect(wallToUtcIso('2026-01-01T09:00', 'America/New_York')).toBe('2026-01-01T14:00:00.000Z'); // EST, UTC-5
    expect(utcToLocalInput('2026-07-01T13:00:00.000Z', 'America/New_York')).toBe('2026-07-01T09:00');
  });
  test('UTC is identity and bad input is null', () => {
    expect(wallToUtcIso('2026-07-01T09:00', 'UTC')).toBe('2026-07-01T09:00:00.000Z');
    expect(wallToUtcIso('', 'UTC')).toBeNull();
    expect(wallToUtcIso('nonsense', 'UTC')).toBeNull();
    expect(wallToUtcIso('2026-07-01T09:00', 'Not/AZone')).toBeNull();
  });
});

describe('relativeFromNow', () => {
  test('formats minutes, hours and days', () => {
    expect(relativeFromNow('2026-03-01T12:05:00Z', NOW)).toBe('in 5 minutes');
    expect(relativeFromNow('2026-03-01T15:30:00Z', NOW)).toBe('in 3 hours 30 min');
    expect(relativeFromNow('2026-03-03T16:00:00Z', NOW)).toBe('in 2 days 4 hours');
    expect(relativeFromNow('2026-03-01T12:00:10Z', NOW)).toBe('in under a minute');
  });
  test('past or empty gives null', () => {
    expect(relativeFromNow('2026-03-01T11:00:00Z', NOW)).toBeNull();
    expect(relativeFromNow('', NOW)).toBeNull();
  });
});

describe('formatInterval', () => {
  test('uses natural units', () => {
    expect(formatInterval(60)).toBe('hour');
    expect(formatInterval(1440)).toBe('day');
    expect(formatInterval(10080)).toBe('week');
    expect(formatInterval(180)).toBe('3 hours');
    expect(formatInterval(90)).toBe('90 minutes');
    expect(formatInterval(0)).toBe('');
  });
});

describe('checkSchedule', () => {
  const base = { send_at: '2026-03-02T09:00', stop_date: '', timezone: 'UTC', repeat_interval: '' };
  test('a valid future time has no errors', () => {
    expect(checkSchedule(base, NOW).errors).toEqual([]);
  });
  test('past time is an error only when the time was changed', () => {
    const past = { ...base, send_at: '2026-02-01T09:00' };
    expect(checkSchedule(past, NOW).errors[0]).toMatch(/past/);
    expect(checkSchedule({ ...past, timeChanged: false }, NOW).errors).toEqual([]);
  });
  test('a time skipped by a DST jump is warned about, not blocked', () => {
    // US clocks jump 02:00 -> 03:00 on 2026-03-08, so 02:30 does not exist in New York.
    const r = checkSchedule({ ...base, send_at: '2026-03-08T02:30', timezone: 'America/New_York' }, NOW);
    expect(r.errors).toEqual([]);
    expect(r.warnings[0]).toMatch(/does not exist/);
  });
  test('stop date must follow the first send; warned if not repeating', () => {
    expect(checkSchedule({ ...base, stop_date: '2026-03-02T08:00', repeat_interval: '60' }, NOW).errors[0]).toMatch(/after the first/);
    expect(checkSchedule({ ...base, stop_date: '2026-03-05T08:00', repeat_interval: '' }, NOW).warnings[0]).toMatch(/repeats/);
    expect(checkSchedule({ ...base, stop_date: '2026-03-05T08:00', repeat_interval: '60' }, NOW)).toMatchObject({ errors: [], warnings: [] });
  });
  test('repeat interval must be a non-negative whole number', () => {
    expect(checkSchedule({ ...base, repeat_interval: '-5' }, NOW).errors.length).toBe(1);
    expect(checkSchedule({ ...base, repeat_interval: '1.5' }, NOW).errors.length).toBe(1);
    expect(checkSchedule({ ...base, repeat_interval: '0' }, NOW).errors).toEqual([]);
  });
});

describe('timezone edge cases', () => {
  test('half-hour and southern-hemisphere zones convert exactly', () => {
    expect(wallToUtcIso('2030-06-15T12:00', 'Asia/Kolkata')).toBe('2030-06-15T06:30:00.000Z');
    expect(wallToUtcIso('2030-01-15T12:00', 'Australia/Sydney')).toBe('2030-01-15T01:00:00.000Z'); // AEDT +11
    expect(wallToUtcIso('2030-07-15T12:00', 'Australia/Sydney')).toBe('2030-07-15T02:00:00.000Z'); // AEST +10
  });
  test('the same wall time maps to different UTC either side of a DST change', () => {
    expect(wallToUtcIso('2030-03-09T12:00', 'America/New_York')).toBe('2030-03-09T17:00:00.000Z'); // EST
    expect(wallToUtcIso('2030-03-11T12:00', 'America/New_York')).toBe('2030-03-11T16:00:00.000Z'); // EDT
  });
  test('an ambiguous fall-back hour resolves to one instant that round-trips', () => {
    const iso = wallToUtcIso('2030-11-03T01:30', 'America/New_York');
    expect(iso).not.toBeNull();
    expect(utcToLocalInput(iso, 'America/New_York')).toBe('2030-11-03T01:30');
  });
  test('leap day is accepted, and an impossible date is not a valid schedule', () => {
    expect(wallToUtcIso('2032-02-29T09:00', 'UTC')).toBe('2032-02-29T09:00:00.000Z');
    const bad = checkSchedule({ send_at: '2031-02-30T09:00', timezone: 'UTC', repeat_interval: 0 }, Date.UTC(2030, 0, 1));
    expect(bad.errors.length).toBeGreaterThan(0);
  });
  test('an unknown timezone name never throws', () => {
    expect(() => checkSchedule({ send_at: '2031-01-01T09:00', timezone: 'Mars/Base', repeat_interval: 0 }, Date.UTC(2030, 0, 1))).not.toThrow();
  });
});
