import React from 'react';
import { Box, Typography, Card, CardContent, Button, Chip, Grid } from '@mui/material';
import { Campaign, Analytics, Verified, Schedule, Send, Forum, TrendingUp } from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';

const COMING_FEATURES = [
  { icon: Analytics,   label: 'Channel Analytics',     desc: 'Views, reactions, forwards — beyond Telegram\'s 90-day limit.' },
  { icon: Verified,    label: 'TCS Authenticity Score', desc: 'Detect fake subscribers, bot reactions, and purchased growth.' },
  { icon: Schedule,    label: 'Content Scheduling',     desc: 'Schedule posts, recurring content, and editorial calendar.' },
  { icon: Send,        label: 'Cross-Posting',          desc: 'Forward announcements from your channel to multiple groups.' },
  { icon: Forum,       label: 'Discussion Group',       desc: 'Protect your channel\'s comment section with Telegizer moderation.' },
  { icon: TrendingUp,  label: 'Community Directory',    desc: 'List your channel and get discovered by brands and advertisers.' },
];

export default function Channels() {
  const navigate = useNavigate();

  return (
    <Box sx={{ p: { xs: 2, md: 4 }, maxWidth: 900, mx: 'auto' }}>

      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1 }}>
          <Campaign sx={{ fontSize: 28, color: 'primary.main' }} />
          <Typography variant="h5" fontWeight={700}>Channels</Typography>
          <Chip label="Coming Soon" size="small" color="primary" variant="outlined" />
        </Box>
        <Typography color="text.secondary" maxWidth={600}>
          Manage your Telegram channels — analytics, fake-subscriber detection, content scheduling,
          and cross-posting to your groups. All in one place.
        </Typography>
      </Box>

      {/* Early access CTA */}
      <Card sx={{ mb: 4, bgcolor: 'rgba(37,99,235,0.08)', border: '1px solid rgba(37,99,235,0.3)' }}>
        <CardContent sx={{ p: 3 }}>
          <Typography variant="subtitle1" fontWeight={700} gutterBottom>
            Channel support is being built now
          </Typography>
          <Typography variant="body2" color="text.secondary" mb={2}>
            Your linked groups already protect your channel's discussion section.
            Full channel analytics and tools are next on the roadmap.
          </Typography>
          <Button variant="contained" size="small" onClick={() => navigate('/groups')}>
            Manage your Groups →
          </Button>
        </CardContent>
      </Card>

      {/* Feature preview grid */}
      <Typography variant="subtitle2" fontWeight={700} color="text.secondary" mb={2} textTransform="uppercase" letterSpacing={1} fontSize="0.7rem">
        What's coming
      </Typography>
      <Grid container spacing={2}>
        {COMING_FEATURES.map(({ icon: Icon, label, desc }) => (
          <Grid item xs={12} sm={6} key={label}>
            <Card sx={{ height: '100%', opacity: 0.8 }}>
              <CardContent sx={{ p: 2.5 }}>
                <Box sx={{ display: 'flex', gap: 1.5, alignItems: 'flex-start' }}>
                  <Box sx={{ p: 1, borderRadius: 1.5, bgcolor: 'rgba(37,99,235,0.1)', flexShrink: 0 }}>
                    <Icon sx={{ fontSize: 18, color: 'primary.main' }} />
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
