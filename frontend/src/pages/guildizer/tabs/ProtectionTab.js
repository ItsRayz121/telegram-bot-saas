import React, { useEffect, useState } from 'react';
import {
  Box, Grid, Card, CardContent, Typography, Switch, FormControlLabel, TextField,
  MenuItem, Button, Chip, CircularProgress, Alert, Snackbar, List, ListItem, ListItemText, Stack,
} from '@mui/material';
import guildizerApi from '../../../services/guildizerApi';

const TEXT_TYPES = new Set([0, 5]);
const CF_ACTIONS = ['delete', 'warn', 'timeout', 'kick', 'ban'];
const RG_ACTIONS = ['timeout', 'kick'];
const CAT_LABEL = {
  nsfw: 'NSFW', csam: 'CSAM', invite: 'Invite', link: 'Link', custom: 'Blocked word',
  spam: 'Spam', raid: 'Raid', lockdown_join: 'Lockdown join', join_gate: 'Join gate', manual_lockdown: 'Lockdown',
  external_link: 'External link', emoji_flood: 'Emoji flood', caps_lock: 'Caps lock', language: 'Language',
  attachment: 'Attachment', sticker: 'Sticker', voice_message: 'Voice message',
  warning: 'Warning', moderation: 'Moderation', report: 'Report',
};
const SCRIPTS = ['cyrillic', 'chinese', 'korean', 'arabic', 'japanese'];
const CAT_COLOR = { nsfw: 'error', csam: 'error', raid: 'warning', manual_lockdown: 'warning', lockdown_join: 'warning', invite: 'info', link: 'info' };

export default function ProtectionTab({ guildId, channels = [] }) {
  const [cfg, setCfg] = useState(null);
  const [wordsText, setWordsText] = useState('');
  const [events, setEvents] = useState([]);
  const [wlText, setWlText] = useState('');
  const [reports, setReports] = useState([]);
  const [recentWarnings, setRecentWarnings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(null);

  const textChannels = channels.filter((c) => TEXT_TYPES.has(c.type));

  const loadEvents = () => guildizerApi.get(`/api/guilds/${guildId}/protection/events?limit=50`)
    .then(({ data }) => setEvents(data.events)).catch(() => {});
  const loadReports = () => guildizerApi.get(`/api/guilds/${guildId}/reports?status=open`)
    .then(({ data }) => setReports(data.reports)).catch(() => {});
  const loadWarnings = () => guildizerApi.get(`/api/guilds/${guildId}/warnings?limit=15`)
    .then(({ data }) => setRecentWarnings(data.warnings)).catch(() => {});

  useEffect(() => {
    guildizerApi.get(`/api/guilds/${guildId}/moderation`)
      .then(({ data }) => {
        setCfg(data);
        setWordsText((data.cf_custom_words || []).join(', '));
        setWlText(((data.automod?.external_links?.whitelist) || []).join(', '));
      })
      .catch(() => setError('Failed to load protection settings.'))
      .finally(() => setLoading(false));
    loadEvents(); loadReports(); loadWarnings(); /* eslint-disable-next-line */
  }, [guildId]);

  const set = (patch) => setCfg((c) => ({ ...c, ...patch }));
  const setAm = (section, patch) => setCfg((c) => ({
    ...c, automod: { ...c.automod, [section]: { ...c.automod?.[section], ...patch } },
  }));
  const setW = (patch) => setCfg((c) => ({ ...c, warnings: { ...c.warnings, ...patch } }));
  const setAc = (patch) => setCfg((c) => ({ ...c, auto_clean: { ...c.auto_clean, ...patch } }));

  async function reviewReport(id, status) {
    try {
      await guildizerApi.post(`/api/guilds/${guildId}/reports/${id}/review`, { status });
      loadReports();
    } catch { setError('Could not update the report.'); }
  }

  async function save() {
    setSaving(true); setError(null);
    try {
      const payload = {
        ...cfg,
        cf_custom_words: wordsText.split(',').map((w) => w.trim()).filter(Boolean),
        automod: {
          ...cfg.automod,
          external_links: {
            ...cfg.automod?.external_links,
            whitelist: wlText.split(',').map((w) => w.trim()).filter(Boolean),
          },
        },
      };
      const { data } = await guildizerApi.put(`/api/guilds/${guildId}/moderation`, payload);
      setCfg(data);
      setWordsText((data.cf_custom_words || []).join(', '));
      setWlText(((data.automod?.external_links?.whitelist) || []).join(', '));
      setSaved(true);
    } catch { setError('Save failed.'); } finally { setSaving(false); }
  }

  async function lockdown(minutes) {
    const { data } = await guildizerApi.post(`/api/guilds/${guildId}/moderation/lockdown`, { minutes });
    setCfg(data); loadEvents();
  }

  if (loading) return <Box sx={{ display: 'grid', placeItems: 'center', py: 4 }}><CircularProgress /></Box>;
  if (!cfg) return <Alert severity="warning">{error || 'No settings.'}</Alert>;

  const num = (label, key, min, max) => (
    <TextField type="number" size="small" margin="dense" fullWidth label={label}
      value={cfg[key]} inputProps={{ min, max }} onChange={(e) => set({ [key]: Number(e.target.value) })} />
  );

  return (
    <Grid container spacing={2}>
      <Grid item xs={12} md={6}>
        <Card variant="outlined"><CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>Content filter</Typography>
          <FormControlLabel control={<Switch checked={cfg.cf_enabled} onChange={(e) => set({ cf_enabled: e.target.checked })} />} label="Scan messages and act on violations" />
          <TextField select size="small" margin="dense" fullWidth label="Action on violation"
            value={cfg.cf_action} onChange={(e) => set({ cf_action: e.target.value })}
            helperText="CSAM always bans regardless of this setting.">
            {CF_ACTIONS.map((a) => <MenuItem key={a} value={a}>{a}</MenuItem>)}
          </TextField>
          <FormControlLabel control={<Switch checked={cfg.cf_nsfw} onChange={(e) => set({ cf_nsfw: e.target.checked })} />} label="Block NSFW / explicit content" />
          <FormControlLabel control={<Switch checked={cfg.cf_invites} onChange={(e) => set({ cf_invites: e.target.checked })} />} label="Remove foreign Discord invites" />
          <FormControlLabel control={<Switch checked={cfg.cf_links} onChange={(e) => set({ cf_links: e.target.checked })} />} label="Remove shortened / suspicious links" />
          <TextField size="small" margin="dense" fullWidth label="Custom blocked words" placeholder="word1, word2, …"
            value={wordsText} onChange={(e) => { setWordsText(e.target.value); }} helperText="Comma-separated (leet/spacing aware)." />
        </CardContent></Card>
      </Grid>

      <Grid item xs={12} md={6}>
        <Card variant="outlined"><CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>Raid guard</Typography>
          <FormControlLabel control={<Switch checked={cfg.rg_enabled} onChange={(e) => set({ rg_enabled: e.target.checked })} />} label="Auto-lock on coordinated spam" />
          <Typography variant="caption" color="text.secondary" display="block" mb={1}>
            Triggers on many distinct accounts tripping the filter or posting identical text — not raw join rate.
          </Typography>
          {num('Window (seconds)', 'rg_window_seconds', 10, 600)}
          {num('Violators to trigger', 'rg_trigger_violators', 2, 50)}
          {num('Duplicate-flood threshold', 'rg_duplicate_threshold', 2, 50)}
          {num('Lockdown minutes', 'rg_lockdown_minutes', 1, 1440)}
          <TextField select size="small" margin="dense" fullWidth label="Lockdown action for joiners"
            value={cfg.rg_lockdown_action} onChange={(e) => set({ rg_lockdown_action: e.target.value })}>
            {RG_ACTIONS.map((a) => <MenuItem key={a} value={a}>{a}</MenuItem>)}
          </TextField>
          <FormControlLabel control={<Switch checked={cfg.rg_notify} onChange={(e) => set({ rg_notify: e.target.checked })} />} label="Announce when raid mode activates" />
          <TextField select size="small" margin="dense" fullWidth label="Announce in channel"
            value={cfg.rg_notify_channel_id || ''} onChange={(e) => set({ rg_notify_channel_id: e.target.value || null })}>
            <MenuItem value="">— system channel —</MenuItem>
            {textChannels.map((c) => <MenuItem key={c.id} value={c.id}># {c.name}</MenuItem>)}
          </TextField>
        </CardContent></Card>
      </Grid>

      <Grid item xs={12} md={6}>
        <Card variant="outlined"><CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>Join gate</Typography>
          {num('Minimum account age (days, 0 = off)', 'jg_min_account_age_days', 0, 365)}
          <Typography variant="caption" color="text.disabled">Newer accounts are kicked on join. Useful during raids.</Typography>
        </CardContent></Card>
      </Grid>

      <Grid item xs={12} md={6}>
        <Card variant="outlined"><CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>Emergency lockdown</Typography>
          {cfg.manual_lockdown_active ? (
            <>
              <Typography color="error" fontWeight={600} mb={1}>🔒 Active until {new Date(cfg.manual_lockdown_until).toLocaleString()}</Typography>
              <Button variant="outlined" onClick={() => lockdown(0)}>Lift lockdown</Button>
            </>
          ) : (
            <>
              <Typography variant="body2" color="text.secondary" mb={1}>Instantly restrict every new joiner (timeout/kick per raid-guard action).</Typography>
              <Stack direction="row" spacing={1}>
                <Button variant="contained" onClick={() => lockdown(30)}>Lock 30 min</Button>
                <Button variant="outlined" onClick={() => lockdown(120)}>Lock 2 h</Button>
              </Stack>
            </>
          )}
        </CardContent></Card>
      </Grid>

      <Grid item xs={12} md={6}>
        <Card variant="outlined"><CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>Automod — links & text</Typography>
          <FormControlLabel control={<Switch checked={!!cfg.automod?.external_links?.enabled} onChange={(e) => setAm('external_links', { enabled: e.target.checked })} />} label="Block all external links except the whitelist" />
          <TextField size="small" margin="dense" fullWidth label="Whitelisted domains" placeholder="youtube.com, x.com"
            value={wlText} onChange={(e) => setWlText(e.target.value)} helperText="Comma-separated. Subdomains are allowed automatically." />
          <FormControlLabel control={<Switch checked={!!cfg.automod?.excessive_emojis?.enabled} onChange={(e) => setAm('excessive_emojis', { enabled: e.target.checked })} />} label="Limit emojis per message" />
          <TextField type="number" size="small" margin="dense" fullWidth label="Max emojis"
            value={cfg.automod?.excessive_emojis?.max_emojis ?? 15} inputProps={{ min: 1, max: 100 }}
            onChange={(e) => setAm('excessive_emojis', { max_emojis: Number(e.target.value) })} />
          <FormControlLabel control={<Switch checked={!!cfg.automod?.caps_lock?.enabled} onChange={(e) => setAm('caps_lock', { enabled: e.target.checked })} />} label="Remove ALL-CAPS shouting" />
          <FormControlLabel control={<Switch checked={!!cfg.automod?.language_filter?.enabled} onChange={(e) => setAm('language_filter', { enabled: e.target.checked })} />} label="Filter foreign scripts" />
          <TextField select size="small" margin="dense" fullWidth label="Filtered scripts"
            SelectProps={{ multiple: true }} value={cfg.automod?.language_filter?.scripts || []}
            onChange={(e) => setAm('language_filter', { scripts: e.target.value })}>
            {SCRIPTS.map((s) => <MenuItem key={s} value={s}>{s}</MenuItem>)}
          </TextField>
        </CardContent></Card>
      </Grid>

      <Grid item xs={12} md={6}>
        <Card variant="outlined"><CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>Automod — media & warnings</Typography>
          <FormControlLabel control={<Switch checked={!!cfg.automod?.media?.block_attachments} onChange={(e) => setAm('media', { block_attachments: e.target.checked })} />} label="Block file / image attachments" />
          <FormControlLabel control={<Switch checked={!!cfg.automod?.media?.block_stickers} onChange={(e) => setAm('media', { block_stickers: e.target.checked })} />} label="Block stickers" />
          <FormControlLabel control={<Switch checked={!!cfg.automod?.media?.block_voice} onChange={(e) => setAm('media', { block_voice: e.target.checked })} />} label="Block voice messages" />
          <Typography variant="subtitle2" fontWeight={700} mt={2} mb={0.5}>Warning ladder</Typography>
          <Typography variant="caption" color="text.secondary" display="block" mb={1}>
            /warn and automod warnings count up; at the limit the action fires and the count resets.
          </Typography>
          <TextField type="number" size="small" margin="dense" fullWidth label="Max warnings"
            value={cfg.warnings?.max_warnings ?? 3} inputProps={{ min: 1, max: 20 }}
            onChange={(e) => setW({ max_warnings: Number(e.target.value) })} />
          <TextField select size="small" margin="dense" fullWidth label="Action at the limit"
            value={cfg.warnings?.action || 'timeout'} onChange={(e) => setW({ action: e.target.value })}>
            {['timeout', 'kick', 'ban', 'none'].map((a) => <MenuItem key={a} value={a}>{a}</MenuItem>)}
          </TextField>
          {(cfg.warnings?.action || 'timeout') === 'timeout' && (
            <TextField type="number" size="small" margin="dense" fullWidth label="Timeout minutes"
              value={cfg.warnings?.timeout_minutes ?? 30} inputProps={{ min: 1, max: 40320 }}
              onChange={(e) => setW({ timeout_minutes: Number(e.target.value) })} />
          )}
          <FormControlLabel control={<Switch checked={!!cfg.auto_clean?.join_messages} onChange={(e) => setAc({ join_messages: e.target.checked })} />} label={'Auto-delete "X joined the server" messages'} />
        </CardContent></Card>
      </Grid>

      <Grid item xs={12} md={6}>
        <Card variant="outlined"><CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>Open reports ({reports.length})</Typography>
          {reports.length === 0 && <Typography variant="body2" color="text.secondary">No open reports. 🎉</Typography>}
          <List dense>
            {reports.map((r) => (
              <ListItem key={r.id} disableGutters
                secondaryAction={(
                  <Stack direction="row" spacing={1}>
                    <Button size="small" onClick={() => reviewReport(r.id, 'actioned')}>Actioned</Button>
                    <Button size="small" color="inherit" onClick={() => reviewReport(r.id, 'dismissed')}>Dismiss</Button>
                  </Stack>
                )}>
                <ListItemText
                  primary={`${r.target_name || r.target_id || 'unknown'} — ${r.reason || 'no reason'}`}
                  secondary={`by ${r.reporter_name} · ${new Date(r.created_at).toLocaleString()}${r.message_excerpt ? ` · "${r.message_excerpt.slice(0, 80)}"` : ''}`}
                  primaryTypographyProps={{ variant: 'body2', noWrap: true }} />
              </ListItem>
            ))}
          </List>
        </CardContent></Card>
      </Grid>

      <Grid item xs={12} md={6}>
        <Card variant="outlined"><CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>Recent warnings</Typography>
          {recentWarnings.length === 0 && <Typography variant="body2" color="text.secondary">No warnings yet.</Typography>}
          <List dense>
            {recentWarnings.map((w) => (
              <ListItem key={w.id} disableGutters
                secondaryAction={<Typography variant="caption" color="text.disabled">{new Date(w.created_at).toLocaleString()}</Typography>}>
                <ListItemText
                  primary={`${w.username || w.user_id} — ${w.reason || 'no reason'}`}
                  secondary={`by ${w.moderator_name || 'automod'}`}
                  primaryTypographyProps={{ variant: 'body2', noWrap: true }} />
              </ListItem>
            ))}
          </List>
        </CardContent></Card>
      </Grid>

      <Grid item xs={12} sx={{ display: 'flex', justifyContent: 'flex-end', gap: 2, alignItems: 'center' }}>
        {error && <Alert severity="error" sx={{ py: 0 }}>{error}</Alert>}
        <Button variant="contained" onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Save changes'}</Button>
      </Grid>

      <Grid item xs={12}>
        <Card variant="outlined"><CardContent>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>Protection activity</Typography>
          {events.length === 0 && <Typography variant="body2" color="text.secondary">No events yet.</Typography>}
          <List dense>
            {events.map((e) => (
              <ListItem key={e.id} disableGutters
                secondaryAction={<Typography variant="caption" color="text.disabled">{new Date(e.created_at).toLocaleString()}</Typography>}>
                <Chip size="small" label={CAT_LABEL[e.category] || e.category} color={CAT_COLOR[e.category] || 'default'} variant="outlined" sx={{ mr: 1 }} />
                <ListItemText primary={`${e.action} — ${e.username ? e.username + ' · ' : ''}${e.detail || ''}`}
                  primaryTypographyProps={{ variant: 'body2', noWrap: true }} />
              </ListItem>
            ))}
          </List>
        </CardContent></Card>
      </Grid>

      <Snackbar open={saved} autoHideDuration={2500} onClose={() => setSaved(false)} message="Saved"
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }} />
    </Grid>
  );
}
