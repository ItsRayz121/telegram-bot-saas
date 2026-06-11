import React, { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Box, Typography, Button, Card, CardContent, Grid, Avatar,
  CircularProgress, Alert, Chip, Stack, IconButton, Badge, Menu, MenuItem,
  ListItemText, Dialog, DialogTitle, DialogContent, DialogActions, TextField,
} from '@mui/material';
import {
  Forum, Add, OpenInNew, AdminPanelSettings, SmartToy, Notifications, Redeem,
} from '@mui/icons-material';
import guildizerApi, { guildizerLoginUrl } from '../../services/guildizerApi';

const OAUTH_ERRORS = {
  invalid_state: 'Login session expired — please try connecting again.',
  oauth_failed: 'Could not reach Discord. Please try again.',
  access_denied: 'You cancelled the Discord authorization.',
};

export default function GuildizerServers() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [state, setState] = useState({ loading: true, connected: false, guilds: [], inviteUrl: null });
  const [error, setError] = useState(OAUTH_ERRORS[params.get('error')] || null);
  const [isAdmin, setIsAdmin] = useState(false);
  const [redeemOpen, setRedeemOpen] = useState(false);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const { data: me } = await guildizerApi.get('/auth/me'); // 401 → not connected
        const { data } = await guildizerApi.get('/api/guilds');
        if (alive) {
          setState({ loading: false, connected: true, guilds: data.guilds, inviteUrl: data.invite_url });
          setIsAdmin(!!me.is_admin);
        }
      } catch (e) {
        if (!alive) return;
        if (e?.response?.status === 401) setState({ loading: false, connected: false, guilds: [], inviteUrl: null });
        else { setError('Failed to load your Discord servers.'); setState((s) => ({ ...s, loading: false })); }
      }
    })();
    return () => { alive = false; };
  }, []);

  if (state.loading) {
    return <Box sx={{ display: 'grid', placeItems: 'center', minHeight: 320 }}><CircularProgress /></Box>;
  }

  return (
    <Box sx={{ maxWidth: 1000, mx: 'auto', px: { xs: 2, md: 3 }, py: 3 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 0.5 }}>
        <Forum color="primary" />
        <Typography variant="h5" fontWeight={800}>Discord</Typography>
      </Box>
      <Typography variant="body2" color="text.secondary" mb={3}>
        Manage your Discord servers with Guildizer — moderation, leveling, campaigns and more.
      </Typography>

      {error && <Alert severity="warning" sx={{ mb: 2 }} onClose={() => setError(null)}>{error}</Alert>}

      {!state.connected ? (
        <Card variant="outlined" sx={{ maxWidth: 460, mx: 'auto', textAlign: 'center' }}>
          <CardContent sx={{ p: 4 }}>
            <Forum sx={{ fontSize: 44, color: 'primary.main', mb: 1 }} />
            <Typography variant="h6" fontWeight={700} mb={0.5}>Connect your Discord</Typography>
            <Typography variant="body2" color="text.secondary" mb={3}>
              Authorize Discord to see and manage the servers you run. We request <b>identify</b> and <b>guilds</b> only.
            </Typography>
            <Button
              variant="contained" size="large" startIcon={<Forum />}
              onClick={() => { window.location.href = guildizerLoginUrl(); }}
            >
              Continue with Discord
            </Button>
          </CardContent>
        </Card>
      ) : (
        <>
          <Box sx={{ display: 'flex', justifyContent: 'flex-end', gap: 1, mb: 2 }}>
            {isAdmin && (
              <Button variant="outlined" startIcon={<AdminPanelSettings />} onClick={() => navigate('/guildizer/admin')}>
                Admin
              </Button>
            )}
            <Button variant="outlined" startIcon={<SmartToy />} onClick={() => navigate('/guildizer/bots')}>
              My Bots
            </Button>
            <Button variant="outlined" startIcon={<Redeem />} onClick={() => setRedeemOpen(true)}>
              Redeem code
            </Button>
            <NotificationsBell />
            {state.inviteUrl && (
              <Button variant="contained" startIcon={<Add />} href={state.inviteUrl} target="_blank" rel="noreferrer">
                Add to a server
              </Button>
            )}
          </Box>

          {state.guilds.length === 0 ? (
            <Card variant="outlined"><CardContent sx={{ textAlign: 'center', py: 5 }}>
              <Typography color="text.secondary">No manageable servers found.</Typography>
              <Typography variant="caption" color="text.disabled">
                You need the <b>Manage Server</b> permission, or to own the server.
              </Typography>
            </CardContent></Card>
          ) : (
            <Grid container spacing={2}>
              {state.guilds.map((g) => <ServerCard key={g.id} guild={g} navigate={navigate} />)}
            </Grid>
          )}
        </>
      )}
      <RedeemDialog open={redeemOpen} onClose={() => setRedeemOpen(false)} />
    </Box>
  );
}

function NotificationsBell() {
  const [anchor, setAnchor] = useState(null);
  const [items, setItems] = useState([]);
  const [unread, setUnread] = useState(0);

  useEffect(() => {
    guildizerApi.get('/api/notifications')
      .then(({ data }) => { setItems(data.notifications); setUnread(data.unread); })
      .catch(() => {});
  }, []);

  const openMenu = (e) => {
    setAnchor(e.currentTarget);
    if (unread > 0) {
      guildizerApi.post('/api/notifications/read').then(() => setUnread(0)).catch(() => {});
    }
  };

  return (
    <>
      <IconButton onClick={openMenu}>
        <Badge badgeContent={unread} color="error"><Notifications /></Badge>
      </IconButton>
      <Menu anchorEl={anchor} open={!!anchor} onClose={() => setAnchor(null)}>
        {items.length === 0 && <MenuItem disabled>No notifications</MenuItem>}
        {items.map((n) => (
          <MenuItem key={n.id} sx={{ whiteSpace: 'normal', maxWidth: 360 }} onClick={() => setAnchor(null)}>
            <ListItemText primary={n.title} secondary={n.body}
              primaryTypographyProps={{ fontWeight: n.read ? 400 : 700, variant: 'body2' }} />
          </MenuItem>
        ))}
      </Menu>
    </>
  );
}

function RedeemDialog({ open, onClose }) {
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);

  async function redeem() {
    setBusy(true); setMsg(null);
    try {
      const { data } = await guildizerApi.post('/api/team/redeem', { code: code.trim() });
      setMsg({ ok: true, text: `You now have dashboard access to ${data.guild.name}. Reload to see it.` });
      setCode('');
    } catch (e) {
      setMsg({ ok: false, text: e?.response?.status === 404 ? 'That code is invalid, used, or expired.' : 'Something went wrong.' });
    }
    setBusy(false);
  }

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="xs">
      <DialogTitle>Redeem a team invite</DialogTitle>
      <DialogContent>
        {msg && <Alert severity={msg.ok ? 'success' : 'error'} sx={{ mb: 1.5 }}>{msg.text}</Alert>}
        <TextField autoFocus fullWidth size="small" label="Invite code" value={code}
          onChange={(e) => setCode(e.target.value)} />
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
        <Button variant="contained" disabled={busy || !code.trim()} onClick={redeem}>Redeem</Button>
      </DialogActions>
    </Dialog>
  );
}

function ServerCard({ guild, navigate }) {
  const initials = (guild.name || '?').slice(0, 2).toUpperCase();
  return (
    <Grid item xs={12} sm={6} md={4}>
      <Card variant="outlined" sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
        <CardContent sx={{ flex: 1 }}>
          <Stack direction="row" spacing={1.5} alignItems="center" mb={1.5}>
            <Avatar src={guild.icon_url || undefined} variant="rounded" sx={{ width: 44, height: 44, fontWeight: 700 }}>
              {initials}
            </Avatar>
            <Box sx={{ minWidth: 0 }}>
              <Typography fontWeight={700} noWrap>{guild.name}</Typography>
              <Typography variant="caption" color="text.secondary">
                {guild.bot_present ? `${guild.member_count} members` : 'Bot not added'}
                {guild.is_owner && ' · Owner'}
              </Typography>
            </Box>
          </Stack>
          {guild.bot_present
            ? <Chip size="small" color="success" label="Active" variant="outlined" />
            : <Chip size="small" label="Not installed" variant="outlined" />}
        </CardContent>
        <Box sx={{ p: 1.5, pt: 0 }}>
          {guild.bot_present ? (
            <Button fullWidth variant="outlined" onClick={() => navigate(`/guildizer/servers/${guild.id}`)}>
              Manage
            </Button>
          ) : (
            <Button fullWidth variant="contained" endIcon={<OpenInNew />} href={guild.invite_url} target="_blank" rel="noreferrer">
              Add Guildizer
            </Button>
          )}
        </Box>
      </Card>
    </Grid>
  );
}
