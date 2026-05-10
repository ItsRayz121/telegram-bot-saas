import React, { useState, useEffect } from 'react';
import { SUPPORT_EMAIL, SUPPORT_LINKS as SUPPORT_HREFS } from '../config/support';
import {
  Box, Container, Typography, Card, CardContent, Chip,
  CircularProgress, Divider, Link,
} from '@mui/material';
import {
  CheckCircle, Warning, Error as ErrorIcon, Refresh,
} from '@mui/icons-material';
import { createTheme, ThemeProvider } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';

const darkTheme = createTheme({
  palette: {
    mode: 'dark',
    background: { default: '#0f172a', paper: '#1e293b' },
    primary: { main: '#2563EB' },
  },
  typography: { fontFamily: "'Inter', -apple-system, sans-serif" },
  components: {
    MuiCard: { styleOverrides: { root: { borderRadius: 12, border: '1px solid #334155' } } },
  },
});

const API_BASE = process.env.REACT_APP_API_URL || '';

const SERVICES = [
  { key: 'api', label: 'API', description: 'Core REST API' },
  { key: 'bot', label: 'Telegram Bot', description: 'Official @telegizer_bot' },
  { key: 'db', label: 'Database', description: 'PostgreSQL' },
  { key: 'email', label: 'Email', description: 'Transactional email delivery' },
];

function StatusBadge({ status }) {
  if (status === 'loading') return <CircularProgress size={18} />;
  if (status === 'operational')
    return <Chip icon={<CheckCircle sx={{ fontSize: 16 }} />} label="Operational" size="small" sx={{ bgcolor: '#16a34a22', color: '#4ade80', borderColor: '#16a34a55', border: '1px solid' }} />;
  if (status === 'degraded')
    return <Chip icon={<Warning sx={{ fontSize: 16 }} />} label="Degraded" size="small" sx={{ bgcolor: '#ca8a0422', color: '#facc15', borderColor: '#ca8a0455', border: '1px solid' }} />;
  return <Chip icon={<ErrorIcon sx={{ fontSize: 16 }} />} label="Outage" size="small" sx={{ bgcolor: '#dc262622', color: '#f87171', borderColor: '#dc262655', border: '1px solid' }} />;
}

function overallStatus(statuses) {
  const vals = Object.values(statuses);
  if (vals.includes('outage')) return 'outage';
  if (vals.includes('degraded')) return 'degraded';
  if (vals.every(v => v === 'operational')) return 'operational';
  return 'loading';
}

export default function Status() {
  const [statuses, setStatuses] = useState(
    Object.fromEntries(SERVICES.map(s => [s.key, 'loading']))
  );
  const [lastChecked, setLastChecked] = useState(null);

  async function checkStatus() {
    setStatuses(Object.fromEntries(SERVICES.map(s => [s.key, 'loading'])));
    try {
      const res = await fetch(`${API_BASE}/api/health`, { signal: AbortSignal.timeout(8000) });
      const data = await res.json();
      setStatuses({
        api: res.ok ? 'operational' : 'outage',
        bot: data.bot_status === 'ok' ? 'operational' : data.bot_status === 'degraded' ? 'degraded' : 'outage',
        db: data.db_status === 'ok' ? 'operational' : 'outage',
        email: data.email_status === 'ok' ? 'operational' : 'degraded',
      });
    } catch {
      setStatuses(Object.fromEntries(SERVICES.map(s => [s.key, 'outage'])));
    }
    setLastChecked(new Date());
  }

  useEffect(() => { checkStatus(); }, []);

  const overall = overallStatus(statuses);

  return (
    <ThemeProvider theme={darkTheme}>
      <CssBaseline />
      <Box sx={{ minHeight: '100vh', bgcolor: 'background.default', py: 6 }}>
        <Container maxWidth="sm">
          <Box sx={{ textAlign: 'center', mb: 4 }}>
            <Typography variant="h4" fontWeight={700} gutterBottom>
              Telegizer Status
            </Typography>
            {overall === 'operational' && (
              <Typography color="success.main" fontWeight={600}>
                ✓ All systems operational
              </Typography>
            )}
            {overall === 'degraded' && (
              <Typography color="warning.main" fontWeight={600}>
                ⚠ Some systems degraded
              </Typography>
            )}
            {overall === 'outage' && (
              <Typography color="error.main" fontWeight={600}>
                ✗ Service disruption detected
              </Typography>
            )}
            {lastChecked && (
              <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
                Last checked: {lastChecked.toLocaleTimeString()}{' '}
                <Link onClick={checkStatus} sx={{ cursor: 'pointer', color: 'primary.main' }}>
                  <Refresh sx={{ fontSize: 13, verticalAlign: 'middle' }} /> Refresh
                </Link>
              </Typography>
            )}
          </Box>

          <Card>
            <CardContent sx={{ p: 0 }}>
              {SERVICES.map((svc, i) => (
                <Box key={svc.key}>
                  {i > 0 && <Divider />}
                  <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', px: 3, py: 2 }}>
                    <Box>
                      <Typography fontWeight={600} fontSize="0.9rem">{svc.label}</Typography>
                      <Typography variant="caption" color="text.secondary">{svc.description}</Typography>
                    </Box>
                    <StatusBadge status={statuses[svc.key]} />
                  </Box>
                </Box>
              ))}
            </CardContent>
          </Card>

          <Box sx={{ mt: 4, textAlign: 'center' }}>
            <Typography variant="body2" color="text.secondary">
              Having issues?{' '}
              <Link href="https://t.me/telegizer_community" target="_blank" rel="noopener" color="primary.main">
                Join the community group
              </Link>
              {', '}
              <Link href="https://t.me/telegizer" target="_blank" rel="noopener" color="primary.main">
                follow the official channel
              </Link>
              {', or email '}
              <Link href={SUPPORT_HREFS.email} color="primary.main">
                {SUPPORT_EMAIL}
              </Link>
            </Typography>
          </Box>
        </Container>
      </Box>
    </ThemeProvider>
  );
}
