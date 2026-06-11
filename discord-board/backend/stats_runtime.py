"""Activity rollups + feature-usage spine (Phase 15). Sync DB helpers — the
bot buffers per-message counters in memory and flushes here every ~60s, so
chat volume never turns into per-message writes.
"""
from __future__ import annotations

import logging
from datetime import datetime

from database import SessionLocal
from models import FeatureUsageEvent, GuildDailyStat, Member

log = logging.getLogger("guildizer.stats")


def today() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


def flush_activity(items: list[tuple[int, int, str | None, int]]) -> None:
    """items = [(guild_id, user_id, username, add_messages)]. Sets last_seen,
    bumps message counts not already counted by leveling."""
    if not items:
        return
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        for guild_id, user_id, username, add_msgs in items:
            m = db.get(Member, {"guild_id": guild_id, "user_id": user_id})
            if m is None:
                m = Member(guild_id=guild_id, user_id=user_id)
                db.add(m)
            m.last_seen = now
            if username:
                m.username = username[:120]
            if add_msgs:
                m.messages = (m.messages or 0) + add_msgs
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("flush_activity failed")
    finally:
        db.close()
        SessionLocal.remove()


def bump_daily(guild_id: int, *, messages: int = 0, joins: int = 0, leaves: int = 0) -> None:
    if not (messages or joins or leaves):
        return
    db = SessionLocal()
    try:
        key = {"guild_id": guild_id, "day": today()}
        row = db.get(GuildDailyStat, key)
        if row is None:
            row = GuildDailyStat(guild_id=guild_id, day=today())
            db.add(row)
        row.messages = (row.messages or 0) + messages
        row.joins = (row.joins or 0) + joins
        row.leaves = (row.leaves or 0) + leaves
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("bump_daily failed for guild %s", guild_id)
    finally:
        db.close()
        SessionLocal.remove()


def record_feature(guild_id: int | None, user_id: int | None, feature: str) -> None:
    db = SessionLocal()
    try:
        db.add(FeatureUsageEvent(guild_id=guild_id, user_id=user_id,
                                 feature=(feature or "unknown")[:40]))
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
    finally:
        db.close()
        SessionLocal.remove()


def set_wallet(guild_id: int, user_id: int, username: str | None, wallet: str | None) -> None:
    db = SessionLocal()
    try:
        m = db.get(Member, {"guild_id": guild_id, "user_id": user_id})
        if m is None:
            m = Member(guild_id=guild_id, user_id=user_id, username=(username or "")[:120] or None)
            db.add(m)
        m.wallet = (wallet or "").strip()[:120] or None
        db.commit()
    finally:
        db.close()
        SessionLocal.remove()


def get_wallet(guild_id: int, user_id: int) -> str | None:
    db = SessionLocal()
    try:
        m = db.get(Member, {"guild_id": guild_id, "user_id": user_id})
        return m.wallet if m is not None else None
    finally:
        db.close()
        SessionLocal.remove()


# --- slash commands ------------------------------------------------------------------
def attach_wallet_commands(client) -> None:
    import discord
    from discord import app_commands  # noqa: F401

    class WalletModal(discord.ui.Modal):
        def __init__(self, guild_id: int) -> None:
            super().__init__(title="Set your wallet address")
            self.guild_id = guild_id
            self.addr = discord.ui.TextInput(
                label="Wallet address", max_length=120, required=True,
                placeholder="0x… / bc1… / your chain's address",
            )
            self.add_item(self.addr)

        async def on_submit(self, interaction: discord.Interaction) -> None:
            import asyncio
            await asyncio.to_thread(set_wallet, self.guild_id, interaction.user.id,
                                    str(interaction.user), str(self.addr.value))
            await interaction.response.send_message(
                "💳 Wallet saved. Only server admins can see it.", ephemeral=True
            )

    @client.tree.command(name="wallet", description="Save your wallet address for this server's rewards.")
    async def wallet(interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return
        await interaction.response.send_modal(WalletModal(interaction.guild.id))

    @client.tree.command(name="mywallet", description="Show the wallet address you saved here.")
    async def mywallet(interaction: discord.Interaction) -> None:
        import asyncio
        if interaction.guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return
        addr = await asyncio.to_thread(get_wallet, interaction.guild.id, interaction.user.id)
        if not addr:
            await interaction.response.send_message(
                "You haven't saved a wallet here yet — use /wallet.", ephemeral=True
            )
            return
        masked = addr if len(addr) <= 12 else f"{addr[:6]}…{addr[-4:]}"
        await interaction.response.send_message(f"💳 Your saved wallet: `{masked}`", ephemeral=True)
