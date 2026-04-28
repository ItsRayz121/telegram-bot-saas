import axios from 'axios';

const BASE_URL = process.env.REACT_APP_API_URL || '';

const api = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      window.location.href = '/login';
    }
    // Hard redirect if backend rejects due to unverified email
    if (
      error.response?.status === 403 &&
      error.response?.data?.code === 'EMAIL_NOT_VERIFIED'
    ) {
      window.location.href = '/verify-email';
    }
    return Promise.reject(error);
  }
);

export const auth = {
  register: (data) => api.post('/api/auth/register', data),
  login: (data) => api.post('/api/auth/login', data),
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
  // Lemon Squeezy — card / bank transfer
  lemonCheckout: (data) => api.post('/api/billing/lemon/checkout', data),
  // NOWPayments — crypto (USDT, BTC, ETH, etc.)
  cryptoCheckout: (data) => api.post('/api/billing/crypto/checkout', data),
};

export const referrals = {
  getStats: () => api.get('/api/referrals/stats'),
  applyRewards: () => api.post('/api/referrals/apply-rewards'),
  getLeaderboard: () => api.get('/api/referrals/leaderboard'),
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
  add: (data) => api.post('/api/custom-bots', data),
  get: (id) => api.get(`/api/custom-bots/${id}`),
  delete: (id) => api.delete(`/api/custom-bots/${id}`),
};

export const telegramAccount = {
  generateConnectCode: () => api.post('/api/telegram/generate-connect-code'),
  connectionStatus: () => api.get('/api/telegram/connection-status'),
  disconnect: () => api.delete('/api/telegram/disconnect'),
};

export default api;
