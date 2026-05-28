import React, { useState, useEffect, useCallback } from 'react';
import { openSupportEmail } from '../config/support';
import {
  Box, AppBar, Toolbar, Typography, Button, Card, CardContent,
  Chip, Stack, Divider, Alert, IconButton,
  Grid, Table, TableBody, TableCell, TableContainer, TableHead,
  TableRow, TablePagination, Dialog, DialogTitle, DialogContent,
  DialogContentText, DialogActions, CircularProgress,
} from '@mui/material';
import {
  ArrowBack, Upgrade, CheckCircle,
  CurrencyBitcoin, Refresh, ReceiptLong, Cancel, CreditCard, OpenInNew,
} from '@mui/icons-material';
import Skeleton from '@mui/material/Skeleton';
import { useNavigate } from 'react-router-dom';
import TelegizerLogo from '../components/TelegizerLogo';
import { toast } from 'react-toastify';
import { billing } from '../services/api';
import { track } from '../services/analytics';

const TIER_FEATURES = {
  free: ['1 bot', '3 groups per bot', 'Basic moderation', 'Welcome messages', 'XP system'],
  pro: ['3 bots', 'Unlimited groups', 'Advanced AutoMod', 'Scheduled messages', 'Analytics dashboard', 'Priority support'],
  enterprise: ['50 bots', 'Unlimited groups', 'All Pro features', 'API access', 'SLA guarantee', 'Dedicated support'],
};

const TIER_PRICES = { free: '$0', pro: '$9/mo', enterprise: '$49/mo' };

const PROVIDER_LABELS = { nowpayments: 'Crypto (NOWPayments)' };
const STATUS_COLORS = { confirmed: 'success', pending: 'warning', failed: 'error' };


export default function Billing() {
  const navigate = useNavigate();
  const [subscription, setSubscription] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [history, setHistory] = useState([]);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [historyPage, setHistoryPage] = useState(0);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [cancelDialogOpen, setCancelDialogOpen] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [cryptoLoading, setCryptoLoading] = useState(false);

  const fetchSub = useCallback(async () => {
    try {
      const res = await billing.getSubscription();
      setSubscription(res.data.subscription);
    } catch {
      toast.error('Failed to load subscription info');
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchHistory = useCallback(async (page = 0) => {
    setHistoryLoading(true);
    try {
      const res = await billing.getHistory({ page: page + 1, per_page: 10 });
      setHistory(res.data.history || []);
      setHistoryTotal(res.data.total || 0);
    } catch {
      // silent — empty state shown
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    try {
      const res = await billing.getSubscription();
      setSubscription(res.data.subscription);
      toast.success('Subscription refreshed');
    } catch {
      toast.error('Failed to refresh subscription');
    } finally {
      setRefreshing(false);
    }
  }, []);

  const handleCancelConfirm = useCallback(async () => {
    setCancelling(true);
    try {
      const resp = await billing.cancelSubscription();
      track('subscription_cancelled', {
        plan: resp.data.plan || 'pro',
        tenure_days: resp.data.tenure_days,
        reason: 'user_initiated',
      });
      toast.success('Subscription cancelled. You are now on the Free plan.');
      setCancelDialogOpen(false);
      await fetchSub();
    } catch (err) {
      toast.error(err?.response?.data?.error || 'Failed to cancel subscription');
    } finally {
      setCancelling(false);
    }
  }, [fetchSub]);

  const handleVerifyPayment = useCallback(async () => {
    setVerifying(true);
    try {
      const res = await billing.verifyPayment();
      if (res.data.upgraded) {
        toast.success(`Payment confirmed! Your ${res.data.plan} plan is now active.`);
        await fetchSub();
      } else {
        toast.info(`Payment status: ${res.data.status || 'pending'}. Please wait a few minutes and try again.`);
      }
    } catch {
      toast.error('Failed to verify payment. Please try again.');
    } finally {
      setVerifying(false);
    }
  }, [fetchSub]);

  const handleCryptoCheckout = useCallback(async (targetTier, interval = 'monthly') => {
    setCryptoLoading(true);
    try {
      const res = await billing.cryptoCheckout({ tier: targetTier, interval });
      if (res.data.checkout_url || res.data.invoice_url) {
        window.open(res.data.checkout_url || res.data.invoice_url, '_blank', 'noopener,noreferrer');
      }
    } catch (err) {
      const msg = err?.response?.data?.error || 'Failed to start crypto checkout';
      toast.error(msg);
    } finally {
      setCryptoLoading(false);
    }
  }, []);

  useEffect(() => { fetchSub(); fetchHistory(0); }, [fetchSub, fetchHistory]);

  const tier = subscription?.tier || 'free';
  const expires = subscription?.expires ? new Date(subscription.expires) : null;
  const isExpired = subscription?.is_expired;
  const daysLeft = expires ? Math.max(0, Math.ceil((expires - Date.now()) / 86400000)) : null;

  return (
    <Box sx={{ minHeight: '100vh' }}>
      <AppBar position="sticky" elevation={0}>
        <Toolbar>
          <IconButton edge="start" onClick={() => navigate('/dashboard')} sx={{ mr: 1, color: 'text.secondary' }}>
            <ArrowBack />
          </IconButton>
          <Box sx={{ flexGrow: 1 }}>
            <TelegizerLogo size="sm" />
          </Box>
        </Toolbar>
      </AppBar>

      <Box sx={{ maxWidth: 800, mx: 'auto', p: { xs: 2, md: 3 } }}>
        {loading ? (
          <>
            <Card sx={{ mb: 3 }}>
              <CardContent sx={{ p: { xs: 2, md: 3 } }}>
                <Skeleton width="30%" height={16} sx={{ mb: 1 }} />
                <Skeleton width="50%" height={48} sx={{ mb: 1 }} />
                <Skeleton width="20%" height={24} />
              </CardContent>
            </Card>
            <Card sx={{ mb: 3 }}>
              <CardContent sx={{ p: { xs: 2, md: 3 } }}>
                <Skeleton width="40%" height={20} sx={{ mb: 2 }} />
                {[1, 2, 3, 4].map((i) => (
                  <Box key={i} sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                    <Skeleton variant="circular" width={20} height={20} />
                    <Skeleton width="60%" height={16} />
                  </Box>
                ))}
              </CardContent>
            </Card>
          </>
        ) : (
          <>
            {/* Current Plan */}
            <Card
              sx={{
                mb: 3,
                background: tier === 'enterprise'
                  ? 'linear-gradient(135deg, rgba(157,108,247,0.1) 0%, rgba(15,29,53,0.95) 100%)'
                  : tier === 'pro'
                  ? 'linear-gradient(135deg, rgba(61,142,248,0.1) 0%, rgba(15,29,53,0.95) 100%)'
                  : undefined,
                borderColor: tier === 'enterprise'
                  ? 'rgba(157,108,247,0.35)'
                  : tier === 'pro'
                  ? 'rgba(61,142,248,0.35)'
                  : undefined,
                boxShadow: tier !== 'free'
                  ? `0 4px 24px rgba(0,0,0,0.4), 0 0 0 1px ${tier === 'enterprise' ? 'rgba(157,108,247,0.18)' : 'rgba(61,142,248,0.18)'}`
                  : undefined,
              }}
            >
              <CardContent sx={{ p: { xs: 2, md: 3 } }}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 2 }}>
                  <Box>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <Typography variant="overline" color="text.secondary">Current Plan</Typography>
                      <IconButton
                        size="small"
                        onClick={handleRefresh}
                        disabled={refreshing}
                        title="Refresh subscription status"
                        sx={{ mt: -0.5 }}
                      >
                        <Refresh fontSize="small" sx={{ animation: refreshing ? 'spin 1s linear infinite' : 'none', '@keyframes spin': { '0%': { transform: 'rotate(0deg)' }, '100%': { transform: 'rotate(360deg)' } } }} />
                      </IconButton>
                    </Box>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mt: 0.5 }}>
                      <Typography variant="h4" fontWeight={800}>
                        {tier.charAt(0).toUpperCase() + tier.slice(1)}
                      </Typography>
                      <Chip
                        label={isExpired ? 'EXPIRED' : 'ACTIVE'}
                        color={isExpired ? 'error' : 'success'}
                        size="small"
                      />
                    </Box>
                    <Typography variant="h6" color="primary.main" fontWeight={600} mt={0.5}>
                      {TIER_PRICES[tier]}
                    </Typography>
                  </Box>

                  <Stack direction="row" spacing={1} flexWrap="wrap">
                    {tier !== 'enterprise' && (
                      <Button
                        variant="contained"
                        startIcon={<Upgrade />}
                        onClick={() => navigate('/pricing')}
                        size="large"
                      >
                        {isExpired ? 'Renew Plan' : 'Upgrade Plan'}
                      </Button>
                    )}
                    {tier !== 'free' && !isExpired && (
                      <Button
                        variant="outlined"
                        color="error"
                        startIcon={<Cancel />}
                        onClick={() => setCancelDialogOpen(true)}
                        size="large"
                      >
                        Cancel Plan
                      </Button>
                    )}
                  </Stack>
                </Box>

                {expires && (
                  <Box sx={{ mt: 2 }}>
                    <Divider sx={{ mb: 2 }} />
                    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={{ xs: 1, sm: 4 }} flexWrap="wrap">
                      <Box>
                        <Typography variant="caption" color="text.secondary">Expiry Date</Typography>
                        <Typography variant="body2" fontWeight={600}>
                          {expires.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })}
                        </Typography>
                      </Box>
                      {!isExpired && daysLeft !== null && (
                        <Box>
                          <Typography variant="caption" color="text.secondary">Days Remaining</Typography>
                          <Typography
                            variant="body2"
                            fontWeight={600}
                            color={daysLeft <= 5 ? 'error.main' : daysLeft <= 10 ? 'warning.main' : 'text.primary'}
                          >
                            {daysLeft} day{daysLeft !== 1 ? 's' : ''}
                          </Typography>
                        </Box>
                      )}
                    </Stack>
                  </Box>
                )}

                {isExpired && (
                  <Alert severity="error" sx={{ mt: 2 }}>
                    Your subscription has expired. Your bots continue to run but paid features are
                    restricted. Renew to restore full access.
                  </Alert>
                )}

                {!isExpired && daysLeft !== null && daysLeft <= 5 && (
                  <Alert severity="warning" sx={{ mt: 2 }}>
                    Your subscription expires in {daysLeft} day{daysLeft !== 1 ? 's' : ''}. Renew now to avoid interruption.
                  </Alert>
                )}
              </CardContent>
            </Card>

            {/* Included Features */}
            <Card sx={{ mb: 3, background: 'rgba(11,22,38,0.8)' }}>
              <CardContent sx={{ p: { xs: 2, md: 3 } }}>
                <Typography variant="subtitle1" fontWeight={700} mb={2}>
                  What's included in your plan
                </Typography>
                <Grid container spacing={1}>
                  {TIER_FEATURES[tier]?.map((feature) => (
                    <Grid item xs={12} sm={6} key={feature}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <CheckCircle fontSize="small" color="success" />
                        <Typography variant="body2">{feature}</Typography>
                      </Box>
                    </Grid>
                  ))}
                </Grid>
              </CardContent>
            </Card>

            {/* Payment Methods */}
            <Card sx={{ mb: 3 }}>
              <CardContent sx={{ p: { xs: 2, md: 3 } }}>
                <Typography variant="subtitle1" fontWeight={700} mb={2}>
                  Payment Methods
                </Typography>
                <Stack spacing={2}>
                  {/* Crypto — PRIMARY CTA */}
                  <Box
                    role="button"
                    tabIndex={0}
                    onClick={() => !cryptoLoading && handleCryptoCheckout(tier === 'free' ? 'pro' : tier)}
                    onKeyDown={e => e.key === 'Enter' && !cryptoLoading && handleCryptoCheckout(tier === 'free' ? 'pro' : tier)}
                    sx={{
                      display: 'flex', alignItems: 'center', gap: 2,
                      p: { xs: 1.75, md: 2.25 },
                      border: '2px solid', borderColor: 'success.main',
                      borderRadius: 2, cursor: cryptoLoading ? 'wait' : 'pointer',
                      transition: 'box-shadow 0.18s, border-color 0.18s, background 0.18s',
                      '&:hover': {
                        boxShadow: '0 0 0 3px rgba(34,197,94,0.18)',
                        bgcolor: 'rgba(34,197,94,0.04)',
                      },
                      '&:focus-visible': {
                        outline: '2px solid',
                        outlineColor: 'success.main',
                        outlineOffset: 2,
                      },
                    }}
                  >
                    <CurrencyBitcoin sx={{ color: 'warning.main', fontSize: 28, flexShrink: 0 }} />
                    <Box sx={{ flexGrow: 1, minWidth: 0 }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                        <Typography variant="body2" fontWeight={700}>Pay with Crypto</Typography>
                        <Chip label="Recommended" color="success" size="small" sx={{ height: 18, fontSize: '0.65rem' }} />
                      </Box>
                      <Typography variant="caption" color="text.secondary">
                        USDT, BTC, ETH, BNB and 300+ coins via NOWPayments
                      </Typography>
                    </Box>
                    <Button
                      variant="contained"
                      color="success"
                      size="small"
                      disabled={cryptoLoading}
                      tabIndex={-1}
                      startIcon={cryptoLoading ? <CircularProgress size={13} color="inherit" /> : <OpenInNew fontSize="small" />}
                      sx={{ flexShrink: 0, pointerEvents: 'none' }}
                    >
                      {cryptoLoading ? 'Opening…' : 'Upgrade'}
                    </Button>
                  </Box>

                  {/* Card payments — Coming Soon */}
                  <Box
                    sx={{
                      display: 'flex', alignItems: 'center', gap: 2,
                      p: { xs: 1.75, md: 2.25 },
                      border: '1px solid', borderColor: 'divider',
                      borderRadius: 2, opacity: 0.55, cursor: 'not-allowed',
                    }}
                  >
                    <CreditCard sx={{ color: 'text.disabled', fontSize: 28, flexShrink: 0 }} />
                    <Box sx={{ flexGrow: 1, minWidth: 0 }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                        <Typography variant="body2" fontWeight={600} color="text.secondary">Pay with Card</Typography>
                        <Chip label="Coming Soon" size="small" sx={{ height: 18, fontSize: '0.65rem' }} />
                      </Box>
                      <Typography variant="caption" color="text.disabled">
                        Visa, Mastercard, Apple Pay and more
                      </Typography>
                    </Box>
                  </Box>

                  {/* Verify pending crypto payment */}
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, p: { xs: 1.5, md: 2 }, bgcolor: 'action.hover', borderRadius: 2 }}>
                    <Refresh color="action" sx={{ flexShrink: 0 }} />
                    <Box sx={{ flexGrow: 1, minWidth: 0 }}>
                      <Typography variant="body2" fontWeight={600}>Already paid with crypto?</Typography>
                      <Typography variant="caption" color="text.secondary">
                        If your plan hasn't activated yet, click to manually verify your payment.
                      </Typography>
                    </Box>
                    <Button
                      variant="outlined"
                      size="small"
                      onClick={handleVerifyPayment}
                      disabled={verifying}
                      sx={{ flexShrink: 0 }}
                      startIcon={verifying ? <CircularProgress size={13} /> : <Refresh fontSize="small" />}
                    >
                      {verifying ? 'Checking…' : 'Verify'}
                    </Button>
                  </Box>
                </Stack>
              </CardContent>
            </Card>

            {/* Payment History */}
            <Card sx={{ mb: 3 }}>
              <CardContent sx={{ p: { xs: 2, md: 3 } }}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                  <Typography variant="subtitle1" fontWeight={700}>Payment History</Typography>
                </Box>
                {historyLoading ? (
                  <Box>
                    {[1, 2, 3].map((i) => (
                      <Box key={i} sx={{ display: 'flex', gap: 2, mb: 1.5 }}>
                        <Skeleton width="15%" height={20} />
                        <Skeleton width="12%" height={20} />
                        <Skeleton width="20%" height={20} />
                        <Skeleton width="10%" height={20} />
                        <Skeleton width="12%" height={20} />
                        <Skeleton width="20%" height={20} />
                      </Box>
                    ))}
                  </Box>
                ) : history.length === 0 ? (
                  <Box sx={{ textAlign: 'center', py: 4 }}>
                    <ReceiptLong sx={{ fontSize: 48, color: 'text.disabled', mb: 1 }} />
                    <Typography variant="body2" color="text.secondary">
                      No payments recorded yet.
                    </Typography>
                    <Typography variant="caption" color="text.disabled" display="block" mt={0.5}>
                      Your transactions will appear here after your first payment.
                    </Typography>
                  </Box>
                ) : (
                  <>
                    <TableContainer sx={{ overflowX: 'auto' }}>
                      <Table size="small" sx={{ minWidth: 560 }}>
                        <TableHead>
                          <TableRow>
                            <TableCell>Date</TableCell>
                            <TableCell>Plan</TableCell>
                            <TableCell>Billing</TableCell>
                            <TableCell>Provider</TableCell>
                            <TableCell align="right">Amount</TableCell>
                            <TableCell>Status</TableCell>
                            <TableCell>Transaction ID</TableCell>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {history.map((row) => (
                            <TableRow key={row.id} hover>
                              <TableCell sx={{ whiteSpace: 'nowrap' }}>
                                {new Date(row.created_at).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })}
                              </TableCell>
                              <TableCell>
                                <Chip label={row.plan.charAt(0).toUpperCase() + row.plan.slice(1)}
                                  size="small" color={row.plan === 'enterprise' ? 'secondary' : 'primary'} />
                              </TableCell>
                              <TableCell sx={{ fontSize: '0.75rem' }}>
                                {(row.billing_period || 'monthly') === 'annual' ? 'Annual' : 'Monthly'}
                              </TableCell>
                              <TableCell sx={{ fontSize: '0.75rem' }}>
                                {PROVIDER_LABELS[row.provider] || row.provider}
                              </TableCell>
                              <TableCell align="right" sx={{ fontWeight: 600 }}>
                                {row.amount_usd ? `$${(row.amount_usd / 100).toFixed(2)}` : '—'}
                              </TableCell>
                              <TableCell>
                                <Chip label={row.status} size="small"
                                  color={STATUS_COLORS[row.status] || 'default'} />
                              </TableCell>
                              <TableCell sx={{ fontSize: '0.72rem', color: 'text.secondary', fontFamily: 'monospace' }}>
                                {row.payment_id_masked || '—'}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </TableContainer>
                    <TablePagination
                      component="div"
                      count={historyTotal}
                      page={historyPage}
                      onPageChange={(_, p) => { setHistoryPage(p); fetchHistory(p); }}
                      rowsPerPage={10}
                      rowsPerPageOptions={[10]}
                    />
                  </>
                )}
              </CardContent>
            </Card>

            {/* Upgrade CTA (if not enterprise) */}
            {tier !== 'enterprise' && !isExpired && (
              <Card
                sx={{
                  background: 'linear-gradient(135deg, #1565c0 0%, #7c4dff 100%)',
                  border: 'none',
                }}
              >
                <CardContent sx={{ p: { xs: 2, md: 3 }, textAlign: 'center' }}>
                  <Typography variant="h6" fontWeight={700} color="white" mb={1}>
                    {tier === 'free'
                      ? 'Unlock the full power of Telegizer'
                      : 'Scale to Enterprise — 50 bots, dedicated support'}
                  </Typography>
                  <Typography variant="body2" sx={{ color: 'rgba(255,255,255,0.8)', mb: 2 }}>
                    {tier === 'free'
                      ? 'Pro plan: 5 bots, unlimited groups, scheduling & analytics. Just $9/month.'
                      : 'API access, SLA guarantee, and dedicated account management.'}
                  </Typography>
                  <Button
                    variant="contained"
                    onClick={() => navigate('/pricing')}
                    sx={{ bgcolor: 'white', color: 'primary.main', '&:hover': { bgcolor: '#f0f0f0' } }}
                  >
                    {tier === 'free' ? 'Upgrade to Pro — $9/mo' : 'Upgrade to Enterprise — $49/mo'}
                  </Button>
                </CardContent>
              </Card>
            )}

            {/* Support */}
            <Box sx={{ mt: 3, textAlign: 'center' }}>
              <Typography variant="caption" color="text.disabled">
                Questions about your billing?{' '}
                <Typography
                  component="span"
                  variant="caption"
                  color="primary.main"
                  sx={{ cursor: 'pointer' }}
                  onClick={openSupportEmail}
                >
                  Contact support
                </Typography>
                {' '}· 14-day money-back guarantee on first purchase
              </Typography>
            </Box>
          </>
        )}

        {/* Cancel confirmation dialog */}
        <Dialog open={cancelDialogOpen} onClose={() => !cancelling && setCancelDialogOpen(false)} fullWidth maxWidth="xs">
          <DialogTitle>Cancel your subscription?</DialogTitle>
          <DialogContent>
            <DialogContentText>
              Your plan will be immediately downgraded to <strong>Free</strong>. You will lose access
              to paid features and any remaining days will not be refunded. This action cannot be undone.
            </DialogContentText>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setCancelDialogOpen(false)} disabled={cancelling}>
              Keep Plan
            </Button>
            <Button
              onClick={handleCancelConfirm}
              color="error"
              variant="contained"
              disabled={cancelling}
            >
              {cancelling ? 'Cancelling…' : 'Yes, Cancel Subscription'}
            </Button>
          </DialogActions>
        </Dialog>
      </Box>
    </Box>
  );
}
