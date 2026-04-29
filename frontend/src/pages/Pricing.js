import React, { useState, useEffect } from 'react';
import {
  Box, AppBar, Toolbar, Typography, Button, Card, CardContent,
  Grid, Chip, List, ListItem, ListItemIcon, ListItemText,
  CircularProgress, IconButton, Dialog, DialogTitle, DialogContent,
  DialogActions, Stack, Alert, Accordion, AccordionSummary, AccordionDetails, Divider,
} from '@mui/material';
import { Check, ArrowBack, CurrencyBitcoin, LocalOffer, ExpandMore } from '@mui/icons-material';
import Switch from '@mui/material/Switch';
import { useNavigate } from 'react-router-dom';
import { toast } from 'react-toastify';
import { billing } from '../services/api';

const PLANS = [
  {
    id: 'free',
    name: 'Free',
    monthlyPrice: 0,
    annualPrice: 0,
    period: 'forever',
    color: 'default',
    features: [
      '1 bot',
      '1 group per bot',
      'Basic verification',
      'Welcome messages',
      'XP system',
      'Basic moderation commands',
    ],
  },
  {
    id: 'pro',
    name: 'Pro',
    monthlyPrice: 9,
    annualPrice: 90,
    period: '/month',
    color: 'primary',
    popular: true,
    features: [
      '5 bots',
      'Unlimited groups',
      'All verification types',
      'Advanced AutoMod',
      'Scheduled messages',
      'Raid management',
      'Analytics dashboard',
      'Priority support',
    ],
  },
  {
    id: 'enterprise',
    name: 'Enterprise',
    monthlyPrice: 49,
    annualPrice: 470,
    period: '/month',
    color: 'secondary',
    features: [
      '50 bots',
      'Unlimited groups',
      'All Pro features',
      'Custom rank cards',
      'API access',
      'Dedicated support',
      'SLA guarantee',
      'Custom integrations',
    ],
  },
];

export default function Pricing() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [selectedTier, setSelectedTier] = useState(null);
  const [methodLoading, setMethodLoading] = useState('');
  const [currentTier, setCurrentTier] = useState('free');
  const [subExpires, setSubExpires] = useState(null);
  const [annual, setAnnual] = useState(false);
  const token = localStorage.getItem('token');

  // Load current subscription so we can show correct "Current Plan" state
  useEffect(() => {
    if (!token) return;
    billing.getSubscription()
      .then((res) => {
        const sub = res.data.subscription;
        setCurrentTier(sub.tier || 'free');
        setSubExpires(sub.expires || null);
      })
      .catch(() => {
        // Fallback to localStorage user
        try {
          const u = JSON.parse(localStorage.getItem('user') || '{}');
          setCurrentTier(u.subscription_tier || 'free');
        } catch { /* ignore */ }
      });
  }, [token]);

  const isCurrentPlan = (planId) => planId === currentTier;

  const handleUpgrade = (tier) => {
    if (!token) { navigate('/register'); return; }
    if (tier === 'free' || isCurrentPlan(tier)) return;
    setSelectedTier(tier);
    setDialogOpen(true);
  };

  const handlePaymentMethod = async () => {
    setMethodLoading('crypto');
    try {
      const res = await billing.cryptoCheckout({ tier: selectedTier, annual });

      if (res.data.admin_upgrade) {
        toast.success(res.data.message || `Plan switched to ${selectedTier}`);
        setCurrentTier(selectedTier);
        setDialogOpen(false);
        setTimeout(() => navigate('/dashboard'), 1200);
        return;
      }

      window.location.href = res.data.url;
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to start checkout. Please try again.');
    } finally {
      setMethodLoading('');
    }
  };

  const handleCloseDialog = () => {
    if (methodLoading) return;
    setDialogOpen(false);
    setSelectedTier(null);
  };

  const getPlanButtonLabel = (plan) => {
    if (plan.id === 'free') return 'Free Forever';
    if (isCurrentPlan(plan.id)) return 'Current Plan';
    return `Get ${plan.name}`;
  };

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <AppBar position="sticky" elevation={0} sx={{ borderBottom: '1px solid', borderColor: 'divider' }}>
        <Toolbar>
          {token && (
            <IconButton edge="start" onClick={() => navigate('/dashboard')} sx={{ mr: 1 }}>
              <ArrowBack />
            </IconButton>
          )}
          <Typography variant="h6" fontWeight={700} sx={{ flexGrow: 1 }}>
            Telegizer
          </Typography>
          {!token && (
            <Stack direction="row" spacing={1}>
              <Button onClick={() => navigate('/login')}>Sign In</Button>
              <Button variant="contained" onClick={() => navigate('/register')}>Start Free</Button>
            </Stack>
          )}
        </Toolbar>
      </AppBar>

      <Box sx={{ maxWidth: 1100, mx: 'auto', p: { xs: 2, md: 3 }, textAlign: 'center' }}>
        <Typography variant="h3" fontWeight={700} mb={1} mt={4} sx={{ fontSize: { xs: '1.9rem', sm: '2.5rem', md: '3rem' } }}>
          Simple, Transparent Pricing
        </Typography>
        <Typography variant="h6" color="text.secondary" mb={3} sx={{ fontSize: { xs: '1rem', md: '1.25rem' } }}>
          Start free, scale as your communities grow
        </Typography>

        {/* Annual / Monthly toggle */}
        <Stack direction="row" spacing={1} alignItems="center" justifyContent="center" mb={4}>
          <Typography variant="body2" color={annual ? 'text.secondary' : 'text.primary'} fontWeight={annual ? 400 : 600}>
            Monthly
          </Typography>
          <Switch checked={annual} onChange={(e) => setAnnual(e.target.checked)} color="primary" />
          <Typography variant="body2" color={annual ? 'text.primary' : 'text.secondary'} fontWeight={annual ? 600 : 400}>
            Annual
          </Typography>
          <Chip
            label="Save ~17%"
            size="small"
            color="success"
            icon={<LocalOffer fontSize="small" />}
            sx={{ fontWeight: 700 }}
          />
        </Stack>

        {subExpires && (
          <Chip
            label={`${currentTier.charAt(0).toUpperCase() + currentTier.slice(1)} plan â€” expires ${new Date(subExpires).toLocaleDateString()}`}
            color="primary"
            sx={{ mb: 3 }}
          />
        )}

        <Grid container spacing={3} justifyContent="center" sx={{ mb: 2 }}>
          {PLANS.map((plan) => (
            <Grid item xs={12} sm={6} md={4} key={plan.id}>
              {/* Wrapper reserves badge space for ALL cards so they stay the same height */}
              <Box sx={{ position: 'relative', pt: '14px', height: '100%' }}>
                {plan.popular && !isCurrentPlan(plan.id) && (
                  <Chip
                    label="Most Popular"
                    color="primary"
                    size="small"
                    sx={{
                      position: 'absolute',
                      top: 0,
                      left: '50%',
                      transform: 'translateX(-50%)',
                      zIndex: 1,
                      fontWeight: 700,
                      whiteSpace: 'nowrap',
                    }}
                  />
                )}
                {isCurrentPlan(plan.id) && (
                  <Chip
                    label="Your Plan"
                    color="success"
                    size="small"
                    sx={{
                      position: 'absolute',
                      top: 0,
                      left: '50%',
                      transform: 'translateX(-50%)',
                      zIndex: 1,
                      fontWeight: 700,
                      whiteSpace: 'nowrap',
                    }}
                  />
                )}
                <Card
                  sx={{
                    height: '100%',
                    display: 'flex',
                    flexDirection: 'column',
                    border: plan.popular ? '2px solid' : '1px solid',
                    borderColor: isCurrentPlan(plan.id) ? 'success.main' : plan.popular ? 'primary.main' : 'divider',
                  }}
                >
                <CardContent sx={{ flexGrow: 1, p: { xs: 2.5, md: 3 } }}>
                  <Typography variant="h5" fontWeight={700} mb={1}>{plan.name}</Typography>
                  <Box sx={{ mb: 1 }}>
                    {plan.id === 'free' ? (
                      <>
                        <Typography component="span" fontWeight={800} sx={{ fontSize: { xs: '2.2rem', md: '3rem' } }}>$0</Typography>
                        <Typography component="span" variant="body1" color="text.secondary"> forever</Typography>
                      </>
                    ) : annual ? (
                      <>
                        <Typography component="span" fontWeight={800} sx={{ fontSize: { xs: '2.2rem', md: '3rem' } }}>
                          ${Math.round(plan.annualPrice / 12)}
                        </Typography>
                        <Typography component="span" variant="body1" color="text.secondary">/month</Typography>
                        <Typography variant="caption" display="block" color="success.main" fontWeight={600} mb={1}>
                          ${plan.annualPrice}/year · ~2 months free
                        </Typography>
                      </>
                    ) : (
                      <>
                        <Typography component="span" fontWeight={800} sx={{ fontSize: { xs: '2.2rem', md: '3rem' } }}>
                          ${plan.monthlyPrice}
                        </Typography>
                        <Typography component="span" variant="body1" color="text.secondary">/month</Typography>
                      </>
                    )}
                  </Box>
                  <Button
                    fullWidth
                    variant={isCurrentPlan(plan.id) ? 'outlined' : plan.popular ? 'contained' : 'outlined'}
                    color={isCurrentPlan(plan.id) ? 'success' : plan.color === 'default' ? 'inherit' : plan.color}
                    onClick={() => handleUpgrade(plan.id)}
                    disabled={loading === plan.id || plan.id === 'free' || isCurrentPlan(plan.id)}
                    sx={{ mb: 3 }}
                  >
                    {loading === plan.id
                      ? <CircularProgress size={20} color="inherit" />
                      : getPlanButtonLabel(plan)}
                  </Button>
                  <List dense disablePadding>
                    {plan.features.map((feature) => (
                      <ListItem key={feature} disableGutters>
                        <ListItemIcon sx={{ minWidth: 28 }}>
                          <Check fontSize="small" color="success" />
                        </ListItemIcon>
                        <ListItemText primary={feature} primaryTypographyProps={{ variant: 'body2' }} />
                      </ListItem>
                    ))}
                  </List>
                </CardContent>
              </Card>
              </Box>
            </Grid>
          ))}
        </Grid>

        <Typography variant="body2" color="text.secondary" mt={4} mb={1}>
          All plans include a 14-day money-back guarantee. No hidden fees.
        </Typography>
        <Typography variant="caption" color="text.disabled">
          Payments accepted via crypto — USDT, BTC, ETH, BNB, TRX, SOL and 300+ coins via NOWPayments
        </Typography>

        {/* FAQ */}
        <Divider sx={{ my: 6 }} />
        <Typography variant="overline" color="primary.main" fontWeight={700} display="block" mb={1}>
          FAQ
        </Typography>
        <Typography variant="h5" fontWeight={800} mb={4}>
          Frequently asked questions
        </Typography>
        <Box sx={{ textAlign: 'left', maxWidth: 720, mx: 'auto', mb: 4 }}>
          {[
            {
              q: 'What happens if I cancel or my plan expires?',
              a: 'Your bots keep running but paid features become read-only. Free plan features stay active indefinitely. Renew any time and everything restores instantly — no data loss.',
            },
            {
              q: 'What coins and payment methods are supported?',
              a: 'We accept USDT, BTC, ETH, BNB, TRX, SOL, and 300+ coins via NOWPayments. All payments are processed on-chain — no card or bank transfer required.',
            },
            {
              q: 'How long do crypto payments take to confirm?',
              a: 'Most payments confirm in 1–10 minutes. Bitcoin and Ethereum can take 10–30+ minutes during congestion. Your plan activates automatically once the blockchain confirms — no manual steps.',
            },
            {
              q: 'Is my bot token stored securely?',
              a: 'Yes. Bot tokens are encrypted at rest using AES-256 (Fernet) before being written to the database. They are never stored in plain text and never appear in API responses.',
            },
            {
              q: 'Can I manage multiple groups with one bot?',
              a: 'Yes. One bot can be added to unlimited Telegram groups. Each group has its own settings, moderation rules, XP system, and scheduled content.',
            },
            {
              q: 'Can I get a refund?',
              a: 'Yes, within 14 days of payment if the platform did not work as described. Contact support with your payment ID. Crypto refunds are processed back to the originating wallet.',
            },
          ].map(({ q, a }) => (
            <Accordion key={q} disableGutters elevation={0}
              sx={{ border: '1px solid', borderColor: 'divider', mb: 1, borderRadius: '8px !important', '&:before': { display: 'none' } }}>
              <AccordionSummary expandIcon={<ExpandMore />}>
                <Typography fontWeight={600}>{q}</Typography>
              </AccordionSummary>
              <AccordionDetails>
                <Typography variant="body2" color="text.secondary" lineHeight={1.7}>{a}</Typography>
              </AccordionDetails>
            </Accordion>
          ))}
        </Box>
      </Box>

      {/* Payment dialog — crypto only */}
      <Dialog open={dialogOpen} onClose={handleCloseDialog} maxWidth=”xs” fullWidth>
        <DialogTitle sx={{ fontWeight: 700, textAlign: 'center', pb: 1 }}>
          Complete Your Upgrade
        </DialogTitle>
        <DialogContent>
          <Typography variant=”body2” color=”text.secondary” textAlign=”center” mb={3}>
            {selectedTier && (
              <>
                <strong>{selectedTier.charAt(0).toUpperCase() + selectedTier.slice(1)}</strong> Plan
                {' — '}<strong>{annual ? 'Annual' : 'Monthly'}</strong>
                {annual && <> · <span style={{ color: '#66bb6a' }}>~2 months free</span></>}
              </>
            )}
          </Typography>

          <Button
            fullWidth
            variant=”contained”
            color=”warning”
            size=”large”
            startIcon={methodLoading ? <CircularProgress size={18} color=”inherit” /> : <CurrencyBitcoin />}
            onClick={handlePaymentMethod}
            disabled={!!methodLoading}
            sx={{ py: 1.8, mb: 2 }}
          >
            {methodLoading ? 'Redirecting…' : 'Pay with Crypto'}
          </Button>

          <Typography variant=”caption” color=”text.disabled” display=”block” textAlign=”center” mb={1}>
            USDT · BTC · ETH · BNB · TRX · SOL and 300+ coins via NOWPayments
          </Typography>

          <Alert severity=”info” sx={{ mt: 2 }} icon={false}>
            <Typography variant=”caption”>
              Your plan activates automatically within 1–10 minutes of blockchain confirmation.
              No manual steps needed.
            </Typography>
          </Alert>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={handleCloseDialog} disabled={!!methodLoading} fullWidth variant=”text”>
            Cancel
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
