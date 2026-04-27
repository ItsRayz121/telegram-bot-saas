"""
API routes for the official Telegizer bot group ecosystem.

Endpoints:
  GET  /api/telegram-groups              — list user's linked groups
  POST /api/telegram-groups/link         — link a group using a code
  GET  /api/telegram-groups/<id>         — get single group
  PUT  /api/telegram-groups/<id>         — update group settings
  DELETE /api/telegram-groups/<id>       — unlink group
  POST /api/telegram-groups/link-code    — admin: generate code manually (fallback)
  GET  /api/telegram-groups/<id>/events  — event log for a group
  GET  /api/telegram-groups/<id>/commands — list custom commands (proxy)
  GET/POST /api/telegram-groups/<id>/scheduled-messages — CRUD official scheduled messages
  GET/POST /api/telegram-groups/<id>/polls              — CRUD official polls
  GET/POST/DELETE /api/telegram-groups/<id>/knowledge   — CRUD knowledge base documents
  GET/POST/PUT/DELETE /api/telegram-groups/<id>/auto-responses — CRUD auto-responses
  GET/POST/DELETE /api/telegram-groups/<id>/invite-links — CRUD invite links
  GET/POST/DELETE /api/telegram-groups/<id>/api-key     — CRUD AI provider API key
"""

from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..models import db, User, TelegramGroup, TelegramGroupLinkCode, BotEvent, OfficialWarning, OfficialMember, Bot, CustomBot, OfficialScheduledMessage, OfficialPoll, KnowledgeDocument, AutoResponse, InviteLink, UserApiKey
from ..middleware.rate_limit import rate_limit
from ..config import Config
from ..group_defaults import apply_group_defaults

tg_groups_bp = Blueprint("telegram_groups", __name__, url_prefix="/api/telegram-groups")


def _current_user():
    return User.query.get(int(get_jwt_identity()))


def _owns_group(user_id: int, group_id: str) -> "TelegramGroup | None":
    """Return group only if the user owns it."""
    return TelegramGroup.query.filter_by(
        telegram_group_id=group_id,
        owner_user_id=user_id,
        is_disabled=False,
    ).first()


# ── List user's linked groups ──────────────────────────────────────────────────

@tg_groups_bp.route("", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def list_groups():
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    groups = TelegramGroup.query.filter_by(
        owner_user_id=user.id,
        is_disabled=False,
    ).order_by(TelegramGroup.linked_at.desc()).all()

    groups_data = [g.to_dict() for g in groups]

    # Also surface groups that were linked via the legacy bot_manager runner
    # (stored in the old Bot/Group tables, never migrated to TelegramGroup).
    new_system_tg_ids = {g.telegram_group_id for g in groups}

    old_bots = Bot.query.filter_by(user_id=user.id).all()
    custom_bots = CustomBot.query.filter_by(owner_user_id=user.id).all()
    custom_bot_id_by_username = {cb.bot_username: cb.id for cb in custom_bots if cb.bot_username}

    # Build lookup: custom_bot.id → display name
    custom_bot_name_by_id = {
        cb.id: (cb.bot_name or f"@{cb.bot_username}")
        for cb in custom_bots
    }
    custom_bot_username_by_id = {cb.id: cb.bot_username for cb in custom_bots}

    for old_bot in old_bots:
        for grp in old_bot.groups:
            if grp.telegram_group_id in new_system_tg_ids:
                continue  # already present in TelegramGroup
            linked_bot_id = custom_bot_id_by_username.get(old_bot.bot_username)
            groups_data.append({
                "id": None,
                "telegram_group_id": grp.telegram_group_id,
                "title": grp.group_name or "Unknown Group",
                "username": None,
                "invite_link": None,
                "owner_user_id": user.id,
                "linked_via_bot_type": "custom",
                "linked_bot_id": linked_bot_id,
                "linked_bot_name": custom_bot_name_by_id.get(linked_bot_id) if linked_bot_id else None,
                "linked_bot_username": custom_bot_username_by_id.get(linked_bot_id) if linked_bot_id else None,
                "bot_status": "active" if old_bot.is_active else "inactive",
                "bot_permissions": None,
                "linked_at": None,
                "last_activity": old_bot.last_active.isoformat() if old_bot.last_active else None,
                "is_disabled": False,
                "created_at": None,
                "updated_at": None,
                "member_count": grp.telegram_member_count or 0,
                "description": None,
                "source": "legacy",
            })

    # Inject linked_bot_name into groups already in the TelegramGroup table
    for g in groups_data:
        if g.get("linked_bot_id") and "linked_bot_name" not in g:
            bid = g["linked_bot_id"]
            g["linked_bot_name"] = custom_bot_name_by_id.get(bid)
            g["linked_bot_username"] = custom_bot_username_by_id.get(bid)

    return jsonify({"groups": groups_data})


# ── Link a group via code ──────────────────────────────────────────────────────

@tg_groups_bp.route("/link", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def link_group():
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json() or {}
    code = (data.get("code") or "").strip().upper()
    if not code:
        return jsonify({"error": "Verification code is required"}), 400

    link_code = TelegramGroupLinkCode.query.filter_by(code=code).first()
    if not link_code:
        return jsonify({"error": "Invalid verification code"}), 400

    if not link_code.is_valid:
        return jsonify({"error": "Code has expired or already been used"}), 400

    # Check not already claimed by another user
    tg = TelegramGroup.query.filter_by(
        telegram_group_id=link_code.telegram_group_id
    ).first()

    if not tg:
        return jsonify({"error": "Group not found. Make sure the bot is in the group."}), 404

    if tg.owner_user_id and tg.owner_user_id != user.id:
        return jsonify({"error": "This group is already linked to another account"}), 409

    # Enforce per-tier official group limit
    max_groups = Config.MAX_OFFICIAL_GROUPS.get(user.subscription_tier, 3)
    if max_groups != -1:
        current_count = TelegramGroup.query.filter_by(
            owner_user_id=user.id, is_disabled=False
        ).count()
        if tg.owner_user_id != user.id and current_count >= max_groups:
            return jsonify({
                "error": (
                    f"Your {user.subscription_tier.capitalize()} plan allows {max_groups} "
                    f"linked group(s). Upgrade to Pro to link unlimited groups."
                ),
                "code": "GROUP_LIMIT_REACHED",
                "limit": max_groups,
            }), 403

    # Mark code used and link the group
    link_code.used_at = datetime.utcnow()
    tg.owner_user_id = user.id
    tg.bot_status = "active"
    tg.linked_at = datetime.utcnow()
    tg.linked_via_bot_type = "official"
    # Safety net: apply defaults if the group was created before defaults existed.
    apply_group_defaults(tg)
    db.session.commit()

    # Log event
    ev = BotEvent(
        telegram_group_id=tg.telegram_group_id,
        event_type="group_linked",
        message=f"Group linked by user {user.id}",
        metadata_={"user_id": user.id, "user_email": user.email},
    )
    db.session.add(ev)
    db.session.commit()

    return jsonify({"group": tg.to_dict(), "message": "Group linked successfully"})


# ── Get single group ───────────────────────────────────────────────────────────

@tg_groups_bp.route("/<group_id>", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def get_group(group_id):
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    return jsonify({"group": tg.to_dict()})


# ── Update group settings (title, invite link, etc.) ──────────────────────────

@tg_groups_bp.route("/<group_id>", methods=["PUT"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def update_group(group_id):
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    data = request.get_json() or {}
    if "title" in data and data["title"]:
        tg.title = data["title"][:255]
    if "invite_link" in data:
        tg.invite_link = data["invite_link"]

    db.session.commit()
    return jsonify({"group": tg.to_dict()})


# ── Unlink / remove group ──────────────────────────────────────────────────────

@tg_groups_bp.route("/<group_id>", methods=["DELETE"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def unlink_group(group_id):
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    tg.owner_user_id = None
    tg.bot_status = "pending"
    tg.linked_at = None
    db.session.commit()

    ev = BotEvent(
        telegram_group_id=tg.telegram_group_id,
        event_type="group_unlinked",
        message=f"Group unlinked by user {user.id}",
        metadata_={"user_id": user.id},
    )
    db.session.add(ev)
    db.session.commit()

    return jsonify({"message": "Group unlinked successfully"})


# ── Group event log ────────────────────────────────────────────────────────────

@tg_groups_bp.route("/<group_id>/events", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def get_group_events(group_id):
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 100)

    paginated = BotEvent.query.filter_by(
        telegram_group_id=group_id
    ).order_by(BotEvent.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        "events": [e.to_dict() for e in paginated.items],
        "total": paginated.total,
        "page": page,
        "pages": paginated.pages,
    })


# ── Pending groups (bot added but not linked) ──────────────────────────────────

@tg_groups_bp.route("/pending", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def get_pending_groups():
    """Groups where bot is present but not yet linked to any user."""
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    # Return unlinked groups — user must supply link code to claim
    pending = TelegramGroup.query.filter_by(
        owner_user_id=None,
        bot_status="pending",
    ).order_by(TelegramGroup.created_at.desc()).limit(50).all()

    return jsonify({"groups": [g.to_dict() for g in pending]})


# ── Warnings ───────────────────────────────────────────────────────────────────

@tg_groups_bp.route("/<group_id>/warnings", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def list_warnings(group_id):
    """List all active warnings in a group, optionally filtered by user."""
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    target_user_id = request.args.get("user_id")
    q = OfficialWarning.query.filter_by(telegram_group_id=group_id)
    if target_user_id:
        q = q.filter_by(target_user_id=str(target_user_id))

    include_inactive = request.args.get("include_inactive", "false").lower() == "true"
    if not include_inactive:
        q = q.filter_by(active=True)

    warnings = q.order_by(OfficialWarning.created_at.desc()).limit(200).all()
    return jsonify({"warnings": [w.to_dict() for w in warnings]}), 200


@tg_groups_bp.route("/<group_id>/warnings/<int:warning_id>", methods=["DELETE"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def remove_warning(group_id, warning_id):
    """Deactivate (soft-delete) a specific warning."""
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    w = OfficialWarning.query.filter_by(id=warning_id, telegram_group_id=group_id).first()
    if not w:
        return jsonify({"error": "Warning not found"}), 404

    w.active = False
    db.session.commit()
    return jsonify({"message": "Warning removed"}), 200


# ── Mod-log (BotEvent stream for mod actions) ──────────────────────────────────

@tg_groups_bp.route("/<group_id>/mod-log", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def get_mod_log(group_id):
    """Return moderation events (ban/kick/mute/warn/purge) for a group."""
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    MOD_EVENT_TYPES = (
        "mod_warning", "mod_ban", "mod_kick", "mod_mute", "mod_unmute",
        "mod_tempban", "mod_purge", "automod_action",
    )
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 100)

    paginated = BotEvent.query.filter(
        BotEvent.telegram_group_id == group_id,
        BotEvent.event_type.in_(MOD_EVENT_TYPES),
    ).order_by(BotEvent.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        "events": [e.to_dict() for e in paginated.items],
        "total": paginated.total,
        "page": page,
        "pages": paginated.pages,
    }), 200


# ── XP Leaderboard ─────────────────────────────────────────────────────────────

@tg_groups_bp.route("/<group_id>/leaderboard", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def get_leaderboard(group_id):
    """Return top members by XP for a group."""
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    limit = min(request.args.get("limit", 20, type=int), 100)
    members = (
        OfficialMember.query.filter_by(telegram_group_id=group_id)
        .order_by(OfficialMember.xp.desc())
        .limit(limit)
        .all()
    )
    return jsonify({"members": [m.to_dict() for m in members]}), 200


# ── Official-group Digest ──────────────────────────────────────────────────────

@tg_groups_bp.route("/<group_id>/digest", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def get_digest_settings(group_id):
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    digest = (tg.settings or {}).get("digest", {})
    return jsonify({"digest": digest}), 200


@tg_groups_bp.route("/<group_id>/digest", methods=["PUT"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def update_digest_settings(group_id):
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    data = request.get_json() or {}
    settings = dict(tg.settings or {})
    settings["digest"] = {
        "daily":   bool(data.get("daily", False)),
        "weekly":  bool(data.get("weekly", False)),
        "monthly": bool(data.get("monthly", False)),
        "send_to_group": bool(data.get("send_to_group", True)),
    }
    tg.settings = settings
    db.session.commit()
    return jsonify({"digest": settings["digest"]}), 200


@tg_groups_bp.route("/<group_id>/digest/send", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=5)
def send_digest_now(group_id):
    """Trigger an on-demand digest for this group."""
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    from ..official_bot import _runner
    try:
        import asyncio
        from ..official_bot import _build_official_digest, _send_official_digest
        loop = _runner.loop
        if not loop or not loop.is_running():
            return jsonify({"error": "Official bot is not running"}), 503

        future = asyncio.run_coroutine_threadsafe(
            _send_official_digest(_runner.application.bot, tg, days=7),
            loop,
        )
        future.result(timeout=30)
        return jsonify({"message": "Digest sent"}), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ── Official Scheduled Messages ───────────────────────────────────────────────

@tg_groups_bp.route("/<group_id>/scheduled-messages", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def list_official_scheduled_messages(group_id):
    user = _current_user()
    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404
    msgs = OfficialScheduledMessage.query.filter_by(
        telegram_group_id=group_id
    ).order_by(OfficialScheduledMessage.send_at.asc()).all()
    return jsonify([m.to_dict() for m in msgs])


@tg_groups_bp.route("/<group_id>/scheduled-messages", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def create_official_scheduled_message(group_id):
    user = _current_user()
    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    data = request.get_json() or {}
    title = (data.get("title") or "").strip()
    message_text = (data.get("message_text") or "").strip()
    send_at_raw = data.get("send_at")
    if not title or not message_text or not send_at_raw:
        return jsonify({"error": "title, message_text, and send_at are required"}), 400

    try:
        send_at = datetime.fromisoformat(send_at_raw.replace("Z", "+00:00")).replace(tzinfo=None)
    except (ValueError, AttributeError):
        return jsonify({"error": "Invalid send_at format — use ISO 8601"}), 400

    msg = OfficialScheduledMessage(
        telegram_group_id=group_id,
        title=title,
        message_text=message_text,
        media_url=data.get("media_url"),
        buttons=data.get("buttons"),
        send_at=send_at,
        repeat_interval=data.get("repeat_interval"),
        stop_date=datetime.fromisoformat(data["stop_date"].replace("Z", "+00:00")).replace(tzinfo=None) if data.get("stop_date") else None,
        pin_message=bool(data.get("pin_message", False)),
        auto_delete_after=data.get("auto_delete_after"),
        link_preview_enabled=bool(data.get("link_preview_enabled", True)),
        topic_id=data.get("topic_id"),
        timezone=data.get("timezone", "UTC"),
    )
    db.session.add(msg)
    db.session.commit()
    return jsonify(msg.to_dict()), 201


@tg_groups_bp.route("/<group_id>/scheduled-messages/<int:msg_id>", methods=["PUT"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def update_official_scheduled_message(group_id, msg_id):
    user = _current_user()
    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    msg = OfficialScheduledMessage.query.filter_by(id=msg_id, telegram_group_id=group_id).first()
    if not msg:
        return jsonify({"error": "Message not found"}), 404

    data = request.get_json() or {}
    if "title" in data:
        msg.title = data["title"]
    if "message_text" in data:
        msg.message_text = data["message_text"]
    if "send_at" in data:
        try:
            msg.send_at = datetime.fromisoformat(data["send_at"].replace("Z", "+00:00")).replace(tzinfo=None)
        except (ValueError, AttributeError):
            return jsonify({"error": "Invalid send_at format"}), 400
    for field in ("media_url", "buttons", "repeat_interval", "pin_message",
                  "auto_delete_after", "link_preview_enabled", "topic_id", "timezone"):
        if field in data:
            setattr(msg, field, data[field])
    if "stop_date" in data:
        msg.stop_date = datetime.fromisoformat(data["stop_date"].replace("Z", "+00:00")).replace(tzinfo=None) if data["stop_date"] else None
    db.session.commit()
    return jsonify(msg.to_dict())


@tg_groups_bp.route("/<group_id>/scheduled-messages/<int:msg_id>", methods=["DELETE"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def delete_official_scheduled_message(group_id, msg_id):
    user = _current_user()
    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    msg = OfficialScheduledMessage.query.filter_by(id=msg_id, telegram_group_id=group_id).first()
    if not msg:
        return jsonify({"error": "Message not found"}), 404

    db.session.delete(msg)
    db.session.commit()
    return jsonify({"message": "Deleted"}), 200


# ── Official Polls ─────────────────────────────────────────────────────────────

@tg_groups_bp.route("/<group_id>/polls", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def list_official_polls(group_id):
    user = _current_user()
    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404
    polls = OfficialPoll.query.filter_by(
        telegram_group_id=group_id
    ).order_by(OfficialPoll.scheduled_at.asc()).all()
    return jsonify([p.to_dict() for p in polls])


@tg_groups_bp.route("/<group_id>/polls", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def create_official_poll(group_id):
    user = _current_user()
    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    data = request.get_json() or {}
    question = (data.get("question") or "").strip()
    options = data.get("options") or []
    if not question or len(options) < 2:
        return jsonify({"error": "question and at least 2 options are required"}), 400
    if len(options) > 10:
        return jsonify({"error": "Telegram allows at most 10 poll options"}), 400

    scheduled_at = None
    if data.get("scheduled_at"):
        try:
            scheduled_at = datetime.fromisoformat(data["scheduled_at"].replace("Z", "+00:00")).replace(tzinfo=None)
        except (ValueError, AttributeError):
            return jsonify({"error": "Invalid scheduled_at format — use ISO 8601"}), 400

    poll = OfficialPoll(
        telegram_group_id=group_id,
        question=question,
        options=options,
        correct_option_index=data.get("correct_option_index"),
        is_quiz=bool(data.get("is_quiz", False)),
        is_anonymous=bool(data.get("is_anonymous", True)),
        allows_multiple=bool(data.get("allows_multiple", False)),
        explanation=data.get("explanation"),
        scheduled_at=scheduled_at,
        timezone=data.get("timezone", "UTC"),
    )
    db.session.add(poll)
    db.session.commit()
    return jsonify(poll.to_dict()), 201


@tg_groups_bp.route("/<group_id>/polls/<int:poll_id>", methods=["DELETE"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def delete_official_poll(group_id, poll_id):
    user = _current_user()
    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    poll = OfficialPoll.query.filter_by(id=poll_id, telegram_group_id=group_id).first()
    if not poll:
        return jsonify({"error": "Poll not found"}), 404

    db.session.delete(poll)
    db.session.commit()
    return jsonify({"message": "Deleted"}), 200


# ── Knowledge Base ─────────────────────────────────────────────────────────────

@tg_groups_bp.route("/<group_id>/knowledge", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def list_knowledge_docs(group_id):
    user = _current_user()
    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    docs = KnowledgeDocument.query.filter_by(
        telegram_group_id=group_id
    ).order_by(KnowledgeDocument.created_at.desc()).all()
    return jsonify({"documents": [d.to_dict() for d in docs]}), 200


@tg_groups_bp.route("/<group_id>/knowledge", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def upload_knowledge_doc(group_id):
    user = _current_user()
    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    f = request.files["file"]
    filename = f.filename or "upload"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "txt"
    if ext not in ("txt", "md", "pdf", "docx"):
        return jsonify({"error": "Unsupported file type. Use txt, md, pdf, or docx."}), 400

    content_bytes = f.read()
    if len(content_bytes) > 10 * 1024 * 1024:
        return jsonify({"error": "File too large (max 10 MB)"}), 413

    from ..bot_features.knowledge_base import KnowledgeBaseSystem
    from flask import current_app
    kb = KnowledgeBaseSystem(current_app._get_current_object())
    doc_dict, err = kb.process_document(
        group_id=None,
        filename=filename,
        file_type=ext,
        content_bytes=content_bytes,
        telegram_group_id=group_id,
    )
    if err:
        return jsonify({"error": err}), 422
    return jsonify({"document": doc_dict}), 201


@tg_groups_bp.route("/<group_id>/knowledge/<int:doc_id>", methods=["DELETE"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def delete_knowledge_doc(group_id, doc_id):
    user = _current_user()
    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    doc = KnowledgeDocument.query.filter_by(id=doc_id, telegram_group_id=group_id).first()
    if not doc:
        return jsonify({"error": "Document not found"}), 404

    db.session.delete(doc)
    db.session.commit()
    return jsonify({"message": "Deleted"}), 200


# ── Auto-Responses ─────────────────────────────────────────────────────────────

@tg_groups_bp.route("/<group_id>/auto-responses", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def list_auto_responses(group_id):
    user = _current_user()
    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    responses = AutoResponse.query.filter_by(
        telegram_group_id=group_id
    ).order_by(AutoResponse.created_at.asc()).all()
    return jsonify({"auto_responses": [r.to_dict() for r in responses]}), 200


@tg_groups_bp.route("/<group_id>/auto-responses", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def create_auto_response(group_id):
    user = _current_user()
    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    data = request.get_json() or {}
    trigger = (data.get("trigger_text") or "").strip()
    response_text = (data.get("response_text") or "").strip()
    if not trigger or not response_text:
        return jsonify({"error": "trigger_text and response_text are required"}), 400

    match_type = data.get("match_type", "contains")
    if match_type not in ("exact", "contains", "starts_with"):
        return jsonify({"error": "match_type must be exact, contains, or starts_with"}), 400

    ar = AutoResponse(
        telegram_group_id=group_id,
        trigger_text=trigger[:500],
        response_text=response_text,
        match_type=match_type,
        is_case_sensitive=bool(data.get("is_case_sensitive", False)),
        is_enabled=bool(data.get("is_enabled", True)),
    )
    db.session.add(ar)
    db.session.commit()
    return jsonify({"auto_response": ar.to_dict()}), 201


@tg_groups_bp.route("/<group_id>/auto-responses/<int:ar_id>", methods=["PUT"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def update_auto_response(group_id, ar_id):
    user = _current_user()
    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    ar = AutoResponse.query.filter_by(id=ar_id, telegram_group_id=group_id).first()
    if not ar:
        return jsonify({"error": "Auto-response not found"}), 404

    data = request.get_json() or {}
    if "trigger_text" in data:
        ar.trigger_text = data["trigger_text"][:500]
    if "response_text" in data:
        ar.response_text = data["response_text"]
    if "match_type" in data:
        if data["match_type"] not in ("exact", "contains", "starts_with"):
            return jsonify({"error": "Invalid match_type"}), 400
        ar.match_type = data["match_type"]
    if "is_case_sensitive" in data:
        ar.is_case_sensitive = bool(data["is_case_sensitive"])
    if "is_enabled" in data:
        ar.is_enabled = bool(data["is_enabled"])

    db.session.commit()
    return jsonify({"auto_response": ar.to_dict()}), 200


@tg_groups_bp.route("/<group_id>/auto-responses/<int:ar_id>", methods=["DELETE"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def delete_auto_response(group_id, ar_id):
    user = _current_user()
    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    ar = AutoResponse.query.filter_by(id=ar_id, telegram_group_id=group_id).first()
    if not ar:
        return jsonify({"error": "Auto-response not found"}), 404

    db.session.delete(ar)
    db.session.commit()
    return jsonify({"message": "Deleted"}), 200


# ── Invite Links ───────────────────────────────────────────────────────────────

@tg_groups_bp.route("/<group_id>/invite-links", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def list_invite_links(group_id):
    user = _current_user()
    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    links = InviteLink.query.filter_by(
        telegram_group_id=group_id
    ).order_by(InviteLink.created_at.desc()).all()
    return jsonify({"invite_links": [lnk.to_dict(include_analytics=True) for lnk in links]}), 200


@tg_groups_bp.route("/<group_id>/invite-links", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def create_invite_link(group_id):
    user = _current_user()
    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400

    max_uses = data.get("max_uses")
    expire_date = None
    if data.get("expire_date"):
        try:
            expire_date = datetime.fromisoformat(
                data["expire_date"].replace("Z", "+00:00")
            ).replace(tzinfo=None)
        except (ValueError, AttributeError):
            return jsonify({"error": "Invalid expire_date format — use ISO 8601"}), 400

    # Ask the official bot to create the link via Telegram API
    telegram_invite_link = None
    from ..official_bot import get_official_bot_loop
    bot, loop = get_official_bot_loop()
    if bot and loop:
        import asyncio
        try:
            kwargs = {"chat_id": int(group_id), "name": name[:32]}
            if max_uses:
                kwargs["member_limit"] = int(max_uses)
            if expire_date:
                import time
                kwargs["expire_date"] = int(expire_date.timestamp())
            future = asyncio.run_coroutine_threadsafe(
                bot.create_chat_invite_link(**kwargs), loop
            )
            tg_link_obj = future.result(timeout=15)
            telegram_invite_link = tg_link_obj.invite_link
        except Exception as exc:
            return jsonify({"error": f"Telegram API error: {exc}"}), 502

    lnk = InviteLink(
        telegram_group_id=group_id,
        name=name[:100],
        telegram_invite_link=telegram_invite_link,
        max_uses=int(max_uses) if max_uses else None,
        expire_date=expire_date,
        created_by_user_id=user.id,
    )
    db.session.add(lnk)
    db.session.commit()
    return jsonify({"invite_link": lnk.to_dict()}), 201


@tg_groups_bp.route("/<group_id>/invite-links/<int:link_id>", methods=["DELETE"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def delete_invite_link(group_id, link_id):
    user = _current_user()
    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    lnk = InviteLink.query.filter_by(id=link_id, telegram_group_id=group_id).first()
    if not lnk:
        return jsonify({"error": "Invite link not found"}), 404

    # Revoke on Telegram side if possible
    if lnk.telegram_invite_link:
        from ..official_bot import get_official_bot_loop
        bot, loop = get_official_bot_loop()
        if bot and loop:
            import asyncio
            try:
                asyncio.run_coroutine_threadsafe(
                    bot.revoke_chat_invite_link(
                        chat_id=int(group_id),
                        invite_link=lnk.telegram_invite_link,
                    ),
                    loop,
                ).result(timeout=10)
            except Exception:
                pass

    db.session.delete(lnk)
    db.session.commit()
    return jsonify({"message": "Deleted"}), 200


# ── AI Provider API Key (for official groups) ──────────────────────────────────

@tg_groups_bp.route("/<group_id>/api-key", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def get_official_api_key(group_id):
    user = _current_user()
    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    record = UserApiKey.query.filter_by(
        telegram_group_id=group_id, is_active=True
    ).order_by(UserApiKey.created_at.desc()).first()
    return jsonify({"api_key": record.to_dict() if record else None}), 200


@tg_groups_bp.route("/<group_id>/api-key", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def set_official_api_key(group_id):
    user = _current_user()
    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    data = request.get_json() or {}
    provider = (data.get("provider") or "").strip()
    api_key_raw = (data.get("api_key") or "").strip()
    if not provider or not api_key_raw:
        return jsonify({"error": "provider and api_key are required"}), 400
    if provider not in ("openai", "openrouter", "anthropic", "gemini", "custom"):
        return jsonify({"error": "Invalid provider"}), 400

    from ..utils.encryption import encrypt_value

    # Deactivate existing keys for this telegram group
    UserApiKey.query.filter_by(telegram_group_id=group_id).update({"is_active": False})

    record = UserApiKey(
        telegram_group_id=group_id,
        user_id=user.id,
        provider=provider,
        api_key_encrypted=encrypt_value(api_key_raw),
        base_url=data.get("base_url") or None,
        model_name=data.get("model_name") or None,
        is_active=True,
    )
    db.session.add(record)
    db.session.commit()
    return jsonify({"api_key": record.to_dict()}), 201


@tg_groups_bp.route("/<group_id>/api-key", methods=["DELETE"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def delete_official_api_key(group_id):
    user = _current_user()
    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    UserApiKey.query.filter_by(telegram_group_id=group_id).update({"is_active": False})
    db.session.commit()
    return jsonify({"message": "API key deactivated"}), 200
