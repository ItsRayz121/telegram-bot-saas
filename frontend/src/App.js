import React, { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useSearchParams } from 'react-router-dom';
import { Box, CircularProgress } from '@mui/material';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import { ToastContainer } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';
import PWAInstallBanner from './components/PWAInstallBanner';

// Register service worker for PWA
if ('serviceWorker' in navigator && process.env.NODE_ENV === 'production') {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  });
}

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
import Terms from './pages/Terms';
import Privacy from './pages/Privacy';
import NotFound from './pages/NotFound';

const darkTheme = createTheme({
  palette: {
    mode: 'dark',
    primary: { main: '#2196f3' },
    secondary: { main: '#7c4dff' },
    background: {
      default: '#0d1117',
      paper: '#161b22',
    },
    divider: '#30363d',
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
        root: { borderRadius: 12, border: '1px solid #30363d' },
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

function PrivateRoute({ children }) {
  const token = localStorage.getItem('token');
  return token ? children : <Navigate to="/login" replace />;
}

// Redirect already-authenticated users away from auth pages
function PublicOnlyRoute({ children }) {
  const token = localStorage.getItem('token');
  return token ? <Navigate to="/dashboard" replace /> : children;
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

          {/* Protected */}
          <Route path="/dashboard" element={<PrivateRoute><Dashboard /></PrivateRoute>} />
          <Route path="/bot/:id" element={<PrivateRoute><BotSettings /></PrivateRoute>} />
          <Route path="/bot/:id/group/:groupId" element={<PrivateRoute><GroupSettings /></PrivateRoute>} />
          <Route path="/analytics/:id" element={<PrivateRoute><Analytics /></PrivateRoute>} />

          {/* Admin only */}
          <Route path="/admin" element={<AdminRoute><AdminPanel /></AdminRoute>} />

          {/* Billing — protected */}
          <Route path="/billing" element={<PrivateRoute><Billing /></PrivateRoute>} />

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
    </ThemeProvider>
  );
}
