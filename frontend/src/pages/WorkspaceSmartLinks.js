import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Typography, Card, CardContent, Button, IconButton, Chip,
  Dialog, DialogTitle, DialogContent, DialogActions, TextField,
  Switch, FormControlLabel, ToggleButton, ToggleButtonGroup,
  Tooltip, CircularProgress, Alert, Divider, Select,
  MenuItem, FormControl, InputLabel,
} from '@mui/material';
import {
  Add, Edit, Delete, Link, Public, Groups,
  CalendarMonth, Slideshow, Language, Support, QuestionAnswer,
  MenuBook, Sell, VideoCall, CheckCircle,
} from '@mui/icons-material';
import { toast } from 'react-toastify';
import { workspace as wsApi, telegramGroups as tgApi } from '../services/api';

// ── Quick-add presets ──────────────────────────────────────────────────────────

const PRESETS = [
  { icon: CalendarMonth, label: 'Calendly',   triggers: 'calendly,book a call,schedule,book meeting', url: '', placeholder: 'https://calendly.com/yourlink' },
  { icon: Slideshow,     label: 'Pitch Deck', triggers: 'pitch deck,deck,presentation,slides',         url: '', placeholder: 'https://drive.google.com/...' },
  { icon: Language,      label: 'Website',    triggers: 'website,site,homepage,your site',             url: '', placeholder: 'https://yourdomain.com' },
  { icon: Support,       label: 'Support',    triggers: 'support,help,contact,issue,problem',          url: '', placeholder: 'https://t.me/your_support' },
  { icon: QuestionAnswer,label: 'FAQ',        triggers: 'faq,questions,common questions,help guide',   url: '', placeholder: 'https://...' },
  { icon: MenuBook,      label: 'Docs',       triggers: 'docs,documentation,guide,manual',             url: '', placeholder: 'https://docs.yoursite.com' },
  { icon: Sell,          label: 'Pricing',    triggers: 'pricing,price,cost,how much,plans',           url: '', placeholder: 'https://yoursite.com/pricing' },
  { icon: VideoCall,     label: 'Demo',       triggers: 'demo,book demo,see demo,request demo',        url: '', placeholder: 'https://calendly.com/demo' },
];

// ── Helpers ────────────────────────────────────────────────────────────────────

const SCOPE_LABEL = { user: 'All groups', group: 'Specific group' };

function scopeColor(scope) {
  return scope === 'user' ? 'primary' : 'default';
}

// ── SmartLink card ─────────────────────────────────────────────────────────────

function SmartLinkCard({ link, groups, onEdit, onDelete, onToggle }) {
  const triggers = link.trigger_text.split(',').map(t => t.trim()).filter(Boolean);
  const groupName = groups.find(g => g.telegram_group_id === link.telegram_group_id)?.name;

  return (
    <Card sx={{ mb: 1.5, opacity: link.is_enabled ? 1 : 0.55, transition: 'opacity 0.2s' }}>
      <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
        <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1.5 }}>

          {/* Icon */}
          <Box sx={{ p: 1, borderRadius: 1.5, bgcolor: 'rgba(37,99,235,0.1)', flexShrink: 0, mt: 0.25 }}>
            <Link sx={{ fontSize: 18, color: 'primary.main' }} />
          </Box>

          {/* Content */}
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap', mb: 0.5 }}>
              <Typography fontWeight={700} fontSize="0.9rem">{link.link_label || 'Smart Link'}</Typography>
              <Chip label={SCOPE_LABEL[link.scope] || link.scope} size="small" color={scopeColor(link.scope)} sx={{ height: 18, fontSize: '0.62rem' }} />
              {link.scope === 'group' && groupName && (
                <Chip label={groupName} size="small" sx={{ height: 18, fontSize: '0.62rem' }} />
              )}
            </Box>

            {/* Trigger phrases */}
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mb: 0.75 }}>
              {triggers.map(t => (
                <Chip key={t} label={`"${t}"`} size="small" variant="outlined"
                  sx={{ height: 18, fontSize: '0.65rem', borderColor: 'divider' }} />
              ))}
            </Box>

            {/* URL or text */}
            {link.link_url ? (
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                <Link sx={{ fontSize: 13, color: 'text.disabled' }} />
                <Typography fontSize="0.75rem" color="primary.light" noWrap
                  component="a" href={link.link_url} target="_blank" rel="noopener noreferrer"
                  sx={{ textDecoration: 'none', '&:hover': { textDecoration: 'underline' } }}>
                  {link.link_url}
                </Typography>
              </Box>
            ) : (
              <Typography fontSize="0.75rem" color="text.secondary" noWrap>
                {link.response_text}
              </Typography>
            )}
          </Box>

          {/* Actions */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, flexShrink: 0 }}>
            <Tooltip title={link.is_enabled ? 'Disable' : 'Enable'}>
              <Switch size="small" checked={link.is_enabled} onChange={() => onToggle(link)} />
            </Tooltip>
            <Tooltip title="Edit">
              <IconButton size="small" onClick={() => onEdit(link)}><Edit fontSize="small" /></IconButton>
            </Tooltip>
            <Tooltip title="Delete">
              <IconButton size="small" color="error" onClick={() => onDelete(link)}><Delete fontSize="small" /></IconButton>
            </Tooltip>
          </Box>
        </Box>
      </CardContent>
    </Card>
  );
}

// ── Create / Edit dialog ───────────────────────────────────────────────────────

const EMPTY_FORM = {
  link_label: '',
  trigger_text: '',
  link_url: '',
  response_text: '',
  match_type: 'contains',
  scope: 'user',
  telegram_group_id: '',
  is_case_sensitive: false,
};

function SmartLinkDialog({ open, onClose, onSave, initial, groups }) {
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setForm(initial ? { ...EMPTY_FORM, ...initial } : EMPTY_FORM);
  }, [initial, open]);

  const set = (field) => (e) => setForm(f => ({ ...f, [field]: e.target.value }));
  const setVal = (field, val) => setForm(f => ({ ...f, [field]: val }));

  const handlePreset = (preset) => {
    setForm(f => ({
      ...f,
      link_label: preset.label,
      trigger_text: preset.triggers,
      link_url: f.link_url || preset.placeholder || '',
    }));
  };

  const handleSave = async () => {
    if (!form.link_label.trim()) { toast.error('Name is required'); return; }
    if (!form.trigger_text.trim()) { toast.error('At least one trigger phrase is required'); return; }
    if (!form.link_url.trim() && !form.response_text.trim()) {
      toast.error('URL or response text is required'); return;
    }
    setSaving(true);
    try {
      await onSave({
        ...form,
        response_text: form.response_text || form.link_url,
        telegram_group_id: form.scope === 'group' ? form.telegram_group_id : null,
      });
      onClose();
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle fontWeight={700}>{initial ? 'Edit Smart Link' : 'Add Smart Link'}</DialogTitle>
      <DialogContent sx={{ pt: 1 }}>

        {/* Quick-add presets (only on create) */}
        {!initial && (
          <Box sx={{ mb: 2 }}>
            <Typography variant="caption" color="text.secondary" display="block" mb={0.75}>
              Quick add a preset:
            </Typography>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.75 }}>
              {PRESETS.map(p => (
                <Button key={p.label} size="small" variant="outlined" startIcon={<p.icon fontSize="small" />}
                  sx={{ py: 0.4, fontSize: '0.75rem' }}
                  onClick={() => handlePreset(p)}>
                  {p.label}
                </Button>
              ))}
            </Box>
          </Box>
        )}

        <Divider sx={{ mb: 2 }} />

        <TextField
          label="Name *"
          placeholder="e.g. Calendly Link"
          value={form.link_label}
          onChange={set('link_label')}
          fullWidth sx={{ mb: 2 }}
          inputProps={{ maxLength: 100 }}
          helperText="A short label for your own reference"
        />

        <TextField
          label="Trigger phrases *"
          placeholder="calendly, book a call, schedule, appointment"
          value={form.trigger_text}
          onChange={set('trigger_text')}
          fullWidth sx={{ mb: 2 }}
          helperText="Comma-separated. Bot replies when any of these appear in a message."
          inputProps={{ maxLength: 500 }}
        />

        <TextField
          label="URL"
          placeholder="https://calendly.com/yourlink"
          value={form.link_url}
          onChange={set('link_url')}
          fullWidth sx={{ mb: 2 }}
          helperText="The link the bot will share. Leave empty to use custom text instead."
        />

        {!form.link_url && (
          <TextField
            label="Response text *"
            placeholder="Here's the link: ..."
            value={form.response_text}
            onChange={set('response_text')}
            fullWidth multiline rows={2} sx={{ mb: 2 }}
            helperText="Used when no URL is set."
          />
        )}

        {/* Scope */}
        <FormControl fullWidth sx={{ mb: 2 }}>
          <InputLabel>Scope</InputLabel>
          <Select value={form.scope} label="Scope"
            onChange={e => setVal('scope', e.target.value)}>
            <MenuItem value="user">
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <Public fontSize="small" />All my groups (global)
              </Box>
            </MenuItem>
            <MenuItem value="group">
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <Groups fontSize="small" />Specific group only
              </Box>
            </MenuItem>
          </Select>
        </FormControl>

        {form.scope === 'group' && (
          <FormControl fullWidth sx={{ mb: 2 }}>
            <InputLabel>Group</InputLabel>
            <Select value={form.telegram_group_id} label="Group"
              onChange={e => setVal('telegram_group_id', e.target.value)}>
              {groups.map(g => (
                <MenuItem key={g.id} value={g.telegram_group_id}>{g.name}</MenuItem>
              ))}
            </Select>
          </FormControl>
        )}

        {/* Match type */}
        <Box sx={{ mb: 1 }}>
          <Typography variant="caption" color="text.secondary" display="block" mb={0.5}>
            Match type
          </Typography>
          <ToggleButtonGroup exclusive size="small" value={form.match_type}
            onChange={(_, v) => v && setVal('match_type', v)}>
            <ToggleButton value="contains" sx={{ fontSize: '0.75rem', px: 1.5 }}>Contains</ToggleButton>
            <ToggleButton value="exact"    sx={{ fontSize: '0.75rem', px: 1.5 }}>Exact</ToggleButton>
            <ToggleButton value="starts_with" sx={{ fontSize: '0.75rem', px: 1.5 }}>Starts with</ToggleButton>
          </ToggleButtonGroup>
        </Box>

        <FormControlLabel
          control={<Switch size="small" checked={form.is_case_sensitive}
            onChange={e => setVal('is_case_sensitive', e.target.checked)} />}
          label={<Typography fontSize="0.82rem">Case sensitive</Typography>}
        />

      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose} disabled={saving}>Cancel</Button>
        <Button variant="contained" onClick={handleSave} disabled={saving}
          startIcon={saving ? <CircularProgress size={14} /> : <CheckCircle fontSize="small" />}>
          {saving ? 'Saving…' : 'Save Link'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// ── Delete confirmation ────────────────────────────────────────────────────────

function DeleteDialog({ open, link, onClose, onConfirm }) {
  const [deleting, setDeleting] = useState(false);
  const handleConfirm = async () => {
    setDeleting(true);
    await onConfirm();
    setDeleting(false);
    onClose();
  };
  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle fontWeight={700}>Delete Smart Link</DialogTitle>
      <DialogContent>
        <Typography>
          Delete <strong>{link?.link_label}</strong>? The bot will stop auto-replying to its trigger phrases.
        </Typography>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose} disabled={deleting}>Cancel</Button>
        <Button variant="contained" color="error" onClick={handleConfirm} disabled={deleting}
          startIcon={deleting ? <CircularProgress size={14} /> : <Delete fontSize="small" />}>
          {deleting ? 'Deleting…' : 'Delete'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function WorkspaceSmartLinks() {
  const [links, setLinks] = useState([]);
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editTarget, setEditTarget] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);

  const load = useCallback(async () => {
    try {
      const [linksRes, groupsRes] = await Promise.all([
        wsApi.listSmartLinks(),
        tgApi.list(),
      ]);
      setLinks(linksRes.data.smart_links || []);
      setGroups(groupsRes.data.groups || []);
    } catch {
      toast.error('Failed to load smart links');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleSave = async (form) => {
    if (editTarget) {
      const res = await wsApi.updateSmartLink(editTarget.id, form);
      setLinks(l => l.map(x => x.id === editTarget.id ? res.data.smart_link : x));
      toast.success('Smart link updated');
    } else {
      const res = await wsApi.createSmartLink(form);
      setLinks(l => [res.data.smart_link, ...l]);
      toast.success('Smart link created');
    }
    setEditTarget(null);
  };

  const handleToggle = async (link) => {
    try {
      const res = await wsApi.toggleSmartLink(link.id);
      setLinks(l => l.map(x => x.id === link.id ? res.data.smart_link : x));
    } catch {
      toast.error('Failed to toggle');
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    await wsApi.deleteSmartLink(deleteTarget.id);
    setLinks(l => l.filter(x => x.id !== deleteTarget.id));
    toast.success('Deleted');
  };

  const openCreate = () => { setEditTarget(null); setDialogOpen(true); };
  const openEdit = (link) => { setEditTarget(link); setDialogOpen(true); };

  const globalLinks = links.filter(l => l.scope === 'user');
  const groupLinks  = links.filter(l => l.scope === 'group');

  return (
    <Box sx={{ p: { xs: 2, md: 4 }, maxWidth: 800, mx: 'auto' }}>

      {/* Header */}
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 3 }}>
        <Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 0.5 }}>
            <Link sx={{ fontSize: 24, color: 'primary.main' }} />
            <Typography variant="h5" fontWeight={700}>Smart Links</Typography>
          </Box>
          <Typography color="text.secondary" fontSize="0.875rem">
            Save links and text. The bot auto-replies when someone asks in any of your groups.
          </Typography>
        </Box>
        <Button variant="contained" startIcon={<Add />} onClick={openCreate} sx={{ flexShrink: 0 }}>
          Add Link
        </Button>
      </Box>

      {/* How it works banner */}
      <Alert severity="info" sx={{ mb: 3 }} icon={<Link />}>
        <Typography variant="body2">
          <strong>How it works:</strong> When someone says "can you share the calendly?" or "what's the website?" in any of your groups, the bot replies automatically with your saved link. No extra setup needed.
        </Typography>
      </Alert>

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
          <CircularProgress />
        </Box>
      ) : links.length === 0 ? (
        /* Empty state */
        <Card sx={{ textAlign: 'center', py: 6 }}>
          <Link sx={{ fontSize: 48, color: 'text.disabled', mb: 2 }} />
          <Typography variant="h6" fontWeight={600} gutterBottom>No smart links yet</Typography>
          <Typography color="text.secondary" mb={3} fontSize="0.875rem">
            Add your Calendly, pitch deck, website, or any other link.<br />
            The bot will share it automatically when someone asks.
          </Typography>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, justifyContent: 'center', mb: 3 }}>
            {PRESETS.slice(0, 4).map(p => (
              <Button key={p.label} variant="outlined" size="small" startIcon={<p.icon fontSize="small" />}
                onClick={() => { setEditTarget(null); setDialogOpen(true); }}>
                {p.label}
              </Button>
            ))}
          </Box>
          <Button variant="contained" startIcon={<Add />} onClick={openCreate}>
            Add your first link
          </Button>
        </Card>
      ) : (
        <>
          {/* Global links */}
          {globalLinks.length > 0 && (
            <Box sx={{ mb: 3 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.5 }}>
                <Public sx={{ fontSize: 16, color: 'primary.main' }} />
                <Typography variant="subtitle2" fontWeight={700} color="primary.light">
                  All Groups ({globalLinks.length})
                </Typography>
                <Typography variant="caption" color="text.disabled">
                  — active in every group you manage
                </Typography>
              </Box>
              {globalLinks.map(link => (
                <SmartLinkCard key={link.id} link={link} groups={groups}
                  onEdit={openEdit} onDelete={setDeleteTarget} onToggle={handleToggle} />
              ))}
            </Box>
          )}

          {/* Group-specific links */}
          {groupLinks.length > 0 && (
            <Box>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.5 }}>
                <Groups sx={{ fontSize: 16, color: 'text.secondary' }} />
                <Typography variant="subtitle2" fontWeight={700} color="text.secondary">
                  Group-Specific ({groupLinks.length})
                </Typography>
              </Box>
              {groupLinks.map(link => (
                <SmartLinkCard key={link.id} link={link} groups={groups}
                  onEdit={openEdit} onDelete={setDeleteTarget} onToggle={handleToggle} />
              ))}
            </Box>
          )}
        </>
      )}

      {/* Create / Edit dialog */}
      <SmartLinkDialog
        open={dialogOpen}
        onClose={() => { setDialogOpen(false); setEditTarget(null); }}
        onSave={handleSave}
        initial={editTarget}
        groups={groups}
      />

      {/* Delete dialog */}
      <DeleteDialog
        open={Boolean(deleteTarget)}
        link={deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
      />
    </Box>
  );
}
