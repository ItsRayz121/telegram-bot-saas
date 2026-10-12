import io
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def _smart_name(first_name: str, username: str) -> str:
    """
    Best display name from the scalar fields stored on OfficialMember/Member.
    LevelSystem only has first_name + username (no last_name), so:
      1. @username  (if present — more identifiable than first name alone)
      2. first_name (fallback)
    Use the WelcomeSystem variant (which has access to the full User object and
    can include the last name) for welcome messages.
    """
    if username:
        return f"@{username}"
    return (first_name or "User").strip()


# ── Shared XP math — importable by both bot_manager.py and official_bot.py ───

def level_from_xp(xp: int) -> int:
    """Return the level that corresponds to a given total XP value."""
    return max(1, xp // 100 + 1)


def role_for_level(roles, level: int) -> str:
    """Role slug for a level, from a group's levels.roles list (highest threshold
    reached wins). Same slug form the custom bot has always stored ("Active Member"
    -> "active_member"); "member" when nothing matches."""
    for r in sorted(roles or [], key=lambda r: r.get("level", 0), reverse=True):
        if level >= r.get("level", 0):
            return str(r.get("name", "member")).lower().replace(" ", "_")
    return "member"


def resync_roles(model, group_filter, roles) -> None:
    """Re-derive every member's role from their stored level after the group's
    role ladder changed. One bulk UPDATE per tier. Caller commits."""
    tiers = sorted(roles or [], key=lambda r: r.get("level", 0))
    bounds = [t.get("level", 0) for t in tiers]
    for i, t in enumerate(tiers):
        q = model.query.filter(group_filter, model.level >= bounds[i])
        if i + 1 < len(tiers):
            q = q.filter(model.level < bounds[i + 1])
        q.update({"role": role_for_level(tiers, bounds[i])}, synchronize_session=False)
    if tiers:
        model.query.filter(group_filter, model.level < bounds[0]).update(
            {"role": "member"}, synchronize_session=False)


def xp_for_level(level: int) -> int:
    """Return the XP threshold required to reach `level`."""
    return max(0, (level - 1) * 100)


def _hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip("#")
    try:
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    except Exception:
        return (26, 26, 46)


class LevelSystem:

    def __init__(self, app):
        self.app = app

    async def add_message_xp(self, bot, chat_id, user_id, username, first_name, group):
        settings = group.settings.get("levels", {})
        if not settings.get("enabled", True):
            return

        xp_amount = settings.get("xp_per_message", 10)
        cooldown = settings.get("xp_cooldown_seconds", 60)

        with self.app.app_context():
            from ..database import DatabaseManager
            member = DatabaseManager.get_or_create_member(group.id, user_id, username, first_name)

            if member.last_xp_at:
                elapsed = (datetime.utcnow() - member.last_xp_at).total_seconds()
                if elapsed < cooldown:
                    return

            member, leveled_up, new_level = DatabaseManager.add_xp(
                group.id, user_id, xp_amount, username, first_name
            )

            if leveled_up and settings.get("announce_level_up", True):
                level_up_msg = settings.get(
                    "level_up_message",
                    "🎉 {first_name} leveled up to level {level}!",
                )

                if settings.get("ai_levelup_enabled"):
                    ai_text = await self._generate_ai_levelup(first_name or "User", new_level,
                                                              group_key=getattr(group, "id", None))
                    if ai_text:
                        level_up_msg = ai_text

                text = level_up_msg.format(
                    name=_smart_name(first_name, username),
                    first_name=first_name or "User",
                    username=f"@{username}" if username else first_name,
                    level=new_level,
                    user_id=user_id,
                )
                try:
                    topic_id = settings.get("levelup_topic_id")
                    kwargs = {}
                    if topic_id:
                        kwargs["message_thread_id"] = int(topic_id)
                    sent = await bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown", **kwargs)
                    delete_after = settings.get("delete_levelup_after_seconds", 0)
                    if delete_after and delete_after > 0 and sent:
                        import asyncio as _asyncio
                        await _asyncio.sleep(delete_after)
                        try:
                            await bot.delete_message(chat_id=chat_id, message_id=sent.message_id)
                        except Exception:
                            pass
                except Exception as e:
                    logger.error(f"Level up message error: {e}")

    async def add_reaction_xp(self, bot, chat_id, user_id, username, first_name, group):
        settings = group.settings.get("levels", {})
        if not settings.get("enabled", True):
            return
        xp_amount = settings.get("xp_per_reaction", 10)
        if xp_amount <= 0:
            return
        cooldown = settings.get("xp_reaction_cooldown_seconds", 30)

        with self.app.app_context():
            from ..database import DatabaseManager
            from ..models import Member
            member = DatabaseManager.get_or_create_member(group.id, user_id, username, first_name)
            if member.last_xp_at:
                elapsed = (datetime.utcnow() - member.last_xp_at).total_seconds()
                if elapsed < cooldown:
                    return
            DatabaseManager.add_xp(group.id, user_id, xp_amount, username, first_name)

    async def _generate_ai_levelup(self, first_name, level, group_key=None):
        try:
            from ..config import Config
            if not Config.OPENAI_API_KEY:
                return None
            from . import ai_burst_guard
            if not ai_burst_guard.allow("levelup", group_key):
                return None  # over the per-group cap: caller uses the group's own template
            import asyncio
            from openai import OpenAI
            client = OpenAI(api_key=Config.OPENAI_API_KEY, timeout=8.0, max_retries=0)
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model="gpt-3.5-turbo",
                messages=[{
                    "role": "user",
                    "content": f"Write a short, enthusiastic congratulation message for {first_name} reaching level {level} in a Telegram group. Max 1 sentence. Include an emoji."
                }],
                max_tokens=60,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"AI levelup generation error: {e}")
            return None

    def generate_rank_card(self, member, rank_position, total_members, settings=None,
                           name=None, avatar_bytes=None, avatar_key=""):
        """Return (png_bytes, caption) for the 960x640 rank card, or None on failure.
        Image and caption come from one RankSnapshot, so they can't disagree."""
        try:
            from . import rank_card
            first = (member.first_name or "").strip()
            last = (getattr(member, "last_name", None) or "").strip()
            snap = rank_card.build_snapshot(
                member, rank_position, total_members,
                name or " ".join(x for x in (first, last) if x) or (f"@{member.username}" if member.username else ""),
                accent=rank_card.accent_from_settings(settings),
                avatar_key=avatar_key if avatar_bytes else "",
            )
            return rank_card.render_cached(snap, avatar_bytes), snap.caption
        except ImportError:
            logger.warning("Pillow not available, returning None for rank card")
            return None
        except Exception as e:
            logger.error(f"Rank card generation error: {e}", exc_info=True)
            return None

    def _xp_for_level(self, level):
        total = 0
        xp_needed = 100
        for _ in range(level - 1):
            total += xp_needed
            xp_needed = int(xp_needed * 1.5)
        return total
