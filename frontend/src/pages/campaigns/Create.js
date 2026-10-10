import React, { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Alert, Box, Button, Card, CardActionArea, Chip, Dialog, DialogActions, DialogContent, DialogTitle, Typography } from '@mui/material';
import { engagementWs } from '../../services/api';
import { CampaignWizard, TYPES, XKeyDialog } from '../../components/CampaignManager';
import { useWorkspace } from './common';

export default function Create() {
  const ws = useWorkspace();
  const navigate = useNavigate();
  const [sp, setSp] = useSearchParams();
  const type = TYPES.some((t) => t.value === sp.get('type')) ? sp.get('type') : null;
  const [dirty, setDirty] = useState(false);
  const [leave, setLeave] = useState(false);
  const [keyOpen, setKeyOpen] = useState(false);
  const [xStatus, setXStatus] = useState('disabled');
  const dirtyRef = useRef(false);
  dirtyRef.current = dirty;

  useEffect(() => {
    if (!ws.ready) return;
    engagementWs.overview(ws.botId, ws.groupId, { days: 7 }).then((r) => setXStatus(r.data.x_autoverify_status || 'disabled')).catch(() => {});
  }, [ws.ready, ws.botId, ws.groupId]);

  // Warn before the tab is closed / reloaded with unsaved input.
  useEffect(() => {
    const h = (e) => { if (dirtyRef.current) { e.preventDefault(); e.returnValue = ''; } };
    window.addEventListener('beforeunload', h);
    return () => window.removeEventListener('beforeunload', h);
  }, []);

  if (ws.isViewer) return <Alert severity="info">View-only access: you can't create campaigns in this group.</Alert>;

  if (!type) {
    return (
      <Box>
        <Typography variant="h6" component="h2" fontWeight={700} sx={{ mb: 0.5 }}>What kind of campaign?</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>It will be created in <strong>{ws.groupName || 'this group'}</strong>.</Typography>
        <Box sx={{ display: 'grid', gap: 1.5, gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)', md: 'repeat(3, 1fr)' } }}>
          {TYPES.map((t) => (
            <Card key={t.value} variant="outlined">
              <CardActionArea onClick={() => setSp({ type: t.value }, { replace: true })} sx={{ p: 2, height: '100%' }}>
                <Typography variant="subtitle1" fontWeight={700}><span aria-hidden>{t.emoji}</span> {t.label}</Typography>
                <Typography variant="body2" color="text.secondary">{t.help}</Typography>
              </CardActionArea>
            </Card>
          ))}
        </Box>
      </Box>
    );
  }

  const cancel = () => (dirty ? setLeave(true) : navigate(ws.paths.list));

  return (
    <Box sx={{ maxWidth: 900 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap', mb: 2 }}>
        <Typography variant="body2" color="text.secondary">Creating in</Typography>
        <Chip color="primary" variant="outlined" size="small" label={ws.groupName || 'this group'} />
        <Typography variant="caption" color="text.secondary">(fixed - set by the group you opened this from)</Typography>
      </Box>
      <CampaignWizard
        page botId={ws.botId} groupId={ws.groupId} initialType={type} isPaid={ws.isPaid} groupName={ws.groupName}
        xAutoverifyStatus={xStatus} onManageKey={() => setKeyOpen(true)}
        onDirty={setDirty} onClose={cancel}
        onCreated={(published, campaign) => {
          setDirty(false);
          ws.bump();
          navigate(campaign?.id ? ws.paths.detail(campaign.id) : ws.paths.list, { replace: true });
        }}
      />
      <XKeyDialog open={keyOpen} onClose={() => setKeyOpen(false)} onSaved={(s) => s && setXStatus(s)} />
      <Dialog open={leave} onClose={() => setLeave(false)} maxWidth="xs" fullWidth aria-labelledby="leave-title">
        <DialogTitle id="leave-title">Discard this campaign?</DialogTitle>
        <DialogContent><Typography variant="body2" color="text.secondary">You haven't saved it. Nothing has been posted to the group. If you leave now, what you typed is lost.</Typography></DialogContent>
        <DialogActions>
          <Button onClick={() => setLeave(false)}>Keep editing</Button>
          <Button color="error" onClick={() => { setDirty(false); navigate(ws.paths.list); }}>Discard</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
