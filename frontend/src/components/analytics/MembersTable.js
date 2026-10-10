import React, { useState } from 'react';
import {
  Box, Button, Chip, Collapse, IconButton, Paper, Stack, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow, Tooltip, Typography,
} from '@mui/material';
import { ExpandMore } from '@mui/icons-material';
import { toast } from 'react-toastify';
import { EmptyNote, Loading, MemberLink, ProfileButton, memberProfilePath } from './shared';

const XP_FIELD = { '1d': 'xp_1d', '7d': 'xp_7d', '30d': 'xp_30d' };
const XP_LABEL = { '1d': 'XP (today)', '7d': 'XP (7d)', '30d': 'XP (30d)' };

export function shortWallet(w, head = 8, tail = 6) {
  return w && w.length > head + tail + 2 ? `${w.slice(0, head)}…${w.slice(-tail)}` : w;
}

export function copyWallet(w) {
  try {
    navigator.clipboard.writeText(w);
    toast.success('Wallet address copied');
  } catch {
    toast.error('Could not copy');
  }
}

function StatusChips({ m }) {
  return (
    <Stack direction="row" spacing={0.5} useFlexGap flexWrap="wrap">
      {m.is_verified ? <Chip size="small" color="success" label="Verified" /> : <Chip size="small" variant="outlined" label="Unverified" />}
      {m.is_muted && <Chip size="small" color="warning" label="Muted" />}
      {m.is_admin && <Chip size="small" color="info" variant="outlined" label="Admin" />}
    </Stack>
  );
}

function WarningsCell({ m }) {
  // Active warning RECORDS (same definition as the Warnings tab). The legacy
  // per-member counter can drift when a warning is removed, so it is only a fallback.
  const n = m.active_warnings ?? m.warnings ?? 0;
  if (!n) return <Typography variant="body2" color="text.disabled">0</Typography>;
  return <Chip size="small" color={n > 1 ? 'warning' : 'default'} variant={n > 1 ? 'filled' : 'outlined'} label={n} aria-label={`${n} active warnings`} />;
}

function WalletLine({ m }) {
  if (!m.wallet_address) return <Typography variant="body2" color="text.disabled">No wallet submitted</Typography>;
  return (
    <Tooltip title={`${m.wallet_address} - click to copy`} arrow>
      <Typography
        component="button" type="button" variant="body2" onClick={() => copyWallet(m.wallet_address)}
        sx={{ all: 'unset', cursor: 'pointer', fontFamily: 'monospace', fontSize: '0.78rem', color: 'primary.main',
          '&:focus-visible': { outline: '2px solid', outlineColor: 'primary.main', borderRadius: 0.5 } }}
      >
        {shortWallet(m.wallet_address)}
      </Typography>
    </Tooltip>
  );
}

function Detail({ label, children }) {
  return (
    <Box sx={{ minWidth: 0 }}>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>{label}</Typography>
      <Box sx={{ typography: 'body2', wordBreak: 'break-word' }}>{children}</Box>
    </Box>
  );
}

function ExtraDetails({ m, fmt }) {
  return (
    <Box sx={{ display: 'grid', gap: 1.5, gridTemplateColumns: { xs: '1fr 1fr', md: 'repeat(4, 1fr)' }, py: 1 }}>
      <Detail label="Telegram ID"><code>{m.telegram_user_id}</code></Detail>
      <Detail label="Joined">{fmt(m.joined_at)}</Detail>
      <Detail label="Last message">{m.last_message_at ? fmt(m.last_message_at) : 'No message recorded'}</Detail>
      <Detail label="Messages">{(m.message_count ?? 0).toLocaleString()}</Detail>
      <Detail label="Wallet"><WalletLine m={m} /></Detail>
      <Detail label="Wallet submitted">{m.wallet_submitted_at ? fmt(m.wallet_submitted_at) : '—'}</Detail>
      <Detail label="CRM tags">{(m.crm_tags || []).length ? (m.crm_tags || []).join(', ') : '—'}</Detail>
      <Detail label="Engagement score">{m.engagement_score ?? 'Not computed'}</Detail>
    </Box>
  );
}

export default function MembersTable({ members, loading, period, isOfficial, botId, groupId, isMobile, fmt, emptyText }) {
  const [open, setOpen] = useState(null);
  const xpField = XP_FIELD[period] || 'xp';
  const profile = (m) => memberProfilePath({ isOfficial, botId, groupId, userId: m.telegram_user_id });

  if (loading && !members.length) return <Loading label="Loading members…" />;
  if (!members.length) return <EmptyNote>{emptyText || 'No members match these filters.'}</EmptyNote>;

  if (isMobile) {
    return (
      <Stack spacing={1.25} aria-busy={loading}>
        {members.map((m) => (
          <Paper key={m.id} variant="outlined" sx={{ p: 1.5 }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 1, alignItems: 'flex-start' }}>
              <MemberLink member={{ ...m, name: m.first_name }} profile={profile(m)} secondary={m.username ? `@${m.username}` : `ID ${m.telegram_user_id}`} />
              <Chip size="small" variant="outlined" label={m.role} />
            </Box>
            <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap" sx={{ mt: 1 }}>
              <Chip size="small" color="primary" variant="outlined" label={`${XP_LABEL[period] || 'XP'} ${(m[xpField] ?? 0).toLocaleString()}`} />
              <Chip size="small" variant="outlined" label={`Lv ${m.level}`} />
              {(m.active_warnings ?? m.warnings) > 0 && <Chip size="small" color="warning" label={`${m.active_warnings ?? m.warnings} warnings`} />}
              {m.wallet_address && <Chip size="small" color="success" variant="outlined" label="Wallet" />}
            </Stack>
            <Box sx={{ mt: 1 }}><StatusChips m={m} /></Box>
            <Collapse in={open === m.id} unmountOnExit><ExtraDetails m={m} fmt={fmt} /></Collapse>
            <Box sx={{ display: 'flex', gap: 1, mt: 1 }}>
              <ProfileButton to={profile(m)} />
              <Button size="small" onClick={() => setOpen(open === m.id ? null : m.id)} aria-expanded={open === m.id}>
                {open === m.id ? 'Less' : 'More details'}
              </Button>
            </Box>
          </Paper>
        ))}
      </Stack>
    );
  }

  return (
    <TableContainer component={Paper} variant="outlined" aria-busy={loading}>
      <Table size="medium" sx={{ '& td, & th': { py: 1.1 } }}>
        <TableHead>
          <TableRow>
            <TableCell>Member</TableCell>
            <TableCell align="right">{XP_LABEL[period] || 'XP'}</TableCell>
            <TableCell align="right">Level</TableCell>
            <TableCell align="right">Active warnings</TableCell>
            <TableCell>Role</TableCell>
            <TableCell>Status</TableCell>
            <TableCell>Wallet</TableCell>
            <TableCell align="right" sx={{ width: 150 }}>Actions</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {members.map((m) => (
            <React.Fragment key={m.id}>
              <TableRow hover sx={{ '& td': { borderBottom: open === m.id ? 'none' : undefined } }}>
                <TableCell sx={{ maxWidth: 260 }}>
                  <MemberLink member={{ ...m, name: m.first_name }} profile={profile(m)} secondary={m.username ? `@${m.username}` : `ID ${m.telegram_user_id}`} />
                </TableCell>
                <TableCell align="right">{(m[xpField] ?? 0).toLocaleString()}</TableCell>
                <TableCell align="right">{m.level}</TableCell>
                <TableCell align="right"><WarningsCell m={m} /></TableCell>
                <TableCell><Chip size="small" variant="outlined" label={m.role} /></TableCell>
                <TableCell><StatusChips m={m} /></TableCell>
                <TableCell><WalletLine m={m} /></TableCell>
                <TableCell align="right">
                  <Box sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5 }}>
                    <ProfileButton to={profile(m)} />
                    <Tooltip title={open === m.id ? 'Hide details' : 'More details'}>
                      <IconButton size="small" aria-label={open === m.id ? 'Hide details' : 'Show more details'} aria-expanded={open === m.id}
                        onClick={() => setOpen(open === m.id ? null : m.id)}
                        sx={{ transform: open === m.id ? 'rotate(180deg)' : 'none', transition: 'transform .15s', '@media (prefers-reduced-motion: reduce)': { transition: 'none' } }}>
                        <ExpandMore fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  </Box>
                </TableCell>
              </TableRow>
              {open === m.id && (
                <TableRow>
                  <TableCell colSpan={8} sx={{ bgcolor: 'action.hover' }}><ExtraDetails m={m} fmt={fmt} /></TableCell>
                </TableRow>
              )}
            </React.Fragment>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}
