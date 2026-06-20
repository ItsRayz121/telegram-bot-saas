import React, { useState } from 'react';
import { Box, Typography, Tooltip, IconButton, Chip } from '@mui/material';
import { ContentCopy, CheckCircle, Telegram, Language } from '@mui/icons-material';

/**
 * Shared "Share your link" block that surfaces BOTH referral links for the
 * SAME referral code:
 *   • Telegram link  — t.me/<bot>?start=ref_<code>  (one-tap, auto sign-in)
 *   • Website link   — <origin>/r/<code>            (web & social sharing)
 *
 * Both links carry the same `code`, so whichever a friend uses, the same
 * referrer is credited (Telegram bot reads `start=ref_<code>`; the web link
 * routes to /register?ref=<code>). This is the single source of truth for how
 * a referral link is built across the whole app (Telegizer + Guildizer).
 *
 * Props:
 *   refCode      referral code (string). Links render as "Loading…" until set.
 *   botUsername  Telegram bot username (defaults to env / telegizer_bot).
 *   primary      'telegram' | 'web' — which link gets the PRIMARY badge + top spot.
 *   title        section label (set to '' to hide).
 *   sx           extra MUI styles for the wrapper.
 */
export default function ReferralLinks({
  refCode,
  botUsername,
  primary = 'telegram',
  title = 'Share your link',
  sx,
}) {
  const username = (botUsername || process.env.REACT_APP_TELEGRAM_BOT_USERNAME || 'telegizer_bot').replace(/^@/, '');
  const origin = typeof window !== 'undefined' ? window.location.origin : '';
  const tgLink = refCode ? `https://t.me/${username}?start=ref_${refCode}` : '';
  const webLink = refCode ? `${origin}/r/${refCode}` : '';

  const [copied, setCopied] = useState('');

  const copy = (which, value) => {
    if (!value) return;
    navigator.clipboard.writeText(value).then(() => {
      setCopied(which);
      setTimeout(() => setCopied((c) => (c === which ? '' : c)), 2000);
    });
  };

  const Row = ({ which, icon, label, badge, value, hint }) => (
    <Box
      sx={{
        display: 'flex', alignItems: 'center', gap: 1.5,
        p: 1.5, borderRadius: 1.5,
        border: '1px solid', borderColor: 'divider',
        bgcolor: 'background.default',
      }}
    >
      <Box sx={{ flexShrink: 0, display: 'flex' }}>{icon}</Box>
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
          <Typography variant="body2" fontWeight={700}>{label}</Typography>
          {badge && (
            <Chip
              label={badge}
              size="small"
              color="primary"
              sx={{ height: 16, fontSize: '0.58rem', fontWeight: 700, '& .MuiChip-label': { px: 0.75 } }}
            />
          )}
        </Box>
        <Typography
          variant="caption"
          sx={{
            display: 'block', fontFamily: 'monospace', color: 'text.secondary',
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}
        >
          {value || 'Loading…'}
        </Typography>
        {hint && (
          <Typography variant="caption" color="text.disabled" sx={{ display: 'block' }}>{hint}</Typography>
        )}
      </Box>
      <Tooltip title={copied === which ? 'Copied!' : 'Copy link'}>
        <span>
          <IconButton
            size="small"
            disabled={!value}
            onClick={() => copy(which, value)}
            color={copied === which ? 'success' : 'default'}
          >
            {copied === which ? <CheckCircle fontSize="small" /> : <ContentCopy fontSize="small" />}
          </IconButton>
        </span>
      </Tooltip>
    </Box>
  );

  const tgRow = (
    <Row
      key="tg"
      which="tg"
      icon={<Telegram sx={{ color: '#0088cc' }} />}
      label="Telegram link"
      badge={primary === 'telegram' ? 'PRIMARY' : null}
      value={tgLink}
      hint="Best for Telegram — one tap, auto sign-in"
    />
  );
  const webRow = (
    <Row
      key="web"
      which="web"
      icon={<Language sx={{ color: 'primary.main' }} />}
      label="Website link"
      badge={primary === 'web' ? 'PRIMARY' : null}
      value={webLink}
      hint="Best for web & social sharing"
    />
  );

  return (
    <Box sx={{ ...sx }}>
      {title ? (
        <Typography
          variant="caption"
          fontWeight={700}
          color="text.secondary"
          sx={{ textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', mb: 1 }}
        >
          {title}
        </Typography>
      ) : null}
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
        {primary === 'web' ? [webRow, tgRow] : [tgRow, webRow]}
      </Box>
    </Box>
  );
}
