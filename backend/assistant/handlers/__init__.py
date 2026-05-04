# Assistant handler modules — re-export public API
from .meeting import handle_schedule_meeting
from .reminder import handle_create_reminder
from .schedule import handle_upcoming_schedule
from .notes import handle_save_note, handle_list_notes, handle_search_notes, handle_summarize_notes, handle_save_link
from .tasks import handle_create_task, handle_list_tasks, handle_list_meetings, handle_list_reminders
from .groups import handle_group_query
from .general import handle_general, handle_add_resource, attach_resource
from .state_machine import handle_continue_state
from .analyze import handle_analyze_day

__all__ = [
    "handle_schedule_meeting",
    "handle_create_reminder",
    "handle_upcoming_schedule",
    "handle_save_note", "handle_list_notes", "handle_search_notes", "handle_summarize_notes", "handle_save_link",
    "handle_create_task", "handle_list_tasks", "handle_list_meetings", "handle_list_reminders",
    "handle_group_query",
    "handle_general", "handle_add_resource", "attach_resource",
    "handle_continue_state",
    "handle_analyze_day",
]
