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

  /** Overview tab aggregation. */
  getOverview: (groupId) =>
    api.get('/api/hub/overview', { params: groupId ? { group_id: groupId } : {} }),

  // ── Inbox ──────────────────────────────────────────────────────────────────
  listInbox: (params) => api.get('/api/hub/inbox', { params }),
  confirmInboxItem: (id) => api.patch(`/api/hub/inbox/${id}/confirm`),
  dismissInboxItem: (id) => api.patch(`/api/hub/inbox/${id}/dismiss`),

  // ── Tasks ──────────────────────────────────────────────────────────────────
  listTasks: (params) => api.get('/api/hub/tasks', { params }),
  createTask: (data) => api.post('/api/hub/tasks', data),
  updateTask: (id, data) => api.patch(`/api/hub/tasks/${id}`, data),
  deleteTask: (id) => api.delete(`/api/hub/tasks/${id}`),

  // ── Reminders ─────────────────────────────────────────────────────────────
  listReminders: (params) => api.get('/api/hub/reminders', { params }),
  createReminder: (data) => api.post('/api/hub/reminders', data),
  updateReminder: (id, data) => api.patch(`/api/hub/reminders/${id}`, data),
  deleteReminder: (id) => api.delete(`/api/hub/reminders/${id}`),

  // ── Notes ─────────────────────────────────────────────────────────────────
  listNotes: (params) => api.get('/api/hub/notes', { params }),
  createNote: (data) => api.post('/api/hub/notes', data),
  updateNote: (id, data) => api.patch(`/api/hub/notes/${id}`, data),
  deleteNote: (id) => api.delete(`/api/hub/notes/${id}`),

  // ── Decisions & Meetings ──────────────────────────────────────────────────
  listDecisions: (params) => api.get('/api/hub/decisions', { params }),
  dismissDecision: (id) => api.patch(`/api/hub/decisions/${id}/dismiss`),
  listMeetings: (params) => api.get('/api/hub/meetings', { params }),
  dismissMeeting: (id) => api.patch(`/api/hub/meetings/${id}/dismiss`),

  // ── Automations ───────────────────────────────────────────────────────────
  getAutomations: () => api.get('/api/hub/bots/official/automations'),
  updateAutomations: (data) => api.patch('/api/hub/bots/official/automations', data),

  // ── Templates ─────────────────────────────────────────────────────────────
  listTemplates: () => api.get('/api/hub/templates'),
  createTemplate: (data) => api.post('/api/hub/templates', data),
  updateTemplate: (id, data) => api.patch(`/api/hub/templates/${id}`, data),
  deleteTemplate: (id) => api.delete(`/api/hub/templates/${id}`),

  // ── Custom Bots ────────────────────────────────────────────────────────────
  createBot: (data) => api.post('/api/hub/bots', data),
  updateBot: (id, data) => api.patch(`/api/hub/bots/${id}`, data),
  deleteBot: (id) => api.delete(`/api/hub/bots/${id}`),

  // ── Knowledge Cards ────────────────────────────────────────────────────────
  listKnowledge: (botId) => api.get('/api/hub/knowledge', { params: botId ? { bot_id: botId } : {} }),
  createKnowledge: (data) => api.post('/api/hub/knowledge', data),
  updateKnowledge: (id, data) => api.patch(`/api/hub/knowledge/${id}`, data),
  deleteKnowledge: (id) => api.delete(`/api/hub/knowledge/${id}`),
  useKnowledge: (id) => api.post(`/api/hub/knowledge/${id}/use`),

  // ── Memory ─────────────────────────────────────────────────────────────────
  getMemoryGlobal: () => api.get('/api/hub/memory/global'),
  updateMemoryGlobal: (data) => api.patch('/api/hub/memory/global', data),
  listMemoryPeople: () => api.get('/api/hub/memory/people'),
  createMemoryPerson: (data) => api.post('/api/hub/memory/people', data),
  updateMemoryPerson: (id, data) => api.patch(`/api/hub/memory/people/${id}`, data),
  deleteMemoryPerson: (id) => api.delete(`/api/hub/memory/people/${id}`),
  listMemoryProjects: () => api.get('/api/hub/memory/projects'),
  createMemoryProject: (data) => api.post('/api/hub/memory/projects', data),
  updateMemoryProject: (id, data) => api.patch(`/api/hub/memory/projects/${id}`, data),
  deleteMemoryProject: (id) => api.delete(`/api/hub/memory/projects/${id}`),
};

export default hub;
