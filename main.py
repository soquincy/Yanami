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

bot_token = str(bot_token)

try:
    CHANNEL_ID = int(channel_id_str)
except ValueError:
    raise ValueError("CHANNEL_ID environment variable must be an integer")

# Define the Bot Class to handle setup and syncing
class Freesona(commands.Bot):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def setup_hook(self):
        # List of your extensions
        extensions = [
            "cogs.ytdlp", "cogs.hello", "cogs.help", 
            "cogs.utils", "cogs.genai", "cogs.wolfram", "cogs.status"
        ]
        for ext in extensions:
            await self.load_extension(ext)
        
        # Syncing slash commands globally
        await self.tree.sync()
        print(f"Synced slash commands for {self.user}")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.dm_messages = True
intents.guilds = True

# Initialize using the new class
bot = Freesona(command_prefix="~", intents=intents)
bot.remove_command('help')

logging.basicConfig(level=logging.INFO, format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')
logger = logging.getLogger(__name__)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    try:
        # This syncs commands globally. 
        # Note: Global sync can take up to an hour to propagate.
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Error syncing tree: {e}")

    user = bot.user
    if user is None: return
    logger.info(f"Logged in as {user} (ID: {user.id})")

    bot_name = os.getenv("BOT_NAME", "Bot") 
    channel = bot.get_channel(CHANNEL_ID)
    if isinstance(channel, abc.Messageable):
        try:
            await channel.send(
                f"Heya! {bot_name} here! My knowledge is mostly from late 2025. "
                "For fresh info, use `~search <query>`."
            )
        except Exception as e:
            logger.warning(f"Failed to send startup message: {e}")

        
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

async def start_http():
    config = uvicorn.Config(app, host="0.0.0.0", port=10000, log_level="warning")
    server = uvicorn.Server(config)
    await server.serve()

async def start_bot():
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