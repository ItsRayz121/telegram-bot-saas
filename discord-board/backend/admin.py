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


def is_super(user_id) -> bool:
    """Env-configured super admins (bootstrap) or DB-granted super role."""
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return False
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
