import React from 'react';
import {
  Box, AppBar, Toolbar, Typography, Button, Container, Divider, Link,
} from '@mui/material';
import TelegizerLogo from '../components/TelegizerLogo';
import { useNavigate } from 'react-router-dom';

const LAST_UPDATED = 'May 9, 2026';
const SUPPORT_EMAIL = 'support@telegizer.com';
const PRIVACY_EMAIL = 'privacy@telegizer.com';

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
    <Box sx={{ mb: 4 }}>
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
    <Box component="ul" sx={{ pl: 3, mb: 1.5 }}>
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
      <Box sx={{ display: 'flex', gap: 3, flexWrap: 'wrap', pb: 6 }}>
        {[
          { label: 'Terms of Service', path: '/terms' },
          { label: 'Contact', path: '/contact' },
          { label: 'About', path: '/about' },
          { label: 'Back to Home', path: '/' },
        ].map(({ label, path }) => (
          <Typography
            key={path}
            variant="body2"
            color={path === '/privacy' ? 'text.disabled' : 'primary.main'}
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

export default function Privacy() {
  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <PageNav />
      <Container maxWidth="md" sx={{ py: 6 }}>
        <Typography variant="h4" fontWeight={800} mb={1}>Privacy Policy</Typography>
        <Typography variant="body2" color="text.disabled" mb={4}>Last updated: {LAST_UPDATED}</Typography>
        <Divider sx={{ mb: 4 }} />

        <P>
          Telegizer ("we", "us", "our") is committed to protecting your privacy. This Privacy Policy
          explains what information we collect, how we use it, and your rights regarding that data.
          By using Telegizer, you agree to the practices described here.
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
            rules, scheduled messages, custom commands, etc.).
          </P>
          <Typography variant="subtitle2" fontWeight={600} mb={1}>Community Member Data</Typography>
          <P>
            Telegizer processes Telegram user IDs, usernames, and activity data (XP, warnings,
            message counts) for members in the groups your bot manages. This data is used solely
            to deliver the features you configure — moderation, levels, analytics.
          </P>
          <Typography variant="subtitle2" fontWeight={600} mb={1}>Payment Data</Typography>
          <P>
            Payments are processed by NOWPayments (crypto). We do not store your payment
            instrument details. We retain transaction records (order IDs, plan tier, timestamp)
            for billing and accounting purposes.
          </P>
          <Typography variant="subtitle2" fontWeight={600} mb={1}>Usage & Log Data</Typography>
          <P>
            We collect standard server logs including IP addresses, request timestamps, and
            response codes to operate and improve the service. We do not sell this data.
          </P>
        </Section>

        <Section title="2. How We Use Your Information">
          <UL items={[
            'Provide, operate, and improve the Telegizer platform',
            'Authenticate your account and keep it secure',
            'Process payments and manage subscriptions',
            'Send transactional emails (welcome, password reset, subscription confirmation)',
            'Enforce our Terms of Service and prevent abuse',
            'Analyze aggregate usage patterns to improve the product',
          ]} />
          <P>
            We do not use your data for advertising. We do not sell or share your personal data
            with third parties for marketing purposes.
          </P>
        </Section>

        <Section title="3. Data Storage & Security">
          <P>
            Data is stored in encrypted PostgreSQL databases hosted on Railway. Bot tokens are
            encrypted at the application layer (AES-256) before storage. Passwords are hashed
            using bcrypt and never stored in plain text.
          </P>
          <P>
            All communication between your browser and our servers is encrypted via HTTPS (TLS 1.2+).
            We follow industry-standard security practices, but no system is 100% secure. You are
            responsible for keeping your login credentials confidential.
          </P>
        </Section>

        <Section title="4. AI Features & Message Storage">
          <P>
            When you enable AI Daily Digest or Auto-Reply features, Telegizer temporarily stores
            message content from your linked Telegram groups to generate AI summaries and responses.
          </P>
          <UL items={[
            'Stored for a maximum of 72 hours, then automatically deleted',
            'Encrypted at rest using AES-256',
            'Never shared with third parties or used for training AI models',
            'Stored on US/EU Railway infrastructure',
            'You control this via the "Store Messages for AI Features" toggle per group',
          ]} />
          <P>
            Legal basis (GDPR): Legitimate interests in providing the contracted AI service,
            balanced against member privacy. You must obtain appropriate consent from your group
            members before enabling AI message storage.
          </P>
        </Section>

        <Section title="5. Third-Party Services">
          <P>Telegizer integrates with the following third-party services:</P>
          <UL items={[
            'Telegram — to run your bots (subject to Telegram\'s Privacy Policy)',
            'NOWPayments — for cryptocurrency payment processing',
            'Railway — for cloud hosting and database infrastructure',
            'Resend / SMTP — for transactional email delivery',
            'OpenRouter — for AI features (platform-provided key only; messages are not retained)',
            'Sentry — for error monitoring (anonymized crash reports only)',
            'PostHog — for product analytics (anonymized usage data)',
            'Plausible — for privacy-first website analytics (no cookies, no personal data)',
          ]} />
          <P>
            Each third party has its own privacy policy. We share only the minimum data necessary
            to deliver the service.
          </P>
        </Section>

        <Section title="6. Cookies & Local Storage">
          <P>
            Telegizer uses secure HTTP-only cookies to store your authentication tokens. We do not
            use third-party advertising cookies or tracking pixels. Analytics (Plausible) use no
            cookies and collect no personal data.
          </P>
        </Section>

        <Section title="7. Data Retention">
          <P>
            We retain your account and bot configuration data for as long as your account is active.
            If you delete your account, we permanently delete your personal data within 30 days,
            except where required by law (e.g., transaction records for accounting — retained for
            7 years in many jurisdictions).
          </P>
          <P>
            Community member data (Telegram user IDs, XP, warnings) is deleted when you delete
            the associated group configuration.
          </P>
        </Section>

        <Section title="8. Your Rights (GDPR & CCPA)">
          <P>Depending on your location, you may have the following rights:</P>
          <UL items={[
            'Access — request a copy of the personal data we hold about you',
            'Correction — ask us to correct inaccurate data',
            'Deletion — request deletion of your personal data ("right to be forgotten")',
            'Portability — receive your data in a machine-readable format',
            'Objection — object to certain processing of your data',
            'Restriction — ask us to restrict processing in certain circumstances',
          ]} />
          <P>
            To exercise any of these rights, email us at{' '}
            <Link href={`mailto:${PRIVACY_EMAIL}`} color="primary.main" underline="hover">{PRIVACY_EMAIL}</Link>.
            We will respond within 30 days (EU users: within 1 month as required by GDPR).
          </P>
        </Section>

        <Section title="9. Children's Privacy">
          <P>
            Telegizer is not intended for users under 16. We do not knowingly collect personal
            data from children. If you believe we have collected data from a minor, please contact
            us immediately at {PRIVACY_EMAIL} and we will delete it promptly.
          </P>
        </Section>

        <Section title="10. International Transfers">
          <P>
            Your data may be processed in the United States where our infrastructure is hosted.
            If you are based in the EU/EEA, your data is transferred under appropriate safeguards
            (Railway's EU region availability or Standard Contractual Clauses where applicable).
          </P>
        </Section>

        <Section title="11. Changes to This Policy">
          <P>
            We may update this Privacy Policy from time to time. We will notify you of material
            changes via email or an in-app notice at least 14 days before they take effect.
            Continued use of the Service constitutes acceptance of the updated policy. The
            "Last updated" date at the top always reflects the current version.
          </P>
        </Section>

        <Section title="12. Contact">
          <P>
            For privacy-related questions or data requests, contact us at{' '}
            <Link href={`mailto:${PRIVACY_EMAIL}`} color="primary.main" underline="hover">{PRIVACY_EMAIL}</Link>.
            For general support, use{' '}
            <Link href={`mailto:${SUPPORT_EMAIL}`} color="primary.main" underline="hover">{SUPPORT_EMAIL}</Link>.
            We aim to respond within 2 business days.
          </P>
        </Section>

        <PageFooter />
      </Container>
    </Box>
  );
}
