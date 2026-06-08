import React, { useState, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import {
  Box, Card, CardContent, Typography, Button, TextField, Stack,
  Chip, Alert, CircularProgress, Divider,
} from '@mui/material';
import { OpenInNew, CheckCircle, EmojiEvents } from '@mui/icons-material';
import { toast } from 'react-toastify';
import { engagementTasks } from '../services/api';

const STATUS_CHIP = {
  pending: { label: '🟡 Pending review', color: 'warning' },
  verified: { label: '✅ Verified', color: 'success' },
  rejected: { label: '❌ Rejected', color: 'error' },
};

const RANK_MEDAL = { 1: '🥇', 2: '🥈', 3: '🥉' };

export default function CampaignTask() {
  const { id } = useParams();
  const [campaign, setCampaign] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await engagementTasks.get(id);
      setCampaign(res.data.campaign);
    } catch (e) {
      toast.error(e.response?.data?.error || 'Campaign not found');
      setCampaign(null);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}><CircularProgress /></Box>;
  }
  if (!campaign) {
    return <Box sx={{ p: 3 }}><Alert severity="error">This campaign is not available.</Alert></Box>;
  }

  const isOpen = campaign.is_open;
  const tasks = campaign.tasks || [];
  const isMulti = tasks.length > 0;
  const mySubs = campaign.my_submissions || [];
  const subForTask = (tid) => mySubs.find((s) => s.task_id === tid) || null;

  return (
    <Box sx={{ maxWidth: 560, mx: 'auto', p: 2, pb: 'calc(var(--bottom-nav-clearance, 16px))' }}>
      <Card>
        <CardContent>
          <Typography variant="h6" fontWeight={700}>{campaign.title}</Typography>
          <Stack direction="row" spacing={1} sx={{ my: 1, flexWrap: 'wrap', gap: 0.5 }}>
            <Chip size="small" label={isOpen ? '🟢 Active' : '🔴 Closed'} color={isOpen ? 'success' : 'default'} />
            {campaign.reward_label && <Chip size="small" label={`🎁 ${campaign.reward_label}`} />}
            {!isMulti && campaign.reward_xp ? <Chip size="small" label={`⭐ ${campaign.reward_xp} XP`} /> : null}
            {isMulti && <Chip size="small" label={`🧩 ${tasks.length} tasks`} />}
            {campaign.ends_at && <Chip size="small" label={`⏳ ${new Date(campaign.ends_at).toLocaleString()}`} />}
          </Stack>
          {campaign.description && (
            <Typography variant="body2" color="text.secondary" sx={{ mb: isMulti ? 0 : 2 }}>{campaign.description}</Typography>
          )}

          {!isMulti && (
            <>
              {campaign.task_url && (
                <Button variant="outlined" startIcon={<OpenInNew />} href={campaign.task_url} target="_blank" rel="noopener" sx={{ mt: 2, mb: 2 }}>
                  Open Task
                </Button>
              )}
              <Divider sx={{ my: 2 }} />
              <TaskBlock campaignId={id} spec={campaign} taskId={null} mySub={campaign.my_submission} isOpen={isOpen} onSubmitted={load} />
            </>
          )}
        </CardContent>
      </Card>

      {isMulti && tasks.map((t) => (
        <Card key={t.id} sx={{ mt: 2 }}>
          <CardContent>
            <Typography variant="subtitle1" fontWeight={700}>{t.title}</Typography>
            <Stack direction="row" spacing={0.5} sx={{ my: 0.5, flexWrap: 'wrap', gap: 0.5 }}>
              {t.platform && <Chip size="small" variant="outlined" label={t.platform} />}
              {t.reward_xp ? <Chip size="small" label={`⭐ ${t.reward_xp} XP`} /> : null}
            </Stack>
            <Divider sx={{ my: 1.5 }} />
            <TaskBlock campaignId={id} spec={t} taskId={t.id} mySub={subForTask(t.id)} isOpen={isOpen} onSubmitted={load} />
          </CardContent>
        </Card>
      ))}

      <CampaignLeaderboardCard campaignId={id} reloadKey={mySubs.length} />
    </Box>
  );
}

// ── One task's proof form / status (used campaign-level and per task) ────────────

function TaskBlock({ campaignId, spec, taskId, mySub, isOpen, onSubmitted }) {
  const [answers, setAnswers] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const fields = spec.custom_fields || [];
  const hasScreenshot = fields.some((f) => f.field_type === 'screenshot');
  const isAuto = spec.verification_mode === 'auto';
  const setField = (k, v) => setAnswers((p) => ({ ...p, [k]: v }));

  const submit = async () => {
    for (const f of fields) {
      if (f.required && f.field_type !== 'screenshot' && !(answers[f.key] || '').trim()) {
        toast.error(`${f.label} is required`); return;
      }
    }
    setSubmitting(true);
    try {
      await engagementTasks.submit(campaignId, answers, taskId);
      toast.success('Submitted!');
      onSubmitted();
    } catch (e) {
      toast.error(e.response?.data?.error || 'Failed to submit');
    } finally {
      setSubmitting(false);
    }
  };

  // For a multi-task block, the description / open-task link live with the task.
  return (
    <Stack spacing={1.5}>
      {taskId != null && spec.description && (
        <Typography variant="body2" color="text.secondary">{spec.description}</Typography>
      )}
      {taskId != null && spec.task_url && (
        <Button variant="outlined" size="small" startIcon={<OpenInNew />} href={spec.task_url} target="_blank" rel="noopener" sx={{ alignSelf: 'flex-start' }}>
          Open Task
        </Button>
      )}
      {mySub ? (
        <Alert severity={mySub.status === 'verified' ? 'success' : mySub.status === 'rejected' ? 'error' : 'info'} icon={<CheckCircle />}>
          Your submission: {(STATUS_CHIP[mySub.status] || {}).label || mySub.status}
          {mySub.review_reason ? ` — ${mySub.review_reason}` : ''}
        </Alert>
      ) : !isOpen ? (
        <Alert severity="warning">This campaign is closed. The submission window has ended.</Alert>
      ) : isAuto ? (
        <Alert severity="info">
          This task is auto-verified via Telegram. Please complete it from the bot chat to verify your membership.
        </Alert>
      ) : (
        <>
          {hasScreenshot && (
            <Alert severity="info">This task needs a screenshot — please submit it from the bot chat.</Alert>
          )}
          {fields.filter((f) => f.field_type !== 'screenshot').map((f) => (
            <TextField
              key={f.key}
              fullWidth
              label={f.label + (f.required ? ' *' : '')}
              value={answers[f.key] || ''}
              onChange={(e) => setField(f.key, e.target.value)}
            />
          ))}
          <Button variant="contained" disabled={submitting || hasScreenshot} onClick={submit}>
            {submitting ? <CircularProgress size={20} color="inherit" /> : (fields.length ? 'Submit' : 'Participate')}
          </Button>
        </>
      )}
    </Stack>
  );
}

// ── Participant leaderboard (Pro campaigns only; silently hidden otherwise) ──────

function CampaignLeaderboardCard({ campaignId, reloadKey }) {
  const [data, setData] = useState(null);
  const [show, setShow] = useState(false);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const res = await engagementTasks.leaderboard(campaignId, { limit: 10 });
        if (active) { setData(res.data); setShow(true); }
      } catch {
        // 403 (not a Pro campaign) or any error → keep the board hidden.
        if (active) setShow(false);
      }
    })();
    return () => { active = false; };
    // reloadKey re-fetches after the viewer's own submission status changes.
  }, [campaignId, reloadKey]);

  const entries = data?.entries || [];
  if (!show || entries.length === 0) return null;
  const me = data?.me;
  const meInPage = me && entries.some((e) => e.telegram_user_id === me.telegram_user_id);

  const row = (e, highlight) => (
    <Box
      key={e.telegram_user_id}
      sx={{
        display: 'flex', alignItems: 'center', gap: 1, py: 0.75, px: 1, borderRadius: 1,
        bgcolor: highlight ? 'action.selected' : 'transparent',
      }}
    >
      <Typography variant="body2" fontWeight={e.rank <= 3 ? 700 : 500} sx={{ minWidth: 28, textAlign: 'right' }}>
        {RANK_MEDAL[e.rank] || e.rank}
      </Typography>
      <Typography variant="body2" sx={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {highlight ? 'You' : (e.telegram_username ? `@${e.telegram_username}` : `User ${e.telegram_user_id}`)}
      </Typography>
      {e.xp_earned ? <Chip size="small" label={`+${e.xp_earned} XP`} /> : null}
    </Box>
  );

  return (
    <Card sx={{ mt: 2 }}>
      <CardContent>
        <Typography variant="subtitle1" fontWeight={700} sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.5 }}>
          <EmojiEvents fontSize="small" color="warning" /> Leaderboard
        </Typography>
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
          {data.total_participants} participant(s) · top {entries.length}
        </Typography>
        <Stack spacing={0}>
          {entries.map((e) => row(e, me && e.telegram_user_id === me.telegram_user_id))}
        </Stack>
        {me && !meInPage && (
          <>
            <Divider sx={{ my: 1 }} />
            {row(me, true)}
          </>
        )}
      </CardContent>
    </Card>
  );
}
