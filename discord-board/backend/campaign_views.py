"""Discord UI for campaign proof flows: a persistent "Submit proof" button per
campaign/task and a proof modal. Buttons survive bot restarts via DynamicItem
(custom_id carries the campaign + task ids); register once with
bot.add_dynamic_items(ProofButton).
"""
from __future__ import annotations

import asyncio
import logging

import discord

import campaign_runtime as cr

log = logging.getLogger("guildizer.campaigns")

ACCENT = 0x5865F2


def _result_text(status: str, reward: int) -> str:
    if status == "verified":
        return f"✅ Verified! +{reward} XP" if reward else "✅ Verified — thanks!"
    if status == "pending":
        return "📝 Submitted — an admin will review it shortly. Thanks!"
    if status == "duplicate":
        return "🙌 You've already submitted for this one."
    return "This campaign is closed."


class ProofModal(discord.ui.Modal):
    def __init__(self, cid: int, tid: int, title: str) -> None:
        super().__init__(title=f"Submit proof · {title}"[:45])
        self.cid = cid
        self.tid = tid
        self.value = discord.ui.TextInput(
            label="Your proof (link or text)",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=500,
        )
        self.add_item(self.value)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        status, reward = await asyncio.to_thread(
            cr.create_submission, self.cid, self.tid,
            interaction.user.id, str(interaction.user), str(self.value),
        )
        await interaction.response.send_message(_result_text(status, reward), ephemeral=True)


class ProofButton(discord.ui.DynamicItem[discord.ui.Button], template=r"gz:proof:(?P<cid>\d+):(?P<tid>\d+)"):
    def __init__(self, cid: int, tid: int, label: str = "Submit proof", honor: bool = False) -> None:
        self.cid = cid
        self.tid = tid
        super().__init__(
            discord.ui.Button(
                label=label[:80],
                style=discord.ButtonStyle.success if honor else discord.ButtonStyle.primary,
                custom_id=f"gz:proof:{cid}:{tid}",
            )
        )

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match["cid"]), int(match["tid"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        ctx = await asyncio.to_thread(cr.submit_context, self.cid, self.tid)
        if ctx is None:
            await interaction.response.send_message("This campaign is closed.", ephemeral=True)
            return
        if ctx["verification_mode"] == "honor":
            status, reward = await asyncio.to_thread(
                cr.create_submission, self.cid, self.tid,
                interaction.user.id, str(interaction.user), None,
            )
            await interaction.response.send_message(_result_text(status, reward), ephemeral=True)
        else:
            await interaction.response.send_modal(ProofModal(self.cid, self.tid, ctx["title"]))


def build_embed(data: dict) -> discord.Embed:
    embed = discord.Embed(title=data["title"][:256], description=(data["description"] or None), color=ACCENT)
    if data["tasks"]:
        for t in data["tasks"]:
            val = t["description"] or ""
            if t["task_url"]:
                val += f"\n🔗 {t['task_url']}"
            if t["reward_xp"]:
                val += f"\n🎁 {t['reward_xp']} XP"
            embed.add_field(name=t["title"][:256], value=(val.strip() or "—")[:1024], inline=False)
    else:
        if data["task_url"]:
            embed.add_field(name="Task", value=data["task_url"][:1024], inline=False)
        reward = f"{data['reward_xp']} XP" if data["reward_xp"] else ""
        if data["reward_label"]:
            reward = (reward + " · " if reward else "") + data["reward_label"]
        if reward:
            embed.add_field(name="Reward", value=reward[:1024], inline=False)
    embed.set_footer(text="Guildizer • tap a button below to submit proof")
    return embed


def build_view(data: dict) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    tasks = data["tasks"][:25]
    if tasks:
        for t in tasks:
            view.add_item(ProofButton(
                data["id"], t["id"],
                label=f"Submit: {t['title']}", honor=(t["verification_mode"] == "honor"),
            ))
    else:
        view.add_item(ProofButton(
            data["id"], 0, label="Submit proof",
            honor=(data["verification_mode"] == "honor"),
        ))
    return view


async def post_campaign(bot, cid: int) -> None:
    """(Re)post a campaign announcement with proof buttons into its channel."""
    data = await asyncio.to_thread(cr.load_for_post, cid)
    if not data or not data["channel_id"]:
        await asyncio.to_thread(cr.mark_post_failed, cid, "no announcement channel set")
        return
    channel = bot.get_channel(int(data["channel_id"]))
    if channel is None or not hasattr(channel, "send"):
        await asyncio.to_thread(cr.mark_post_failed, cid, "channel not found")
        return

    if data["message_id"]:
        try:
            old = await channel.fetch_message(int(data["message_id"]))
            await old.delete()
        except Exception:  # noqa: BLE001 — old message may be gone; ignore
            pass

    try:
        msg = await channel.send(embed=build_embed(data), view=build_view(data))
        await asyncio.to_thread(cr.mark_posted, cid, msg.id)
        log.info("Posted campaign %s to channel %s", cid, data["channel_id"])
    except discord.Forbidden:
        await asyncio.to_thread(cr.mark_post_failed, cid, "missing permission to post")
    except discord.HTTPException as exc:
        await asyncio.to_thread(cr.mark_post_failed, cid, str(exc))
