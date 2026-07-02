// Central admin navigation map — the single source of truth for the admin
// sidebar (AdminSidebar) and the section resolver (AdminPanel). The 24 admin
// sections are grouped into 6 top-level categories so the panel reads like a
// real SaaS Super Admin product instead of a wall of horizontal tabs.
//
// Each item's `key` matches the renderer key in AdminPanel.js and its
// `permission` matches the RBAC permission the backend enforces. Items the
// current admin role cannot access are hidden by the consumer.
import {
  TrendingUp, Verified, Flag, People, Security, VerifiedUser, Warning,
  FolderOpen, Groups, SmartToy, MonitorHeart, NetworkCheck, Insights,
  Campaign, Timeline, History, AttachMoney, Psychology, Tune, Key, Dns,
  Gavel, Payment, SpaceDashboard, Settings, ShowChart, Article, SupportAgent,
} from '@mui/icons-material';

export const ADMIN_CATEGORIES = [
  {
    slug: 'overview',
    label: 'Overview',
    icon: SpaceDashboard,
    items: [
      { key: 'dashboard', label: 'Dashboard', permission: 'analytics.view', icon: TrendingUp },
      { key: 'proof', label: 'Proof Metrics', permission: 'analytics.view', icon: Verified },
      { key: 'reports', label: 'Reports', permission: 'moderation.view', icon: Flag },
    ],
  },
  {
    slug: 'access',
    label: 'Users & Access',
    icon: People,
    items: [
      { key: 'users', label: 'Users', permission: 'users.view', icon: People },
      { key: 'roles', label: 'Roles & Access', permission: 'roles.manage', icon: Security },
      { key: 'referrals', label: 'Referrals', permission: 'referrals.manage', icon: VerifiedUser },
      { key: 'suspicious', label: 'Suspicious', permission: 'fraud.view', icon: Warning },
      { key: 'directory', label: 'Directory', permission: 'moderation.view', icon: FolderOpen },
    ],
  },
  {
    slug: 'bots',
    label: 'Bots & Groups',
    icon: SmartToy,
    items: [
      { key: 'groups', label: 'TG Groups', permission: 'groups.view', icon: Groups },
      { key: 'bots', label: 'Custom Bots', permission: 'bots.view', icon: SmartToy },
      { key: 'bothealth', label: 'Bot Health', permission: 'health.view', icon: MonitorHeart },
      { key: 'diagnostics', label: 'Diagnostics', permission: 'health.view', icon: NetworkCheck },
    ],
  },
  {
    slug: 'analytics',
    label: 'Product Analytics',
    icon: Insights,
    items: [
      { key: 'feature-usage', label: 'Feature Usage', permission: 'analytics.view', icon: Insights },
      { key: 'campaigns', label: 'Campaigns', permission: 'campaigns.view', icon: Campaign },
      { key: 'ai-usage', label: 'AI Usage', permission: 'ai.manage', icon: ShowChart },
      { key: 'event-log', label: 'Event Log', permission: 'audit.view', icon: Timeline },
      { key: 'audit', label: 'Audit Log', permission: 'audit.view', icon: History },
    ],
  },
  {
    slug: 'platform',
    label: 'Platform Settings',
    icon: Settings,
    items: [
      { key: 'pricing', label: 'Pricing', permission: 'pricing.manage', icon: AttachMoney },
      { key: 'ai', label: 'AI Management', permission: 'ai.manage', icon: Psychology },
      { key: 'config', label: 'Configuration', permission: 'config.manage', icon: Tune },
      { key: 'secrets', label: 'Secrets & Keys', permission: 'secrets.manage', icon: Key },
      { key: 'system', label: 'System', permission: 'health.view', icon: Dns },
    ],
  },
  {
    slug: 'compliance',
    label: 'Compliance & Comms',
    icon: Gavel,
    items: [
      { key: 'compliance', label: 'Compliance', permission: 'moderation.view', icon: Gavel },
      { key: 'support', label: 'Live Chat', permission: 'support.manage', icon: SupportAgent },
      { key: 'blog', label: 'Blog', permission: 'announcements.manage', icon: Article },
      { key: 'announce', label: 'Announcements', permission: 'announcements.manage', icon: Campaign },
      { key: 'promo', label: 'Promo Codes', permission: 'billing.view', icon: Payment },
    ],
  },
];

// Flat lookup of every item, annotated with its parent category slug.
export const ADMIN_ITEMS = ADMIN_CATEGORIES.flatMap((c) =>
  c.items.map((i) => ({ ...i, category: c.slug })),
);

// Resolve a section key → { item, category }. Returns null for unknown keys.
export function findAdminItem(key) {
  const item = ADMIN_ITEMS.find((i) => i.key === key);
  if (!item) return null;
  return item;
}

// Build the canonical URL for a section.
export function adminPath(key) {
  const item = findAdminItem(key);
  if (!item) return '/admin';
  return `/admin/${item.category}/${item.key}`;
}

export const DEFAULT_ADMIN_KEY = 'dashboard';
