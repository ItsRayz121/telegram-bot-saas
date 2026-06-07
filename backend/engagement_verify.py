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


# Human labels for platforms, used in field-level error messages.
_PLATFORM_LABEL = {
    "x": "Twitter/X", "youtube": "YouTube", "telegram": "Telegram",
    "instagram": "Instagram", "facebook": "Facebook",
}

_URL_RE = re.compile(r"^https?://", re.I)
_UID_RE = re.compile(r"^[A-Za-z0-9._-]{3,64}$")
_USERNAME_RE = re.compile(r"^@?[A-Za-z0-9._]{2,64}$")
_WALLET_RE = re.compile(r"^(0x[a-fA-F0-9]{40}|[A-Za-z0-9]{26,64})$")
_TXHASH_RE = re.compile(r"^(0x)?[A-Fa-f0-9]{40,128}$")


def _looks_like_url(value):
    return bool(_URL_RE.match((value or "").strip()))


def validate_field_value(field_type, value, *, platform=None):
    """Validate a single proof value by its declared type. Returns
    (ok, normalized_value, error_message). Used by BOTH the bot DM flow and the
    Mini App API so submissions are validated identically everywhere.

    Screenshots are validated separately (a photo upload), not here.
    """
    v = (value or "").strip()
    if not v:
        return False, v, "Please provide a value."

    if field_type == "url":
        ok, reason = validate_link(v, platform)
        if not ok:
            return False, v, reason
        return True, v, None

    if field_type == "uid":
        if _looks_like_url(v):
            return False, v, "Please submit your exchange UID, not a link."
        if not _UID_RE.match(v):
            return False, v, "That doesn’t look like a valid UID. Send the numbers/letters only (e.g. 123456789)."
        return True, v, None

    if field_type == "wallet":
        if _looks_like_url(v) or " " in v:
            return False, v, "Please submit a valid wallet address (no links or spaces)."
        if not _WALLET_RE.match(v):
            return False, v, "That doesn’t look like a valid wallet address. Double-check and resend."
        return True, v, None

    if field_type == "tx_hash":
        if _looks_like_url(v) or " " in v:
            return False, v, "Please submit a valid transaction hash."
        if not _TXHASH_RE.match(v):
            return False, v, "That doesn’t look like a valid transaction hash."
        return True, v, None

    if field_type == "username":
        if _looks_like_url(v) or " " in v:
            return False, v, "Please submit a username / handle, not a link."
        if not _USERNAME_RE.match(v):
            return False, v, "That doesn’t look like a valid username/handle."
        return True, v.lstrip("@"), None  # normalize: strip leading @

    # text and any unknown type → accept as-is.
    return True, v, None


def validate_link(url, platform=None):
    """Shape + platform-host validation. Returns (ok, reason)."""
    if not url or not re.match(r"^https?://", url.strip(), re.I):
        return False, "Please send a valid link starting with http:// or https://"
    if platform and platform in _PLATFORM_HOSTS:
        host_ok = any(h in url.lower() for h in _PLATFORM_HOSTS[platform])
        if not host_ok:
            label = _PLATFORM_LABEL.get(platform, platform)
            return False, f"Please submit a valid {label} URL."
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
