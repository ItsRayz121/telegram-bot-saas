"""Native Discord AutoMod sync. Both lineages.

Mirrors the dashboard's custom blocked words (ModerationSettings.cf_custom_words)
into one Discord-managed AutoMod keyword rule, so those words stay blocked even
when the bot is offline. Optionally also blocks discord.gg invite links natively.

Config + sync state live in ModerationSettings.extra["automod"]["native_sync"]
(self-heals, no migration). The dashboard PUT flips `dirty`; the bot's 20s post
loop reconciles dirty guilds: create/edit/delete the managed rule, then write
back rule_id / last_synced_at / last_error and clear the flag. Only the keys in
EXTRA_DEFAULTS are dashboard-writable — the state keys are bot-owned.

Needs the Manage Server permission; a missing permission or Discord's rule cap
is reported back to the dashboard via last_error instead of raising.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

import discord

from database import SessionLocal
from models import ModerationSettings

log = logging.getLogger("guildizer.automod_sync")

RULE_NAME = "Guildizer · Banned words"
BLOCK_MESSAGE = "Blocked by the server's banned-words filter (Guildizer)."

# Discord caps keyword_filter at 1000 entries of <=60 chars; cf_custom_words is
# capped at 50 words of <=40 chars upstream, so the only hard limit that can
# realistically bite is the per-guild rule count (HTTPException, surfaced).
_MAX_KEYWORDS = 1000
_INVITE_PATTERNS = [
    "*discord.gg/*",
    "*discord.com/invite/*",
    "*discordapp.com/invite/*",
]


def _merged(extra: dict | None) -> dict:
    return dict(((extra or {}).get("automod") or {}).get("native_sync") or {})


# ── storage helpers (sync — call via to_thread) ────────────────────────────────
def pending_guilds() -> list[int]:
    """Guild ids whose native_sync config changed since the last reconcile.
    Cheap at current fleet size; rows without the section are skipped fast."""
    out: list[int] = []
    db = SessionLocal()
    try:
        rows = (
            db.query(ModerationSettings.guild_id, ModerationSettings.extra)
            .filter(ModerationSettings.extra.isnot(None))
            .all()
        )
        for gid, extra in rows:
            if _merged(extra).get("dirty"):
                out.append(gid)
        return out
    finally:
        db.close()
        SessionLocal.remove()


def snapshot(guild_id: int) -> dict | None:
    """Words + native_sync config/state for one guild."""
    db = SessionLocal()
    try:
        row = db.get(ModerationSettings, guild_id)
        if row is None:
            return None
        return {"words": list(row.cf_custom_words or []), **_merged(row.extra)}
    finally:
        db.close()
        SessionLocal.remove()


def write_state(guild_id: int, patch: dict) -> None:
    """Persist bot-owned sync state (rule_id, last_synced_at, last_error, dirty)."""
    db = SessionLocal()
    try:
        row = db.get(ModerationSettings, guild_id)
        if row is None:
            return
        extra = dict(row.extra or {})
        am = dict(extra.get("automod") or {})
        ns = dict(am.get("native_sync") or {})
        ns.update(patch)
        am["native_sync"] = ns
        extra["automod"] = am
        row.extra = extra
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("automod sync state write failed for guild %s", guild_id)
    finally:
        db.close()
        SessionLocal.remove()


# ── reconcile loop (called from bot_core's 20s post loop) ──────────────────────
async def process_pending(bot) -> None:
    """Push queued AutoMod changes to Discord for every guild this bot serves."""
    from bot_core import serves   # local import — bot_core imports this module

    for gid in await asyncio.to_thread(pending_guilds):
        if not serves(bot, gid):
            continue
        guild = bot.get_guild(gid)
        if guild is None:
            continue
        try:
            await _sync_guild(guild)
        except Exception:  # noqa: BLE001
            log.exception("automod sync failed for guild %s", gid)
            await asyncio.to_thread(write_state, gid, {
                "dirty": False, "last_error": "Unexpected error during sync.",
            })


def _build_keywords(cfg: dict) -> list[str]:
    # *word* = match anywhere, mirroring the bot's own substring matching.
    keywords = []
    for w in cfg.get("words") or []:
        w = str(w).strip()
        if w and "*" not in w:
            keywords.append(f"*{w[:58]}*")
    if cfg.get("block_invites"):
        keywords.extend(_INVITE_PATTERNS)
    return keywords[:_MAX_KEYWORDS]


async def _find_rule(guild: discord.Guild, rule_id) -> discord.AutoModRule | None:
    rules = await guild.fetch_automod_rules()
    if rule_id and str(rule_id).isdigit():
        for r in rules:
            if r.id == int(rule_id):
                return r
    # rule_id lost or stale — fall back to the managed name so we never duplicate
    return next((r for r in rules if r.name == RULE_NAME), None)


async def _sync_guild(guild: discord.Guild) -> None:
    cfg = await asyncio.to_thread(snapshot, guild.id)
    if cfg is None:
        return
    keywords = _build_keywords(cfg)
    want_rule = bool(cfg.get("enabled")) and bool(keywords)

    state = {"dirty": False, "last_error": None,
             "last_synced_at": datetime.utcnow().isoformat()}
    try:
        rule = await _find_rule(guild, cfg.get("rule_id"))

        if not want_rule:
            if rule is not None:
                await rule.delete(reason="Guildizer: native AutoMod sync disabled")
            state["rule_id"] = None
        else:
            trigger = discord.AutoModTrigger(
                type=discord.AutoModRuleTriggerType.keyword,
                keyword_filter=keywords,
            )
            actions = [discord.AutoModRuleAction(custom_message=BLOCK_MESSAGE)]
            alert = cfg.get("alert_channel_id")
            if alert and str(alert).isdigit() and guild.get_channel(int(alert)):
                actions.append(discord.AutoModRuleAction(channel_id=int(alert)))
            if rule is None:
                rule = await guild.create_automod_rule(
                    name=RULE_NAME,
                    event_type=discord.AutoModRuleEventType.message_send,
                    trigger=trigger,
                    actions=actions,
                    enabled=True,
                    reason="Guildizer: native AutoMod sync",
                )
            else:
                await rule.edit(trigger=trigger, actions=actions, enabled=True,
                                reason="Guildizer: native AutoMod sync")
            state["rule_id"] = str(rule.id)
    except discord.Forbidden:
        state["last_error"] = ("The bot is missing the Manage Server permission, "
                               "which Discord requires for AutoMod rules.")
    except discord.HTTPException as exc:
        # Most commonly Discord's per-guild keyword-rule cap (6).
        state["last_error"] = f"Discord rejected the AutoMod rule: {exc.text or exc}"[:200]
        log.warning("automod sync rejected for guild %s: %s", guild.id, exc)

    await asyncio.to_thread(write_state, guild.id, state)
