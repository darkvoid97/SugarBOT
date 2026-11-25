import os
from zoneinfo import ZoneInfo
from datetime import datetime
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

class SugarBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        intents.message_content = True
        intents.voice_states = True
        activity = discord.CustomActivity(name="Playing with toys 🐶")

        super().__init__(command_prefix=".", intents=intents, activity=activity, status=discord.Status.online)

    async def setup_hook(self):
        await self.load_extension("cogs.general")
        await self.load_extension("cogs.announcements")
        await self.load_extension("cogs.ai_functions")
        #await self.load_extension("cogs.voice")

        await self.tree.sync()
        print("Global command tree synchronized.")

def format_timestamp(dt: datetime, fmt: str = "%d/%b/%Y %H:%M:%S", tz_name: str = "Europe/Rome"):
    tz = ZoneInfo(tz_name)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(tz).strftime(fmt)

def extract_attachment_urls(attachments):
    if not attachments:
        return []
    return [a.url for a in attachments if getattr(a, "url", None)]

def format_sender_header(author_name: str, is_bot: bool, mode: str, channel_id: int | str | None = None, bot_name: str = "SugarBOT"):
    if mode not in ("-1", "-2"):
        raise ValueError(f"Unsupported header mode: {mode}")
    if is_bot:
        receiver_name = f"DM User (ChannelID: {channel_id})"
    else:
        receiver_name = f"{bot_name} <BOT>"
    sender_name = f"{author_name} <BOT>" if is_bot else author_name
    return f"{sender_name}] --> [{receiver_name}"

def build_msg(msg, mode, user: discord.User = None):
    attach = extract_attachment_urls(getattr(msg, "attachments", None))
    attachment_suffix = f"[Attachment: {attach[0]}]" if attach else ""
    content_spacing = " " if msg.content != "" else ""

    if mode in ("-1", "-2"):
        channel_id = getattr(getattr(msg, "channel", None), "id", 0)
        bot_name = getattr(getattr(bot, "user", None), "name", "SugarBOT")
        senders = format_sender_header(author_name=msg.author.name, is_bot=msg.author.bot, mode=mode, channel_id=channel_id, bot_name=bot_name)
        if mode == "-1":
            ts = format_timestamp(msg.created_at, "%d %b %Y - %H:%M")
            return (f"**[{senders}]** [{ts}]\n{msg.content}{content_spacing}{attachment_suffix}")
        else:
            ts = format_timestamp(msg.created_at, "%d/%b/%Y %H:%M:%S")
            return (f"[{ts}] [{senders}]: {msg.content}{content_spacing}{attachment_suffix}")
    else:
        ts = format_timestamp(msg.created_at, "%d/%b/%Y %H:%M:%S")
        channel_prefix = f"[#{msg.channel.name}] " if mode == "1" else ""
        bot_tag = "[BOT]" if msg.author.bot else ""
        return (f"[{ts}] {channel_prefix}<{msg.author.name}{bot_tag}>: {msg.content}{content_spacing}{attachment_suffix}")

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
OWNER_ID = os.getenv('OWNER_ID')
bot = SugarBot()

@bot.command(name="sync")
@commands.is_owner()
async def sync_tree(ctx: commands.Context):
    synced = await bot.tree.sync()
    await ctx.send(f"Synced {len(synced)} global command(s). Am I a good boy or what? :dog:")

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("Hey, you are not my owner, you don't have permissions to do that. Don't make me mad, I may be smol but I bite. **Grrr**. :angry:", ephemeral=True)
    else:
        if interaction.response.is_done():
            await interaction.followup.send(f"An error occurred: {error}", ephemeral=True)
        else:
            await interaction.response.send_message(f"An error occurred: {error}", ephemeral=True)

def main():
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN is not set in the env file.")
    bot.run(TOKEN)

if __name__ == "__main__":
    main()