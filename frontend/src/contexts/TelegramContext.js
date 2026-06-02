import React, { createContext, useContext, useEffect, useState, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import api from '../services/api';

// TMA-specific axios instance — uses in-memory Bearer token for Mini App API calls.
// After auth, token is also written to localStorage so the full dashboard session works.
const tmaApi = axios.create({
  baseURL: process.env.REACT_APP_API_URL || '',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});
let _tmaToken = null;
const setTmaToken = (token) => {
  _tmaToken = token;
};
tmaApi.interceptors.request.use((config) => {
  if (_tmaToken) config.headers['Authorization'] = `Bearer ${_tmaToken}`;
  return config;
});
export { tmaApi };

const TelegramContext = createContext(null);

// Extract MUI-compatible palette from Telegram themeParams
export function extractTgTheme(tg) {
  const p = tg?.themeParams || {};
  return {
    bgColor: p.bg_color || null,
    textColor: p.text_color || null,
    hintColor: p.hint_color || null,
    buttonColor: p.button_color || null,
    buttonTextColor: p.button_text_color || null,
    secondaryBgColor: p.secondary_bg_color || null,
  };
}

export function TelegramProvider({ children }) {
  const [tg, setTg] = useState(null);
  const [tgUser, setTgUser] = useState(null);
  const [appUser, setAppUser] = useState(null);
  const [groups, setGroups] = useState([]);
  const [tgTheme, setTgTheme] = useState(null);
  const [status, setStatus] = useState('loading'); // loading | ok | error | no_webapp | no_init_data
  const [authError, setAuthError] = useState(null);
  const [emailLinked, setEmailLinked] = useState(false);
  const [referralLink, setReferralLink] = useState(null);

  useEffect(() => {
    let cancelled = false;
    let attempts = 0;
    const MAX_ATTEMPTS = 25; // ~3.75s at 150ms — give the async SDK time to populate initData

    // TMA auth — backend sets httpOnly cookies; also store in localStorage so
    // AppRoute guard and the full dashboard recognise the session immediately.
    const doAuth = (webapp) => {
      api.post('/api/miniapp/auth', { init_data: webapp.initData })
        .then(res => {
          if (cancelled) return;
          const { token, user, groups: grps, email_linked, referral_link } = res.data;
          setTmaToken(token);
          localStorage.setItem('token', token);
          localStorage.setItem('user', JSON.stringify(user));
          setAppUser(user);
          setGroups(grps || []);
          setTgUser(webapp.initDataUnsafe?.user || null);
          setEmailLinked(email_linked ?? Boolean(user?.email));
          setReferralLink(referral_link || null);
          setStatus('ok');
        })
        .catch(err => {
          if (cancelled) return;
          const msg = err.response?.data?.error || null;
          setAuthError(msg);
          setStatus('error');
        });
    };

    const init = () => {
      if (cancelled) return;
      const webapp = window?.Telegram?.WebApp;

      // SDK / native bridge not ready yet. If we know we're inside Telegram (launch
      // hash captured in index.html), keep retrying briefly while the async SDK loads
      // — instead of falsely bailing to 'no_webapp'/'no_init_data' on the first tick.
      if (!webapp || !webapp.initData) {
        if (window.__IS_TELEGRAM__ && attempts < MAX_ATTEMPTS) {
          attempts += 1;
          setTimeout(init, 150);
          return;
        }
        setStatus(webapp ? 'no_init_data' : 'no_webapp');
        return;
      }

      webapp.ready();
      webapp.expand();
      // 2-G-01: match header/bg to Telegizer dark theme
      try { webapp.setHeaderColor('#0f172a'); } catch {}
      try { webapp.setBackgroundColor('#0f172a'); } catch {}
      setTg(webapp);
      setTgTheme(extractTgTheme(webapp));

      // Keep theme in sync if Telegram sends theme updates
      webapp.onEvent('themeChanged', () => setTgTheme(extractTgTheme(webapp)));

      doAuth(webapp);
    };

    init();
    return () => { cancelled = true; };
  }, []);

  const refetchUser = useCallback(() => {
    tmaApi.get('/api/miniapp/me')
      .then(res => {
        const { user, groups: grps, email_linked, referral_link } = res.data;
        setAppUser(user);
        setGroups(grps || []);
        setEmailLinked(email_linked ?? Boolean(user?.email));
        setReferralLink(referral_link || null);
      })
      .catch(() => {});
  }, []);

  const onEmailLinked = useCallback((newUser, newToken) => {
    if (newToken) {
      setTmaToken(newToken);
      localStorage.setItem('token', newToken);
    }
    if (newUser) {
      setAppUser(newUser);
      localStorage.setItem('user', JSON.stringify(newUser));
    }
    setEmailLinked(true);
  }, []);

  // Haptic feedback helpers — silently no-op when not in Telegram
  const haptic = useMemo(() => ({
    impact: (style = 'medium') => {
      try { tg?.HapticFeedback?.impactOccurred(style); } catch {}
    },
    notification: (type = 'success') => {
      try { tg?.HapticFeedback?.notificationOccurred(type); } catch {}
    },
    selection: () => {
      try { tg?.HapticFeedback?.selectionChanged(); } catch {}
    },
  }), [tg]);

  return (
    <TelegramContext.Provider value={{
      tg, tgUser, appUser, groups, tgTheme,
      status, authError,
      emailLinked, referralLink,
      refetchUser, onEmailLinked,
      haptic,
    }}>
      {children}
    </TelegramContext.Provider>
  );
}

export const useTelegram = () => useContext(TelegramContext);

/**
 * Show the Telegram BackButton for the lifetime of the component that calls this hook.
 * Pass a custom `onBack` handler, or leave undefined to call navigate(-1).
 */
export function useBackButton(onBack) {
  const { tg } = useTelegram();
  const navigate = useNavigate();

  useEffect(() => {
    const btn = tg?.BackButton;
    if (!btn) return;
    const handler = onBack || (() => navigate(-1));
    btn.show();
    btn.onClick(handler);
    return () => {
      btn.offClick(handler);
      btn.hide();
    };
  }, [tg, onBack, navigate]);
}
