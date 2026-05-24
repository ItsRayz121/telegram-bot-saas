import React, { createContext, useContext, useEffect, useState, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import api from '../services/api';

// 2-G-01: TMA-specific axios instance — uses in-memory Bearer token, never localStorage.
// Token is injected via setTmaToken() after successful miniapp auth.
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
  const [status, setStatus] = useState('loading'); // loading | ok | not_linked | error | no_webapp | no_init_data
  const [authError, setAuthError] = useState(null);

  useEffect(() => {
    const webapp = window?.Telegram?.WebApp;
    if (!webapp) {
      setStatus('no_webapp');
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

    const initData = webapp.initData;
    if (!initData) {
      setStatus('no_init_data');
      return;
    }

    // 2-G-02: TMA auth — token stored in memory only, never localStorage
    api.post('/api/miniapp/auth', { init_data: initData })
      .then(res => {
        const { token, user, groups: grps } = res.data;
        setTmaToken(token);   // in-memory only
        setAppUser(user);
        setGroups(grps || []);
        setTgUser(webapp.initDataUnsafe?.user || null);
        setStatus('ok');
      })
      .catch(err => {
        const code = err.response?.data?.code;
        const msg  = err.response?.data?.error || null;
        if (code === 'NOT_LINKED') {
          setStatus('not_linked');
        } else {
          setAuthError(msg);
          setStatus('error');
        }
      });
  }, []);

  const refetchGroups = useCallback(() => {
    tmaApi.get('/api/miniapp/me')
      .then(res => {
        setAppUser(res.data.user);
        setGroups(res.data.groups || []);
      })
      .catch(() => {});
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
    <TelegramContext.Provider value={{ tg, tgUser, appUser, groups, tgTheme, status, authError, refetchGroups, haptic }}>
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
