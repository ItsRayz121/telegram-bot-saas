import io
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


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
            import math

            rank_card_cfg = {}
            if settings:
                rank_card_cfg = settings.get("levels", {}).get("rank_card", {})

            color_start = _hex_to_rgb(rank_card_cfg.get("bg_color_start", "#1a1a2e"))
            color_end = _hex_to_rgb(rank_card_cfg.get("bg_color_end", "#16213e"))
            accent = _hex_to_rgb(rank_card_cfg.get("accent_color", "#2196f3"))

            width, height = 800, 200
            img = Image.new("RGBA", (width, height), (*color_start, 255))
            draw = ImageDraw.Draw(img)

            for i in range(width):
                t = i / width
                r = int(color_start[0] + (color_end[0] - color_start[0]) * t)
                g = int(color_start[1] + (color_end[1] - color_start[1]) * t)
                b = int(color_start[2] + (color_end[2] - color_start[2]) * t)
                for j in range(height):
                    img.putpixel((i, j), (r, g, b, 255))

            draw.rectangle([0, 0, width - 1, height - 1], outline=accent, width=2)

            try:
                font_large = ImageFont.truetype("arial.ttf", 28)
                font_medium = ImageFont.truetype("arial.ttf", 20)
                font_small = ImageFont.truetype("arial.ttf", 16)
            except Exception:
                font_large = ImageFont.load_default()
                font_medium = font_large
                font_small = font_large

            avatar_x, avatar_y = 20, 20
            avatar_size = 160
            draw.ellipse(
                [avatar_x, avatar_y, avatar_x + avatar_size, avatar_y + avatar_size],
                outline=accent,
                width=3,
            )
            draw.text(
                (avatar_x + avatar_size // 2, avatar_y + avatar_size // 2),
                (member.first_name or "?")[0].upper(),
                fill=(255, 255, 255),
                font=font_large,
                anchor="mm",
            )

            text_x = avatar_x + avatar_size + 20
            name = member.first_name or "Unknown"
            if member.username:
                name += f" @{member.username}"
            draw.text((text_x, 20), name, fill=(255, 255, 255), font=font_large)
            draw.text((text_x, 60), f"Level {member.level}", fill=accent, font=font_medium)
            draw.text((text_x, 90), f"Rank #{rank_position} of {total_members}", fill=(180, 180, 200), font=font_small)
            draw.text((text_x, 115), f"XP: {member.xp:,}", fill=(180, 180, 200), font=font_small)

            xp_bar_x = text_x
            xp_bar_y = 145
            xp_bar_width = width - text_x - 20
            xp_bar_height = 20

            current_level_xp = self._xp_for_level(member.level)
            next_level_xp = self._xp_for_level(member.level + 1)
            remaining_xp = member.xp - current_level_xp
            needed_xp = next_level_xp - current_level_xp
            progress = min(1.0, remaining_xp / max(1, needed_xp))

            draw.rounded_rectangle(
                [xp_bar_x, xp_bar_y, xp_bar_x + xp_bar_width, xp_bar_y + xp_bar_height],
                radius=10,
                fill=(30, 30, 60),
            )
            fill_width = int(xp_bar_width * progress)
            if fill_width > 0:
                draw.rounded_rectangle(
                    [xp_bar_x, xp_bar_y, xp_bar_x + fill_width, xp_bar_y + xp_bar_height],
                    radius=10,
                    fill=accent,
                )
            draw.text(
                (xp_bar_x + xp_bar_width // 2, xp_bar_y + xp_bar_height // 2),
                f"{remaining_xp}/{needed_xp} XP",
                fill=(255, 255, 255),
                font=font_small,
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
