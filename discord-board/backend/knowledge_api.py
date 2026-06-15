"""Knowledge base + digest config endpoints (Phase 16).

  GET/POST    /api/guilds/<id>/knowledge
  PUT/DELETE  /api/guilds/<id>/knowledge/<did>
  GET/PUT     /api/guilds/<id>/digest
"""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

import digest_runtime
import access
import kb_index
import plan_limits
from auth import login_required
from models import Guild, GuildSettings, KnowledgeDocument, UserGuild

knowledge_bp = Blueprint("knowledge", __name__)

MAX_DOCS = 50


def _manage_or_403(guild_id: int):
    return access.manage_or_403(g.db, g.user_id, guild_id)


@knowledge_bp.get("/api/guilds/<int:guild_id>/knowledge")
@login_required
def list_docs(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    rows = (
        g.db.query(KnowledgeDocument)
        .filter(KnowledgeDocument.guild_id == guild_id)
        .order_by(KnowledgeDocument.updated_at.desc())
        .all()
    )
    return jsonify(documents=[r.to_dict() for r in rows])


@knowledge_bp.post("/api/guilds/<int:guild_id>/knowledge")
@login_required
def create_doc(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    cap = plan_limits.limit(g.db, guild_id, "knowledge_docs")
    if g.db.query(KnowledgeDocument).filter(KnowledgeDocument.guild_id == guild_id).count() >= cap:
        return plan_limits.limit_response("knowledge_docs", cap)
    body = request.get_json(silent=True) or {}
    title = str(body.get("title") or "").strip()[:200]
    content = str(body.get("content") or "").strip()[:8000]
    if not title or not content:
        return jsonify(error="title_and_content_required"), 400
    row = KnowledgeDocument(guild_id=guild_id, title=title, content=content)
    g.db.add(row)
    g.db.commit()
    return jsonify(document=row.to_dict()), 201


@knowledge_bp.post("/api/guilds/<int:guild_id>/knowledge/upload")
@login_required
def upload_doc(guild_id: int):
    """Ingest an uploaded PDF / DOCX / TXT / MD file: extract text, chunk, embed,
    and index it for semantic /ask retrieval."""
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    cap = plan_limits.limit(g.db, guild_id, "knowledge_docs")
    if g.db.query(KnowledgeDocument).filter(KnowledgeDocument.guild_id == guild_id).count() >= cap:
        return plan_limits.limit_response("knowledge_docs", cap)

    f = request.files.get("file")
    if f is None:
        return jsonify(error="no_file"), 400
    filename = (f.filename or "document").strip()
    content_bytes = f.read()
    if not content_bytes:
        return jsonify(error="empty_file"), 400
    if len(content_bytes) > kb_index.MAX_FILE_BYTES:
        return jsonify(error="file_too_large", detail="Max 5MB per file."), 400

    file_type, type_err = kb_index.detect_type(filename, content_bytes)
    if type_err:
        return jsonify(error="bad_file", detail=type_err), 400

    try:
        doc, proc_err = kb_index.process_upload(g.db, guild_id, filename, file_type, content_bytes)
    except Exception:  # noqa: BLE001
        g.db.rollback()
        return jsonify(error="processing_failed"), 500
    if proc_err:
        return jsonify(error="processing_failed", detail=proc_err), 400
    return jsonify(document=doc), 201


@knowledge_bp.put("/api/guilds/<int:guild_id>/knowledge/<int:did>")
@login_required
def update_doc(guild_id: int, did: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = g.db.get(KnowledgeDocument, did)
    if row is None or row.guild_id != guild_id:
        return jsonify(error="not_found"), 404
    body = request.get_json(silent=True) or {}
    if "title" in body and str(body["title"]).strip():
        row.title = str(body["title"]).strip()[:200]
    if "content" in body and str(body["content"]).strip():
        row.content = str(body["content"]).strip()[:8000]
    if "enabled" in body:
        row.enabled = bool(body["enabled"])
    g.db.commit()
    return jsonify(document=row.to_dict())


@knowledge_bp.delete("/api/guilds/<int:guild_id>/knowledge/<int:did>")
@login_required
def delete_doc(guild_id: int, did: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = g.db.get(KnowledgeDocument, did)
    if row is None or row.guild_id != guild_id:
        return jsonify(error="not_found"), 404
    g.db.delete(row)
    g.db.commit()
    return jsonify(ok=True)


# --- digest config -------------------------------------------------------------------
@knowledge_bp.get("/api/guilds/<int:guild_id>/digest")
@login_required
def get_digest(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    return jsonify(digest_runtime.get_config(guild_id))


@knowledge_bp.put("/api/guilds/<int:guild_id>/digest")
@login_required
def update_digest(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = g.db.get(GuildSettings, guild_id)
    if row is None:
        return jsonify(error="not_found"), 404
    body = request.get_json(silent=True) or {}
    extra = dict(row.extra or {})
    digest = {**digest_runtime.DIGEST_DEFAULTS, **(extra.get("digest") or {})}
    if "enabled" in body:
        digest["enabled"] = bool(body["enabled"])
    if "channel_id" in body:
        ch = body["channel_id"]
        digest["channel_id"] = str(ch) if ch and str(ch).isdigit() else None
    if "hour_utc" in body:
        try:
            digest["hour_utc"] = max(0, min(23, int(body["hour_utc"])))
        except (TypeError, ValueError):
            pass
    if body.get("cadence") in ("daily", "weekly", "monthly"):
        digest["cadence"] = body["cadence"]
    if "weekday" in body:
        try:
            digest["weekday"] = max(0, min(6, int(body["weekday"])))
        except (TypeError, ValueError):
            pass
    extra["digest"] = digest
    row.extra = extra
    g.db.commit()
    return jsonify(digest)
