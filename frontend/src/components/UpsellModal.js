import React, { useEffect } from 'react';
import {
  Dialog, DialogTitle, DialogContent, DialogActions,
  Button, Typography, Box, List, ListItem, ListItemIcon, ListItemText,
  Divider, Chip,
} from '@mui/material';
import {
  Upgrade, CheckCircle, SmartToy, Groups, Psychology,
  BarChart, Campaign, Close,
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { track } from '../services/analytics';

const PRO_FEATURES = [
  { icon: SmartToy,   label: '3 custom bots',          sub: 'not available on Free' },
  { icon: Groups,     label: 'Unlimited linked groups', sub: 'on your own bots' },
  { icon: Psychology, label: 'AI Assistant & Hub',       sub: 'Full knowledge base & digests' },
  { icon: BarChart,   label: 'Advanced analytics',       sub: 'Member growth, engagement charts' },
  { icon: Campaign,   label: 'Scheduled messages',       sub: 'Unlimited broadcasts' },
];

export default function UpsellModal({ open, onClose, feature, limitMessage }) {
  const navigate = useNavigate();

  useEffect(() => {
    if (open) {
      track('upsell_shown', { feature: feature || 'generic', trigger: 'limit_hit' });
    }
  }, [open, feature]);

  const handleUpgrade = () => {
    track('upsell_clicked', { feature: feature || 'generic' });
    onClose();
    navigate('/billing');
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle sx={{ pb: 1, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Upgrade sx={{ color: 'primary.main' }} />
          <Typography variant="h6" fontWeight={700}>Upgrade to Pro</Typography>
        </Box>
        <Button size="small" onClick={onClose} sx={{ minWidth: 0, p: 0.5 }}>
          <Close fontSize="small" />
        </Button>
      </DialogTitle>

      <DialogContent sx={{ pt: 0 }}>
        {limitMessage && (
          <Box sx={{ mb: 2, p: 1.5, bgcolor: 'rgba(239,68,68,0.08)', borderRadius: 1.5, border: '1px solid rgba(239,68,68,0.2)' }}>
            <Typography variant="body2" color="error.main" fontWeight={500}>
              {limitMessage}
            </Typography>
          </Box>
        )}

        <Typography variant="body2" color="text.secondary" mb={2}>
          Unlock the full power of Telegizer. Pro gives you:
        </Typography>

        <List dense disablePadding>
          {PRO_FEATURES.map(({ icon: Icon, label, sub }) => (
            <ListItem key={label} disableGutters sx={{ py: 0.5 }}>
              <ListItemIcon sx={{ minWidth: 34 }}>
                <CheckCircle sx={{ fontSize: 16, color: 'success.main' }} />
              </ListItemIcon>
              <ListItemText
                primary={label}
                secondary={sub}
                primaryTypographyProps={{ variant: 'body2', fontWeight: 600 }}
                secondaryTypographyProps={{ variant: 'caption' }}
              />
            </ListItem>
          ))}
        </List>

        <Divider sx={{ my: 2 }} />

        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Typography variant="h5" fontWeight={800} color="primary.main">$9</Typography>
          <Typography variant="body2" color="text.secondary">/month</Typography>
          <Chip label="Save 33% annual" size="small" color="success" sx={{ ml: 'auto', fontSize: '0.68rem' }} />
        </Box>
      </DialogContent>

      <DialogActions sx={{ px: 3, pb: 2.5, gap: 1 }}>
        <Button variant="text" onClick={onClose} size="small" color="inherit">
          Maybe later
        </Button>
        <Button
          variant="contained"
          startIcon={<Upgrade />}
          onClick={handleUpgrade}
          sx={{ flex: 1 }}
        >
          Upgrade Now
        </Button>
      </DialogActions>
    </Dialog>
  );
}
