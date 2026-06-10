import React, { useEffect, useState } from 'react';
import {
  Box, Grid, Card, CardContent, Typography, Button, Chip, List, ListItem,
  ListItemIcon, ListItemText, CircularProgress, Alert,
} from '@mui/material';
import { CheckCircle } from '@mui/icons-material';
import guildizerApi from '../../../services/guildizerApi';

export default function BillingTab({ guildId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);

  useEffect(() => {
    guildizerApi.get(`/api/guilds/${guildId}/billing`)
      .then(({ data }) => setData(data))
      .catch(() => setMsg('Failed to load billing.'))
      .finally(() => setLoading(false));
  }, [guildId]);

  async function upgrade() {
    setBusy(true); setMsg(null);
    try {
      const { data } = await guildizerApi.post(`/api/guilds/${guildId}/billing/checkout`);
      window.location.href = data.invoice_url; // hosted NOWPayments checkout
    } catch (e) {
      setMsg(e?.response?.status === 503 ? "Payments aren't configured on this instance yet." : 'Could not start checkout.');
      setBusy(false);
    }
  }

  if (loading) return <Box sx={{ display: 'grid', placeItems: 'center', py: 4 }}><CircularProgress /></Box>;
  if (!data) return <Alert severity="warning">{msg || 'No billing info.'}</Alert>;

  const pro = data.pricing.pro;

  return (
    <Grid container spacing={2}>
      <Grid item xs={12} md={6}>
        <Card variant="outlined"><CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>Plan</Typography>
          <Typography mb={1}>Current plan: <Chip label={data.is_pro ? 'Pro' : 'Free'} color={data.is_pro ? 'success' : 'default'} size="small" /></Typography>
          {data.is_pro && data.plan_expires_at && (
            <Typography variant="caption" color="text.secondary" display="block" mb={1}>
              Renews / expires {new Date(data.plan_expires_at).toLocaleDateString()}
            </Typography>
          )}
          {msg && <Alert severity="info" sx={{ my: 1 }}>{msg}</Alert>}
          <Button variant={data.is_pro ? 'outlined' : 'contained'} onClick={upgrade} disabled={busy}>
            {busy ? 'Starting…' : data.is_pro ? 'Extend Pro' : `Upgrade to Pro — $${pro.price_usd}/mo`}
          </Button>
          {!data.configured && (
            <Typography variant="caption" color="text.disabled" display="block" mt={1}>
              Payments are not configured on this server instance.
            </Typography>
          )}
        </CardContent></Card>
      </Grid>

      <Grid item xs={12} md={6}>
        <Card variant="outlined"><CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>{pro.name} includes</Typography>
          <List dense>
            {pro.features.map((f) => (
              <ListItem key={f} disableGutters>
                <ListItemIcon sx={{ minWidth: 32 }}><CheckCircle color="success" fontSize="small" /></ListItemIcon>
                <ListItemText primary={f} />
              </ListItem>
            ))}
          </List>
          <Typography variant="caption" color="text.disabled">
            Paid in crypto via NOWPayments. {pro.period_days}-day periods; re-ups stack.
          </Typography>
        </CardContent></Card>
      </Grid>
    </Grid>
  );
}
