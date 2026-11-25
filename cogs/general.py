import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
import random
import re
import aiohttp

# Multiple answers for randomization message of the 'ping' command
ping_quotes = [
        'Woof Woof! :dog:',
        'Hey, gimme something to eat, or I\'ll pee in your living room. :dog:',
        'Somebody saw my toy? :dog:',
        'Wanna play with me? Throw my ball! :dog::tennis:'
    ]

URL_PATTERN = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)

class General(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="ping", description="Say hello to the doggo! Also checks the bot latency")
    async def ping(self, ctx: commands.Context):
        latency = round(self.bot.latency * 1000)
        await ctx.send(f"Pong! {random.choice(ping_quotes)}\nLatency is `{latency}ms`.", ephemeral=True)

    @commands.hybrid_command(name="avatar", description="Fetch a user's avatar")
    @app_commands.describe(member="The member whose avatar you want to inspect")
    async def avatar(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        member = member or ctx.author
        await ctx.defer(ephemeral=False) 
        embed = discord.Embed(title=f"{member.display_name}'s Avatar")
        embed.set_image(url=member.display_avatar.url)
        
        await ctx.send(embed=embed, ephemeral=True)

    @app_commands.command(name="purge", description="Clean messages from the channel with optional filters")
    @app_commands.describe(amount="Maximum number of recent messages to scan (1-100)", user="Only delete messages from this specific user", bots_only="Only delete messages sent by bots", links_only="Only delete messages containing web links", has_attachments="Only delete messages containing files or images", contains_text="Only delete messages containing this specific text")
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.guild_only()
    async def purge(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100], user: Optional[discord.User] = None, bots_only: bool = False, links_only: bool = False, has_attachments: bool = False, contains_text: Optional[str] = None):
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message("Hey, you are not my owner, you don't have permissions to do that. Don't make me mad, I may be smol but I bite. **Grrr**. :angry:", ephemeral=True)
            return
        
        channel = interaction.channel
        if not isinstance(channel, (discord.TextChannel, discord.Thread, discord.VoiceChannel)):
            await interaction.response.send_message("I can only do this in standard text channels or threads. :dog:", ephemeral=True)
            return

        permissions = channel.permissions_for(interaction.guild.me)

        if not permissions.manage_messages:
            await interaction.response.send_message("Missing permissions: I need the `Manage Messages` permission to delete messages. :pleading_face:", ephemeral=True)
            return

        if not permissions.read_message_history:
            await interaction.response.send_message("Missing permissions: I need `Read Message History` to scan messages. :pleading_face:", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        def check(message: discord.Message):
            if message.pinned:
                return False

            if user and message.author.id != user.id:
                return False

            if bots_only and not message.author.bot:
                return False

            if links_only and not URL_PATTERN.search(message.content):
                return False

            if has_attachments and not (message.attachments or any(e.image or e.video for e in message.embeds)):
                return False

            if contains_text and contains_text.lower() not in message.content.lower():
                return False

            return True

        try:
            deleted = await channel.purge(limit=amount, check=check, bulk=True)
        except discord.Forbidden:
            await interaction.followup.send("Forbidden: I lack permission to delete one or more targeted messages. :pleading_face:", ephemeral=True)
            return
        except discord.HTTPException as err:
            await interaction.followup.send(f"An error occurred while purging messages: `{err}`", ephemeral=True)
            return

        applied_filters = []
        if user:
            applied_filters.append(f"• User: {user.mention}")
        if bots_only:
            applied_filters.append("• Bots only: `Yes`")
        if links_only:
            applied_filters.append("• Links only: `Yes`")
        if has_attachments:
            applied_filters.append("• Attachments/Media only: `Yes`")
        if contains_text:
            applied_filters.append(f"• Contains: \"`{contains_text}`\"")

        filter_details = "\n".join(applied_filters) if applied_filters else "• None (all messages)"

        embed = discord.Embed(title="Purge Completed", color=discord.Color.green(), timestamp=discord.utils.utcnow())
        embed.add_field(name="Scanned Scope", value=f"`{amount}` messages", inline=True)
        embed.add_field(name="Deleted Count", value=f"`{len(deleted)}` messages", inline=True)
        embed.add_field(name="Applied Filters", value=filter_details, inline=False)
        embed.set_footer(text="Note: Messages older than 14 days cannot be bulk-deleted.")

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="meme", description="Let me fetch a random meme from the wonders of the world wide web!")
    async def meme(self, interaction: discord.Interaction):
        url = "https://meme-api.com/gimme"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url) as response:
                    if response.status != 200:
                        await interaction.response.send_message("Could not fetch a meme right now. Try again later. In the meantime, want me to fetch my ball? :dog::tennis:")
                        return
                    
                    data = await response.json()
                    embed = discord.Embed(title=data.get("title", "Meme"), url=data.get("postLink"), color=discord.Color.blurple())
                    embed.set_image(url=data.get("url"))
                    embed.set_footer(text=f"from r/{data.get('subreddit')}")
                    
                    await interaction.response.send_message(embed=embed)
                    
            except aiohttp.ClientError:
                await interaction.response.send_message("Network error occurred while fetching the meme. :pleading_face:")

async def setup(bot: commands.Bot):
    await bot.add_cog(General(bot))