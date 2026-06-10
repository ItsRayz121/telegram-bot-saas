"""Platform-admin RBAC for Guildizer.

Admins are configured by Discord user id (ADMIN_USER_IDS env), not stored in the
DB — so access can't be granted by tampering with data. admin_required guards
the admin API and, like login_required, sets g.user_id and g.db.
"""
from __future__ import annotations

from functools import wraps

from flask import g, jsonify

from auth import current_user_id
from config import Config
from database import SessionLocal


def is_admin(user_id) -> bool:
    try:
        return int(user_id) in Config.ADMIN_USER_IDS
    except (TypeError, ValueError):
        return False


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        uid = current_user_id()
        if uid is None:
            return jsonify(error="unauthorized"), 401
        if not is_admin(uid):
            return jsonify(error="forbidden"), 403
        g.user_id = uid
        g.db = SessionLocal()
        try:
            return fn(*args, **kwargs)
        finally:
            g.db.close()
            SessionLocal.remove()

    return wrapper
