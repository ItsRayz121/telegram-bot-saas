import React from 'react';
import {
  Box, AppBar, Toolbar, Typography, Button, Container, Divider,
} from '@mui/material';
import { SmartToy } from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';

const LAST_UPDATED = 'April 24, 2026';
const CONTACT_EMAIL = 'support@botforge.app';

function Section({ title, children }) {
  return (
    <Box sx={{ mb: 4 }}>
      <Typography variant="h6" fontWeight={700} mb={1.5}>{title}</Typography>
      {children}
    </Box>
  );
}

function P({ children }) {
  return (
    <Typography variant="body2" color="text.secondary" lineHeight={1.8} mb={1.5}>
      {children}
    </Typography>
  );
}

export default function Privacy() {
  const navigate = useNavigate();

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <AppBar position="sticky" elevation={0} sx={{ borderBottom: '1px solid', borderColor: 'divider', bgcolor: 'background.default' }}>
        <Toolbar>
          <SmartToy sx={{ mr: 1, color: 'primary.main' }} />
          <Typography
            variant="h6"
            fontWeight={700}
            sx={{ flexGrow: 1, cursor: 'pointer' }}
            onClick={() => navigate('/')}
          >
            BotForge
          </Typography>
          <Button onClick={() => navigate('/register')}>Get Started</Button>
        </Toolbar>
      </AppBar>

      <Container maxWidth="md" sx={{ py: 6 }}>
        <Typography variant="h4" fontWeight={800} mb={1}>Privacy Policy</Typography>
        <Typography variant="body2" color="text.disabled" mb={4}>
          Last updated: {LAST_UPDATED}
        </Typography>
        <Divider sx={{ mb: 4 }} />

        <P>
          BotForge ("we", "us", "our") is committed to protecting your privacy. This Privacy Policy
          explains what information we collect, how we use it, and your rights regarding that data.
          By using BotForge, you agree to the practices described here.
        </P>

        <Section title="1. Information We Collect">
          <Typography variant="subtitle2" fontWeight={600} mb={1}>Account Information</Typography>
          <P>
            When you register, we collect your full name, email address, and a hashed version of
            your password. We never store your password in plain text.
          </P>
          <Typography variant="subtitle2" fontWeight={600} mb={1}>Bot & Group Data</Typography>
          <P>
            To provide the Service, we store your Telegram bot tokens (encrypted at rest), the
            Telegram group IDs your bots manage, and configuration settings you apply (AutoMod
            rules, scheduled messages, etc.).
          </P>
          <Typography variant="subtitle2" fontWeight={600} mb={1}>Community Member Data</Typography>
          <P>
            BotForge processes Telegram user IDs, usernames, and activity data (XP, warnings,
            message counts) for members in the groups your bot manages. This data is used solely
            to deliver the features you configure (moderation, levels, analytics).
          </P>
          <Typography variant="subtitle2" fontWeight={600} mb={1}>Payment Data</Typography>
          <P>
            Payments are processed by NOWPayments (crypto) and Lemon Squeezy (card, when
            available). We do not store your payment instrument details. We retain transaction
            records (order IDs, plan tier, timestamp) for billing purposes.
          </P>
          <Typography variant="subtitle2" fontWeight={600} mb={1}>Usage Data</Typography>
          <P>
            We collect standard server logs including IP addresses, request timestamps, and
            response codes to operate and improve the service. We do not sell this data.
          </P>
        </Section>

        <Section title="2. How We Use Your Information">
          <Box component="ul" sx={{ pl: 3, color: 'text.secondary' }}>
            {[
              'Provide, operate, and improve the BotForge platform',
              'Authenticate your account and keep it secure',
              'Process payments and manage subscriptions',
              'Send transactional emails (welcome, password reset, subscription confirmation)',
              'Enforce our Terms of Service and prevent abuse',
              'Analyze aggregate usage patterns to improve the product',
            ].map((item) => (
              <Typography key={item} component="li" variant="body2" color="text.secondary" mb={0.5} lineHeight={1.8}>
                {item}
              </Typography>
            ))}
          </Box>
          <P>
            We do not use your data for advertising. We do not sell or share your personal data
            with third parties for marketing purposes.
          </P>
        </Section>

        <Section title="3. Data Storage & Security">
          <P>
            Data is stored in encrypted PostgreSQL databases hosted on Railway (US region by
            default). Bot tokens are encrypted at the application layer before storage. Passwords
            are hashed using bcrypt and never stored in plain text.
          </P>
          <P>
            All communication between your browser and our servers is encrypted via HTTPS (TLS).
            We follow industry-standard security practices but cannot guarantee absolute security.
            You are responsible for keeping your login credentials confidential.
          </P>
        </Section>

        <Section title="4. Third-Party Services">
          <P>BotForge integrates with the following third-party services:</P>
          <Box component="ul" sx={{ pl: 3, color: 'text.secondary' }}>
            {[
              'Telegram — to run your bots (subject to Telegram\'s Privacy Policy)',
              'NOWPayments — for cryptocurrency payment processing',
              'Lemon Squeezy — for card payment processing (when available)',
              'Railway — for cloud hosting and database infrastructure',
              'SendGrid / SMTP — for transactional email delivery',
            ].map((item) => (
              <Typography key={item} component="li" variant="body2" color="text.secondary" mb={0.5} lineHeight={1.8}>
                {item}
              </Typography>
            ))}
          </Box>
          <P>
            Each third party has its own privacy policy. We only share the minimum data necessary
            to deliver the service.
          </P>
        </Section>

        <Section title="5. Data Retention">
          <P>
            We retain your account and bot configuration data for as long as your account is
            active. If you delete your account, we permanently delete your personal data within
            30 days, except where we are required by law to retain it (e.g., transaction records
            for accounting).
          </P>
          <P>
            Community member data (Telegram user IDs, XP, warnings) is deleted when you delete
            the associated bot or group configuration.
          </P>
        </Section>

        <Section title="6. Cookies">
          <P>
            BotForge uses browser localStorage to store your authentication token. We do not use
            third-party advertising cookies or tracking pixels. We may use essential session
            cookies for security purposes.
          </P>
        </Section>

        <Section title="7. Your Rights">
          <P>Depending on your location, you may have the following rights:</P>
          <Box component="ul" sx={{ pl: 3, color: 'text.secondary' }}>
            {[
              'Access — request a copy of the personal data we hold about you',
              'Correction — ask us to correct inaccurate data',
              'Deletion — request deletion of your personal data ("right to be forgotten")',
              'Portability — receive your data in a machine-readable format',
              'Objection — object to certain processing of your data',
            ].map((item) => (
              <Typography key={item} component="li" variant="body2" color="text.secondary" mb={0.5} lineHeight={1.8}>
                {item}
              </Typography>
            ))}
          </Box>
          <P>
            To exercise any of these rights, email us at {CONTACT_EMAIL}. We will respond within
            30 days.
          </P>
        </Section>

        <Section title="8. Children's Privacy">
          <P>
            BotForge is not intended for users under 16. We do not knowingly collect personal
            data from children. If you believe we have collected data from a minor, please contact
            us immediately.
          </P>
        </Section>

        <Section title="9. Changes to This Policy">
          <P>
            We may update this Privacy Policy from time to time. We will notify you of material
            changes via email or an in-app notice at least 14 days before they take effect.
            Continued use of the Service constitutes acceptance of the updated policy.
          </P>
        </Section>

        <Section title="10. Contact">
          <P>
            For privacy-related questions or requests, contact us at{' '}
            <Typography component="span" variant="body2" color="primary.main">
              {CONTACT_EMAIL}
            </Typography>
            . We aim to respond within 2 business days.
          </P>
        </Section>

        <Divider sx={{ mt: 4, mb: 3 }} />
        <Box sx={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
          <Typography
            variant="body2"
            color="primary.main"
            sx={{ cursor: 'pointer' }}
            onClick={() => navigate('/terms')}
          >
            Terms of Service
          </Typography>
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ cursor: 'pointer' }}
            onClick={() => navigate('/')}
          >
            Back to Home
          </Typography>
        </Box>
      </Container>
    </Box>
  );
}
