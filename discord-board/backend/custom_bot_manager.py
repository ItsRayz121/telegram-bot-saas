"""White-label custom bot fleet (Phase 9).

Runs one discord.Client gateway session per active CustomBot row, all on the
official bot's asyncio loop (bot.py starts FleetManager.run()). Every client is
a thin shell over bot_core.CoreMixin, so custom bots run the exact same engine
as the official bot — features ship to the whole fleet on deploy.

Reconcile loop (every 30s):
  - start clients for active bots that aren't running (staggered connects)
  - restart clients whose row is flagged needs_restart (token replaced / re-enabled)
  - stop clients whose row was deleted or disabled
  - mark rows status=error on login failure (bad/reset token) + health event
"""
from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands

import bot_core
import bot_policy
import campaign_views
import self_roles
import tickets
import verification
import crypto
from database import SessionLocal
from models import CustomBot

log = logging.getLogger("guildizer.fleet")

RECONCILE_SECONDS = 30
CONNECT_STAGGER_SECONDS = 2   # politeness between gateway identifies at boot


class CustomBotClient(bot_core.CoreMixin, discord.Client):
    """A single white-label bot. Plain Client — customer bots serve a handful
    of guilds each, far below Discord's ~2,500-guild sharding threshold."""

    def __init__(self, bot_id: int) -> None:
        super().__init__(intents=bot_core.build_intents())
        self.custom_bot_id = bot_id
        self.tree = app_commands.CommandTree(self)
        self._booted = False
        bot_core.attach_builtin_commands(self)

    async def setup_hook(self) -> None:
        # Global built-ins registered on the CUSTOMER's application — their bot
        # answers /ping, /rank, etc. under their own name and avatar.
        await self.tree.sync()
        self.add_dynamic_items(campaign_views.ProofButton)
        # ActionStartButton is the current per-action entry point; RaidStartButton
        # stays registered so raid posts made before it was generalized still work.
        self.add_dynamic_items(campaign_views.ActionStartButton)
        self.add_dynamic_items(campaign_views.RaidStartButton)
        self.add_dynamic_items(verification.VerifyButton,
                               bot_policy.TrustBotButton, bot_policy.KickBotButton)
        self.add_dynamic_items(self_roles.SelfRoleButton)
        self.add_dynamic_items(tickets.TicketOpenButton, tickets.TicketClaimButton, tickets.TicketCloseButton)
        self.resync_commands.start()
        self.post_campaigns.start()
        self.deliver_reminders.start()
        self.process_mod_actions.start()
        self.content_loop.start()
        self.voice_loop.start()

    async def on_ready(self) -> None:
        log.info("Custom bot #%s online as %s (id=%s, %d guild(s))",
                 self.custom_bot_id, self.user, self.user.id, len(self.guilds))
        if self._booted:
            return
        self._booted = True
        await asyncio.to_thread(bot_core.record_health, self.custom_bot_id, "connect")
        await self.core_boot()


class FleetManager:
    def __init__(self) -> None:
        self._running: dict[int, tuple[CustomBotClient, asyncio.Task]] = {}
        self._stopping = False

    # --- DB snapshots (sync, called via to_thread) -----------------------------
    @staticmethod
    def _load_active_bots() -> list[tuple[int, str | None, bool]]:
        """(id, decrypted_token_or_None, needs_restart) for status=active rows."""
        db = SessionLocal()
        try:
            rows = db.query(CustomBot).filter(CustomBot.status == "active").all()
            return [(b.id, crypto.decrypt_token(b.token_encrypted), bool(b.needs_restart))
                    for b in rows]
        finally:
            db.close()
            SessionLocal.remove()

    @staticmethod
    def _clear_restart_flag(bot_id: int) -> None:
        db = SessionLocal()
        try:
            row = db.get(CustomBot, bot_id)
            if row is not None:
                row.needs_restart = False
                db.commit()
        finally:
            db.close()
            SessionLocal.remove()

    @staticmethod
    def _mark_error(bot_id: int, detail: str) -> None:
        import access

        db = SessionLocal()
        try:
            row = db.get(CustomBot, bot_id)
            if row is not None:
                row.status = "error"
                row.error_detail = detail[:300]
                access.notify(db, row.owner_user_id,
                              f"Custom bot @{row.bot_username} needs attention",
                              detail[:300], "error")
                db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
            log.exception("mark_error failed for bot %s", bot_id)
        finally:
            db.close()
            SessionLocal.remove()

    # --- client lifecycle --------------------------------------------------------
    async def _run_client(self, bot_id: int, token: str) -> None:
        client = CustomBotClient(bot_id)
        self._running[bot_id] = (client, asyncio.current_task())
        try:
            async with client:
                await client.start(token)
        except discord.LoginFailure:
            log.warning("Custom bot #%s: token rejected by Discord.", bot_id)
            await asyncio.to_thread(
                self._mark_error, bot_id,
                "Discord rejected the token — it was probably reset. Enter the new token.",
            )
            await asyncio.to_thread(bot_core.record_health, bot_id, "auth_failed")
        except discord.PrivilegedIntentsRequired:
            log.warning("Custom bot #%s: privileged intents not enabled.", bot_id)
            await asyncio.to_thread(
                self._mark_error, bot_id,
                "Privileged intents are OFF for this app. Enable Server Members + "
                "Message Content in the Developer Portal, then re-check.",
            )
            await asyncio.to_thread(bot_core.record_health, bot_id, "error",
                                    "privileged intents missing")
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.exception("Custom bot #%s crashed.", bot_id)
            await asyncio.to_thread(bot_core.record_health, bot_id, "error", str(exc))
        finally:
            self._running.pop(bot_id, None)
            if not self._stopping:
                await asyncio.to_thread(bot_core.record_health, bot_id, "disconnect")

    async def _stop_client(self, bot_id: int) -> None:
        entry = self._running.pop(bot_id, None)
        if entry is None:
            return
        client, task = entry
        if not client.is_closed():
            await client.close()
        task.cancel()

    # --- reconcile ----------------------------------------------------------------
    async def reconcile(self) -> None:
        rows = await asyncio.to_thread(self._load_active_bots)
        wanted: dict[int, str] = {}
        for bot_id, token, needs_restart in rows:
            if token is None:
                await asyncio.to_thread(
                    self._mark_error, bot_id,
                    "Stored token could not be decrypted — please re-enter it.",
                )
                continue
            wanted[bot_id] = token
            if needs_restart and bot_id in self._running:
                log.info("Custom bot #%s flagged for restart.", bot_id)
                await self._stop_client(bot_id)

        # stop clients no longer wanted (deleted / disabled / errored rows)
        for bot_id in list(self._running):
            if bot_id not in wanted:
                log.info("Stopping custom bot #%s (no longer active).", bot_id)
                await self._stop_client(bot_id)

        # start missing clients, staggered
        for bot_id, token in wanted.items():
            if bot_id in self._running:
                continue
            log.info("Starting custom bot #%s…", bot_id)
            asyncio.create_task(self._run_client(bot_id, token), name=f"custom-bot-{bot_id}")
            await asyncio.to_thread(self._clear_restart_flag, bot_id)
            await asyncio.sleep(CONNECT_STAGGER_SECONDS)

    async def run(self) -> None:
        log.info("Custom-bot fleet manager started.")
        while not self._stopping:
            try:
                await self.reconcile()
            except asyncio.CancelledError:
                return
            except Exception:  # noqa: BLE001
                log.exception("Fleet reconcile failed; retrying next tick.")
            await asyncio.sleep(RECONCILE_SECONDS)

    async def shutdown(self) -> None:
        if self._stopping:
            return
        self._stopping = True
        for bot_id in list(self._running):
            try:
                await self._stop_client(bot_id)
            except Exception:  # noqa: BLE001
                log.exception("Error stopping custom bot #%s", bot_id)
        log.info("Custom-bot fleet stopped.")
