"""Discord OAuth2 login for Guildizer (replaces Telegizer's Mini App initData auth).

Flow:
  GET  /auth/discord/login     -> redirect to Discord's authorize screen
  GET  /auth/discord/callback  -> exchange code, upsert user + guild memberships,
                                  set a signed session cookie, bounce to frontend
  GET  /auth/me                -> the logged-in user (or 401)
  POST /auth/logout            -> clear the session cookie

The session is a signed, timed token (itsdangerous) carrying just the user id,
stored in an httpOnly cookie. No server-side session store needed.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from functools import wraps
from urllib.parse import urlencode

from flask import (
    Blueprint,
    current_app,
    g,
    jsonify,
    make_response,
    redirect,
    request,
)
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

import discord_api
from config import Config
from database import SessionLocal
from models import Guild, User, UserGuild

auth_bp = Blueprint("auth", __name__)

_OAUTH_SCOPES = "identify guilds"
_STATE_COOKIE = "guildizer_oauth_state"


# --- session token helpers ----------------------------------------------------
def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(Config.SECRET_KEY, salt="guildizer-session")


def _issue_session(user_id: int) -> str:
    return _serializer().dumps({"uid": str(user_id)})


def _read_session(token: str) -> int | None:
    try:
        data = _serializer().loads(token, max_age=Config.SESSION_MAX_AGE)
        return int(data["uid"])
    except (BadSignature, SignatureExpired, KeyError, ValueError, TypeError):
        return None


def _set_session_cookie(resp, user_id: int) -> None:
    resp.set_cookie(
        Config.SESSION_COOKIE_NAME,
        _issue_session(user_id),
        max_age=Config.SESSION_MAX_AGE,
        httponly=True,
        secure=Config.SESSION_COOKIE_SECURE,
        samesite=Config.SESSION_COOKIE_SAMESITE,
    )


def _clear_session_cookie(resp) -> None:
    resp.delete_cookie(
        Config.SESSION_COOKIE_NAME,
        samesite=Config.SESSION_COOKIE_SAMESITE,
        secure=Config.SESSION_COOKIE_SECURE,
    )


# --- request-scoped current user ----------------------------------------------
def current_user_id() -> int | None:
    token = request.cookies.get(Config.SESSION_COOKIE_NAME)
    if not token:
        return None
    return _read_session(token)


def login_required(fn):
    """Guards an endpoint; sets g.user_id and g.db (a session) for the handler."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        uid = current_user_id()
        if uid is None:
            return jsonify(error="unauthorized"), 401
        g.user_id = uid
        g.db = SessionLocal()
        try:
            return fn(*args, **kwargs)
        finally:
            g.db.close()
            SessionLocal.remove()

    return wrapper


# --- routes -------------------------------------------------------------------
@auth_bp.get("/auth/discord/login")
def discord_login():
    if not Config.DISCORD_CLIENT_ID:
        return jsonify(error="DISCORD_CLIENT_ID not configured"), 500
    state = secrets.token_urlsafe(24)
    params = {
        "client_id": Config.DISCORD_CLIENT_ID,
        "redirect_uri": Config.DISCORD_REDIRECT_URI,
        "response_type": "code",
        "scope": _OAUTH_SCOPES,
        "state": state,
        "prompt": "consent",
    }
    url = f"{discord_api.AUTHORIZE_URL}?{urlencode(params)}"
    resp = make_response(redirect(url))
    # short-lived CSRF state cookie
    resp.set_cookie(
        _STATE_COOKIE,
        state,
        max_age=600,
        httponly=True,
        secure=Config.SESSION_COOKIE_SECURE,
        samesite=Config.SESSION_COOKIE_SAMESITE,
    )
    return resp


@auth_bp.get("/auth/discord/callback")
def discord_callback():
    error = request.args.get("error")
    if error:
        return redirect(f"{Config.FRONTEND_URL}/login?error={error}")

    code = request.args.get("code")
    state = request.args.get("state")
    expected_state = request.cookies.get(_STATE_COOKIE)
    if not code or not state or state != expected_state:
        return redirect(f"{Config.FRONTEND_URL}/login?error=invalid_state")

    try:
        token = discord_api.exchange_code(code)
        access_token = token["access_token"]
        profile = discord_api.get_current_user(access_token)
        guilds = discord_api.get_user_guilds(access_token)
    except Exception:  # noqa: BLE001 — surface any OAuth/REST failure as a clean bounce
        current_app.logger.exception("Discord OAuth callback failed")
        return redirect(f"{Config.FRONTEND_URL}/login?error=oauth_failed")

    db = SessionLocal()
    try:
        user_id = int(profile["id"])
        user = db.get(User, user_id) or User(id=user_id)
        user.username = profile.get("username")
        user.global_name = profile.get("global_name")
        user.avatar = profile.get("avatar")
        user.access_token = access_token
        user.refresh_token = token.get("refresh_token")
        expires_in = int(token.get("expires_in", 0) or 0)
        user.token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        user.last_login_at = datetime.utcnow()
        db.add(user)

        _sync_memberships(db, user_id, guilds)
        db.commit()
    finally:
        db.close()
        SessionLocal.remove()

    resp = make_response(redirect(f"{Config.FRONTEND_URL}/dashboard"))
    _set_session_cookie(resp, user_id)
    resp.delete_cookie(_STATE_COOKIE)
    return resp


def _sync_memberships(db, user_id: int, guilds: list[dict]) -> None:
    """Upsert the user's guild list into Guild + UserGuild rows.

    We only ever *create* guild stubs here (name/icon) — bot_present is left for
    the bot's gateway sync to set. Stale memberships (left servers) are removed.
    """
    seen: set[int] = set()
    for gd in guilds:
        gid = int(gd["id"])
        seen.add(gid)
        permissions = int(gd.get("permissions", 0) or 0)
        is_owner = bool(gd.get("owner"))

        guild = db.get(Guild, gid)
        if guild is None:
            guild = Guild(id=gid, bot_present=False)
            db.add(guild)
        guild.name = gd.get("name")
        guild.icon = gd.get("icon")
        if is_owner and guild.owner_id is None:
            guild.owner_id = user_id

        membership = db.get(UserGuild, {"user_id": user_id, "guild_id": gid})
        if membership is None:
            membership = UserGuild(user_id=user_id, guild_id=gid)
            db.add(membership)
        membership.permissions = str(permissions)
        membership.is_owner = is_owner
        membership.can_manage = discord_api.can_manage(permissions, is_owner=is_owner)
        membership.updated_at = datetime.utcnow()

    # drop memberships the user no longer has
    stale = (
        db.query(UserGuild)
        .filter(UserGuild.user_id == user_id, ~UserGuild.guild_id.in_(seen or {0}))
        .all()
    )
    for m in stale:
        db.delete(m)


@auth_bp.get("/auth/me")
def me():
    uid = current_user_id()
    if uid is None:
        return jsonify(error="unauthorized"), 401
    db = SessionLocal()
    try:
        user = db.get(User, uid)
        if user is None:
            return jsonify(error="unauthorized"), 401
        data = user.to_dict()
        data["is_admin"] = uid in Config.ADMIN_USER_IDS
        return jsonify(data)
    finally:
        db.close()
        SessionLocal.remove()


@auth_bp.post("/auth/logout")
def logout():
    resp = make_response(jsonify(ok=True))
    _clear_session_cookie(resp)
    return resp
