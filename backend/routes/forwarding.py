"""
Forwarding API — user-scoped cross-posting rules.

Rules   GET/POST/PUT/DELETE /api/forwarding/rules
        GET                 /api/forwarding/rules/:id/logs
Pending GET                 /api/forwarding/pending
        POST                /api/forwarding/pending/:log_id/approve
        POST                /api/forwarding/pending/:log_id/reject
"""
import logging
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..models import (
    db, User, TelegramGroup, Group, Bot, Channel,
    ForwardRule, ForwardLog, ForwardSource, ForwardDestination,
)
from ..middleware.rate_limit import rate_limit
from ..automation.forwarding_runtime import parse_topic_link

forwarding_bp = Blueprint("forwarding", __name__, url_prefix="/api/forwarding")
_log = logging.getLogger(__name__)

_VALID_MATCH = {"contains", "starts_with"}
_MAX_RULES_FREE = 3
_MAX_RULES_PRO = 20


def _current_user() -> User:
    return User.query.get(int(get_jwt_identity()))


def _owns_rule(user: User, rule: ForwardRule) -> bool:
    return rule.owner_user_id == user.id


def _owns_group(user: User, group_id: str) -> bool:
    return TelegramGroup.query.filter_by(
        telegram_group_id=group_id, owner_user_id=user.id, is_disabled=False
    ).first() is not None


def _owns_source(user: User, chat_id: str) -> bool:
    """A source must be a chat the user controls — official group, custom-bot
    group (via Bot ownership), or one of their channels."""
    chat_key = str(chat_id)
    if _owns_group(user, chat_key):
        return True
    g = Group.query.filter_by(telegram_group_id=chat_key).first()
    if g and g.bot_id:
        b = Bot.query.get(g.bot_id)
        if b and b.user_id == user.id:
            return True
    ch = Channel.query.filter_by(telegram_channel_id=chat_key).first()
    if ch and ch.user_id == user.id:
        return True
    return False


def _parse_endpoints(raw_list, *, legacy_chat=None, legacy_topic=None):
    """Normalize a sources/destinations payload into [{chat_id, topic_id}].

    Accepts the new list shape ([{chat_id, topic_link|topic_id}, ...]) and falls
    back to a single legacy chat id when the list is absent/empty.
    """
    out = []
    for item in (raw_list or []):
        if isinstance(item, dict):
            chat = str(item.get("chat_id") or item.get("destination_id") or "").strip()
            topic = item.get("topic_id")
            if topic is None:
                topic = parse_topic_link(item.get("topic_link"))
        else:
            chat, topic = str(item).strip(), None
        if chat:
            out.append({"chat_id": chat[:255], "topic_id": topic})
    if not out and legacy_chat:
        out.append({"chat_id": str(legacy_chat).strip()[:255],
                    "topic_id": parse_topic_link(legacy_topic) if legacy_topic else None})
    return out


def _validate_destination_admin(source_chat, destinations):
    """Best-effort D6 check: is the managing bot an admin able to post in each
    destination? Returns a list of human warnings naming the correct bot. Never
    raises; an empty list means 'all good (or could not verify)'."""
    warnings = []
    try:
        from ..automation.bot_resolver import resolve_bot_loop_for_chat
        import asyncio
        bot, loop = resolve_bot_loop_for_chat(source_chat)
        if not (bot and loop and loop.is_running()):
            return ["Bot isn't running right now, so destination permissions "
                    "couldn't be verified. Make sure the bot is an admin in every "
                    "destination chat."]
        bot_label = f"@{bot.username}" if getattr(bot, "username", None) else "the bot"
        for dest in destinations:
            chat = dest["chat_id"]

            async def _check():
                me = await bot.get_chat_member(chat, bot.id)
                return getattr(me, "status", None)

            try:
                fut = asyncio.run_coroutine_threadsafe(_check(), loop)
                status = fut.result(timeout=8)
                if status not in ("administrator", "creator"):
                    warnings.append(
                        f"Add {bot_label} as an admin (with permission to post) in "
                        f"destination {chat}, otherwise forwarding there will fail."
                    )
            except Exception:
                warnings.append(
                    f"Couldn't verify {bot_label}'s access to destination {chat}. "
                    f"Ensure it's added there as an admin."
                )
    except Exception as exc:  # noqa: BLE001
        _log.debug("destination admin validation failed: %s", exc)
    return warnings


def _replace_children(rule, sources, destinations):
    """Rewrite a rule's ForwardSource / ForwardDestination rows, preserving the
    pause state of destinations that survive the edit."""
    prev_pause = {
        (d.destination_id, d.topic_id): (d.is_paused, d.pause_reason)
        for d in rule.destinations
    }
    for child in list(rule.sources):
        db.session.delete(child)
    for child in list(rule.destinations):
        db.session.delete(child)
    db.session.flush()
    for s in sources:
        db.session.add(ForwardSource(
            rule_id=rule.id, source_chat_id=s["chat_id"], source_topic_id=s["topic_id"],
        ))
    for d in destinations:
        paused, reason = prev_pause.get((d["chat_id"], d["topic_id"]), (False, None))
        db.session.add(ForwardDestination(
            rule_id=rule.id, destination_id=d["chat_id"], topic_id=d["topic_id"],
            is_paused=paused, pause_reason=reason,
        ))


# ── List rules ───────────────────────────────────────────────────────────────

@forwarding_bp.route("/rules", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def list_rules():
    user = _current_user()
    rules = ForwardRule.query.filter_by(owner_user_id=user.id)\
        .order_by(ForwardRule.created_at.desc()).all()
    return jsonify({"rules": [r.to_dict() for r in rules]})


# ── Create rule ──────────────────────────────────────────────────────────────

@forwarding_bp.route("/rules", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def create_rule():
    user = _current_user()
    data = request.get_json() or {}

    rule_name = (data.get("rule_name") or "").strip()
    keyword_filter = (data.get("keyword_filter") or "").strip() or None
    match_type = data.get("match_type", "contains")
    prefix_text = (data.get("prefix_text") or "").strip() or None
    suffix_text = (data.get("suffix_text") or "").strip() or None
    require_approval = bool(data.get("require_approval", False))

    # Many→many shape with single-source/destination back-compat.
    sources = _parse_endpoints(
        data.get("sources"),
        legacy_chat=data.get("source_group_id"),
        legacy_topic=data.get("source_topic_id") or data.get("source_topic_link"),
    )
    destinations = _parse_endpoints(
        data.get("destinations"),
        legacy_chat=data.get("destination_id"),
    )

    if not rule_name:
        return jsonify({"error": "rule_name is required"}), 400
    if not sources:
        return jsonify({"error": "At least one source is required"}), 400
    if not destinations:
        return jsonify({"error": "At least one destination is required"}), 400
    if match_type not in _VALID_MATCH:
        return jsonify({"error": f"match_type must be one of {sorted(_VALID_MATCH)}"}), 400

    # Verify the user owns every source chat
    for src in sources:
        if not _owns_source(user, src["chat_id"]):
            return jsonify({
                "error": f"Source {src['chat_id']} not found or not owned by you"
            }), 404

    # Tier limits
    existing = ForwardRule.query.filter_by(owner_user_id=user.id).count()
    limit = _MAX_RULES_PRO if user.subscription_tier in ("pro", "enterprise") else _MAX_RULES_FREE
    if existing >= limit:
        return jsonify({
            "error": f"Rule limit reached ({limit} rules). Upgrade to create more.",
            "code": "LIMIT_REACHED",
        }), 403

    rule = ForwardRule(
        owner_user_id=user.id,
        rule_name=rule_name[:200],
        # legacy columns mirror the first source/destination for back-compat
        source_group_id=sources[0]["chat_id"],
        source_topic_id=sources[0]["topic_id"],
        destination_id=destinations[0]["chat_id"],
        keyword_filter=keyword_filter[:1000] if keyword_filter else None,
        match_type=match_type,
        prefix_text=prefix_text[:500] if prefix_text else None,
        suffix_text=suffix_text[:500] if suffix_text else None,
        require_approval=require_approval,
        is_active=True,
    )
    db.session.add(rule)
    db.session.flush()  # assign rule.id before adding children
    _replace_children(rule, sources, destinations)
    db.session.commit()

    # D6 — best-effort admin/permission warnings (don't block rule creation)
    warnings = _validate_destination_admin(sources[0]["chat_id"], destinations)
    return jsonify({"rule": rule.to_dict(), "warnings": warnings}), 201


# ── Update rule ──────────────────────────────────────────────────────────────

@forwarding_bp.route("/rules/<int:rule_id>", methods=["PUT"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def update_rule(rule_id):
    user = _current_user()
    rule = ForwardRule.query.get_or_404(rule_id)
    if not _owns_rule(user, rule):
        return jsonify({"error": "Not found"}), 404

    data = request.get_json() or {}
    if "rule_name" in data:
        rule.rule_name = (data["rule_name"] or "").strip()[:200]
    if "keyword_filter" in data:
        rule.keyword_filter = (data["keyword_filter"] or "").strip()[:1000] or None
    if "match_type" in data and data["match_type"] in _VALID_MATCH:
        rule.match_type = data["match_type"]
    if "prefix_text" in data:
        rule.prefix_text = (data["prefix_text"] or "").strip()[:500] or None
    if "suffix_text" in data:
        rule.suffix_text = (data["suffix_text"] or "").strip()[:500] or None
    if "require_approval" in data:
        rule.require_approval = bool(data["require_approval"])
    if "is_active" in data:
        rule.is_active = bool(data["is_active"])

    # Optional source/destination edits (many→many + topics)
    warnings = []
    has_src = "sources" in data or "source_group_id" in data
    has_dst = "destinations" in data or "destination_id" in data
    if has_src or has_dst:
        sources = _parse_endpoints(
            data.get("sources"),
            legacy_chat=data.get("source_group_id") or rule.source_group_id,
            legacy_topic=data.get("source_topic_id") or data.get("source_topic_link"),
        )
        destinations = _parse_endpoints(
            data.get("destinations"),
            legacy_chat=data.get("destination_id") or rule.destination_id,
        )
        if not sources:
            return jsonify({"error": "At least one source is required"}), 400
        if not destinations:
            return jsonify({"error": "At least one destination is required"}), 400
        for src in sources:
            if not _owns_source(user, src["chat_id"]):
                return jsonify({
                    "error": f"Source {src['chat_id']} not found or not owned by you"
                }), 404
        rule.source_group_id = sources[0]["chat_id"]
        rule.source_topic_id = sources[0]["topic_id"]
        rule.destination_id = destinations[0]["chat_id"]
        _replace_children(rule, sources, destinations)
        db.session.commit()
        warnings = _validate_destination_admin(sources[0]["chat_id"], destinations)
    else:
        db.session.commit()

    return jsonify({"rule": rule.to_dict(), "warnings": warnings})


# ── Delete rule ──────────────────────────────────────────────────────────────

@forwarding_bp.route("/rules/<int:rule_id>", methods=["DELETE"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def delete_rule(rule_id):
    user = _current_user()
    rule = ForwardRule.query.get_or_404(rule_id)
    if not _owns_rule(user, rule):
        return jsonify({"error": "Not found"}), 404
    db.session.delete(rule)
    db.session.commit()
    return jsonify({"ok": True})


# ── Toggle active ─────────────────────────────────────────────────────────────

@forwarding_bp.route("/rules/<int:rule_id>/toggle", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def toggle_rule(rule_id):
    user = _current_user()
    rule = ForwardRule.query.get_or_404(rule_id)
    if not _owns_rule(user, rule):
        return jsonify({"error": "Not found"}), 404
    rule.is_active = not rule.is_active
    db.session.commit()
    return jsonify({"rule": rule.to_dict()})


# ── Rule logs ─────────────────────────────────────────────────────────────────

@forwarding_bp.route("/rules/<int:rule_id>/logs", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def rule_logs(rule_id):
    user = _current_user()
    rule = ForwardRule.query.get_or_404(rule_id)
    if not _owns_rule(user, rule):
        return jsonify({"error": "Not found"}), 404

    page = int(request.args.get("page", 1))
    per_page = min(int(request.args.get("per_page", 20)), 50)
    logs = rule.logs.order_by(ForwardLog.created_at.desc())\
        .paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        "logs": [l.to_dict() for l in logs.items],
        "total": logs.total,
        "page": page,
    })


# ── Pending approval queue ────────────────────────────────────────────────────

@forwarding_bp.route("/pending", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def list_pending():
    user = _current_user()
    rule_ids = [r.id for r in ForwardRule.query.filter_by(owner_user_id=user.id).all()]
    if not rule_ids:
        return jsonify({"pending": []})
    pending = ForwardLog.query.filter(
        ForwardLog.rule_id.in_(rule_ids),
        ForwardLog.status == "pending_approval",
    ).order_by(ForwardLog.created_at.desc()).limit(100).all()
    return jsonify({"pending": [p.to_dict() for p in pending]})


@forwarding_bp.route("/pending/<int:log_id>/approve", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def approve_pending(log_id):
    user = _current_user()
    log_entry = ForwardLog.query.get_or_404(log_id)
    rule = ForwardRule.query.get(log_entry.rule_id)
    if not rule or not _owns_rule(user, rule):
        return jsonify({"error": "Not found"}), 404
    if log_entry.status != "pending_approval":
        return jsonify({"error": "Not pending"}), 400

    # Attempt to send via the OWNING bot's event loop (official or custom),
    # resolved from the source chat — then deliver through the shared runtime
    # so the anti-ban governor + topic targeting apply here too.
    try:
        from ..automation.bot_resolver import resolve_bot_loop_for_chat
        from ..automation.forwarding_runtime import deliver_pending_log

        bot, loop = resolve_bot_loop_for_chat(log_entry.source_chat_id)
        if bot and loop and loop.is_running():
            import asyncio
            future = asyncio.run_coroutine_threadsafe(
                deliver_pending_log(bot, rule, log_entry), loop
            )
            try:
                ok, err = future.result(timeout=15)
            except Exception as exc:
                ok, err = False, str(exc)[:500]
            if not ok:
                log_entry.status = "failed"
                log_entry.error_msg = err
                db.session.commit()
                return jsonify({"error": "Forward failed", "detail": err}), 502
        else:
            log_entry.status = "failed"
            log_entry.error_msg = "Bot not running for source chat"
            db.session.commit()
            return jsonify({"error": "Bot unavailable — could not forward message"}), 502

        log_entry.status = "approved"
        rule.forward_count = (rule.forward_count or 0) + 1
        db.session.commit()
        return jsonify({"ok": True})
    except Exception as exc:
        _log.warning("Approve forward failed: %s", exc)
        try:
            log_entry.status = "failed"
            log_entry.error_msg = str(exc)[:500]
            db.session.commit()
        except Exception:
            pass
        return jsonify({"error": "Bot unavailable — could not forward message", "detail": str(exc)}), 502


@forwarding_bp.route("/pending/<int:log_id>/reject", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def reject_pending(log_id):
    user = _current_user()
    log_entry = ForwardLog.query.get_or_404(log_id)
    rule = ForwardRule.query.get(log_entry.rule_id)
    if not rule or not _owns_rule(user, rule):
        return jsonify({"error": "Not found"}), 404
    if log_entry.status != "pending_approval":
        return jsonify({"error": "Not pending"}), 400
    log_entry.status = "rejected"
    db.session.commit()
    return jsonify({"ok": True})
