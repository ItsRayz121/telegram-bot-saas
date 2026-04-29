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
from ..models import db, User, TelegramGroup, ForwardRule, ForwardLog
from ..middleware.rate_limit import rate_limit

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
    source_group_id = (data.get("source_group_id") or "").strip()
    destination_id = (data.get("destination_id") or "").strip()
    keyword_filter = (data.get("keyword_filter") or "").strip() or None
    match_type = data.get("match_type", "contains")
    prefix_text = (data.get("prefix_text") or "").strip() or None
    suffix_text = (data.get("suffix_text") or "").strip() or None
    require_approval = bool(data.get("require_approval", False))

    if not rule_name:
        return jsonify({"error": "rule_name is required"}), 400
    if not source_group_id:
        return jsonify({"error": "source_group_id is required"}), 400
    if not destination_id:
        return jsonify({"error": "destination_id is required"}), 400
    if match_type not in _VALID_MATCH:
        return jsonify({"error": f"match_type must be one of {sorted(_VALID_MATCH)}"}), 400

    # Verify the user owns the source group
    if not _owns_group(user, source_group_id):
        return jsonify({"error": "Source group not found or not owned by you"}), 404

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
        source_group_id=source_group_id,
        destination_id=destination_id[:255],
        keyword_filter=keyword_filter[:1000] if keyword_filter else None,
        match_type=match_type,
        prefix_text=prefix_text[:500] if prefix_text else None,
        suffix_text=suffix_text[:500] if suffix_text else None,
        require_approval=require_approval,
        is_active=True,
    )
    db.session.add(rule)
    db.session.commit()
    return jsonify({"rule": rule.to_dict()}), 201


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
    if "destination_id" in data:
        rule.destination_id = (data["destination_id"] or "").strip()[:255]
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

    db.session.commit()
    return jsonify({"rule": rule.to_dict()})


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

    # Attempt to send via the running bot event loop
    try:
        from ..official_bot import get_official_bot_loop

        bot, loop = get_official_bot_loop()
        if bot and loop and loop.is_running():
            async def _do_forward():
                if rule.prefix_text or rule.suffix_text:
                    parts = []
                    if rule.prefix_text:
                        parts.append(rule.prefix_text)
                    if log_entry.source_text:
                        parts.append(log_entry.source_text)
                    if rule.suffix_text:
                        parts.append(rule.suffix_text)
                    await bot.send_message(chat_id=rule.destination_id, text="\n".join(parts))
                else:
                    await bot.copy_message(
                        chat_id=rule.destination_id,
                        from_chat_id=log_entry.source_chat_id,
                        message_id=log_entry.source_message_id,
                    )

            import asyncio
            future = asyncio.run_coroutine_threadsafe(_do_forward(), loop)
            try:
                future.result(timeout=10)
            except Exception as exc:
                log_entry.status = "failed"
                log_entry.error_msg = str(exc)[:500]
                db.session.commit()
                return jsonify({"error": "Forward failed", "detail": str(exc)}), 502

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
