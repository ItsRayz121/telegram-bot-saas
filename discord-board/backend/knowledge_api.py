"""Knowledge base + digest config endpoints (Phase 16).

  GET/POST    /api/guilds/<id>/knowledge
  PUT/DELETE  /api/guilds/<id>/knowledge/<did>
  GET/PUT     /api/guilds/<id>/digest
"""
from __future__ import annotations

import os
import re
import time
from datetime import datetime

from flask import Blueprint, g, jsonify, request

import ai
import digest_runtime
import access
import knowledge
import kb_index
import kb_sources
import knowledge_sources
import knowledge_sync
import plan_limits
from auth import login_required
from models import Guild, GuildSettings, KnowledgeDocument, KnowledgeSource, UserGuild

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
    # Source-backed documents are managed through /knowledge/sources, not edited here.
    rows = (
        g.db.query(KnowledgeDocument)
        .filter(KnowledgeDocument.guild_id == guild_id, KnowledgeDocument.source_id.is_(None))
        .order_by(KnowledgeDocument.updated_at.desc())
        .all()
    )
    return jsonify(documents=[r.to_dict() for r in rows])


def _doc_count(guild_id: int) -> int:
    """Manual entries + uploads (source-backed documents have their own cap)."""
    return (g.db.query(KnowledgeDocument)
            .filter(KnowledgeDocument.guild_id == guild_id, KnowledgeDocument.source_id.is_(None))
            .count())


@knowledge_bp.post("/api/guilds/<int:guild_id>/knowledge")
@login_required
def create_doc(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    cap = plan_limits.limit(g.db, guild_id, "knowledge_docs")
    if _doc_count(guild_id) >= cap:
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
    if _doc_count(guild_id) >= cap:
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
    if row.source_id:
        return jsonify(error="managed_by_source", detail="Change this through its knowledge source."), 400
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
    if row.source_id:
        return jsonify(error="managed_by_source", detail="Remove the knowledge source instead."), 400
    g.db.delete(row)
    g.db.commit()
    return jsonify(ok=True)


# --- external knowledge sources (website / X / YouTube) -------------------------------
def _source_or_404(guild_id: int, sid: int):
    row = g.db.get(KnowledgeSource, sid)
    if row is None or row.guild_id != guild_id:
        return None
    return row


def _pro_or_402(guild_id: int):
    """Sources are a Pro feature, enforced here and again when a sync runs."""
    if not knowledge_sync.is_paid(g.db, guild_id):
        return jsonify(error="pro_required", message="External knowledge sources require Pro."), 402
    return None


@knowledge_bp.get("/api/guilds/<int:guild_id>/knowledge/sources")
@login_required
def list_sources(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    rows = (g.db.query(KnowledgeSource).filter(KnowledgeSource.guild_id == guild_id)
            .order_by(KnowledgeSource.created_at.desc()).all())
    return jsonify(sources=[r.to_dict() for r in rows], max_sources=kb_sources.MAX_SOURCES,
                   pro=knowledge_sync.is_paid(g.db, guild_id),
                   enabled=knowledge_sync.sources_enabled())


@knowledge_bp.post("/api/guilds/<int:guild_id>/knowledge/sources")
@login_required
def create_source(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    gate = _pro_or_402(guild_id)
    if gate:
        return gate
    if not knowledge_sync.sources_enabled():
        return jsonify(error="disabled", message="External knowledge source syncing is temporarily disabled."), 503
    body = request.get_json(silent=True) or {}
    url = str(body.get("url") or "").strip()[:500]
    if not url:
        return jsonify(error="url_required"), 400
    stype = str(body.get("source_type") or "").strip().lower() or knowledge_sources.detect_source_type(url)
    if stype not in knowledge_sources.SOURCE_TYPES:
        return jsonify(error="bad_source_type", message="Use a website, X or YouTube link."), 400
    if stype == "website" and not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    if stype == "twitter" and not knowledge_sources.x_handle(url):
        return jsonify(error="bad_url", message="Could not find an X handle in that link."), 400
    count = g.db.query(KnowledgeSource).filter(KnowledgeSource.guild_id == guild_id).count()
    if count >= kb_sources.MAX_SOURCES:
        return jsonify(error="source_limit", message=f"You can add up to {kb_sources.MAX_SOURCES} sources."), 400
    if g.db.query(KnowledgeSource).filter(KnowledgeSource.guild_id == guild_id,
                                          KnowledgeSource.url == url).first():
        return jsonify(error="duplicate", message="That source is already added."), 409
    row = KnowledgeSource(guild_id=guild_id, source_type=stype, url=url,
                          label=(str(body.get("label") or "").strip()[:120] or None))
    g.db.add(row)
    g.db.commit()
    return jsonify(source=row.to_dict()), 201


@knowledge_bp.patch("/api/guilds/<int:guild_id>/knowledge/sources/<int:sid>")
@login_required
def patch_source(guild_id: int, sid: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = _source_or_404(guild_id, sid)
    if row is None:
        return jsonify(error="not_found"), 404
    body = request.get_json(silent=True) or {}
    payload, status = kb_sources.update_source(g.db, row, body, knowledge_sync.is_paid(g.db, guild_id))
    return jsonify(payload), status


@knowledge_bp.delete("/api/guilds/<int:guild_id>/knowledge/sources/<int:sid>")
@login_required
def remove_source(guild_id: int, sid: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = _source_or_404(guild_id, sid)
    if row is None:
        return jsonify(error="not_found"), 404
    kb_sources.delete_source(g.db, row)
    return jsonify(ok=True)


@knowledge_bp.post("/api/guilds/<int:guild_id>/knowledge/sources/<int:sid>/sync")
@login_required
def sync_source_now(guild_id: int, sid: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = _source_or_404(guild_id, sid)
    if row is None:
        return jsonify(error="not_found"), 404
    result = kb_sources.sync_source(g.db, row.id, trigger="manual")
    payload, status = kb_sources.sync_response(g.db, result, row)
    return jsonify(payload), status


@knowledge_bp.get("/api/guilds/<int:guild_id>/knowledge/sources/<int:sid>/preview")
@login_required
def preview_source(guild_id: int, sid: int):
    """Stored extracted text + status + dates. Reads rows only: no provider fetch,
    no AI call."""
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = _source_or_404(guild_id, sid)
    if row is None:
        return jsonify(error="not_found"), 404
    return jsonify(kb_sources.preview_payload(g.db, row, request.args.get("q", "")))


@knowledge_bp.get("/api/guilds/<int:guild_id>/knowledge/sources/<int:sid>/versions")
@login_required
def source_versions(guild_id: int, sid: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = _source_or_404(guild_id, sid)
    if row is None:
        return jsonify(error="not_found"), 404
    return jsonify(kb_sources.list_versions(g.db, row))


@knowledge_bp.post("/api/guilds/<int:guild_id>/knowledge/sources/<int:sid>/versions/<int:vid>/activate")
@login_required
def activate_source_version(guild_id: int, sid: int, vid: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = _source_or_404(guild_id, sid)
    if row is None:
        return jsonify(error="not_found"), 404
    gate = _pro_or_402(guild_id)
    if gate:
        return gate
    done, msg = kb_sources.activate_version(g.db, row.id, vid)
    if not done:
        return jsonify(error=msg), 400
    g.db.refresh(row)
    return jsonify(source=row.to_dict())


# --- "try a question": one real AI answer from the knowledge base, stored nowhere -----
_SAMPLE_COOLDOWN_SECONDS = 10
_SAMPLE_DAILY_LIMIT = 20
_sample_last: dict = {}      # (guild, user) -> monotonic ts
_sample_day: dict = {}       # guild -> (YYYY-MM-DD, count)


@knowledge_bp.post("/api/guilds/<int:guild_id>/knowledge/ask-sample")
@login_required
def ask_sample(guild_id: int):
    """Answer one question exactly the way the bot would (same knowledge, same
    prompt rules), so an admin can test the knowledge base. Makes ONE paid AI call.
    Writes nothing (no usage ledger row, no memory, no XP, no analytics) and posts
    nothing to Discord. Kill switch: AI_SAMPLES_ENABLED=0."""
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    if os.environ.get("AI_SAMPLES_ENABLED", "1") == "0":
        return jsonify(error="disabled", message="AI samples are temporarily switched off."), 503
    if not ai.is_configured():
        return jsonify(error="ai_unavailable", message="The AI assistant is not configured on this platform."), 503
    question = str((request.get_json(silent=True) or {}).get("question") or "").strip()[:300]
    if len(question) < 3:
        return jsonify(error="question_required"), 400

    now = time.monotonic()
    key = (guild_id, g.user_id)
    if now - _sample_last.get(key, 0.0) < _SAMPLE_COOLDOWN_SECONDS:
        return jsonify(error="slow_down", message="Wait a few seconds between samples."), 429
    today = datetime.utcnow().strftime("%Y-%m-%d")
    day, count = _sample_day.get(guild_id, (today, 0))
    if day != today:
        day, count = today, 0
    if count >= _SAMPLE_DAILY_LIMIT:
        return jsonify(error="daily_limit", message="Daily sample limit reached for this server."), 429
    _sample_last[key] = now
    _sample_day[guild_id] = (day, count + 1)

    system, confident = knowledge.grounded_with_confidence(guild_id, question)
    if system is None:
        return jsonify(status="no_knowledge", answer=None, confident=False,
                       note="Add documents or a source first. Sample only: nothing was posted or stored.")
    result = ai.complete(system, question)
    if result is None:
        return jsonify(error="ai_failed", message="The AI provider did not answer. Try again."), 502
    if knowledge.is_conflict(result.text):
        status, answer = "conflict", None
    elif knowledge.is_no_answer(result.text):
        status, answer = "no_answer", None
    else:
        status, answer = "answered", result.text.strip()[:1900]
    return jsonify(status=status, answer=answer, confident=bool(confident),
                   note="Sample only: nothing was posted, stored or counted.")


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
