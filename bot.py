import discord
from discord.ext import commands
import os
import logging
import asyncio
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "bot_token.env"))
bot_token = os.getenv("BOT_TOKEN")
channel_id_str = os.getenv("CHANNEL_ID")

if not bot_token or not channel_id_str:
    raise ValueError("Missing BOT_TOKEN or CHANNEL_ID in environment variables")

try:
    CHANNEL_ID = int(channel_id_str)
except ValueError:
    raise ValueError("CHANNEL_ID environment variable must be an integer")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.dm_messages = True

bot = commands.Bot(command_prefix="~", intents=intents)

logging.basicConfig(level=logging.INFO, format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')
logger = logging.getLogger(__name__)

@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        try:
            await channel.send(
                "Heya! Anna here! My knowledge is mostly from early 2023. "
                "For fresh info, use `~search <query>`."
            )
        except Exception as e:
            logger.warning(f"Failed to send startup message: {e}")
    else:
        logger.warning(f"Channel with ID {CHANNEL_ID} not found.")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("Unknown command. Try `~help`.")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("You lack permissions to do that.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Missing argument `{error.param.name}`. See `~help {ctx.command}`.")
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"Cooldown active. Try again in {error.retry_after:.1f}s.")
    else:
        logger.error(f"Error in command {ctx.command}: {error}", exc_info=True)
        await ctx.send("An error occurred. Please try again later.")

bot.remove_command('help')

async def main():
    await bot.load_extension("cogs.hello")
    await bot.load_extension("cogs.help")
    await bot.load_extension("cogs.add")
    await bot.load_extension("cogs.utils")
    await bot.load_extension("cogs.genai")
    await bot.load_extension("cogs.wolfram")
    await bot.start(bot_token)

try:
    asyncio.run(main())
except KeyboardInterrupt:
    print("Bot stopped by user.")