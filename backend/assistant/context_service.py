"""
AssistantContextService — single source of truth for user workspace context.

Called once per assistant request. Builds a complete snapshot of the user's
workspace and returns it as an AssistantContext dataclass. Every AI call
injects this context into the system prompt so all responses are context-aware.

Usage:
    ctx = AssistantContextService.build(user_id)
    prompt = ctx.to_prompt_text()
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

_log = logging.getLogger(__name__)

# Cache: {user_id: (built_at, AssistantContext)}
# Avoids N+1 DB hits when multiple intent handlers run per request.
_CONTEXT_CACHE: dict[int, tuple[datetime, "AssistantContext"]] = {}
_CACHE_TTL_SECONDS = 60


@dataclass
class AssistantContext:
    user_id: int
    full_name: str
    plan: str
    timezone: str
    telegram_connected: bool
    telegram_user_id: Optional[str]
    joined_days_ago: int

    groups: list = field(default_factory=list)           # [{id, title, member_count, is_active, last_message_at}]
    upcoming_meetings: list = field(default_factory=list) # [{id, title, scheduled_at_human, notes, remind_before}]
    upcoming_reminders: list = field(default_factory=list)# [{id, text, remind_at_human}]
    pending_tasks: list = field(default_factory=list)    # [{id, title, priority, due_at_human}]
    recent_notes: list = field(default_factory=list)     # [{id, content_preview, tags, created_at_human}]
    recent_conversation: list = field(default_factory=list) # [{direction, content, created_at_human}]
    knowledge_docs: list = field(default_factory=list)   # [{id, title, preview}]
    platform_today: dict = field(default_factory=dict)   # {messages_received, automations_fired, digests_sent}
    group_alerts: list = field(default_factory=list)     # [{group_title, health_status, ai_summary}] (Phase 3+)

    def to_prompt_text(self) -> str:
        """Render context as a concise text block for AI system prompts."""
        lines = [
            f"User: {self.full_name} | Plan: {self.plan} | Timezone: {self.timezone}",
            f"Telegram connected: {'Yes' if self.telegram_connected else 'No'}",
            f"Member for: {self.joined_days_ago} day(s)",
        ]

        if self.groups:
            lines.append(f"\nConnected groups ({len(self.groups)}):")
            for g in self.groups[:5]:
                status = "active" if g.get("is_active") else "inactive"
                lines.append(f"  • {g['title']} — {g.get('member_count', '?')} members, {status}")
        else:
            lines.append("\nConnected groups: None yet")

        if self.upcoming_meetings:
            lines.append(f"\nUpcoming meetings ({len(self.upcoming_meetings)}):")
            for m in self.upcoming_meetings[:5]:
                note = f" | Notes: {m['notes'][:60]}" if m.get("notes") else ""
                lines.append(f"  • {m['title']} — {m['scheduled_at_human']}{note}")
        else:
            lines.append("\nUpcoming meetings: None")

        if self.upcoming_reminders:
            lines.append(f"\nUpcoming reminders ({len(self.upcoming_reminders)}):")
            for r in self.upcoming_reminders[:5]:
                lines.append(f"  • {r['text']} — {r['remind_at_human']}")
        else:
            lines.append("\nUpcoming reminders: None")

        if self.pending_tasks:
            lines.append(f"\nPending tasks ({len(self.pending_tasks)}):")
            for t in self.pending_tasks[:5]:
                due = f" | Due: {t['due_at_human']}" if t.get("due_at_human") else ""
                lines.append(f"  • [{t.get('priority','medium').upper()}] {t['title']}{due}")
        else:
            lines.append("\nPending tasks: None")

        if self.recent_notes:
            lines.append(f"\nRecent notes ({len(self.recent_notes)}):")
            for n in self.recent_notes[:3]:
                tags = f" [{', '.join(n['tags'])}]" if n.get("tags") else ""
                lines.append(f"  • {n['content_preview']}{tags}")

        if self.knowledge_docs:
            lines.append(f"\nKnowledge base ({len(self.knowledge_docs)} doc(s)):")
            for d in self.knowledge_docs[:3]:
                lines.append(f"  • {d['title']}: {d.get('preview', '')[:80]}")

        if self.platform_today:
            p = self.platform_today
            lines.append(
                f"\nToday's activity: {p.get('messages_received', 0)} group messages, "
                f"{p.get('automations_fired', 0)} automations fired, "
                f"{p.get('digests_sent', 0)} digests sent"
            )

        if self.group_alerts:
            lines.append(f"\nGroup alerts:")
            for a in self.group_alerts:
                lines.append(f"  ⚠️ {a['group_title']}: {a['health_status']} — {a.get('ai_summary','')[:100]}")

        if self.recent_conversation:
            lines.append("\nRecent conversation:")
            for msg in self.recent_conversation[-8:]:
                role = "User" if msg["direction"] == "in" else "Assistant"
                lines.append(f"  [{role}]: {msg['content'][:120]}")

        return "\n".join(lines)

    def has_groups(self) -> bool:
        return len(self.groups) > 0

    def first_group_id(self) -> Optional[str]:
        return self.groups[0]["id"] if self.groups else None


class AssistantContextService:
    """
    Builds and caches the AssistantContext for a given user.
    Call build() once per assistant request.
    """

    @staticmethod
    def build(user_id: int) -> AssistantContext:
        """
        Build (or return cached) AssistantContext for user_id.
        Must be called inside a Flask app context.
        """
        # Cache hit
        cached = _CONTEXT_CACHE.get(user_id)
        if cached:
            built_at, ctx = cached
            if (datetime.utcnow() - built_at).total_seconds() < _CACHE_TTL_SECONDS:
                return ctx

        try:
            ctx = AssistantContextService._build_fresh(user_id)
            _CONTEXT_CACHE[user_id] = (datetime.utcnow(), ctx)
            return ctx
        except Exception as exc:
            _log.error("AssistantContextService.build failed for user %s: %s", user_id, exc)
            # Return a minimal context so the assistant doesn't crash
            return AssistantContext(
                user_id=user_id,
                full_name="User",
                plan="free",
                timezone="UTC",
                telegram_connected=False,
                telegram_user_id=None,
                joined_days_ago=0,
            )

    @staticmethod
    def invalidate(user_id: int):
        """Invalidate cache after writes (meeting created, note saved, etc.)."""
        _CONTEXT_CACHE.pop(user_id, None)

    @staticmethod
    def _build_fresh(user_id: int) -> AssistantContext:
        from ..models import (
            User, TelegramGroup, Meeting, WorkspaceReminder, Task,
            Note, BotDMMessage, MessageBuffer, DigestLog, AutoReplyLog,
        )

        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # ── User ─────────────────────────────────────────────────────────────
        user = User.query.get(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")

        joined_days = (now - user.created_at).days if user.created_at else 0

        # ── Groups ───────────────────────────────────────────────────────────
        groups_raw = TelegramGroup.query.filter_by(
            owner_user_id=user_id, is_disabled=False
        ).order_by(TelegramGroup.created_at.desc()).limit(10).all()

        group_ids = [g.telegram_group_id for g in groups_raw]

        # Last message time per group
        last_msg_map: dict[str, datetime] = {}
        if group_ids:
            cutoff = now - timedelta(days=7)
            recent_msgs = (
                MessageBuffer.query
                .filter(
                    MessageBuffer.telegram_group_id.in_(group_ids),
                    MessageBuffer.created_at >= cutoff,
                )
                .with_entities(
                    MessageBuffer.telegram_group_id,
                    MessageBuffer.created_at,
                )
                .order_by(MessageBuffer.created_at.desc())
                .all()
            )
            for gid, ts in recent_msgs:
                if gid not in last_msg_map:
                    last_msg_map[gid] = ts

        groups = []
        for g in groups_raw:
            last_msg = last_msg_map.get(g.telegram_group_id)
            is_active = last_msg and (now - last_msg).days < 3
            groups.append({
                "id": g.telegram_group_id,
                "title": g.title or g.telegram_group_id,
                "member_count": getattr(g, "member_count", None),
                "is_active": bool(is_active),
                "last_message_at": last_msg.isoformat() if last_msg else None,
            })

        # ── Upcoming meetings ─────────────────────────────────────────────────
        meetings_raw = (
            Meeting.query
            .filter(
                Meeting.owner_user_id == user_id,
                Meeting.scheduled_at >= now,
                Meeting.is_complete == False,
            )
            .order_by(Meeting.scheduled_at.asc())
            .limit(5)
            .all()
        )
        upcoming_meetings = [
            {
                "id": m.id,
                "title": m.title,
                "scheduled_at_human": m.scheduled_at.strftime("%a %d %b at %I:%M %p UTC"),
                "notes": m.notes,
                "remind_before_minutes": m.remind_before_minutes,
                "resources": m.resources or [],
            }
            for m in meetings_raw
        ]

        # ── Upcoming reminders ────────────────────────────────────────────────
        reminders_raw = (
            WorkspaceReminder.query
            .filter(
                WorkspaceReminder.owner_user_id == user_id,
                WorkspaceReminder.remind_at >= now,
                WorkspaceReminder.is_delivered == False,
            )
            .order_by(WorkspaceReminder.remind_at.asc())
            .limit(5)
            .all()
        )
        upcoming_reminders = [
            {
                "id": r.id,
                "text": r.reminder_text,
                "remind_at_human": r.remind_at.strftime("%a %d %b at %I:%M %p UTC"),
                "remind_at_iso": r.remind_at.isoformat(),
            }
            for r in reminders_raw
        ]

        # ── Pending tasks ─────────────────────────────────────────────────────
        tasks_raw = (
            Task.query
            .filter_by(user_id=user_id, status="todo")
            .order_by(Task.created_at.desc())
            .limit(10)
            .all()
        )
        pending_tasks = [
            {
                "id": t.id,
                "title": t.title,
                "priority": t.priority,
                "due_at_human": t.due_at.strftime("%a %d %b") if t.due_at else None,
            }
            for t in tasks_raw
        ]

        # ── Recent notes ──────────────────────────────────────────────────────
        notes_raw = (
            Note.query
            .filter_by(user_id=user_id)
            .order_by(Note.created_at.desc())
            .limit(5)
            .all()
        )
        recent_notes = [
            {
                "id": n.id,
                "content_preview": n.content[:120],
                "tags": n.tags or [],
                "created_at_human": n.created_at.strftime("%d %b"),
            }
            for n in notes_raw
        ]

        # ── Recent conversation (last 8 BotDMMessage turns) ───────────────────
        conv_raw = (
            BotDMMessage.query
            .filter_by(user_id=user_id)
            .order_by(BotDMMessage.created_at.desc())
            .limit(8)
            .all()
        )
        recent_conversation = [
            {
                "direction": m.direction,
                "content": m.content,
                "intent": m.intent,
                "created_at_human": m.created_at.strftime("%H:%M"),
            }
            for m in reversed(conv_raw)
        ]

        # ── Knowledge docs ────────────────────────────────────────────────────
        knowledge_docs = []
        try:
            from ..models import WorkspaceKnowledgeDocument
            docs_raw = (
                WorkspaceKnowledgeDocument.query
                .filter_by(user_id=user_id, is_active=True)
                .order_by(WorkspaceKnowledgeDocument.created_at.desc())
                .limit(5)
                .all()
            )
            knowledge_docs = [
                {
                    "id": d.id,
                    "title": getattr(d, "title", "Document"),
                    "preview": (getattr(d, "content", "") or "")[:200],
                }
                for d in docs_raw
            ]
        except Exception:
            pass  # Model may not exist in all deployments

        # ── Platform activity today ───────────────────────────────────────────
        platform_today: dict = {}
        try:
            msg_count = (
                MessageBuffer.query
                .filter(
                    MessageBuffer.telegram_group_id.in_(group_ids),
                    MessageBuffer.created_at >= today_start,
                )
                .count()
            ) if group_ids else 0

            auto_count = (
                AutoReplyLog.query
                .filter(
                    AutoReplyLog.user_id == user_id,
                    AutoReplyLog.triggered_at >= today_start,
                )
                .count()
            )

            digest_count = (
                DigestLog.query
                .filter(
                    DigestLog.user_id == user_id,
                    DigestLog.sent_at >= today_start,
                )
                .count()
            )

            platform_today = {
                "messages_received": msg_count,
                "automations_fired": auto_count,
                "digests_sent": digest_count,
            }
        except Exception:
            pass

        return AssistantContext(
            user_id=user_id,
            full_name=user.full_name or "User",
            plan=user.subscription_tier or "free",
            timezone=user.timezone or "UTC",
            telegram_connected=bool(user.telegram_user_id),
            telegram_user_id=user.telegram_user_id,
            joined_days_ago=joined_days,
            groups=groups,
            upcoming_meetings=upcoming_meetings,
            upcoming_reminders=upcoming_reminders,
            pending_tasks=pending_tasks,
            recent_notes=recent_notes,
            recent_conversation=recent_conversation,
            knowledge_docs=knowledge_docs,
            platform_today=platform_today,
            group_alerts=[],  # Populated in Phase 3 via GroupDailySignal
        )
