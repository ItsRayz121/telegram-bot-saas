"""Role applications: members apply on Discord (/applyrole), staff review in the
dashboard. DB helpers are pure (testable); the slash command is a thin wrapper.

Config lives in GuildSettings.extra["role_apps"] = {"roles": [{"role_id", "label"}]}.
Only roles an admin listed can be applied for, and a role that carries moderation or
management permissions can never be listed - the application path is not a way to
become staff.
"""
from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands

import role_policy
from database import SessionLocal
from models import GuildSettings, RoleApplication

log = logging.getLogger("guildizer.roleapps")
MAX_ROLES = 10


def configured_roles(extra) -> list[dict]:
    out = []
    for r in ((extra or {}).get("role_apps") or {}).get("roles") or []:
        if str(r.get("role_id", "")).isdigit():
            out.append({"role_id": str(r["role_id"]), "label": str(r.get("label") or "")[:60]})
    return out[:MAX_ROLES]


def submit(db, guild_id: int, user_id: int, username: str | None, role_id: int, evidence: str):
    """(status, application). status: ok | not_offered | already_pending | unsafe."""
    row = db.get(GuildSettings, guild_id)
    offered = {r["role_id"] for r in configured_roles(row.extra if row else None)}
    if str(role_id) not in offered:
        return "not_offered", None
    if role_policy.check_roles(db, guild_id, [role_id]):
        return "unsafe", None
    dup = (db.query(RoleApplication)
           .filter_by(guild_id=guild_id, user_id=user_id, role_id=role_id, status="pending").first())
    if dup is not None:
        return "already_pending", dup
    app = RoleApplication(guild_id=guild_id, user_id=user_id, username=(username or "")[:120] or None,
                          role_id=role_id, evidence=(evidence or "").strip()[:1000] or None)
    db.add(app)
    db.flush()
    return "ok", app


def attach_role_app_commands(client) -> None:
    tree = client.tree

    async def _role_choices(interaction: discord.Interaction, current: str):
        def load():
            db = SessionLocal()
            try:
                row = db.get(GuildSettings, interaction.guild_id)
                return configured_roles(row.extra if row else None)
            finally:
                db.close()
                SessionLocal.remove()
        offered = await asyncio.to_thread(load)
        out = []
        for r in offered:
            role = interaction.guild.get_role(int(r["role_id"])) if interaction.guild else None
            if role is None:
                continue
            name = r["label"] or role.name
            if current.lower() in name.lower():
                out.append(app_commands.Choice(name=name[:100], value=r["role_id"]))
        return out[:25]

    @tree.command(name="applyrole", description="Apply for a special role (staff review your evidence).")
    @app_commands.describe(role="The role you are applying for", evidence="Links or notes that support your application")
    @app_commands.autocomplete(role=_role_choices)
    async def applyrole(interaction: discord.Interaction, role: str, evidence: str) -> None:
        if interaction.guild is None or not role.isdigit():
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        target = interaction.guild.get_role(int(role))
        if target is None:
            return await interaction.response.send_message("That role no longer exists.", ephemeral=True)
        member = interaction.user
        if isinstance(member, discord.Member) and target in member.roles:
            return await interaction.response.send_message(f"You already have **{target.name}**.", ephemeral=True)

        def run():
            db = SessionLocal()
            try:
                res = submit(db, interaction.guild_id, interaction.user.id, str(interaction.user), int(role), evidence)
                db.commit()
                return res[0]
            except Exception:  # noqa: BLE001
                db.rollback()
                log.exception("role application failed")
                return "error"
            finally:
                db.close()
                SessionLocal.remove()
        status = await asyncio.to_thread(run)
        text = {
            "ok": f"✅ Application for **{target.name}** sent. Staff will review it.",
            "already_pending": f"You already have a pending application for **{target.name}**.",
            "not_offered": "That role isn't open for applications.",
            "unsafe": "That role can't be applied for.",
        }.get(status, "Couldn't record your application — try again later.")
        await interaction.response.send_message(text, ephemeral=True)
