import React, { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useSearchParams } from 'react-router-dom';
import { Box, CircularProgress } from '@mui/material';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import { ToastContainer } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';
import ErrorBoundary from './components/ErrorBoundary';
import PWAInstallBanner from './components/PWAInstallBanner';
import Landing from './pages/Landing';
import Login from './pages/Login';
import Register from './pages/Register';
import Dashboard from './pages/Dashboard';
import BotSettings from './pages/BotSettings';
import GroupSettings from './pages/GroupSettings';
import Pricing from './pages/Pricing';
import Analytics from './pages/Analytics';
import AdminPanel from './pages/AdminPanel';
import ForgotPassword from './pages/ForgotPassword';
import ResetPassword from './pages/ResetPassword';
import PaymentSuccess from './pages/PaymentSuccess';
import Billing from './pages/Billing';
import Settings from './pages/Settings';
import Terms from './pages/Terms';
import Privacy from './pages/Privacy';
import NotFound from './pages/NotFound';
import VerifyEmail from './pages/VerifyEmail';
import MyGroups from './pages/MyGroups';
import GroupManagement from './pages/GroupManagement';
import MyBots from './pages/MyBots';

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

// Register service worker for PWA (must be after imports to satisfy ESLint import/first)
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
      styleOverrides: {
        root: { textTransform: 'none', borderRadius: 8 },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: { borderRadius: 12, border: '1px solid #334155' },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: { borderRadius: 12 },
      },
    },
  },
});

function JoinRedirect() {
  const [searchParams] = useSearchParams();
  const ref = searchParams.get('ref') || '';
  return <Navigate to={`/register${ref ? `?ref=${ref}` : ''}`} replace />;
}

// Read stored user object from localStorage (never trust for security, only for routing UX).
function _storedUser() {
  try { return JSON.parse(localStorage.getItem('user') || '{}'); } catch { return {}; }
}

// Requires auth + verified email. Unauth → /login. Auth but unverified → /verify-email.
// Synchronous localStorage read means no flash-of-content before redirect.
function VerifiedRoute({ children }) {
  const token = localStorage.getItem('token');
  if (!token) return <Navigate to="/login" replace />;
  const user = _storedUser();
  if (user.email_verified === false) return <Navigate to="/verify-email" replace />;
  return children;
}

// Redirect already-authenticated users away from auth pages.
// Unverified logged-in users go to /verify-email, not /dashboard.
function PublicOnlyRoute({ children }) {
  const token = localStorage.getItem('token');
  if (!token) return children;
  const user = _storedUser();
  if (user.email_verified === false) return <Navigate to="/verify-email" replace />;
  return <Navigate to="/dashboard" replace />;
}

// Admin-only route: validates is_admin from backend on each mount — never trusts localStorage
function AdminRoute({ children }) {
  const [status, setStatus] = useState('loading'); // loading | allowed | denied

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) { setStatus('denied'); return; }
    const base = process.env.REACT_APP_API_URL || '';
    fetch(`${base}/api/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then((data) => setStatus(data.user?.is_admin ? 'allowed' : 'denied'))
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
  return children;
}

export default function App() {
  return (
    <ThemeProvider theme={darkTheme}>
      <CssBaseline />
      <ErrorBoundary>
        <BrowserRouter>
          <Routes>
            {/* Public */}
            <Route path="/" element={<Landing />} />
            <Route path="/pricing" element={<Pricing />} />
            <Route path="/payment/success" element={<PaymentSuccess />} />
            <Route path="/terms" element={<Terms />} />
            <Route path="/privacy" element={<Privacy />} />
            {/* Referral short-link: /join?ref=CODE → /register?ref=CODE */}
            <Route path="/join" element={<JoinRedirect />} />

            {/* Auth pages — redirect to dashboard if already logged in */}
            <Route path="/login" element={<PublicOnlyRoute><Login /></PublicOnlyRoute>} />
            <Route path="/register" element={<PublicOnlyRoute><Register /></PublicOnlyRoute>} />
            <Route path="/forgot-password" element={<ForgotPassword />} />
            <Route path="/reset-password" element={<ResetPassword />} />

            {/* Email verification — accessible with or without auth */}
            <Route path="/verify-email" element={<VerifyEmail />} />

            {/* Protected — requires auth AND verified email */}
            <Route path="/dashboard" element={<VerifiedRoute><Dashboard /></VerifiedRoute>} />
            <Route path="/bot/:id" element={<VerifiedRoute><BotSettings /></VerifiedRoute>} />
            <Route path="/bot/:id/group/:groupId" element={<VerifiedRoute><GroupSettings /></VerifiedRoute>} />
            <Route path="/analytics/:id" element={<VerifiedRoute><Analytics /></VerifiedRoute>} />

            {/* Official bot ecosystem */}
            <Route path="/my-groups" element={<VerifiedRoute><MyGroups /></VerifiedRoute>} />
            <Route path="/my-groups/:groupId" element={<VerifiedRoute><GroupManagement /></VerifiedRoute>} />
            <Route path="/add-group" element={<VerifiedRoute><MyGroups /></VerifiedRoute>} />
            <Route path="/my-bots" element={<VerifiedRoute><MyBots /></VerifiedRoute>} />

            {/* Admin only */}
            <Route path="/admin" element={<AdminRoute><AdminPanel /></AdminRoute>} />

            {/* Billing — protected */}
            <Route path="/billing" element={<VerifiedRoute><Billing /></VerifiedRoute>} />

            {/* Settings — protected */}
            <Route path="/settings" element={<VerifiedRoute><Settings /></VerifiedRoute>} />

            {/* 404 */}
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
