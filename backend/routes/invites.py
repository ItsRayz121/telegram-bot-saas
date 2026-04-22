import asyncio
import logging
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..models import db, User, Bot, Group, InviteLink, InviteLinkJoin
from ..middleware.rate_limit import rate_limit

logger = logging.getLogger(__name__)

invites_bp = Blueprint("invites", __name__, url_prefix="/api")


def _get_current_user():
    return User.query.get(int(get_jwt_identity()))


def _get_group(user, bot_id, group_id):
    bot = Bot.query.filter_by(id=bot_id, user_id=user.id).first()
    if not bot:
        return None, None
    group = Group.query.filter_by(id=group_id, bot_id=bot.id).first()
    return bot, group


@invites_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/invite-links", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def list_invite_links(bot_id, group_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    _, group = _get_group(user, bot_id, group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404

    time_filter = request.args.get("time_filter", "all")  # 1d | 7d | 30d | all
    links = InviteLink.query.filter_by(group_id=group.id).order_by(InviteLink.created_at.desc()).all()

    result = []
    for link in links:
        d = link.to_dict(include_analytics=True)
        # Apply time filter to the "featured" count shown
        if time_filter == "1d":
            d["featured_joins"] = d["joins_1d"]
        elif time_filter == "7d":
            d["featured_joins"] = d["joins_7d"]
        elif time_filter == "30d":
            d["featured_joins"] = d["joins_30d"]
        else:
            d["featured_joins"] = d["joins_total"]
        result.append(d)

    return jsonify({"invite_links": result})


@invites_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/invite-links", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def create_invite_link(bot_id, group_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    bot_obj, group = _get_group(user, bot_id, group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404

    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Name is required"}), 400

    max_uses = data.get("max_uses")
    expire_date = None
    if data.get("expire_date"):
        try:
            expire_date = datetime.fromisoformat(data["expire_date"].replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            return jsonify({"error": "Invalid expire_date format"}), 400

    link = InviteLink(
        group_id=group.id,
        name=name,
        max_uses=int(max_uses) if max_uses else None,
        expire_date=expire_date,
        is_active=True,
        created_by_user_id=user.id,
    )
    db.session.add(link)
    db.session.flush()

    # Generate real Telegram invite link via bot
    from ..app import bot_manager
    instance = bot_manager.active_bots.get(bot_obj.id)
    if instance and instance.application and instance.loop and instance.loop.is_running():
        future = asyncio.run_coroutine_threadsafe(
            _create_telegram_link(instance, group, link, expire_date, max_uses),
            instance.loop,
        )
        try:
            tg_link = future.result(timeout=10)
            link.telegram_invite_link = tg_link
        except Exception as e:
            logger.error(f"Telegram invite link creation error: {e}")

    db.session.commit()
    return jsonify({"invite_link": link.to_dict(include_analytics=True)}), 201


async def _create_telegram_link(instance, group, link, expire_date, max_uses):
    kwargs = {
        "chat_id": group.telegram_group_id,
        "name": link.name[:32],
        "creates_join_request": False,
    }
    if max_uses:
        kwargs["member_limit"] = int(max_uses)
    if expire_date:
        kwargs["expire_date"] = expire_date
    result = await instance.application.bot.create_chat_invite_link(**kwargs)
    return result.invite_link


@invites_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/invite-links/<int:link_id>", methods=["DELETE"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def delete_invite_link(bot_id, group_id, link_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    _, group = _get_group(user, bot_id, group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404
    link = InviteLink.query.filter_by(id=link_id, group_id=group.id).first()
    if not link:
        return jsonify({"error": "Invite link not found"}), 404
    link.is_active = False
    db.session.commit()
    return jsonify({"success": True})


@invites_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/invite-links/<int:link_id>/analytics", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def invite_link_analytics(bot_id, group_id, link_id):
    """Return join events for a specific invite link, optionally filtered by time range."""
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    _, group = _get_group(user, bot_id, group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404

    link = InviteLink.query.filter_by(id=link_id, group_id=group.id).first()
    if not link:
        return jsonify({"error": "Invite link not found"}), 404

    now = datetime.utcnow()
    joins_query = InviteLinkJoin.query.filter_by(invite_link_id=link.id)

    time_filter = request.args.get("time_filter", "all")
    if time_filter == "1d":
        joins_query = joins_query.filter(InviteLinkJoin.joined_at >= now - timedelta(days=1))
    elif time_filter == "7d":
        joins_query = joins_query.filter(InviteLinkJoin.joined_at >= now - timedelta(days=7))
    elif time_filter == "30d":
        joins_query = joins_query.filter(InviteLinkJoin.joined_at >= now - timedelta(days=30))

    joins = joins_query.order_by(InviteLinkJoin.joined_at.desc()).limit(100).all()
    return jsonify({
        "link": link.to_dict(include_analytics=True),
        "joins": [j.to_dict() for j in joins],
    })
