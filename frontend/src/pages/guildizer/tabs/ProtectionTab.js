import React, { useEffect, useState } from 'react';
import {
  Box, Grid, Card, CardContent, Typography, Switch, FormControlLabel, TextField,
  MenuItem, Button, Chip, CircularProgress, Alert, Snackbar, List, ListItem,
  ListItemText, Stack, IconButton, Checkbox,
} from '@mui/material';
import { Delete, Add } from '@mui/icons-material';
import guildizerApi from '../../../services/guildizerApi';

const TEXT_TYPES = new Set([0, 5]);
const CF_ACTIONS = ['delete', 'warn', 'timeout', 'kick', 'ban'];
const RG_ACTIONS = ['timeout', 'kick'];
const LADDER_ACTIONS = ['timeout', 'kick', 'ban'];
const CAT_LABEL = {
  nsfw: 'NSFW', csam: 'CSAM', invite: 'Invite', link: 'Link', custom: 'Blocked word',
  spam: 'Spam', raid: 'Raid', lockdown_join: 'Lockdown join', join_gate: 'Join gate', manual_lockdown: 'Lockdown',
  external_link: 'External link', emoji_flood: 'Emoji flood', caps_lock: 'Caps lock', language: 'Language',
  attachment: 'Attachment', sticker: 'Sticker', voice_message: 'Voice message',
  warning: 'Warning', moderation: 'Moderation', report: 'Report',
  smart_mod: 'Smart mod', image_ai: 'Image AI', bot_policy: 'Bot policy',
  anti_nuke: 'Anti-nuke',
};
const SCRIPTS = ['cyrillic', 'chinese', 'korean', 'arabic', 'japanese'];
const CAT_COLOR = { nsfw: 'error', csam: 'error', raid: 'warning', manual_lockdown: 'warning', lockdown_join: 'warning', invite: 'info', link: 'info', anti_nuke: 'error' };
const ESCALATION_TYPES = [
  { key: 'ai_kb', label: '🤖 AI knowledge base — escalate when /ask confidence is low' },
  { key: 'ai_image', label: '🖼️ AI image review — escalate low-confidence image results' },
  { key: 'automation', label: '⚙️ Automation errors — escalate failed scheduled posts / workflows' },
  { key: 'command', label: '📌 Unknown commands — escalate unrecognised bot commands' },
];

// One shared component for every moderation-backed subtab. `section` selects
// which cards render: automod | behavior | reports | verification | escalation.
// All sections share the same GET/PUT /moderation config + save bar.
export default function ProtectionTab({ guildId, channels = [], section = 'automod' }) {
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
    if (section === 'automod') loadEvents();
    if (section === 'reports') loadReports();
    if (section === 'behavior') loadWarnings();
    /* eslint-disable-next-line */
  }, [guildId, section]);

  const set = (patch) => setCfg((c) => ({ ...c, ...patch }));
  const setAm = (sect, patch) => setCfg((c) => ({
    ...c, automod: { ...c.automod, [sect]: { ...c.automod?.[sect], ...patch } },
  }));
  const setSection = (sect) => (patch) => setCfg((c) => ({ ...c, [sect]: { ...c[sect], ...patch } }));
  const setW = setSection('warnings');
  const setAc = setSection('auto_clean');
  const setV = setSection('verification');
  const setEsc = setSection('escalation');
  const setBp = setSection('bot_policy');
  const setEr = setSection('emoji_reactions');
  const setAn = setSection('anti_nuke');
  const setCp = setSection('command_permissions');
  const setWl = setSection('warn_ladder');
  const setRp = setSection('reports');

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
  const channelSelect = (label, value, onChange, emptyLabel = '— system channel —') => (
    <TextField select size="small" margin="dense" fullWidth label={label}
      value={value || ''} onChange={(e) => onChange(e.target.value || null)}>
      <MenuItem value="">{emptyLabel}</MenuItem>
      {textChannels.map((c) => <MenuItem key={c.id} value={c.id}># {c.name}</MenuItem>)}
    </TextField>
  );

  return (
    <Grid container spacing={2}>

      {/* ════════ AUTOMOD ════════ */}
      {section === 'automod' && (
        <>
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
              <Typography variant="subtitle1" fontWeight={700} mb={1}>Automod — media</Typography>
              <FormControlLabel control={<Switch checked={!!cfg.automod?.media?.block_attachments} onChange={(e) => setAm('media', { block_attachments: e.target.checked })} />} label="Block file / image attachments" />
              <FormControlLabel control={<Switch checked={!!cfg.automod?.media?.block_stickers} onChange={(e) => setAm('media', { block_stickers: e.target.checked })} />} label="Block stickers" />
              <FormControlLabel control={<Switch checked={!!cfg.automod?.media?.block_voice} onChange={(e) => setAm('media', { block_voice: e.target.checked })} />} label="Block voice messages" />
            </CardContent></Card>
          </Grid>

          <Grid item xs={12} md={6}>
            <Card variant="outlined"><CardContent>
              <Typography variant="subtitle1" fontWeight={700} mb={1}>AI moderation</Typography>
              <Typography variant="caption" color="text.secondary" display="block" mb={1}>
                Needs an AI key configured on the backend; switches do nothing without it.
              </Typography>
              <FormControlLabel control={<Switch checked={!!cfg.automod?.smart_mod?.enabled} onChange={(e) => setAm('smart_mod', { enabled: e.target.checked })} />} label="Smart mod — AI flags unsolicited promotion/spam" />
              <TextField size="small" margin="dense" fullWidth label="Community topic (helps the AI judge)"
                placeholder="e.g. CreatorX — creator economy tools"
                value={cfg.automod?.smart_mod?.group_topic || ''} onChange={(e) => setAm('smart_mod', { group_topic: e.target.value })} />
              <TextField select size="small" margin="dense" fullWidth label="Action on promo"
                value={cfg.automod?.smart_mod?.action || 'delete'} onChange={(e) => setAm('smart_mod', { action: e.target.value })}>
                {CF_ACTIONS.map((a) => <MenuItem key={a} value={a}>{a}</MenuItem>)}
              </TextField>
              <FormControlLabel control={<Switch checked={!!cfg.automod?.image_ai?.enabled} onChange={(e) => setAm('image_ai', { enabled: e.target.checked })} />} label="Image AI — remove NSFW images" />
            </CardContent></Card>
          </Grid>

          <Grid item xs={12} md={6}>
            <Card variant="outlined"><CardContent>
              <Typography variant="subtitle1" fontWeight={700} mb={1}>🛡️ Bot protection</Typography>
              <FormControlLabel control={<Switch checked={!!cfg.bot_policy?.enabled} onChange={(e) => setBp({ enabled: e.target.checked })} />} label="Guard against unknown bots being added" />
              <TextField select size="small" margin="dense" fullWidth label="When an untrusted bot joins"
                value={cfg.bot_policy?.policy || 'kick_untrusted'} onChange={(e) => setBp({ policy: e.target.value })}>
                <MenuItem value="kick_untrusted">Kick it and alert admins</MenuItem>
                <MenuItem value="alert_only">Alert admins only</MenuItem>
              </TextField>
              {channelSelect('Alert channel', cfg.bot_policy?.alert_channel_id, (v) => setBp({ alert_channel_id: v }))}
              <TextField size="small" margin="dense" fullWidth label="Trusted bot IDs"
                placeholder="123456789, 987654321"
                value={(cfg.bot_policy?.trusted_bot_ids || []).join(', ')}
                onChange={(e) => setBp({ trusted_bot_ids: e.target.value.split(',').map((s) => s.trim()).filter(Boolean) })}
                helperText="Comma-separated Discord user IDs. The alert message also has a one-click Trust button." />
            </CardContent></Card>
          </Grid>

          <Grid item xs={12} md={6}>
            <Card variant="outlined"><CardContent>
              <Typography variant="subtitle1" fontWeight={700} mb={1}>🚨 Raid mode</Typography>
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
              {channelSelect('Announce in channel', cfg.rg_notify_channel_id, (v) => set({ rg_notify_channel_id: v }))}
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
              <Typography variant="subtitle1" fontWeight={700} mb={1}>🧨 Anti-nuke guard</Typography>
              <FormControlLabel control={<Switch checked={!!cfg.anti_nuke?.enabled} onChange={(e) => setAn({ enabled: e.target.checked })} />} label="Contain a compromised admin account" />
              <Typography variant="caption" color="text.secondary" display="block" mb={1}>
                Counts destructive actions per admin (from the audit log). Crossing a threshold inside
                the window triggers the response below. Needs the View Audit Log permission. 0 disables a threshold.
              </Typography>
              <TextField type="number" size="small" margin="dense" fullWidth label="Window (seconds)"
                value={cfg.anti_nuke?.window_seconds ?? 300} inputProps={{ min: 30, max: 3600 }}
                onChange={(e) => setAn({ window_seconds: Number(e.target.value) })} />
              <Grid container spacing={1}>
                {[['max_bans', 'Max bans'], ['max_kicks', 'Max kicks'],
                  ['max_channel_deletes', 'Max channel deletes'], ['max_role_deletes', 'Max role deletes']]
                  .map(([key, label]) => (
                    <Grid item xs={6} key={key}>
                      <TextField type="number" size="small" margin="dense" fullWidth label={label}
                        value={cfg.anti_nuke?.[key] ?? 0} inputProps={{ min: 0, max: 100 }}
                        onChange={(e) => setAn({ [key]: Number(e.target.value) })} />
                    </Grid>
                  ))}
              </Grid>
              <TextField select size="small" margin="dense" fullWidth label="Response when triggered"
                value={cfg.anti_nuke?.action || 'strip_roles'} onChange={(e) => setAn({ action: e.target.value })}>
                <MenuItem value="strip_roles">Strip their elevated roles</MenuItem>
                <MenuItem value="ban">Ban them</MenuItem>
                <MenuItem value="alert_only">Alert admins only</MenuItem>
              </TextField>
              {channelSelect('Alert channel', cfg.anti_nuke?.alert_channel_id, (v) => setAn({ alert_channel_id: v }))}
              <TextField size="small" margin="dense" fullWidth label="Whitelisted admin IDs"
                placeholder="123456789, 987654321"
                value={(cfg.anti_nuke?.whitelist_user_ids || []).join(', ')}
                onChange={(e) => setAn({ whitelist_user_ids: e.target.value.split(',').map((s) => s.trim()).filter(Boolean) })}
                helperText="Comma-separated user IDs the guard never acts on. The server owner and the bot are always exempt." />
            </CardContent></Card>
          </Grid>

          <Grid item xs={12} md={6}>
            <Card variant="outlined"><CardContent>
              <Typography variant="subtitle1" fontWeight={700} mb={1}>Emoji reactions</Typography>
              <Typography variant="caption" color="text.secondary" display="block" mb={1}>
                The bot reacts to messages to keep the community warm. Member reactions follow the cooldown below.
              </Typography>
              <FormControlLabel control={<Switch checked={!!cfg.emoji_reactions?.enabled} onChange={(e) => setEr({ enabled: e.target.checked })} />} label="Enable emoji reactions" />
              <FormControlLabel control={<Switch checked={!!cfg.emoji_reactions?.admin_thumbs_up} onChange={(e) => setEr({ admin_thumbs_up: e.target.checked })} />} label="👍 Thumbs-up on every admin message" />
              <FormControlLabel control={<Switch checked={!!cfg.emoji_reactions?.sentiment_reactions} onChange={(e) => setEr({ sentiment_reactions: e.target.checked })} />} label="React to member messages by sentiment (❤️ 🔥 😂 👍 🎉)" />
              <TextField type="number" size="small" margin="dense" fullWidth label="Cooldown per member (minutes)"
                value={cfg.emoji_reactions?.cooldown_minutes ?? 10} inputProps={{ min: 1, max: 1440 }}
                onChange={(e) => setEr({ cooldown_minutes: Number(e.target.value) })} />
            </CardContent></Card>
          </Grid>

          <Grid item xs={12} md={6}>
            <Card variant="outlined"><CardContent>
              <Typography variant="subtitle1" fontWeight={700} mb={1}>Command permissions</Typography>
              <FormControlLabel control={<Switch checked={!!cfg.command_permissions?.delete_unauthorized} onChange={(e) => setCp({ delete_unauthorized: e.target.checked })} />} label="Delete messages that invoke commands the member can't use" />
              <Typography variant="caption" color="text.secondary" display="block" mt={1}>
                Discord also enforces native slash-command permissions per role — configure those in
                Server Settings → Integrations. This switch covers text-style command misuse.
              </Typography>
            </CardContent></Card>
          </Grid>

          <Grid item xs={12}>
            <Card variant="outlined"><CardContent>
              <Typography variant="subtitle1" fontWeight={700} mb={1}>📋 Protection activity</Typography>
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
        </>
      )}

      {/* ════════ BEHAVIOR ════════ */}
      {section === 'behavior' && (
        <>
          <Grid item xs={12} md={6}>
            <Card variant="outlined"><CardContent>
              <Typography variant="subtitle1" fontWeight={700} mb={1}>Warning thresholds</Typography>
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
              <TextField type="number" size="small" margin="dense" fullWidth
                label="Count warnings from the last N hours (0 = all time)"
                value={cfg.warnings?.window_hours ?? 0} inputProps={{ min: 0, max: 720 }}
                onChange={(e) => setW({ window_hours: Number(e.target.value) })} />
            </CardContent></Card>
          </Grid>

          <Grid item xs={12} md={6}>
            <Card variant="outlined"><CardContent>
              <Typography variant="subtitle1" fontWeight={700} mb={1}>Auto clean</Typography>
              <FormControlLabel control={<Switch checked={!!cfg.auto_clean?.join_messages} onChange={(e) => setAc({ join_messages: e.target.checked })} />} label={'Auto-delete "X joined the server" messages'} />
              <TextField type="number" size="small" margin="dense" fullWidth
                label="Delete warning messages after (seconds, 0 = never)"
                value={cfg.auto_clean?.warn_messages_seconds ?? 0} inputProps={{ min: 0, max: 86400 }}
                onChange={(e) => setAc({ warn_messages_seconds: Number(e.target.value) })} />
              <TextField type="number" size="small" margin="dense" fullWidth
                label="Delete mod-action messages after (seconds, 0 = never)"
                value={cfg.auto_clean?.action_messages_seconds ?? 0} inputProps={{ min: 0, max: 86400 }}
                onChange={(e) => setAc({ action_messages_seconds: Number(e.target.value) })} />
            </CardContent></Card>
          </Grid>

          <Grid item xs={12}>
            <Card variant="outlined"><CardContent>
              <Typography variant="subtitle1" fontWeight={700} mb={1}>Escalating punishments</Typography>
              <FormControlLabel control={<Switch checked={!!cfg.warn_ladder?.enabled} onChange={(e) => setWl({ enabled: e.target.checked })} />} label="Enable an escalating punishment ladder" />
              <Typography variant="caption" color="text.secondary" display="block" mb={1}>
                Each step fires when a member reaches that warning count (counted within the step's window). Warnings aren't reset between steps, so higher steps stay reachable.
              </Typography>
              {(cfg.warn_ladder?.steps || []).map((s, i) => (
                <Stack key={i} direction="row" spacing={1} alignItems="center" mb={1} useFlexGap flexWrap="wrap">
                  <TextField type="number" size="small" label="At warning #" value={s.at}
                    inputProps={{ min: 1, max: 20 }} sx={{ width: 120 }}
                    onChange={(e) => setWl({ steps: cfg.warn_ladder.steps.map((x, j) => j === i ? { ...x, at: Number(e.target.value) } : x) })} />
                  <TextField select size="small" label="Action" value={s.action} sx={{ width: 130 }}
                    onChange={(e) => setWl({ steps: cfg.warn_ladder.steps.map((x, j) => j === i ? { ...x, action: e.target.value } : x) })}>
                    {LADDER_ACTIONS.map((a) => <MenuItem key={a} value={a}>{a}</MenuItem>)}
                  </TextField>
                  {s.action === 'timeout' && (
                    <TextField type="number" size="small" label="Minutes" value={s.minutes}
                      inputProps={{ min: 1, max: 40320 }} sx={{ width: 110 }}
                      onChange={(e) => setWl({ steps: cfg.warn_ladder.steps.map((x, j) => j === i ? { ...x, minutes: Number(e.target.value) } : x) })} />
                  )}
                  <TextField type="number" size="small" label="Within (hrs, 0=all)" value={s.window_hours}
                    inputProps={{ min: 0, max: 720 }} sx={{ width: 150 }}
                    onChange={(e) => setWl({ steps: cfg.warn_ladder.steps.map((x, j) => j === i ? { ...x, window_hours: Number(e.target.value) } : x) })} />
                  <IconButton size="small" onClick={() => setWl({ steps: cfg.warn_ladder.steps.filter((_, j) => j !== i) })}>
                    <Delete fontSize="small" />
                  </IconButton>
                </Stack>
              ))}
              <Button size="small" startIcon={<Add />}
                disabled={(cfg.warn_ladder?.steps || []).length >= 5}
                onClick={() => setWl({ steps: [...(cfg.warn_ladder?.steps || []), { at: (cfg.warn_ladder?.steps?.length || 0) + 2, action: 'timeout', minutes: 30, window_hours: 0 }] })}>
                Add step
              </Button>
            </CardContent></Card>
          </Grid>

          <Grid item xs={12}>
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
        </>
      )}

      {/* ════════ REPORTS ════════ */}
      {section === 'reports' && (
        <>
          <Grid item xs={12} md={6}>
            <Card variant="outlined"><CardContent>
              <Typography variant="subtitle1" fontWeight={700} mb={1}>Report settings</Typography>
              <Typography variant="caption" color="text.secondary" display="block" mb={1}>
                Members use /report to flag messages or members. Reports land here and (optionally) in a channel.
              </Typography>
              {channelSelect('Alert channel for new reports', cfg.reports?.alert_channel_id,
                (v) => setRp({ alert_channel_id: v }), '— dashboard only —')}
            </CardContent></Card>
          </Grid>

          <Grid item xs={12}>
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
        </>
      )}

      {/* ════════ VERIFICATION (Members tab) ════════ */}
      {section === 'verification' && (
        <>
          <Grid item xs={12} md={6}>
            <Card variant="outlined"><CardContent>
              <Typography variant="subtitle1" fontWeight={700} mb={1}>Join verification (captcha)</Typography>
              <FormControlLabel control={<Switch checked={!!cfg.verification?.enabled} onChange={(e) => setV({ enabled: e.target.checked })} />} label="Require new members to verify before they can see the server" />
              <Typography variant="caption" color="text.secondary" display="block" mb={1}>
                On first use the bot creates an Unverified role and a #verify channel, and hides
                other channels from unverified members. Needs Manage Roles + Manage Channels.
              </Typography>
              <TextField select size="small" margin="dense" fullWidth label="Challenge type"
                value={cfg.verification?.method || 'button'} onChange={(e) => setV({ method: e.target.value })}>
                <MenuItem value="button">Button click</MenuItem>
                <MenuItem value="math">Math question</MenuItem>
                <MenuItem value="word">Type a word</MenuItem>
              </TextField>
              <TextField type="number" size="small" margin="dense" fullWidth label="Timeout (seconds)"
                value={cfg.verification?.timeout_seconds ?? 300} inputProps={{ min: 60, max: 3600 }}
                onChange={(e) => setV({ timeout_seconds: Number(e.target.value) })} />
              <TextField type="number" size="small" margin="dense" fullWidth label="Max attempts"
                value={cfg.verification?.max_attempts ?? 3} inputProps={{ min: 1, max: 10 }}
                onChange={(e) => setV({ max_attempts: Number(e.target.value) })} />
              <TextField select size="small" margin="dense" fullWidth label="On timeout"
                value={cfg.verification?.on_timeout || 'kick'} onChange={(e) => setV({ on_timeout: e.target.value })}>
                <MenuItem value="kick">Kick the member</MenuItem>
                <MenuItem value="keep">Keep them unverified</MenuItem>
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
        </>
      )}

      {/* ════════ ESCALATION (AI & Integrations tab) ════════ */}
      {section === 'escalation' && (
        <Grid item xs={12} md={8}>
          <Card variant="outlined"><CardContent>
            <Typography variant="subtitle1" fontWeight={700} mb={1}>Escalation alerts</Typography>
            <FormControlLabel control={<Switch checked={!!cfg.escalation?.enabled} onChange={(e) => setEsc({ enabled: e.target.checked })} />} label="Alert admins when members sound frustrated" />
            <TextField size="small" margin="dense" fullWidth label="Trigger keywords"
              placeholder="refund, scam, not working"
              value={(cfg.escalation?.keywords || []).join(', ')}
              onChange={(e) => setEsc({ keywords: e.target.value.split(',').map((k) => k.trim()).filter(Boolean) })}
              helperText="Comma-separated. One alert per member per 10 minutes." />
            <TextField select size="small" margin="dense" fullWidth label="Alert channel"
              value={cfg.escalation?.alert_channel_id || ''} onChange={(e) => setEsc({ alert_channel_id: e.target.value || null })}>
              <MenuItem value="">- none -</MenuItem>
              {textChannels.map((c) => <MenuItem key={c.id} value={c.id}># {c.name}</MenuItem>)}
            </TextField>
            <Typography variant="subtitle2" fontWeight={700} mt={2}>Also escalate</Typography>
            {ESCALATION_TYPES.map(({ key, label }) => (
              <FormControlLabel key={key} sx={{ display: 'flex' }} control={(
                <Checkbox size="small" checked={(cfg.escalation?.types || []).includes(key)}
                  onChange={(e) => setEsc({
                    types: e.target.checked
                      ? [...(cfg.escalation?.types || []), key]
                      : (cfg.escalation?.types || []).filter((t) => t !== key),
                  })} />
              )} label={<Typography variant="body2">{label}</Typography>} />
            ))}
          </CardContent></Card>
        </Grid>
      )}

      <Grid item xs={12} sx={{ display: 'flex', justifyContent: 'flex-end', gap: 2, alignItems: 'center' }}>
        {error && <Alert severity="error" sx={{ py: 0 }}>{error}</Alert>}
        <Button variant="contained" onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Save changes'}</Button>
      </Grid>

      <Snackbar open={saved} autoHideDuration={2500} onClose={() => setSaved(false)} message="Saved"
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }} />
    </Grid>
  );
}
