import React, { useState } from 'react';
import {
  Box, AppBar, Toolbar, Typography, Button, Card, CardContent,
  Grid, Chip, List, ListItem, ListItemIcon, ListItemText,
  CircularProgress, IconButton, Dialog, DialogTitle, DialogContent,
  DialogActions, Stack,
} from '@mui/material';
import { Check, ArrowBack, CreditCard, CurrencyBitcoin } from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { toast } from 'react-toastify';
import { billing } from '../services/api';

const PLANS = [
  {
    id: 'free',
    name: 'Free',
    price: '$0',
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
    price: '$9',
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
    price: '$49',
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
  const token = localStorage.getItem('token');

  const handleUpgrade = (tier) => {
    if (!token) {
      navigate('/register');
      return;
    }
    if (tier === 'free') return;
    setSelectedTier(tier);
    setDialogOpen(true);
  };

  const handlePaymentMethod = async (method) => {
    setMethodLoading(method);
    try {
      let res;
      if (method === 'card') {
        res = await billing.lemonCheckout({ tier: selectedTier });
      } else {
        res = await billing.cryptoCheckout({ tier: selectedTier });
      }

      if (res.data.admin_upgrade) {
        toast.success(res.data.message || `Plan switched to ${selectedTier}`);
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
            BotForge
          </Typography>
          {!token && (
            <Button variant="outlined" onClick={() => navigate('/login')}>Sign In</Button>
          )}
        </Toolbar>
      </AppBar>

      <Box sx={{ maxWidth: 1100, mx: 'auto', p: 3, textAlign: 'center' }}>
        <Typography variant="h3" fontWeight={700} mb={1} mt={4}>
          Simple, Transparent Pricing
        </Typography>
        <Typography variant="h6" color="text.secondary" mb={6}>
          Start free, scale as your communities grow
        </Typography>

        <Grid container spacing={3} justifyContent="center">
          {PLANS.map((plan) => (
            <Grid item xs={12} sm={6} md={4} key={plan.id}>
              <Card
                sx={{
                  height: '100%',
                  display: 'flex',
                  flexDirection: 'column',
                  position: 'relative',
                  border: plan.popular ? '2px solid' : '1px solid',
                  borderColor: plan.popular ? 'primary.main' : 'divider',
                }}
              >
                {plan.popular && (
                  <Chip
                    label="Most Popular"
                    color="primary"
                    size="small"
                    sx={{ position: 'absolute', top: -12, left: '50%', transform: 'translateX(-50%)' }}
                  />
                )}
                <CardContent sx={{ flexGrow: 1, p: 3 }}>
                  <Typography variant="h5" fontWeight={700} mb={1}>{plan.name}</Typography>
                  <Box sx={{ mb: 3 }}>
                    <Typography component="span" variant="h3" fontWeight={800}>
                      {plan.price}
                    </Typography>
                    <Typography component="span" variant="body1" color="text.secondary">
                      {plan.period}
                    </Typography>
                  </Box>
                  <Button
                    fullWidth
                    variant={plan.popular ? 'contained' : 'outlined'}
                    color={plan.color === 'default' ? 'inherit' : plan.color}
                    onClick={() => handleUpgrade(plan.id)}
                    disabled={loading === plan.id || plan.id === 'free'}
                    sx={{ mb: 3 }}
                  >
                    {loading === plan.id ? (
                      <CircularProgress size={20} color="inherit" />
                    ) : plan.id === 'free' ? 'Current Plan' : `Get ${plan.name}`}
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
            </Grid>
          ))}
        </Grid>

        <Typography variant="body2" color="text.secondary" mt={6}>
          All plans include 14-day money back guarantee. No hidden fees.
        </Typography>
      </Box>

      {/* Payment method selection dialog */}
      <Dialog open={dialogOpen} onClose={handleCloseDialog} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ fontWeight: 700, textAlign: 'center', pb: 1 }}>
          Choose Payment Method
        </DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" textAlign="center" mb={3}>
            {selectedTier && `Upgrading to ${selectedTier.charAt(0).toUpperCase() + selectedTier.slice(1)} Plan`}
          </Typography>
          <Stack spacing={2}>
            <Button
              fullWidth
              variant="outlined"
              size="large"
              startIcon={methodLoading === 'card' ? <CircularProgress size={18} /> : <CreditCard />}
              onClick={() => handlePaymentMethod('card')}
              disabled={!!methodLoading}
              sx={{ py: 1.5, justifyContent: 'flex-start', px: 3 }}
            >
              <Box sx={{ textAlign: 'left', ml: 1 }}>
                <Typography variant="body1" fontWeight={600}>Card / Bank Transfer</Typography>
                <Typography variant="caption" color="text.secondary">
                  Visa, Mastercard, PayPal via Lemon Squeezy
                </Typography>
              </Box>
            </Button>

            <Button
              fullWidth
              variant="outlined"
              size="large"
              color="warning"
              startIcon={methodLoading === 'crypto' ? <CircularProgress size={18} color="inherit" /> : <CurrencyBitcoin />}
              onClick={() => handlePaymentMethod('crypto')}
              disabled={!!methodLoading}
              sx={{ py: 1.5, justifyContent: 'flex-start', px: 3 }}
            >
              <Box sx={{ textAlign: 'left', ml: 1 }}>
                <Typography variant="body1" fontWeight={600}>Crypto</Typography>
                <Typography variant="caption" color="text.secondary">
                  USDT, BTC, ETH, BNB and 300+ coins via NOWPayments
                </Typography>
              </Box>
            </Button>
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={handleCloseDialog} disabled={!!methodLoading} fullWidth>
            Cancel
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
