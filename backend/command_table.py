"""Command management table (Telegram): one row per command with access scope, the two cleanup
toggles, the delay and the status switch. Shared by the official-bot and custom-bot routes.

Storage inside the group's settings JSON (nothing new to migrate for settings):
  command_table[<cmd>]            -> {delete_command, delete_reply, seconds, enabled}   (command_cleanup)
  command_routing.commands[/cmd]  -> {scope: all_group|specific_topics, topic_ids: []}  (existing routing)
"""
from . import command_cleanup as cc

# (command, module). Moderation commands stay out: their replies are evidence / already self-clean.
TELEGRAM_COMMANDS = [
    ("xp", "XP & Ranking"), ("rank", "XP & Ranking"), ("leaderboard", "XP & Ranking"),
    ("me", "XP & Ranking"), ("level", "XP & Ranking"),
    ("roles", "Roles"),
    ("help", "General"), ("rules", "General"), ("stats", "General"), ("status", "General"),
    ("admins", "General"), ("whois", "General"), ("groupinfo", "General"), ("warnings", "General"),
    ("invitelink", "Engagement"), ("wallet", "Engagement"), ("remind", "Automation"),
    ("ask", "AI"), ("assist", "AI"), ("report", "Moderation"),
]
_MODULE = dict(TELEGRAM_COMMANDS)


def _routing_rule(routing, cmd):
    cmds = (routing or {}).get("commands") or {}
    keys = [f"/{cmd}", cmd] + [f"/{k}" for k, v in cc.ALIASES.items() if v == cmd]
    for key in keys:
        if isinstance(cmds.get(key), dict):
            return cmds[key]
    return {}


def build_table(settings):
    """Resolved rows for every known command (saved row, else the legacy mapping)."""
    settings = settings or {}
    routing = settings.get("command_routing") or {}
    saved = settings.get("command_table") or {}
    rows = []
    for cmd, module in TELEGRAM_COMMANDS:
        row = cc.resolve_row(settings, cmd)
        rule = _routing_rule(routing, cmd)
        scope = rule.get("scope", "all_group")
        rows.append({
            "command": f"/{cmd}", "module": module,
            "scope": "specific_topics" if scope == "specific_topics" else "all_group",
            "topic_ids": [str(t) for t in (rule.get("topic_ids") or [])],
            "delete_command": row["delete_command"], "delete_reply": row["delete_reply"],
            "seconds": row["seconds"], "enabled": row["enabled"] and scope != "disabled",
            "configured": isinstance(saved, dict) and cmd in saved,
        })
    return {"commands": rows, "topics": (routing.get("topics") or []),
            "limits": {"min_seconds": cc.MIN_SECONDS, "max_seconds": cc.MAX_SECONDS,
                       "can_delete_command": True}}


def apply_table(settings, rows):
    """Merge submitted rows into a copy of `settings`. Raises ValueError on invalid input.
    Only the submitted commands change; every other command keeps its own row."""
    if not isinstance(rows, list):
        raise ValueError("commands must be a list")
    current = dict(settings or {})
    table = dict(current.get("command_table") or {})
    routing = dict(current.get("command_routing") or {})
    rcmds = dict(routing.get("commands") or {})
    for item in rows:
        if not isinstance(item, dict):
            raise ValueError("each command must be an object")
        cmd = cc.canon(item.get("command"))
        if cmd not in _MODULE:
            raise ValueError(f"unknown command: {item.get('command')}")
        table[cmd] = cc.normalize_row(item)
        scope = item.get("scope", "all_group")
        if scope not in ("all_group", "specific_topics"):
            raise ValueError("invalid access scope")
        topic_ids = [str(t) for t in (item.get("topic_ids") or [])][:50]
        for alias, target in cc.ALIASES.items():   # drop stale alias keys so one rule wins
            if target == cmd:
                rcmds.pop(f"/{alias}", None)
        rcmds[f"/{cmd}"] = {"scope": scope, "topic_ids": topic_ids if scope == "specific_topics" else []}
    routing["commands"] = rcmds
    current["command_table"] = table
    current["command_routing"] = routing
    return current


def recent_failures(chat_ids):
    """Count of cleanup jobs that failed in the last 24h because the bot may not delete messages."""
    from datetime import datetime, timedelta
    from .models import CommandCleanupJob
    return CommandCleanupJob.query.filter(
        CommandCleanupJob.scope_id.in_([str(c) for c in chat_ids]), CommandCleanupJob.status == "failed",
        CommandCleanupJob.deliver_at > datetime.utcnow() - timedelta(hours=24)).count()
