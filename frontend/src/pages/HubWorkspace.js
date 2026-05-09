/**
 * /hub/official/:tab — Official bot workspace.
 *
 * Tab bar: Overview | Notes | Reminders | Tasks | Templates | Automation | Settings
 * Knowledge tab is hidden in V1.
 *
 * Mirrors the Group Management tab pattern exactly.
 */
import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  Box, Tabs, Tab, Typography, Chip, Button, CircularProgress,
  Card, CardContent, Switch, FormControlLabel, Divider, Select, MenuItem,
  FormControl, InputLabel, FormHelperText, TextField, Alert, Dialog,
  DialogTitle, DialogContent, DialogActions,
} from '@mui/material';
import { ArrowBack, SmartToy } from '@mui/icons-material';
import hub from '../services/hubApi';
import AddToGroupFlow from '../components/hub/AddToGroupFlow';
import GroupSettingsOverlay from '../components/hub/GroupSettingsOverlay';

// ── Tab definitions (Knowledge hidden in V1) ──────────────────────────────────
const TABS = [
  { label: 'Overview',    value: 'overview' },
  { label: 'Notes',       value: 'notes' },
  { label: 'Reminders',   value: 'reminders' },
  { label: 'Tasks',       value: 'tasks' },
  { label: 'Templates',   value: 'templates' },
  { label: 'Automation',  value: 'automation' },
  { label: 'Settings',    value: 'settings' },
];

export default function HubWorkspace() {
  const navigate = useNavigate();
  const { tab = 'overview' } = useParams();

  const [botData, setBotData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    hub.getOfficialBot()
      .then(r => setBotData(r.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const handleTabChange = (_, newTab) => {
    navigate(`/hub/official/${newTab}`);
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* ── Header ── */}
      <Box
        sx={{
          px: { xs: 2, sm: 3 }, pt: 2, pb: 0,
          borderBottom: '1px solid', borderColor: 'divider',
          bgcolor: 'background.paper',
        }}
      >
        {/* Back link + bot identity row */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1 }}>
          <Button
            size="small"
            startIcon={<ArrowBack sx={{ fontSize: 15 }} />}
            onClick={() => navigate('/hub')}
            sx={{ minWidth: 0, color: 'text.secondary', fontWeight: 400, px: 0.5 }}
          >
            Hub
          </Button>

          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flex: 1, minWidth: 0 }}>
            <SmartToy sx={{ fontSize: 20, color: 'primary.main', flexShrink: 0 }} />
            {loading ? (
              <CircularProgress size={16} />
            ) : (
              <>
                <Typography variant="subtitle1" fontWeight={700} noWrap>
                  {botData?.display_name || 'Official Telegizer Assistant'}
                </Typography>
                <Chip
                  label="Active"
                  size="small"
                  sx={{ bgcolor: 'success.main', color: '#fff', height: 18, fontSize: '0.65rem', flexShrink: 0 }}
                />
                <Typography variant="caption" color="text.secondary" noWrap sx={{ flexShrink: 0 }}>
                  @{botData?.telegram_bot_username || 'telegizer_bot'} · {botData?.group_count ?? 0} groups
                </Typography>
              </>
            )}
          </Box>
        </Box>

        {/* Tab bar */}
        <Tabs
          value={TABS.find(t => t.value === tab) ? tab : 'overview'}
          onChange={handleTabChange}
          variant="scrollable"
          scrollButtons="auto"
          sx={{
            minHeight: 38,
            '& .MuiTab-root': { minHeight: 38, fontSize: '0.8rem', py: 0, px: 1.5, textTransform: 'none' },
          }}
        >
          {TABS.map(t => (
            <Tab key={t.value} label={t.label} value={t.value} />
          ))}
        </Tabs>
      </Box>

      {/* ── Tab content ── */}
      <Box sx={{ flex: 1, overflow: 'auto', p: { xs: 2, sm: 3 } }}>
        <TabContent tab={tab} botData={botData} />
      </Box>
    </Box>
  );
}


// ── Tab content dispatcher ────────────────────────────────────────────────────

function TabContent({ tab, botData }) {
  switch (tab) {
    case 'overview':   return <HubOverview botData={botData} />;
    case 'notes':      return <HubNotes />;
    case 'reminders':  return <HubReminders />;
    case 'tasks':      return <HubTasks />;
    case 'templates':  return <HubTemplates />;
    case 'automation': return <HubAutomation />;
    case 'settings':   return <HubSettings botData={botData} />;
    default:           return <HubOverview botData={botData} />;
  }
}


// ── Overview ──────────────────────────────────────────────────────────────────

function HubOverview({ botData }) {
  const navigate = useNavigate();
  const groupCount = botData?.group_count ?? 0;

  if (groupCount === 0) {
    return (
      <EmptyState
        icon="🤖"
        title="Add the Telegizer bot to your private groups to get started."
        body="The assistant will silently observe and surface tasks, decisions, and meetings here."
        action={
          <Button variant="contained" size="small" onClick={() => navigate('/hub/official/settings')}>
            + Add to Group
          </Button>
        }
      />
    );
  }

  return (
    <EmptyState
      icon="👁"
      title={`Watching ${groupCount} group${groupCount !== 1 ? 's' : ''}.`}
      body="Activity will appear here once there are group discussions to process."
    />
  );
}


// ── Notes ─────────────────────────────────────────────────────────────────────

function HubNotes() {
  return (
    <EmptyState
      icon="📝"
      title="No notes yet."
      body="I'll extract them from group discussions. You can also add notes manually."
      action={<Button variant="outlined" size="small">+ New Note</Button>}
    />
  );
}


// ── Reminders ─────────────────────────────────────────────────────────────────

function HubReminders() {
  return (
    <EmptyState
      icon="🔔"
      title="No reminders scheduled."
      body="Reminders extracted from group discussions will appear here."
      action={<Button variant="outlined" size="small">+ New Reminder</Button>}
    />
  );
}


// ── Tasks ─────────────────────────────────────────────────────────────────────

function HubTasks() {
  return (
    <EmptyState
      icon="✅"
      title="No tasks yet."
      body="I'll surface tasks and action items from group discussions."
      action={<Button variant="outlined" size="small">+ New Task</Button>}
    />
  );
}


// ── Templates ─────────────────────────────────────────────────────────────────

function HubTemplates() {
  return (
    <EmptyState
      icon="📋"
      title="No templates yet."
      body="Create reusable content blocks and dispatch them into groups with /assist [name]."
      action={<Button variant="outlined" size="small">+ New Template</Button>}
    />
  );
}


// ── Automation ────────────────────────────────────────────────────────────────

function HubAutomation() {
  const [digestEnabled, setDigestEnabled] = useState(false);
  const [digestTime, setDigestTime] = useState('21:00');
  const [digestFormat, setDigestFormat] = useState('compact');
  const [meetingReminder, setMeetingReminder] = useState(true);
  const [deadlineAlert, setDeadlineAlert] = useState(true);
  const [followUpReminder, setFollowUpReminder] = useState(false);

  return (
    <Box sx={{ maxWidth: 640 }}>
      {/* Daily Digest */}
      <Typography variant="subtitle2" fontWeight={700} color="text.secondary" sx={{ mb: 1.5, textTransform: 'uppercase', fontSize: '0.7rem', letterSpacing: '0.08em' }}>
        Daily Digest
      </Typography>
      <Card variant="outlined" sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="body2" color="text.secondary" mb={2}>
            Send a daily summary to your Telegram DM
          </Typography>
          <FormControlLabel
            control={<Switch checked={digestEnabled} onChange={e => setDigestEnabled(e.target.checked)} size="small" />}
            label={<Typography variant="body2">{digestEnabled ? 'Enabled' : 'Disabled'}</Typography>}
          />
          {digestEnabled && (
            <Box sx={{ mt: 2, display: 'flex', gap: 2, flexWrap: 'wrap' }}>
              <FormControl size="small" sx={{ minWidth: 120 }}>
                <InputLabel>Time</InputLabel>
                <Select value={digestTime} label="Time" onChange={e => setDigestTime(e.target.value)}>
                  {['07:00','08:00','09:00','12:00','18:00','20:00','21:00','22:00'].map(t => (
                    <MenuItem key={t} value={t}>{t}</MenuItem>
                  ))}
                </Select>
              </FormControl>
              <FormControl size="small" sx={{ minWidth: 120 }}>
                <InputLabel>Format</InputLabel>
                <Select value={digestFormat} label="Format" onChange={e => setDigestFormat(e.target.value)}>
                  <MenuItem value="compact">Compact</MenuItem>
                  <MenuItem value="detailed">Detailed</MenuItem>
                </Select>
              </FormControl>
            </Box>
          )}
        </CardContent>
      </Card>

      {/* Smart Triggers */}
      <Typography variant="subtitle2" fontWeight={700} color="text.secondary" sx={{ mb: 1.5, textTransform: 'uppercase', fontSize: '0.7rem', letterSpacing: '0.08em' }}>
        Smart Triggers
      </Typography>
      <Card variant="outlined" sx={{ mb: 3 }}>
        <CardContent sx={{ pb: '12px !important' }}>
          <Typography variant="body2" color="text.secondary" mb={2}>
            Automated behaviors when specific events are detected
          </Typography>

          <AutomationToggle
            checked={meetingReminder}
            onChange={setMeetingReminder}
            label="Meeting Reminder"
            description="Remind me 1 hour before any extracted meeting"
          />
          <Divider sx={{ my: 1.5 }} />
          <AutomationToggle
            checked={deadlineAlert}
            onChange={setDeadlineAlert}
            label="Deadline Alert"
            description="Send me a DM immediately when a task with a deadline is extracted"
          />
          <Divider sx={{ my: 1.5 }} />
          <AutomationToggle
            checked={followUpReminder}
            onChange={setFollowUpReminder}
            label="Follow-up Reminder"
            description="Remind me 2 days after a follow-up is detected"
          />
        </CardContent>
      </Card>

      {/* Forwarding — Coming V1.5 */}
      <Typography variant="subtitle2" fontWeight={700} color="text.secondary" sx={{ mb: 1.5, textTransform: 'uppercase', fontSize: '0.7rem', letterSpacing: '0.08em' }}>
        Forwarding
      </Typography>
      <Card variant="outlined" sx={{ borderStyle: 'dashed', borderColor: 'divider', bgcolor: 'transparent' }}>
        <CardContent>
          <Typography variant="body2" color="text.secondary">
            Forward extracted summaries to another Telegram chat — Coming in V1.5
          </Typography>
        </CardContent>
      </Card>
    </Box>
  );
}

function AutomationToggle({ checked, onChange, label, description }) {
  return (
    <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 1 }}>
      <Box>
        <Typography variant="body2" fontWeight={500}>{label}</Typography>
        <Typography variant="caption" color="text.secondary">{description}</Typography>
      </Box>
      <Switch checked={checked} onChange={e => onChange(e.target.checked)} size="small" sx={{ flexShrink: 0 }} />
    </Box>
  );
}


// ── Settings ──────────────────────────────────────────────────────────────────

function HubSettings({ botData }) {
  const [groups, setGroups] = useState([]);
  const [groupsLoading, setGroupsLoading] = useState(true);
  const [settings, setSettings] = useState(null);
  const [personality, setPersonality] = useState('');
  const [language, setLanguage] = useState('en');
  const [sensitivity, setSensitivity] = useState('standard');
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [settingsError, setSettingsError] = useState(null);
  const [settingsSaved, setSettingsSaved] = useState(false);

  // Group settings overlay
  const [overlayGroup, setOverlayGroup] = useState(null);

  // Add-to-group flow
  const [addFlowOpen, setAddFlowOpen] = useState(false);

  // Privacy
  const [retention, setRetention] = useState('72');
  const [retentionSaving, setRetentionSaving] = useState(false);

  // Delete-all dialog
  const [deleteAllOpen, setDeleteAllOpen] = useState(false);
  const [deleteAllConfirm, setDeleteAllConfirm] = useState('');
  const [deleteAllLoading, setDeleteAllLoading] = useState(false);
  const [deleteAllError, setDeleteAllError] = useState(null);

  // Export
  const [exportLoading, setExportLoading] = useState(false);

  useEffect(() => {
    hub.listOfficialGroups()
      .then(r => setGroups(r.data.groups || []))
      .catch(() => {})
      .finally(() => setGroupsLoading(false));

    hub.getOfficialSettings()
      .then(r => {
        const s = r.data.settings || {};
        setSettings(s);
        setPersonality(s.ai_personality_note || '');
        setLanguage(s.response_language || 'en');
        setSensitivity(s.extraction_sensitivity || 'standard');
        setRetention(String(s.buffer_ttl_hours || 72));
      })
      .catch(() => {});
  }, []);

  const handleSaveAI = async () => {
    setSettingsSaving(true);
    setSettingsError(null);
    setSettingsSaved(false);
    try {
      await hub.updateOfficialSettings({
        ai_personality_note: personality || null,
        response_language: language,
        extraction_sensitivity: sensitivity,
      });
      setSettingsSaved(true);
      setTimeout(() => setSettingsSaved(false), 2500);
    } catch (e) {
      setSettingsError(e?.response?.data?.error || 'Failed to save.');
    } finally {
      setSettingsSaving(false);
    }
  };

  const handleRetentionChange = async (val) => {
    setRetention(val);
    setRetentionSaving(true);
    try {
      await hub.updateRetention(Number(val));
    } catch (_) {}
    setRetentionSaving(false);
  };

  const handleExport = async () => {
    setExportLoading(true);
    try {
      const r = await hub.exportData();
      const blob = new Blob([JSON.stringify(r.data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'hub-export.json';
      a.click();
      URL.revokeObjectURL(url);
    } catch (_) {}
    setExportLoading(false);
  };

  const handleDeleteAll = async () => {
    if (deleteAllConfirm !== 'DELETE') return;
    setDeleteAllLoading(true);
    setDeleteAllError(null);
    try {
      await hub.deleteAll();
      setDeleteAllOpen(false);
      setGroups([]);
    } catch (e) {
      setDeleteAllError(e?.response?.data?.error || 'Failed to delete.');
    } finally {
      setDeleteAllLoading(false);
    }
  };

  const handleGroupUpdated = (updated) => {
    setGroups(prev => prev.map(g => g.id === updated.id ? { ...g, ...updated } : g));
  };

  const handleGroupDisconnected = (groupId) => {
    setGroups(prev => prev.filter(g => g.id !== groupId));
  };

  const handleGroupConnected = (newGroup) => {
    setGroups(prev => [...prev, newGroup]);
  };

  return (
    <Box sx={{ maxWidth: 640 }}>
      {/* AI Assistant */}
      <SectionHeader label="AI Assistant" />
      <Card variant="outlined" sx={{ mb: 3 }}>
        <CardContent>
          {settingsError && <Alert severity="error" sx={{ mb: 2 }}>{settingsError}</Alert>}
          {settingsSaved && <Alert severity="success" sx={{ mb: 2 }}>Settings saved.</Alert>}
          <TextField
            label="Personality Note"
            multiline
            rows={3}
            fullWidth
            size="small"
            placeholder="e.g. I'm a founder focused on growth. Keep extractions focused on action items and decisions."
            value={personality}
            inputProps={{ maxLength: 200 }}
            helperText="Max 200 chars · Applied to all extractions for this bot"
            sx={{ mb: 2 }}
            onChange={e => setPersonality(e.target.value)}
          />

          <FormControl size="small" fullWidth sx={{ mb: 2 }}>
            <InputLabel>Response Language</InputLabel>
            <Select value={language} label="Response Language" onChange={e => setLanguage(e.target.value)}>
              <MenuItem value="en">English</MenuItem>
              <MenuItem value="ar">Arabic</MenuItem>
              <MenuItem value="es">Spanish</MenuItem>
              <MenuItem value="fr">French</MenuItem>
            </Select>
          </FormControl>

          <Typography variant="body2" fontWeight={500} gutterBottom>Extraction Sensitivity</Typography>
          <Box sx={{ display: 'flex', gap: 1, mb: 2 }}>
            {['minimal', 'standard', 'aggressive'].map(v => (
              <Button
                key={v}
                size="small"
                variant={sensitivity === v ? 'contained' : 'outlined'}
                sx={{ textTransform: 'capitalize' }}
                onClick={() => setSensitivity(v)}
              >
                {v}
              </Button>
            ))}
          </Box>

          <Button
            variant="contained"
            size="small"
            onClick={handleSaveAI}
            disabled={settingsSaving}
          >
            {settingsSaving ? <CircularProgress size={14} sx={{ mr: 0.5 }} /> : null}
            Save AI Settings
          </Button>
        </CardContent>
      </Card>

      {/* Connected Groups */}
      <SectionHeader label="Connected Groups" />
      <Card variant="outlined" sx={{ mb: 3 }}>
        <CardContent>
          {groupsLoading ? (
            <CircularProgress size={20} />
          ) : groups.length === 0 ? (
            <Typography variant="body2" color="text.secondary" mb={1.5}>
              No groups connected yet.
            </Typography>
          ) : (
            groups.map((g, i) => (
              <Box key={g.id}>
                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', py: 0.75 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, minWidth: 0 }}>
                    <Box sx={{ width: 8, height: 8, borderRadius: '50%', flexShrink: 0, bgcolor: g.is_active ? 'success.main' : 'text.disabled' }} />
                    <Typography variant="body2" noWrap>
                      {g.display_name || g.group_name || `Group ${g.telegram_group_id}`}
                    </Typography>
                    {g.pause_reason === 'plan_limit' && (
                      <Chip label="Plan limit" size="small" sx={{ height: 16, fontSize: '0.6rem', bgcolor: 'warning.main', color: '#fff', flexShrink: 0 }} />
                    )}
                    {!g.is_active && g.pause_reason !== 'plan_limit' && (
                      <Chip label="Paused" size="small" sx={{ height: 16, fontSize: '0.6rem', flexShrink: 0 }} />
                    )}
                  </Box>
                  <Button
                    size="small"
                    variant="outlined"
                    sx={{ fontSize: '0.72rem', flexShrink: 0, ml: 1 }}
                    onClick={() => setOverlayGroup(g)}
                  >
                    Settings
                  </Button>
                </Box>
                {i < groups.length - 1 && <Divider />}
              </Box>
            ))
          )}
          <Button
            variant="outlined"
            size="small"
            startIcon={<span style={{ fontSize: '1rem', lineHeight: 1 }}>+</span>}
            sx={{ mt: groups.length > 0 ? 1.5 : 0 }}
            onClick={() => setAddFlowOpen(true)}
          >
            Add to Group
          </Button>
        </CardContent>
      </Card>

      {/* Memory */}
      <SectionHeader label="Memory" />
      <Card variant="outlined" sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="body2" color="text.secondary" mb={1.5}>
            Global memory is shared across all your bots.
          </Typography>
          <Button variant="outlined" size="small">Edit Memory →</Button>
        </CardContent>
      </Card>

      {/* Notifications */}
      <SectionHeader label="Notifications" />
      <Card variant="outlined" sx={{ mb: 3 }}>
        <CardContent>
          <FormControlLabel
            control={<Switch defaultChecked size="small" />}
            label={<Typography variant="body2">Telegram DM alerts</Typography>}
          />
        </CardContent>
      </Card>

      {/* Privacy & Data */}
      <SectionHeader label="Privacy & Data" />
      <Card variant="outlined">
        <CardContent>
          <FormControl size="small" sx={{ mb: 2, minWidth: 180 }}>
            <InputLabel>Message retention</InputLabel>
            <Select
              value={retention}
              label="Message retention"
              disabled={retentionSaving}
              onChange={e => handleRetentionChange(e.target.value)}
            >
              <MenuItem value="24">24 hours</MenuItem>
              <MenuItem value="48">48 hours</MenuItem>
              <MenuItem value="72">72 hours</MenuItem>
            </Select>
            <FormHelperText>Raw message buffer TTL{retentionSaving ? ' — saving…' : ''}</FormHelperText>
          </FormControl>
          <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
            <Button variant="outlined" size="small" onClick={handleExport} disabled={exportLoading}>
              {exportLoading ? <CircularProgress size={14} sx={{ mr: 0.5 }} /> : null}
              Export data
            </Button>
            <Button variant="outlined" size="small" color="error" onClick={() => setDeleteAllOpen(true)}>
              Delete all data
            </Button>
          </Box>
        </CardContent>
      </Card>

      {/* Modals */}
      <AddToGroupFlow
        open={addFlowOpen}
        onClose={() => setAddFlowOpen(false)}
        onGroupConnected={handleGroupConnected}
      />

      <GroupSettingsOverlay
        open={Boolean(overlayGroup)}
        group={overlayGroup}
        onClose={() => setOverlayGroup(null)}
        onUpdated={handleGroupUpdated}
        onDisconnected={handleGroupDisconnected}
      />

      {/* Delete-all confirmation dialog */}
      <Dialog open={deleteAllOpen} onClose={() => setDeleteAllOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>Delete all Hub data?</DialogTitle>
        <DialogContent>
          {deleteAllError && <Alert severity="error" sx={{ mb: 2 }}>{deleteAllError}</Alert>}
          <Typography variant="body2" color="text.secondary" mb={2}>
            This permanently deletes all digests, tasks, reminders, notes, decisions, meetings, and memory records.
            Connected groups will remain but all extracted data will be erased.
          </Typography>
          <TextField
            label='Type "DELETE" to confirm'
            size="small"
            fullWidth
            value={deleteAllConfirm}
            onChange={e => setDeleteAllConfirm(e.target.value)}
          />
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => { setDeleteAllOpen(false); setDeleteAllConfirm(''); }} size="small" color="inherit">
            Cancel
          </Button>
          <Button
            onClick={handleDeleteAll}
            variant="contained"
            color="error"
            size="small"
            disabled={deleteAllConfirm !== 'DELETE' || deleteAllLoading}
          >
            {deleteAllLoading ? <CircularProgress size={14} sx={{ mr: 0.5 }} /> : null}
            Delete all
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

function SectionHeader({ label }) {
  return (
    <Typography
      variant="caption"
      fontWeight={700}
      color="text.disabled"
      sx={{ display: 'block', mb: 1, textTransform: 'uppercase', letterSpacing: '0.08em', fontSize: '0.68rem' }}
    >
      {label}
    </Typography>
  );
}


// ── Shared empty state ────────────────────────────────────────────────────────

function EmptyState({ icon, title, body, action }) {
  return (
    <Box sx={{ textAlign: 'center', py: 8, maxWidth: 440, mx: 'auto' }}>
      {icon && <Typography fontSize="2.5rem" mb={1.5}>{icon}</Typography>}
      <Typography variant="body1" fontWeight={600} gutterBottom>{title}</Typography>
      {body && <Typography variant="body2" color="text.secondary" mb={action ? 3 : 0}>{body}</Typography>}
      {action}
    </Box>
  );
}
