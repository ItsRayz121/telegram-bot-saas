/**
 * Add to Group flow — 4-step modal.
 *
 * Step 1 — Instructions: copy bot username, confirm "I added the bot"
 * Step 2 — Waiting: pulse animation, polling for new group
 * Step 3 — Consent pending: user told to check Telegram DM
 * Step 4 — Connected: success state
 *
 * Public/large group warning is shown in the Telegram DM by the bot itself
 * (backend handles it). Dashboard simply reflects "consent pending" state.
 */
import React, { useState, useEffect, useRef } from 'react';
import {
  Dialog, DialogTitle, DialogContent, DialogActions,
  Button, Typography, Box, CircularProgress, IconButton,
  Alert,
} from '@mui/material';
import { Close, ContentCopy, Check, SmartToy } from '@mui/icons-material';
import { hub } from '../../services/api';

const OFFICIAL_BOT_USERNAME = process.env.REACT_APP_TELEGRAM_BOT_USERNAME || 'telegizer_bot';
const POLL_INTERVAL_MS = 4000;
const POLL_TIMEOUT_MS = 5 * 60 * 1000; // 5 minutes

export default function AddToGroupFlow({ open, onClose, onGroupConnected, botId = null, botUsername = null }) {
  const [step, setStep] = useState(0); // 0=instructions 1=waiting 2=consent_pending 3=connected
  const [copied, setCopied] = useState(false);
  const [newGroup, setNewGroup] = useState(null);
  const [error, setError] = useState(null);
  const pollRef = useRef(null);
  const timeoutRef = useRef(null);
  const knownGroupsRef = useRef(null);

  // Reset on open
  useEffect(() => {
    if (open) {
      setStep(0);
      setCopied(false);
      setNewGroup(null);
      setError(null);
      knownGroupsRef.current = null;
    } else {
      _stopPolling();
    }
  }, [open]);

  // Cleanup on unmount
  useEffect(() => () => _stopPolling(), []);

  function _stopPolling() {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    if (timeoutRef.current) { clearTimeout(timeoutRef.current); timeoutRef.current = null; }
  }

  const _listGroups = () => botId ? hub.listBotGroups(botId) : hub.listOfficialGroups();
  const displayUsername = botUsername || OFFICIAL_BOT_USERNAME;

  function _startPolling() {
    // Snapshot current groups so we can detect the new one
    _listGroups().then(r => {
      knownGroupsRef.current = new Set((r.data.groups || []).map(g => g.id));
    }).catch(() => {
      knownGroupsRef.current = new Set();
    });

    pollRef.current = setInterval(async () => {
      try {
        const r = await _listGroups();
        const groups = r.data.groups || [];
        const known = knownGroupsRef.current || new Set();
        const found = groups.find(g => !known.has(g.id));
        if (found) {
          _stopPolling();
          setNewGroup(found);
          if (found.consent_confirmed_at) {
            setStep(3);
            if (onGroupConnected) onGroupConnected(found);
          } else {
            setStep(2); // consent pending — user needs to confirm in Telegram DM
          }
        }
      } catch (_) {}
    }, POLL_INTERVAL_MS);

    // Timeout after 5 minutes
    timeoutRef.current = setTimeout(() => {
      _stopPolling();
      setError("Timed out waiting for the bot to be added. Please try again.");
      setStep(0);
    }, POLL_TIMEOUT_MS);
  }

  const handleCopy = () => {
    navigator.clipboard.writeText(`@${displayUsername}`).catch(() => {});
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleIAddedIt = () => {
    setStep(1);
    _startPolling();
  };

  const handleCancel = () => {
    _stopPolling();
    onClose();
  };

  const handleDoLater = () => {
    _stopPolling();
    onClose();
  };

  return (
    <Dialog open={open} onClose={handleCancel} maxWidth="xs" fullWidth>
      <DialogTitle sx={{ pr: 6 }}>
        Add to Group
        <IconButton onClick={handleCancel} size="small" sx={{ position: 'absolute', right: 8, top: 8 }}>
          <Close fontSize="small" />
        </IconButton>
      </DialogTitle>

      <DialogContent dividers>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

        {/* Step 0 — Instructions */}
        {step === 0 && (
          <Box>
            <Box sx={{ display: 'flex', justifyContent: 'center', mb: 2 }}>
              <Box sx={{ width: 56, height: 56, borderRadius: 3, bgcolor: 'primary.main', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <SmartToy sx={{ color: '#fff', fontSize: 28 }} />
              </Box>
            </Box>
            <Typography variant="body2" textAlign="center" mb={2}>
              Add <strong>@{displayUsername}</strong> to your private Telegram group.
              No admin permissions needed.
              Once added, I'll DM you to confirm.
            </Typography>
            <Button
              variant="outlined"
              fullWidth
              startIcon={copied ? <Check /> : <ContentCopy />}
              onClick={handleCopy}
              color={copied ? 'success' : 'primary'}
              sx={{ mb: 1 }}
            >
              {copied ? 'Copied!' : `Copy @${OFFICIAL_BOT_USERNAME}`}
            </Button>
          </Box>
        )}

        {/* Step 1 — Waiting */}
        {step === 1 && (
          <Box sx={{ textAlign: 'center', py: 3 }}>
            <CircularProgress size={48} sx={{ mb: 2 }} />
            <Typography variant="body2" fontWeight={600}>Waiting for you to add the bot…</Typography>
            <Typography variant="caption" color="text.secondary" display="block" mt={0.5}>
              Watching for @{displayUsername} to join a group
            </Typography>
          </Box>
        )}

        {/* Step 2 — Consent pending */}
        {step === 2 && (
          <Box sx={{ textAlign: 'center', py: 2 }}>
            <Typography fontSize="2.5rem" mb={1}>📲</Typography>
            <Typography variant="body2" fontWeight={600} gutterBottom>
              Check your Telegram DM from @{displayUsername}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Tap <strong>✓ Start Observing</strong> in the message to confirm.
            </Typography>
          </Box>
        )}

        {/* Step 3 — Connected */}
        {step === 3 && newGroup && (
          <Box sx={{ textAlign: 'center', py: 2 }}>
            <Typography fontSize="2.5rem" mb={1}>✅</Typography>
            <Typography variant="body2" fontWeight={600} gutterBottom>
              {newGroup.group_name || 'Group'} connected.
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Activity will appear in the Overview tab.
            </Typography>
          </Box>
        )}
      </DialogContent>

      <DialogActions sx={{ px: 3, pb: 2 }}>
        {step === 0 && (
          <>
            <Button onClick={handleDoLater} size="small" color="inherit">I'll do this later</Button>
            <Button onClick={handleIAddedIt} variant="contained" size="small">I added the bot →</Button>
          </>
        )}
        {step === 1 && (
          <Button onClick={handleCancel} size="small" color="inherit">Cancel</Button>
        )}
        {step === 2 && (
          <Button onClick={handleCancel} size="small" color="inherit">I'll confirm later</Button>
        )}
        {step === 3 && (
          <Button onClick={onClose} variant="contained" size="small">Go to Overview</Button>
        )}
      </DialogActions>
    </Dialog>
  );
}
