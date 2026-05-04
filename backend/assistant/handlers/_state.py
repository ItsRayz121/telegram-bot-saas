"""Conversation state helpers — thin wrappers around AssistantConversationState."""
from datetime import datetime, timedelta


def get_state(user_id: int):
    from ...models import db, AssistantConversationState
    state = AssistantConversationState.query.filter_by(user_id=user_id).first()
    if state and state.expires_at < datetime.utcnow():
        db.session.delete(state)
        db.session.commit()
        return None
    return state


def clear_state(user_id: int):
    from ...models import db, AssistantConversationState
    AssistantConversationState.query.filter_by(user_id=user_id).delete()
    db.session.commit()


def save_state(user_id: int, intent: str, data: dict, awaiting: str):
    from ...models import db, AssistantConversationState
    state = AssistantConversationState.query.filter_by(user_id=user_id).first()
    if not state:
        state = AssistantConversationState(user_id=user_id)
        db.session.add(state)
    state.pending_intent = intent
    state.collected_data = data
    state.awaiting_field = awaiting
    state.expires_at = datetime.utcnow() + timedelta(minutes=15)
    db.session.commit()
