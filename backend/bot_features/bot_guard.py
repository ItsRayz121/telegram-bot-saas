"""
Bot-join policy enforcement (Phase 1 of the bot-spam protection work).

WHY THIS EXISTS
───────────────
Telegram NEVER delivers a message sent by one bot to another bot, regardless of
privacy mode or admin status. So when a *bot member* spams a group (adult/NSFW
content, inline-button link farms, invite redirects), Telegizer's bot literally
never receives those messages — no message-level scanner can ever see them.

The only reliable lever for bot-posted spam is to control the bot at JOIN time:
detect that the new member is a bot, mute it immediately, and apply the group's
Bot Policy before it gets a chance to post. This module is the single,
runtime-agnostic place that logic lives, so BOTH the official Telegizer bot and
custom (bring-your-own) bots inherit identical behaviour (per the bot-lineage
rule).

NOTIFICATION SAFETY
───────────────────
Admins are notified by private DM by default. We must NEVER post the spam bot's
@username as a tappable link in the group — during the window before an admin
responds, members would tap it and get scammed. The bot is muted the instant it
joins, so no notification is load-bearing for safety; it only decides WHO acts.

It deliberately knows nothing about Flask models or which runtime called it. The
caller passes a plain `settings` dict and a few callables; this module performs
the Telegram-side actions and builds the alert text. Anti-ban throttling is
handled by the caller's send path.
"""

import logging
from telegram import (
    ChatPermissions,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

logger = logging.getLogger(__name__)

_ADMIN_STATUSES = ("creator", "administrator")

# Default policy used when a group predates the bot_policy settings section.
_POLICY_DEFAULTS = {
    "enabled": True,
    "policy": "restrict_until_approval",
    "trusted_bot_usernames": [],
    "auto_trust_own_bots": True,
    "notify": "dm",
    "delete_alert_after_decision": True,
    "log_events": True,
    "approval_timeout_minutes": 60,
    "on_timeout": "ban",
}

# Pending approvals awaiting an admin decision, keyed by (group_id, bot_id).
# Per-process (each runtime imports its own instance) — used only to make the
# approval-timeout a no-op once an admin has already decided. If the process
# restarts the set is lost; the bot simply stays muted (the safe default) and
# admins can still Approve/Ban via the DM buttons, which carry all state inline.
_PENDING = set()


def mark_pending(group_id, bot_id):
    _PENDING.add((str(group_id), int(bot_id)))


def clear_pending(group_id, bot_id):
    _PENDING.discard((str(group_id), int(bot_id)))


def is_pending(group_id, bot_id) -> bool:
    return (str(group_id), int(bot_id)) in _PENDING


def normalize_username(username) -> str:
    """Lowercase, strip a leading @ and surrounding whitespace. '' for falsy."""
    if not username:
        return ""
    return str(username).strip().lstrip("@").lower()


def get_policy(settings: dict) -> dict:
    """Return the group's bot_policy merged over defaults (never raises)."""
    merged = dict(_POLICY_DEFAULTS)
    try:
        merged.update(settings.get("bot_policy", {}) or {})
    except Exception:
        pass
    return merged


def is_trusted(bot_username: str, policy: dict, auto_trusted_usernames=None) -> bool:
    """Is this bot exempt from policy enforcement?"""
    uname = normalize_username(bot_username)
    if not uname:
        return False
    explicit = {normalize_username(u) for u in policy.get("trusted_bot_usernames", []) or []}
    if uname in explicit:
        return True
    if policy.get("auto_trust_own_bots", True):
        auto = {normalize_username(u) for u in (auto_trusted_usernames or [])}
        if uname in auto:
            return True
    return False


async def bot_can_restrict(bot, chat_id) -> bool:
    """Live check: does *our* bot hold can_restrict_members in this chat?"""
    try:
        me = await bot.get_chat_member(chat_id=chat_id, user_id=bot.id)
        if me.status == "creator":
            return True
        return bool(getattr(me, "can_restrict_members", False))
    except Exception as exc:
        logger.debug("bot_can_restrict check failed for chat %s: %s", chat_id, exc)
        return False


async def restrict_bot(bot, chat_id, target_bot_id) -> bool:
    """Mute a bot member (cannot send anything). Returns True on success."""
    try:
        await bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=target_bot_id,
            permissions=ChatPermissions(
                can_send_messages=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
            ),
        )
        return True
    except Exception as exc:
        logger.warning("restrict_bot failed (chat=%s bot=%s): %s", chat_id, target_bot_id, exc)
        return False


async def lift_restriction(bot, chat_id, target_bot_id) -> bool:
    """Restore a bot's ability to post (used on approval)."""
    try:
        await bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=target_bot_id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
            ),
        )
        return True
    except Exception as exc:
        logger.warning("lift_restriction failed (chat=%s bot=%s): %s", chat_id, target_bot_id, exc)
        return False


async def ban_bot(bot, chat_id, target_bot_id) -> bool:
    """Ban a bot member from the group. Returns True on success."""
    try:
        await bot.ban_chat_member(chat_id=chat_id, user_id=target_bot_id)
        return True
    except Exception as exc:
        logger.warning("ban_bot failed (chat=%s bot=%s): %s", chat_id, target_bot_id, exc)
        return False


def _kb(group_id, bot_id):
    """Approve / Ban / Keep keyboard. group_id is embedded so the buttons work
    from a private DM (where query.message.chat is the DM, not the group)."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"botguard:approve:{group_id}:{bot_id}"),
            InlineKeyboardButton("⛔ Ban", callback_data=f"botguard:ban:{group_id}:{bot_id}"),
        ],
        [InlineKeyboardButton("🔇 Keep restricted", callback_data=f"botguard:keep:{group_id}:{bot_id}")],
    ])


def build_dm_alert(bot_user, group_title, added_by_name, outcome, group_id, timeout_minutes=None):
    """Private DM to an admin. Safe to include the @username here — only the
    admin sees it. Returns (text, reply_markup)."""
    label = ("@" + bot_user.username) if getattr(bot_user, "username", None) else (
        getattr(bot_user, "first_name", None) or f"bot {bot_user.id}")
    where = f" in *{group_title}*" if group_title else ""
    by = f"\nAdded by: {added_by_name}" if added_by_name else ""

    if outcome == "banned":
        text = (
            f"⛔ *Unapproved bot banned*{where}\n\n"
            f"Bot: {label}{by}\n\n"
            f"Group policy blocks bots that aren't on the trusted list."
        )
        return text, None

    if outcome == "alert_only":
        text = (
            f"⚠️ *New bot added*{where}\n\n"
            f"Bot: {label}{by}\n\n"
            f"I couldn't restrict it — I'm not an admin with *Ban users* permission there, "
            f"or the bot itself is an admin. Please review it, or grant me that permission "
            f"so I can protect the group automatically."
        )
        return text, None

    # restricted — actionable
    timeout_clause = (
        f"\n\nIf no one decides within *{timeout_minutes} min*, it will be banned automatically."
        if timeout_minutes else ""
    )
    text = (
        f"🤖 *New bot restricted*{where}\n\n"
        f"Bot: {label}{by}\n\n"
        f"It has been *muted* (cannot post). Bots can post adult/spam content that "
        f"automated scanners can't see, so new bots are held for review.{timeout_clause}\n\n"
        f"What should happen?"
    )
    return text, _kb(group_id, bot_user.id)


def build_group_notice(bot_user, outcome, group_id, with_buttons=False):
    """In-group notice. NEVER includes the bot's @username (no tappable scam
    link). Returns (text, reply_markup)."""
    if outcome == "banned":
        return ("⛔ An unapproved bot was added and has been *banned* per this group's policy.", None)
    if outcome == "alert_only":
        return (
            "⚠️ A new unverified bot was added, but I couldn't restrict it — I need "
            "*Ban users* admin permission. An admin should review or remove it.",
            None,
        )
    text = (
        "🛡️ A new *unverified bot* was added and has been automatically *restricted* "
        "(it can't post). An admin has been notified to approve or ban it."
    )
    kb = _kb(group_id, bot_user.id) if with_buttons else None
    return text, kb


async def enforce_bot_join(
    *,
    bot,
    chat,
    bot_user,
    added_by_name=None,
    settings: dict,
    auto_trusted_usernames=None,
):
    """Apply the group's Bot Policy to a freshly joined bot member.

    Performs the Telegram-side action (mute / ban) and returns a structured
    outcome so the caller can notify admins (DM / group) and log it.

    Returns a dict with: acted, outcome (ignored|trusted|restricted|banned|
    alert_only), reason, show_alert, bot_user, policy.
    """
    policy = get_policy(settings)
    result = {"acted": False, "outcome": "ignored", "reason": "",
              "show_alert": False, "bot_user": bot_user, "policy": policy}

    if not policy.get("enabled", True):
        result["reason"] = "bot_policy disabled"
        return result

    mode = policy.get("policy", "restrict_until_approval")
    if mode == "allow_all":
        result["reason"] = "policy=allow_all"
        return result

    if is_trusted(getattr(bot_user, "username", None), policy, auto_trusted_usernames):
        result["outcome"] = "trusted"
        result["reason"] = "bot on trusted allowlist"
        return result

    chat_id = chat.id
    target_id = bot_user.id

    can_act = await bot_can_restrict(bot, chat_id)
    target_is_admin = False
    try:
        tm = await bot.get_chat_member(chat_id=chat_id, user_id=target_id)
        target_is_admin = tm.status in _ADMIN_STATUSES
    except Exception:
        pass

    if not can_act or target_is_admin:
        result.update({
            "acted": False, "outcome": "alert_only",
            "reason": "no ban permission" if not can_act else "target is admin",
            "show_alert": True,
        })
        return result

    if mode in ("block_unapproved", "allowlist_only"):
        ok = await ban_bot(bot, chat_id, target_id)
        result.update({
            "acted": ok, "outcome": "banned" if ok else "alert_only",
            "reason": f"policy={mode}", "show_alert": True,
        })
        return result

    # Default: restrict_until_approval — mute and queue for admin decision.
    ok = await restrict_bot(bot, chat_id, target_id)
    if ok:
        mark_pending(chat_id, target_id)
    result.update({
        "acted": ok, "outcome": "restricted" if ok else "alert_only",
        "reason": "restricted pending admin approval", "show_alert": True,
    })
    return result


async def apply_timeout_action(bot, group_id, bot_id, on_timeout: str) -> str:
    """Called when the approval timer fires. No-ops if an admin already decided
    (the pending entry was cleared). Returns the action taken: ban|keep|skip."""
    if not is_pending(group_id, bot_id):
        return "skip"
    clear_pending(group_id, bot_id)
    if on_timeout == "ban":
        await ban_bot(bot, group_id, bot_id)
        return "ban"
    return "keep"


# ── Callback (Approve / Ban / Keep) ──────────────────────────────────────────

def parse_callback(data: str):
    """Parse 'botguard:<action>:<group_id>:<bot_id>' → (action, group_id, bot_id)
    or (None, None, None). group_id stays a string (chat ids are large/negative)."""
    try:
        parts = data.split(":")
        if len(parts) == 4 and parts[0] == "botguard":
            return parts[1], parts[2], int(parts[3])
    except Exception:
        pass
    return None, None, None


async def resolve_bot_username(bot, chat_id, bot_id):
    """Best-effort fetch of a bot member's username (for adding to the allowlist)."""
    try:
        m = await bot.get_chat_member(chat_id=chat_id, user_id=bot_id)
        return getattr(m.user, "username", None)
    except Exception:
        return None
