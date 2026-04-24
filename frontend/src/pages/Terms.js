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

export default function Terms() {
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
        <Typography variant="h4" fontWeight={800} mb={1}>Terms of Service</Typography>
        <Typography variant="body2" color="text.disabled" mb={4}>
          Last updated: {LAST_UPDATED}
        </Typography>
        <Divider sx={{ mb: 4 }} />

        <P>
          By accessing or using BotForge ("the Service"), you agree to be bound by these Terms of
          Service. If you do not agree to these terms, please do not use the Service.
        </P>

        <Section title="1. Service Description">
          <P>
            BotForge is a SaaS platform that allows you to connect, configure, and automate
            Telegram bots for community management. Features include automated moderation,
            scheduled messages, member analytics, polls, and more.
          </P>
          <P>
            BotForge is not affiliated with Telegram Messenger. Your use of Telegram bots through
            our platform is also subject to Telegram's own Terms of Service.
          </P>
        </Section>

        <Section title="2. Account Registration">
          <P>
            You must provide accurate, current, and complete information when creating an account.
            You are responsible for maintaining the confidentiality of your login credentials and
            for all activity that occurs under your account.
          </P>
          <P>
            You must be at least 16 years of age to use the Service. By registering, you confirm
            that you meet this age requirement.
          </P>
          <P>
            We reserve the right to suspend or terminate accounts that violate these terms, engage
            in abuse, or provide false registration information.
          </P>
        </Section>

        <Section title="3. Payments & Refunds">
          <P>
            Paid plans (Pro, Enterprise) are billed monthly. Payment is accepted via
            cryptocurrency through NOWPayments (USDT, BTC, ETH, BNB, and 300+ coins). Card
            payments will be available when our card processor review is complete.
          </P>
          <P>
            Subscriptions are activated immediately upon confirmed payment. Crypto payments may
            take 1–10 minutes to confirm depending on network congestion.
          </P>
          <P>
            We offer a 14-day money-back guarantee on your first subscription purchase. If you are
            not satisfied, contact us within 14 days of payment at {CONTACT_EMAIL} and we will
            process a full refund. Refunds are not available for subsequent billing periods.
          </P>
          <P>
            Subscriptions do not auto-renew. You must manually renew your plan before expiry to
            maintain access to paid features. You will not be charged without your explicit action.
          </P>
        </Section>

        <Section title="4. Free Plan">
          <P>
            The Free plan is available at no cost and includes basic features (1 bot, 1 group per
            bot). We reserve the right to modify, limit, or discontinue the Free plan at any time
            with reasonable notice.
          </P>
        </Section>

        <Section title="5. User Responsibilities">
          <P>You agree to use the Service only for lawful purposes. You must not:</P>
          <Box component="ul" sx={{ pl: 3, color: 'text.secondary' }}>
            {[
              'Use BotForge to send spam, unsolicited messages, or harass users',
              'Violate Telegram\'s Terms of Service through bots managed on our platform',
              'Use the Service to distribute malware, phishing content, or illegal material',
              'Attempt to reverse-engineer, hack, or disrupt the platform',
              'Create multiple accounts to abuse free-tier limits',
              'Resell or sublicense access to the Service without written permission',
            ].map((item) => (
              <Typography key={item} component="li" variant="body2" color="text.secondary" mb={0.5} lineHeight={1.8}>
                {item}
              </Typography>
            ))}
          </Box>
        </Section>

        <Section title="6. Bot Token Security">
          <P>
            You are responsible for keeping your Telegram bot tokens secure. BotForge stores
            tokens encrypted at rest. If you believe a token has been compromised, revoke it
            immediately via @BotFather and update it in your BotForge dashboard.
          </P>
        </Section>

        <Section title="7. Data & Privacy">
          <P>
            Your use of the Service is also governed by our{' '}
            <Typography
              component="span"
              variant="body2"
              color="primary.main"
              sx={{ cursor: 'pointer' }}
              onClick={() => navigate('/privacy')}
            >
              Privacy Policy
            </Typography>
            , which is incorporated into these Terms by reference.
          </P>
        </Section>

        <Section title="8. Service Availability">
          <P>
            We strive for 24/7 availability but do not guarantee uninterrupted service. Scheduled
            maintenance will be announced in advance where possible. We are not liable for losses
            caused by downtime, delays, or data loss.
          </P>
          <P>
            Enterprise plan customers receive priority support and an SLA guarantee as described
            in their plan details.
          </P>
        </Section>

        <Section title="9. Intellectual Property">
          <P>
            BotForge and its logos, design, and software are the property of BotForge. You retain
            ownership of any content you provide (messages, bot configurations) but grant us a
            limited license to process it to provide the Service.
          </P>
        </Section>

        <Section title="10. Limitation of Liability">
          <P>
            To the maximum extent permitted by law, BotForge is not liable for any indirect,
            incidental, special, or consequential damages arising from your use of the Service,
            including but not limited to loss of data, revenue, or community engagement.
          </P>
          <P>
            Our total liability in any matter is limited to the amount you paid us in the 30 days
            preceding the claim.
          </P>
        </Section>

        <Section title="11. Termination">
          <P>
            You may delete your account at any time from the dashboard. Termination does not
            entitle you to a refund outside the 14-day guarantee window. We may terminate your
            account for violation of these Terms with or without notice.
          </P>
        </Section>

        <Section title="12. Changes to Terms">
          <P>
            We may update these Terms from time to time. We will notify you of significant changes
            via email or an in-app notice. Continued use of the Service after changes constitutes
            acceptance of the updated Terms.
          </P>
        </Section>

        <Section title="13. Contact">
          <P>
            Questions about these Terms? Contact us at{' '}
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
            onClick={() => navigate('/privacy')}
          >
            Privacy Policy
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
