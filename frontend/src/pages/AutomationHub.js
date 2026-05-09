import React from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box, Typography, Grid, Card, CardActionArea, CardContent,
  Chip, Divider,
} from '@mui/material';
import {
  Send, AutoMode, ArrowForward, FlashOn, CallSplit,
} from '@mui/icons-material';

const MODULES = [
  {
    key: 'forwarding',
    path: '/workspace/forwarding',
    icon: Send,
    iconColor: '#2196f3',
    iconBg: 'rgba(33,150,243,0.10)',
    title: 'Forwarding',
    description: 'Relay messages between groups, repost to channels, route broadcasts, and create cross-chat pipelines.',
    tags: ['Relay', 'Repost', 'Broadcast'],
    badge: null,
  },
  {
    key: 'workflows',
    path: '/workspace/automations',
    icon: AutoMode,
    iconColor: '#9c27b0',
    iconBg: 'rgba(156,39,176,0.10)',
    title: 'Workflows',
    description: 'Build trigger → condition → action automations. React to events in your groups automatically.',
    tags: ['Trigger', 'Condition', 'Action'],
    badge: 'Popular',
  },
];

export default function AutomationHub() {
  const navigate = useNavigate();

  return (
    <Box sx={{ maxWidth: 860, mx: 'auto', px: { xs: 2, sm: 3 }, py: 4 }}>
      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1 }}>
          <FlashOn sx={{ fontSize: 26, color: 'primary.main' }} />
          <Typography variant="h5" fontWeight={700}>Automation</Typography>
        </Box>
        <Typography variant="body2" color="text.secondary">
          Automate your Telegram community — set up forwarding pipelines or build
          custom trigger-based workflows.
        </Typography>
      </Box>

      <Divider sx={{ mb: 4 }} />

      {/* Module cards */}
      <Grid container spacing={2.5}>
        {MODULES.map((mod) => {
          const Icon = mod.icon;
          return (
            <Grid item xs={12} sm={6} key={mod.key}>
              <Card
                variant="outlined"
                sx={{
                  height: '100%',
                  borderRadius: 3,
                  transition: 'border-color 0.15s, box-shadow 0.15s',
                  '&:hover': {
                    borderColor: 'primary.main',
                    boxShadow: '0 4px 20px rgba(0,0,0,0.10)',
                  },
                }}
              >
                <CardActionArea
                  onClick={() => navigate(mod.path)}
                  sx={{ height: '100%', p: 0.5 }}
                >
                  <CardContent sx={{ p: 3 }}>
                    {/* Icon + badge row */}
                    <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', mb: 2 }}>
                      <Box sx={{
                        width: 48, height: 48, borderRadius: 2,
                        bgcolor: mod.iconBg,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        flexShrink: 0,
                      }}>
                        <Icon sx={{ fontSize: 26, color: mod.iconColor }} />
                      </Box>
                      {mod.badge && (
                        <Chip
                          label={mod.badge}
                          size="small"
                          sx={{
                            height: 20, fontSize: '0.65rem', fontWeight: 600,
                            bgcolor: 'primary.main', color: '#fff',
                          }}
                        />
                      )}
                    </Box>

                    {/* Title */}
                    <Typography variant="subtitle1" fontWeight={700} sx={{ mb: 0.75 }}>
                      {mod.title}
                    </Typography>

                    {/* Description */}
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 2, lineHeight: 1.55 }}>
                      {mod.description}
                    </Typography>

                    {/* Tags */}
                    <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.75, mb: 2 }}>
                      {mod.tags.map(tag => (
                        <Chip
                          key={tag}
                          label={tag}
                          size="small"
                          variant="outlined"
                          sx={{ height: 20, fontSize: '0.65rem' }}
                        />
                      ))}
                    </Box>

                    {/* CTA row */}
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                      <Typography variant="caption" color="primary.main" fontWeight={600}>
                        Open {mod.title}
                      </Typography>
                      <ArrowForward sx={{ fontSize: 13, color: 'primary.main' }} />
                    </Box>
                  </CardContent>
                </CardActionArea>
              </Card>
            </Grid>
          );
        })}
      </Grid>

      {/* Footer hint */}
      <Box sx={{ mt: 5, display: 'flex', alignItems: 'center', gap: 1 }}>
        <CallSplit sx={{ fontSize: 16, color: 'text.disabled' }} />
        <Typography variant="caption" color="text.disabled">
          More automation modules coming soon — webhooks, scheduled posts, and AI-powered triggers.
        </Typography>
      </Box>
    </Box>
  );
}
