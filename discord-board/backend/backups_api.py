"""Server backup/restore dashboard endpoints.

  GET    /api/guilds/<id>/backups               list (newest first)
  POST   /api/guilds/<id>/backups               queue a snapshot {label}
  POST   /api/guilds/<id>/backups/<bid>/restore queue a restore
  DELETE /api/guilds/<id>/backups/<bid>

The bot does the Discord-side work from its 20s loop (backups.py); the API only
queues rows. At most 5 stored snapshots per guild — the oldest finished one is
dropped to make room.
"""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

import access
from auth import login_required
from models import GuildBackup

backups_bp = Blueprint("backups", __name__)

MAX_BACKUPS = 5


def _manage_or_403(guild_id: int):
    return access.manage_or_403(g.db, g.user_id, guild_id)


@backups_bp.get("/api/guilds/<int:guild_id>/backups")
@login_required
def list_backups(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    rows = (
        g.db.query(GuildBackup)
        .filter(GuildBackup.guild_id == guild_id)
        .order_by(GuildBackup.created_at.desc())
        .limit(MAX_BACKUPS * 2)
        .all()
    )
    return jsonify(backups=[r.to_dict() for r in rows])


@backups_bp.post("/api/guilds/<int:guild_id>/backups")
@login_required
def create_backup(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    body = request.get_json(silent=True) or {}

    rows = (
        g.db.query(GuildBackup)
        .filter(GuildBackup.guild_id == guild_id)
        .order_by(GuildBackup.created_at.asc())
        .all()
    )
    if any(r.needs_snapshot or r.needs_restore for r in rows):
        return jsonify(error="backup_or_restore_in_progress"), 409
    while len(rows) >= MAX_BACKUPS:
        g.db.delete(rows.pop(0))   # oldest first

    row = GuildBackup(
        guild_id=guild_id,
        label=str(body.get("label") or "").strip()[:100],
        created_by=g.user_id,
    )
    g.db.add(row)
    g.db.commit()
    return jsonify(backup=row.to_dict()), 201


@backups_bp.post("/api/guilds/<int:guild_id>/backups/<int:bid>/restore")
@login_required
def restore_backup(guild_id: int, bid: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = g.db.get(GuildBackup, bid)
    if row is None or row.guild_id != guild_id:
        return jsonify(error="not_found"), 404
    if row.data is None or row.status in ("pending", "failed"):
        return jsonify(error="backup_has_no_data"), 400
    busy = (
        g.db.query(GuildBackup)
        .filter(GuildBackup.guild_id == guild_id,
                (GuildBackup.needs_snapshot.is_(True))
                | (GuildBackup.needs_restore.is_(True)))
        .count()
    )
    if busy:
        return jsonify(error="backup_or_restore_in_progress"), 409
    row.needs_restore = True
    g.db.commit()
    return jsonify(backup=row.to_dict())


@backups_bp.delete("/api/guilds/<int:guild_id>/backups/<int:bid>")
@login_required
def delete_backup(guild_id: int, bid: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = g.db.get(GuildBackup, bid)
    if row is None or row.guild_id != guild_id:
        return jsonify(error="not_found"), 404
    g.db.delete(row)
    g.db.commit()
    return jsonify(ok=True)
