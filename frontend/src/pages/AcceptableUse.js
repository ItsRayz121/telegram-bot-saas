import React from 'react';
import {
  Box, Container, Typography, Card, CardContent, List, ListItem,
  ListItemIcon, ListItemText, Divider, Button, Link,
} from '@mui/material';
import { Block, CheckCircle, OpenInNew } from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import TelegizerLogo from '../components/TelegizerLogo';
import usePageMeta from '../hooks/usePageMeta';
import { SUPPORT_EMAIL } from '../config/support';

const PROHIBITED = [
  'Sending unsolicited bulk messages (spam) to Telegram users or groups',
  'Automating mass invitations or adding members without their consent',
  'Impersonating other users, bots, or organizations',
  'Distributing malware, phishing links, or harmful content through bots',
  'Facilitating illegal activities including fraud, harassment, or hate speech',
  'Scraping or exfiltrating user data without explicit authorization',
  'Circumventing Telegram platform rate limits or anti-abuse systems',
  'Using bot automation to manipulate votes, polls, or engagement metrics',
  'Operating bots that violate the Telegram Bot API Terms of Service',
  'Reselling or sub-licensing Telegizer services to third parties without prior written consent',
];

const PERMITTED = [
  'Community moderation and automated rule enforcement in groups you own or administer',
  'Sending scheduled announcements to members who have opted in to your group',
  'Providing customer support bots for your own business or organization',
  'Running polls, contests, and engagement features for your genuine community',
  'Knowledge-base Q&A bots that serve content you are authorized to distribute',
];

export default function AcceptableUse() {
  usePageMeta(
    'Acceptable Use Policy',
    "Telegizer Acceptable Use Policy: what is and isn't allowed when running bots and communities on our platform."
  );
  const navigate = useNavigate();

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default', py: 6 }}>
      <Container maxWidth="md">
        <Box sx={{ display: 'flex', justifyContent: 'center', mb: 3 }}>
          <TelegizerLogo size="lg" />
        </Box>

        <Typography variant="h4" fontWeight={800} textAlign="center" mb={1}>
          Acceptable Use Policy
        </Typography>
        <Typography variant="body2" color="text.secondary" textAlign="center" mb={4}>
          Last updated: May 12, 2026
        </Typography>

        <Card sx={{ mb: 3 }}>
          <CardContent>
            <Typography variant="h6" fontWeight={700} mb={1}>Overview</Typography>
            <Typography variant="body2" color="text.secondary">
              Telegizer provides tools to automate and manage Telegram communities. By using Telegizer
              you agree to use these tools responsibly and in compliance with{' '}
              <Link
                href="https://core.telegram.org/bots/api"
                target="_blank"
                rel="noopener noreferrer"
                sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.3 }}
              >
                Telegram Bot API Terms of Service
                <OpenInNew sx={{ fontSize: '0.8rem' }} />
              </Link>
              {' '}and all applicable laws. Violations may result in immediate account suspension and
              reporting to Telegram.
            </Typography>
          </CardContent>
        </Card>

        <Card sx={{ mb: 3 }}>
          <CardContent>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
              <CheckCircle color="success" />
              <Typography variant="h6" fontWeight={700}>Permitted Uses</Typography>
            </Box>
            <List dense disablePadding>
              {PERMITTED.map((item) => (
                <ListItem key={item} disableGutters sx={{ alignItems: 'flex-start', py: 0.5 }}>
                  <ListItemIcon sx={{ minWidth: 28, mt: 0.3 }}>
                    <CheckCircle color="success" sx={{ fontSize: 16 }} />
                  </ListItemIcon>
                  <ListItemText
                    primary={<Typography variant="body2">{item}</Typography>}
                  />
                </ListItem>
              ))}
            </List>
          </CardContent>
        </Card>

        <Card sx={{ mb: 3 }}>
          <CardContent>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
              <Block color="error" />
              <Typography variant="h6" fontWeight={700}>Prohibited Uses</Typography>
            </Box>
            <List dense disablePadding>
              {PROHIBITED.map((item) => (
                <ListItem key={item} disableGutters sx={{ alignItems: 'flex-start', py: 0.5 }}>
                  <ListItemIcon sx={{ minWidth: 28, mt: 0.3 }}>
                    <Block color="error" sx={{ fontSize: 16 }} />
                  </ListItemIcon>
                  <ListItemText
                    primary={<Typography variant="body2">{item}</Typography>}
                  />
                </ListItem>
              ))}
            </List>
          </CardContent>
        </Card>

        <Card sx={{ mb: 3 }}>
          <CardContent>
            <Typography variant="h6" fontWeight={700} mb={1}>Enforcement</Typography>
            <Typography variant="body2" color="text.secondary" mb={1}>
              Violations of this policy may result in:
            </Typography>
            <List dense disablePadding>
              {['Immediate suspension of your Telegizer account and all associated bots',
                'Reporting of abuse to Telegram for action against your bot token(s)',
                'Legal action where required by applicable law'].map((item) => (
                <ListItem key={item} disableGutters>
                  <ListItemText primary={<Typography variant="body2" color="text.secondary">• {item}</Typography>} />
                </ListItem>
              ))}
            </List>
          </CardContent>
        </Card>

        <Card sx={{ mb: 4 }}>
          <CardContent>
            <Typography variant="h6" fontWeight={700} mb={1}>Contact</Typography>
            <Typography variant="body2" color="text.secondary">
              If you have questions about this policy or want to report abuse, contact us at{' '}
              <Link href={`mailto:${SUPPORT_EMAIL}`}>{SUPPORT_EMAIL}</Link>.
            </Typography>
          </CardContent>
        </Card>

        <Divider sx={{ mb: 3 }} />
        <Box sx={{ display: 'flex', gap: 2, justifyContent: 'center' }}>
          <Button variant="outlined" onClick={() => navigate('/terms')}>Terms of Service</Button>
          <Button variant="outlined" onClick={() => navigate('/privacy')}>Privacy Policy</Button>
          <Button variant="contained" onClick={() => navigate('/register')}>Get Started</Button>
        </Box>
      </Container>
    </Box>
  );
}
