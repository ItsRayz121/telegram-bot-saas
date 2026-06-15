"""Join captcha — quarantine-role verification (Phase 11). Both lineages.

Flow: member joins → bot assigns the Unverified role and posts a challenge in
the #verify channel. Button method verifies on click; math/word open a modal.
Success removes the role and the challenge; max failed attempts or timeout
applies the configured action (kick/keep). Buttons survive restarts via
DynamicItem; expiry is swept by the bot's 60s loop.

Setup is automatic: when verification is enabled and the role/channel are
missing, the serving bot creates an "Unverified" role, a #verify channel only
that role can see, and hides every other channel from the role.
"""
from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta

import discord

import governor
import protection
from database import SessionLocal
from models import PendingVerification

log = logging.getLogger("guildizer.verify")

ROLE_NAME = "Unverified"
CHANNEL_NAME = "verify"
_WORDS = ["sunrise", "harbor", "violet", "compass", "meadow", "lantern", "ember", "willow"]


# --- challenge content -----------------------------------------------------------
def make_challenge(method: str) -> tuple[str | None, str | None]:
    """(prompt, expected_answer) for the modal methods; (None, None) for button."""
    if method == "math":
        a, b = random.randint(2, 9), random.randint(2, 9)
        return f"What is {a} + {b}?", str(a + b)
    if method == "word":
        word = random.choice(_WORDS)
        return f"Type the word: {word}", word
    return None, None


# --- DB helpers (sync — call via to_thread) ----------------------------------------
def create_pending(guild_id, user_id, username, cfg) -> dict:
    method = cfg.get("method", "button")
    prompt, answer = make_challenge(method)
    db = SessionLocal()
    try:
        # one active challenge per member — replace any stale one
        db.query(PendingVerification).filter(
            PendingVerification.guild_id == guild_id,
            PendingVerification.user_id == user_id,
        ).delete()
        row = PendingVerification(
            guild_id=guild_id, user_id=user_id, username=(username or "")[:120] or None,
            method=method, prompt=prompt, answer=answer,
            expires_at=datetime.utcnow() + timedelta(seconds=int(cfg.get("timeout_seconds", 300))),
        )
        db.add(row)
        db.commit()
        return {"id": row.id, "method": method, "prompt": prompt}
    finally:
        db.close()
        SessionLocal.remove()


def set_challenge_message(guild_id, user_id, channel_id, message_id) -> None:
    db = SessionLocal()
    try:
        row = _get(db, guild_id, user_id)
        if row is not None:
            row.channel_id = channel_id
            row.message_id = message_id
            db.commit()
    finally:
        db.close()
        SessionLocal.remove()


def _get(db, guild_id, user_id) -> PendingVerification | None:
    return (
        db.query(PendingVerification)
        .filter(PendingVerification.guild_id == guild_id,
                PendingVerification.user_id == user_id)
        .first()
    )


def check_answer(guild_id, user_id, given: str) -> tuple[str, dict]:
    """Returns (outcome, info): outcome = pass | retry | fail | missing."""
    db = SessionLocal()
    try:
        row = _get(db, guild_id, user_id)
        if row is None:
            return "missing", {}
        snap = protection.load_snapshot(db, guild_id) or {}
        cfg = snap.get("verification") or {}
        info = {"message_id": row.message_id, "channel_id": row.channel_id}
        if row.method == "button" or (row.answer or "").strip().lower() == (given or "").strip().lower():
            db.delete(row)
            db.commit()
            return "pass", info
        row.attempts = (row.attempts or 0) + 1
        if row.attempts >= int(cfg.get("max_attempts", 3)):
            db.delete(row)
            db.commit()
            return "fail", info
        remaining = int(cfg.get("max_attempts", 3)) - row.attempts
        db.commit()
        info["remaining"] = remaining
        return "retry", info
    finally:
        db.close()
        SessionLocal.remove()


def expired_rows(served_guild_ids: list[int]) -> list[dict]:
    """Pop expired challenges for the given guilds only — each bot identity
    sweeps just the guilds it serves (rows are deleted as they're returned)."""
    if not served_guild_ids:
        return []
    db = SessionLocal()
    try:
        rows = (
            db.query(PendingVerification)
            .filter(PendingVerification.expires_at <= datetime.utcnow(),
                    PendingVerification.guild_id.in_(served_guild_ids))
            .limit(25)
            .all()
        )
        out = [{"id": r.id, "guild_id": r.guild_id, "user_id": r.user_id,
                "username": r.username, "channel_id": r.channel_id,
                "message_id": r.message_id} for r in rows]
        for r in rows:
            db.delete(r)
        db.commit()
        return out
    finally:
        db.close()
        SessionLocal.remove()


def is_verified(guild_id, user_id) -> bool:
    """True if the member already passed first-message verification once."""
    from models import Member
    db = SessionLocal()
    try:
        m = db.get(Member, {"guild_id": guild_id, "user_id": user_id})
        return bool(m and m.verified)
    finally:
        db.close()
        SessionLocal.remove()


def mark_verified(guild_id, user_id, username=None) -> None:
    """Persist that the member passed verification (used by first_message mode)."""
    import leveling
    db = SessionLocal()
    try:
        m = leveling.get_or_create_member(db, guild_id, user_id, username)
        m.verified = True
        db.commit()
    finally:
        db.close()
        SessionLocal.remove()


def save_setup_ids(guild_id, role_id, channel_id) -> None:
    db = SessionLocal()
    try:
        protection.update_extra_section(db, guild_id, "verification",
                                        {"role_id": str(role_id), "channel_id": str(channel_id)})
        db.commit()
    finally:
        db.close()
        SessionLocal.remove()


# --- Discord-side flow ----------------------------------------------------------------
async def ensure_setup(guild: discord.Guild, cfg: dict) -> dict | None:
    """Create the Unverified role + #verify channel if missing; hide other
    channels from the role. Returns updated {role_id, channel_id} or None."""
    role = guild.get_role(int(cfg["role_id"])) if cfg.get("role_id") else None
    if role is None:
        role = discord.utils.get(guild.roles, name=ROLE_NAME)
    if role is None:
        try:
            role = await guild.create_role(name=ROLE_NAME, reason="Guildizer verification setup")
        except (discord.Forbidden, discord.HTTPException):
            log.warning("verification setup: cannot create role in guild %s", guild.id)
            return None

    channel = guild.get_channel(int(cfg["channel_id"])) if cfg.get("channel_id") else None
    if channel is None:
        channel = discord.utils.get(guild.text_channels, name=CHANNEL_NAME)
    if channel is None:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            role: discord.PermissionOverwrite(view_channel=True, read_message_history=True,
                                              send_messages=False),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }
        try:
            channel = await guild.create_text_channel(
                CHANNEL_NAME, overwrites=overwrites, reason="Guildizer verification setup"
            )
        except (discord.Forbidden, discord.HTTPException):
            log.warning("verification setup: cannot create channel in guild %s", guild.id)
            return None

    # hide the rest of the server from Unverified (cap the work; governor-safe)
    for ch in guild.channels[:75]:
        if ch.id == channel.id:
            continue
        existing = ch.overwrites_for(role)
        if existing.view_channel is False:
            continue
        await governor.safe(
            ch.set_permissions(role, view_channel=False, reason="Guildizer verification"),
            what="verification overwrite",
        )
    return {"role_id": role.id, "channel_id": channel.id}


def challenge_view(guild_id: int, user_id: int) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(VerifyButton(guild_id, user_id))
    return view


class VerifyModal(discord.ui.Modal):
    def __init__(self, guild_id: int, user_id: int, prompt: str) -> None:
        super().__init__(title="Verification")
        self.guild_id = guild_id
        self.user_id = user_id
        self.answer = discord.ui.TextInput(label=prompt[:45], max_length=40)
        self.add_item(self.answer)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        import asyncio
        outcome, info = await asyncio.to_thread(
            check_answer, self.guild_id, self.user_id, str(self.answer.value)
        )
        await finish_attempt(interaction, outcome, info)


class VerifyButton(discord.ui.DynamicItem[discord.ui.Button],
                   template=r"gz:verify:(?P<gid>\d+):(?P<uid>\d+)"):
    def __init__(self, gid: int, uid: int) -> None:
        super().__init__(discord.ui.Button(
            label="✅ Verify me", style=discord.ButtonStyle.success,
            custom_id=f"gz:verify:{gid}:{uid}",
        ))
        self.gid = gid
        self.uid = uid

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match["gid"]), int(match["uid"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        import asyncio
        if interaction.user.id != self.uid:
            await interaction.response.send_message("This challenge isn't for you.", ephemeral=True)
            return
        # modal methods ask the question; button method passes straight through
        db_info = await asyncio.to_thread(_peek_method, self.gid, self.uid)
        if db_info is None:
            await interaction.response.send_message(
                "This challenge expired — rejoin the server to get a new one.", ephemeral=True
            )
            return
        method, prompt = db_info
        if method in ("math", "word"):
            await interaction.response.send_modal(VerifyModal(self.gid, self.uid, prompt or "Answer"))
            return
        outcome, info = await asyncio.to_thread(check_answer, self.gid, self.uid, "")
        await finish_attempt(interaction, outcome, info)


def _peek_method(guild_id, user_id):
    db = SessionLocal()
    try:
        row = _get(db, guild_id, user_id)
        return (row.method, row.prompt) if row is not None else None
    finally:
        db.close()
        SessionLocal.remove()


async def finish_attempt(interaction: discord.Interaction, outcome: str, info: dict) -> None:
    """Apply the verification outcome for the interacting member."""
    import asyncio
    guild = interaction.guild
    member = interaction.user
    if outcome == "pass":
        cfg = await asyncio.to_thread(_verification_cfg, guild.id)
        role = guild.get_role(int(cfg["role_id"])) if cfg.get("role_id") else None
        if role is not None:
            await governor.safe(member.remove_roles(role, reason="Guildizer: verified"),
                                what="verify role removal")
        await interaction.response.send_message("✅ You're verified — welcome!", ephemeral=True)
        await _delete_challenge_message(guild, info)
        await asyncio.to_thread(mark_verified, guild.id, member.id, str(member))
        await asyncio.to_thread(_log, guild.id, "verification", "verified", member.id, str(member))
    elif outcome == "retry":
        await interaction.response.send_message(
            f"❌ Wrong answer — {info.get('remaining', 1)} attempt(s) left.", ephemeral=True
        )
    elif outcome == "fail":
        await interaction.response.send_message("❌ Verification failed.", ephemeral=True)
        await _delete_challenge_message(guild, info)
        await governor.safe(member.kick(reason="Guildizer: failed verification"), what="verify fail kick")
        await asyncio.to_thread(_log, guild.id, "verification", "kick", member.id, str(member),
                                "max attempts reached")
    else:  # missing
        await interaction.response.send_message(
            "This challenge expired — rejoin the server to get a new one.", ephemeral=True
        )


def _verification_cfg(guild_id):
    db = SessionLocal()
    try:
        snap = protection.load_snapshot(db, guild_id) or {}
        return snap.get("verification") or {}
    finally:
        db.close()
        SessionLocal.remove()


def _log(guild_id, category, action, user_id=None, username=None, detail=None):
    db = SessionLocal()
    try:
        protection.log_event(db, guild_id, category, action,
                             user_id=user_id, username=username, detail=detail)
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
    finally:
        db.close()
        SessionLocal.remove()


async def _delete_challenge_message(guild: discord.Guild, info: dict) -> None:
    ch_id, msg_id = info.get("channel_id"), info.get("message_id")
    if not (ch_id and msg_id):
        return
    channel = guild.get_channel(int(ch_id))
    if channel is None:
        return
    try:
        msg = channel.get_partial_message(int(msg_id))
        await governor.safe(msg.delete(), what="delete challenge message")
    except discord.HTTPException:
        pass
