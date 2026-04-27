import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box, Container, Typography, Card, CardContent, Grid,
  CircularProgress, Alert, Button, Chip, FormControl,
  InputLabel, Select, MenuItem, Table, TableBody,
  TableCell, TableContainer, TableHead, TableRow, Paper,
} from '@mui/material';
import {
  Groups, PersonAdd, Shield, Bolt, BarChart, Lock,
} from '@mui/icons-material';
import {
  BarChart as RBarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer,
} from 'recharts';
import { toast } from 'react-toastify';
import { analytics as analyticsApi, auth } from '../services/api';
import TopNav from '../components/TopNav';

const EVENT_LABELS = {
  member_joined:       'Joined',
  verification_passed: 'Verified',
  verification_failed: 'Failed Verification',
  automod_action:      'AutoMod',
  command_triggered:   'Commands',
  bot_added:           'Bot Added',
  bot_removed:         'Bot Removed',
};

function StatCard({ icon, label, value, color = 'primary.main' }) {
  return (
    <Card>
      <CardContent sx={{ display: 'flex', alignItems: 'center', gap: 2, py: '16px !important' }}>
        <Box sx={{ p: 1.5, borderRadius: 2, bgcolor: `${color}22`, flexShrink: 0 }}>
          {React.cloneElement(icon, { sx: { color, fontSize: 22 } })}
        </Box>
        <Box>
          <Typography variant="h5" fontWeight={700}>{value ?? 0}</Typography>
          <Typography variant="body2" color="text.secondary">{label}</Typography>
        </Box>
      </CardContent>
    </Card>
  );
}

function LockedCard({ title, description }) {
  const navigate = useNavigate();
  return (
    <Card sx={{ position: 'relative', overflow: 'hidden', minHeight: 160 }}>
      <CardContent sx={{ filter: 'blur(4px)', userSelect: 'none', pointerEvents: 'none' }}>
        <Typography variant="h6" fontWeight={600} mb={1}>{title}</Typography>
        <Box sx={{ height: 100, bgcolor: 'action.hover', borderRadius: 1 }} />
      </CardContent>
      <Box sx={{
        position: 'absolute', inset: 0,
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center', gap: 1.5,
        background: 'rgba(15,23,42,0.75)',
        backdropFilter: 'blur(2px)',
      }}>
        <Lock sx={{ fontSize: 28, color: 'primary.main' }} />
        <Typography variant="subtitle1" fontWeight={700}>{title}</Typography>
        <Typography variant="body2" color="text.secondary" textAlign="center" px={3} fontSize="0.8rem">
          {description}
        </Typography>
        <Button variant="contained" size="small" onClick={() => navigate('/billing')}>
          Upgrade to Pro
        </Button>
      </Box>
    </Card>
  );
}

const CHART_STYLE = { background: '#161b22', border: '1px solid #30363d' };

export default function OfficialAnalyticsOverview() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [days, setDays] = useState(30);
  const [loading, setLoading] = useState(true);
  const [tier, setTier] = useState('free');

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [analyticsRes, meRes] = await Promise.all([
        analyticsApi.getOfficialOverview({ days }),
        auth.getMe(),
      ]);
      setData(analyticsRes.data.analytics);
      setTier(meRes.data.user?.subscription_tier || 'free');
    } catch {
      toast.error('Failed to load analytics');
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const isPro = tier === 'pro' || tier === 'enterprise';
  const summary = data?.summary || {};
  const topGroups = data?.top_groups || [];
  const eventsByType = data?.events_by_type || {};

  const eventBarData = Object.entries(eventsByType)
    .map(([type, count]) => ({ type: EVENT_LABELS[type] || type, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 8);

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <TopNav
        breadcrumb={[
          { label: 'Dashboard', path: '/dashboard' },
          { label: 'My Bots', path: '/my-bots' },
          { label: 'Analytics Overview' },
        ]}
        actions={
          <FormControl size="small" sx={{ minWidth: 110 }}>
            <InputLabel>Range</InputLabel>
            <Select value={days} label="Range" onChange={(e) => setDays(e.target.value)}>
              <MenuItem value={7}>7 days</MenuItem>
              <MenuItem value={14}>14 days</MenuItem>
              <MenuItem value={30}>30 days</MenuItem>
              {isPro && <MenuItem value={90}>90 days</MenuItem>}
            </Select>
          </FormControl>
        }
      />

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', mt: 10 }}>
          <CircularProgress />
        </Box>
      ) : (
        <Container maxWidth="lg" sx={{ py: 4 }}>
          <Box sx={{ mb: 3 }}>
            <Typography variant="h4" fontWeight={700}>Official Bot — Analytics Overview</Typography>
            <Typography variant="body2" color="text.secondary" mt={0.5}>
              Aggregate across all {data?.total_groups ?? 0} linked groups · last {days} days
            </Typography>
          </Box>

          {data?.total_groups === 0 ? (
            <Alert severity="info" action={
              <Button color="inherit" size="small" onClick={() => navigate('/my-groups')}>
                My Groups
              </Button>
            }>
              No linked groups yet. Add the bot to a group and link it first.
            </Alert>
          ) : (
            <>
              {/* Summary stats */}
              <Grid container spacing={2} mb={3}>
                <Grid item xs={6} md={3}>
                  <StatCard icon={<Groups />} label="Linked Groups" value={data?.total_groups} color="#2196f3" />
                </Grid>
                <Grid item xs={6} md={3}>
                  <StatCard icon={<PersonAdd />} label="Members Joined" value={summary.member_joins} color="#4caf50" />
                </Grid>
                <Grid item xs={6} md={3}>
                  <StatCard icon={<Shield />} label="AutoMod Actions" value={summary.automod_actions} color="#f44336" />
                </Grid>
                <Grid item xs={6} md={3}>
                  <StatCard icon={<Bolt />} label="Commands Used" value={summary.commands_used} color="#7c4dff" />
                </Grid>
              </Grid>

              <Grid container spacing={2} mb={3}>
                {/* Events breakdown — pro only */}
                <Grid item xs={12} md={7}>
                  {isPro ? (
                    <Card>
                      <CardContent>
                        <Typography variant="h6" fontWeight={600} mb={2}>Events by Type</Typography>
                        {eventBarData.length === 0 ? (
                          <Alert severity="info">No events in this period.</Alert>
                        ) : (
                          <ResponsiveContainer width="100%" height={220}>
                            <RBarChart data={eventBarData} layout="vertical" margin={{ left: 8 }}>
                              <CartesianGrid strokeDasharray="3 3" stroke="#30363d" horizontal={false} />
                              <XAxis type="number" tick={{ fontSize: 11, fill: '#8b949e' }} allowDecimals={false} />
                              <YAxis
                                type="category"
                                dataKey="type"
                                tick={{ fontSize: 11, fill: '#8b949e' }}
                                width={120}
                              />
                              <Tooltip contentStyle={CHART_STYLE} />
                              <Bar dataKey="count" fill="#2196f3" radius={[0, 4, 4, 0]} name="Count" />
                            </RBarChart>
                          </ResponsiveContainer>
                        )}
                      </CardContent>
                    </Card>
                  ) : (
                    <LockedCard
                      title="Events Breakdown"
                      description="See all event types across all groups. Available on Pro and Enterprise."
                    />
                  )}
                </Grid>

                {/* Top groups by activity */}
                <Grid item xs={12} md={5}>
                  <Card sx={{ height: '100%' }}>
                    <CardContent>
                      <Typography variant="h6" fontWeight={600} mb={2}>
                        Most Active Groups
                        {!isPro && <Chip label="Top 5" size="small" sx={{ ml: 1, fontSize: '0.65rem' }} />}
                      </Typography>
                      {topGroups.length === 0 ? (
                        <Alert severity="info">No activity in this period.</Alert>
                      ) : (
                        <TableContainer component={Paper} variant="outlined">
                          <Table size="small">
                            <TableHead>
                              <TableRow>
                                <TableCell>Group</TableCell>
                                <TableCell align="right">Events</TableCell>
                                <TableCell align="right" sx={{ width: 70 }}></TableCell>
                              </TableRow>
                            </TableHead>
                            <TableBody>
                              {topGroups.map((g) => (
                                <TableRow key={g.group_id} hover>
                                  <TableCell>
                                    <Typography variant="body2" noWrap sx={{ maxWidth: 150 }}>
                                      {g.title || g.group_id}
                                    </Typography>
                                  </TableCell>
                                  <TableCell align="right">
                                    <Typography variant="body2" fontWeight={600}>{g.events}</Typography>
                                  </TableCell>
                                  <TableCell align="right">
                                    <Button
                                      size="small"
                                      variant="text"
                                      sx={{ fontSize: '0.7rem', px: 1, py: 0 }}
                                      onClick={() => navigate(`/my-groups/${g.group_id}/analytics`)}
                                    >
                                      View
                                    </Button>
                                  </TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                        </TableContainer>
                      )}
                    </CardContent>
                  </Card>
                </Grid>
              </Grid>

              {/* Upgrade banner for free users */}
              {!isPro && (
                <Card>
                  <CardContent sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                    <BarChart color="primary" />
                    <Box sx={{ flex: 1 }}>
                      <Typography variant="subtitle2" fontWeight={600}>
                        Get deeper insights with Pro
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        90-day history, events breakdown by type, verification funnels, and full recent event logs.
                      </Typography>
                    </Box>
                    <Button variant="contained" size="small" onClick={() => navigate('/billing')}>
                      Upgrade
                    </Button>
                  </CardContent>
                </Card>
              )}
            </>
          )}
        </Container>
      )}
    </Box>
  );
}
