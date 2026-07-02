import React from 'react';
import {
  Box, AppBar, Toolbar, Typography, Button, Container, Divider, Link,
} from '@mui/material';
import TelegizerLogo from '../components/TelegizerLogo';
import { useNavigate } from 'react-router-dom';
import usePageMeta from '../hooks/usePageMeta';
import { SUPPORT_EMAIL } from '../config/support';

const LAST_UPDATED = 'May 9, 2026';

function PageNav() {
  const navigate = useNavigate();
  return (
    <AppBar position="sticky" elevation={0} sx={{ borderBottom: '1px solid', borderColor: 'divider', bgcolor: 'background.default' }}>
      <Toolbar>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, cursor: 'pointer', flexGrow: 1 }} onClick={() => navigate('/')}>
          <TelegizerLogo size="sm" variant="icon" />
          <Typography variant="h6" fontWeight={700}>Telegizer</Typography>
        </Box>
        <Button size="small" onClick={() => navigate('/register')}>Get Started</Button>
      </Toolbar>
    </AppBar>
  );
}

function Section({ title, children }) {
  return (
    <Box sx={{ mb: { xs: 2.5, sm: 4 } }}>
      <Typography variant="h6" fontWeight={700} mb={1.5}>{title}</Typography>
      {children}
    </Box>
  );
}

function P({ children }) {
  return (
    <Typography variant="body2" color="text.secondary" lineHeight={1.9} mb={1.5}>
      {children}
    </Typography>
  );
}

function UL({ items }) {
  return (
    <Box component="ul" sx={{ pl: { xs: 2, sm: 3 }, mb: 1.5 }}>
      {items.map((item) => (
        <Typography key={item} component="li" variant="body2" color="text.secondary" mb={0.5} lineHeight={1.8}>
          {item}
        </Typography>
      ))}
    </Box>
  );
}

function PageFooter() {
  const navigate = useNavigate();
  return (
    <>
      <Divider sx={{ mt: 6, mb: 3 }} />
      <Box sx={{ display: 'flex', gap: { xs: 1.5, md: 3 }, flexWrap: 'wrap', pb: 6 }}>
        {[
          { label: 'Privacy Policy', path: '/privacy' },
          { label: 'Contact', path: '/contact' },
          { label: 'About', path: '/about' },
          { label: 'Back to Home', path: '/' },
        ].map(({ label, path }) => (
          <Typography
            key={path}
            variant="body2"
            color="primary.main"
            sx={{ cursor: 'pointer' }}
            onClick={() => navigate(path)}
          >
            {label}
          </Typography>
        ))}
      </Box>
    </>
  );
}

export default function Terms() {
  usePageMeta(
    'Terms of Service',
    'Telegizer Terms of Service: subscriptions, refunds, acceptable use, and your rights when using our Telegram community management platform.'
  );
  const navigate = useNavigate();

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <PageNav />
      <Container maxWidth="md" sx={{ py: 6 }}>
        <Typography variant="h4" fontWeight={800} mb={1}>Terms of Service</Typography>
        <Typography variant="body2" color="text.disabled" mb={4}>Last updated: {LAST_UPDATED}</Typography>
        <Divider sx={{ mb: 4 }} />

        <P>
          By accessing or using Telegizer ("the Service", "we", "us") at telegizer.com, you agree
          to be bound by these Terms of Service. If you do not agree to these terms, please do not
          use the Service.
        </P>

        <Section title="1. Service Description">
          <P>
            Telegizer is a SaaS platform that allows you to connect, configure, and automate
            Telegram bots for community management. Features include automated moderation,
            scheduled messages, member analytics, XP/leveling, custom commands, AI digests,
            and more.
          </P>
          <P>
            Telegizer is not affiliated with Telegram Messenger LLP. Your use of Telegram bots
            through our platform is also subject to Telegram's own Terms of Service.
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

        <Section title="3. Subscriptions & Payments">
          <P>
            Paid plans (Pro, Enterprise) are billed as one-time payments per billing period.
            Payment is accepted via cryptocurrency through NOWPayments (USDT, BTC, ETH, BNB,
            and 300+ coins).
          </P>
          <P>
            Subscriptions are activated immediately upon confirmed payment. Cryptocurrency
            payments may take 1–10 minutes to confirm depending on network congestion.
          </P>
          <P>
            Subscriptions do not auto-renew. You must manually renew before expiry to maintain
            access to paid features. You will not be charged without your explicit action.
          </P>
        </Section>

        <Section title="4. Refund Policy">
          <P>
            We offer a 14-day money-back guarantee on your first subscription purchase. If you
            are not satisfied, contact us within 14 days of payment at{' '}
            <Link href={`mailto:${SUPPORT_EMAIL}`} color="primary.main" underline="hover">{SUPPORT_EMAIL}</Link>{' '}
            and we will process a full refund. Refunds are issued in the same currency/method
            where technically possible; crypto refunds are processed at current exchange rates.
          </P>
          <P>
            Refunds are not available after the 14-day window or for subsequent billing periods.
            Partial refunds for unused time are not provided.
          </P>
        </Section>

        <Section title="5. Free Plan">
          <P>
            The Free plan is available at no cost and includes basic features (1 custom bot
            with up to 3 groups, plus unlimited groups on the shared @telegizer_bot). New
            accounts also receive a one-time 14-day Pro trial, which downgrades to the Free
            plan automatically when it ends — no payment is taken. We reserve the right to
            modify, limit, or discontinue the Free plan at any time with reasonable notice
            (minimum 30 days for existing free users).
          </P>
        </Section>

        <Section title="6. Acceptable Use">
          <P>You agree to use the Service only for lawful purposes. You must not:</P>
          <UL items={[
            'Use Telegizer to send spam, unsolicited messages, or harass users',
            "Violate Telegram's Terms of Service through bots managed on our platform",
            'Use the Service to distribute malware, phishing content, or illegal material',
            'Attempt to reverse-engineer, scrape, hack, or disrupt the platform',
            'Create multiple accounts to abuse free-tier limits',
            'Resell or sublicense access to the Service without written permission',
            'Use the Service to collect personal data without proper consent',
            'Impersonate Telegizer or any other person or organization',
          ]} />
        </Section>

        <Section title="7. Bot Token Security">
          <P>
            You are responsible for keeping your Telegram bot tokens secure. Telegizer stores
            tokens encrypted at rest using AES-256. If you believe a token has been compromised,
            revoke it immediately via @BotFather and update it in your Telegizer dashboard.
            We are not liable for damages resulting from compromised tokens.
          </P>
        </Section>

        <Section title="8. AI Features">
          <P>
            AI-powered features (digests, auto-replies, assistant) are provided on a
            best-effort basis. AI responses may be inaccurate, incomplete, or inappropriate.
            You are responsible for reviewing AI-generated content before relying on it.
            Telegizer is not liable for damages arising from AI errors or omissions.
          </P>
          <P>
            You must ensure that your group members are appropriately informed about and
            consent to AI message processing where required by applicable law.
          </P>
        </Section>

        <Section title="9. Data & Privacy">
          <P>
            Your use of the Service is governed by our{' '}
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

        <Section title="10. Service Availability">
          <P>
            We strive for 24/7 availability but do not guarantee uninterrupted service. Scheduled
            maintenance will be announced in advance where possible. We target 99.5% uptime for
            paid plans. We are not liable for losses caused by downtime, delays, or data loss
            outside our reasonable control.
          </P>
        </Section>

        <Section title="11. Intellectual Property">
          <P>
            Telegizer, its logo, design, and software are the intellectual property of Telegizer.
            You retain ownership of your content (bot configurations, custom commands, messages)
            but grant us a limited, non-exclusive license to process it to provide the Service.
          </P>
          <P>
            You may not use the Telegizer name, logo, or branding without prior written permission.
          </P>
        </Section>

        <Section title="12. Limitation of Liability">
          <P>
            To the maximum extent permitted by applicable law, Telegizer is not liable for any
            indirect, incidental, special, or consequential damages arising from your use of the
            Service, including loss of data, revenue, profits, or community engagement.
          </P>
          <P>
            Our total aggregate liability for any claim is limited to the greater of (a) the
            amount you paid us in the 90 days preceding the claim, or (b) $10 USD.
          </P>
        </Section>

        <Section title="13. Indemnification">
          <P>
            You agree to indemnify and hold Telegizer harmless from any claims, damages, or
            expenses (including legal fees) arising from your use of the Service, your violation
            of these Terms, or your violation of any third-party rights.
          </P>
        </Section>

        <Section title="14. Termination">
          <P>
            You may delete your account at any time from Settings → Account → Delete Account.
            Termination does not entitle you to a refund outside the 14-day guarantee window.
          </P>
          <P>
            We may suspend or terminate your account for violation of these Terms, with or without
            prior notice. In cases of serious violations (illegal activity, harassment), termination
            is immediate. For other violations, we will typically provide a warning first.
          </P>
        </Section>

        <Section title="15. Governing Law">
          <P>
            These Terms are governed by the laws of the jurisdiction in which Telegizer operates,
            without regard to conflict of law provisions. Any disputes will be resolved through
            good-faith negotiation first; failing that, through binding arbitration or the courts
            of the applicable jurisdiction.
          </P>
        </Section>

        <Section title="16. Changes to Terms">
          <P>
            We may update these Terms from time to time. We will notify you of significant changes
            via email or an in-app notice at least 14 days before they take effect. Continued
            use of the Service after changes constitutes acceptance of the updated Terms.
          </P>
        </Section>

        <Section title="17. Contact">
          <P>
            Questions about these Terms? Contact us at{' '}
            <Link href={`mailto:${SUPPORT_EMAIL}`} color="primary.main" underline="hover">{SUPPORT_EMAIL}</Link>.
            We aim to respond within 2 business days.
          </P>
        </Section>

        <PageFooter />
      </Container>
    </Box>
  );
}
