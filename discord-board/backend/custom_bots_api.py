"""White-label custom bot endpoints (Phase 9).

  GET    /api/custom-bots                      -> the user's custom bots
  POST   /api/custom-bots                      -> connect a bot {token}
  POST   /api/custom-bots/<id>/token           -> replace the token (after a reset)
  POST   /api/custom-bots/<id>/recheck         -> re-read intent flags / revive from error
  POST   /api/custom-bots/<id>/stop            -> owner switches the bot off (status=disabled)
  POST   /api/custom-bots/<id>/start           -> turn a stopped bot back on (needs Pro)
  DELETE /api/custom-bots/<id>                 -> disconnect (unlinks its guilds)
  GET    /api/custom-bots/<id>/invite          -> invite URL for THEIR application
  POST   /api/custom-bots/<id>/guilds/<gid>    -> link a guild to this bot
  DELETE /api/custom-bots/<id>/guilds/<gid>    -> unlink (guild reverts to official bot)

Tokens are validated against Discord before save, stored Fernet-encrypted, and
never returned after that. The bot worker picks up changes via needs_restart.
"""
from __future__ import annotations

import os
from urllib.parse import urlencode

import requests
from flask import Blueprint, g, jsonify, request

import crypto
import discord_api
import access
import plan_limits
from auth import login_required
from models import CustomBot, Guild

custom_bots_bp = Blueprint("custom_bots", __name__)

MAX_BOTS_PER_USER = 5


def _own_bot_or_404(bot_id: int) -> CustomBot | None:
    bot = g.db.get(CustomBot, bot_id)
    if bot is None or bot.owner_user_id != g.user_id:
        return None
    return bot


def _bot_payload(bot: CustomBot) -> dict:
    data = bot.to_dict()
    linked = g.db.query(Guild).filter(Guild.custom_bot_id == bot.id).all()
    data["linked_guilds"] = [
        {"id": str(gu.id), "name": gu.name, "icon_url": gu.icon_url()} for gu in linked
    ]
    return data


@custom_bots_bp.get("/api/custom-bots")
@login_required
def list_bots():
    # The page loads this on every visit, so it keeps a paid Telegizer plan fresh
    # for the lifecycle job (no-op without the token header).
    import custom_bot_lifecycle
    custom_bot_lifecycle.refresh_unified_pro(g.db, g.user_id)
    bots = (
        g.db.query(CustomBot)
        .filter(CustomBot.owner_user_id == g.user_id)
        .order_by(CustomBot.created_at)
        .all()
    )
    # `entitled` lets the page show the right plan label and enable Add Bot for owners whose
    # Pro comes from a paid Telegizer plan rather than a Pro server.
    entitled = custom_bot_lifecycle.owner_entitled(g.db, g.user_id)
    from admin import bridge_status
    return jsonify(bots=[_bot_payload(b) for b in bots], entitled=entitled, plan_bridge=bridge_status())


@custom_bots_bp.post("/api/custom-bots")
@login_required
def connect_bot():
    token = ((request.get_json(silent=True) or {}).get("token") or "").strip()
    if not token:
        return jsonify(error="token_required"), 400

    count = g.db.query(CustomBot).filter(CustomBot.owner_user_id == g.user_id).count()
    if count >= MAX_BOTS_PER_USER:
        return jsonify(error="bot_limit_reached", limit=MAX_BOTS_PER_USER), 403
    # White-label bots are the top-tier feature (Phase 18): the user must
    # manage at least one Pro server.
    if plan_limits.CUSTOM_BOTS_REQUIRE_PRO:
        # A paid Telegizer plan counts too (unified subscription); refreshing it
        # also stamps the user so the lifecycle job agrees with this check.
        import custom_bot_lifecycle
        custom_bot_lifecycle.refresh_unified_pro(g.db, g.user_id)
        if not custom_bot_lifecycle.owner_entitled(g.db, g.user_id):
            return jsonify(error="pro_required",
                           message="Custom bots need at least one Pro server."), 403

    try:
        info = discord_api.validate_bot_token(token)
    except discord_api.InvalidBotToken:
        return jsonify(error="invalid_token"), 422
    except requests.RequestException:
        return jsonify(error="discord_unreachable"), 502

    existing = (
        g.db.query(CustomBot)
        .filter(CustomBot.bot_user_id == info["bot_user_id"])
        .one_or_none()
    )
    if existing is not None and existing.owner_user_id != g.user_id:
        return jsonify(error="bot_already_connected"), 409

    bot = existing or CustomBot(owner_user_id=g.user_id, bot_user_id=info["bot_user_id"])
    bot.application_id = info["application_id"]
    bot.bot_username = info["bot_username"]
    bot.bot_avatar = info["bot_avatar"]
    bot.intents_members = info["intents_members"]
    bot.intents_message_content = info["intents_message_content"]
    bot.token_encrypted = crypto.encrypt_token(token)
    bot.status = "active"
    bot.error_detail = None
    bot.needs_restart = True
    # Connecting needs a Pro server (checked above), so any earlier lapse is over.
    bot.lapse_started_at = None
    bot.paused_at = None
    bot.pause_reason = None
    g.db.add(bot)
    g.db.commit()
    return jsonify(bot=_bot_payload(bot)), 201


@custom_bots_bp.post("/api/custom-bots/<int:bot_id>/token")
@login_required
def replace_token(bot_id: int):
    bot = _own_bot_or_404(bot_id)
    if bot is None:
        return jsonify(error="not_found"), 404
    token = ((request.get_json(silent=True) or {}).get("token") or "").strip()
    if not token:
        return jsonify(error="token_required"), 400
    try:
        info = discord_api.validate_bot_token(token)
    except discord_api.InvalidBotToken:
        return jsonify(error="invalid_token"), 422
    except requests.RequestException:
        return jsonify(error="discord_unreachable"), 502
    if info["bot_user_id"] != bot.bot_user_id:
        return jsonify(error="token_belongs_to_different_bot"), 422

    bot.bot_username = info["bot_username"]
    bot.bot_avatar = info["bot_avatar"]
    bot.intents_members = info["intents_members"]
    bot.intents_message_content = info["intents_message_content"]
    bot.token_encrypted = crypto.encrypt_token(token)
    # A paused bot only comes back through /reactivate, a stopped one through /start.
    if bot.status not in ("paused", "disabled"):
        bot.status = "active"
        bot.error_detail = None
        bot.needs_restart = True
    g.db.commit()
    return jsonify(bot=_bot_payload(bot))


@custom_bots_bp.post("/api/custom-bots/<int:bot_id>/recheck")
@login_required
def recheck_bot(bot_id: int):
    """Re-read the app's intent flags (after the owner toggles them in the portal)."""
    bot = _own_bot_or_404(bot_id)
    if bot is None:
        return jsonify(error="not_found"), 404
    token = crypto.decrypt_token(bot.token_encrypted)
    if token is None:
        bot.status = "error"
        bot.error_detail = "Stored token could not be decrypted — please re-enter it."
        g.db.commit()
        return jsonify(bot=_bot_payload(bot))
    try:
        info = discord_api.validate_bot_token(token)
    except discord_api.InvalidBotToken:
        bot.status = "error"
        bot.error_detail = "Discord rejected the stored token — it was probably reset. Enter the new token."
        g.db.commit()
        return jsonify(bot=_bot_payload(bot))
    except requests.RequestException:
        return jsonify(error="discord_unreachable"), 502

    bot.bot_username = info["bot_username"]
    bot.bot_avatar = info["bot_avatar"]
    bot.intents_members = info["intents_members"]
    bot.intents_message_content = info["intents_message_content"]
    if bot.status == "error":
        bot.status = "active"
        bot.error_detail = None
        bot.needs_restart = True
    g.db.commit()
    return jsonify(bot=_bot_payload(bot))


@custom_bots_bp.post("/api/custom-bots/<int:bot_id>/stop")
@login_required
def stop_bot(bot_id: int):
    """Owner switches the bot off. Nothing is deleted: the fleet worker stops the
    gateway client on its next tick and the bot can be started again."""
    bot = _own_bot_or_404(bot_id)
    if bot is None:
        return jsonify(error="not_found"), 404
    if bot.status == "paused":
        return jsonify(error="paused", message="This bot was paused because Pro ended. Use Reactivate."), 400
    bot.status = "disabled"
    g.db.commit()
    return jsonify(bot=_bot_payload(bot))


@custom_bots_bp.post("/api/custom-bots/<int:bot_id>/start")
@login_required
def start_bot(bot_id: int):
    """Turn a stopped bot back on. Needs the same Pro entitlement as running one."""
    import custom_bot_lifecycle
    bot = _own_bot_or_404(bot_id)
    if bot is None:
        return jsonify(error="not_found"), 404
    if bot.status != "disabled":
        return jsonify(error="not_stopped"), 400
    if not custom_bot_lifecycle.owner_entitled(g.db, g.user_id):
        return jsonify(error="pro_required", message="Custom bots need at least one Pro server."), 402
    bot.status = "active"
    bot.error_detail = None
    bot.needs_restart = True
    g.db.commit()
    return jsonify(bot=_bot_payload(bot))


@custom_bots_bp.post("/api/custom-bots/<int:bot_id>/reactivate")
@login_required
def reactivate_bot(bot_id: int):
    """Bring a PAUSED bot back after the owner renewed Pro. Resumes the existing
    row (it does not count as creating a new bot), and only if Pro is active again."""
    import custom_bot_lifecycle
    bot = _own_bot_or_404(bot_id)
    if bot is None:
        return jsonify(error="not_found"), 404
    if bot.status != "paused":
        return jsonify(error="not_paused"), 400
    if not custom_bot_lifecycle.owner_entitled(g.db, g.user_id):
        return jsonify(error="pro_required",
                       message="Renew Pro on one of your servers, then reactivate."), 402
    bot.status = "active"
    bot.error_detail = None
    bot.paused_at = None
    bot.pause_reason = None
    bot.lapse_started_at = None
    bot.needs_restart = True
    from models import CustomBotLifecycleStage
    g.db.query(CustomBotLifecycleStage).filter(CustomBotLifecycleStage.bot_id == bot.id).delete(synchronize_session=False)
    g.db.commit()
    return jsonify(bot=_bot_payload(bot))


def _leave_servers(bot, guild_ids) -> tuple[int, int]:
    """Have the bot leave the given servers. LEAVE_ON_DISCONNECT=0 turns this off
    without a deploy. Never raises: a Discord problem must not block the unlink."""
    if not guild_ids or os.getenv("LEAVE_ON_DISCONNECT", "1") == "0":
        return 0, 0
    token = crypto.decrypt_token(bot.token_encrypted) if bot.token_encrypted else None
    if not token:
        return 0, 0
    return discord_api.leave_guilds(token, guild_ids)


def _settle_after_leave(db, guild_ids) -> None:
    """A custom bot's sync marks the server bot_present. Once it has left, the
    server is only 'installed' if the official bot really is in it."""
    for gid in guild_ids:
        guild = db.get(Guild, gid)
        present = discord_api.official_bot_in_guild(gid)
        if guild is not None and present is not None:
            guild.bot_present = present


@custom_bots_bp.delete("/api/custom-bots/<int:bot_id>")
@login_required
def disconnect_bot(bot_id: int):
    bot = _own_bot_or_404(bot_id)
    if bot is None:
        return jsonify(error="not_found"), 404
    # ?leave=1 also removes the bot from the servers linked to it (only those),
    # using its own token before that token is deleted.
    left, failed = 0, 0
    if request.args.get("leave") == "1":
        linked = [gid for (gid,) in g.db.query(Guild.id).filter(Guild.custom_bot_id == bot.id).all()]
        left, failed = _leave_servers(bot, linked)
        if left:
            _settle_after_leave(g.db, linked)
    # Servers lose this bot; they only show as installed if the official bot is in them.
    g.db.query(Guild).filter(Guild.custom_bot_id == bot.id).update({"custom_bot_id": None})
    g.db.delete(bot)
    g.db.commit()
    return jsonify(ok=True, left_servers=left, failed_servers=failed)


@custom_bots_bp.get("/api/custom-bots/<int:bot_id>/invite")
@login_required
def bot_invite(bot_id: int):
    bot = _own_bot_or_404(bot_id)
    if bot is None:
        return jsonify(error="not_found"), 404
    params = {
        "client_id": str(bot.application_id),
        "scope": "bot applications.commands",
        "permissions": str(discord_api.bot_invite_permissions()),
    }
    return jsonify(invite_url=f"{discord_api.AUTHORIZE_URL}?{urlencode(params)}")


def _manageable_guild(guild_id: int) -> Guild | None:
    if not access.can_manage_guild(g.db, g.user_id, guild_id):
        return None
    return g.db.get(Guild, guild_id)


@custom_bots_bp.post("/api/custom-bots/<int:bot_id>/guilds/<int:guild_id>")
@login_required
def link_guild(bot_id: int, guild_id: int):
    bot = _own_bot_or_404(bot_id)
    if bot is None:
        return jsonify(error="not_found"), 404
    guild = _manageable_guild(guild_id)
    if guild is None:
        return jsonify(error="forbidden"), 403
    guild.custom_bot_id = bot.id
    g.db.commit()
    return jsonify(ok=True, guild=guild.to_dict())


@custom_bots_bp.delete("/api/custom-bots/<int:bot_id>/guilds/<int:guild_id>")
@login_required
def unlink_guild(bot_id: int, guild_id: int):
    bot = _own_bot_or_404(bot_id)
    if bot is None:
        return jsonify(error="not_found"), 404
    guild = _manageable_guild(guild_id)
    if guild is None:
        return jsonify(error="forbidden"), 403
    left = 0
    if guild.custom_bot_id == bot.id:
        # ?leave=1 also removes the bot from this one server.
        if request.args.get("leave") == "1":
            left, _ = _leave_servers(bot, [guild.id])
            if left:
                _settle_after_leave(g.db, [guild.id])
        guild.custom_bot_id = None
        g.db.commit()
    return jsonify(ok=True, guild=guild.to_dict(), left=bool(left))
