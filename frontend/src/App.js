import React, { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useParams } from 'react-router-dom';
import { Box, CircularProgress } from '@mui/material';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import { ToastContainer } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';
import ErrorBoundary from './components/ErrorBoundary';
import PWAInstallBanner from './components/PWAInstallBanner';
import AppLayout from './layouts/AppLayout';

// Pages — public
import Landing from './pages/Landing';
import Login from './pages/Login';
import Register from './pages/Register';
import Pricing from './pages/Pricing';
import PaymentSuccess from './pages/PaymentSuccess';
import Terms from './pages/Terms';
import Privacy from './pages/Privacy';
import NotFound from './pages/NotFound';
import VerifyEmail from './pages/VerifyEmail';
import ForgotPassword from './pages/ForgotPassword';
import ResetPassword from './pages/ResetPassword';

// Pages — authenticated (sidebar layout)
import Dashboard from './pages/Dashboard';
import MyGroups from './pages/MyGroups';
import GroupSettings from './pages/GroupSettings';
import GroupManagement from './pages/GroupManagement';
import OfficialGroupAnalytics from './pages/OfficialGroupAnalytics';
import OfficialAnalyticsOverview from './pages/OfficialAnalyticsOverview';
import MyBots from './pages/MyBots';
import BotSettings from './pages/BotSettings';
import GroupAnalytics from './pages/GroupAnalytics';
import Analytics from './pages/Analytics';
import Billing from './pages/Billing';
import Settings from './pages/Settings';
import AdminPanel from './pages/AdminPanel';

// Pages — new sections
import Channels from './pages/Channels';
import Workspace from './pages/Workspace';
import WorkspaceSmartLinks from './pages/WorkspaceSmartLinks';
import WorkspaceReminders from './pages/WorkspaceReminders';
import WorkspaceForwarding from './pages/WorkspaceForwarding';
import MiniApp from './pages/MiniApp';
import MiniAppLayout from './layouts/MiniAppLayout';
import Directory from './pages/Directory';
import JoinReferral from './pages/JoinReferral';

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

const darkTheme = createTheme({
  palette: {
    mode: 'dark',
    primary: { main: '#2563EB', light: '#60a5fa', dark: '#1d4ed8' },
    secondary: { main: '#7C3AED', light: '#a78bfa', dark: '#5b21b6' },
    info: { main: '#06B6D4' },
    background: {
      default: '#0f172a',
      paper: '#1e293b',
    },
    divider: '#334155',
  },
  typography: {
    fontFamily: "'Inter', -apple-system, sans-serif",
  },
  components: {
    MuiButton: {
      styleOverrides: { root: { textTransform: 'none', borderRadius: 8 } },
    },
    MuiCard: {
      styleOverrides: { root: { borderRadius: 12, border: '1px solid #334155' } },
    },
    MuiPaper: {
      styleOverrides: { root: { borderRadius: 12 } },
    },
  },
});


function _storedUser() {
  try { return JSON.parse(localStorage.getItem('user') || '{}'); } catch { return {}; }
}

// Requires auth + verified email + wraps in AppLayout (sidebar)
function AppRoute({ children }) {
  const token = localStorage.getItem('token');
  if (!token) return <Navigate to="/login" replace />;
  const user = _storedUser();
  if (user.email_verified === false) return <Navigate to="/verify-email" replace />;
  return <AppLayout>{children}</AppLayout>;
}

function PublicOnlyRoute({ children }) {
  const token = localStorage.getItem('token');
  if (!token) return children;
  const user = _storedUser();
  if (user.email_verified === false) return <Navigate to="/verify-email" replace />;
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
  if (status === 'denied') return <Navigate to="/dashboard" replace />;
  return <AppLayout>{children}</AppLayout>;
}

export default function App() {
  return (
    <ThemeProvider theme={darkTheme}>
      <CssBaseline />
      <ErrorBoundary>
        <BrowserRouter>
          <Routes>

            {/* ── Public (no sidebar) ─────────────────────────────────────── */}
            <Route path="/" element={<Landing />} />
            <Route path="/pricing" element={<Pricing />} />
            <Route path="/payment/success" element={<PaymentSuccess />} />
            <Route path="/terms" element={<Terms />} />
            <Route path="/privacy" element={<Privacy />} />
            <Route path="/join" element={<JoinReferral />} />

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
            <Route path="/groups/:groupId"                  element={<AppRoute><GroupSettings /></AppRoute>} />
            <Route path="/groups/:groupId/analytics"        element={<AppRoute><OfficialGroupAnalytics /></AppRoute>} />
            <Route path="/groups/:groupId/manage"           element={<AppRoute><GroupManagement /></AppRoute>} />

            {/* /my-groups/* → redirect to /groups/* (backward compat) */}
            <Route path="/my-groups"                        element={<Navigate to="/groups" replace />} />
            <Route path="/my-groups/:groupId"               element={<RedirectGroupId prefix="/groups" />} />
            <Route path="/my-groups/:groupId/analytics"     element={<RedirectGroupId prefix="/groups" suffix="/analytics" />} />
            <Route path="/add-group"                        element={<Navigate to="/groups" replace />} />

            {/* ── Channels ──────────────────────────────────────────────────── */}
            <Route path="/channels"    element={<AppRoute><Channels /></AppRoute>} />
            <Route path="/channels/*"  element={<AppRoute><Channels /></AppRoute>} />

            {/* ── Workspace ─────────────────────────────────────────────────── */}
            <Route path="/workspace"               element={<AppRoute><Workspace /></AppRoute>} />
            <Route path="/workspace/smart-links"   element={<AppRoute><WorkspaceSmartLinks /></AppRoute>} />
            <Route path="/workspace/reminders"     element={<AppRoute><WorkspaceReminders /></AppRoute>} />
            <Route path="/workspace/forwarding"    element={<AppRoute><WorkspaceForwarding /></AppRoute>} />
            <Route path="/workspace/automations"   element={<AppRoute><Workspace /></AppRoute>} />

            {/* ── Telegram Mini App ─────────────────────────────────────────── */}
            <Route path="/mini-app" element={<MiniAppLayout><MiniApp /></MiniAppLayout>} />
            <Route path="/mini-app/*" element={<MiniAppLayout><MiniApp /></MiniAppLayout>} />

            {/* ── Directory ─────────────────────────────────────────────────── */}
            <Route path="/directory"  element={<AppRoute><Directory /></AppRoute>} />
            <Route path="/directory/*" element={<AppRoute><Directory /></AppRoute>} />

            {/* ── Analytics ─────────────────────────────────────────────────── */}
            <Route path="/analytics"                element={<AppRoute><OfficialAnalyticsOverview /></AppRoute>} />
            <Route path="/analytics/:id"            element={<AppRoute><Analytics /></AppRoute>} />
            <Route path="/official-analytics"       element={<Navigate to="/analytics" replace />} />

            {/* ── Custom bots (canonical /custom-bots, keep /my-bots alias) ─── */}
            <Route path="/custom-bots"              element={<AppRoute><MyBots /></AppRoute>} />
            <Route path="/my-bots"                  element={<Navigate to="/custom-bots" replace />} />
            <Route path="/bot/:id"                  element={<AppRoute><BotSettings /></AppRoute>} />
            <Route path="/bot/:id/group/:groupId"            element={<AppRoute><GroupSettings /></AppRoute>} />
            <Route path="/bot/:id/group/:groupId/analytics"  element={<AppRoute><GroupAnalytics /></AppRoute>} />

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
      </ErrorBoundary>
    </ThemeProvider>
  );
}

// Utility: redirect /my-groups/:groupId → /groups/:groupId (with optional suffix)
function RedirectGroupId({ prefix, suffix = '' }) {
  const { groupId } = useParams();
  return <Navigate to={`${prefix}/${groupId}${suffix}`} replace />;
}
