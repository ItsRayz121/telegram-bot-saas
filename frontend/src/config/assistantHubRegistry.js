/**
 * Assistant Hub Tab Registry — single source of truth.
 *
 * To add a new tab to both official and custom bot workspaces:
 *   1. Add an entry here.
 *   2. Add a case in TabContent (HubWorkspace.js) for the component.
 *   Done — both workspaces pick it up automatically.
 *
 * Flags:
 *   officialOnly  — tab only appears for the shared Telegizer bot
 *   customOnly    — tab only appears for user-registered custom bots
 *   (omit both)   — tab appears in every assistant hub workspace
 */
export const ASSISTANT_HUB_TABS = [
  { key: 'overview',   label: 'Overview' },
  { key: 'notes',      label: 'Notes' },
  { key: 'reminders',  label: 'Reminders' },
  { key: 'meetings',   label: 'Meetings' },
  { key: 'tasks',      label: 'Tasks' },
  { key: 'templates',  label: 'Templates' },
  { key: 'knowledge',  label: 'Knowledge' },
  { key: 'automation', label: 'Automation' },
  { key: 'settings',   label: 'Settings' },

  // ── Future tabs (uncomment to activate, add case in TabContent) ──────────────
  // { key: 'memory',     label: 'Memory' },
  // { key: 'crm',        label: 'CRM' },
  // { key: 'inbox',      label: 'Team Inbox' },
  // { key: 'agents',     label: 'AI Agents' },
  // { key: 'documents',  label: 'Documents' },
  // { key: 'analytics',  label: 'Analytics', officialOnly: true },
  // { key: 'voice',      label: 'Voice Notes' },
];

/**
 * Returns tabs visible for a given workspace type.
 * @param {boolean} isOfficial — true for /hub/official, false for /hub/bots/:id
 */
export function getTabsForBot(isOfficial) {
  return ASSISTANT_HUB_TABS.filter(tab => {
    if (tab.officialOnly && !isOfficial) return false;
    if (tab.customOnly  &&  isOfficial) return false;
    return true;
  });
}
