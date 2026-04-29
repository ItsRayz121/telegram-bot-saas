import React, { createContext, useContext, useEffect, useState, useCallback, useMemo } from 'react';
import api from '../services/api';

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

  useEffect(() => {
    const webapp = window?.Telegram?.WebApp;
    if (!webapp) {
      setStatus('no_webapp');
      return;
    }

    webapp.ready();
    webapp.expand();
    setTg(webapp);
    setTgTheme(extractTgTheme(webapp));

    // Keep theme in sync if Telegram sends theme updates
    webapp.onEvent('themeChanged', () => setTgTheme(extractTgTheme(webapp)));

    const initData = webapp.initData;
    if (!initData) {
      setStatus('no_init_data');
      return;
    }

    api.post('/api/miniapp/auth', { init_data: initData })
      .then(res => {
        const { token, user, groups: grps } = res.data;
        localStorage.setItem('token', token);
        localStorage.setItem('user', JSON.stringify(user));
        setAppUser(user);
        setGroups(grps || []);
        setTgUser(webapp.initDataUnsafe?.user || null);
        setStatus('ok');
      })
      .catch(err => {
        const code = err.response?.data?.code;
        setStatus(code === 'NOT_LINKED' ? 'not_linked' : 'error');
      });
  }, []);

  const refetchGroups = useCallback(() => {
    api.get('/api/miniapp/me')
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
    <TelegramContext.Provider value={{ tg, tgUser, appUser, groups, tgTheme, status, refetchGroups, haptic }}>
      {children}
    </TelegramContext.Provider>
  );
}

export const useTelegram = () => useContext(TelegramContext);
