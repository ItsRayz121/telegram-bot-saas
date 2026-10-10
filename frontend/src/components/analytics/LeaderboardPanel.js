import React from 'react';
import {
  Box, Button, Chip, InputAdornment, Paper, Stack, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow, TextField, Typography,
} from '@mui/material';
import { EmojiEvents, FileDownload, Search } from '@mui/icons-material';
import {
  EmptyNote, Loading, MemberLink, Panel, PeriodChips, ProfileButton, memberProfilePath,
} from './shared';
import { copyWallet, shortWallet } from './MembersTable';

const PERIODS = [
  { key: 'all', label: 'All time' },
  { key: '30d', label: '30 days' },
  { key: '7d', label: '7 days' },
  { key: '1d', label: 'Today' },
];
const XP_FIELD = { '1d': 'xp_1d', '7d': 'xp_7d', '30d': 'xp_30d' };
const SCOPE_TEXT = {
  all: 'Lifetime XP',
  '30d': 'XP earned in the last 30 days',
  '7d': 'XP earned in the last 7 days',
  '1d': 'XP earned in the last 24 hours',
};
const MEDAL = ['#f5c542', '#b8c2cc', '#cd7f32'];

export default function LeaderboardPanel({
  members, loading, period, onPeriod, walletOnly, onWalletOnly, search, onSearch,
  totalRanked, limit, onExport, isOfficial, botId, groupId, isMobile,
}) {
  const xpField = XP_FIELD[period] || 'xp';
  const xpOf = (m) => m[xpField] ?? 0;
  const profile = (m) => memberProfilePath({ isOfficial, botId, groupId, userId: m.telegram_user_id });
  const filtered = !!search.trim() || walletOnly;
  const top = members.slice(0, 3);
  const showWeek = period === 'all';

  return (
    <>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 1, mb: 1.5 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <EmojiEvents color="primary" />
          <Box>
            <Typography variant="h6" fontWeight={700} component="h2">XP leaderboard</Typography>
            <Typography variant="caption" color="text.secondary">{SCOPE_TEXT[period]}</Typography>
          </Box>
        </Box>
        <Button size="small" variant="outlined" startIcon={<FileDownload fontSize="small" />} onClick={onExport} disabled={!members.length}>
          Export CSV
        </Button>
      </Box>

      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1.5, alignItems: 'center', mb: 1.5 }}>
        <PeriodChips value={period} options={PERIODS} onChange={onPeriod} ariaLabel="Leaderboard period" />
        <Chip size="small" clickable label="Has wallet" aria-pressed={walletOnly}
          variant={walletOnly ? 'filled' : 'outlined'} color={walletOnly ? 'success' : 'default'} onClick={() => onWalletOnly(!walletOnly)} />
      </Box>
      <TextField
        size="small" fullWidth sx={{ mb: 2 }} value={search} onChange={(e) => onSearch(e.target.value)}
        placeholder="Search name, @username, Telegram ID, wallet…" inputProps={{ 'aria-label': 'Search leaderboard' }}
        InputProps={{ startAdornment: (<InputAdornment position="start"><Search fontSize="small" /></InputAdornment>) }}
      />

      {loading && !members.length ? <Loading label="Loading leaderboard…" /> : members.length === 0 ? (
        <EmptyNote>
          {period === 'all'
            ? 'No members with XP yet. Members earn XP by sending messages and using commands.'
            : `Nobody earned XP in ${SCOPE_TEXT[period].replace('XP earned in ', '')}.`}
        </EmptyNote>
      ) : (
        <>
          {/* Top three */}
          <Box
            component="ol" aria-label={filtered ? 'Top matches' : 'Top contributors'}
            sx={{ listStyle: 'none', p: 0, m: 0, mb: 2, display: 'grid', gap: 1.5, gridTemplateColumns: { xs: '1fr', sm: 'repeat(3, 1fr)' } }}
          >
            {top.map((m, i) => {
              const next = members[i + 1];
              const gap = next ? xpOf(m) - xpOf(next) : null;
              return (
                <Paper component="li" key={m.id} variant="outlined" sx={{ p: 1.75, borderColor: i === 0 ? MEDAL[0] : 'divider', position: 'relative' }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                    <Chip size="small" label={`#${i + 1}`} sx={{ fontWeight: 800, bgcolor: MEDAL[i], color: '#0b1626' }} />
                    {gap !== null && (
                      <Typography variant="caption" color="text.secondary">
                        {gap === 0 ? 'Tied with next' : `${gap.toLocaleString()} XP ahead of #${i + 2}`}
                      </Typography>
                    )}
                  </Box>
                  <MemberLink member={{ ...m, name: m.first_name }} profile={profile(m)} size={36} strong
                    secondary={m.username ? `@${m.username}` : `Level ${m.level}`} />
                  <Typography variant="h5" fontWeight={800} color="primary.main" sx={{ mt: 1 }}>
                    {xpOf(m).toLocaleString()} <Typography component="span" variant="caption" color="text.secondary">XP</Typography>
                  </Typography>
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                    {SCOPE_TEXT[period]}
                  </Typography>
                  {showWeek && m.xp_week_ledger !== undefined && (
                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                      Last 7 days (separate period): <strong>{m.xp_week_ledger.toLocaleString()} XP</strong>
                    </Typography>
                  )}
                  <Box sx={{ mt: 1.25 }}><ProfileButton to={profile(m)} /></Box>
                </Paper>
              );
            })}
          </Box>
          {filtered && (
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
              Ranks below are positions within the filtered results, not within the whole group.
            </Typography>
          )}

          {/* Full ranking */}
          <Panel
            title="Full ranking"
            subtitle={`Showing ${members.length.toLocaleString()}${totalRanked > members.length ? ` of ${totalRanked.toLocaleString()}` : ''} ranked member${(totalRanked || members.length) === 1 ? '' : 's'} · ties are listed in a fixed order`}
            sx={{ mb: 0 }}
          >
            {isMobile ? (
              <Stack spacing={1}>
                {members.map((m, i) => (
                  <Paper key={m.id} variant="outlined" sx={{ p: 1.25 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <Typography variant="body2" fontWeight={700} sx={{ width: 30, color: i < 3 ? MEDAL[i] : 'text.secondary' }}>#{i + 1}</Typography>
                      <Box sx={{ flex: 1, minWidth: 0 }}>
                        <MemberLink member={{ ...m, name: m.first_name }} profile={profile(m)} secondary={`Level ${m.level} · ${m.role}`} />
                      </Box>
                      <Typography variant="body2" fontWeight={700} color="primary.main">{xpOf(m).toLocaleString()}</Typography>
                    </Box>
                    <Box sx={{ mt: 0.75 }}><ProfileButton to={profile(m)} /></Box>
                  </Paper>
                ))}
              </Stack>
            ) : (
              <TableContainer component={Paper} variant="outlined">
                <Table size="medium" sx={{ '& td, & th': { py: 1 } }}>
                  <TableHead>
                    <TableRow>
                      <TableCell align="center" sx={{ width: 64 }}>Rank</TableCell>
                      <TableCell>Member</TableCell>
                      <TableCell align="right">{period === 'all' ? 'Lifetime XP' : SCOPE_TEXT[period].replace('XP earned in the ', 'XP · ')}</TableCell>
                      {showWeek && <TableCell align="right">Last 7 days</TableCell>}
                      <TableCell align="right">Level</TableCell>
                      <TableCell>Role</TableCell>
                      <TableCell>Wallet</TableCell>
                      <TableCell align="right" sx={{ width: 130 }}>Profile</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {members.map((m, i) => {
                      const tied = (members[i - 1] && xpOf(members[i - 1]) === xpOf(m)) || (members[i + 1] && xpOf(members[i + 1]) === xpOf(m));
                      return (
                        <TableRow key={m.id} hover>
                          <TableCell align="center">
                            <Typography variant="body2" fontWeight={i < 3 ? 800 : 500} sx={{ color: i < 3 ? MEDAL[i] : 'text.primary' }}>{i + 1}</Typography>
                          </TableCell>
                          <TableCell sx={{ maxWidth: 280 }}>
                            <MemberLink member={{ ...m, name: m.first_name }} profile={profile(m)} secondary={m.username ? `@${m.username}` : undefined} />
                          </TableCell>
                          <TableCell align="right">
                            <Typography variant="body2" fontWeight={700} color="primary.main">{xpOf(m).toLocaleString()}</Typography>
                            {tied && <Typography variant="caption" color="text.secondary">tied</Typography>}
                          </TableCell>
                          {showWeek && <TableCell align="right">{(m.xp_week_ledger ?? 0).toLocaleString()}</TableCell>}
                          <TableCell align="right">{m.level}</TableCell>
                          <TableCell><Chip size="small" variant="outlined" label={m.role} /></TableCell>
                          <TableCell>
                            {m.wallet_address ? (
                              <Typography component="button" type="button" onClick={() => copyWallet(m.wallet_address)} title={`${m.wallet_address} - click to copy`}
                                sx={{ all: 'unset', cursor: 'pointer', fontFamily: 'monospace', fontSize: '0.78rem', color: 'primary.main' }}>
                                {shortWallet(m.wallet_address)}
                              </Typography>
                            ) : <Typography variant="body2" color="text.disabled">—</Typography>}
                          </TableCell>
                          <TableCell align="right"><ProfileButton to={profile(m)} /></TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </Panel>
        </>
      )}
    </>
  );
}
