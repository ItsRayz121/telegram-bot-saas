import React from 'react';
import { Box, Typography, Card, CardContent, Button, Chip, Grid } from '@mui/material';
import { Explore, Verified, Search, Handshake, TrendingUp, Public } from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';

const FEATURES = [
  { icon: Search,      label: 'Community Discovery',    desc: 'Filter by country, category, size, and engagement rate to find exactly the right communities for partnerships.' },
  { icon: Verified,    label: 'TCS Verified Badge',     desc: 'Verified communities command higher ad rates. Your TCS score is your credibility score to advertisers.' },
  { icon: Handshake,   label: 'B2B Outreach',           desc: 'Contact community admins directly through the platform — no cold DMs, no guessing at contacts.' },
  { icon: TrendingUp,  label: 'Sponsorship Marketplace', desc: 'Standardized pricing, escrow payments, campaign analytics, and post-performance reports.' },
  { icon: Public,      label: 'Global Coverage',        desc: 'Priority coverage: India, Indonesia, Nigeria, Brazil, Turkey — the highest-growth Telegram markets.' },
];

export default function Directory() {
  const navigate = useNavigate();

  return (
    <Box sx={{ p: { xs: 2, md: 4 }, maxWidth: 900, mx: 'auto' }}>

      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1 }}>
          <Explore sx={{ fontSize: 28, color: 'primary.main' }} />
          <Typography variant="h5" fontWeight={700}>Directory</Typography>
          <Chip label="Coming Soon" size="small" color="primary" variant="outlined" />
        </Box>
        <Typography color="text.secondary" maxWidth={620}>
          The first globally-indexed, quality-scored Telegram community marketplace.
          List your groups and channels. Get discovered by brands, advertisers, and partners.
        </Typography>
      </Box>

      {/* Opportunity card */}
      <Card sx={{ mb: 4, bgcolor: 'rgba(16,185,129,0.08)', border: '1px solid rgba(16,185,129,0.25)' }}>
        <CardContent sx={{ p: 3 }}>
          <Typography variant="subtitle1" fontWeight={700} gutterBottom>
            The gap in the market
          </Typography>
          <Typography variant="body2" color="text.secondary" mb={2}>
            TGStat covers 2.7M channels but is CIS-only. There is no globally-indexed,
            quality-scored Telegram directory for B2B partnerships outside Russia.
            Every sponsorship deal is currently 100% manual — find channel on TGStat,
            cold DM admin, negotiate with no market data, pay with no escrow, measure with nothing.
          </Typography>
          <Button variant="outlined" size="small" onClick={() => navigate('/groups')}>
            Prepare your communities →
          </Button>
        </CardContent>
      </Card>

      {/* Feature grid */}
      <Typography variant="subtitle2" fontWeight={700} color="text.secondary" mb={2} textTransform="uppercase" letterSpacing={1} fontSize="0.7rem">
        What the Directory will offer
      </Typography>
      <Grid container spacing={2}>
        {FEATURES.map(({ icon: Icon, label, desc }) => (
          <Grid item xs={12} sm={6} key={label}>
            <Card sx={{ height: '100%', opacity: 0.8 }}>
              <CardContent sx={{ p: 2.5 }}>
                <Box sx={{ display: 'flex', gap: 1.5, alignItems: 'flex-start' }}>
                  <Box sx={{ p: 1, borderRadius: 1.5, bgcolor: 'rgba(16,185,129,0.1)', flexShrink: 0 }}>
                    <Icon sx={{ fontSize: 18, color: '#10b981' }} />
                  </Box>
                  <Box>
                    <Typography variant="body2" fontWeight={600}>{label}</Typography>
                    <Typography variant="caption" color="text.secondary">{desc}</Typography>
                  </Box>
                </Box>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>
    </Box>
  );
}
