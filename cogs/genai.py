import os
import re
import asyncio
import logging
import requests
import discord
import urllib.parse
from datetime import timedelta, datetime
from typing import Optional

from discord.ext import commands
from discord import app_commands, ui
from dotenv import load_dotenv
from google import genai

# Load .env variables
load_dotenv()

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("FreesonaBot")

# --- Configuration & Paths ---
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_SEARCH_API_KEY = os.getenv("GOOGLE_SEARCH_API_KEY")
SEARCH_ENGINE_ID = os.getenv("SEARCH_ENGINE_ID")
BOT_NAME = os.getenv("BOT_NAME", "Bot")

# Update this variable in Railway to /etc/secrets/persona.txt
AI_PERSONA_PATH = os.getenv("AI_PERSONA_FILE", "/etc/secrets/persona.txt")
MODEL_NAME = "gemini-flash-latest"

# Ensure required keys exist
if not GOOGLE_API_KEY:
    raise EnvironmentError("GOOGLE_API_KEY is missing from environment variables.")

# --- Persistence Logic ---

def load_persona():
    """Reads persona from volume; falls back to env var or default string."""
    if os.path.exists(AI_PERSONA_PATH):
        try:
            with open(AI_PERSONA_PATH, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    logger.info("Loaded persona from volume.")
                    return content
        except Exception as e:
            logger.error(f"Error reading persona file: {e}")
    
    logger.info("Persona file not found or empty. Using fallback.")
    return os.getenv("AI_PERSONA", "You are a helpful assistant.")

# Live variable used by the AI
CURRENT_PERSONA = load_persona()

# --- Gemini Client ---
try:
    client = genai.Client(api_key=GOOGLE_API_KEY)
    logger.info("Gemini client initialized successfully.")
except Exception as e:
    logger.error(f"Failed to initialize Gemini: {e}")
    raise

# Rate limiter (5 requests per minute)
api_semaphore = asyncio.Semaphore(5)

# --- UI Components ---

class PersonaModal(ui.Modal, title='Update AI Persona'):
    """Pop-up editor for the bot's personality."""
    persona_input = ui.TextInput(
        label='Instructions (Saved to Volume)',
        style=discord.TextStyle.paragraph,
        placeholder='e.g. You are a helpful assistant that speaks in short sentences.',
        required=True,
        max_length=2000,
    )

    def __init__(self):
        super().__init__()
        self.persona_input.default = CURRENT_PERSONA

    async def on_submit(self, interaction: discord.Interaction):
        global CURRENT_PERSONA
        new_persona = self.persona_input.value
        
        # Update the live memory
        CURRENT_PERSONA = new_persona
        
        # Save to the Railway Volume
        try:
            # This 'w' mode creates the file automatically if it doesn't exist
            with open(AI_PERSONA_PATH, "w", encoding="utf-8") as f:
                f.write(new_persona)
            
            await interaction.response.send_message(
                f"✅ **Persona updated!** Changes saved to `{AI_PERSONA_PATH}`.", 
                ephemeral=True
            )
            logger.info(f"Persona updated and saved to volume by {interaction.user}")
        except Exception as e:
            await interaction.response.send_message(
                f"❌ **Failed to save to volume:** {e}", 
                ephemeral=True
            )
            logger.error(f"File write error: {e}")

# --- Core AI Logic ---

async def generate_gemini_content(prompt: str, apply_persona: bool = True) -> str:
    global CURRENT_PERSONA
    
    if apply_persona and CURRENT_PERSONA:
        full_prompt = f"{CURRENT_PERSONA}\n\nUser: {prompt}\n{BOT_NAME}:"
    else:
        full_prompt = prompt

    async with api_semaphore:
        try:
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=MODEL_NAME,
                contents=full_prompt
            )
            return response.text if response.text else "The AI returned an empty response."
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return f"Error: {e}"

async def web_search(query: str) -> str:
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": GOOGLE_SEARCH_API_KEY, 
        "cx": SEARCH_ENGINE_ID, 
        "q": query, 
        "num": 5
    }
    try:
        response = await asyncio.to_thread(requests.get, url, params=params, timeout=10)
        data = response.json()
        items = data.get("items", [])
        if not items: return "No results."
        return "\n".join([f"- {i['title']}: {i['snippet']} ({i['link']})" for i in items])
    except Exception as e:
        logger.error(f"Search error: {e}")
        return "Search service unavailable."

# --- Discord Cog ---

class GenAICog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name='setpersona', help='Update the bots personality (Owner only).')
    @commands.is_owner()
    async def set_persona(self, ctx):
        """Opens a modal to change the bot's system instructions."""
        if ctx.interaction:
            await ctx.interaction.response.send_modal(PersonaModal())
        else:
            await ctx.send("Please use the slash command `/setpersona` to open the editor.")

    @commands.hybrid_command(name='write', aliases=['ask'], help='Ask the AI anything.')
    @app_commands.describe(query="Your question or prompt for the AI.")
    async def write_cmd(self, ctx, *, query: str):
        await ctx.defer()
        
        response_text = await generate_gemini_content(query)
        
        embed = discord.Embed(
            title=f"✨ {BOT_NAME}",
            description=response_text[:4000],
            color=discord.Color.brand_green()
        )
        embed.set_footer(text=f"Asked by {ctx.author}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='search', help='Search Google and summarize with AI.')
    @app_commands.describe(query="The topic you want to research.")
    async def search_cmd(self, ctx, *, query: str):
        await ctx.defer()
        
        results = await web_search(query)
        summary_prompt = f"Summarize these search results for the query '{query}':\n\n{results}"
        summary = await generate_gemini_content(summary_prompt, apply_persona=False)

        embed = discord.Embed(
            title=f"🔎 Search Results: {query}",
            description=summary[:4000],
            color=discord.Color.blue()
        )
        search_url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
        embed.add_field(name="Sources", value=f"[View Google Search]({search_url})")
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(GenAICog(bot))