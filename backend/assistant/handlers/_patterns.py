"""Compiled regex patterns for keyword-based intent detection."""
import re

SCHEDULE_PATTERNS = re.compile(
    r"\b(schedul|book|set up|create|add|save|plan|arrange|organis|organiz|set a meeting|set meeting"
    r"|new meeting|make a meeting|can you schedule|new call|set a call)\b",
    re.IGNORECASE,
)
MEETING_NOUN = re.compile(
    r"\b(meeting|call|standup|stand.?up|sync|catchup|catch.?up|session|appointment|interview|demo|webinar|event)\b",
    re.IGNORECASE,
)
LIST_MEETINGS_PATTERNS = re.compile(
    r"\b(any meetings?|what meetings?|my meetings?|show meetings?|list meetings?|next meeting"
    r"|meetings? today|meetings? tomorrow|do i have.*meeting|meeting scheduled|scheduled.*meeting"
    r"|upcoming meeting|got a meeting|have a meeting)\b",
    re.IGNORECASE,
)
UPCOMING_SCHEDULE_PATTERNS = re.compile(
    r"\b(upcoming|my schedule|check my calendar|what.?s next|what.?s today|what.?s on|schedule today"
    r"|schedule tomorrow|important.*upcoming|any important|timeline|what do i have|anything today)\b",
    re.IGNORECASE,
)
CREATE_REMINDER_PATTERNS = re.compile(
    r"\b(remind me|set a reminder|create reminder|add reminder|new reminder|remind me about|remind me to)\b",
    re.IGNORECASE,
)
LIST_REMINDERS_PATTERNS = re.compile(
    r"\b(my reminders|show reminders|list reminders|upcoming reminders|any reminders|what reminders|see reminders)\b",
    re.IGNORECASE,
)
GROUP_PATTERNS = re.compile(
    r"\b(group|groups|community|communities|members|moderation|spam|group activity|group summary)\b",
    re.IGNORECASE,
)
GROUP_ISSUE_SIGNALS = re.compile(
    r"\b(issue|problem|spam|going on|activity|summary|happening|trouble|concern|report|status|check|any major)\b",
    re.IGNORECASE,
)
SAVE_NOTE_PATTERNS = re.compile(
    r"\b(note this|note:|save this as|save as note|remember this|jot this|write this down|log this"
    r"|save this note|quick note|add note|make a note)\b",
    re.IGNORECASE,
)
LIST_NOTES_PATTERNS = re.compile(
    r"\b(my notes|show notes|list notes|what notes|see notes|view notes|recent notes|saved notes|get my notes)\b",
    re.IGNORECASE,
)
SAVE_LINK_PATTERNS = re.compile(
    r"\b(save.*link|save.*url|save.*http|remember.*link|bookmark|save for later|keep this link|save this link)\b",
    re.IGNORECASE,
)
CREATE_TASK_PATTERNS = re.compile(
    r"\b(create task|add task|new task|task:|to do:|todo:|add to.{0,10}task|add.{0,10}to my list"
    r"|i need to|don.t forget to)\b",
    re.IGNORECASE,
)
LIST_TASKS_PATTERNS = re.compile(
    r"\b(my tasks|show tasks|list tasks|pending tasks|what tasks|see tasks|open tasks|to.do list)\b",
    re.IGNORECASE,
)
ANALYZE_DAY_PATTERNS = re.compile(
    r"\b(analyze my day|analyse my day|day analysis|what.?s my day look like|how.?s my day"
    r"|daily overview|daily summary|summarize my day|summarise my day|what do i have today"
    r"|review my day|day review|what.?s going on today|brief me|give me a briefing"
    r"|analyze my work|analyse my work|workspace overview|what should i focus on)\b",
    re.IGNORECASE,
)

CANCEL_PATTERNS = re.compile(
    r"^(cancel|stop|nevermind|never mind|forget it|abort|quit|exit|no thanks|nope|no)\s*[.!]?$",
    re.IGNORECASE,
)
CONFIRM_YES_PATTERNS = re.compile(
    r"^(yes|yeah|yep|yup|ok|okay|sure|confirm|save it|go ahead|do it|save|correct|right|looks good|perfect)\s*[.!]?$",
    re.IGNORECASE,
)

SKIP_VALUE = "__skip__"
