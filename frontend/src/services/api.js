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

const _notAvailable = (msg) =>
  Promise.reject({ response: { data: { error: msg } } });

export const settings = {
  getGroupSettings: (botId, groupId) =>
    botId === 'official'
      ? api.get(`/api/official-groups/${groupId}/settings`)
      : api.get(`/api/bots/${botId}/groups/${groupId}/settings`),
  updateGroupSettings: (botId, groupId, data) =>
    botId === 'official'
      ? api.put(`/api/official-groups/${groupId}/settings`, data)
      : api.put(`/api/bots/${botId}/groups/${groupId}/settings`, data),
  getMembers: (botId, groupId, params) =>
    botId === 'official'
      ? Promise.resolve({ data: { members: [], total: 0, pages: 0, page: 1, per_page: 20 } })
      : api.get(`/api/bots/${botId}/groups/${groupId}/members`, { params }),
  getAuditLogs: (botId, groupId, params) =>
    botId === 'official'
      ? Promise.resolve({ data: { logs: [], total: 0, pages: 0, page: 1 } })
      : api.get(`/api/bots/${botId}/groups/${groupId}/audit-logs`, { params }),
  getScheduledMessages: (botId, groupId) =>
    botId === 'official'
      ? Promise.resolve({ data: { messages: [] } })
      : api.get(`/api/bots/${botId}/groups/${groupId}/scheduled-messages`),
  createScheduledMessage: (botId, groupId, data) =>
    botId === 'official'
      ? _notAvailable('Scheduled messages are coming soon for official bot groups.')
      : api.post(`/api/bots/${botId}/groups/${groupId}/scheduled-messages`, data),
  createRaid: (botId, groupId, data) =>
    botId === 'official'
      ? _notAvailable('Raids are coming soon for official bot groups.')
      : api.post(`/api/bots/${botId}/groups/${groupId}/raids`, data),
  getAutoResponses: (botId, groupId) =>
    botId === 'official'
      ? Promise.resolve({ data: { auto_responses: [] } })
      : api.get(`/api/bots/${botId}/groups/${groupId}/auto-responses`),
  createAutoResponse: (botId, groupId, data) =>
    botId === 'official'
      ? _notAvailable('Auto-responses are coming soon for official bot groups.')
      : api.post(`/api/bots/${botId}/groups/${groupId}/auto-responses`, data),
  updateAutoResponse: (botId, groupId, arId, data) =>
    botId === 'official'
      ? _notAvailable('Auto-responses are coming soon for official bot groups.')
      : api.put(`/api/bots/${botId}/groups/${groupId}/auto-responses/${arId}`, data),
  deleteAutoResponse: (botId, groupId, arId) =>
    botId === 'official'
      ? _notAvailable('Auto-responses are coming soon for official bot groups.')
      : api.delete(`/api/bots/${botId}/groups/${groupId}/auto-responses/${arId}`),
  getReports: (botId, groupId, params) =>
    botId === 'official'
      ? Promise.resolve({ data: { reports: [] } })
      : api.get(`/api/bots/${botId}/groups/${groupId}/reports`, { params }),
  resolveReport: (botId, groupId, reportId) =>
    botId === 'official'
      ? Promise.resolve({ data: { message: 'OK' } })
      : api.post(`/api/bots/${botId}/groups/${groupId}/reports/${reportId}/resolve`),
  deleteScheduledMessage: (botId, groupId, msgId) =>
    botId === 'official'
      ? Promise.resolve({ data: { message: 'OK' } })
      : api.delete(`/api/bots/${botId}/groups/${groupId}/scheduled-messages/${msgId}`),
  getGroupAdmins: (botId, groupId) =>
    botId === 'official'
      ? api.get(`/api/official-groups/${groupId}/admins`)
      : api.get(`/api/bots/${botId}/groups/${groupId}/admins`),
  getBotPermissions: (groupId) =>
    api.get(`/api/official-groups/${groupId}/permissions`),
};

export const knowledge = {
  list: (botId, groupId) =>
    botId === 'official'
      ? Promise.resolve({ data: { documents: [] } })
      : api.get(`/api/bots/${botId}/groups/${groupId}/knowledge`),
  upload: (botId, groupId, formData) =>
    botId === 'official'
      ? _notAvailable('Knowledge base is coming soon for official bot groups.')
      : api.post(`/api/bots/${botId}/groups/${groupId}/knowledge`, formData, {
          headers: { 'Content-Type': undefined },
        }),
  delete: (botId, groupId, docId) =>
    botId === 'official'
      ? Promise.resolve({ data: {} })
      : api.delete(`/api/bots/${botId}/groups/${groupId}/knowledge/${docId}`),
};

export const polls = {
  list: (botId, groupId) =>
    botId === 'official'
      ? Promise.resolve({ data: { polls: [] } })
      : api.get(`/api/bots/${botId}/groups/${groupId}/polls`),
  create: (botId, groupId, data) =>
    botId === 'official'
      ? _notAvailable('Polls are coming soon for official bot groups.')
      : api.post(`/api/bots/${botId}/groups/${groupId}/polls`, data),
  delete: (botId, groupId, pollId) =>
    botId === 'official'
      ? Promise.resolve({ data: {} })
      : api.delete(`/api/bots/${botId}/groups/${groupId}/polls/${pollId}`),
};

export const webhooks = {
  list: (botId, groupId) =>
    botId === 'official'
      ? Promise.resolve({ data: { webhooks: [] } })
      : api.get(`/api/bots/${botId}/groups/${groupId}/webhooks`),
  create: (botId, groupId, data) =>
    botId === 'official'
      ? _notAvailable('Webhooks are coming soon for official bot groups.')
      : api.post(`/api/bots/${botId}/groups/${groupId}/webhooks`, data),
  update: (botId, groupId, hookId, data) =>
    botId === 'official'
      ? _notAvailable('Webhooks are coming soon for official bot groups.')
      : api.put(`/api/bots/${botId}/groups/${groupId}/webhooks/${hookId}`, data),
  delete: (botId, groupId, hookId) =>
    botId === 'official'
      ? Promise.resolve({ data: {} })
      : api.delete(`/api/bots/${botId}/groups/${groupId}/webhooks/${hookId}`),
};

export const invites = {
  list: (botId, groupId, params) =>
    botId === 'official'
      ? Promise.resolve({ data: { links: [] } })
      : api.get(`/api/bots/${botId}/groups/${groupId}/invite-links`, { params }),
  create: (botId, groupId, data) =>
    botId === 'official'
      ? _notAvailable('Invite links are coming soon for official bot groups.')
      : api.post(`/api/bots/${botId}/groups/${groupId}/invite-links`, data),
  delete: (botId, groupId, linkId) =>
    botId === 'official'
      ? Promise.resolve({ data: {} })
      : api.delete(`/api/bots/${botId}/groups/${groupId}/invite-links/${linkId}`),
  getLinkAnalytics: (botId, groupId, linkId, params) =>
    botId === 'official'
      ? Promise.resolve({ data: { clicks: [], total: 0 } })
      : api.get(`/api/bots/${botId}/groups/${groupId}/invite-links/${linkId}/analytics`, { params }),
};

export const apiKeys = {
  get: (botId, groupId) =>
    api.get(`/api/bots/${botId}/groups/${groupId}/api-keys`),
  save: (botId, groupId, data) =>
    api.post(`/api/bots/${botId}/groups/${groupId}/api-keys`, data),
  delete: (botId, groupId) =>
    api.delete(`/api/bots/${botId}/groups/${groupId}/api-keys`),
  test: (botId, groupId, data) =>
    api.post(`/api/bots/${botId}/groups/${groupId}/api-keys/test`, data),
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
  // Warnings / mod-log
  listWarnings: (groupId, params) => api.get(`/api/telegram-groups/${groupId}/warnings`, { params }),
  removeWarning: (groupId, warningId) => api.delete(`/api/telegram-groups/${groupId}/warnings/${warningId}`),
  getModLog: (groupId, params) => api.get(`/api/telegram-groups/${groupId}/mod-log`, { params }),
  getLeaderboard: (groupId, params) => api.get(`/api/telegram-groups/${groupId}/leaderboard`, { params }),
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
