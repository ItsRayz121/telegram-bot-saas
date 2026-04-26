import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box, Container, Typography, Button, Card, CardContent,
  Chip, CircularProgress, Alert, Dialog, DialogTitle,
  DialogContent, DialogActions, TextField, IconButton,
  Tooltip, Grid, Divider, Paper,
} from '@mui/material';
import {
  Add, Groups, CheckCircle, HourglassEmpty, LinkOff,
  Settings, Refresh, ContentCopy, OpenInNew, Warning,
} from '@mui/icons-material';
import { toast } from 'react-toastify';
import { telegramGroups } from '../services/api';

const BOT_USERNAME = process.env.REACT_APP_BOT_USERNAME || 'telegizer_bot';

function StatusChip({ status }) {
  const map = {
    active: { label: 'Active', color: 'success' },
    pending: { label: 'Pending', color: 'warning' },
    removed: { label: 'Removed', color: 'error' },
    disabled: { label: 'Disabled', color: 'error' },
  };
  const { label, color } = map[status] || { label: status, color: 'default' };
  return <Chip label={label} color={color} size="small" />;
}

function PermBadge({ perms }) {
  if (!perms) return <Chip label="Unknown" color="default" size="small" />;
  const missing = Object.entries(perms).filter(([, v]) => !v).map(([k]) => k);
  if (missing.length === 0) return <Chip label="All Granted" color="success" size="small" />;
  return (
    <Tooltip title={`Missing: ${missing.join(', ')}`}>
      <Chip label={`${missing.length} Missing`} color="warning" size="small" icon={<Warning fontSize="small" />} />
    </Tooltip>
  );
}

export default function MyGroups() {
  const navigate = useNavigate();
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [linkOpen, setLinkOpen] = useState(false);
  const [linkCode, setLinkCode] = useState('');
  const [linking, setLinking] = useState(false);
  const [unlinkTarget, setUnlinkTarget] = useState(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const res = await telegramGroups.list();
      setGroups(res.data.groups || []);
    } catch {
      toast.error('Failed to load groups');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleLink = async () => {
    if (!linkCode.trim()) return;
    setLinking(true);
    try {
      const res = await telegramGroups.link({ code: linkCode.trim().toUpperCase() });
      toast.success(`Group "${res.data.group.title}" linked successfully!`);
      setLinkOpen(false);
      setLinkCode('');
      load();
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to link group');
    } finally {
      setLinking(false);
    }
  };

  const handleUnlink = async () => {
    if (!unlinkTarget) return;
    try {
      await telegramGroups.unlink(unlinkTarget.telegram_group_id);
      toast.success(`Group "${unlinkTarget.title}" unlinked`);
      setUnlinkTarget(null);
      load();
    } catch {
      toast.error('Failed to unlink group');
    }
  };

  const addToGroupUrl = `https://t.me/${BOT_USERNAME}?startgroup=setup`;

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default', py: 4 }}>
      <Container maxWidth="lg">
        {/* Header */}
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 4 }}>
          <Box>
            <Typography variant="h4" fontWeight={700}>My Groups</Typography>
            <Typography variant="body2" color="text.secondary" mt={0.5}>
              Manage your Telegram groups linked to Telegizer
            </Typography>
          </Box>
          <Box sx={{ display: 'flex', gap: 1 }}>
            <IconButton onClick={load} disabled={loading}><Refresh /></IconButton>
            <Button
              variant="outlined"
              startIcon={<OpenInNew />}
              href={addToGroupUrl}
              target="_blank"
              rel="noreferrer"
            >
              Add Bot to Group
            </Button>
            <Button
              variant="contained"
              startIcon={<Add />}
              onClick={() => setLinkOpen(true)}
            >
              Link Group
            </Button>
          </Box>
        </Box>

        {/* Setup instruction banner */}
        <Paper
          sx={{
            p: 2.5, mb: 3,
            background: 'linear-gradient(135deg, #1e293b 0%, #0f172a 100%)',
            border: '1px solid #334155',
          }}
        >
          <Typography variant="subtitle2" fontWeight={600} gutterBottom>
            How to link a group
          </Typography>
          <Typography variant="body2" color="text.secondary">
            1. Add <strong>@{BOT_USERNAME}</strong> to your Telegram group as admin &nbsp;
            2. In the group, run <code>/linkgroup</code> &nbsp;
            3. Copy the code shown &nbsp;
            4. Click <strong>Link Group</strong> above and paste it
          </Typography>
        </Paper>

        {loading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
            <CircularProgress />
          </Box>
        ) : groups.length === 0 ? (
          <Card sx={{ textAlign: 'center', py: 6 }}>
            <Groups sx={{ fontSize: 64, color: 'text.secondary', mb: 2 }} />
            <Typography variant="h6" gutterBottom>No groups linked yet</Typography>
            <Typography variant="body2" color="text.secondary" mb={3}>
              Add the Telegizer bot to your group then link it here.
            </Typography>
            <Button
              variant="contained"
              startIcon={<Add />}
              onClick={() => setLinkOpen(true)}
            >
              Link Your First Group
            </Button>
          </Card>
        ) : (
          <Grid container spacing={2}>
            {groups.map((g) => (
              <Grid item xs={12} md={6} key={g.telegram_group_id}>
                <Card sx={{ height: '100%' }}>
                  <CardContent>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                      <Box sx={{ flex: 1, minWidth: 0 }}>
                        <Typography variant="h6" noWrap fontWeight={600}>
                          {g.title}
                        </Typography>
                        <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'monospace' }}>
                          ID: {g.telegram_group_id}
                        </Typography>
                      </Box>
                      <StatusChip status={g.bot_status} />
                    </Box>

                    <Divider sx={{ my: 1.5 }} />

                    <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mb: 2 }}>
                      <Box>
                        <Typography variant="caption" color="text.secondary">Bot Type</Typography>
                        <Typography variant="body2" fontWeight={500}>
                          {g.linked_via_bot_type === 'official' ? '🟢 Official Telegizer' : '🔵 Custom Bot'}
                        </Typography>
                      </Box>
                      <Box sx={{ ml: 'auto' }}>
                        <Typography variant="caption" color="text.secondary">Permissions</Typography>
                        <Box mt={0.25}><PermBadge perms={g.bot_permissions} /></Box>
                      </Box>
                    </Box>

                    {g.last_activity && (
                      <Typography variant="caption" color="text.secondary" display="block" mb={2}>
                        Last activity: {new Date(g.last_activity).toLocaleString()}
                      </Typography>
                    )}

                    <Box sx={{ display: 'flex', gap: 1 }}>
                      <Button
                        size="small"
                        variant="contained"
                        startIcon={<Settings />}
                        onClick={() => navigate(`/my-groups/${g.telegram_group_id}`)}
                        sx={{ flex: 1 }}
                      >
                        Manage
                      </Button>
                      <Tooltip title="Unlink group">
                        <IconButton
                          size="small"
                          color="error"
                          onClick={() => setUnlinkTarget(g)}
                        >
                          <LinkOff fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        )}
      </Container>

      {/* Link group dialog */}
      <Dialog open={linkOpen} onClose={() => setLinkOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Link a Telegram Group</DialogTitle>
        <DialogContent>
          <Alert severity="info" sx={{ mb: 2 }}>
            Run <code>/linkgroup</code> in your Telegram group to get a verification code, then paste it below.
          </Alert>
          <TextField
            autoFocus
            fullWidth
            label="Verification Code"
            value={linkCode}
            onChange={(e) => setLinkCode(e.target.value.toUpperCase())}
            placeholder="TLG-XXXXXXXX"
            inputProps={{ style: { fontFamily: 'monospace', letterSpacing: 2 } }}
            onKeyDown={(e) => e.key === 'Enter' && handleLink()}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setLinkOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            onClick={handleLink}
            disabled={linking || !linkCode.trim()}
          >
            {linking ? <CircularProgress size={20} /> : 'Link Group'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Unlink confirm dialog */}
      <Dialog open={!!unlinkTarget} onClose={() => setUnlinkTarget(null)}>
        <DialogTitle>Unlink Group?</DialogTitle>
        <DialogContent>
          <Typography>
            Are you sure you want to unlink <strong>{unlinkTarget?.title}</strong>?
            The bot will remain in the group but the group won't appear in your dashboard.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setUnlinkTarget(null)}>Cancel</Button>
          <Button variant="contained" color="error" onClick={handleUnlink}>Unlink</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
