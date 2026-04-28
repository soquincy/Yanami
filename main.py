import discord
from discord.ext import commands
from discord import abc
import os
import logging
import asyncio
import uvicorn
import json
from fastapi_server import app
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "actual.env"))

# --- Configuration & Persistence Setup ---
bot_token = os.getenv("BOT_TOKEN")
channel_id_str = os.getenv("CHANNEL_ID")
# Use /etc/secrets/config.json if in cloud, otherwise local config.json
CONFIG_PATH = os.getenv("CONFIG_FILE_PATH", "config.json")

if not bot_token or not channel_id_str:
    raise ValueError("Missing BOT_TOKEN or CHANNEL_ID in environment variables")

try:
    CHANNEL_ID = int(channel_id_str)
except ValueError:
    raise ValueError("CHANNEL_ID must be an integer")

def get_prefix(bot, message):
    """Reads the prefix from the persistent JSON file."""
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r") as f:
                data = json.load(f)
                return data.get("prefix", "~")
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return "~"

# --- Bot Class Definition ---
class Freesona(commands.Bot):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def setup_hook(self):
        extensions = [
            "cogs.ytdlp", "cogs.hello", "cogs.help", 
            "cogs.utils", "cogs.genai", "cogs.wolfram", "cogs.status"
        ]
        for ext in extensions:
            await self.load_extension(ext)
        
        await self.tree.sync()
        print(f"Synced slash commands for {self.user}")

# Initialize Bot
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.dm_messages = True
intents.guilds = True

bot = Freesona(command_prefix=get_prefix, intents=intents)
bot.remove_command('help')

logging.basicConfig(level=logging.INFO, format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')
logger = logging.getLogger(__name__)

# --- Commands & Events ---

@bot.command(name="prefix")
@commands.has_permissions(administrator=True)
async def change_prefix(ctx, new_prefix: str):
    """Changes the bot prefix and saves it to /etc/secrets/config.json"""
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump({"prefix": new_prefix}, f)
        await ctx.send(f"Prefix updated to: `{new_prefix}`")
    except Exception as e:
        logger.error(f"Failed to save prefix: {e}")
        await ctx.send("Error saving prefix to persistent storage.")

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Error syncing tree: {e}")

    channel = bot.get_channel(CHANNEL_ID)
    if isinstance(channel, abc.Messageable):
        bot_name = os.getenv("BOT_NAME", "Bot")
        try:
            current_p = get_prefix(bot, None)
            await channel.send(
                f"Heya! {bot_name} here! Current prefix is `{current_p}`. "
                "For fresh info, use `~search <query>`."
            )
        except Exception as e:
            logger.warning(f"Failed to send startup message: {e}")

# --- Background Tasks & Execution ---

async def start_http():
    config = uvicorn.Config(app, host="0.0.0.0", port=10000, log_level="warning")
    server = uvicorn.Server(config)
    await server.serve()

async def start_bot():
    await bot.start(str(bot_token))

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