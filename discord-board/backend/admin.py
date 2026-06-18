"""Platform-admin RBAC for Guildizer.

Admins are configured by Discord user id (ADMIN_USER_IDS env), not stored in the
DB — so access can't be granted by tampering with data. admin_required guards
the admin API and, like login_required, sets g.user_id and g.db.

Super-admin bridge
------------------
A platform owner manages everything from the telegizer.com website with their
email login — they should not need a separate Discord login just to open the
Guildizer admin panel (the panel only *views* platform data; it owns no Discord
server, so Discord OAuth buys it nothing). So admin_required also accepts the
caller's Telegizer login: it validates the token against the main site's own
``/api/auth/me`` and, if that user is a Telegizer ``super_admin``, grants admin
here. We call the main site's *public* endpoint — no Telegizer code is imported
and no database is shared, preserving full product isolation. Bridge admins act
under the sentinel id ``BRIDGE_ADMIN_ID`` and are treated as super.
"""
from __future__ import annotations

import hashlib
import logging
import time
from functools import wraps

import requests
from flask import g, jsonify, request

log = logging.getLogger("guildizer.admin")

from auth import current_user_id
from config import Config
from database import SessionLocal

# Sentinel acting id for a super-admin who came in via the Telegizer email bridge
# (they have no Discord user row). admin_id columns are FK-free, so this is safe.
BRIDGE_ADMIN_ID = 0

# Header the Telegizer frontend attaches with the caller's website token so the
# Guildizer admin panel can authorise off the existing email login.
_BRIDGE_TOKEN_HEADER = "X-Telegizer-Token"

# Tiny cache so we don't hit the main site on every admin request. Keyed by a
# hash of the token → (expiry_epoch, identity_dict_or_None).
_BRIDGE_TTL = 60.0
_bridge_cache: dict[str, tuple[float, dict | None]] = {}


def bridge_super_admin():
    """Return ``{"email": ...}`` if the request carries a valid Telegizer
    super-admin token, else None. Validates against the main site's /api/auth/me.

    Disabled (returns None) unless TELEGIZER_API_URL is configured.
    """
    if not Config.TELEGIZER_API_URL:
        return None
    token = (request.headers.get(_BRIDGE_TOKEN_HEADER) or "").strip()
    if not token:
        return None

    key = hashlib.sha256(token.encode()).hexdigest()
    now = time.time()
    cached = _bridge_cache.get(key)
    if cached and cached[0] > now:
        return cached[1]

    identity = None
    try:
        resp = requests.get(
            f"{Config.TELEGIZER_API_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=6,
        )
        if resp.status_code == 200:
            user = (resp.json() or {}).get("user") or {}
            # Only a Telegizer super_admin is bridged in — full access, matching
            # "super admins can access everything".
            if user.get("admin_role") == "super_admin":
                identity = {"email": (user.get("email") or "").lower()}
            else:
                log.info("Bridge: token valid but not super_admin (role=%s).", user.get("admin_role"))
        else:
            # The classic misconfig: TELEGIZER_API_URL points at the Vercel front
            # end (no /api route) → 404 → bridge silently disabled. Log loudly.
            log.warning("Bridge: %s/api/auth/me returned %s — check TELEGIZER_API_URL "
                        "points at the BACKEND API base.", Config.TELEGIZER_API_URL, resp.status_code)
    except requests.RequestException as e:
        log.warning("Bridge: could not reach %s/api/auth/me (%s).", Config.TELEGIZER_API_URL, e)
        identity = None

    _bridge_cache[key] = (now + _BRIDGE_TTL, identity)
    return identity


def is_super(user_id) -> bool:
    """Env-configured super admins (bootstrap), the email bridge, or a DB-granted
    super role."""
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return False
    # Bridge admins act as id 0 and are always super (only super_admins bridge in).
    if uid == BRIDGE_ADMIN_ID and getattr(g, "is_bridge_super", False):
        return True
    if uid in Config.ADMIN_USER_IDS:
        return True
    from models import AdminRole
    db = SessionLocal()
    try:
        row = db.get(AdminRole, uid)
        return row is not None and row.role == "super"
    finally:
        db.close()
        SessionLocal.remove()


def is_admin(user_id) -> bool:
    """Super admins + DB-granted support staff (Phase 19)."""
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return False
    if uid in Config.ADMIN_USER_IDS:
        return True
    from models import AdminRole
    db = SessionLocal()
    try:
        return db.get(AdminRole, uid) is not None
    finally:
        db.close()
        SessionLocal.remove()


def audit(db, admin_id, action: str, target: str = "", detail: str = "") -> None:
    """Record a mutating admin action. Caller commits."""
    from models import AdminAuditLog
    db.add(AdminAuditLog(admin_id=admin_id, action=(action or "")[:40],
                         target=(target or "")[:80] or None,
                         detail=(detail or "")[:300] or None))


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        # 1) Native Discord-session admin (Discord id in ADMIN_USER_IDS / DB role).
        uid = current_user_id()
        if uid is not None and is_admin(uid):
            g.user_id = uid
            g.is_bridge_super = False
            g.admin_email = None
            return _run(fn, args, kwargs)

        # 2) Telegizer email super-admin bridge (no Discord login required).
        ident = bridge_super_admin()
        if ident is not None:
            g.user_id = BRIDGE_ADMIN_ID
            g.is_bridge_super = True
            g.admin_email = ident.get("email")
            return _run(fn, args, kwargs)

        # No usable credentials at all → 401; otherwise a real user who isn't an
        # admin → 403.
        if uid is None and not request.headers.get(_BRIDGE_TOKEN_HEADER):
            return jsonify(error="unauthorized"), 401
        return jsonify(error="forbidden"), 403

    return wrapper


def _run(fn, args, kwargs):
    g.db = SessionLocal()
    try:
        return fn(*args, **kwargs)
    finally:
        g.db.close()
        SessionLocal.remove()
