"""Community Directory — public listing of channels and groups."""
from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, verify_jwt_in_request
from ..models import (
    db, DirectoryListing, Channel, TelegramGroup, User,
    DIRECTORY_CATEGORIES, DIRECTORY_LANGUAGES,
)

directory_bp = Blueprint("directory", __name__)

PAGE_SIZE = 20


def _get_user():
    return User.query.get(int(get_jwt_identity()))


# ── Public endpoints (no auth) ────────────────────────────────────────────────

@directory_bp.route("/api/directory", methods=["GET"])
def list_directory():
    q = DirectoryListing.query.filter_by(is_public=True)

    category = request.args.get("category")
    if category:
        q = q.filter_by(category=category)

    listing_type = request.args.get("type")
    if listing_type in ("channel", "group"):
        q = q.filter_by(listing_type=listing_type)

    language = request.args.get("language")
    if language:
        q = q.filter_by(language=language)

    country = request.args.get("country")
    if country:
        q = q.filter_by(country=country)

    search = (request.args.get("q") or "").strip()
    if search:
        like = f"%{search}%"
        q = q.filter(
            db.or_(
                DirectoryListing.title.ilike(like),
                DirectoryListing.description.ilike(like),
            )
        )

    sort = request.args.get("sort", "featured")
    if sort == "members":
        q = q.order_by(DirectoryListing.member_count.desc())
    elif sort == "tcs":
        q = q.order_by(DirectoryListing.tcs_score.desc().nullslast())
    elif sort == "newest":
        q = q.order_by(DirectoryListing.created_at.desc())
    else:
        # Default: featured first, then by member count
        q = q.order_by(
            DirectoryListing.is_featured.desc(),
            DirectoryListing.member_count.desc(),
        )

    page = max(1, min(request.args.get("page", 1, type=int), 500))
    total = q.count()
    listings = q.offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE).all()

    return jsonify({
        "listings": [l.to_dict() for l in listings],
        "total": total,
        "page": page,
        "pages": max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE),
        "categories": DIRECTORY_CATEGORIES,
        "languages": DIRECTORY_LANGUAGES,
    })


@directory_bp.route("/api/directory/<int:lid>/view", methods=["POST"])
def record_view(lid):
    listing = DirectoryListing.query.filter_by(id=lid, is_public=True).first_or_404()
    listing.view_count = (listing.view_count or 0) + 1
    db.session.commit()
    return jsonify({"ok": True})


@directory_bp.route("/api/directory/<int:lid>/contact", methods=["POST"])
def record_contact(lid):
    listing = DirectoryListing.query.filter_by(id=lid, is_public=True).first_or_404()
    listing.contact_count = (listing.contact_count or 0) + 1
    db.session.commit()
    return jsonify({"ok": True})


# ── Authenticated endpoints ───────────────────────────────────────────────────

@directory_bp.route("/api/directory/mine", methods=["GET"])
@jwt_required()
def my_listings():
    user = _get_user()
    listings = DirectoryListing.query.filter_by(user_id=user.id).all()
    return jsonify([l.to_dict(include_contact=True) for l in listings])


@directory_bp.route("/api/directory", methods=["POST"])
@jwt_required()
def create_listing():
    user = _get_user()
    data = request.get_json() or {}

    listing_type = data.get("listing_type")
    if listing_type not in ("channel", "group"):
        return jsonify({"error": "listing_type must be 'channel' or 'group'"}), 400

    title = (data.get("title") or "").strip()
    description = (data.get("description") or "").strip()
    category = data.get("category")
    language = data.get("language", "English")
    country = (data.get("country") or "Global").strip()
    telegram_link = (data.get("telegram_link") or "").strip()

    if not title:
        return jsonify({"error": "title is required"}), 400
    if category not in DIRECTORY_CATEGORIES:
        return jsonify({"error": f"Invalid category. Choose from: {', '.join(DIRECTORY_CATEGORIES)}"}), 400
    if not telegram_link:
        return jsonify({"error": "telegram_link is required (e.g. https://t.me/yourcommunity)"}), 400
    if not (telegram_link.startswith("https://t.me/") or telegram_link.startswith("https://telegram.me/")):
        return jsonify({"error": "telegram_link must be a valid Telegram URL (https://t.me/...)"}), 400

    channel_id = None
    tg_group_id = None
    member_count = 0
    tcs_score = None
    tcs_grade = None

    if listing_type == "channel":
        cid = data.get("channel_id")
        if not cid:
            return jsonify({"error": "channel_id is required for channel listings"}), 400
        ch = Channel.query.filter_by(id=cid, user_id=user.id).first()
        if not ch:
            return jsonify({"error": "Channel not found or not owned by you"}), 404
        if DirectoryListing.query.filter_by(channel_id=ch.id).first():
            return jsonify({"error": "This channel is already listed"}), 409
        channel_id = ch.id
        member_count = ch.member_count or 0
        tcs_score = ch.tcs_score
        tcs_grade = ch.tcs_grade
        if not title:
            title = ch.title

    else:  # group
        gid = data.get("telegram_group_id")
        if not gid:
            return jsonify({"error": "telegram_group_id is required for group listings"}), 400
        grp = TelegramGroup.query.filter_by(
            telegram_group_id=str(gid), user_id=user.id
        ).first()
        if not grp:
            return jsonify({"error": "Group not found or not owned by you"}), 404
        if DirectoryListing.query.filter_by(telegram_group_id=str(gid)).first():
            return jsonify({"error": "This group is already listed"}), 409
        tg_group_id = str(gid)
        member_count = grp.member_count or 0
        if not title:
            title = grp.name

    listing = DirectoryListing(
        user_id=user.id,
        channel_id=channel_id,
        telegram_group_id=tg_group_id,
        listing_type=listing_type,
        title=title,
        description=description or None,
        category=category,
        language=language,
        country=country,
        telegram_link=telegram_link,
        member_count=member_count,
        tcs_score=tcs_score,
        tcs_grade=tcs_grade,
    )
    db.session.add(listing)
    db.session.commit()
    return jsonify(listing.to_dict(include_contact=True)), 201


@directory_bp.route("/api/directory/<int:lid>", methods=["PUT"])
@jwt_required()
def update_listing(lid):
    user = _get_user()
    listing = DirectoryListing.query.filter_by(id=lid, user_id=user.id).first_or_404()
    data = request.get_json() or {}

    for field in ("title", "description", "category", "language", "country", "telegram_link"):
        val = data.get(field)
        if val is not None:
            setattr(listing, field, val.strip() if isinstance(val, str) else val)

    if "is_public" in data:
        listing.is_public = bool(data["is_public"])

    listing.last_updated = datetime.utcnow()
    db.session.commit()
    return jsonify(listing.to_dict(include_contact=True))


@directory_bp.route("/api/directory/<int:lid>", methods=["DELETE"])
@jwt_required()
def delete_listing(lid):
    user = _get_user()
    listing = DirectoryListing.query.filter_by(id=lid, user_id=user.id).first_or_404()
    db.session.delete(listing)
    db.session.commit()
    return jsonify({"ok": True})
