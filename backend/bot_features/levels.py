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
                    ai_text = await self._generate_ai_levelup(first_name or "User", new_level)
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

    async def _generate_ai_levelup(self, first_name, level):
        try:
            from ..config import Config
            if not Config.OPENAI_API_KEY:
                return None
            from openai import OpenAI
            client = OpenAI(api_key=Config.OPENAI_API_KEY)
            response = client.chat.completions.create(
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

    def generate_rank_card(self, member, rank_position, total_members, settings=None):
        try:
            from PIL import Image, ImageDraw, ImageFont

            rank_card_cfg = {}
            if settings:
                rank_card_cfg = settings.get("levels", {}).get("rank_card", {})

            color_start = _hex_to_rgb(rank_card_cfg.get("bg_color_start", "#1a1a2e"))
            color_end = _hex_to_rgb(rank_card_cfg.get("bg_color_end", "#16213e"))
            accent = _hex_to_rgb(rank_card_cfg.get("accent_color", "#2196f3"))

            # 900×360 — 2.5:1 aspect ratio renders as a proper image preview in Telegram
            width, height = 900, 360
            img = Image.new("RGBA", (width, height), (*color_start, 255))
            draw = ImageDraw.Draw(img)

            # Horizontal gradient background
            for x in range(width):
                t = x / width
                r = int(color_start[0] + (color_end[0] - color_start[0]) * t)
                g = int(color_start[1] + (color_end[1] - color_start[1]) * t)
                b = int(color_start[2] + (color_end[2] - color_start[2]) * t)
                for y in range(height):
                    img.putpixel((x, y), (r, g, b, 255))

            # Accent border
            draw.rectangle([0, 0, width - 1, height - 1], outline=accent, width=3)

            # Load fonts — try common system fonts then fall back
            def _load_font(size):
                for name in ("arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"):
                    try:
                        return ImageFont.truetype(name, size)
                    except Exception:
                        pass
                return ImageFont.load_default()

            font_name  = _load_font(36)
            font_level = _load_font(26)
            font_info  = _load_font(22)
            font_bar   = _load_font(20)

            # Avatar circle (left column)
            pad = 30
            avatar_size = 160
            av_cx = pad + avatar_size // 2
            av_cy = height // 2
            draw.ellipse(
                [av_cx - avatar_size // 2, av_cy - avatar_size // 2,
                 av_cx + avatar_size // 2, av_cy + avatar_size // 2],
                outline=accent,
                width=4,
            )
            initial = (member.first_name or "?")[0].upper()
            draw.text((av_cx, av_cy), initial, fill=(255, 255, 255), font=_load_font(72), anchor="mm")

            # Text column
            tx = pad + avatar_size + 30
            ty = 45

            # Full name
            first = (member.first_name or "").strip()
            last = (getattr(member, "last_name", None) or "").strip()
            full_name = " ".join(x for x in [first, last] if x) or (member.username or f"User {member.telegram_user_id}")
            draw.text((tx, ty), full_name, fill=(255, 255, 255), font=font_name)

            # Username subtitle
            if member.username:
                draw.text((tx, ty + 46), f"@{member.username}", fill=(150, 160, 200), font=font_info)
                ty += 46

            ty += 52
            draw.text((tx, ty), f"Level {member.level}", fill=accent, font=font_level)
            ty += 38
            draw.text((tx, ty), f"Rank  #{rank_position} of {total_members}", fill=(180, 190, 210), font=font_info)
            ty += 32
            draw.text((tx, ty), f"XP  {member.xp:,}", fill=(180, 190, 210), font=font_info)

            # XP progress bar
            bar_x = tx
            bar_y = height - 70
            bar_w = width - tx - pad
            bar_h = 28

            current_level_xp = self._xp_for_level(member.level)
            next_level_xp = self._xp_for_level(member.level + 1)
            remaining_xp = member.xp - current_level_xp
            needed_xp = max(1, next_level_xp - current_level_xp)
            progress = min(1.0, remaining_xp / needed_xp)

            draw.rounded_rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], radius=14, fill=(30, 30, 60))
            fill_w = max(28, int(bar_w * progress))
            draw.rounded_rectangle([bar_x, bar_y, bar_x + fill_w, bar_y + bar_h], radius=14, fill=accent)
            draw.text(
                (bar_x + bar_w // 2, bar_y + bar_h // 2),
                f"{remaining_xp} / {needed_xp} XP",
                fill=(255, 255, 255),
                font=font_bar,
                anchor="mm",
            )

            buf = io.BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)
            return buf

        except ImportError:
            logger.warning("Pillow not available, returning None for rank card")
            return None
        except Exception as e:
            logger.error(f"Rank card generation error: {e}")
            return None

    def _xp_for_level(self, level):
        total = 0
        xp_needed = 100
        for _ in range(level - 1):
            total += xp_needed
            xp_needed = int(xp_needed * 1.5)
        return total
