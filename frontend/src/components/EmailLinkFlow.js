/**
 * EmailLinkFlow — 3-step modal for optionally linking email + password to a
 * Telegram-only Telegizer account ("Protect your account" flow).
 *
 * Step 1: Enter email  → POST /api/miniapp/link-email/request
 * Step 2: Enter OTP    → validates 6-digit code from email
 * Step 3: Set password → POST /api/miniapp/link-email/verify
 *
 * On success: calls onEmailLinked(user, token) via TelegramContext
 * On merge:   backend returns { status: "merged", token, user } — same handling
 */
import React, { useState, useEffect, useRef } from 'react';
import {
  Dialog, DialogTitle, DialogContent, DialogActions,
  Box, Button, Typography, TextField, CircularProgress,
  Alert, Stepper, Step, StepLabel, InputAdornment, IconButton,
  Divider,
} from '@mui/material';
import {
  Email, Lock, CheckCircle, Visibility, VisibilityOff, Shield,
} from '@mui/icons-material';
import { toast } from 'react-toastify';
import { tmaApi } from '../contexts/TelegramContext';
import { useTelegram } from '../contexts/TelegramContext';

const STEPS = ['Enter email', 'Verify code', 'Set password'];

const OTP_LENGTH = 6;
const RESEND_COOLDOWN = 60; // seconds

export default function EmailLinkFlow({ open, onClose }) {
  const { onEmailLinked, haptic } = useTelegram();

  const [step, setStep] = useState(0);
  const [email, setEmail] = useState('');
  const [otp, setOtp] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [isMerge, setIsMerge] = useState(false);
  const [resendCooldown, setResendCooldown] = useState(0);

  const cooldownRef = useRef(null);
  const otpInputRef = useRef(null);

  // Reset state when modal opens
  useEffect(() => {
    if (open) {
      setStep(0);
      setEmail('');
      setOtp('');
      setPassword('');
      setConfirmPassword('');
      setError('');
      setIsMerge(false);
      setResendCooldown(0);
    }
    return () => clearInterval(cooldownRef.current);
  }, [open]);

  // Focus OTP input when step 2 becomes active
  useEffect(() => {
    if (step === 1) {
      setTimeout(() => otpInputRef.current?.focus(), 200);
    }
  }, [step]);

  const startCooldown = () => {
    setResendCooldown(RESEND_COOLDOWN);
    cooldownRef.current = setInterval(() => {
      setResendCooldown(prev => {
        if (prev <= 1) { clearInterval(cooldownRef.current); return 0; }
        return prev - 1;
      });
    }, 1000);
  };

  // ── Step 1: request OTP ────────────────────────────────────────────────────

  const handleRequestOtp = async () => {
    setError('');
    const trimmed = email.trim().toLowerCase();
    if (!trimmed || !/^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(trimmed)) {
      setError('Please enter a valid email address.');
      return;
    }
    setLoading(true);
    try {
      const res = await tmaApi.post('/api/miniapp/link-email/request', { email: trimmed });
      setIsMerge(res.data.merge === true);
      haptic.notification('success');
      setStep(1);
      startCooldown();
    } catch (err) {
      const msg = err.response?.data?.error || 'Failed to send code. Please try again.';
      setError(msg);
      haptic.notification('error');
    } finally {
      setLoading(false);
    }
  };

  const handleResend = async () => {
    if (resendCooldown > 0 || loading) return;
    setError('');
    setLoading(true);
    try {
      const res = await tmaApi.post('/api/miniapp/link-email/request', { email: email.trim().toLowerCase() });
      setIsMerge(res.data.merge === true);
      toast.success('New code sent!');
      setOtp('');
      startCooldown();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to resend code.');
    } finally {
      setLoading(false);
    }
  };

  // ── Step 2 → 3: OTP entered, move to password ─────────────────────────────

  const handleOtpNext = () => {
    setError('');
    if (otp.length !== OTP_LENGTH || !/^\d{6}$/.test(otp)) {
      setError('Please enter the 6-digit code from your email.');
      return;
    }
    setStep(2);
  };

  // ── Step 3: verify OTP + set password ─────────────────────────────────────

  const handleVerify = async () => {
    setError('');
    if (password.length < 8) {
      setError('Password must be at least 8 characters.');
      return;
    }
    if (password !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }
    setLoading(true);
    try {
      const res = await tmaApi.post('/api/miniapp/link-email/verify', { otp, password });
      const { status, user, token } = res.data;

      haptic.notification('success');

      if (status === 'merged') {
        toast.success('Accounts merged! Your Telegram is now linked to your existing account.');
      } else {
        toast.success('Email linked! Check your inbox to verify your address.');
      }

      onEmailLinked(user, token);
      onClose();
    } catch (err) {
      const msg = err.response?.data?.error || 'Verification failed. Please try again.';
      setError(msg);
      haptic.notification('error');
      // If OTP error, go back to step 1 so user can re-request
      if (err.response?.status === 400 && msg.toLowerCase().includes('invalid')) {
        setStep(1);
        setOtp('');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e, action) => {
    if (e.key === 'Enter') action();
  };

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <Dialog
      open={open}
      onClose={loading ? undefined : onClose}
      fullWidth
      maxWidth="xs"
      PaperProps={{ sx: { borderRadius: 3, bgcolor: 'background.paper' } }}
    >
      <DialogTitle sx={{ pb: 0 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <Shield sx={{ color: 'warning.main' }} />
          <Typography fontWeight={700} fontSize="1.05rem">Protect your account</Typography>
        </Box>
        <Typography variant="body2" color="text.secondary" mt={0.5}>
          Add email &amp; password for account recovery and website login.
        </Typography>
      </DialogTitle>

      <DialogContent sx={{ pt: 2 }}>
        {/* Stepper */}
        <Stepper activeStep={step} alternativeLabel sx={{ mb: 3 }}>
          {STEPS.map((label) => (
            <Step key={label}>
              <StepLabel sx={{ '& .MuiStepLabel-label': { fontSize: '0.7rem' } }}>
                {label}
              </StepLabel>
            </Step>
          ))}
        </Stepper>

        {error && (
          <Alert severity="error" sx={{ mb: 2, fontSize: '0.82rem' }} onClose={() => setError('')}>
            {error}
          </Alert>
        )}

        {/* ── Step 0: Email input ────────────────────────────────────────── */}
        {step === 0 && (
          <Box>
            <TextField
              fullWidth
              label="Email address"
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              onKeyDown={e => handleKeyDown(e, handleRequestOtp)}
              autoFocus
              disabled={loading}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <Email fontSize="small" color="action" />
                  </InputAdornment>
                ),
              }}
              sx={{ mb: 1.5 }}
            />
            <Typography variant="caption" color="text.secondary">
              We'll send a 6-digit verification code to this address.
            </Typography>
          </Box>
        )}

        {/* ── Step 1: OTP input ──────────────────────────────────────────── */}
        {step === 1 && (
          <Box>
            {isMerge && (
              <Alert severity="warning" sx={{ mb: 2, fontSize: '0.82rem' }}>
                This email is linked to an existing account. Verifying will merge your Telegram into that account.
              </Alert>
            )}
            <Typography variant="body2" color="text.secondary" mb={2}>
              Enter the 6-digit code sent to <strong>{email}</strong>.
            </Typography>
            <TextField
              fullWidth
              label="Verification code"
              value={otp}
              onChange={e => setOtp(e.target.value.replace(/\D/g, '').slice(0, OTP_LENGTH))}
              onKeyDown={e => handleKeyDown(e, handleOtpNext)}
              inputRef={otpInputRef}
              inputProps={{ maxLength: OTP_LENGTH, inputMode: 'numeric', style: { letterSpacing: '0.3em', fontSize: '1.3rem', textAlign: 'center' } }}
              disabled={loading}
              sx={{ mb: 1.5 }}
            />
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Typography variant="caption" color="text.disabled">
                Code expires in 10 minutes
              </Typography>
              <Button
                size="small"
                variant="text"
                onClick={handleResend}
                disabled={resendCooldown > 0 || loading}
                sx={{ fontSize: '0.72rem' }}
              >
                {resendCooldown > 0 ? `Resend in ${resendCooldown}s` : 'Resend code'}
              </Button>
            </Box>
          </Box>
        )}

        {/* ── Step 2: Password setup ─────────────────────────────────────── */}
        {step === 2 && (
          <Box>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
              <CheckCircle fontSize="small" color="success" />
              <Typography variant="body2" color="success.main">Code verified!</Typography>
            </Box>
            <Divider sx={{ mb: 2 }} />
            <TextField
              fullWidth
              label="Password"
              type={showPassword ? 'text' : 'password'}
              value={password}
              onChange={e => setPassword(e.target.value)}
              disabled={loading}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <Lock fontSize="small" color="action" />
                  </InputAdornment>
                ),
                endAdornment: (
                  <InputAdornment position="end">
                    <IconButton size="small" onClick={() => setShowPassword(v => !v)} edge="end">
                      {showPassword ? <VisibilityOff fontSize="small" /> : <Visibility fontSize="small" />}
                    </IconButton>
                  </InputAdornment>
                ),
              }}
              sx={{ mb: 1.5 }}
              helperText="Minimum 8 characters"
            />
            <TextField
              fullWidth
              label="Confirm password"
              type={showPassword ? 'text' : 'password'}
              value={confirmPassword}
              onChange={e => setConfirmPassword(e.target.value)}
              onKeyDown={e => handleKeyDown(e, handleVerify)}
              disabled={loading}
              error={confirmPassword.length > 0 && password !== confirmPassword}
              helperText={confirmPassword.length > 0 && password !== confirmPassword ? 'Passwords do not match' : ''}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <Lock fontSize="small" color="action" />
                  </InputAdornment>
                ),
              }}
            />
          </Box>
        )}
      </DialogContent>

      <DialogActions sx={{ px: 3, pb: 2.5, pt: 0, gap: 1 }}>
        {!loading && (
          <Button variant="text" onClick={onClose} sx={{ mr: 'auto', color: 'text.secondary' }}>
            Skip for now
          </Button>
        )}

        {step === 0 && (
          <Button
            variant="contained"
            onClick={handleRequestOtp}
            disabled={loading || !email.trim()}
            startIcon={loading ? <CircularProgress size={16} color="inherit" /> : null}
          >
            {loading ? 'Sending…' : 'Send code'}
          </Button>
        )}

        {step === 1 && (
          <Button
            variant="contained"
            onClick={handleOtpNext}
            disabled={otp.length !== OTP_LENGTH}
          >
            Continue
          </Button>
        )}

        {step === 2 && (
          <Button
            variant="contained"
            color="success"
            onClick={handleVerify}
            disabled={loading || password.length < 8 || password !== confirmPassword}
            startIcon={loading ? <CircularProgress size={16} color="inherit" /> : <Shield fontSize="small" />}
          >
            {loading ? 'Saving…' : 'Protect account'}
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );
}
