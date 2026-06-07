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
    EngagementSubmission,
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

def _check_create_gating(user, *, scope, group_id, telegram_group_id, status, verification_mode, platform, field_count):
    """Raise EngagementError(403) if a free/expired user exceeds free limits."""
    if _is_paid(user):
        return

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

    _check_create_gating(
        user, scope=scope, group_id=group_id, telegram_group_id=telegram_group_id,
        status=status, verification_mode=vmode, platform=platform, field_count=len(fields_in),
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

    db.session.commit()
    _maybe_publish(campaign)
    return campaign


def _replace_custom_fields(campaign, fields_in):
    """Validate + (re)create custom fields for a campaign. Caller commits."""
    # Drop existing
    for f in campaign.custom_fields.all():
        db.session.delete(f)
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
        db.session.add(EngagementCustomField(
            campaign_id=campaign.id,
            key=key,
            label=label[:200],
            field_type=ftype,
            required=bool(raw.get("required", True)),
            order=_coerce_int(raw.get("order"), "order") or idx,
        ))


# ── Update / lifecycle ────────────────────────────────────────────────────────

# Fields a PATCH may edit directly (content edits, distinct from lifecycle action).
_EDITABLE_FIELDS = {
    "title", "description", "task_url", "platform", "reward_xp",
    "reward_label", "starts_at", "ends_at", "max_participants",
    "one_per_user", "pin_message", "verification_mode", "settings",
}


def update_campaign(campaign, data):
    """Apply a content edit and/or a lifecycle `action`. Returns the campaign."""
    data = data or {}

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

    db.session.commit()
    if action == "publish":
        _maybe_publish(campaign)
    return campaign


def _maybe_publish(campaign):
    """Post the campaign to Telegram on first activation (best-effort).

    Guarded by telegram_message_id so a pause→reopen never double-posts.
    Publishing failures never break the API (the dashboard still works; the
    admin can re-trigger by toggling status)."""
    if campaign.status != "active" or campaign.telegram_message_id:
        return
    try:
        from .engagement_telegram import publish_campaign
        publish_campaign(campaign)
    except Exception:
        logger.exception("campaign publish hook failed for %s", getattr(campaign, "id", "?"))


# ── Submissions ───────────────────────────────────────────────────────────────

def list_submissions(campaign, *, status=None, limit=1000):
    q = campaign.submissions
    if status:
        q = q.filter(EngagementSubmission.status == status)
    rows = q.order_by(EngagementSubmission.created_at.desc()).limit(limit).all()
    return [s.to_dict() for s in rows]


def review_submission(campaign, submission_id, action, *, reviewed_by=None, reason=None):
    """Approve or reject a submission. XP reward on approval is wired in Phase 4
    (kept idempotent via EngagementSubmission.rewarded)."""
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
        award_submission(campaign, sub)
    return sub


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


def detect_duplicate(campaign, answers, file_hash):
    """Return (is_dup, reason) if a normalized proof value or screenshot hash has
    already been used by another participant in this group. Anti-farming guard."""
    answers = answers or {}
    # Build the set of (key → normalized value) we care about.
    dedup_keys = {
        f.key for f in campaign.custom_fields.all() if f.field_type in _DEDUP_FIELD_TYPES
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


def create_submission(campaign, *, telegram_user_id, telegram_username=None,
                      answers=None, file_id=None, file_hash=None, forced_status=None):
    """Shared submission pipeline used by BOTH the bot DM flow and the Mini App
    API. Validates window + one-per-user, decides status by verification mode,
    runs dedup, creates the row, logs fraud signals, and awards XP on verify.

    Returns (submission, error_message). error_message is a user-facing string
    when the submission was rejected (closed / duplicate / invalid link)."""
    from .models import EngagementSubmission, OfficialMember
    from .engagement_verify import validate_link_payload

    tg_user_id = str(telegram_user_id)
    answers = answers or {}

    if not campaign.is_open:
        return None, "This campaign is closed. The submission window has ended."

    if campaign.one_per_user:
        dupe = EngagementSubmission.query.filter_by(
            campaign_id=campaign.id, telegram_user_id=tg_user_id
        ).first()
        if dupe:
            return None, "You have already submitted for this task."

    scope = "official" if campaign.telegram_group_id else "custom"
    member_id = None
    if scope == "official":
        m = OfficialMember.query.filter_by(
            telegram_group_id=campaign.telegram_group_id, telegram_user_id=tg_user_id,
        ).first()
        member_id = m.id if m else None

    # Status by verification mode.
    if forced_status:
        status = forced_status
    elif campaign.verification_mode == "honor":
        status = "verified"
    elif campaign.verification_mode == "link":
        ok, reason = validate_link_payload(campaign, answers)
        if not ok:
            return None, reason
        status = "verified"
    else:
        status = "pending"

    # Anti-fraud: duplicate proof / screenshot.
    flagged, flag_reason = detect_duplicate(campaign, answers, file_hash)
    if flagged:
        status = "pending"  # never auto-verify/reward a duplicate

    sub = EngagementSubmission(
        campaign_id=campaign.id,
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

    return sub, None


def award_submission(campaign, submission):
    """Idempotently grant the campaign's reward_xp to the submitter. Best-effort:
    never raises, guarded by submission.rewarded so it can't double-award.
    Lineage-aware (custom → Member ledger, official → OfficialMember ledger)."""
    if submission.rewarded or not campaign.reward_xp:
        return
    try:
        if campaign.group_id:  # custom lineage
            from .database import DatabaseManager
            DatabaseManager.add_xp(
                campaign.group_id, submission.telegram_user_id,
                campaign.reward_xp, submission.telegram_username,
            )
        else:  # official lineage
            from .models import OfficialMember, XpEvent
            m = OfficialMember.query.filter_by(
                telegram_group_id=campaign.telegram_group_id,
                telegram_user_id=str(submission.telegram_user_id),
            ).first()
            if m:
                m.xp = (m.xp or 0) + campaign.reward_xp
                m.xp_1d = (m.xp_1d or 0) + campaign.reward_xp
                m.xp_7d = (m.xp_7d or 0) + campaign.reward_xp
                m.xp_30d = (m.xp_30d or 0) + campaign.reward_xp
                db.session.flush()
                db.session.add(XpEvent(
                    scope="official", member_id=m.id,
                    amount=campaign.reward_xp, reason=f"campaign:{campaign.id}",
                ))
        submission.rewarded = True
        db.session.commit()
    except Exception:
        logger.exception("award_submission failed for submission %s", getattr(submission, "id", "?"))
        try:
            db.session.rollback()
        except Exception:
            pass


def submissions_csv(campaign):
    """Return a CSV string of all submissions for a campaign."""
    fields = campaign.custom_fields.all()
    field_keys = [f.key for f in fields]
    header = [
        "submission_id", "telegram_user_id", "telegram_username",
        "status", "created_at", "reviewed_at", "reviewed_by", "review_reason",
    ] + field_keys + ["file_id", "file_hash"]

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    for s in campaign.submissions.order_by(EngagementSubmission.created_at.asc()).all():
        payload = s.payload or {}
        row = [
            s.id, s.telegram_user_id, s.telegram_username or "",
            s.status,
            s.created_at.isoformat() if s.created_at else "",
            s.reviewed_at.isoformat() if s.reviewed_at else "",
            s.reviewed_by or "", s.review_reason or "",
        ] + [payload.get(k, "") for k in field_keys] + [s.file_id or "", s.file_hash or ""]
        writer.writerow(row)
    return buf.getvalue()
