import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, AppBar, Toolbar, Typography, IconButton, Tabs, Tab,
  Card, CardContent, Button, TextField, Switch, FormControlLabel,
  Grid, CircularProgress, Chip, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow, Paper, Select, MenuItem,
  FormControl, InputLabel, Pagination, Divider, Accordion,
  AccordionSummary, AccordionDetails, Dialog, DialogTitle,
  DialogContent, DialogActions, Tooltip, Alert, Stack,
} from '@mui/material';
import {
  ArrowBack, Save, Add, ExpandMore, Delete, CheckCircle, Schedule,
  Send, Assessment, Shield, Group, AutoAwesome, BarChart, People, Bolt,
} from '@mui/icons-material';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'react-toastify';
import { settings, digest as digestApi } from '../services/api';
import RaidCreator from '../components/RaidCreator';
import ScheduledMessages from '../components/ScheduledMessages';
import KnowledgeBase from '../components/KnowledgeBase';
import PollCreator from '../components/PollCreator';
import WebhookManager from '../components/WebhookManager';
import InviteLinks from '../components/InviteLinks';
import TimezoneSelect from '../components/TimezoneSelect';

const CATEGORIES = [
  { id: 'moderation', label: 'Moderation', icon: Shield, subTabs: ['AutoMod', 'Behavior', 'Reports'] },
  { id: 'members',    label: 'Members',    icon: Group,  subTabs: ['Verification', 'Welcome', 'XP & Roles'] },
  { id: 'automation', label: 'Automation', icon: Bolt,   subTabs: ['Scheduler', 'Auto Reply', 'Polls'] },
  { id: 'community',  label: 'Community',  icon: People, subTabs: ['Raids', 'Invite Links'] },
  { id: 'ai',         label: 'AI & Integrations', icon: AutoAwesome, subTabs: ['Knowledge Base', 'Webhooks'] },
  { id: 'analytics',  label: 'Analytics',  icon: BarChart, subTabs: ['Members', 'Audit Log', 'Digest'] },
];

function ProBadge() {
  return <Chip label="Pro" color="primary" size="small" sx={{ ml: 1, height: 18, fontSize: '0.65rem', fontWeight: 700 }} />;
}

function EntBadge() {
  return <Chip label="Enterprise" color="secondary" size="small" sx={{ ml: 1, height: 18, fontSize: '0.65rem', fontWeight: 700 }} />;
}

function DefaultTimezoneCard({ value, onChange }) {
  return (
    <Card sx={{ mb: 2 }}>
      <CardContent>
        <Typography variant="subtitle1" fontWeight={600} mb={0.5}>Group Default Timezone</Typography>
        <Typography variant="body2" color="text.secondary" mb={2}>
          Saved per this group. All new scheduled items in this group use it automatically.
          You can still override the timezone per individual item.
        </Typography>
        <Grid container spacing={2} alignItems="center">
          <Grid item xs={12} sm={6}>
            <TimezoneSelect value={value} onChange={onChange} label="Default Timezone" size="medium" />
          </Grid>
          <Grid item xs={12} sm={6}>
            <Typography variant="caption" color="text.secondary">
              Current time in this timezone:{' '}
              <strong>
                {new Date().toLocaleString('en-GB', {
                  timeZone: value || 'UTC',
                  year: 'numeric', month: '2-digit', day: '2-digit',
                  hour: '2-digit', minute: '2-digit', second: '2-digit',
                  hour12: false,
                })}
              </strong>
            </Typography>
          </Grid>
        </Grid>
      </CardContent>
    </Card>
  );
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
  const [cat, setCat] = useState('moderation');
  const [subTab, setSubTab] = useState(0);
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

  const [digestConfig, setDigestConfig] = useState({ daily: false, weekly: false, monthly: false });
  const [digestLoading, setDigestLoading] = useState(false);
  const [digestSaving, setDigestSaving] = useState(false);
  const [digestSending, setDigestSending] = useState('');

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

  const fetchDigest = useCallback(async () => {
    setDigestLoading(true);
    try {
      const res = await digestApi.get(botId, groupId);
      setDigestConfig(res.data.digest);
    } catch {
      // digest not yet configured — use defaults
    } finally {
      setDigestLoading(false);
    }
  }, [botId, groupId]);

  const handleSaveDigest = async () => {
    setDigestSaving(true);
    try {
      await digestApi.update(botId, groupId, digestConfig);
      toast.success('Digest settings saved!');
    } catch {
      toast.error('Failed to save digest settings');
    } finally {
      setDigestSaving(false);
    }
  };

  const handleSendNow = async (period) => {
    setDigestSending(period);
    try {
      await digestApi.sendNow(botId, groupId, { period });
      toast.success(`${period.charAt(0).toUpperCase() + period.slice(1)} report sent to the group!`);
      fetchDigest();
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to send report');
    } finally {
      setDigestSending('');
    }
  };

  useEffect(() => { fetchSettings(); }, [fetchSettings]);
  useEffect(() => { if (cat === 'analytics' && subTab === 0) fetchMembers(membersPage); }, [cat, subTab, membersPage, fetchMembers]);
  useEffect(() => { if (cat === 'analytics' && subTab === 1) fetchAuditLogs(auditPage); }, [cat, subTab, auditPage, fetchAuditLogs]);
  useEffect(() => { if (cat === 'automation' && subTab === 1) fetchAutoResponses(); }, [cat, subTab, fetchAutoResponses]);
  useEffect(() => { if (cat === 'moderation' && subTab === 2) fetchReports(); }, [cat, subTab, fetchReports]);
  useEffect(() => { if (cat === 'analytics' && subTab === 2) fetchDigest(); }, [cat, subTab, fetchDigest]);

  const [upgradeModalOpen, setUpgradeModalOpen] = useState(false);
  const [upgradeFeature, setUpgradeFeature] = useState('');

  const handleSave = async () => {
    setSaving(true);
    try {
      await settings.updateGroupSettings(botId, groupId, settingsData);
      toast.success('Settings saved!');
    } catch (err) {
      if (err.response?.status === 403 && err.response?.data?.code === 'FEATURE_REQUIRES_PRO') {
        setUpgradeFeature(err.response.data.feature || 'This feature');
        setUpgradeModalOpen(true);
      } else {
        toast.error(err.response?.data?.error || 'Failed to save settings');
      }
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

  const handleCatChange = (newCat) => {
    setCat(newCat);
    setSubTab(0);
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

  const currentCat = CATEGORIES.find((c) => c.id === cat);

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>

      {/* Upgrade required modal */}
      <Dialog open={upgradeModalOpen} onClose={() => setUpgradeModalOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ fontWeight: 700 }}>Pro Feature Required</DialogTitle>
        <DialogContent>
          <Typography variant="body2" gutterBottom>
            <strong>{upgradeFeature}</strong> is available on the Pro and Enterprise plans.
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Upgrade to unlock advanced moderation, scheduled content, analytics, AI knowledge base, and more.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setUpgradeModalOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={() => { setUpgradeModalOpen(false); navigate('/pricing'); }}>
            View Plans
          </Button>
        </DialogActions>
      </Dialog>

      <AppBar position="sticky" elevation={0} sx={{ borderBottom: '1px solid', borderColor: 'divider' }}>
        <Toolbar>
          <IconButton edge="start" onClick={() => navigate(`/bot/${botId}`)} sx={{ mr: 1 }}>
            <ArrowBack />
          </IconButton>
          <Typography variant="h6" fontWeight={600} sx={{ flexGrow: 1 }}>
            {groupData?.group_name || 'Group Settings'}
          </Typography>
          {settingsData && (
            <Tooltip title="Group default timezone — change it in Automation › Scheduler">
              <Chip
                icon={<Schedule sx={{ fontSize: 14 }} />}
                label={settingsData.timezone || 'UTC'}
                size="small"
                variant="outlined"
                sx={{ mr: 1.5, fontSize: 11, color: 'inherit', borderColor: 'rgba(255,255,255,0.4)', cursor: 'default' }}
              />
            </Tooltip>
          )}
          <Button
            variant="contained"
            startIcon={saving ? <CircularProgress size={16} color="inherit" /> : <Save />}
            onClick={handleSave}
            disabled={saving || cat === 'analytics'}
          >
            Save
          </Button>
        </Toolbar>

        {/* Category pill nav — fade gradient on right edge signals horizontal scroll */}
        <Box sx={{ position: 'relative' }}>
          <Box sx={{
            position: 'absolute', right: 0, top: 0, bottom: 0, width: 32, zIndex: 1, pointerEvents: 'none',
            background: 'linear-gradient(to right, transparent, rgba(22,27,34,0.95))',
            display: { xs: 'block', md: 'none' },
          }} />
        <Box sx={{
          display: 'flex', gap: 0.75, px: 2, py: 1.25, overflowX: 'auto',
          '::-webkit-scrollbar': { display: 'none' },
          scrollBehavior: 'smooth',
          WebkitOverflowScrolling: 'touch',
        }}>
          {CATEGORIES.map(({ id, label, icon: Icon }) => {
            const active = cat === id;
            return (
              <Box
                key={id}
                onClick={() => handleCatChange(id)}
                sx={{
                  display: 'flex', alignItems: 'center', gap: 0.75,
                  px: 1.5, py: 0.6, borderRadius: 2, cursor: 'pointer',
                  whiteSpace: 'nowrap', userSelect: 'none',
                  bgcolor: active ? 'primary.main' : 'rgba(255,255,255,0.05)',
                  color: active ? 'white' : 'text.secondary',
                  border: '1px solid',
                  borderColor: active ? 'primary.main' : 'rgba(255,255,255,0.12)',
                  transition: 'all 0.15s ease',
                  '&:hover': { bgcolor: active ? 'primary.dark' : 'rgba(255,255,255,0.09)' },
                }}
              >
                <Icon sx={{ fontSize: 15 }} />
                <Typography variant="body2" fontWeight={active ? 700 : 500} fontSize="0.78rem">{label}</Typography>
              </Box>
            );
          })}
        </Box>
        </Box>

        {/* Sub-tab row */}
        {currentCat && currentCat.subTabs.length > 1 && (
          <Tabs
            value={subTab}
            onChange={(_, v) => setSubTab(v)}
            variant="scrollable"
            scrollButtons="auto"
            sx={{ px: 2, minHeight: 38, '& .MuiTab-root': { minHeight: 38, py: 0 } }}
          >
            {currentCat.subTabs.map((label) => (
              <Tab key={label} label={label} sx={{ fontSize: '0.8rem' }} />
            ))}
          </Tabs>
        )}
      </AppBar>

      <Box sx={{ maxWidth: 900, mx: 'auto', p: { xs: 2, md: 3 } }}>

        {/* ══════════════════════════════════════════════════════════
            MODERATION
        ══════════════════════════════════════════════════════════ */}

        {/* MODERATION › AutoMod */}
        {cat === 'moderation' && subTab === 0 && (
          <>
            <Card sx={{ mb: 2 }}>
              <CardContent>
                <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                  <Typography variant="h6" fontWeight={600}>AutoMod</Typography>
                </Box>
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
                <Box sx={{ display: 'flex', alignItems: 'center' }}>
                  <Typography fontWeight={600}>Extended Rules — Media & Content</Typography>
                  <ProBadge />
                </Box>
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
                <Box sx={{ display: 'flex', alignItems: 'center' }}>
                  <Typography fontWeight={600}>Language Filter</Typography>
                  <ProBadge />
                </Box>
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
          </>
        )}

        {/* MODERATION › Behavior */}
        {cat === 'moderation' && subTab === 1 && (
          <>
            <Card sx={{ mb: 2 }}>
              <CardContent>
                <Typography variant="h6" fontWeight={600} mb={2}>Warning Thresholds</Typography>
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
                <Box sx={{ display: 'flex', alignItems: 'center' }}>
                  <Typography fontWeight={600}>Escalation Chain</Typography>
                  <ProBadge />
                </Box>
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
                    {step.action === 'mute' && (
                      <TextField size="small" type="number" label="Minutes" sx={{ width: 90 }}
                        value={step.duration_minutes || 60}
                        onChange={(e) => {
                          const steps = [...(mod.escalation_steps || [])];
                          steps[idx] = { ...steps[idx], duration_minutes: parseInt(e.target.value) };
                          updateSetting('moderation.escalation_steps', steps);
                        }} />
                    )}
                    {step.action === 'tempban' && (
                      <TextField size="small" type="number" label="Hours" sx={{ width: 90 }}
                        value={step.duration_hours || 24}
                        onChange={(e) => {
                          const steps = [...(mod.escalation_steps || [])];
                          steps[idx] = { ...steps[idx], duration_hours: parseInt(e.target.value) };
                          updateSetting('moderation.escalation_steps', steps);
                        }} />
                    )}
                    <TextField size="small" type="number" label="Time Window (hrs)" placeholder="Any" sx={{ width: 130 }}
                      value={step.time_window_hours ?? ''}
                      onChange={(e) => {
                        const steps = [...(mod.escalation_steps || [])];
                        const val = e.target.value === '' ? null : parseInt(e.target.value);
                        steps[idx] = { ...steps[idx], time_window_hours: val };
                        updateSetting('moderation.escalation_steps', steps);
                      }} />
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

            <Card sx={{ mt: 2, mb: 2 }}>
              <CardContent>
                <Typography variant="subtitle1" fontWeight={600} mb={1}>Auto Clean System Messages</Typography>
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

            <Card>
              <CardContent>
                <Typography variant="subtitle1" fontWeight={600} mb={1}>Auto-Delete Notification Messages</Typography>
                <Typography variant="body2" color="text.secondary" mb={2}>
                  How long to keep AutoMod and moderation notification messages before deleting them. 0 = never delete.
                </Typography>
                <Grid container spacing={2}>
                  <Grid item xs={12} sm={6}>
                    <TextField fullWidth type="number" label="Delete Warn Messages After (seconds, 0=never)"
                      inputProps={{ min: 0 }}
                      value={mod.auto_delete_warn_seconds ?? 0}
                      onChange={(e) => updateSetting('moderation.auto_delete_warn_seconds', parseInt(e.target.value) || 0)} />
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <TextField fullWidth type="number" label="Delete Action Messages After (seconds, 0=never)"
                      inputProps={{ min: 0 }}
                      value={mod.auto_delete_action_seconds ?? 0}
                      onChange={(e) => updateSetting('moderation.auto_delete_action_seconds', parseInt(e.target.value) || 0)} />
                  </Grid>
                </Grid>
              </CardContent>
            </Card>
          </>
        )}

        {/* MODERATION › Reports */}
        {cat === 'moderation' && subTab === 2 && (
          <>
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
                                <Typography variant="caption">{r.created_at ? new Date(r.created_at).toLocaleDateString() : '-'}</Typography>
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
          </>
        )}

        {/* ══════════════════════════════════════════════════════════
            MEMBERS
        ══════════════════════════════════════════════════════════ */}

        {/* MEMBERS › Verification */}
        {cat === 'members' && subTab === 0 && (
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
                <Grid item xs={12} sm={6}>
                  <TextField fullWidth type="number" label="Max Verification Attempts"
                    value={v.max_attempts ?? 3}
                    onChange={(e) => updateSetting('verification.max_attempts', parseInt(e.target.value))} />
                </Grid>
                <Grid item xs={12} sm={6}>
                  <FormControl fullWidth>
                    <InputLabel>Trigger Verification</InputLabel>
                    <Select value={v.verify_on || 'join'} label="Trigger Verification"
                      onChange={(e) => updateSetting('verification.verify_on', e.target.value)}>
                      <MenuItem value="join">On Join</MenuItem>
                      <MenuItem value="first_message">On First Message</MenuItem>
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
        )}

        {/* MEMBERS › Welcome */}
        {cat === 'members' && subTab === 1 && (
          <>
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
                  label={<Box sx={{ display: 'flex', alignItems: 'center' }}>AI-generated welcome messages (requires OpenAI API key)<ProBadge /></Box>}
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

            <Card sx={{ mt: 2 }}>
              <CardContent>
                <Typography variant="subtitle1" fontWeight={600} mb={1}>Private Welcome DM</Typography>
                <Typography variant="body2" color="text.secondary" mb={2}>
                  Send a private message to each new member in addition to the group welcome.
                </Typography>
                <FormControlLabel
                  control={<Switch checked={!!w.dm_enabled} onChange={e => updateSetting('welcome.dm_enabled', e.target.checked)} />}
                  label="Send DM to new members"
                />
                {w.dm_enabled && (
                  <TextField fullWidth multiline rows={3} label="DM Message" sx={{ mt: 2 }}
                    value={w.dm_message || ''}
                    onChange={e => updateSetting('welcome.dm_message', e.target.value)}
                    helperText="Placeholders: {first_name}, {group_name}, {username}" />
                )}
              </CardContent>
            </Card>
          </>
        )}

        {/* MEMBERS › XP & Roles */}
        {cat === 'members' && subTab === 2 && (
          <>
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
                      label={<Box sx={{ display: 'flex', alignItems: 'center' }}>AI-generated level-up messages (requires OpenAI API key)<ProBadge /></Box>}
                    />
                  </Grid>
                  <Grid item xs={12} sm={4}>
                    <TextField fullWidth type="number" label="XP per Reaction"
                      value={l.xp_per_reaction ?? 10}
                      onChange={(e) => updateSetting('levels.xp_per_reaction', parseInt(e.target.value))} />
                  </Grid>
                  <Grid item xs={12} sm={4}>
                    <TextField fullWidth type="number" label="Reaction XP Cooldown (s)"
                      value={l.xp_reaction_cooldown_seconds ?? 30}
                      onChange={(e) => updateSetting('levels.xp_reaction_cooldown_seconds', parseInt(e.target.value))} />
                  </Grid>
                  <Grid item xs={12} sm={4}>
                    <TextField fullWidth type="number" label="Delete Level-Up Message After (s, 0=never)"
                      value={l.delete_levelup_after_seconds ?? 0}
                      onChange={(e) => updateSetting('levels.delete_levelup_after_seconds', parseInt(e.target.value))} />
                  </Grid>
                </Grid>
              </CardContent>
            </Card>

            <Card sx={{ mb: 2 }}>
              <CardContent>
                <Typography variant="subtitle1" fontWeight={600} mb={1}>XP Penalties (Moderation Actions)</Typography>
                <Typography variant="body2" color="text.secondary" mb={2}>XP deducted when a moderation action is applied to a member.</Typography>
                <Grid container spacing={2}>
                  <Grid item xs={6} sm={3}>
                    <TextField fullWidth type="number" label="Warn Penalty"
                      value={l.xp_penalty_warn ?? -10}
                      onChange={(e) => updateSetting('levels.xp_penalty_warn', parseInt(e.target.value))} />
                  </Grid>
                  <Grid item xs={6} sm={3}>
                    <TextField fullWidth type="number" label="Mute Penalty"
                      value={l.xp_penalty_mute ?? -20}
                      onChange={(e) => updateSetting('levels.xp_penalty_mute', parseInt(e.target.value))} />
                  </Grid>
                  <Grid item xs={6} sm={3}>
                    <TextField fullWidth type="number" label="Kick Penalty"
                      value={l.xp_penalty_kick ?? -30}
                      onChange={(e) => updateSetting('levels.xp_penalty_kick', parseInt(e.target.value))} />
                  </Grid>
                  <Grid item xs={6} sm={3}>
                    <TextField fullWidth type="number" label="Ban Penalty"
                      value={l.xp_penalty_ban ?? -50}
                      onChange={(e) => updateSetting('levels.xp_penalty_ban', parseInt(e.target.value))} />
                  </Grid>
                </Grid>
              </CardContent>
            </Card>

            <Card sx={{ mb: 2 }}>
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

            <Card>
              <CardContent>
                <Typography variant="subtitle1" fontWeight={600} mb={1}>Roles</Typography>
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
          </>
        )}

        {/* ══════════════════════════════════════════════════════════
            AUTOMATION
        ══════════════════════════════════════════════════════════ */}

        {/* AUTOMATION › Scheduler */}
        {cat === 'automation' && subTab === 0 && (
          <>
            <DefaultTimezoneCard
              value={settingsData?.timezone || 'UTC'}
              onChange={tz => updateSetting('timezone', tz)}
            />
            <ScheduledMessages botId={botId} groupId={groupId} defaultTimezone={settingsData?.timezone || 'UTC'} />
          </>
        )}

        {/* AUTOMATION › Auto Reply */}
        {cat === 'automation' && subTab === 1 && (
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
        )}

        {/* AUTOMATION › Polls */}
        {cat === 'automation' && subTab === 2 && (
          <>
            <DefaultTimezoneCard
              value={settingsData?.timezone || 'UTC'}
              onChange={tz => updateSetting('timezone', tz)}
            />
            <PollCreator botId={botId} groupId={groupId} defaultTimezone={settingsData?.timezone || 'UTC'} />
          </>
        )}

        {/* ══════════════════════════════════════════════════════════
            COMMUNITY
        ══════════════════════════════════════════════════════════ */}

        {/* COMMUNITY › Raids */}
        {cat === 'community' && subTab === 0 && (
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                <Box>
                  <Box sx={{ display: 'flex', alignItems: 'center' }}>
                    <Typography variant="h6" fontWeight={600}>Raid Manager</Typography>
                    <ProBadge />
                  </Box>
                  <Typography variant="body2" color="text.secondary">
                    Coordinate Twitter/X raids with your community. Members earn XP for participating.
                  </Typography>
                </Box>
                <Button variant="contained" startIcon={<Add />} onClick={() => setRaidOpen(true)}>
                  Create Raid
                </Button>
              </Box>
            </CardContent>
          </Card>
        )}

        {/* COMMUNITY › Invite Links */}
        {cat === 'community' && subTab === 1 && (
          <InviteLinks botId={botId} groupId={groupId} />
        )}

        {/* ══════════════════════════════════════════════════════════
            AI & INTEGRATIONS
        ══════════════════════════════════════════════════════════ */}

        {/* AI › Knowledge Base */}
        {cat === 'ai' && subTab === 0 && (
          <KnowledgeBase botId={botId} groupId={groupId} settings={settingsData} updateSetting={updateSetting} />
        )}

        {/* AI › Webhooks */}
        {cat === 'ai' && subTab === 1 && (
          <>
            <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
              <Typography variant="h6" fontWeight={600}>Webhooks</Typography>
              <EntBadge />
            </Box>
            <WebhookManager botId={botId} groupId={groupId} />
          </>
        )}

        {/* ══════════════════════════════════════════════════════════
            ANALYTICS
        ══════════════════════════════════════════════════════════ */}

        {/* ANALYTICS › Members */}
        {cat === 'analytics' && subTab === 0 && (
          <>
            <TableContainer component={Paper} sx={{ border: '1px solid', borderColor: 'divider', overflowX: 'auto' }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>User</TableCell>
                    <TableCell align="right">XP</TableCell>
                    <TableCell align="right">Level</TableCell>
                    <TableCell align="right">Warnings</TableCell>
                    <TableCell>Role</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell>Wallet</TableCell>
                    <TableCell>Wallet Address</TableCell>
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
                      <TableCell align="right">{(m.xp ?? 0).toLocaleString()}</TableCell>
                      <TableCell align="right">{m.level}</TableCell>
                      <TableCell align="right">{m.warnings}</TableCell>
                      <TableCell><Chip label={m.role} size="small" variant="outlined" /></TableCell>
                      <TableCell>
                        {m.is_verified
                          ? <Chip label="Verified" color="success" size="small" />
                          : <Chip label="Unverified" color="default" size="small" />}
                      </TableCell>
                      <TableCell>
                        {m.wallet_address
                          ? <Chip label="Yes" color="success" size="small" />
                          : <Chip label="No" color="default" size="small" />}
                      </TableCell>
                      <TableCell sx={{ maxWidth: 180 }}>
                        {m.wallet_address ? (
                          <Tooltip title={m.wallet_address} arrow>
                            <Typography
                              variant="body2"
                              sx={{
                                fontFamily: 'monospace',
                                fontSize: '0.75rem',
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                                whiteSpace: 'nowrap',
                                cursor: 'pointer',
                                color: 'primary.main',
                              }}
                              onClick={() => navigator.clipboard.writeText(m.wallet_address)}
                            >
                              {m.wallet_address.length > 16
                                ? `${m.wallet_address.slice(0, 8)}…${m.wallet_address.slice(-6)}`
                                : m.wallet_address}
                            </Typography>
                          </Tooltip>
                        ) : (
                          <Typography variant="body2" color="text.disabled">—</Typography>
                        )}
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
          </>
        )}

        {/* ANALYTICS › Audit Log */}
        {cat === 'analytics' && subTab === 1 && (
          <>
            <TableContainer component={Paper} sx={{ border: '1px solid', borderColor: 'divider', overflowX: 'auto' }}>
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
                          {log.timestamp ? new Date(log.timestamp).toLocaleString() : '-'}
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
          </>
        )}

        {/* ANALYTICS › Digest */}
        {cat === 'analytics' && subTab === 2 && (
          digestLoading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}><CircularProgress /></Box>
          ) : (
            <>
              <Card sx={{ mb: 2 }}>
                <CardContent>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                    <Assessment color="primary" />
                    <Typography variant="h6" fontWeight={600}>Telegram Report Digest</Typography>
                  </Box>
                  <Typography variant="body2" color="text.secondary" mb={3}>
                    Automatically send a summary report to this Telegram group on your chosen schedule.
                    The report includes spam removed, members warned/banned, scheduled posts sent, polls created, and growth stats.
                  </Typography>

                  <Grid container spacing={2} mb={3}>
                    {[
                      { key: 'daily',   label: 'Daily Report',   desc: 'Sent every ~24 hours' },
                      { key: 'weekly',  label: 'Weekly Report',  desc: 'Sent every ~7 days' },
                      { key: 'monthly', label: 'Monthly Report', desc: 'Sent every ~30 days' },
                    ].map(({ key, label, desc }) => (
                      <Grid item xs={12} sm={4} key={key}>
                        <Card
                          variant="outlined"
                          sx={{
                            p: 2,
                            borderColor: digestConfig[key] ? 'primary.main' : 'divider',
                            bgcolor: digestConfig[key] ? 'rgba(33,150,243,0.05)' : 'transparent',
                            cursor: 'pointer',
                          }}
                          onClick={() => setDigestConfig((prev) => ({ ...prev, [key]: !prev[key] }))}
                        >
                          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <Box>
                              <Typography variant="body2" fontWeight={700}>{label}</Typography>
                              <Typography variant="caption" color="text.secondary">{desc}</Typography>
                            </Box>
                            <Switch
                              checked={!!digestConfig[key]}
                              onChange={(e) => {
                                e.stopPropagation();
                                setDigestConfig((prev) => ({ ...prev, [key]: e.target.checked }));
                              }}
                              size="small"
                            />
                          </Box>
                          {digestConfig[`last_${key}`] && (
                            <Typography variant="caption" color="text.disabled" display="block" mt={0.5}>
                              Last sent: {new Date(digestConfig[`last_${key}`]).toLocaleString()}
                            </Typography>
                          )}
                        </Card>
                      </Grid>
                    ))}
                  </Grid>

                  <Button
                    variant="contained"
                    startIcon={digestSaving ? <CircularProgress size={16} color="inherit" /> : <Save />}
                    onClick={handleSaveDigest}
                    disabled={digestSaving}
                    sx={{ mr: 2 }}
                  >
                    Save Digest Settings
                  </Button>
                </CardContent>
              </Card>

              <Card>
                <CardContent>
                  <Typography variant="subtitle1" fontWeight={600} mb={0.5}>Send Report Now</Typography>
                  <Typography variant="body2" color="text.secondary" mb={2}>
                    Immediately send a report summary to this group's Telegram chat.
                    Useful for checking the setup or sharing a snapshot with your community.
                  </Typography>
                  <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                    {[
                      { key: 'daily',   label: 'Send Daily Report' },
                      { key: 'weekly',  label: 'Send Weekly Report' },
                      { key: 'monthly', label: 'Send Monthly Report' },
                    ].map(({ key, label }) => (
                      <Button
                        key={key}
                        variant="outlined"
                        startIcon={digestSending === key
                          ? <CircularProgress size={16} color="inherit" />
                          : <Send fontSize="small" />
                        }
                        disabled={!!digestSending}
                        onClick={() => handleSendNow(key)}
                      >
                        {label}
                      </Button>
                    ))}
                  </Stack>

                  <Alert severity="info" sx={{ mt: 2 }} icon={false}>
                    <Typography variant="caption">
                      The bot must be active and present in the group as an admin to send reports.
                    </Typography>
                  </Alert>
                </CardContent>
              </Card>
            </>
          )
        )}

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

      {/* Sticky mobile save button — only visible on xs/sm, analytics tab has no save */}
      {cat !== 'analytics' && (
        <Box
          sx={{
            display: { xs: 'block', md: 'none' },
            position: 'fixed',
            bottom: 0,
            left: 0,
            right: 0,
            zIndex: 1200,
            p: 1.5,
            bgcolor: 'background.paper',
            borderTop: '1px solid',
            borderColor: 'divider',
          }}
        >
          <Button
            fullWidth
            variant="contained"
            startIcon={saving ? <CircularProgress size={16} color="inherit" /> : <Save />}
            onClick={handleSave}
            disabled={saving}
          >
            Save Settings
          </Button>
        </Box>
      )}
    </Box>
  );
}
