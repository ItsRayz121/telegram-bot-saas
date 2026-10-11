"""AI *samples* for the dashboard's message previews.

A sample answers a made-up question with the configured prompt so an admin can see tone, length and
language before going live. It is NOT a live reply:

  * nothing is sent to Telegram/Discord, and no delivery job is queued;
  * no conversation memory, knowledge-base content, member XP, campaign record, analytics counter or
    ai_activity row is written (the live paths log those; these helpers never call them);
  * it reads no group data at all: the question and the "knowledge" it may use are typed by the admin;
  * it is a real provider call, so it counts against the same quota / platform spend ceiling as any
    other AI call made with the platform key (and is billed to the admin's own key if they set one).

Only one sample per user + target runs at a time.
"""
import logging
import threading
import time

_log = logging.getLogger(__name__)
_inflight: dict = {}
_lock = threading.Lock()
_STALE_AFTER = 75  # seconds; a crashed request must not block the button forever

MAX_QUESTION = 300
MAX_CONTEXT = 800
MAX_NOTE = 1200


def claim(key) -> bool:
    """True if this caller may start a sample; False if one is already running for `key`."""
    now = time.time()
    with _lock:
        started = _inflight.get(key)
        if started and now - started < _STALE_AFTER:
            return False
        _inflight[key] = now
        return True


def release(key) -> None:
    with _lock:
        _inflight.pop(key, None)


def clamp(value, limit) -> str:
    return str(value or "").strip()[:limit]


def estimate_tokens(*texts) -> int:
    """Rough token count (4 chars/token) for platform-key accounting when the provider gives no usage."""
    return max(1, sum(len(t or "") for t in texts) // 4)


def ai_enabled() -> bool:
    from . import platform_config as pc
    return bool(pc.is_feature_enabled("ai_features_enabled"))


def generate_group_sample(*, plan_owner, owner_user_id, group_id=None, telegram_group_id=None,
                          group_name="this community", lock_key, data):
    """Shared by the official-group and legacy custom-bot-group sample endpoints.

    Returns (payload_dict, http_status). Callers have ALREADY authorised the person for this group
    (owner/manager only; viewers never reach here) and passed the owner's user object as `plan_owner`.
    """
    import asyncio
    from flask import current_app
    from .utils.plan_gating import require_paid
    from .bot_features.ai_personality import PERSONALITIES
    from .bot_features.knowledge_base import KnowledgeBaseSystem, _is_no_answer
    from .assistant.ai_key_resolver import (
        resolve_ai_provider_for_group, record_token_usage, QuotaExceededError, PlatformCostLimitError,
    )
    from .models import db, User

    if not ai_enabled():
        return {"error": "AI features are switched off platform-wide right now.", "code": "AI_DISABLED"}, 503
    paid = require_paid(plan_owner, "AI replies")
    if paid:
        resp, status = paid
        return resp.get_json(), status

    question = clamp(data.get("question"), MAX_QUESTION)
    context = clamp(data.get("sample_context"), MAX_CONTEXT)
    if not question:
        return {"error": "Enter a sample question first."}, 400
    if not context:
        return {"error": "Enter a sample fact for the bot to answer from."}, 400
    personality = data.get("personality") or "professional_support"
    if personality not in PERSONALITIES:
        return {"error": "Unknown personality"}, 400
    kb_settings = {
        "personality": personality,
        "reply_length": data.get("reply_length") or "balanced",
        "emoji_level": data.get("emoji_level") or "minimal",
        "formality_level": data.get("formality_level") or "neutral",
        "custom_instructions": clamp(data.get("custom_instructions"), MAX_NOTE),
    }

    if not claim(lock_key):
        return {"error": "A sample is already being generated. Wait for it to finish."}, 429
    try:
        try:
            resolved = resolve_ai_provider_for_group(owner_user_id, group_id, telegram_group_id)
        except QuotaExceededError as e:
            return {"error": str(e), "code": "QUOTA"}, 429
        except PlatformCostLimitError as e:
            return {"error": str(e), "code": "PLATFORM_BUDGET"}, 503
        if not resolved.get("api_key"):
            return {"error": "No AI provider is configured for this group. Add a key under AI & Integrations.", "code": "NO_PROVIDER"}, 409
        key_config = {
            "provider": resolved["provider"], "api_key": resolved["api_key"],
            "base_url": resolved.get("base_url"), "model_name": resolved.get("model"),
        }
        kb = KnowledgeBaseSystem(current_app._get_current_object())
        knowledge = "[SAMPLE KNOWLEDGE typed by the admin for this preview]\n" + context
        try:
            answer = asyncio.run(kb._generate_answer(
                question, knowledge, key_config, group_name=group_name or "this community", kb_settings=kb_settings))
        except Exception:
            _log.exception("ai reply sample provider call failed")
            answer = None
        if not answer:
            return {"error": "The AI provider did not return a sample. Try again in a moment.", "code": "PROVIDER_FAILED"}, 502
        if resolved.get("source") == "platform":
            try:
                record_token_usage(User.query.get(owner_user_id), estimate_tokens(question, knowledge, answer))
            except Exception:
                db.session.rollback()
        no_answer = bool(_is_no_answer(answer))
        return {
            "answer": None if no_answer else answer, "no_answer": no_answer,
            "provider": resolved.get("provider"), "model": resolved.get("model"),
            "billed_to": "platform quota" if resolved.get("source") == "platform" else "your own API key",
        }, 200
    finally:
        release(lock_key)
