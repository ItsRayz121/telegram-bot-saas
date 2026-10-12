"""Request-level logic for knowledge sources, shared by BOTH route lineages
(routes/knowledge.py for custom bots, routes/telegram_groups.py for official-bot
groups). The route files only do authentication, group scoping and the plan gate;
everything else lives here so the two cannot drift apart.

Nothing in this module contacts a provider or an AI model: previews and version
listings read stored rows only.
"""
import re
from datetime import datetime, timedelta

from . import knowledge_sync as kg
from .models import db, KnowledgeDocument, KnowledgeSource, KnowledgeSourceVersion

_STALE_AFTER = timedelta(days=30)
_PREVIEW_MAX_CHARS = 60_000
_MAX_MATCHES = 100


def _iso(dt):
    return dt.isoformat() + "Z" if dt else None


def _reconstruct_from_chunks(doc):
    """Legacy sources (synced before versions existed) have chunks but no version
    row. Rebuild the indexed text by dropping the 50-word overlap between chunks."""
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


def preview_payload(source, query=""):
    """Everything the 'View extracted text' drawer shows. Read-only."""
    ver = KnowledgeSourceVersion.query.get(source.active_version_id) if source.active_version_id else None
    doc = KnowledgeDocument.query.filter_by(source_id=source.id).first()
    reconstructed = False
    if ver:
        text, chunk_count, indexed_at = ver.text, ver.chunk_count, ver.indexed_at
        version_info = {"id": ver.id, "version_no": ver.version_no, "is_partial": bool(ver.is_partial)}
        published_at = ver.published_at
    elif doc and doc.chunks:
        text, chunk_count, indexed_at = _reconstruct_from_chunks(doc), len(doc.chunks), None
        reconstructed = True
        version_info = None
        published_at = source.published_at
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
        owner = kg.owner_user_id(source)
        from .bot_features.knowledge_sources import x_handle
        h = x_handle(source.url)
        if owner and h:
            cool = kg.cooldown_until(db, kg.cooldown_key(source, owner, h))
    versions = (KnowledgeSourceVersion.query.filter_by(source_id=source.id)
                .order_by(KnowledgeSourceVersion.version_no.desc()).count())
    return {
        "source": {
            "id": source.id, "label": source.label, "url": source.url, "source_type": source.source_type,
            "enabled": bool(source.enabled), "sync_schedule": source.sync_schedule or "manual",
        },
        "status": source_status(source, has_text),
        "available": has_text,
        "text": shown if has_text else None,
        "truncated": has_text and len(text) > _PREVIEW_MAX_CHARS,
        "reconstructed_from_chunks": reconstructed,
        "char_count": len(text) if has_text else 0,
        "chunk_count": chunk_count,
        "active_version": version_info,
        "version_count": versions,
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


def update_source(source, data, owner_is_paid):
    """PATCH: schedule, enabled, label. Returns (payload, http_status)."""
    now = datetime.utcnow()
    if "label" in data:
        source.label = (str(data["label"] or "").strip()[:120]) or None
    if "enabled" in data:
        source.enabled = bool(data["enabled"])
    if "sync_schedule" in data:
        sched = str(data["sync_schedule"] or "manual")
        if sched not in kg.SCHEDULES:
            return {"error": "Choose Manual, Daily, Every 3 days or Weekly."}, 400
        if sched != "manual" and not owner_is_paid:
            return {"error": "Scheduled syncing requires an active Pro or Enterprise plan."}, 403
        changed = sched != (source.sync_schedule or "manual")
        source.sync_schedule = sched
        if sched == "manual":
            source.next_sync_at = None
            source.schedule_paused_reason = None
        elif changed or source.next_sync_at is None:
            # Opting in never fetches immediately: the first scheduled run is one
            # full interval away (and never inside an X cooldown window).
            nxt = kg.next_scheduled(sched, now)
            owner = kg.owner_user_id(source)
            if source.source_type == "twitter" and owner:
                from .bot_features.knowledge_sources import x_handle
                cool = kg.cooldown_until(db, kg.cooldown_key(source, owner, x_handle(source.url)))
                if cool and cool > nxt:
                    nxt = cool
            source.next_sync_at = nxt
            source.schedule_paused_reason = None
            source.consecutive_failures = 0
    db.session.commit()
    return {"source": source.to_dict()}, 200


def list_versions(source):
    rows = (KnowledgeSourceVersion.query.filter_by(source_id=source.id)
            .order_by(KnowledgeSourceVersion.version_no.desc()).all())
    return {"versions": [v.to_dict() for v in rows]}


def delete_source(source):
    """Remove a source and everything derived from it, together."""
    KnowledgeDocument.query.filter_by(source_id=source.id).delete()
    KnowledgeSourceVersion.query.filter_by(source_id=source.id).delete()
    db.session.delete(source)
    db.session.commit()


def sync_response(result, source):
    """Map a sync_external_source result onto (payload, status)."""
    db.session.refresh(source)
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
    status = {"cooldown": 429, "budget": 429, "busy": 429, "disabled": 503, "plan": 403}.get(code, 400)
    return body, status
