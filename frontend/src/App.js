import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import { ToastContainer } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';

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

function PrivateRoute({ children }) {
  const token = localStorage.getItem('token');
  return token ? children : <Navigate to="/login" replace />;
}

// Redirect already-authenticated users away from auth pages
function PublicOnlyRoute({ children }) {
  const token = localStorage.getItem('token');
  return token ? <Navigate to="/dashboard" replace /> : children;
}

// Admin-only route: requires both auth token and is_admin flag
function AdminRoute({ children }) {
  const token = localStorage.getItem('token');
  if (!token) return <Navigate to="/login" replace />;
  try {
    const user = JSON.parse(localStorage.getItem('user') || '{}');
    if (!user.is_admin) return <Navigate to="/dashboard" replace />;
  } catch {
    return <Navigate to="/dashboard" replace />;
  }
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
        position="bottom-right"
        autoClose={4000}
        theme="dark"
        hideProgressBar={false}
        newestOnTop
        closeOnClick
        pauseOnHover
      />
    </ThemeProvider>
  );
}
