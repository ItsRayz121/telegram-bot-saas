import React, { useState } from 'react';
import { Link as RouterLink, useNavigate } from 'react-router-dom';
import {
  Alert, Badge, Box, Button, Chip, Container, Divider, IconButton, ListItemIcon, ListItemText, Menu, MenuItem, Tab, Tabs, Tooltip, Typography,
} from '@mui/material';
import { Add, ArrowBack, ArrowDropDown, Build, Download, Link as LinkIcon } from '@mui/icons-material';
import { toast } from 'react-toastify';
import { engagementWs } from '../../services/api';
import { downloadCsv, exportFilename, fetchAllPages } from '../../utils/csvExport';
import { TYPES, XKeyDialog } from '../../components/CampaignManager';
import { WorkspaceProvider, useWorkspace, usePolled, TYPE_LABEL, STATUS_LABEL } from './common';
import Overview from './Overview';
import Directory from './Directory';
import Queue from './Queue';
import Detail from './Detail';
import Create from './Create';

const X_LABEL = { live: 'Connected and working', rejected: 'Connected, but X rejected the key', disabled: 'Not connected' };

function Shell({ view, children }) {
  const ws = useWorkspace();
  const navigate = useNavigate();
  const [createAnchor, setCreateAnchor] = useState(null);
  const [toolsAnchor, setToolsAnchor] = useState(null);
  const [keyOpen, setKeyOpen] = useState(false);
  const [xStatus, setXStatus] = useState(null);
  const [exporting, setExporting] = useState(false);
  // Cheap pending counter for the tab badge (refreshes with the rest of the workspace).
  const q = usePolled(() => engagementWs.queue(ws.botId, ws.groupId, { per_page: 1, status: 'pending' }), [ws.botId, ws.groupId, ws.tick], { intervalMs: 90000, enabled: ws.ready });
  const pending = q.data?.pending_total;

  // Only look up the X connection when the Tools menu is opened (it is account-level and rarely changes).
  const openTools = (e) => {
    setToolsAnchor(e.currentTarget);
    engagementWs.overview(ws.botId, ws.groupId, { days: 7 })
      .then((r) => setXStatus(r.data.x_autoverify_status))
      .catch(() => setXStatus('unknown'));
  };

  if (ws.loadError) {
    return (
      <Container maxWidth="sm" sx={{ py: 6 }}>
        <Alert severity="error" action={<Button color="inherit" size="small" component={RouterLink} to="/groups">My groups</Button>}>{ws.loadError}</Alert>
      </Container>
    );
  }

  const exportDirectory = async () => {
    setToolsAnchor(null);
    setExporting(true);
    try {
      const { rows } = await fetchAllPages(async (page) => {
        const r = await engagementWs.campaigns(ws.botId, ws.groupId, { page, per_page: 100 });
        return { rows: r.data.campaigns, pages: r.data.pages };
      });
      if (!rows.length) { toast.info('No campaigns to export'); return; }
      downloadCsv(exportFilename(ws.groupName || ws.groupId, 'campaigns'),
        ['Campaign ID', 'Title', 'Type', 'Status', 'Starts (UTC)', 'Ends (UTC)', 'Submitted', 'Approved', 'Pending review', 'XP per approval', 'Reward (text)', 'Group post'],
        rows.map((c) => [c.id, c.title, TYPE_LABEL[c.type] || c.type, STATUS_LABEL[c.status] || c.status, c.starts_at ? `${c.starts_at}Z` : '',
          c.ends_at ? `${c.ends_at}Z` : '', c.submitted, c.approved, c.pending, c.reward_xp, c.reward_label || '', c.post_status]));
      toast.success(`Exported all ${rows.length} campaign${rows.length === 1 ? '' : 's'} in ${ws.groupName || 'this group'}`);
    } catch {
      toast.error('Export failed - nothing was downloaded');
    } finally {
      setExporting(false);
    }
  };

  const tabs = [
    { value: 'overview', label: 'Overview', to: ws.paths.overview },
    { value: 'list', label: 'Campaigns', to: ws.paths.list },
    { value: 'review', label: 'Review queue', to: ws.paths.review },
  ];
  const tabValue = tabs.some((t) => t.value === view) ? view : false;

  return (
    <Container maxWidth="lg" sx={{ py: { xs: 2, md: 3 }, px: { xs: 2, sm: 3 } }}>
      <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1, flexWrap: 'wrap', mb: 1 }}>
        <Tooltip title={`Back to ${ws.groupName || 'group'} dashboard`}>
          <IconButton component={RouterLink} to={ws.paths.group} aria-label={`Back to ${ws.groupName || 'group'} dashboard`} size="small" sx={{ mt: 0.5 }}>
            <ArrowBack />
          </IconButton>
        </Tooltip>
        <Box sx={{ flex: '1 1 240px', minWidth: 0 }}>
          <Typography variant="h5" component="h1" fontWeight={800} sx={{ lineHeight: 1.2 }}>Campaigns</Typography>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap', mt: 0.5 }}>
            <Chip size="small" color="primary" variant="outlined" label={ws.groupName || 'Loading group…'} sx={{ maxWidth: '100%' }} />
            <Typography variant="caption" color="text.secondary">All data on these pages belongs to this group only · times in {ws.tz}</Typography>
          </Box>
        </Box>
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
          <Button variant="outlined" size="small" startIcon={<Build />} endIcon={<ArrowDropDown />} onClick={openTools} disabled={exporting}>
            Tools
          </Button>
          <Button variant="contained" size="small" startIcon={<Add />} endIcon={<ArrowDropDown />} onClick={(e) => setCreateAnchor(e.currentTarget)} disabled={ws.isViewer}>
            New campaign
          </Button>
        </Box>
        <Menu anchorEl={createAnchor} open={!!createAnchor} onClose={() => setCreateAnchor(null)}>
          {TYPES.map((t) => (
            <MenuItem key={t.value} onClick={() => { setCreateAnchor(null); navigate(ws.paths.create(t.value)); }}>
              <Box component="span" sx={{ mr: 1 }} aria-hidden>{t.emoji}</Box> {t.label}
            </MenuItem>
          ))}
        </Menu>
        <Menu anchorEl={toolsAnchor} open={!!toolsAnchor} onClose={() => setToolsAnchor(null)}>
          <MenuItem onClick={exportDirectory}>
            <ListItemIcon><Download fontSize="small" /></ListItemIcon>
            <ListItemText primary="Export all campaigns (CSV)" secondary="Every campaign in this group" />
          </MenuItem>
          <Divider />
          <MenuItem onClick={() => { setToolsAnchor(null); setKeyOpen(true); }}>
            <ListItemIcon><LinkIcon fontSize="small" /></ListItemIcon>
            <ListItemText primary="X (Twitter) verification" secondary={xStatus ? (X_LABEL[xStatus] || 'Status unavailable') : 'Checking…'} />
          </MenuItem>
        </Menu>
      </Box>

      {ws.isViewer && <Alert severity="info" sx={{ mb: 1.5 }}>You have view-only access to this group. You can read campaigns and submissions, but not change or review them.</Alert>}

      <Tabs value={tabValue} variant="scrollable" scrollButtons="auto" allowScrollButtonsMobile aria-label="Campaign workspace sections"
        sx={{ borderBottom: 1, borderColor: 'divider', mb: 2.5, minHeight: 44 }}>
        {tabs.map((t) => (
          <Tab key={t.value} value={t.value} component={RouterLink} to={t.to} sx={{ textTransform: 'none', fontWeight: 600 }}
            label={t.value === 'review' && pending ? (
              <Badge color="warning" badgeContent={pending > 99 ? '99+' : pending} sx={{ '& .MuiBadge-badge': { right: 0, top: 4 } }}>
                <span style={{ paddingRight: 22 }}>{t.label}</span>
              </Badge>
            ) : t.label} />
        ))}
      </Tabs>

      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 2 }}>
        {ws.isPaid ? `${ws.tier.charAt(0).toUpperCase()}${ws.tier.slice(1)} plan: multiple campaigns, multi-task campaigns, link checks, winner picker and bulk export are available.`
          : 'Free plan: 1 active campaign, manual/honor proof, Telegram-join auto-verify. Pro adds multiple campaigns, link checks, advanced fields, winner picker and bulk export.'}
      </Typography>

      {children}

      <XKeyDialog open={keyOpen} onClose={() => setKeyOpen(false)} onSaved={(s) => { if (s) setXStatus(s); ws.bump(); }} />
    </Container>
  );
}

export default function CampaignWorkspace({ view }) {
  return (
    <WorkspaceProvider>
      <Shell view={view}>
        {view === 'overview' && <Overview />}
        {view === 'list' && <Directory />}
        {view === 'review' && <Queue />}
        {view === 'detail' && <Detail />}
        {view === 'create' && <Create />}
      </Shell>
    </WorkspaceProvider>
  );
}

