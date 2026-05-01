import secrets
import logging
from flask import Blueprint, request, jsonify

logger = logging.getLogger(__name__)
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..models import db, User, Bot, Group, KnowledgeDocument
from ..middleware.rate_limit import rate_limit

knowledge_bp = Blueprint("knowledge", __name__, url_prefix="/api")


def _get_current_user():
    return User.query.get(int(get_jwt_identity()))


def _get_group(user, bot_id, group_id):
    bot = Bot.query.filter_by(id=bot_id, user_id=user.id).first()
    if not bot:
        return None, None
    group = Group.query.filter_by(id=group_id, bot_id=bot.id).first()
    return bot, group


@knowledge_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/knowledge", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def list_documents(bot_id, group_id):
    try:
        user = _get_current_user()
        if not user:
            return jsonify({"error": "User not found"}), 404
        _, group = _get_group(user, bot_id, group_id)
        if not group:
            return jsonify({"error": "Group not found"}), 404
        docs = KnowledgeDocument.query.filter_by(group_id=group.id).order_by(KnowledgeDocument.created_at.desc()).all()
        return jsonify({"documents": [d.to_dict() for d in docs]})
    except Exception as e:
        logger.error(f"list_documents error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


_KB_GROUP_QUOTA_BYTES = 100 * 1024 * 1024  # 100MB per group


@knowledge_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/knowledge", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=3)
def upload_document(bot_id, group_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    _, group = _get_group(user, bot_id, group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404

    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    f = request.files["file"]
    filename = f.filename or "document"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "txt"

    allowed_ext = {"pdf", "txt", "md", "docx"}
    if ext not in allowed_ext:
        return jsonify({"error": f"File type .{ext} not supported. Use: {', '.join(sorted(allowed_ext))}"}), 400

    content_bytes = f.read()
    file_size = len(content_bytes)
    if file_size > 5 * 1024 * 1024:
        return jsonify({"error": "File too large (max 5MB)"}), 400

    # Group-level storage quota (100MB total)
    from sqlalchemy import func as _func
    existing_total = db.session.query(
        _func.sum(_func.length(KnowledgeDocument.content_text))
    ).filter_by(group_id=group.id).scalar() or 0
    if existing_total + file_size > _KB_GROUP_QUOTA_BYTES:
        return jsonify({"error": "Group knowledge base storage limit (100MB) reached. Delete documents to free space."}), 413

    # Validate actual MIME type via magic bytes — extension alone is spoofable.
    _MAGIC_SIGNATURES = {
        b"%PDF": "pdf",
        b"PK\x03\x04": "docx",  # ZIP container (docx is a ZIP)
    }
    detected = None
    for magic, ftype in _MAGIC_SIGNATURES.items():
        if content_bytes[:len(magic)] == magic:
            detected = ftype
            break
    if detected is None and ext in ("txt", "md"):
        # txt/md have no magic bytes — accept if extension claims it
        try:
            content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return jsonify({"error": "File does not appear to be valid UTF-8 text"}), 400
    elif detected is not None and detected != ext:
        return jsonify({"error": f"File content does not match its extension (.{ext})"}), 400
    elif detected is None and ext in ("pdf", "docx"):
        return jsonify({"error": f"File does not appear to be a valid {ext.upper()}"}), 400

    from flask import current_app
    from ..bot_features.knowledge_base import KnowledgeBaseSystem
    kb = KnowledgeBaseSystem(current_app._get_current_object())
    try:
        doc, error = kb.process_document(group.id, filename, ext, content_bytes)
    except Exception as e:
        logger.error(f"Knowledge base process_document error: {e}", exc_info=True)
        return jsonify({"error": f"Processing failed: {str(e)}"}), 500
    if error:
        return jsonify({"error": error}), 400

    return jsonify({"document": doc}), 201


@knowledge_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/knowledge/<int:doc_id>", methods=["DELETE"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def delete_document(bot_id, group_id, doc_id):
    try:
        user = _get_current_user()
        if not user:
            return jsonify({"error": "User not found"}), 404
        _, group = _get_group(user, bot_id, group_id)
        if not group:
            return jsonify({"error": "Group not found"}), 404
        doc = KnowledgeDocument.query.filter_by(id=doc_id, group_id=group.id).first()
        if not doc:
            return jsonify({"error": "Document not found"}), 404
        db.session.delete(doc)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"delete_document error: {e}", exc_info=True)
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify({"error": str(e)}), 500
