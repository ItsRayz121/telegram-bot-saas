import axios from 'axios';

export const API_CONFIG_ERROR =
  !process.env.REACT_APP_API_URL && process.env.NODE_ENV === 'production'
    ? 'REACT_APP_API_URL is not set. All API calls will fail. Contact support or check Vercel environment variables.'
    : null;

if (API_CONFIG_ERROR) {
  console.error('[api]', API_CONFIG_ERROR);
}

const BASE_URL = process.env.REACT_APP_API_URL || '';

// 1-D-01: cookies carry JWT — send credentials on every request
const api = axios.create({
  baseURL: BASE_URL,
  timeout: 30000,
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
});

// 1-D-02: attach CSRF token from cookie to every state-changing request
api.interceptors.request.use((config) => {
  const csrfToken = document.cookie.match(/csrf_token=([^;]+)/)?.[1];
  if (csrfToken) config.headers['X-CSRF-Token'] = csrfToken;
  return config;
});

let _isRefreshing = false;
let _failedQueue = [];

const _processQueue = (error) => {
  _failedQueue.forEach((p) => (error ? p.reject(error) : p.resolve()));
  _failedQueue = [];
};

const _clearSession = () => {
  // cookies are cleared by the server on logout; just purge any legacy localStorage state
  localStorage.removeItem('token');
  localStorage.removeItem('refresh_token');
  localStorage.removeItem('user');
  window.location.href = '/login';
};

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;

    // Hard redirect if backend rejects due to unverified email
    if (error.response?.status === 403 && error.response?.data?.code === 'EMAIL_NOT_VERIFIED') {
      window.location.href = '/verify-email';
      return Promise.reject(error);
    }

    // On 401, try silent token refresh using the refresh cookie (set automatically by browser)
    const isAuthEndpoint = original.url?.includes('/api/auth/');
    if (error.response?.status === 401 && !original._retry && !isAuthEndpoint) {
      if (_isRefreshing) {
        return new Promise((resolve, reject) => {
          _failedQueue.push({ resolve, reject });
        }).then(() => api(original));
      }

      original._retry = true;
      _isRefreshing = true;

      try {
        // Refresh cookie is scoped to /api/auth/refresh — browser sends it automatically
        await axios.post(`${BASE_URL}/api/auth/refresh`, {}, { withCredentials: true });
        _processQueue(null);
        return api(original);
      } catch (refreshErr) {
        _processQueue(refreshErr);
        _clearSession();
        return Promise.reject(refreshErr);
      } finally {
        _isRefreshing = false;
      }
    }

    if (error.response?.status === 401 && isAuthEndpoint) {
      _clearSession();
    }

    // Capture 5xx errors in Sentry
    if (error.response?.status >= 500) {
      try {
        import('@sentry/react').then(({ captureException }) => captureException(error)).catch(() => {});
      } catch {}
    }

    return Promise.reject(error);
  }
);

export const auth = {
  register: (data) => api.post('/api/auth/register', data),
  login: (data) => api.post('/api/auth/login', data),
  refresh: () => api.post('/api/auth/refresh'),
  getMe: () => api.get('/api/auth/me'),
  logout: () => api.post('/api/auth/logout'),
  changePassword: (data) => api.post('/api/auth/change-password', data),
  forgotPassword: (data) => api.post('/api/auth/forgot-password', data),
  resetPassword: (data) => api.post('/api/auth/reset-password', data),
  // Email verification
  verifyEmail: (data) => api.post('/api/auth/verify-email', data),
  resendVerification: () => api.post('/api/auth/resend-verification'),
  // 2FA login completion
  verifyTotpLogin: (data) => api.post('/api/auth/verify-totp-login', data),
  // Onboarding step tracking (2-B-01)
  markOnboardingStep: (step) => api.patch('/api/auth/onboarding', { step }),
};

export const totp = {
  setup: () => api.post('/api/auth/2fa/setup'),
  enable: (data) => api.post('/api/auth/2fa/enable', data),
  disable: (data) => api.post('/api/auth/2fa/disable', data),
  getBackupCodeCount: () => api.get('/api/auth/2fa/backup-codes'),
  regenerateBackupCodes: (data) => api.post('/api/auth/2fa/regenerate-backup-codes', data),
};

export const notifications = {
  list: (params) => api.get('/api/notifications', { params }),
  unreadCount: () => api.get('/api/notifications/unread-count'),
  markRead: (id) => api.post(`/api/notifications/${id}/read`),
  markAllRead: () => api.post('/api/notifications/read-all'),
};

export const bots = {
  getAll: () => api.get('/api/bots'),
  create: (data) => api.post('/api/bots', data),
  get: (id) => api.get(`/api/bots/${id}`),
  delete: (id) => api.delete(`/api/bots/${id}`),
  getGroups: (id) => api.get(`/api/bots/${id}/groups`),
  disconnectGroup: (botId, groupId) => api.delete(`/api/bots/${botId}/groups/${groupId}`),
  toggle: (id) => api.post(`/api/bots/${id}/toggle`),
  getStatus: (id) => api.get(`/api/bots/${id}/status`),
};

// Normalise official-group mod-log event_type → action_type used by the Audit Log UI
const _modTypeMap = (t) => ({
  mod_warn: 'warn', mod_warning: 'warn',
  mod_ban: 'ban', mod_kick: 'kick',
  mod_mute: 'mute', mod_unmute: 'unmute',
  mod_tempban: 'tempban', mod_tempmute: 'tempmute',
  mod_purge: 'purge', automod_action: 'purge',
}[t] || t);

export const settings = {
  getGroupSettings: (botId, groupId) =>
    botId === 'official'
      ? api.get(`/api/official-groups/${groupId}/settings`)
      : api.get(`/api/bots/${botId}/groups/${groupId}/settings`),
  updateGroupSettings: (botId, groupId, data) =>
    botId === 'official'
      ? api.put(`/api/official-groups/${groupId}/settings`, data)
      : api.put(`/api/bots/${botId}/groups/${groupId}/settings`, data),

  // Official groups: real OfficialMember directory with pagination/search/filters
  getMembers: (botId, groupId, params) =>
    botId === 'official'
      ? api.get(`/api/telegram-groups/${groupId}/members`, { params })
      : api.get(`/api/bots/${botId}/groups/${groupId}/members`, { params }),

  // Official groups: use mod-log and normalise to the audit-log shape the UI expects
  getAuditLogs: (botId, groupId, params) =>
    botId === 'official'
      ? api.get(`/api/telegram-groups/${groupId}/mod-log`, { params }).then(r => ({
          data: {
            logs: (r.data.events || []).map(e => ({
              id: e.id,
              action_type: _modTypeMap(e.event_type),
              target_username: e.metadata?.target_username || e.metadata?.target_user_id || '',
              target_user_id: e.metadata?.target_user_id || '',
              moderator_username: e.metadata?.moderator_username || e.metadata?.moderator_id || '',
              moderator_id: e.metadata?.moderator_id || '',
              reason: e.metadata?.reason || e.message || '',
              timestamp: e.created_at,
            })),
            total: r.data.total,
            pages: r.data.pages,
            page: r.data.page,
          },
        }))
      : api.get(`/api/bots/${botId}/groups/${groupId}/audit-logs`, { params }),

  // Leaderboard: official reads OfficialMember, custom reads Member table
  getLeaderboard: (botId, groupId, params) =>
    botId === 'official'
      ? api.get(`/api/telegram-groups/${groupId}/leaderboard`, { params })
      : api.get(`/api/bots/${botId}/groups/${groupId}/leaderboard`, { params }),

  // Warnings: official reads OfficialWarning, custom reads AuditLog warn entries
  listWarnings: (botId, groupId, params) =>
    botId === 'official'
      ? api.get(`/api/telegram-groups/${groupId}/warnings`, { params })
      : api.get(`/api/bots/${botId}/groups/${groupId}/warnings`, { params }),

  removeWarning: (botId, groupId, warningId) =>
    botId === 'official'
      ? api.delete(`/api/telegram-groups/${groupId}/warnings/${warningId}`)
      : Promise.resolve({ data: { message: 'ok' } }), // custom bot warnings are AuditLog entries — no delete needed

  // Official groups: real scheduled-messages endpoints
  getScheduledMessages: (botId, groupId) =>
    botId === 'official'
      ? api.get(`/api/telegram-groups/${groupId}/scheduled-messages`)
      : api.get(`/api/bots/${botId}/groups/${groupId}/scheduled-messages`),
  createScheduledMessage: (botId, groupId, data) =>
    botId === 'official'
      ? api.post(`/api/telegram-groups/${groupId}/scheduled-messages`, data)
      : api.post(`/api/bots/${botId}/groups/${groupId}/scheduled-messages`, data),
  deleteScheduledMessage: (botId, groupId, msgId) =>
    botId === 'official'
      ? api.delete(`/api/telegram-groups/${groupId}/scheduled-messages/${msgId}`)
      : api.delete(`/api/bots/${botId}/groups/${groupId}/scheduled-messages/${msgId}`),

  // Raids — official groups now have a real endpoint
  createRaid: (botId, groupId, data) =>
    botId === 'official'
      ? api.post(`/api/telegram-groups/${groupId}/raids`, data)
      : api.post(`/api/bots/${botId}/groups/${groupId}/raids`, data),

  // Official groups: real auto-response endpoints
  getAutoResponses: (botId, groupId) =>
    botId === 'official'
      ? api.get(`/api/telegram-groups/${groupId}/auto-responses`)
      : api.get(`/api/bots/${botId}/groups/${groupId}/auto-responses`),
  createAutoResponse: (botId, groupId, data) =>
    botId === 'official'
      ? api.post(`/api/telegram-groups/${groupId}/auto-responses`, data)
      : api.post(`/api/bots/${botId}/groups/${groupId}/auto-responses`, data),
  updateAutoResponse: (botId, groupId, arId, data) =>
    botId === 'official'
      ? api.put(`/api/telegram-groups/${groupId}/auto-responses/${arId}`, data)
      : api.put(`/api/bots/${botId}/groups/${groupId}/auto-responses/${arId}`, data),
  deleteAutoResponse: (botId, groupId, arId) =>
    botId === 'official'
      ? api.delete(`/api/telegram-groups/${groupId}/auto-responses/${arId}`)
      : api.delete(`/api/bots/${botId}/groups/${groupId}/auto-responses/${arId}`),

  // Reports — official groups now have real endpoints
  getReports: (botId, groupId, params) =>
    botId === 'official'
      ? api.get(`/api/telegram-groups/${groupId}/reports`, { params })
      : api.get(`/api/bots/${botId}/groups/${groupId}/reports`, { params }),
  resolveReport: (botId, groupId, reportId) =>
    botId === 'official'
      ? api.post(`/api/telegram-groups/${groupId}/reports/${reportId}/resolve`)
      : api.post(`/api/bots/${botId}/groups/${groupId}/reports/${reportId}/resolve`),

  getGroupAdmins: (botId, groupId) =>
    botId === 'official'
      ? api.get(`/api/official-groups/${groupId}/admins`)
      : api.get(`/api/bots/${botId}/groups/${groupId}/admins`),
  getBotPermissions: (groupId) =>
    api.get(`/api/official-groups/${groupId}/permissions`),

  getCommandRouting: (botId, groupId) =>
    api.get(`/api/official-groups/${groupId}/command-routing`),
  updateCommandRouting: (botId, groupId, data) =>
    api.put(`/api/official-groups/${groupId}/command-routing`, data),
  refreshForumTopics: (botId, groupId) =>
    api.post(`/api/official-groups/${groupId}/command-routing/refresh-topics`),
  getCustomCommandRouting: (botId, groupId) =>
    api.get(`/api/bots/${botId}/groups/${groupId}/command-routing`),
  updateCustomCommandRouting: (botId, groupId, data) =>
    api.put(`/api/bots/${botId}/groups/${groupId}/command-routing`, data),
};

// Official groups: real knowledge-base endpoints via /api/telegram-groups
export const knowledge = {
  list: (botId, groupId) =>
    botId === 'official'
      ? api.get(`/api/telegram-groups/${groupId}/knowledge`)
      : api.get(`/api/bots/${botId}/groups/${groupId}/knowledge`),
  upload: (botId, groupId, formData) =>
    botId === 'official'
      ? api.post(`/api/telegram-groups/${groupId}/knowledge`, formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
        })
      : api.post(`/api/bots/${botId}/groups/${groupId}/knowledge`, formData, {
          headers: { 'Content-Type': undefined },
        }),
  /**
   * Upload with real progress events.
   * onProgress(pct: number, stage: string) called as upload proceeds.
   * Returns a Promise resolving to the parsed JSON response.
   */
  uploadWithProgress: (botId, groupId, formData, onProgress) => {
    const url = botId === 'official'
      ? `${BASE_URL}/api/telegram-groups/${groupId}/knowledge`
      : `${BASE_URL}/api/bots/${botId}/groups/${groupId}/knowledge`;

    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', url, true);
      xhr.withCredentials = true;

      const csrfToken = document.cookie.match(/csrf_token=([^;]+)/)?.[1];
      if (csrfToken) xhr.setRequestHeader('X-CSRF-Token', csrfToken);

      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          // Map upload bytes to 0–90% of the bar; 90–100% is server-side processing
          const pct = Math.round((e.loaded / e.total) * 90);
          onProgress?.(pct, pct < 90 ? 'Uploading…' : 'Processing…');
        }
      };

      xhr.onload = () => {
        let json;
        try { json = JSON.parse(xhr.responseText); } catch { json = {}; }
        if (xhr.status >= 200 && xhr.status < 300) {
          onProgress?.(100, 'Indexed ✓');
          resolve({ data: json, status: xhr.status });
        } else {
          const err = new Error(json.error || `Upload failed (${xhr.status})`);
          err.response = { data: json, status: xhr.status };
          reject(err);
        }
      };

      xhr.onerror = () => {
        const err = new Error('Network error — check your connection and try again');
        reject(err);
      };
      xhr.ontimeout = () => reject(new Error('Upload timed out — try a smaller file'));
      xhr.timeout = 120000; // 2 min for large files + server processing

      xhr.send(formData);
    });
  },
  delete: (botId, groupId, docId) =>
    botId === 'official'
      ? api.delete(`/api/telegram-groups/${groupId}/knowledge/${docId}`)
      : api.delete(`/api/bots/${botId}/groups/${groupId}/knowledge/${docId}`),
};

// Official groups: real polls endpoints via /api/telegram-groups
// Backend returns a raw array for GET; normalise to { polls: [] } for the PollCreator component
export const polls = {
  list: (botId, groupId) =>
    botId === 'official'
      ? api.get(`/api/telegram-groups/${groupId}/polls`)
          .then(r => ({ data: { polls: Array.isArray(r.data) ? r.data : (r.data.polls || []) } }))
      : api.get(`/api/bots/${botId}/groups/${groupId}/polls`),
  create: (botId, groupId, data) =>
    botId === 'official'
      ? api.post(`/api/telegram-groups/${groupId}/polls`, data)
      : api.post(`/api/bots/${botId}/groups/${groupId}/polls`, data),
  delete: (botId, groupId, pollId) =>
    botId === 'official'
      ? api.delete(`/api/telegram-groups/${groupId}/polls/${pollId}`)
      : api.delete(`/api/bots/${botId}/groups/${groupId}/polls/${pollId}`),
};

export const webhooks = {
  list: (botId, groupId) =>
    botId === 'official'
      ? api.get(`/api/telegram-groups/${groupId}/webhooks`)
      : api.get(`/api/bots/${botId}/groups/${groupId}/webhooks`),
  create: (botId, groupId, data) =>
    botId === 'official'
      ? api.post(`/api/telegram-groups/${groupId}/webhooks`, data)
      : api.post(`/api/bots/${botId}/groups/${groupId}/webhooks`, data),
  update: (botId, groupId, hookId, data) =>
    botId === 'official'
      ? api.put(`/api/telegram-groups/${groupId}/webhooks/${hookId}`, data)
      : api.put(`/api/bots/${botId}/groups/${groupId}/webhooks/${hookId}`, data),
  delete: (botId, groupId, hookId) =>
    botId === 'official'
      ? api.delete(`/api/telegram-groups/${groupId}/webhooks/${hookId}`)
      : api.delete(`/api/bots/${botId}/groups/${groupId}/webhooks/${hookId}`),
};

// Official groups: real invite-link endpoints via /api/telegram-groups
export const invites = {
  list: (botId, groupId, params) =>
    botId === 'official'
      ? api.get(`/api/telegram-groups/${groupId}/invite-links`, { params })
      : api.get(`/api/bots/${botId}/groups/${groupId}/invite-links`, { params }),
  create: (botId, groupId, data) =>
    botId === 'official'
      ? api.post(`/api/telegram-groups/${groupId}/invite-links`, data)
      : api.post(`/api/bots/${botId}/groups/${groupId}/invite-links`, data),
  delete: (botId, groupId, linkId) =>
    botId === 'official'
      ? api.delete(`/api/telegram-groups/${groupId}/invite-links/${linkId}`)
      : api.delete(`/api/bots/${botId}/groups/${groupId}/invite-links/${linkId}`),
  getLinkAnalytics: (botId, groupId, linkId, params) =>
    botId === 'official'
      ? api.get(`/api/telegram-groups/${groupId}/invite-links/${linkId}/analytics`, { params })
      : api.get(`/api/bots/${botId}/groups/${groupId}/invite-links/${linkId}/analytics`, { params }),
};

// Official groups: real AI-key endpoints via /api/telegram-groups
export const apiKeys = {
  get: (botId, groupId) =>
    botId === 'official'
      ? api.get(`/api/telegram-groups/${groupId}/api-key`)
      : api.get(`/api/bots/${botId}/groups/${groupId}/api-keys`),
  save: (botId, groupId, data) =>
    botId === 'official'
      ? api.post(`/api/telegram-groups/${groupId}/api-key`, data)
      : api.post(`/api/bots/${botId}/groups/${groupId}/api-keys`, data),
  delete: (botId, groupId) =>
    botId === 'official'
      ? api.delete(`/api/telegram-groups/${groupId}/api-key`)
      : api.delete(`/api/bots/${botId}/groups/${groupId}/api-keys`),
  test: (botId, groupId, data) =>
    botId === 'official'
      ? api.post(`/api/telegram-groups/${groupId}/api-key/test`, data)
      : api.post(`/api/bots/${botId}/groups/${groupId}/api-keys/test`, data),
};

export const analytics = {
  getBotAnalytics: (botId, params) =>
    api.get(`/api/bots/${botId}/analytics`, { params }),
  getGroupAnalytics: (botId, groupId, params) =>
    botId === 'official'
      ? api.get(`/api/official-groups/${groupId}/analytics`, { params })
      : api.get(`/api/bots/${botId}/groups/${groupId}/analytics`, { params }),
  getPlatformStats: () => api.get('/api/platform/stats'),
  // Official bot ecosystem analytics
  getOfficialGroupAnalytics: (groupId, params) =>
    api.get(`/api/official-groups/${groupId}/analytics`, { params }),
  getOfficialOverview: (params) =>
    api.get('/api/official-groups/analytics/overview', { params }),
};

export const billing = {
  getPlans: () => api.get('/api/billing/plans'),
  getSubscription: () => api.get('/api/billing/subscription'),
  getHistory: (params) => api.get('/api/billing/history', { params }),
  // NOWPayments — crypto (USDT, BTC, ETH, etc.)
  cryptoCheckout: (data) => api.post('/api/billing/crypto/checkout', data),
  // Lemon Squeezy — card payments (1-H-01)
  createLsCheckout: (data) => api.post('/api/billing/lemon-squeezy/checkout', data),
  // Manual payment verification (1-I-02)
  verifyPayment: () => api.post('/api/billing/verify-payment'),
  cancelSubscription: () => api.delete('/api/billing/subscription'),
};

export const referrals = {
  getStats: () => api.get('/api/referrals/stats'),
  applyRewards: () => api.post('/api/referrals/apply-rewards'),
  getLeaderboard: () => api.get('/api/referrals/leaderboard'),
  lookupCode: (code) => api.get('/api/referrals/lookup', { params: { code } }),
};

export const userSettings = {
  deleteAccount: (data) => api.delete('/api/auth/account', { data }),
};

// Digest: official groups use /api/official-groups/ (existing official_settings.py blueprint)
export const digest = {
  get: (botId, groupId) =>
    botId === 'official'
      ? api.get(`/api/official-groups/${groupId}/digest`)
      : api.get(`/api/bots/${botId}/groups/${groupId}/digest`),
  update: (botId, groupId, data) =>
    botId === 'official'
      ? api.put(`/api/official-groups/${groupId}/digest`, data)
      : api.put(`/api/bots/${botId}/groups/${groupId}/digest`, data),
  sendNow: (botId, groupId, data) =>
    botId === 'official'
      ? api.post(`/api/official-groups/${groupId}/digest/send-now`, data)
      : api.post(`/api/bots/${botId}/groups/${groupId}/digest/send-now`, data),
};

export const admin = {
  getUsers: (params) => api.get('/api/admin/users', { params }),
  getUser: (id) => api.get(`/api/admin/users/${id}`),
  updateSubscription: (id, data) => api.put(`/api/admin/users/${id}/subscription`, data),
  banUser: (id, data) => api.post(`/api/admin/users/${id}/ban`, data),
  unbanUser: (id) => api.post(`/api/admin/users/${id}/unban`),
  deleteUser: (id) => api.delete(`/api/admin/users/${id}`),
  getStats: () => api.get('/api/admin/stats'),
  getAllBots: (params) => api.get('/api/admin/bots', { params }),
  getSuspicious: (params) => api.get('/api/admin/suspicious', { params }),
  dismissSuspicious: (id) => api.post(`/api/admin/suspicious/${id}/dismiss`),
  getReferrals: (params) => api.get('/api/admin/referrals', { params }),
  updateReferralStatus: (id, data) => api.post(`/api/admin/referrals/${id}/status`, data),
  // Official bot ecosystem
  getTelegramGroups: (params) => api.get('/api/admin/telegram-groups', { params }),
  getTelegramGroupStats: () => api.get('/api/admin/telegram-groups/stats'),
  disableTelegramGroup: (groupId) => api.post(`/api/admin/telegram-groups/${groupId}/disable`),
  unlinkTelegramGroup: (groupId) => api.post(`/api/admin/telegram-groups/${groupId}/unlink`),
  getGroupEvents: (groupId, params) => api.get(`/api/admin/telegram-groups/${groupId}/events`, { params }),
  getCustomBots: (params) => api.get('/api/admin/custom-bots', { params }),
  disableCustomBot: (id) => api.post(`/api/admin/custom-bots/${id}/disable`),
};

export const telegramGroups = {
  list: () => api.get('/api/telegram-groups'),
  link: (data) => api.post('/api/telegram-groups/link', data),
  get: (groupId) => api.get(`/api/telegram-groups/${groupId}`),
  update: (groupId, data) => api.put(`/api/telegram-groups/${groupId}`, data),
  unlink: (groupId) => api.delete(`/api/telegram-groups/${groupId}`),
  getEvents: (groupId, params) => api.get(`/api/telegram-groups/${groupId}/events`, { params }),
  getPending: () => api.get('/api/telegram-groups/pending'),
  listCommands: (groupId) => api.get(`/api/telegram-groups/${groupId}/commands`),
  createCommand: (groupId, data) => api.post(`/api/telegram-groups/${groupId}/commands`, data),
  updateCommand: (groupId, cmdId, data) => api.put(`/api/telegram-groups/${groupId}/commands/${cmdId}`, data),
  deleteCommand: (groupId, cmdId) => api.delete(`/api/telegram-groups/${groupId}/commands/${cmdId}`),
  // Knowledge base
  listKnowledge: (groupId) => api.get(`/api/telegram-groups/${groupId}/knowledge`),
  uploadKnowledge: (groupId, formData) => api.post(`/api/telegram-groups/${groupId}/knowledge`, formData, { headers: { 'Content-Type': 'multipart/form-data' } }),
  deleteKnowledge: (groupId, docId) => api.delete(`/api/telegram-groups/${groupId}/knowledge/${docId}`),
  // Auto-responses
  listAutoResponses: (groupId) => api.get(`/api/telegram-groups/${groupId}/auto-responses`),
  createAutoResponse: (groupId, data) => api.post(`/api/telegram-groups/${groupId}/auto-responses`, data),
  updateAutoResponse: (groupId, arId, data) => api.put(`/api/telegram-groups/${groupId}/auto-responses/${arId}`, data),
  deleteAutoResponse: (groupId, arId) => api.delete(`/api/telegram-groups/${groupId}/auto-responses/${arId}`),
  // Invite links
  listInviteLinks: (groupId) => api.get(`/api/telegram-groups/${groupId}/invite-links`),
  createInviteLink: (groupId, data) => api.post(`/api/telegram-groups/${groupId}/invite-links`, data),
  deleteInviteLink: (groupId, linkId) => api.delete(`/api/telegram-groups/${groupId}/invite-links/${linkId}`),
  // AI API key
  getApiKey: (groupId) => api.get(`/api/telegram-groups/${groupId}/api-key`),
  setApiKey: (groupId, data) => api.post(`/api/telegram-groups/${groupId}/api-key`, data),
  deleteApiKey: (groupId) => api.delete(`/api/telegram-groups/${groupId}/api-key`),
  // Warnings / mod-log / leaderboard
  listWarnings: (groupId, params) => api.get(`/api/telegram-groups/${groupId}/warnings`, { params }),
  removeWarning: (groupId, warningId) => api.delete(`/api/telegram-groups/${groupId}/warnings/${warningId}`),
  getModLog: (groupId, params) => api.get(`/api/telegram-groups/${groupId}/mod-log`, { params }),
  getLeaderboard: (groupId, params) => api.get(`/api/telegram-groups/${groupId}/leaderboard`, { params }),
  // Scheduled messages
  listScheduledMessages: (groupId) => api.get(`/api/telegram-groups/${groupId}/scheduled-messages`),
  createScheduledMessage: (groupId, data) => api.post(`/api/telegram-groups/${groupId}/scheduled-messages`, data),
  updateScheduledMessage: (groupId, msgId, data) => api.put(`/api/telegram-groups/${groupId}/scheduled-messages/${msgId}`, data),
  deleteScheduledMessage: (groupId, msgId) => api.delete(`/api/telegram-groups/${groupId}/scheduled-messages/${msgId}`),
  // Polls
  listPolls: (groupId) => api.get(`/api/telegram-groups/${groupId}/polls`),
  createPoll: (groupId, data) => api.post(`/api/telegram-groups/${groupId}/polls`, data),
  deletePoll: (groupId, pollId) => api.delete(`/api/telegram-groups/${groupId}/polls/${pollId}`),
  // Digest (alternative to /api/official-groups/ route — both work)
  getDigest: (groupId) => api.get(`/api/telegram-groups/${groupId}/digest`),
  updateDigest: (groupId, data) => api.put(`/api/telegram-groups/${groupId}/digest`, data),
  sendDigest: (groupId, data) => api.post(`/api/telegram-groups/${groupId}/digest/send`, data),
  // Members directory
  listMembers: (groupId, params) => api.get(`/api/telegram-groups/${groupId}/members`, { params }),
  // Raids
  listRaids: (groupId) => api.get(`/api/telegram-groups/${groupId}/raids`),
  createRaid: (groupId, data) => api.post(`/api/telegram-groups/${groupId}/raids`, data),
  // Webhooks
  listWebhooks: (groupId) => api.get(`/api/telegram-groups/${groupId}/webhooks`),
  createWebhook: (groupId, data) => api.post(`/api/telegram-groups/${groupId}/webhooks`, data),
  updateWebhook: (groupId, hookId, data) => api.put(`/api/telegram-groups/${groupId}/webhooks/${hookId}`, data),
  deleteWebhook: (groupId, hookId) => api.delete(`/api/telegram-groups/${groupId}/webhooks/${hookId}`),
  // Invite link analytics
  getLinkAnalytics: (groupId, linkId) => api.get(`/api/telegram-groups/${groupId}/invite-links/${linkId}/analytics`),
  // API key test
  testApiKey: (groupId, data) => api.post(`/api/telegram-groups/${groupId}/api-key/test`, data),
  // Reports
  listReports: (groupId, params) => api.get(`/api/telegram-groups/${groupId}/reports`, { params }),
  resolveReport: (groupId, reportId) => api.post(`/api/telegram-groups/${groupId}/reports/${reportId}/resolve`),
};

export const customBots = {
  list: () => api.get('/api/custom-bots'),
  validateToken: (bot_token) => api.post('/api/custom-bots/validate-token', { bot_token }),
  add: (data) => api.post('/api/custom-bots', data),
  get: (id) => api.get(`/api/custom-bots/${id}`),
  delete: (id) => api.delete(`/api/custom-bots/${id}`),
};

export const telegramAccount = {
  generateConnectCode: () => api.post('/api/telegram/generate-connect-code'),
  connectionStatus: () => api.get('/api/telegram/connection-status'),
  disconnect: () => api.delete('/api/telegram/disconnect'),
  // Multi-account management
  listLinkedAccounts: () => api.get('/api/account/telegram-accounts'),
  addLinkedAccount: (data) => api.post('/api/account/telegram-accounts', data),
  removeLinkedAccount: (id) => api.delete(`/api/account/telegram-accounts/${id}`),
  setPrimaryAccount: (id) => api.post(`/api/account/telegram-accounts/${id}/set-primary`),
};

export const workspace = {
  // Smart Links
  listSmartLinks: () => api.get('/api/workspace/smart-links'),
  createSmartLink: (data) => api.post('/api/workspace/smart-links', data),
  updateSmartLink: (id, data) => api.put(`/api/workspace/smart-links/${id}`, data),
  deleteSmartLink: (id) => api.delete(`/api/workspace/smart-links/${id}`),
  toggleSmartLink: (id) => api.post(`/api/workspace/smart-links/${id}/toggle`),
  // Reminders
  listReminders: (params) => api.get('/api/workspace/reminders', { params }),
  createReminder: (data) => api.post('/api/workspace/reminders', data),
  deleteReminder: (id) => api.delete(`/api/workspace/reminders/${id}`),
};

export const workspaceAI = {
  getSettings: () => api.get('/api/workspace/ai-settings'),
  saveKey: (provider, apiKey, model, baseUrl) =>
    api.post('/api/workspace/ai-settings', { provider, api_key: apiKey, model, base_url: baseUrl }),
  deleteKey: () => api.delete('/api/workspace/ai-settings'),
  testKey: (provider, apiKey, model, baseUrl) =>
    api.post('/api/workspace/ai-settings/test', { provider, api_key: apiKey, model, base_url: baseUrl }),
};

export const digests = {
  getAll: () => api.get('/api/workspace/digests'),
  update: (groupId, config) => api.put(`/api/telegram-groups/${groupId}/digest`, config),
  sendNow: (groupId) => api.post(`/api/telegram-groups/${groupId}/digest/send`),
  getHistory: (groupId) => api.get(`/api/telegram-groups/${groupId}/digest/history`),
};

export const notes = {
  list: (params) => api.get('/api/notes', { params }),
  create: (data) => api.post('/api/notes', data),
  update: (id, data) => api.put(`/api/notes/${id}`, data),
  delete: (id) => api.delete(`/api/notes/${id}`),
  generate: (groupId) => api.post(`/api/notes/generate/${groupId}`),
};

export const assistant = {
  hubSummary: () => api.get('/api/assistant/hub-summary'),
  briefing: () => api.get('/api/assistant/briefing'),
  getDmMessages: (lastId = 0) => api.get(`/api/assistant/dm-messages?last_id=${lastId}`),
  sendDm: (text) => api.post('/api/assistant/send-dm', { text }),
  chat: (message, timezone) => api.post('/api/assistant/chat', { message, timezone }),
  ask: (question) => api.post('/api/assistant/ask', { question }),
  getAutoReplyLogs: () => api.get('/api/assistant/autoreply-logs'),
  // Group trend analytics (7/30-day history)
  groupTrends: (days = 7, groupId = null) => api.get('/api/assistant/group-trends', { params: { days, group_id: groupId } }),
  // Inline AI actions (summarize, suggest_automod, write_announcement, explain, improve_message)
  inlineAI: (action, context) => api.post('/api/assistant/inline-ai', { action, context }),
  // Universal search across meetings, reminders, notes, tasks, groups
  search: (q, types = 'meetings,reminders,notes,tasks,groups') => api.get('/api/assistant/search', { params: { q, types } }),
  // Learned user preferences
  getProfile: () => api.get('/api/assistant/profile'),
};

export const meetings = {
  list: (params) => api.get('/api/meetings', { params }),
  create: (data) => api.post('/api/meetings', data),
  update: (id, data) => api.put(`/api/meetings/${id}`, data),
  remove: (id) => api.delete(`/api/meetings/${id}`),
  complete: (id) => api.post(`/api/meetings/${id}/complete`),
  addResource: (id, data) => api.post(`/api/meetings/${id}/resources`, data),
};

export const integrationWebhooks = {
  list: () => api.get('/api/integrations/webhooks'),
  create: (data) => api.post('/api/integrations/webhooks', data),
  update: (id, data) => api.put(`/api/integrations/webhooks/${id}`, data),
  remove: (id) => api.delete(`/api/integrations/webhooks/${id}`),
  test: (id) => api.post(`/api/integrations/webhooks/${id}/test`),
};

export const assistantBot = {
  get: () => api.get('/api/assistant-bot'),
  create: (data) => api.post('/api/assistant-bot', data),
  update: (data) => api.put('/api/assistant-bot', data),
  remove: () => api.delete('/api/assistant-bot'),
  listSpaces: () => api.get('/api/assistant-bot/spaces'),
};

export const tasks = {
  list: (params) => api.get('/api/tasks', { params }),
  create: (data) => api.post('/api/tasks', data),
  update: (id, data) => api.put(`/api/tasks/${id}`, data),
  delete: (id) => api.delete(`/api/tasks/${id}`),
  extract: (groupId) => api.post(`/api/tasks/extract/${groupId}`),
};

export const workspaceKnowledge = {
  list: () => api.get('/api/workspace/knowledge'),
  upload: (formData) => api.post('/api/workspace/knowledge', formData),
  uploadText: (data) => api.post('/api/workspace/knowledge', data),
  delete: (id) => api.delete(`/api/workspace/knowledge/${id}`),
  search: (q) => api.get('/api/workspace/knowledge/search', { params: { q } }),
  ask: (id, question) => api.post(`/api/workspace/knowledge/${id}/ask`, { question }),
};

export const automations = {
  listWorkflows: () => api.get('/api/automations/workflows'),
  createWorkflow: (data) => api.post('/api/automations/workflows', data),
  updateWorkflow: (id, data) => api.put(`/api/automations/workflows/${id}`, data),
  deleteWorkflow: (id) => api.delete(`/api/automations/workflows/${id}`),
  toggleWorkflow: (id) => api.post(`/api/automations/workflows/${id}/toggle`),
  getExecutions: (id, params) => api.get(`/api/automations/workflows/${id}/executions`, { params }),
  listTemplates: () => api.get('/api/automations/templates'),
};

export const miniapp = {
  auth: (initData) => api.post('/api/miniapp/auth', { init_data: initData }),
  me: () => api.get('/api/miniapp/me'),
};

export const forwarding = {
  listRules: () => api.get('/api/forwarding/rules'),
  createRule: (data) => api.post('/api/forwarding/rules', data),
  updateRule: (id, data) => api.put(`/api/forwarding/rules/${id}`, data),
  deleteRule: (id) => api.delete(`/api/forwarding/rules/${id}`),
  toggleRule: (id) => api.post(`/api/forwarding/rules/${id}/toggle`),
  getRuleLogs: (id, params) => api.get(`/api/forwarding/rules/${id}/logs`, { params }),
  listPending: () => api.get('/api/forwarding/pending'),
  approvePending: (logId) => api.post(`/api/forwarding/pending/${logId}/approve`),
  rejectPending: (logId) => api.post(`/api/forwarding/pending/${logId}/reject`),
};

export const marketplace = {
  browse: (params) => api.get('/api/marketplace', { params }),
  deals: (params) => api.get('/api/marketplace/deals', { params }),
  getDeal: (id) => api.get(`/api/marketplace/deals/${id}`),
  createDeal: (data) => api.post('/api/marketplace/deals', data),
  accept: (id) => api.post(`/api/marketplace/deals/${id}/accept`),
  decline: (id, data) => api.post(`/api/marketplace/deals/${id}/decline`, data),
  pay: (id, data) => api.post(`/api/marketplace/deals/${id}/pay`, data),
  deliver: (id, data) => api.post(`/api/marketplace/deals/${id}/deliver`, data),
  complete: (id) => api.post(`/api/marketplace/deals/${id}/complete`),
  dispute: (id, data) => api.post(`/api/marketplace/deals/${id}/dispute`, data),
  cancel: (id) => api.post(`/api/marketplace/deals/${id}/cancel`),
  sendMessage: (id, body) => api.post(`/api/marketplace/deals/${id}/messages`, { body }),
  updatePricing: (lid, data) => api.patch(`/api/marketplace/listing/${lid}/pricing`, data),
};

export const crm = {
  overview: (gid) => api.get(`/api/crm/${gid}/overview`),
  members: (gid, params) => api.get(`/api/crm/${gid}/members`, { params }),
  getMember: (gid, uid) => api.get(`/api/crm/${gid}/members/${uid}`),
  updateMember: (gid, uid, data) => api.patch(`/api/crm/${gid}/members/${uid}`, data),
  computeScores: (gid) => api.post(`/api/crm/${gid}/compute-scores`),
};

export const directory = {
  list: (params) => api.get('/api/directory', { params }),
  mine: () => api.get('/api/directory/mine'),
  create: (data) => api.post('/api/directory', data),
  update: (id, data) => api.put(`/api/directory/${id}`, data),
  delete: (id) => api.delete(`/api/directory/${id}`),
  recordView: (id) => api.post(`/api/directory/${id}/view`),
  recordContact: (id) => api.post(`/api/directory/${id}/contact`),
};

export const channels = {
  list: () => api.get('/api/channels'),
  add: (data) => api.post('/api/channels', data),
  get: (id, params) => api.get(`/api/channels/${id}`, { params }),
  delete: (id) => api.delete(`/api/channels/${id}`),
  posts: (id, params) => api.get(`/api/channels/${id}/posts`, { params }),
  refresh: (id) => api.post(`/api/channels/${id}/refresh`),
  computeTcs: (id) => api.post(`/api/channels/${id}/tcs`),
};

// ── Hub API (consolidated from hubApi.js — uses same auth as all other calls) ─
export const hub = {
  getStatus:            ()           => api.get('/api/hub/status'),
  listBots:             ()           => api.get('/api/hub/bots'),
  getOfficialBot:       ()           => api.get('/api/hub/bots/official'),
  getOfficialSettings:  ()           => api.get('/api/hub/bots/official/settings'),
  updateOfficialSettings: (data)     => api.patch('/api/hub/bots/official/settings', data),
  listOfficialGroups:   ()           => api.get('/api/hub/bots/official/groups'),
  listBotGroups:        (botId)      => api.get(`/api/hub/bots/${botId}/groups`),
  updateGroupSettings:  (id, data)   => api.patch(`/api/hub/bots/official/groups/${id}`, data),
  deleteGroupData:      (id)         => api.delete(`/api/hub/bots/official/groups/${id}/data`),
  getOfficialStats:     ()           => api.get('/api/hub/bots/official/stats'),
  getLimits:            ()           => api.get('/api/hub/limits'),
  disconnectGroup:      (id)         => api.delete(`/api/hub/bots/official/groups/${id}/disconnect`),
  pauseGroup:           (id)         => api.post(`/api/hub/bots/official/groups/${id}/pause`),
  resumeGroup:          (id)         => api.post(`/api/hub/bots/official/groups/${id}/resume`),
  exportData:           ()           => api.get('/api/hub/export'),
  deleteAll:            ()           => api.delete('/api/hub/delete-all', { headers: { 'X-Hub-Confirm': 'DELETE' } }),
  updateRetention:      (ttl)        => api.patch('/api/hub/bots/official/settings/retention', { buffer_ttl_hours: ttl }),
  getOverview:          (groupId, botId)    => api.get('/api/hub/overview', { params: { ...(groupId ? { group_id: groupId } : {}), ...(botId ? { bot_id: botId } : {}) } }),
  listInbox:            (params)     => api.get('/api/hub/inbox', { params }),
  confirmInboxItem:     (id)         => api.patch(`/api/hub/inbox/${id}/confirm`),
  dismissInboxItem:     (id)         => api.patch(`/api/hub/inbox/${id}/dismiss`),
  listTasks:            (params)     => api.get('/api/hub/tasks', { params }),
  createTask:           (data)       => api.post('/api/hub/tasks', data),
  updateTask:           (id, data)   => api.patch(`/api/hub/tasks/${id}`, data),
  deleteTask:           (id)         => api.delete(`/api/hub/tasks/${id}`),
  listReminders:        (params)     => api.get('/api/hub/reminders', { params }),
  createReminder:       (data)       => api.post('/api/hub/reminders', data),
  updateReminder:       (id, data)   => api.patch(`/api/hub/reminders/${id}`, data),
  deleteReminder:       (id)         => api.delete(`/api/hub/reminders/${id}`),
  listNotes:            (params)     => api.get('/api/hub/notes', { params }),
  createNote:           (data)       => api.post('/api/hub/notes', data),
  updateNote:           (id, data)   => api.patch(`/api/hub/notes/${id}`, data),
  deleteNote:           (id)         => api.delete(`/api/hub/notes/${id}`),
  listDecisions:        (params)     => api.get('/api/hub/decisions', { params }),
  dismissDecision:      (id)         => api.patch(`/api/hub/decisions/${id}/dismiss`),
  listMeetings:         (params)     => api.get('/api/hub/meetings', { params }),
  dismissMeeting:       (id)         => api.patch(`/api/hub/meetings/${id}/dismiss`),
  getAutomations:       ()           => api.get('/api/hub/bots/official/automations'),
  updateAutomations:    (data)       => api.patch('/api/hub/bots/official/automations', data),
  listTemplates:        (botId)      => api.get('/api/hub/templates', { params: botId ? { bot_id: botId } : {} }),
  createTemplate:       (data)       => api.post('/api/hub/templates', data),
  updateTemplate:       (id, data)   => api.patch(`/api/hub/templates/${id}`, data),
  deleteTemplate:       (id)         => api.delete(`/api/hub/templates/${id}`),
  createBot:            (data)       => api.post('/api/hub/bots', data),
  updateBot:            (id, data)   => api.patch(`/api/hub/bots/${id}`, data),
  deleteBot:            (id)         => api.delete(`/api/hub/bots/${id}`),
  listKnowledge:        (botId)      => api.get('/api/hub/knowledge', { params: botId ? { bot_id: botId } : {} }),
  createKnowledge:      (data)       => api.post('/api/hub/knowledge', data),
  updateKnowledge:      (id, data)   => api.patch(`/api/hub/knowledge/${id}`, data),
  deleteKnowledge:      (id)         => api.delete(`/api/hub/knowledge/${id}`),
  useKnowledge:         (id)         => api.post(`/api/hub/knowledge/${id}/use`),
  getMemoryGlobal:      ()           => api.get('/api/hub/memory/global'),
  updateMemoryGlobal:   (data)       => api.patch('/api/hub/memory/global', data),
  listMemoryPeople:     ()           => api.get('/api/hub/memory/people'),
  createMemoryPerson:   (data)       => api.post('/api/hub/memory/people', data),
  updateMemoryPerson:   (id, data)   => api.patch(`/api/hub/memory/people/${id}`, data),
  deleteMemoryPerson:   (id)         => api.delete(`/api/hub/memory/people/${id}`),
  listMemoryProjects:   ()           => api.get('/api/hub/memory/projects'),
  createMemoryProject:  (data)       => api.post('/api/hub/memory/projects', data),
  updateMemoryProject:  (id, data)   => api.patch(`/api/hub/memory/projects/${id}`, data),
  deleteMemoryProject:  (id)         => api.delete(`/api/hub/memory/projects/${id}`),
  // Follow-ups (Sprint 8)
  listFollowUps:        (status, groupId) => api.get('/api/hub/follow-ups', { params: { status, group_id: groupId } }),
  resolveFollowUp:      (id)         => api.patch(`/api/hub/follow-ups/${id}/resolve`),
  dismissFollowUp:      (id)         => api.patch(`/api/hub/follow-ups/${id}/dismiss`),
  // Cross-group AI summary (Sprint 8)
  crossGroupSummary:    (range, startDate, endDate) => api.post('/api/hub/cross-group-summary', { range, start_date: startDate, end_date: endDate }),
};

export default api;
