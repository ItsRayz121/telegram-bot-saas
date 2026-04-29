import React from 'react';
import { Box, Typography, Card, CardContent, Button, Chip, Grid } from '@mui/material';
import { Bolt, Link, AccessTime, Send, AutoMode, ArrowForward } from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';

const SECTIONS = [
  {
    icon: Link,
    label: 'Smart Links',
    desc: 'Save your Calendly, pitch deck, website, and support links. The bot replies automatically when someone asks.',
    path: '/workspace/smart-links',
    available: true,
    color: '#2563EB',
  },
  {
    icon: AccessTime,
    label: 'Reminders',
    desc: 'Bot detects "remind me to follow up" and "let\'s discuss Friday" — creates reminders and DMs you at the right time.',
    path: '/workspace/reminders',
    available: true,
    color: '#7C3AED',
  },
  {
    icon: Send,
    label: 'Forwarding',
    desc: 'Forward messages from one channel to multiple groups automatically — with keyword filters, prefix/suffix templates, and approval queues.',
    path: '/workspace/forwarding',
    available: true,
    color: '#06B6D4',
  },
  {
    icon: AutoMode,
    label: 'Automations',
    desc: 'Build workflows: When a message contains "urgent" → notify me via DM. When member joins → send welcome DM. Trigger → Condition → Action.',
    path: '/workspace/automations',
    available: true,
    color: '#10b981',
  },
];

export default function Workspace() {
  const navigate = useNavigate();

  return (
    <Box sx={{ p: { xs: 2, md: 4 }, maxWidth: 900, mx: 'auto' }}>

      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1 }}>
          <Bolt sx={{ fontSize: 28, color: 'primary.main' }} />
          <Typography variant="h5" fontWeight={700}>Workspace</Typography>
          <Chip label="Beta" size="small" color="primary" variant="outlined" />
        </Box>
        <Typography color="text.secondary" maxWidth={620}>
          Your personal command center across all groups and channels. Smart links, reminders,
          message forwarding, and automation workflows — all user-scoped, not group-scoped.
        </Typography>
      </Box>

      {/* What makes Workspace different */}
      <Card sx={{ mb: 4, bgcolor: 'rgba(124,58,237,0.08)', border: '1px solid rgba(124,58,237,0.25)' }}>
        <CardContent sx={{ p: 3 }}>
          <Typography variant="subtitle1" fontWeight={700} gutterBottom>
            Why Workspace is separate from Group Settings
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Groups settings are scoped to one group. Workspace is scoped to <strong>you</strong> —
            across all your groups and channels. A forwarding rule that moves messages from
            Channel A to Group B can't logically live inside either one.
          </Typography>
        </CardContent>
      </Card>

      {/* Feature cards */}
      <Grid container spacing={2.5}>
        {SECTIONS.map(({ icon: Icon, label, desc, path, available, color }) => (
          <Grid item xs={12} sm={6} key={label}>
            <Card
              sx={{
                height: '100%',
                cursor: available ? 'pointer' : 'default',
                opacity: available ? 1 : 0.75,
                transition: 'box-shadow 0.15s',
                '&:hover': available ? { boxShadow: 6 } : {},
              }}
              onClick={available ? () => navigate(path) : undefined}
            >
              <CardContent sx={{ p: 3 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1.5 }}>
                  <Box sx={{ p: 1.25, borderRadius: 2, bgcolor: `${color}20`, flexShrink: 0 }}>
                    <Icon sx={{ fontSize: 20, color }} />
                  </Box>
                  <Box sx={{ flex: 1 }}>
                    <Typography variant="body1" fontWeight={700}>{label}</Typography>
                  </Box>
                  {!available && <Chip label="Soon" size="small" sx={{ height: 18, fontSize: '0.6rem' }} />}
                </Box>
                <Typography variant="body2" color="text.secondary" lineHeight={1.55}>{desc}</Typography>
                {available && (
                  <Button size="small" endIcon={<ArrowForward fontSize="small" />} sx={{ mt: 1.5 }} onClick={() => navigate(path)}>
                    Open
                  </Button>
                )}
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>
    </Box>
  );
}
