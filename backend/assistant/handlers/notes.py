"""Notes, links, and search handlers."""
from __future__ import annotations

from ._ai import call_ai_text
from ._state import save_state
from ._prompts import GENERAL_AI_SYSTEM


def handle_save_note(user_id: int, content: str) -> dict:
    from ...models import db, Note
    if not content or not content.strip():
        return {"reply": "What would you like me to note down?", "intent": "save_note", "data": None}
    note = Note(user_id=user_id, content=content.strip()[:5000], source="bot", tags=[])
    db.session.add(note)
    db.session.commit()
    try:
        from ...assistant.context_service import AssistantContextService
        AssistantContextService.invalidate(user_id)
    except Exception:
        pass
    return {
        "reply": f'📝 Note saved: "{content.strip()[:80]}{"…" if len(content) > 80 else ""}"',
        "intent": "save_note",
        "data": note.to_dict(),
        "suggestions": [
            {"label": "Show my notes", "value": "show my notes"},
            {"label": "Add another", "value": "note this: "},
        ],
    }


def handle_list_notes(user_id: int) -> dict:
    from ...models import Note
    notes = (
        Note.query.filter_by(user_id=user_id)
        .order_by(Note.created_at.desc()).limit(8).all()
    )
    if not notes:
        return {"reply": 'You have no notes yet. Try "Note this: your message".', "intent": "list_notes", "data": {"notes": []}}
    lines = [f"• {n.content[:100]}{'…' if len(n.content) > 100 else ''}" for n in notes]
    return {"reply": f"Here are your {len(notes)} most recent notes:\n\n" + "\n".join(lines),
            "intent": "list_notes", "data": {"notes": [n.to_dict() for n in notes]}}


def handle_search_notes(user_id: int, query: str, key_info: dict) -> dict:
    from ...assistant.embeddings import semantic_search
    results = semantic_search(user_id, query, key_info, limit=5)
    if not results:
        return {"reply": f'No notes found matching "{query[:60]}". Try a different phrase.',
                "intent": "search_notes", "data": {"notes": [], "query": query}}
    lines = [f"• {n.content[:120]}{'…' if len(n.content) > 120 else ''}" for n in results]
    return {
        "reply": f'Found {len(results)} note(s) matching "{query[:40]}":\n\n' + "\n".join(lines),
        "intent": "search_notes",
        "data": {"notes": [n.to_dict() for n in results], "query": query},
    }


def handle_summarize_notes(user_id: int, key_info: dict) -> dict:
    from ...models import Note
    notes = (
        Note.query.filter_by(user_id=user_id)
        .order_by(Note.created_at.desc()).limit(20).all()
    )
    if not notes:
        return {"reply": "You have no notes to summarize yet.", "intent": "summarize_notes", "data": None}

    if not key_info.get("api_key"):
        return handle_list_notes(user_id)

    notes_text = "\n".join(f"- {n.content[:200]}" for n in notes)
    prompt = (
        "The following are a user's personal notes. Provide a concise summary (3–5 bullet points) "
        "highlighting key themes, decisions, and action items.\n\n"
        f"Notes:\n{notes_text}\n\nSummary:"
    )
    try:
        summary = call_ai_text(key_info, GENERAL_AI_SYSTEM, prompt)
    except Exception:
        summary = f"You have {len(notes)} notes covering various topics."

    return {
        "reply": f"📝 Summary of your {len(notes)} most recent notes:\n\n{summary}",
        "intent": "summarize_notes",
        "data": {"note_count": len(notes)},
        "suggestions": [
            {"label": "Show all notes", "value": "show my notes"},
            {"label": "Search notes", "value": "search my notes"},
        ],
    }


def handle_save_link(user_id: int, url: str, label: str | None = None) -> dict:
    from ...models import db, Note
    content = f"{label or 'Saved link'}: {url}"
    note = Note(user_id=user_id, content=content[:5000], source="bot", tags=["link"])
    db.session.add(note)
    db.session.commit()
    return {
        "reply": f"🔗 Link saved: {url[:80]}",
        "intent": "save_link",
        "data": note.to_dict(),
        "suggestions": [{"label": "Show saved links", "value": "show my notes"}],
    }
