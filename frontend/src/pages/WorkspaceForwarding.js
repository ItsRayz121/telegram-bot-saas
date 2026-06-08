import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Typography, Card, CardContent, Button, IconButton, Chip,
  Dialog, DialogTitle, DialogContent, DialogActions, TextField,
  Switch, FormControlLabel, Select, MenuItem, FormControl, InputLabel,
  Alert, CircularProgress, Divider, Tabs, Tab, Collapse, Tooltip,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
} from '@mui/material';
import {
  Add, Delete, Send, ExpandMore, ExpandLess, CheckCircle,
  Cancel, ArrowBack, FilterList, PlayArrow, Pause,
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { toast } from 'react-toastify';
import { forwarding as fwdApi, telegramGroups as tgApi } from '../services/api';
import PlanGate from '../components/PlanGate';

function _getUser() {
  try { return JSON.parse(localStorage.getItem('user') || '{}'); } catch { return {}; }
}

const STATUS_COLOR = {
  forwarded: 'success',
  approved: 'success',
  pending_approval: 'warning',
  rejected: 'error',
  failed: 'error',
};

const EMPTY_RULE = {
  rule_name: '',
  source_group_id: '',
  source_topic_link: '',
  keyword_filter: '',
  match_type: 'contains',
  prefix_text: '',
  suffix_text: '',
  require_approval: false,
};

// One blank destination row: a chat id/@username + an optional forum topic link.
const EMPTY_DEST = { chat_id: '', topic_link: '' };

// ── Rule log drawer ─────────────────────────────────────────────────────────

function RuleLogs({ ruleId, open }) {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || !ruleId) return;
    setLoading(true);
    fwdApi.getRuleLogs(ruleId, { per_page: 20 })
      .then(r => setLogs(r.data.logs || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [open, ruleId]);

  if (!open) return null;

  return (
    <Box sx={{ px: 2, pb: 2 }}>
      <Divider sx={{ mb: 2 }} />
      <Typography variant="caption" color="text.secondary" fontWeight={700} display="block" mb={1}>
        Recent Activity
      </Typography>
      {loading ? (
        <CircularProgress size={18} />
      ) : logs.length === 0 ? (
        <Typography variant="caption" color="text.disabled">No forwarding activity yet.</Typography>
      ) : (
        <TableContainer sx={{ overflowX: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell sx={{ fontSize: '0.7rem', py: 0.5 }}>Time</TableCell>
                <TableCell sx={{ fontSize: '0.7rem', py: 0.5 }}>Status</TableCell>
                <TableCell sx={{ fontSize: '0.7rem', py: 0.5 }}>Message preview</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {logs.map(l => (
                <TableRow key={l.id}>
                  <TableCell sx={{ fontSize: '0.7rem', py: 0.5, whiteSpace: 'nowrap' }}>
                    {new Date(l.created_at).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                  </TableCell>
                  <TableCell sx={{ py: 0.5 }}>
                    <Chip label={l.status} color={STATUS_COLOR[l.status] || 'default'} size="small" sx={{ height: 16, fontSize: '0.62rem' }} />
                  </TableCell>
                  <TableCell sx={{ fontSize: '0.7rem', py: 0.5, maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {l.source_text || <em style={{ color: '#64748b' }}>media / no text</em>}
                    {l.error_msg && <Typography variant="caption" color="error.main" display="block">{l.error_msg}</Typography>}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </Box>
  );
}

// ── Rule card ────────────────────────────────────────────────────────────────

function RuleCard({ rule, groups, onToggle, onDelete, onEdit }) {
  const [logsOpen, setLogsOpen] = useState(false);
  const sourceGroup = groups.find(g => g.telegram_group_id === rule.source_group_id);

  return (
    <Card sx={{ mb: 2, opacity: rule.is_active ? 1 : 0.65, transition: 'opacity 0.2s' }}>
      <CardContent sx={{ p: 2, '&:last-child': { pb: logsOpen ? 0 : 2 } }}>
        <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1.5 }}>
          <Box sx={{ p: 1.25, borderRadius: 2, bgcolor: 'rgba(6,182,212,0.1)', flexShrink: 0, mt: 0.25 }}>
            <Send sx={{ fontSize: 18, color: 'info.main' }} />
          </Box>

          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap', mb: 0.5 }}>
              <Typography fontWeight={700} fontSize="0.9rem">{rule.rule_name}</Typography>
              {rule.require_approval && (
                <Chip label="Approval required" size="small" color="warning" sx={{ height: 18, fontSize: '0.62rem' }} />
              )}
              {!rule.is_active && (
                <Chip label="Paused" size="small" sx={{ height: 18, fontSize: '0.62rem' }} />
              )}
            </Box>

            <Typography variant="caption" color="text.secondary" display="block">
              <strong>From:</strong> {sourceGroup?.name || rule.source_group_id}
              {rule.source_topic_id ? ` (topic ${rule.source_topic_id})` : ''}
            </Typography>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mt: 0.5 }}>
              <Typography variant="caption" color="text.secondary"><strong>To:</strong></Typography>
              {(rule.destinations && rule.destinations.length
                ? rule.destinations
                : [{ destination_id: rule.destination_id }]
              ).map((d, i) => (
                <Chip
                  key={`${d.destination_id}-${i}`}
                  size="small"
                  variant="outlined"
                  color={d.is_paused ? 'error' : 'default'}
                  label={`${d.destination_id}${d.topic_id ? ` › topic ${d.topic_id}` : ''}${d.is_paused ? ' (paused)' : ''}`}
                  sx={{ height: 18, fontSize: '0.62rem' }}
                />
              ))}
            </Box>

            {rule.keyword_filter && (
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mt: 0.75 }}>
                <FilterList sx={{ fontSize: 13, color: 'text.disabled', mt: '1px' }} />
                {rule.keyword_filter.split(',').map(k => k.trim()).filter(Boolean).map(k => (
                  <Chip key={k} label={k} size="small" variant="outlined" sx={{ height: 16, fontSize: '0.62rem' }} />
                ))}
              </Box>
            )}

            <Typography variant="caption" color="text.disabled" display="block" mt={0.5}>
              {rule.forward_count} forwarded total
            </Typography>
          </Box>

          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, flexShrink: 0 }}>
            <Tooltip title={rule.is_active ? 'Pause rule' : 'Activate rule'}>
              <IconButton size="small" onClick={() => onToggle(rule.id)}>
                {rule.is_active ? <Pause fontSize="small" /> : <PlayArrow fontSize="small" />}
              </IconButton>
            </Tooltip>
            <Tooltip title="Delete rule">
              <IconButton size="small" color="error" onClick={() => onDelete(rule.id)}>
                <Delete fontSize="small" />
              </IconButton>
            </Tooltip>
            <IconButton size="small" onClick={() => setLogsOpen(o => !o)}>
              {logsOpen ? <ExpandLess fontSize="small" /> : <ExpandMore fontSize="small" />}
            </IconButton>
          </Box>
        </Box>

        <Collapse in={logsOpen}>
          <RuleLogs ruleId={rule.id} open={logsOpen} />
        </Collapse>
      </CardContent>
    </Card>
  );
}

// ── Create dialog ────────────────────────────────────────────────────────────

function CreateRuleDialog({ open, onClose, onCreated, groups, fixedSource }) {
  const [form, setForm] = useState(EMPTY_RULE);
  const [dests, setDests] = useState([{ ...EMPTY_DEST }]);
  const [saving, setSaving] = useState(false);

  const set = (field) => (e) => setForm(f => ({ ...f, [field]: e.target.value }));
  const setCheck = (field) => (e) => setForm(f => ({ ...f, [field]: e.target.checked }));

  const setDest = (idx, field) => (e) => setDests(ds =>
    ds.map((d, i) => i === idx ? { ...d, [field]: e.target.value } : d));
  const addDest = () => setDests(ds => [...ds, { ...EMPTY_DEST }]);
  const removeDest = (idx) => setDests(ds => ds.length > 1 ? ds.filter((_, i) => i !== idx) : ds);

  const handleSubmit = async () => {
    if (!form.rule_name.trim()) { toast.error('Rule name is required'); return; }
    const sourceId = fixedSource || form.source_group_id;
    if (!sourceId) { toast.error('Select a source group'); return; }
    const cleanDests = dests
      .map(d => ({ chat_id: (d.chat_id || '').trim(), topic_link: (d.topic_link || '').trim() }))
      .filter(d => d.chat_id);
    if (cleanDests.length === 0) { toast.error('Add at least one destination'); return; }
    setSaving(true);
    try {
      const payload = {
        rule_name: form.rule_name,
        keyword_filter: form.keyword_filter,
        match_type: form.match_type,
        prefix_text: form.prefix_text,
        suffix_text: form.suffix_text,
        require_approval: form.require_approval,
        sources: [{ chat_id: sourceId, topic_link: form.source_topic_link || '' }],
        destinations: cleanDests,
      };
      const res = await fwdApi.createRule(payload);
      (res.data.warnings || []).forEach(w => toast.warn(w, { autoClose: 8000 }));
      onCreated(res.data.rule);
      setForm(EMPTY_RULE);
      setDests([{ ...EMPTY_DEST }]);
      onClose();
      toast.success('Forwarding rule created');
    } catch (e) {
      toast.error(e.response?.data?.error || 'Failed to create rule');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle fontWeight={700}>New Forwarding Rule</DialogTitle>
      <DialogContent sx={{ pt: 1 }}>
        <TextField
          fullWidth label="Rule name" size="small" sx={{ mb: 2, mt: 1 }}
          value={form.rule_name} onChange={set('rule_name')}
          placeholder="e.g. Announcements → Community Chat"
        />

        {!fixedSource && (
          <FormControl fullWidth size="small" sx={{ mb: 2 }}>
            <InputLabel>Source group</InputLabel>
            <Select label="Source group" value={form.source_group_id} onChange={set('source_group_id')}>
              {groups.map(g => (
                <MenuItem key={g.telegram_group_id} value={g.telegram_group_id}>{g.name}</MenuItem>
              ))}
            </Select>
          </FormControl>
        )}

        <TextField
          fullWidth label="Source topic link (optional)" size="small" sx={{ mb: 2 }}
          value={form.source_topic_link} onChange={set('source_topic_link')}
          helperText="Only forward from this forum topic. Paste the topic link, e.g. https://t.me/c/123.../45"
        />

        <Divider sx={{ mb: 1.5 }}><Typography variant="caption" color="text.secondary">Destinations</Typography></Divider>
        {dests.map((d, idx) => (
          <Box key={idx} sx={{ display: 'flex', gap: 1, mb: 1.5, alignItems: 'flex-start' }}>
            <Box sx={{ flex: 1 }}>
              <TextField
                fullWidth label={`Destination ${idx + 1} — chat ID or @username`} size="small"
                value={d.chat_id} onChange={setDest(idx, 'chat_id')}
                helperText="The bot must be an admin of this chat"
              />
              <TextField
                fullWidth label="Topic link (optional)" size="small" sx={{ mt: 1 }}
                value={d.topic_link} onChange={setDest(idx, 'topic_link')}
                placeholder="Paste a forum topic link to deliver into that topic"
              />
            </Box>
            <IconButton size="small" color="error" onClick={() => removeDest(idx)}
              disabled={dests.length === 1} sx={{ mt: 0.5 }}>
              <Delete fontSize="small" />
            </IconButton>
          </Box>
        ))}
        <Button size="small" startIcon={<Add />} onClick={addDest} sx={{ mb: 2 }}>
          Add destination
        </Button>

        <TextField
          fullWidth label="Keyword filter (optional)" size="small" sx={{ mb: 2 }}
          value={form.keyword_filter} onChange={set('keyword_filter')}
          helperText="Comma-separated keywords — leave blank to forward every message"
        />

        <FormControl fullWidth size="small" sx={{ mb: 2 }}>
          <InputLabel>Match type</InputLabel>
          <Select label="Match type" value={form.match_type} onChange={set('match_type')}>
            <MenuItem value="contains">Contains keyword</MenuItem>
            <MenuItem value="starts_with">Starts with keyword</MenuItem>
          </Select>
        </FormControl>

        <TextField
          fullWidth label="Prefix text (optional)" size="small" sx={{ mb: 2 }}
          value={form.prefix_text} onChange={set('prefix_text')}
          placeholder="e.g. 📢 From #announcements:"
        />
        <TextField
          fullWidth label="Suffix text (optional)" size="small" sx={{ mb: 2 }}
          value={form.suffix_text} onChange={set('suffix_text')}
          placeholder="e.g. — Telegizer AutoForward"
        />

        <FormControlLabel
          control={<Switch checked={form.require_approval} onChange={setCheck('require_approval')} />}
          label={
            <Box>
              <Typography variant="body2" fontWeight={600}>Require approval</Typography>
              <Typography variant="caption" color="text.secondary">
                Messages queue for your manual review before being forwarded
              </Typography>
            </Box>
          }
        />
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose} disabled={saving}>Cancel</Button>
        <Button variant="contained" onClick={handleSubmit} disabled={saving}
          startIcon={saving ? <CircularProgress size={16} color="inherit" /> : null}>
          Create Rule
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// ── Pending approval tab ─────────────────────────────────────────────────────

function PendingTab({ rules, embeddedGroupId = null }) {
  const [pending, setPending] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    fwdApi.listPending()
      .then(r => {
        let ps = r.data.pending || [];
        if (embeddedGroupId) ps = ps.filter(p => String(p.source_chat_id) === String(embeddedGroupId));
        setPending(ps);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [embeddedGroupId]);

  useEffect(() => { load(); }, [load]);

  const handle = async (logId, action) => {
    try {
      if (action === 'approve') await fwdApi.approvePending(logId);
      else await fwdApi.rejectPending(logId);
      toast.success(action === 'approve' ? 'Forwarded' : 'Rejected');
      load();
    } catch (e) {
      toast.error(e.response?.data?.error || 'Action failed');
    }
  };

  if (loading) return <Box sx={{ py: 4, textAlign: 'center' }}><CircularProgress size={24} /></Box>;

  if (pending.length === 0) {
    return (
      <Box sx={{ py: 6, textAlign: 'center' }}>
        <CheckCircle sx={{ fontSize: 48, color: 'success.main', mb: 1 }} />
        <Typography color="text.secondary">No messages waiting for approval.</Typography>
      </Box>
    );
  }

  return (
    <Box>
      {pending.map(p => {
        const rule = rules.find(r => r.id === p.rule_id);
        return (
          <Card key={p.id} sx={{ mb: 1.5 }}>
            <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
              <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 2 }}>
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography variant="caption" color="text.secondary" display="block" mb={0.5}>
                    Rule: <strong>{rule?.rule_name || `#${p.rule_id}`}</strong> →{' '}
                    {new Date(p.created_at).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                  </Typography>
                  <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                    {p.source_text || <em>Media message (no text)</em>}
                  </Typography>
                  <Typography variant="caption" color="text.disabled" display="block" mt={0.5}>
                    Destination: {p.destination_id}
                  </Typography>
                </Box>
                <Box sx={{ display: 'flex', gap: 1, flexShrink: 0 }}>
                  <Button size="small" variant="contained" color="success"
                    startIcon={<CheckCircle fontSize="small" />}
                    onClick={() => handle(p.id, 'approve')}>
                    Forward
                  </Button>
                  <Button size="small" variant="outlined" color="error"
                    startIcon={<Cancel fontSize="small" />}
                    onClick={() => handle(p.id, 'reject')}>
                    Reject
                  </Button>
                </Box>
              </Box>
            </CardContent>
          </Card>
        );
      })}
    </Box>
  );
}

// ── Main page ────────────────────────────────────────────────────────────────

export default function WorkspaceForwarding({ embeddedGroupId = null, embeddedGroupName = null }) {
  const navigate = useNavigate();
  const embedded = !!embeddedGroupId;
  const [rules, setRules] = useState([]);
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState(0);
  const [createOpen, setCreateOpen] = useState(false);
  const [pendingCount, setPendingCount] = useState(0);

  const loadRules = useCallback(() => {
    fwdApi.listRules()
      .then(r => {
        let rs = r.data.rules || [];
        if (embeddedGroupId) rs = rs.filter(x => String(x.source_group_id) === String(embeddedGroupId));
        setRules(rs);
      })
      .catch(() => toast.error('Failed to load forwarding rules'))
      .finally(() => setLoading(false));
  }, [embeddedGroupId]);

  useEffect(() => {
    loadRules();
    tgApi.list().then(r => setGroups(r.data.groups || [])).catch(() => {});
    fwdApi.listPending().then(r => {
      let ps = r.data.pending || [];
      if (embeddedGroupId) ps = ps.filter(p => String(p.source_chat_id) === String(embeddedGroupId));
      setPendingCount(ps.length);
    }).catch(() => {});
  }, [loadRules, embeddedGroupId]);

  const handleToggle = async (id) => {
    try {
      const res = await fwdApi.toggleRule(id);
      setRules(prev => prev.map(r => r.id === id ? res.data.rule : r));
    } catch { toast.error('Failed to toggle rule'); }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this forwarding rule? This also deletes its log.')) return;
    try {
      await fwdApi.deleteRule(id);
      setRules(prev => prev.filter(r => r.id !== id));
      toast.success('Rule deleted');
    } catch { toast.error('Failed to delete rule'); }
  };

  const handleCreated = (rule) => {
    setRules(prev => [rule, ...prev]);
  };

  const user = _getUser();

  return (
    <PlanGate plan="pro" userTier={user.subscription_tier} feature="Message Forwarding">
    <Box sx={{ p: embedded ? 0 : { xs: 2, md: 4 }, maxWidth: embedded ? '100%' : 900, mx: 'auto' }}>

      {/* Header */}
      {!embedded && (
        <>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
            <IconButton size="small" onClick={() => navigate('/workspace')} sx={{ mr: 0.5 }}>
              <ArrowBack fontSize="small" />
            </IconButton>
            <Send sx={{ color: 'info.main' }} />
            <Typography variant="h5" fontWeight={700}>Message Forwarding</Typography>
          </Box>
          <Typography color="text.secondary" mb={3} pl={6}>
            Automatically copy messages from one group to another — with keyword filters, prefix/suffix templates, and approval queues.
          </Typography>
        </>
      )}

      <Alert severity="info" sx={{ mb: 3 }}>
        {embedded
          ? <>Forwarding rules sourced from <strong>{embeddedGroupName || 'this group'}</strong>. The bot must be an admin of every destination chat.</>
          : <>The bot must be a <strong>member or admin</strong> of the destination chat to forward messages.
            Use the chat's numeric ID (e.g. <code>-1001234567890</code>) or public <code>@username</code>.</>}
      </Alert>

      {/* Tabs */}
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 3 }}>
        <Tabs value={tab} onChange={(_, v) => setTab(v)}>
          <Tab label={`Rules (${rules.length})`} />
          <Tab label={
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
              Pending approval
              {pendingCount > 0 && (
                <Chip label={pendingCount} size="small" color="warning" sx={{ height: 18, fontSize: '0.62rem' }} />
              )}
            </Box>
          } />
        </Tabs>
        {tab === 0 && (
          <Button variant="contained" startIcon={<Add />} onClick={() => setCreateOpen(true)}>
            New Rule
          </Button>
        )}
      </Box>

      {/* Tab 0 — Rules */}
      {tab === 0 && (
        loading ? (
          <Box sx={{ py: 6, textAlign: 'center' }}><CircularProgress /></Box>
        ) : rules.length === 0 ? (
          <Card>
            <CardContent sx={{ py: 6, textAlign: 'center' }}>
              <Send sx={{ fontSize: 48, color: 'text.disabled', mb: 1.5 }} />
              <Typography variant="h6" fontWeight={600} gutterBottom>No forwarding rules yet</Typography>
              <Typography variant="body2" color="text.secondary" mb={3} maxWidth={400} mx="auto">
                Create a rule to automatically copy messages from a source group to any destination chat — channel, group, or DM.
              </Typography>
              <Button variant="contained" startIcon={<Add />} onClick={() => setCreateOpen(true)}>
                Create your first rule
              </Button>
            </CardContent>
          </Card>
        ) : (
          rules.map(rule => (
            <RuleCard
              key={rule.id}
              rule={rule}
              groups={groups}
              onToggle={handleToggle}
              onDelete={handleDelete}
            />
          ))
        )
      )}

      {/* Tab 1 — Pending */}
      {tab === 1 && <PendingTab rules={rules} embeddedGroupId={embeddedGroupId} />}

      <CreateRuleDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={handleCreated}
        groups={groups}
        fixedSource={embeddedGroupId}
      />
    </Box>
    </PlanGate>
  );
}
