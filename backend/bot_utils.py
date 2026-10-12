"""
Shared Telegram bot utilities.

send_group_message  — wrapper around bot.send_message that automatically
                      propagates message_thread_id for forum groups.

split_long_message  — split text that exceeds Telegram's 4096-char limit
                      into safe chunks.
"""

import logging

logger = logging.getLogger(__name__)

_TG_MAX_LEN = 4096


async def send_group_message(bot, chat_id, text, *, parse_mode=None,
                             reply_markup=None, source_message=None,
                             message_thread_id=None, **kwargs):
    """
    Send a message to a group, automatically propagating forum topic context.

    Priority for message_thread_id:
      1. Explicitly passed message_thread_id argument
      2. source_message.message_thread_id  (PTB Message object)
      3. None (regular group, no topic)
    """
    if message_thread_id is None and source_message is not None:
        message_thread_id = getattr(source_message, "message_thread_id", None)

    send_kwargs = dict(
        chat_id=chat_id,
        text=text,
        **kwargs,
    )
    if parse_mode:
        send_kwargs["parse_mode"] = parse_mode
    if reply_markup:
        send_kwargs["reply_markup"] = reply_markup
    if message_thread_id:
        send_kwargs["message_thread_id"] = message_thread_id

    return await bot.send_message(**send_kwargs)


def split_long_message(text, max_len=_TG_MAX_LEN):
    """
    Split text into chunks of at most max_len characters.
    Attempts to split on newlines to keep paragraphs intact.
    Returns a list of strings.
    """
    if len(text) <= max_len:
        return [text]

    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        # Try to split on the last newline before max_len
        # Prefer a paragraph boundary, then a line break, so an answer's blank-line
        # structure survives being split across messages.
        split_at = text.rfind("\n\n", 0, max_len)
        if split_at == -1:
            split_at = text.rfind("\n", 0, max_len)
        if split_at == -1:
            split_at = max_len
        chunks.append(text[:split_at].rstrip())
        text = text[split_at:].lstrip("\n")

    return chunks


async def send_long_message(bot, chat_id, text, *, parse_mode=None,
                            source_message=None, message_thread_id=None, **kwargs):
    """Send text, splitting into multiple messages if needed."""
    chunks = split_long_message(text)
    sent = []
    for chunk in chunks:
        try:
            msg = await send_group_message(
                bot, chat_id, chunk,
                parse_mode=parse_mode,
                source_message=source_message,
                message_thread_id=message_thread_id,
                **kwargs,
            )
            sent.append(msg)
        except Exception as e:
            logger.error("send_long_message chunk error chat=%s: %s", chat_id, e)
    return sent


def is_markdown_rejection(exc) -> bool:
    """True only when Telegram CONFIRMED it rejected the message's entities.

    A timeout / network error is ambiguous: the first send may already have been
    delivered, so resending (as plain text) could post the answer twice."""
    if type(exc).__name__ != "BadRequest":
        return False
    msg = str(exc).lower()
    return any(m in msg for m in (
        "can't parse entities", "can't find end of the entity", "unsupported start tag",
        "entity beginning", "can't parse"))


async def reply_ai_answer(message, text, *, prefix=""):
    """Reply with an AI-generated answer as ONE readable message (more only when
    it exceeds Telegram's 4096-char limit, split on paragraph boundaries).

    Paragraph breaks are preserved. The model's text is untrusted for Markdown
    purposes: a stray ``_`` or ``*`` makes Telegram reject the entity parse. Only
    that confirmed rejection falls back to plain text; any other failure (timeout,
    flood-wait, network) is re-raised and NOT resent, since the first attempt may
    have been delivered.
    """
    body = (text or "").strip()
    if not body:
        return None
    first = None
    for i, chunk in enumerate(split_long_message(body, _TG_MAX_LEN - len(prefix))):
        out = f"{prefix}{chunk}" if i == 0 else chunk
        try:
            sent = await message.reply_text(out, parse_mode="Markdown")
        except Exception as exc:
            if not is_markdown_rejection(exc):
                raise
            sent = await message.reply_text(out)
        first = first or sent
    return first
