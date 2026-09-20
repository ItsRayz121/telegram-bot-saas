import React, { useState, useEffect } from 'react';
import {
  Alert, Button, Stack, CircularProgress, Typography,
} from '@mui/material';
import { useNavigate } from 'react-router-dom';
import { toast } from 'react-toastify';
import { customBots } from '../services/api';

// Mirrors backend/custom_bot_lifecycle.py STAGES / DISCOUNT_CODE / RETENTION_DAYS —
// used only as an instant fallback before the lifecycle-status fetch resolves.
export const GRACE_DAYS = { trial_expired: 3, subscription_expired: 7 };
export const RETENTION_DAYS = { trial_expired: 7, subscription_expired: 15 };
export const DISCOUNT_CODE_FALLBACK = { trial_expired: 'TRIAL20', subscription_expired: 'COMEBACK20' };

export function formatLifecycleDate(iso) {
  if (!iso) return null;
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

export function addDaysIso(iso, days) {
  if (!iso) return null;
  const d = new Date(iso);
  d.setDate(d.getDate() + days);
  return d.toISOString();
}

/** Short "your plan ended" / "paused" status line, shared by the banner and the lifecycle page. */
export function lifecycleStatusLine(bot) {
  const reason = bot.pause_reason;
  if (!reason) return '';
  if (bot.status === 'paused') {
    const deadline = formatLifecycleDate(bot.retention_deadline_at);
    return deadline
      ? `Paused. Data is kept until ${deadline}.`
      : 'Paused. Data is kept for a limited time before permanent deletion.';
  }
  const planLabel = reason === 'trial_expired' ? 'Your Pro trial' : 'Your Pro plan';
  const pauseDate = formatLifecycleDate(addDaysIso(bot.grace_started_at, GRACE_DAYS[reason] || 3));
  return pauseDate
    ? `${planLabel} ended — this bot pauses on ${pauseDate}.`
    : `${planLabel} ended — this bot will pause soon.`;
}

/**
 * Renders on a custom bot's card whenever the bot is anywhere in the
 * pause/retain/delete lifecycle (bot.pause_reason is set). Lazily fetches
 * group/member counts + the discount code from GET /lifecycle-status only
 * when it's actually going to render something.
 */
export default function CustomBotLifecycleBanner({ bot, userTier, onReactivated }) {
  const navigate = useNavigate();
  const [info, setInfo] = useState(null);
  const [reactivating, setReactivating] = useState(false);

  const shouldShow = !!bot.pause_reason;

  useEffect(() => {
    if (!shouldShow) return;
    let cancelled = false;
    customBots.getLifecycleStatus(bot.id)
      .then((res) => { if (!cancelled) setInfo(res.data); })
      .catch(() => { /* banner still works off bot fields alone */ });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shouldShow, bot.id]);

  if (!shouldShow) return null;

  const discountCode = info?.discount_code || DISCOUNT_CODE_FALLBACK[bot.pause_reason] || null;
  const pricingUrl = info?.pricing_url || (discountCode ? `/pricing?promo=${discountCode}` : '/pricing');

  const handleReactivate = async () => {
    // Still mid-grace (not paused yet) — "reactivate" isn't valid, the only
    // useful action is upgrading now, so send them there instead of no-oping.
    if (bot.status !== 'paused') {
      navigate(pricingUrl);
      return;
    }
    if (userTier !== 'pro' && userTier !== 'enterprise') {
      navigate(pricingUrl);
      return;
    }
    setReactivating(true);
    try {
      await customBots.reactivate(bot.id);
      toast.success('Bot reactivated!');
      if (onReactivated) onReactivated();
    } catch (err) {
      toast.error(err.response?.data?.error || 'Could not reactivate bot');
    } finally {
      setReactivating(false);
    }
  };

  return (
    <Alert severity={bot.status === 'paused' ? 'error' : 'warning'} sx={{ mb: 1.5 }} icon={false}>
      <Typography variant="body2" fontWeight={600} sx={{ mb: info ? 0.25 : 1 }}>
        {lifecycleStatusLine(bot)}
      </Typography>
      {info && (
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
          {info.group_count} group{info.group_count === 1 ? '' : 's'} · {info.member_count} member{info.member_count === 1 ? '' : 's'} affected
        </Typography>
      )}
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
        <Button size="small" variant="outlined" onClick={() => navigate('/groups')}>
          Switch to official bot (free)
        </Button>
        <Button size="small" variant="outlined" onClick={() => navigate(`/groups?bot_id=${bot.id}`)}>
          Export settings
        </Button>
        <Button
          size="small"
          variant="contained"
          color="warning"
          disabled={reactivating}
          onClick={handleReactivate}
        >
          {reactivating
            ? <CircularProgress size={16} sx={{ color: 'inherit' }} />
            : `Reactivate${discountCode ? ` — ${discountCode}` : ', 20% off'}`}
        </Button>
      </Stack>
    </Alert>
  );
}
