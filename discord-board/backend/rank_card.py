"""Rank-card image generator for Guildizer's /rank command (Pillow).

Renders a Telegizer-style level card: gradient background, circular avatar with
an accent ring, username, level/rank, and an accent XP progress bar. Pure Pillow,
no network. Returns PNG bytes, or None when Pillow is unavailable or rendering
fails — callers fall back to a plain text reply so /rank never hard-fails.
"""
from __future__ import annotations

import io
import logging

log = logging.getLogger("guildizer.rankcard")

W, H = 880, 240
PAD = 32
AV = 160  # avatar diameter

# Common Linux/container font locations (Railway images ship DejaVu). Falls back
# to Pillow's scalable default when none are present.
_FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]


def _hex(value: str, fallback: tuple) -> tuple:
    s = (value or "").lstrip("#")
    if len(s) == 6:
        try:
            return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            pass
    return fallback


def _font(size: int, bold: bool = False):
    from PIL import ImageFont
    for path in _FONT_PATHS:
        try:
            if bold and "Bold" not in path:
                continue
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    # any DejaVu (non-bold) as a second pass
    for path in _FONT_PATHS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size)  # Pillow >= 10.1 scalable default
    except TypeError:
        return ImageFont.load_default()


def render(*, username: str, avatar_bytes: bytes | None, level: int, xp: int,
           rank: int, into_level: int, need_for_level: int, style: dict | None = None) -> bytes | None:
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        log.warning("Pillow not installed; rank card disabled")
        return None
    try:
        style = style or {}
        c_start = _hex(style.get("bg_color_start"), (26, 26, 46))
        c_end = _hex(style.get("bg_color_end"), (22, 33, 62))
        accent = _hex(style.get("accent_color"), (88, 101, 242))

        # vertical gradient background
        base = Image.new("RGB", (W, H), c_start)
        top = Image.new("RGB", (W, H), c_end)
        mask = Image.new("L", (W, H))
        mask.putdata([int(255 * (y / H)) for y in range(H) for _ in range(W)])
        base = Image.composite(top, base, mask)

        card = base.convert("RGBA")
        draw = ImageDraw.Draw(card)

        # avatar (circular) with accent ring
        ax, ay = PAD, (H - AV) // 2
        ring = 6
        draw.ellipse([ax - ring, ay - ring, ax + AV + ring, ay + AV + ring], fill=accent)
        if avatar_bytes:
            try:
                av = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA").resize((AV, AV))
                circle = Image.new("L", (AV, AV), 0)
                ImageDraw.Draw(circle).ellipse([0, 0, AV, AV], fill=255)
                card.paste(av, (ax, ay), circle)
            except Exception:  # noqa: BLE001 — bad/no avatar -> placeholder dot
                draw.ellipse([ax, ay, ax + AV, ay + AV], fill=(60, 65, 90))
        else:
            draw.ellipse([ax, ay, ax + AV, ay + AV], fill=(60, 65, 90))

        tx = ax + AV + 36           # text column x
        white = (255, 255, 255)
        muted = (180, 186, 200)

        # username
        draw.text((tx, ay + 4), (username or "Member")[:24], font=_font(40, bold=True), fill=white)
        # level / rank line
        draw.text((tx, ay + 58),
                  f"LEVEL {level}    RANK #{rank}", font=_font(26, bold=True), fill=accent)

        # XP progress bar
        bar_x0, bar_x1 = tx, W - PAD
        bar_y = ay + AV - 30
        bar_h = 26
        radius = bar_h // 2
        draw.rounded_rectangle([bar_x0, bar_y, bar_x1, bar_y + bar_h], radius=radius,
                               fill=(255, 255, 255, 40))
        need = max(1, need_for_level)
        frac = max(0.02, min(1.0, into_level / need))
        fill_x1 = int(bar_x0 + (bar_x1 - bar_x0) * frac)
        if fill_x1 - bar_x0 >= bar_h:
            draw.rounded_rectangle([bar_x0, bar_y, fill_x1, bar_y + bar_h], radius=radius, fill=accent)
        # xp text above the bar
        draw.text((tx, bar_y - 30), f"{into_level} / {need} XP   ·   {xp} total",
                  font=_font(20), fill=muted)

        out = io.BytesIO()
        card.convert("RGB").save(out, format="PNG")
        out.seek(0)
        return out.read()
    except Exception:  # noqa: BLE001 — never break /rank
        log.exception("rank card render failed")
        return None
