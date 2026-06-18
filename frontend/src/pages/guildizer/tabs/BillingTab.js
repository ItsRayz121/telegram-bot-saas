import React, { useEffect, useState } from 'react';
import {
  Box, Grid, Typography, Button, Chip, List, ListItem,
  ListItemIcon, ListItemText, CircularProgress, Alert, Stack, TextField,
} from '@mui/material';
import { CheckCircle } from '@mui/icons-material';
import guildizerApi from '../../../services/guildizerApi';
import GuildizerCollapsibleCard from '../../../components/guildizer/GuildizerCollapsibleCard';

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
      <Grid item xs={12}>
        <GuildizerCollapsibleCard id="settings.billing.plan" title="Plan">
          <Typography variant="body2" color="text.secondary" mb={2}>
            Your current subscription tier and renewal date for this server.
          </Typography>
          <Typography mb={1}>Current plan: <Chip label={data.is_pro ? 'Pro' : 'Free'} color={data.is_pro ? 'success' : 'default'} size="small" /></Typography>
          {data.via_account && (
            <Alert severity="success" sx={{ mb: 1, py: 0 }}>
              Pro is active on your account — it covers all your servers. No separate purchase needed for this one.
            </Alert>
          )}
          {data.is_pro && !data.via_account && data.plan_expires_at && (
            <Typography variant="caption" color="text.secondary" display="block" mb={1}>
              Renews / expires {new Date(data.plan_expires_at).toLocaleDateString()}
            </Typography>
          )}
          {msg && <Alert severity="info" sx={{ my: 1 }}>{msg}</Alert>}
          {!data.via_account && (
            <Button variant={data.is_pro ? 'outlined' : 'contained'} onClick={upgrade} disabled={busy}>
              {busy ? 'Starting…' : data.is_pro ? 'Extend Pro' : `Upgrade to Pro — $${pro.price_usd}/mo`}
            </Button>
          )}
          {!data.configured && (
            <Typography variant="caption" color="text.disabled" display="block" mt={1}>
              Payments are not configured on this server instance.
            </Typography>
          )}
        </GuildizerCollapsibleCard>
      </Grid>

      <Grid item xs={12}>
        <GuildizerCollapsibleCard id="settings.billing.pro_includes" title={`${pro.name} includes`}>
          <Typography variant="body2" color="text.secondary" mb={2}>
            Everything you unlock by upgrading this server to Pro.
          </Typography>
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
        </GuildizerCollapsibleCard>
      </Grid>

      <Grid item xs={12}>
        <PromoCard guildId={guildId} />
      </Grid>
      <Grid item xs={12}>
        <HistoryCard guildId={guildId} />
      </Grid>
    </Grid>
  );
}

function PromoCard({ guildId }) {
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);

  async function redeem() {
    setBusy(true); setMsg(null);
    try {
      const { data } = await guildizerApi.post(`/api/guilds/${guildId}/billing/promo`, { code: code.trim() });
      setMsg({ ok: true, text: `${data.days_added} days of Pro added! Active until ${new Date(data.plan_expires_at).toLocaleDateString()}.` });
      setCode('');
    } catch (e) {
      const err = e?.response?.data?.error;
      setMsg({ ok: false, text: err === 'already_redeemed_here' ? 'This server already used that code.' : err === 'invalid_code' ? 'That code is invalid or exhausted.' : 'Something went wrong.' });
    }
    setBusy(false);
  }

  return (
    <GuildizerCollapsibleCard id="settings.billing.promo_code" title="Promo code">
      <Typography variant="body2" color="text.secondary" mb={2}>
        Have a promo code? Redeem it here to add Pro days to this server.
      </Typography>
      {msg && <Alert severity={msg.ok ? 'success' : 'error'} sx={{ mb: 1 }}>{msg.text}</Alert>}
      <Stack direction="row" spacing={1}>
        <TextField size="small" fullWidth label="Code" value={code} onChange={(e) => setCode(e.target.value)} />
        <Button variant="contained" size="small" disabled={busy || !code.trim()} onClick={redeem}>Redeem</Button>
      </Stack>
    </GuildizerCollapsibleCard>
  );
}

function HistoryCard({ guildId }) {
  const [rows, setRows] = useState(null);

  useEffect(() => {
    guildizerApi.get(`/api/guilds/${guildId}/billing/history`)
      .then(({ data }) => setRows(data.history)).catch(() => setRows([]));
  }, [guildId]);

  if (rows === null) return null;
  return (
    <GuildizerCollapsibleCard id="settings.billing.payment_history" title="Payment history">
      <Typography variant="body2" color="text.secondary" mb={2}>
        A record of past and pending checkouts for this server.
      </Typography>
      {rows.length === 0 && <Typography variant="body2" color="text.secondary">No payments yet.</Typography>}
      <List dense>
        {rows.map((r) => (
          <ListItem key={r.id} disableGutters
            secondaryAction={<Chip size="small" variant="outlined"
              color={r.status === 'active' ? 'success' : r.status === 'pending' ? 'warning' : 'default'}
              label={r.status} />}>
            <ListItemText
              primary={`$${r.amount} ${r.currency} — ${r.plan}`}
              secondary={r.created_at ? new Date(r.created_at).toLocaleString() : ''} />
          </ListItem>
        ))}
      </List>
      {rows.some((r) => r.status === 'pending') && (
        <Typography variant="caption" color="text.secondary">
          Pending rows mean a checkout was started but not finished — start a new
          checkout above to complete the upgrade.
        </Typography>
      )}
    </GuildizerCollapsibleCard>
  );
}
