/**
 * SINGLE SOURCE OF TRUTH for all dashboard features/modules.
 *
 * Rules:
 *   - officialOnly: true  → tab/subtab only shown for the official Telegizer bot
 *   - officialOnly: false → shown for both official and all custom bots
 *
 * To add a new module: add an entry here. Both official and custom bot
 * dashboards derive their tab lists from this registry automatically.
 * No changes to GroupSettings.js are required.
 *
 * To lock a feature behind a plan: add its settings key to PLAN_GATES below.
 */

import {
  Group, Shield, People, AutoAwesome, Bolt, BarChart,
} from '@mui/icons-material';

// ── Tab + SubTab Registry ─────────────────────────────────────────────────────

export const FEATURE_TABS = [
  {
    // Moderation first — highest-value feature for new users, drives the "Enable AutoMod" onboarding step
    id: 'moderation',
    label: 'Moderation',
    icon: Shield,
    subTabs: [
      { label: 'AutoMod',   officialOnly: false },
      { label: 'Behavior',  officialOnly: false },
      { label: 'Reports',   officialOnly: false },
    ],
  },
  {
    id: 'members',
    label: 'Members',
    icon: Group,
    subTabs: [
      { label: 'Verification',     officialOnly: false },
      { label: 'Welcome',          officialOnly: false },
      { label: 'XP & Roles',       officialOnly: false },
    ],
  },
  {
    id: 'community',
    label: 'Engagement',
    icon: People,
    subTabs: [
      { label: 'Raids',        officialOnly: false },
      { label: 'Invite Links', officialOnly: false },
      { label: 'Campaigns',    officialOnly: false },
    ],
  },
  {
    id: 'ai',
    label: 'AI & Integrations',
    icon: AutoAwesome,
    subTabs: [
      { label: 'Knowledge Base', officialOnly: false },
      { label: 'Escalation',     officialOnly: false },
    ],
  },
  {
    id: 'automation',
    label: 'Automation',
    icon: Bolt,
    subTabs: [
      { label: 'Scheduler',   officialOnly: false },
      { label: 'Auto Reply',  officialOnly: false },
      { label: 'Polls',       officialOnly: false },
      { label: 'Forwarding',  officialOnly: false },
      { label: 'Workflows',   officialOnly: false },
      { label: 'Webhooks',    officialOnly: false },
    ],
  },
  {
    id: 'analytics',
    label: 'Analytics',
    icon: BarChart,
    subTabs: [
      { label: 'Members',     officialOnly: false },
      { label: 'Leaderboard', officialOnly: false },
      { label: 'Audit Log',   officialOnly: false },
      { label: 'Warnings',    officialOnly: false },
      { label: 'Digest',      officialOnly: false },
      { label: 'AI Activity', officialOnly: false },
    ],
  },
];

// ── Plan-Gating Registry ──────────────────────────────────────────────────────
// Maps settings keys → plan requirement and human-readable label.
// Mirrors backend routes/settings.py _GATED_SECTIONS / _ENTERPRISE_ONLY_KEYS.

export const PLAN_GATES = {
  pro: {
    verification:        'Member Verification',
    levels:              'XP & Levels System',
    raids:               'Raid Coordinator',
    knowledge_base:      'AI Knowledge Base',
    webhooks:            'Webhook Integrations',
    scheduled_messages:  'Scheduled Messages',
    assistant:           'AI Assistant',
  },
  enterprise: {
    white_label:       'White Label',
    custom_branding:   'Custom Branding',
    api_access:        'API Access',
    priority_support:  'Priority Support',
  },
};

// ── Derived exports (backward-compatible) ─────────────────────────────────────

export const PRO_GATED_SECTIONS = new Set(Object.keys(PLAN_GATES.pro));
export const PRO_GATED_LABELS   = { ...PLAN_GATES.pro };
export const ENTERPRISE_GATED_SECTIONS = new Set(Object.keys(PLAN_GATES.enterprise));

// ── Helper functions ──────────────────────────────────────────────────────────

/**
 * Build the categories array used by GroupSettings.
 * Custom bots receive every tab/subtab that is not officialOnly.
 */
export function buildCategories(isOfficial) {
  return FEATURE_TABS.map((tab) => ({
    id:      tab.id,
    label:   tab.label,
    icon:    tab.icon,
    subTabs: tab.subTabs
      .filter((s) => isOfficial || !s.officialOnly)
      .map((s) => s.label),
  }));
}

/**
 * Return the runtime index of a subtab within a built categories array.
 * Returns -1 if the tab or subtab does not exist (e.g. officialOnly tab
 * in a custom-bot context), which safely disables the associated useEffect.
 */
export function getSubTabIndex(categories, catId, subTabLabel) {
  const cat = categories.find((c) => c.id === catId);
  if (!cat) return -1;
  return cat.subTabs.indexOf(subTabLabel);
}
