"""Telegram /rank card: one deterministic 960x640 template (Pillow).

Designed to be read while the *whole* image is shown ~300px wide in the chat
bubble (scale ~0.31), so every text element is >= 42px at export size.

The image and the caption are both built from one RankSnapshot, and the
snapshot's `cache_key` covers every displayed value, so a cached render can
never show stale data.
"""
import hashlib
import io
import logging
import os
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

W, H = 960, 640
SS = 2  # supersample factor; downscaled with LANCZOS for clean edges
MARGIN = 56

NAVY = (11, 27, 61)
MUTED = (71, 85, 115)  # 7.2:1 on white
TRACK = (226, 232, 244)
DEFAULT_ACCENT = (37, 99, 235)

_FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "fonts")
# Only bundled fonts are used, so the card renders identically on any host
# (Railway's image has no system fonts we can rely on).
_FONTS = tuple(os.path.join(_FONT_DIR, f) for f in ("NotoSans-Bold.ttf", "NotoSansArabic-Bold.ttf"))


# ── Snapshot ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RankSnapshot:
    name: str              # what is drawn on the image (always renderable)
    caption_name: str      # full original name, used only in the caption
    rank: int
    total: int
    level: int
    xp: int
    level_floor_xp: int
    level_ceil_xp: int
    next_level: int
    xp_remaining: int      # XP still needed for next level
    xp_into_level: int
    xp_span: int           # size of the current level
    progress: float        # 0..1 inside the current level
    max_level: bool
    accent: tuple
    avatar_key: str        # file_unique_id, "" when there is no avatar

    @property
    def cache_key(self) -> str:
        raw = repr((self.name, self.rank, self.total, self.level, self.xp,
                    self.level_floor_xp, self.level_ceil_xp, self.max_level,
                    self.accent, self.avatar_key))
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    @property
    def caption(self) -> str:
        name = self.caption_name if len(self.caption_name) <= 120 else self.caption_name[:119] + "…"
        second = ("Max level reached" if self.max_level
                  else f"{self.xp_remaining:,} XP to Level {self.next_level}")
        return f"{name} · Rank #{self.rank} · Level {self.level}\n{second}"


def _hex_to_rgb(value, default=DEFAULT_ACCENT):
    try:
        v = str(value).lstrip("#")
        return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return default


def xp_threshold(level: int) -> int:
    """Total XP needed to reach `level`. Same curve as DatabaseManager._calculate_level."""
    total, need = 0, 100
    for _ in range(max(0, level - 1)):
        total += need
        need = int(need * 1.5)
    return total


def build_snapshot(member, rank: int, total: int, name: str, accent=None,
                   avatar_key: str = "", max_level: Optional[int] = None,
                   username: str = "", threshold=xp_threshold) -> RankSnapshot:
    """`threshold(level)` = total XP needed to reach `level`; each bot passes its own rule."""
    xp = max(0, int(member.xp or 0))
    level = max(1, int(member.level or 1))
    floor_xp = threshold(level)
    is_max = max_level is not None and level >= max_level
    ceil_xp = threshold(level + 1)
    span = max(1, ceil_xp - floor_xp)
    into = min(span, max(0, xp - floor_xp))
    progress = 1.0 if is_max else min(1.0, into / span)
    return RankSnapshot(
        name=image_name(name, username), caption_name=(name or "").strip() or "Member",
        rank=max(1, int(rank)), total=max(int(total), int(rank), 1),
        level=level, xp=xp, level_floor_xp=floor_xp, level_ceil_xp=ceil_xp,
        next_level=level + 1, xp_remaining=max(0, ceil_xp - xp),
        xp_into_level=into, xp_span=span, progress=progress, max_level=is_max,
        accent=tuple(accent) if accent else DEFAULT_ACCENT, avatar_key=avatar_key or "",
    )


def accent_from_settings(settings) -> tuple:
    cfg = ((settings or {}).get("levels", {}) or {}).get("rank_card", {}) or {}
    return _hex_to_rgb(cfg.get("accent_color", "#2563eb"))


# ── Fonts (loaded once) ─────────────────────────────────────────────────────

_font_lock = threading.Lock()
_font_cache = {}
_glyph_cache = {}


def _font(path, size):
    from PIL import ImageFont
    key = (path, size)
    f = _font_cache.get(key)
    if f is None:
        with _font_lock:
            f = _font_cache.get(key)
            if f is None:
                f = ImageFont.truetype(path, size)
                _font_cache[key] = f
    return f


def _font_paths():
    paths = [p for p in _FONTS if os.path.exists(p)]
    if len(paths) != len(_FONTS):
        raise RuntimeError("bundled rank-card fonts missing from backend/assets/fonts")
    return paths


def _glyph_bytes(path, size, ch):
    from PIL import Image, ImageDraw
    im = Image.new("L", (size * 2, size * 2), 0)
    ImageDraw.Draw(im).text((4, 4), ch, font=_font(path, size), fill=255)
    return im.tobytes()


def _has_glyph(path, size, ch) -> bool:
    """False when the font would draw its .notdef box (or nothing) for `ch`."""
    key = (path, ch)
    hit = _glyph_cache.get(key)
    if hit is None:
        try:
            probe = 40  # coverage doesn't depend on size; probe small for speed
            got = _glyph_bytes(path, probe, ch)
            hit = (any(got)
                   and got != _glyph_bytes(path, probe, "￿")
                   and got != _glyph_bytes(path, probe, "􏿽"))
        except Exception:
            hit = False
        _glyph_cache[key] = hit
    return hit


def _covered(ch) -> bool:
    return ch.isspace() or any(_has_glyph(p, 40, ch) for p in _font_paths())


def _is_rtl_char(ch) -> bool:
    import unicodedata
    return unicodedata.bidirectional(ch) in ("R", "AL")


def _display(text: str) -> str:
    """Logical text -> visual order with Arabic-script letters joined (shaped).
    Pure Python (arabic-reshaper + python-bidi): needs no libraqm/fribidi on the host."""
    if not any(_is_rtl_char(c) for c in text):
        return text
    import arabic_reshaper
    from bidi.algorithm import get_display
    return get_display(arabic_reshaper.reshape(text))


def _clean_name(text: str) -> str:
    """Drop emoji/pictographs and invisible format chars (not letters), tidy spaces."""
    import unicodedata
    text = unicodedata.normalize("NFC", text or "")
    out = []
    for ch in text:
        cat = unicodedata.category(ch)
        if ch == "‌":          # ZWNJ is meaningful in Persian/Urdu
            out.append(ch)
        elif cat in ("Cf", "Cc", "Cs", "Co", "Cn", "So", "Sk") or ch == "️":
            continue
        else:
            out.append(ch)
    return " ".join("".join(out).split())


def _renderable(text: str) -> bool:
    return bool(text) and any(c.isalnum() for c in text) and all(_covered(c) for c in text)


def image_name(name: str, username: str = "") -> str:
    """The name drawn on the card. Real name if every letter can be rendered
    correctly with the bundled fonts, else @username, else "Member"."""
    for cand in (_clean_name(name), _clean_name(f"@{username}") if username else ""):
        if _renderable(cand):
            return cand
    return "Member"


def _runs(text, size):
    """Split display text into (font, chunk) runs, first bundled font with the glyph."""
    paths = _font_paths()
    out = []
    for ch in text:
        chosen = out[-1][0] if (ch.isspace() and out) else paths[0]
        if not ch.isspace():
            chosen = next((p for p in paths if _has_glyph(p, size, ch)), paths[0])
        if out and out[-1][0] == chosen:
            out[-1][1] += ch
        else:
            out.append([chosen, ch])
    return [(_font(p, size), t) for p, t in out]


def _width(draw, text, size):
    return sum(draw.textlength(t, font=f) for f, t in _runs(text, size))


def _draw_text(draw, xy, text, size, fill, anchor="l"):
    """Draw display-ready text with per-glyph font choice. anchor: l/r horizontal, baseline vertical."""
    x, y = xy
    if anchor == "r":
        x -= _width(draw, text, size)
    for f, t in _runs(text, size):
        draw.text((x, y), t, font=f, fill=fill, anchor="ls")
        x += draw.textlength(t, font=f)


def _ellipsize(draw, text, size, max_w):
    """Truncate the LOGICAL text (so RTL cuts the right end), return display text."""
    if _width(draw, _display(text), size) <= max_w:
        return _display(text)
    t = text.rstrip()
    while t and _width(draw, _display(t.rstrip() + "…"), size) > max_w:
        t = t[:-1]
    return _display(t.rstrip() + "…") if t else "…"


def _fit_size(draw, text, start, minimum, max_w):
    """Largest size in [minimum, start] that fits; only used for extreme numbers."""
    size = start
    while size > minimum and _width(draw, text, size) > max_w:
        size -= 4
    return size


def _compact(n: int) -> str:
    for div, suf in ((10**12, "T"), (10**9, "B"), (10**6, "M"), (10**3, "K")):
        if n >= div:
            if n >= 10**15:  # beyond T: scientific, e.g. 1.7e20
                break
            return f"{n / div:.1f}".rstrip("0").rstrip(".") + suf
    if n >= 10**15:
        return f"{n:.1e}".replace("e+", "e")
    return str(n)


# ── Avatar helpers ──────────────────────────────────────────────────────────

def _initials(name: str) -> str:
    words = [w for w in name.replace("@", " ").split() if w]
    if not words:
        return "?"
    first, last = words[0][:1], words[-1][:1]
    return _display((first if len(words) == 1 else first + last).upper())


def _circle_avatar(avatar_bytes, d):
    from PIL import Image, ImageDraw, ImageOps
    im = Image.open(io.BytesIO(avatar_bytes)).convert("RGB")
    im = ImageOps.fit(im, (d, d), Image.LANCZOS)
    mask = Image.new("L", (d, d), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, d - 1, d - 1], fill=255)
    out = Image.new("RGBA", (d, d), (0, 0, 0, 0))
    out.paste(im, (0, 0), mask)
    return out


# ── Render ──────────────────────────────────────────────────────────────────

def render_png(s: RankSnapshot, avatar_bytes: Optional[bytes] = None) -> bytes:
    from PIL import Image, ImageDraw

    k = SS
    img = Image.new("RGB", (W * k, H * k), (255, 255, 255))
    d = ImageDraw.Draw(img)
    accent = s.accent
    tint = tuple(int(255 * 0.88 + c * 0.12) for c in accent)

    def S(v):
        return int(round(v * k))

    def text(x, y, t, size, fill, anchor="l"):
        _draw_text(d, (S(x), S(y)), t, S(size), fill, anchor)

    def width(t, size):
        return _width(d, t, S(size)) / k

    # Accent stripe along the top edge (the single accent colour).
    d.rectangle([0, 0, S(W), S(12)], fill=accent)

    # ── Top: avatar + name ──
    av = 112
    av_x, av_y = MARGIN, 52
    drawn = False
    if avatar_bytes:
        try:
            circ = _circle_avatar(avatar_bytes, S(av))
            img.paste(circ, (S(av_x), S(av_y)), circ)
            drawn = True
        except Exception as e:
            logger.warning("rank card avatar decode failed: %s", e)
    if not drawn:
        d.ellipse([S(av_x), S(av_y), S(av_x + av), S(av_y + av)], fill=tint, outline=accent, width=S(3))
        ini = _initials(s.name)
        isz = 52
        text(av_x + av / 2 - width(ini, isz) / 2, av_y + av / 2 + isz * 0.36, ini, isz, accent)

    name_x = av_x + av + 32
    name_size = 64
    name = _ellipsize(d, s.name, S(name_size), S(W - MARGIN - name_x))
    text(name_x, av_y + av / 2 + name_size * 0.36, name, name_size, NAVY)

    # ── Middle: two columns ──
    label_size, num_size, sub_size = 44, 136, 44
    label_y, num_y = 252, 410
    level_txt = str(s.level)
    level_w = width(level_txt, num_size)
    col2_w = max(236, min(380, level_w + 8))
    col2_x = W - MARGIN - col2_w
    col1_w = col2_x - 40 - MARGIN

    text(MARGIN, label_y, "RANK", label_size, MUTED)
    rank_txt = f"#{s.rank}"
    total_txt = f"of {s.total}"
    gap = 20
    if width(rank_txt, num_size) + gap + width(total_txt, sub_size) > col1_w:
        total_txt = f"of {_compact(s.total)}"
    avail = col1_w - gap - width(total_txt, sub_size)
    if width(rank_txt, 88) > avail:       # still too wide at the minimum size: drop "of N"
        total_txt, avail = "", col1_w
    if width(rank_txt, 88) > avail:       # absurd rank: compact it too
        rank_txt = f"#{_compact(s.rank)}"
    rsize = _fit_size(d, rank_txt, S(num_size), S(88), S(avail)) / k
    text(MARGIN, num_y, rank_txt, rsize, NAVY)
    if total_txt:
        text(MARGIN + width(rank_txt, rsize) + gap, num_y, total_txt, sub_size, MUTED)

    # Divider + level column
    d.rectangle([S(col2_x - 20 - 2), S(label_y - 40), S(col2_x - 20), S(num_y + 12)], fill=TRACK)
    text(col2_x, label_y, "LEVEL", label_size, MUTED)
    lsize = _fit_size(d, level_txt, S(num_size), S(88), S(col2_w)) / k
    text(col2_x, num_y, level_txt, lsize, accent)

    # ── Bottom: progress text ABOVE the bar, then the bar ──
    bx0, bx1 = MARGIN, W - MARGIN
    prog_y = 502
    if s.max_level:
        left, right = "Max level reached", ""
    else:
        left = f"Next: Level {s.next_level}"
        right = f"{s.xp_into_level:,} / {s.xp_span:,} XP"
        room = bx1 - bx0 - 48
        if width(left, sub_size) + width(right, sub_size) > room:
            left = f"Level {s.next_level}"
        if width(left, sub_size) + width(right, sub_size) > room:
            right = f"{_compact(s.xp_into_level)} / {_compact(s.xp_span)} XP"
        if width(left, sub_size) + width(right, sub_size) > room:
            right = f"{int(s.progress * 100)}%"
    text(bx0, prog_y, left, sub_size, NAVY)
    if right:
        text(bx1, prog_y, right, sub_size, MUTED, anchor="r")

    by0, by1 = 530, 576
    r = (by1 - by0) / 2
    d.rounded_rectangle([S(bx0), S(by0), S(bx1), S(by1)], radius=S(r), fill=TRACK)
    fill_w = (bx1 - bx0) * s.progress
    if s.progress > 0:
        # Never narrower than the bar height so the rounded end stays a clean pill.
        fill_w = max(fill_w, by1 - by0)
        d.rounded_rectangle([S(bx0), S(by0), S(bx0 + fill_w), S(by1)], radius=S(r), fill=accent)

    img = img.resize((W, H), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ── Render cache ────────────────────────────────────────────────────────────

class RenderCache:
    """Small LRU: cache_key -> png bytes. Keys hash every displayed value, so a
    changed rank/XP/name/avatar is simply a different key (no manual invalidation)."""

    def __init__(self, max_items=256):
        self._d = OrderedDict()
        self._max = max_items
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            v = self._d.get(key)
            if v is not None:
                self._d.move_to_end(key)
            return v

    def put(self, key, png):
        with self._lock:
            self._d[key] = png
            self._d.move_to_end(key)
            while len(self._d) > self._max:
                self._d.popitem(last=False)


_cache = RenderCache()
# Renders share a process with the web service; cap concurrent CPU-heavy renders.
_render_slots = threading.BoundedSemaphore(2)


def render_cached(s: RankSnapshot, avatar_bytes: Optional[bytes] = None) -> bytes:
    png = _cache.get(s.cache_key)
    if png is None:
        with _render_slots:
            png = _cache.get(s.cache_key) or render_png(s, avatar_bytes)
        _cache.put(s.cache_key, png)
    return png


# ── Telegram helpers ────────────────────────────────────────────────────────

_AVATAR_TTL = 3600
_avatar_cache = OrderedDict()  # user_id -> (fetched_at, unique_id, bytes|None)


async def fetch_avatar(bot, user_id, timeout=3.0):
    """Return (avatar_key, jpeg_bytes) or ("", None). Cached for an hour (also
    negative results) so /rank doesn't pay two extra Telegram round-trips each time."""
    import asyncio
    import time
    now = time.monotonic()
    hit = _avatar_cache.get(user_id)
    if hit and now - hit[0] < _AVATAR_TTL:
        return (hit[1], hit[2])
    key, data = "", None
    try:
        async def _go():
            photos = await bot.get_user_profile_photos(user_id, limit=1)
            if not photos or not photos.photos:
                return "", None
            sizes = photos.photos[0]
            # smallest size that is still >= 224px (rendered at 112px, 2x supersampled)
            pick = next((p for p in sizes if (p.width or 0) >= 224), sizes[-1])
            f = await bot.get_file(pick.file_id)
            return pick.file_unique_id, bytes(await f.download_as_bytearray())
        key, data = await asyncio.wait_for(_go(), timeout)
    except Exception as e:  # privacy-restricted, no photo, network: fall back to initials
        logger.debug("rank card avatar unavailable for %s: %s", user_id, e)
    _avatar_cache[user_id] = (now, key, data)
    while len(_avatar_cache) > 512:
        _avatar_cache.popitem(last=False)
    return key, data
