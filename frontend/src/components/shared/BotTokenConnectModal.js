import React, { useState, useEffect } from 'react';
import {
  Dialog, DialogTitle, DialogContent, DialogActions,
  Button, TextField, Alert, Box, Typography, CircularProgress, Chip,
} from '@mui/material';
import { CheckCircle, Warning, SmartToy } from '@mui/icons-material';
import { customBots, hub } from '../../services/api';

/**
 * Unified two-step bot token connect modal.
 *
 * Props:
 *   open        – boolean
 *   onClose     – () => void
 *   onConnected – (bot) => void   receives the newly created bot record
 *   mode        – "group_management" | "assistant_hub"
 *   plan        – user's subscription tier string (optional; used to gate paid features)
 */
export default function BotTokenConnectModal({ open, onClose, onConnected, mode = 'group_management', plan }) {
  const [token, setToken] = useState('');
  const [verifying, setVerifying] = useState(false);
  const [preview, setPreview] = useState(null);
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (open) { setToken(''); setPreview(null); setError(null); }
  }, [open]);

  const isHub = mode === 'assistant_hub';
  const isPlanBlocked = isHub && plan === 'free';

  const handleVerify = async () => {
    if (!token.trim()) { setError('Paste your bot token first.'); return; }
    setVerifying(true);
    setError(null);
    try {
      // Both pillars can use the same validate-token endpoint — it only hits getMe()
      const res = await customBots.validateToken(token.trim());
      setPreview(res.data);
    } catch (e) {
      const code = e.response?.data?.error;
      if (code === 'invalid_token' || e.response?.status === 400) {
        setError('Invalid bot token. Double-check it in @BotFather → /mybots → API Token.');
      } else {
        setError('Could not reach Telegram. Check your connection and try again.');
      }
    } finally {
      setVerifying(false);
    }
  };

  const handleConnect = async () => {
    if (!preview) return;
    setConnecting(true);
    setError(null);
    try {
      let bot;
      if (isHub) {
        const res = await hub.createBot({ telegram_bot_token: token.trim() });
        bot = res.data.bot;
      } else {
        await customBots.add({ bot_token: token.trim(), bot_username: preview.bot_username });
        bot = preview;
      }
      onConnected(bot);
      // Both sides are now wired — the backend auto-mirrors the bot to the other pillar
    } catch (e) {
      const code = e.response?.data?.error;
      if (code === 'plan_limit') setError('Bot limit reached. Upgrade your plan.');
      else if (code === 'already_registered' || e.response?.status === 409) setError('This bot is already connected.');
      else setError('Connection failed. Please try again.');
    } finally {
      setConnecting(false);
    }
  };

  const title = isHub ? 'Connect Assistant Bot' : 'Connect Your Own Bot';

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{title}</DialogTitle>
      <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: '16px !important' }}>
        {isPlanBlocked && (
          <Alert severity="warning">Custom bots require a Pro or Enterprise plan.</Alert>
        )}
        {error && <Alert severity="error">{error}</Alert>}

        <TextField
          label="Bot Token"
          value={token}
          onChange={(e) => { setToken(e.target.value.trim()); setPreview(null); setError(null); }}
          placeholder="1234567890:AAAA..."
          size="small"
          type="password"
          disabled={verifying || connecting || isPlanBlocked}
          helperText="Get this from @BotFather → /mybots → API Token"
          fullWidth
        />

        {preview && (
          <Box sx={{ border: '1px solid', borderColor: 'success.light', borderRadius: 1, p: 1.5, bgcolor: 'success.50' }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
              <CheckCircle color="success" fontSize="small" />
              <Typography variant="body2" fontWeight={600}>Bot verified</Typography>
            </Box>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
              <SmartToy fontSize="small" color="primary" />
              <Typography variant="body2"><strong>{preview.bot_name}</strong></Typography>
              <Chip label={`@${preview.bot_username}`} size="small" variant="outlined" />
            </Box>
            <Box sx={{ mt: 1 }}>
              <Typography variant="caption" color="text.secondary">
                This bot will be available in both <strong>Assistant Hub</strong> (private groups) and <strong>Group Management</strong> (public communities).
              </Typography>
            </Box>
            {!preview.can_join_groups && (
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mt: 1 }}>
                <Warning fontSize="small" color="warning" />
                <Typography variant="body2" color="warning.main">
                  This bot cannot join groups. Enable "Allow Groups & Channels" in @BotFather.
                </Typography>
              </Box>
            )}
          </Box>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={connecting}>Cancel</Button>
        {!preview ? (
          <Button
            variant="contained"
            onClick={handleVerify}
            disabled={verifying || !token.trim() || isPlanBlocked}
            startIcon={verifying ? <CircularProgress size={14} /> : null}
          >
            {verifying ? 'Verifying…' : 'Verify Token'}
          </Button>
        ) : (
          <Button
            variant="contained"
            color="success"
            onClick={handleConnect}
            disabled={connecting}
            startIcon={connecting ? <CircularProgress size={14} /> : <CheckCircle />}
          >
            {connecting ? 'Connecting…' : 'Connect Bot'}
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );
}
