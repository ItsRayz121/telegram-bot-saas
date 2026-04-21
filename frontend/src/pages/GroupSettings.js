import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, AppBar, Toolbar, Typography, IconButton, Tabs, Tab,
  Card, CardContent, Button, TextField, Switch, FormControlLabel,
  Grid, CircularProgress, Chip, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow, Paper, Select, MenuItem,
  FormControl, InputLabel, Pagination, Divider,
} from '@mui/material';
import { ArrowBack, Save, Add } from '@mui/icons-material';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'react-toastify';
import { settings } from '../services/api';
import RaidCreator from '../components/RaidCreator';

function TabPanel({ children, value, index }) {
  return value === index ? <Box sx={{ pt: 3 }}>{children}</Box> : null;
}

const ACTION_COLORS = {
  warn: 'warning',
  ban: 'error',
  kick: 'error',
  mute: 'warning',
  unmute: 'success',
  unban: 'success',
  tempban: 'error',
  tempmute: 'warning',
  purge: 'info',
};

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
  const [raidOpen, setRaidOpen] = useState(false);

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

  useEffect(() => {
    fetchSettings();
  }, [fetchSettings]);

  useEffect(() => {
    if (tab === 5) fetchMembers(membersPage);
  }, [tab, membersPage, fetchMembers]);

  useEffect(() => {
    if (tab === 6) fetchAuditLogs(auditPage);
  }, [tab, auditPage, fetchAuditLogs]);

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
            disabled={saving || tab >= 5}
          >
            Save
          </Button>
        </Toolbar>
        <Tabs
          value={tab}
          onChange={(_, v) => setTab(v)}
          variant="scrollable"
          scrollButtons="auto"
          sx={{ px: 2 }}
        >
          <Tab label="Verification" />
          <Tab label="Welcome" />
          <Tab label="Levels" />
          <Tab label="AutoMod" />
          <Tab label="Moderation" />
          <Tab label="Members" />
          <Tab label="Audit Logs" />
        </Tabs>
      </AppBar>

      <Box sx={{ maxWidth: 900, mx: 'auto', p: 3 }}>

        {/* Verification Tab */}
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
                    <InputLabel>Verification Type</InputLabel>
                    <Select
                      value={v.type || 'button'}
                      label="Verification Type"
                      onChange={(e) => updateSetting('verification.type', e.target.value)}
                    >
                      <MenuItem value="button">Button Click</MenuItem>
                      <MenuItem value="math">Math Captcha</MenuItem>
                      <MenuItem value="word">Word Captcha</MenuItem>
                    </Select>
                  </FormControl>
                </Grid>
                <Grid item xs={12} sm={6}>
                  <TextField
                    fullWidth
                    type="number"
                    label="Timeout (seconds)"
                    value={v.timeout || 120}
                    onChange={(e) => updateSetting('verification.timeout', parseInt(e.target.value))}
                  />
                </Grid>
                <Grid item xs={12}>
                  <TextField
                    fullWidth
                    label="Kick on Fail"
                    select
                    value={v.kick_on_fail ? 'true' : 'false'}
                    onChange={(e) => updateSetting('verification.kick_on_fail', e.target.value === 'true')}
                  >
                    <MenuItem value="true">Yes — kick unverified users</MenuItem>
                    <MenuItem value="false">No — restrict until verified</MenuItem>
                  </TextField>
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </TabPanel>

        {/* Welcome Tab */}
        <TabPanel value={tab} index={1}>
          <Card>
            <CardContent>
              <Typography variant="h6" fontWeight={600} mb={2}>Welcome Message</Typography>
              <FormControlLabel
                control={<Switch checked={!!w.enabled} onChange={(e) => updateSetting('welcome.enabled', e.target.checked)} />}
                label="Send welcome message to new members"
              />
              <Divider sx={{ my: 2 }} />
              <TextField
                fullWidth
                multiline
                rows={5}
                label="Welcome Message"
                value={w.message || ''}
                onChange={(e) => updateSetting('welcome.message', e.target.value)}
                helperText="Use {name} for member name, {group} for group name, {count} for member count"
                sx={{ mb: 2 }}
              />
              <FormControlLabel
                control={<Switch checked={!!w.delete_after} onChange={(e) => updateSetting('welcome.delete_after', e.target.checked)} />}
                label="Auto-delete welcome message after 60 seconds"
              />
            </CardContent>
          </Card>
        </TabPanel>

        {/* Levels Tab */}
        <TabPanel value={tab} index={2}>
          <Card>
            <CardContent>
              <Typography variant="h6" fontWeight={600} mb={2}>XP & Level System</Typography>
              <FormControlLabel
                control={<Switch checked={!!l.enabled} onChange={(e) => updateSetting('levels.enabled', e.target.checked)} />}
                label="Enable XP and leveling system"
              />
              <Divider sx={{ my: 2 }} />
              <Grid container spacing={2}>
                <Grid item xs={12} sm={4}>
                  <TextField
                    fullWidth
                    type="number"
                    label="XP per Message"
                    value={l.xp_per_message || 5}
                    onChange={(e) => updateSetting('levels.xp_per_message', parseInt(e.target.value))}
                  />
                </Grid>
                <Grid item xs={12} sm={4}>
                  <TextField
                    fullWidth
                    type="number"
                    label="XP Cooldown (seconds)"
                    value={l.cooldown || 60}
                    onChange={(e) => updateSetting('levels.cooldown', parseInt(e.target.value))}
                  />
                </Grid>
                <Grid item xs={12} sm={4}>
                  <FormControlLabel
                    control={<Switch checked={!!l.announce_levelup} onChange={(e) => updateSetting('levels.announce_levelup', e.target.checked)} />}
                    label="Announce level ups"
                    sx={{ mt: 1 }}
                  />
                </Grid>
                <Grid item xs={12}>
                  <TextField
                    fullWidth
                    multiline
                    rows={2}
                    label="Level Up Message"
                    value={l.levelup_message || ''}
                    onChange={(e) => updateSetting('levels.levelup_message', e.target.value)}
                    helperText="Use {name}, {level}"
                  />
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </TabPanel>

        {/* AutoMod Tab */}
        <TabPanel value={tab} index={3}>
          <Card>
            <CardContent>
              <Typography variant="h6" fontWeight={600} mb={2}>AutoMod Settings</Typography>
              <FormControlLabel
                control={<Switch checked={!!am.enabled} onChange={(e) => updateSetting('automod.enabled', e.target.checked)} />}
                label="Enable AutoMod"
              />
              <Divider sx={{ my: 2 }} />
              <Grid container spacing={2}>
                {[
                  ['Spam Detection', 'spam.enabled', 'automod.spam.enabled'],
                  ['Bad Words Filter', 'bad_words.enabled', 'automod.bad_words.enabled'],
                  ['Block External Links', 'external_links.enabled', 'automod.external_links.enabled'],
                  ['Block Telegram Links', 'telegram_links.enabled', 'automod.telegram_links.enabled'],
                  ['Excessive Emojis', 'excessive_emojis.enabled', 'automod.excessive_emojis.enabled'],
                  ['Caps Lock Filter', 'caps_lock.enabled', 'automod.caps_lock.enabled'],
                  ['Block Forwarded Messages', 'forwarded_messages.enabled', 'automod.forwarded_messages.enabled'],
                ].map(([label, key, path]) => (
                  <Grid item xs={12} sm={6} key={key}>
                    <FormControlLabel
                      control={
                        <Switch
                          checked={!!(am[key.split('.')[0]] || {})[key.split('.')[1]]}
                          onChange={(e) => updateSetting(path, e.target.checked)}
                        />
                      }
                      label={label}
                    />
                  </Grid>
                ))}
                <Grid item xs={12}>
                  <TextField
                    fullWidth
                    multiline
                    rows={3}
                    label="Banned Words (comma separated)"
                    value={(am.bad_words?.words || []).join(', ')}
                    onChange={(e) =>
                      updateSetting('automod.bad_words.words', e.target.value.split(',').map((w) => w.trim()).filter(Boolean))
                    }
                  />
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </TabPanel>

        {/* Moderation Tab */}
        <TabPanel value={tab} index={4}>
          <Card sx={{ mb: 2 }}>
            <CardContent>
              <Typography variant="h6" fontWeight={600} mb={2}>Moderation Settings</Typography>
              <Grid container spacing={2}>
                <Grid item xs={12} sm={6}>
                  <TextField
                    fullWidth
                    type="number"
                    label="Warnings Before Ban"
                    value={mod.warnings_before_ban || 3}
                    onChange={(e) => updateSetting('moderation.warnings_before_ban', parseInt(e.target.value))}
                  />
                </Grid>
                <Grid item xs={12} sm={6}>
                  <FormControlLabel
                    control={
                      <Switch
                        checked={!!mod.ban_on_max_warnings}
                        onChange={(e) => updateSetting('moderation.ban_on_max_warnings', e.target.checked)}
                      />
                    }
                    label="Auto-ban on max warnings"
                    sx={{ mt: 1 }}
                  />
                </Grid>
              </Grid>
            </CardContent>
          </Card>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                <Typography variant="h6" fontWeight={600}>Raid Manager</Typography>
                <Button variant="contained" startIcon={<Add />} onClick={() => setRaidOpen(true)}>
                  Create Raid
                </Button>
              </Box>
              <Typography variant="body2" color="text.secondary">
                Coordinate Twitter/X raids with your community. Members earn XP for participating.
              </Typography>
            </CardContent>
          </Card>
        </TabPanel>

        {/* Members Tab */}
        <TabPanel value={tab} index={5}>
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
                        {m.first_name} {m.username ? `(@${m.username})` : ''}
                      </Typography>
                    </TableCell>
                    <TableCell align="right">{m.xp.toLocaleString()}</TableCell>
                    <TableCell align="right">{m.level}</TableCell>
                    <TableCell align="right">{m.warnings}</TableCell>
                    <TableCell>
                      <Chip label={m.role} size="small" variant="outlined" />
                    </TableCell>
                    <TableCell>
                      {m.is_verified ? (
                        <Chip label="Verified" color="success" size="small" />
                      ) : (
                        <Chip label="Unverified" color="default" size="small" />
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
          {membersTotal > 1 && (
            <Box sx={{ display: 'flex', justifyContent: 'center', mt: 2 }}>
              <Pagination
                count={membersTotal}
                page={membersPage}
                onChange={(_, p) => setMembersPage(p)}
                color="primary"
              />
            </Box>
          )}
        </TabPanel>

        {/* Audit Logs Tab */}
        <TabPanel value={tab} index={6}>
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
                      <Chip
                        label={log.action_type}
                        color={ACTION_COLORS[log.action_type] || 'default'}
                        size="small"
                      />
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">
                        {log.target_username || log.target_user_id}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">
                        {log.moderator_username || log.moderator_id}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" color="text.secondary">
                        {log.reason || '-'}
                      </Typography>
                    </TableCell>
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
              <Pagination
                count={auditTotal}
                page={auditPage}
                onChange={(_, p) => setAuditPage(p)}
                color="primary"
              />
            </Box>
          )}
        </TabPanel>
      </Box>

      <RaidCreator
        open={raidOpen}
        onClose={() => setRaidOpen(false)}
        botId={botId}
        groupId={groupId}
      />
    </Box>
  );
}
