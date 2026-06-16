"""Per-user UI preferences — currently the open/closed state of collapsible
settings cards across the dashboard.

Shape stored on User.ui_preferences:
    {"cards": {"<card_id>": bool, ...}}

A card is open ONLY if its id is present and True. Absent ids are closed by
default, which is what lets a refresh keep a card the user collapsed closed.
"""
import logging
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..models import db, User
from ..middleware.rate_limit import rate_limit

logger = logging.getLogger(__name__)
ui_prefs_bp = Blueprint("ui_prefs", __name__, url_prefix="/api/ui-prefs")

# Guardrails so a malformed client can't bloat the JSON column.
_MAX_CARDS = 1000
_MAX_KEY_LEN = 160


def _get_user():
    return User.query.get(int(get_jwt_identity()))


def get_card_states(user) -> dict:
    """Return {card_id: bool} from the user's stored prefs (empty if none)."""
    stored = getattr(user, "ui_preferences", None) or {}
    cards = stored.get("cards") if isinstance(stored, dict) else None
    if isinstance(cards, dict):
        return {str(k): bool(v) for k, v in cards.items()}
    return {}


@ui_prefs_bp.route("", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=120)
def get_ui_prefs():
    user = _get_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify({"cards": get_card_states(user)})


@ui_prefs_bp.route("", methods=["PUT"])
@jwt_required()
@rate_limit(requests_per_minute=120)
def update_ui_prefs():
    user = _get_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    body = request.get_json(silent=True) or {}
    cards = body.get("cards")
    if not isinstance(cards, dict):
        return jsonify({"error": "cards must be an object"}), 400
    clean = {}
    for k, v in list(cards.items())[:_MAX_CARDS]:
        clean[str(k)[:_MAX_KEY_LEN]] = bool(v)
    prefs = dict(getattr(user, "ui_preferences", None) or {})
    prefs["cards"] = clean
    user.ui_preferences = prefs
    db.session.commit()
    return jsonify({"ok": True, "cards": clean})
