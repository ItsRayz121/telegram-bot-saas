"""Engagement Campaigns — verification engine (Phase 5).

The realistic, production-safe subset (see ENGAGEMENT_CAMPAIGNS_PLAN.md §4):
  - Telegram channel/group JOIN  → reliably auto-verifiable via getChatMember
    (the bot must be an admin in the target chat).
  - Link-validity                → URL shape + platform-host match (premium gate
    is enforced at campaign creation). Optional deep API checks degrade
    gracefully to shape-only when no API key is configured.

Everything else (X likes/follows, YouTube subscribe, IG/FB) stays manual/honor —
intentionally NOT auto-verified.
"""

import logging
import re

logger = logging.getLogger(__name__)

# Member-like statuses returned by getChatMember.
_MEMBER_STATUSES = {"creator", "administrator", "member", "owner"}

# Allowed hosts per platform for link-validity checks.
_PLATFORM_HOSTS = {
    "x": ["x.com", "twitter.com"],
    "youtube": ["youtube.com", "youtu.be"],
    "telegram": ["t.me", "telegram.me"],
    "instagram": ["instagram.com"],
    "facebook": ["facebook.com", "fb.com"],
}


async def verify_telegram_join(bot, chat_ref, user_id):
    """Return True iff user_id is a member of chat_ref. Never raises."""
    if not chat_ref:
        return False
    try:
        member = await bot.get_chat_member(chat_id=chat_ref, user_id=int(user_id))
        status = getattr(member, "status", None)
        status = getattr(status, "value", status)  # enum → str
        if status in _MEMBER_STATUSES:
            return True
        # 'restricted' members may still be in the chat.
        if status == "restricted" and getattr(member, "is_member", False):
            return True
        return False
    except Exception as e:
        logger.info("verify_telegram_join failed for chat=%s user=%s: %s", chat_ref, user_id, e)
        return False


def validate_link(url, platform=None):
    """Shape + platform-host validation. Returns (ok, reason)."""
    if not url or not re.match(r"^https?://", url.strip(), re.I):
        return False, "Please send a valid link starting with http:// or https://"
    if platform and platform in _PLATFORM_HOSTS:
        host_ok = any(h in url.lower() for h in _PLATFORM_HOSTS[platform])
        if not host_ok:
            return False, f"That doesn’t look like a {platform} link."
    return True, None


def validate_link_payload(campaign, answers):
    """For a link-mode campaign, validate the submitted link(s). Returns
    (ok, reason). Checks every URL-type field; if there are none, validates any
    answer that looks like a URL."""
    answers = answers or {}
    url_fields = [f for f in campaign.custom_fields.all() if f.field_type == "url"]
    values = []
    if url_fields:
        values = [(answers.get(f.key) or "").strip() for f in url_fields]
        if not any(values):
            return False, "Please submit the required link."
    else:
        values = [v for v in answers.values() if isinstance(v, str) and v.strip().lower().startswith("http")]
        if not values:
            return False, "Please submit a valid link."
    for v in values:
        if not v:
            continue
        ok, reason = validate_link(v, campaign.platform)
        if not ok:
            return False, reason
    return True, None
