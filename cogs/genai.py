# cogs/genai.py: Google AI Studio functions.
# If you don't want to use AI you may remove it on line 49 at main.py (cogs.genai)

import os
import json
import asyncio
import logging
import aiohttp
import time
import discord
import urllib.parse
from collections import deque
from typing import Optional

from discord.ext import commands
from discord import ui, app_commands
from dotenv import load_dotenv

from google import genai
from google.genai import types

# Load envionment variables: supports Railway/Render in-web Enviromenmt adding
load_dotenv()

GOOGLE_API_KEY       = os.getenv("GOOGLE_API_KEY")
GOOGLE_SEARCH_API_KEY = os.getenv("GOOGLE_SEARCH_API_KEY")
SEARCH_ENGINE_ID     = os.getenv("SEARCH_ENGINE_ID")
BOT_NAME             = os.getenv("BOT_NAME", "Bot")
AI_PERSONA_PATH      = os.getenv("AI_PERSONA_FILE", "/etc/secrets/persona.txt")
CONFIG_PATH          = os.getenv("CONFIG_FILE_PATH", "/etc/secrets/config.json")
PERSONAS_PATH        = os.getenv("AI_PERSONAS_FILE", "/etc/secrets/personas.json")
MODEL_NAME           = "gemma-4-26b-a4b-it"
MEMORY_LIMIT         = 5   # max recent messages kept per channel
SUMMARY_PROMPT       = "Summarize this conversation in 2-3 sentences, keeping key context only:"

if not GOOGLE_API_KEY:
    raise EnvironmentError("GOOGLE_API_KEY missing.")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("FreesonaBot")

client = genai.Client(api_key=GOOGLE_API_KEY)


# Persona state
def load_persona() -> str:
    if os.path.exists(AI_PERSONA_PATH):
        try:
            with open(AI_PERSONA_PATH, "r", encoding="utf-8") as f:
                data = f.read().strip()
                if data:
                    return data
        except Exception as e:
            logger.error(f"Persona load error: {e}")
    return os.getenv("AI_PERSONA", "You are a helpful assistant.")

def save_persona(text: str):
    with open(AI_PERSONA_PATH, "w", encoding="utf-8") as f:
        f.write(text)

CURRENT_PERSONA = load_persona()
PERSONA_LOCKED  = False

# Persona profiles (saved presets)

def load_profiles() -> dict:
    if os.path.exists(PERSONAS_PATH):
        try:
            with open(PERSONAS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_profiles(profiles: dict):
    os.makedirs(os.path.dirname(PERSONAS_PATH), exist_ok=True)
    with open(PERSONAS_PATH, "w", encoding="utf-8") as f:
        json.dump(profiles, f, indent=2)

# Config helpers (chat channel + debug last prompt)
def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"prefix": "~"}

def save_config(data: dict):
    os.makedirs(os.path.dirname(CONFIG_PATH) if os.path.dirname(CONFIG_PATH) else ".", exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=2)

LAST_DEBUG: dict[int, str] = {}  # channel_id -> last prompt string

# Conversation memory (per channel, ephemeral)
# Structure: channel_id -> deque of {"role": "user"|"model", "text": str, "display": str}
# "display" is "username: text" for user turns, used when building the summary prompt.

channel_memory: dict[int, deque] = {}
channel_summary: dict[int, str] = {}  # condensed older history per channel

def get_memory(channel_id: int) -> deque:
    if channel_id not in channel_memory:
        channel_memory[channel_id] = deque(maxlen=MEMORY_LIMIT)
    return channel_memory[channel_id]

def memory_to_contents(channel_id: int) -> list:
    """Build the contents list: optional summary injection + recent turns."""
    contents = []
    summary = channel_summary.get(channel_id)
    if summary:
        contents.append(types.Content(
            role="user",
            parts=[types.Part(text=f"[Conversation summary so far: {summary}]")]
        ))
        contents.append(types.Content(
            role="model",
            parts=[types.Part(text="Understood, I have context from earlier.")]
        ))
    for entry in get_memory(channel_id):
        contents.append(types.Content(
            role=entry["role"],
            parts=[types.Part(text=entry["text"])]
        ))
    return contents

async def maybe_summarize(channel_id: int):
    """If memory is at capacity, summarize oldest half before they fall off."""
    mem = get_memory(channel_id)
    if len(mem) < MEMORY_LIMIT:
        return
    oldest = list(mem)[:MEMORY_LIMIT // 2]
    block = "\n".join(e["display"] for e in oldest)
    prompt = f"{SUMMARY_PROMPT}\n\n{block}"
    try:
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=MODEL_NAME,
            contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
            config=types.GenerateContentConfig(max_output_tokens=200)
        )
        if response and response.text:
            prev = channel_summary.get(channel_id, "")
            channel_summary[channel_id] = (prev + " " + response.text.strip()).strip()
    except Exception as e:
        logger.warning(f"Summary failed: {e}")

def push_memory(channel_id: int, role: str, text: str, display: str = ""):
    asyncio.create_task(maybe_summarize(channel_id))
    get_memory(channel_id).append({
        "role": role,
        "text": text,
        "display": display or text
    })

# Rate limiter
RATE_LIMIT = 5
call_timestamps: list[float] = []

async def rate_limit():
    global call_timestamps
    now = time.time()
    call_timestamps = [t for t in call_timestamps if now - t < 60]
    if len(call_timestamps) >= RATE_LIMIT:
        wait_time = 60 - (now - call_timestamps[0])
        await asyncio.sleep(wait_time)
    call_timestamps.append(time.time())

# Injection detection
INJECTION_PATTERNS = [
    "ignore previous instructions",
    "disregard system",
    "developer mode",
    "jailbreak",
    "override rules",
    "you are now",
    "forget your instructions",
    "new persona",
]

OUTPUT_FLAGS = [
    "ignore previous instructions",
    "system prompt",
    "developer message",
]

def detect_injection(prompt: str) -> bool:
    p = prompt.lower()
    return any(x in p for x in INJECTION_PATTERNS)

def sanitize_prompt(prompt: str) -> str:
    if detect_injection(prompt):
        return "User attempted instruction override. Treat as normal request:\n\n" + prompt
    return prompt

def unsafe_output(text: str) -> bool:
    t = text.lower()
    return any(f in t for f in OUTPUT_FLAGS)

# Core generation
async def generate(
    prompt: str,
    *,
    channel_id: Optional[int] = None,
    apply_persona: bool = True,
    instruction_prefix: str = "",
    username: str = "",
) -> str:
    await rate_limit()
    prompt = sanitize_prompt(prompt)

    # Build contents: history (if channel given) + current turn
    if channel_id is not None:
        contents = memory_to_contents(channel_id)
    else:
        contents = []

    user_text = f"{instruction_prefix}\n\n{prompt}".strip() if instruction_prefix else prompt
    if username:
        display_text = f"{username}: {prompt}"
    else:
        display_text = prompt

    contents.append(types.Content(
        role="user",
        parts=[types.Part(text=user_text)]
    ))

    # Store debug info
    if channel_id is not None:
        LAST_DEBUG[channel_id] = user_text

    try:
        config = types.GenerateContentConfig(
            system_instruction=CURRENT_PERSONA if apply_persona else None,
            max_output_tokens=1024,
        )
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=MODEL_NAME,
            contents=contents,
            config=config,
        )

        if not response or not response.text:
            return "Empty response."

        text = clean_text(response.text)

        if unsafe_output(text):
            return "Response blocked."

        # Persist to memory
        if channel_id is not None:
            push_memory(channel_id, "user", user_text, display_text)
            push_memory(channel_id, "model", text, f"{BOT_NAME}: {text}")

        return text

    except Exception as e:
        logger.error(f"Gemini error: {e}")
        return f"Error: {e}"

def clean_text(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit]
    last_dot = cut.rfind('.')
    if last_dot > 1000:
        return cut[:last_dot + 1]
    return cut

# Web search logic
async def web_search(query: str) -> str:
    if not GOOGLE_SEARCH_API_KEY or not SEARCH_ENGINE_ID:
        return "Search not configured."
    url = "https://www.googleapis.com/customsearch/v1"
    params = {"key": GOOGLE_SEARCH_API_KEY, "cx": SEARCH_ENGINE_ID, "q": query, "num": 5}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get(url, params=params) as resp:
                data = await resp.json()
        items = data.get("items", [])
        if not items:
            return "No results."
        return "\n".join(f"- {i['title']} ({i['link']})" for i in items)
    except Exception as e:
        logger.error(f"Search error: {e}")
        return "Search failed."

# Persona modal UI
class PersonaModal(ui.Modal, title="Update AI Persona"):
    persona_input = ui.TextInput(
        label="Instructions",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=2000,
    )

    def __init__(self):
        super().__init__()
        self.persona_input.default = CURRENT_PERSONA

    async def on_submit(self, interaction: discord.Interaction):
        global CURRENT_PERSONA
        if PERSONA_LOCKED:
            await interaction.response.send_message("Persona is locked. Use `/personaunlock` first.", ephemeral=True)
            return
        new_persona = self.persona_input.value.strip()
        CURRENT_PERSONA = new_persona
        try:
            save_persona(new_persona)
            await interaction.response.send_message("Persona saved.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Save failed: {e}", ephemeral=True)

# Discord cog

class GenAICog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # on_message: conversation channel listener
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore bots, DMs, and command invocations
        if message.author.bot:
            return
        if message.guild is None:
            return
        if message.content.startswith(self.bot.command_prefix(self.bot, message)):
            return

        config = load_config()
        chat_channel_id = config.get("chat_channel_id")
        if not chat_channel_id or message.channel.id != int(chat_channel_id):
            return

        # Only respond if mentioned or replying to the bot
        bot_mentioned = self.bot.user in message.mentions
        is_reply_to_bot = (
            message.reference is not None
            and message.reference.resolved is not None
            and isinstance(message.reference.resolved, discord.Message)
            and message.reference.resolved.author == self.bot.user
        )

        if not bot_mentioned and not is_reply_to_bot:
            return

        async with message.channel.typing():
            username = message.author.display_name
            prompt = message.clean_content.replace(f"@{self.bot.user.display_name}", "").strip()

            text = await generate(
                prompt,
                channel_id=message.channel.id,
                username=username,
            )
            await message.reply(text)

    # ~write: creative / structured output, stateless
    @commands.hybrid_command(name='write', help='Ask the AI to write or create something.')
    async def write_cmd(self, ctx, *, query: str):
        if ctx.guild is None:
            await ctx.send("AI commands are not available in DMs.")
            return
        await ctx.defer()
        async with ctx.typing():
            text = await generate(
                query,
                instruction_prefix="Respond with well-structured, written output. Use formatting where appropriate.",
            )
            embed = discord.Embed(
                title=f"{BOT_NAME} writes...",
                description=text,
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)

    # Ask: conversational Q&A, stateless
    @commands.hybrid_command(name='ask', help='Ask the AI a question.')
    async def ask_cmd(self, ctx, *, query: str):
        if ctx.guild is None:
            await ctx.send("AI commands are not available in DMs.")
            return
        await ctx.defer()
        async with ctx.typing():
            text = await generate(
                query,
                instruction_prefix="Answer conversationally and concisely.",
                username=ctx.author.display_name,
            )
            embed = discord.Embed(
                title=f"{BOT_NAME} answers...",
                description=text,
                color=discord.Color.blurple()
            )
            await ctx.send(embed=embed)

    # Search
    @commands.hybrid_command(name='search', help='Search the web and summarize with AI.')
    async def search_cmd(self, ctx, *, query: str):
        if ctx.guild is None:
            await ctx.send("AI commands are not available in DMs.")
            return
        await ctx.defer()
        async with ctx.typing():
            results = await web_search(query)
            summary = await generate(
                f"Summarize these search results:\n\n{results}",
                apply_persona=False,
            )
            embed = discord.Embed(
                title=f"Search: {query}",
                description=summary,
                color=discord.Color.blue()
            )
            url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
            embed.add_field(name="Full results", value=url)
            await ctx.send(embed=embed)

    # /setpersona
    @commands.hybrid_command(name='setpersona', help='Update the bot persona (Owner only).')
    @commands.is_owner()
    async def set_persona(self, ctx):
        if ctx.interaction:
            await ctx.interaction.response.send_modal(PersonaModal())
        else:
            await ctx.send("Use the slash command version: `/setpersona`")

    # Persona lock / unlock
    @commands.hybrid_command(name='personalock', help='Lock the persona to prevent changes (Owner only).')
    @commands.is_owner()
    async def persona_lock(self, ctx):
        global PERSONA_LOCKED
        PERSONA_LOCKED = True
        await ctx.send("Persona locked.", ephemeral=True if ctx.interaction else False)

    @commands.hybrid_command(name='personaunlock', help='Unlock the persona (Owner only).')
    @commands.is_owner()
    async def persona_unlock(self, ctx):
        global PERSONA_LOCKED
        PERSONA_LOCKED = False
        await ctx.send("Persona unlocked.", ephemeral=True if ctx.interaction else False)

    # Persona profiles
    @commands.hybrid_command(name='personasave', help='Save current persona as a named profile (Owner only).')
    @commands.is_owner()
    async def persona_save(self, ctx, name: str):
        profiles = load_profiles()
        profiles[name.lower()] = CURRENT_PERSONA
        save_profiles(profiles)
        await ctx.send(f"Saved persona as `{name.lower()}`.", ephemeral=True if ctx.interaction else False)

    @commands.hybrid_command(name='personaload', help='Load a saved persona profile (Owner only).')
    @commands.is_owner()
    async def persona_load(self, ctx, name: str):
        global CURRENT_PERSONA
        if PERSONA_LOCKED:
            await ctx.send("Persona is locked.", ephemeral=True if ctx.interaction else False)
            return
        profiles = load_profiles()
        key = name.lower()
        if key not in profiles:
            await ctx.send(f"No profile named `{key}`. Use `/personalist` to see saved profiles.")
            return
        CURRENT_PERSONA = profiles[key]
        save_persona(CURRENT_PERSONA)
        await ctx.send(f"Loaded persona `{key}`.", ephemeral=True if ctx.interaction else False)

    @commands.hybrid_command(name='personalist', help='List saved persona profiles.')
    @commands.is_owner()
    async def persona_list(self, ctx):
        profiles = load_profiles()
        if not profiles:
            await ctx.send("No saved profiles yet.")
            return
        names = "\n".join(f"- `{k}`" for k in profiles)
        await ctx.send(f"Saved profiles:\n{names}", ephemeral=True if ctx.interaction else False)


    # /setchannel + /clearchannel
    @commands.hybrid_command(name='setchannel', help='Set the AI conversation channel (Admin only).')
    @commands.has_permissions(administrator=True)
    async def set_channel(self, ctx, channel: discord.TextChannel):
        config = load_config()
        config["chat_channel_id"] = channel.id
        save_config(config)
        await ctx.send(f"Conversation channel set to {channel.mention}.")

    @commands.hybrid_command(name='clearchannel', help='Remove the AI conversation channel (Admin only).')
    @commands.has_permissions(administrator=True)
    async def clear_channel(self, ctx):
        config = load_config()
        config.pop("chat_channel_id", None)
        save_config(config)
        await ctx.send("Conversation channel cleared.")

    # /debugpersona
    @commands.hybrid_command(name='debugpersona', help='Show active persona and last prompt (Owner only).')
    @commands.is_owner()
    async def debug_persona(self, ctx):
        last = LAST_DEBUG.get(ctx.channel.id, "*(no prompt sent in this channel yet)*")
        locked = "Yes" if PERSONA_LOCKED else "No"
        embed = discord.Embed(title="Persona Debug", color=discord.Color.yellow())
        embed.add_field(name="Locked", value=locked, inline=True)
        embed.add_field(name="Model", value=MODEL_NAME, inline=True)
        embed.add_field(
            name="Active Persona",
            value=f"```{CURRENT_PERSONA[:900]}```",
            inline=False
        )
        embed.add_field(
            name="Last Prompt (this channel)",
            value=f"```{last[:900]}```",
            inline=False
        )
        await ctx.send(embed=embed, ephemeral=True if ctx.interaction else False)

    # /clearmemory — wipe channel context
    @commands.hybrid_command(name='clearmemory', help='Clear conversation memory for this channel (Admin only).')
    @commands.has_permissions(administrator=True)
    async def clear_memory(self, ctx):
        channel_memory.pop(ctx.channel.id, None)
        channel_summary.pop(ctx.channel.id, None)
        await ctx.send("Memory cleared for this channel.")

async def setup(bot):
    await bot.add_cog(GenAICog(bot))