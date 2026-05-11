"""
Multimodal image understanding for Telegram group bots.

Architecture (cheapest-first gating):
  Gate 1 — feature flag + photo/document presence
  Gate 2 — cheap text classifier on caption (zero API cost)
  Gate 3 — file size / type guard
  Gate 4 — vision API call (GPT-4o mini by default)
  → high confidence  → reply to user
  → low confidence   → escalate to admin(s) with AI summary

Cost target: ~$0.0003–0.0008 per analyzed image (GPT-4o mini).
Images that don't pass gates cost $0.
"""
import asyncio
import base64
import io
import json
import logging
import re

logger = logging.getLogger(__name__)

# ── Cheap caption keyword classifier ─────────────────────────────────────────
# These words in a caption strongly suggest the user needs help with the image.

_SIGNAL_PATTERNS = re.compile(
    r"\b("
    r"why|what|how|help|error|issue|problem|fail(?:ed|ing)?|"
    r"not work(?:ing)?|broken|bug|stuck|wrong|cant|can't|"
    r"withdraw|transaction|wallet|payment|deposit|transfer|"
    r"pending|reject(?:ed)?|declin(?:ed|ing)?|block(?:ed)?|"
    r"fix|solve|support|urgent|please|explain|understand|"
    r"screenshot|proof|showing|see|look|check"
    r")\b",
    re.IGNORECASE,
)

_MAX_IMAGE_MB = 10  # absolute ceiling before even trying
_VISION_MODEL = "gpt-4o-mini"  # 15× cheaper than gpt-4o, sufficient for screenshots

# ── Structured vision prompt ──────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a helpful community support assistant analyzing an image sent by a group member.
Respond ONLY with valid JSON matching this exact schema — no markdown, no extra text:

{
  "visible_text": "<exact text visible in the image, or empty string>",
  "issue_type": "<one of: withdrawal_error | transaction_issue | wallet_issue | ui_bug | payment_proof | chart | error_message | app_screenshot | other | unclear>",
  "summary": "<one concise sentence describing what is shown>",
  "can_answer": <true or false>,
  "answer": "<helpful answer for the user, or null if cannot answer>",
  "confidence": <float 0.0–1.0>,
  "escalation_reason": "<why you cannot answer confidently, or null>"
}

Confidence guide:
- 0.85+: clear, specific answer derivable from image + caption
- 0.65–0.85: likely answer but some ambiguity
- 0.40–0.65: partial answer, missing context
- below 0.40: cannot determine reliably

Be accurate and concise. Do NOT hallucinate details not visible in the image.\
"""


def _build_user_prompt(caption: str, group_name: str) -> str:
    parts = []
    if caption:
        parts.append(f"User message/caption: {caption}")
    parts.append(f"Community: {group_name}")
    if not caption:
        parts.append("(No text caption — analyze image only)")
    return "\n".join(parts)


# ── Gate 2: cheap caption classifier ─────────────────────────────────────────

def _caption_has_signal(caption: str) -> bool:
    """Return True if caption suggests the image needs AI analysis."""
    if not caption:
        return False  # no caption = no context = skip by default
    return bool(_SIGNAL_PATTERNS.search(caption))


# ── Gate 3: file type guard ───────────────────────────────────────────────────

_SKIP_MIME = {"image/gif", "image/webp", "video/mp4", "video/webm"}
_ALLOWED_PHOTO_MIME = {"image/jpeg", "image/png"}


def _should_skip_document(document) -> bool:
    """Return True for GIFs, stickers, videos — not useful for vision."""
    if not document:
        return False
    mime = (document.mime_type or "").lower()
    return mime in _SKIP_MIME or not mime.startswith("image/")


# ── Vision API call ───────────────────────────────────────────────────────────

async def _call_vision(api_key: str, base_url: str | None,
                       image_bytes: bytes, caption: str, group_name: str) -> dict:
    """Call GPT-4o mini vision. Returns parsed JSON dict or raises."""
    from openai import AsyncOpenAI

    kwargs = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url

    client = AsyncOpenAI(**kwargs)
    b64 = base64.b64encode(image_bytes).decode()

    response = await client.chat.completions.create(
        model=_VISION_MODEL,
        max_tokens=600,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{b64}",
                            "detail": "low",  # "low" detail = 85 tokens flat, sufficient for screenshots
                        },
                    },
                    {"type": "text", "text": _build_user_prompt(caption, group_name)},
                ],
            },
        ],
    )

    raw = response.choices[0].message.content or ""
    # Strip markdown code fences if model wraps output
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    return json.loads(raw)


# ── Download helper ───────────────────────────────────────────────────────────

async def _download_image(bot, file_id: str, max_mb: float) -> bytes | None:
    """Download a Telegram file into memory. Returns None if too large."""
    try:
        tg_file = await bot.get_file(file_id)
        if tg_file.file_size and tg_file.file_size > max_mb * 1024 * 1024:
            logger.debug(f"image_ai: file too large ({tg_file.file_size} bytes), skipping")
            return None
        buf = io.BytesIO()
        await tg_file.download_to_memory(buf)
        return buf.getvalue()
    except Exception as exc:
        logger.warning(f"image_ai: download failed: {exc}")
        return None


# ── Admin escalation ──────────────────────────────────────────────────────────

async def _escalate_to_admins(bot, message, result: dict, admin_ids: list,
                               group_name: str, caption: str):
    """Forward the original message to each admin with an AI-generated summary."""
    if not admin_ids:
        return

    sender = message.from_user
    sender_name = f"@{sender.username}" if (sender and sender.username) else (
        sender.first_name if sender else "Unknown"
    )

    issue = result.get("issue_type", "unknown")
    summary = result.get("summary", "No summary available.")
    confidence = result.get("confidence", 0.0)
    escalation_reason = result.get("escalation_reason") or "Low confidence — needs human review"
    visible_text = result.get("visible_text", "")

    summary_msg = (
        f"🔍 *AI Escalation — Image Review Needed*\n\n"
        f"👤 *User:* {sender_name}\n"
        f"📍 *Group:* {group_name}\n"
        f"🏷️ *Issue type:* {issue.replace('_', ' ').title()}\n"
        f"🤖 *AI summary:* {summary}\n"
    )
    if visible_text:
        preview = visible_text[:200] + ("…" if len(visible_text) > 200 else "")
        summary_msg += f"📄 *Visible text:* `{preview}`\n"
    if caption:
        summary_msg += f"💬 *User caption:* _{caption}_\n"
    summary_msg += (
        f"⚠️ *AI confidence:* {int(confidence * 100)}% — human review needed\n"
        f"📌 *Reason:* {escalation_reason}"
    )

    for admin_id in admin_ids:
        try:
            await bot.send_message(
                chat_id=int(admin_id),
                text=summary_msg,
                parse_mode="Markdown",
            )
            # Forward the original message so admin sees image + context
            await bot.forward_message(
                chat_id=int(admin_id),
                from_chat_id=message.chat_id,
                message_id=message.message_id,
            )
        except Exception as exc:
            logger.debug(f"image_ai: escalation DM to admin {admin_id} failed: {exc}")


# ── Main entry point ──────────────────────────────────────────────────────────

async def maybe_handle_image(
    bot,
    message,
    group_id,
    telegram_group_id,
    image_settings: dict,
    kb_settings: dict,
    group_name: str,
    app,                    # Flask app for DB context
    api_key: str | None,
    base_url: str | None,
) -> bool:
    """
    Full gating + analysis pipeline. Returns True if image was handled (reply or escalation sent).

    Callers: bot_manager._handle_auto_kb_reply area, official_bot.on_message.
    """
    if not image_settings.get("enabled", False):
        return False

    # Gate 1 — does this message have an image?
    photo = message.photo
    document = message.document
    if not photo and not document:
        return False

    # Gate 1b — skip animated GIFs, stickers, videos
    if document and _should_skip_document(document):
        return False

    # Gate 1c — skip bot senders
    sender = message.from_user
    if not sender or sender.is_bot:
        return False

    caption = (message.caption or message.text or "").strip()

    cost_mode = image_settings.get("cost_mode", "balanced")
    mention_only = image_settings.get("mention_only", True)

    # Gate 2a — require caption (free check before any API call)
    require_caption = image_settings.get("require_caption", True)
    if require_caption and not caption:
        return False

    # Gate 2b — caption signal keywords (free, before any API call)
    if cost_mode in ("balanced", "aggressive_savings"):
        if not _caption_has_signal(caption):
            logger.debug("image_ai: caption has no signal keywords, skipping")
            return False

    # Gate 2c — mention check (one bot.get_me() call, only if needed)
    if mention_only:
        bot_me = await bot.get_me()
        bot_username = bot_me.username
        mentioned = bot_username and f"@{bot_username}".lower() in caption.lower()
        replied_to_bot = (
            message.reply_to_message and
            message.reply_to_message.from_user and
            message.reply_to_message.from_user.username == bot_username
        )
        if not mentioned and not replied_to_bot:
            return False

    # Gate 3 — file size
    max_mb = float(image_settings.get("max_image_size_mb", 5))
    file_id = photo[-1].file_id if photo else document.file_id

    # Gate 4 — needs an API key
    if not api_key:
        logger.debug("image_ai: no API key available, skipping")
        return False

    # Download image
    image_bytes = await _download_image(bot, file_id, max_mb=min(max_mb, _MAX_IMAGE_MB))
    if not image_bytes:
        return False

    # Vision API call
    try:
        result = await asyncio.wait_for(
            _call_vision(api_key, base_url, image_bytes, caption, group_name),
            timeout=30.0,
        )
    except asyncio.TimeoutError:
        logger.warning("image_ai: vision API timed out")
        return False
    except json.JSONDecodeError as exc:
        logger.warning(f"image_ai: JSON parse error from vision API: {exc}")
        return False
    except Exception as exc:
        logger.error(f"image_ai: vision API error: {exc}")
        return False

    threshold = float(image_settings.get("confidence_threshold", 0.65))
    confidence = float(result.get("confidence", 0.0))
    can_answer = result.get("can_answer", False)
    answer = result.get("answer")

    logger.debug(f"image_ai: confidence={confidence:.2f}, can_answer={can_answer}, issue={result.get('issue_type')}")

    # High confidence — reply to user
    if can_answer and answer and confidence >= threshold:
        try:
            await message.reply_text(answer)
            return True
        except Exception as exc:
            logger.error(f"image_ai: reply failed: {exc}")
            return False

    # Low confidence — prefer global escalation, fall back to legacy image_ai escalation
    group_settings = {}
    if app:
        try:
            with app.app_context():
                from ..models import Group
                grp = Group.query.get(group_id)
                if grp:
                    group_settings = grp.settings or {}
        except Exception:
            pass

    global_esc = group_settings.get("escalation", {})
    used_global = False

    if global_esc.get("enabled") and "ai_image" in global_esc.get("types", []):
        try:
            from .escalation import trigger_escalation
            sender = message.from_user
            uname = getattr(sender, "username", None) or ""
            uid   = getattr(sender, "id", None)
            await trigger_escalation(
                bot=bot,
                group_settings=group_settings,
                issue_type="ai_image",
                original_content=caption or result.get("visible_text", "") or "(image)",
                context_data={
                    "confidence": confidence,
                    "group_name": group_name,
                    "user_id": uid,
                    "username": uname,
                    "issue_type": result.get("issue_type"),
                    "summary": result.get("summary"),
                },
                app=app,
                group_id=group_id,
                telegram_group_id=str(telegram_group_id) if telegram_group_id else None,
                original_message=message,
            )
            used_global = True
        except Exception as exc:
            logger.warning(f"image_ai: global escalation failed: {exc}")

    if not used_global and image_settings.get("escalation_enabled", True):
        admin_ids = image_settings.get("escalation_admin_ids") or []
        if admin_ids:
            await _escalate_to_admins(bot, message, result, admin_ids, group_name, caption)
            used_global = True

    if used_global:
        try:
            await message.reply_text(
                "I've forwarded your message to the support team for a detailed response. "
                "They'll get back to you as soon as possible."
            )
        except Exception:
            pass
        return True

    return False
