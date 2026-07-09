"""
Export / import of a group's bot configuration as a portable JSON file.

The export file is meant to be handed to another person, so it must never carry
anything private or anything that only makes sense inside the source group:

  • Secrets      — AI keys, webhook URLs and bot tokens live in their own tables
                   (UserApiKey, Webhook, Bot), never in TelegramGroup.settings.
                   `assert_no_secrets()` re-checks that at export time so a future
                   settings key holding a credential can't silently start leaking.
  • Bindings     — channel / topic / admin IDs. Valid only in the source group;
                   importing them elsewhere would point moderation at chats that
                   don't exist. Stripped on export, listed for the UI, never applied.

Import is a deep-merge (keys absent from the file keep their current value) and
is plan-aware: a Pro section arriving on a Free plan is kept but forced to
enabled=False, so the config is already in place if the user later upgrades.
"""

import copy
import re
from datetime import datetime, timezone

SCHEMA_VERSION = 1
PRODUCT = "telegizer"

# Dotted paths that identify a chat, topic, channel or admin inside the SOURCE
# group. Never exported, never imported. `*` matches one path segment.
BINDING_PATHS = (
    "verification.destination_topic_id",
    "verification.destination_chat_id",
    "welcome.topic_id",
    "levels.levelup_topic_id",
    "moderation.log_channel_id",
    "moderation.log_to_channel",
    "reports.selected_admin_ids",
    "escalation.admin_ids",
    "escalation.admins",
    "image_ai.escalation_admin_ids",
    "automod.smart_mod.group_topic",
    "command_routing.topics",
    "command_routing.commands.*.topic_ids",
    "topics",
    "default_topic_id",
)

# Any settings key matching this is a credential and must never reach the file.
# Belt-and-braces: no current key matches. If one is ever added, export raises
# instead of quietly writing a secret into a file the user is about to share.
_SECRET_KEY_RE = re.compile(
    r"(api[_-]?key|secret|password|passwd|bot[_-]?token|access[_-]?token|"
    r"webhook[_-]?url|private[_-]?key|credential)",
    re.IGNORECASE,
)

# Top-level sections that are meaningful to move between groups. Anything else
# in settings (runtime scratch written by the bot) is dropped on export.
EXPORTABLE_SECTIONS = (
    "verification", "welcome", "levels", "automod", "moderation",
    "warning_escalation", "auto_clean", "reports", "knowledge_base",
    "auto_responses", "escalation", "image_ai", "social_replies",
    "reactions", "raids", "digest", "admin_alerts", "command_routing",
    "bot_policy", "raid_guard", "assistant", "timezone",
)


class SecretLeakError(RuntimeError):
    """A settings key looked like a credential. Refuse to export."""


def _iter_leaf_paths(node, prefix=""):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _iter_leaf_paths(value, f"{prefix}.{key}" if prefix else key)
    else:
        yield prefix, node


def assert_no_secrets(settings: dict) -> None:
    for path, _ in _iter_leaf_paths(settings):
        leaf = path.rsplit(".", 1)[-1]
        if _SECRET_KEY_RE.search(leaf):
            raise SecretLeakError(
                f"Refusing to export: settings key '{path}' looks like a credential. "
                f"Add it to the export blocklist or move it out of group settings."
            )


def _split(path):
    return path.split(".")


def _pop_path(node, segments):
    """Remove `segments` from `node`. Returns [(full_path, value)] for what was removed."""
    head, rest = segments[0], segments[1:]

    if head == "*":
        if not isinstance(node, dict):
            return []
        removed = []
        for key, child in node.items():
            for sub_path, value in _pop_path(child, rest):
                removed.append((f"{key}.{sub_path}" if sub_path else key, value))
        return removed

    if not isinstance(node, dict) or head not in node:
        return []

    if not rest:
        return [(head, node.pop(head))]

    removed = []
    for sub_path, value in _pop_path(node[head], rest):
        removed.append((f"{head}.{sub_path}", value))
    return removed


def strip_bindings(settings: dict):
    """Remove every BINDING_PATHS entry in-place. Returns the list of paths removed.

    Only paths that were actually present AND carried a non-empty value are
    reported, so the UI doesn't tell the user we skipped a channel binding they
    never set.
    """
    stripped = []
    for path in BINDING_PATHS:
        for removed_path, value in _pop_path(settings, _split(path)):
            if value not in (None, "", [], {}, False):
                stripped.append(removed_path)

    # "Notify selected admins" is a mode, not a binding — but the IDs it points at
    # just left with the bindings. Without this it would silently notify nobody.
    reports = settings.get("reports")
    if isinstance(reports, dict) and reports.get("notify_admins") == "selected":
        reports["notify_admins"] = "all"

    return sorted(set(stripped))


def build_export(settings: dict, *, group_title: str = "", scope: str = "official") -> dict:
    """Serialize a group's settings into the portable envelope."""
    source = copy.deepcopy(dict(settings or {}))
    assert_no_secrets(source)

    payload = {k: v for k, v in source.items() if k in EXPORTABLE_SECTIONS}
    stripped = strip_bindings(payload)

    return {
        "telegizer_settings_export": {
            "schema_version": SCHEMA_VERSION,
            "product": PRODUCT,
            "scope": scope,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "source_group": group_title or "",
            "bindings_excluded": stripped,
        },
        "settings": payload,
    }


def parse_export(raw: dict):
    """Validate an uploaded file. Returns (settings, error_message)."""
    if not isinstance(raw, dict):
        return None, "That file isn't a valid settings export."

    meta = raw.get("telegizer_settings_export")
    if not isinstance(meta, dict):
        return None, "That file isn't a Telegizer settings export."

    if meta.get("product") != PRODUCT:
        other = meta.get("product") or "another product"
        return None, f"That file was exported from {other}, not Telegizer."

    version = meta.get("schema_version")
    if version != SCHEMA_VERSION:
        return None, (
            f"That file uses settings format v{version}, but this version of "
            f"Telegizer reads v{SCHEMA_VERSION}."
        )

    settings = raw.get("settings")
    if not isinstance(settings, dict) or not settings:
        return None, "That export file has no settings in it."

    unknown = set(settings) - set(EXPORTABLE_SECTIONS)
    if unknown:
        return None, f"That file has settings we don't recognise: {', '.join(sorted(unknown))}"

    # An older file, or a hand-edited one, may still carry bindings. Drop them
    # here too — import must never trust the file.
    incoming = copy.deepcopy(settings)
    strip_bindings(incoming)
    return incoming, None


MAX_DEPTH = 10


def diff_settings(current: dict, incoming: dict, _prefix="", _depth: int = 0):
    """Leaf-level changes the import would make. Returns [{path, from, to}].

    A subtree the target doesn't have yet still reports one row per leaf, so the
    preview never shows the user a raw nested object to interpret. Depth-capped
    like the plan gate, so a hand-edited file can't nest its way into a
    RecursionError.
    """
    changes = []
    for key, new_value in incoming.items():
        path = f"{_prefix}.{key}" if _prefix else key
        old_value = (current or {}).get(key)
        if (isinstance(new_value, dict) and isinstance(old_value, (dict, type(None)))
                and _depth < MAX_DEPTH):
            changes.extend(diff_settings(old_value or {}, new_value, path, _depth + 1))
        elif old_value != new_value:
            changes.append({"path": path, "from": old_value, "to": new_value})
    return changes
