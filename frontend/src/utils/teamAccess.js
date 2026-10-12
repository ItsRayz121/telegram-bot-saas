// Pure state derivation for the Team Access dashboard. Everything here is computed from what the
// backend returned (admins, members, invitations); nothing is assumed or invented.
//
// Two independent things are tracked per person:
//   - bot connection:       did they press Start on the group's bot?  (botStarted)
//   - invitation lifecycle: none -> pending -> accepted -> active, or declined / expired / revoked.

// The backend stores naive UTC datetimes and serialises them without a "Z".
export function parseUtc(iso) {
  if (!iso) return null;
  const s = String(iso);
  const d = new Date(/[zZ]|[+-]\d{2}:?\d{2}$/.test(s) ? s : `${s}Z`);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function fmtDateTime(iso) {
  const d = parseUtc(iso);
  return d ? d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : '';
}

export function fmtDate(iso) {
  const d = parseUtc(iso);
  return d ? d.toLocaleDateString(undefined, { dateStyle: 'medium' }) : '';
}

// "in 6d 3h" / "2d ago"
export function relativeTime(iso, now = Date.now()) {
  const d = parseUtc(iso);
  if (!d) return '';
  const diff = d.getTime() - now;
  const abs = Math.abs(diff);
  const mins = Math.floor(abs / 60000);
  const hrs = Math.floor(mins / 60);
  const days = Math.floor(hrs / 24);
  let text;
  if (days >= 1) text = `${days}d${hrs % 24 ? ` ${hrs % 24}h` : ''}`;
  else if (hrs >= 1) text = `${hrs}h${mins % 60 ? ` ${mins % 60}m` : ''}`;
  else text = `${Math.max(mins, 1)}m`;
  return diff >= 0 ? `in ${text}` : `${text} ago`;
}

export const ROLE_LABEL = { manager: 'Manager', viewer: 'Viewer' };

export const ROLE_PERMISSIONS = {
  manager: [
    'Change settings, moderation, automations, forwarding and tasks',
    'See everything in this group',
  ],
  viewer: [
    'See everything in this group',
    'Cannot change anything',
  ],
};
export const ALWAYS_OWNER_ONLY = [
  'Unlink the group, manage AI API keys or billing',
  'Invite, change or remove team members',
];

export const STAGE_META = {
  active:      { label: 'Active',          tone: 'success' },
  inherited:   { label: 'Active (whole bot)', tone: 'success' },
  pending:     { label: 'Pending',         tone: 'warning' },
  ready:       { label: 'Ready to invite', tone: 'info' },
  not_started: { label: 'Not started',     tone: 'neutral' },
  declined:    { label: 'Declined',        tone: 'error' },
  expired:     { label: 'Expired',         tone: 'neutral' },
  revoked:     { label: 'Revoked',         tone: 'error' },
  unknown:     { label: 'Unknown',         tone: 'neutral' },
};

const latestFirst = (a, b) => {
  const ta = parseUtc(a.created_at)?.getTime() || 0;
  const tb = parseUtc(b.created_at)?.getTime() || 0;
  return tb - ta || (b.id || 0) - (a.id || 0);
};

function stageOf({ member, latest, botStarted }) {
  if (member) return 'active';
  if (latest) {
    if (latest.status === 'pending') return 'pending';
    if (latest.status === 'accepted') return 'revoked'; // accepted, but the access row is gone
    if (latest.status === 'declined') return 'declined';
    if (latest.status === 'expired') return 'expired';
  }
  if (botStarted === true) return 'ready';
  if (botStarted === false) return 'not_started';
  return 'unknown';
}

// Can the owner send a (new) direct invitation to this person right now?
export function canInvite(row) {
  return row.isAdmin === true && row.botStarted === true && !row.member && row.stage !== 'pending';
}

/**
 * Merge the three backend lists into one row per person.
 *   admins       GET .../team/admins -> admins[]   (null when it could not be loaded)
 *   members      GET .../team        -> members[]
 *   invitations  GET .../team        -> invitations[] (direct invites, every state)
 *   inherited    GET .../team        -> inherited[]  (whole-bot access, read-only here)
 */
export function buildRows({ admins, members = [], invitations = [], inherited = [] }) {
  const adminsLoaded = Array.isArray(admins);
  const memberById = new Map(members.map((m) => [m.user_id, m]));
  const invByTg = new Map();
  [...invitations].sort(latestFirst).forEach((i) => {
    const k = String(i.invitee_telegram_id);
    if (!invByTg.has(k)) invByTg.set(k, []);
    invByTg.get(k).push(i);
  });
  const seenMembers = new Set();
  const seenTg = new Set();
  const rows = [];

  const make = (base) => {
    const history = base.history || [];
    const latest = history[0] || null;
    const viaInvite = history.some((i) => i.status === 'accepted');
    const stage = stageOf({ member: base.member, latest, botStarted: base.botStarted });
    return { ...base, history, latest, viaInvite, stage };
  };

  (admins || []).forEach((a) => {
    const tg = String(a.user_id);
    seenTg.add(tg);
    const member = a.member_user_id != null ? memberById.get(a.member_user_id) || null : null;
    if (member) seenMembers.add(member.user_id);
    rows.push(make({
      key: `tg-${tg}`, tgId: tg, name: a.name, username: a.username || null,
      tgStatus: a.status || null, isAdmin: true, botStarted: !!a.can_dm,
      member, history: invByTg.get(tg) || [],
    }));
  });

  // Invitees who are no longer in the admin list (or the list could not be loaded).
  invByTg.forEach((history, tg) => {
    if (seenTg.has(tg)) return;
    const accepted = history.find((i) => i.status === 'accepted' && i.used_by != null);
    const member = accepted ? memberById.get(accepted.used_by) || null : null;
    if (member) seenMembers.add(member.user_id);
    rows.push(make({
      key: `tg-${tg}`, tgId: tg, name: history[0].invitee_name || `Telegram user ${tg}`, username: null,
      tgStatus: null, isAdmin: adminsLoaded ? false : null, botStarted: null, member, history,
    }));
  });

  // Members with no Telegram link in the data we have (joined with an access code).
  members.forEach((m) => {
    if (seenMembers.has(m.user_id)) return;
    rows.push(make({
      key: `m-${m.user_id}`, tgId: null, name: m.full_name || m.email || `User ${m.user_id}`,
      username: null, email: m.email || null, isAdmin: null, botStarted: null, member: m,
      history: [], viaCode: true,
    }));
  });

  inherited.forEach((m) => {
    rows.push({
      key: `inh-${m.bot_key}-${m.user_id}`, tgId: null, name: m.full_name || m.email || `User ${m.user_id}`,
      username: null, email: m.email || null, isAdmin: null, botStarted: null, member: null,
      history: [], latest: null, viaInvite: false, stage: 'inherited',
      inheritedFrom: m.bot_key, inheritedRole: m.role,
    });
  });

  const order = { pending: 0, active: 1, inherited: 2, ready: 3, declined: 4, expired: 5, revoked: 6, unknown: 7, not_started: 8 };
  rows.sort((a, b) => (order[a.stage] - order[b.stage]) || a.name.localeCompare(b.name));
  return rows;
}

export const FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'ready', label: 'Ready to invite' },
  { id: 'pending', label: 'Pending' },
  { id: 'active', label: 'Active' },
  { id: 'not_started', label: 'Not started' },
];

export function matchesFilter(row, filter) {
  switch (filter) {
    case 'ready': return canInvite(row);
    case 'pending': return row.stage === 'pending';
    case 'active': return row.stage === 'active' || row.stage === 'inherited';
    case 'not_started': return row.isAdmin === true && row.botStarted === false && !row.member;
    default: return true;
  }
}

export function matchesSearch(row, q) {
  const s = q.trim().toLowerCase();
  if (!s) return true;
  return [row.name, row.username, row.email, row.tgId, row.member?.email, row.member?.full_name]
    .some((v) => v && String(v).toLowerCase().includes(s));
}

export function filterCounts(rows) {
  const out = {};
  FILTERS.forEach((f) => { out[f.id] = rows.filter((r) => matchesFilter(r, f.id)).length; });
  return out;
}

// The four overview numbers. Admin-derived ones are null while the Telegram admin list is unavailable.
export function overview({ admins, members = [], invitations = [], codes = [], max = 10 }) {
  const adminsLoaded = Array.isArray(admins);
  const pending = invitations.filter((i) => i.status === 'pending').length;
  return {
    active: members.length,
    max,
    pending,
    reserved: pending + codes.length, // pending DM invitations and open codes both use a slot
    codes: codes.length,
    adminCount: adminsLoaded ? admins.length : null,
    botReady: adminsLoaded ? admins.filter((a) => a.can_dm).length : null,
    notStarted: adminsLoaded ? admins.filter((a) => !a.can_dm).length : null,
  };
}

/**
 * The four-step progress for one person. Each step: done | todo | warn | error | na | unknown.
 * "na" = does not apply (someone who joined with an access code never had a DM invitation).
 */
export function stepsFor(row) {
  if (row.stage === 'inherited') {
    return [
      { key: 'bot', label: 'Bot started', state: 'na' },
      { key: 'sent', label: 'Invitation sent', state: 'na' },
      { key: 'accepted', label: 'Invitation accepted', state: 'na' },
      { key: 'active', label: 'Access active', state: 'done' },
    ];
  }
  const hasInvite = row.history.length > 0;
  // No recorded invitation (code join, or an invitation older than the 90-day history): do not claim either.
  const code = !!row.viaCode || (!!row.member && !hasInvite);
  let bot = 'unknown';
  if (code) bot = 'na';
  else if (row.botStarted === true || hasInvite) bot = 'done';
  else if (row.botStarted === false) bot = 'todo';
  const sent = code ? 'na' : !hasInvite ? 'todo' : row.stage === 'expired' ? 'warn' : 'done';
  let accepted = 'todo';
  if (code) accepted = 'na';
  else if (row.viaInvite) accepted = 'done';
  else if (row.stage === 'declined') accepted = 'error';
  let active = 'todo';
  if (row.member) active = 'done';
  else if (row.stage === 'revoked') active = 'error';
  return [
    { key: 'bot', label: 'Bot started', state: bot },
    { key: 'sent', label: row.stage === 'expired' ? 'Invitation expired' : 'Invitation sent', state: sent },
    { key: 'accepted', label: row.stage === 'declined' ? 'Invitation declined' : 'Invitation accepted', state: accepted },
    { key: 'active', label: row.stage === 'revoked' ? 'Access revoked' : 'Access active', state: active },
  ];
}

/** Dated events for the drawer, newest first. Only things the backend actually recorded. */
export function timelineFor(row) {
  const ev = [];
  row.history.forEach((i) => {
    const role = ROLE_LABEL[i.role] || i.role;
    ev.push({ at: i.created_at, text: `Invitation sent as ${role}`, tone: 'info' });
    if (i.status === 'accepted') ev.push({ at: i.used_at, text: 'Invitation accepted', tone: 'success' });
    if (i.status === 'declined') ev.push({ at: i.declined_at, text: 'Invitation declined', tone: 'error' });
    if (i.status === 'expired') ev.push({ at: i.expires_at, text: 'Invitation expired without a response', tone: 'neutral' });
  });
  if (row.member && !row.viaInvite) {
    ev.push({ at: row.member.joined_at, text: `Access granted as ${ROLE_LABEL[row.member.role] || row.member.role}`, tone: 'success' });
  }
  return ev.sort((a, b) => (parseUtc(b.at)?.getTime() || 0) - (parseUtc(a.at)?.getTime() || 0));
}
