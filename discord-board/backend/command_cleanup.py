"""Per-command cleanup of slash-command replies (Guildizer: official AND custom bots).

Each server has a command table (guild_settings.extra["command_table"]), one independent row per
command:  {"rank": {"delete_reply": true, "seconds": 30, "enabled": true}, ...}

How it runs
  * When a slash command has been answered, ONE persisted job is created with the deadline
    (answer time + seconds). Jobs live in the command_cleanup_jobs table, so they survive restarts.
  * A fast in-process timer fires it on time; a sweeper in every client recovers overdue jobs and
    claims each with an atomic UPDATE (two workers never delete the same reply twice).
  * The reply is deleted through the interaction webhook (DELETE .../messages/@original). That is the
    only way Discord lets a bot remove a slash-command reply, and it needs no bot permission.

Discord limits, by design
  * "Delete command" is NOT possible: a slash command is an interaction, not a message the bot can
    delete. The table therefore only exposes "Delete reply" on Discord.
  * Interaction tokens last 15 minutes, so the delay is capped at MAX_SECONDS (= 14m50s).
  * Ephemeral replies are only visible to the member and are never touched.

Kill switch: env COMMAND_AUTODELETE_ENABLED=0 stops every deletion at once, no deploy.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta

import aiohttp

from database import SessionLocal
from models import CommandCleanupJob, CustomCommand, GuildSettings

log = logging.getLogger(__name__)

MIN_SECONDS = 1
MAX_SECONDS = 890
DEFAULT_SECONDS = 30
MAX_ATTEMPTS = 5
LEASE_SECONDS = 120
API = "https://discord.com/api/v10"

# (command, module). Replies to moderation commands are ephemeral / evidence and are not offered.
BUILTIN_COMMANDS = [
    ("rank", "XP & Ranking"), ("leaderboard", "XP & Ranking"),
    ("ask", "AI"), ("userinfo", "General"), ("ping", "General"), ("invitelink", "Engagement"),
    ("wallet", "Engagement"), ("mywallet", "Engagement"),
    ("remind", "Automation"), ("reminders", "Automation"), ("note", "Automation"), ("notes", "Automation"),
    ("task", "Automation"), ("tasks", "Automation"), ("done", "Automation"),
    ("warnings", "Moderation"), ("report", "Moderation"),
]
_BUILTIN = dict(BUILTIN_COMMANDS)


def enabled() -> bool:
    return os.environ.get("COMMAND_AUTODELETE_ENABLED", "1").strip().lower() not in ("0", "false", "off", "no")


# ── configuration ───────────────────────────────────────────────────────────────

def normalize_row(raw) -> dict:
    """Validated row from user input. Raises ValueError on a malformed row."""
    if not isinstance(raw, dict):
        raise ValueError("row must be an object")
    try:
        seconds = int(raw.get("seconds", DEFAULT_SECONDS))
    except (TypeError, ValueError):
        raise ValueError("seconds must be a whole number")
    if seconds < MIN_SECONDS or seconds > MAX_SECONDS:
        raise ValueError(f"seconds must be between {MIN_SECONDS} and {MAX_SECONDS}")
    return {"delete_command": False,   # unsupported on Discord (see module docstring)
            "delete_reply": bool(raw.get("delete_reply", True)),
            "seconds": seconds, "enabled": bool(raw.get("enabled", True))}


def _legacy_seconds(l2: dict, command: str) -> int:
    def clamp(v):
        try:
            return max(0, min(int(v or 0), MAX_SECONDS))
        except (TypeError, ValueError):
            return 0
    generic = clamp(l2.get("command_reply_delete_after_seconds"))
    if command == "leaderboard":
        return clamp(l2.get("leaderboard_delete_after_seconds")) or generic
    return generic


def resolve_row(extra: dict | None, command: str) -> dict:
    """Saved row, else the legacy per-server delay (0 = keep) so nothing changes until a row is saved."""
    extra = extra or {}
    raw = (extra.get("command_table") or {}).get(command)
    if isinstance(raw, dict):
        try:
            return normalize_row(raw)
        except ValueError:
            pass
    secs = _legacy_seconds(extra.get("leveling2") or {}, command)
    return {"delete_command": False, "delete_reply": secs > 0,
            "seconds": secs or DEFAULT_SECONDS, "enabled": True}


def is_command_enabled(extra: dict | None, command: str) -> bool:
    raw = ((extra or {}).get("command_table") or {}).get(command)
    return not (isinstance(raw, dict) and raw.get("enabled") is False)


def command_rows(extra: dict | None, custom_names=()) -> list[dict]:
    rows = []
    for name, module in list(BUILTIN_COMMANDS) + [(n, "Custom commands") for n in custom_names]:
        row = resolve_row(extra, name)
        rows.append({"command": f"/{name}", "module": module, **row,
                     "configured": name in ((extra or {}).get("command_table") or {})})
    return rows


def apply_table(extra: dict | None, rows, custom_names=()) -> dict:
    """Merge submitted rows into a copy of `extra`; other commands keep their own rows."""
    if not isinstance(rows, list):
        raise ValueError("commands must be a list")
    valid = set(_BUILTIN) | set(custom_names)
    out = dict(extra or {})
    table = dict(out.get("command_table") or {})
    for item in rows:
        if not isinstance(item, dict):
            raise ValueError("each command must be an object")
        name = str(item.get("command") or "").lstrip("/").lower()
        if name not in valid:
            raise ValueError(f"unknown command: {item.get('command')}")
        table[name] = normalize_row(item)
    out["command_table"] = table
    return out


# ── reading settings / registering jobs ─────────────────────────────────────────

def row_for(guild_id, command) -> dict | None:
    """The row to apply for this answered command, or None when no cleanup is configured."""
    if guild_id is None or not command or not enabled():
        return None
    db = SessionLocal()
    try:
        gs = db.get(GuildSettings, int(guild_id))
        row = resolve_row(gs.extra if gs else {}, command)
        return row if row["delete_reply"] else None
    except Exception:  # noqa: BLE001
        return None
    finally:
        db.close()
        SessionLocal.remove()


def custom_command_names(db, guild_id) -> list[str]:
    return [c.name for c in db.query(CustomCommand).filter_by(guild_id=int(guild_id)).all()]


def command_enabled(guild_id, command) -> bool:
    if guild_id is None:
        return True
    db = SessionLocal()
    try:
        gs = db.get(GuildSettings, int(guild_id))
        return is_command_enabled(gs.extra if gs else {}, command)
    except Exception:  # noqa: BLE001
        return True
    finally:
        db.close()
        SessionLocal.remove()


def create_job(bot_ref, guild_id, command, application_id, token, deliver_at) -> int:
    db = SessionLocal()
    try:
        job = CommandCleanupJob(bot_ref=str(bot_ref), guild_id=int(guild_id), command=command,
                                application_id=str(application_id), token=token, deliver_at=deliver_at)
        db.add(job)
        db.commit()
        return job.id
    finally:
        db.close()
        SessionLocal.remove()


def claim(job_id) -> dict | None:
    """Atomically take a due job. Returns its data or None when someone else has it / not due."""
    now = datetime.utcnow()
    db = SessionLocal()
    try:
        from sqlalchemy import and_, or_
        n = db.query(CommandCleanupJob).filter(
            CommandCleanupJob.id == job_id, CommandCleanupJob.deliver_at <= now,
            or_(CommandCleanupJob.status == "pending",
                and_(CommandCleanupJob.status == "claimed", CommandCleanupJob.claimed_until < now)),
        ).update({"status": "claimed", "claimed_until": now + timedelta(seconds=LEASE_SECONDS),
                  "attempts": CommandCleanupJob.attempts + 1}, synchronize_session=False)
        db.commit()
        if not n:
            return None
        job = db.get(CommandCleanupJob, job_id)
        return {"application_id": job.application_id, "token": job.token, "attempts": job.attempts,
                "deliver_at": job.deliver_at}
    finally:
        db.close()
        SessionLocal.remove()


def settle(job_id, status, error=None, retry_in=None) -> None:
    db = SessionLocal()
    try:
        job = db.get(CommandCleanupJob, job_id)
        if job is None:
            return
        job.last_error = (error or "")[:255] or None
        job.claimed_until = None
        if retry_in is not None:
            job.status = "pending"
            job.deliver_at = datetime.utcnow() + timedelta(seconds=retry_in)
        else:
            job.status = status
            job.token = None       # the token is a credential for the reply; drop it once finished
        db.commit()
    finally:
        db.close()
        SessionLocal.remove()


def due_ids(bot_ref) -> list[int]:
    now = datetime.utcnow()
    db = SessionLocal()
    try:
        from sqlalchemy import and_, or_
        rows = db.query(CommandCleanupJob).filter(
            CommandCleanupJob.bot_ref == str(bot_ref), CommandCleanupJob.deliver_at <= now,
            or_(CommandCleanupJob.status == "pending",
                and_(CommandCleanupJob.status == "claimed", CommandCleanupJob.claimed_until < now)),
        ).order_by(CommandCleanupJob.deliver_at).limit(200).all()
        return [r.id for r in rows]
    finally:
        db.close()
        SessionLocal.remove()


def recent_failures(guild_id) -> int:
    db = SessionLocal()
    try:
        return db.query(CommandCleanupJob).filter(
            CommandCleanupJob.guild_id == int(guild_id), CommandCleanupJob.status == "failed",
            CommandCleanupJob.deliver_at > datetime.utcnow() - timedelta(hours=24)).count()
    finally:
        db.close()
        SessionLocal.remove()


# ── executing ───────────────────────────────────────────────────────────────────

async def _delete_original(app_id: str, token: str, session=None) -> str:
    """'done' | 'skip' (ephemeral / gone) | 'retry' | 'expired'."""
    url = f"{API}/webhooks/{app_id}/{token}/messages/@original"
    own = session is None
    session = session or aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))
    try:
        async with session.get(url) as r:
            if r.status in (401, 404):
                return "expired" if r.status == 401 else "skip"
            if r.status == 429 or r.status >= 500:
                return "retry"
            body = await r.json(content_type=None)
            if int((body or {}).get("flags") or 0) & 64:
                return "skip"                    # ephemeral: only the member sees it
        async with session.delete(url) as r:
            if r.status in (200, 204, 404):
                return "done"
            if r.status in (401, 403):
                return "expired"
            return "retry"
    except Exception:  # noqa: BLE001 - network trouble: try again
        return "retry"
    finally:
        if own:
            await session.close()


async def execute(job_id, deleter=None) -> None:
    """Run one due job. Never raises."""
    try:
        if not enabled():
            return
        job = await asyncio.to_thread(claim, job_id)
        if not job:
            return
        deleter = deleter or _delete_original
        outcome = await deleter(job["application_id"], job["token"])
        if outcome == "retry" and job["attempts"] < MAX_ATTEMPTS:
            await asyncio.to_thread(settle, job_id, None, "retrying", min(30 * 2 ** (job["attempts"] - 1), 300))
        elif outcome == "retry":
            await asyncio.to_thread(settle, job_id, "failed", "Discord kept refusing the delete")
        elif outcome == "expired":
            await asyncio.to_thread(settle, job_id, "failed", "the interaction expired before the delete")
        else:
            await asyncio.to_thread(settle, job_id, "done")
    except Exception:  # noqa: BLE001
        log.debug("command cleanup job %s failed", job_id, exc_info=True)


async def run_at(job_id, deliver_at) -> None:
    wait = (deliver_at - datetime.utcnow()).total_seconds()
    if wait > 0:
        await asyncio.sleep(wait)
    await execute(job_id)


async def sweep_once(bot_ref) -> int:
    """Run every overdue job of this bot identity (restart recovery)."""
    ids = await asyncio.to_thread(due_ids, bot_ref)
    for jid in ids:
        await execute(jid)
    return len(ids)


async def schedule_for_interaction(interaction, command: str) -> int | None:
    """Called when a slash command finished answering. Creates the persisted job and its timer.
    Returns the job id, or None when nothing is configured. Never raises."""
    try:
        if interaction.guild_id is None:
            return None
        row = await asyncio.to_thread(row_for, interaction.guild_id, command)
        if row is None:
            return None
        deliver_at = datetime.utcnow() + timedelta(seconds=row["seconds"])
        job_id = await asyncio.to_thread(
            create_job, interaction.application_id, interaction.guild_id, command,
            interaction.application_id, interaction.token, deliver_at)
        asyncio.ensure_future(run_at(job_id, deliver_at))
        return job_id
    except Exception:  # noqa: BLE001
        log.debug("command cleanup skipped", exc_info=True)
        return None
