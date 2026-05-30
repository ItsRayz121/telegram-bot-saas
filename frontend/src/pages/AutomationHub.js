import React from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box, Typography, Grid, Card, CardActionArea, CardContent,
  Chip, Divider, Avatar,
} from '@mui/material';
import {
  Send, AutoMode, ArrowForward, FlashOn, CallSplit, AccountTree,
} from '@mui/icons-material';
import { PALETTE } from '../theme';

const TEAL = '#14b8a6';
const GLOW_TEAL = 'rgba(20,184,166,0.18)';

const MODULES = [
  {
    key: 'forwarding',
    path: '/workspace/forwarding',
    icon: Send,
    iconColor: PALETTE.blue,
    iconBg: `${PALETTE.blue}18`,
    glowColor: PALETTE.glowBlue,
    title: 'Forwarding',
    description: 'Relay messages between groups, repost to channels, route broadcasts, and create cross-chat pipelines.',
    tags: ['Relay', 'Repost', 'Broadcast'],
    badge: null,
  },
  {
    key: 'workflows',
    path: '/workspace/automations',
    icon: AutoMode,
    iconColor: PALETTE.purple,
    iconBg: `${PALETTE.purple}18`,
    glowColor: PALETTE.glowPurple,
    title: 'Workflows',
    description: 'Build trigger → condition → action automations. React to events in your groups automatically.',
    tags: ['Trigger', 'Condition', 'Action'],
    badge: 'Popular',
  },
  {
    key: 'workflow-builder',
    path: '/workflow-builder',
    icon: AccountTree,
    iconColor: TEAL,
    iconBg: `${TEAL}18`,
    glowColor: GLOW_TEAL,
    title: 'Workflow Builder',
    description: 'Visual node-based editor. Drag and connect triggers, conditions, and actions without writing any code.',
    tags: ['Visual', 'No-Code', 'Pro'],
    badge: 'New',
  },
];

export default function AutomationHub() {
  const navigate = useNavigate();

  return (
    <Box sx={{ maxWidth: 860, mx: 'auto', px: { xs: 2, sm: 3 }, py: 4 }}>

      {/* ── Hero header ── */}
      <Box
        sx={{
          mb: 4, p: { xs: 2.5, sm: 3 }, borderRadius: 3, position: 'relative', overflow: 'hidden',
          background: `linear-gradient(135deg, rgba(61,142,248,0.1) 0%, rgba(157,108,247,0.06) 60%, transparent 100%)`,
          border: `1px solid rgba(61,142,248,0.2)`,
        }}
      >
        <Box sx={{
          position: 'absolute', bottom: -30, right: -30, width: 160, height: 160,
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(61,142,248,0.12) 0%, transparent 70%)',
          pointerEvents: 'none',
        }} />
        <Box sx={{ position: 'relative', display: 'flex', alignItems: 'center', gap: 2 }}>
          <Avatar
            sx={{
              width: 46, height: 46,
              background: `linear-gradient(135deg, ${PALETTE.blue}, ${PALETTE.purple})`,
              boxShadow: `0 0 18px ${PALETTE.glowBlue}`,
            }}
          >
            <FlashOn fontSize="medium" />
          </Avatar>
          <Box>
            <Typography variant="h5" fontWeight={800} letterSpacing="-0.02em">Automation</Typography>
            <Typography variant="body2" color="text.secondary" mt={0.25}>
              Automate your Telegram community — forwarding pipelines and trigger-based workflows.
            </Typography>
          </Box>
        </Box>
      </Box>

      <Divider sx={{ mb: 4, borderColor: PALETTE.border1 }} />

      {/* ── Module cards ── */}
      <Grid container spacing={2.5}>
        {MODULES.map((mod) => {
          const Icon = mod.icon;
          return (
            <Grid item xs={12} sm={6} key={mod.key}>
              <Card
                sx={{
                  height: '100%', borderRadius: 3,
                  transition: 'transform 0.2s cubic-bezier(0.22,1,0.36,1), box-shadow 0.2s, border-color 0.2s',
                  '&:hover': {
                    transform: 'translateY(-4px)',
                    borderColor: mod.iconColor + '55',
                    boxShadow: `0 12px 40px rgba(0,0,0,0.5), 0 0 20px ${mod.glowColor}`,
                  },
                }}
              >
                <CardActionArea onClick={() => navigate(mod.path)} sx={{ height: '100%', p: 0.5 }}>
                  <CardContent sx={{ p: 3 }}>
                    {/* Icon + badge */}
                    <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', mb: 2.5 }}>
                      <Box
                        sx={{
                          width: 52, height: 52, borderRadius: 2.5,
                          bgcolor: mod.iconBg,
                          border: `1px solid ${mod.iconColor}28`,
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          flexShrink: 0,
                          boxShadow: `0 0 16px ${mod.glowColor}`,
                        }}
                      >
                        <Icon sx={{ fontSize: 26, color: mod.iconColor }} />
                      </Box>
                      {mod.badge && (
                        <Chip
                          label={mod.badge}
                          size="small"
                          sx={{
                            height: 20, fontSize: '0.65rem', fontWeight: 700,
                            background: `linear-gradient(135deg, ${PALETTE.blue}, ${PALETTE.purple})`,
                            color: '#fff',
                          }}
                        />
                      )}
                    </Box>

                    <Typography variant="subtitle1" fontWeight={700} letterSpacing="-0.01em" sx={{ mb: 0.75 }}>
                      {mod.title}
                    </Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 2, lineHeight: 1.6 }}>
                      {mod.description}
                    </Typography>

                    <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.75, mb: 2.5 }}>
                      {mod.tags.map(tag => (
                        <Chip
                          key={tag} label={tag} size="small" variant="outlined"
                          sx={{ height: 20, fontSize: '0.65rem', borderColor: PALETTE.border2 }}
                        />
                      ))}
                    </Box>

                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                      <Typography variant="caption" fontWeight={600} sx={{ color: mod.iconColor }}>
                        Open {mod.title}
                      </Typography>
                      <ArrowForward sx={{ fontSize: 13, color: mod.iconColor }} />
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
        <CallSplit sx={{ fontSize: 15, color: 'text.disabled' }} />
        <Typography variant="caption" color="text.disabled">
          More automation modules coming — webhooks, scheduled posts, and AI-powered triggers. Workflow Builder requires a Pro plan.
        </Typography>
      </Box>
    </Box>
  );
}
