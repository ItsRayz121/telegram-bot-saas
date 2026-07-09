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

            # Light, high-contrast card. Only the accent stays themeable; the
            # legacy dark bg_color_start/end are intentionally ignored — the
            # readable redesign is always a light card. (The Discord/Guildizer
            # rank card is a separate file and is deliberately left untouched.)
            accent = _hex_to_rgb(rank_card_cfg.get("accent_color", "#2196f3"))

            # Logical 600×160 banner, supersampled ×3 so text + rounded corners
            # stay crisp and antialiased after Telegram downscales the photo
            # into the chat bubble (the old 900×360 dark card rendered tiny).
            S = 3
            W, H = 600, 160

            def px(v):
                return int(round(v * S))

            img = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)

            # Load fonts — bold faces where available, falling back to regular
            # then the PIL default.
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

            # All faces bold + slightly larger so the card reads clearly on a
            # phone — the previous thin/regular text was hard to see.
            f_name    = _load_font(px(20))
            f_user    = _load_font(px(14))
            f_rank_l  = _load_font(px(14))
            f_rank_v  = _load_font(px(14))
            f_prog    = _load_font(px(13))
            f_xp      = _load_font(px(12))
            f_pct     = _load_font(px(12))
            f_lvl_lbl = _load_font(px(12))
            f_lvl_num = _load_font(px(38))
            f_avatar  = _load_font(px(24))

            # ── Light palette ──
            ink       = (28, 32, 44)     # primary text
            muted     = (92, 100, 118)   # secondary text — darkened for contrast
            border    = (228, 231, 238)  # card hairline
            track     = (234, 237, 243)  # progress track
            tint      = tuple(int(255 * 0.84 + c * 0.16) for c in accent)  # light accent wash
            accent_dk = tuple(int(c * 0.78) for c in accent)

            # ── Card body: white rounded rect (transparent corners) + hairline ──
            draw.rounded_rectangle(
                [px(1), px(1), W * S - px(1), H * S - px(1)],
                radius=px(14), fill=(255, 255, 255, 255), outline=border, width=max(1, px(1)),
            )

            PAD = 18

            # ── Avatar (left): light accent disc + initials ──
            av_d = 58
            av_x = PAD
            av_cx = av_x + av_d / 2
            av_cy = H / 2
            draw.ellipse(
                [px(av_x), px(av_cy - av_d / 2), px(av_x + av_d), px(av_cy + av_d / 2)],
                fill=(*tint, 255), outline=accent, width=max(1, px(1.5)),
            )
            first = (member.first_name or "").strip()
            last = (getattr(member, "last_name", None) or "").strip()
            initials = ((first[:1] + last[:1]) or (member.username or "?")[:1] or "?").upper()
            draw.text((px(av_cx), px(av_cy)), initials, fill=accent_dk, font=f_avatar, anchor="mm")

            # ── Level chip (right): light tint panel, "LEVEL" + big number ──
            lv_w = 92
            lv_x = W - PAD - lv_w
            lv_cx = lv_x + lv_w / 2
            draw.rounded_rectangle(
                [px(lv_x), px(34), px(lv_x + lv_w), px(H - 34)],
                radius=px(14), fill=(*tint, 255), outline=accent, width=max(1, px(1)),
            )
            draw.text((px(lv_cx), px(52)), "LEVEL", fill=accent_dk, font=f_lvl_lbl, anchor="mm")
            draw.text((px(lv_cx), px(92)), str(member.level), fill=accent, font=f_lvl_num, anchor="mm")

            # ── Text column ──
            tx = av_x + av_d + 18
            text_right = lv_x - 16
            max_w = px(text_right - tx)

            def _fit(text, font, mw):
                """Ellipsize text to fit mw pixels."""
                if draw.textlength(text, font=font) <= mw:
                    return text
                while text and draw.textlength(text + "…", font=font) > mw:
                    text = text[:-1]
                return (text + "…") if text else text

            full_name = " ".join(x for x in [first, last] if x) or (member.username or f"User {member.telegram_user_id}")
            draw.text((px(tx), px(22)), _fit(full_name, f_name, max_w), fill=ink, font=f_name)

            if member.username:
                draw.text((px(tx), px(50)), _fit(f"@{member.username}", f_user, max_w), fill=muted, font=f_user)

            # Rank row — muted label + bold value
            rank_y = 74
            draw.text((px(tx), px(rank_y)), "Rank ", fill=muted, font=f_rank_l)
            rl_w = draw.textlength("Rank ", font=f_rank_l)
            draw.text((px(tx) + rl_w, px(rank_y)), f"#{rank_position} of {total_members}",
                      fill=ink, font=f_rank_v)

            # ── Progress to next level ──
            current_level_xp = self._xp_for_level(member.level)
            next_level_xp = self._xp_for_level(member.level + 1)
            remaining_xp = max(0, member.xp - current_level_xp)
            needed_xp = max(1, next_level_xp - current_level_xp)
            progress = min(1.0, max(0.0, remaining_xp / needed_xp))

            label_y = 100
            draw.text((px(tx), px(label_y)), f"Progress to Level {member.level + 1}",
                      fill=muted, font=f_prog)
            draw.text((px(text_right), px(label_y)), f"{int(progress * 100)}%",
                      fill=accent_dk, font=f_pct, anchor="ra")

            bar_x0, bar_x1 = tx, text_right
            bar_y0, bar_y1 = 120, 138
            draw.rounded_rectangle(
                [px(bar_x0), px(bar_y0), px(bar_x1), px(bar_y1)], radius=px(9), fill=track,
            )
            fill_w = int((bar_x1 - bar_x0) * progress)
            if fill_w >= (bar_y1 - bar_y0):  # only draw a rounded fill once it's wider than its radius
                draw.rounded_rectangle(
                    [px(bar_x0), px(bar_y0), px(bar_x0 + fill_w), px(bar_y1)], radius=px(9), fill=accent,
                )
            # XP centered on the bar; flip to white once the fill reaches the middle
            xp_color = (255, 255, 255) if progress >= 0.5 else ink
            draw.text(
                (px((bar_x0 + bar_x1) / 2), px((bar_y0 + bar_y1) / 2)),
                f"{remaining_xp} / {needed_xp} XP", fill=xp_color, font=f_xp, anchor="mm",
            )

            # Downscale for crisp antialiasing
            img = img.resize((W, H), Image.LANCZOS)

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
