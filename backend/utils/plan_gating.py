"""Shared Pro/Enterprise plan gate for routes.

Several route modules independently duplicate a `_require_paid` helper
(routes/polls.py, routes/settings.py, routes/totp.py predate this module and
are left as-is). This is the shared version for new call sites so the gating
logic doesn't drift across yet more copies — the newest, external knowledge
sources feature (routes/knowledge.py, routes/telegram_groups.py) uses this one.
"""
from flask import jsonify

PAID_TIERS = {"pro", "enterprise"}


def require_paid(user, feature="This feature"):
    """Return a 403 response tuple if user lacks a valid paid subscription, else None."""
    if user.subscription_tier not in PAID_TIERS:
        return (
            jsonify({"error": f"{feature} requires a Pro or Enterprise subscription. Upgrade at /pricing."}),
            403,
        )
    if not user.subscription_active:
        return (
            jsonify({"error": "Your subscription has expired. Please renew to continue using this feature."}),
            403,
        )
    return None
