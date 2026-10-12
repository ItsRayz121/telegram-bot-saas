import React, { useCallback, useEffect, useState } from 'react';
import { Alert, Box, Button, CircularProgress, MenuItem, Select, Stack, Tooltip, Typography } from '@mui/material';
import guildizerApi from '../../services/guildizerApi';

function Tile({ label, value, hint }) {
  return (
    <Box sx={{ flex: '1 1 130px', border: 1, borderColor: 'divider', borderRadius: 1, p: 1.25, minWidth: 0 }}>
      <Typography variant="caption" color="text.secondary">{label}</Typography>
      <Typography variant="h6" fontWeight={700}>{value}</Typography>
      {hint && <Typography variant="caption" color="text.secondary" display="block">{hint}</Typography>}
    </Box>
  );
}

function Bars({ series, label }) {
  const max = Math.max(1, ...series.map((d) => d.count));
  return (
    <Box sx={{ display: 'flex', alignItems: 'flex-end', gap: '2px', height: 44, mt: 1, width: '100%' }} role="img" aria-label={label}>
      {series.map((d) => (
        <Tooltip key={d.date} title={`${d.date}: ${d.count}`}>
          <Box sx={{ flex: 1, bgcolor: 'primary.main', height: `${(d.count / max) * 100}%`, minHeight: d.count ? 2 : 0 }} />
        </Tooltip>
      ))}
    </Box>
  );
}

const num = (n) => Number(n || 0).toLocaleString();

// Each kind maps its payload to tiles + an optional list and chart. All numbers come
// from the server over the whole server (not just the rows on screen).
const KINDS = {
  members: {
    ranged: false,
    tiles: (d) => [
      ['Members tracked', num(d.total)],
      ['Active, last 7 days', num(d.active['7d']), `${num(d.active['24h'])} in 24h · ${num(d.active['30d'])} in 30d`],
      ['Verified', num(d.verified)],
      ['With a warning', num(d.with_warnings)],
      ['With a wallet', num(d.with_wallet)],
    ],
    lists: (d) => [['Members by level', d.level_distribution.map((b) => `${b.label}: ${num(b.count)}`).join(' · ')]],
  },
  audit: {
    ranged: true,
    tiles: (d) => [
      ['Events', num(d.total)],
      ['From AI layers', num(d.ai_events)],
      ['From rules and staff', num(d.rule_events)],
    ],
    lists: (d) => [
      ['By type', d.by_category.map((c) => `${c.category}: ${num(c.count)}`).join(' · ') || 'None'],
      ['Most actioned', d.most_actioned_members.map((m) => `${m.username || m.user_id} (${m.count})`).join(' · ') || 'None'],
    ],
    series: (d) => d.series,
  },
  warnings: {
    ranged: true,
    tiles: (d) => [
      ['Warnings on record', num(d.total)],
      ['Members warned', num(d.members_warned)],
      ['In this range', num(d.recent)],
      ['Repeat offenders', num(d.repeat_offenders), '2 or more warnings'],
      ['From automod', num(d.from_automod), `${num(d.from_moderators)} from moderators`],
    ],
    lists: (d) => [['Most warned', d.top_warned.map((m) => `${m.username || m.user_id} (${m.count})`).join(' · ') || 'None']],
    series: (d) => d.series,
  },
  ai: {
    ranged: true,
    tiles: (d) => [
      ['AI requests', num(d.requests)],
      ['Tokens in / out', `${num(d.tokens_in)} / ${num(d.tokens_out)}`],
      ['Moderation decisions', num(d.moderation_decisions), `${num(d.moderation_removals)} removed · ${num(d.moderation_no_action)} no action`],
    ],
    lists: (d) => [['Models', d.by_model.map((m) => `${m.model}: ${num(m.requests)}`).join(' · ') || 'None']],
    series: (d) => d.series,
  },
};

/** Server-side summary strip for a Guildizer analytics sub-tab. Read-only. */
export default function InsightsStrip({ guildId, kind }) {
  const cfg = KINDS[kind];
  const [days, setDays] = useState(30);
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let live = true;
    setData(null);
    setError(false);
    guildizerApi.get(`/api/guilds/${guildId}/insights/${kind}`, { params: cfg.ranged ? { days } : {} })
      .then((r) => { if (live) setData(r.data); })
      .catch(() => { if (live) setError(true); });
    return () => { live = false; };
  }, [guildId, kind, days, cfg.ranged]);

  if (error) return <Alert severity="warning" sx={{ mb: 1.5 }}>Could not load the summary.</Alert>;
  if (!data) return <Box sx={{ display: 'grid', placeItems: 'center', py: 1.5 }}><CircularProgress size={20} /></Box>;
  return (
    <Box sx={{ mb: 2 }}>
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
        {cfg.tiles(data).map(([label, value, hint]) => <Tile key={label} label={label} value={value} hint={hint} />)}
      </Stack>
      {cfg.lists(data).map(([label, text]) => (
        <Typography key={label} variant="caption" color="text.secondary" display="block" sx={{ mt: 0.75 }}>
          <strong>{label}:</strong> {text}
        </Typography>
      ))}
      {cfg.series && <Bars series={cfg.series(data)} label={`${kind} per day`} />}
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mt: 0.5 }}>
        <Typography variant="caption" color="text.secondary">{data.note || ''}</Typography>
        {cfg.ranged && (
          <Select size="small" value={days} onChange={(e) => setDays(e.target.value)} inputProps={{ 'aria-label': 'Range' }}>
            {[7, 14, 30, 90].map((d) => <MenuItem key={d} value={d}>Last {d} days</MenuItem>)}
          </Select>
        )}
      </Box>
    </Box>
  );
}

/** Digest preview: the text the real digest would post. Never sends anything. */
export function DigestPreview({ guildId }) {
  const [label, setLabel] = useState('Daily');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  const load = useCallback((l) => {
    setLoading(true);
    setError(false);
    guildizerApi.get(`/api/guilds/${guildId}/insights/digest-preview`, { params: { label: l } })
      .then((r) => setData(r.data))
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [guildId]);

  useEffect(() => { load('Daily'); setLabel('Daily'); }, [load]);

  return (
    <Box sx={{ mt: 2 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap', mb: 0.5 }}>
        <Typography variant="subtitle2" fontWeight={700} sx={{ flex: 1 }}>Preview</Typography>
        <Select size="small" value={label} onChange={(e) => { setLabel(e.target.value); load(e.target.value); }}
          inputProps={{ 'aria-label': 'Digest type' }}>
          {['Daily', 'Weekly', 'Monthly'].map((l) => <MenuItem key={l} value={l}>{l}</MenuItem>)}
        </Select>
        <Button size="small" onClick={() => load(label)} disabled={loading}>Refresh</Button>
      </Box>
      {error && <Alert severity="warning">Could not build the preview.</Alert>}
      {data && (
        <Box component="pre" sx={{ m: 0, p: 1.5, bgcolor: 'action.hover', borderRadius: 1, whiteSpace: 'pre-wrap',
          wordBreak: 'break-word', fontFamily: 'inherit', fontSize: 13.5 }}>
          {data.text}
        </Box>
      )}
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
        Preview only: nothing is posted. {data && !data.enabled ? 'The digest is currently switched off.' : ''}
      </Typography>
    </Box>
  );
}
