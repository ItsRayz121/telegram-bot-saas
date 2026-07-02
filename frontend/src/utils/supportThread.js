// Shared rendering helpers for the live-chat thread (widget + admin inbox).
//
// A user's support thread is one permanent conversation split into dated
// SESSIONS (episodes). buildThreadItems walks the messages and interleaves
// session-start / session-end dividers so past issues stay visible and
// separated by when they happened. Dividers are only emitted for sessions that
// actually contain messages, so an empty (reopened-but-unused) session shows
// nothing.

export function buildThreadItems(messages, sessions) {
  const byId = {};
  (sessions || []).forEach((s) => { byId[s.id] = s; });

  const items = [];
  let curr; // undefined until first message
  (messages || []).forEach((m) => {
    if (m.session_id !== curr) {
      if (curr !== undefined && byId[curr]?.status === 'closed') {
        items.push({ kind: 'end', session: byId[curr], key: `end-${curr}` });
      }
      curr = m.session_id;
      const s = byId[curr];
      items.push({ kind: 'start', session: s || null, at: s?.started_at || m.created_at, key: `start-${curr}-${m.id}` });
    }
    items.push({ kind: 'msg', message: m, key: `m-${m.id}` });
  });
  if (curr !== undefined && byId[curr]?.status === 'closed') {
    items.push({ kind: 'end', session: byId[curr], key: `end-${curr}` });
  }
  return items;
}

const REASON_LABELS = {
  auto_idle: 'closed after inactivity',
  admin: 'closed by our team',
  user: 'closed',
};

export function closeReasonLabel(reason) {
  return REASON_LABELS[reason] || 'closed';
}

export function fmtDivider(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit',
  });
}
