/**
 * Analytics area subtabs (Telegizer-parity IA):
 * Leaderboard · Audit Log · Warnings · Digest · AI Activity.
 * (Overview reuses AnalyticsTab, Members reuses MembersTab.)
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Box, Card, CardContent, Typography, Chip, CircularProgress, Alert,
  IconButton, TextField, InputAdornment, Stack, Button, Menu, MenuItem, Divider,
  Table, TableHead, TableBody, TableRow, TableCell, Collapse, ToggleButtonGroup,
  ToggleButton, Tooltip,
} from '@mui/material';
import {
  Delete, Search, Download, Gavel,
  WarningAmber, VolumeOff, VolumeUp, LockOpen, PersonRemove, Block,
} from '@mui/icons-material';
import { useSearchParams } from 'react-router-dom';
import guildizerApi from '../../../services/guildizerApi';
import { DigestCard } from './ContentTab';
import { downloadCsv } from './csv';
import GuildizerCollapsibleCard from '../../../components/guildizer/GuildizerCollapsibleCard';

const TEXT_TYPES = new Set([0, 5]);
const CAT_LABEL = {
  nsfw: 'NSFW', csam: 'CSAM', invite: 'Invite', link: 'Link', custom: 'Blocked word',
  spam: 'Spam', raid: 'Raid', lockdown_join: 'Lockdown join', join_gate: 'Join gate', manual_lockdown: 'Lockdown',
  external_link: 'External link', emoji_flood: 'Emoji flood', caps_lock: 'Caps lock', language: 'Language',
  attachment: 'Attachment', sticker: 'Sticker', voice_message: 'Voice message',
  warning: 'Warning', moderation: 'Moderation', report: 'Report',
  smart_mod: 'Smart mod', smart_promo: 'Smart mod', image_ai: 'Image AI', image_nsfw: 'Image AI',
  verification: 'Verification', bot_policy: 'Bot policy', escalation: 'Escalation',
};
const CAT_COLOR = { nsfw: 'error', csam: 'error', raid: 'warning', manual_lockdown: 'warning', lockdown_join: 'warning', invite: 'info', link: 'info' };
const ACTION_COLOR = { ban: 'error', kick: 'warning', timeout: 'warning', warned: 'warning', deleted: 'default', restricted: 'info', none: 'default', untimeout: 'success', unban: 'success' };
const AI_CATEGORIES = new Set(['smart_mod', 'smart_promo', 'image_ai', 'image_nsfw', 'ask', 'ai', 'escalation']);
const PERIODS = [
  { value: 'all', label: 'All Time' }, { value: '30d', label: '30 Days' },
  { value: '7d', label: '7 Days' }, { value: '1d', label: 'Today' },
];

function Loading() {
  return <Box sx={{ display: 'grid', placeItems: 'center', py: 4 }}><CircularProgress /></Box>;
}

// ── Shared moderation row-action menu (Warn / Mute / Kick / Temp-ban / Ban) ────
const MOD_ACTIONS = [
  { key: 'warn', label: 'Warn', icon: <WarningAmber fontSize="small" />, confirm: false },
  { key: 'mute', label: 'Mute 1 hour', icon: <VolumeOff fontSize="small" />, minutes: 60, confirm: false },
  { key: 'kick', label: 'Kick (remove)', icon: <PersonRemove fontSize="small" />, confirm: true },
  { key: 'tempban', label: 'Temp-ban 24h', icon: <Gavel fontSize="small" />, minutes: 1440, confirm: true },
  { key: 'ban', label: 'Ban permanently', icon: <Block fontSize="small" />, confirm: true, danger: true },
  // Reverse actions — lift a timeout/ban applied by the bot or an admin.
  { key: 'unmute', label: 'Unmute (remove timeout)', icon: <VolumeUp fontSize="small" color="success" />, confirm: false, restore: true },
  { key: 'unban', label: 'Unban', icon: <LockOpen fontSize="small" color="success" />, confirm: true, restore: true },
];

export function ModActionMenu({ guildId, userId, username, reason, onActed }) {
  const [anchor, setAnchor] = useState(null);
  const [busy, setBusy] = useState(false);

  async function run(a) {
    setAnchor(null);
    const who = username || userId;
    if (a.confirm && !window.confirm(`${a.label} ${who}?`)) return;
    setBusy(true);
    try {
      await guildizerApi.post(`/api/guilds/${guildId}/moderation/action`, {
        action: a.key, user_id: String(userId), username, reason: reason || 'Dashboard action',
        ...(a.minutes ? { minutes: a.minutes } : {}),
      });
      onActed && onActed();
    } catch (e) {
      window.alert(e?.response?.data?.error === 'bot_not_in_server'
        ? 'The bot is not in this server.' : 'Could not apply that action (check the bot has the permission).');
    }
    setBusy(false);
  }

  if (!userId) return null;
  return (
    <>
      <Tooltip title="Moderate this member">
        <span><IconButton size="small" disabled={busy} onClick={(e) => setAnchor(e.currentTarget)}><Gavel fontSize="small" /></IconButton></span>
      </Tooltip>
      <Menu anchorEl={anchor} open={!!anchor} onClose={() => setAnchor(null)}>
        {MOD_ACTIONS.map((a, i) => (
          <React.Fragment key={a.key}>
            {a.restore && !MOD_ACTIONS[i - 1]?.restore && <Divider />}
            <MenuItem onClick={() => run(a)} sx={a.danger ? { color: 'error.main' } : (a.restore ? { color: 'success.main' } : undefined)}>
              <Box sx={{ mr: 1, display: 'flex' }}>{a.icon}</Box>{a.label}
            </MenuItem>
          </React.Fragment>
        ))}
      </Menu>
    </>
  );
}

// ── Leaderboard ────────────────────────────────────────────────────────────────
export function LeaderboardSubtab({ guildId }) {
  const [board, setBoard] = useState(null);
  const [error, setError] = useState(null);
  const [period, setPeriod] = useState('all');
  const [walletOnly, setWalletOnly] = useState(false);
  const [query, setQuery] = useState('');

  const load = useCallback(() => {
    const params = new URLSearchParams({ limit: '50', period });
    if (walletOnly) params.set('has_wallet', 'true');
    if (query.trim()) params.set('q', query.trim());
    guildizerApi.get(`/api/guilds/${guildId}/leaderboard?${params}`)
      .then(({ data }) => { setBoard(data.leaderboard || []); setError(null); })
      .catch(() => { setError('Failed to load the leaderboard.'); setBoard([]); });
  }, [guildId, period, walletOnly, query]);

  useEffect(() => {
    const t = setTimeout(load, 250);
    return () => clearTimeout(t);
  }, [load]);

  const periodXp = period !== 'all';
  const xpLabel = period === '1d' ? 'XP (Today)' : period === '7d' ? 'XP (7d)' : period === '30d' ? 'XP (30d)' : 'XP (All Time)';
  const exportCsv = () => {
    const headers = ['Rank', 'Name', 'User ID', xpLabel, 'Level', 'Role', 'Wallet Address'];
    const rows = (board || []).map((m) => [
      m.rank, m.username || '', m.user_id, periodXp ? (m.xp_period ?? 0) : m.xp, m.level, m.role || '', m.wallet || '',
    ]);
    downloadCsv(`leaderboard_${guildId}_${period}.csv`, headers, rows);
  };

  if (board === null) return <Loading />;

  return (
    <Card variant="outlined"><CardContent>
      <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" alignItems={{ md: 'center' }} spacing={1} mb={1}>
        <Typography variant="h6" fontWeight={600}>🏆 XP Leaderboard <Typography component="span" variant="body2" color="text.secondary">— top members ranked by XP</Typography></Typography>
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
          <ToggleButtonGroup size="small" exclusive value={period} onChange={(_, v) => v && setPeriod(v)}>
            {PERIODS.map((p) => <ToggleButton key={p.value} value={p.value} sx={{ px: 1.2 }}>{p.label}</ToggleButton>)}
          </ToggleButtonGroup>
          <Button size="small" variant={walletOnly ? 'contained' : 'outlined'} onClick={() => setWalletOnly((v) => !v)}>Has Wallet</Button>
          <Button size="small" startIcon={<Download />} onClick={exportCsv} disabled={!board.length}>Export CSV</Button>
        </Stack>
      </Stack>
      <TextField size="small" fullWidth placeholder="Search name, @username, Telegram ID, wallet…" value={query}
        onChange={(e) => setQuery(e.target.value)} sx={{ mb: 1 }}
        InputProps={{ startAdornment: <InputAdornment position="start"><Search fontSize="small" /></InputAdornment> }} />
      {error && <Alert severity="warning" sx={{ mb: 1 }}>{error}</Alert>}
      {board.length === 0 ? (
        <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>No members with XP yet. Members earn XP by chatting and voice activity.</Typography>
      ) : (
        <Box sx={{ overflowX: 'auto' }}>
          <Table size="small" sx={{ minWidth: 560 }}>
            <TableHead><TableRow>
              <TableCell>#</TableCell><TableCell>USER</TableCell>
              <TableCell align="right">{xpLabel.toUpperCase()}</TableCell>
              <TableCell align="right">LEVEL</TableCell><TableCell>ROLE</TableCell><TableCell>WALLET ADDRESS</TableCell>
            </TableRow></TableHead>
            <TableBody>
              {board.map((m) => {
                const medal = m.rank === 1 ? '🥇' : m.rank === 2 ? '🥈' : m.rank === 3 ? '🥉' : `${m.rank}`;
                return (
                  <TableRow key={m.user_id} hover>
                    <TableCell sx={{ fontWeight: 700 }}>{medal}</TableCell>
                    <TableCell><Typography variant="body2" fontWeight={600} noWrap>{m.username || m.user_id}</Typography></TableCell>
                    <TableCell align="right" sx={{ color: 'primary.main', fontWeight: 700 }}>{((periodXp ? m.xp_period : m.xp) || 0).toLocaleString()}</TableCell>
                    <TableCell align="right">{m.level}</TableCell>
                    <TableCell>{m.role ? <Chip size="small" variant="outlined" label={m.role} /> : '—'}</TableCell>
                    <TableCell>{m.wallet ? <Typography variant="caption" sx={{ fontFamily: 'monospace' }}>{m.wallet.length > 14 ? `${m.wallet.slice(0, 6)}…${m.wallet.slice(-4)}` : m.wallet}</Typography> : '—'}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </Box>
      )}
    </CardContent></Card>
  );
}

// ── Audit Log: every protection / moderation event ─────────────────────────────
export function AuditLogSubtab({ guildId }) {
  return <EventFeed guildId={guildId} title="Audit log" limit={150}
    subtitle="Moderation actions (bans, kicks, mutes, warns, purges) logged by your bot in this server."
    showActions />;
}

export function AIActivitySubtab({ guildId }) {
  return (
    <Stack spacing={0}>
      <AIStatusPanel guildId={guildId} />
      <GuildizerCollapsibleCard id="analytics.ai_activity" title="🤖 AI Activity" defaultOpen>
        <EventFeed guildId={guildId} title="AI activity" limit={200} bare
          filter={(e) => AI_CATEGORIES.has(e.category)}
          subtitle="Smart-moderation, image-AI and knowledge-base actions taken by the AI. Click a row to preview what the AI acted on."
          emptyText="No AI actions yet. Enable Smart mod, Image AI or the knowledge base to see activity here." />
      </GuildizerCollapsibleCard>
    </Stack>
  );
}

// AI Status panel — live layer states + action counts. Each chip deep-links to
// the setting that controls it (with a focus pulse).
function AIStatusPanel({ guildId }) {
  const [s, setS] = useState(null);
  const [, setParams] = useSearchParams();

  useEffect(() => {
    guildizerApi.get(`/api/guilds/${guildId}/ai-status`).then(({ data }) => setS(data)).catch(() => setS(false));
  }, [guildId]);

  const go = (link) => link && setParams({ tab: link.tab, sub: link.sub, ...(link.focus ? { focus: link.focus } : {}) });
  const chip = (label, on, link, onText = 'Enabled', offText = 'Off') => (
    <Tooltip title={link ? 'Open settings' : ''}>
      <Chip size="small" clickable={!!link} onClick={() => go(link)} variant="outlined"
        color={on ? 'success' : 'default'} label={`${label}: ${on ? onText : offText}`} sx={{ mr: 0.5, mb: 0.5 }} />
    </Tooltip>
  );

  if (s === null) return <Loading />;
  return (
    <GuildizerCollapsibleCard id="analytics.ai_status" title="🤖 AI Status" defaultOpen>
      {s === false ? (
        <Typography variant="body2" color="text.secondary">Could not load AI status.</Typography>
      ) : (
        <>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', mb: 1.5 }}>
            {chip('Smart Moderation', s.smart_moderation, s.links?.smart_moderation)}
            {chip('Human-Like Replies', s.human_like, s.links?.human_like)}
            {chip('Knowledge Base', s.kb_configured, s.links?.knowledge_base, 'Configured', 'Not set')}
            {chip(`Provider (${s.provider})`, s.provider_connected, s.links?.provider, 'Connected', 'Not connected')}
          </Box>
          {s.last_action_at && (
            <Typography variant="caption" color="text.secondary" display="block" mb={1.5}>
              Last AI action: {new Date(s.last_action_at).toLocaleString()}
            </Typography>
          )}
          <Stack direction="row" spacing={1}>
            {[['Today', s.counts?.today], ['This Week', s.counts?.week], ['This Month', s.counts?.month], ['Total', s.counts?.total]].map(([label, n]) => (
              <Box key={label} sx={{ flex: 1, textAlign: 'center', border: '1px solid', borderColor: 'divider', borderRadius: 1, py: 1 }}>
                <Typography variant="h6" fontWeight={800}>{n ?? 0}</Typography>
                <Typography variant="caption" color="text.secondary">{label}</Typography>
              </Box>
            ))}
          </Stack>
        </>
      )}
    </GuildizerCollapsibleCard>
  );
}

function EventFeed({ guildId, title, subtitle, limit, filter, showActions, bare, emptyText = 'No events yet.' }) {
  const [events, setEvents] = useState(null);
  const [error, setError] = useState(null);
  const [query, setQuery] = useState('');
  const [openId, setOpenId] = useState(null);

  const reload = useCallback(() => {
    guildizerApi.get(`/api/guilds/${guildId}/protection/events?limit=${limit}`)
      .then(({ data }) => setEvents(filter ? data.events.filter(filter) : data.events))
      .catch(() => { setError('Failed to load events.'); setEvents([]); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [guildId, limit]);
  useEffect(() => { reload(); }, [reload]);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q || !events) return events || [];
    return events.filter((e) => [e.action, e.username, e.detail, e.category, CAT_LABEL[e.category]]
      .some((v) => (v || '').toString().toLowerCase().includes(q)));
  }, [events, query]);

  if (events === null) return <Loading />;

  const inner = (
    <>
      <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ xs: 'stretch', sm: 'center' }} spacing={1} mb={1}>
        {!bare && <Typography variant="h6" fontWeight={600}>{title}</Typography>}
        <TextField size="small" placeholder="Search action, target, reason, detail…" value={query}
          onChange={(e) => setQuery(e.target.value)} sx={{ minWidth: { sm: 300 }, flex: bare ? 1 : 'unset' }}
          InputProps={{ startAdornment: <InputAdornment position="start"><Search fontSize="small" /></InputAdornment> }} />
      </Stack>
      {subtitle && <Typography variant="body2" color="text.secondary" mb={1.5}>{subtitle}</Typography>}
      {error && <Alert severity="warning" sx={{ mb: 1 }}>{error}</Alert>}
      {shown.length === 0 ? (
        <Typography variant="body2" color="text.secondary">{query.trim() ? 'No events match your search.' : emptyText}</Typography>
      ) : (
        <Box sx={{ overflowX: 'auto' }}>
          <Table size="small" sx={{ minWidth: 720 }}>
            <TableHead><TableRow>
              <TableCell>ACTION</TableCell><TableCell>TARGET</TableCell><TableCell>MODERATOR</TableCell>
              <TableCell>REASON</TableCell><TableCell>MSG PREVIEW</TableCell><TableCell>TIME</TableCell>
              {showActions && <TableCell align="center">ACT</TableCell>}
            </TableRow></TableHead>
            <TableBody>
              {shown.map((e) => (
                <React.Fragment key={e.id}>
                  <TableRow hover sx={{ cursor: 'pointer', '& > td': { borderBottom: openId === e.id ? 'none' : undefined } }}
                    onClick={() => setOpenId(openId === e.id ? null : e.id)}>
                    <TableCell><Chip size="small" variant="outlined" color={ACTION_COLOR[e.action] || 'default'} label={e.action || '—'} /></TableCell>
                    <TableCell><Typography variant="body2" noWrap>{e.username || (e.user_id ? e.user_id : '—')}</Typography></TableCell>
                    <TableCell><Typography variant="caption" color="text.secondary">@AutoMod</Typography></TableCell>
                    <TableCell><Chip size="small" variant="outlined" color={CAT_COLOR[e.category] || 'default'} label={CAT_LABEL[e.category] || e.category} /></TableCell>
                    <TableCell sx={{ maxWidth: 220 }}><Typography variant="caption" color="text.secondary" noWrap sx={{ display: 'block' }}>{e.detail || '—'}</Typography></TableCell>
                    <TableCell><Typography variant="caption" color="text.disabled" noWrap>{e.created_at ? new Date(e.created_at).toLocaleString() : ''}</Typography></TableCell>
                    {showActions && <TableCell align="center" onClick={(ev) => ev.stopPropagation()}>
                      <ModActionMenu guildId={guildId} userId={e.user_id} username={e.username} reason={CAT_LABEL[e.category] || e.category} onActed={reload} />
                    </TableCell>}
                  </TableRow>
                  <TableRow>
                    <TableCell colSpan={showActions ? 7 : 6} sx={{ py: 0, border: 0 }}>
                      <Collapse in={openId === e.id} unmountOnExit>
                        <Box sx={{ py: 1.5, pl: 1 }}>
                          <Typography variant="caption" fontWeight={700} display="block">Full detail</Typography>
                          <Typography variant="body2" color="text.secondary" sx={{ whiteSpace: 'pre-wrap', mb: 0.5 }}>{e.detail || '—'}</Typography>
                          <Typography variant="caption" color="text.disabled">Category: {CAT_LABEL[e.category] || e.category}{e.channel_id ? ` · channel ${e.channel_id}` : ''}</Typography>
                        </Box>
                      </Collapse>
                    </TableCell>
                  </TableRow>
                </React.Fragment>
              ))}
            </TableBody>
          </Table>
        </Box>
      )}
    </>
  );

  if (bare) return inner;
  return <Card variant="outlined"><CardContent>{inner}</CardContent></Card>;
}

// ── Warnings: active warnings with preview + removal + moderation ──────────────
export function WarningsSubtab({ guildId }) {
  const [warnings, setWarnings] = useState(null);
  const [error, setError] = useState(null);
  const [query, setQuery] = useState('');
  const [openId, setOpenId] = useState(null);

  const reload = useCallback(() => guildizerApi.get(`/api/guilds/${guildId}/warnings?limit=100`)
    .then(({ data }) => setWarnings(data.warnings))
    .catch(() => { setError('Failed to load warnings.'); setWarnings([]); }), [guildId]);
  useEffect(() => { reload(); }, [reload]);

  async function remove(id) {
    try { await guildizerApi.delete(`/api/guilds/${guildId}/warnings/${id}`); await reload(); }
    catch { setError('Could not remove the warning.'); }
  }

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q || !warnings) return warnings || [];
    return warnings.filter((w) => [w.username, w.user_id, w.reason, w.moderator_name]
      .some((v) => (v || '').toString().toLowerCase().includes(q)));
  }, [warnings, query]);

  if (warnings === null) return <Loading />;

  return (
    <Card variant="outlined"><CardContent>
      <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ xs: 'stretch', sm: 'center' }} spacing={1} mb={1}>
        <Typography variant="h6" fontWeight={600}>⚠️ Active Warnings <Chip size="small" label={warnings.length} sx={{ ml: 0.5 }} /></Typography>
        <TextField size="small" placeholder="Search member, reason, moderator…" value={query}
          onChange={(e) => setQuery(e.target.value)} sx={{ minWidth: { sm: 300 } }}
          InputProps={{ startAdornment: <InputAdornment position="start"><Search fontSize="small" /></InputAdornment> }} />
      </Stack>
      <Typography variant="body2" color="text.secondary" mb={1.5}>Active warnings issued by admins or AutoMod. Click any row to see full details.</Typography>
      {error && <Alert severity="warning" sx={{ mb: 1 }} onClose={() => setError(null)}>{error}</Alert>}
      {shown.length === 0 ? (
        <Typography variant="body2" color="text.secondary">{query.trim() ? 'No warnings match your search.' : 'No warnings on record. 🎉'}</Typography>
      ) : (
        <Box sx={{ overflowX: 'auto' }}>
          <Table size="small" sx={{ minWidth: 680 }}>
            <TableHead><TableRow>
              <TableCell>MEMBER</TableCell><TableCell>REASON</TableCell><TableCell>MSG PREVIEW</TableCell>
              <TableCell>ISSUED BY</TableCell><TableCell>DATE</TableCell><TableCell align="center">ACTIONS</TableCell>
            </TableRow></TableHead>
            <TableBody>
              {shown.map((w) => (
                <React.Fragment key={w.id}>
                  <TableRow hover sx={{ cursor: 'pointer', '& > td': { borderBottom: openId === w.id ? 'none' : undefined } }}
                    onClick={() => setOpenId(openId === w.id ? null : w.id)}>
                    <TableCell>
                      <Typography variant="body2" fontWeight={600} noWrap>{w.username || w.user_id}</Typography>
                      <Typography variant="caption" color="text.secondary">{w.user_id}</Typography>
                    </TableCell>
                    <TableCell>{w.reason || 'no reason'}</TableCell>
                    <TableCell sx={{ maxWidth: 200 }}><Typography variant="caption" color="text.secondary" noWrap sx={{ display: 'block' }}>{w.reason || '—'}</Typography></TableCell>
                    <TableCell><Typography variant="caption" color="text.secondary">{w.moderator_name || '@AutoMod'}</Typography></TableCell>
                    <TableCell><Typography variant="caption" color="text.disabled" noWrap>{w.created_at ? new Date(w.created_at).toLocaleString() : ''}</Typography></TableCell>
                    <TableCell align="center" onClick={(ev) => ev.stopPropagation()}>
                      <Stack direction="row" spacing={0} justifyContent="center">
                        <ModActionMenu guildId={guildId} userId={w.user_id} username={w.username} reason={w.reason} onActed={reload} />
                        <IconButton size="small" color="error" onClick={() => remove(w.id)} title="Remove warning"><Delete fontSize="small" /></IconButton>
                      </Stack>
                    </TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell colSpan={6} sx={{ py: 0, border: 0 }}>
                      <Collapse in={openId === w.id} unmountOnExit>
                        <Box sx={{ py: 1.5, pl: 1 }}>
                          <Typography variant="caption" fontWeight={700} display="block">Full reason</Typography>
                          <Typography variant="body2" color="text.secondary" sx={{ whiteSpace: 'pre-wrap', mb: 0.5 }}>{w.reason || '—'}</Typography>
                          <Typography variant="caption" color="text.disabled">Issued by {w.moderator_name || '@AutoMod'} · {w.created_at ? new Date(w.created_at).toLocaleString() : ''}</Typography>
                        </Box>
                      </Collapse>
                    </TableCell>
                  </TableRow>
                </React.Fragment>
              ))}
            </TableBody>
          </Table>
        </Box>
      )}
    </CardContent></Card>
  );
}

// ── Digest: reuses the digest settings card ────────────────────────────────────
export function DigestSubtab({ guildId, channels = [] }) {
  const textChannels = channels.filter((c) => TEXT_TYPES.has(c.type));
  return <DigestCard guildId={guildId} channels={textChannels} />;
}
