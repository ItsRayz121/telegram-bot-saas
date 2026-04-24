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
    return Promise.reject(error);
  }
);

export const auth = {
  register: (data) => api.post('/api/auth/register', data),
  login: (data) => api.post('/api/auth/login', data),
  getMe: () => api.get('/api/auth/me'),
  changePassword: (data) => api.post('/api/auth/change-password', data),
  forgotPassword: (data) => api.post('/api/auth/forgot-password', data),
  resetPassword: (data) => api.post('/api/auth/reset-password', data),
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

export const settings = {
  getGroupSettings: (botId, groupId) =>
    api.get(`/api/bots/${botId}/groups/${groupId}/settings`),
  updateGroupSettings: (botId, groupId, data) =>
    api.put(`/api/bots/${botId}/groups/${groupId}/settings`, data),
  getMembers: (botId, groupId, params) =>
    api.get(`/api/bots/${botId}/groups/${groupId}/members`, { params }),
  getAuditLogs: (botId, groupId, params) =>
    api.get(`/api/bots/${botId}/groups/${groupId}/audit-logs`, { params }),
  getScheduledMessages: (botId, groupId) =>
    api.get(`/api/bots/${botId}/groups/${groupId}/scheduled-messages`),
  createScheduledMessage: (botId, groupId, data) =>
    api.post(`/api/bots/${botId}/groups/${groupId}/scheduled-messages`, data),
  createRaid: (botId, groupId, data) =>
    api.post(`/api/bots/${botId}/groups/${groupId}/raids`, data),
  getAutoResponses: (botId, groupId) =>
    api.get(`/api/bots/${botId}/groups/${groupId}/auto-responses`),
  createAutoResponse: (botId, groupId, data) =>
    api.post(`/api/bots/${botId}/groups/${groupId}/auto-responses`, data),
  updateAutoResponse: (botId, groupId, arId, data) =>
    api.put(`/api/bots/${botId}/groups/${groupId}/auto-responses/${arId}`, data),
  deleteAutoResponse: (botId, groupId, arId) =>
    api.delete(`/api/bots/${botId}/groups/${groupId}/auto-responses/${arId}`),
  getReports: (botId, groupId, params) =>
    api.get(`/api/bots/${botId}/groups/${groupId}/reports`, { params }),
  resolveReport: (botId, groupId, reportId) =>
    api.post(`/api/bots/${botId}/groups/${groupId}/reports/${reportId}/resolve`),
  deleteScheduledMessage: (botId, groupId, msgId) =>
    api.delete(`/api/bots/${botId}/groups/${groupId}/scheduled-messages/${msgId}`),
};

export const knowledge = {
  list: (botId, groupId) => api.get(`/api/bots/${botId}/groups/${groupId}/knowledge`),
  upload: (botId, groupId, formData) =>
    api.post(`/api/bots/${botId}/groups/${groupId}/knowledge`, formData, {
      headers: { 'Content-Type': undefined }, // let Axios set multipart + boundary automatically
    }),
  delete: (botId, groupId, docId) =>
    api.delete(`/api/bots/${botId}/groups/${groupId}/knowledge/${docId}`),
};

export const polls = {
  list: (botId, groupId) => api.get(`/api/bots/${botId}/groups/${groupId}/polls`),
  create: (botId, groupId, data) => api.post(`/api/bots/${botId}/groups/${groupId}/polls`, data),
  delete: (botId, groupId, pollId) => api.delete(`/api/bots/${botId}/groups/${groupId}/polls/${pollId}`),
};

export const webhooks = {
  list: (botId, groupId) => api.get(`/api/bots/${botId}/groups/${groupId}/webhooks`),
  create: (botId, groupId, data) => api.post(`/api/bots/${botId}/groups/${groupId}/webhooks`, data),
  update: (botId, groupId, hookId, data) =>
    api.put(`/api/bots/${botId}/groups/${groupId}/webhooks/${hookId}`, data),
  delete: (botId, groupId, hookId) =>
    api.delete(`/api/bots/${botId}/groups/${groupId}/webhooks/${hookId}`),
};

export const invites = {
  list: (botId, groupId, params) =>
    api.get(`/api/bots/${botId}/groups/${groupId}/invite-links`, { params }),
  create: (botId, groupId, data) =>
    api.post(`/api/bots/${botId}/groups/${groupId}/invite-links`, data),
  delete: (botId, groupId, linkId) =>
    api.delete(`/api/bots/${botId}/groups/${groupId}/invite-links/${linkId}`),
  getLinkAnalytics: (botId, groupId, linkId, params) =>
    api.get(`/api/bots/${botId}/groups/${groupId}/invite-links/${linkId}/analytics`, { params }),
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
    api.get(`/api/bots/${botId}/groups/${groupId}/analytics`, { params }),
  getPlatformStats: () => api.get('/api/platform/stats'),
};

export const billing = {
  getPlans: () => api.get('/api/billing/plans'),
  getSubscription: () => api.get('/api/billing/subscription'),
  // Lemon Squeezy — card / bank transfer
  lemonCheckout: (data) => api.post('/api/billing/lemon/checkout', data),
  // NOWPayments — crypto (USDT, BTC, ETH, etc.)
  cryptoCheckout: (data) => api.post('/api/billing/crypto/checkout', data),
};

export const referrals = {
  getStats: () => api.get('/api/referrals/stats'),
  applyRewards: () => api.post('/api/referrals/apply-rewards'),
};

export const digest = {
  get: (botId, groupId) =>
    api.get(`/api/bots/${botId}/groups/${groupId}/digest`),
  update: (botId, groupId, data) =>
    api.put(`/api/bots/${botId}/groups/${groupId}/digest`, data),
  sendNow: (botId, groupId, data) =>
    api.post(`/api/bots/${botId}/groups/${groupId}/digest/send-now`, data),
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
};

export default api;
