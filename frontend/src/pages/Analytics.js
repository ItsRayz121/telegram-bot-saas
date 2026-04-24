import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, AppBar, Toolbar, Typography, IconButton, Card, CardContent,
  Grid, CircularProgress, Select, MenuItem, FormControl, InputLabel,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Paper,
  Avatar,
} from '@mui/material';
import { ArrowBack, Group, PersonAdd, Shield, TrendingUp } from '@mui/icons-material';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend, BarChart, Bar,
} from 'recharts';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'react-toastify';
import { analytics, bots } from '../services/api';

const PIE_COLORS = ['#2196f3', '#7c4dff', '#00bcd4', '#4caf50', '#ff9800', '#f44336'];

function StatCard({ icon, label, value, color = 'primary.main' }) {
  return (
    <Card>
      <CardContent sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
        <Box sx={{ p: 1.5, borderRadius: 2, bgcolor: `${color}22` }}>
          {React.cloneElement(icon, { sx: { color } })}
        </Box>
        <Box>
          <Typography variant="h5" fontWeight={700}>{value}</Typography>
          <Typography variant="body2" color="text.secondary">{label}</Typography>
        </Box>
      </CardContent>
    </Card>
  );
}

export default function Analytics() {
  const navigate = useNavigate();
  const { id: botId } = useParams();
  const [bot, setBot] = useState(null);
  const [data, setData] = useState(null);
  const [days, setDays] = useState(30);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [botRes, analyticsRes] = await Promise.all([
        bots.get(botId),
        analytics.getBotAnalytics(botId, { days }),
      ]);
      setBot(botRes.data.bot);
      setData(analyticsRes.data.analytics);
    } catch {
      toast.error('Failed to load analytics');
      navigate('/dashboard');
    } finally {
      setLoading(false);
    }
  }, [botId, days, navigate]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <AppBar position="sticky" elevation={0} sx={{ borderBottom: '1px solid', borderColor: 'divider' }}>
        <Toolbar>
          <IconButton edge="start" onClick={() => navigate('/dashboard')} sx={{ mr: 1 }}>
            <ArrowBack />
          </IconButton>
          <Typography variant="h6" fontWeight={600} sx={{ flexGrow: 1 }}>
            Analytics — {bot?.bot_name}
          </Typography>
          <FormControl size="small" sx={{ minWidth: 120 }}>
            <InputLabel>Range</InputLabel>
            <Select value={days} label="Range" onChange={(e) => setDays(e.target.value)}>
              <MenuItem value={7}>7 days</MenuItem>
              <MenuItem value={30}>30 days</MenuItem>
              <MenuItem value={90}>90 days</MenuItem>
            </Select>
          </FormControl>
        </Toolbar>
      </AppBar>

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', mt: 8 }}>
          <CircularProgress />
        </Box>
      ) : (
        <Box sx={{ maxWidth: 1200, mx: 'auto', p: 3 }}>
          <Grid container spacing={2} mb={3}>
            <Grid item xs={6} md={3}>
              <StatCard icon={<Group />} label="Total Groups" value={data?.total_groups || 0} />
            </Grid>
            <Grid item xs={6} md={3}>
              <StatCard icon={<PersonAdd />} label="Total Members" value={data?.summary?.total_members || 0} color="#4caf50" />
            </Grid>
            <Grid item xs={6} md={3}>
              <StatCard icon={<TrendingUp />} label={`New (${days}d)`} value={data?.summary?.new_members || 0} color="#7c4dff" />
            </Grid>
            <Grid item xs={6} md={3}>
              <StatCard icon={<Shield />} label="Mod Actions" value={data?.summary?.total_mod_actions || 0} color="#f44336" />
            </Grid>
          </Grid>

          <Grid container spacing={2} mb={2}>
            <Grid item xs={12} md={8}>
              <Card>
                <CardContent>
                  <Typography variant="h6" fontWeight={600} mb={2}>Member Growth</Typography>
                  <ResponsiveContainer width="100%" height={260}>
                    <LineChart data={data?.member_growth || []}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
                      <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#8b949e' }} tickFormatter={(d) => d.slice(5)} />
                      <YAxis tick={{ fontSize: 11, fill: '#8b949e' }} />
                      <Tooltip contentStyle={{ background: '#161b22', border: '1px solid #30363d' }} />
                      <Line type="monotone" dataKey="new_members" stroke="#2196f3" strokeWidth={2} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} md={4}>
              <Card sx={{ height: '100%' }}>
                <CardContent>
                  <Typography variant="h6" fontWeight={600} mb={2}>Level Distribution</Typography>
                  <ResponsiveContainer width="100%" height={260}>
                    <PieChart>
                      <Pie
                        data={data?.level_distribution || []}
                        dataKey="count"
                        nameKey="level"
                        cx="50%"
                        cy="50%"
                        outerRadius={90}
                        label={({ level }) => `Lvl ${level}`}
                        labelLine={false}
                      >
                        {(data?.level_distribution || []).map((_, i) => (
                          <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip contentStyle={{ background: '#161b22', border: '1px solid #30363d' }} />
                    </PieChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            </Grid>
          </Grid>

          <Grid container spacing={2}>
            <Grid item xs={12} md={7}>
              <Card>
                <CardContent>
                  <Typography variant="h6" fontWeight={600} mb={2}>Moderation Actions</Typography>
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={data?.mod_actions || []}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
                      <XAxis dataKey="action" tick={{ fontSize: 11, fill: '#8b949e' }} />
                      <YAxis tick={{ fontSize: 11, fill: '#8b949e' }} />
                      <Tooltip contentStyle={{ background: '#161b22', border: '1px solid #30363d' }} />
                      <Bar dataKey="count" fill="#7c4dff" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} md={5}>
              <Card sx={{ height: '100%' }}>
                <CardContent>
                  <Typography variant="h6" fontWeight={600} mb={2}>Top Members</Typography>
                  <TableContainer>
                    <Table size="small">
                      <TableHead>
                        <TableRow>
                          <TableCell>#</TableCell>
                          <TableCell>User</TableCell>
                          <TableCell align="right">XP</TableCell>
                          <TableCell align="right">Lvl</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {(data?.top_members || []).map((m, i) => (
                          <TableRow key={i} hover>
                            <TableCell>
                              <Typography variant="body2" color="text.secondary">{i + 1}</Typography>
                            </TableCell>
                            <TableCell>
                              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                <Avatar sx={{ width: 24, height: 24, fontSize: 11, bgcolor: PIE_COLORS[i % PIE_COLORS.length] }}>
                                  {(m.username || '?')[0].toUpperCase()}
                                </Avatar>
                                <Typography variant="body2" noWrap>{m.username}</Typography>
                              </Box>
                            </TableCell>
                            <TableCell align="right">
                              <Typography variant="body2">{(m.xp ?? 0).toLocaleString()}</Typography>
                            </TableCell>
                            <TableCell align="right">
                              <Typography variant="body2">{m.level}</Typography>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </TableContainer>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </Box>
      )}
    </Box>
  );
}
