"""Read-only endpoints for the campaign workspace (overview / directory / review queue).

Authorization is the same as the existing campaign endpoints: the group must be
one the caller owns or has been granted access to, and every query is scoped to
that one group (see engagement_insights.CampaignScope). Reviewing, publishing,
editing and deleting keep using the existing campaign endpoints.

  /api/telegram-groups/<group_id>/engagement/...          official bot groups
  /api/bots/<bot_id>/groups/<group_id>/engagement/...     custom-bot groups
"""
import logging

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..models import User
from ..middleware.rate_limit import rate_limit
from .. import engagement as eng
from .. import engagement_insights as ei

logger = logging.getLogger(__name__)

workspace_official_bp = Blueprint("eng_ws_official", __name__, url_prefix="/api/telegram-groups/<group_id>/engagement")
workspace_custom_bp = Blueprint("eng_ws_custom", __name__, url_prefix="/api/bots/<int:bot_id>/groups/<int:group_id>/engagement")


def _user():
    return User.query.get(int(get_jwt_identity()))


def _official(group_id):
    from ..group_access import get_group_for_user
    user = _user()
    if not user:
        return None, None
    tg = get_group_for_user(user.id, group_id)
    return (user, ei.CampaignScope("official", tg)) if tg else (user, None)


def _custom(bot_id, group_id):
    from ..group_access import get_legacy_bot_group
    user = _user()
    if not user:
        return None, None
    bot, group = get_legacy_bot_group(user.id, bot_id, group_id)
    return (user, ei.CampaignScope("custom", group)) if (bot and group) else (user, None)


def _int(name, default, lo=1, hi=1000):
    try:
        return min(hi, max(lo, int(request.args.get(name, default))))
    except (TypeError, ValueError):
        return default


# ── handlers (scope-agnostic) ──────────────────────────────────────────────────

def _h_overview(cs, user):
    data = ei.overview(cs, days=_int("days", 30, 1, 90))
    # Whether the account's X (Twitter) verification connection is live. Account-level,
    # cheap (no external call); lets the Tools menu show the real state.
    try:
        from .. import twitter_verify
        data["x_autoverify_status"] = twitter_verify.autoverify_status(user.id)
    except Exception:
        data["x_autoverify_status"] = "disabled"
    return jsonify(data)


def _h_campaigns(cs, user):
    return jsonify(ei.campaigns_page(
        cs, q=(request.args.get("q") or "").strip(), status=request.args.get("status") or "",
        ctype=request.args.get("type") or "", sort=request.args.get("sort") or "created_at",
        direction=request.args.get("dir") or "desc", page=_int("page", 1, 1, 100000), per_page=_int("per_page", 20, 1, 100)))


def _h_queue(cs, user):
    cid = request.args.get("campaign_id")
    return jsonify(ei.queue(
        cs, status=request.args.get("status") or "pending", campaign_id=int(cid) if (cid or "").isdigit() else None,
        q=(request.args.get("q") or "").strip(), flagged=(request.args.get("flagged") == "true"),
        sort=request.args.get("sort") or "oldest", page=_int("page", 1, 1, 100000), per_page=_int("per_page", 25, 1, 100)))


def _campaign(cs, campaign_id):
    # Scoped lookup: a campaign id from any other group raises 404 here.
    if cs.scope == "official":
        return eng.get_campaign(campaign_id, "official", telegram_group_id=cs.ref)
    return eng.get_campaign(campaign_id, "custom", group_id=cs.ref)


def _h_summary(cs, user, campaign_id):
    try:
        return jsonify(ei.campaign_summary(_campaign(cs, campaign_id), days=_int("days", 30, 1, 90)))
    except eng.EngagementError as e:
        body, status = e.to_response()
        return jsonify(body), status


def _h_activity(cs, user, campaign_id):
    try:
        return jsonify(ei.campaign_activity(_campaign(cs, campaign_id)))
    except eng.EngagementError as e:
        body, status = e.to_response()
        return jsonify(body), status


def _h_preview(cs, user):
    return jsonify(ei.preview_message(cs, user, request.get_json(silent=True) or {}))


_GET = {"overview": _h_overview, "campaigns": _h_campaigns, "queue": _h_queue}


def _run(fn, cs, user, *args):
    try:
        return fn(cs, user, *args)
    except Exception as exc:
        logger.error("engagement workspace %s failed: %s", getattr(fn, "__name__", fn), exc, exc_info=True)
        return jsonify({"error": "Could not load this view"}), 500


# ── official ───────────────────────────────────────────────────────────────────

@workspace_official_bp.route("/<kind>", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=90)
def official_get(group_id, kind):
    fn = _GET.get(kind)
    if fn is None:
        return jsonify({"error": "Unknown view"}), 404
    user, cs = _official(group_id)
    if cs is None:
        return jsonify({"error": "Group not found"}), 404
    return _run(fn, cs, user)


@workspace_official_bp.route("/campaigns/<int:campaign_id>/summary", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=90)
def official_summary(group_id, campaign_id):
    user, cs = _official(group_id)
    if cs is None:
        return jsonify({"error": "Group not found"}), 404
    return _run(_h_summary, cs, user, campaign_id)


@workspace_official_bp.route("/campaigns/<int:campaign_id>/activity", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def official_activity(group_id, campaign_id):
    user, cs = _official(group_id)
    if cs is None:
        return jsonify({"error": "Group not found"}), 404
    return _run(_h_activity, cs, user, campaign_id)


@workspace_official_bp.route("/preview", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def official_preview(group_id):
    user, cs = _official(group_id)
    if cs is None:
        return jsonify({"error": "Group not found"}), 404
    return _run(_h_preview, cs, user)


# ── custom bots ────────────────────────────────────────────────────────────────

@workspace_custom_bp.route("/<kind>", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=90)
def custom_get(bot_id, group_id, kind):
    fn = _GET.get(kind)
    if fn is None:
        return jsonify({"error": "Unknown view"}), 404
    user, cs = _custom(bot_id, group_id)
    if cs is None:
        return jsonify({"error": "Group not found"}), 404
    return _run(fn, cs, user)


@workspace_custom_bp.route("/campaigns/<int:campaign_id>/summary", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=90)
def custom_summary(bot_id, group_id, campaign_id):
    user, cs = _custom(bot_id, group_id)
    if cs is None:
        return jsonify({"error": "Group not found"}), 404
    return _run(_h_summary, cs, user, campaign_id)


@workspace_custom_bp.route("/campaigns/<int:campaign_id>/activity", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def custom_activity(bot_id, group_id, campaign_id):
    user, cs = _custom(bot_id, group_id)
    if cs is None:
        return jsonify({"error": "Group not found"}), 404
    return _run(_h_activity, cs, user, campaign_id)


@workspace_custom_bp.route("/preview", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def custom_preview(bot_id, group_id):
    user, cs = _custom(bot_id, group_id)
    if cs is None:
        return jsonify({"error": "Group not found"}), 404
    return _run(_h_preview, cs, user)
