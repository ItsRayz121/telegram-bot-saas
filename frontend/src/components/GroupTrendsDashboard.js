import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Card, CardContent, Typography, ToggleButton, ToggleButtonGroup,
  Select, MenuItem, FormControl, InputLabel, Chip, CircularProgress, Alert,
} from '@mui/material';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
  AreaChart, Area,
} from 'recharts';
import { assistant } from '../services/api';

const HEALTH_COLOR = { healthy: '#4caf50', watch: '#ff9800', critical: '#f44336' };
const SENTIMENT_COLOR = { positive: '#4caf50', neutral: '#90a4ae', negative: '#f44336' };

function EmptyState({ message = 'No data yet — signals are computed every 2 hours.' }) {
  return (
    <Box sx={{ py: 6, textAlign: 'center', color: 'text.disabled' }}>
      <Typography variant="body2">{message}</Typography>
    </Box>
  );
}

export default function GroupTrendsDashboard() {
  const [days, setDays] = useState(7);
  const [selectedGroup, setSelectedGroup] = useState('');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await assistant.groupTrends(days, selectedGroup || null);
      setData(res.data);
    } catch (e) {
      setError('Failed to load group trends.');
    } finally {
      setLoading(false);
    }
  }, [days, selectedGroup]);

  useEffect(() => { load(); }, [load]);

  const groups = data?.groups || [];
  const trends = data?.trends || [];

  // Merge all groups into a single flat timeline for multi-line chart
  const dateMap = {};
  trends.forEach(group => {
    group.days.forEach(d => {
      if (!dateMap[d.date]) dateMap[d.date] = { date: d.date };
      const key = group.title.slice(0, 12);
      dateMap[d.date][`${key}_spam`] = d.spam_score;
      dateMap[d.date][`${key}_conflict`] = d.conflict_score;
      dateMap[d.date][`${key}_messages`] = d.message_count;
      dateMap[d.date][`${key}_members`] = d.active_members;
    });
  });
  const chartData = Object.values(dateMap).sort((a, b) => a.date.localeCompare(b.date));

  // Single group selected — detailed view
  const activeTrend = selectedGroup ? trends.find(t => t.group_id === selectedGroup) : trends[0];
  const singleData = activeTrend?.days || [];

  return (
    <Box>
      {/* Controls */}
      <Box sx={{ display: 'flex', gap: 2, alignItems: 'center', mb: 3, flexWrap: 'wrap' }}>
        <ToggleButtonGroup
          value={days}
          exclusive
          onChange={(_, v) => v && setDays(v)}
          size="small"
        >
          <ToggleButton value={7}>7d</ToggleButton>
          <ToggleButton value={14}>14d</ToggleButton>
          <ToggleButton value={30}>30d</ToggleButton>
        </ToggleButtonGroup>

        {groups.length > 1 && (
          <FormControl size="small" sx={{ minWidth: 200 }}>
            <InputLabel>Group</InputLabel>
            <Select
              value={selectedGroup}
              label="Group"
              onChange={e => setSelectedGroup(e.target.value)}
            >
              <MenuItem value="">All groups</MenuItem>
              {groups.map(g => (
                <MenuItem key={g.id} value={g.id}>{g.title}</MenuItem>
              ))}
            </Select>
          </FormControl>
        )}
      </Box>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
          <CircularProgress size={32} />
        </Box>
      ) : singleData.length === 0 ? (
        <EmptyState />
      ) : (
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
          {/* Health status timeline */}
          <Card>
            <CardContent>
              <Typography variant="subtitle1" fontWeight={600} gutterBottom>
                Daily Health Status
              </Typography>
              <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mb: 1 }}>
                {singleData.map(d => (
                  <Chip
                    key={d.date}
                    label={`${d.date.slice(5)} ${d.health_status}`}
                    size="small"
                    sx={{
                      bgcolor: (HEALTH_COLOR[d.health_status] || '#90a4ae') + '22',
                      color: HEALTH_COLOR[d.health_status] || 'text.secondary',
                      fontWeight: 600,
                      fontSize: 11,
                    }}
                  />
                ))}
              </Box>
            </CardContent>
          </Card>

          {/* Spam & Conflict trend */}
          <Card>
            <CardContent>
              <Typography variant="subtitle1" fontWeight={600} gutterBottom>
                Spam & Conflict Score (0–10)
              </Typography>
              <ResponsiveContainer width="100%" height={200}>
                <AreaChart data={singleData} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} tickFormatter={v => v.slice(5)} />
                  <YAxis domain={[0, 10]} tick={{ fontSize: 11 }} />
                  <Tooltip formatter={(v, n) => [v.toFixed(1), n]} />
                  <Legend />
                  <Area type="monotone" dataKey="spam_score" name="Spam" stroke="#ff9800" fill="#ff980022" strokeWidth={2} />
                  <Area type="monotone" dataKey="conflict_score" name="Conflict" stroke="#f44336" fill="#f4433622" strokeWidth={2} />
                </AreaChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* Activity trend */}
          <Card>
            <CardContent>
              <Typography variant="subtitle1" fontWeight={600} gutterBottom>
                Daily Activity
              </Typography>
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={singleData} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} tickFormatter={v => v.slice(5)} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Legend />
                  <Line type="monotone" dataKey="message_count" name="Messages" stroke="#2196f3" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="active_members" name="Active Members" stroke="#7c4dff" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="questions_unanswered" name="Unanswered ?s" stroke="#ff9800" strokeWidth={1} strokeDasharray="4 2" dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* AI summaries */}
          {singleData.some(d => d.ai_summary) && (
            <Card>
              <CardContent>
                <Typography variant="subtitle1" fontWeight={600} gutterBottom>
                  AI Daily Summaries
                </Typography>
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                  {singleData.filter(d => d.ai_summary).map(d => (
                    <Box key={d.date} sx={{ display: 'flex', gap: 1.5, alignItems: 'flex-start' }}>
                      <Typography variant="caption" color="text.disabled" sx={{ minWidth: 50, pt: 0.2 }}>
                        {d.date.slice(5)}
                      </Typography>
                      <Typography variant="body2">{d.ai_summary}</Typography>
                    </Box>
                  ))}
                </Box>
              </CardContent>
            </Card>
          )}
        </Box>
      )}
    </Box>
  );
}
