"""Engagement Campaigns — shared core service.

One engine, used by BOTH bot lineages:
  - custom bots  → keyed by group_id (groups.id)
  - official bot → keyed by telegram_group_id (string)

Routes in routes/settings.py (custom) and routes/telegram_groups.py (official)
are thin wrappers that resolve + check ownership, then delegate here. This keeps
campaign logic in one place so custom bots inherit everything the official bot
gets (Bot Lineage Rule).

Phase 1 scope: CRUD + lifecycle + plan gating + submission review + CSV export.
Telegram publishing (Phase 3), bot participation/proof flow (Phase 4),
verification (Phase 5), XP rewards + anti-fraud (Phase 4/6) are added later.
See ENGAGEMENT_CAMPAIGNS_PLAN.md.
"""

import csv
import io
import logging
from datetime import datetime, timedelta

from .models import (
    db,
    EngagementCampaign,
    EngagementCustomField,
    EngagementTask,
    EngagementSubmission,
    SocialIdentity,
    CAMPAIGN_TYPES,
    CAMPAIGN_VERIFICATION_MODES,
    CAMPAIGN_STATUSES,
    CAMPAIGN_FIELD_TYPES,
)

logger = logging.getLogger(__name__)

_PAID_TIERS = {"pro", "enterprise"}

# ── Free-plan caps (premium lifts these) ──────────────────────────────────────
FREE_MAX_ACTIVE_CAMPAIGNS = 1
FREE_MAX_CUSTOM_FIELDS = 3
FREE_MAX_SUBMISSIONS_PER_MONTH = 100  # enforced at submission time (Phase 4)

# Valid lifecycle transitions for the PATCH `action` verb.
_LIFECYCLE_ACTIONS = {
    "publish": "active",     # draft/paused → active  (actual Telegram post is Phase 3)
    "pause": "paused",       # active → paused
    "reopen": "active",      # paused/closed → active
    "close": "closed",       # any → closed
    "archive": "archived",   # any → archived
}


class EngagementError(Exception):
    """Raised by the service for client-facing errors; routes convert to JSON."""

    def __init__(self, message, status=400, code=None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code

    def to_response(self):
        body = {"error": self.message}
        if self.code:
            body["code"] = self.code
        return body, self.status


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_paid(user):
    return bool(
        user
        and user.subscription_tier in _PAID_TIERS
        and getattr(user, "subscription_active", True)
    )


def _base_query(scope, group_id=None, telegram_group_id=None):
    q = EngagementCampaign.query
    if scope == "official":
        return q.filter_by(telegram_group_id=str(telegram_group_id))
    return q.filter_by(group_id=group_id)


def _parse_dt(value, field_name):
    if value in (None, ""):
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        raise EngagementError(f"Invalid datetime for {field_name}", 400)


def _coerce_int(value, field_name, *, minimum=None, allow_none=True):
    if value in (None, ""):
        if allow_none:
            return None
        raise EngagementError(f"{field_name} is required", 400)
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise EngagementError(f"{field_name} must be a number", 400)
    if minimum is not None and n < minimum:
        raise EngagementError(f"{field_name} must be >= {minimum}", 400)
    return n


# ── Outbound webhook events ─────────────────────────────────────────────────--

def _fire_campaign_event(campaign, event, extra=None):
    """Fire an outbound webhook event to the campaign OWNER's integrations
    (backend/integrations/dispatcher.py). Best-effort; never raises."""
    if not getattr(campaign, "owner_user_id", None):
        return
    try:
        from flask import current_app
        from .integrations.dispatcher import fire_event
        payload = {
            "campaign_id": campaign.id,
            "title": campaign.title,
            "type": campaign.type,
            "status": campaign.status,
            "group_id": campaign.group_id,
            "telegram_group_id": campaign.telegram_group_id,
        }
        if extra:
            payload.update(extra)
        fire_event(campaign.owner_user_id, event, payload,
                   flask_app=current_app._get_current_object())
    except Exception:
        logger.debug("campaign webhook event %s failed", event, exc_info=True)


def _submission_event(campaign, submission, event):
    _fire_campaign_event(campaign, event, {
        "submission_id": submission.id,
        "task_id": submission.task_id,
        "telegram_user_id": submission.telegram_user_id,
        "telegram_username": submission.telegram_username,
        "status": submission.status,
    })


# ── Read ──────────────────────────────────────────────────────────────────────

def list_campaigns(scope, *, group_id=None, telegram_group_id=None, status=None, limit=200):
    q = _base_query(scope, group_id, telegram_group_id)
    if status:
        q = q.filter(EngagementCampaign.status == status)
    rows = q.order_by(EngagementCampaign.created_at.desc()).limit(limit).all()
    return [c.to_dict(include_fields=True, include_analytics=True) for c in rows]


def get_campaign(campaign_id, scope, *, group_id=None, telegram_group_id=None):
    c = _base_query(scope, group_id, telegram_group_id).filter(
        EngagementCampaign.id == campaign_id
    ).first()
    if not c:
        raise EngagementError("Campaign not found", 404)
    return c


# ── Gating ──────────────────────────────────────────────────────────────────--

def _check_create_gating(user, *, scope, group_id, telegram_group_id, status, verification_mode, platform, field_count, task_count=0):
    """Raise EngagementError(403) if a free/expired user exceeds free limits."""
    if _is_paid(user):
        return

    # Multi-task campaigns (more than one sub-task) are premium.
    if task_count > 1:
        raise EngagementError(
            "Multi-task campaigns require a Pro or Enterprise subscription.",
            403, code="FEATURE_REQUIRES_PRO",
        )

    # Link-validity auto-checks are premium.
    if verification_mode == "link":
        raise EngagementError(
            "Link-validity verification requires a Pro or Enterprise subscription.",
            403, code="FEATURE_REQUIRES_PRO",
        )
    # 'auto' verification is free ONLY for Telegram join; other platforms are premium.
    if verification_mode == "auto" and platform != "telegram":
        raise EngagementError(
            "Automatic verification for this platform requires a Pro or Enterprise subscription.",
            403, code="FEATURE_REQUIRES_PRO",
        )
    if field_count > FREE_MAX_CUSTOM_FIELDS:
        raise EngagementError(
            f"The free plan allows up to {FREE_MAX_CUSTOM_FIELDS} custom fields per campaign. "
            "Upgrade to Pro for more.",
            403, code="FEATURE_REQUIRES_PRO",
        )
    # Active-campaign cap (only relevant when creating/publishing as active).
    if status == "active":
        active = _base_query(scope, group_id, telegram_group_id).filter(
            EngagementCampaign.status == "active"
        ).count()
        if active >= FREE_MAX_ACTIVE_CAMPAIGNS:
            raise EngagementError(
                f"The free plan allows {FREE_MAX_ACTIVE_CAMPAIGNS} active campaign at a time. "
                "Close it or upgrade to Pro to run more.",
                403, code="FEATURE_REQUIRES_PRO",
            )


# ── Create ──────────────────────────────────────────────────────────────────--

def create_campaign(user, data, *, scope, owner_user_id, group_id=None, telegram_group_id=None):
    data = data or {}

    title = (data.get("title") or "").strip()
    if not title:
        raise EngagementError("Title is required", 400)
    if len(title) > 200:
        title = title[:200]

    ctype = (data.get("type") or "proof_collection").strip()
    if ctype not in CAMPAIGN_TYPES:
        raise EngagementError(f"Invalid campaign type: {ctype}", 400)

    vmode = (data.get("verification_mode") or "manual").strip()
    if vmode not in CAMPAIGN_VERIFICATION_MODES:
        raise EngagementError(f"Invalid verification_mode: {vmode}", 400)

    status = (data.get("status") or "draft").strip()
    if status not in ("draft", "active"):
        raise EngagementError("Campaign can only be created as 'draft' or 'active'", 400)

    platform = (data.get("platform") or None)
    if platform:
        platform = str(platform).strip().lower() or None

    # Deadline: explicit ends_at wins; else derive from duration_hours.
    starts_at = _parse_dt(data.get("starts_at"), "starts_at")
    ends_at = _parse_dt(data.get("ends_at"), "ends_at")
    if not ends_at and data.get("duration_hours"):
        hours = _coerce_int(data.get("duration_hours"), "duration_hours", minimum=1)
        ends_at = (starts_at or datetime.utcnow()) + timedelta(hours=hours)

    fields_in = data.get("custom_fields") or []
    if not isinstance(fields_in, list):
        raise EngagementError("custom_fields must be a list", 400)

    tasks_in = data.get("tasks")
    task_count = len(tasks_in) if isinstance(tasks_in, list) else 0

    _check_create_gating(
        user, scope=scope, group_id=group_id, telegram_group_id=telegram_group_id,
        status=status, verification_mode=vmode, platform=platform,
        field_count=len(fields_in), task_count=task_count,
    )
    # Real-time X auto-verify (raid) is a Pro/Enterprise feature; free owners can
    # still create the raid, just without automatic verification.
    if (data.get("settings") or {}).get("auto_verify_x") and not _is_paid(user):
        raise EngagementError(
            "Automatic X verification requires a Pro or Enterprise subscription.",
            403, code="FEATURE_REQUIRES_PRO",
        )

    campaign = EngagementCampaign(
        group_id=group_id,
        telegram_group_id=str(telegram_group_id) if telegram_group_id is not None else None,
        owner_user_id=owner_user_id,
        type=ctype,
        platform=platform,
        title=title,
        description=(data.get("description") or None),
        task_url=(data.get("task_url") or None),
        verification_mode=vmode,
        reward_xp=_coerce_int(data.get("reward_xp"), "reward_xp", minimum=0) or 0,
        reward_label=(data.get("reward_label") or None),
        status=status,
        starts_at=starts_at,
        ends_at=ends_at,
        max_participants=_coerce_int(data.get("max_participants"), "max_participants", minimum=1),
        one_per_user=bool(data.get("one_per_user", True)),
        pin_message=bool(data.get("pin_message", True)),
        message_thread_id=_coerce_int(data.get("message_thread_id"), "message_thread_id"),
        settings=data.get("settings") or {},
    )
    db.session.add(campaign)
    db.session.flush()  # get campaign.id for fields

    _replace_custom_fields(campaign, fields_in)
    _replace_tasks(campaign, tasks_in)

    db.session.commit()
    _fire_campaign_event(campaign, "campaign.created")
    if campaign.status == "active":
        _fire_campaign_event(campaign, "campaign.published")
    _maybe_publish(campaign)
    return campaign


def _validate_fields(fields_in):
    """Validate raw proof-field dicts → list of normalized kwargs (no DB writes).
    Shared by campaign-level and task-level field creation."""
    if not isinstance(fields_in, list):
        raise EngagementError("custom_fields must be a list", 400)
    out = []
    seen_keys = set()
    for idx, raw in enumerate(fields_in):
        if not isinstance(raw, dict):
            raise EngagementError("Each custom field must be an object", 400)
        label = (raw.get("label") or "").strip()
        if not label:
            raise EngagementError("Each custom field needs a label", 400)
        ftype = (raw.get("field_type") or "text").strip()
        if ftype not in CAMPAIGN_FIELD_TYPES:
            raise EngagementError(f"Invalid field_type: {ftype}", 400)
        key = (raw.get("key") or label).strip().lower().replace(" ", "_")[:64]
        if key in seen_keys:
            key = f"{key}_{idx}"
        seen_keys.add(key)
        example = (raw.get("example") or "").strip()
        out.append(dict(
            key=key,
            label=label[:200],
            field_type=ftype,
            required=bool(raw.get("required", True)),
            order=_coerce_int(raw.get("order"), "order") or idx,
            example=(example[:255] or None),
        ))
    return out


def _replace_custom_fields(campaign, fields_in):
    """Validate + (re)create campaign-level custom fields. Caller commits."""
    for f in campaign.custom_fields.all():
        db.session.delete(f)
    for kw in _validate_fields(fields_in):
        db.session.add(EngagementCustomField(campaign_id=campaign.id, **kw))


def _replace_tasks(campaign, tasks_in):
    """Validate + (re)create the campaign's sub-tasks and each task's proof
    fields. Caller commits. `tasks_in` None leaves tasks untouched; an empty list
    clears them (back to single-task)."""
    if tasks_in is None:
        return
    if not isinstance(tasks_in, list):
        raise EngagementError("tasks must be a list", 400)
    existing = campaign.tasks.all()
    if existing:
        # Deleting a task CASCADE-deletes its submissions at the DB level — refuse
        # to replace tasks once members have started submitting (data-loss guard).
        existing_ids = [t.id for t in existing]
        if EngagementSubmission.query.filter(
            EngagementSubmission.task_id.in_(existing_ids)
        ).first():
            raise EngagementError(
                "This campaign's tasks can't be changed after members have started "
                "submitting. Close it and create a new campaign instead.", 400,
            )
    for t in existing:
        db.session.delete(t)
    db.session.flush()
    for idx, raw in enumerate(tasks_in):
        if not isinstance(raw, dict):
            raise EngagementError("Each task must be an object", 400)
        title = (raw.get("title") or "").strip()
        if not title:
            raise EngagementError("Each task needs a title", 400)
        ttype = (raw.get("type") or "social_task").strip()
        if ttype not in CAMPAIGN_TYPES:
            raise EngagementError(f"Invalid task type: {ttype}", 400)
        tmode = (raw.get("verification_mode") or "manual").strip()
        if tmode not in CAMPAIGN_VERIFICATION_MODES:
            raise EngagementError(f"Invalid verification_mode: {tmode}", 400)
        platform = raw.get("platform")
        platform = (str(platform).strip().lower() or None) if platform else None
        task = EngagementTask(
            campaign_id=campaign.id,
            order=_coerce_int(raw.get("order"), "order") or idx,
            title=title[:200],
            description=(raw.get("description") or None),
            type=ttype,
            platform=platform,
            task_url=(raw.get("task_url") or None),
            verification_mode=tmode,
            reward_xp=_coerce_int(raw.get("reward_xp"), "reward_xp", minimum=0) or 0,
            reward_label=(raw.get("reward_label") or None),
            settings=raw.get("settings") or {},
        )
        db.session.add(task)
        db.session.flush()  # need task.id for its fields
        for kw in _validate_fields(raw.get("custom_fields") or []):
            db.session.add(EngagementCustomField(task_id=task.id, **kw))


# ── Update / lifecycle ────────────────────────────────────────────────────────

# Fields a PATCH may edit directly (content edits, distinct from lifecycle action).
_EDITABLE_FIELDS = {
    "title", "description", "task_url", "platform", "reward_xp",
    "reward_label", "starts_at", "ends_at", "max_participants",
    "one_per_user", "pin_message", "verification_mode", "settings",
}


def update_campaign(campaign, data, *, user=None):
    """Apply a content edit and/or a lifecycle `action`. Returns the campaign."""
    data = data or {}

    # Multi-task is premium — gate when a free owner edits in >1 task.
    if isinstance(data.get("tasks"), list) and len(data["tasks"]) > 1 and not _is_paid(user):
        raise EngagementError(
            "Multi-task campaigns require a Pro or Enterprise subscription.",
            403, code="FEATURE_REQUIRES_PRO",
        )
    # Enabling X auto-verify via an edit is Pro/Enterprise too.
    if isinstance(data.get("settings"), dict) and data["settings"].get("auto_verify_x") and not _is_paid(user):
        raise EngagementError(
            "Automatic X verification requires a Pro or Enterprise subscription.",
            403, code="FEATURE_REQUIRES_PRO",
        )

    action = data.get("action")
    if action is not None:
        if action not in _LIFECYCLE_ACTIONS:
            raise EngagementError(f"Unknown action: {action}", 400)
        campaign.status = _LIFECYCLE_ACTIONS[action]

    for key in list(data.keys()):
        if key not in _EDITABLE_FIELDS:
            continue
        value = data[key]
        if key in ("starts_at", "ends_at"):
            setattr(campaign, key, _parse_dt(value, key))
        elif key == "reward_xp":
            campaign.reward_xp = _coerce_int(value, "reward_xp", minimum=0) or 0
        elif key == "max_participants":
            campaign.max_participants = _coerce_int(value, "max_participants", minimum=1)
        elif key in ("one_per_user", "pin_message"):
            setattr(campaign, key, bool(value))
        elif key == "verification_mode":
            if value not in CAMPAIGN_VERIFICATION_MODES:
                raise EngagementError(f"Invalid verification_mode: {value}", 400)
            campaign.verification_mode = value
        elif key == "settings":
            campaign.settings = value or {}
        else:
            setattr(campaign, key, (value or None) if isinstance(value, str) else value)

    if isinstance(data.get("custom_fields"), list):
        _replace_custom_fields(campaign, data["custom_fields"])
    if "tasks" in data:
        _replace_tasks(campaign, data.get("tasks"))

    db.session.commit()
    if action == "publish":
        _fire_campaign_event(campaign, "campaign.published")
        _maybe_publish(campaign)
    elif action == "close":
        _fire_campaign_event(campaign, "campaign.closed")
    elif action is None:
        # Pure content edit (no lifecycle change) → refresh the live group post so
        # it reflects the new title/reward/deadline/tasks/leaderboard.
        _maybe_refresh_post(campaign)
    return campaign


def _maybe_publish(campaign):
    """Post the campaign to Telegram on first activation (best-effort).

    Posts when the campaign is active and has not yet been delivered
    (post_status != 'posted'); this also auto-retries a previously failed post
    on the next publish/reopen. A successful post sets post_status='posted' so a
    pause→reopen never double-posts. Publishing failures never break the API."""
    if campaign.status != "active":
        return
    if campaign.post_status == "posted" and campaign.telegram_message_id:
        return
    try:
        from .engagement_telegram import publish_campaign
        publish_campaign(campaign)
    except Exception:
        logger.exception("campaign publish hook failed for %s", getattr(campaign, "id", "?"))


def _maybe_refresh_post(campaign):
    """Re-render the already-posted group announcement after a content edit
    (best-effort). Only for an active, already-posted campaign — we never re-add
    participate buttons to a paused/closed post."""
    if campaign.status != "active" or campaign.post_status != "posted" or not campaign.telegram_message_id:
        return
    try:
        from .engagement_telegram import edit_campaign_post
        edit_campaign_post(campaign)
    except Exception:
        logger.debug("campaign post refresh hook failed for %s", getattr(campaign, "id", "?"), exc_info=True)


def repost_campaign(campaign):
    """Manual 'Post to group' / retry from the dashboard. Re-sends the group
    announcement (even if a previous attempt failed) and returns the campaign.
    Only meaningful for an active campaign."""
    if campaign.status != "active":
        raise EngagementError("Only an active campaign can be posted to the group.", 400)
    from .engagement_telegram import publish_campaign
    publish_campaign(campaign)
    return campaign


def delete_campaign_post(campaign):
    """Delete the published group announcement from Telegram, then clear the
    post-tracking columns so the dashboard shows 'Not posted' and the admin can
    repost. Raises EngagementError if Telegram refused the delete."""
    if not campaign.telegram_message_id:
        raise EngagementError("This campaign hasn't been posted to the group.", 400)
    from .engagement_telegram import delete_campaign_post as _delete
    ok, error = _delete(campaign)
    if not ok:
        raise EngagementError(error or "Couldn't delete the group post.", 400)
    campaign.telegram_message_id = None
    campaign.post_status = "none"
    campaign.posted_at = None
    campaign.post_error = None
    db.session.commit()
    return campaign


# ── Submissions ───────────────────────────────────────────────────────────────

def list_submissions(campaign, *, status=None, limit=1000):
    q = campaign.submissions
    if status:
        q = q.filter(EngagementSubmission.status == status)
    rows = q.order_by(EngagementSubmission.created_at.desc()).limit(limit).all()
    return [s.to_dict() for s in rows]


def list_user_submissions(scope, telegram_user_id, *, group_id=None, telegram_group_id=None, limit=200):
    """All campaign submissions by one participant within a group (both lineages),
    enriched with the campaign title/type — powers the per-user submission history
    in the member profile. Returns a list of dicts."""
    tg = str(telegram_user_id)
    camp_ids = [
        c.id for c in _base_query(scope, group_id, telegram_group_id)
        .with_entities(EngagementCampaign.id).all()
    ]
    if not camp_ids:
        return []
    rows = (
        EngagementSubmission.query
        .filter(EngagementSubmission.campaign_id.in_(camp_ids))
        .filter(EngagementSubmission.telegram_user_id == tg)
        .order_by(EngagementSubmission.created_at.desc())
        .limit(limit).all()
    )
    by_id = {c.id: c for c in EngagementCampaign.query.filter(EngagementCampaign.id.in_(camp_ids)).all()}
    out = []
    for s in rows:
        d = s.to_dict()
        c = by_id.get(s.campaign_id)
        d["campaign_title"] = c.title if c else None
        d["campaign_type"] = c.type if c else None
        d["reward_xp"] = c.reward_xp if c else 0
        out.append(d)
    return out


def get_submission_file(campaign, submission_id):
    """Return (bytes, content_type) for a submission's uploaded screenshot/photo,
    or None if there is no file or it can't be fetched. Validates the submission
    belongs to this campaign so one group's owner can't read another's proof.

    The image is stored only as a Telegram file_id; this downloads it through the
    campaign's own lineage bot so the dashboard can finally display it.
    """
    sub = EngagementSubmission.query.filter_by(
        id=submission_id, campaign_id=campaign.id
    ).first()
    if not sub:
        raise EngagementError("Submission not found", 404)
    if not sub.file_id:
        return None
    from .engagement_telegram import fetch_submission_file
    return fetch_submission_file(campaign, sub.file_id)


def review_submission(campaign, submission_id, action, *, reviewed_by=None, reason=None):
    """Approve or reject a submission. On approve we credit XP idempotently
    (guarded by EngagementSubmission.rewarded) and the verified row is what the
    winner picker / giveaway pool draws from. On reject we credit nothing and
    store the reason. Either way we DM the participant the outcome (best-effort,
    recorded on the submission)."""
    sub = EngagementSubmission.query.filter_by(
        id=submission_id, campaign_id=campaign.id
    ).first()
    if not sub:
        raise EngagementError("Submission not found", 404)
    if action == "approve":
        sub.status = "verified"
    elif action == "reject":
        sub.status = "rejected"
    else:
        raise EngagementError(f"Unknown review action: {action}", 400)
    sub.reviewed_by = str(reviewed_by) if reviewed_by is not None else None
    sub.review_reason = (reason or None)
    sub.reviewed_at = datetime.utcnow()
    db.session.commit()
    if action == "approve":
        award_submission(campaign, sub)  # credits XP, then commits
        _refresh_post_progress(campaign)  # update the live quota countdown
    _notify_review(campaign, sub, approved=(action == "approve"), reason=reason)
    _submission_event(
        campaign, sub,
        "campaign.submission.verified" if action == "approve" else "campaign.submission.rejected",
    )
    return sub


def _notify_review(campaign, submission, *, approved, reason=None):
    """DM the participant the review outcome. Best-effort; never raises."""
    try:
        from .engagement_telegram import notify_submission_review
        allow_resubmit = bool((campaign.settings or {}).get("allow_resubmit"))
        notify_submission_review(
            campaign, submission, approved=approved,
            reason=reason, allow_resubmit=allow_resubmit,
        )
    except Exception:
        logger.debug("review notification failed", exc_info=True)


def _sibling_campaign_ids(campaign):
    """All campaign ids in the same group (same lineage) — the dedup scope."""
    q = EngagementCampaign.query.with_entities(EngagementCampaign.id)
    if campaign.group_id:
        q = q.filter(EngagementCampaign.group_id == campaign.group_id)
    else:
        q = q.filter(EngagementCampaign.telegram_group_id == campaign.telegram_group_id)
    return [row[0] for row in q.all()]


# Proof field types whose values must be unique across participants.
_DEDUP_FIELD_TYPES = {"uid", "wallet", "tx_hash", "username", "url"}


def detect_duplicate(campaign, answers, file_hash, fields=None):
    """Return (is_dup, reason) if a normalized proof value or screenshot hash has
    already been used by another participant in this group. Anti-farming guard.
    `fields` defaults to the campaign's fields; pass a task's fields for a
    multi-task submission."""
    answers = answers or {}
    if fields is None:
        fields = campaign.custom_fields.all()
    # Build the set of (key → normalized value) we care about.
    dedup_keys = {
        f.key for f in fields if f.field_type in _DEDUP_FIELD_TYPES
    }
    values = {
        (answers.get(k) or "").strip().lower()
        for k in dedup_keys
        if (answers.get(k) or "").strip()
    }
    if not values and not file_hash:
        return False, None

    sib_ids = _sibling_campaign_ids(campaign)
    if not sib_ids:
        return False, None

    existing = EngagementSubmission.query.filter(
        EngagementSubmission.campaign_id.in_(sib_ids)
    ).all()
    for s in existing:
        if file_hash and s.file_hash and s.file_hash == file_hash:
            return True, "Duplicate screenshot already submitted"
        payload = s.payload or {}
        s_values = {str(v).strip().lower() for v in payload.values() if str(v).strip()}
        if values & s_values:
            return True, "Duplicate proof value already submitted"
    return False, None


def log_suspicious(campaign_id, telegram_user_id, reason):
    """Record a duplicate/fraud signal for admin review. Best-effort."""
    try:
        from .models import SuspiciousActivity
        db.session.add(SuspiciousActivity(
            user_id=None,
            event_type="engagement_duplicate",
            reason=(reason or "duplicate")[:255],
            event_metadata={"campaign_id": campaign_id, "telegram_user_id": str(telegram_user_id)},
        ))
        db.session.commit()
    except Exception:
        logger.debug("log_suspicious failed", exc_info=True)
        try:
            db.session.rollback()
        except Exception:
            pass


def _extract_x_handle(answers, fields, telegram_username=None):
    """Find the participant's X/Twitter @handle among their submitted proof fields,
    so raid auto-verify can match them against likers / retweeters / followers.
    Prefers a 'username'-typed field, then any field whose key/label hints at X.
    Never falls back to the Telegram username (different namespace)."""
    answers = answers or {}
    for f in (fields or []):
        if getattr(f, "field_type", None) == "username" and answers.get(f.key):
            return answers.get(f.key)
    _HINTS = ("twitter", "x_user", "xuser", "x_handle", "handle", "username")
    for f in (fields or []):
        label = (getattr(f, "label", "") or "").lower()
        key = (getattr(f, "key", "") or "").lower()
        if any(h in label or h in key for h in _HINTS) and answers.get(f.key):
            return answers.get(f.key)
    return None


def create_submission(campaign, *, telegram_user_id, telegram_username=None,
                      answers=None, file_id=None, file_hash=None, forced_status=None,
                      task_id=None):
    """Shared submission pipeline used by BOTH the bot DM flow and the Mini App
    API. Validates window + one-per-user, decides status by verification mode,
    runs dedup, creates the row, logs fraud signals, and awards XP on verify.

    For a multi-task campaign, `task_id` selects the sub-task; the task's own
    verification_mode / platform / proof fields / reward then govern the
    submission. For a legacy single-task campaign, task_id is None and the
    campaign-level config is used.

    Returns (submission, error_message). error_message is a user-facing string
    when the submission was rejected (closed / duplicate / invalid link)."""
    from .models import EngagementSubmission, OfficialMember
    from .engagement_verify import validate_link_payload, validate_field_value

    tg_user_id = str(telegram_user_id)
    answers = answers or {}

    if not campaign.is_open:
        return None, "This campaign is closed. The submission window has ended."

    # Resolve the task (spec source) for a multi-task campaign.
    task = None
    if task_id is not None:
        task = EngagementTask.query.filter_by(id=task_id, campaign_id=campaign.id).first()
        if not task:
            return None, "That task is no longer available."
    elif campaign.tasks.count() > 0:
        return None, "Please choose a task to complete."

    # `spec` is the task (multi-task) or the campaign (legacy single-task).
    spec = task or campaign
    spec_fields = (task.custom_fields if task else campaign.custom_fields).all()

    allow_resubmit = bool((campaign.settings or {}).get("allow_resubmit"))
    if campaign.one_per_user:
        dupe = EngagementSubmission.query.filter_by(
            campaign_id=campaign.id, task_id=task_id, telegram_user_id=tg_user_id
        ).order_by(EngagementSubmission.created_at.desc()).first()
        # A prior rejected attempt may be resubmitted only if the campaign allows it.
        if dupe and not (dupe.status == "rejected" and allow_resubmit):
            return None, "You have already submitted for this task."

    # Per-field validation (also covers the Mini App path, which doesn't validate
    # field-by-field like the bot DM flow does). Screenshots validated elsewhere.
    for f in spec_fields:
        if f.field_type == "screenshot":
            continue
        raw = answers.get(f.key)
        if raw in (None, ""):
            if f.required:
                return None, f"Please provide: {f.label}"
            continue
        ok, normalized, err = validate_field_value(f.field_type, raw, platform=spec.platform)
        if not ok:
            return None, err
        answers[f.key] = normalized

    scope = "official" if campaign.telegram_group_id else "custom"
    member_id = None
    if scope == "official":
        m = OfficialMember.query.filter_by(
            telegram_group_id=campaign.telegram_group_id, telegram_user_id=tg_user_id,
        ).first()
        member_id = m.id if m else None

    # Status by verification mode (of the task when multi-task, else the campaign).
    if forced_status:
        status = forced_status
    elif spec.verification_mode == "honor":
        status = "verified"
    elif spec.verification_mode == "link":
        ok, reason = validate_link_payload(spec, answers)
        if not ok:
            return None, reason
        status = "verified"
    else:
        status = "pending"

    # X raid auto-verify (Pro/Enterprise): when the campaign has it enabled and a
    # key is configured, try to confirm the participant actually performed the
    # selected actions and upgrade pending → verified. Purely additive: it only
    # ever upgrades on a positive match and never auto-rejects (uncertainty stays
    # pending for manual review). See twitter_verify for the safety contract.
    if status == "pending" and campaign.type == "raid" and (campaign.settings or {}).get("auto_verify_x"):
        try:
            from . import twitter_verify
            if twitter_verify.enabled(campaign.owner_user_id):
                handle = _extract_x_handle(answers, spec_fields, telegram_username)
                if handle and twitter_verify.verify_raid(campaign, handle).get("overall") == "verified":
                    status = "verified"
        except Exception:
            logger.info("x raid auto-verify failed for campaign %s", campaign.id, exc_info=True)

    # Anti-fraud: duplicate proof / screenshot (dedup against the spec's fields).
    flagged, flag_reason = detect_duplicate(campaign, answers, file_hash, fields=spec_fields)
    if flagged:
        status = "pending"  # never auto-verify/reward a duplicate

    sub = EngagementSubmission(
        campaign_id=campaign.id,
        task_id=task_id,
        telegram_user_id=tg_user_id,
        telegram_username=telegram_username,
        member_id=member_id,
        scope=scope,
        status=status,
        payload=answers,
        file_id=file_id,
        file_hash=file_hash,
        flagged=flagged,
        flag_reason=flag_reason,
    )
    db.session.add(sub)
    db.session.commit()

    if flagged:
        log_suspicious(campaign.id, tg_user_id, flag_reason)
    if status == "verified":
        award_submission(campaign, sub)

    _submission_event(campaign, sub, "campaign.submission.created")
    if sub.status == "verified":
        _submission_event(campaign, sub, "campaign.submission.verified")
        _refresh_post_progress(campaign)

    return sub, None


def _refresh_post_progress(campaign):
    """Best-effort: nudge the live quota countdown in the group post after a
    submission verifies. No-op unless the campaign shows a target block (the
    refresh function self-guards and throttles)."""
    try:
        from .engagement_telegram import refresh_post_progress
        refresh_post_progress(campaign)
    except Exception:
        logger.debug("post-progress refresh failed for %s", getattr(campaign, "id", "?"), exc_info=True)


def award_submission(campaign, submission):
    """Idempotently grant the reward_xp to the submitter — the task's reward for a
    multi-task submission, else the campaign's. Best-effort: never raises, guarded
    by submission.rewarded so it can't double-award. Lineage-aware (custom →
    Member ledger, official → OfficialMember ledger)."""
    reward = campaign.reward_xp
    if submission.task_id:
        task = EngagementTask.query.get(submission.task_id)
        reward = task.reward_xp if task else 0
    if submission.rewarded or not reward:
        return
    try:
        if campaign.group_id:  # custom lineage
            from .database import DatabaseManager
            DatabaseManager.add_xp(
                campaign.group_id, submission.telegram_user_id,
                reward, submission.telegram_username,
            )
        else:  # official lineage
            from .models import OfficialMember, XpEvent
            m = OfficialMember.query.filter_by(
                telegram_group_id=campaign.telegram_group_id,
                telegram_user_id=str(submission.telegram_user_id),
            ).first()
            if m:
                m.xp = (m.xp or 0) + reward
                m.xp_1d = (m.xp_1d or 0) + reward
                m.xp_7d = (m.xp_7d or 0) + reward
                m.xp_30d = (m.xp_30d or 0) + reward
                db.session.flush()
                db.session.add(XpEvent(
                    scope="official", member_id=m.id,
                    amount=reward, reason=f"campaign:{campaign.id}",
                ))
        submission.rewarded = True
        db.session.commit()
    except Exception:
        logger.exception("award_submission failed for submission %s", getattr(submission, "id", "?"))
        try:
            db.session.rollback()
        except Exception:
            pass


# ── Per-action verify flow (Engagement V3) ────────────────────────────────────
# Raids / X social-tasks where the member does each action (Like/Repost/Comment/
# Quote/Follow) in the bot DM and taps Verify. One submission per (campaign,user),
# with each action's status stored in payload["actions"]. Likes auto-accept (X has
# no likers endpoint); the rest verify live via twitterapi.io for Pro/Enterprise
# owners, or fall back to manual review for free owners.

# Campaign goal-key (plural) → twitter_verify canonical action (singular).
GOAL_ACTIONS = [
    ("likes", "like"), ("retweets", "retweet"), ("comments", "comment"),
    ("quotes", "quote"), ("follows", "follow"),
]
GOAL_TO_ACTION = dict(GOAL_ACTIONS)
# Actions that can never be auto-verified (no read endpoint) → behavioural gate.
# These can't be proven via the API (X has no likers endpoint), so instead of
# blindly auto-accepting we require the participant to actually OPEN the post
# (tap the action button, which stamps opened_at) and let it SOAK for a few
# seconds before they may Verify — killing the "tap Verify without doing anything"
# abuse. See record_action_open + the like branch of verify_user_action.
AUTO_ACCEPT_ACTIONS = {"like"}
# Golden-period: seconds a user must wait between verify attempts on one action.
ACTION_RETRY_COOLDOWN_DEFAULT = 30
# Like soak: seconds that must pass AFTER the user opens the post before a like
# can be confirmed (per-campaign overridable via settings.like_soak_seconds).
LIKE_SOAK_SECONDS = 30


def _normalize_handle(value):
    try:
        from . import twitter_verify
        return twitter_verify.normalize_handle(value)
    except Exception:
        v = (value or "").strip().lstrip("@")
        return v or None


def _ensure_social_table():
    """Self-heal: create social_identities if a deploy shipped this code before the
    migration created the table (the per-action raid flow is the first thing to
    touch it, so a missing table would silently kill 'Join Raid'). Idempotent."""
    try:
        db.session.rollback()
    except Exception:
        pass
    try:
        SocialIdentity.__table__.create(bind=db.engine, checkfirst=True)
        return True
    except Exception:
        logger.exception("could not ensure social_identities table")
        return False


def get_social_handle(telegram_user_id, platform="x"):
    """The stored handle for this user+platform, or None — so the bot asks once."""
    try:
        row = SocialIdentity.query.filter_by(
            telegram_user_id=str(telegram_user_id), platform=platform
        ).first()
    except Exception:
        # Table not there yet on this deploy → create it and treat as "no handle".
        if not _ensure_social_table():
            return None
        return None
    return row.handle if row else None


def set_social_handle(telegram_user_id, handle, platform="x"):
    """Upsert the user's handle (normalized). Returns the stored handle or None if
    the input wasn't a usable username."""
    norm = _normalize_handle(handle)
    if not norm:
        return None
    for _attempt in (1, 2):
        try:
            row = SocialIdentity.query.filter_by(
                telegram_user_id=str(telegram_user_id), platform=platform
            ).first()
            if row:
                row.handle = norm
            else:
                row = SocialIdentity(telegram_user_id=str(telegram_user_id), platform=platform, handle=norm)
                db.session.add(row)
            db.session.commit()
            return norm
        except Exception:
            db.session.rollback()
            if _attempt == 1 and _ensure_social_table():
                continue  # table just created — retry the upsert once
            logger.exception("set_social_handle failed")
            return None
    return None


def campaign_owner_is_paid(campaign):
    """True if the campaign owner is on a paid tier (Pro/Enterprise). Live X
    verification is gated to paid owners; free owners get manual review."""
    return _is_paid(_campaign_owner(campaign))


def campaign_action_goals(campaign):
    """Ordered [(goal_key, action, target)] for the actions this campaign targets,
    reading raid_goals (raid) or social_targets (social_task)."""
    s = campaign.settings or {}
    goals = s.get("raid_goals") if campaign.type == "raid" else s.get("social_targets")
    goals = goals or {}
    return [(gk, act, goals[gk]) for gk, act in GOAL_ACTIONS if goals.get(gk)]


def has_action_flow(campaign):
    """True if this campaign uses the per-action DM verify flow (an X raid or an
    X social-task that targets at least one action)."""
    if campaign.type == "raid":
        return bool(campaign_action_goals(campaign))
    if campaign.type == "social_task":
        if (campaign.platform or "").lower() not in ("x", "twitter"):
            return False
        return bool(campaign_action_goals(campaign))
    return False


def _action_submission(campaign, telegram_user_id, telegram_username=None, create=False):
    """The single (campaign, user) submission that holds the per-action map. The
    action flow is campaign-level, so task_id is always NULL here."""
    sub = EngagementSubmission.query.filter_by(
        campaign_id=campaign.id, task_id=None,
        telegram_user_id=str(telegram_user_id),
    ).order_by(EngagementSubmission.created_at.desc()).first()
    if sub or not create:
        return sub
    scope = "official" if campaign.telegram_group_id else "custom"
    member_id = None
    if scope == "official":
        from .models import OfficialMember
        m = OfficialMember.query.filter_by(
            telegram_group_id=campaign.telegram_group_id,
            telegram_user_id=str(telegram_user_id),
        ).first()
        member_id = m.id if m else None
    sub = EngagementSubmission(
        campaign_id=campaign.id, task_id=None,
        telegram_user_id=str(telegram_user_id), telegram_username=telegram_username,
        member_id=member_id, scope=scope, status="pending",
        payload={"actions": {}},
    )
    db.session.add(sub)
    db.session.commit()
    return sub


def action_status_map(campaign, telegram_user_id):
    """{action: status} for this user's submission, or {} if none yet."""
    sub = _action_submission(campaign, telegram_user_id)
    if not sub:
        return {}
    return {a: (v or {}).get("status") for a, v in ((sub.payload or {}).get("actions") or {}).items()}


def action_retry_remaining(campaign, telegram_user_id, action):
    """Seconds left in the golden-period cooldown for this action, else 0."""
    sub = _action_submission(campaign, telegram_user_id)
    if not sub:
        return 0
    rec = ((sub.payload or {}).get("actions") or {}).get(action) or {}
    last = rec.get("last_attempt")
    if not last:
        return 0
    cooldown = int((campaign.settings or {}).get("action_retry_cooldown", ACTION_RETRY_COOLDOWN_DEFAULT))
    try:
        elapsed = (datetime.utcnow() - datetime.fromisoformat(last)).total_seconds()
    except Exception:
        return 0
    return max(0, int(cooldown - elapsed))


def record_action_open(campaign, *, telegram_user_id, telegram_username, action):
    """Record that the participant OPENED the post for `action` (tapped the action
    button). Stamps opened_at once so the like soak-gate can measure from the first
    real open. Returns the opened_at iso string. No-op (idempotent) if already set.

    Only meaningful for AUTO_ACCEPT actions (likes) — provable actions are proven by
    the API, not by an open — but it's harmless to record for any action."""
    sub = _action_submission(campaign, telegram_user_id, telegram_username, create=True)
    payload = dict(sub.payload or {})
    actions = dict(payload.get("actions") or {})
    rec = dict(actions.get(action) or {})
    if not rec.get("opened_at"):
        rec["opened_at"] = datetime.utcnow().isoformat()
        actions[action] = rec
        payload["actions"] = actions
        sub.payload = payload
        sub.telegram_username = telegram_username or sub.telegram_username
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(sub, "payload")
        db.session.commit()
    return rec["opened_at"]


def verify_user_action(campaign, *, telegram_user_id, telegram_username, action, handle):
    """Run/record one action verify for a participant and return a result dict
    {status, detail, completed} where status ∈ {verified, failed, manual, cooldown,
    need_open}.

    - like (and any AUTO_ACCEPT action) → can't be API-checked, so we gate on real
      behaviour: the user must have OPENED the post (need_open if not) and let it
      soak ≥ like_soak_seconds (cooldown if too soon); only then "verified". XP is
      still awarded; we never auto-pay a cash reward off a like.
    - retweet/comment/quote/follow → live twitterapi.io check for paid owners with
      auto-verify on; otherwise recorded "manual" for admin review.
    `completed` is True when this tap completed every targeted action → the whole
    submission flips to verified and XP is awarded."""
    sub = _action_submission(campaign, telegram_user_id, telegram_username, create=True)
    payload = dict(sub.payload or {})
    actions = dict(payload.get("actions") or {})
    rec = dict(actions.get(action) or {})
    now_iso = datetime.utcnow().isoformat()

    if action in AUTO_ACCEPT_ACTIONS:
        # Behavioural anti-fraud gate (no API can prove a like — X privatised them).
        opened = rec.get("opened_at")
        if not opened:
            return {"status": "need_open", "completed": False, "all_submitted": False,
                    "detail": "Tap the 👍 Like button to open the post and like it first, "
                              "then come back and tap Verify."}
        soak = int((campaign.settings or {}).get("like_soak_seconds", LIKE_SOAK_SECONDS))
        try:
            elapsed = (datetime.utcnow() - datetime.fromisoformat(opened)).total_seconds()
        except Exception:
            elapsed = soak  # unparseable timestamp → don't trap the user forever
        if elapsed < soak:
            wait = max(1, int(soak - elapsed))
            return {"status": "cooldown", "completed": False, "all_submitted": False,
                    "wait": wait,
                    "detail": f"Like the post, then tap Verify in {wait}s."}
        status, detail = "verified", "Accepted (post opened & liked)"
    else:
        # Record the attempt timestamp up-front so the golden-period cooldown
        # counts from each try (the bot checks action_retry_remaining before calling).
        rec["last_attempt"] = now_iso
        live = False
        try:
            from . import twitter_verify
            live = (campaign_owner_is_paid(campaign)
                    and bool((campaign.settings or {}).get("auto_verify_x"))
                    and twitter_verify.enabled(campaign.owner_user_id))
        except Exception:
            live = False
        if not live:
            status, detail = "manual", "Submitted for manual review"
        else:
            try:
                from . import twitter_verify
                tweet_id = twitter_verify.extract_tweet_id(campaign.task_url)
                target = ((campaign.settings or {}).get("raid_follow_target")
                          or twitter_verify.extract_author_handle(campaign.task_url))
                vstatus, vdetail = twitter_verify.verify_action(
                    action, username=handle, tweet_id=tweet_id, target_handle=target,
                    key=twitter_verify._key(campaign.owner_user_id),
                )
                if vstatus == "verified":
                    status, detail = "verified", vdetail or "Verified on X"
                elif vstatus == "failed":
                    status, detail = "failed", vdetail or "Not detected on X"
                else:  # unknown / manual → couldn't confirm; let them retry
                    status, detail = "failed", "Couldn't detect it yet — try again shortly"
            except Exception:
                logger.info("verify_user_action live check failed for %s", campaign.id, exc_info=True)
                status, detail = "failed", "Verification error — try again shortly"

    rec["status"] = status
    actions[action] = rec
    payload["actions"] = actions
    sub.payload = payload
    sub.telegram_username = telegram_username or sub.telegram_username
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(sub, "payload")

    # Completed when every targeted action is verified OR accepted-for-manual.
    targeted = [act for _, act, _ in campaign_action_goals(campaign)]
    done = all((actions.get(a) or {}).get("status") in ("verified", "manual") for a in targeted)
    all_provable_verified = all((actions.get(a) or {}).get("status") == "verified" for a in targeted)
    completed = False
    if done and all_provable_verified:
        sub.status = "verified"
        completed = True
    elif done:
        sub.status = "pending"   # has manual actions awaiting admin review
    db.session.commit()

    if completed:
        award_submission(campaign, sub)
        _refresh_post_progress(campaign)
        _submission_event(campaign, sub, "campaign.submission.verified")

    # `all_submitted` is True once every action has a result, even if some are
    # awaiting manual review (free owner) — lets the bot post a clear summary.
    return {"status": status, "detail": detail, "completed": completed, "all_submitted": done}


def action_extra_collected(campaign, telegram_user_id):
    """True if the participant already answered the campaign's extra proof fields
    (wallet/UID/link the bot can't read from X) in the per-action flow. Derived
    from key presence on the action submission payload — no separate marker."""
    keys = [f.key for f in campaign.custom_fields.all()]
    if not keys:
        return True
    sub = _action_submission(campaign, telegram_user_id)
    payload = (sub.payload or {}) if sub else {}
    return all(k in payload for k in keys)


def attach_action_extra_fields(campaign, telegram_user_id, answers, *, telegram_username=None):
    """Merge extra proof-field answers into the participant's per-action submission
    payload (stored top-level so they show in the dashboard / CSV like any field).
    Best-effort; returns True if stored."""
    sub = _action_submission(campaign, telegram_user_id, telegram_username, create=True)
    if not sub:
        return False
    payload = dict(sub.payload or {})
    payload.update(answers or {})
    sub.payload = payload
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(sub, "payload")
    db.session.commit()
    return True


# ── Leaderboards (premium) ─────────────────────────────────────────────────────

LEADERBOARD_DEFAULT_LIMIT = 50
LEADERBOARD_MAX_LIMIT = 200


def _campaign_owner(campaign):
    from .models import User
    if not campaign.owner_user_id:
        return None
    return User.query.get(campaign.owner_user_id)


def leaderboard_premium_ok(campaign):
    """ACCESS gate: per-campaign leaderboard DATA requires the campaign OWNER to be
    on a paid plan (not the viewer's). This is what the dashboard board and the
    API endpoints check, so a paid owner can always view rankings for their own
    campaign — independent of whether the board is surfaced publicly."""
    return _is_paid(_campaign_owner(campaign))


def _leaderboard_default_on(campaign):
    """Intelligent default for whether to SURFACE the leaderboard when the owner
    hasn't set an explicit preference. A ranked board is meaningful for
    competitive / XP-bearing campaigns; it isn't for one-shot data collection
    (UID / wallet / KYC / proof), where everyone submits once and there's nothing
    to rank."""
    if (campaign.reward_xp or 0) > 0:
        return True
    try:
        if campaign.tasks.count() > 0:  # multi-task → ranked by tasks completed
            return True
    except Exception:
        pass
    return campaign.type in ("social_task", "raid")


def leaderboard_visible(campaign):
    """SURFACING gate: whether to show the 🏆 leaderboard button in the group post
    and to participants. Requires the owner to be paid AND the board to be on —
    an explicit settings['leaderboard'] True/False wins; otherwise an intelligent
    default decides (on for XP/multi-task/social/raid, off for pure collection)."""
    pref = (campaign.settings or {}).get("leaderboard")
    if pref is False:
        return False
    if not leaderboard_premium_ok(campaign):
        return False
    if pref is True:
        return True
    return _leaderboard_default_on(campaign)


# Back-compat alias (kept so any external caller keeps working).
def leaderboard_enabled(campaign):
    return leaderboard_visible(campaign)


def campaign_leaderboard(campaign, *, limit=LEADERBOARD_DEFAULT_LIMIT, offset=0,
                         enforce_premium=True, require_visible=False, highlight_user_id=None):
    """Ranked participant board for ONE campaign (premium).

    Ranking is by campaign contribution, derived from the campaign's own VERIFIED
    submissions — the same rows award_submission credits XP from, so the board
    lines up with the XP ledger without re-reading it:
      • primary  → total XP earned (sum of completed-task rewards) (desc)
      • then     → number of verified submissions / tasks completed (desc)
      • tiebreak → earliest verification time (asc) — first to complete ranks higher

    xp_earned sums the reward of each completed task (task.reward_xp for a
    multi-task submission, else the campaign's reward_xp). For a single-task
    campaign this is verified_count * reward_xp — unchanged.

    Returns {campaign_id, campaign_title, reward_xp, total_participants, limit,
    offset, entries:[…], me:{…}|None}. `me` is the highlight_user_id's row (with
    its true rank) even when it falls outside the requested page.
    """
    if enforce_premium and not leaderboard_premium_ok(campaign):
        raise EngagementError(
            "Per-campaign leaderboards require a Pro or Enterprise subscription.",
            403, code="FEATURE_REQUIRES_PRO",
        )
    # Participant-facing surfaces (Mini App card, bot deep-link) honor the owner's
    # visibility choice; the admin dashboard passes require_visible=False so the
    # owner can always inspect rankings for their own campaign.
    if require_visible and not leaderboard_visible(campaign):
        raise EngagementError("The leaderboard isn't shown for this campaign.", 403)

    limit = max(1, min(_coerce_int(limit, "limit", minimum=1) or LEADERBOARD_DEFAULT_LIMIT,
                       LEADERBOARD_MAX_LIMIT))
    offset = max(0, _coerce_int(offset, "offset") or 0)
    default_reward = campaign.reward_xp or 0
    task_rewards = {t.id: (t.reward_xp or 0) for t in campaign.tasks.all()}

    # Aggregate each participant's verified submissions. Ordered newest-first so
    # the first username seen per user is the most recent.
    agg = {}
    unames = {}
    for s in (
        EngagementSubmission.query
        .filter(EngagementSubmission.campaign_id == campaign.id)
        .filter(EngagementSubmission.status == "verified")
        .order_by(EngagementSubmission.created_at.desc())
        .all()
    ):
        uid = s.telegram_user_id
        reward = task_rewards.get(s.task_id, default_reward) if s.task_id else default_reward
        a = agg.get(uid)
        if a is None:
            a = agg[uid] = {"count": 0, "xp": 0, "first": None, "last": None}
        a["count"] += 1
        a["xp"] += reward
        if s.reviewed_at and (a["first"] is None or s.reviewed_at < a["first"]):
            a["first"] = s.reviewed_at
        if s.created_at and (a["last"] is None or s.created_at > a["last"]):
            a["last"] = s.created_at
        if s.telegram_username and uid not in unames:
            unames[uid] = s.telegram_username

    # Highest XP first, then most tasks done, then earliest completion (null last).
    ordered = sorted(
        agg.items(),
        key=lambda kv: (-kv[1]["xp"], -kv[1]["count"], kv[1]["first"] or datetime.max),
    )

    def _entry(rank, uid, a):
        return {
            "rank": rank,
            "telegram_user_id": uid,
            "telegram_username": unames.get(uid),
            "verified_count": a["count"],
            "xp_earned": a["xp"],
            "first_verified_at": a["first"].isoformat() if a["first"] else None,
            "last_activity_at": a["last"].isoformat() if a["last"] else None,
        }

    entries = [_entry(i + 1, uid, a) for i, (uid, a) in enumerate(ordered)]
    reward_xp = default_reward

    me = None
    if highlight_user_id is not None:
        hid = str(highlight_user_id)
        me = next((e for e in entries if e["telegram_user_id"] == hid), None)

    return {
        "campaign_id": campaign.id,
        "campaign_title": campaign.title,
        "reward_xp": reward_xp,
        "total_participants": len(entries),
        "limit": limit,
        "offset": offset,
        "entries": entries[offset:offset + limit],
        "me": me,
    }


def submissions_csv(campaign):
    """Return a CSV string of all submissions for a campaign."""
    # Union of campaign-level and all task-level field keys (multi-task safe).
    field_keys = [f.key for f in campaign.custom_fields.all()]
    task_titles = {}
    for t in campaign.tasks.all():
        task_titles[t.id] = t.title
        for f in t.custom_fields.all():
            if f.key not in field_keys:
                field_keys.append(f.key)
    subs = campaign.submissions.order_by(EngagementSubmission.created_at.asc()).all()
    # Also surface any extra payload keys that aren't a configured field — e.g. a
    # bot-injected default proof field on a review task with no custom fields — so
    # the proof never silently drops out of the export.
    has_actions = False
    for s in subs:
        for k in (s.payload or {}):
            if k == "actions":
                has_actions = True  # per-action verify map → its own flattened column
                continue
            if k not in field_keys:
                field_keys.append(k)
    header = [
        "submission_id", "task_id", "task_title", "telegram_user_id", "telegram_username",
        "status", "created_at", "reviewed_at", "reviewed_by", "review_reason",
    ] + field_keys + (["actions"] if has_actions else []) + ["file_id", "file_hash"]

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    for s in subs:
        payload = s.payload or {}
        row = [
            s.id, s.task_id or "", task_titles.get(s.task_id, ""),
            s.telegram_user_id, s.telegram_username or "",
            s.status,
            s.created_at.isoformat() if s.created_at else "",
            s.reviewed_at.isoformat() if s.reviewed_at else "",
            s.reviewed_by or "", s.review_reason or "",
        ] + [payload.get(k, "") for k in field_keys]
        if has_actions:
            amap = payload.get("actions") or {}
            row.append("; ".join(
                f"{a}={(v or {}).get('status', '')}" for a, v in amap.items()
            ) if isinstance(amap, dict) else "")
        row += [s.file_id or "", s.file_hash or ""]
        writer.writerow(row)
    return buf.getvalue()
