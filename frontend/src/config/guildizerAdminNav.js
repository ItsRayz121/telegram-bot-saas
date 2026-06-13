// Guildizer admin navigation map — the single source of truth for the Guildizer
// admin sidebar (GuildizerAdminSidebar) and the section resolver
// (GuildizerAdminPanel). Mirrors the Telegizer admin structure (6 categories) but
// is an INDEPENDENT copy: it is never imported from the Telegizer adminNav, and
// every section is backed by Guildizer's own API.
//
// Guildizer has roles (support / super) rather than granular permissions, so
// `superOnly: true` marks items only super-admins may see; everything else is
// visible to any admin. The backend enforces the same on its super-only routes.
import {
  TrendingUp, Verified, Flag, People, Security, VerifiedUser, Warning,
  Groups, SmartToy, MonitorHeart, NetworkCheck, Insights, Campaign,
  Timeline, History, AttachMoney, Psychology, Tune, Key, Dns, Gavel,
  Payment, SpaceDashboard, Settings, ShowChart,
} from '@mui/icons-material';

export const GUILDIZER_ADMIN_CATEGORIES = [
  {
    slug: 'overview',
    label: 'Overview',
    icon: SpaceDashboard,
    items: [
      { key: 'dashboard', label: 'Dashboard', icon: TrendingUp },
      { key: 'proof', label: 'Proof Metrics', icon: Verified },
      { key: 'reports', label: 'Reports', icon: Flag },
    ],
  },
  {
    slug: 'access',
    label: 'Users & Access',
    icon: People,
    items: [
      { key: 'users', label: 'Users', icon: People },
      { key: 'roles', label: 'Roles & Access', icon: Security, superOnly: true },
      { key: 'referrals', label: 'Referrals', icon: VerifiedUser },
      { key: 'suspicious', label: 'Suspicious', icon: Warning },
    ],
  },
  {
    slug: 'bots',
    label: 'Bots & Servers',
    icon: SmartToy,
    items: [
      { key: 'servers', label: 'Servers', icon: Groups },
      { key: 'bots', label: 'Custom Bots', icon: SmartToy },
      { key: 'bothealth', label: 'Bot Health', icon: MonitorHeart },
      { key: 'diagnostics', label: 'Diagnostics', icon: NetworkCheck },
    ],
  },
  {
    slug: 'analytics',
    label: 'Product Analytics',
    icon: Insights,
    items: [
      { key: 'feature-usage', label: 'Feature Usage', icon: Insights },
      { key: 'campaigns', label: 'Campaigns', icon: Campaign },
      { key: 'ai-usage', label: 'AI Usage', icon: ShowChart },
      { key: 'event-log', label: 'Event Log', icon: Timeline },
      { key: 'audit', label: 'Audit Log', icon: History },
    ],
  },
  {
    slug: 'platform',
    label: 'Platform Settings',
    icon: Settings,
    items: [
      { key: 'pricing', label: 'Pricing', icon: AttachMoney },
      { key: 'ai', label: 'AI Management', icon: Psychology },
      { key: 'config', label: 'Configuration', icon: Tune },
      { key: 'secrets', label: 'Secrets & Keys', icon: Key, superOnly: true },
      { key: 'system', label: 'System', icon: Dns },
    ],
  },
  {
    slug: 'compliance',
    label: 'Compliance & Comms',
    icon: Gavel,
    items: [
      { key: 'compliance', label: 'Compliance', icon: Gavel, superOnly: true },
      { key: 'announce', label: 'Announcements', icon: Campaign },
      { key: 'promo', label: 'Promo Codes', icon: Payment },
    ],
  },
];

// Flat lookup of every item, annotated with its parent category slug.
export const GUILDIZER_ADMIN_ITEMS = GUILDIZER_ADMIN_CATEGORIES.flatMap((c) =>
  c.items.map((i) => ({ ...i, category: c.slug })),
);

// Resolve a section key → { ...item, category }. Returns null for unknown keys.
export function findGuildizerAdminItem(key) {
  return GUILDIZER_ADMIN_ITEMS.find((i) => i.key === key) || null;
}

// Canonical URL for a section.
export function guildizerAdminPath(key) {
  const item = findGuildizerAdminItem(key);
  if (!item) return '/guildizer/admin';
  return `/guildizer/admin/${item.category}/${item.key}`;
}

export const DEFAULT_GUILDIZER_ADMIN_KEY = 'dashboard';
