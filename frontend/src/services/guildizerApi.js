// API client for the Guildizer (Discord) pillar.
//
// Guildizer runs as a SEPARATE backend (its own Railway service + Postgres), so
// these calls go to guild-api.telegizer.com — a subdomain of telegizer.com, which
// keeps the Discord-login session cookie first-party (no token juggling).
//
// Set REACT_APP_GUILDIZER_API_URL on the Telegizer Vercel project, e.g.
//   REACT_APP_GUILDIZER_API_URL=https://guild-api.telegizer.com
import axios from 'axios';

export const GUILDIZER_API_URL = process.env.REACT_APP_GUILDIZER_API_URL || '';

const guildizerApi = axios.create({
  baseURL: GUILDIZER_API_URL,
  withCredentials: true, // send/receive the Guildizer session cookie
  headers: { 'Content-Type': 'application/json' },
});

// Super-admin bridge: attach the Telegizer website token so the Guildizer admin
// panel can authorise off the existing email login (no separate Discord login).
// Harmless for non-admin endpoints — only admin_required reads this header.
guildizerApi.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) config.headers['X-Telegizer-Token'] = token;
  return config;
});

// Full-page redirect into Discord OAuth (must be top-level navigation).
export const guildizerLoginUrl = () => `${GUILDIZER_API_URL}/auth/discord/login`;

export async function guildizerLogout() {
  try {
    await guildizerApi.post('/auth/logout');
  } catch {
    /* ignore */
  }
}

export default guildizerApi;
