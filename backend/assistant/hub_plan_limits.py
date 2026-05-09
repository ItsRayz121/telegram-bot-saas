"""
Plan limits for Assistant Hub. Enforced at the API layer on write.
Names match real Telegizer plan names: free / pro / enterprise.
"""
from ..models import db
from .hub_models import (
    HubConnectedGroup, HubTemplate, HubKnowledgeCard,
    HubMemoryPerson, HubMemoryProject,
)

# -1 = unlimited
LIMITS = {
    "free": {
        "custom_bots": 0,
        "connected_groups_official": 2,
        "connected_groups_custom": 0,
        "knowledge_cards_per_bot": 10,
        "templates_per_bot": 5,
        "memory_people": 5,
        "memory_projects": 3,
        "extraction_calls_per_day": 30,
        "digest_history_days": 30,
    },
    "pro": {
        "custom_bots": 2,
        "connected_groups_official": 10,
        "connected_groups_custom": 5,
        "knowledge_cards_per_bot": 50,
        "templates_per_bot": 30,
        "memory_people": 50,
        "memory_projects": 30,
        "extraction_calls_per_day": 300,
        "digest_history_days": 90,
    },
    "enterprise": {
        "custom_bots": -1,
        "connected_groups_official": -1,
        "connected_groups_custom": -1,
        "knowledge_cards_per_bot": -1,
        "templates_per_bot": -1,
        "memory_people": -1,
        "memory_projects": -1,
        "extraction_calls_per_day": -1,
        "digest_history_days": 90,
    },
}


def _limit(plan: str, key: str) -> int:
    return LIMITS.get(plan, LIMITS["free"]).get(key, 0)


def _unlimited(plan: str, key: str) -> bool:
    return _limit(plan, key) == -1


class PlanLimitError(Exception):
    """Raised when a plan limit would be exceeded."""
    def __init__(self, resource: str, current: int, max_allowed: int, plan: str):
        self.resource = resource
        self.current = current
        self.max_allowed = max_allowed
        self.plan = plan
        super().__init__(
            f"Plan limit reached: {resource} ({current}/{max_allowed} on {plan} plan)"
        )

    def to_dict(self):
        return {
            "error": "plan_limit",
            "resource": self.resource,
            "current": self.current,
            "max_allowed": self.max_allowed,
            "plan": self.plan,
        }


def check_connected_groups(user_id: int, bot_id: str, bot_type: str, plan: str) -> None:
    """Raise PlanLimitError if adding another group would exceed the plan limit."""
    key = "connected_groups_official" if bot_type == "official" else "connected_groups_custom"
    if _unlimited(plan, key):
        return
    max_allowed = _limit(plan, key)
    current = HubConnectedGroup.query.filter_by(
        user_id=user_id, bot_id=bot_id, is_active=True
    ).count()
    if current >= max_allowed:
        raise PlanLimitError("connected_groups", current, max_allowed, plan)


def check_templates(user_id: int, bot_id: str, plan: str) -> None:
    if _unlimited(plan, "templates_per_bot"):
        return
    max_allowed = _limit(plan, "templates_per_bot")
    current = HubTemplate.query.filter_by(bot_id=bot_id).count()
    if current >= max_allowed:
        raise PlanLimitError("templates", current, max_allowed, plan)


def check_knowledge_cards(user_id: int, bot_id: str, plan: str) -> None:
    if _unlimited(plan, "knowledge_cards_per_bot"):
        return
    max_allowed = _limit(plan, "knowledge_cards_per_bot")
    current = HubKnowledgeCard.query.filter_by(bot_id=bot_id).count()
    if current >= max_allowed:
        raise PlanLimitError("knowledge_cards", current, max_allowed, plan)


def check_memory_people(user_id: int, plan: str) -> None:
    if _unlimited(plan, "memory_people"):
        return
    max_allowed = _limit(plan, "memory_people")
    current = HubMemoryPerson.query.filter_by(user_id=user_id).count()
    if current >= max_allowed:
        raise PlanLimitError("memory_people", current, max_allowed, plan)


def check_memory_projects(user_id: int, plan: str) -> None:
    if _unlimited(plan, "memory_projects"):
        return
    max_allowed = _limit(plan, "memory_projects")
    current = HubMemoryProject.query.filter_by(user_id=user_id).count()
    if current >= max_allowed:
        raise PlanLimitError("memory_projects", current, max_allowed, plan)


def get_limits_for_plan(plan: str) -> dict:
    return dict(LIMITS.get(plan, LIMITS["free"]))
