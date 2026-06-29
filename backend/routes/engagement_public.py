"""Engagement Campaigns — participant-facing API (Phase 9, Mini App).

These endpoints are for the PERSON completing a task (not the admin). Identity is
the authenticated user's linked Telegram account; no group-ownership is required.
Submission logic is shared with the bot DM flow via engagement.create_submission,
so verification, dedup, fraud-flagging and rewards behave identically.
"""

import logging
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..models import (
    db, User, EngagementCampaign, EngagementSubmission, OfficialMember, Member,
)
from ..middleware.rate_limit import rate_limit
from .. import engagement as eng

logger = logging.getLogger(__name__)

engagement_public_bp = Blueprint("engagement_public", __name__, url_prefix="/api/engagement")


def _user():
    ident = get_jwt_identity()
    return User.query.get(int(ident)) if ident is not None else None


def _public_dict(c, tg_user_id):
    """Campaign info safe to expose to a participant + their own submission(s)."""
    d = c.to_dict(include_fields=True)
    d.pop("settings", None)  # never leak verify_chat / internal flags
    for t in d.get("tasks", []):
        t.pop("settings", None)
    subs = []
    if tg_user_id:
        subs = EngagementSubmission.query.filter_by(
            campaign_id=c.id, telegram_user_id=str(tg_user_id)
        ).order_by(EngagementSubmission.created_at.desc()).all()
    # my_submission = latest (legacy single-task); my_submissions = all (per task).
    d["my_submission"] = subs[0].to_dict() if subs else None
    d["my_submissions"] = [s.to_dict() for s in subs]
    return d


@engagement_public_bp.route("/campaigns/<int:campaign_id>", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def get_campaign(campaign_id):
    user = _user()
    c = EngagementCampaign.query.get(campaign_id)
    if not c or c.status in ("draft", "archived"):
        return jsonify({"error": "Campaign not found"}), 404
    tg = user.telegram_user_id if user else None
    return jsonify({"campaign": _public_dict(c, tg)})


@engagement_public_bp.route("/campaigns/<int:campaign_id>/submit", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def submit_campaign(campaign_id):
    user = _user()
    if not user or not user.telegram_user_id:
        return jsonify({"error": "Link your Telegram account first to participate."}), 400
    c = EngagementCampaign.query.get(campaign_id)
    if not c:
        return jsonify({"error": "Campaign not found"}), 404

    # Per-action verify campaigns (X raids / X social-tasks) run their tap-each-
    # action-then-Verify flow only in the bot DM — the flat Mini App form can't
    # drive it. Send the user to the chat instead of creating a mismatched row.
    if eng.has_action_flow(c):
        return jsonify({"error": "Please complete this campaign from the bot chat — tap “Take Part” on the group post."}), 400

    data = request.get_json() or {}
    answers = data.get("answers") or {}
    if not isinstance(answers, dict):
        return jsonify({"error": "answers must be an object"}), 400
    task_id = data.get("task_id")

    # Resolve the proof fields for the chosen task (multi-task) or the campaign.
    fields = c.custom_fields.all()
    if task_id is not None:
        from ..models import EngagementTask
        t = EngagementTask.query.filter_by(id=task_id, campaign_id=c.id).first()
        if not t:
            return jsonify({"error": "That task is no longer available."}), 404
        fields = t.custom_fields.all()
    elif c.tasks.count() > 0:
        return jsonify({"error": "Please choose a task to complete."}), 400

    # Screenshot proof can't be uploaded via the Mini App API — direct to the bot.
    if any(f.field_type == "screenshot" and f.required for f in fields):
        return jsonify({"error": "This task needs a screenshot — please submit via the bot chat."}), 400

    # Review-based task (manual/screenshot/link) with no proof fields: the bot
    # collects a default proof, but the Mini App API has none to send — submitting
    # here would create an empty "under review" row. Direct the user to the bot.
    spec = t if task_id is not None else c
    if not fields and spec.verification_mode in ("manual", "screenshot", "link"):
        return jsonify({"error": "Please complete this task from the bot chat so it can collect your proof."}), 400

    try:
        sub, error = eng.create_submission(
            c,
            telegram_user_id=user.telegram_user_id,
            telegram_username=user.telegram_username,
            answers=answers,
            task_id=task_id,
        )
    except Exception as e:
        logger.error(f"submit_campaign error: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({"error": "Failed to submit"}), 500

    if error:
        return jsonify({"error": error}), 400
    return jsonify({"submission": sub.to_dict()}), 201


@engagement_public_bp.route("/campaigns/<int:campaign_id>/leaderboard", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def campaign_leaderboard(campaign_id):
    """Public ranked board for a campaign + the viewer's own rank (`me`). Premium
    feature — returns 403 (FEATURE_REQUIRES_PRO) on a non-paid owner's campaign."""
    user = _user()
    c = EngagementCampaign.query.get(campaign_id)
    if not c or c.status in ("draft", "archived"):
        return jsonify({"error": "Campaign not found"}), 404
    tg = user.telegram_user_id if user else None
    try:
        lb = eng.campaign_leaderboard(
            c,
            limit=request.args.get("limit", eng.LEADERBOARD_DEFAULT_LIMIT),
            offset=request.args.get("offset", 0),
            require_visible=True,  # participant-facing → honor the owner's toggle
            highlight_user_id=tg,
        )
    except eng.EngagementError as e:
        body, status = e.to_response()
        return jsonify(body), status
    return jsonify(lb)


@engagement_public_bp.route("/my-tasks", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def my_tasks():
    """Active campaigns available to this user (groups they belong to) plus any
    campaign they've already submitted to — grouped client-side by status."""
    user = _user()
    tg = user.telegram_user_id if user else None
    if not tg:
        return jsonify({"tasks": []})
    tg = str(tg)

    ids = set()
    # Campaigns the user has already engaged with.
    for s in EngagementSubmission.query.filter_by(telegram_user_id=tg).all():
        ids.add(s.campaign_id)
    # Active campaigns in official groups the user is a member of.
    off_groups = [m.telegram_group_id for m in OfficialMember.query.filter_by(telegram_user_id=tg).all()]
    if off_groups:
        for c in EngagementCampaign.query.filter(
            EngagementCampaign.telegram_group_id.in_(off_groups),
            EngagementCampaign.status == "active",
        ).all():
            ids.add(c.id)
    # Active campaigns in custom-bot groups the user is a member of.
    mem_groups = [m.group_id for m in Member.query.filter_by(telegram_user_id=tg).all()]
    if mem_groups:
        for c in EngagementCampaign.query.filter(
            EngagementCampaign.group_id.in_(mem_groups),
            EngagementCampaign.status == "active",
        ).all():
            ids.add(c.id)

    if not ids:
        return jsonify({"tasks": []})
    campaigns = EngagementCampaign.query.filter(EngagementCampaign.id.in_(ids)).order_by(
        EngagementCampaign.created_at.desc()
    ).all()
    return jsonify({"tasks": [_public_dict(c, tg) for c in campaigns]})
