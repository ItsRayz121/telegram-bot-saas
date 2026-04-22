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
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    _, group = _get_group(user, bot_id, group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404
    docs = KnowledgeDocument.query.filter_by(group_id=group.id).order_by(KnowledgeDocument.created_at.desc()).all()
    return jsonify({"documents": [d.to_dict() for d in docs]})


@knowledge_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/knowledge", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=10)
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

    allowed = {"pdf", "txt", "md", "docx"}
    if ext not in allowed:
        return jsonify({"error": f"File type .{ext} not supported. Use: {', '.join(allowed)}"}), 400

    content_bytes = f.read()
    if len(content_bytes) > 5 * 1024 * 1024:
        return jsonify({"error": "File too large (max 5MB)"}), 400

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
