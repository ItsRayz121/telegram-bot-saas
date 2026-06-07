import React, { useState, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import {
  Box, Card, CardContent, Typography, Button, TextField, Stack,
  Chip, Alert, CircularProgress, Divider,
} from '@mui/material';
import { OpenInNew, CheckCircle } from '@mui/icons-material';
import { toast } from 'react-toastify';
import { engagementTasks } from '../services/api';

const STATUS_CHIP = {
  pending: { label: '🟡 Pending review', color: 'warning' },
  verified: { label: '✅ Verified', color: 'success' },
  rejected: { label: '❌ Rejected', color: 'error' },
};

export default function CampaignTask() {
  const { id } = useParams();
  const [campaign, setCampaign] = useState(null);
  const [loading, setLoading] = useState(true);
  const [answers, setAnswers] = useState({});
  const [submitting, setSubmitting] = useState(false);

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

  const setField = (key, val) => setAnswers((p) => ({ ...p, [key]: val }));

  const submit = async () => {
    const fields = campaign.custom_fields || [];
    for (const f of fields) {
      if (f.required && f.field_type !== 'screenshot' && !(answers[f.key] || '').trim()) {
        toast.error(`${f.label} is required`); return;
      }
    }
    setSubmitting(true);
    try {
      await engagementTasks.submit(id, answers);
      toast.success('Submitted!');
      load();
    } catch (e) {
      toast.error(e.response?.data?.error || 'Failed to submit');
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}><CircularProgress /></Box>;
  }
  if (!campaign) {
    return <Box sx={{ p: 3 }}><Alert severity="error">This campaign is not available.</Alert></Box>;
  }

  const sub = campaign.my_submission;
  const isOpen = campaign.is_open;
  const fields = campaign.custom_fields || [];
  const hasScreenshot = fields.some((f) => f.field_type === 'screenshot');
  const isAuto = campaign.verification_mode === 'auto';

  return (
    <Box sx={{ maxWidth: 560, mx: 'auto', p: 2, pb: 'calc(var(--bottom-nav-clearance, 16px))' }}>
      <Card>
        <CardContent>
          <Typography variant="h6" fontWeight={700}>{campaign.title}</Typography>
          <Stack direction="row" spacing={1} sx={{ my: 1, flexWrap: 'wrap', gap: 0.5 }}>
            <Chip size="small" label={isOpen ? '🟢 Active' : '🔴 Closed'} color={isOpen ? 'success' : 'default'} />
            {campaign.reward_label && <Chip size="small" label={`🎁 ${campaign.reward_label}`} />}
            {campaign.reward_xp ? <Chip size="small" label={`⭐ ${campaign.reward_xp} XP`} /> : null}
            {campaign.ends_at && <Chip size="small" label={`⏳ ${new Date(campaign.ends_at).toLocaleString()}`} />}
          </Stack>
          {campaign.description && <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>{campaign.description}</Typography>}
          {campaign.task_url && (
            <Button variant="outlined" startIcon={<OpenInNew />} href={campaign.task_url} target="_blank" rel="noopener" sx={{ mb: 2 }}>
              Open Task
            </Button>
          )}

          <Divider sx={{ my: 2 }} />

          {sub ? (
            <Alert severity={sub.status === 'verified' ? 'success' : sub.status === 'rejected' ? 'error' : 'info'} icon={<CheckCircle />}>
              Your submission: {(STATUS_CHIP[sub.status] || {}).label || sub.status}
              {sub.review_reason ? ` — ${sub.review_reason}` : ''}
            </Alert>
          ) : !isOpen ? (
            <Alert severity="warning">This campaign is closed. The submission window has ended.</Alert>
          ) : isAuto ? (
            <Alert severity="info">
              This task is auto-verified via Telegram. Please complete it from the bot chat to verify your membership.
            </Alert>
          ) : (
            <Stack spacing={2}>
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
            </Stack>
          )}
        </CardContent>
      </Card>
    </Box>
  );
}
