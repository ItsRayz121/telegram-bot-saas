import io
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


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
                text = level_up_msg.format(
                    first_name=first_name or "User",
                    username=f"@{username}" if username else first_name,
                    level=new_level,
                    user_id=user_id,
                )
                try:
                    await bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
                except Exception as e:
                    logger.error(f"Level up message error: {e}")

    def generate_rank_card(self, member, rank_position, total_members):
        try:
            from PIL import Image, ImageDraw, ImageFont
            import math

            width, height = 800, 200
            img = Image.new("RGBA", (width, height), (15, 15, 30, 255))
            draw = ImageDraw.Draw(img)

            for i in range(width):
                r = int(30 + (i / width) * 40)
                g = int(15 + (i / width) * 20)
                b = int(60 + (i / width) * 80)
                for j in range(height):
                    existing = img.getpixel((i, j))
                    img.putpixel((i, j), (r, g, b, 255))

            draw.rectangle([0, 0, width - 1, height - 1], outline=(102, 126, 234), width=2)

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
                outline=(102, 126, 234),
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
            draw.text((text_x, 60), f"Level {member.level}", fill=(102, 126, 234), font=font_medium)
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
                    fill=(102, 126, 234),
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
