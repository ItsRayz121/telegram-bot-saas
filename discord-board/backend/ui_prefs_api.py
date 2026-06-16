"""Per-user UI preferences — the open/closed state of collapsible settings cards
across the Guildizer dashboard.

Shape stored on User.ui_preferences:
    {"cards": {"<card_id>": bool, ...}}

A card is open ONLY if its id is present and True. Absent ids are closed by
default, which lets a refresh keep a card the user collapsed closed.

Mirrors Telegizer's backend/routes/ui_prefs.py (copied logic, not imported — the
two products stay fully isolated).
"""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from auth import login_required
from models import User

ui_prefs_bp = Blueprint("ui_prefs", __name__)

_MAX_CARDS = 1000
_MAX_KEY_LEN = 160


def get_card_states(user) -> dict:
    """Return {card_id: bool} from the user's stored prefs (empty if none)."""
    stored = getattr(user, "ui_preferences", None) or {}
    cards = stored.get("cards") if isinstance(stored, dict) else None
    if isinstance(cards, dict):
        return {str(k): bool(v) for k, v in cards.items()}
    return {}


@ui_prefs_bp.get("/api/ui-prefs")
@login_required
def get_ui_prefs():
    user = g.db.get(User, g.user_id)
    if not user:
        return jsonify(error="not_found"), 404
    return jsonify(cards=get_card_states(user))


@ui_prefs_bp.put("/api/ui-prefs")
@login_required
def update_ui_prefs():
    user = g.db.get(User, g.user_id)
    if not user:
        return jsonify(error="not_found"), 404
    body = request.get_json(silent=True) or {}
    cards = body.get("cards")
    if not isinstance(cards, dict):
        return jsonify(error="cards must be an object"), 400
    clean = {}
    for k, v in list(cards.items())[:_MAX_CARDS]:
        clean[str(k)[:_MAX_KEY_LEN]] = bool(v)
    prefs = dict(getattr(user, "ui_preferences", None) or {})
    prefs["cards"] = clean
    user.ui_preferences = prefs
    g.db.commit()
    return jsonify(ok=True, cards=clean)
