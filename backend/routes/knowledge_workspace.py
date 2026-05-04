"""
Workspace Knowledge Base API — user-scoped document storage and search.

GET    /api/workspace/knowledge            list documents
POST   /api/workspace/knowledge            upload document (multipart/form-data or JSON text)
DELETE /api/workspace/knowledge/<id>       delete document
POST   /api/workspace/knowledge/<id>/search  AI-powered search within a document
GET    /api/workspace/knowledge/search     keyword search across all documents
"""
import io
import logging
from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..models import db, User, WorkspaceKnowledgeDocument
from ..middleware.rate_limit import rate_limit

_log = logging.getLogger(__name__)

knowledge_ws_bp = Blueprint("knowledge_workspace", __name__, url_prefix="/api/workspace/knowledge")

ALLOWED_TYPES = {"pdf", "txt", "md", "docx"}
MAX_SIZE = 5 * 1024 * 1024  # 5 MB


def _me() -> User:
    return User.query.get(int(get_jwt_identity()))


def _extract_text(data: bytes, ext: str) -> str:
    """Best-effort text extraction — falls back to raw decode."""
    if ext in ("txt", "md"):
        return data.decode("utf-8", errors="replace")
    if ext == "pdf":
        try:
            import pdfplumber, io as _io
            with pdfplumber.open(_io.BytesIO(data)) as pdf:
                return "\n".join(p.extract_text() or "" for p in pdf.pages)[:200000]
        except Exception:
            return data.decode("utf-8", errors="replace")[:200000]
    if ext == "docx":
        try:
            from docx import Document as _Doc
            import io as _io
            doc = _Doc(_io.BytesIO(data))
            return "\n".join(p.text for p in doc.paragraphs)[:200000]
        except Exception:
            return data.decode("utf-8", errors="replace")[:200000]
    return data.decode("utf-8", errors="replace")[:200000]


def _chunk_text(text: str, size: int = 800) -> list[str]:
    words = text.split()
    chunks, buf = [], []
    for w in words:
        buf.append(w)
        if len(" ".join(buf)) >= size:
            chunks.append(" ".join(buf))
            buf = []
    if buf:
        chunks.append(" ".join(buf))
    return chunks


@knowledge_ws_bp.route("", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def list_docs():
    user = _me()
    try:
        docs = (
            WorkspaceKnowledgeDocument.query
            .filter_by(user_id=user.id)
            .order_by(WorkspaceKnowledgeDocument.created_at.desc())
            .all()
        )
        return jsonify({"documents": [d.to_dict() for d in docs]})
    except Exception as _e:
        # Graceful degradation while migration is pending (e.g. missing embedding column)
        from ..models import db
        db.session.rollback()
        import logging
        logging.getLogger(__name__).warning("list_docs fallback (schema migration pending): %s", _e)
        from sqlalchemy import text
        rows = db.session.execute(
            text("SELECT id, user_id, filename, file_type, content_text, tags, description, created_at FROM workspace_knowledge_documents WHERE user_id=:uid ORDER BY created_at DESC"),
            {"uid": user.id}
        ).fetchall()
        docs_list = [
            {"id": r[0], "filename": r[2], "file_type": r[3],
             "content_preview": (r[4] or "")[:120], "tags": r[5] or [],
             "description": r[6], "created_at": str(r[7])}
            for r in rows
        ]
        return jsonify({"documents": docs_list})


@knowledge_ws_bp.route("", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def upload_doc():
    user = _me()

    # Accept either file upload OR plain JSON text
    if request.content_type and "multipart" in request.content_type:
        f = request.files.get("file")
        if not f:
            return jsonify({"error": "No file provided"}), 400
        data = f.read(MAX_SIZE + 1)
        if len(data) > MAX_SIZE:
            return jsonify({"error": "File exceeds 5 MB limit"}), 413
        filename = f.filename or "document.txt"
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "txt"
        if ext not in ALLOWED_TYPES:
            return jsonify({"error": f"Unsupported type: {ext}"}), 415
        content_text = _extract_text(data, ext)
        description = request.form.get("description", "")
        tags = [t.strip() for t in (request.form.get("tags") or "").split(",") if t.strip()]
    else:
        body = request.get_json(silent=True) or {}
        content_text = (body.get("content") or "").strip()
        if not content_text:
            return jsonify({"error": "content required"}), 400
        filename = (body.get("filename") or "note.txt").strip()
        ext = "txt"
        description = (body.get("description") or "").strip()
        tags = body.get("tags") or []

    chunks = _chunk_text(content_text)
    doc = WorkspaceKnowledgeDocument(
        user_id=user.id,
        filename=filename[:255],
        file_type=ext,
        content_text=content_text,
        chunks=chunks,
        tags=tags or [],
        description=description[:500] or None,
    )
    db.session.add(doc)
    db.session.commit()
    return jsonify({"document": doc.to_dict()}), 201


@knowledge_ws_bp.route("/<int:doc_id>", methods=["DELETE"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def delete_doc(doc_id):
    user = _me()
    doc = WorkspaceKnowledgeDocument.query.filter_by(id=doc_id, user_id=user.id).first_or_404()
    db.session.delete(doc)
    db.session.commit()
    return jsonify({"success": True})


@knowledge_ws_bp.route("/search", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def search_docs():
    """Keyword search across all workspace documents."""
    user = _me()
    q = (request.args.get("q") or "").strip().lower()
    if not q or len(q) < 2:
        return jsonify({"error": "q must be at least 2 characters"}), 400

    docs = WorkspaceKnowledgeDocument.query.filter_by(user_id=user.id).all()
    results = []
    for doc in docs:
        text_lower = (doc.content_text or "").lower()
        if q in text_lower:
            idx = text_lower.find(q)
            snippet_start = max(0, idx - 100)
            snippet = doc.content_text[snippet_start: idx + 300]
            results.append({**doc.to_dict(), "snippet": snippet})
    return jsonify({"results": results, "query": q})


@knowledge_ws_bp.route("/<int:doc_id>/ask", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def ask_doc(doc_id):
    """AI-powered Q&A within a single document."""
    user = _me()
    doc = WorkspaceKnowledgeDocument.query.filter_by(id=doc_id, user_id=user.id).first_or_404()
    body = request.get_json(silent=True) or {}
    question = (body.get("question") or "").strip()[:500]
    if not question:
        return jsonify({"error": "question required"}), 400

    from ..assistant.ai_key_resolver import get_workspace_ai_key
    key_info = get_workspace_ai_key(user)
    if not key_info.get("api_key"):
        return jsonify({"error": "No AI key configured"}), 400

    context = (doc.content_text or "")[:10000]
    prompt = (
        f"Answer the following question based only on the provided document.\n\n"
        f"Document ({doc.filename}):\n{context}\n\n"
        f"Question: {question}\n\nAnswer:"
    )

    try:
        answer = _call_ai_text(key_info, prompt)
    except Exception as exc:
        _log.warning("Document Q&A failed: %s", exc)
        return jsonify({"error": "AI request failed"}), 502

    return jsonify({"answer": answer, "document": doc.filename})


def _call_ai_text(key_info: dict, prompt: str) -> str:
    import requests as _r
    provider = key_info.get("provider", "gemini")
    api_key = key_info["api_key"]
    model = key_info.get("model", "gemini-2.0-flash")

    if provider == "gemini":
        resp = _r.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    if provider == "anthropic":
        resp = _r.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
            json={"model": model or "claude-haiku-4-5-20251001", "max_tokens": 1024,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"].strip()
    base = key_info.get("base_url", "https://api.openai.com/v1")
    resp = _r.post(
        f"{base.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": model or "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}]},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()
