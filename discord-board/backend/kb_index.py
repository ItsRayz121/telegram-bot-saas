"""Knowledge-base document ingestion + semantic retrieval for Guildizer.

Parity with Telegizer's KnowledgeBaseSystem, adapted to Guildizer's stack:
  * extract text from uploaded PDF / DOCX / TXT / MD files,
  * split into overlapping word chunks,
  * embed each chunk with OpenAI ``text-embedding-3-small`` (platform key),
  * persist the chunks (+ embeddings) on the KnowledgeDocument row,
  * answer /ask via cosine similarity over those chunks.

Guildizer is intentionally a *global-key* product (one platform OPENAI_API_KEY
on the worker, no per-guild keys), so embeddings use Config.OPENAI_API_KEY, else OPENROUTER_API_KEY.
When no key is set, documents are still stored and indexed for the keyword
fallback in ``knowledge.py`` — uploads never hard-fail just because vision/AI is
off. Self-contained: no Telegizer imports (Discord isolation rule).
"""
from __future__ import annotations

import io
import logging
import math
import re
import threading

from config import Config
from database import SessionLocal
from models import KnowledgeDocument

log = logging.getLogger("guildizer.kb")

EMBED_MODEL = "text-embedding-3-small"
_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Per-thread reason the last _embed() produced nothing (see embed_failure_message).
_embed_state = threading.local()
ALLOWED_EXT = ("pdf", "docx", "txt", "md")
MAX_FILE_BYTES = 5 * 1024 * 1024            # 5 MB per file (matches Telegizer)
_MAX_CONTENT_TEXT = 10000                   # stored extracted-text cap
_TOP_K = 3
_MAX_DOCS = 70                              # 50 documents (Pro cap) + 10 sources, with headroom
_MAX_CONTEXT = 4000

# Magic-byte signatures — extension alone is spoofable.
_MAGIC_SIGNATURES = {
    b"%PDF": "pdf",
    b"PK\x03\x04": "docx",   # docx is a ZIP container
}


# --- extraction --------------------------------------------------------------

def _extract_text(content_bytes: bytes, file_type: str) -> str:
    try:
        if file_type in ("txt", "md"):
            return content_bytes.decode("utf-8", errors="ignore")
        if file_type == "pdf":
            from pypdf import PdfReader  # lazy: optional dependency
            reader = PdfReader(io.BytesIO(content_bytes))
            return "\n".join((p.extract_text() or "") for p in reader.pages)
        if file_type == "docx":
            import docx  # lazy: python-docx
            d = docx.Document(io.BytesIO(content_bytes))
            return "\n".join(p.text for p in d.paragraphs)
    except Exception as e:  # noqa: BLE001
        log.error("KB text extraction failed (%s): %s", file_type, e)
    return ""


def _chunk_text(text: str, chunk_size: int = 400, overlap: int = 50) -> list[str]:
    words = (text or "").split()
    chunks, i = [], 0
    while i < len(words):
        chunks.append(" ".join(words[i:i + chunk_size]))
        i += chunk_size - overlap
    return [c for c in chunks if c.strip()]


# --- embeddings --------------------------------------------------------------

def _embedding_route(skip_openai: bool = False) -> tuple[str | None, str | None, str | None]:
    """(api_key, base_url, model): the platform OpenAI key if set, else the platform
    OpenRouter key, which serves the same model under an ``openai/`` prefix.
    ``skip_openai`` forces the OpenRouter route (used after OpenAI rejects the key)."""
    if Config.OPENAI_API_KEY and not skip_openai:
        return Config.OPENAI_API_KEY, None, EMBED_MODEL
    if Config.OPENROUTER_API_KEY:
        return Config.OPENROUTER_API_KEY, _OPENROUTER_BASE_URL, f"openai/{EMBED_MODEL}"
    return None, None, None


def embed_failure_message() -> str:
    """Why the last _embed() in this thread produced nothing. Names a missing key
    only when there really is none; a provider error is reported as such."""
    err = getattr(_embed_state, "error", None)
    if err:
        return f"Embeddings failed: the AI provider returned an error ({err}). The previous version is still in use."
    return ("Embeddings are unavailable: no OPENAI_API_KEY or OPENROUTER_API_KEY is set on the Guildizer "
            "service. The previous version is still in use.")


def _embed(texts: list[str]) -> list[list[float] | None]:
    """Embed texts with the platform key (OpenAI, else OpenRouter). Returns one
    vector per text, or None per text when embeddings are unavailable (no key /
    SDK / API error). Never raises — callers degrade to keyword search."""
    _embed_state.error = None
    if not texts:
        return []
    api_key, base_url, model = _embedding_route()
    if not api_key:
        return [None] * len(texts)
    try:
        from openai import OpenAI  # lazy
    except ImportError:
        log.warning("openai SDK not installed; KB embeddings disabled")
        _embed_state.error = "openai SDK not installed"
        return [None] * len(texts)
    client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)
    out: list[list[float] | None] = []
    # Batch to stay well under request limits.
    for start in range(0, len(texts), 64):
        batch = texts[start:start + 64]
        try:
            resp = client.embeddings.create(model=model, input=batch)
            out.extend(e.embedding for e in resp.data)
        except Exception as e:  # noqa: BLE001
            # The platform OpenAI key was rejected (revoked / typo'd env var): don't
            # strand the knowledge base on it - retry once via the OpenRouter key
            # (same model), and keep using that route for the remaining batches.
            if getattr(e, "status_code", None) == 401 and base_url is None:
                alt_key, alt_url, alt_model = _embedding_route(skip_openai=True)
                if alt_key:
                    log.warning("Platform OpenAI key rejected (401); retrying embeddings via OpenRouter")
                    try:
                        client = OpenAI(api_key=alt_key, base_url=alt_url)
                        base_url, model = alt_url, alt_model
                        resp = client.embeddings.create(model=model, input=batch)
                        out.extend(x.embedding for x in resp.data)
                        continue
                    except Exception as e2:  # noqa: BLE001
                        e = e2
            log.error("KB embedding error: %s", e)
            _embed_state.error = str(e)[:160]
            out.extend([None] * len(batch))
    return out


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


# --- ingestion ---------------------------------------------------------------

def detect_type(filename: str, content_bytes: bytes) -> tuple[str | None, str | None]:
    """(file_type, error). Validates extension against magic bytes."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "txt"
    if ext not in ALLOWED_EXT:
        return None, f"Unsupported file type .{ext}. Use: {', '.join(ALLOWED_EXT)}"
    detected = None
    for magic, ftype in _MAGIC_SIGNATURES.items():
        if content_bytes[:len(magic)] == magic:
            detected = ftype
            break
    if ext in ("txt", "md"):
        try:
            content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return None, "File does not appear to be valid UTF-8 text"
    elif detected is None:
        return None, f"File does not appear to be a valid {ext.upper()}"
    elif detected != ext:
        return None, f"File content does not match its extension (.{ext})"
    return ext, None


def process_upload(db, guild_id: int, filename: str, file_type: str,
                   content_bytes: bytes) -> tuple[dict | None, str | None]:
    """Extract → chunk → embed → persist. Returns (doc_dict, error)."""
    text = _extract_text(content_bytes, file_type)
    if not text.strip():
        if file_type == "pdf":
            return None, ("No selectable text found — this looks like a scanned or "
                          "image-only PDF. Re-save it with real text (or paste the "
                          "content as a text entry).")
        if file_type == "docx":
            return None, "No text found in this document — it may be empty or contain only images."
        return None, "Could not extract any text from this file."
    chunks = _chunk_text(text)
    if not chunks:
        return None, "No usable text after processing."
    embeddings = _embed(chunks)
    chunk_data = [{"text": c, "embedding": e} for c, e in zip(chunks, embeddings)]

    row = KnowledgeDocument(
        guild_id=guild_id,
        title=filename[:200],
        file_type=file_type,
        content="",                       # manual-text field unused for uploads
        content_text=text[:_MAX_CONTENT_TEXT],
        chunks=chunk_data,
        enabled=True,
    )
    db.add(row)
    db.commit()
    return row.to_dict(), None


# --- retrieval ---------------------------------------------------------------

_SOURCE_KIND = {
    "twitter": "external feed: X posts",
    "youtube": "external feed: YouTube",
    "website": "external source: website",
}


def _day(dt):
    return dt.strftime("%Y-%m-%d") if dt else None


def source_label(doc, src) -> str:
    """The label the model sees in front of each retrieved chunk.

    Three different dates are never conflated:
      published - what the provider reported about the content (or 'unknown');
      fetched / uploaded - when WE stored it. Not evidence of when a fact was true.
    """
    if src is not None:
        published = _day(src.published_at)
        fetched = _day(src.last_success_at or src.last_synced_at)
        return (
            f"{doc.title} | {_SOURCE_KIND.get(src.source_type, 'external source')} | "
            f"{'newest content published ' + published if published else 'publication date unknown'} | "
            f"fetched {fetched or 'unknown'}"
        )
    if (doc.file_type or "text") == "text":
        return f"{doc.title} | owner-written entry | publication date unknown"
    return (f"{doc.title} | owner-approved uploaded document | publication date unknown | "
            f"uploaded {_day(doc.created_at) or 'unknown'}")


def labels_for_docs(db, docs) -> dict:
    """{doc.id: label} for a list of KnowledgeDocument rows (one query for sources)."""
    from models import KnowledgeSource
    ids = [d.source_id for d in docs if d.source_id]
    srcs = {s.id: s for s in db.query(KnowledgeSource).filter(KnowledgeSource.id.in_(ids)).all()} if ids else {}
    return {d.id: source_label(d, srcs.get(d.source_id)) for d in docs}

def semantic_context(guild_id: int, question: str) -> tuple[str | None, bool] | None:
    """Best-effort semantic retrieval over embedded chunks.

    Returns ``(context, confident)`` when embedded chunks exist, or ``None`` to
    signal the caller should use the keyword fallback (no embeddings available)."""
    db = SessionLocal()
    try:
        docs = (
            db.query(KnowledgeDocument)
            .filter(KnowledgeDocument.guild_id == guild_id,
                    KnowledgeDocument.enabled.is_(True))
            .order_by(KnowledgeDocument.id)
            .limit(_MAX_DOCS)
            .all()
        )
        labels = labels_for_docs(db, docs)
        all_chunks = []
        for d in docs:
            for ch in (d.chunks or []):
                if ch.get("embedding"):
                    all_chunks.append((labels.get(d.id), ch))
        if not all_chunks:
            return None  # no embedded chunks → let keyword search handle it
        q_emb = _embed([question])[0]
        if q_emb is None:
            return None
        scored = sorted(
            ((_cosine(q_emb, ch["embedding"]), label, ch) for label, ch in all_chunks),
            key=lambda x: x[0], reverse=True,
        )
        confident = scored[0][0] >= 0.30
        context = ""
        for _score, label, ch in scored[:_TOP_K]:
            piece = (f"[Source: {label}]\n" if label else "") + ch["text"] + "\n\n"
            if len(context) + len(piece) > _MAX_CONTEXT:
                break
            context += piece
        return context.strip(), confident
    finally:
        db.close()
        SessionLocal.remove()
