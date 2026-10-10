import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Box, Chip, LinearProgress, Typography } from '@mui/material';
import { settings } from '../../services/api';

// ── labels (never show raw enum values) ───────────────────────────────────────
export const STATUS_LABEL = { draft: 'Draft', active: 'Active', paused: 'Paused', closed: 'Closed', archived: 'Archived' };
export const STATUS_COLOR = { draft: 'default', active: 'success', paused: 'warning', closed: 'default', archived: 'default' };
export const SUB_LABEL = { pending: 'Pending review', verified: 'Approved', rejected: 'Rejected' };
export const SUB_COLOR = { pending: 'warning', verified: 'success', rejected: 'error' };
export const TYPE_LABEL = {
  social_task: 'Social task', proof_collection: 'Proof collection', content_submission: 'Content submission',
  giveaway: 'Giveaway', raid: 'Twitter raid',
};
export const SOURCE_LABEL = {
  admin: 'Approved by an administrator', api: 'Verified automatically via API', self_reported: 'Self-reported (honor-based)',
  telegram_auto: 'Verified automatically (Telegram)', link_check: 'Link check', automatic: 'Automatic',
};
export const POST_LABEL = { posted: 'Posted to group', failed: 'Post failed', posting: 'Posting…', none: 'Not posted' };
export const GOAL_LABEL = { likes: 'Likes', retweets: 'Reposts', comments: 'Comments', quotes: 'Quotes', follows: 'Follows' };

// ── time (server timestamps are UTC without a zone suffix) ────────────────────
export function fmtTime(ts, tz, opts) {
  if (!ts) return '—';
  const d = new Date(/(Z|[+-]\d\d:?\d\d)$/.test(ts) ? ts : `${ts}Z`);
  try {
    return d.toLocaleString([], { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: tz || undefined, ...opts });
  } catch {
    return d.toLocaleString();
  }
}

export function timeLeft(ts) {
  if (!ts) return null;
  const ms = new Date(/(Z|[+-]\d\d:?\d\d)$/.test(ts) ? ts : `${ts}Z`).getTime() - Date.now();
  if (ms <= 0) return 'ended';
  const h = ms / 3600000;
  if (h >= 48) return `${Math.floor(h / 24)} days left`;
  if (h >= 1) return `${Math.floor(h)}h left`;
  return `${Math.max(1, Math.floor(ms / 60000))}m left`;
}

// ── workspace context: the current group is the boundary ──────────────────────
const Ctx = createContext(null);
export const useWorkspace = () => useContext(Ctx);

export function WorkspaceProvider({ children }) {
  const { id: rawBotId, groupId } = useParams();
  const botId = rawBotId || 'official';
  const isOfficial = !rawBotId;
  const [info, setInfo] = useState({ loading: true, error: null, group: null, tier: 'free', role: null, tz: 'UTC' });
  const [tick, setTick] = useState(0);              // bumped after changes so every view refetches
  const bump = useCallback(() => setTick((n) => n + 1), []);

  useEffect(() => {
    let cancelled = false;
    setInfo((i) => ({ ...i, loading: true, error: null }));
    settings.getGroupSettings(botId, groupId)
      .then((r) => {
        if (cancelled) return;
        const g = r.data.group || {};
        setInfo({
          loading: false, error: null, group: g,
          tier: r.data.owner_plan || 'free', role: r.data.access_role || null,
          tz: r.data.timezone || g.timezone || 'UTC',
        });
      })
      .catch((e) => { if (!cancelled) setInfo((i) => ({ ...i, loading: false, error: e?.response?.status === 404 ? 'This group was not found or you do not have access.' : 'Could not load this group.' })); });
    return () => { cancelled = true; };
  }, [botId, groupId]);

  const base = isOfficial ? `/groups/${groupId}` : `/bot/${rawBotId}/group/${groupId}`;
  const paths = {
    group: base,
    overview: `${base}/campaigns`,
    list: `${base}/campaigns/all`,
    review: `${base}/campaigns/review`,
    create: (type) => `${base}/campaigns/new${type ? `?type=${type}` : ''}`,
    detail: (id, tab) => `${base}/campaigns/${id}${tab ? `?tab=${tab}` : ''}`,
    crm: `${base}/crm`,
  };
  const value = {
    botId, rawBotId, groupId, isOfficial, paths, tick, bump,
    groupName: info.group?.title || info.group?.group_name || info.group?.name || null,
    group: info.group, tier: info.tier, isPaid: info.tier && info.tier !== 'free',
    role: info.role, isViewer: info.role === 'viewer', tz: info.tz, ready: !info.loading, loadError: info.error,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

/**
 * Loads data and refreshes it modestly (default every 60s, only while the tab is
 * visible). Exposes when it was last fetched and whether the last refresh failed,
 * so the UI can say so honestly instead of implying anything is "live".
 */
export function usePolled(fetcher, deps, { intervalMs = 60000, enabled = true } = {}) {
  const [state, setState] = useState({ data: null, loading: enabled, error: null, at: null, stale: false });
  const seq = useRef(0);
  const fetchRef = useRef(fetcher);
  fetchRef.current = fetcher;
  const load = useCallback((quiet) => {
    if (!enabled) return Promise.resolve();
    const my = ++seq.current;
    if (!quiet) setState((s) => ({ ...s, loading: true, error: null }));
    return fetchRef.current()
      .then((r) => { if (my === seq.current) setState({ data: r.data, loading: false, error: null, at: new Date(), stale: false }); })
      .catch((e) => {
        if (my === seq.current) {
          setState((s) => ({ ...s, loading: false, error: e?.response?.data?.error || 'Could not load this view', stale: !!s.data }));
        }
      });
  }, [enabled]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(false); }, [...deps, enabled]);
  useEffect(() => {
    if (!enabled || !intervalMs) return undefined;
    const t = setInterval(() => { if (document.visibilityState === 'visible') load(true); }, intervalMs);
    return () => clearInterval(t);
  }, [enabled, intervalMs, load]);
  return { ...state, reload: () => load(false) };
}

export function Freshness({ at, error, stale, intervalMs = 60000, tz }) {
  if (!at && !error) return null;
  const secs = Math.round(intervalMs / 1000);
  return (
    <Typography variant="caption" color={stale ? 'warning.main' : 'text.secondary'} role="status">
      {stale
        ? `Couldn't refresh - showing data from ${at ? fmtTime(at.toISOString(), tz, { year: undefined }) : 'earlier'}.`
        : at ? `Updated ${fmtTime(at.toISOString(), tz, { year: undefined })} · refreshes about every ${secs}s while open` : error}
    </Typography>
  );
}

export function TypeChip({ type }) {
  return <Chip size="small" variant="outlined" label={TYPE_LABEL[type] || type} />;
}
export function StatusChip({ status }) {
  return <Chip size="small" color={STATUS_COLOR[status] || 'default'} variant={status === 'active' ? 'filled' : 'outlined'} label={STATUS_LABEL[status] || status} />;
}

/** A progress bar that always says what it measures. */
export function LabeledProgress({ label, done, target, unit }) {
  const pct = Math.min(100, Math.round((done / target) * 100));
  return (
    <Box sx={{ minWidth: 0 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 1 }}>
        <Typography variant="caption" color="text.secondary" noWrap>{label}</Typography>
        <Typography variant="caption" fontWeight={700}>{done.toLocaleString()} / {target.toLocaleString()}{unit ? ` ${unit}` : ''}</Typography>
      </Box>
      <LinearProgress variant="determinate" value={pct} aria-label={`${label}: ${done} of ${target}`} sx={{ height: 6, borderRadius: 3 }} />
    </Box>
  );
}

export function ProgressBlock({ progress }) {
  if (!progress) return null;
  const rows = [];
  if (progress.participants) {
    rows.push(<LabeledProgress key="p" label="Approved people vs participant limit" done={progress.participants.done} target={progress.participants.target} />);
  }
  (progress.actions || []).forEach((a) => {
    rows.push(<LabeledProgress key={a.goal} label={`${GOAL_LABEL[a.goal] || a.goal} (verified)`} done={a.done} target={a.target} />);
  });
  if (!rows.length) return null;
  return <Box sx={{ display: 'grid', gap: 0.75 }}>{rows}</Box>;
}
