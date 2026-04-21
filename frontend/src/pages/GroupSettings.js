import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, AppBar, Toolbar, Typography, IconButton, Tabs, Tab,
  Card, CardContent, Button, TextField, Switch, FormControlLabel,
  Grid, CircularProgress, Chip, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow, Paper, Select, MenuItem,
  FormControl, InputLabel, Pagination, Divider, Accordion,
  AccordionSummary, AccordionDetails, Dialog, DialogTitle,
  DialogContent, DialogActions, Tooltip, Alert,
} from '@mui/material';
import {
  ArrowBack, Save, Add, ExpandMore, Delete, CheckCircle,
} from '@mui/icons-material';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'react-toastify';
import { settings } from '../services/api';
import RaidCreator from '../components/RaidCreator';

function TabPanel({ children, value, index }) {
  return value === index ? <Box sx={{ pt: 3 }}>{children}</Box> : null;
}

const ACTION_COLORS = {
  warn: 'warning', ban: 'error', kick: 'error', mute: 'warning',
  unmute: 'success', unban: 'success', tempban: 'error', tempmute: 'warning', purge: 'info',
};

const AUTOMOD_EXTENDED_RULES = [
  { key: 'contact_sharing', label: 'Block Contact Sharing' },
  { key: 'location_sharing', label: 'Block Location Sharing' },
  { key: 'email_detection', label: 'Block Email Addresses' },
  { key: 'spoiler_content', label: 'Block Spoiler Content' },
  { key: 'voice_notes', label: 'Block Voice Notes' },
  { key: 'video_notes', label: 'Block Video Notes (Circles)' },
  { key: 'file_attachments', label: 'Block File Attachments' },
  { key: 'photos', label: 'Block Photos' },
  { key: 'videos', label: 'Block Videos' },
  { key: 'gifs', label: 'Block GIFs / Animations' },
  { key: 'stickers', label: 'Block Stickers' },
  { key: 'games', label: 'Block Games' },
  { key: 'bot_mentions', label: 'Block Bot Mentions' },
];

const LANGUAGE_OPTIONS = [
  { value: 'cyrillic', label: 'Cyrillic (Russian, Ukrainian…)' },
  { value: 'chinese', label: 'Chinese' },
  { value: 'korean', label: 'Korean' },
  { value: 'arabic', label: 'Arabic' },
  { value: 'hindi', label: 'Hindi' },
  { value: 'japanese', label: 'Japanese' },
];

export default function GroupSettings() {
  const navigate = useNavigate();
  const { id: botId, groupId } = useParams();
  const [tab, setTab] = useState(0);
  const [groupData, setGroupData] = useState(null);
  const [settingsData, setSettingsData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const [members, setMembers] = useState([]);
  const [membersTotal, setMembersTotal] = useState(0);
  const [membersPage, setMembersPage] = useState(1);

  const [auditLogs, setAuditLogs] = useState([]);
  const [auditTotal, setAuditTotal] = useState(0);
  const [auditPage, setAuditPage] = useState(1);

  const [autoResponses, setAutoResponses] = useState([]);
  const [arDialogOpen, setArDialogOpen] = useState(false);
  const [arForm, setArForm] = useState({ trigger_text: '', response_text: '', match_type: 'contains', is_case_sensitive: false });
  const [arSaving, setArSaving] = useState(false);

  const [reports, setReports] = useState([]);
  const [reportsLoading, setReportsLoading] = useState(false);

  const [raidOpen, setRaidOpen] = useState(false);

  const READONLY_TABS = [9, 10]; // Members, Audit Logs

  const fetchSettings = useCallback(async () => {
    try {
      const res = await settings.getGroupSettings(botId, groupId);
      setGroupData(res.data.group);
      setSettingsData(res.data.settings);
    } catch {
      toast.error('Failed to load settings');
      navigate(`/bot/${botId}`);
    } finally {
      setLoading(false);
    }
  }, [botId, groupId, navigate]);

  const fetchMembers = useCallback(async (page = 1) => {
    try {
      const res = await settings.getMembers(botId, groupId, { page, per_page: 20 });
      setMembers(res.data.members);
      setMembersTotal(res.data.pages);
    } catch {
      toast.error('Failed to load members');
    }
  }, [botId, groupId]);

  const fetchAuditLogs = useCallback(async (page = 1) => {
    try {
      const res = await settings.getAuditLogs(botId, groupId, { page, per_page: 20 });
      setAuditLogs(res.data.logs);
      setAuditTotal(res.data.pages);
    } catch {
      toast.error('Failed to load audit logs');
    }
  }, [botId, groupId]);

  const fetchAutoResponses = useCallback(async () => {
    try {
      const res = await settings.getAutoResponses(botId, groupId);
      setAutoResponses(res.data.auto_responses);
    } catch {
      toast.error('Failed to load auto-responses');
    }
  }, [botId, groupId]);

  const fetchReports = useCallback(async () => {
    setReportsLoading(true);
    try {
      const res = await settings.getReports(botId, groupId);
      setReports(res.data.reports);
    } catch {
      toast.error('Failed to load reports');
    } finally {
      setReportsLoading(false);
    }
  }, [botId, groupId]);

  useEffect(() => { fetchSettings(); }, [fetchSettings]);
  useEffect(() => { if (tab === 9) fetchMembers(membersPage); }, [tab, membersPage, fetchMembers]);
  useEffect(() => { if (tab === 10) fetchAuditLogs(auditPage); }, [tab, auditPage, fetchAuditLogs]);
  useEffect(() => { if (tab === 8) fetchAutoResponses(); }, [tab, fetchAutoResponses]);
  useEffect(() => { if (tab === 7) fetchReports(); }, [tab, fetchReports]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await settings.updateGroupSettings(botId, groupId, settingsData);
      toast.success('Settings saved!');
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to save settings');
    } finally {
      setSaving(false);
    }
  };

  const updateSetting = (path, value) => {
    const keys = path.split('.');
    setSettingsData((prev) => {
      const updated = { ...prev };
      let obj = updated;
      for (let i = 0; i < keys.length - 1; i++) {
        obj[keys[i]] = { ...obj[keys[i]] };
        obj = obj[keys[i]];
      }
      obj[keys[keys.length - 1]] = value;
      return updated;
    });
  };

  const handleCreateAutoResponse = async () => {
    if (!arForm.trigger_text || !arForm.response_text) {
      toast.error('Trigger and response are required');
      return;
    }
    setArSaving(true);
    try {
      await settings.createAutoResponse(botId, groupId, arForm);
      toast.success('Auto-response created');
      setArDialogOpen(false);
      setArForm({ trigger_text: '', response_text: '', match_type: 'contains', is_case_sensitive: false });
      fetchAutoResponses();
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to create');
    } finally {
      setArSaving(false);
    }
  };

  const handleDeleteAutoResponse = async (arId) => {
    try {
      await settings.deleteAutoResponse(botId, groupId, arId);
      toast.success('Deleted');
      fetchAutoResponses();
    } catch {
      toast.error('Failed to delete');
    }
  };

  const handleToggleAutoResponse = async (ar) => {
    try {
      await settings.updateAutoResponse(botId, groupId, ar.id, { is_enabled: !ar.is_enabled });
      fetchAutoResponses();
    } catch {
      toast.error('Failed to update');
    }
  };

  const handleResolveReport = async (reportId) => {
    try {
      await settings.resolveReport(botId, groupId, reportId);
      toast.success('Report resolved');
      fetchReports();
    } catch {
      toast.error('Failed to resolve report');
    }
  };

  if (loading || !settingsData) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh' }}>
        <CircularProgress />
      </Box>
    );
  }

  const v = settingsData.verification || {};
  const w = settingsData.welcome || {};
  const l = settingsData.levels || {};
  const am = settingsData.automod || {};
  const mod = settingsData.moderation || {};
  const ac = settingsData.auto_clean || {};
  const rep = settingsData.reports || {};

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <AppBar position="sticky" elevation={0} sx={{ borderBottom: '1px solid', borderColor: 'divider' }}>
        <Toolbar>
          <IconButton edge="start" onClick={() => navigate(`/bot/${botId}`)} sx={{ mr: 1 }}>
            <ArrowBack />
          </IconButton>
          <Typography variant="h6" fontWeight={600} sx={{ flexGrow: 1 }}>
            {groupData?.group_name || 'Group Settings'}
          </Typography>
          <Button
            variant="contained"
            startIcon={saving ? <CircularProgress size={16} color="inherit" /> : <Save />}
            onClick={handleSave}
            disabled={saving || READONLY_TABS.includes(tab)}
          >
            Save
          </Button>
        </Toolbar>
        <Tabs value={tab} onChange={(_, v) => setTab(v)} variant="scrollable" scrollButtons="auto" sx={{ px: 2 }}>
          <Tab label="Verification" />
          <Tab label="Welcome" />
          <Tab label="Levels" />
          <Tab label="AutoMod" />
          <Tab label="Moderation" />
          <Tab label="Auto Clean" />
          <Tab label="Roles" />
          <Tab label="Reports" />
          <Tab label="Auto Response" />
          <Tab label="Members" />
          <Tab label="Audit Logs" />
        </Tabs>
      </AppBar>

      <Box sx={{ maxWidth: 900, mx: 'auto', p: 3 }}>

        {/* ── Verification Tab ── */}
        <TabPanel value={tab} index={0}>
          <Card>
            <CardContent>
              <Typography variant="h6" fontWeight={600} mb={2}>Verification Settings</Typography>
              <FormControlLabel
                control={<Switch checked={!!v.enabled} onChange={(e) => updateSetting('verification.enabled', e.target.checked)} />}
                label="Enable verification for new members"
              />
              <Divider sx={{ my: 2 }} />
              <Grid container spacing={2}>
                <Grid item xs={12} sm={6}>
                  <FormControl fullWidth>
                    <InputLabel>Verification Method</InputLabel>
                    <Select value={v.method || 'button'} label="Verification Method"
                      onChange={(e) => updateSetting('verification.method', e.target.value)}>
                      <MenuItem value="button">Button Click</MenuItem>
                      <MenuItem value="math">Math Captcha</MenuItem>
                      <MenuItem value="word">Word Captcha</MenuItem>
                    </Select>
                  </FormControl>
                </Grid>
                <Grid item xs={12} sm={6}>
                  <TextField fullWidth type="number" label="Timeout (seconds)"
                    value={v.timeout_seconds || 60}
                    onChange={(e) => updateSetting('verification.timeout_seconds', parseInt(e.target.value))} />
                </Grid>
                <Grid item xs={12} sm={6}>
                  <FormControl fullWidth>
                    <InputLabel>On Failure</InputLabel>
                    <Select value={v.kick_on_fail ? 'true' : 'false'} label="On Failure"
                      onChange={(e) => updateSetting('verification.kick_on_fail', e.target.value === 'true')}>
                      <MenuItem value="true">Kick unverified users</MenuItem>
                      <MenuItem value="false">Restrict until verified</MenuItem>
                    </Select>
                  </FormControl>
                </Grid>
              </Grid>
              <Divider sx={{ my: 2 }} />
              <Typography variant="subtitle2" fontWeight={600} mb={1}>Channel Verification</Typography>
              <FormControlLabel
                control={<Switch checked={!!v.channel_verification_enabled}
                  onChange={(e) => updateSetting('verification.channel_verification_enabled', e.target.checked)} />}
                label="Use dedicated verification channel"
              />
              {v.channel_verification_enabled && (
                <TextField fullWidth label="Verification Channel ID" sx={{ mt: 2 }}
                  value={v.verification_channel_id || ''}
                  onChange={(e) => updateSetting('verification.verification_channel_id', e.target.value)}
                  helperText="Telegram channel ID where new members verify" />
              )}
            </CardContent>
          </Card>
        </TabPanel>

        {/* ── Welcome Tab ── */}
        <TabPanel value={tab} index={1}>
          <Card>
            <CardContent>
              <Typography variant="h6" fontWeight={600} mb={2}>Welcome Message</Typography>
              <FormControlLabel
                control={<Switch checked={!!w.enabled} onChange={(e) => updateSetting('welcome.enabled', e.target.checked)} />}
                label="Send welcome message to new members"
              />
              <Divider sx={{ my: 2 }} />
              <FormControlLabel
                control={<Switch checked={!!w.ai_welcome_enabled}
                  onChange={(e) => updateSetting('welcome.ai_welcome_enabled', e.target.checked)} />}
                label="AI-generated welcome messages (requires OpenAI API key)"
              />
              {!w.ai_welcome_enabled && (
                <TextField fullWidth multiline rows={4} label="Welcome Message" sx={{ mt: 2, mb: 2 }}
                  value={w.message || ''}
                  onChange={(e) => updateSetting('welcome.message', e.target.value)}
                  helperText="Placeholders: {first_name}, {group_name}, {member_count}, {username}" />
              )}
              {w.ai_welcome_enabled && (
                <Alert severity="info" sx={{ mt: 2, mb: 2 }}>
                  AI will generate a unique welcome message for each new member. Set OPENAI_API_KEY in your Railway environment.
                </Alert>
              )}
              <Grid container spacing={2}>
                <Grid item xs={12} sm={6}>
                  <TextField fullWidth type="number" label="Auto-delete after (seconds, 0 = never)"
                    value={w.delete_after_seconds || 0}
                    onChange={(e) => updateSetting('welcome.delete_after_seconds', parseInt(e.target.value))} />
                </Grid>
                <Grid item xs={12} sm={6}>
                  <TextField fullWidth type="number" label="Forum Topic ID (leave blank for main chat)"
                    value={w.topic_id || ''}
                    onChange={(e) => updateSetting('welcome.topic_id', e.target.value ? parseInt(e.target.value) : null)}
                    helperText="Send welcome to a specific forum topic thread" />
                </Grid>
                <Grid item xs={12}>
                  <FormControlLabel
                    control={<Switch checked={!!w.show_rules} onChange={(e) => updateSetting('welcome.show_rules', e.target.checked)} />}
                    label="Show rules in welcome message"
                  />
                </Grid>
                {w.show_rules && (
                  <Grid item xs={12}>
                    <TextField fullWidth multiline rows={4} label="Rules Text"
                      value={w.rules_text || ''}
                      onChange={(e) => updateSetting('welcome.rules_text', e.target.value)} />
                  </Grid>
                )}
              </Grid>
            </CardContent>
          </Card>
        </TabPanel>

        {/* ── Levels Tab ── */}
        <TabPanel value={tab} index={2}>
          <Card sx={{ mb: 2 }}>
            <CardContent>
              <Typography variant="h6" fontWeight={600} mb={2}>XP & Level System</Typography>
              <FormControlLabel
                control={<Switch checked={!!l.enabled} onChange={(e) => updateSetting('levels.enabled', e.target.checked)} />}
                label="Enable XP and leveling system"
              />
              <Divider sx={{ my: 2 }} />
              <Grid container spacing={2}>
                <Grid item xs={12} sm={4}>
                  <TextField fullWidth type="number" label="XP per Message"
                    value={l.xp_per_message || 10}
                    onChange={(e) => updateSetting('levels.xp_per_message', parseInt(e.target.value))} />
                </Grid>
                <Grid item xs={12} sm={4}>
                  <TextField fullWidth type="number" label="XP Cooldown (seconds)"
                    value={l.xp_cooldown_seconds || 60}
                    onChange={(e) => updateSetting('levels.xp_cooldown_seconds', parseInt(e.target.value))} />
                </Grid>
                <Grid item xs={12} sm={4}>
                  <TextField fullWidth type="number" label="Level-up Topic ID (blank = main chat)"
                    value={l.levelup_topic_id || ''}
                    onChange={(e) => updateSetting('levels.levelup_topic_id', e.target.value ? parseInt(e.target.value) : null)} />
                </Grid>
                <Grid item xs={12} sm={8}>
                  <TextField fullWidth label="Level-up Message"
                    value={l.level_up_message || ''}
                    onChange={(e) => updateSetting('levels.level_up_message', e.target.value)}
                    helperText="Placeholders: {first_name}, {level}" />
                </Grid>
                <Grid item xs={12} sm={4}>
                  <FormControlLabel
                    control={<Switch checked={!!l.announce_level_up}
                      onChange={(e) => updateSetting('levels.announce_level_up', e.target.checked)} />}
                    label="Announce level-ups"
                    sx={{ mt: 1 }}
                  />
                </Grid>
                <Grid item xs={12}>
                  <FormControlLabel
                    control={<Switch checked={!!l.ai_levelup_enabled}
                      onChange={(e) => updateSetting('levels.ai_levelup_enabled', e.target.checked)} />}
                    label="AI-generated level-up messages (requires OpenAI API key)"
                  />
                </Grid>
              </Grid>
            </CardContent>
          </Card>
          <Card>
            <CardContent>
              <Typography variant="subtitle1" fontWeight={600} mb={2}>Rank Card Style</Typography>
              <Grid container spacing={2} alignItems="center">
                <Grid item xs={12} sm={4}>
                  <Typography variant="body2" color="text.secondary" mb={0.5}>Background Start</Typography>
                  <input type="color"
                    value={(l.rank_card || {}).bg_color_start || '#1a1a2e'}
                    onChange={(e) => updateSetting('levels.rank_card.bg_color_start', e.target.value)}
                    style={{ width: '100%', height: 40, borderRadius: 8, border: '1px solid #30363d', cursor: 'pointer' }} />
                </Grid>
                <Grid item xs={12} sm={4}>
                  <Typography variant="body2" color="text.secondary" mb={0.5}>Background End</Typography>
                  <input type="color"
                    value={(l.rank_card || {}).bg_color_end || '#16213e'}
                    onChange={(e) => updateSetting('levels.rank_card.bg_color_end', e.target.value)}
                    style={{ width: '100%', height: 40, borderRadius: 8, border: '1px solid #30363d', cursor: 'pointer' }} />
                </Grid>
                <Grid item xs={12} sm={4}>
                  <Typography variant="body2" color="text.secondary" mb={0.5}>Accent Color</Typography>
                  <input type="color"
                    value={(l.rank_card || {}).accent_color || '#2196f3'}
                    onChange={(e) => updateSetting('levels.rank_card.accent_color', e.target.value)}
                    style={{ width: '100%', height: 40, borderRadius: 8, border: '1px solid #30363d', cursor: 'pointer' }} />
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </TabPanel>

        {/* ── AutoMod Tab ── */}
        <TabPanel value={tab} index={3}>
          <Card sx={{ mb: 2 }}>
            <CardContent>
              <Typography variant="h6" fontWeight={600} mb={2}>AutoMod</Typography>
              <FormControlLabel
                control={<Switch checked={!!am.enabled} onChange={(e) => updateSetting('automod.enabled', e.target.checked)} />}
                label="Enable AutoMod globally"
              />
              <Divider sx={{ my: 2 }} />
              <Typography variant="subtitle2" fontWeight={600} mb={1}>Core Rules</Typography>
              <Grid container spacing={1}>
                {[
                  ['Spam Detection', 'automod.spam.enabled', !!(am.spam || {}).enabled],
                  ['Bad Words Filter', 'automod.bad_words.enabled', !!(am.bad_words || {}).enabled],
                  ['Block External Links', 'automod.external_links.enabled', !!(am.external_links || {}).enabled],
                  ['Block Telegram Links', 'automod.telegram_links.enabled', !!(am.telegram_links || {}).enabled],
                  ['Excessive Emojis', 'automod.excessive_emojis.enabled', !!(am.excessive_emojis || {}).enabled],
                  ['Caps Lock Filter', 'automod.caps_lock.enabled', !!(am.caps_lock || {}).enabled],
                  ['Block Forwarded Messages', 'automod.forwarded_messages.enabled', !!(am.forwarded_messages || {}).enabled],
                  ['Homoglyph Normalization', 'automod.homoglyphs.enabled', !!(am.homoglyphs || {}).enabled],
                ].map(([label, path, checked]) => (
                  <Grid item xs={12} sm={6} key={path}>
                    <FormControlLabel
                      control={<Switch checked={checked} onChange={(e) => updateSetting(path, e.target.checked)} />}
                      label={label}
                    />
                  </Grid>
                ))}
              </Grid>
              <TextField fullWidth multiline rows={2} label="Banned Words (comma separated)" sx={{ mt: 2 }}
                value={(am.bad_words?.words || []).join(', ')}
                onChange={(e) => updateSetting('automod.bad_words.words', e.target.value.split(',').map(w => w.trim()).filter(Boolean))} />
            </CardContent>
          </Card>

          <Accordion>
            <AccordionSummary expandIcon={<ExpandMore />}>
              <Typography fontWeight={600}>Extended Rules — Media & Content</Typography>
            </AccordionSummary>
            <AccordionDetails>
              <Grid container spacing={1}>
                {AUTOMOD_EXTENDED_RULES.map(({ key, label }) => {
                  const rule = am[key] || {};
                  return (
                    <Grid item xs={12} key={key}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>
                        <FormControlLabel
                          sx={{ minWidth: 280 }}
                          control={<Switch checked={!!rule.enabled}
                            onChange={(e) => updateSetting(`automod.${key}.enabled`, e.target.checked)} />}
                          label={label}
                        />
                        <FormControl size="small" sx={{ minWidth: 120 }}>
                          <InputLabel>Action</InputLabel>
                          <Select value={rule.action || 'delete'} label="Action"
                            onChange={(e) => updateSetting(`automod.${key}.action`, e.target.value)}>
                            <MenuItem value="delete">Delete</MenuItem>
                            <MenuItem value="warn">Warn</MenuItem>
                            <MenuItem value="mute">Mute</MenuItem>
                            <MenuItem value="ban">Ban</MenuItem>
                          </Select>
                        </FormControl>
                        <FormControlLabel
                          control={<Switch checked={!!rule.warn_user}
                            onChange={(e) => updateSetting(`automod.${key}.warn_user`, e.target.checked)} />}
                          label="Warn user"
                        />
                      </Box>
                    </Grid>
                  );
                })}
              </Grid>
            </AccordionDetails>
          </Accordion>

          <Accordion sx={{ mt: 1 }}>
            <AccordionSummary expandIcon={<ExpandMore />}>
              <Typography fontWeight={600}>Language Filter</Typography>
            </AccordionSummary>
            <AccordionDetails>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2, flexWrap: 'wrap' }}>
                <FormControlLabel
                  control={<Switch checked={!!(am.language_filter || {}).enabled}
                    onChange={(e) => updateSetting('automod.language_filter.enabled', e.target.checked)} />}
                  label="Enable language filter"
                />
                <FormControl size="small" sx={{ minWidth: 120 }}>
                  <InputLabel>Action</InputLabel>
                  <Select value={(am.language_filter || {}).action || 'delete'} label="Action"
                    onChange={(e) => updateSetting('automod.language_filter.action', e.target.value)}>
                    <MenuItem value="delete">Delete</MenuItem>
                    <MenuItem value="warn">Warn</MenuItem>
                    <MenuItem value="mute">Mute</MenuItem>
                  </Select>
                </FormControl>
              </Box>
              <Typography variant="body2" color="text.secondary" mb={1}>Block messages containing these scripts:</Typography>
              <Grid container spacing={1}>
                {LANGUAGE_OPTIONS.map(({ value, label }) => {
                  const langs = (am.language_filter || {}).languages || [];
                  const checked = langs.includes(value);
                  return (
                    <Grid item xs={12} sm={6} key={value}>
                      <FormControlLabel
                        control={<Switch checked={checked} onChange={(e) => {
                          const newLangs = e.target.checked ? [...langs, value] : langs.filter(l => l !== value);
                          updateSetting('automod.language_filter.languages', newLangs);
                        }} />}
                        label={label}
                      />
                    </Grid>
                  );
                })}
              </Grid>
            </AccordionDetails>
          </Accordion>
        </TabPanel>

        {/* ── Moderation Tab ── */}
        <TabPanel value={tab} index={4}>
          <Card sx={{ mb: 2 }}>
            <CardContent>
              <Typography variant="h6" fontWeight={600} mb={2}>Moderation Settings</Typography>
              <Grid container spacing={2}>
                <Grid item xs={12} sm={4}>
                  <TextField fullWidth type="number" label="Max Warnings"
                    value={mod.max_warnings || 3}
                    onChange={(e) => updateSetting('moderation.max_warnings', parseInt(e.target.value))} />
                </Grid>
                <Grid item xs={12} sm={4}>
                  <FormControl fullWidth>
                    <InputLabel>Warning Action</InputLabel>
                    <Select value={mod.warning_action || 'ban'} label="Warning Action"
                      onChange={(e) => updateSetting('moderation.warning_action', e.target.value)}>
                      <MenuItem value="ban">Ban</MenuItem>
                      <MenuItem value="kick">Kick</MenuItem>
                      <MenuItem value="mute">Mute</MenuItem>
                    </Select>
                  </FormControl>
                </Grid>
                <Grid item xs={12} sm={4}>
                  <TextField fullWidth type="number" label="Mute Duration (minutes)"
                    value={mod.mute_duration_minutes || 60}
                    onChange={(e) => updateSetting('moderation.mute_duration_minutes', parseInt(e.target.value))} />
                </Grid>
              </Grid>
            </CardContent>
          </Card>

          <Accordion>
            <AccordionSummary expandIcon={<ExpandMore />}>
              <Typography fontWeight={600}>Escalation Chain</Typography>
            </AccordionSummary>
            <AccordionDetails>
              <FormControlLabel
                control={<Switch checked={!!mod.escalation_enabled}
                  onChange={(e) => updateSetting('moderation.escalation_enabled', e.target.checked)} />}
                label="Enable escalating punishments"
              />
              <Typography variant="body2" color="text.secondary" mb={2} mt={1}>
                Instead of a single action, apply progressive punishments as warning count increases.
              </Typography>
              {(mod.escalation_steps || []).map((step, idx) => (
                <Box key={idx} sx={{ display: 'flex', gap: 1, mb: 1, alignItems: 'center', flexWrap: 'wrap' }}>
                  <TextField size="small" type="number" label="At warning #" sx={{ width: 110 }}
                    value={step.at_warning}
                    onChange={(e) => {
                      const steps = [...(mod.escalation_steps || [])];
                      steps[idx] = { ...steps[idx], at_warning: parseInt(e.target.value) };
                      updateSetting('moderation.escalation_steps', steps);
                    }} />
                  <FormControl size="small" sx={{ width: 110 }}>
                    <InputLabel>Action</InputLabel>
                    <Select value={step.action || 'mute'} label="Action"
                      onChange={(e) => {
                        const steps = [...(mod.escalation_steps || [])];
                        steps[idx] = { ...steps[idx], action: e.target.value };
                        updateSetting('moderation.escalation_steps', steps);
                      }}>
                      <MenuItem value="mute">Mute</MenuItem>
                      <MenuItem value="tempban">Temp Ban</MenuItem>
                      <MenuItem value="ban">Ban</MenuItem>
                    </Select>
                  </FormControl>
                  {(step.action === 'mute') && (
                    <TextField size="small" type="number" label="Minutes" sx={{ width: 90 }}
                      value={step.duration_minutes || 60}
                      onChange={(e) => {
                        const steps = [...(mod.escalation_steps || [])];
                        steps[idx] = { ...steps[idx], duration_minutes: parseInt(e.target.value) };
                        updateSetting('moderation.escalation_steps', steps);
                      }} />
                  )}
                  {(step.action === 'tempban') && (
                    <TextField size="small" type="number" label="Hours" sx={{ width: 90 }}
                      value={step.duration_hours || 24}
                      onChange={(e) => {
                        const steps = [...(mod.escalation_steps || [])];
                        steps[idx] = { ...steps[idx], duration_hours: parseInt(e.target.value) };
                        updateSetting('moderation.escalation_steps', steps);
                      }} />
                  )}
                  <IconButton size="small" color="error" onClick={() => {
                    const steps = (mod.escalation_steps || []).filter((_, i) => i !== idx);
                    updateSetting('moderation.escalation_steps', steps);
                  }}>
                    <Delete fontSize="small" />
                  </IconButton>
                </Box>
              ))}
              <Button size="small" startIcon={<Add />} onClick={() => {
                const steps = [...(mod.escalation_steps || [])];
                steps.push({ at_warning: (steps[steps.length - 1]?.at_warning || 1) + 1, action: 'mute', duration_minutes: 60 });
                updateSetting('moderation.escalation_steps', steps);
              }} sx={{ mt: 1 }}>
                Add Step
              </Button>
            </AccordionDetails>
          </Accordion>

          <Card sx={{ mt: 2 }}>
            <CardContent>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                <Typography variant="subtitle1" fontWeight={600}>Raid Manager</Typography>
                <Button variant="contained" size="small" startIcon={<Add />} onClick={() => setRaidOpen(true)}>
                  Create Raid
                </Button>
              </Box>
              <Typography variant="body2" color="text.secondary">
                Coordinate Twitter/X raids with your community. Members earn XP for participating.
              </Typography>
            </CardContent>
          </Card>
        </TabPanel>

        {/* ── Auto Clean Tab ── */}
        <TabPanel value={tab} index={5}>
          <Card>
            <CardContent>
              <Typography variant="h6" fontWeight={600} mb={1}>Auto Clean</Typography>
              <Typography variant="body2" color="text.secondary" mb={2}>
                Automatically delete Telegram system messages to keep your chat clean.
              </Typography>
              <FormControlLabel
                control={<Switch checked={!!ac.enabled} onChange={(e) => updateSetting('auto_clean.enabled', e.target.checked)} />}
                label="Enable Auto Clean"
              />
              <Divider sx={{ my: 2 }} />
              <Grid container spacing={1}>
                {[
                  ['Delete join notifications', 'auto_clean.delete_joins', ac.delete_joins],
                  ['Delete leave notifications', 'auto_clean.delete_leaves', ac.delete_leaves],
                  ['Delete profile photo changes', 'auto_clean.delete_photo_changes', ac.delete_photo_changes],
                  ['Delete pinned message alerts', 'auto_clean.delete_pinned_messages', ac.delete_pinned_messages],
                  ['Delete forum topic events', 'auto_clean.delete_forum_events', ac.delete_forum_events],
                  ['Delete game score messages', 'auto_clean.delete_game_scores', ac.delete_game_scores],
                  ['Delete voice/video chat events', 'auto_clean.delete_voice_chat_events', ac.delete_voice_chat_events],
                  ['Delete bot command messages', 'auto_clean.delete_commands', ac.delete_commands],
                ].map(([label, path, checked]) => (
                  <Grid item xs={12} sm={6} key={path}>
                    <FormControlLabel
                      control={<Switch checked={!!checked} onChange={(e) => updateSetting(path, e.target.checked)} />}
                      label={label}
                    />
                  </Grid>
                ))}
              </Grid>
            </CardContent>
          </Card>
        </TabPanel>

        {/* ── Roles Tab ── */}
        <TabPanel value={tab} index={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" fontWeight={600} mb={1}>Roles</Typography>
              <Typography variant="body2" color="text.secondary" mb={2}>
                Members are automatically assigned a role when they reach the specified level. Use <code>/roles</code> in Telegram to display the list.
              </Typography>
              <Divider sx={{ mb: 2 }} />
              {(l.roles || []).map((role, idx) => (
                <Box key={idx} sx={{ display: 'flex', gap: 2, mb: 1.5, alignItems: 'center' }}>
                  <TextField size="small" type="number" label="From Level" sx={{ width: 110 }}
                    value={role.level}
                    onChange={(e) => {
                      const roles = [...(l.roles || [])];
                      roles[idx] = { ...roles[idx], level: parseInt(e.target.value) };
                      updateSetting('levels.roles', roles);
                    }} />
                  <TextField size="small" label="Role Name" sx={{ flexGrow: 1 }}
                    value={role.name}
                    onChange={(e) => {
                      const roles = [...(l.roles || [])];
                      roles[idx] = { ...roles[idx], name: e.target.value };
                      updateSetting('levels.roles', roles);
                    }} />
                  <IconButton size="small" color="error" onClick={() => {
                    const roles = (l.roles || []).filter((_, i) => i !== idx);
                    updateSetting('levels.roles', roles);
                  }}>
                    <Delete fontSize="small" />
                  </IconButton>
                </Box>
              ))}
              <Button size="small" startIcon={<Add />} sx={{ mt: 1 }} onClick={() => {
                const roles = [...(l.roles || [])];
                const maxLevel = roles.reduce((m, r) => Math.max(m, r.level), 0);
                roles.push({ level: maxLevel + 10, name: 'New Role' });
                updateSetting('levels.roles', roles);
              }}>
                Add Role
              </Button>
            </CardContent>
          </Card>
        </TabPanel>

        {/* ── Reports Tab ── */}
        <TabPanel value={tab} index={7}>
          <Card sx={{ mb: 2 }}>
            <CardContent>
              <Typography variant="h6" fontWeight={600} mb={2}>Reports Settings</Typography>
              <FormControlLabel
                control={<Switch checked={!!rep.enabled} onChange={(e) => updateSetting('reports.enabled', e.target.checked)} />}
                label="Enable /report command"
              />
              <Grid container spacing={2} sx={{ mt: 1 }}>
                <Grid item xs={12} sm={6}>
                  <FormControl fullWidth>
                    <InputLabel>Notify Admins</InputLabel>
                    <Select value={rep.notify_admins || 'all'} label="Notify Admins"
                      onChange={(e) => updateSetting('reports.notify_admins', e.target.value)}>
                      <MenuItem value="all">All admins</MenuItem>
                      <MenuItem value="selected">Selected admins only</MenuItem>
                    </Select>
                  </FormControl>
                </Grid>
              </Grid>
            </CardContent>
          </Card>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                <Typography variant="subtitle1" fontWeight={600}>Reported Messages</Typography>
                <Button size="small" onClick={fetchReports} disabled={reportsLoading}>Refresh</Button>
              </Box>
              {reportsLoading ? <CircularProgress size={24} /> : (
                reports.length === 0 ? (
                  <Typography color="text.secondary">No reports yet.</Typography>
                ) : (
                  <TableContainer>
                    <Table size="small">
                      <TableHead>
                        <TableRow>
                          <TableCell>Reporter</TableCell>
                          <TableCell>Reported User</TableCell>
                          <TableCell>Reason</TableCell>
                          <TableCell>Status</TableCell>
                          <TableCell>Date</TableCell>
                          <TableCell>Action</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {reports.map((r) => (
                          <TableRow key={r.id} hover>
                            <TableCell>@{r.reporter_username || r.reporter_user_id}</TableCell>
                            <TableCell>@{r.reported_username || r.reported_user_id}</TableCell>
                            <TableCell>{r.reason || '-'}</TableCell>
                            <TableCell>
                              <Chip label={r.status} size="small"
                                color={r.status === 'open' ? 'warning' : 'success'} />
                            </TableCell>
                            <TableCell>
                              <Typography variant="caption">{new Date(r.created_at).toLocaleDateString()}</Typography>
                            </TableCell>
                            <TableCell>
                              {r.status === 'open' && (
                                <Tooltip title="Mark resolved">
                                  <IconButton size="small" color="success"
                                    onClick={() => handleResolveReport(r.id)}>
                                    <CheckCircle fontSize="small" />
                                  </IconButton>
                                </Tooltip>
                              )}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </TableContainer>
                )
              )}
            </CardContent>
          </Card>
        </TabPanel>

        {/* ── Auto Response Tab ── */}
        <TabPanel value={tab} index={8}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                <Box>
                  <Typography variant="h6" fontWeight={600}>Auto Response Triggers</Typography>
                  <Typography variant="body2" color="text.secondary">
                    Bot auto-replies when a message matches a trigger keyword.
                  </Typography>
                </Box>
                <Button variant="contained" startIcon={<Add />} onClick={() => setArDialogOpen(true)}>
                  Add Trigger
                </Button>
              </Box>
              {autoResponses.length === 0 ? (
                <Typography color="text.secondary">No triggers configured yet.</Typography>
              ) : (
                <TableContainer>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Trigger</TableCell>
                        <TableCell>Response</TableCell>
                        <TableCell>Match</TableCell>
                        <TableCell>Enabled</TableCell>
                        <TableCell>Actions</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {autoResponses.map((ar) => (
                        <TableRow key={ar.id} hover>
                          <TableCell><code>{ar.trigger_text}</code></TableCell>
                          <TableCell sx={{ maxWidth: 200 }}>
                            <Typography variant="body2" noWrap>{ar.response_text}</Typography>
                          </TableCell>
                          <TableCell><Chip label={ar.match_type} size="small" /></TableCell>
                          <TableCell>
                            <Switch size="small" checked={ar.is_enabled}
                              onChange={() => handleToggleAutoResponse(ar)} />
                          </TableCell>
                          <TableCell>
                            <IconButton size="small" color="error"
                              onClick={() => handleDeleteAutoResponse(ar.id)}>
                              <Delete fontSize="small" />
                            </IconButton>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              )}
            </CardContent>
          </Card>
        </TabPanel>

        {/* ── Members Tab ── */}
        <TabPanel value={tab} index={9}>
          <TableContainer component={Paper} sx={{ border: '1px solid', borderColor: 'divider' }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>User</TableCell>
                  <TableCell align="right">XP</TableCell>
                  <TableCell align="right">Level</TableCell>
                  <TableCell align="right">Warnings</TableCell>
                  <TableCell>Role</TableCell>
                  <TableCell>Status</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {members.map((m) => (
                  <TableRow key={m.id} hover>
                    <TableCell>
                      <Typography variant="body2" fontWeight={500}>
                        {m.first_name}{m.username ? ` (@${m.username})` : ''}
                      </Typography>
                    </TableCell>
                    <TableCell align="right">{m.xp.toLocaleString()}</TableCell>
                    <TableCell align="right">{m.level}</TableCell>
                    <TableCell align="right">{m.warnings}</TableCell>
                    <TableCell><Chip label={m.role} size="small" variant="outlined" /></TableCell>
                    <TableCell>
                      {m.is_verified
                        ? <Chip label="Verified" color="success" size="small" />
                        : <Chip label="Unverified" color="default" size="small" />}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
          {membersTotal > 1 && (
            <Box sx={{ display: 'flex', justifyContent: 'center', mt: 2 }}>
              <Pagination count={membersTotal} page={membersPage}
                onChange={(_, p) => setMembersPage(p)} color="primary" />
            </Box>
          )}
        </TabPanel>

        {/* ── Audit Logs Tab ── */}
        <TabPanel value={tab} index={10}>
          <TableContainer component={Paper} sx={{ border: '1px solid', borderColor: 'divider' }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Action</TableCell>
                  <TableCell>Target</TableCell>
                  <TableCell>Moderator</TableCell>
                  <TableCell>Reason</TableCell>
                  <TableCell>Time</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {auditLogs.map((log) => (
                  <TableRow key={log.id} hover>
                    <TableCell>
                      <Chip label={log.action_type} color={ACTION_COLORS[log.action_type] || 'default'} size="small" />
                    </TableCell>
                    <TableCell><Typography variant="body2">{log.target_username || log.target_user_id}</Typography></TableCell>
                    <TableCell><Typography variant="body2">{log.moderator_username || log.moderator_id}</Typography></TableCell>
                    <TableCell><Typography variant="body2" color="text.secondary">{log.reason || '-'}</Typography></TableCell>
                    <TableCell>
                      <Typography variant="caption" color="text.secondary">
                        {new Date(log.timestamp).toLocaleString()}
                      </Typography>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
          {auditTotal > 1 && (
            <Box sx={{ display: 'flex', justifyContent: 'center', mt: 2 }}>
              <Pagination count={auditTotal} page={auditPage}
                onChange={(_, p) => setAuditPage(p)} color="primary" />
            </Box>
          )}
        </TabPanel>
      </Box>

      {/* ── Add Auto-Response Dialog ── */}
      <Dialog open={arDialogOpen} onClose={() => setArDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Add Auto-Response Trigger</DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: 2 }}>
          <TextField label="Trigger Text" fullWidth value={arForm.trigger_text}
            onChange={(e) => setArForm({ ...arForm, trigger_text: e.target.value })}
            helperText="The keyword or phrase that triggers the response" />
          <TextField label="Response Text" fullWidth multiline rows={3} value={arForm.response_text}
            onChange={(e) => setArForm({ ...arForm, response_text: e.target.value })} />
          <FormControl fullWidth>
            <InputLabel>Match Type</InputLabel>
            <Select value={arForm.match_type} label="Match Type"
              onChange={(e) => setArForm({ ...arForm, match_type: e.target.value })}>
              <MenuItem value="contains">Contains</MenuItem>
              <MenuItem value="exact">Exact Match</MenuItem>
              <MenuItem value="starts_with">Starts With</MenuItem>
            </Select>
          </FormControl>
          <FormControlLabel
            control={<Switch checked={arForm.is_case_sensitive}
              onChange={(e) => setArForm({ ...arForm, is_case_sensitive: e.target.checked })} />}
            label="Case sensitive"
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setArDialogOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={handleCreateAutoResponse} disabled={arSaving}>
            {arSaving ? <CircularProgress size={20} /> : 'Create'}
          </Button>
        </DialogActions>
      </Dialog>

      <RaidCreator open={raidOpen} onClose={() => setRaidOpen(false)} botId={botId} groupId={groupId} />
    </Box>
  );
}
