import React, { useState, useEffect } from 'react';
import {
  Box, Card, CardContent, Typography, Button, TextField, Grid,
  Switch, FormControlLabel, Dialog, DialogTitle, DialogContent,
  DialogActions, IconButton, Chip, Alert, Tooltip, Collapse,
  List, ListItem, ListItemText, Divider,
} from '@mui/material';
import { Add, Delete, Edit, ContentCopy, ExpandMore, ExpandLess, Webhook } from '@mui/icons-material';
import { toast } from 'react-toastify';
import { webhooks } from '../services/api';

const API_BASE = process.env.REACT_APP_API_URL || window.location.origin;

export default function WebhookManager({ botId, groupId }) {
  const [hookList, setHookList] = useState([]);
  const [open, setOpen] = useState(false);
  const [editHook, setEditHook] = useState(null);
  const [expanded, setExpanded] = useState({});
  const [form, setForm] = useState({ name: '', description: '', message_template: '📡 *{name}*\n\n{payload}' });

  const load = async () => {
    try {
      const res = await webhooks.list(botId, groupId);
      setHookList(res.data.webhooks || []);
    } catch { }
  };

  useEffect(() => { load(); }, [botId, groupId]);

  const handleCreate = async () => {
    if (!form.name.trim()) { toast.error('Name is required'); return; }
    try {
      if (editHook) {
        await webhooks.update(botId, groupId, editHook.id, form);
        toast.success('Webhook updated');
      } else {
        await webhooks.create(botId, groupId, form);
        toast.success('Webhook created');
      }
      setOpen(false);
      setEditHook(null);
      setForm({ name: '', description: '', message_template: '📡 *{name}*\n\n{payload}' });
      load();
    } catch (e) { toast.error(e.response?.data?.error || 'Failed'); }
  };

  const handleDelete = async (id) => {
    try {
      await webhooks.delete(botId, groupId, id);
      setHookList(prev => prev.filter(h => h.id !== id));
      toast.success('Deleted');
    } catch { toast.error('Failed to delete'); }
  };

  const handleToggle = async (hook) => {
    try {
      await webhooks.update(botId, groupId, hook.id, { is_active: !hook.is_active });
      setHookList(prev => prev.map(h => h.id === hook.id ? { ...h, is_active: !h.is_active } : h));
    } catch { toast.error('Failed to update'); }
  };

  const openEdit = (hook) => {
    setEditHook(hook);
    setForm({ name: hook.name, description: hook.description || '', message_template: hook.message_template });
    setOpen(true);
  };

  const copyUrl = (token) => {
    navigator.clipboard.writeText(`${API_BASE}/api/webhooks/${token}/trigger`);
    toast.success('Webhook URL copied!');
  };

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Typography variant="h6" fontWeight={600}>Webhook Integrations</Typography>
        <Button variant="contained" startIcon={<Add />} onClick={() => { setEditHook(null); setForm({ name: '', description: '', message_template: '📡 *{name}*\n\n{payload}' }); setOpen(true); }}>
          Add Webhook
        </Button>
      </Box>

      <Alert severity="info" sx={{ mb: 2 }}>
        Webhooks let external services (GitHub, price feeds, custom scripts) send messages to your group. Send a POST request with JSON body to the webhook URL.
        Template variables: <strong>{'{name}'}</strong>, <strong>{'{payload}'}</strong>, or any JSON key from the POST body.
      </Alert>

      {hookList.length === 0 ? (
        <Card><CardContent><Typography color="text.secondary" align="center">No webhooks created yet.</Typography></CardContent></Card>
      ) : (
        hookList.map(hook => (
          <Card key={hook.id} sx={{ mb: 1.5 }}>
            <CardContent sx={{ pb: '12px !important' }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Webhook color={hook.is_active ? 'primary' : 'disabled'} />
                  <Typography fontWeight={600}>{hook.name}</Typography>
                  <Chip label={hook.is_active ? 'Active' : 'Inactive'} size="small" color={hook.is_active ? 'success' : 'default'} />
                </Box>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                  <Switch size="small" checked={hook.is_active} onChange={() => handleToggle(hook)} />
                  <Tooltip title="Copy webhook URL">
                    <IconButton size="small" onClick={() => copyUrl(hook.webhook_token)}><ContentCopy fontSize="small" /></IconButton>
                  </Tooltip>
                  <IconButton size="small" onClick={() => openEdit(hook)}><Edit fontSize="small" /></IconButton>
                  <IconButton size="small" color="error" onClick={() => handleDelete(hook.id)}><Delete fontSize="small" /></IconButton>
                  <IconButton size="small" onClick={() => setExpanded(p => ({ ...p, [hook.id]: !p[hook.id] }))}>
                    {expanded[hook.id] ? <ExpandLess /> : <ExpandMore />}
                  </IconButton>
                </Box>
              </Box>
              {hook.description && <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>{hook.description}</Typography>}
              <Collapse in={expanded[hook.id]}>
                <Box sx={{ mt: 1.5, p: 1.5, bgcolor: 'background.paper', borderRadius: 1, border: '1px solid', borderColor: 'divider' }}>
                  <Typography variant="caption" color="text.secondary" display="block" mb={0.5}>Webhook URL (POST to this):</Typography>
                  <Typography variant="body2" sx={{ fontFamily: 'monospace', wordBreak: 'break-all', fontSize: 12 }}>
                    {`${API_BASE}/api/webhooks/${hook.webhook_token}/trigger`}
                  </Typography>
                  <Divider sx={{ my: 1 }} />
                  <Typography variant="caption" color="text.secondary" display="block" mb={0.5}>Message template:</Typography>
                  <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', fontFamily: 'monospace', fontSize: 12 }}>{hook.message_template}</Typography>
                </Box>
              </Collapse>
            </CardContent>
          </Card>
        ))
      )}

      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{editHook ? 'Edit Webhook' : 'Create Webhook'}</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 0.5 }}>
            <Grid item xs={12}>
              <TextField fullWidth label="Name" value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))} />
            </Grid>
            <Grid item xs={12}>
              <TextField fullWidth label="Description (optional)" value={form.description} onChange={e => setForm(p => ({ ...p, description: e.target.value }))} />
            </Grid>
            <Grid item xs={12}>
              <TextField fullWidth multiline rows={4} label="Message Template"
                helperText="Use {name}, {payload}, or any JSON key from POST body"
                value={form.message_template} onChange={e => setForm(p => ({ ...p, message_template: e.target.value }))} />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={handleCreate}>{editHook ? 'Save' : 'Create'}</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
