import React, { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, Outlet, useParams, useLocation } from 'react-router-dom';
import { trackGAPageView } from './index';
import { Box, CircularProgress, Typography, Button } from '@mui/material';
import { ThemeProvider } from '@mui/material/styles';
import telegizer from './theme';
import CssBaseline from '@mui/material/CssBaseline';
import { ToastContainer } from 'react-toastify';
import ConnectionStatus from './components/connection/ConnectionStatus';
import 'react-toastify/dist/ReactToastify.css';
import ErrorBoundary from './components/ErrorBoundary';
import PWAInstallBanner from './components/PWAInstallBanner';
import CookieConsent from './components/CookieConsent';
import DebugPanel from './components/DebugPanel';
import AppLayout from './layouts/AppLayout';
import AdminLayout from './layouts/AdminLayout';
import { API_CONFIG_ERROR } from './services/api';
import { isTelegramMiniApp } from './utils/telegram';

// Pages — public
import Landing from './pages/Landing';
import Login from './pages/Login';
import Register from './pages/Register';
import NotFound from './pages/NotFound';

// Pages — authenticated (sidebar layout)

// Pages — new sections
import MiniAppLayout from './layouts/MiniAppLayout';

// Echo (AI Assistant)

// Discord pillar (Guildizer) — separate backend, embedded UI
import GuildizerAdminLayout from './layouts/GuildizerAdminLayout';

import lazyWithRetry, { clearChunkReloadFlag } from './utils/lazyWithRetry';

// Pages — lazy loaded
const GuildizerLanding = lazyWithRetry(() => import('./pages/GuildizerLanding'));
const EchoLanding = lazyWithRetry(() => import('./pages/EchoLanding'));
const Pricing = lazyWithRetry(() => import('./pages/Pricing'));
const PaymentSuccess = lazyWithRetry(() => import('./pages/PaymentSuccess'));
const Terms = lazyWithRetry(() => import('./pages/Terms'));
const Privacy = lazyWithRetry(() => import('./pages/Privacy'));
const AcceptableUse = lazyWithRetry(() => import('./pages/AcceptableUse'));
const Contact = lazyWithRetry(() => import('./pages/Contact'));
const About = lazyWithRetry(() => import('./pages/About'));
const Status = lazyWithRetry(() => import('./pages/Status'));
const VerifyEmail = lazyWithRetry(() => import('./pages/VerifyEmail'));
const ForgotPassword = lazyWithRetry(() => import('./pages/ForgotPassword'));
const ResetPassword = lazyWithRetry(() => import('./pages/ResetPassword'));
const Dashboard = lazyWithRetry(() => import('./pages/Dashboard'));
const MyGroups = lazyWithRetry(() => import('./pages/MyGroups'));
const GroupSettings = lazyWithRetry(() => import('./pages/GroupSettings'));
const GroupManagement = lazyWithRetry(() => import('./pages/GroupManagement'));
const OfficialGroupAnalytics = lazyWithRetry(() => import('./pages/OfficialGroupAnalytics'));
const MyBots = lazyWithRetry(() => import('./pages/MyBots'));
const CustomBotLifecycle = lazyWithRetry(() => import('./pages/CustomBotLifecycle'));
const BotSettings = lazyWithRetry(() => import('./pages/BotSettings'));
const GroupAnalytics = lazyWithRetry(() => import('./pages/GroupAnalytics'));
const Analytics = lazyWithRetry(() => import('./pages/Analytics'));
const Billing = lazyWithRetry(() => import('./pages/Billing'));
const Settings = lazyWithRetry(() => import('./pages/Settings'));
const NotificationsPage = lazyWithRetry(() => import('./pages/Notifications'));
const AdminPanel = lazyWithRetry(() => import('./pages/AdminPanel'));
const AdminUserDetail = lazyWithRetry(() => import('./pages/AdminUserDetail'));
const AdminGroupDetail = lazyWithRetry(() => import('./pages/AdminGroupDetail'));
const AdminCustomBotDetail = lazyWithRetry(() => import('./pages/AdminCustomBotDetail'));
const Channels = lazyWithRetry(() => import('./pages/Channels'));
const ChannelDetail = lazyWithRetry(() => import('./pages/ChannelDetail'));
const Workspace = lazyWithRetry(() => import('./pages/Workspace'));
const WorkspaceSmartLinks = lazyWithRetry(() => import('./pages/WorkspaceSmartLinks'));
const WorkspaceReminders = lazyWithRetry(() => import('./pages/WorkspaceReminders'));
const WorkspaceForwarding = lazyWithRetry(() => import('./pages/WorkspaceForwarding'));
const WorkspaceAutomations = lazyWithRetry(() => import('./pages/WorkspaceAutomations'));
const Integrations = lazyWithRetry(() => import('./pages/Integrations'));
const MiniApp = lazyWithRetry(() => import('./pages/MiniApp'));
const CampaignTask = lazyWithRetry(() => import('./pages/CampaignTask'));
const MyTasks = lazyWithRetry(() => import('./pages/MyTasks'));
const Directory = lazyWithRetry(() => import('./pages/Directory'));
const DirectorySubmit = lazyWithRetry(() => import('./pages/DirectorySubmit'));
const GroupCRM = lazyWithRetry(() => import('./pages/GroupCRM'));
const Marketplace = lazyWithRetry(() => import('./pages/Marketplace'));
const MarketplaceDeal = lazyWithRetry(() => import('./pages/MarketplaceDeal'));
const JoinReferral = lazyWithRetry(() => import('./pages/JoinReferral'));
const InviteLanding = lazyWithRetry(() => import('./pages/InviteLanding'));
const TeamInvitePage = lazyWithRetry(() => import('./pages/TeamInvitePage'));
const GroupTeamJoin = lazyWithRetry(() => import('./pages/GroupTeamJoin'));
const Referrals = lazyWithRetry(() => import('./pages/Referrals'));
const HubLanding = lazyWithRetry(() => import('./pages/HubLanding'));
const HubWorkspace = lazyWithRetry(() => import('./pages/HubWorkspace'));
const HubCustomBotWorkspace = lazyWithRetry(() => import('./pages/HubCustomBotWorkspace'));
const GuildizerServers = lazyWithRetry(() => import('./pages/guildizer/GuildizerServers'));
const GuildizerManageServers = lazyWithRetry(() => import('./pages/guildizer/GuildizerManageServers'));
const GuildizerServerDetail = lazyWithRetry(() => import('./pages/guildizer/GuildizerServerDetail'));
const GuildizerBots = lazyWithRetry(() => import('./pages/guildizer/GuildizerBots'));
const GuildizerNotifications = lazyWithRetry(() => import('./pages/guildizer/GuildizerNotifications'));
const GuildizerReferrals = lazyWithRetry(() => import('./pages/guildizer/GuildizerReferrals'));
const GuildizerAdminPanel = lazyWithRetry(() => import('./pages/guildizer/admin/GuildizerAdminPanel'));
const GuildizerAdminUserDetail = lazyWithRetry(() => import('./pages/guildizer/admin/GuildizerAdminUserDetail'));
const GuildizerAdminServerDetail = lazyWithRetry(() => import('./pages/guildizer/admin/GuildizerAdminServerDetail'));
const GuildizerAdminCustomBotDetail = lazyWithRetry(() => import('./pages/guildizer/admin/GuildizerAdminCustomBotDetail'));
const GuildizerAdminCampaignDetail = lazyWithRetry(() => import('./pages/guildizer/admin/GuildizerAdminCampaignDetail'));
const AdminHub = lazyWithRetry(() => import('./pages/AdminHub'));
const AssistantNotes = lazyWithRetry(() => import('./pages/AssistantNotes'));
const AssistantBotSettings = lazyWithRetry(() => import('./pages/AssistantBotSettings'));
const AssistantDigests = lazyWithRetry(() => import('./pages/AssistantDigests'));
const AssistantAISettings = lazyWithRetry(() => import('./pages/AssistantAISettings'));
const AssistantTasks = lazyWithRetry(() => import('./pages/AssistantTasks'));
const AssistantKnowledge = lazyWithRetry(() => import('./pages/AssistantKnowledge'));
const AssistantMemory = lazyWithRetry(() => import('./pages/AssistantMemory'));
const AssistantMeetingLinks = lazyWithRetry(() => import('./pages/AssistantMeetingLinks'));
const AnalyticsHub = lazyWithRetry(() => import('./pages/AnalyticsHub'));
const CampaignWorkspace = lazyWithRetry(() => import('./pages/campaigns/Workspace'));
const WorkflowBuilder = lazyWithRetry(() => import('./pages/WorkflowBuilder'));

// Initialize Sentry if DSN is configured
const SENTRY_DSN = process.env.REACT_APP_SENTRY_DSN;
if (SENTRY_DSN) {
  import('@sentry/react').then(({ init, browserTracingIntegration }) => {
    init({
      dsn: SENTRY_DSN,
      integrations: [browserTracingIntegration()],
      tracesSampleRate: 0.1,
      sendDefaultPii: false,
    });
  }).catch(() => {});
}

// Register service worker for PWA
if ('serviceWorker' in navigator && process.env.NODE_ENV === 'production') {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  });
}



function _storedUser() {
  try { return JSON.parse(localStorage.getItem('user') || '{}'); } catch { return {}; }
}

function GATracker() {
  const location = useLocation();
  useEffect(() => {
    trackGAPageView(location.pathname + location.search);
  }, [location]);
  return null;
}

// Reset scroll to the top on every route change. Without this, navigating
// from a scrolled page (e.g. a footer link) lands on the next page still
// scrolled to the bottom.
function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => {
    if ('scrollRestoration' in window.history) {
      window.history.scrollRestoration = 'manual';
    }
    window.scrollTo(0, 0);
  }, [pathname]);
  return null;
}

// Forces GroupSettings remount when groupId (or botId) changes, preventing stale state/race conditions
function KeyedGroupSettings() {
  const params = useParams();
  const key = params.id ? `${params.id}-${params.groupId}` : params.groupId;
  return <GroupSettings key={key} />;
}

// Requires auth + verified email + wraps in AppLayout (sidebar)
function AppRoute({ children }) {
  const token = localStorage.getItem('token');
  if (!token) return <Navigate to="/login" replace />;
  const user = _storedUser();
  // Users who authenticated via Telegram (provider = 'telegram' or 'both') don't
  // need to verify their email to access the dashboard — Telegram is their primary auth.
  // Only pure email-registered accounts must verify before entry.
  const hasTelegramAuth = user.auth_provider === 'telegram' || user.auth_provider === 'both';
  if (user.email_verified === false && !hasTelegramAuth) return <Navigate to="/verify-email" replace />;
  return <AppLayout>{children}</AppLayout>;
}

// Any public/marketing page that should NEVER render inside Telegram.
// When opened in the Mini App, bounce straight to TMA auth — no landing, no signup, no flash.
function TelegramAware({ children }) {
  if (isTelegramMiniApp()) {
    return <Navigate to="/mini-app" replace />;
  }
  return children;
}

function PublicOnlyRoute({ children }) {
  // If opened inside Telegram Mini App (any URL), always use TMA auth — never show email forms
  if (isTelegramMiniApp()) {
    return <Navigate to="/mini-app" replace />;
  }
  const token = localStorage.getItem('token');
  if (!token) return children;
  const user = _storedUser();
  const hasTelegramAuth = user.auth_provider === 'telegram' || user.auth_provider === 'both';
  if (user.email_verified === false && !hasTelegramAuth) return <Navigate to="/verify-email" replace />;
  return <Navigate to="/dashboard" replace />;
}

function AdminRoute({ children }) {
  const [status, setStatus] = useState('loading');
  const [adminUser, setAdminUser] = useState(null);

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) { setStatus('denied'); return; }
    const base = process.env.REACT_APP_API_URL || '';
    fetch(`${base}/api/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.json())
      .then(data => {
        if (data.user?.is_admin) {
          setAdminUser(data.user);
          try { localStorage.setItem('user', JSON.stringify(data.user)); } catch {}
          setStatus('allowed');
        } else {
          setStatus('denied');
        }
      })
      .catch(() => setStatus('denied'));
  }, []);

  if (status === 'loading') {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh' }}>
        <CircularProgress />
      </Box>
    );
  }
  if (status === 'denied') {
    return (
      <Box sx={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', gap: 2, px: 2, textAlign: 'center' }}>
        <Typography variant="h6" fontWeight={700}>Admin Access Required</Typography>
        <Typography variant="body2" color="text.secondary">
          Your account does not have admin privileges. Contact a platform administrator if you believe this is an error.
        </Typography>
        <Button variant="outlined" onClick={() => { window.location.href = '/dashboard'; }}>
          Return to Dashboard
        </Button>
      </Box>
    );
  }
  return <AdminLayout user={adminUser}>{children}</AdminLayout>;
}

// Guildizer admin: requires app login, then renders the dedicated full-screen
// Guildizer admin shell (which gates on the Guildizer session). Nested child
// routes render inside the shell's <Outlet/>. Kept fully separate from the
// Telegizer AdminRoute/AdminLayout above.
function GuildizerAdminRoute() {
  const token = localStorage.getItem('token');
  if (!token) return <Navigate to="/login" replace />;
  return <GuildizerAdminLayout><Outlet /></GuildizerAdminLayout>;
}

function RouteFallback() {
  return (
    <Box role="status" aria-label="Loading" sx={{ minHeight: '60vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <CircularProgress size={28} />
    </Box>
  );
}

export default function App() {
  // Allow one more recovery reload after the app has been up for a while (see utils/lazyWithRetry).
  useEffect(() => {
    const t = setTimeout(clearChunkReloadFlag, 10000);
    return () => clearTimeout(t);
  }, []);
  return (
    <ThemeProvider theme={telegizer}>
      <CssBaseline />
      {API_CONFIG_ERROR && (
        <Box sx={{ bgcolor: 'error.main', color: '#fff', p: 1.5, textAlign: 'center', fontSize: '0.85rem', fontWeight: 600, zIndex: 9999 }}>
          ⚠️ {API_CONFIG_ERROR}
        </Box>
      )}
      <ErrorBoundary>
        <BrowserRouter>
          <GATracker />
          <ScrollToTop />
          <React.Suspense fallback={<RouteFallback />}>
          <Routes>

            {/* ── Public (no sidebar) ─────────────────────────────────────── */}
            {/* Root + referral/invite entry pages: redirect to /mini-app when opened inside Telegram */}
            <Route path="/" element={<TelegramAware><Landing /></TelegramAware>} />
            <Route path="/guildizer-landing" element={<GuildizerLanding />} />
            <Route path="/echo" element={<EchoLanding />} />
            <Route path="/pricing" element={<Pricing />} />
            <Route path="/payment/success" element={<PaymentSuccess />} />
            <Route path="/terms" element={<Terms />} />
            <Route path="/privacy" element={<Privacy />} />
            <Route path="/acceptable-use" element={<AcceptableUse />} />
            <Route path="/contact" element={<Contact />} />
            <Route path="/about" element={<About />} />
            <Route path="/status" element={<Status />} />
            <Route path="/join" element={<TelegramAware><JoinReferral /></TelegramAware>} />
            <Route path="/invite/:code" element={<TelegramAware><InviteLanding /></TelegramAware>} />
            {/* Short website referral link (shared everywhere as the "Website link") */}
            <Route path="/r/:code" element={<TelegramAware><InviteLanding /></TelegramAware>} />
            <Route path="/team/join/:token" element={<TeamInvitePage />} />
            <Route path="/group-team/join/:code" element={<GroupTeamJoin />} />

            {/* ── Auth (no sidebar) ─────────────────────────────────────────── */}
            <Route path="/login"          element={<PublicOnlyRoute><Login /></PublicOnlyRoute>} />
            <Route path="/register"       element={<PublicOnlyRoute><Register /></PublicOnlyRoute>} />
            <Route path="/forgot-password" element={<ForgotPassword />} />
            <Route path="/reset-password"  element={<ResetPassword />} />
            <Route path="/verify-email"    element={<VerifyEmail />} />

            {/* ── Dashboard ─────────────────────────────────────────────────── */}
            <Route path="/dashboard" element={<AppRoute><Dashboard /></AppRoute>} />

            {/* ── Groups (canonical routes) ─────────────────────────────────── */}
            <Route path="/groups"                           element={<AppRoute><MyGroups /></AppRoute>} />
            <Route path="/groups/:groupId"                  element={<AppRoute><KeyedGroupSettings /></AppRoute>} />
            <Route path="/groups/:groupId/analytics"        element={<AppRoute><OfficialGroupAnalytics /></AppRoute>} />
            <Route path="/groups/:groupId/manage"           element={<AppRoute><GroupManagement /></AppRoute>} />
            <Route path="/groups/:groupId/crm"             element={<AppRoute><GroupCRM /></AppRoute>} />
            {/* Campaign workspace: the group in the URL is the only boundary */}
            <Route path="/groups/:groupId/campaigns"              element={<AppRoute><React.Suspense fallback={null}><CampaignWorkspace view="overview" /></React.Suspense></AppRoute>} />
            <Route path="/groups/:groupId/campaigns/all"          element={<AppRoute><React.Suspense fallback={null}><CampaignWorkspace view="list" /></React.Suspense></AppRoute>} />
            <Route path="/groups/:groupId/campaigns/review"       element={<AppRoute><React.Suspense fallback={null}><CampaignWorkspace view="review" /></React.Suspense></AppRoute>} />
            <Route path="/groups/:groupId/campaigns/new"          element={<AppRoute><React.Suspense fallback={null}><CampaignWorkspace view="create" /></React.Suspense></AppRoute>} />
            <Route path="/groups/:groupId/campaigns/:campaignId"  element={<AppRoute><React.Suspense fallback={null}><CampaignWorkspace view="detail" /></React.Suspense></AppRoute>} />

            {/* /my-groups/* → redirect to /groups/* (backward compat, preserves query string) */}
            <Route path="/my-groups"                        element={<RedirectMyGroups />} />
            <Route path="/my-groups/:groupId"               element={<RedirectGroupId prefix="/groups" />} />
            <Route path="/my-groups/:groupId/analytics"     element={<RedirectGroupId prefix="/groups" suffix="/analytics" />} />
            <Route path="/add-group"                        element={<Navigate to="/groups" replace />} />

            {/* ── Channels ──────────────────────────────────────────────────── */}
            <Route path="/channels"         element={<AppRoute><Channels /></AppRoute>} />
            <Route path="/channels/:cid"    element={<AppRoute><ChannelDetail /></AppRoute>} />

            {/* ── Echo (/ark prefix) ────────────────────────────────────────── */}
            <Route path="/ark"                         element={<AppRoute><HubLanding /></AppRoute>} />
            <Route path="/ark/official"                element={<Navigate to="/ark/official/overview" replace />} />
            <Route path="/ark/official/:tab"           element={<AppRoute><HubWorkspace /></AppRoute>} />
            <Route path="/ark/bots/:botId"             element={<Navigate to="overview" replace />} />
            <Route path="/ark/bots/:botId/:tab"        element={<AppRoute><HubCustomBotWorkspace /></AppRoute>} />
            {/* legacy /hub redirects */}
            <Route path="/hub"                         element={<Navigate to="/ark" replace />} />
            <Route path="/hub/official/:tab"           element={<Navigate to="/ark/official/overview" replace />} />
            <Route path="/hub/bots/:botId/:tab"        element={<Navigate to="/ark" replace />} />

            {/* ── Discord (Guildizer) — 3rd pillar ──────────────────────────── */}
            <Route path="/guildizer"                    element={<AppRoute><GuildizerServers /></AppRoute>} />
            <Route path="/guildizer/bots"               element={<AppRoute><GuildizerBots /></AppRoute>} />
            <Route path="/guildizer/notifications"      element={<AppRoute><GuildizerNotifications /></AppRoute>} />
            <Route path="/guildizer/referrals"          element={<AppRoute><GuildizerReferrals /></AppRoute>} />
            <Route path="/guildizer/servers"            element={<AppRoute><GuildizerManageServers /></AppRoute>} />
            <Route path="/guildizer/servers/:guildId"   element={<AppRoute><GuildizerServerDetail /></AppRoute>} />
            {/* Guildizer admin console — dedicated full-screen shell (nested) */}
            <Route path="/guildizer/admin" element={<GuildizerAdminRoute />}>
              <Route index element={<Navigate to="overview/dashboard" replace />} />
              <Route path="access/users/:userId" element={<GuildizerAdminUserDetail />} />
              <Route path="bots/servers/:guildId" element={<GuildizerAdminServerDetail />} />
              <Route path="bots/bot/:botId" element={<GuildizerAdminCustomBotDetail />} />
              <Route path="analytics/campaigns/:campaignId" element={<GuildizerAdminCampaignDetail />} />
              <Route path=":category/:section" element={<GuildizerAdminPanel />} />
            </Route>

            {/* ── Workspace ─────────────────────────────────────────────────── */}
            <Route path="/workspace"               element={<AppRoute><Workspace /></AppRoute>} />
            <Route path="/workspace/smart-links"   element={<AppRoute><WorkspaceSmartLinks /></AppRoute>} />
            <Route path="/workspace/reminders"     element={<AppRoute><WorkspaceReminders /></AppRoute>} />
            {/* Automation hub consolidated into per-group Automation tabs — redirect legacy link */}
            <Route path="/automation"              element={<Navigate to="/workspace" replace />} />
            <Route path="/integrations"            element={<AppRoute><Integrations /></AppRoute>} />
            <Route path="/workspace/forwarding"    element={<AppRoute><WorkspaceForwarding /></AppRoute>} />
            <Route path="/workspace/automations"   element={<AppRoute><WorkspaceAutomations /></AppRoute>} />
            <Route path="/workspace/notes"         element={<AppRoute><React.Suspense fallback={null}><AssistantNotes /></React.Suspense></AppRoute>} />
            <Route path="/workspace/digests"       element={<AppRoute><React.Suspense fallback={null}><AssistantDigests /></React.Suspense></AppRoute>} />
            <Route path="/workspace/ai-settings"   element={<AppRoute><React.Suspense fallback={null}><AssistantAISettings /></React.Suspense></AppRoute>} />
            <Route path="/workspace/tasks"         element={<AppRoute><React.Suspense fallback={null}><AssistantTasks /></React.Suspense></AppRoute>} />
            <Route path="/workspace/knowledge"     element={<AppRoute><React.Suspense fallback={null}><AssistantKnowledge /></React.Suspense></AppRoute>} />
            <Route path="/workspace/memory"        element={<AppRoute><React.Suspense fallback={null}><AssistantMemory /></React.Suspense></AppRoute>} />
            <Route path="/workspace/meeting-links" element={<AppRoute><React.Suspense fallback={null}><AssistantMeetingLinks /></React.Suspense></AppRoute>} />
            <Route path="/workspace/assistant-bot" element={<AppRoute><React.Suspense fallback={null}><AssistantBotSettings /></React.Suspense></AppRoute>} />
            <Route path="/workflow-builder"        element={<AppRoute><React.Suspense fallback={null}><WorkflowBuilder /></React.Suspense></AppRoute>} />

            {/* ── Telegram Mini App ─────────────────────────────────────────── */}
            <Route path="/mini-app" element={<MiniAppLayout><MiniApp /></MiniAppLayout>} />
            <Route path="/mini-app/*" element={<MiniAppLayout><MiniApp /></MiniAppLayout>} />

            {/* ── Engagement participant pages (Mini App tasks) ─────────────── */}
            <Route path="/tasks"     element={<AppRoute><MyTasks /></AppRoute>} />
            <Route path="/task/:id"  element={<AppRoute><CampaignTask /></AppRoute>} />

            {/* ── Directory ─────────────────────────────────────────────────── */}
            <Route path="/directory"              element={<Directory />} />
            <Route path="/directory/submit"       element={<AppRoute><DirectorySubmit /></AppRoute>} />
            <Route path="/marketplace"            element={<Marketplace />} />
            <Route path="/marketplace/deals"      element={<AppRoute><Marketplace tab="deals" /></AppRoute>} />
            <Route path="/marketplace/deals/:did" element={<AppRoute><MarketplaceDeal /></AppRoute>} />

            {/* ── Analytics ─────────────────────────────────────────────────── */}
            <Route path="/analytics"                element={<AppRoute><React.Suspense fallback={null}><AnalyticsHub /></React.Suspense></AppRoute>} />
            <Route path="/analytics/:id"            element={<AppRoute><Analytics /></AppRoute>} />
            <Route path="/official-analytics"       element={<Navigate to="/analytics" replace />} />

            {/* ── Custom bots (canonical /custom-bots, keep /my-bots alias) ─── */}
            <Route path="/custom-bots"              element={<AppRoute><MyBots /></AppRoute>} />
            <Route path="/my-bots"                  element={<Navigate to="/custom-bots" replace />} />
            {/* Deep-link target only (in-app notification metadata.url) — no nav entry */}
            <Route path="/dashboard/bots/:botId/lifecycle" element={<AppRoute><CustomBotLifecycle /></AppRoute>} />
            <Route path="/bot/:id"                  element={<AppRoute><BotSettings /></AppRoute>} />
            <Route path="/bot/:id/group/:groupId"            element={<AppRoute><KeyedGroupSettings /></AppRoute>} />
            <Route path="/bot/:id/group/:groupId/analytics"  element={<AppRoute><GroupAnalytics /></AppRoute>} />
            <Route path="/bot/:id/group/:groupId/crm"        element={<AppRoute><GroupCRM /></AppRoute>} />
            <Route path="/bot/:id/group/:groupId/campaigns"              element={<AppRoute><React.Suspense fallback={null}><CampaignWorkspace view="overview" /></React.Suspense></AppRoute>} />
            <Route path="/bot/:id/group/:groupId/campaigns/all"          element={<AppRoute><React.Suspense fallback={null}><CampaignWorkspace view="list" /></React.Suspense></AppRoute>} />
            <Route path="/bot/:id/group/:groupId/campaigns/review"       element={<AppRoute><React.Suspense fallback={null}><CampaignWorkspace view="review" /></React.Suspense></AppRoute>} />
            <Route path="/bot/:id/group/:groupId/campaigns/new"          element={<AppRoute><React.Suspense fallback={null}><CampaignWorkspace view="create" /></React.Suspense></AppRoute>} />
            <Route path="/bot/:id/group/:groupId/campaigns/:campaignId"  element={<AppRoute><React.Suspense fallback={null}><CampaignWorkspace view="detail" /></React.Suspense></AppRoute>} />

            {/* ── Referrals ─────────────────────────────────────────────────── */}
            <Route path="/referrals" element={<AppRoute><Referrals /></AppRoute>} />

            {/* ── Billing / Settings / Notifications ─────────────────────────── */}
            <Route path="/billing"  element={<AppRoute><Billing /></AppRoute>} />
            <Route path="/settings" element={<AppRoute><Settings /></AppRoute>} />
            <Route path="/notifications" element={<AppRoute><NotificationsPage /></AppRoute>} />

            {/* ── Admin ─────────────────────────────────────────────────────── */}
            {/* Console chooser: Telegizer vs Guildizer admin */}
            <Route path="/admin-hub" element={<AdminHub />} />
            <Route path="/admin" element={<AdminRoute><AdminPanel /></AdminRoute>} />
            <Route path="/admin/users/:userId" element={<AdminRoute><AdminUserDetail /></AdminRoute>} />
            <Route path="/admin/groups/:groupId" element={<AdminRoute><AdminGroupDetail /></AdminRoute>} />
            <Route path="/admin/custom-bots/:botId" element={<AdminRoute><AdminCustomBotDetail /></AdminRoute>} />
            {/* Category → section routing (sidebar-driven). Static detail routes above win by specificity. */}
            <Route path="/admin/:category/:tab" element={<AdminRoute><AdminPanel /></AdminRoute>} />

            {/* ── 404 ───────────────────────────────────────────────────────── */}
            <Route path="*" element={<NotFound />} />

          </Routes>
          </React.Suspense>
        </BrowserRouter>

        <ToastContainer
          position="top-center"
          autoClose={4000}
          theme="dark"
          hideProgressBar={false}
          newestOnTop
          closeOnClick
          pauseOnHover
          style={{ zIndex: 9999 }}
        />
        <ConnectionStatus />
        <PWAInstallBanner />
        <CookieConsent />
        <DebugPanel />
      </ErrorBoundary>
    </ThemeProvider>
  );
}

// Utility: redirect /my-groups → /groups, preserving query string (e.g. ?bot_type=official)
function RedirectMyGroups() {
  const { search } = useLocation();
  return <Navigate to={`/groups${search}`} replace />;
}

// Utility: redirect /my-groups/:groupId → /groups/:groupId (with optional suffix)
function RedirectGroupId({ prefix, suffix = '' }) {
  const { groupId } = useParams();
  return <Navigate to={`${prefix}/${groupId}${suffix}`} replace />;
}

