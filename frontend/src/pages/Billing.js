import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, AppBar, Toolbar, Typography, Button, Card, CardContent,
  Chip, CircularProgress, Stack, Divider, Alert, IconButton,
  Grid,
} from '@mui/material';
import {
  SmartToy, ArrowBack, Upgrade, CheckCircle, HourglassTop,
  CurrencyBitcoin, CreditCard, OpenInNew,
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { toast } from 'react-toastify';
import { billing } from '../services/api';

const TIER_COLORS = { free: 'default', pro: 'primary', enterprise: 'secondary' };

const TIER_FEATURES = {
  free: ['1 bot', '1 group per bot', 'Basic moderation', 'Welcome messages', 'XP system'],
  pro: ['5 bots', 'Unlimited groups', 'Advanced AutoMod', 'Scheduled messages', 'Analytics dashboard', 'Priority support'],
  enterprise: ['50 bots', 'Unlimited groups', 'All Pro features', 'API access', 'SLA guarantee', 'Dedicated support'],
};

const TIER_PRICES = { free: '$0', pro: '$9/mo', enterprise: '$49/mo' };

export default function Billing() {
  const navigate = useNavigate();
  const [subscription, setSubscription] = useState(null);
  const [loading, setLoading] = useState(true);

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

  useEffect(() => { fetchSub(); }, [fetchSub]);

  const tier = subscription?.tier || 'free';
  const expires = subscription?.expires ? new Date(subscription.expires) : null;
  const isExpired = subscription?.is_expired;
  const daysLeft = expires ? Math.max(0, Math.ceil((expires - Date.now()) / 86400000)) : null;

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <AppBar position="sticky" elevation={0} sx={{ borderBottom: '1px solid', borderColor: 'divider' }}>
        <Toolbar>
          <IconButton edge="start" onClick={() => navigate('/dashboard')} sx={{ mr: 1 }}>
            <ArrowBack />
          </IconButton>
          <SmartToy sx={{ mr: 1, color: 'primary.main' }} />
          <Typography variant="h6" fontWeight={700} sx={{ flexGrow: 1 }}>
            BotForge — Billing
          </Typography>
        </Toolbar>
      </AppBar>

      <Box sx={{ maxWidth: 800, mx: 'auto', p: 3 }}>
        {loading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', mt: 8 }}>
            <CircularProgress />
          </Box>
        ) : (
          <>
            {/* Current Plan */}
            <Card sx={{ mb: 3 }}>
              <CardContent sx={{ p: 3 }}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 2 }}>
                  <Box>
                    <Typography variant="overline" color="text.secondary">Current Plan</Typography>
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
                </Box>

                {expires && (
                  <Box sx={{ mt: 2 }}>
                    <Divider sx={{ mb: 2 }} />
                    <Stack direction="row" spacing={4} flexWrap="wrap">
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
            <Card sx={{ mb: 3 }}>
              <CardContent sx={{ p: 3 }}>
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
              <CardContent sx={{ p: 3 }}>
                <Typography variant="subtitle1" fontWeight={700} mb={2}>
                  Payment Methods
                </Typography>
                <Stack spacing={2}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, p: 2, border: '1px solid', borderColor: 'divider', borderRadius: 2 }}>
                    <CurrencyBitcoin color="warning" />
                    <Box sx={{ flexGrow: 1 }}>
                      <Typography variant="body2" fontWeight={600}>Crypto (Active)</Typography>
                      <Typography variant="caption" color="text.secondary">
                        USDT, BTC, ETH, BNB and 300+ coins via NOWPayments
                      </Typography>
                    </Box>
                    <Chip label="Available" color="success" size="small" />
                  </Box>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, p: 2, border: '1px solid', borderColor: 'divider', borderRadius: 2, opacity: 0.6 }}>
                    <CreditCard />
                    <Box sx={{ flexGrow: 1 }}>
                      <Typography variant="body2" fontWeight={600}>Card / Bank Transfer</Typography>
                      <Typography variant="caption" color="text.secondary">
                        Visa, Mastercard — under review by processor
                      </Typography>
                    </Box>
                    <Chip label="Coming Soon" size="small" />
                  </Box>
                </Stack>
              </CardContent>
            </Card>

            {/* Payment History */}
            <Card sx={{ mb: 3 }}>
              <CardContent sx={{ p: 3 }}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                  <Typography variant="subtitle1" fontWeight={700}>Payment History</Typography>
                  <Chip label="NOWPayments Dashboard" icon={<OpenInNew fontSize="small" />} size="small" clickable
                    component="a" href="https://nowpayments.io" target="_blank" rel="noopener noreferrer"
                  />
                </Box>
                <Box sx={{ textAlign: 'center', py: 3 }}>
                  <HourglassTop sx={{ fontSize: 40, color: 'text.disabled', mb: 1 }} />
                  <Typography variant="body2" color="text.secondary">
                    Detailed payment history is available in your NOWPayments dashboard.
                  </Typography>
                  <Typography variant="caption" color="text.disabled" display="block" mt={1}>
                    Full transaction history coming soon to BotForge.
                  </Typography>
                </Box>
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
                <CardContent sx={{ p: 3, textAlign: 'center' }}>
                  <Typography variant="h6" fontWeight={700} color="white" mb={1}>
                    {tier === 'free'
                      ? 'Unlock the full power of BotForge'
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
                  onClick={() => window.open('mailto:support@botforge.app')}
                >
                  Contact support
                </Typography>
                {' '}· 14-day money-back guarantee on first purchase
              </Typography>
            </Box>
          </>
        )}
      </Box>
    </Box>
  );
}
