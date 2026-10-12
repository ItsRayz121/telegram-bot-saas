"""Knowledge sources for Guildizer: sync, versions, preview, scheduling.

Ported from Telegizer's KnowledgeBaseSystem.sync_external_source and
knowledge_source_api (logic copied, not imported). The HTTP layer (knowledge_api)
only does authentication, server scoping and the Pro gate; the rest lives here.

Safety properties:
  - the old version stays active until the new one is fetched, validated, chunked
    AND embedded; any failure leaves answers untouched;
  - unchanged content is detected by hash and is not re-embedded;
  - the swap (version row + the source's document chunks + source fields) is ONE
    commit, so retrieval never sees a half-written source;
  - network I/O happens with no open transaction;
  - previews and version listings read stored rows only (no provider call, no AI).
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timedelta

from sqlalchemy import func

import kb_index
import knowledge_sources as ks
import knowledge_sync as kg
from database import SessionLocal
from models import KnowledgeDocument, KnowledgeSource, KnowledgeSourceVersion

log = logging.getLogger("guildizer.kb.sources")

MAX_SOURCES = 10
KEEP_VERSIONS = 5
_STALE_AFTER = timedelta(days=30)
_PREVIEW_MAX_CHARS = 60_000
_MAX_MATCHES = 100
_BUSY_SECONDS = 55


def _iso(dt):
    return dt.isoformat() + "Z" if dt else None


def _out(ok, error=None, code=None, **kw):
    d = {"ok": ok, "error": error, "code": code, "unchanged": False,
         "next_available_at": None, "partial": False}
    d.update(kw)
    return d


# ── sync ──────────────────────────────────────────────────────────────────────

def _finish_failed(db, source_id, msg, ledger_id, usage, status, now, *, fatal=False,
                   rate_until=None, cooldown_key=None, refund=None):
    """Record a failed attempt: error on the row, ledger corrected (a failed or
    retried attempt stays counted), schedule policy applied. ``refund`` is used
    only when the provider was never contacted."""
    from models import KnowledgeSyncLedger
    try:
        row = db.get(KnowledgeSource, source_id)
        if row:
            row.last_sync_status = "error"
            row.last_sync_error = str(msg)[:500]
            row.last_synced_at = now
            if status != "ok":      # fetch ok but embed failed is not a source failure
                kg.record_failure(row, now, fatal=fatal)
            if rate_until and cooldown_key:
                kg.extend_cooldown(db, cooldown_key, rate_until)
                if row.sync_schedule != "manual" and not row.schedule_paused_reason:
                    row.next_sync_at = rate_until
            db.commit()
        if ledger_id:
            led = db.get(KnowledgeSyncLedger, ledger_id)
            if led:
                if refund:          # provider never contacted: nothing was spent
                    led.pages_reserved = 0
                kg.finish_ledger(db, led, status, usage)
        if refund:
            kg.release_cooldown(db, refund[0], refund[1])
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("failed to record sync failure for source %s", source_id)


def _persist_state_only(db, source_id, state):
    if not state:
        return
    try:
        row = db.get(KnowledgeSource, source_id)
        if row:
            row.sync_state = state
            db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        log.debug("persist sync state failed", exc_info=True)


def _mark_success(row, now, result, nchars, partial=False):
    row.last_sync_status = "partial" if partial else "success"
    row.last_sync_error = ("Import incomplete: the page budget ended early; the next sync resumes where it stopped."
                           if partial else None)
    row.last_sync_chars = nchars
    row.last_success_at = now
    row.last_synced_at = now
    if result.get("published_at"):
        row.published_at = result["published_at"]
    kg.record_success(row, now)


def _finish_ledger_ok(db, ledger_id, usage):
    if not ledger_id:
        return
    from models import KnowledgeSyncLedger
    row = db.get(KnowledgeSyncLedger, ledger_id)
    if row:
        kg.finish_ledger(db, row, "ok", usage)


def sync_source(db, source_id: int, trigger: str = "manual") -> dict:
    """Fetch, chunk, embed and ACTIVATE one KnowledgeSource version.

    Returns {ok, error, code, unchanged, next_available_at, partial}. ``code`` is
    one of None | disabled | plan | cooldown | budget | busy | no_key | error, so a
    route can pick the right HTTP status."""
    now = datetime.utcnow()
    is_x = False
    ledger_id = cooldown_key = prev_cooldown = None
    pages_allowed = 1

    row = db.get(KnowledgeSource, source_id)
    if row is None:
        return _out(False, "Source was deleted", "error")
    if not kg.sources_enabled():
        return _out(False, "External knowledge source syncing is temporarily disabled.", "disabled")
    if not row.enabled:
        return _out(False, "This source is disabled. Enable it to sync.", "disabled")
    if trigger == "scheduled" and not kg.scheduled_sync_enabled():
        return _out(False, "Scheduled syncing is temporarily disabled.", "disabled")
    if not kg.is_paid(db, row.guild_id):
        return _out(False, "External knowledge sources require an active Pro plan.", "plan")

    owner_id = kg.owner_user_id(db, row)
    source_type, url, guild_id = row.source_type, row.url, row.guild_id
    state = dict(row.sync_state or {})
    is_x = source_type == "twitter"

    if is_x:
        # Shared rolling cooldown + budget, all BEFORE the provider is touched.
        if not kg.x_sync_enabled():
            return _out(False, "X syncing is temporarily disabled.", "disabled")
        handle = ks.x_handle(url)
        if not handle:
            return _out(False, "Could not find a handle in that URL.", "error")
        from config import Config
        if not Config.TWITTERAPI_IO_KEY:
            return _out(False, "No twitterapi.io API key is configured on this platform yet.", "no_key")
        cooldown_key = kg.cooldown_key(owner_id, handle)
        prev_cooldown = kg.cooldown_until(db, cooldown_key)
        if not kg.claim_cooldown(db, cooldown_key, now, kg.limits()["cooldown"]):
            return _out(False, "This X account was already synced in the last 24 hours. The stored version is being used.",
                        "cooldown", next_available_at=kg.cooldown_until(db, cooldown_key))
        ledger, pages_allowed, scope = kg.reserve(db, row, owner_id, trigger, now)
        if ledger is None:
            kg.release_cooldown(db, cooldown_key, prev_cooldown)   # nothing was fetched
            return _out(False, f"The X sync budget ({scope}) is used up for now. The stored version is being used.",
                        "budget", next_available_at=kg.cooldown_until(db, cooldown_key))
        ledger_id = ledger.id
    else:
        # Atomic claim: only succeeds if the source was not synced in the last ~55s,
        # so a double-click / two tabs cannot both fetch and embed.
        cutoff = now - timedelta(seconds=_BUSY_SECONDS)
        claimed = (db.query(KnowledgeSource)
                   .filter(KnowledgeSource.id == source_id,
                           (KnowledgeSource.last_synced_at.is_(None)) | (KnowledgeSource.last_synced_at < cutoff))
                   .update({"last_synced_at": now}, synchronize_session=False))
        db.commit()
        if not claimed:
            return _out(False, "A sync for this source is already running or ran within the last minute.", "busy")

    row = db.get(KnowledgeSource, source_id)
    row.last_synced_at = now           # last ATTEMPT (success or not)
    db.commit()

    lim = kg.limits()
    result = ks.fetch_source(source_type, url, state=state, max_pages=pages_allowed,
                             initial_cap=lim["initial_posts"])

    if not result["ok"]:
        status = "rate_limited" if result.get("rate_limited_until") else "failed"
        _finish_failed(db, source_id, result["error"], ledger_id, result.get("usage"), status, now,
                       fatal=result.get("fatal", False), rate_until=result.get("rate_limited_until"),
                       cooldown_key=cooldown_key)
        return _out(False, result["error"], "error")

    text = result["text"]
    chunks = kb_index._chunk_text(text)
    if not chunks:
        _finish_failed(db, source_id, "No content to embed", ledger_id, result.get("usage"), "failed", now)
        return _out(False, "No content to embed", "error")

    chash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    partial = bool(result.get("incomplete"))

    row = db.get(KnowledgeSource, source_id)
    if row is None:
        return _out(False, "Source was deleted", "error")
    active = db.get(KnowledgeSourceVersion, row.active_version_id) if row.active_version_id else None
    if active and active.content_hash == chash and bool(active.is_partial) == partial:
        # Same content: do not re-embed. Still persist connector state and dates.
        row.sync_state = result.get("state") or row.sync_state
        _mark_success(row, now, result, len(text))
        _finish_ledger_ok(db, ledger_id, result.get("usage"))
        db.commit()
        return _out(True, None, None, unchanged=True, partial=partial)

    embeddings = kb_index._embed(chunks)
    if all(e is None for e in embeddings):
        err = ("Embeddings are unavailable right now (no OPENAI_API_KEY on the platform, or the "
               "provider rejected the request). The previous version is still in use.")
        # The fetch itself succeeded and cost quota; keep its state so the next run
        # does not repeat those pages.
        _persist_state_only(db, source_id, result.get("state"))
        _finish_failed(db, source_id, err, ledger_id, result.get("usage"), "ok", now)
        return _out(False, err, "error")

    chunk_data = [{"text": c, "embedding": e} for c, e in zip(chunks, embeddings) if e is not None]
    indexed_at = datetime.utcnow()

    row = db.get(KnowledgeSource, source_id)
    if row is None:
        return _out(False, "Source was deleted", "error")
    try:
        # Single commit: new active version + replaced chunks + source fields.
        prev = db.get(KnowledgeSourceVersion, row.active_version_id) if row.active_version_id else None
        next_no = (db.query(func.coalesce(func.max(KnowledgeSourceVersion.version_no), 0))
                   .filter(KnowledgeSourceVersion.source_id == row.id).scalar() or 0) + 1
        if prev:
            prev.status = "superseded"
        ver = KnowledgeSourceVersion(
            source_id=row.id, version_no=next_no, status="active", content_hash=chash,
            text=text, char_count=len(text), chunk_count=len(chunk_data), is_partial=partial,
            published_at=result.get("published_at"), fetched_at=now, indexed_at=indexed_at)
        db.add(ver)
        db.flush()

        existing = db.query(KnowledgeDocument).filter(KnowledgeDocument.source_id == row.id).first()
        if existing:
            existing.title = (row.label or row.url)[:200]
            existing.content_text = text[:kb_index._MAX_CONTENT_TEXT]
            existing.chunks = chunk_data
            existing.enabled = bool(row.enabled)
        else:
            db.add(KnowledgeDocument(
                guild_id=row.guild_id, title=(row.label or row.url)[:200], file_type=row.source_type,
                content="", content_text=text[:kb_index._MAX_CONTENT_TEXT], chunks=chunk_data,
                enabled=bool(row.enabled), source_id=row.id))
        row.active_version_id = ver.id
        row.sync_state = result.get("state") or row.sync_state
        _mark_success(row, now, result, len(text), partial=partial)
        _finish_ledger_ok(db, ledger_id, result.get("usage"))
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("could not activate new version for source %s", source_id)
        _finish_failed(db, source_id, "Could not save the new version. The previous version is still in use.",
                       ledger_id, result.get("usage"), "ok", now)
        return _out(False, "Could not save the new version. The previous version is still in use.", "error")

    # Keep history bounded: newest KEEP_VERSIONS versions retain their text.
    old = (db.query(KnowledgeSourceVersion).filter(KnowledgeSourceVersion.source_id == source_id)
           .order_by(KnowledgeSourceVersion.version_no.desc()).offset(KEEP_VERSIONS).all())
    for o in old:
        db.delete(o)
    if old:
        db.commit()
    return _out(True, None, None, partial=partial)


def activate_version(db, source_id: int, version_id: int):
    """Roll a source back to an older stored version: re-index that version's exact
    text, then swap it in. Returns (ok, error). Nothing changes unless indexing
    succeeds. Explicit owner action: costs embeddings, never a provider fetch."""
    row = db.get(KnowledgeSource, source_id)
    ver = (db.query(KnowledgeSourceVersion)
           .filter(KnowledgeSourceVersion.id == version_id, KnowledgeSourceVersion.source_id == source_id).first())
    if not row or not ver:
        return False, "Version not found"
    if row.active_version_id == ver.id:
        return True, None
    text = ver.text
    chunks = kb_index._chunk_text(text)
    if not chunks:
        return False, "That version has no content to index."
    embeddings = kb_index._embed(chunks)
    if all(e is None for e in embeddings):
        return False, "Embeddings are unavailable right now, so that version could not be re-indexed."
    chunk_data = [{"text": c, "embedding": e} for c, e in zip(chunks, embeddings) if e is not None]
    try:
        for other in (db.query(KnowledgeSourceVersion)
                      .filter(KnowledgeSourceVersion.source_id == source_id,
                              KnowledgeSourceVersion.status == "active").all()):
            other.status = "superseded"
        ver.status = "active"
        ver.chunk_count = len(chunk_data)
        ver.indexed_at = datetime.utcnow()
        doc = db.query(KnowledgeDocument).filter(KnowledgeDocument.source_id == source_id).first()
        if doc:
            doc.content_text = text[:kb_index._MAX_CONTENT_TEXT]
            doc.chunks = chunk_data
        else:
            db.add(KnowledgeDocument(
                guild_id=row.guild_id, title=(row.label or row.url)[:200], file_type=row.source_type,
                content="", content_text=text[:kb_index._MAX_CONTENT_TEXT], chunks=chunk_data,
                enabled=bool(row.enabled), source_id=row.id))
        row.active_version_id = ver.id
        row.last_sync_chars = len(text)
        row.published_at = ver.published_at
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("rollback to version %s failed", version_id)
        return False, "Could not restore that version."
    return True, None


# ── request-level helpers (used by knowledge_api) ─────────────────────────────

def _reconstruct_from_chunks(doc):
    """Sources synced before versions existed have chunks but no version row.
    Rebuild the indexed text by dropping the 50-word overlap between chunks."""
    parts = []
    for i, ch in enumerate(doc.chunks or []):
        words = (ch.get("text") or "").split()
        parts.append(" ".join(words if i == 0 else words[50:]))
    return " ".join(p for p in parts if p)


def source_status(source, has_text, now=None):
    now = now or datetime.utcnow()
    if not has_text:
        return "unavailable"
    if source.last_sync_status == "error":
        return "stale"          # showing the last good version after a failed sync
    if source.last_sync_status == "partial":
        return "partial"
    if source.last_success_at and now - source.last_success_at > _STALE_AFTER:
        return "stale"
    return "ok"


def preview_payload(db, source, query=""):
    """Everything the "View extracted text" drawer shows. Read-only."""
    ver = db.get(KnowledgeSourceVersion, source.active_version_id) if source.active_version_id else None
    doc = db.query(KnowledgeDocument).filter(KnowledgeDocument.source_id == source.id).first()
    reconstructed = False
    if ver:
        text, chunk_count, indexed_at = ver.text, ver.chunk_count, ver.indexed_at
        version_info = {"id": ver.id, "version_no": ver.version_no, "is_partial": bool(ver.is_partial)}
        published_at = ver.published_at
    elif doc and doc.chunks:
        text, chunk_count, indexed_at = _reconstruct_from_chunks(doc), len(doc.chunks), None
        reconstructed, version_info, published_at = True, None, source.published_at
    else:
        text, chunk_count, indexed_at, version_info, published_at = None, 0, None, None, source.published_at

    has_text = bool(text)
    shown = (text or "")[:_PREVIEW_MAX_CHARS]
    q = (query or "").strip()[:100]
    matches = []
    if q and has_text:
        for m in re.finditer(re.escape(q), shown, re.I):
            start = max(0, m.start() - 60)
            matches.append({"offset": m.start(), "snippet": shown[start:m.end() + 60]})
            if len(matches) >= _MAX_MATCHES:
                break
    cool = None
    if source.source_type == "twitter":
        owner = kg.owner_user_id(db, source)
        h = ks.x_handle(source.url)
        if owner and h:
            cool = kg.cooldown_until(db, kg.cooldown_key(owner, h))
    version_count = (db.query(func.count(KnowledgeSourceVersion.id))
                     .filter(KnowledgeSourceVersion.source_id == source.id).scalar() or 0)
    return {
        "source": {"id": source.id, "label": source.label, "url": source.url,
                   "source_type": source.source_type, "enabled": bool(source.enabled),
                   "sync_schedule": source.sync_schedule or "manual"},
        "status": source_status(source, has_text),
        "available": has_text,
        "text": shown if has_text else None,
        "truncated": has_text and len(text) > _PREVIEW_MAX_CHARS,
        "reconstructed_from_chunks": reconstructed,
        "char_count": len(text) if has_text else 0,
        "chunk_count": chunk_count,
        "active_version": version_info,
        "version_count": version_count,
        "dates": {
            "last_attempt": _iso(source.last_synced_at),
            "last_success": _iso(source.last_success_at),
            "published": _iso(published_at),           # None = the provider did not say
            "indexed": _iso(indexed_at),
            "next_sync": _iso(source.next_sync_at),
            "next_available": _iso(cool) if cool and cool > datetime.utcnow() else None,
        },
        "last_error": source.last_sync_error,
        "schedule_paused_reason": source.schedule_paused_reason,
        "matches": matches,
        "match_count": len(matches),
    }


def update_source(db, source, data, paid):
    """PATCH: schedule, enabled, label. Returns (payload, http_status)."""
    now = datetime.utcnow()
    if "label" in data:
        source.label = (str(data["label"] or "").strip()[:120]) or None
    if "enabled" in data:
        source.enabled = bool(data["enabled"])
        doc = db.query(KnowledgeDocument).filter(KnowledgeDocument.source_id == source.id).first()
        if doc:
            doc.enabled = bool(source.enabled)     # a disabled source is not searchable
    if "sync_schedule" in data:
        sched = str(data["sync_schedule"] or "manual")
        if sched not in kg.SCHEDULES:
            return {"error": "Choose Manual, Daily, Every 3 days or Weekly."}, 400
        if sched != "manual" and not paid:
            return {"error": "Scheduled syncing requires an active Pro plan."}, 402
        changed = sched != (source.sync_schedule or "manual")
        source.sync_schedule = sched
        if sched == "manual":
            source.next_sync_at = None
            source.schedule_paused_reason = None
        elif changed or source.next_sync_at is None:
            # Opting in never fetches immediately: the first scheduled run is one
            # full interval away (and never inside an X cooldown window).
            nxt = kg.next_scheduled(sched, now)
            if source.source_type == "twitter":
                owner = kg.owner_user_id(db, source)
                h = ks.x_handle(source.url)
                cool = kg.cooldown_until(db, kg.cooldown_key(owner, h)) if owner and h else None
                if cool and cool > nxt:
                    nxt = cool
            source.next_sync_at = nxt
            source.schedule_paused_reason = None
            source.consecutive_failures = 0
    if "enabled" in data and source.enabled and source.sync_schedule != "manual" and source.next_sync_at is None \
            and not source.schedule_paused_reason:
        source.next_sync_at = kg.next_scheduled(source.sync_schedule, now)
    db.commit()
    return {"source": source.to_dict()}, 200


def list_versions(db, source):
    rows = (db.query(KnowledgeSourceVersion).filter(KnowledgeSourceVersion.source_id == source.id)
            .order_by(KnowledgeSourceVersion.version_no.desc()).all())
    return {"versions": [v.to_dict() for v in rows]}


def delete_source(db, source):
    """Remove a source and everything derived from it, together."""
    db.query(KnowledgeDocument).filter(KnowledgeDocument.source_id == source.id).delete(synchronize_session=False)
    db.query(KnowledgeSourceVersion).filter(KnowledgeSourceVersion.source_id == source.id).delete(synchronize_session=False)
    db.delete(source)
    db.commit()


def sync_response(db, result, source):
    """Map a sync_source result onto (payload, status)."""
    db.refresh(source)
    code = result.get("code")
    body = {"source": source.to_dict()}
    if result["ok"]:
        body["unchanged"] = bool(result.get("unchanged"))
        body["partial"] = bool(result.get("partial"))
        return body, 200
    body["error"] = result.get("error")
    nxt = result.get("next_available_at")
    if nxt:
        body["next_available_at"] = _iso(nxt)
        body["serving_stored_version"] = True
    status = {"cooldown": 429, "budget": 429, "busy": 429, "disabled": 503, "plan": 402}.get(code, 400)
    return body, status


# ── scheduler tick (called from the bot worker) ───────────────────────────────

def run_scheduled_sync(max_sources: int = 3) -> int:
    """Sync up to ``max_sources`` due, opt-in sources. Returns how many ran.

    Does nothing unless KNOWLEDGE_SOURCES_ENABLED and KNOWLEDGE_SCHEDULED_SYNC_ENABLED
    are on. Pro is re-checked per source inside sync_source, so a lapsed plan stops."""
    if not kg.sources_enabled() or not kg.scheduled_sync_enabled():
        return 0
    db = SessionLocal()
    ran = 0
    try:
        for src in kg.due_sources(db, datetime.utcnow(), limit=max_sources):
            try:
                res = sync_source(db, src.id, trigger="scheduled")
                ran += 1
                if not res["ok"] and res.get("code") in ("plan", "disabled"):
                    # Not an error to retry every tick: push the next run out a day.
                    row = db.get(KnowledgeSource, src.id)
                    if row and row.sync_schedule != "manual":
                        row.next_sync_at = datetime.utcnow() + timedelta(days=1)
                        db.commit()
            except Exception:  # noqa: BLE001
                db.rollback()
                log.exception("scheduled sync crashed for source %s", src.id)
        return ran
    finally:
        db.close()
        SessionLocal.remove()
