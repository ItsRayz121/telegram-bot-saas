/**
 * Assistant Hub API service — Sprint 1.
 * All endpoints use /api/hub prefix.
 */
import axios from 'axios';

const BASE_URL = process.env.REACT_APP_API_URL || '';

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 30000,
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
});

// Attach auth token from localStorage (matches existing app pattern)
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) config.headers['Authorization'] = `Bearer ${token}`;
  return config;
});

export const hub = {
  /** Lazy-init global record + official bot. Call on first Hub page visit. */
  getStatus: () => api.get('/api/hub/status'),

  /** List all bot identities for the user. */
  listBots: () => api.get('/api/hub/bots'),

  /** Official bot card data. */
  getOfficialBot: () => api.get('/api/hub/bots/official'),

  /** Effective settings for official bot (via resolver). */
  getOfficialSettings: () => api.get('/api/hub/bots/official/settings'),

  /** Update official bot settings. */
  updateOfficialSettings: (data) => api.patch('/api/hub/bots/official/settings', data),

  /** List connected groups for official bot. */
  listOfficialGroups: () => api.get('/api/hub/bots/official/groups'),

  /** Update per-group overrides. */
  updateGroupSettings: (groupId, data) =>
    api.patch(`/api/hub/bots/official/groups/${groupId}`, data),

  /** Delete all extracted data from a group (keeps the group record). */
  deleteGroupData: (groupId) =>
    api.delete(`/api/hub/bots/official/groups/${groupId}/data`),

  /** Overview stats for the official bot. */
  getOfficialStats: () => api.get('/api/hub/bots/official/stats'),

  /** Plan limits and current usage. */
  getLimits: () => api.get('/api/hub/limits'),

  /** Disconnect a group (bot leaves and record is removed). */
  disconnectGroup: (groupId) =>
    api.delete(`/api/hub/bots/official/groups/${groupId}/disconnect`),

  /** Export all Hub data as JSON. */
  exportData: () => api.get('/api/hub/export'),

  /** Delete all Hub data (requires X-Hub-Confirm header). */
  deleteAll: () =>
    api.delete('/api/hub/delete-all', { headers: { 'X-Hub-Confirm': 'DELETE' } }),

  /** Update retention window setting. */
  updateRetention: (bufferTtlHours) =>
    api.patch('/api/hub/bots/official/settings/retention', { buffer_ttl_hours: bufferTtlHours }),
};

export default hub;
