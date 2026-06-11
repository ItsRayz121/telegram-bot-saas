"""White-label custom bot endpoints (Phase 9).

  GET    /api/custom-bots                      -> the user's custom bots
  POST   /api/custom-bots                      -> connect a bot {token}
  POST   /api/custom-bots/<id>/token           -> replace the token (after a reset)
  POST   /api/custom-bots/<id>/recheck         -> re-read intent flags / revive from error
  DELETE /api/custom-bots/<id>                 -> disconnect (unlinks its guilds)
  GET    /api/custom-bots/<id>/invite          -> invite URL for THEIR application
  POST   /api/custom-bots/<id>/guilds/<gid>    -> link a guild to this bot
  DELETE /api/custom-bots/<id>/guilds/<gid>    -> unlink (guild reverts to official bot)

Tokens are validated against Discord before save, stored Fernet-encrypted, and
never returned after that. The bot worker picks up changes via needs_restart.
"""
from __future__ import annotations

from urllib.parse import urlencode

import requests
from flask import Blueprint, g, jsonify, request

import crypto
import discord_api
from auth import login_required
from models import CustomBot, Guild, UserGuild

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
    bots = (
        g.db.query(CustomBot)
        .filter(CustomBot.owner_user_id == g.user_id)
        .order_by(CustomBot.created_at)
        .all()
    )
    return jsonify(bots=[_bot_payload(b) for b in bots])


@custom_bots_bp.post("/api/custom-bots")
@login_required
def connect_bot():
    token = ((request.get_json(silent=True) or {}).get("token") or "").strip()
    if not token:
        return jsonify(error="token_required"), 400

    count = g.db.query(CustomBot).filter(CustomBot.owner_user_id == g.user_id).count()
    if count >= MAX_BOTS_PER_USER:
        return jsonify(error="bot_limit_reached", limit=MAX_BOTS_PER_USER), 403

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


@custom_bots_bp.delete("/api/custom-bots/<int:bot_id>")
@login_required
def disconnect_bot(bot_id: int):
    bot = _own_bot_or_404(bot_id)
    if bot is None:
        return jsonify(error="not_found"), 404
    # Guilds revert to the official bot; the worker stops the client on next reconcile.
    g.db.query(Guild).filter(Guild.custom_bot_id == bot.id).update({"custom_bot_id": None})
    g.db.delete(bot)
    g.db.commit()
    return jsonify(ok=True)


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
    membership = g.db.get(UserGuild, {"user_id": g.user_id, "guild_id": guild_id})
    if membership is None or not membership.can_manage:
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
    if guild.custom_bot_id == bot.id:
        guild.custom_bot_id = None
        g.db.commit()
    return jsonify(ok=True, guild=guild.to_dict())
