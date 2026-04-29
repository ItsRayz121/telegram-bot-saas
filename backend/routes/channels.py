"""Channel analytics — CRUD + metrics endpoints."""
from datetime import datetime, date, timedelta
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..models import db, Channel, ChannelPost, ChannelDailyStat, User
from ..official_bot import get_official_bot_loop
import asyncio
import logging

logger = logging.getLogger(__name__)
channels_bp = Blueprint("channels", __name__)

TIER_LIMITS = {"free": 2, "pro": 20, "enterprise": 100}


def _get_user():
    return User.query.get(int(get_jwt_identity()))


def _recompute_averages(channel):
    """Update rolling 30-day averages on the channel row."""
    cutoff = datetime.utcnow() - timedelta(days=30)
    posts = channel.posts.filter(ChannelPost.posted_at >= cutoff).all()
    if not posts:
        return
    channel.avg_views = sum(p.views for p in posts) / len(posts)
    channel.avg_reactions = sum(p.reactions for p in posts) / len(posts)
    channel.avg_forwards = sum(p.forwards for p in posts) / len(posts)
    total_views = sum(p.views for p in posts)
    total_reactions = sum(p.reactions for p in posts)
    channel.engagement_rate = (total_reactions / total_views * 100) if total_views else 0


async def _fetch_chat_info(bot, channel_id: str):
    """Return (chat, member_count) or raise."""
    chat = await bot.get_chat(channel_id)
    count = await bot.get_chat_member_count(channel_id)
    return chat, count


async def _check_bot_admin(bot, channel_id: str) -> bool:
    try:
        me = await bot.get_me()
        member = await bot.get_chat_member(channel_id, me.id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False


# ── List / Add ────────────────────────────────────────────────────────────────

@channels_bp.route("/api/channels", methods=["GET"])
@jwt_required()
def list_channels():
    user = _get_user()
    chs = Channel.query.filter_by(user_id=user.id).order_by(Channel.created_at.desc()).all()
    return jsonify([c.to_dict() for c in chs])


@channels_bp.route("/api/channels", methods=["POST"])
@jwt_required()
def add_channel():
    user = _get_user()
    limit = TIER_LIMITS.get(user.subscription_tier, 2)
    if Channel.query.filter_by(user_id=user.id).count() >= limit:
        return jsonify({"error": f"Your plan allows up to {limit} channels. Upgrade to add more."}), 403

    data = request.get_json() or {}
    raw = (data.get("channel_id") or "").strip()
    if not raw:
        return jsonify({"error": "channel_id is required (@username or -100xxx)"}), 400

    # Normalize to @username or numeric id
    channel_ref = raw if raw.startswith("-100") else (raw if raw.startswith("@") else f"@{raw}")

    bot, loop = get_official_bot_loop()
    if not bot or not loop:
        return jsonify({"error": "Bot not available. Try again shortly."}), 503

    try:
        chat, count = asyncio.run_coroutine_threadsafe(
            _fetch_chat_info(bot, channel_ref), loop
        ).result(timeout=10)
    except Exception as e:
        return jsonify({"error": f"Could not fetch channel: {e}"}), 400

    if chat.type != "channel":
        return jsonify({"error": "That is not a channel. Only Telegram channels are supported."}), 400

    tg_id = str(chat.id)
    if Channel.query.filter_by(telegram_channel_id=tg_id).first():
        return jsonify({"error": "This channel is already tracked."}), 409

    is_admin = asyncio.run_coroutine_threadsafe(
        _check_bot_admin(bot, tg_id), loop
    ).result(timeout=10)

    channel = Channel(
        user_id=user.id,
        telegram_channel_id=tg_id,
        username=chat.username,
        title=chat.title,
        description=chat.description,
        member_count=count,
        bot_status="active" if is_admin else "no_admin",
        last_refreshed_at=datetime.utcnow(),
    )
    db.session.add(channel)
    db.session.flush()

    # Seed today's daily stat
    today_stat = ChannelDailyStat(
        channel_id=channel.id,
        date=date.today(),
        member_count=count,
    )
    db.session.add(today_stat)
    db.session.commit()

    return jsonify(channel.to_dict()), 201


# ── Detail / Delete ───────────────────────────────────────────────────────────

@channels_bp.route("/api/channels/<int:cid>", methods=["GET"])
@jwt_required()
def get_channel(cid):
    user = _get_user()
    ch = Channel.query.filter_by(id=cid, user_id=user.id).first_or_404()
    data = ch.to_dict()

    # Last 30 days daily stats
    cutoff = date.today() - timedelta(days=30)
    stats = (ch.daily_stats
               .filter(ChannelDailyStat.date >= cutoff)
               .order_by(ChannelDailyStat.date)
               .all())
    data["daily_stats"] = [s.to_dict() for s in stats]

    # Top 5 posts by views
    top = (ch.posts
             .order_by(ChannelPost.views.desc())
             .limit(5)
             .all())
    data["top_posts"] = [p.to_dict() for p in top]
    return jsonify(data)


@channels_bp.route("/api/channels/<int:cid>", methods=["DELETE"])
@jwt_required()
def delete_channel(cid):
    user = _get_user()
    ch = Channel.query.filter_by(id=cid, user_id=user.id).first_or_404()
    db.session.delete(ch)
    db.session.commit()
    return jsonify({"ok": True})


# ── Posts list ────────────────────────────────────────────────────────────────

@channels_bp.route("/api/channels/<int:cid>/posts", methods=["GET"])
@jwt_required()
def list_posts(cid):
    user = _get_user()
    ch = Channel.query.filter_by(id=cid, user_id=user.id).first_or_404()
    page = request.args.get("page", 1, type=int)
    per_page = 20
    q = ch.posts.order_by(ChannelPost.posted_at.desc())
    total = q.count()
    posts = q.offset((page - 1) * per_page).limit(per_page).all()
    return jsonify({
        "posts": [p.to_dict() for p in posts],
        "total": total,
        "page": page,
        "pages": (total + per_page - 1) // per_page,
    })


# ── Refresh (re-fetch member count + recompute averages) ─────────────────────

@channels_bp.route("/api/channels/<int:cid>/refresh", methods=["POST"])
@jwt_required()
def refresh_channel(cid):
    user = _get_user()
    ch = Channel.query.filter_by(id=cid, user_id=user.id).first_or_404()

    bot, loop = get_official_bot_loop()
    if not bot or not loop:
        return jsonify({"error": "Bot not available"}), 503

    try:
        _, count = asyncio.run_coroutine_threadsafe(
            _fetch_chat_info(bot, ch.telegram_channel_id), loop
        ).result(timeout=10)
        ch.member_count = count

        is_admin = asyncio.run_coroutine_threadsafe(
            _check_bot_admin(bot, ch.telegram_channel_id), loop
        ).result(timeout=10)
        ch.bot_status = "active" if is_admin else "no_admin"
    except Exception as e:
        logger.warning("Channel refresh failed: %s", e)

    _recompute_averages(ch)
    ch.last_refreshed_at = datetime.utcnow()

    # Upsert today's daily stat
    today = date.today()
    stat = ch.daily_stats.filter_by(date=today).first()
    if not stat:
        stat = ChannelDailyStat(channel_id=ch.id, date=today)
        db.session.add(stat)

    stat.member_count = ch.member_count
    cutoff = datetime.utcnow() - timedelta(hours=24)
    todays_posts = ch.posts.filter(ChannelPost.posted_at >= cutoff).all()
    stat.posts_count = len(todays_posts)
    stat.total_views = sum(p.views for p in todays_posts)
    stat.total_reactions = sum(p.reactions for p in todays_posts)
    stat.total_forwards = sum(p.forwards for p in todays_posts)
    stat.avg_views_per_post = (stat.total_views / stat.posts_count) if stat.posts_count else 0

    db.session.commit()
    return jsonify(ch.to_dict())
