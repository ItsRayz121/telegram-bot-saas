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

// Notification + Web Push client for the Guildizer pillar. Shape matches the
// Telegizer `notifications` client so shared helpers (utils/push.js,
// NotificationBell) can be reused with either backend.
export const guildizerNotifications = {
  list: (params) => guildizerApi.get('/api/notifications/history', { params }),
  unreadCount: () => guildizerApi.get('/api/notifications/unread-count'),
  // GZ marks all read in one call (no per-id endpoint); markRead/markAllRead
  // both hit the same route so the shared bell component works unchanged.
  markRead: () => guildizerApi.post('/api/notifications/read'),
  markAllRead: () => guildizerApi.post('/api/notifications/read'),
  getPreferences: () => guildizerApi.get('/api/notifications/preferences'),
  updatePreferences: (data) => guildizerApi.put('/api/notifications/preferences', data),
  vapidKey: () => guildizerApi.get('/api/notifications/vapid-public-key'),
  subscribePush: (subscription) => guildizerApi.post('/api/notifications/subscribe', subscription),
  unsubscribePush: (data) => guildizerApi.post('/api/notifications/unsubscribe', data || {}),
  // Top-of-app announcement banner (show once, dismissible)
  getBanner: () => guildizerApi.get('/api/notifications/banner'),
  dismissBanner: (id) => guildizerApi.post(`/api/notifications/banner/${id}/dismiss`),
};

// Per-user UI preferences (open/closed state of collapsible settings cards).
export const guildizerUiPrefs = {
  get: () => guildizerApi.get('/api/ui-prefs'),
  update: (data) => guildizerApi.put('/api/ui-prefs', data),
};

// Account-level bring-your-own twitterapi.io key for X raid auto-verify.
// Account-scoped (one key covers every guild the user manages).
export const guildizerXVerifyKey = {
  get: () => guildizerApi.get('/api/account/x-verify-key'),
  save: (apiKey) => guildizerApi.post('/api/account/x-verify-key', { api_key: apiKey }),
  delete: () => guildizerApi.delete('/api/account/x-verify-key'),
};

// Engagement campaigns. Mirrors the Telegizer `engagement` client so
// CampaignsTab reads 1:1 against CampaignManager (guildId ↔ botId+groupId).
const camp = (guildId, cid) =>
  `/api/guilds/${guildId}/campaigns${cid != null ? `/${cid}` : ''}`;

export const guildizerEngagement = {
  list: (guildId) => guildizerApi.get(camp(guildId)),
  create: (guildId, body) => guildizerApi.post(camp(guildId), body),
  get: (guildId, cid) => guildizerApi.get(camp(guildId, cid)),
  update: (guildId, cid, body) => guildizerApi.put(camp(guildId, cid), body),
  remove: (guildId, cid) => guildizerApi.delete(camp(guildId, cid)),
  post: (guildId, cid) => guildizerApi.post(`${camp(guildId, cid)}/post`),
  deletePost: (guildId, cid) => guildizerApi.delete(`${camp(guildId, cid)}/post`),
  listSubmissions: (guildId, cid, params) =>
    guildizerApi.get(`${camp(guildId, cid)}/submissions`, { params }),
  reviewSubmission: (guildId, cid, sid, body) =>
    guildizerApi.post(`${camp(guildId, cid)}/submissions/${sid}/review`, body),
  leaderboard: (guildId, cid) => guildizerApi.get(`${camp(guildId, cid)}/leaderboard`),
};

export default guildizerApi;
