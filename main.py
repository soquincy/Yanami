import discord
from discord.ext import commands
from discord import abc
import os
import logging
import asyncio
import uvicorn
from fastapi_server import app
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "actual.env"))

bot_token = os.getenv("BOT_TOKEN")
channel_id_str = os.getenv("CHANNEL_ID")

if not bot_token or not channel_id_str:
    raise ValueError("Missing BOT_TOKEN or CHANNEL_ID in environment variables")

# Explicitly cast so Pylance knows these are str, not str | None
bot_token = str(bot_token)

try:
    CHANNEL_ID = int(channel_id_str)
except ValueError:
    raise ValueError("CHANNEL_ID environment variable must be an integer")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.dm_messages = True
intents.guilds = True

bot = commands.Bot(command_prefix="~", intents=intents)

logging.basicConfig(level=logging.INFO, format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')
logger = logging.getLogger(__name__)


@bot.event
async def on_ready():
    user = bot.user
    if user is None:
        return
    logger.info(f"Logged in as {user} (ID: {user.id})")

    # Get the name from .env
    bot_name = os.getenv("BOT_NAME", "Bot") 

    channel = bot.get_channel(CHANNEL_ID)
    if isinstance(channel, abc.Messageable):
        try:
            # Use an f-string to inject the variable
            await channel.send(
                f"Heya! {bot_name} here! My knowledge is mostly from late 2025. "
                "For fresh info, use `~search <query>`."
            )
        except Exception as e:
            logger.warning(f"Failed to send startup message: {e}")
    else:
        logger.warning(f"Channel with ID {CHANNEL_ID} not found or does not support messages.")


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


async def start_http():
    config = uvicorn.Config(app, host="0.0.0.0", port=10000, log_level="warning")
    server = uvicorn.Server(config)
    await server.serve()


async def start_bot():
    await bot.load_extension("cogs.ytdlp")
    await bot.load_extension("cogs.hello")
    await bot.load_extension("cogs.help")
    await bot.load_extension("cogs.utils")
    await bot.load_extension("cogs.genai")
    await bot.load_extension("cogs.wolfram")
    await bot.load_extension("cogs.status")
    assert bot_token is not None
    await bot.start(bot_token)


async def main():
    await asyncio.gather(
        start_http(),
        start_bot()
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped.")