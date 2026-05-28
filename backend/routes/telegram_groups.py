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

import secrets as _secrets
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..models import db, User, TelegramGroup, TelegramGroupLinkCode, BotEvent, OfficialWarning, OfficialMember, Bot, CustomBot, OfficialScheduledMessage, OfficialPoll, KnowledgeDocument, AutoResponse, InviteLink, InviteLinkJoin, UserApiKey, OfficialRaid, OfficialWebhookIntegration, OfficialReportedMessage
from ..middleware.rate_limit import rate_limit
from ..config import Config
from ..group_defaults import apply_group_defaults, fill_missing_defaults

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

    groups = TelegramGroup.query.filter(
        TelegramGroup.owner_user_id == user.id,
        TelegramGroup.is_disabled == False,
        db.or_(
            TelegramGroup.group_context == "group_management",
            TelegramGroup.group_context == None,  # noqa: E711 — SQL IS NULL
        ),
        # Private groups from custom bots belong in Assistant Hub only.
        # A group is private when username IS NULL *or* username == "" (empty string).
        db.not_(
            db.and_(
                TelegramGroup.linked_via_bot_type == "custom",
                db.or_(
                    TelegramGroup.username.is_(None),    # SQL IS NULL
                    TelegramGroup.username == "",         # empty string stored by bot_manager
                ),
            )
        ),
    ).order_by(TelegramGroup.linked_at.desc()).limit(500).all()

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

    # Build reverse lookup: telegram_group_id → old Bot, for enriching TelegramGroup rows
    # that have linked_via_bot_type='custom' but a NULL linked_bot_id.
    tg_id_to_old_bot = {}
    for old_bot in old_bots:
        for grp in old_bot.groups:
            tg_id_to_old_bot[grp.telegram_group_id] = old_bot

    # Enrich TelegramGroup rows that are custom but missing linked_bot_id
    for g in groups_data:
        if g.get("linked_via_bot_type") == "custom" and not g.get("linked_bot_id"):
            ob = tg_id_to_old_bot.get(g["telegram_group_id"])
            if ob:
                bid = custom_bot_id_by_username.get(ob.bot_username)
                if bid:
                    g["linked_bot_id"] = bid
                    g["linked_bot_name"] = custom_bot_name_by_id.get(bid)
                    g["linked_bot_username"] = custom_bot_username_by_id.get(bid)

    # Pre-fetch HubConnectedGroup records for all custom bots owned by this user,
    # so we can skip private custom-bot groups that already live in Assistant Hub.
    from ..assistant.hub_models import HubConnectedGroup, HubBotIdentity
    hub_bot_ids = [
        hb.id for hb in HubBotIdentity.query.filter_by(user_id=user.id, bot_type="custom").all()
    ]
    hub_private_tg_ids: set = set()
    if hub_bot_ids:
        hub_groups = HubConnectedGroup.query.filter(
            HubConnectedGroup.bot_id.in_(hub_bot_ids),
            HubConnectedGroup.is_active == True,  # noqa: E712
        ).all()
        hub_private_tg_ids = {
            str(hg.telegram_group_id) for hg in hub_groups if not hg.is_public_group
        }

    for old_bot in old_bots:
        # A Bot record whose username matches a CustomBot is a custom-bot polling thread.
        # Private groups for such bots are owned by Assistant Hub — don't show them here.
        is_custom_bot_record = bool(custom_bot_id_by_username.get(old_bot.bot_username))

        for grp in old_bot.groups:
            if grp.telegram_group_id in new_system_tg_ids:
                continue  # already present in TelegramGroup
            # Private groups belonging to custom bots are owned by Assistant Hub — skip them.
            if is_custom_bot_record and grp.telegram_group_id in hub_private_tg_ids:
                continue
            linked_bot_id = custom_bot_id_by_username.get(old_bot.bot_username)
            groups_data.append({
                # grp.id is the Group table PK — required for /bot/:bot_id/group/:group_id routing
                "id": grp.id,
                "telegram_group_id": grp.telegram_group_id,
                "title": grp.group_name or "Unknown Group",
                "username": None,
                "invite_link": None,
                "owner_user_id": user.id,
                "linked_via_bot_type": "custom",
                "linked_bot_id": linked_bot_id,
                "linked_bot_name": custom_bot_name_by_id.get(linked_bot_id) if linked_bot_id else None,
                "linked_bot_username": custom_bot_username_by_id.get(linked_bot_id) if linked_bot_id else None,
                # old_bot.id is the Bot table PK — needed for /api/bots/<bot_id>/... endpoints
                "legacy_bot_id": old_bot.id,
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

    # ── Pillar separation guard ────────────────────────────────────────────────
    # Block linking a group that is already connected to this user's Assistant Hub.
    # Hub groups live in hub_connected_groups (separate table). Silently merging
    # them into Group Management would expose moderation features (XP, welcome
    # messages, analytics, warnings) on what was intended as a private assistant
    # group. The user must explicitly disconnect from Hub first.
    from ..assistant.hub_models import HubConnectedGroup, HubBotIdentity
    hub_bot_ids = [
        b.id for b in HubBotIdentity.query.filter_by(user_id=user.id).all()
    ]
    if hub_bot_ids:
        hub_clash = HubConnectedGroup.query.filter(
            HubConnectedGroup.bot_id.in_(hub_bot_ids),
            HubConnectedGroup.telegram_group_id == int(tg.telegram_group_id),
        ).first()
        if hub_clash:
            return jsonify({
                "error": (
                    "This group is already connected to Echo. "
                    "Echo groups are separate from Group Management groups. "
                    "To use it for Group Management, disconnect it from Echo first."
                ),
                "code": "HUB_GROUP_CONFLICT",
                "hint": "Go to Echo → Groups → Disconnect, then try linking again.",
            }), 409

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
    tg.group_context = "group_management"
    # Fill in any default sections the group may be missing (handles both
    # brand-new groups and those created before a feature was added).
    fill_missing_defaults(tg)
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

    # Deactivate matching HubConnectedGroup so Assistant Hub stays in sync.
    # The TelegramGroup stores linked_bot_id → CustomBot.id; we follow the FK
    # chain: CustomBot → hub_bot_id → HubBotIdentity → HubConnectedGroup.
    if tg.linked_bot_id:
        try:
            cb = CustomBot.query.filter_by(id=tg.linked_bot_id).first()
            if cb and cb.hub_bot_id:
                from ..assistant.hub_models import HubConnectedGroup as _HCG
                hub_grp = _HCG.query.filter_by(
                    bot_id=cb.hub_bot_id,
                    telegram_group_id=tg.telegram_group_id,
                    user_id=user.id,
                ).first()
                if hub_grp:
                    hub_grp.is_active = False
                    hub_grp.pause_reason = "user_unlinked"
        except Exception as _e:
            import logging as _log
            _log.getLogger(__name__).warning(
                "unlink_group: hub sync failed for tg=%s: %s", group_id, _e
            )

    tg.owner_user_id = None
    tg.bot_status = "pending"
    tg.linked_at = None
    tg.linked_bot_id = None
    tg.linked_via_bot_type = "official"
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
    period = request.args.get("period", "all")
    has_wallet = request.args.get("has_wallet")

    period_col_map = {
        "1d": OfficialMember.xp_1d,
        "7d": OfficialMember.xp_7d,
        "30d": OfficialMember.xp_30d,
    }
    sort_col = period_col_map.get(period, OfficialMember.xp)

    members_q = OfficialMember.query.filter_by(telegram_group_id=group_id)
    if period != "all":
        members_q = members_q.filter(sort_col > 0)
    if has_wallet == "true":
        members_q = members_q.filter(
            OfficialMember.wallet_address.isnot(None),
            OfficialMember.wallet_address != "",
        )
    members = members_q.order_by(sort_col.desc()).limit(limit).all()
    return jsonify({"members": [m.to_dict() for m in members]}), 200


# ── Forum Topics ──────────────────────────────────────────────────────────────

@tg_groups_bp.route("/<group_id>/forum-topics", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def get_forum_topics(group_id):
    """Return cached forum topics discovered by the bot for this group."""
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    from ..models import GroupForumTopic
    topics = (
        GroupForumTopic.query
        .filter_by(telegram_group_id=group_id)
        .order_by(GroupForumTopic.name)
        .all()
    )
    return jsonify({"topics": [t.to_dict() for t in topics]}), 200


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
    # Merge into existing digest config so last_daily/weekly/monthly timestamps survive
    existing_digest = dict(settings.get("digest", {}))
    valid_delivery = {"dm", "group"}
    delivery = data.get("delivery", existing_digest.get("delivery", "dm"))
    if delivery not in valid_delivery:
        delivery = "dm"
    existing_digest.update({
        "enabled":       bool(data.get("enabled", existing_digest.get("enabled", False))),
        "frequency":     data.get("frequency", existing_digest.get("frequency", "daily")),
        "schedule_time": (data.get("schedule_time") or existing_digest.get("schedule_time") or "09:00")[:5],
        "delivery":      delivery,
        # Legacy fields kept for scheduler compatibility
        "daily":         data.get("frequency", existing_digest.get("frequency", "daily")) == "daily",
        "weekly":        data.get("frequency", existing_digest.get("frequency", "daily")) == "weekly",
        "monthly":       data.get("frequency", existing_digest.get("frequency", "daily")) == "monthly",
        "send_to_group": delivery == "group",
    })
    settings["digest"] = existing_digest
    # Keep assistant.ai_digest_enabled in sync so message buffering + AI summary activate correctly
    assistant = dict(settings.get("assistant", {}))
    assistant["ai_digest_enabled"] = existing_digest["enabled"]
    settings["assistant"] = assistant
    tg.settings = settings
    db.session.commit()
    return jsonify({"digest": existing_digest}), 200


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


@tg_groups_bp.route("/<group_id>/digest/history", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def get_digest_history(group_id):
    from ..models import DigestLog
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    logs = (
        DigestLog.query
        .filter_by(group_id=tg.telegram_group_id)
        .order_by(DigestLog.sent_at.desc())
        .limit(20)
        .all()
    )
    return jsonify({"history": [l.to_dict() for l in logs]}), 200


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

    repeat_interval = data.get("repeat_interval")
    if repeat_interval is not None:
        try:
            repeat_interval = int(repeat_interval)
            if repeat_interval < 60:
                return jsonify({"error": "repeat_interval must be at least 60 minutes"}), 400
            if repeat_interval > 525600:  # 1 year in minutes
                return jsonify({"error": "repeat_interval must be at most 525600 minutes (1 year)"}), 400
        except (TypeError, ValueError):
            return jsonify({"error": "repeat_interval must be an integer (minutes)"}), 400

    msg = OfficialScheduledMessage(
        telegram_group_id=group_id,
        title=title,
        message_text=message_text,
        media_url=data.get("media_url"),
        buttons=data.get("buttons"),
        send_at=send_at,
        repeat_interval=repeat_interval,
        stop_date=datetime.fromisoformat(data["stop_date"].replace("Z", "+00:00")).replace(tzinfo=None) if data.get("stop_date") else None,
        pin_message=bool(data.get("pin_message", False)),
        auto_delete_after=data.get("auto_delete_after"),
        link_preview_enabled=bool(data.get("link_preview_enabled", True)),
        topic_id=data.get("topic_id"),
        timezone=data.get("timezone", "UTC"),
    )
    db.session.add(msg)
    db.session.commit()
    try:
        from ..routes.auth import _mark_onboarding_step
        _mark_onboarding_step(user, "schedule_created")
    except Exception:
        pass
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


# ── Forum Topics (1-F-02) ──────────────────────────────────────────────────────

@tg_groups_bp.route("/<group_id>/topics", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def get_group_topics(group_id):
    """Return forum topics for a forum group. Cached in group.settings['topics']."""
    user = _current_user()
    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    if not tg.is_forum:
        return jsonify({"error": "Not a forum group"}), 400

    # Return cached topics if available
    cached = (tg.settings or {}).get("topics")
    if cached:
        return jsonify({"topics": cached}), 200

    # Try to fetch live from Telegram bot
    import requests as _req
    from ..config import Config
    token = Config.TELEGRAM_BOT_TOKEN
    if not token:
        return jsonify({"topics": [{"id": 1, "name": "General"}]}), 200

    try:
        resp = _req.get(
            f"https://api.telegram.org/bot{token}/getForumTopics",
            params={"chat_id": tg.telegram_chat_id},
            timeout=5,
        )
        data = resp.json()
        if data.get("ok"):
            raw = data.get("result", {}).get("topics", [])
            topics = [{"id": t["message_thread_id"], "name": t["name"]} for t in raw]
        else:
            topics = [{"id": 1, "name": "General"}]
    except Exception:
        topics = [{"id": 1, "name": "General"}]

    # Cache in settings
    settings = dict(tg.settings or {})
    settings["topics"] = topics
    tg.settings = settings
    db.session.commit()

    return jsonify({"topics": topics}), 200


@tg_groups_bp.route("/<group_id>/topics/default", methods=["PUT"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def set_default_topic(group_id):
    """Set the default forum topic ID for group messages."""
    user = _current_user()
    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    topic_id = request.json.get("topic_id")
    if not isinstance(topic_id, int):
        return jsonify({"error": "topic_id must be an integer"}), 400

    settings = dict(tg.settings or {})
    settings["default_topic_id"] = topic_id
    tg.settings = settings
    db.session.commit()
    return jsonify({"default_topic_id": topic_id}), 200


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
    ).order_by(OfficialPoll.scheduled_at.asc()).limit(500).all()
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
    ).order_by(KnowledgeDocument.created_at.desc()).limit(500).all()
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
    ).order_by(AutoResponse.created_at.asc()).limit(500).all()
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
    if "use_as_ai_knowledge" in data:
        ar.use_as_ai_knowledge = bool(data["use_as_ai_knowledge"])

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


# ── AI Provider API Key Test ───────────────────────────────────────────────────

@tg_groups_bp.route("/<group_id>/api-key/test", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def test_official_api_key(group_id):
    user = _current_user()
    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    record = UserApiKey.query.filter_by(
        telegram_group_id=group_id, is_active=True
    ).order_by(UserApiKey.created_at.desc()).first()
    if not record:
        return jsonify({"error": "No API key configured"}), 404

    from ..utils.encryption import decrypt_value, DecryptionError
    try:
        raw_key = decrypt_value(record.api_key_encrypted)
    except DecryptionError:
        return jsonify({"error": "Failed to decrypt stored API key — check ENCRYPTION_KEY config"}), 500

    try:
        if record.provider == "openai":
            import openai
            client = openai.OpenAI(api_key=raw_key, base_url=record.base_url or None)
            client.models.list()
        elif record.provider == "anthropic":
            import anthropic
            client = anthropic.Anthropic(api_key=raw_key)
            client.models.list()
        elif record.provider in ("openrouter", "custom"):
            import requests as req
            base = record.base_url or "https://openrouter.ai/api/v1"
            resp = req.get(f"{base}/models", headers={"Authorization": f"Bearer {raw_key}"}, timeout=10)
            resp.raise_for_status()
        elif record.provider == "gemini":
            import requests as req
            resp = req.get(
                f"https://generativelanguage.googleapis.com/v1beta/models?key={raw_key}",
                timeout=10,
            )
            resp.raise_for_status()
        else:
            return jsonify({"error": f"Test not supported for provider '{record.provider}'"}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 200

    return jsonify({"ok": True, "provider": record.provider}), 200


# ── Members Directory ──────────────────────────────────────────────────────────

@tg_groups_bp.route("/<group_id>/members", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def list_official_members(group_id):
    user = _current_user()
    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    page = max(1, int(request.args.get("page", 1)))
    per_page = min(100, max(1, int(request.args.get("per_page", 50))))
    q = (request.args.get("q") or "").strip().lower()
    role_filter = request.args.get("role")
    is_verified = request.args.get("is_verified")
    is_muted = request.args.get("is_muted")
    is_admin = request.args.get("is_admin")
    has_wallet = request.args.get("has_wallet")
    has_warnings = request.args.get("has_warnings")
    sort_by = request.args.get("sort_by", "xp")
    sort_dir = request.args.get("sort_dir", "desc")
    period = request.args.get("period", "all")

    # When sorting by XP and a time period is set, sort by the period column instead
    period_col_map = {"1d": "xp_1d", "7d": "xp_7d", "30d": "xp_30d"}
    if period != "all" and sort_by == "xp":
        sort_by = period_col_map.get(period, "xp")

    query = OfficialMember.query.filter_by(telegram_group_id=group_id)

    if q:
        query = query.filter(
            db.or_(
                OfficialMember.username.ilike(f"%{q}%"),
                OfficialMember.first_name.ilike(f"%{q}%"),
            )
        )
    if role_filter:
        query = query.filter(OfficialMember.role == role_filter)
    if is_verified is not None:
        query = query.filter(OfficialMember.is_verified == (is_verified.lower() == "true"))
    if is_muted is not None:
        query = query.filter(OfficialMember.is_muted == (is_muted.lower() == "true"))
    if is_admin is not None:
        query = query.filter(OfficialMember.is_admin == (is_admin.lower() == "true"))
    if has_wallet is not None:
        if has_wallet.lower() == "true":
            query = query.filter(OfficialMember.wallet_address.isnot(None), OfficialMember.wallet_address != "")
        else:
            query = query.filter(
                db.or_(OfficialMember.wallet_address.is_(None), OfficialMember.wallet_address == "")
            )
    if has_warnings is not None and has_warnings.lower() == "true":
        query = query.filter(OfficialMember.warnings > 0)

    col = getattr(OfficialMember, sort_by, OfficialMember.xp)
    query = query.order_by(col.desc() if sort_dir == "desc" else col.asc())

    total = query.count()
    members = query.offset((page - 1) * per_page).limit(per_page).all()

    return jsonify({
        "members": [m.to_dict() for m in members],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": max(1, (total + per_page - 1) // per_page),
    }), 200


# ── Raids ──────────────────────────────────────────────────────────────────────

@tg_groups_bp.route("/<group_id>/raids", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def list_official_raids(group_id):
    user = _current_user()
    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    raids = OfficialRaid.query.filter_by(
        telegram_group_id=group_id
    ).order_by(OfficialRaid.created_at.desc()).all()
    return jsonify({"raids": [r.to_dict() for r in raids]}), 200


@tg_groups_bp.route("/<group_id>/raids", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def create_official_raid(group_id):
    user = _current_user()
    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    data = request.get_json() or {}
    tweet_url = (data.get("tweet_url") or "").strip()
    if not tweet_url:
        return jsonify({"error": "tweet_url is required"}), 400

    duration_hours = int(data.get("duration_hours", 24))
    ends_at = datetime.utcnow() + timedelta(hours=duration_hours)

    raid = OfficialRaid(
        telegram_group_id=group_id,
        tweet_url=tweet_url,
        goals=data.get("goals") or {},
        duration_hours=duration_hours,
        xp_reward=int(data.get("xp_reward", 100)),
        pin_message=bool(data.get("pin_message", True)),
        reminders_enabled=bool(data.get("reminders_enabled", True)),
        is_active=True,
        ends_at=ends_at,
        participants=[],
    )
    db.session.add(raid)
    db.session.commit()

    # Announce raid in the Telegram group
    from ..official_bot import get_official_bot_loop
    bot, loop = get_official_bot_loop()
    if bot and loop:
        import asyncio
        goals_text = ""
        if raid.goals:
            goals_text = "\n".join(
                f"  • {g.get('type', 'action').title()}: {g.get('target', 0)}"
                for g in (raid.goals if isinstance(raid.goals, list) else [])
            )
        msg = (
            f"🚀 *Raid Started!*\n\n"
            f"Tweet: {tweet_url}\n"
            f"Duration: {duration_hours}h  •  XP Reward: {raid.xp_reward}\n"
            f"{goals_text}\n\n"
            f"Use /raid to participate!"
        )
        try:
            sent = asyncio.run_coroutine_threadsafe(
                bot.send_message(chat_id=int(group_id), text=msg, parse_mode="Markdown"),
                loop,
            ).result(timeout=15)
            if raid.pin_message:
                asyncio.run_coroutine_threadsafe(
                    bot.pin_chat_message(chat_id=int(group_id), message_id=sent.message_id),
                    loop,
                ).result(timeout=10)
        except Exception:
            pass

    return jsonify({"raid": raid.to_dict()}), 201


# ── Webhooks ───────────────────────────────────────────────────────────────────

@tg_groups_bp.route("/<group_id>/webhooks", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def list_official_webhooks(group_id):
    user = _current_user()
    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    hooks = OfficialWebhookIntegration.query.filter_by(
        telegram_group_id=group_id
    ).order_by(OfficialWebhookIntegration.created_at.desc()).all()
    return jsonify({"webhooks": [h.to_dict() for h in hooks]}), 200


@tg_groups_bp.route("/<group_id>/webhooks", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def create_official_webhook(group_id):
    user = _current_user()
    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400

    hook = OfficialWebhookIntegration(
        telegram_group_id=group_id,
        name=name[:100],
        webhook_token=_secrets.token_urlsafe(32),
        description=data.get("description"),
        message_template=data.get("message_template") or "📡 *{name}*\n\n{payload}",
        is_active=bool(data.get("is_active", True)),
    )
    db.session.add(hook)
    db.session.commit()
    return jsonify({"webhook": hook.to_dict()}), 201


@tg_groups_bp.route("/<group_id>/webhooks/<int:hook_id>", methods=["PUT"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def update_official_webhook(group_id, hook_id):
    user = _current_user()
    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    hook = OfficialWebhookIntegration.query.filter_by(id=hook_id, telegram_group_id=group_id).first()
    if not hook:
        return jsonify({"error": "Webhook not found"}), 404

    data = request.get_json() or {}
    if "name" in data:
        hook.name = data["name"][:100]
    if "description" in data:
        hook.description = data["description"]
    if "message_template" in data:
        hook.message_template = data["message_template"]
    if "is_active" in data:
        hook.is_active = bool(data["is_active"])

    db.session.commit()
    return jsonify({"webhook": hook.to_dict()}), 200


@tg_groups_bp.route("/<group_id>/webhooks/<int:hook_id>", methods=["DELETE"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def delete_official_webhook(group_id, hook_id):
    user = _current_user()
    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    hook = OfficialWebhookIntegration.query.filter_by(id=hook_id, telegram_group_id=group_id).first()
    if not hook:
        return jsonify({"error": "Webhook not found"}), 404

    db.session.delete(hook)
    db.session.commit()
    return jsonify({"message": "Deleted"}), 200


# ── Public Webhook Trigger ─────────────────────────────────────────────────────

@tg_groups_bp.route("/webhook-trigger/<token>", methods=["POST"])
@rate_limit(requests_per_minute=30)
def trigger_official_webhook(token):
    hook = OfficialWebhookIntegration.query.filter_by(webhook_token=token, is_active=True).first()
    if not hook:
        return jsonify({"error": "Invalid or inactive webhook token"}), 404

    data = request.get_json() or {}
    payload = data.get("payload") or ""
    name = hook.name
    msg = hook.message_template.replace("{name}", name).replace("{payload}", str(payload))
    for k, v in (data.get("vars") or {}).items():
        msg = msg.replace(f"{{{k}}}", str(v))

    from ..official_bot import get_official_bot_loop
    bot, loop = get_official_bot_loop()
    if not bot or not loop:
        return jsonify({"error": "Bot unavailable"}), 503

    import asyncio
    try:
        asyncio.run_coroutine_threadsafe(
            bot.send_message(
                chat_id=int(hook.telegram_group_id),
                text=msg,
                parse_mode="Markdown",
            ),
            loop,
        ).result(timeout=15)
    except Exception as exc:
        return jsonify({"error": f"Telegram delivery failed: {exc}"}), 502

    return jsonify({"ok": True}), 200


# ── Invite Link Analytics ──────────────────────────────────────────────────────

@tg_groups_bp.route("/<group_id>/invite-links/<int:link_id>/analytics", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def get_invite_link_analytics(group_id, link_id):
    user = _current_user()
    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    lnk = InviteLink.query.filter_by(id=link_id, telegram_group_id=group_id).first()
    if not lnk:
        return jsonify({"error": "Invite link not found"}), 404

    joins = InviteLinkJoin.query.filter_by(invite_link_id=link_id).order_by(InviteLinkJoin.joined_at.desc()).all()
    return jsonify({
        "invite_link": lnk.to_dict(include_analytics=True),
        "joins": [
            {
                "id": j.id,
                "telegram_user_id": j.telegram_user_id,
                "username": j.username,
                "first_name": j.first_name,
                "joined_at": j.joined_at.isoformat() + "Z",
            }
            for j in joins
        ],
        "total_joins": len(joins),
    }), 200


# ── Reports ────────────────────────────────────────────────────────────────────

@tg_groups_bp.route("/<group_id>/reports", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def list_official_reports(group_id):
    user = _current_user()
    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    status_filter = request.args.get("status")
    query = OfficialReportedMessage.query.filter_by(telegram_group_id=group_id)
    if status_filter in ("open", "resolved"):
        query = query.filter_by(status=status_filter)

    reports = query.order_by(OfficialReportedMessage.created_at.desc()).all()
    return jsonify({"reports": [r.to_dict() for r in reports]}), 200


@tg_groups_bp.route("/<group_id>/reports/<int:report_id>/resolve", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def resolve_official_report(group_id, report_id):
    user = _current_user()
    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    report = OfficialReportedMessage.query.filter_by(id=report_id, telegram_group_id=group_id).first()
    if not report:
        return jsonify({"error": "Report not found"}), 404

    report.status = "resolved"
    db.session.commit()
    return jsonify({"report": report.to_dict()}), 200


# ── 1-B-02: Dashboard-side link code generation ────────────────────────────────

@tg_groups_bp.route("/generate-link-code", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def generate_link_code():
    """Generate a one-time TLG-XXXXXXXX code for the user to run in their group."""
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json() or {}
    bot_id = data.get("bot_id")  # None = official bot

    # Delete any existing unused dashboard-generated codes for this user
    TelegramGroupLinkCode.query.filter_by(user_id=user.id, used=False).delete()

    import secrets as _s
    import string as _str
    alphabet = _str.ascii_uppercase + _str.digits
    code = "TLG-" + "".join(_s.choice(alphabet) for _ in range(8))
    while TelegramGroupLinkCode.query.filter_by(code=code).first():
        code = "TLG-" + "".join(_s.choice(alphabet) for _ in range(8))

    expires_at = datetime.utcnow() + timedelta(minutes=12)
    link_code = TelegramGroupLinkCode(
        code=code,
        user_id=user.id,
        bot_id=bot_id,
        expires_at=expires_at,
        used=False,
    )
    db.session.add(link_code)
    db.session.commit()

    return jsonify({
        "code": code,
        "expires_at": expires_at.isoformat() + "Z",
        "instructions": f"Run /linkgroup {code} in your Telegram group",
    }), 200


# ── 1-B-04: Link status polling ────────────────────────────────────────────────

@tg_groups_bp.route("/link-status", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def link_status():
    """Poll whether a dashboard-generated link code has been consumed by the bot."""
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    code = request.args.get("code", "").upper()
    if not code:
        return jsonify({"error": "code parameter required"}), 400

    link_code = TelegramGroupLinkCode.query.filter_by(code=code, user_id=user.id).first()
    if not link_code:
        return jsonify({"status": "expired"}), 200

    if link_code.used:
        group = TelegramGroup.query.filter_by(owner_user_id=user.id).order_by(
            TelegramGroup.linked_at.desc()
        ).first()
        group_data = None
        if group:
            group_data = {
                "id": group.telegram_group_id,
                "title": group.title,
                "member_count": group.member_count or 0,
            }
        return jsonify({"status": "linked", "group": group_data}), 200

    if datetime.utcnow() > link_code.expires_at:
        return jsonify({"status": "expired"}), 200

    return jsonify({
        "status": "pending",
        "expires_at": link_code.expires_at.isoformat() + "Z",
    }), 200


# ── 1-B-05: Bot permissions endpoint ──────────────────────────────────────────

@tg_groups_bp.route("/<group_id>/permissions", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def get_group_permissions(group_id):
    """Return the stored bot permissions for a group."""
    user = _current_user()
    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    perms = tg.bot_permissions or {}
    score = perms.get("permission_score", 0)
    return jsonify({
        "permissions": perms,
        "permission_score": score,
        "access_tier": perms.get("access_tier", "Unknown"),
    }), 200

