import React, { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useParams, useLocation } from 'react-router-dom';
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
import { API_CONFIG_ERROR } from './services/api';

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

// Pages — new sections
import Channels from './pages/Channels';
import ChannelDetail from './pages/ChannelDetail';
import Workspace from './pages/Workspace';
import WorkspaceSmartLinks from './pages/WorkspaceSmartLinks';
import WorkspaceReminders from './pages/WorkspaceReminders';
import WorkspaceForwarding from './pages/WorkspaceForwarding';
import WorkspaceAutomations from './pages/WorkspaceAutomations';
import AutomationHub from './pages/AutomationHub';
import Integrations from './pages/Integrations';
import MiniApp from './pages/MiniApp';
import MiniAppLayout from './layouts/MiniAppLayout';
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

function PublicOnlyRoute({ children }) {
  // If opened inside Telegram Mini App (any URL), always use TMA auth — never show email forms
  if (window?.Telegram?.WebApp?.initData) {
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

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) { setStatus('denied'); return; }
    const base = process.env.REACT_APP_API_URL || '';
    fetch(`${base}/api/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.json())
      .then(data => setStatus(data.user?.is_admin ? 'allowed' : 'denied'))
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
  return <AppLayout>{children}</AppLayout>;
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
          <Routes>

            {/* ── Public (no sidebar) ─────────────────────────────────────── */}
            <Route path="/" element={<Landing />} />
            <Route path="/pricing" element={<Pricing />} />
            <Route path="/payment/success" element={<PaymentSuccess />} />
            <Route path="/terms" element={<Terms />} />
            <Route path="/privacy" element={<Privacy />} />
            <Route path="/acceptable-use" element={<AcceptableUse />} />
            <Route path="/contact" element={<Contact />} />
            <Route path="/about" element={<About />} />
            <Route path="/status" element={<Status />} />
            <Route path="/join" element={<JoinReferral />} />
            <Route path="/invite/:code" element={<InviteLanding />} />
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

            {/* ── Workspace ─────────────────────────────────────────────────── */}
            <Route path="/workspace"               element={<AppRoute><Workspace /></AppRoute>} />
            <Route path="/workspace/smart-links"   element={<AppRoute><WorkspaceSmartLinks /></AppRoute>} />
            <Route path="/workspace/reminders"     element={<AppRoute><WorkspaceReminders /></AppRoute>} />
            <Route path="/automation"              element={<AppRoute><AutomationHub /></AppRoute>} />
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
            <Route path="/admin" element={<AdminRoute><AdminPanel /></AdminRoute>} />

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

