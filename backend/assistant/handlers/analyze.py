"""
Analyze My Day — deep AI analysis of the user's entire workspace.

Aggregates meetings, tasks, notes, reminders, groups and generates:
- A plain-language daily summary
- Gap analysis (what's missing)
- Risk flags (overdue, no follow-ups)
- Ranked recommendations

This is the highest-value assistant intent — it should feel like a
chief of staff reviewing your day and telling you what matters.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

_log = logging.getLogger(__name__)


def handle_analyze_day(user_id: int, key_info: dict) -> dict:
    from ...models import (
        Meeting, WorkspaceReminder, Note, WorkspaceTask, TelegramGroup,
        GroupDailySignal,
    )
    from datetime import date

    now = datetime.utcnow()
    today = date.today()
    today_start = datetime(now.year, now.month, now.day)
    today_end = today_start + timedelta(hours=23, minutes=59)
    this_week_end = today_start + timedelta(days=7)

    # ── Gather all data ───────────────────────────────────────────────────────
    meetings_today = Meeting.query.filter(
        Meeting.owner_user_id == user_id,
        Meeting.scheduled_at >= today_start,
        Meeting.scheduled_at <= today_end,
        Meeting.is_complete == False,
    ).order_by(Meeting.scheduled_at).all()

    meetings_week = Meeting.query.filter(
        Meeting.owner_user_id == user_id,
        Meeting.scheduled_at > today_end,
        Meeting.scheduled_at <= this_week_end,
        Meeting.is_complete == False,
    ).order_by(Meeting.scheduled_at).all()

    overdue_meetings = Meeting.query.filter(
        Meeting.owner_user_id == user_id,
        Meeting.scheduled_at < today_start,
        Meeting.is_complete == False,
    ).count()

    tasks_todo = WorkspaceTask.query.filter_by(
        user_id=user_id, status="todo"
    ).order_by(WorkspaceTask.created_at.desc()).all()

    tasks_doing = WorkspaceTask.query.filter_by(
        user_id=user_id, status="doing"
    ).all()

    tasks_high = [t for t in tasks_todo if t.priority == "high"]

    reminders_today = WorkspaceReminder.query.filter(
        WorkspaceReminder.user_id == user_id,
        WorkspaceReminder.remind_at >= today_start,
        WorkspaceReminder.remind_at <= today_end,
        WorkspaceReminder.is_sent == False,
    ).all()

    reminders_overdue = WorkspaceReminder.query.filter(
        WorkspaceReminder.user_id == user_id,
        WorkspaceReminder.remind_at < today_start,
        WorkspaceReminder.is_sent == False,
    ).count()

    recent_notes = Note.query.filter_by(user_id=user_id).order_by(
        Note.created_at.desc()
    ).limit(5).all()

    groups = TelegramGroup.query.filter_by(
        owner_user_id=user_id, is_disabled=False
    ).all()
    group_alerts = []
    for g in groups:
        sig = GroupDailySignal.query.filter_by(
            telegram_group_id=g.telegram_group_id, date=today
        ).first()
        if sig and sig.health_status in ("watch", "critical"):
            group_alerts.append({
                "title": g.title or g.telegram_group_id,
                "status": sig.health_status,
                "spam": sig.spam_score,
                "conflict": sig.conflict_score,
            })

    # ── Build structured analysis ─────────────────────────────────────────────
    insights = []
    gaps = []
    risks = []
    recommendations = []

    # Insights
    if meetings_today:
        insights.append(f"📅 {len(meetings_today)} meeting(s) today")
    if tasks_doing:
        insights.append(f"⚙️ {len(tasks_doing)} task(s) in progress")
    if reminders_today:
        insights.append(f"🔔 {len(reminders_today)} reminder(s) due today")
    if recent_notes:
        insights.append(f"📝 {len(recent_notes)} recent notes saved")
    if groups:
        insights.append(f"👥 {len(groups)} group(s) connected")

    # Gaps
    if meetings_today and not tasks_todo:
        gaps.append("You have meetings but no tasks — consider creating follow-up action items")
    if meetings_today and not recent_notes:
        gaps.append("No notes saved recently — consider capturing key decisions from meetings")
    if tasks_todo and len(tasks_todo) > 10:
        gaps.append(f"Task backlog is large ({len(tasks_todo)} to-do items) — prioritise or defer some")
    if not meetings_today and not tasks_todo and not reminders_today:
        gaps.append("Nothing scheduled today — good time to plan the week ahead")

    # Risks
    if overdue_meetings:
        risks.append(f"⚠️ {overdue_meetings} overdue meeting(s) not marked complete")
    if reminders_overdue:
        risks.append(f"⚠️ {reminders_overdue} overdue reminder(s) — review and dismiss or reschedule")
    if tasks_high:
        risks.append(f"🔴 {len(tasks_high)} high-priority task(s) not started")
    for alert in group_alerts:
        risks.append(f"🚨 Group '{alert['title']}' is {alert['status']} (spam: {alert['spam']:.1f}, conflict: {alert['conflict']:.1f})")

    # Recommendations (ranked by urgency)
    if risks:
        recommendations.append("Address risks first — overdue items block everything downstream")
    if meetings_today and not any("follow-up" in g.lower() or "task" in g.lower() for g in gaps):
        for m in meetings_today[:2]:
            recommendations.append(f"Before '{m.title}' — review agenda and prepare notes")
    if tasks_high:
        recommendations.append(f"Start with your {len(tasks_high)} high-priority task(s) before meetings")
    if gaps:
        recommendations.append(gaps[0])
    if meetings_week:
        recommendations.append(f"Plan for {len(meetings_week)} meeting(s) later this week")
    if group_alerts:
        recommendations.append("Check your group health dashboard — some groups need attention")

    # ── AI synthesis (if key available) ──────────────────────────────────────
    ai_narrative = None
    if key_info.get("api_key") and (insights or risks or recommendations):
        try:
            from ._ai import call_ai_text
            context_lines = []
            if meetings_today:
                context_lines.append(f"Meetings today: {', '.join(m.title for m in meetings_today)}")
            if tasks_doing:
                context_lines.append(f"In-progress tasks: {', '.join(t.title for t in tasks_doing[:3])}")
            if tasks_high:
                context_lines.append(f"High-priority tasks: {', '.join(t.title for t in tasks_high[:3])}")
            if risks:
                context_lines.append(f"Risks: {'; '.join(risks)}")
            if gaps:
                context_lines.append(f"Gaps: {'; '.join(gaps)}")

            prompt = (
                f"Today's workspace snapshot for the user:\n"
                + "\n".join(context_lines)
                + "\n\nWrite a 2-3 sentence daily briefing as a sharp chief of staff would. "
                "Be direct, specific, and action-oriented. No filler words."
            )
            from ._prompts import GENERAL_AI_SYSTEM
            ai_narrative = call_ai_text(key_info, GENERAL_AI_SYSTEM, prompt)
        except Exception as exc:
            _log.warning("analyze_day AI narrative failed: %s", exc)

    # ── Build reply ───────────────────────────────────────────────────────────
    sections = []

    if ai_narrative:
        sections.append(ai_narrative)
        sections.append("")

    if insights:
        sections.append("**📊 Today at a glance**")
        sections.extend(f"  {i}" for i in insights)

    if risks:
        sections.append("\n**🚨 Needs attention**")
        sections.extend(f"  {r}" for r in risks)

    if gaps:
        sections.append("\n**🔍 Gaps detected**")
        sections.extend(f"  • {g}" for g in gaps)

    if recommendations:
        sections.append("\n**✅ Recommended actions**")
        for i, r in enumerate(recommendations[:4], 1):
            sections.append(f"  {i}. {r}")

    if not sections:
        sections.append("Your workspace looks clear today — nothing urgent. Good time to plan ahead or review your notes.")

    reply = "\n".join(sections)

    # Smart suggestions based on analysis
    suggestions = []
    if meetings_today:
        suggestions.append({"label": "📋 Add meeting notes", "value": f"Add notes to {meetings_today[0].title}"})
    if tasks_high:
        suggestions.append({"label": "🔴 View high-priority tasks", "value": "Show my tasks"})
    if not tasks_todo:
        suggestions.append({"label": "➕ Create a task", "value": "Create task"})
    if group_alerts:
        suggestions.append({"label": "👥 Check group health", "value": "Any issues in my groups?"})
    if len(suggestions) < 2:
        suggestions.append({"label": "📅 What's next?", "value": "What's on my schedule?"})

    return {
        "reply": reply,
        "intent": "analyze_day",
        "data": {
            "meetings_today": len(meetings_today),
            "tasks_todo": len(tasks_todo),
            "tasks_doing": len(tasks_doing),
            "risks": len(risks),
            "gaps": len(gaps),
            "group_alerts": len(group_alerts),
        },
        "suggestions": suggestions[:3],
    }
