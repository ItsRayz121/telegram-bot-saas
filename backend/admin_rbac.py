"""Role-based access control for the platform admin panel.

Phase 1 of the admin-panel overhaul. Until now admin access was all-or-nothing:
any email in ``Config.ADMIN_EMAILS`` could do everything. This module introduces
six platform-admin roles with a server-enforced permission matrix.

Design decisions (locked with the platform owner):
  • A nullable ``users.admin_role`` column is the source of truth.
  • Bootstrap rule: any email listed in ``Config.ADMIN_EMAILS`` with NO explicit
    role is treated as ``super_admin``. This keeps existing sole-admin setups
    working with zero migration, and means you can never lock yourself out by
    removing your own role — your allowlist membership still grants super_admin.
  • ``super_admin`` always has every permission, including the sensitive ones
    (secrets, platform config, pricing, role management) that no other role gets.

Enforcement lives in the route decorators (see ``routes/admin.py``); this module
only answers "what role is this user?" and "does this role have permission X?".
"""

from functools import lru_cache
from .config import Config

# ── Roles ────────────────────────────────────────────────────────────────────
SUPER_ADMIN = "super_admin"
ADMIN = "admin"
SUPPORT = "support"
FINANCE = "finance"
MODERATOR = "moderator"
ANALYST = "analyst"

ROLES = [SUPER_ADMIN, ADMIN, SUPPORT, FINANCE, MODERATOR, ANALYST]

ROLE_LABELS = {
    SUPER_ADMIN: "Super Admin",
    ADMIN: "Admin",
    SUPPORT: "Support",
    FINANCE: "Finance",
    MODERATOR: "Moderator",
    ANALYST: "Read-only Analyst",
}

ROLE_DESCRIPTIONS = {
    SUPER_ADMIN: "Full control, including secrets, platform config, pricing and role management.",
    ADMIN: "All operational tooling except secrets, platform config, pricing and roles.",
    SUPPORT: "User lookup & moderation, ban/unban, gift trials, resolve reports. Read-only billing.",
    FINANCE: "Revenue, payments, refunds, chargebacks, promo codes, subscriptions. No secrets.",
    MODERATOR: "Directory/report moderation, group disable, suspicious review. No billing or deletes.",
    ANALYST: "Read-only access to dashboards, analytics, logs and health. No mutations.",
}

# ── Permission keys ──────────────────────────────────────────────────────────
# Granular, area-scoped. ``view`` = read, ``manage`` = mutate within that area.
P_USERS_VIEW = "users.view"
P_USERS_MANAGE = "users.manage"        # ban/unban, change tier
P_USERS_DELETE = "users.delete"
P_USERS_GIFT = "users.gift"            # gift subscription / trial

P_BILLING_VIEW = "billing.view"
P_BILLING_MANAGE = "billing.manage"    # promo codes, refunds, chargebacks
P_PRICING_MANAGE = "pricing.manage"    # plan & price edits (super only)

P_SECRETS_MANAGE = "secrets.manage"    # API keys & tokens (super only)
P_CONFIG_MANAGE = "config.manage"      # platform config, feature flags, maintenance (super only)
P_ROLES_MANAGE = "roles.manage"        # assign admin roles (super only)

P_BOTS_VIEW = "bots.view"
P_BOTS_MANAGE = "bots.manage"          # disable bots, ping/health actions
P_GROUPS_VIEW = "groups.view"
P_GROUPS_MANAGE = "groups.manage"      # disable/unlink/reconcile groups

P_CAMPAIGNS_VIEW = "campaigns.view"
P_CAMPAIGNS_MANAGE = "campaigns.manage"

P_MODERATION_VIEW = "moderation.view"  # reports, directory, suspicious lists
P_MODERATION_MANAGE = "moderation.manage"  # resolve reports, moderate directory, dismiss suspicious
P_FRAUD_VIEW = "fraud.view"            # fraud clusters / anomalies

P_REFERRALS_MANAGE = "referrals.manage"
P_ANNOUNCEMENTS_MANAGE = "announcements.manage"
P_SUPPORT_MANAGE = "support.manage"    # live-chat support inbox (view + reply)
P_AUDIT_VIEW = "audit.view"
P_AI_MANAGE = "ai.manage"              # AI selftest, model/limit config
P_HEALTH_VIEW = "health.view"          # platform & bot health
P_ANALYTICS_VIEW = "analytics.view"    # stats, revenue, cohorts, feature adoption

ALL_PERMISSIONS = [
    P_USERS_VIEW, P_USERS_MANAGE, P_USERS_DELETE, P_USERS_GIFT,
    P_BILLING_VIEW, P_BILLING_MANAGE, P_PRICING_MANAGE,
    P_SECRETS_MANAGE, P_CONFIG_MANAGE, P_ROLES_MANAGE,
    P_BOTS_VIEW, P_BOTS_MANAGE, P_GROUPS_VIEW, P_GROUPS_MANAGE,
    P_CAMPAIGNS_VIEW, P_CAMPAIGNS_MANAGE,
    P_MODERATION_VIEW, P_MODERATION_MANAGE, P_FRAUD_VIEW,
    P_REFERRALS_MANAGE, P_ANNOUNCEMENTS_MANAGE, P_SUPPORT_MANAGE, P_AUDIT_VIEW,
    P_AI_MANAGE, P_HEALTH_VIEW, P_ANALYTICS_VIEW,
]

# Permissions that are NEVER granted to anyone but super_admin.
SUPER_ONLY = {P_SECRETS_MANAGE, P_CONFIG_MANAGE, P_PRICING_MANAGE, P_ROLES_MANAGE}

# ── Role → permission matrix ─────────────────────────────────────────────────
# super_admin is handled specially (gets everything) and is intentionally not
# enumerated here.
_BASE_MATRIX = {
    ADMIN: set(ALL_PERMISSIONS) - SUPER_ONLY,
    SUPPORT: {
        P_USERS_VIEW, P_USERS_MANAGE, P_USERS_GIFT,
        P_MODERATION_VIEW, P_MODERATION_MANAGE, P_SUPPORT_MANAGE,
        P_BILLING_VIEW, P_HEALTH_VIEW, P_ANALYTICS_VIEW, P_AUDIT_VIEW,
        P_BOTS_VIEW, P_GROUPS_VIEW, P_CAMPAIGNS_VIEW,
    },
    FINANCE: {
        P_BILLING_VIEW, P_BILLING_MANAGE,
        P_REFERRALS_MANAGE, P_FRAUD_VIEW,
        P_USERS_VIEW, P_ANALYTICS_VIEW, P_AUDIT_VIEW, P_HEALTH_VIEW,
    },
    MODERATOR: {
        P_MODERATION_VIEW, P_MODERATION_MANAGE, P_FRAUD_VIEW,
        P_GROUPS_VIEW, P_GROUPS_MANAGE,
        P_BOTS_VIEW, P_CAMPAIGNS_VIEW, P_CAMPAIGNS_MANAGE,
        P_USERS_VIEW, P_HEALTH_VIEW, P_ANALYTICS_VIEW,
    },
    # Analyst: read-only — every ``*.view`` permission, no mutations.
    ANALYST: {p for p in ALL_PERMISSIONS if p.endswith(".view")},
}


def role_permissions(role: str) -> set:
    """Return the set of permission keys granted to ``role``.

    ``super_admin`` gets every permission. Unknown / None roles get nothing.
    """
    if role == SUPER_ADMIN:
        return set(ALL_PERMISSIONS)
    return set(_BASE_MATRIX.get(role, set()))


def resolve_admin_role(user) -> str | None:
    """Return the effective admin role for ``user`` or None if not an admin.

    Precedence:
      1. An explicit, valid ``user.admin_role`` column value.
      2. Bootstrap: membership in ``Config.ADMIN_EMAILS`` ⇒ ``super_admin``.
      3. Otherwise: not an admin.
    """
    if user is None:
        return None
    role = getattr(user, "admin_role", None)
    if role in ROLES:
        return role
    email = (getattr(user, "email", None) or "").lower()
    if email and email in Config.ADMIN_EMAILS:
        return SUPER_ADMIN
    return None


def is_admin(user) -> bool:
    """True if the user has any platform-admin role (explicit or bootstrapped)."""
    return resolve_admin_role(user) is not None


def is_super_admin(user) -> bool:
    return resolve_admin_role(user) == SUPER_ADMIN


def get_permissions(user) -> set:
    """Return the permission set for a user (empty if not an admin)."""
    role = resolve_admin_role(user)
    return role_permissions(role) if role else set()


def has_permission(user, permission: str) -> bool:
    """True if the user's role grants ``permission``."""
    return permission in get_permissions(user)


def role_matrix() -> dict:
    """Serializable role→permissions map for the admin UI."""
    return {
        role: {
            "label": ROLE_LABELS[role],
            "description": ROLE_DESCRIPTIONS[role],
            "permissions": sorted(role_permissions(role)),
        }
        for role in ROLES
    }
