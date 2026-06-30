import React, { useEffect, useState, useMemo } from 'react';
import {
  Box, Grid, Typography, Switch, FormControlLabel, TextField,
  MenuItem, Button, Chip, CircularProgress, Alert, Snackbar, List, ListItem,
  ListItemText, Stack, IconButton, Checkbox, Divider, FormControl, InputLabel,
  Select,
} from '@mui/material';
import { Delete, Add } from '@mui/icons-material';
import guildizerApi from '../../../services/guildizerApi';
import GuildizerCollapsibleCard from '../../../components/guildizer/GuildizerCollapsibleCard';
import BlockedWordPresets from '../../../components/BlockedWordPresets';
import { DISCORD_PACKS } from '../../../data/blockedWordPacks';
import { useSaveBar } from './saveBar';

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
const SCRIPTS = [
  { value: 'cyrillic', label: 'Cyrillic (Russian, Ukrainian…)' },
  { value: 'chinese', label: 'Chinese' },
  { value: 'korean', label: 'Korean' },
  { value: 'arabic', label: 'Arabic' },
  { value: 'japanese', label: 'Japanese' },
];
const CAT_COLOR = { nsfw: 'error', csam: 'error', raid: 'warning', manual_lockdown: 'warning', lockdown_join: 'warning', invite: 'info', link: 'info', anti_nuke: 'error' };
const ESCALATION_TYPES = [
  { key: 'ai_kb', label: '🤖 AI knowledge base — escalate when /ask confidence is low' },
  { key: 'ai_image', label: '🖼️ AI image review — escalate low-confidence image results' },
  { key: 'automation', label: '⚙️ Automation errors — escalate failed scheduled posts / workflows' },
  { key: 'command', label: '📌 Unknown commands — escalate unrecognised bot commands' },
];

// Pro gating chip — visual parity with Telegizer's ProBadge.
function ProBadge() {
  return <Chip label="Pro" color="primary" size="small" sx={{ ml: 1, height: 18, fontSize: '0.65rem', fontWeight: 700 }} />;
}

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
  const [orig, setOrig] = useState(null);
  const [eventsLoading, setEventsLoading] = useState(false);

  const textChannels = channels.filter((c) => TEXT_TYPES.has(c.type));

  const snapshot = (data, words, wl) => JSON.stringify([data, words, wl]);

  const loadEvents = () => {
    setEventsLoading(true);
    return guildizerApi.get(`/api/guilds/${guildId}/protection/events?limit=50`)
      .then(({ data }) => setEvents(data.events)).catch(() => {}).finally(() => setEventsLoading(false));
  };
  const loadReports = () => guildizerApi.get(`/api/guilds/${guildId}/reports?status=open`)
    .then(({ data }) => setReports(data.reports)).catch(() => {});
  const loadWarnings = () => guildizerApi.get(`/api/guilds/${guildId}/warnings?limit=15`)
    .then(({ data }) => setRecentWarnings(data.warnings)).catch(() => {});

  useEffect(() => {
    guildizerApi.get(`/api/guilds/${guildId}/moderation`)
      .then(({ data }) => {
        const words = (data.cf_custom_words || []).join(', ');
        const wl = ((data.automod?.external_links?.whitelist) || []).join(', ');
        setCfg(data);
        setWordsText(words);
        setWlText(wl);
        setOrig(snapshot(data, words, wl));
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
  const setMl = setSection('mod_log');
  const setAa = setSection('admin_alerts');
  const setSr = setSection('social_replies');

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
      const words = (data.cf_custom_words || []).join(', ');
      const wl = ((data.automod?.external_links?.whitelist) || []).join(', ');
      setCfg(data);
      setWordsText(words);
      setWlText(wl);
      setOrig(snapshot(data, words, wl));
      setSaved(true);
    } catch { setError('Save failed.'); } finally { setSaving(false); }
  }

  async function lockdown(minutes) {
    const { data } = await guildizerApi.post(`/api/guilds/${guildId}/moderation/lockdown`, { minutes });
    setCfg(data); loadEvents();
  }

  const dirty = useMemo(
    () => cfg != null && orig != null && snapshot(cfg, wordsText, wlText) !== orig,
    [cfg, wordsText, wlText, orig],
  );

  // Register with the shell's single sticky Save button. Standalone → render own.
  const sb = useSaveBar({ save, dirty, saving });

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

  const am = cfg.automod || {};

  // Core Rules grid — Guildizer's real boolean filters, laid out like Telegizer.
  const coreRules = [
    ['NSFW / Adult Filter', !!cfg.cf_nsfw, (v) => set({ cf_nsfw: v })],
    ['Remove Foreign Invites', !!cfg.cf_invites, (v) => set({ cf_invites: v })],
    ['Suspicious / Shortened Links', !!cfg.cf_links, (v) => set({ cf_links: v })],
    ['Block External Links', !!am.external_links?.enabled, (v) => setAm('external_links', { enabled: v })],
    ['Excessive Emojis', !!am.excessive_emojis?.enabled, (v) => setAm('excessive_emojis', { enabled: v })],
    ['Caps-Lock Shouting', !!am.caps_lock?.enabled, (v) => setAm('caps_lock', { enabled: v })],
  ];

  return (
    <Box>
      {/* ════════════════════════════ AUTOMOD ════════════════════════════ */}
      {section === 'automod' && (
        <>
          {/* 1 ── AutoMod / Core Rules ─────────────────────────────────────── */}
          <GuildizerCollapsibleCard id="gz.moderation.automod" title="AutoMod" sx={{ mb: 2 }}>
              <FormControlLabel
                control={<Switch checked={!!cfg.cf_enabled} onChange={(e) => set({ cf_enabled: e.target.checked })} />}
                label="Enable content filtering globally"
              />

              <Divider sx={{ my: 2 }} />
              <Typography variant="subtitle2" fontWeight={600} mb={1}>Core Rules</Typography>
              <Grid container spacing={1}>
                {coreRules.map(([label, checked, onChange]) => (
                  <Grid item xs={12} sm={6} key={label}>
                    <FormControlLabel
                      control={<Switch checked={checked} onChange={(e) => onChange(e.target.checked)} />}
                      label={label}
                    />
                  </Grid>
                ))}
              </Grid>

              <Grid container spacing={2} sx={{ mt: 0.5 }}>
                <Grid item xs={12} sm={6}>
                  <TextField select size="small" fullWidth label="Action on violation"
                    value={cfg.cf_action} onChange={(e) => set({ cf_action: e.target.value })}
                    helperText="CSAM always bans regardless of this setting.">
                    {CF_ACTIONS.map((a) => <MenuItem key={a} value={a}>{a}</MenuItem>)}
                  </TextField>
                </Grid>
                <Grid item xs={12} sm={6}>
                  <TextField type="number" size="small" fullWidth label="Max emojis per message"
                    value={am.excessive_emojis?.max_emojis ?? 15} inputProps={{ min: 1, max: 100 }}
                    onChange={(e) => setAm('excessive_emojis', { max_emojis: Number(e.target.value) })} />
                </Grid>
              </Grid>
              <TextField fullWidth multiline rows={2} label="Custom Blocked Words (comma separated)" sx={{ mt: 2 }}
                placeholder="word1, word2, …" helperText="Leet/spacing aware."
                value={wordsText} onChange={(e) => setWordsText(e.target.value)} />
              <BlockedWordPresets packs={DISCORD_PACKS} onAdd={(words) => {
                const cur = wordsText.split(',').map((w) => w.trim()).filter(Boolean);
                setWordsText(Array.from(new Set([...cur, ...words])).join(', '));
              }} />
              <TextField fullWidth multiline rows={2} label="Whitelisted Domains (for external-link blocking)" sx={{ mt: 2 }}
                placeholder="youtube.com, x.com" helperText="Comma-separated. Subdomains are allowed automatically."
                value={wlText} onChange={(e) => setWlText(e.target.value)} />

              <Divider sx={{ my: 2 }} />
              <Typography variant="subtitle2" fontWeight={600} mb={1}>⚡ Native AutoMod sync</Typography>
              <Typography variant="body2" color="text.secondary" mb={1}>
                Discord has its own built-in <strong>AutoMod</strong> that blocks messages at the
                platform level — before anyone sees them, and <strong>even when Guildizer is offline
                or rate-limited</strong>. This mirrors your custom blocked-words list (and optionally
                discord.gg invite links) into that native filter, so your rules keep working as a
                safety net. Guildizer still does the smarter AI moderation on top; this is belt-and-braces.
                Needs the <strong>Manage Server</strong> permission; syncs within a minute of saving.
              </Typography>
              <FormControlLabel control={<Switch checked={!!am.native_sync?.enabled} onChange={(e) => setAm('native_sync', { enabled: e.target.checked })} />} label="Mirror the custom blocked words into Discord AutoMod" />
              <FormControlLabel control={<Switch checked={!!am.native_sync?.block_invites} onChange={(e) => setAm('native_sync', { block_invites: e.target.checked })} />} label="Also block discord.gg invite links natively" />
              {channelSelect('Alert channel for blocked messages', am.native_sync?.alert_channel_id, (v) => setAm('native_sync', { alert_channel_id: v }), '— no alerts —')}
              {am.native_sync?.last_error ? (
                <Alert severity="warning" sx={{ mt: 1 }}>{am.native_sync.last_error}</Alert>
              ) : (
                <Typography variant="caption" color="text.disabled" display="block" mt={1}>
                  {am.native_sync?.dirty
                    ? 'Sync queued…'
                    : am.native_sync?.last_synced_at
                      ? `Last synced ${new Date(am.native_sync.last_synced_at).toLocaleString()}`
                      : 'Not synced yet.'}
                </Typography>
              )}
          </GuildizerCollapsibleCard>

          {/* 1b ── Anti-Spam / Flood ───────────────────────────────────────── */}
          <GuildizerCollapsibleCard id="gz.moderation.anti_spam_flood" title="Anti-Spam / Flood" sx={{ mb: 2 }}>
              <Typography variant="body2" color="text.secondary" mb={2}>
                Catches a single member firing off messages too fast. (Coordinated multi-user
                raids are handled separately under <b>Behavior → Raid Protection</b>.)
              </Typography>

              <Alert severity="info" icon={false} sx={{ mb: 2 }}>
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                  <b>Want Discord's native Slowmode</b> (the box shows a live "you can send again in …"
                  countdown that blocks posting up front)? It's set <b>per channel</b>, and any admin can
                  turn it on in seconds:
                </Typography>
                <Typography component="ol" variant="caption" color="text.secondary"
                  sx={{ pl: 2.5, m: 0, mt: 0.75, '& li': { mb: 0.25 } }}>
                  <li>Hover the channel → <b>Edit Channel</b> (gear) → <b>Overview</b>.</li>
                  <li>Set <b>Slowmode</b> to an interval (5s – 6h) and save.</li>
                  <li>Done — Discord shows every member a per-user cooldown timer in that channel.</li>
                </Typography>
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.75 }}>
                  Run both together — they don't conflict. Native Slowmode paces the steady drip per
                  channel; the flood control below catches bursts across the whole server and can
                  timeout repeat offenders.
                </Typography>
              </Alert>

              <FormControlLabel
                control={<Switch checked={!!am.flood?.enabled} onChange={(e) => setAm('flood', { enabled: e.target.checked })} />}
                label="Enable per-member flood control"
              />
              {am.flood?.enabled && (
                <Grid container spacing={2} sx={{ mt: 0.5 }}>
                  <Grid item xs={6} sm={3}>
                    <TextField type="number" size="small" fullWidth label="Max messages"
                      value={am.flood?.max_messages ?? 5} inputProps={{ min: 2, max: 50 }}
                      onChange={(e) => setAm('flood', { max_messages: Number(e.target.value) })} />
                  </Grid>
                  <Grid item xs={6} sm={3}>
                    <TextField type="number" size="small" fullWidth label="Within seconds"
                      value={am.flood?.window_seconds ?? 10} inputProps={{ min: 2, max: 120 }}
                      onChange={(e) => setAm('flood', { window_seconds: Number(e.target.value) })} />
                  </Grid>
                  <Grid item xs={6} sm={3}>
                    <FormControl size="small" fullWidth>
                      <InputLabel>Action</InputLabel>
                      <Select label="Action" value={am.flood?.action || 'timeout'}
                        onChange={(e) => setAm('flood', { action: e.target.value })}>
                        {CF_ACTIONS.map((a) => <MenuItem key={a} value={a}>{a}</MenuItem>)}
                      </Select>
                    </FormControl>
                  </Grid>
                  {(am.flood?.action || 'timeout') === 'timeout' && (
                    <Grid item xs={6} sm={3}>
                      <TextField type="number" size="small" fullWidth label="Timeout (minutes)"
                        value={am.flood?.timeout_minutes ?? 10} inputProps={{ min: 1, max: 1000 }}
                        onChange={(e) => setAm('flood', { timeout_minutes: Number(e.target.value) })} />
                    </Grid>
                  )}
                </Grid>
              )}
          </GuildizerCollapsibleCard>

          {/* 2 ── Bot Protection ───────────────────────────────────────────── */}
          <GuildizerCollapsibleCard id="gz.moderation.bot_protection" title="🛡️ Bot Protection" sx={{ mb: 2 }}>
              <Typography variant="body2" color="text.secondary" mb={2}>
                Guards against unknown bots being added to your server. New bots can be kicked
                on join or simply flagged to admins — the alert message has a one-click Trust button.
              </Typography>
              <FormControlLabel
                control={<Switch checked={!!cfg.bot_policy?.enabled} onChange={(e) => setBp({ enabled: e.target.checked })} />}
                label="Enable bot protection"
              />
              <FormControl fullWidth size="small" sx={{ mt: 2 }}>
                <InputLabel>When an untrusted bot joins</InputLabel>
                <Select label="When an untrusted bot joins"
                  value={cfg.bot_policy?.policy || 'kick_untrusted'} onChange={(e) => setBp({ policy: e.target.value })}>
                  <MenuItem value="kick_untrusted">Kick it and alert admins</MenuItem>
                  <MenuItem value="alert_only">Alert admins only</MenuItem>
                </Select>
              </FormControl>
              {channelSelect('Alert channel', cfg.bot_policy?.alert_channel_id, (v) => setBp({ alert_channel_id: v }))}

              <Divider sx={{ my: 2 }} />
              <Typography variant="subtitle2" fontWeight={600} mb={1}>Trusted bots</Typography>
              <Typography variant="body2" color="text.secondary" mb={1}>
                These bots are never restricted. Comma-separated Discord user IDs.
              </Typography>
              <TextField size="small" fullWidth label="Trusted bot IDs" placeholder="123456789, 987654321"
                value={(cfg.bot_policy?.trusted_bot_ids || []).join(', ')}
                onChange={(e) => setBp({ trusted_bot_ids: e.target.value.split(',').map((s) => s.trim()).filter(Boolean) })} />
          </GuildizerCollapsibleCard>

          {/* 3 ── Raid Mode + Emergency lockdown ───────────────────────────── */}
          <GuildizerCollapsibleCard id="gz.moderation.raid_mode" title="🚨 Raid Mode" sx={{ mb: 2 }}>
              <Typography variant="body2" color="text.secondary" mb={2}>
                Detects <b>coordinated</b> spam — many distinct accounts tripping the filters or
                posting identical text in a short burst. It does <b>not</b> lock on raw join rate.
                Members who join during a raid are auto-restricted until it settles.
              </Typography>
              <FormControlLabel
                control={<Switch checked={!!cfg.rg_enabled} onChange={(e) => set({ rg_enabled: e.target.checked })} />}
                label="Enable raid mode"
              />
              <Grid container spacing={2} sx={{ mt: 0.5 }}>
                <Grid item xs={12} sm={6}>{num('Violators to trigger', 'rg_trigger_violators', 2, 50)}</Grid>
                <Grid item xs={12} sm={6}>{num('Duplicate-flood threshold', 'rg_duplicate_threshold', 2, 50)}</Grid>
                <Grid item xs={12} sm={6}>{num('Detection window (seconds)', 'rg_window_seconds', 10, 600)}</Grid>
                <Grid item xs={12} sm={6}>{num('Lockdown duration (minutes)', 'rg_lockdown_minutes', 1, 1440)}</Grid>
              </Grid>
              <FormControl fullWidth size="small" sx={{ mt: 2 }}>
                <InputLabel>Lockdown action for joiners</InputLabel>
                <Select label="Lockdown action for joiners"
                  value={cfg.rg_lockdown_action} onChange={(e) => set({ rg_lockdown_action: e.target.value })}>
                  {RG_ACTIONS.map((a) => <MenuItem key={a} value={a}>{a}</MenuItem>)}
                </Select>
              </FormControl>
              <FormControlLabel sx={{ mt: 1 }}
                control={<Switch checked={!!cfg.rg_notify} onChange={(e) => set({ rg_notify: e.target.checked })} />}
                label="Announce when raid mode activates"
              />
              {channelSelect('Announce in channel', cfg.rg_notify_channel_id, (v) => set({ rg_notify_channel_id: v }))}

              <Divider sx={{ my: 2 }} />
              <Typography variant="subtitle2" fontWeight={600} mb={1}>Emergency lockdown</Typography>
              {cfg.manual_lockdown_active ? (
                <Alert severity="warning" sx={{ alignItems: 'center' }}
                  action={<Button color="inherit" size="small" onClick={() => lockdown(0)}>Lift now</Button>}>
                  🔒 Locked down until <b>{new Date(cfg.manual_lockdown_until).toLocaleString()}</b> —
                  every new member is being auto-restricted on join.
                </Alert>
              ) : (
                <Box>
                  <Typography variant="body2" color="text.secondary" mb={1}>
                    Instantly restrict every new joiner for a set time — use during an active attack.
                    Works even if raid detection above is off.
                  </Typography>
                  <Stack direction="row" spacing={1}>
                    <Button variant="contained" color="error" onClick={() => lockdown(30)}>Lock 30 min</Button>
                    <Button variant="outlined" color="error" onClick={() => lockdown(120)}>Lock 2 h</Button>
                  </Stack>
                </Box>
              )}
          </GuildizerCollapsibleCard>

          {/* 4 ── Anti-nuke guard (Discord-native extra) ───────────────────── */}
          <GuildizerCollapsibleCard id="gz.moderation.anti_nuke_guard" title="🧨 Anti-Nuke Guard" sx={{ mb: 2 }}>
              <Typography variant="body2" color="text.secondary" mb={2}>
                Contains a compromised admin account. Counts destructive actions per admin from the
                audit log; crossing a threshold inside the window triggers the response below. Needs
                the View Audit Log permission. 0 disables a threshold.
              </Typography>
              <FormControlLabel
                control={<Switch checked={!!cfg.anti_nuke?.enabled} onChange={(e) => setAn({ enabled: e.target.checked })} />}
                label="Contain a compromised admin account"
              />
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
              <FormControl fullWidth size="small" sx={{ mt: 2 }}>
                <InputLabel>Response when triggered</InputLabel>
                <Select label="Response when triggered"
                  value={cfg.anti_nuke?.action || 'strip_roles'} onChange={(e) => setAn({ action: e.target.value })}>
                  <MenuItem value="strip_roles">Strip their elevated roles</MenuItem>
                  <MenuItem value="ban">Ban them</MenuItem>
                  <MenuItem value="alert_only">Alert admins only</MenuItem>
                </Select>
              </FormControl>
              {channelSelect('Alert channel', cfg.anti_nuke?.alert_channel_id, (v) => setAn({ alert_channel_id: v }))}
              <TextField size="small" margin="dense" fullWidth label="Whitelisted admin IDs"
                placeholder="123456789, 987654321"
                value={(cfg.anti_nuke?.whitelist_user_ids || []).join(', ')}
                onChange={(e) => setAn({ whitelist_user_ids: e.target.value.split(',').map((s) => s.trim()).filter(Boolean) })}
                helperText="Comma-separated user IDs the guard never acts on. The server owner and the bot are always exempt." />
          </GuildizerCollapsibleCard>

          {/* 5 ── Protection Activity feed ─────────────────────────────────── */}
          <GuildizerCollapsibleCard
            id="gz.moderation.protection_activity"
            title="📋 Protection Activity"
            sx={{ mb: 2 }}
            action={(
              <Button size="small" onClick={loadEvents} disabled={eventsLoading}>
                {eventsLoading ? 'Refreshing…' : 'Refresh'}
              </Button>
            )}
          >
              <Typography variant="body2" color="text.secondary" mb={2}>
                What the bot did at <b>join time</b> and during raids — restricting/banning bots,
                locking down raids and containing nukes. These never appear in the normal moderation log.
              </Typography>
              {events.length === 0 ? (
                <Typography variant="body2" color="text.disabled">
                  {eventsLoading ? 'Loading…' : 'No protection events yet.'}
                </Typography>
              ) : (
                <Box sx={{ display: 'flex', flexDirection: 'column' }}>
                  {events.map((e) => (
                    <Box key={e.id} sx={{ display: 'flex', alignItems: 'flex-start', gap: 1, py: 0.75, borderBottom: '1px solid', borderColor: 'divider' }}>
                      <Chip size="small" label={CAT_LABEL[e.category] || e.category} color={CAT_COLOR[e.category] || 'default'} variant="outlined" sx={{ mt: 0.25 }} />
                      <Box sx={{ flexGrow: 1, minWidth: 0 }}>
                        <Typography variant="body2" fontWeight={600} noWrap>
                          {e.action}{e.username ? ` — ${e.username}` : ''}
                        </Typography>
                        {e.detail && (
                          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', wordBreak: 'break-word' }}>
                            {e.detail}
                          </Typography>
                        )}
                      </Box>
                      <Typography variant="caption" color="text.disabled" sx={{ whiteSpace: 'nowrap' }}>
                        {new Date(e.created_at).toLocaleString()}
                      </Typography>
                    </Box>
                  ))}
                </Box>
              )}
          </GuildizerCollapsibleCard>

          {/* 6 ── Smart Moderation — 3-layer system (Pro) ─────────────────── */}
          <GuildizerCollapsibleCard id="gz.moderation.smart_moderation" title="Smart Moderation" badge={<ProBadge />} sx={{ mt: 2, mb: 2 }}>
              <Box sx={{ mb: 1 }}>
                <Chip
                  label={am.smart_mod?.ai_enabled ? 'AI Active' : 'Rule-based · AI optional'}
                  size="small"
                  color={am.smart_mod?.ai_enabled ? 'primary' : 'default'}
                  variant="outlined"
                />
              </Box>
              <Typography variant="body2" color="text.secondary" mb={2}>
                Three-layer system: fast rules → obfuscated-URL detection → optional AI relevance
                check. Layers 1 &amp; 2 run with no AI cost; Layer 3 runs only when enabled below
                <b> and</b> an AI key is configured on the backend.
              </Typography>
              <FormControlLabel
                control={<Switch checked={!!am.smart_mod?.enabled} onChange={(e) => setAm('smart_mod', { enabled: e.target.checked })} />}
                label="Enable Smart Moderation"
              />
              <TextField fullWidth label="Community topic (helps the AI judge)" sx={{ mt: 2 }}
                placeholder="e.g. CreatorX — creator economy tools"
                value={am.smart_mod?.group_topic || ''} onChange={(e) => setAm('smart_mod', { group_topic: e.target.value })}
                helperText="Describe what this server is about. Used by Layer 3 AI to judge relevance." />

              <Divider sx={{ my: 2 }} />
              <Typography variant="subtitle2" fontWeight={600} mb={1}>Layer 2 — Pattern Detection</Typography>
              <Grid container spacing={1}>
                <Grid item xs={12} sm={6}>
                  <FormControlLabel
                    control={<Switch checked={!!am.smart_mod?.promotional_detection} onChange={(e) => setAm('smart_mod', { promotional_detection: e.target.checked })} />}
                    label="Detect promotional content"
                  />
                  <Typography variant="caption" color="text.secondary" display="block" ml={4}>
                    DM-me spam, referral/promo codes, fake earnings, crypto shilling
                  </Typography>
                </Grid>
                <Grid item xs={12} sm={6}>
                  <FormControlLabel
                    control={<Switch checked={!!am.smart_mod?.hidden_url_detection} onChange={(e) => setAm('smart_mod', { hidden_url_detection: e.target.checked })} />}
                    label="Detect hidden / obfuscated URLs"
                  />
                  <Typography variant="caption" color="text.secondary" display="block" ml={4}>
                    "site dot com", hxxps://, example_com, t . me / x, etc.
                  </Typography>
                </Grid>
                <Grid item xs={12} sm={6}>
                  <FormControlLabel
                    control={<Switch checked={!!am.smart_mod?.allow_referral_codes} onChange={(e) => setAm('smart_mod', { allow_referral_codes: e.target.checked })} />}
                    label="Allow referral codes"
                  />
                  <Typography variant="caption" color="text.secondary" display="block" ml={4}>
                    Exempts bare referral mentions from promotional detection
                  </Typography>
                </Grid>
              </Grid>

              <Divider sx={{ my: 2 }} />
              <Typography variant="subtitle2" fontWeight={600} mb={1}>Layer 3 — AI Relevance Check</Typography>
              <FormControlLabel
                control={<Switch checked={am.smart_mod?.ai_enabled !== false} onChange={(e) => setAm('smart_mod', { ai_enabled: e.target.checked })} />}
                label="AI flags off-topic / unsolicited promotion"
              />
              <Typography variant="caption" color="text.secondary" display="block" ml={4} mb={1}>
                Uses your backend AI key. Only runs after Layers 1 &amp; 2 pass. Skips very short messages.
              </Typography>
              <FormControlLabel
                control={<Switch checked={!!am.image_ai?.enabled} onChange={(e) => setAm('image_ai', { enabled: e.target.checked })} />}
                label="Image AI — remove NSFW images"
              />

              <Divider sx={{ my: 2 }} />
              <Typography variant="subtitle2" fontWeight={600} mb={1}>Action &amp; trusted users</Typography>
              <FormControl fullWidth size="small">
                <InputLabel>Action on a flagged message</InputLabel>
                <Select label="Action on a flagged message"
                  value={am.smart_mod?.action || 'delete'} onChange={(e) => setAm('smart_mod', { action: e.target.value })}>
                  {CF_ACTIONS.map((a) => <MenuItem key={a} value={a}>{a}</MenuItem>)}
                </Select>
              </FormControl>
              <TextField size="small" fullWidth sx={{ mt: 2 }} label="Trusted user IDs (bypass smart moderation)"
                placeholder="123456789, 987654321"
                value={(am.smart_mod?.trusted_user_ids || []).join(', ')}
                onChange={(e) => setAm('smart_mod', { trusted_user_ids: e.target.value.split(',').map((s) => s.trim()).filter(Boolean) })}
                helperText="Comma-separated Discord user IDs whose messages skip all smart-moderation checks." />
          </GuildizerCollapsibleCard>

          {/* 7 ── Extended Rules accordion (Media & Content) ───────────────── */}
          <GuildizerCollapsibleCard id="gz.moderation.extended_rules_media_content" title="Extended Rules — Media &amp; Content" badge={<ProBadge />}>
              {/* Media types — share one action; toggled individually */}
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 1, mb: 1 }}>
                <Typography variant="subtitle2" fontWeight={600}>Media types</Typography>
                <FormControl size="small" sx={{ minWidth: 150 }}>
                  <InputLabel>Action for media</InputLabel>
                  <Select label="Action for media"
                    value={am.media?.action || 'delete'} onChange={(e) => setAm('media', { action: e.target.value })}>
                    {CF_ACTIONS.map((a) => <MenuItem key={a} value={a}>{a}</MenuItem>)}
                  </Select>
                </FormControl>
              </Box>
              <Grid container spacing={1}>
                {[
                  ['Block File / Image Attachments', 'block_attachments'],
                  ['Block Photos', 'block_photos'],
                  ['Block Videos', 'block_videos'],
                  ['Block GIFs / Animations', 'block_gifs'],
                  ['Block Stickers', 'block_stickers'],
                  ['Block Voice Messages', 'block_voice'],
                ].map(([label, key]) => (
                  <Grid item xs={12} sm={6} key={key}>
                    <FormControlLabel
                      control={<Switch checked={!!am.media?.[key]} onChange={(e) => setAm('media', { [key]: e.target.checked })} />}
                      label={label}
                    />
                  </Grid>
                ))}
              </Grid>

              <Divider sx={{ my: 2 }} />
              <Typography variant="subtitle2" fontWeight={600} mb={1}>Content rules</Typography>
              <Typography variant="body2" color="text.secondary" mb={1}>
                Each rule has its own action. Enable a rule to choose what happens.
              </Typography>
              <Grid container spacing={1}>
                {[
                  ['Block Email Addresses', 'email_detection'],
                  ['Block Phone Numbers', 'contact_sharing'],
                  ['Block Spoiler Content', 'spoiler_content'],
                  ['Block Bot Mentions', 'bot_mentions'],
                  ['Block Look-alike / Mixed-script Spoofing', 'homoglyphs'],
                ].map(([label, key]) => {
                  const rule = am[key] || {};
                  return (
                    <Grid item xs={12} key={key}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap', py: 0.5 }}>
                        <FormControlLabel
                          sx={{ minWidth: 240 }}
                          control={<Switch checked={!!rule.enabled} onChange={(e) => setAm(key, { enabled: e.target.checked })} />}
                          label={label}
                        />
                        {rule.enabled && (
                          <FormControl size="small" sx={{ minWidth: 120 }}>
                            <InputLabel>Action</InputLabel>
                            <Select label="Action" value={rule.action || 'delete'}
                              onChange={(e) => setAm(key, { action: e.target.value })}>
                              {CF_ACTIONS.map((a) => <MenuItem key={a} value={a}>{a}</MenuItem>)}
                            </Select>
                          </FormControl>
                        )}
                      </Box>
                    </Grid>
                  );
                })}
              </Grid>
          </GuildizerCollapsibleCard>

          {/* 8 ── Language Filter accordion ────────────────────────────────── */}
          <GuildizerCollapsibleCard id="gz.moderation.language_filter" title="Language Filter" badge={<ProBadge />} sx={{ mt: 1 }}>
              <FormControlLabel
                control={<Switch checked={!!am.language_filter?.enabled} onChange={(e) => setAm('language_filter', { enabled: e.target.checked })} />}
                label="Enable language filter"
              />
              <Typography variant="body2" color="text.secondary" mt={1} mb={1}>Block messages containing these scripts:</Typography>
              <Grid container spacing={1}>
                {SCRIPTS.map(({ value, label }) => {
                  const scripts = am.language_filter?.scripts || [];
                  const checked = scripts.includes(value);
                  return (
                    <Grid item xs={12} sm={6} key={value}>
                      <FormControlLabel
                        control={<Switch checked={checked} onChange={(e) => {
                          const next = e.target.checked ? [...scripts, value] : scripts.filter((s) => s !== value);
                          setAm('language_filter', { scripts: next });
                        }} />}
                        label={label}
                      />
                    </Grid>
                  );
                })}
              </Grid>
          </GuildizerCollapsibleCard>

          {/* 9 ── Emoji Reactions ──────────────────────────────────────────── */}
          <GuildizerCollapsibleCard id="gz.moderation.emoji_reactions" title="Emoji Reactions" sx={{ mt: 2, mb: 2 }}>
              <Typography variant="body2" color="text.secondary" mb={2}>
                The bot reacts to messages to keep the community warm. Admin messages always get 👍.
                Member messages get ❤️ 🔥 😂 👍 🎉 based on tone, with the cooldown below.
              </Typography>
              <FormControlLabel
                control={<Switch checked={!!cfg.emoji_reactions?.enabled} onChange={(e) => setEr({ enabled: e.target.checked })} />}
                label="Enable emoji reactions"
              />
              <Box sx={{ mt: 1, display: 'flex', flexDirection: 'column', gap: 0.5 }}>
                <FormControlLabel
                  control={<Switch checked={!!cfg.emoji_reactions?.admin_thumbs_up} onChange={(e) => setEr({ admin_thumbs_up: e.target.checked })} />}
                  label="👍 Thumbs-up on every admin message"
                />
                <FormControlLabel
                  control={<Switch checked={!!cfg.emoji_reactions?.sentiment_reactions} onChange={(e) => setEr({ sentiment_reactions: e.target.checked })} />}
                  label="React to member messages by sentiment (❤️ 🔥 😂 👍 🎉)"
                />
              </Box>
              <TextField type="number" size="small" margin="dense" fullWidth label="Cooldown per member (minutes)" sx={{ mt: 1 }}
                value={cfg.emoji_reactions?.cooldown_minutes ?? 10} inputProps={{ min: 1, max: 1440 }}
                onChange={(e) => setEr({ cooldown_minutes: Number(e.target.value) })} />
          </GuildizerCollapsibleCard>

          {/* 9b ── Social Replies ──────────────────────────────────────────── */}
          <GuildizerCollapsibleCard id="gz.moderation.social_replies" title="Social Replies" sx={{ mt: 2, mb: 2 }}>
              <Typography variant="body2" color="text.secondary" mb={2}>
                The bot replies warmly when a member says thanks ("that helped!", "you rock").
                No AI cost — friendly canned responses, with a per-member cooldown.
              </Typography>
              <FormControlLabel
                control={<Switch checked={!!cfg.social_replies?.enabled} onChange={(e) => setSr({ enabled: e.target.checked })} />}
                label="Enable social replies"
              />
              {cfg.social_replies?.enabled && (
                <>
                  <Box sx={{ mt: 1, display: 'flex', flexDirection: 'column' }}>
                    <FormControlLabel
                      control={<Switch checked={cfg.social_replies?.reply_to_appreciation !== false} onChange={(e) => setSr({ reply_to_appreciation: e.target.checked })} />}
                      label="Reply with a friendly message"
                    />
                    <FormControlLabel
                      control={<Switch checked={cfg.social_replies?.react_to_appreciation !== false} onChange={(e) => setSr({ react_to_appreciation: e.target.checked })} />}
                      label="Add a 🙏 reaction"
                    />
                  </Box>
                  <Grid container spacing={2} sx={{ mt: 0.5 }}>
                    <Grid item xs={12} sm={6}>
                      <FormControl fullWidth size="small">
                        <InputLabel>Personality</InputLabel>
                        <Select label="Personality" value={cfg.social_replies?.mode || 'friendly'}
                          onChange={(e) => setSr({ mode: e.target.value })}>
                          <MenuItem value="minimal">Minimal</MenuItem>
                          <MenuItem value="professional">Professional</MenuItem>
                          <MenuItem value="friendly">Friendly</MenuItem>
                          <MenuItem value="community_manager">Community manager</MenuItem>
                        </Select>
                      </FormControl>
                    </Grid>
                    <Grid item xs={12} sm={6}>
                      <TextField type="number" size="small" fullWidth label="Cooldown per member (minutes)"
                        value={cfg.social_replies?.cooldown_minutes ?? 5} inputProps={{ min: 1, max: 1440 }}
                        onChange={(e) => setSr({ cooldown_minutes: Number(e.target.value) })} />
                    </Grid>
                  </Grid>
                </>
              )}
          </GuildizerCollapsibleCard>

          {/* 10 ── Command Permissions ─────────────────────────────────────── */}
          <GuildizerCollapsibleCard id="gz.moderation.command_permissions" title="Command Permissions" sx={{ mt: 2 }}>
              <Typography variant="body2" color="text.secondary" mb={2}>
                Control who can use moderation commands. Default is admins only.
              </Typography>
              <FormControlLabel
                sx={{ mb: 1 }}
                control={<Switch checked={!!cfg.command_permissions?.delete_unauthorized} onChange={(e) => setCp({ delete_unauthorized: e.target.checked })} />}
                label="Delete messages that invoke commands the member can't use"
              />
              <Typography variant="caption" color="text.secondary" display="block" mb={2}>
                When a member runs a moderation command they aren't allowed to use, delete their
                message instead of replying in the channel. The attempt is still recorded in the
                activity log. This switch covers text-style command misuse.
              </Typography>
              <Box sx={{ maxWidth: 460 }}>
                {['/warn', '/ban', '/mute', '/kick'].map((cmd) => {
                  const key = cmd.slice(1);
                  const val = (cfg.command_permissions?.per_command || {})[key] || 'admins_only';
                  return (
                    <Box key={cmd} sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 2, py: 0.75, borderBottom: '1px solid', borderColor: 'divider' }}>
                      <Typography fontWeight={600} sx={{ fontFamily: 'monospace', fontSize: '0.9rem', minWidth: 70 }}>{cmd}</Typography>
                      <FormControl size="small" sx={{ minWidth: 160 }}>
                        <Select
                          value={val}
                          onChange={(e) => setCp({ per_command: { ...(cfg.command_permissions?.per_command || {}), [key]: e.target.value } })}
                        >
                          <MenuItem value="admins_only">Admins only</MenuItem>
                          <MenuItem value="everyone">Everyone</MenuItem>
                        </Select>
                      </FormControl>
                    </Box>
                  );
                })}
              </Box>
              <Typography variant="caption" color="text.secondary" display="block" mt={1.5}>
                <b>Admins only</b> (default) keeps the command restricted to staff with the matching
                permission. <b>Everyone</b> lets any member run it. For destructive commands prefer
                Discord's native per-role permissions (Server Settings → Integrations → Guildizer),
                which also control whether the command is visible to members.
              </Typography>
          </GuildizerCollapsibleCard>
        </>
      )}

      {/* ════════════════════════════ BEHAVIOR ════════════════════════════ */}
      {section === 'behavior' && (
        <Grid container spacing={2}>
          <Grid item xs={12}>
            <GuildizerCollapsibleCard id="gz.moderation.warning_thresholds" title="Warning Thresholds">
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
            </GuildizerCollapsibleCard>
          </Grid>

          {/* Warning Escalation sits right after Thresholds to match Telegizer's Behavior order. */}
          <Grid item xs={12}>
            <GuildizerCollapsibleCard id="gz.moderation.warning_escalation" title="Warning Escalation">
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
            </GuildizerCollapsibleCard>
          </Grid>

          <Grid item xs={12}>
            <GuildizerCollapsibleCard id="gz.moderation.auto_clean" title="Auto clean">
              <FormControlLabel control={<Switch checked={!!cfg.auto_clean?.join_messages} onChange={(e) => setAc({ join_messages: e.target.checked })} />} label={'Auto-delete "X joined the server" messages'} />
              <FormControlLabel control={<Switch checked={!!cfg.auto_clean?.boost_messages} onChange={(e) => setAc({ boost_messages: e.target.checked })} />} label={'Auto-delete server-boost messages'} />
              <FormControlLabel control={<Switch checked={!!cfg.auto_clean?.pin_notifications} onChange={(e) => setAc({ pin_notifications: e.target.checked })} />} label={'Auto-delete "X pinned a message" notices'} />
              <TextField type="number" size="small" margin="dense" fullWidth
                label="Delete warning messages after (seconds, 0 = never)"
                value={cfg.auto_clean?.warn_messages_seconds ?? 0} inputProps={{ min: 0, max: 86400 }}
                onChange={(e) => setAc({ warn_messages_seconds: Number(e.target.value) })} />
              <TextField type="number" size="small" margin="dense" fullWidth
                label="Delete mod-action messages after (seconds, 0 = never)"
                value={cfg.auto_clean?.action_messages_seconds ?? 0} inputProps={{ min: 0, max: 86400 }}
                onChange={(e) => setAc({ action_messages_seconds: Number(e.target.value) })} />
            </GuildizerCollapsibleCard>
          </Grid>

          <Grid item xs={12}>
            <GuildizerCollapsibleCard id="gz.moderation.mod_action_log" title="Mod-action log">
              <Typography variant="caption" color="text.secondary" display="block" mb={1}>
                Mirror every moderation action — automod removals plus /warn, /mute, /kick, /ban,
                /tempban, /unban and /purge — into a private channel as an embed.
              </Typography>
              <FormControlLabel
                control={<Switch checked={!!cfg.mod_log?.enabled} onChange={(e) => setMl({ enabled: e.target.checked })} />}
                label="Enable the mod-action log channel"
              />
              {cfg.mod_log?.enabled && channelSelect('Log channel', cfg.mod_log?.channel_id,
                (v) => setMl({ channel_id: v }), '— pick a channel —')}
            </GuildizerCollapsibleCard>
          </Grid>

          <Grid item xs={12}>
            <GuildizerCollapsibleCard id="gz.moderation.critical_alerts" title="Critical alerts">
              <Typography variant="caption" color="text.secondary" display="block" mb={1}>
                One channel for the high-signal safety events, so you don't have to watch the full
                mod-log. Pick which events should ping here.
              </Typography>
              <FormControlLabel
                control={<Switch checked={!!cfg.admin_alerts?.enabled} onChange={(e) => setAa({ enabled: e.target.checked })} />}
                label="Enable a consolidated critical-alerts channel"
              />
              {cfg.admin_alerts?.enabled && (
                <>
                  {channelSelect('Alert channel', cfg.admin_alerts?.channel_id,
                    (v) => setAa({ channel_id: v }), '— pick a channel —')}
                  <Box sx={{ mt: 1, display: 'flex', flexDirection: 'column' }}>
                    {[
                      ['on_ban', 'Bans (automod + manual)'],
                      ['on_raid', 'Raid mode activated'],
                      ['on_nuke', 'Anti-nuke triggered'],
                      ['on_report', 'New member reports'],
                    ].map(([key, label]) => (
                      <FormControlLabel key={key}
                        control={<Switch checked={!!cfg.admin_alerts?.[key]} onChange={(e) => setAa({ [key]: e.target.checked })} />}
                        label={label} />
                    ))}
                  </Box>
                </>
              )}
            </GuildizerCollapsibleCard>
          </Grid>

          <Grid item xs={12}>
            <GuildizerCollapsibleCard id="gz.moderation.recent_warnings" title="Recent warnings">
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
            </GuildizerCollapsibleCard>
          </Grid>
        </Grid>
      )}

      {/* ════════════════════════════ REPORTS ════════════════════════════ */}
      {section === 'reports' && (
        <Grid container spacing={2}>
          <Grid item xs={12}>
            <GuildizerCollapsibleCard id="gz.moderation.reports_settings" title="Reports Settings">
              <Typography variant="caption" color="text.secondary" display="block" mb={1}>
                Members use /report to flag messages or members. Reports land here and (optionally) in a channel.
              </Typography>
              <FormControlLabel
                control={<Switch checked={cfg.reports?.enabled !== false}
                  onChange={(e) => setRp({ enabled: e.target.checked })} />}
                label="Enable the /report command and Report Message action"
              />
              {cfg.reports?.enabled !== false &&
                channelSelect('Alert channel for new reports', cfg.reports?.alert_channel_id,
                  (v) => setRp({ alert_channel_id: v }), '— dashboard only —')}
            </GuildizerCollapsibleCard>
          </Grid>

          <Grid item xs={12}>
            <GuildizerCollapsibleCard id="gz.moderation.open_reports" title={`Open reports (${reports.length})`}>
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
            </GuildizerCollapsibleCard>
          </Grid>
        </Grid>
      )}

      {/* ════════════════════ VERIFICATION (Members tab) ════════════════════ */}
      {section === 'verification' && (
        <Grid container spacing={2}>
          <Grid item xs={12}>
            <GuildizerCollapsibleCard id="gz.members.join_verification_captcha" title="Join verification (captcha)">
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
              <TextField select size="small" margin="dense" fullWidth label="When to verify"
                value={cfg.verification?.verify_on || 'join'} onChange={(e) => setV({ verify_on: e.target.value })}
                helperText="On join gates everyone immediately. On first message lets people lurk, and only challenges them when they first speak.">
                <MenuItem value="join">On join</MenuItem>
                <MenuItem value="first_message">On first message</MenuItem>
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
              <FormControlLabel sx={{ mt: 0.5 }}
                control={<Switch checked={cfg.verification?.auto_delete_on_timeout !== false}
                  onChange={(e) => setV({ auto_delete_on_timeout: e.target.checked })} />}
                label="Auto-delete the challenge message on timeout" />
            </GuildizerCollapsibleCard>
          </Grid>

          <Grid item xs={12}>
            <GuildizerCollapsibleCard id="gz.members.join_gate" title="Join gate">
              {num('Minimum account age (days, 0 = off)', 'jg_min_account_age_days', 0, 365)}
              <Typography variant="caption" color="text.disabled">Newer accounts are kicked on join. Useful during raids.</Typography>
            </GuildizerCollapsibleCard>
          </Grid>
        </Grid>
      )}

      {/* ════════════════ ESCALATION (AI & Integrations tab) ════════════════ */}
      {section === 'escalation' && (
        <Grid container spacing={2}>
          <Grid item xs={12}>
            <GuildizerCollapsibleCard id="gz.moderation.escalation_alerts" title="Escalation alerts">
              <Typography variant="caption" color="text.secondary" display="block" mb={1}>
                Escalation pings your staff when the bot can't handle something on its own — a
                low-confidence /ask answer, an unclear image, a failed automation, or an unknown
                command. Pick where the alerts go, then choose which situations escalate.
              </Typography>
              <TextField select size="small" margin="dense" fullWidth label="Alert channel"
                value={cfg.escalation?.alert_channel_id || ''} onChange={(e) => setEsc({ alert_channel_id: e.target.value || null })}>
                <MenuItem value="">- none -</MenuItem>
                {textChannels.map((c) => <MenuItem key={c.id} value={c.id}># {c.name}</MenuItem>)}
              </TextField>

              <Typography variant="subtitle2" fontWeight={700} mt={2}>Escalate when the bot can't handle it</Typography>
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

              <Typography variant="subtitle2" fontWeight={700} mt={2}>Optional — frustration detection</Typography>
              <Typography variant="caption" color="text.secondary" display="block" mb={0.5}>
                Separately, ping staff when a member's message contains certain words (e.g. they
                sound upset). Leave off if you only want the bot-can't-handle-it alerts above.
              </Typography>
              <FormControlLabel control={<Switch checked={!!cfg.escalation?.enabled} onChange={(e) => setEsc({ enabled: e.target.checked })} />} label="Alert admins when members sound frustrated" />
              {cfg.escalation?.enabled && (
                <TextField size="small" margin="dense" fullWidth label="Trigger keywords"
                  placeholder="refund, scam, not working"
                  value={(cfg.escalation?.keywords || []).join(', ')}
                  onChange={(e) => setEsc({ keywords: e.target.value.split(',').map((k) => k.trim()).filter(Boolean) })}
                  helperText="Comma-separated. One alert per member per 10 minutes." />
              )}
            </GuildizerCollapsibleCard>
          </Grid>
        </Grid>
      )}

      {/* Inline save bar — only when used standalone (no shell sticky Save). */}
      {!sb && (
        <Box sx={{ display: 'flex', justifyContent: 'flex-end', gap: 2, alignItems: 'center', mt: 2 }}>
          {error && <Alert severity="error" sx={{ py: 0 }}>{error}</Alert>}
          <Button variant="contained" onClick={save} disabled={saving || !dirty}>
            {saving ? 'Saving…' : dirty ? 'Save changes' : 'Saved'}
          </Button>
        </Box>
      )}
      {sb && error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}

      <Snackbar open={saved} autoHideDuration={2500} onClose={() => setSaved(false)} message="Saved"
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }} />
    </Box>
  );
}
