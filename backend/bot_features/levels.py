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

            # Load fonts — prefer BOLD faces for a punchier, high-contrast card,
            # falling back to regular then the PIL default.
            def _load_font(size, bold=True):
                names = (
                    ("arialbd.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf",
                     "arial.ttf", "DejaVuSans.ttf")
                    if bold else
                    ("arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf")
                )
                for name in names:
                    try:
                        return ImageFont.truetype(name, size)
                    except Exception:
                        pass
                return ImageFont.load_default()

            font_name      = _load_font(50)
            font_user      = _load_font(26, bold=False)
            font_stats     = _load_font(30)
            font_badge_lbl = _load_font(22)
            font_badge_num = _load_font(96)
            font_bar       = _load_font(24)
            font_initial   = _load_font(86)

            white = (255, 255, 255)
            sub   = (175, 185, 215)
            stat  = (214, 222, 240)
            # A darkened tint of the accent for filled surfaces (disc / badge).
            # `disc` for the avatar; `panel` is a subtler accent-tinted panel for the
            # level badge. Both opaque — PIL's ImageDraw doesn't alpha-blend, so a
            # sub-255 alpha here would render see-through in the saved PNG.
            disc  = tuple(min(255, int(c * 0.55)) for c in accent)
            panel = tuple(min(255, int(color_end[i] * 0.6 + disc[i] * 0.4)) for i in range(3))

            # ── Avatar (left): filled accent disc + bold initial ──
            pad = 36
            avatar_size = 168
            av_cx = pad + avatar_size // 2
            av_cy = height // 2
            draw.ellipse(
                [av_cx - avatar_size // 2, av_cy - avatar_size // 2,
                 av_cx + avatar_size // 2, av_cy + avatar_size // 2],
                fill=(*disc, 255), outline=accent, width=5,
            )
            initial = (member.first_name or member.username or "?")[0].upper()
            draw.text((av_cx, av_cy), initial, fill=white, font=font_initial, anchor="mm")

            # ── Level badge (right): big number that fills the previously empty space ──
            badge_w = badge_h = 176
            badge_x = width - pad - badge_w
            badge_y = (height - badge_h) // 2 - 18
            draw.rounded_rectangle(
                [badge_x, badge_y, badge_x + badge_w, badge_y + badge_h],
                radius=24, fill=(*panel, 255), outline=accent, width=4,
            )
            bcx = badge_x + badge_w // 2
            draw.text((bcx, badge_y + 30), "LEVEL", fill=accent, font=font_badge_lbl, anchor="mm")
            draw.text((bcx, badge_y + badge_h // 2 + 16), str(member.level),
                      fill=white, font=font_badge_num, anchor="mm")

            # ── Text column ──
            tx = pad + avatar_size + 38
            text_right = badge_x - 24  # keep text clear of the badge

            def _fit(text, font, max_w):
                """Ellipsize text to fit max_w pixels."""
                if draw.textlength(text, font=font) <= max_w:
                    return text
                while text and draw.textlength(text + "…", font=font) > max_w:
                    text = text[:-1]
                return (text + "…") if text else text

            first = (member.first_name or "").strip()
            last = (getattr(member, "last_name", None) or "").strip()
            full_name = " ".join(x for x in [first, last] if x) or (member.username or f"User {member.telegram_user_id}")
            draw.text((tx, 58), _fit(full_name, font_name, text_right - tx), fill=white, font=font_name)

            ty = 58 + 62
            if member.username:
                draw.text((tx, ty), _fit(f"@{member.username}", font_user, text_right - tx), fill=sub, font=font_user)
                ty += 46
            else:
                ty += 12

            # Rank + XP on one bold stat row (XP wraps to a second line if cramped).
            rank_txt = f"Rank  #{rank_position} of {total_members}"
            xp_txt = f"XP  {member.xp:,}"
            draw.text((tx, ty + 6), rank_txt, fill=stat, font=font_stats)
            xp_x = tx + draw.textlength(rank_txt, font=font_stats) + 36
            if xp_x + draw.textlength(xp_txt, font=font_stats) <= text_right:
                draw.text((xp_x, ty + 6), xp_txt, fill=stat, font=font_stats)
            else:
                draw.text((tx, ty + 44), xp_txt, fill=stat, font=font_stats)

            # ── XP progress bar (full width, bold) ──
            bar_x = tx
            bar_y = height - 64
            bar_w = width - tx - pad
            bar_h = 34

            current_level_xp = self._xp_for_level(member.level)
            next_level_xp = self._xp_for_level(member.level + 1)
            remaining_xp = member.xp - current_level_xp
            needed_xp = max(1, next_level_xp - current_level_xp)
            progress = min(1.0, max(0.0, remaining_xp / needed_xp))

            draw.rounded_rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], radius=17, fill=(38, 42, 70))
            fill_w = max(bar_h, int(bar_w * progress))
            draw.rounded_rectangle([bar_x, bar_y, bar_x + fill_w, bar_y + bar_h], radius=17, fill=accent)
            draw.text(
                (bar_x + bar_w // 2, bar_y + bar_h // 2),
                f"{max(0, remaining_xp)} / {needed_xp} XP",
                fill=white,
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
