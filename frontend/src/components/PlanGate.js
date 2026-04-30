import React from 'react';
import {
  Box, Card, CardContent, Typography, Button, Chip,
} from '@mui/material';
import { LockOutlined, Upgrade } from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';

const TIER_ORDER = { free: 0, pro: 1, enterprise: 2 };

function userMeetsPlan(userTier, requiredPlan) {
  return (TIER_ORDER[userTier] || 0) >= (TIER_ORDER[requiredPlan] || 0);
}

/**
 * Wrap any feature block with PlanGate to show a consistent upgrade wall when
 * the user's subscription tier is below the required plan.
 *
 * Usage:
 *   <PlanGate plan="pro" userTier={user.subscription_tier}>
 *     <ExpensiveFeature />
 *   </PlanGate>
 *
 * Props:
 *   plan        — required tier: 'pro' | 'enterprise'
 *   userTier    — current user tier string (from user object)
 *   feature     — optional label shown in the upgrade card ("Scheduled Messages")
 *   inline      — if true, render a compact chip-style lock instead of a card
 *   children    — content to render when access is granted
 */
export default function PlanGate({ plan = 'pro', userTier = 'free', feature, inline = false, children }) {
  const navigate = useNavigate();
  const hasAccess = userMeetsPlan(userTier, plan);

  if (hasAccess) return children;

  const planLabel = plan.charAt(0).toUpperCase() + plan.slice(1);
  const featureLabel = feature || `This feature`;

  if (inline) {
    return (
      <Box sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.75 }}>
        <Chip
          icon={<LockOutlined sx={{ fontSize: '0.75rem !important' }} />}
          label={`${planLabel}+`}
          size="small"
          color="warning"
          onClick={() => navigate('/pricing')}
          sx={{ cursor: 'pointer', fontSize: '0.65rem', height: 20 }}
        />
      </Box>
    );
  }

  return (
    <Card
      sx={{
        border: '1px dashed',
        borderColor: 'divider',
        bgcolor: 'background.paper',
        textAlign: 'center',
      }}
    >
      <CardContent sx={{ py: 4 }}>
        <LockOutlined sx={{ fontSize: 40, color: 'text.disabled', mb: 1.5 }} />
        <Typography variant="subtitle1" fontWeight={700} gutterBottom>
          {featureLabel} requires {planLabel}
        </Typography>
        <Typography variant="body2" color="text.secondary" mb={2.5}>
          Upgrade to the <strong>{planLabel}</strong> plan to unlock this feature.
        </Typography>
        <Button
          variant="contained"
          startIcon={<Upgrade />}
          onClick={() => navigate('/pricing')}
        >
          Upgrade to {planLabel}
        </Button>
      </CardContent>
    </Card>
  );
}
