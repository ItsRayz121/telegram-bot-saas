import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Box, Container, Typography, Button, Card, CardContent,
  Chip, CircularProgress, Alert, Dialog, DialogTitle,
  DialogContent, DialogActions, TextField, IconButton,
  Tooltip, Grid, Divider, Switch, FormControlLabel,
  Tabs, Tab, Table, TableBody, TableCell, TableHead,
  TableRow, Paper, Select, MenuItem, InputLabel, FormControl,
} from '@mui/material';
import {
  ArrowBack, Add, Delete, Edit, CheckCircle, Warning,
  Code, Event, Settings,
} from '@mui/icons-material';
import { toast } from 'react-toastify';
import { telegramGroups } from '../services/api';

function TabPanel({ children, value, index }) {
  return value === index ? <Box sx={{ pt: 3 }}>{children}</Box> : null;
}

const TEMPLATES = [
  { command: 'rules', label: '/rules', text: '📋 *Group Rules*\n\n1. Be respectful\n2. No spam\n3. Stay on topic' },
  { command: 'support', label: '/support', text: '💬 *Need support?*\nContact us at support@example.com' },
  { command: 'website', label: '/website', text: '🌐 Visit our website: https://example.com' },
  { command: 'buy', label: '/buy', text: '💳 Purchase here: https://example.com/buy' },
  { command: 'officiallinks', label: '/officiallinks', text: '🔗 *Official Links*\nWebsite: https://example.com' },
  { command: 'help', label: '/help', text: '❓ Use /rules or /support for assistance.' },
];

export default function GroupManagement() {
  const { groupId } = useParams();
  const navigate = useNavigate();
  const [group, setGroup] = useState(null);
  const [commands, setCommands] = useState([]);
  const [events, setEvents] = useState([]);
  const [tab, setTab] = useState(0);
  const [loading, setLoading] = useState(true);
  const [cmdDialog, setCmdDialog] = useState(false);
  const [editCmd, setEditCmd] = useState(null);
  const [form, setForm] = useState({ command: '', response_text: '', response_type: 'text', enabled: true });
  const [saving, setSaving] = useState(false);

  const loadGroup = useCallback(async () => {
    try {
      const [gRes, cmdRes] = await Promise.all([
        telegramGroups.get(groupId),
        telegramGroups.listCommands(groupId),
      ]);
      setGroup(gRes.data.group);
      setCommands(cmdRes.data.commands || []);
    } catch {
      toast.error('Failed to load group');
      navigate('/my-groups');
    } finally {
      setLoading(false);
    }
  }, [groupId, navigate]);

  const loadEvents = useCallback(async () => {
    try {
      const res = await telegramGroups.getEvents(groupId, { per_page: 30 });
      setEvents(res.data.events || []);
    } catch {
      /* non-fatal */
    }
  }, [groupId]);

  useEffect(() => {
    loadGroup();
  }, [loadGroup]);

  useEffect(() => {
    if (tab === 1) loadEvents();
  }, [tab, loadEvents]);

  const openNewCmd = () => {
    setEditCmd(null);
    setForm({ command: '', response_text: '', response_type: 'text', enabled: true });
    setCmdDialog(true);
  };

  const openEditCmd = (cmd) => {
    setEditCmd(cmd);
    setForm({
      command: cmd.command,
      response_text: cmd.response_text,
      response_type: cmd.response_type,
      enabled: cmd.enabled,
    });
    setCmdDialog(true);
  };

  const applyTemplate = (tpl) => {
    setForm((f) => ({ ...f, command: tpl.command, response_text: tpl.text, response_type: 'markdown' }));
  };

  const saveCmd = async () => {
    if (!form.command || !form.response_text) return;
    setSaving(true);
    try {
      if (editCmd) {
        await telegramGroups.updateCommand(groupId, editCmd.id, form);
        toast.success('Command updated');
      } else {
        await telegramGroups.createCommand(groupId, form);
        toast.success(`/${form.command} created`);
      }
      setCmdDialog(false);
      loadGroup();
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to save command');
    } finally {
      setSaving(false);
    }
  };

  const deleteCmd = async (cmd) => {
    if (!window.confirm(`Delete /${cmd.command}?`)) return;
    try {
      await telegramGroups.deleteCommand(groupId, cmd.id);
      toast.success('Command deleted');
      loadGroup();
    } catch {
      toast.error('Failed to delete command');
    }
  };

  const toggleCmd = async (cmd) => {
    try {
      await telegramGroups.updateCommand(groupId, cmd.id, { enabled: !cmd.enabled });
      loadGroup();
    } catch {
      toast.error('Failed to update command');
    }
  };

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh' }}>
        <CircularProgress />
      </Box>
    );
  }

  if (!group) return null;

  const perms = group.bot_permissions || {};
  const missingPerms = Object.entries(perms).filter(([, v]) => !v).map(([k]) => k);

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default', py: 4 }}>
      <Container maxWidth="lg">
        {/* Header */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 4 }}>
          <IconButton onClick={() => navigate('/my-groups')}><ArrowBack /></IconButton>
          <Box sx={{ flex: 1 }}>
            <Typography variant="h5" fontWeight={700}>{group.title}</Typography>
            <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'monospace' }}>
              ID: {group.telegram_group_id} &nbsp;·&nbsp;
              {group.linked_via_bot_type === 'official' ? '🟢 Official Bot' : '🔵 Custom Bot'}
            </Typography>
          </Box>
          <Chip
            label={group.bot_status}
            color={group.bot_status === 'active' ? 'success' : 'warning'}
          />
        </Box>

        {missingPerms.length > 0 && (
          <Alert severity="warning" sx={{ mb: 3 }} icon={<Warning />}>
            Missing permissions: <strong>{missingPerms.join(', ')}</strong>. Some features won't work.
            Grant admin rights to the bot in Telegram.
          </Alert>
        )}

        {/* Tabs */}
        <Paper sx={{ mb: 3 }}>
          <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ borderBottom: 1, borderColor: 'divider' }}>
            <Tab icon={<Code fontSize="small" />} iconPosition="start" label="Custom Commands" />
            <Tab icon={<Event fontSize="small" />} iconPosition="start" label="Event Log" />
          </Tabs>

          {/* Custom Commands Tab */}
          <TabPanel value={tab} index={0}>
            <Box sx={{ px: 3, pb: 3 }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
                <Typography variant="subtitle1" fontWeight={600}>
                  Custom Commands ({commands.length})
                </Typography>
                <Button variant="contained" size="small" startIcon={<Add />} onClick={openNewCmd}>
                  New Command
                </Button>
              </Box>

              {commands.length === 0 ? (
                <Box sx={{ textAlign: 'center', py: 6, color: 'text.secondary' }}>
                  <Code sx={{ fontSize: 48, mb: 1 }} />
                  <Typography>No custom commands yet.</Typography>
                  <Typography variant="body2" mt={0.5}>
                    Create commands like /rules, /support, /website
                  </Typography>
                </Box>
              ) : (
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Command</TableCell>
                      <TableCell>Response Preview</TableCell>
                      <TableCell>Type</TableCell>
                      <TableCell align="center">Enabled</TableCell>
                      <TableCell align="right">Actions</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {commands.map((cmd) => (
                      <TableRow key={cmd.id} hover>
                        <TableCell>
                          <Typography variant="body2" fontFamily="monospace" fontWeight={600}>
                            /{cmd.command}
                          </Typography>
                        </TableCell>
                        <TableCell>
                          <Typography
                            variant="body2"
                            color="text.secondary"
                            sx={{ maxWidth: 280, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                          >
                            {cmd.response_text}
                          </Typography>
                        </TableCell>
                        <TableCell>
                          <Chip label={cmd.response_type} size="small" variant="outlined" />
                        </TableCell>
                        <TableCell align="center">
                          <Switch
                            size="small"
                            checked={cmd.enabled}
                            onChange={() => toggleCmd(cmd)}
                          />
                        </TableCell>
                        <TableCell align="right">
                          <IconButton size="small" onClick={() => openEditCmd(cmd)}>
                            <Edit fontSize="small" />
                          </IconButton>
                          <IconButton size="small" color="error" onClick={() => deleteCmd(cmd)}>
                            <Delete fontSize="small" />
                          </IconButton>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </Box>
          </TabPanel>

          {/* Event Log Tab */}
          <TabPanel value={tab} index={1}>
            <Box sx={{ px: 3, pb: 3 }}>
              <Typography variant="subtitle1" fontWeight={600} mb={2}>
                Recent Events
              </Typography>
              {events.length === 0 ? (
                <Typography color="text.secondary">No events recorded yet.</Typography>
              ) : (
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Event</TableCell>
                      <TableCell>Message</TableCell>
                      <TableCell>Time</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {events.map((ev) => (
                      <TableRow key={ev.id} hover>
                        <TableCell>
                          <Chip label={ev.event_type} size="small" variant="outlined" />
                        </TableCell>
                        <TableCell>
                          <Typography variant="body2" color="text.secondary">
                            {ev.message || '—'}
                          </Typography>
                        </TableCell>
                        <TableCell>
                          <Typography variant="caption" color="text.secondary">
                            {new Date(ev.created_at).toLocaleString()}
                          </Typography>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </Box>
          </TabPanel>
        </Paper>
      </Container>

      {/* Command dialog */}
      <Dialog open={cmdDialog} onClose={() => setCmdDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{editCmd ? `Edit /${editCmd.command}` : 'New Custom Command'}</DialogTitle>
        <DialogContent sx={{ pt: '16px !important' }}>
          {!editCmd && (
            <>
              <Typography variant="caption" color="text.secondary" gutterBottom>
                Quick templates:
              </Typography>
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.75, mb: 2 }}>
                {TEMPLATES.map((t) => (
                  <Chip
                    key={t.command}
                    label={t.label}
                    size="small"
                    variant="outlined"
                    onClick={() => applyTemplate(t)}
                    sx={{ cursor: 'pointer' }}
                  />
                ))}
              </Box>
            </>
          )}

          <TextField
            fullWidth
            label="Command (without /)"
            value={form.command}
            onChange={(e) => setForm({ ...form, command: e.target.value.toLowerCase().replace(/\W/g, '') })}
            placeholder="rules"
            disabled={!!editCmd}
            sx={{ mb: 2 }}
            InputProps={{ startAdornment: <Typography color="text.secondary" mr={0.5}>/</Typography> }}
          />

          <FormControl fullWidth sx={{ mb: 2 }}>
            <InputLabel>Response Type</InputLabel>
            <Select
              value={form.response_type}
              label="Response Type"
              onChange={(e) => setForm({ ...form, response_type: e.target.value })}
            >
              <MenuItem value="text">Plain Text</MenuItem>
              <MenuItem value="markdown">Markdown</MenuItem>
            </Select>
          </FormControl>

          <TextField
            fullWidth
            multiline
            rows={5}
            label="Response Text"
            value={form.response_text}
            onChange={(e) => setForm({ ...form, response_text: e.target.value })}
            placeholder="Enter the bot's reply..."
            helperText={form.response_type === 'markdown' ? 'Supports *bold*, _italic_, `code`' : undefined}
          />

          <FormControlLabel
            sx={{ mt: 1 }}
            control={
              <Switch
                checked={form.enabled}
                onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
              />
            }
            label="Enabled"
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCmdDialog(false)}>Cancel</Button>
          <Button
            variant="contained"
            onClick={saveCmd}
            disabled={saving || !form.command || !form.response_text}
          >
            {saving ? <CircularProgress size={20} /> : (editCmd ? 'Save Changes' : 'Create Command')}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
