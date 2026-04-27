import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  Box, Container, Typography, Card, CardContent, Grid,
  CircularProgress, Alert, Chip, Button, FormControl,
  InputLabel, Select, MenuItem, Table, TableBody,
  TableCell, TableContainer, TableHead, TableRow, Paper,
} from '@mui/material';
import {
  PersonAdd, Shield, CheckCircle, Cancel, BarChart,
  Lock, TrendingUp, Bolt,
} from '@mui/icons-material';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, BarChart as RBarChart, Bar,
} from 'recharts';
import { toast } from 'react-toastify';
import { analytics as analyticsApi, telegramGroups, auth } from '../services/api';
import TopNav from '../components/TopNav';

const EVENT_LABELS = {
  member_joined:        'Member Joined',
  verification_passed:  'Verification Passed',
  verification_failed:  'Verification Failed',
  automod_action:       'AutoMod Action',
  command_triggered:    'Command Used',
  bot_added:            'Bot Added',
  bot_removed:          'Bot Removed',
  group_linked:         'Group Linked',
  member_joined_restricted: 'Restricted (pending)',
};

function StatCard({ icon, label, value, color = 'primary.main', subtitle }) {
  return (
    <Card>
      <CardContent sx={{ display: 'flex', alignItems: 'center', gap: 2, py: '16px !important' }}>
        <Box sx={{ p: 1.5, borderRadius: 2, bgcolor: `${color}22`, flexShrink: 0 }}>
          {React.cloneElement(icon, { sx: { color, fontSize: 22 } })}
        </Box>
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="h5" fontWeight={700}>{value ?? 0}</Typography>
          <Typography variant="body2" color="text.secondary" noWrap>{label}</Typography>
          {subtitle && (
            <Typography variant="caption" color="text.disabled">{subtitle}</Typography>
          )}
        </Box>
      </CardContent>
    </Card>
  );
}

function LockedCard({ title, description }) {
  const navigate = useNavigate();
  return (
    <Card sx={{ position: 'relative', overflow: 'hidden', minHeight: 200 }}>
      {/* Blurred placeholder content */}
      <CardContent sx={{ filter: 'blur(4px)', userSelect: 'none', pointerEvents: 'none' }}>
        <Typography variant="h6" fontWeight={600} mb={1}>{title}</Typography>
        <Box sx={{ height: 140, bgcolor: 'action.hover', borderRadius: 1 }} />
      </CardContent>
      {/* Overlay */}
      <Box sx={{
        position: 'absolute', inset: 0,
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center', gap: 1.5,
        background: 'rgba(15,23,42,0.75)',
        backdropFilter: 'blur(2px)',
      }}>
        <Lock sx={{ fontSize: 32, color: 'primary.main' }} />
        <Typography variant="subtitle1" fontWeight={700}>{title}</Typography>
        <Typography variant="body2" color="text.secondary" textAlign="center" px={3}>
          {description}
        </Typography>
        <Button
          variant="contained"
          size="small"
          onClick={() => navigate('/billing')}
        >
          Upgrade to Pro
        </Button>
      </Box>
    </Card>
  );
}

const CHART_STYLE = { background: '#161b22', border: '1px solid #30363d' };

export default function OfficialGroupAnalytics() {
  const { groupId } = useParams();
  const navigate = useNavigate();

  const [group, setGroup] = useState(null);
  const [data, setData] = useState(null);
  const [days, setDays] = useState(30);
  const [loading, setLoading] = useState(true);
  const [tier, setTier] = useState('free');

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [groupRes, analyticsRes, meRes] = await Promise.all([
        telegramGroups.get(groupId),
        analyticsApi.getOfficialGroupAnalytics(groupId, { days }),
        auth.getMe(),
      ]);
      setGroup(groupRes.data.group);
      setData(analyticsRes.data.analytics);
      setTier(meRes.data.user?.subscription_tier || 'free');
    } catch (err) {
      toast.error('Failed to load analytics');
      navigate('/my-groups');
    } finally {
      setLoading(false);
    }
  }, [groupId, days, navigate]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const isPro = tier === 'pro' || tier === 'enterprise';

  const summary = data?.summary || {};
  const dailyJoins = data?.daily_joins || [];
  const recentEvents = data?.recent_events || [];
  const eventsByType = data?.events_by_type || {};

  // Build bar chart data from events_by_type
  const eventBarData = Object.entries(eventsByType)
    .map(([type, count]) => ({ type: EVENT_LABELS[type] || type, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 8);

  // Verification funnel
  const totalJoins = summary.member_joins || 0;
  const passed = summary.verifications_passed || 0;
  const failed = summary.verifications_failed || 0;
  const pending = Math.max(0, totalJoins - passed - failed);
  const funnelData = [
    { name: 'Joined', value: totalJoins },
    { name: 'Passed', value: passed },
    { name: 'Failed', value: failed },
    { name: 'Pending', value: pending },
  ].filter((d) => d.value > 0);

  const verificationRate = totalJoins > 0 ? Math.round((passed / totalJoins) * 100) : null;

  // Recent events visible to free = last 5, pro = all
  const visibleEvents = isPro ? recentEvents : recentEvents.slice(0, 5);

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <TopNav
        breadcrumb={[
          { label: 'Dashboard', path: '/dashboard' },
          { label: 'My Groups', path: '/my-groups' },
          { label: group?.title || groupId, path: `/my-groups/${groupId}` },
          { label: 'Analytics' },
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
          {/* Title row */}
          <Box sx={{ mb: 3 }}>
            <Typography variant="h4" fontWeight={700}>
              {group?.title || 'Group'} — Analytics
            </Typography>
            <Typography variant="body2" color="text.secondary" mt={0.5}>
              Last {days} days · {isPro ? tier.charAt(0).toUpperCase() + tier.slice(1) + ' plan' : 'Free plan — upgrade for full analytics'}
            </Typography>
          </Box>

          {/* Stat cards — visible to all */}
          <Grid container spacing={2} mb={3}>
            <Grid item xs={6} md={3}>
              <StatCard
                icon={<PersonAdd />}
                label="Members Joined"
                value={summary.member_joins}
                color="#4caf50"
              />
            </Grid>
            <Grid item xs={6} md={3}>
              <StatCard
                icon={<CheckCircle />}
                label="Verifications Passed"
                value={summary.verifications_passed}
                color="#2196f3"
                subtitle={verificationRate !== null ? `${verificationRate}% pass rate` : undefined}
              />
            </Grid>
            <Grid item xs={6} md={3}>
              <StatCard
                icon={<Shield />}
                label="AutoMod Actions"
                value={summary.automod_actions}
                color="#f44336"
              />
            </Grid>
            <Grid item xs={6} md={3}>
              <StatCard
                icon={<Bolt />}
                label="Commands Used"
                value={summary.commands_used}
                color="#7c4dff"
              />
            </Grid>
          </Grid>

          {/* Daily joins chart — visible to all */}
          <Card sx={{ mb: 3 }}>
            <CardContent>
              <Typography variant="h6" fontWeight={600} mb={2}>
                Daily Member Joins
              </Typography>
              {dailyJoins.length === 0 ? (
                <Alert severity="info">No join events recorded in this period.</Alert>
              ) : (
                <ResponsiveContainer width="100%" height={240}>
                  <LineChart data={dailyJoins}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
                    <XAxis
                      dataKey="date"
                      tick={{ fontSize: 11, fill: '#8b949e' }}
                      tickFormatter={(d) => d.slice(5)}
                    />
                    <YAxis tick={{ fontSize: 11, fill: '#8b949e' }} allowDecimals={false} />
                    <Tooltip contentStyle={CHART_STYLE} />
                    <Line
                      type="monotone"
                      dataKey="joins"
                      stroke="#4caf50"
                      strokeWidth={2}
                      dot={false}
                      name="Joins"
                    />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>

          {/* Pro-gated section */}
          <Grid container spacing={2} mb={3}>
            {/* Events by type — pro only */}
            <Grid item xs={12} md={7}>
              {isPro ? (
                <Card>
                  <CardContent>
                    <Typography variant="h6" fontWeight={600} mb={2}>
                      Events by Type
                    </Typography>
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
                            width={130}
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
                  description="See a full breakdown of all event types — joins, automod, commands, and more."
                />
              )}
            </Grid>

            {/* Verification funnel — pro only */}
            <Grid item xs={12} md={5}>
              {isPro ? (
                <Card sx={{ height: '100%' }}>
                  <CardContent>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
                      <Typography variant="h6" fontWeight={600}>Verification Funnel</Typography>
                      {verificationRate !== null && (
                        <Chip
                          label={`${verificationRate}% pass`}
                          color={verificationRate >= 70 ? 'success' : 'warning'}
                          size="small"
                        />
                      )}
                    </Box>
                    {funnelData.length === 0 ? (
                      <Alert severity="info">No verification events in this period.</Alert>
                    ) : (
                      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
                        {[
                          { label: 'Total Joined', value: totalJoins, color: '#2196f3' },
                          { label: 'Passed',       value: passed,     color: '#4caf50' },
                          { label: 'Failed',       value: failed,     color: '#f44336' },
                          { label: 'Pending',      value: pending,    color: '#ff9800' },
                        ].map(({ label, value, color }) => (
                          <Box key={label}>
                            <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                              <Typography variant="body2" color="text.secondary">{label}</Typography>
                              <Typography variant="body2" fontWeight={700}>{value}</Typography>
                            </Box>
                            <Box sx={{ height: 6, borderRadius: 3, bgcolor: 'action.hover', overflow: 'hidden' }}>
                              <Box sx={{
                                height: '100%',
                                width: totalJoins > 0 ? `${(value / totalJoins) * 100}%` : '0%',
                                bgcolor: color,
                                borderRadius: 3,
                                transition: 'width 0.6s ease',
                              }} />
                            </Box>
                          </Box>
                        ))}
                      </Box>
                    )}
                  </CardContent>
                </Card>
              ) : (
                <LockedCard
                  title="Verification Funnel"
                  description="Track verification pass/fail rates and pending challenges over time."
                />
              )}
            </Grid>
          </Grid>

          {/* AutoMod stats — pro only */}
          {!isPro && (
            <Card sx={{ mb: 3 }}>
              <CardContent sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                <TrendingUp color="primary" />
                <Box sx={{ flex: 1 }}>
                  <Typography variant="subtitle2" fontWeight={600}>
                    Upgrade to Pro for full analytics
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    90-day history, events breakdown, verification funnel, and unlimited recent events.
                  </Typography>
                </Box>
                <Button variant="contained" size="small" onClick={() => navigate('/billing')}>
                  Upgrade
                </Button>
              </CardContent>
            </Card>
          )}

          {/* Recent events table */}
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                <Typography variant="h6" fontWeight={600}>Recent Events</Typography>
                {!isPro && (
                  <Chip label="Showing last 5 · Upgrade for full log" size="small" color="warning" />
                )}
              </Box>
              {visibleEvents.length === 0 ? (
                <Alert severity="info">No events recorded in this period.</Alert>
              ) : (
                <TableContainer component={Paper} variant="outlined">
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Time</TableCell>
                        <TableCell>Event</TableCell>
                        <TableCell>Details</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {visibleEvents.map((ev) => (
                        <TableRow key={ev.id} hover>
                          <TableCell>
                            <Typography variant="caption" sx={{ fontFamily: 'monospace', whiteSpace: 'nowrap' }}>
                              {new Date(ev.created_at).toLocaleString()}
                            </Typography>
                          </TableCell>
                          <TableCell>
                            <Chip
                              label={EVENT_LABELS[ev.event_type] || ev.event_type}
                              size="small"
                              color={
                                ev.event_type === 'verification_passed' ? 'success' :
                                ev.event_type === 'verification_failed' ? 'error' :
                                ev.event_type === 'automod_action' ? 'warning' :
                                'default'
                              }
                              sx={{ fontSize: '0.7rem' }}
                            />
                          </TableCell>
                          <TableCell>
                            <Typography variant="caption" color="text.secondary" noWrap sx={{ maxWidth: 300, display: 'block' }}>
                              {ev.message || '—'}
                            </Typography>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              )}
              {!isPro && recentEvents.length > 5 && (
                <Alert severity="warning" sx={{ mt: 1.5 }} icon={<Lock fontSize="small" />}>
                  {recentEvents.length - 5} more events hidden.{' '}
                  <Button size="small" onClick={() => navigate('/billing')}>Upgrade to Pro</Button> to see all.
                </Alert>
              )}
            </CardContent>
          </Card>
        </Container>
      )}
    </Box>
  );
}
