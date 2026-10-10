import React, { useState } from 'react';
import { Alert, Avatar, Box, Button, Chip, Stack, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material';
import { Refresh } from '@mui/icons-material';
import { InsightError, Loading, Panel, useInsight } from './shared';

// Telegram Markdown (legacy): *bold*, _italic_. Anything else is shown as-is.
function renderLine(line, key) {
  const parts = [];
  const re = /(\*[^*\n]+\*|_[^_\n]+_)/g;
  let last = 0; let m; let i = 0;
  // eslint-disable-next-line no-cond-assign
  while ((m = re.exec(line))) {
    if (m.index > last) parts.push(line.slice(last, m.index));
    const tok = m[0];
    parts.push(tok[0] === '*'
      ? <strong key={`${key}-${i++}`}>{tok.slice(1, -1)}</strong>
      : <em key={`${key}-${i++}`}>{tok.slice(1, -1)}</em>);
    last = m.index + tok.length;
  }
  if (last < line.length) parts.push(line.slice(last));
  return parts;
}

function TelegramBubble({ text, title, time }) {
  const lines = text.split('\n');
  return (
    <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-end' }}>
      <Avatar sx={{ width: 32, height: 32, bgcolor: 'primary.main', fontSize: 14 }}>T</Avatar>
      <Box sx={{
        maxWidth: 440, width: '100%', bgcolor: '#182533', color: '#e8edf5', borderRadius: '14px 14px 14px 4px',
        px: 1.75, py: 1.25, boxShadow: 1,
      }}>
        <Typography variant="caption" sx={{ color: '#6ab3f3', fontWeight: 700, display: 'block' }}>{title}</Typography>
        <Box sx={{ fontSize: 14.5, lineHeight: 1.45, wordBreak: 'break-word' }}>
          {lines.map((l, i) => (
            <Box key={i} sx={{ minHeight: l ? undefined : '0.7em', whiteSpace: 'pre-wrap' }}>{renderLine(l, i)}</Box>
          ))}
        </Box>
        <Typography variant="caption" sx={{ color: '#7f91a4', display: 'block', textAlign: 'right', mt: 0.5 }}>{time}</Typography>
      </Box>
    </Box>
  );
}

const PERIODS = [
  { key: 'daily', label: 'Daily' },
  { key: 'weekly', label: 'Weekly' },
  { key: 'monthly', label: 'Monthly' },
];

/**
 * Website preview of the Telegram report. The text is produced by the same
 * server functions that build the real report; requesting it never sends
 * anything. Schedule + recipients shown beside it come from the (possibly
 * unsaved) form, so what you are editing is reflected immediately.
 */
export default function DigestPreview({ botId, groupId, config, fmt, refreshKey, botLabel = 'Telegizer' }) {
  const [period, setPeriod] = useState('weekly');
  const [variant, setVariant] = useState('manual');
  const { data, loading, error, reload } = useInsight(botId, groupId, 'digest-preview', { period, _r: refreshKey });
  const v = data?.variants?.find((x) => x.id === variant) || data?.variants?.[0];
  const rec = config?.recipients || {};
  const adminCount = (rec.selected_admin_ids || []).length;
  const targets = [
    (rec.send_to_group ?? true) && `Group chat${rec.group_topic_id ? ` (topic ${rec.group_topic_id})` : ''}`,
    rec.owner_dm && 'DM to the account owner',
    adminCount > 0 && `DM to ${adminCount} selected admin${adminCount === 1 ? '' : 's'}`,
  ].filter(Boolean);
  const scheduled = ['daily', 'weekly', 'monthly'].filter((k) => config?.[k]);
  const lastSent = config?.[`last_${period}`];

  return (
    <Panel
      title="Report preview"
      subtitle="How the report will look in Telegram. Previewing never sends anything."
      action={
        <Button size="small" startIcon={<Refresh />} onClick={reload} disabled={loading}>Refresh preview</Button>
      }
    >
      <Box sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap', alignItems: 'center', mb: 1.5 }}>
        <ToggleButtonGroup size="small" exclusive value={period} onChange={(_, p) => p && setPeriod(p)} aria-label="Report period">
          {PERIODS.map((p) => <ToggleButton key={p.key} value={p.key}>{p.label}</ToggleButton>)}
        </ToggleButtonGroup>
        {data?.variants?.length > 1 && (
          <ToggleButtonGroup size="small" exclusive value={v?.id} onChange={(_, x) => x && setVariant(x)} aria-label="Report type">
            {data.variants.map((x) => <ToggleButton key={x.id} value={x.id}>{x.label}</ToggleButton>)}
          </ToggleButtonGroup>
        )}
      </Box>

      {error && !data ? <InsightError message={error} onRetry={reload} /> : loading && !data ? <Loading label="Building preview…" /> : v && (
        <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', md: 'minmax(0, 1.2fr) minmax(0, 1fr)' }, alignItems: 'start' }}>
          <Box sx={{ bgcolor: '#0e1621', borderRadius: 2, p: 2, opacity: loading ? 0.6 : 1 }} aria-busy={loading}>
            <TelegramBubble text={v.text} title={botLabel} time={data.generated_at ? fmt(data.generated_at) : ''} />
            {v.id === 'scheduled' && v.ai_summary_enabled && (
              <Typography variant="caption" sx={{ color: '#7f91a4', display: 'block', mt: 1 }}>
                An AI summary is appended to the scheduled report when it is sent. It isn't generated for this preview.
              </Typography>
            )}
          </Box>
          <Stack spacing={1.25}>
            <Typography variant="body2" color="text.secondary">{v.description}</Typography>
            <Box>
              <Typography variant="caption" color="text.secondary">Sent to</Typography>
              <Box sx={{ mt: 0.5, display: 'flex', gap: 0.75, flexWrap: 'wrap' }}>
                {targets.length ? targets.map((t) => <Chip key={t} size="small" label={t} />)
                  : <Chip size="small" color="warning" label="No recipient selected" />}
              </Box>
            </Box>
            <Box>
              <Typography variant="caption" color="text.secondary">Automatic schedule</Typography>
              <Box sx={{ mt: 0.5, display: 'flex', gap: 0.75, flexWrap: 'wrap' }}>
                {scheduled.length ? scheduled.map((k) => (
                  <Chip key={k} size="small" color={k === period ? 'primary' : 'default'} variant={k === period ? 'filled' : 'outlined'} label={k} />
                )) : <Chip size="small" variant="outlined" label="Not scheduled" />}
              </Box>
            </Box>
            <Typography variant="caption" color="text.secondary">
              {lastSent ? `Last ${period} report sent ${fmt(lastSent)}.` : `No ${period} report has been sent yet.`}
              {' '}Covers the {data.period_days} day{data.period_days === 1 ? '' : 's'} up to now; times inside the report are UTC.
            </Typography>
            <Alert severity="info" icon={false} sx={{ py: 0 }}>
              Delivery history isn't stored per send — only the last-sent time above is recorded.
            </Alert>
          </Stack>
        </Box>
      )}
    </Panel>
  );
}
