import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Typography, Card, CardContent, Button, Chip, Grid,
  TextField, InputAdornment, Select, MenuItem, FormControl,
  InputLabel, CircularProgress, Alert, Avatar, Stack, Divider,
  Drawer, IconButton, Tooltip, LinearProgress,
  Table, TableBody, TableCell, TableHead, TableRow, TableContainer, Paper,
} from '@mui/material';
import {
  ArrowBack, Search, People, Refresh,
  Close, Edit, Save, Warning, VerifiedUser, Message,
  EmojiEvents, Label,
} from '@mui/icons-material';
import { useParams, useNavigate } from 'react-router-dom';
import { toast } from 'react-toastify';
import { crm as crmApi } from '../services/api';
import api from '../services/api';

const TAG_COLORS = {
  VIP: 'warning',
  Lead: 'info',
  Partner: 'secondary',
  Ambassador: 'primary',
  'At Risk': 'error',
  Inactive: 'default',
  Spammer: 'error',
  New: 'success',
};

const ALL_TAGS = ["VIP", "Lead", "Partner", "Ambassador", "At Risk", "Inactive", "Spammer", "New"];

function ScoreBar({ score }) {
  if (score == null) return <Typography variant="caption" color="text.disabled">—</Typography>;
  const color = score >= 70 ? 'success' : score >= 40 ? 'warning' : 'error';
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, minWidth: { xs: 70, sm: 100 } }}>
      <LinearProgress
        variant="determinate" value={score} color={color}
        sx={{ flex: 1, height: 6, borderRadius: 3 }}
      />
      <Typography variant="caption" fontWeight={700} color={`${color}.main`} sx={{ minWidth: 28 }}>
        {score}
      </Typography>
    </Box>
  );
}

function MemberAvatar({ member }) {
  const initials = (member.first_name?.[0] || member.username?.[0] || '?').toUpperCase();
  const color = member.engagement_score >= 70 ? '#16a34a'
    : member.engagement_score >= 40 ? '#d97706' : '#6b7280';
  return (
    <Avatar sx={{ width: 32, height: 32, fontSize: '0.8rem', bgcolor: color }}>
      {initials}
    </Avatar>
  );
}

// ── Member detail drawer ──────────────────────────────────────────────────────

function MemberDrawer({ member, groupId, open, onClose, onUpdated }) {
  const [tags, setTags] = useState(member?.crm_tags || []);
  const [notes, setNotes] = useState(member?.crm_notes || '');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (member) {
      setTags(member.crm_tags || []);
      setNotes(member.crm_notes || '');
    }
  }, [member]);

  if (!member) return null;

  const toggleTag = (tag) => {
    setTags(prev => prev.includes(tag) ? prev.filter(t => t !== tag) : [...prev, tag]);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await crmApi.updateMember(groupId, member.telegram_user_id, { crm_tags: tags, crm_notes: notes });
      onUpdated(res.data);
      toast.success('Saved');
    } catch {
      toast.error('Save failed');
    } finally {
      setSaving(false);
    }
  };

  const displayName = member.first_name || member.username || `User ${member.telegram_user_id}`;

  return (
    <Drawer anchor="right" open={open} onClose={onClose}
      PaperProps={{ sx: { width: { xs: '100%', sm: 420 }, p: 3, bgcolor: 'background.default' } }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 3 }}>
        <Typography variant="h6" fontWeight={700}>Member Profile</Typography>
        <IconButton onClick={onClose}><Close /></IconButton>
      </Box>

      {/* Identity */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 3 }}>
        <Avatar sx={{ width: 52, height: 52, fontSize: '1.3rem', bgcolor: 'primary.main' }}>
          {displayName[0]?.toUpperCase()}
        </Avatar>
        <Box>
          <Typography fontWeight={700} fontSize="1rem">{displayName}</Typography>
          {member.username && <Typography variant="caption" color="text.secondary">@{member.username}</Typography>}
        </Box>
      </Box>

      {/* Engagement score */}
      <Card sx={{ mb: 2.5 }}>
        <CardContent sx={{ p: 2 }}>
          <Typography variant="caption" color="text.secondary" fontWeight={600} display="block" mb={1}>
            Engagement Score
          </Typography>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <Typography variant="h3" fontWeight={900}
              color={member.engagement_score >= 70 ? 'success.main' : member.engagement_score >= 40 ? 'warning.main' : 'error.main'}>
              {member.engagement_score ?? '—'}
            </Typography>
            <Box sx={{ flex: 1 }}>
              <LinearProgress
                variant="determinate"
                value={member.engagement_score || 0}
                color={member.engagement_score >= 70 ? 'success' : member.engagement_score >= 40 ? 'warning' : 'error'}
                sx={{ height: 8, borderRadius: 4 }}
              />
            </Box>
          </Box>
        </CardContent>
      </Card>

      {/* Stats grid */}
      <Grid container spacing={1.5} mb={2.5}>
        {[
          { icon: <Message sx={{ fontSize: 14 }} />, label: 'Messages', value: (member.message_count || 0).toLocaleString() },
          { icon: <EmojiEvents sx={{ fontSize: 14 }} />, label: 'XP / Level', value: `${member.xp || 0} / L${member.level || 1}` },
          { icon: <Warning sx={{ fontSize: 14 }} />, label: 'Warnings', value: member.warnings || 0 },
          { icon: <VerifiedUser sx={{ fontSize: 14 }} />, label: 'Verified', value: member.is_verified ? 'Yes' : 'No' },
        ].map(s => (
          <Grid item xs={6} key={s.label}>
            <Box sx={{ bgcolor: 'rgba(255,255,255,0.04)', borderRadius: 1.5, p: 1.5 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, color: 'text.secondary', mb: 0.5 }}>
                {s.icon}
                <Typography variant="caption" color="text.secondary">{s.label}</Typography>
              </Box>
              <Typography variant="body2" fontWeight={700}>{s.value}</Typography>
            </Box>
          </Grid>
        ))}
      </Grid>

      <Typography variant="caption" color="text.disabled" display="block" mb={2}>
        Joined {member.joined_at ? new Date(member.joined_at).toLocaleDateString() : 'unknown'}
        {member.last_message_at && ` · Last active ${new Date(member.last_message_at).toLocaleDateString()}`}
      </Typography>

      <Divider sx={{ mb: 2 }} />

      {/* Tags */}
      <Typography variant="subtitle2" fontWeight={700} mb={1.5}>
        <Label sx={{ fontSize: 14, mr: 0.5, verticalAlign: 'middle' }} />
        Tags
      </Typography>
      <Stack direction="row" flexWrap="wrap" gap={1} mb={2.5}>
        {ALL_TAGS.map(tag => (
          <Chip
            key={tag}
            label={tag}
            size="small"
            color={tags.includes(tag) ? TAG_COLORS[tag] || 'primary' : 'default'}
            variant={tags.includes(tag) ? 'filled' : 'outlined'}
            onClick={() => toggleTag(tag)}
            sx={{ cursor: 'pointer', fontSize: '0.72rem' }}
          />
        ))}
      </Stack>

      {/* Notes */}
      <Typography variant="subtitle2" fontWeight={700} mb={1}>
        <Edit sx={{ fontSize: 14, mr: 0.5, verticalAlign: 'middle' }} />
        Notes
      </Typography>
      <TextField
        fullWidth multiline rows={4}
        placeholder="Internal notes visible only to you…"
        value={notes}
        onChange={e => setNotes(e.target.value)}
        sx={{ mb: 2.5 }}
      />

      <Button
        fullWidth variant="contained" startIcon={saving ? <CircularProgress size={16} /> : <Save />}
        onClick={handleSave} disabled={saving}
      >
        Save Changes
      </Button>
    </Drawer>
  );
}

// ── Overview cards ────────────────────────────────────────────────────────────

function OverviewCards({ overview, computing, onCompute }) {
  if (!overview) return null;
  const tiers = overview.tier_breakdown || {};
  return (
    <Grid container spacing={2} mb={3}>
      {[
        { label: 'Total Members', value: overview.total, color: 'primary.main' },
        { label: 'Avg Score', value: overview.avg_score, color: overview.avg_score >= 50 ? 'success.main' : 'warning.main' },
        { label: 'New This Week', value: overview.new_this_week, color: 'info.main' },
        { label: 'Champions (80+)', value: tiers['Champions (80+)'] || 0, color: 'success.main' },
      ].map(s => (
        <Grid item xs={6} sm={3} key={s.label}>
          <Card>
            <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 }, textAlign: 'center' }}>
              <Typography variant="h5" fontWeight={800} color={s.color}>{s.value}</Typography>
              <Typography variant="caption" color="text.secondary">{s.label}</Typography>
            </CardContent>
          </Card>
        </Grid>
      ))}

      {/* Tag breakdown */}
      {Object.keys(overview.tag_breakdown || {}).length > 0 && (
        <Grid item xs={12}>
          <Card>
            <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 } }}>
              <Typography variant="caption" color="text.secondary" fontWeight={600} display="block" mb={1}>Tagged members</Typography>
              <Stack direction="row" flexWrap="wrap" gap={1}>
                {Object.entries(overview.tag_breakdown).map(([tag, count]) => (
                  <Chip key={tag} label={`${tag} · ${count}`} size="small"
                    color={TAG_COLORS[tag] || 'default'} sx={{ fontSize: '0.68rem' }} />
                ))}
              </Stack>
            </CardContent>
          </Card>
        </Grid>
      )}

      {overview.scores_computed < overview.total && (
        <Grid item xs={12}>
          <Alert severity="info" action={
            <Button size="small" onClick={onCompute} disabled={computing}>
              {computing ? <CircularProgress size={16} /> : 'Compute Now'}
            </Button>
          } sx={{ fontSize: '0.75rem' }}>
            {overview.total - overview.scores_computed} members haven't been scored yet.
            Compute engagement scores to unlock sorting and tier breakdown.
          </Alert>
        </Grid>
      )}
    </Grid>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function GroupCRM() {
  const { groupId } = useParams();
  const navigate = useNavigate();

  const [group, setGroup] = useState(null);
  const [overview, setOverview] = useState(null);
  const [members, setMembers] = useState([]);
  const [total, setTotal] = useState(0);
  const [pages, setPages] = useState(1);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [computing, setComputing] = useState(false);

  const [search, setSearch] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [tagFilter, setTagFilter] = useState('');
  const [sort, setSort] = useState('score');

  const [selectedMember, setSelectedMember] = useState(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  // Debounce search
  useEffect(() => {
    const t = setTimeout(() => setSearch(searchInput), 350);
    return () => clearTimeout(t);
  }, [searchInput]);

  useEffect(() => {
    api.get(`/api/groups/${groupId}`).then(r => setGroup(r.data)).catch(() => {});
    crmApi.overview(groupId).then(r => setOverview(r.data)).catch(() => {});
  }, [groupId]);

  const fetchMembers = useCallback((p = 1) => {
    setLoading(true);
    const params = { page: p, sort };
    if (search) params.q = search;
    if (tagFilter) params.tag = tagFilter;

    crmApi.members(groupId, params)
      .then(r => {
        setMembers(r.data.members);
        setTotal(r.data.total);
        setPages(r.data.pages);
        setPage(p);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [groupId, search, tagFilter, sort]);

  useEffect(() => { fetchMembers(1); }, [fetchMembers]);

  const handleCompute = async () => {
    setComputing(true);
    try {
      const res = await crmApi.computeScores(groupId);
      toast.success(`Scored ${res.data.updated} members`);
      // Refresh
      crmApi.overview(groupId).then(r => setOverview(r.data)).catch(() => {});
      fetchMembers(page);
    } catch {
      toast.error('Compute failed');
    } finally {
      setComputing(false);
    }
  };

  const handleMemberClick = (member) => {
    setSelectedMember(member);
    setDrawerOpen(true);
  };

  const handleMemberUpdated = (updated) => {
    setMembers(prev => prev.map(m => m.telegram_user_id === updated.telegram_user_id ? updated : m));
    setSelectedMember(updated);
  };

  return (
    <Box sx={{ p: { xs: 2, md: 4 }, maxWidth: 1100, mx: 'auto' }}>
      {/* Header */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 3, flexWrap: 'wrap' }}>
        <IconButton size="small" onClick={() => navigate(`/groups/${groupId}`)}>
          <ArrowBack />
        </IconButton>
        <Box sx={{ flex: 1 }}>
          <Typography variant="h5" fontWeight={700}>Community CRM</Typography>
          <Typography variant="caption" color="text.secondary">
            {group?.name || groupId} — member engagement, tags & notes
          </Typography>
        </Box>
        <Tooltip title="Recompute all engagement scores">
          <span>
            <Button
              variant="outlined" size="small"
              startIcon={computing ? <CircularProgress size={14} /> : <Refresh />}
              onClick={handleCompute} disabled={computing}
            >
              Compute Scores
            </Button>
          </span>
        </Tooltip>
      </Box>

      {/* Overview */}
      <OverviewCards overview={overview} computing={computing} onCompute={handleCompute} />

      {/* Filters */}
      <Card sx={{ mb: 2 }}>
        <CardContent sx={{ p: 2 }}>
          <Grid container spacing={2} alignItems="center">
            <Grid item xs={12} sm={5}>
              <TextField fullWidth size="small"
                placeholder="Search by name or username…"
                value={searchInput}
                onChange={e => setSearchInput(e.target.value)}
                InputProps={{ startAdornment: <InputAdornment position="start"><Search fontSize="small" /></InputAdornment> }}
              />
            </Grid>
            <Grid item xs={6} sm={3}>
              <FormControl fullWidth size="small">
                <InputLabel>Tag filter</InputLabel>
                <Select value={tagFilter} label="Tag filter" onChange={e => setTagFilter(e.target.value)}>
                  <MenuItem value="">All members</MenuItem>
                  {ALL_TAGS.map(t => <MenuItem key={t} value={t}>{t}</MenuItem>)}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={6} sm={4}>
              <FormControl fullWidth size="small">
                <InputLabel>Sort by</InputLabel>
                <Select value={sort} label="Sort by" onChange={e => setSort(e.target.value)}>
                  <MenuItem value="score">Engagement Score</MenuItem>
                  <MenuItem value="messages">Most Messages</MenuItem>
                  <MenuItem value="xp">Highest XP</MenuItem>
                  <MenuItem value="joined">Newest Members</MenuItem>
                  <MenuItem value="warnings">Most Warnings</MenuItem>
                </Select>
              </FormControl>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {/* Member table */}
      <Card>
        <CardContent sx={{ p: 0 }}>
          <Box sx={{ p: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Typography variant="subtitle2" fontWeight={700}>
              <People sx={{ fontSize: 16, mr: 0.5, verticalAlign: 'middle' }} />
              Members
            </Typography>
            <Typography variant="caption" color="text.secondary">{total} total</Typography>
          </Box>

          {loading ? (
            <Box sx={{ py: 6, textAlign: 'center' }}><CircularProgress /></Box>
          ) : members.length === 0 ? (
            <Box sx={{ py: 6, textAlign: 'center' }}>
              <Typography variant="body2" color="text.disabled">
                No members found. Make sure the bot is active in this group.
              </Typography>
            </Box>
          ) : (
            <TableContainer component={Paper} elevation={0} sx={{ bgcolor: 'transparent', overflowX: 'auto' }}>
              <Table size="small" sx={{ minWidth: 560 }}>
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ fontWeight: 600, fontSize: '0.72rem', color: 'text.secondary' }}>Member</TableCell>
                    <TableCell sx={{ fontWeight: 600, fontSize: '0.72rem', color: 'text.secondary' }}>Score</TableCell>
                    <TableCell align="right" sx={{ fontWeight: 600, fontSize: '0.72rem', color: 'text.secondary' }}>Msgs</TableCell>
                    <TableCell align="right" sx={{ fontWeight: 600, fontSize: '0.72rem', color: 'text.secondary' }}>XP</TableCell>
                    <TableCell align="right" sx={{ fontWeight: 600, fontSize: '0.72rem', color: 'text.secondary' }}>Warns</TableCell>
                    <TableCell sx={{ fontWeight: 600, fontSize: '0.72rem', color: 'text.secondary' }}>Tags</TableCell>
                    <TableCell sx={{ fontWeight: 600, fontSize: '0.72rem', color: 'text.secondary' }}>Joined</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {members.map(m => {
                    const name = m.first_name || m.username || `User ${m.telegram_user_id}`;
                    return (
                      <TableRow key={m.telegram_user_id} hover
                        sx={{ cursor: 'pointer' }}
                        onClick={() => handleMemberClick(m)}>
                        <TableCell>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                            <MemberAvatar member={m} />
                            <Box>
                              <Typography variant="body2" fontWeight={600} noWrap sx={{ maxWidth: 140 }}>{name}</Typography>
                              {m.username && (
                                <Typography variant="caption" color="text.disabled">@{m.username}</Typography>
                              )}
                            </Box>
                            {m.is_admin && <Chip label="Admin" size="small" color="warning" sx={{ height: 16, fontSize: '0.58rem' }} />}
                            {m.is_verified && <VerifiedUser sx={{ fontSize: 13, color: 'primary.main' }} />}
                          </Box>
                        </TableCell>
                        <TableCell sx={{ minWidth: 130 }}>
                          <ScoreBar score={m.engagement_score} />
                        </TableCell>
                        <TableCell align="right">
                          <Typography variant="caption">{(m.message_count || 0).toLocaleString()}</Typography>
                        </TableCell>
                        <TableCell align="right">
                          <Typography variant="caption">{m.xp || 0}</Typography>
                        </TableCell>
                        <TableCell align="right">
                          {m.warnings > 0 && (
                            <Chip label={m.warnings} size="small" color="error" sx={{ height: 16, fontSize: '0.65rem', fontWeight: 700 }} />
                          )}
                        </TableCell>
                        <TableCell>
                          <Stack direction="row" spacing={0.5} flexWrap="wrap">
                            {(m.crm_tags || []).map(t => (
                              <Chip key={t} label={t} size="small"
                                color={TAG_COLORS[t] || 'default'}
                                sx={{ height: 16, fontSize: '0.58rem' }} />
                            ))}
                          </Stack>
                        </TableCell>
                        <TableCell>
                          <Typography variant="caption" color="text.disabled">
                            {m.joined_at ? new Date(m.joined_at).toLocaleDateString() : '—'}
                          </Typography>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </TableContainer>
          )}

          {pages > 1 && (
            <Box sx={{ display: 'flex', justifyContent: 'center', gap: 1, p: 2 }}>
              <Button size="small" disabled={page <= 1} onClick={() => fetchMembers(page - 1)}>Prev</Button>
              <Typography variant="caption" color="text.secondary" sx={{ alignSelf: 'center' }}>
                Page {page} of {pages}
              </Typography>
              <Button size="small" disabled={page >= pages} onClick={() => fetchMembers(page + 1)}>Next</Button>
            </Box>
          )}
        </CardContent>
      </Card>

      {/* Member drawer */}
      <MemberDrawer
        member={selectedMember}
        groupId={groupId}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        onUpdated={handleMemberUpdated}
      />
    </Box>
  );
}
