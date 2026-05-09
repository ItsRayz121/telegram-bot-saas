import React, { useState } from 'react';
import {
  Box, Typography, Card, CardContent, Button, Divider,
  Stepper, Step, StepLabel, StepContent, Chip, Alert, Stack,
} from '@mui/material';
import {
  Settings, ContentCopy, CheckCircle, OpenInNew, SmartToy,
  Groups, Bolt, CardGiftcard,
} from '@mui/icons-material';
import { toast } from 'react-toastify';
import { useTelegram } from '../contexts/TelegramContext';

const BOTFATHER_STEPS = [
  {
    label: 'Open @BotFather',
    content: 'Search for @BotFather in Telegram and start a conversation.',
    action: { label: 'Open @BotFather', url: 'https://t.me/BotFather' },
  },
  {
    label: 'Select your bot',
    content: 'Send /mybots → choose your bot from the list.',
    code: '/mybots',
  },
  {
    label: 'Open Bot Settings',
    content: 'Tap "Bot Settings" → "Menu Button" → "Configure menu button".',
  },
  {
    label: 'Set the menu button URL',
    content: 'Enter this URL as the Mini App URL:',
    code: 'https://telegizer.com/mini-app',
  },
  {
    label: 'Set the button title',
    content: 'Enter a label for the button, e.g.:',
    code: 'Open Dashboard',
  },
  {
    label: 'Done!',
    content: 'Users will now see a "Open Dashboard" button in the bottom bar of your bot — one tap opens the Mini App.',
  },
];

function CopyableCode({ value }) {
  const { haptic } = useTelegram();
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    haptic.impact('light');
    navigator.clipboard.writeText(value).then(() => {
      setCopied(true);
      toast.success('Copied!');
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <Box
      sx={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        bgcolor: 'rgba(0,0,0,0.25)', borderRadius: 1.5, px: 1.5, py: 1, mt: 0.75,
        border: '1px solid rgba(255,255,255,0.07)', cursor: 'pointer',
      }}
      onClick={handleCopy}
    >
      <Typography variant="body2" fontFamily="monospace" fontSize="0.78rem" sx={{ wordBreak: 'break-all', flex: 1 }}>
        {value}
      </Typography>
      {copied
        ? <CheckCircle fontSize="small" sx={{ color: 'success.main', ml: 1, flexShrink: 0 }} />
        : <ContentCopy fontSize="small" sx={{ color: 'text.disabled', ml: 1, flexShrink: 0 }} />
      }
    </Box>
  );
}

function QuickLinks() {
  const { haptic } = useTelegram();
  const links = [
    { label: 'Groups', icon: <Groups fontSize="small" />, url: 'https://telegizer.com/groups' },
    { label: 'Workspace', icon: <Bolt fontSize="small" />, url: 'https://telegizer.com/workspace' },
    { label: 'Billing', icon: <CardGiftcard fontSize="small" />, url: 'https://telegizer.com/billing' },
    { label: 'Settings', icon: <Settings fontSize="small" />, url: 'https://telegizer.com/settings' },
  ];
  return (
    <Card sx={{ mb: 2 }}>
      <CardContent sx={{ p: 2 }}>
        <Typography variant="caption" color="text.secondary" fontWeight={600} display="block" mb={1.5}>
          Quick links
        </Typography>
        <Stack direction="row" flexWrap="wrap" gap={1}>
          {links.map(l => (
            <Button
              key={l.label}
              size="small"
              variant="outlined"
              startIcon={l.icon}
              endIcon={<OpenInNew sx={{ fontSize: '0.7rem !important' }} />}
              href={l.url}
              target="_blank"
              onClick={() => haptic.impact('light')}
              sx={{ fontSize: '0.72rem' }}
            >
              {l.label}
            </Button>
          ))}
        </Stack>
      </CardContent>
    </Card>
  );
}

export default function MiniAppSetup() {
  const [activeStep, setActiveStep] = useState(0);

  return (
    <Box sx={{ pt: 1 }}>
      {/* Header */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 2.5 }}>
        <SmartToy sx={{ color: 'primary.main', fontSize: 28 }} />
        <Box>
          <Typography fontWeight={700} fontSize="1rem">Bot Setup</Typography>
          <Typography variant="caption" color="text.secondary">
            Add the Mini App button to your bot
          </Typography>
        </Box>
      </Box>

      {/* Quick links */}
      <QuickLinks />

      {/* BotFather setup guide */}
      <Card sx={{ mb: 2 }}>
        <CardContent sx={{ p: 2 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
            <Typography variant="subtitle2" fontWeight={700}>Add Mini App button to your bot</Typography>
            <Chip label="BotFather" size="small" sx={{ height: 18, fontSize: '0.6rem' }} />
          </Box>

          <Alert severity="info" sx={{ mb: 2, fontSize: '0.75rem' }} icon={false}>
            This adds a button inside your custom bot that opens this dashboard in one tap.
            Requires a custom bot (not the official @telegizer_bot).
          </Alert>

          <Stepper activeStep={activeStep} orientation="vertical" nonLinear>
            {BOTFATHER_STEPS.map((step, i) => (
              <Step key={i} completed={i < activeStep}>
                <StepLabel
                  onClick={() => setActiveStep(i)}
                  sx={{ cursor: 'pointer', '& .MuiStepLabel-label': { fontSize: '0.82rem', fontWeight: i === activeStep ? 700 : 400 } }}
                >
                  {step.label}
                </StepLabel>
                <StepContent>
                  <Typography variant="body2" color="text.secondary" mb={step.code || step.action ? 0.5 : 1.5}>
                    {step.content}
                  </Typography>
                  {step.code && <CopyableCode value={step.code} />}
                  {step.action && (
                    <Button
                      size="small" variant="outlined" startIcon={<OpenInNew fontSize="small" />}
                      href={step.action.url} target="_blank" sx={{ mt: 1, fontSize: '0.75rem' }}
                    >
                      {step.action.label}
                    </Button>
                  )}
                  <Box sx={{ mt: 1.5 }}>
                    {i < BOTFATHER_STEPS.length - 1 ? (
                      <Button size="small" variant="contained" onClick={() => setActiveStep(i + 1)}>
                        Next
                      </Button>
                    ) : (
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <CheckCircle color="success" fontSize="small" />
                        <Typography variant="body2" color="success.main" fontWeight={600}>
                          Setup complete!
                        </Typography>
                      </Box>
                    )}
                    {i > 0 && (
                      <Button size="small" onClick={() => setActiveStep(i - 1)} sx={{ ml: 1 }}>
                        Back
                      </Button>
                    )}
                  </Box>
                </StepContent>
              </Step>
            ))}
          </Stepper>
        </CardContent>
      </Card>

      {/* App info */}
      <Divider sx={{ my: 2 }} />
      <Box sx={{ textAlign: 'center' }}>
        <Typography variant="caption" color="text.disabled" display="block">
          Telegizer Mini App · v1.0
        </Typography>
        <Typography variant="caption" color="text.disabled">
          telegizer.com
        </Typography>
      </Box>
    </Box>
  );
}
