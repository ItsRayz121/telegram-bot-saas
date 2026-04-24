from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..models import db, User, Bot, Group, Poll
from ..middleware.rate_limit import rate_limit

_PAID_TIERS = {"pro", "enterprise"}


def _require_paid(user, feature="This feature"):
    """Return a 403 response tuple if user lacks a valid paid subscription, else None."""
    if user.subscription_tier not in _PAID_TIERS:
        return (
            jsonify({"error": f"{feature} requires a Pro or Enterprise subscription. Upgrade at /pricing."}),
            403,
        )
    if user.subscription_expires and datetime.utcnow() > user.subscription_expires:
        return (
            jsonify({"error": "Your subscription has expired. Please renew to continue using this feature."}),
            403,
        )
    return None

polls_bp = Blueprint("polls", __name__, url_prefix="/api")


def _get_current_user():
    return User.query.get(int(get_jwt_identity()))


def _get_group(user, bot_id, group_id):
    bot = Bot.query.filter_by(id=bot_id, user_id=user.id).first()
    if not bot:
        return None, None
    group = Group.query.filter_by(id=group_id, bot_id=bot.id).first()
    return bot, group


@polls_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/polls", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def list_polls(bot_id, group_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    _, group = _get_group(user, bot_id, group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404
    polls = Poll.query.filter_by(group_id=group.id).order_by(Poll.created_at.desc()).all()
    return jsonify({"polls": [p.to_dict() for p in polls]})


@polls_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/polls", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def create_poll(bot_id, group_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    bot_obj, group = _get_group(user, bot_id, group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404

    # Scheduled polls are a paid feature; enforce before touching the DB.
    data = request.get_json() or {}
    if data.get("scheduled_at"):
        sub_err = _require_paid(user, "Scheduled polls")
        if sub_err:
            return sub_err

    question = (data.get("question") or "").strip()
    options = data.get("options") or []

    if not question:
        return jsonify({"error": "Question is required"}), 400
    if len(options) < 2 or len(options) > 10:
        return jsonify({"error": "Need 2-10 options"}), 400

    is_quiz = bool(data.get("is_quiz"))
    correct_idx = data.get("correct_option_index")
    if is_quiz and (correct_idx is None or not (0 <= int(correct_idx) < len(options))):
        return jsonify({"error": "Quiz requires a valid correct_option_index"}), 400

    # Authoritative timezone: groups.timezone column → settings JSON → UTC
    group_default_tz = (
        group.timezone
        or (group.settings or {}).get("timezone", "UTC")
        or "UTC"
    )
    tz_name = (data.get("timezone") or group_default_tz).strip() or "UTC"
    scheduled_at = None
    if data.get("scheduled_at"):
        try:
            from zoneinfo import ZoneInfo
            s = data["scheduled_at"].strip()
            has_tz_info = s.endswith("Z") or (
                "T" in s and ("+" in s[10:] or s.count("-") > 2)
            )
            if has_tz_info:
                s = s.replace("Z", "+00:00")
                if len(s) == 16:
                    s += ":00"
                dt = datetime.fromisoformat(s)
                if dt.tzinfo is not None:
                    from datetime import timezone as _stdtz
                    dt = dt.astimezone(_stdtz.utc)
                scheduled_at = dt.replace(tzinfo=None)
            else:
                if len(s) == 16:
                    s += ":00"
                try:
                    zone = ZoneInfo(tz_name)
                except Exception:
                    zone = ZoneInfo("UTC")
                local_dt = datetime.fromisoformat(s).replace(tzinfo=zone)
                scheduled_at = local_dt.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
        except Exception:
            return jsonify({"error": "Invalid scheduled_at format"}), 400

    poll = Poll(
        group_id=group.id,
        question=question,
        options=[str(o) for o in options],
        is_quiz=is_quiz,
        correct_option_index=int(correct_idx) if correct_idx is not None else None,
        is_anonymous=bool(data.get("is_anonymous", True)),
        allows_multiple=bool(data.get("allows_multiple", False)) and not is_quiz,
        explanation=(data.get("explanation") or "")[:200] or None,
        scheduled_at=scheduled_at,
        timezone=tz_name if scheduled_at else None,
        is_sent=False,
    )
    db.session.add(poll)
    db.session.commit()

    # Send immediately if no schedule
    if not scheduled_at:
        from ..app import bot_manager
        import asyncio
        instance = bot_manager.active_bots.get(bot_obj.id)
        if instance and instance.application and instance.loop and instance.loop.is_running():
            async def _send(p=poll, g=group):
                try:
                    kwargs = {
                        "chat_id": g.telegram_group_id,
                        "question": p.question,
                        "options": p.options,
                        "is_anonymous": p.is_anonymous,
                    }
                    if p.is_quiz:
                        kwargs["type"] = "quiz"
                        kwargs["correct_option_id"] = p.correct_option_index
                        if p.explanation:
                            kwargs["explanation"] = p.explanation
                    else:
                        kwargs["allows_multiple_answers"] = p.allows_multiple
                    await instance.application.bot.send_poll(**kwargs)
                    p.is_sent = True
                    db.session.commit()
                except Exception as exc:
                    import logging
                    logging.getLogger(__name__).error(f"Poll send error: {exc}")
            asyncio.run_coroutine_threadsafe(_send(), instance.loop)

    return jsonify({"poll": poll.to_dict()}), 201


@polls_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/polls/<int:poll_id>", methods=["DELETE"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def delete_poll(bot_id, group_id, poll_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    _, group = _get_group(user, bot_id, group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404
    poll = Poll.query.filter_by(id=poll_id, group_id=group.id).first()
    if not poll:
        return jsonify({"error": "Poll not found"}), 404
    db.session.delete(poll)
    db.session.commit()
    return jsonify({"success": True})
