"""Per-plan feature limits (Phase 18). One matrix, enforced at create-time in
the APIs. Safety features are never limited (see the Phase 5 decision:
monetize engagement, never paywall safety).
"""
from __future__ import annotations

from models import Guild

LIMITS = {
    "free": {
        "active_campaigns": 1,
        "workflows": 3,
        "mirrors": 1,
        "inbound_webhooks": 2,
        "outbound_webhooks": 2,
        "scheduled_messages": 3,
        "auto_responses": 5,
        "knowledge_docs": 5,
        "campaign_fields": 2,
    },
    "pro": {
        "active_campaigns": 10,
        "workflows": 25,
        "mirrors": 10,
        "inbound_webhooks": 10,
        "outbound_webhooks": 10,
        "scheduled_messages": 25,
        "auto_responses": 50,
        "knowledge_docs": 50,
        "campaign_fields": 4,
    },
}

# White-label custom bots are the top-tier feature: the connecting user must
# manage at least one Pro guild.
CUSTOM_BOTS_REQUIRE_PRO = True


def plan_of(db, guild_id: int) -> str:
    guild = db.get(Guild, guild_id)
    return "pro" if (guild is not None and guild.is_pro) else "free"


def limit(db, guild_id: int, key: str) -> int:
    plan = plan_of(db, guild_id)
    return LIMITS.get(plan, LIMITS["free"]).get(key, 0)


def limit_response(key: str, value: int):
    from flask import jsonify
    return jsonify(error="plan_limit_reached", limit_key=key, limit=value,
                   message="Upgrade to Pro for more."), 403
