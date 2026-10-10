"""Read-only insight endpoints behind the group Analytics tabs.

Same auth as the existing analytics endpoints: the group must be one the caller
owns or has been given access to (viewers may read - every route here is GET).
Two URL families, one per bot lineage, both thin wrappers over
backend.analytics_insights so the numbers are computed identically:

  /api/telegram-groups/<group_id>/insights/...            official bot groups
  /api/bots/<bot_id>/groups/<group_id>/insights/...       custom-bot groups

Nothing here writes, sends a Telegram message, or calls an AI provider.
"""
import logging
from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..models import User
from ..middleware.rate_limit import rate_limit
from .. import analytics_insights as ai

logger = logging.getLogger(__name__)

insights_official_bp = Blueprint("insights_official", __name__, url_prefix="/api/telegram-groups/<group_id>/insights")
insights_custom_bp = Blueprint("insights_custom", __name__, url_prefix="/api/bots/<int:bot_id>/groups/<int:group_id>/insights")

_PERIODS = ("1d", "7d", "30d", "90d")


def _days(default=30, allow_all=True):
    raw = (request.args.get("days") or request.args.get("period") or "").lower()
    if raw in ("all", "0"):
        return None if allow_all else default
    if raw in _PERIODS:
        return ai.PERIOD_DAYS[raw]
    try:
        n = int(raw)
        return n if n in (1, 7, 14, 30, 90) else default
    except (TypeError, ValueError):
        return default


def _int(name, default, lo=1, hi=200):
    try:
        return min(hi, max(lo, int(request.args.get(name, default))))
    except (TypeError, ValueError):
        return default


def _official_scope(group_id):
    from ..group_access import get_group_for_user
    user = User.query.get(int(get_jwt_identity()))
    if not user:
        return None
    tg = get_group_for_user(user.id, group_id)
    return ai.GroupScope("official", tg) if tg else None


def _custom_scope(bot_id, group_id):
    from ..group_access import get_legacy_bot_group
    user = User.query.get(int(get_jwt_identity()))
    if not user:
        return None
    bot, group = get_legacy_bot_group(user.id, bot_id, group_id)
    return ai.GroupScope("custom", group) if (bot and group) else None


# ── Handlers (scope-agnostic) ──────────────────────────────────────────────────

def _members(sc):
    return jsonify(ai.members_summary(sc, (request.args.get("period") or "all").lower()))


def _audit_summary(sc):
    return jsonify(ai.audit_summary(
        sc, days=_days(30), search=(request.args.get("q") or "").strip(),
        action=request.args.get("action_type") or None))


def _audit_groups(sc):
    return jsonify(ai.audit_groups(
        sc, days=_days(30), search=(request.args.get("q") or "").strip(),
        action=request.args.get("action_type") or None,
        min_count=_int("min_count", 1, 1, 1000),
        page=_int("page", 1, 1, 100000), per_page=_int("per_page", 25, 1, 100)))


def _audit_group_events(sc):
    return jsonify(ai.audit_group_events(
        sc, user_id=request.args.get("user_id") or None,
        action=request.args.get("action") or None,
        label=request.args.get("label") or "",
        days=_days(30), search=(request.args.get("q") or "").strip(),
        page=_int("page", 1, 1, 100000), per_page=_int("per_page", 50, 1, 200)))


def _warnings_summary(sc):
    return jsonify(ai.warnings_summary(sc, days=_days(30, allow_all=False)))


def _warnings_members(sc):
    return jsonify(ai.warnings_members(
        sc, search=request.args.get("search") or "",
        min_count=_int("min_count", 1, 1, 1000),
        page=_int("page", 1, 1, 100000), per_page=_int("per_page", 25, 1, 100)))


def _member_context(sc, user_id):
    return jsonify(ai.member_context(sc, user_id))


def _ai_overview(sc):
    return jsonify(ai.ai_overview(sc.scope, sc.key, days=_days(30, allow_all=False)))


def _digest_preview(sc):
    """Render the Telegram report text for a period without sending anything."""
    from .digest import _build_report_data, _build_report_data_for_official, _format_report_message
    period = (request.args.get("period") or "weekly").lower()
    cfg = {"daily": ("Daily Report", 1), "weekly": ("Weekly Report", 7), "monthly": ("Monthly Report", 30)}
    if period not in cfg:
        return jsonify({"error": "period must be daily, weekly or monthly"}), 400
    label, days = cfg[period]
    since = datetime.utcnow() - timedelta(days=days)
    digest_cfg = (sc.group.settings or {}).get("digest", {}) or {}
    rec = digest_cfg.get("recipients", {}) or {}
    variants = []
    if sc.scope == "official":
        title = sc.group.title or "Your Group"
        data = _build_report_data_for_official(sc.key, since)
        variants.append({
            "id": "manual", "label": "Send report now",
            "description": "What the “Send … Report” buttons deliver.",
            "text": _format_report_message(title, label, data),
        })
        from ..official_bot import _build_official_digest_text
        variants.append({
            "id": "scheduled", "label": "Scheduled report",
            "description": "What the automatic daily/weekly/monthly digest delivers.",
            "text": _build_official_digest_text(sc.group, days, include_ai=False),
            "ai_summary_enabled": bool(((sc.group.settings or {}).get("assistant") or {}).get("ai_digest_enabled")),
        })
    else:
        data = _build_report_data(sc.key, since)
        variants.append({
            "id": "manual", "label": "Report",
            "description": "Used for both scheduled and manual sends.",
            "text": _format_report_message(sc.group.group_name or "Your Group", label, data),
        })
    return jsonify({
        "period": period, "period_days": days, "variants": variants,
        "enabled": {k: bool(digest_cfg.get(k)) for k in ("daily", "weekly", "monthly")},
        "last_sent": {k: digest_cfg.get(f"last_{k}") for k in ("daily", "weekly", "monthly")},
        "recipients": {
            "send_to_group": bool(rec.get("send_to_group", True)),
            "group_topic_id": rec.get("group_topic_id"),
            "owner_dm": bool(rec.get("owner_dm", False)),
            "selected_admin_count": len(rec.get("selected_admin_ids") or []),
        },
        "generated_at": datetime.utcnow().isoformat() + "Z",
    })


_HANDLERS = {
    "members": _members,
    "audit-summary": _audit_summary,
    "audit-groups": _audit_groups,
    "audit-group-events": _audit_group_events,
    "warnings-summary": _warnings_summary,
    "warnings-members": _warnings_members,
    "ai-overview": _ai_overview,
    "digest-preview": _digest_preview,
}


def _safe(fn, sc, *args):
    try:
        return fn(sc, *args)
    except Exception as exc:  # report, never 500 with a stack to the client
        logger.error("insights %s failed: %s", getattr(fn, "__name__", fn), exc, exc_info=True)
        return jsonify({"error": "Could not load this view"}), 500


# ── Official routes ────────────────────────────────────────────────────────────

@insights_official_bp.route("/<kind>", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def official_insight(group_id, kind):
    fn = _HANDLERS.get(kind)
    if fn is None:
        return jsonify({"error": "Unknown insight"}), 404
    sc = _official_scope(group_id)
    if sc is None:
        return jsonify({"error": "Group not found"}), 404
    return _safe(fn, sc)


@insights_official_bp.route("/member/<user_id>", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def official_member_context(group_id, user_id):
    sc = _official_scope(group_id)
    if sc is None:
        return jsonify({"error": "Group not found"}), 404
    return _safe(_member_context, sc, user_id)


# ── Custom-bot routes ──────────────────────────────────────────────────────────

@insights_custom_bp.route("/<kind>", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def custom_insight(bot_id, group_id, kind):
    fn = _HANDLERS.get(kind)
    if fn is None:
        return jsonify({"error": "Unknown insight"}), 404
    sc = _custom_scope(bot_id, group_id)
    if sc is None:
        return jsonify({"error": "Group not found"}), 404
    return _safe(fn, sc)


@insights_custom_bp.route("/member/<user_id>", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def custom_member_context(bot_id, group_id, user_id):
    sc = _custom_scope(bot_id, group_id)
    if sc is None:
        return jsonify({"error": "Group not found"}), 404
    return _safe(_member_context, sc, user_id)
