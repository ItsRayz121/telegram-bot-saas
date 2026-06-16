import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box, Container, Typography, Card, CardContent, Button, Switch, FormControlLabel,
  Divider, List, ListItem, ListItemText, Chip, Skeleton, Alert, Stack,
} from '@mui/material';
import {
  NotificationsActive, VolumeUp, DoneAll, MarkEmailRead, ArrowBack,
} from '@mui/icons-material';
import { guildizerNotifications } from '../../services/guildizerApi';
import { enablePush, disablePush, pushSupported, notificationPermission } from '../../utils/push';

const SOUND_KEY = 'telegizer_notif_sound';

const CATEGORY_LABELS = {
  moderation: 'Moderation & protection',
  campaigns: 'Engagement campaigns',
  ai: 'AI activity',
  members: 'Members & invites',
  billing: 'Billing & subscription',
  system: 'System & announcements',
};

const PER_PAGE = 20;

export default function GuildizerNotifications() {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);

  const [prefs, setPrefs] = useState(null);
  const [pushSupportedFlag, setPushSupportedFlag] = useState(false);
  const [pushBusy, setPushBusy] = useState(false);
  const [savingPrefs, setSavingPrefs] = useState(false);

  const loadPage = useCallback(async (p) => {
    const res = await guildizerNotifications.list({ page: p, per_page: PER_PAGE });
    return res.data;
  }, []);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const data = await loadPage(1);
        if (!alive) return;
        setItems(data.notifications || []);
        setTotal(data.total || 0);
      } catch { /* ignore */ } finally {
        if (alive) setLoading(false);
      }
      try {
        const pr = await guildizerNotifications.getPreferences();
        if (!alive) return;
        const serverPrefs = pr.data.preferences || {};
        try {
          if (typeof serverPrefs.sound === 'boolean') {
            localStorage.setItem(SOUND_KEY, serverPrefs.sound ? 'on' : 'off');
          }
        } catch { /* ignore */ }
        setPrefs({ ...serverPrefs, push: serverPrefs.push && pr.data.push_subscribed });
        setPushSupportedFlag(pushSupported() && pr.data.push_supported);
      } catch { /* ignore */ }
    })();
    return () => { alive = false; };
  }, [loadPage]);

  const savePrefs = async (patch) => {
    setSavingPrefs(true);
    try {
      const next = { sound: prefs?.sound, categories: prefs?.categories, ...patch };
      const res = await guildizerNotifications.updatePreferences(next);
      setPrefs(p => ({ ...(p || {}), ...res.data.preferences }));
    } catch { /* ignore */ } finally {
      setSavingPrefs(false);
    }
  };

  const handleSoundToggle = (e) => {
    const on = e.target.checked;
    try { localStorage.setItem(SOUND_KEY, on ? 'on' : 'off'); } catch { /* ignore */ }
    setPrefs(p => ({ ...(p || {}), sound: on }));
    savePrefs({ sound: on });
  };

  const handleCategoryToggle = (cat) => (e) => {
    const on = e.target.checked;
    const categories = { ...(prefs?.categories || {}), [cat]: on };
    setPrefs(p => ({ ...(p || {}), categories }));
    savePrefs({ categories });
  };

  const handlePushToggle = async (e) => {
    const on = e.target.checked;
    setPushBusy(true);
    try {
      if (on) {
        await enablePush(guildizerNotifications);
        setPrefs(p => ({ ...(p || {}), push: true }));
      } else {
        await disablePush(guildizerNotifications);
        setPrefs(p => ({ ...(p || {}), push: false }));
      }
    } catch (err) {
      setPrefs(p => ({ ...(p || {}), push: !on }));
    } finally {
      setPushBusy(false);
    }
  };

  const markAllRead = async () => {
    try {
      await guildizerNotifications.markAllRead();
      setItems(prev => prev.map(n => ({ ...n, read: true })));
    } catch { /* ignore */ }
  };

  const loadMore = async () => {
    setLoadingMore(true);
    try {
      const data = await loadPage(page + 1);
      setItems(prev => [...prev, ...(data.notifications || [])]);
      setPage(p => p + 1);
    } catch { /* ignore */ } finally {
      setLoadingMore(false);
    }
  };

  const permission = notificationPermission();
  const hasMore = items.length < total;
  const unreadCount = items.filter(n => !n.read).length;

  return (
    <Container maxWidth="md" sx={{ py: { xs: 2, sm: 3 } }}>
      <Button startIcon={<ArrowBack />} size="small" onClick={() => navigate('/guildizer')} sx={{ mb: 2 }}>
        Back to Guildizer
      </Button>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 0.5 }}>
        <NotificationsActive color="primary" />
        <Typography variant="h5" fontWeight={800}>Notifications</Typography>
      </Box>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Your Guildizer alerts, plus how and where you receive them.
      </Typography>

      <Card sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 2, mb: 3 }}>
        <CardContent sx={{ p: { xs: 2, sm: 3 } }}>
          <Typography variant="subtitle1" fontWeight={700} sx={{ mb: 1.5 }}>Delivery</Typography>
          <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 2 }}>
            <Box>
              <Typography variant="body2" fontWeight={600}>Push notifications</Typography>
              <Typography variant="caption" color="text.secondary">
                Get alerts on this device even when the dashboard is closed.
              </Typography>
            </Box>
            <Switch
              checked={Boolean(prefs?.push)}
              onChange={handlePushToggle}
              disabled={!pushSupportedFlag || pushBusy || permission === 'denied'}
            />
          </Box>
          {!pushSupportedFlag && (
            <Alert severity="info" sx={{ mt: 1, py: 0 }}>
              Push isn't available on this browser/device yet. The in-app bell still works.
            </Alert>
          )}
          {permission === 'denied' && (
            <Alert severity="warning" sx={{ mt: 1, py: 0 }}>
              You blocked notifications for this site. Re-enable them in your browser settings.
            </Alert>
          )}
          <Divider sx={{ my: 2 }} />
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 2 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <VolumeUp fontSize="small" color="action" />
              <Box>
                <Typography variant="body2" fontWeight={600}>In-app sound</Typography>
                <Typography variant="caption" color="text.secondary">
                  Play a chime when a new notification arrives while the app is open.
                </Typography>
              </Box>
            </Box>
            <Switch checked={prefs ? prefs.sound !== false : true} onChange={handleSoundToggle} />
          </Box>
        </CardContent>
      </Card>

      <Card sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 2, mb: 3 }}>
        <CardContent sx={{ p: { xs: 2, sm: 3 } }}>
          <Typography variant="subtitle1" fontWeight={700} sx={{ mb: 0.5 }}>
            What to notify me about
          </Typography>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1.5 }}>
            Muting a category stops push for it. It still appears in your history below.
          </Typography>
          <Stack>
            {Object.keys(CATEGORY_LABELS).map(cat => (
              <FormControlLabel
                key={cat}
                control={
                  <Switch
                    size="small"
                    checked={prefs?.categories ? prefs.categories[cat] !== false : true}
                    onChange={handleCategoryToggle(cat)}
                    disabled={savingPrefs}
                  />
                }
                label={<Typography variant="body2">{CATEGORY_LABELS[cat]}</Typography>}
              />
            ))}
          </Stack>
        </CardContent>
      </Card>

      <Card sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 2 }}>
        <CardContent sx={{ p: { xs: 1, sm: 2 } }}>
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', px: 1, mb: 1 }}>
            <Typography variant="subtitle1" fontWeight={700}>
              History {total > 0 && <Chip size="small" label={total} sx={{ ml: 1 }} />}
            </Typography>
            {unreadCount > 0 && (
              <Button size="small" startIcon={<DoneAll />} onClick={markAllRead}>Mark all read</Button>
            )}
          </Box>
          <Divider />
          {loading ? (
            <Box sx={{ p: 2 }}>{[...Array(5)].map((_, i) => <Skeleton key={i} height={56} />)}</Box>
          ) : items.length === 0 ? (
            <Box sx={{ textAlign: 'center', py: 6 }}>
              <MarkEmailRead sx={{ fontSize: 40, color: 'text.disabled', mb: 1 }} />
              <Typography variant="body2" color="text.secondary">
                You're all caught up — no notifications yet.
              </Typography>
            </Box>
          ) : (
            <List disablePadding>
              {items.map(n => (
                <ListItem
                  key={n.id}
                  sx={{
                    alignItems: 'flex-start',
                    borderBottom: '1px solid', borderColor: 'divider',
                    bgcolor: n.read ? 'transparent' : 'action.hover',
                  }}
                >
                  {!n.read && (
                    <Box sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: 'primary.main', mt: 1, mr: 1.5, flexShrink: 0 }} />
                  )}
                  <ListItemText
                    primary={<Typography variant="body2" fontWeight={n.read ? 400 : 700}>{n.title}</Typography>}
                    secondary={
                      <>
                        <Typography variant="body2" color="text.secondary" component="span" sx={{ display: 'block' }}>
                          {n.body || n.message}
                        </Typography>
                        <Typography variant="caption" color="text.disabled">
                          {n.created_at ? new Date(n.created_at).toLocaleString() : ''}
                        </Typography>
                      </>
                    }
                    sx={{ pl: n.read ? 2.5 : 0 }}
                  />
                </ListItem>
              ))}
            </List>
          )}
          {hasMore && (
            <Box sx={{ textAlign: 'center', p: 2 }}>
              <Button onClick={loadMore} disabled={loadingMore}>
                {loadingMore ? 'Loading…' : 'Load more'}
              </Button>
            </Box>
          )}
        </CardContent>
      </Card>
    </Container>
  );
}
