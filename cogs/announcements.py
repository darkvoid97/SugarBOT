import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

class AnnouncementConfirmView(discord.ui.View):
    def __init__(self, author_id: int, target_channel: discord.TextChannel, embed: discord.Embed, mention_str: Optional[str], allowed_mentions: discord.AllowedMentions):
        super().__init__(timeout=180)
        self.author_id = author_id
        self.target_channel = target_channel
        self.embed = embed
        self.mention_str = mention_str
        self.allowed_mentions = allowed_mentions
        self.message: Optional[discord.WebhookMessage] = None

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the author who started this announcement can confirm it.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Publish Announcement", style=discord.ButtonStyle.success, emoji="🚀")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        perms = self.target_channel.permissions_for(self.target_channel.guild.me)
        if not perms.send_messages or not perms.embed_links:
            await interaction.response.send_message(f"Missing permissions: Ensure I have `Send Messages` and `Embed Links` in {self.target_channel.mention}. :pleading_face:", ephemeral=True)
            return

        for item in self.children:
            item.disabled = True

        published_msg = await self.target_channel.send(content=self.mention_str, embed=self.embed, allowed_mentions=self.allowed_mentions)

        await interaction.response.edit_message(
            content=(
                f"✅ **Announcement published successfully!**\n"
                f"• **Channel:** {self.target_channel.mention}\n"
                f"• **Link:** [Jump to Announcement]({published_msg.jump_url})"
            ),
            embed=None,
            view=self
        )
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, emoji="✖️")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(content="Announcement cancelled. Nothing was posted. :dog:", embed=None, view=self)
        self.stop()

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(content="**Announcement preview timed out.** Please run `/announce` again if needed. :dog:", embed=None, view=self)
            except discord.HTTPException:
                pass

class AnnouncementModal(discord.ui.Modal, title="Create Server Announcement"):
    def __init__(self, target_channel: discord.TextChannel, mention_str: Optional[str], allowed_mentions: discord.AllowedMentions):
        super().__init__()
        self.target_channel = target_channel
        self.mention_str = mention_str
        self.allowed_mentions = allowed_mentions

    announcement_title = discord.ui.TextInput(label="Title", placeholder="e.g. Scheduled Maintenance Notice", min_length=3, max_length=256, required=True)

    body = discord.ui.TextInput(label="Announcement Body", style=discord.TextStyle.paragraph, placeholder="Write the announcement body here...", min_length=5, max_length=4000, required=True)

    color = discord.ui.TextInput(label="Embed Color (Hex Code)", placeholder="#5865F2", default="#5865F2", min_length=6, max_length=7, required=False)

    image_url = discord.ui.TextInput( label="Image/Banner URL (Optional)", placeholder="https://example.com/banner.png", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        hex_clean = self.color.value.strip().lstrip("#")
        try:
            embed_color = int(hex_clean, 16) if hex_clean else discord.Color.blurple().value
        except ValueError:
            embed_color = discord.Color.blurple().value

        embed = discord.Embed(title=self.announcement_title.value.strip(), description=self.body.value, color=embed_color, timestamp=discord.utils.utcnow())

        image_val = self.image_url.value.strip()
        if image_val.startswith(("http://", "https://")):
            embed.set_image(url=image_val)

        if interaction.guild:
            embed.set_footer(text=f"Announced by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
            if interaction.guild.icon:
                embed.set_author(name=interaction.guild.name, icon_url=interaction.guild.icon.url)

        view = AnnouncementConfirmView(author_id=interaction.user.id, target_channel=self.target_channel, embed=embed, mention_str=self.mention_str, allowed_mentions=self.allowed_mentions)

        preview_ping_text = f"**Pings:** {self.mention_str}\n" if self.mention_str else "**Pings:** None\n"
        preview_header = (
            f"📋 **Announcement Preview**\n"
            f"• **Target Destination:** {self.target_channel.mention}\n"
            f"• {preview_ping_text}\n"
            f"Review the embed below and choose an option:"
        )

        await interaction.response.send_message(content=preview_header, embed=embed, view=view, ephemeral=True)
        view.message = await interaction.original_response()

class Announcements(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="announce", description="Configure target, pings, and open the announcement builder")
    @app_commands.describe(channel="The text channel where the announcement should be posted", mention_preset="Choose whether to ping @everyone or @here", mention_role="Optionally pick a specific role to ping")
    @app_commands.choices(mention_preset=[app_commands.Choice(name="@everyone", value="@everyone"), app_commands.Choice(name="@here", value="@here")])
    async def announce(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None, mention_preset: Optional[app_commands.Choice[str]] = None, mention_role: Optional[discord.Role] = None):
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message("Hey, you are not my owner, you don't have permissions to do that. Don't make me mad, I may be smol but I bite. **Grrr**. :angry:", ephemeral=True)
            return

        target_channel = channel or interaction.channel
        if not isinstance(target_channel, discord.TextChannel):
            await interaction.response.send_message("The target destination must be a regular server text channel. :pleading_face:", ephemeral=True)
            return

        ping_tokens = []
        allow_everyone = False
        allowed_roles = []

        if mention_preset:
            ping_tokens.append(mention_preset.value)
            allow_everyone = True

        if mention_role:
            ping_tokens.append(mention_role.mention)
            allowed_roles.append(mention_role)

        mention_str = " ".join(ping_tokens) if ping_tokens else None
        allowed_mentions = discord.AllowedMentions(everyone=allow_everyone, roles=allowed_roles if allowed_roles else False)

        await interaction.response.send_modal(AnnouncementModal(target_channel=target_channel, mention_str=mention_str, allowed_mentions=allowed_mentions))

async def setup(bot: commands.Bot):
    await bot.add_cog(Announcements(bot))