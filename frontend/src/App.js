import React, { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, Outlet, useParams, useLocation } from 'react-router-dom';
import { trackGAPageView } from './index';
import { Box, CircularProgress, Typography, Button } from '@mui/material';
import { ThemeProvider } from '@mui/material/styles';
import telegizer from './theme';
import CssBaseline from '@mui/material/CssBaseline';
import { ToastContainer } from 'react-toastify';
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
import Pricing from './pages/Pricing';
import PaymentSuccess from './pages/PaymentSuccess';
import Terms from './pages/Terms';
import Privacy from './pages/Privacy';
import AcceptableUse from './pages/AcceptableUse';
import Contact from './pages/Contact';
import About from './pages/About';
import NotFound from './pages/NotFound';
import Status from './pages/Status';
import VerifyEmail from './pages/VerifyEmail';
import ForgotPassword from './pages/ForgotPassword';
import ResetPassword from './pages/ResetPassword';

// Pages — authenticated (sidebar layout)
import Dashboard from './pages/Dashboard';
import MyGroups from './pages/MyGroups';
import GroupSettings from './pages/GroupSettings';
import GroupManagement from './pages/GroupManagement';
import OfficialGroupAnalytics from './pages/OfficialGroupAnalytics';
import MyBots from './pages/MyBots';
import BotSettings from './pages/BotSettings';
import GroupAnalytics from './pages/GroupAnalytics';
import Analytics from './pages/Analytics';
import Billing from './pages/Billing';
import Settings from './pages/Settings';
import AdminPanel from './pages/AdminPanel';
import AdminUserDetail from './pages/AdminUserDetail';
import AdminGroupDetail from './pages/AdminGroupDetail';
import AdminCustomBotDetail from './pages/AdminCustomBotDetail';

// Pages — new sections
import Channels from './pages/Channels';
import ChannelDetail from './pages/ChannelDetail';
import Workspace from './pages/Workspace';
import WorkspaceSmartLinks from './pages/WorkspaceSmartLinks';
import WorkspaceReminders from './pages/WorkspaceReminders';
import WorkspaceForwarding from './pages/WorkspaceForwarding';
import WorkspaceAutomations from './pages/WorkspaceAutomations';
import Integrations from './pages/Integrations';
import MiniApp from './pages/MiniApp';
import MiniAppLayout from './layouts/MiniAppLayout';
import CampaignTask from './pages/CampaignTask';
import MyTasks from './pages/MyTasks';
import Directory from './pages/Directory';
import DirectorySubmit from './pages/DirectorySubmit';
import GroupCRM from './pages/GroupCRM';
import Marketplace from './pages/Marketplace';
import MarketplaceDeal from './pages/MarketplaceDeal';
import JoinReferral from './pages/JoinReferral';
import InviteLanding from './pages/InviteLanding';
import TeamInvitePage from './pages/TeamInvitePage';
import Referrals from './pages/Referrals';

// Echo (AI Assistant)
import HubLanding from './pages/HubLanding';
import HubWorkspace from './pages/HubWorkspace';
import HubCustomBotWorkspace from './pages/HubCustomBotWorkspace';

// Discord pillar (Guildizer) — separate backend, embedded UI
import GuildizerServers from './pages/guildizer/GuildizerServers';
import GuildizerManageServers from './pages/guildizer/GuildizerManageServers';
import GuildizerServerDetail from './pages/guildizer/GuildizerServerDetail';
import GuildizerBots from './pages/guildizer/GuildizerBots';
import GuildizerAdminLayout from './layouts/GuildizerAdminLayout';
import GuildizerAdminPanel from './pages/guildizer/admin/GuildizerAdminPanel';
import GuildizerAdminUserDetail from './pages/guildizer/admin/GuildizerAdminUserDetail';
import GuildizerAdminServerDetail from './pages/guildizer/admin/GuildizerAdminServerDetail';
import GuildizerAdminCustomBotDetail from './pages/guildizer/admin/GuildizerAdminCustomBotDetail';
import GuildizerAdminCampaignDetail from './pages/guildizer/admin/GuildizerAdminCampaignDetail';
import AdminHub from './pages/AdminHub';

// Pages — lazy loaded
const AssistantNotes = React.lazy(() => import('./pages/AssistantNotes'));
const AssistantBotSettings = React.lazy(() => import('./pages/AssistantBotSettings'));
const AssistantDigests = React.lazy(() => import('./pages/AssistantDigests'));
const AssistantAISettings = React.lazy(() => import('./pages/AssistantAISettings'));
const AssistantTasks = React.lazy(() => import('./pages/AssistantTasks'));
const AssistantKnowledge = React.lazy(() => import('./pages/AssistantKnowledge'));
const AssistantMemory = React.lazy(() => import('./pages/AssistantMemory'));
const AssistantMeetingLinks = React.lazy(() => import('./pages/AssistantMeetingLinks'));
const AnalyticsHub = React.lazy(() => import('./pages/AnalyticsHub'));
const WorkflowBuilder = React.lazy(() => import('./pages/WorkflowBuilder'));

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

export default function App() {
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
          <Routes>

            {/* ── Public (no sidebar) ─────────────────────────────────────── */}
            {/* Root + referral/invite entry pages: redirect to /mini-app when opened inside Telegram */}
            <Route path="/" element={<TelegramAware><Landing /></TelegramAware>} />
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
            <Route path="/team/join/:token" element={<TeamInvitePage />} />

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
            <Route path="/bot/:id"                  element={<AppRoute><BotSettings /></AppRoute>} />
            <Route path="/bot/:id/group/:groupId"            element={<AppRoute><KeyedGroupSettings /></AppRoute>} />
            <Route path="/bot/:id/group/:groupId/analytics"  element={<AppRoute><GroupAnalytics /></AppRoute>} />
            <Route path="/bot/:id/group/:groupId/crm"        element={<AppRoute><GroupCRM /></AppRoute>} />

            {/* ── Referrals ─────────────────────────────────────────────────── */}
            <Route path="/referrals" element={<AppRoute><Referrals /></AppRoute>} />

            {/* ── Billing / Settings ─────────────────────────────────────────── */}
            <Route path="/billing"  element={<AppRoute><Billing /></AppRoute>} />
            <Route path="/settings" element={<AppRoute><Settings /></AppRoute>} />

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

