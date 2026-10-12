import {
  buildRows, canInvite, filterCounts, matchesFilter, matchesSearch, overview, parseUtc,
  relativeTime, stepsFor, timelineFor,
} from './teamAccess';

const inv = (o) => ({
  id: 1, invitee_telegram_id: '222', invitee_name: 'Ali', role: 'manager', status: 'pending',
  created_at: '2026-10-01T10:00:00', expires_at: '2026-10-08T10:00:00', used_by: null, used_at: null,
  declined_at: null, ...o,
});
const admin = (o) => ({
  user_id: '222', name: 'Ali', username: 'ali', status: 'administrator', can_dm: true,
  has_access: false, member_user_id: null, member_role: null, pending: false, ...o,
});
const member = (o) => ({ user_id: 7, role: 'manager', full_name: 'Ali', email: 'a@x.io', joined_at: '2026-10-02T10:00:00', ...o });
const stageOf = (rows, tg) => rows.find((r) => r.tgId === tg).stage;

describe('parseUtc', () => {
  it('treats the backend naive timestamps as UTC', () => {
    expect(parseUtc('2026-10-01T10:00:00').toISOString()).toBe('2026-10-01T10:00:00.000Z');
    expect(parseUtc('2026-10-01T10:00:00+02:00').toISOString()).toBe('2026-10-01T08:00:00.000Z');
    expect(parseUtc(null)).toBeNull();
    expect(parseUtc('garbage')).toBeNull();
  });
  it('formats relative times in both directions', () => {
    const now = Date.parse('2026-10-01T10:00:00Z');
    expect(relativeTime('2026-10-04T13:00:00', now)).toBe('in 3d 3h');
    expect(relativeTime('2026-10-01T08:30:00', now)).toBe('1h 30m ago');
  });
});

describe('lifecycle stages come from real data', () => {
  it('bot not started -> not_started, never invitable', () => {
    const rows = buildRows({ admins: [admin({ can_dm: false })] });
    expect(rows[0].stage).toBe('not_started');
    expect(canInvite(rows[0])).toBe(false);
  });
  it('bot started, nothing sent -> ready', () => {
    const rows = buildRows({ admins: [admin()] });
    expect(rows[0].stage).toBe('ready');
    expect(canInvite(rows[0])).toBe(true);
  });
  it('invitation sent is pending, and not invitable again', () => {
    const rows = buildRows({ admins: [admin({ pending: true })], invitations: [inv()] });
    expect(rows[0].stage).toBe('pending');
    expect(canInvite(rows[0])).toBe(false);
  });
  it('an accepted invitation without access is NOT active (revoked); with access it is active', () => {
    const accepted = inv({ status: 'accepted', used_by: 7, used_at: '2026-10-02T10:00:00' });
    expect(stageOf(buildRows({ admins: [admin()], invitations: [accepted] }), '222')).toBe('revoked');
    const rows = buildRows({
      admins: [admin({ has_access: true, member_user_id: 7, member_role: 'manager' })],
      members: [member()], invitations: [accepted],
    });
    expect(rows[0].stage).toBe('active');
    expect(rows).toHaveLength(1); // the member is not duplicated as a second row
  });
  it('declined and expired are distinct, and both can be re-invited', () => {
    const declined = buildRows({ admins: [admin()], invitations: [inv({ status: 'declined', declined_at: '2026-10-01T11:00:00' })] });
    const expired = buildRows({ admins: [admin()], invitations: [inv({ status: 'expired' })] });
    expect(declined[0].stage).toBe('declined');
    expect(expired[0].stage).toBe('expired');
    expect(canInvite(declined[0])).toBe(true);
    expect(canInvite(expired[0])).toBe(true);
  });
  it('the newest invitation wins over older finished ones', () => {
    const rows = buildRows({
      admins: [admin()],
      invitations: [
        inv({ id: 1, status: 'declined', created_at: '2026-09-01T10:00:00' }),
        inv({ id: 2, status: 'pending', created_at: '2026-10-01T10:00:00' }),
      ],
    });
    expect(rows[0].stage).toBe('pending');
    expect(rows[0].history.map((i) => i.id)).toEqual([2, 1]);
  });
});

describe('rows for people the admin list does not cover', () => {
  it('a member who joined with a code gets their own row and is active', () => {
    const rows = buildRows({ admins: [], members: [member({ user_id: 9, full_name: null, email: 'c@x.io' })] });
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ name: 'c@x.io', stage: 'active', viaCode: true });
    expect(stepsFor(rows[0]).map((s) => s.state)).toEqual(['na', 'na', 'na', 'done']);
  });
  it('an invitee who is no longer an admin keeps their history but cannot be invited', () => {
    const rows = buildRows({ admins: [], invitations: [inv({ status: 'declined' })] });
    expect(rows[0]).toMatchObject({ stage: 'declined', isAdmin: false });
    expect(canInvite(rows[0])).toBe(false);
  });
  it('when the admin list failed, nothing about bot state is claimed', () => {
    const rows = buildRows({ admins: null, invitations: [inv()], members: [member({ user_id: 9 })] });
    const pending = rows.find((r) => r.tgId === '222');
    expect(pending.botStarted).toBeNull();
    expect(pending.isAdmin).toBeNull();
    expect(canInvite(pending)).toBe(false);
  });
  it('whole-bot access is listed read-only as active', () => {
    const rows = buildRows({ admins: [], inherited: [{ bot_key: 'my_bot', user_id: 5, full_name: 'Zed', role: 'viewer' }] });
    expect(rows[0]).toMatchObject({ stage: 'inherited', inheritedFrom: 'my_bot' });
    expect(canInvite(rows[0])).toBe(false);
  });
});

describe('progress steps', () => {
  const steps = (row) => stepsFor(row).map((s) => s.state);
  it('walks bot -> sent -> accepted -> active', () => {
    const base = { admins: [admin({ can_dm: false })] };
    expect(steps(buildRows(base)[0])).toEqual(['todo', 'todo', 'todo', 'todo']);
    expect(steps(buildRows({ admins: [admin()] })[0])).toEqual(['done', 'todo', 'todo', 'todo']);
    expect(steps(buildRows({ admins: [admin()], invitations: [inv()] })[0])).toEqual(['done', 'done', 'todo', 'todo']);
    const accepted = inv({ status: 'accepted', used_by: 7, used_at: '2026-10-02T10:00:00' });
    const active = buildRows({ admins: [admin({ member_user_id: 7 })], members: [member()], invitations: [accepted] })[0];
    expect(steps(active)).toEqual(['done', 'done', 'done', 'done']);
  });
  it('shows declined, expired and revoked as problems, not progress', () => {
    expect(steps(buildRows({ admins: [admin()], invitations: [inv({ status: 'declined' })] })[0])).toEqual(['done', 'done', 'error', 'todo']);
    expect(steps(buildRows({ admins: [admin()], invitations: [inv({ status: 'expired' })] })[0])).toEqual(['done', 'warn', 'todo', 'todo']);
    const accepted = inv({ status: 'accepted', used_by: 7, used_at: '2026-10-02T10:00:00' });
    expect(steps(buildRows({ admins: [admin()], invitations: [accepted] })[0])).toEqual(['done', 'done', 'done', 'error']);
  });
});

describe('timeline only reports recorded events', () => {
  it('orders newest first and never invents a revocation time', () => {
    const accepted = inv({ status: 'accepted', used_by: 7, used_at: '2026-10-02T10:00:00' });
    const row = buildRows({ admins: [admin()], invitations: [accepted] })[0];
    const t = timelineFor(row);
    expect(t.map((e) => e.text)).toEqual(['Invitation accepted', 'Invitation sent as Manager']);
    expect(t.every((e) => e.at)).toBe(true);
  });
  it('a member with no recorded invitation is not mislabelled or shown with fake gaps', () => {
    const row = buildRows({ admins: [admin({ member_user_id: 7 })], members: [member()] })[0];
    expect(row.stage).toBe('active');
    expect(stepsFor(row).map((s) => s.state)).toEqual(['na', 'na', 'na', 'done']);
    expect(timelineFor(row)[0].text).toBe('Access granted as Manager');
  });
  it('a code member gets a single access event', () => {
    const row = buildRows({ admins: [], members: [member({ user_id: 9 })] })[0];
    expect(timelineFor(row)).toHaveLength(1);
  });
});

describe('filters, search and overview numbers', () => {
  const data = {
    admins: [
      admin({ user_id: '1', name: 'Ready Rae' }),
      admin({ user_id: '2', name: 'Sleepy Sam', can_dm: false }),
      admin({ user_id: '3', name: 'Pending Pat', pending: true }),
      admin({ user_id: '4', name: 'Active Amy', member_user_id: 7 }),
    ],
    members: [member({ user_id: 7, full_name: 'Active Amy' })],
    invitations: [inv({ id: 3, invitee_telegram_id: '3' })],
  };
  const rows = buildRows(data);
  it('counts each filter from the rows', () => {
    expect(filterCounts(rows)).toEqual({ all: 4, ready: 1, pending: 1, active: 1, not_started: 1 });
  });
  it('searches name, username and telegram id', () => {
    expect(rows.filter((r) => matchesSearch(r, 'rae')).map((r) => r.tgId)).toEqual(['1']);
    expect(rows.filter((r) => matchesSearch(r, '  3 ')).map((r) => r.tgId)).toEqual(['3']);
    expect(rows.filter((r) => matchesSearch(r, ''))).toHaveLength(4);
  });
  it('an already-active admin is not "ready to invite"', () => {
    expect(matchesFilter(rows.find((r) => r.tgId === '4'), 'ready')).toBe(false);
  });
  it('overview numbers are counted, and null when admins are unavailable', () => {
    expect(overview({ ...data, codes: [{}, {}], max: 10 })).toEqual({
      active: 1, max: 10, pending: 1, reserved: 3, codes: 2, adminCount: 4, botReady: 3, notStarted: 1,
    });
    expect(overview({ ...data, admins: null })).toMatchObject({ botReady: null, notStarted: null, adminCount: null });
  });
});
