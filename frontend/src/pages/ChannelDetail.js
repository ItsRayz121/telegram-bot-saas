import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Typography, Card, CardContent, Button, Chip, Grid,
  CircularProgress, Alert, Avatar, IconButton, Tooltip,
  Table, TableBody, TableCell, TableHead, TableRow, TableContainer,
  Paper, Divider, Stack, ToggleButtonGroup, ToggleButton,
} from '@mui/material';
import {
  ArrowBack, Refresh, Visibility, ThumbUp,
  Image, VideoLibrary, Poll, ArticleOutlined,
  TrendingUp, TrendingDown, Remove, Shield, InfoOutlined,
} from '@mui/icons-material';
import LinearProgress from '@mui/material/LinearProgress';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'react-toastify';
import { channels as chApi } from '../services/api';

const FILTER_OPTIONS = [
  { label: '7 days', days: 7 },
  { label: '30 days', days: 30 },
  { label: '1 year', days: 365 },
  { label: 'All captured', days: 0 },
];

function MiniBar({ value, max, color = 'primary.main' }) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
      <Box sx={{ flex: 1, height: 6, bgcolor: 'rgba(255,255,255,0.08)', borderRadius: 3, overflow: 'hidden' }}>
        <Box sx={{ width: `${pct}%`, height: '100%', bgcolor: color, borderRadius: 3, transition: 'width 0.4s' }} />
      </Box>
      <Typography variant="caption" color="text.secondary" sx={{ minWidth: 40, textAlign: 'right' }}>
        {value.toLocaleString()}
      </Typography>
    </Box>
  );
}

function GrowthBadge({ current, previous }) {
  if (!previous) return null;
  const diff = current - previous;
  const pct = Math.round((diff / previous) * 100);
  if (diff > 0) return <Chip icon={<TrendingUp sx={{ fontSize: '0.9rem !important' }} />} label={`+${pct}%`} color="success" size="small" sx={{ height: 20, fontSize: '0.65rem' }} />;
  if (diff < 0) return <Chip icon={<TrendingDown sx={{ fontSize: '0.9rem !important' }} />} label={`${pct}%`} color="error" size="small" sx={{ height: 20, fontSize: '0.65rem' }} />;
  return <Chip icon={<Remove sx={{ fontSize: '0.9rem !important' }} />} label="0%" size="small" sx={{ height: 20, fontSize: '0.65rem' }} />;
}

function MediaIcon({ type }) {
  const icons = { photo: Image, video: VideoLibrary, gif: VideoLibrary, poll: Poll };
  const Icon = icons[type] || ArticleOutlined;
  return <Icon sx={{ fontSize: 16, color: 'text.disabled' }} />;
}

function StatCard({ label, value, sub, color = 'primary.main' }) {
  return (
    <Card>
      <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
        <Typography variant="caption" color="text.secondary" display="block" mb={0.5}>{label}</Typography>
        <Typography variant="h5" fontWeight={800} color={color}>{value}</Typography>
        {sub && <Typography variant="caption" color="text.disabled">{sub}</Typography>}
      </CardContent>
    </Card>
  );
}

function MemberGrowthChart({ stats }) {
  if (!stats?.length) return (
    <Box sx={{ py: 4, textAlign: 'center' }}>
      <Typography variant="body2" color="text.disabled">
        No daily data yet. Hit Refresh to record today's member count.
      </Typography>
    </Box>
  );
  const max = Math.max(...stats.map(s => s.member_count), 1);
  return (
    <Box>
      {stats.slice(-14).map(s => (
        <Box key={s.date} sx={{ mb: 0.75 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 0.25 }}>
            <Typography variant="caption" color="text.disabled" sx={{ minWidth: 72 }}>
              {new Date(s.date).toLocaleDateString('en', { month: 'short', day: 'numeric' })}
            </Typography>
            <MiniBar value={s.member_count} max={max} />
          </Box>
        </Box>
      ))}
    </Box>
  );
}

function ViewsChart({ stats, botStatus }) {
  const filtered = (stats || []).filter(s => s.avg_views_per_post > 0);
  if (!filtered.length) {
    const msg = botStatus !== 'active'
      ? 'Add the bot as admin to start capturing post views.'
      : 'No view data captured in this period yet. New posts will appear here automatically.';
    return (
      <Box sx={{ py: 4, textAlign: 'center' }}>
        <Typography variant="body2" color="text.disabled">{msg}</Typography>
      </Box>
    );
  }
  const max = Math.max(...filtered.map(s => s.avg_views_per_post), 1);
  return (
    <Box>
      {filtered.slice(-14).map(s => (
        <Box key={s.date} sx={{ mb: 0.75 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 0.25 }}>
            <Typography variant="caption" color="text.disabled" sx={{ minWidth: 72 }}>
              {new Date(s.date).toLocaleDateString('en', { month: 'short', day: 'numeric' })}
            </Typography>
            <MiniBar value={Math.round(s.avg_views_per_post)} max={max} color="secondary.main" />
          </Box>
        </Box>
      ))}
    </Box>
  );
}

// ── TCS Panel ─────────────────────────────────────────────────────────────────

const GRADE_COLOR = { A: 'success', B: 'success', C: 'warning', D: 'warning', F: 'error' };
const GRADE_MUI   = { A: 'success.main', B: 'success.main', C: 'warning.main', D: 'warning.main', F: 'error.main' };

function SignalRow({ signal }) {
  const pct = Math.round((signal.score / signal.max) * 100);
  const color = pct >= 70 ? 'success' : pct >= 40 ? 'warning' : 'error';
  return (
    <Box sx={{ mb: 2 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 0.5 }}>
        <Typography variant="body2" fontWeight={600}>{signal.label}</Typography>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          {signal.value != null && (
            <Typography variant="caption" color="text.secondary">
              {signal.value}{signal.unit || ''}
            </Typography>
          )}
          <Typography variant="caption" fontWeight={700} color={`${color}.main`}>
            {signal.score}/{signal.max}
          </Typography>
        </Box>
      </Box>
      <LinearProgress
        variant="determinate"
        value={pct}
        color={color}
        sx={{ height: 6, borderRadius: 3, mb: 0.5 }}
      />
      <Typography variant="caption" color="text.disabled">{signal.note}</Typography>
    </Box>
  );
}

function TcsPanel({ channel, onComputed }) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(
    channel.tcs_score != null
      ? { score: channel.tcs_score, grade: channel.tcs_grade, breakdown: channel.tcs_breakdown, recommendations: [] }
      : null
  );

  const handleCompute = async () => {
    setLoading(true);
    try {
      const res = await chApi.computeTcs(channel.id);
      setResult(res.data);
      onComputed(res.data);
      toast.success('TCS computed');
    } catch (e) {
      toast.error(e.response?.data?.error || 'Could not compute TCS');
    } finally {
      setLoading(false);
    }
  };

  const grade = result?.grade;
  const score = result?.score;

  return (
    <Card sx={{ mb: 3 }}>
      <CardContent sx={{ p: 2.5 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2, flexWrap: 'wrap', gap: 1 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Shield sx={{ color: 'primary.main', fontSize: 20 }} />
            <Typography variant="subtitle2" fontWeight={700}>Telegizer Community Score (TCS)</Typography>
            <Chip label="Authenticity" size="small" sx={{ height: 18, fontSize: '0.6rem' }} />
          </Box>
          <Button
            size="small" variant={result ? 'outlined' : 'contained'}
            onClick={handleCompute} disabled={loading}
            startIcon={loading ? <CircularProgress size={14} /> : <Shield fontSize="small" />}
          >
            {result ? 'Recompute' : 'Compute TCS'}
          </Button>
        </Box>

        {!result ? (
          <Alert severity="info" icon={<InfoOutlined fontSize="small" />} sx={{ fontSize: '0.75rem' }}>
            TCS analyzes view rate, engagement, post consistency, and forward rate to detect
            fake subscribers and bot inflation. Click "Compute TCS" to score this channel.
          </Alert>
        ) : (
          <>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 3, mb: 3, p: 2, bgcolor: 'rgba(255,255,255,0.04)', borderRadius: 2 }}>
              <Box sx={{ textAlign: 'center', minWidth: 80 }}>
                <Typography variant="h2" fontWeight={900} color={GRADE_MUI[grade] || 'text.primary'} lineHeight={1}>
                  {score}
                </Typography>
                <Typography variant="caption" color="text.secondary">/ 100</Typography>
              </Box>
              <Box sx={{ flex: 1 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                  <Chip
                    label={`Grade ${grade}`}
                    color={GRADE_COLOR[grade] || 'default'}
                    sx={{ fontWeight: 800, fontSize: '0.9rem', height: 28 }}
                  />
                  <Typography variant="body2" color="text.secondary">
                    {score >= 80 ? 'Highly Authentic' : score >= 65 ? 'Good' : score >= 50 ? 'Mixed Signals' : score >= 35 ? 'Suspicious' : 'High Bot Risk'}
                  </Typography>
                </Box>
                {channel.tcs_computed_at && (
                  <Typography variant="caption" color="text.disabled">
                    Computed {new Date(channel.tcs_computed_at).toLocaleDateString()}
                  </Typography>
                )}
              </Box>
            </Box>
            {result.breakdown?.map(s => <SignalRow key={s.label} signal={s} />)}
            {result.recommendations?.length > 0 && (
              <Box sx={{ mt: 2, p: 1.5, bgcolor: 'rgba(255,255,255,0.03)', borderRadius: 1.5 }}>
                <Typography variant="caption" fontWeight={700} color="text.secondary" display="block" mb={1}>
                  Recommendations
                </Typography>
                {result.recommendations.map((r, i) => (
                  <Box key={i} sx={{ display: 'flex', gap: 1, mb: 0.75 }}>
                    <InfoOutlined sx={{ fontSize: 14, color: 'primary.main', flexShrink: 0, mt: 0.2 }} />
                    <Typography variant="caption" color="text.secondary">{r}</Typography>
                  </Box>
                ))}
              </Box>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function ChannelDetail() {
  const { cid } = useParams();
  const navigate = useNavigate();
  const [channel, setChannel] = useState(null);
  const [posts, setPosts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [postsPage, setPostsPage] = useState(1);
  const [postsTotal, setPostsTotal] = useState(0);
  const [filterDays, setFilterDays] = useState(30);

  const load = useCallback(() => {
    return chApi.get(cid, { days: filterDays }).then(r => setChannel(r.data));
  }, [cid, filterDays]);

  const loadPosts = useCallback((page = 1) => {
    return chApi.posts(cid, { page, days: filterDays }).then(r => {
      setPosts(r.data.posts);
      setPostsTotal(r.data.total);
      setPostsPage(page);
    });
  }, [cid, filterDays]);

  useEffect(() => {
    setLoading(true);
    Promise.all([load(), loadPosts(1)])
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [load, loadPosts]);

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await chApi.refresh(cid);
      // Reload channel with current period filter to get fresh period metrics
      await load();
      await loadPosts(1);
      toast.success('Stats refreshed');
    } catch {
      toast.error('Refresh failed');
    } finally {
      setRefreshing(false);
    }
  };

  const handleFilterChange = (_, newVal) => {
    if (newVal == null) return;
    setFilterDays(newVal);
  };

  if (loading) return <Box sx={{ py: 8, textAlign: 'center' }}><CircularProgress /></Box>;
  if (!channel) return <Alert severity="error" sx={{ m: 3 }}>Channel not found.</Alert>;

  const dailyStats = channel.daily_stats || [];
  const lastTwo = dailyStats.slice(-2);
  const prevMember = lastTwo[0]?.member_count;
  const curMember = channel.member_count;

  const periodLabel = FILTER_OPTIONS.find(o => o.days === filterDays)?.label || '';
  const isActive = channel.bot_status === 'active';

  return (
    <Box sx={{ p: { xs: 2, md: 4 }, maxWidth: 960, mx: 'auto' }}>

      {/* Header */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 2, flexWrap: 'wrap' }}>
        <IconButton onClick={() => navigate('/channels')} size="small">
          <ArrowBack />
        </IconButton>
        <Avatar sx={{ bgcolor: 'primary.main', width: 40, height: 40 }}>
          {channel.title[0]?.toUpperCase()}
        </Avatar>
        <Box sx={{ flex: 1 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
            <Typography variant="h6" fontWeight={700}>{channel.title}</Typography>
            <Chip
              label={isActive ? 'Live' : 'No admin access'}
              color={isActive ? 'success' : 'warning'}
              size="small" sx={{ height: 20, fontSize: '0.65rem' }}
            />
          </Box>
          {channel.username && (
            <Typography variant="caption" color="text.secondary">@{channel.username}</Typography>
          )}
        </Box>
        <Tooltip title="Refresh member count and recompute averages">
          <span>
            <Button
              variant="outlined" size="small" startIcon={refreshing ? <CircularProgress size={14} /> : <Refresh />}
              onClick={handleRefresh} disabled={refreshing}
            >
              Refresh
            </Button>
          </span>
        </Tooltip>
      </Box>

      {/* Tracking provenance banner */}
      <Alert
        severity="info"
        icon={<InfoOutlined fontSize="small" />}
        sx={{ mb: 2, fontSize: '0.78rem', '& .MuiAlert-message': { width: '100%' } }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 0.5 }}>
          <span>
            Tracking started:{' '}
            <strong>{new Date(channel.tracking_started_at || channel.created_at).toLocaleDateString('en', { year: 'numeric', month: 'short', day: 'numeric' })}</strong>
            {' '}— Telegizer captures posts from this date onward. Historical posts before this date are not available via the Telegram Bot API.
          </span>
        </Box>
      </Alert>

      {channel.bot_status === 'no_admin' && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          The bot is not admin in this channel. Add it as admin with "Post messages" permission to start capturing post analytics automatically.
          Member count will still update on manual Refresh.
        </Alert>
      )}

      {/* Time filter */}
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 3, flexWrap: 'wrap', gap: 1 }}>
        <Typography variant="subtitle2" color="text.secondary">
          Showing: <strong style={{ color: 'inherit' }}>{periodLabel}</strong>
        </Typography>
        <ToggleButtonGroup
          value={filterDays}
          exclusive
          onChange={handleFilterChange}
          size="small"
        >
          {FILTER_OPTIONS.map(opt => (
            <ToggleButton
              key={opt.days}
              value={opt.days}
              sx={{ px: 1.5, py: 0.4, fontSize: '0.73rem', textTransform: 'none' }}
            >
              {opt.label}
            </ToggleButton>
          ))}
        </ToggleButtonGroup>
      </Box>

      {/* Overview stat cards — period-specific */}
      <Grid container spacing={2} mb={3}>
        <Grid item xs={6} sm={3}>
          <StatCard
            label="Members"
            value={(curMember || 0).toLocaleString()}
            sub={<GrowthBadge current={curMember} previous={prevMember} />}
            color="primary.main"
          />
        </Grid>
        <Grid item xs={6} sm={3}>
          <StatCard
            label="Avg Views / Post"
            value={Math.round(channel.period_avg_views || 0).toLocaleString()}
            sub={periodLabel}
            color="secondary.main"
          />
        </Grid>
        <Grid item xs={6} sm={3}>
          <StatCard
            label="Engagement Rate"
            value={`${(channel.period_engagement_rate || 0).toFixed(2)}%`}
            sub="reactions / views"
            color={(channel.period_engagement_rate || 0) > 1 ? 'success.main' : 'text.primary'}
          />
        </Grid>
        <Grid item xs={6} sm={3}>
          <StatCard
            label="Posts Tracked"
            value={channel.period_post_count || 0}
            sub={filterDays === 0 ? 'all captured' : periodLabel}
            color="text.primary"
          />
        </Grid>
      </Grid>

      {/* Charts row */}
      <Grid container spacing={2} mb={3}>
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent sx={{ p: 2 }}>
              <Typography variant="subtitle2" fontWeight={700} mb={2}>
                Member Growth
              </Typography>
              <MemberGrowthChart stats={dailyStats} />
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent sx={{ p: 2 }}>
              <Typography variant="subtitle2" fontWeight={700} mb={2}>
                Avg Views / Post
              </Typography>
              <ViewsChart stats={dailyStats} botStatus={channel.bot_status} />
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* TCS */}
      <TcsPanel
        channel={channel}
        onComputed={(result) => setChannel(prev => ({
          ...prev,
          tcs_score: result.score,
          tcs_grade: result.grade,
          tcs_breakdown: result.breakdown,
          tcs_computed_at: result.computed_at,
        }))}
      />

      {/* Top posts */}
      {channel.top_posts?.length > 0 && (
        <Card sx={{ mb: 3 }}>
          <CardContent sx={{ p: 2 }}>
            <Typography variant="subtitle2" fontWeight={700} mb={2}>
              Top Posts by Views <Typography component="span" variant="caption" color="text.disabled">({periodLabel})</Typography>
            </Typography>
            {channel.top_posts.map((p, i) => (
              <Box key={p.id} sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1.5 }}>
                <Typography variant="caption" color="text.disabled" sx={{ minWidth: 18, fontWeight: 700 }}>
                  #{i + 1}
                </Typography>
                <MediaIcon type={p.media_type} />
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography variant="body2" noWrap color={p.text_preview ? 'text.primary' : 'text.disabled'}>
                    {p.text_preview || `[${p.media_type || 'media'}]`}
                  </Typography>
                  <Typography variant="caption" color="text.disabled">
                    {new Date(p.posted_at).toLocaleDateString()}
                  </Typography>
                </Box>
                <Stack direction="row" spacing={1.5}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                    <Visibility sx={{ fontSize: 13, color: 'text.disabled' }} />
                    <Typography variant="caption">{(p.views || 0).toLocaleString()}</Typography>
                  </Box>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                    <ThumbUp sx={{ fontSize: 13, color: 'text.disabled' }} />
                    <Typography variant="caption">{(p.reactions || 0).toLocaleString()}</Typography>
                  </Box>
                </Stack>
              </Box>
            ))}
          </CardContent>
        </Card>
      )}

      {/* All posts table */}
      <Card>
        <CardContent sx={{ p: 2 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
            <Typography variant="subtitle2" fontWeight={700}>
              All Posts <Typography component="span" variant="caption" color="text.disabled">({periodLabel})</Typography>
            </Typography>
            <Typography variant="caption" color="text.secondary">{postsTotal} total</Typography>
          </Box>

          {posts.length === 0 ? (
            <Box sx={{ py: 4, textAlign: 'center' }}>
              {isActive ? (
                <>
                  <Typography variant="body2" color="text.disabled" mb={0.5}>
                    No posts captured in this period.
                  </Typography>
                  <Typography variant="caption" color="text.disabled">
                    New posts are captured automatically as they are published.
                    {filterDays > 0 && ' Try "All captured" to see older posts.'}
                  </Typography>
                </>
              ) : (
                <Typography variant="body2" color="text.disabled">
                  Add the bot as admin in this channel to start capturing post analytics.
                </Typography>
              )}
            </Box>
          ) : (
            <>
              <TableContainer component={Paper} elevation={0} sx={{ bgcolor: 'transparent', overflowX: 'auto' }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell sx={{ color: 'text.secondary', fontSize: '0.72rem', fontWeight: 600 }}>Post</TableCell>
                      <TableCell align="right" sx={{ color: 'text.secondary', fontSize: '0.72rem', fontWeight: 600 }}>Views</TableCell>
                      <TableCell align="right" sx={{ color: 'text.secondary', fontSize: '0.72rem', fontWeight: 600 }}>Reactions</TableCell>
                      <TableCell align="right" sx={{ color: 'text.secondary', fontSize: '0.72rem', fontWeight: 600 }}>Eng%</TableCell>
                      <TableCell align="right" sx={{ color: 'text.secondary', fontSize: '0.72rem', fontWeight: 600 }}>Date</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {posts.map(p => (
                      <TableRow key={p.id} hover>
                        <TableCell sx={{ maxWidth: 240 }}>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                            <MediaIcon type={p.media_type} />
                            <Typography variant="caption" noWrap color={p.text_preview ? 'text.primary' : 'text.disabled'}>
                              {p.text_preview || `[${p.media_type || 'media'}]`}
                            </Typography>
                          </Box>
                        </TableCell>
                        <TableCell align="right">
                          <Typography variant="caption" fontWeight={600}>{(p.views || 0).toLocaleString()}</Typography>
                        </TableCell>
                        <TableCell align="right">
                          <Typography variant="caption">{(p.reactions || 0).toLocaleString()}</Typography>
                        </TableCell>
                        <TableCell align="right">
                          <Typography variant="caption" color={p.engagement_rate > 1 ? 'success.main' : 'text.secondary'}>
                            {p.engagement_rate?.toFixed(2)}%
                          </Typography>
                        </TableCell>
                        <TableCell align="right">
                          <Typography variant="caption" color="text.disabled">
                            {new Date(p.posted_at).toLocaleDateString()}
                          </Typography>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>

              {postsTotal > 20 && (
                <Box sx={{ display: 'flex', justifyContent: 'center', gap: 1, mt: 2 }}>
                  <Button size="small" disabled={postsPage <= 1} onClick={() => loadPosts(postsPage - 1)}>
                    Prev
                  </Button>
                  <Typography variant="caption" color="text.secondary" sx={{ alignSelf: 'center' }}>
                    Page {postsPage} of {Math.ceil(postsTotal / 20)}
                  </Typography>
                  <Button size="small" disabled={postsPage >= Math.ceil(postsTotal / 20)} onClick={() => loadPosts(postsPage + 1)}>
                    Next
                  </Button>
                </Box>
              )}
            </>
          )}
        </CardContent>
      </Card>

      <Divider sx={{ my: 3 }} />
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 1 }}>
        <Typography variant="caption" color="text.disabled">
          Last refreshed: {channel.last_refreshed_at
            ? new Date(channel.last_refreshed_at).toLocaleString()
            : 'Never — hit Refresh to record today\'s snapshot'}
        </Typography>
        <Button
          size="small" variant="outlined" startIcon={<Shield fontSize="small" />}
          onClick={() => navigate('/directory/submit')}
          sx={{ fontSize: '0.72rem' }}
        >
          List in Directory
        </Button>
      </Box>
    </Box>
  );
}
