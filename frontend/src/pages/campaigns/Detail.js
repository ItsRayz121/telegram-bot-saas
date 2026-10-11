import React, { useCallback, useEffect, useState } from 'react';
import { Link as RouterLink, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import {
  Alert, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, Menu, MenuItem, Paper, Stack, Tab, Tabs, Typography,
} from '@mui/material';
import { ArrowBack, ArrowDropDown, OpenInNew } from '@mui/icons-material';
import { toast } from 'react-toastify';
import { engagement, engagementWs } from '../../services/api';
import { CampaignEditDialog, CampaignManageDialog, PostStatusCell } from '../../components/CampaignManager';
import { EmptyNote, InsightError, Loading, Panel, StatGrid, StatTile, TrendChart } from '../../components/analytics/shared';
import {
  GOAL_LABEL, ProgressBlock, SOURCE_LABEL, StatusChip, TypeChip, fmtTime, timeLeft, useWorkspace, usePolled,
} from './common';

const TABS = [['overview', 'Summary'], ['submissions', 'Submissions'], ['results', 'Results & rewards'], ['activity', 'Activity'], ['settings', 'Settings']];

const LIFECYCLE = (status) => [
  status !== 'active' && { action: 'publish', label: 'Publish / activate', note: 'Activates the campaign and posts it to the group.' },
  status === 'active' && { action: 'pause', label: 'Pause', note: 'Members can no longer submit until you reopen it.' },
  (status === 'paused' || status === 'closed') && { action: 'reopen', label: 'Reopen', note: 'Members can submit again.' },
  status !== 'closed' && status !== 'archived' && { action: 'close', label: 'Close', note: 'Stops new submissions. Existing submissions stay reviewable.' },
  status !== 'archived' && { action: 'archive', label: 'Archive', note: 'Hides it from the active list. Submissions and rewards are kept.' },
].filter(Boolean);

function telegramPostUrl(group, campaign) {
  if (!campaign.telegram_message_id || !group) return null;
  if (group.username) return `https://t.me/${String(group.username).replace(/^@/, '')}/${campaign.telegram_message_id}`;
  const id = String(group.telegram_group_id || '');
  return id.startsWith('-100') ? `https://t.me/c/${id.slice(4)}/${campaign.telegram_message_id}` : null;
}

function OverviewTab({ ws, campaign, sumState }) {
  const { data: s, loading, error, reload } = sumState;
  if (error && !s) return <InsightError message={error} onRetry={reload} />;
  const c = s?.counts;
  return (
    <Box>
      <StatGrid columns={{ xs: '1fr', sm: 'repeat(2, 1fr)', md: 'repeat(4, 1fr)' }} gap={2}>
        <StatTile label="Submitted" value={c?.submitted} loading={loading && !s} hint={s ? `${s.people.submitted_unique} unique people` : undefined} />
        <StatTile label="Pending review" value={c?.pending} loading={loading && !s} tone={c?.pending ? 'warning.main' : undefined}
          hint={s?.oldest_pending_hours != null ? `Oldest waiting ${s.oldest_pending_hours}h` : 'Nothing waiting'} />
        <StatTile label="Approved" value={c?.approved} loading={loading && !s} hint={s ? `${s.people.approved_unique} unique people` : undefined} />
        <StatTile label="Rejected" value={c?.rejected} loading={loading && !s} />
      </StatGrid>
      {s?.counts.flagged > 0 && <Alert severity="warning" sx={{ mb: 2 }}>{s.counts.flagged} submission{s.counts.flagged === 1 ? ' is' : 's are'} flagged as possible duplicates.</Alert>}
      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', md: 'repeat(2, minmax(0, 1fr))' }, mb: 2, '& > *': { minHeight: 220 } }}>
        <Panel title="Activity (last 30 days)" sx={{ mb: 0 }}>
          <TrendChart series={s?.series || []} height={170}
            keys={[{ key: 'submitted', label: 'New submissions', color: '#3d8ef8' }, { key: 'decisions', label: 'Review decisions', color: '#22c55e' }]}
            emptyText={loading && !s ? 'Loading…' : 'No activity in the last 30 days.'} />
        </Panel>
        <Panel title="Progress" subtitle="Only shown where this campaign has a real target" sx={{ mb: 0 }}>
          {s && (s.progress.participants || s.progress.actions)
            ? <ProgressBlock progress={s.progress} />
            : <EmptyNote>No participant limit or action goals are set.</EmptyNote>}
          {s?.progress.actions && (
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
              Action goals count verified actions ({Object.values(GOAL_LABEL).join(', ')}); the participant limit counts unique approved people. They are different units.
            </Typography>
          )}
        </Panel>
      </Box>
      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', md: 'repeat(2, minmax(0, 1fr))' }, '& > *': { minHeight: 160 } }}>
        <Panel title="How submissions were approved" sx={{ mb: 0 }}>
          {s && Object.keys(s.verification_sources).length ? (
            <Stack spacing={0.5}>
              {Object.entries(s.verification_sources).map(([k, v]) => (
                <Box key={k} sx={{ display: 'flex', justifyContent: 'space-between', gap: 1 }}>
                  <Typography variant="body2">{SOURCE_LABEL[k] || k}</Typography><Typography variant="body2" fontWeight={700}>{v}</Typography>
                </Box>
              ))}
            </Stack>
          ) : <EmptyNote>No approved submissions yet.</EmptyNote>}
        </Panel>
        <Panel title="Rewards" sx={{ mb: 0 }}>
          <Typography variant="body2"><strong>XP per approved submission:</strong> {campaign.reward_xp || 0}</Typography>
          <Typography variant="body2"><strong>Reward description:</strong> {campaign.reward_label || '—'}</Typography>
          {s && <Typography variant="body2"><strong>Submissions already credited with XP:</strong> {s.rewards.submissions_rewarded}</Typography>}
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>{s?.rewards.note || 'XP is granted once per approved submission. Reward descriptions are free text; no payments are recorded.'}</Typography>
        </Panel>
      </Box>
      <Panel title="Details" sx={{ mt: 2 }}>
        <Box component="dl" sx={{ m: 0, display: 'grid', gridTemplateColumns: 'auto 1fr', columnGap: 2, rowGap: 0.75 }}>
          {[
            ['Description', campaign.description || '—'],
            ['Task link', campaign.task_url ? <a href={campaign.task_url} target="_blank" rel="noopener noreferrer">{campaign.task_url}</a> : '—'],
            ['Platform', campaign.platform || '—'],
            ['Verification', campaign.type === 'raid' ? (campaign.settings?.auto_verify_x ? 'Auto-verify on X' : 'Manual review') : campaign.verification_mode],
            ['Participant limit', campaign.max_participants || 'No limit'],
            ['One submission per person', campaign.one_per_user ? 'Yes' : 'No'],
            ['Tasks', campaign.tasks?.length ? campaign.tasks.map((t) => t.title).join(' · ') : 'Single task'],
          ].map(([k, v]) => (
            <React.Fragment key={k}>
              <Typography component="dt" variant="body2" color="text.secondary">{k}</Typography>
              <Typography component="dd" variant="body2" sx={{ m: 0, wordBreak: 'break-word' }}>{v}</Typography>
            </React.Fragment>
          ))}
        </Box>
      </Panel>
    </Box>
  );
}

function ActivityTab({ ws, campaignId }) {
  const { data, loading, error, reload } = usePolled(() => engagementWs.activity(ws.botId, ws.groupId, campaignId), [ws.botId, ws.groupId, campaignId, ws.tick], { intervalMs: 0 });
  if (error && !data) return <InsightError message={error} onRetry={reload} />;
  if (loading && !data) return <Loading />;
  const label = { submitted: 'Submitted', approved: 'Approved', rejected: 'Rejected', posted: 'Posted to the group' };
  return (
    <Panel title="Activity" subtitle="Real history only: when submissions arrived and when they were decided. Edits to the campaign itself aren't logged.">
      {data.events.length === 0 ? <EmptyNote>Nothing has happened yet.</EmptyNote> : (
        <Stack component="ol" spacing={0} sx={{ listStyle: 'none', m: 0, p: 0 }}>
          {data.events.map((e, i) => (
            <Box component="li" key={`${e.kind}-${e.submission_id || 'p'}-${i}`} sx={{ display: 'flex', gap: 1.5, py: 1, borderTop: i ? '1px solid' : 'none', borderColor: 'divider', flexWrap: 'wrap' }}>
              <Typography variant="caption" color="text.secondary" sx={{ width: { sm: 190 }, flexShrink: 0 }}>{fmtTime(e.at, ws.tz)}</Typography>
              <Box sx={{ minWidth: 0 }}>
                <Typography variant="body2">
                  <strong>{label[e.kind] || e.kind}</strong>{e.who ? ` · ${e.who}` : ''}{e.by ? ` · by ${e.by}` : ''}
                </Typography>
                {e.reason && <Typography variant="caption" color="text.secondary" sx={{ wordBreak: 'break-word' }}>Reason: {e.reason}</Typography>}
              </Box>
            </Box>
          ))}
        </Stack>
      )}
    </Panel>
  );
}

export default function Detail() {
  const ws = useWorkspace();
  const { campaignId: raw } = useParams();
  const campaignId = parseInt(raw, 10);
  const navigate = useNavigate();
  const location = useLocation();
  const [sp, setSp] = useSearchParams();
  const tab = TABS.some(([k]) => k === sp.get('tab')) ? sp.get('tab') : 'overview';
  const [state, setState] = useState({ loading: true, campaign: null, error: null });
  const [menu, setMenu] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [busy, setBusy] = useState(false);
  const backTo = location.state?.from || ws.paths.list;

  const load = useCallback(() => {
    setState((s) => ({ ...s, loading: true, error: null }));
    return engagement.get(ws.botId, ws.groupId, campaignId)
      .then((r) => setState({ loading: false, campaign: r.data.campaign, error: null }))
      .catch((e) => setState({ loading: false, campaign: null, error: e.response?.status === 404 ? 'This campaign does not exist in this group.' : 'Could not load this campaign.' }));
  }, [ws.botId, ws.groupId, campaignId]);
  useEffect(() => { if (ws.ready) load(); }, [load, ws.ready, ws.tick]);

  const sumState = usePolled(() => engagementWs.summary(ws.botId, ws.groupId, campaignId), [ws.botId, ws.groupId, campaignId, ws.tick], { enabled: ws.ready && tab === 'overview', intervalMs: 60000 });

  const { campaign: c } = state;
  const setTab = (t) => { const n = new URLSearchParams(sp); n.set('tab', t); setSp(n, { replace: true, state: location.state }); };

  const runLifecycle = async (l) => {
    setBusy(true);
    try {
      await engagement.update(ws.botId, ws.groupId, campaignId, { action: l.action });
      toast.success(`Campaign ${l.action === 'publish' ? 'published' : `${l.action}${l.action.endsWith('e') ? 'd' : 'ed'}`}`);
      setConfirm(null);
      ws.bump();
    } catch (e) {
      toast.error(e.response?.data?.error || `Could not ${l.action} - nothing was changed`);
    } finally {
      setBusy(false);
    }
  };

  if (state.error) {
    return <Alert severity="error" action={<Button color="inherit" size="small" component={RouterLink} to={ws.paths.list}>All campaigns</Button>}>{state.error}</Alert>;
  }
  if (!c) return <Loading label="Loading campaign…" />;
  const postUrl = telegramPostUrl(ws.group, c);
  const lifecycle = LIFECYCLE(c.status);

  return (
    <Box>
      <Button size="small" startIcon={<ArrowBack />} onClick={() => navigate(backTo)} sx={{ mb: 1 }}>Back to campaigns</Button>
      <Paper variant="outlined" sx={{ p: { xs: 1.5, sm: 2.5 }, mb: 2 }}>
        <Box sx={{ display: 'flex', gap: 1.5, justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap' }}>
          <Box sx={{ minWidth: 0, flex: '1 1 280px' }}>
            <Typography variant="h5" component="h2" fontWeight={800} sx={{ wordBreak: 'break-word' }}>{c.title}</Typography>
            <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap" sx={{ my: 1 }}>
              <TypeChip type={c.type} /> <StatusChip status={c.status} />
              {c.is_multitask && <Chip size="small" variant="outlined" label={`${c.tasks.length} tasks`} />}
            </Stack>
            <Typography variant="body2" color="text.secondary">
              Created {fmtTime(c.created_at, ws.tz)}
              {c.starts_at ? ` · starts ${fmtTime(c.starts_at, ws.tz)}` : ''}
              {c.ends_at ? ` · ends ${fmtTime(c.ends_at, ws.tz)} (${timeLeft(c.ends_at)})` : ' · no deadline'}
            </Typography>
          </Box>
          <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
            <PostStatusCell c={c} botId={ws.botId} groupId={ws.groupId} onChanged={() => ws.bump()} />
            {postUrl && <Button size="small" href={postUrl} target="_blank" rel="noopener noreferrer" endIcon={<OpenInNew fontSize="small" />}>View Telegram post</Button>}
            {!ws.isViewer && lifecycle.length > 0 && (
              <>
                <Button size="small" variant="outlined" endIcon={<ArrowDropDown />} onClick={(e) => setMenu(e.currentTarget)} disabled={busy}>Campaign actions</Button>
                <Menu anchorEl={menu} open={!!menu} onClose={() => setMenu(null)}>
                  {lifecycle.map((l) => <MenuItem key={l.action} onClick={() => { setMenu(null); setConfirm(l); }}>{l.label}</MenuItem>)}
                </Menu>
              </>
            )}
          </Box>
        </Box>
        {c.post_status === 'failed' && <Alert severity="error" sx={{ mt: 1.5 }}>Group post failed: {c.post_error || 'unknown error'}. Use the retry button next to the post status.</Alert>}
        {c.status === 'active' && c.post_status === 'none' && <Alert severity="warning" sx={{ mt: 1.5 }}>This campaign is active but hasn't been posted to the group yet. Use the post button next to the status.</Alert>}
      </Paper>

      <Tabs value={tab} onChange={(_, v) => setTab(v)} variant="scrollable" scrollButtons="auto" allowScrollButtonsMobile aria-label="Campaign sections"
        sx={{ borderBottom: 1, borderColor: 'divider', mb: 2 }}>
        {TABS.map(([k, l]) => <Tab key={k} value={k} label={l} sx={{ textTransform: 'none', fontWeight: 600 }} />)}
      </Tabs>

      {tab === 'overview' && <OverviewTab ws={ws} campaign={c} sumState={sumState} />}
      {tab === 'submissions' && <CampaignManageDialog page view="submissions" botId={ws.botId} groupId={ws.groupId} campaignId={campaignId} onChanged={ws.bump} />}
      {tab === 'results' && <CampaignManageDialog page view="results" botId={ws.botId} groupId={ws.groupId} campaignId={campaignId} onChanged={ws.bump} />}
      {tab === 'activity' && <ActivityTab ws={ws} campaignId={campaignId} />}
      {tab === 'settings' && (
        ws.isViewer ? <Alert severity="info">View-only access: campaign settings can't be changed.</Alert> : (
          <CampaignEditDialog page botId={ws.botId} groupId={ws.groupId} campaign={c}
            hasSubmissions={(c.submissions_total ?? 1) > 0}
            onClose={() => setTab('overview')}
            onSaved={() => { setTab('overview'); ws.bump(); }} />
        )
      )}

      <Dialog open={!!confirm} onClose={() => !busy && setConfirm(null)} maxWidth="xs" fullWidth aria-labelledby="lc-title">
        <DialogTitle id="lc-title">{confirm?.label}?</DialogTitle>
        <DialogContent><Typography variant="body2" color="text.secondary">{confirm?.note}</Typography></DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirm(null)} disabled={busy}>Cancel</Button>
          <Button variant="contained" color={confirm?.action === 'archive' || confirm?.action === 'close' ? 'warning' : 'primary'} onClick={() => runLifecycle(confirm)} disabled={busy}>{confirm?.label}</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
