"""Unified site-wide blog (Telegizer + Guildizer share ONE blog).

Why one blog: all SEO authority should land on a single domain (telegizer.com)
instead of being split across products. There is no per-product separation here.

Two surfaces:
  • PUBLIC pages are SERVER-RENDERED HTML (``/blog`` index + ``/blog/<slug>``) so
    Google, Bing and AI answer-engines get the full article text + meta + schema
    without running JavaScript. Vercel rewrites /blog* to this backend.
  • ADMIN writes posts from the SPA via the JSON API under ``/api/admin/blog``.

Images are uploaded to ``/api/admin/blog/media`` (Pillow re-encodes to WebP, caps
size) and stored in Postgres, served from ``/blog/media/<id>`` — no external
object store required. Video is embedded (YouTube / Vimeo / Google Drive) rather
than hosted: the editor stores a placeholder div which this module renders into a
responsive iframe for whitelisted hosts only (safe, no raw iframe is stored).
"""
from __future__ import annotations

import io
import os
import re
import html as _html
from datetime import datetime
from urllib.parse import urlparse, parse_qs, quote

from flask import Blueprint, request, jsonify, Response, abort
from flask_jwt_extended import get_jwt_identity
from sqlalchemy import or_, and_

from ..models import db, BlogPost, BlogMedia, BlogSubscriber
from .admin import admin_required

PER_PAGE = 9  # posts per page on listings

try:
    import bleach
    _HAS_BLEACH = True
except Exception:  # pragma: no cover - bleach is in requirements for prod
    _HAS_BLEACH = False

try:
    from PIL import Image
    _HAS_PIL = True
except Exception:  # pragma: no cover
    _HAS_PIL = False

blog_bp = Blueprint("blog", __name__)

SITE_URL = (os.environ.get("SITE_URL") or "https://telegizer.com").rstrip("/")
BRAND = "Telegizer"

# ── HTML sanitisation whitelist ────────────────────────────────────────────────
ALLOWED_TAGS = [
    "p", "br", "hr", "h2", "h3", "h4", "strong", "b", "em", "i", "u", "s",
    "ul", "ol", "li", "blockquote", "a", "img", "figure", "figcaption",
    "pre", "code", "span", "div", "table", "thead", "tbody", "tr", "th", "td",
]
ALLOWED_ATTRS = {
    "a": ["href", "title", "target", "rel"],
    "img": ["src", "alt", "title", "width", "height", "loading"],
    "div": ["class", "data-embed"],
    "span": ["class"],
    "code": ["class"],
    "th": ["colspan", "rowspan"],
    "td": ["colspan", "rowspan"],
}
ALLOWED_PROTOCOLS = ["http", "https", "mailto", "data"]

# Hosts we will turn a placeholder embed into a real iframe for.
_EMBED_HOSTS = ("youtube.com", "youtu.be", "www.youtube.com", "vimeo.com",
                "player.vimeo.com", "drive.google.com", "t.me", "telegram.me",
                "www.t.me")


def _slugify(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text).strip("-")
    return text[:200] or "post"


def _unique_slug(base: str, exclude_id: int | None = None) -> str:
    slug = _slugify(base)
    n = 2
    while True:
        q = BlogPost.query.filter_by(slug=slug)
        if exclude_id:
            q = q.filter(BlogPost.id != exclude_id)
        if not q.first():
            return slug
        slug = f"{_slugify(base)}-{n}"
        n += 1


def _strip_tags(html_str: str) -> str:
    return re.sub(r"<[^>]+>", " ", html_str or "")


def _reading_minutes(html_str: str) -> int:
    words = len(re.findall(r"\w+", _strip_tags(html_str)))
    return max(1, round(words / 200))


def _auto_excerpt(html_str: str, limit: int = 160) -> str:
    text = re.sub(r"\s+", " ", _strip_tags(html_str)).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


def _sanitize(html_str: str) -> str:
    html_str = html_str or ""
    if _HAS_BLEACH:
        return bleach.clean(html_str, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS,
                            protocols=ALLOWED_PROTOCOLS, strip=True)
    # Fallback: strip <script>/<style> at minimum if bleach is unavailable.
    return re.sub(r"<\s*(script|style|iframe)[^>]*>.*?<\s*/\s*\1\s*>", "",
                  html_str, flags=re.I | re.S)


def _embed_iframe(url: str) -> str | None:
    """Return responsive-iframe HTML for a whitelisted video URL, else None."""
    try:
        p = urlparse(url)
    except Exception:
        return None
    host = (p.netloc or "").lower()
    if host not in _EMBED_HOSTS:
        return None
    src = None
    if "youtu" in host:
        vid = None
        if host == "youtu.be":
            vid = p.path.lstrip("/")
        else:
            vid = (parse_qs(p.query).get("v") or [None])[0]
            if not vid and "/embed/" in p.path:
                vid = p.path.split("/embed/")[-1]
        if vid:
            src = f"https://www.youtube-nocookie.com/embed/{_html.escape(vid)}"
    elif "vimeo" in host:
        vid = re.sub(r"\D", "", p.path)
        if vid:
            src = f"https://player.vimeo.com/video/{vid}"
    elif "drive.google.com" in host:
        m = re.search(r"/d/([^/]+)", p.path)
        if m:
            src = f"https://drive.google.com/file/d/{_html.escape(m.group(1))}/preview"
    elif host in ("t.me", "telegram.me", "www.t.me"):
        # t.me/<channel>/<id> (or /s/<channel>/<id>) → embeddable post iframe.
        # No JS needed; Telegram serves an iframe-ready page at ?embed=1.
        parts = [seg for seg in p.path.split("/") if seg]
        if parts and parts[0] == "s":
            parts = parts[1:]
        if len(parts) >= 2 and parts[1].isdigit():
            ch, mid = _html.escape(parts[0]), _html.escape(parts[1])
            # scrolling="auto" (not "no"): our CSP blocks Telegram's resizer JS,
            # so the iframe stays at the fixed CSS height. With "no", a post taller
            # than that gets clipped and is unreachable; "auto" lets readers scroll
            # to the rest. Short posts show no scrollbar, so there's no regression.
            return ('<div class="tg-post"><iframe '
                    f'src="https://t.me/{ch}/{mid}?embed=1" '
                    'frameborder="0" scrolling="auto"></iframe></div>')
        return None
    if not src:
        return None
    return (f'<div class="tg-video"><iframe src="{src}" loading="lazy" '
            f'allow="accelerometer; autoplay; clipboard-write; encrypted-media; '
            f'gyroscope; picture-in-picture" allowfullscreen></iframe></div>')


def _render_embeds(html_str: str) -> str:
    """Replace stored embed placeholders with safe responsive iframes."""
    def repl(m):
        url = _html.unescape(m.group(1))
        iframe = _embed_iframe(url)
        if iframe:
            return iframe
        # Unrecognised host → a safe clickable link instead of vanishing.
        # Only http(s) links become anchors (never javascript:/data: etc.).
        try:
            scheme = urlparse(url).scheme.lower()
        except Exception:
            scheme = ""
        if scheme not in ("http", "https"):
            return ""
        safe = _html.escape(url, quote=True)
        return (f'<p class="video-link"><a href="{safe}" target="_blank" '
                f'rel="noopener">▶ Watch the video</a></p>')
    return re.sub(
        r'<div[^>]*class="tg-embed"[^>]*data-embed="([^"]+)"[^>]*>.*?</div>',
        repl, html_str or "", flags=re.I | re.S)


# ── Conversion chrome: social icons, table of contents, sidebar widgets ─────────
# Inline SVGs (markup, not script) — allowed by the blog CSP. Brand handles are
# the real ones used elsewhere in the app (see frontend/src/config/support.js).
_SVG_X = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18.244 2.25h3.308'
          'l-7.227 8.26 8.502 11.24h-6.65l-5.21-6.817L4.99 21.75H1.68l7.73-8.835'
          'L1.254 2.25H8.08l4.71 6.231zm-1.16 17.52h1.833L7.084 4.126H5.117z"/></svg>')
_SVG_TG = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M11.944 0A12 12 0 0 0 0 12'
           'a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224'
           'c.1-.002.321.023.464.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502'
           '-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124'
           '-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15'
           '-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.139-5.061 3.345-.479.329-.913.489-1.302.481'
           '-.428-.009-1.252-.242-1.865-.442-.751-.244-1.349-.374-1.297-.789.027-.216.325-.437.893-.663'
           '3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/></svg>')
_SVG_DISCORD = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20.317 4.369a19.79 19.79 0 0 0'
                '-4.885-1.515.074.074 0 0 0-.079.037c-.211.375-.444.864-.608 1.25a18.27 18.27 0 0 0'
                '-5.487 0 12.6 12.6 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.74 19.74 0 0 0 3.677 4.37'
                'a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0'
                ' 5.993 3.03.078.078 0 0 0 .084-.028c.462-.63.874-1.295 1.226-1.994a.076.076 0 0 0-.041-.106'
                ' 13.1 13.1 0 0 1-1.872-.892.077.077 0 0 1-.008-.128c.126-.094.252-.192.372-.291a.074.074 0 0 1'
                ' .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.009c.12.099.246.198.373.292'
                'a.077.077 0 0 1-.006.127 12.3 12.3 0 0 1-1.873.891.077.077 0 0 0-.041.107c.36.698.772 1.362'
                ' 1.225 1.993a.076.076 0 0 0 .084.028 19.84 19.84 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054'
                'c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03zM8.02 15.331c-1.183 0-2.157-1.085'
                '-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418'
                '-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0'
                ' 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z"/></svg>')


def _social_icons():
    links = (
        ("https://x.com/TelegizerApp", "X", _SVG_X),
        ("https://t.me/telegizer", "Telegram", _SVG_TG),
        (f"{SITE_URL}/guildizer-landing", "Discord", _SVG_DISCORD),
    )
    return "".join(
        f'<a href="{u}" target="_blank" rel="noopener" aria-label="{lbl}" title="{lbl}">{svg}</a>'
        for u, lbl, svg in links)


def _add_toc(html_str):
    """Inject ids into H2/H3 headings (at render time only) and build a NESTED
    table of contents. Returns (html_with_ids, sections) where sections is
    [(h2_id, h2_text, [(h3_id, h3_text), …]), …]. H3s nest under the H2 above
    them so the TOC can show a collapsible dropdown per section."""
    sections, used = [], set()

    def uid(text):
        base = _slugify(text) or "section"
        hid, n = base, 2
        while hid in used:
            hid = f"{base}-{n}"; n += 1
        used.add(hid)
        return hid

    def repl(m):
        tag = m.group(1).lower()           # 'h2' | 'h3'
        attrs, inner = m.group(2), m.group(3)
        # Strip tags AND decode entities (e.g. &nbsp;) so the TOC label is clean.
        text = _html.unescape(re.sub(r"<[^>]+>", "", inner)).strip()
        if not text:
            return m.group(0)
        hid = uid(text)
        if tag == "h2" or not sections:
            sections.append((hid, text, []))
        else:
            sections[-1][2].append((hid, text))
        return f'<{tag} id="{hid}"{attrs}>{inner}</{tag}>'

    out = re.sub(r"<(h2|h3)([^>]*)>(.*?)</\1>", repl, html_str or "", flags=re.I | re.S)
    return out, sections


def _toc_widget(sections):
    """Numbered, nested 'On this page' list. Sections with H3 children get a
    pure-CSS collapsible dropdown (hidden-checkbox + label — no JS, CSP-safe)."""
    total = sum(1 + len(ch) for _, _, ch in sections)
    if total < 2:   # not worth a TOC for a single heading
        return ""
    lis = []
    for i, (hid, text, children) in enumerate(sections, 1):
        num = f'<span class="toc-n">{i}</span>'
        link = f'<a href="#{_html.escape(hid, quote=True)}">{_html.escape(text)}</a>'
        if children:
            cid_html = "".join(
                f'<li><a href="#{_html.escape(c0, quote=True)}">{_html.escape(c1)}</a></li>'
                for c0, c1 in children)
            lis.append(
                f'<li class="toc-item has-sub">'
                f'<input class="toc-toggle" id="toc-{i}" type="checkbox" checked hidden>'
                f'<div class="toc-row">{num}{link}'
                f'<label class="toc-caret" for="toc-{i}" aria-label="Toggle subsections"></label></div>'
                f'<ul class="toc-sub">{cid_html}</ul></li>')
        else:
            lis.append(f'<li class="toc-item"><div class="toc-row">{num}{link}</div></li>')
    return (f'<div class="widget toc"><h3>On this page</h3>'
            f'<ol class="toc-list">{"".join(lis)}</ol></div>')


def _search_form(klass="widget search", with_heading=True):
    fields = ('<input type="search" name="q" placeholder="Search articles…" '
              'aria-label="Search articles"><button type="submit">Search</button>')
    if klass == "hero-search":
        # The <form> itself is the flex row (no wrapping div).
        return (f'<form class="hero-search" action="/blog/search" method="get" '
                f'role="search">{fields}</form>')
    head = "<h3>Search</h3>" if with_heading else ""
    return (f'<div class="{klass}">{head}'
            f'<form action="/blog/search" method="get" role="search">{fields}</form></div>')


def _newsletter_form(source="footer"):
    return (f'<div class="widget newsletter"><h3>Growth tips in your inbox</h3>'
            '<p>Join the newsletter for Telegram &amp; Discord community guides. No spam, unsubscribe anytime.</p>'
            '<form action="/blog/subscribe" method="post">'
            '<input type="email" name="email" required placeholder="you@email.com" aria-label="Email address">'
            f'<input type="hidden" name="source" value="{_html.escape(source, quote=True)}">'
            '<button type="submit">Subscribe</button></form></div>')


def _article_sidebar(post, toc_items):
    cta = (f'<div class="widget cta-card"><h3>Run your community on autopilot</h3>'
           f'<p>{BRAND} moderates, engages and grows your Telegram &amp; Discord groups 24/7 — free to start.</p>'
           f'<a class="cta" href="{SITE_URL}/register">Start free</a></div>')
    recents = (BlogPost.query.filter(_live_filter(), BlogPost.id != post.id)
               .order_by(BlogPost.published_at.desc()).limit(5).all())
    recent = ""
    if recents:
        lis = "".join(
            f'<li><a href="{SITE_URL}/blog/{p.slug}">{_html.escape(p.title)}</a>'
            f'<span>{_html.escape(p.category or "Article")} · {_fmt_date(p.published_at)}</span></li>'
            for p in recents)
        recent = f'<div class="widget recent"><h3>Recent posts</h3><ul>{lis}</ul></div>'
    # Order: CTA → Search (above the TOC, per request) → On-this-page → Recent → Newsletter.
    return (cta + _search_form() + _toc_widget(toc_items)
            + recent + _newsletter_form(source="sidebar"))


# ════════════════════════════ ADMIN JSON API ═══════════════════════════════════
def _current_user_id():
    try:
        return int(get_jwt_identity())
    except Exception:
        return None


@blog_bp.get("/api/admin/blog/posts")
@admin_required
def admin_list_posts():
    status = request.args.get("status")
    q = BlogPost.query
    if status in ("draft", "published"):
        q = q.filter(BlogPost.status == status)
    posts = q.order_by(BlogPost.updated_at.desc()).all()
    return jsonify(posts=[p.to_dict() for p in posts])


@blog_bp.get("/api/admin/blog/posts/<int:post_id>")
@admin_required
def admin_get_post(post_id):
    post = db.session.get(BlogPost, post_id)
    if not post:
        return jsonify(error="not_found"), 404
    return jsonify(post=post.to_dict(full=True))


def _apply_post_fields(post: BlogPost, body: dict):
    if "title" in body:
        post.title = (body["title"] or "Untitled").strip()[:255]
    if "body_html" in body:
        post.body_html = _sanitize(body["body_html"])
    if "excerpt" in body:
        post.excerpt = (body["excerpt"] or "").strip()[:320] or None
    if "cover_image_url" in body:
        post.cover_image_url = (body["cover_image_url"] or "").strip()[:500] or None
    if "author_name" in body:
        post.author_name = (body["author_name"] or "Telegizer Team").strip()[:120]
    if "category" in body:
        post.category = (body["category"] or "").strip()[:80] or None
    if "tags" in body and isinstance(body["tags"], list):
        post.tags = [str(t).strip()[:40] for t in body["tags"] if str(t).strip()][:12]
    if "focus_keyword" in body:
        post.focus_keyword = (body["focus_keyword"] or "").strip()[:120] or None
    if "meta_title" in body:
        post.meta_title = (body["meta_title"] or "").strip()[:255] or None
    if "meta_description" in body:
        post.meta_description = (body["meta_description"] or "").strip()[:320] or None
    if "og_image_url" in body:
        post.og_image_url = (body["og_image_url"] or "").strip()[:500] or None
    if "canonical_url" in body:
        post.canonical_url = (body["canonical_url"] or "").strip()[:500] or None
    if "noindex" in body:
        post.noindex = bool(body["noindex"])
    # Derived fields
    if not post.excerpt:
        post.excerpt = _auto_excerpt(post.body_html)
    post.reading_minutes = _reading_minutes(post.body_html)


def _parse_iso(s):
    """Parse an ISO datetime (accepts trailing Z) into naive UTC, or None."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def _apply_status(post: BlogPost, body: dict):
    """Apply draft / published / scheduled with the right published_at.

    'scheduled' with a future date keeps the post hidden until that time (the
    public queries reveal it automatically — no cron needed). A missing/past
    date just publishes now."""
    if body.get("status") in ("draft", "published", "scheduled"):
        post.status = body["status"]
    now = datetime.utcnow()
    if post.status == "scheduled":
        dt = _parse_iso(body.get("published_at"))
        if dt and dt > now:
            post.published_at = dt
        else:
            post.status = "published"
            post.published_at = now
    elif post.status == "published":
        # A published post must not carry a future date (e.g. left over from a
        # prior schedule) — that would show a future byline and sort wrong.
        if not post.published_at or post.published_at > now:
            post.published_at = now
    if body.get("republish"):
        post.published_at = now


@blog_bp.post("/api/admin/blog/posts")
@admin_required
def admin_create_post():
    body = request.get_json(silent=True) or {}
    title = (body.get("title") or "Untitled").strip()[:255]
    slug = _unique_slug(body.get("slug") or title)
    post = BlogPost(slug=slug, title=title, body_html="", status="draft",
                    author_id=_current_user_id())
    _apply_post_fields(post, body)
    _apply_status(post, body)   # publish / schedule on create
    db.session.add(post)
    db.session.commit()
    return jsonify(post=post.to_dict(full=True)), 201


@blog_bp.put("/api/admin/blog/posts/<int:post_id>")
@admin_required
def admin_update_post(post_id):
    post = db.session.get(BlogPost, post_id)
    if not post:
        return jsonify(error="not_found"), 404
    body = request.get_json(silent=True) or {}

    # Slug change (validated unique). Empty regenerates from the title.
    if "slug" in body:
        desired = body["slug"] or post.title
        post.slug = _unique_slug(desired, exclude_id=post.id)

    _apply_post_fields(post, body)
    _apply_status(post, body)   # draft / publish / schedule lifecycle

    db.session.commit()
    return jsonify(post=post.to_dict(full=True))


@blog_bp.delete("/api/admin/blog/posts/<int:post_id>")
@admin_required
def admin_delete_post(post_id):
    post = db.session.get(BlogPost, post_id)
    if not post:
        return jsonify(error="not_found"), 404
    db.session.delete(post)
    db.session.commit()
    return jsonify(ok=True)


@blog_bp.get("/api/admin/blog/subscribers")
@admin_required
def admin_list_subscribers():
    """Newsletter signups for the admin Blog tab (newest first)."""
    subs = BlogSubscriber.query.order_by(BlogSubscriber.created_at.desc()).all()
    return jsonify(subscribers=[s.to_dict() for s in subs], count=len(subs))


@blog_bp.post("/api/admin/blog/media")
@admin_required
def admin_upload_media():
    """Accept an image upload, re-encode to WebP (capped at 1600px), store in DB."""
    if "file" not in request.files:
        return jsonify(error="no_file"), 400
    f = request.files["file"]
    raw = f.read()
    if not raw:
        return jsonify(error="empty"), 400
    if len(raw) > 10 * 1024 * 1024:
        return jsonify(error="too_large", detail="Max 10 MB per image."), 413

    width = height = None
    content_type = f.mimetype or "image/webp"
    data = raw
    if _HAS_PIL:
        try:
            img = Image.open(io.BytesIO(raw))
            img.load()
            if img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGBA")
                bg = Image.new("RGBA", img.size, (255, 255, 255, 0))
                img = Image.alpha_composite(bg, img).convert("RGB")
            else:
                img = img.convert("RGB")
            max_w = 1600
            if img.width > max_w:
                ratio = max_w / float(img.width)
                img = img.resize((max_w, int(img.height * ratio)), Image.LANCZOS)
            out = io.BytesIO()
            img.save(out, format="WEBP", quality=82, method=4)
            data = out.getvalue()
            width, height = img.width, img.height
            content_type = "image/webp"
        except Exception:
            return jsonify(error="bad_image"), 400

    media = BlogMedia(
        filename=(f.filename or "image")[:255],
        content_type=content_type, data=data,
        width=width, height=height, byte_size=len(data),
        alt_text=(request.form.get("alt") or "")[:300] or None,
        uploaded_by=_current_user_id(),
    )
    db.session.add(media)
    db.session.commit()
    return jsonify(media.to_dict()), 201


# ════════════════════════════ PUBLIC: media ════════════════════════════════════
@blog_bp.get("/blog/media/<int:media_id>")
def serve_media(media_id):
    media = db.session.get(BlogMedia, media_id)
    if not media:
        abort(404)
    resp = Response(media.data, content_type=media.content_type)
    resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return resp


# ════════════════════════════ PUBLIC: JSON (optional) ══════════════════════════
def _live_filter():
    """SQLAlchemy filter for posts the public may see: published, or scheduled
    whose time has arrived (so scheduled posts go live with no background job)."""
    now = datetime.utcnow()
    return or_(BlogPost.status == "published",
               and_(BlogPost.status == "scheduled", BlogPost.published_at <= now))


@blog_bp.get("/api/blog/posts")
def public_list_posts():
    limit = min(int(request.args.get("limit", 20) or 20), 50)
    posts = (BlogPost.query.filter(_live_filter())
             .order_by(BlogPost.published_at.desc()).limit(limit).all())
    return jsonify(posts=[p.to_dict() for p in posts])


@blog_bp.get("/api/blog/posts/<slug>")
def public_get_post(slug):
    post = BlogPost.query.filter(_live_filter(), BlogPost.slug == slug).first()
    if not post:
        return jsonify(error="not_found"), 404
    d = post.to_dict(full=True)
    d["body_html"] = _render_embeds(d["body_html"])
    return jsonify(post=d)


# ════════════════════════════ PUBLIC: server-rendered HTML ═════════════════════
def _meta_desc(post: BlogPost) -> str:
    return (post.meta_description or post.excerpt
            or _auto_excerpt(post.body_html))[:300]


def _fmt_date(dt):
    if not dt:
        return ""
    try:
        return dt.strftime("%b %-d, %Y") if os.name != "nt" else dt.strftime("%b %d, %Y")
    except Exception:
        return dt.strftime("%b %d, %Y")


def _fmt_views(n):
    """Compact view count: 1234 → '1.2k', 1500000 → '1.5M'."""
    n = int(n or 0)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M".replace(".0M", "M")
    if n >= 1_000:
        return f"{n / 1_000:.1f}k".replace(".0k", "k")
    return str(n)


def _post_card(p):
    cover = (f'<a href="{SITE_URL}/blog/{p.slug}" class="thumb" '
             f"style=\"background-image:url('{_html.escape(p.cover_image_url)}')\"></a>"
             if p.cover_image_url else
             f'<a href="{SITE_URL}/blog/{p.slug}" class="thumb noimg"></a>')
    views = f' · {_fmt_views(p.views)} views' if (p.views or 0) else ''
    return (f'<article class="card">{cover}<div class="card-body">'
            f'<div class="card-meta">{_html.escape(p.category or "Article")} · {p.reading_minutes or 1} min read</div>'
            f'<h2><a href="{SITE_URL}/blog/{p.slug}">{_html.escape(p.title)}</a></h2>'
            f'<p>{_html.escape(p.excerpt or "")}</p>'
            f'<div class="card-foot">{_html.escape(p.author_name or BRAND)} · {_fmt_date(p.published_at)}{views}</div>'
            f'</div></article>')


def _render_listing(*, items, page, base_path, h1, lede, title, description,
                    canonical_base, jsonld=None, noindex=False, hero_extra="",
                    empty_msg="No posts found — try another search or check back soon."):
    """Paginated grid of post cards — shared by the index + category/tag pages."""
    page = max(1, page)
    total_pages = max(1, (len(items) + PER_PAGE - 1) // PER_PAGE)
    page = min(page, total_pages)
    start = (page - 1) * PER_PAGE
    shown = items[start:start + PER_PAGE]
    grid = ("".join(_post_card(p) for p in shown) if shown
            else f'<p class="empty">{_html.escape(empty_msg)}</p>')
    # base_path may already carry a query (e.g. ?q=…) — pick the right separator.
    sep = '&' if '?' in base_path else '?'
    pager = ""
    if total_pages > 1:
        prev = f'<a href="{base_path}{sep}page={page - 1}">← Newer</a>' if page > 1 else '<span></span>'
        nxt = f'<a href="{base_path}{sep}page={page + 1}">Older →</a>' if page < total_pages else '<span></span>'
        pager = f'<nav class="pager">{prev}<span class="pageno">Page {page} of {total_pages}</span>{nxt}</nav>'
    body = (f'<section class="hero-blog"><h1>{_html.escape(h1)}</h1>'
            f'<p class="lede">{_html.escape(lede)}</p>{hero_extra}</section>'
            f'<section class="grid">{grid}</section>{pager}')
    csep = '&' if '?' in canonical_base else '?'
    canonical = canonical_base if page == 1 else f"{canonical_base}{csep}page={page}"
    return _page(title, description, body, canonical=canonical, jsonld=jsonld, noindex=noindex)


def _page(title, description, body, *, canonical, og_image=None, noindex=False,
          jsonld=None, og_type="website", sidebar=None):
    desc = _html.escape((description or "")[:300], quote=True)
    title_e = _html.escape(title)
    og_image = _html.escape(og_image or f"{SITE_URL}/og-image.png", quote=True)
    canonical = _html.escape(canonical, quote=True)
    robots = "noindex,nofollow" if noindex else "index,follow,max-image-preview:large"
    # Neutralise any "</script>" inside the JSON-LD so a value can't break out of
    # the script block (e.g. a post title containing </script>).
    ld = (f'<script type="application/ld+json">{jsonld.replace("</", "<\\/")}</script>'
          if jsonld else "")
    # Two-column layout (article + sidebar) when a sidebar is supplied; otherwise
    # a single centred column (index, category, tag, search, 404, thank-you).
    main = (f'<main class="has-side"><div class="content">{body}</div>'
            f'<aside class="sidebar"><div class="side-inner">{sidebar}</div></aside></main>'
            if sidebar else f'<main>{body}</main>')
    year = datetime.utcnow().year
    footer = f"""<footer><div class="wrap">
<div class="foot-grid">
<div class="foot-brand"><div class="brand">{BRAND}</div>
<p>Run your Telegram &amp; Discord communities on autopilot — moderation, engagement and growth, 24/7.</p>
<div class="socials">{_social_icons()}</div></div>
<div class="foot-col"><h4>Product</h4>
<a href="{SITE_URL}/">Telegram</a><a href="{SITE_URL}/guildizer-landing">Guildizer (Discord)</a>
<a href="{SITE_URL}/pricing">Pricing</a><a href="{SITE_URL}/register">Start free</a></div>
<div class="foot-col"><h4>Resources</h4>
<a href="{SITE_URL}/blog">Blog</a>
<a href="{SITE_URL}/blog/search">Search</a></div>
<div class="foot-news">{_newsletter_form(source="footer")}</div>
</div>
<div class="foot-bottom">© {year} {BRAND}. All rights reserved.</div>
</div></footer>"""
    return Response(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title_e}</title>
<meta name="description" content="{desc}">
<meta name="robots" content="{robots}">
<link rel="canonical" href="{canonical}">
<link rel="icon" href="{SITE_URL}/icons/icon-192.png">
<meta property="og:site_name" content="{BRAND}">
<meta property="og:type" content="{og_type}">
<meta property="og:title" content="{title_e}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{og_image}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title_e}">
<meta name="twitter:description" content="{desc}">
<meta name="twitter:image" content="{og_image}">
<link rel="alternate" type="application/rss+xml" title="{BRAND} Blog" href="{SITE_URL}/blog/feed.xml">
{ld}
<style>{_CSS}</style>
</head>
<body>
<header class="topbar"><div class="nav"><a class="brand" href="{SITE_URL}/">{BRAND}</a>
<nav><a href="{SITE_URL}/blog">Blog</a>
<a class="cta" href="{SITE_URL}/register">Start free</a></nav></div></header>
{main}
{footer}
</body></html>""", content_type="text/html; charset=utf-8")


@blog_bp.get("/blog")
def blog_index():
    page = request.args.get("page", 1, type=int) or 1
    items = (BlogPost.query.filter(_live_filter())
             .order_by(BlogPost.published_at.desc()).all())
    jsonld = ('{"@context":"https://schema.org","@type":"Blog","name":"%s Blog",'
              '"url":"%s/blog"}' % (BRAND, SITE_URL))
    return _render_listing(
        items=items, page=page, base_path=f"{SITE_URL}/blog",
        h1=f"The {BRAND} Blog",
        lede="Guides on growing, moderating and automating Telegram & Discord communities.",
        title=f"{BRAND} Blog — Telegram & Discord community guides",
        description=f"Guides on growing, moderating and automating Telegram and Discord communities, from {BRAND}.",
        canonical_base=f"{SITE_URL}/blog", jsonld=jsonld,
        hero_extra=_search_form(klass="hero-search", with_heading=False))


@blog_bp.get("/blog/search")
def blog_search():
    """No-JS, server-rendered search across title/excerpt/body (noindex)."""
    q = (request.args.get("q") or "").strip()[:120]
    page = request.args.get("page", 1, type=int) or 1
    items = []
    if q:
        like = f"%{q}%"
        items = (BlogPost.query.filter(
                    _live_filter(),
                    or_(BlogPost.title.ilike(like),
                        BlogPost.excerpt.ilike(like),
                        BlogPost.body_html.ilike(like)))
                 .order_by(BlogPost.published_at.desc()).all())
    if q:
        h1 = f"Search results for “{q}”"
        lede = f'{len(items)} article{"" if len(items) == 1 else "s"} found.'
        base = f"{SITE_URL}/blog/search?q={quote(q)}"
        empty_msg = f"No articles match “{q}”. Try a different word."
    else:
        h1, lede = "Search the blog", "Type a term to search every article."
        base = f"{SITE_URL}/blog/search"
        # No search run yet — don't imply the blog is empty.
        empty_msg = "Type a search term above and hit Search to find articles."
    return _render_listing(
        items=items, page=page, base_path=base, h1=h1, lede=lede,
        title=(f"Search: {q} — {BRAND} Blog" if q else f"Search — {BRAND} Blog"),
        description=f"Search the {BRAND} blog for Telegram & Discord community guides.",
        canonical_base=f"{SITE_URL}/blog/search", noindex=True, empty_msg=empty_msg,
        hero_extra=_search_form(klass="hero-search", with_heading=False))


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@blog_bp.post("/blog/subscribe")
def blog_subscribe():
    """Capture a newsletter email (footer/sidebar form). No-JS: renders a
    server-side confirmation page. Stored in blog_subscribers (deduped)."""
    email = (request.form.get("email") or "").strip().lower()[:254]
    source = (request.form.get("source") or "blog").strip()[:40]
    ok = bool(_EMAIL_RE.match(email))
    if ok:
        try:
            if not BlogSubscriber.query.filter_by(email=email).first():
                db.session.add(BlogSubscriber(email=email, source=source))
                db.session.commit()
        except Exception:
            db.session.rollback()
    if ok:
        inner = (f'<h1>You’re subscribed 🎉</h1>'
                 f'<p>Thanks — we’ll send {_html.escape(email)} our best Telegram &amp; '
                 f'Discord community guides. No spam, unsubscribe anytime.</p>'
                 f'<p><a class="cta" href="{SITE_URL}/register">Start free</a></p>'
                 f'<p class="back"><a href="{SITE_URL}/blog">← Back to the blog</a></p>')
    else:
        inner = ('<h1>That email didn’t look right</h1>'
                 '<p>Please go back and enter a valid email address.</p>'
                 f'<p class="back"><a href="{SITE_URL}/blog">← Back to the blog</a></p>')
    body = f'<section class="article notice">{inner}</section>'
    return _page(f"Newsletter — {BRAND} Blog", "Newsletter subscription.",
                 body, canonical=f"{SITE_URL}/blog", noindex=True)


@blog_bp.get("/blog/category/<cat>")
def blog_category(cat):
    page = request.args.get("page", 1, type=int) or 1
    items = (BlogPost.query.filter(_live_filter(), BlogPost.category.ilike(cat))
             .order_by(BlogPost.published_at.desc()).all())
    return _render_listing(
        items=items, page=page, base_path=f"{SITE_URL}/blog/category/{quote(cat)}",
        h1=cat, lede=f"{BRAND} articles in {cat}.",
        title=f"{cat} — {BRAND} Blog", description=f"{BRAND} guides and articles about {cat}.",
        canonical_base=f"{SITE_URL}/blog/category/{quote(cat)}")


@blog_bp.get("/blog/tag/<tag>")
def blog_tag(tag):
    page = request.args.get("page", 1, type=int) or 1
    live = (BlogPost.query.filter(_live_filter())
            .order_by(BlogPost.published_at.desc()).all())
    tl = tag.lower()
    items = [p for p in live if tl in [str(t).lower() for t in (p.tags or [])]]
    return _render_listing(
        items=items, page=page, base_path=f"{SITE_URL}/blog/tag/{quote(tag)}",
        h1=f"#{tag}", lede=f"{BRAND} articles tagged “{tag}”.",
        title=f"#{tag} — {BRAND} Blog", description=f"{BRAND} articles tagged {tag}.",
        canonical_base=f"{SITE_URL}/blog/tag/{quote(tag)}")


@blog_bp.get("/blog/<slug>")
def blog_post(slug):
    post = BlogPost.query.filter(_live_filter(), BlogPost.slug == slug).first()
    if not post:
        # Minimal 404 (still server-rendered) so crawlers get a clean 404.
        return _page(f"Not found — {BRAND} Blog", "This article could not be found.",
                     '<section class="article"><h1>Post not found</h1>'
                     f'<p><a href="{SITE_URL}/blog">← Back to the blog</a></p></section>',
                     canonical=f"{SITE_URL}/blog/{_html.escape(slug)}", noindex=True), 404

    try:
        post.views = (post.views or 0) + 1
        # A scheduled post whose time has arrived self-corrects to published.
        if post.status == "scheduled" and post.published_at and post.published_at <= datetime.utcnow():
            post.status = "published"
        db.session.commit()
    except Exception:
        db.session.rollback()

    body_html = _render_embeds(post.body_html or "")
    body_html, toc_items = _add_toc(body_html)
    # Stored naive UTC → mark as UTC for schema.org / <time> correctness.
    date_iso = (post.published_at.isoformat() + "Z") if post.published_at else ""
    mod_iso = (post.updated_at.isoformat() + "Z") if post.updated_at else date_iso
    date_h = post.published_at.strftime("%B %d, %Y") if post.published_at else ""
    cover = (f'<img class="cover" src="{_html.escape(post.cover_image_url)}" '
             f'alt="{_html.escape(post.title)}" loading="eager">'
             if post.cover_image_url else "")
    tags = "".join(f'<span class="tag">{_html.escape(t)}</span>'
                   for t in (post.tags or []))
    canonical = post.canonical_url or f"{SITE_URL}/blog/{post.slug}"
    og_image = post.og_image_url or post.cover_image_url or f"{SITE_URL}/og-image.png"

    # Clickable category chip + crumb
    cat_name = post.category or "Article"
    cat_link = f'{SITE_URL}/blog/category/{quote(cat_name)}'
    cat_html = f'<div class="cat"><a href="{cat_link}">{_html.escape(cat_name)}</a></div>'
    crumb_cat = f'<a href="{cat_link}">{_html.escape(cat_name)}</a> › '

    # Clickable tag chips
    tags = "".join(
        f'<a class="tag" href="{SITE_URL}/blog/tag/{quote(t)}">#{_html.escape(t)}</a>'
        for t in (post.tags or []))

    # Social share (pure links — no JS, CSP-safe)
    su, st = quote(canonical, safe=""), quote(post.title, safe="")
    share = (
        '<div class="share"><span>Share:</span>'
        f'<a href="https://twitter.com/intent/tweet?url={su}&text={st}" target="_blank" rel="noopener">X</a>'
        f'<a href="https://t.me/share/url?url={su}&text={st}" target="_blank" rel="noopener">Telegram</a>'
        f'<a href="https://www.linkedin.com/sharing/share-offsite/?url={su}" target="_blank" rel="noopener">LinkedIn</a>'
        f'<a href="https://www.facebook.com/sharer/sharer.php?u={su}" target="_blank" rel="noopener">Facebook</a>'
        f'<a href="https://api.whatsapp.com/send?text={st}%20{su}" target="_blank" rel="noopener">WhatsApp</a>'
        f'<a href="https://www.reddit.com/submit?url={su}&title={st}" target="_blank" rel="noopener">Reddit</a>'
        '</div>')

    # Related posts: same category first, then most recent, excluding self.
    related = (BlogPost.query.filter(_live_filter(), BlogPost.id != post.id,
                                     BlogPost.category == post.category)
               .order_by(BlogPost.published_at.desc()).limit(3).all())
    if len(related) < 3:
        seen = {p.id for p in related} | {post.id}
        for m in (BlogPost.query.filter(_live_filter())
                  .order_by(BlogPost.published_at.desc()).limit(8).all()):
            if m.id not in seen:
                related.append(m); seen.add(m.id)
            if len(related) >= 3:
                break
    related_html = (f'<section class="related"><h2>Related articles</h2>'
                    f'<div class="grid">{"".join(_post_card(p) for p in related)}</div></section>'
                    if related else "")

    body = f"""<article class="article">
<nav class="crumbs"><a href="{SITE_URL}/">Home</a> › <a href="{SITE_URL}/blog">Blog</a> › {crumb_cat}<span>{_html.escape(post.title)}</span></nav>
{cat_html}
<h1>{_html.escape(post.title)}</h1>
<div class="byline">By {_html.escape(post.author_name or BRAND)} · <time datetime="{date_iso}">{date_h}</time> · {post.reading_minutes or 1} min read · {_fmt_views(post.views)} views</div>
{cover}
<div class="prose">{body_html}</div>
<div class="tags">{tags}</div>
{share}
<div class="endcta"><h3>Run your community on autopilot</h3>
<p>{BRAND} moderates, engages and grows your Telegram &amp; Discord groups 24/7.</p>
<a class="cta" href="{SITE_URL}/register">Start free</a></div>
{related_html}
<p class="back"><a href="{SITE_URL}/blog">← Back to all articles</a></p>
</article>"""

    img_for_ld = (og_image or "").replace('"', "")
    jsonld = (
        '{"@context":"https://schema.org","@type":"BlogPosting",'
        f'"headline":{_json_str(post.title)},'
        f'"description":{_json_str(_meta_desc(post))},'
        f'"image":["{img_for_ld}"],'
        f'"datePublished":"{date_iso}",'
        f'"dateModified":"{mod_iso}",'
        f'"author":{{"@type":"Organization","name":{_json_str(post.author_name or BRAND)}}},'
        f'"publisher":{{"@type":"Organization","name":"{BRAND}",'
        f'"logo":{{"@type":"ImageObject","url":"{SITE_URL}/icons/icon-192.png"}}}},'
        f'"mainEntityOfPage":{{"@type":"WebPage","@id":"{canonical}"}}}}'
    )
    title = post.meta_title or f"{post.title} — {BRAND} Blog"
    return _page(title, _meta_desc(post), body, canonical=canonical,
                 og_image=og_image, noindex=post.noindex, jsonld=jsonld,
                 og_type="article", sidebar=_article_sidebar(post, toc_items))


def _json_str(s: str) -> str:
    """JSON-encode a string for inline JSON-LD."""
    import json
    return json.dumps(s or "")


# ════════════════════════════ PUBLIC: sitemap + RSS ════════════════════════════
@blog_bp.get("/blog-sitemap.xml")
def blog_sitemap():
    posts = (BlogPost.query.filter(_live_filter())
             .filter(BlogPost.noindex.is_(False))
             .order_by(BlogPost.published_at.desc()).all())
    urls = [f"<url><loc>{SITE_URL}/blog</loc><changefreq>daily</changefreq><priority>0.8</priority></url>"]
    for p in posts:
        lastmod = (p.updated_at or p.published_at)
        lm = lastmod.strftime("%Y-%m-%d") if lastmod else ""
        urls.append(
            f"<url><loc>{SITE_URL}/blog/{_html.escape(p.slug)}</loc>"
            f"<lastmod>{lm}</lastmod><changefreq>monthly</changefreq><priority>0.7</priority></url>")
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
           + "".join(urls) + "</urlset>")
    return Response(xml, content_type="application/xml; charset=utf-8")


@blog_bp.get("/blog/feed.xml")
def blog_rss():
    posts = (BlogPost.query.filter(_live_filter())
             .order_by(BlogPost.published_at.desc()).limit(30).all())
    items = []
    for p in posts:
        pub = p.published_at.strftime("%a, %d %b %Y %H:%M:%S GMT") if p.published_at else ""
        items.append(
            f"<item><title>{_html.escape(p.title)}</title>"
            f"<link>{SITE_URL}/blog/{_html.escape(p.slug)}</link>"
            f"<guid>{SITE_URL}/blog/{_html.escape(p.slug)}</guid>"
            f"<pubDate>{pub}</pubDate>"
            f"<description>{_html.escape(p.excerpt or '')}</description></item>")
    xml = ('<?xml version="1.0" encoding="UTF-8"?><rss version="2.0">'
           f"<channel><title>{BRAND} Blog</title><link>{SITE_URL}/blog</link>"
           f"<description>Telegram &amp; Discord community guides</description>"
           + "".join(items) + "</channel></rss>")
    return Response(xml, content_type="application/rss+xml; charset=utf-8")


# ── Self-contained dark-theme styles for the public blog (brand-aligned) ────────
_CSS = """
:root{--bg:#0b0d12;--bg2:#12151c;--card:#151922;--bd:#222836;--tx:#e7eaf0;--mut:#9aa3b2;--pl:#9d6cf7;--bl:#3d8ef8}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--tx);font:16px/1.7 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;-webkit-font-smoothing:antialiased}
a{color:var(--bl);text-decoration:none}a:hover{text-decoration:underline}
.topbar{position:sticky;top:0;z-index:50;background:rgba(11,13,18,.82);backdrop-filter:saturate(160%) blur(10px);-webkit-backdrop-filter:saturate(160%) blur(10px);border-bottom:1px solid var(--bd)}
.nav{display:flex;align-items:center;justify-content:space-between;padding:13px 24px;max-width:1180px;margin:0 auto}
.brand{font-weight:800;font-size:1.2rem;color:#fff}
.nav nav{display:flex;gap:20px;align-items:center}
.nav nav a:not(.cta){color:var(--mut);font-weight:600}.nav nav a:not(.cta):hover{color:var(--tx);text-decoration:none}
.nav .cta,.cta{background:linear-gradient(135deg,var(--pl),var(--bl));color:#fff;padding:9px 16px;border-radius:9px;font-weight:600;display:inline-block}
.cta:hover{text-decoration:none;opacity:.92}
main{max-width:1180px;margin:0 auto;padding:0 24px}
main.has-side{display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:48px;align-items:start}
.content{min-width:0}
.content .article{max-width:760px;margin:0;padding-top:28px}
.sidebar{position:sticky;top:78px}
.side-inner{display:flex;flex-direction:column}
.widget{background:var(--card);border:1px solid var(--bd);border-radius:14px;padding:18px;margin-bottom:18px}
.widget h3{margin:0 0 12px;font-size:1rem;color:var(--tx)}
.widget.cta-card{background:linear-gradient(135deg,rgba(157,108,247,.16),rgba(61,142,248,.12));border-color:#2c3550}
.widget.cta-card p{color:var(--mut);font-size:.9rem;margin:0 0 14px}
.widget.cta-card .cta{display:block;text-align:center}
.recent ul{list-style:none;margin:0;padding:0}
.toc-list{list-style:none;margin:0;padding:0}
.toc-item{margin:0}
.toc-row{display:flex;align-items:flex-start;gap:9px;padding:5px 0}
.toc-n{flex:none;width:20px;height:20px;border-radius:6px;background:var(--bg2);border:1px solid var(--bd);color:var(--mut);font-size:.7rem;font-weight:700;display:grid;place-items:center;margin-top:1px}
.toc-row a{flex:1;font-size:.9rem;color:var(--mut);line-height:1.4}
.toc-row a:hover{color:var(--tx)}
.toc-caret{flex:none;width:20px;height:20px;cursor:pointer;position:relative;border-radius:5px}
.toc-caret:hover{background:var(--bg2)}
.toc-caret::before{content:"";position:absolute;top:50%;left:50%;width:6px;height:6px;border-right:2px solid var(--mut);border-bottom:2px solid var(--mut);transform:translate(-60%,-50%) rotate(-45deg);transition:transform .18s}
.toc-toggle:checked ~ .toc-row .toc-caret::before{transform:translate(-50%,-70%) rotate(45deg)}
.toc-caret:hover::before{border-color:var(--tx)}
.toc-sub{list-style:none;margin:0 0 4px 9px;padding:0 0 0 18px;border-left:1px solid var(--bd)}
.toc-sub li{margin:0}
.toc-sub a{display:block;font-size:.84rem;color:var(--mut);padding:3px 0}
.toc-sub a::before{content:"›";margin-right:6px;color:var(--pl)}
.toc-sub a:hover{color:var(--tx)}
.toc-toggle:not(:checked) ~ .toc-sub{display:none}
.recent li{padding:.6em 0;border-top:1px solid var(--bd)}.recent li:first-child{border-top:none;padding-top:0}
.recent li a{display:block;font-size:.9rem;color:var(--tx);font-weight:600;line-height:1.35}
.recent li a:hover{color:var(--pl);text-decoration:none}
.recent li span{display:block;color:var(--mut);font-size:.74rem;margin-top:3px}
.search form,.newsletter form{display:flex;flex-direction:column;gap:9px}
.search input,.newsletter input[type=email]{background:var(--bg2);border:1px solid var(--bd);border-radius:9px;padding:10px 12px;color:var(--tx);font-size:.92rem;width:100%}
.search input:focus,.newsletter input:focus,.hero-search input:focus{outline:none;border-color:var(--pl)}
.search button,.newsletter button{background:linear-gradient(135deg,var(--pl),var(--bl));color:#fff;border:0;border-radius:9px;padding:10px;font-weight:700;cursor:pointer;font-size:.92rem}
.search button:hover,.newsletter button:hover,.hero-search button:hover{opacity:.92}
.newsletter p{color:var(--mut);font-size:.85rem;margin:0 0 12px}
.hero-search{margin-top:20px;display:flex;gap:8px;max-width:460px}
.hero-search input{flex:1;background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:11px 14px;color:var(--tx);font-size:.95rem}
.hero-search button{background:linear-gradient(135deg,var(--pl),var(--bl));color:#fff;border:0;border-radius:10px;padding:11px 20px;font-weight:700;cursor:pointer}
.notice{text-align:center;padding:60px 0}
.hero-blog{padding:48px 0 28px;border-bottom:1px solid var(--bd);margin-bottom:32px}
.hero-blog h1{font-size:2.2rem;margin:0 0 10px;letter-spacing:-.02em}
.lede{color:var(--mut);font-size:1.1rem;margin:0;max-width:640px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:22px;padding-bottom:60px}
.card{background:var(--card);border:1px solid var(--bd);border-radius:14px;overflow:hidden;display:flex;flex-direction:column;transition:transform .15s,border-color .15s}
.card:hover{transform:translateY(-3px);border-color:#33405c}
.thumb{display:block;height:170px;background-size:cover;background-position:center;background-color:#1b2030}
.thumb.noimg{background:linear-gradient(135deg,rgba(157,108,247,.25),rgba(61,142,248,.18))}
.card-body{padding:16px 18px 18px;display:flex;flex-direction:column;gap:8px;flex:1}
.card-meta{color:var(--pl);font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em}
.card h2{font-size:1.15rem;margin:0;line-height:1.35}
.card h2 a{color:#fff}
.card-body p{color:var(--mut);font-size:.92rem;margin:0;flex:1}
.card-foot{color:var(--mut);font-size:.8rem;border-top:1px solid var(--bd);padding-top:10px}
.empty{color:var(--mut);padding:40px 0}
.article{max-width:760px;margin:0 auto;padding:32px 0 60px}
.crumbs{color:var(--mut);font-size:.82rem;margin-bottom:18px}
.crumbs span{color:var(--tx)}
.cat{color:var(--pl);font-weight:700;text-transform:uppercase;letter-spacing:.05em;font-size:.74rem;margin-bottom:8px}
.article h1{font-size:2.3rem;line-height:1.2;letter-spacing:-.02em;margin:0 0 14px}
.byline{color:var(--mut);font-size:.9rem;margin-bottom:24px}
.cover{width:100%;height:auto;border-radius:14px;margin:0 0 28px;display:block}
.prose{font-size:1.08rem}
.prose h2{font-size:1.6rem;margin:2em 0 .6em;letter-spacing:-.01em;scroll-margin-top:90px}
.prose h3{font-size:1.28rem;margin:1.6em 0 .5em}
.prose p{margin:0 0 1.2em}
.prose img{max-width:100%;height:auto;display:block;margin:1.6em auto;border-radius:12px}
.prose figure{margin:1.6em 0}.prose figcaption{color:var(--mut);font-size:.85rem;text-align:center;margin-top:8px}
.prose ul,.prose ol{margin:0 0 1.2em;padding-left:1.4em}.prose li{margin:.4em 0}
.prose a{text-decoration:underline}
.prose blockquote{margin:1.6em 0;padding:14px 20px;border-left:3px solid var(--pl);background:var(--bg2);border-radius:0 10px 10px 0;color:var(--tx)}
.prose pre{background:#0d1017;border:1px solid var(--bd);border-radius:10px;padding:16px;overflow:auto;font-size:.9rem}
.prose code{background:var(--bg2);padding:2px 6px;border-radius:6px;font-size:.9em}
.prose pre code{background:none;padding:0}
.prose table{width:100%;border-collapse:collapse;margin:1.4em 0}
.prose th,.prose td{border:1px solid var(--bd);padding:8px 12px;text-align:left}
.tg-video{position:relative;padding-bottom:56.25%;height:0;margin:1.8em 0;border-radius:12px;overflow:hidden}
.tg-video iframe{position:absolute;top:0;left:0;width:100%;height:100%;border:0}
.tg-post{margin:1.8em auto;max-width:520px}
.tg-post iframe{width:100%;height:560px;border:0;border-radius:12px}
.video-link a{display:inline-block;margin:1.2em 0;padding:10px 18px;background:var(--bg2);border:1px solid var(--bd);border-radius:10px;font-weight:600}
.tags{margin:28px 0;display:flex;flex-wrap:wrap;gap:8px}
.tag{background:var(--bg2);border:1px solid var(--bd);color:var(--mut);padding:4px 12px;border-radius:20px;font-size:.8rem;text-decoration:none}
.tag:hover{border-color:var(--pl);color:var(--tx);text-decoration:none}
.share{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:24px 0;padding:14px 0;border-top:1px solid var(--bd);border-bottom:1px solid var(--bd)}
.share span{color:var(--mut);font-size:.85rem;font-weight:600}
.share a{font-size:.82rem;font-weight:600;color:var(--tx);background:var(--bg2);border:1px solid var(--bd);padding:6px 14px;border-radius:8px;text-decoration:none}
.share a:hover{border-color:var(--bl);text-decoration:none}
.related{margin:48px 0 0;border-top:1px solid var(--bd);padding-top:28px}
.related h2{font-size:1.4rem;margin:0 0 18px}
.pager{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:20px 0 60px;color:var(--mut)}
.pager a{font-weight:600}.pageno{font-size:.85rem}
.endcta{background:linear-gradient(135deg,rgba(157,108,247,.12),rgba(61,142,248,.1));border:1px solid var(--bd);border-radius:16px;padding:28px;text-align:center;margin:36px 0}
.endcta h3{margin:0 0 8px;font-size:1.3rem}.endcta p{color:var(--mut);margin:0 0 18px}
.back{margin-top:30px}
footer{border-top:1px solid var(--bd);margin-top:60px;padding:48px 24px 26px;color:var(--mut);font-size:.9rem;background:var(--bg2)}
footer .wrap{max-width:1180px;margin:0 auto}
.foot-grid{display:grid;grid-template-columns:1.5fr 1fr 1fr 1.7fr;gap:36px}
.foot-brand .brand{color:#fff;font-size:1.2rem;font-weight:800;margin-bottom:8px}
.foot-brand p{margin:.4em 0 16px;max-width:280px;color:var(--mut)}
.socials{display:flex;gap:10px}
.socials a{display:grid;place-items:center;width:38px;height:38px;border:1px solid var(--bd);border-radius:9px;color:var(--mut);background:var(--card)}
.socials a:hover{color:#fff;border-color:var(--pl);text-decoration:none}
.socials svg{width:18px;height:18px;fill:currentColor}
.foot-col h4{color:var(--tx);font-size:.95rem;margin:0 0 12px}
.foot-col a{display:block;color:var(--mut);margin:.55em 0}.foot-col a:hover{color:var(--tx)}
.foot-news .widget{margin:0}
.foot-bottom{border-top:1px solid var(--bd);margin-top:34px;padding-top:20px;text-align:center;color:var(--mut);font-size:.82rem}
@media(max-width:980px){main.has-side{grid-template-columns:1fr}.sidebar{position:static;margin-top:44px}.content .article{max-width:none}}
@media(max-width:860px){.foot-grid{grid-template-columns:1fr 1fr}.foot-news{grid-column:1/-1}}
@media(max-width:600px){.hero-blog h1{font-size:1.8rem}.article h1{font-size:1.7rem}.foot-grid{grid-template-columns:1fr}.hero-search{flex-wrap:wrap}}
"""
