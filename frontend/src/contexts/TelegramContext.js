import React, { createContext, useContext, useEffect, useState } from 'react';
import api from '../services/api';

const TelegramContext = createContext(null);

export function TelegramProvider({ children }) {
  const [tg, setTg] = useState(null);          // window.Telegram.WebApp
  const [tgUser, setTgUser] = useState(null);   // Telegram user from initData
  const [appUser, setAppUser] = useState(null); // Telegizer User
  const [groups, setGroups] = useState([]);
  const [status, setStatus] = useState('loading'); // loading | ok | not_linked | error

  useEffect(() => {
    const webapp = window?.Telegram?.WebApp;
    if (!webapp) {
      setStatus('no_webapp');
      return;
    }

    webapp.ready();
    webapp.expand();
    setTg(webapp);

    const initData = webapp.initData;
    if (!initData) {
      setStatus('no_init_data');
      return;
    }

    // Auth against our backend
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

  const refetchGroups = () => {
    api.get('/api/miniapp/me')
      .then(res => {
        setAppUser(res.data.user);
        setGroups(res.data.groups || []);
      })
      .catch(() => {});
  };

  return (
    <TelegramContext.Provider value={{ tg, tgUser, appUser, groups, status, refetchGroups }}>
      {children}
    </TelegramContext.Provider>
  );
}

export const useTelegram = () => useContext(TelegramContext);
