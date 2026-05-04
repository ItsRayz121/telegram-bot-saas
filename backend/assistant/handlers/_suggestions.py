"""Quick-pick suggestion chip builders."""
from datetime import datetime, timedelta


def time_suggestions() -> list:
    now = datetime.utcnow()
    today_3pm = now.replace(hour=15, minute=0, second=0, microsecond=0)
    today_5pm = now.replace(hour=17, minute=0, second=0, microsecond=0)
    days_to_friday = (4 - now.weekday()) % 7 or 7
    friday_3pm = (now + timedelta(days=days_to_friday)).replace(hour=15, minute=0, second=0, microsecond=0)
    suggestions = []
    if today_3pm > now:
        suggestions.append({"label": "Today 3 PM", "value": "today at 3 PM"})
    if today_5pm > now:
        suggestions.append({"label": "Today 5 PM", "value": "today at 5 PM"})
    suggestions.append({"label": "Tomorrow 9 AM", "value": "tomorrow at 9 AM"})
    suggestions.append({"label": "Tomorrow 3 PM", "value": "tomorrow at 3 PM"})
    suggestions.append({"label": friday_3pm.strftime("Fri %d %b 3 PM"), "value": friday_3pm.strftime("%A at 3 PM")})
    suggestions.append({"label": "Custom time…", "value": None})
    return suggestions


def meeting_title_suggestions() -> list:
    return [
        {"label": "Quick Call", "value": "Quick Call"},
        {"label": "Team Sync", "value": "Team Sync"},
        {"label": "1:1 Meeting", "value": "1:1 Meeting"},
        {"label": "Project Review", "value": "Project Review"},
        {"label": "Investor Call", "value": "Investor Call"},
        {"label": "Other…", "value": None},
    ]


def reminder_suggestions() -> list:
    return [
        {"label": "10 min before", "value": "10 minutes before"},
        {"label": "30 min before", "value": "30 minutes before"},
        {"label": "1 hour before", "value": "1 hour before"},
        {"label": "1 day before", "value": "1 day before"},
        {"label": "No reminder", "value": "no reminder"},
    ]


def skip_suggestions(label: str = "Skip") -> list:
    return [{"label": label, "value": "__skip__"}]


def yes_no_suggestions() -> list:
    return [
        {"label": "Yes, save it", "value": "yes"},
        {"label": "No, cancel", "value": "cancel"},
    ]


def reminder_label(minutes: int | None) -> str:
    if not minutes:
        return "None"
    if minutes < 60:
        return f"{minutes} minutes before"
    if minutes == 60:
        return "1 hour before"
    if minutes < 1440:
        return f"{minutes // 60} hours before"
    return f"{minutes // 1440} day(s) before"
