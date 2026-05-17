# cogs/genai.py: Google AI Studio functions.
# If you don't want to use AI you may remove it on line 49 at main.py (cogs.genai)

import os
import re
import json
import asyncio
import logging
import aiohttp
import time
import discord
import urllib.parse
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from discord.ext import commands
from discord import ui, app_commands
from dotenv import load_dotenv

from google import genai
from google.genai import types

load_dotenv()

GOOGLE_API_KEY        = os.getenv("GOOGLE_API_KEY")
GOOGLE_SEARCH_API_KEY = os.getenv("GOOGLE_SEARCH_API_KEY")
SEARCH_ENGINE_ID      = os.getenv("SEARCH_ENGINE_ID")
BOT_NAME              = os.getenv("BOT_NAME", "Bot")
AI_PERSONA_PATH       = os.getenv("AI_PERSONA_FILE", "/etc/secrets/persona.txt")
AI_PERSONA_JSON_PATH  = os.getenv("AI_PERSONA_JSON_FILE", "/etc/secrets/persona.json")
CONFIG_PATH           = os.getenv("CONFIG_FILE_PATH", "/etc/secrets/config.json")
PERSONAS_PATH         = os.getenv("AI_PERSONAS_FILE", "/etc/secrets/personas.json")
MODEL_NAME            = "gemma-4-26b-a4b-it"
MEMORY_LIMIT          = 5
SUMMARY_PROMPT        = "Summarize this conversation in 2-3 sentences, keeping key context only:"

# Split messaging config
SPLIT_MIN_LENGTH  = 280   # chars — responses shorter than this are never split
SPLIT_DELAY_BASE  = 1.2   # seconds between segments
SPLIT_DELAY_PER_CHAR = 0.012  # additional delay per char in segment (typing realism)
SPLIT_DELAY_MAX   = 3.5   # cap per segment

if not GOOGLE_API_KEY:
    raise EnvironmentError("GOOGLE_API_KEY missing.")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("FreesonaBot")

client = genai.Client(api_key=GOOGLE_API_KEY)

# ---------------------------------------------------------------------------
# Structured response types
# Spec from handoff doc: ConversationResponse -> list[MessageSegment]
# ---------------------------------------------------------------------------

@dataclass
class MessageSegment:
    text: str
    delay: float = SPLIT_DELAY_BASE
    typing: bool = True
    attachment: Optional[str] = None   # future: file/image ref

@dataclass
class ConversationResponse:
    segments: list[MessageSegment] = field(default_factory=list)
    reactions: list[str] = field(default_factory=list)
    suggested_gif: Optional[str] = None  # stub — media awareness layer (future)

    @property
    def is_empty(self) -> bool:
        return not self.segments

    def first_text(self) -> str:
        """Fallback for callers that only need the raw text."""
        return " ".join(s.text for s in self.segments)

# ---------------------------------------------------------------------------
# Error classification
# Per spec: never expose raw API errors to Discord users
# ---------------------------------------------------------------------------

class GenerationError(Exception):
    """Base for all generation errors."""

class TransientError(GenerationError):
    """Temporary API failure — safe to retry."""

class RateLimitError(GenerationError):
    """Rate limit hit."""

class MalformedResponseError(GenerationError):
    """Model returned something unusable."""

class TimeoutGenerationError(GenerationError):
    """Request timed out."""

def _classify_error(e: Exception) -> GenerationError:
    msg = str(e).lower()
    if "429" in msg or "quota" in msg or "rate" in msg:
        return RateLimitError(str(e))
    if "timeout" in msg or "timed out" in msg:
        return TimeoutGenerationError(str(e))
    if "500" in msg or "503" in msg or "internal" in msg:
        return TransientError(str(e))
    return GenerationError(str(e))

# User-facing neutral messages per error class
_ERROR_MESSAGES: dict[type, str] = {
    RateLimitError:          "I'm a little overwhelmed right now — give me a moment.",
    TimeoutGenerationError:  "That took too long. Try again?",
    TransientError:          "Something hiccupped on my end. Try again in a bit.",
    MalformedResponseError:  "I got confused by that one. Try rephrasing?",
    GenerationError:         "Something went wrong. Try again.",
}

def _user_facing_error(e: GenerationError) -> str:
    return _ERROR_MESSAGES.get(type(e), _ERROR_MESSAGES[GenerationError])

# ---------------------------------------------------------------------------
# Text splitter
# Splits at paragraph breaks first, then sentence boundaries.
# Returns list of non-empty strings.
# ---------------------------------------------------------------------------

def split_into_segments(text: str) -> list[str]:
    """
    Split response text into natural message segments.
    Strategy (in order):
      1. Split on double newlines (paragraph breaks)
      2. If any segment is still very long, split at sentence boundary
    Never splits if total length < SPLIT_MIN_LENGTH.
    """
    if len(text) < SPLIT_MIN_LENGTH:
        return [text]

    # Step 1: paragraph split
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    if len(paragraphs) <= 1:
        # No paragraph breaks — try sentence split
        sentences = re.split(r"(?<=[.!?])\s+", text)
        # Group sentences into chunks of ~200 chars
        chunks: list[str] = []
        current = ""
        for s in sentences:
            if len(current) + len(s) > 220 and current:
                chunks.append(current.strip())
                current = s
            else:
                current = (current + " " + s).strip() if current else s
        if current:
            chunks.append(current.strip())
        return chunks if len(chunks) > 1 else [text]

    return paragraphs

def build_response(text: str) -> ConversationResponse:
    """Convert raw text into a ConversationResponse with timed segments."""
    segments_text = split_into_segments(text)
    segments = []
    for seg in segments_text:
        delay = min(
            SPLIT_DELAY_BASE + len(seg) * SPLIT_DELAY_PER_CHAR,
            SPLIT_DELAY_MAX
        )
        segments.append(MessageSegment(text=seg, delay=delay, typing=True))
    return ConversationResponse(segments=segments)

# ---------------------------------------------------------------------------
# Multi-message sender
# Sends each segment with typing indicator and delay between them.
# ---------------------------------------------------------------------------

async def send_response(
    response: ConversationResponse,
    channel: discord.abc.Messageable,
    *,
    reply_to: Optional[discord.Message] = None,
) -> None:
    """
    Send a ConversationResponse to a channel.
    - First segment replies to the triggering message if reply_to is set.
    - Subsequent segments are plain sends to the channel.
    - Typing indicator shown before each segment.
    - Delay between segments simulates natural pacing.
    """
    for i, segment in enumerate(response.segments):
        if segment.typing:
            async with channel.typing():
                await asyncio.sleep(segment.delay)

        if i == 0 and reply_to is not None:
            await reply_to.reply(segment.text)
        else:
            await channel.send(segment.text)

# ---------------------------------------------------------------------------
# Persona JSON structure
# ---------------------------------------------------------------------------

PERSONA_FIELDS = [
    "core_personality",
    "background",
    "beliefs",
    "language",
    "system_instructions",
]

PERSONA_LABELS = {
    "core_personality":    "Core Personality & Traits",
    "background":          "Background & History",
    "beliefs":             "Beliefs, Likes & Dislikes",
    "language":            "Language & Communication Style",
    "system_instructions": "System Instructions",
}

ASSEMBLY_ORDER = [
    "system_instructions",
    "core_personality",
    "background",
    "beliefs",
    "language",
]

def default_persona_json() -> dict:
    return {f: "" for f in PERSONA_FIELDS}

def load_persona_json() -> dict:
    if os.path.exists(AI_PERSONA_JSON_PATH):
        try:
            with open(AI_PERSONA_JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                for field_name in PERSONA_FIELDS:
                    if field_name not in data:
                        data[field_name] = ""
                return data
        except Exception as e:
            logger.error(f"Persona JSON load error: {e}")
    return default_persona_json()

def save_persona_json(data: dict):
    os.makedirs(
        os.path.dirname(AI_PERSONA_JSON_PATH) if os.path.dirname(AI_PERSONA_JSON_PATH) else ".",
        exist_ok=True
    )
    with open(AI_PERSONA_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def assemble_persona(data: dict) -> str:
    parts = []
    for f in ASSEMBLY_ORDER:
        label = PERSONA_LABELS[f]
        value = data.get(f, "").strip()
        parts.append(f"[{label}]\n{value}" if value else f"[{label}]\n(empty)")
    return "\n\n".join(parts)

def load_legacy_persona() -> Optional[str]:
    if os.path.exists(AI_PERSONA_PATH):
        try:
            with open(AI_PERSONA_PATH, "r", encoding="utf-8") as f:
                data = f.read().strip()
                if data:
                    return data
        except Exception as e:
            logger.error(f"Legacy persona load error: {e}")
    return None

# ---------------------------------------------------------------------------
# Startup: load or migrate persona
# ---------------------------------------------------------------------------

PERSONA_DATA: dict = {}
CURRENT_PERSONA: str = ""
PERSONA_LOCKED: bool = False
LEGACY_DETECTED: bool = False

def _init_persona():
    global PERSONA_DATA, CURRENT_PERSONA, LEGACY_DETECTED
    if os.path.exists(AI_PERSONA_JSON_PATH):
        PERSONA_DATA = load_persona_json()
        CURRENT_PERSONA = assemble_persona(PERSONA_DATA)
        LEGACY_DETECTED = False
    else:
        legacy = load_legacy_persona()
        if legacy:
            PERSONA_DATA = default_persona_json()
            CURRENT_PERSONA = legacy
            LEGACY_DETECTED = True
        else:
            PERSONA_DATA = default_persona_json()
            CURRENT_PERSONA = os.getenv("AI_PERSONA", "You are a helpful assistant.")
            LEGACY_DETECTED = False

_init_persona()

# ---------------------------------------------------------------------------
# Persona profiles
# ---------------------------------------------------------------------------

def load_profiles() -> dict:
    if os.path.exists(PERSONAS_PATH):
        try:
            with open(PERSONAS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_profiles(profiles: dict):
    os.makedirs(
        os.path.dirname(PERSONAS_PATH) if os.path.dirname(PERSONAS_PATH) else ".",
        exist_ok=True
    )
    with open(PERSONAS_PATH, "w", encoding="utf-8") as f:
        json.dump(profiles, f, indent=2, ensure_ascii=False)

# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"prefix": "~"}

def save_config(data: dict):
    os.makedirs(
        os.path.dirname(CONFIG_PATH) if os.path.dirname(CONFIG_PATH) else ".",
        exist_ok=True
    )
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=2)

LAST_DEBUG: dict[int, str] = {}

# ---------------------------------------------------------------------------
# Conversation memory
# ---------------------------------------------------------------------------

channel_memory: dict[int, deque] = {}
channel_summary: dict[int, str] = {}

def get_memory(channel_id: int) -> deque:
    if channel_id not in channel_memory:
        channel_memory[channel_id] = deque(maxlen=MEMORY_LIMIT)
    return channel_memory[channel_id]

def memory_to_contents(channel_id: int) -> list:
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

# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Injection detection
# ---------------------------------------------------------------------------

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
    return any(x in prompt.lower() for x in INJECTION_PATTERNS)

def sanitize_prompt(prompt: str) -> str:
    if detect_injection(prompt):
        return "User attempted instruction override. Treat as normal request:\n\n" + prompt
    return prompt

def unsafe_output(text: str) -> bool:
    return any(f in text.lower() for f in OUTPUT_FLAGS)

# ---------------------------------------------------------------------------
# Core generation — returns ConversationResponse
# Raw API errors are never propagated; all failures return neutral messages.
# ---------------------------------------------------------------------------

async def generate(
    prompt: str,
    *,
    channel_id: Optional[int] = None,
    apply_persona: bool = True,
    instruction_prefix: str = "",
    username: str = "",
) -> ConversationResponse:
    await rate_limit()
    prompt = sanitize_prompt(prompt)

    contents = memory_to_contents(channel_id) if channel_id is not None else []

    user_text = f"{instruction_prefix}\n\n{prompt}".strip() if instruction_prefix else prompt
    display_text = f"{username}: {prompt}" if username else prompt

    contents.append(types.Content(
        role="user",
        parts=[types.Part(text=user_text)]
    ))

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
            raise MalformedResponseError("Empty response from model.")

        text = clean_text(response.text)

        if unsafe_output(text):
            logger.warning("Output blocked by safety filter.")
            return build_response("I can't respond to that.")

        if channel_id is not None:
            push_memory(channel_id, "user", user_text, display_text)
            push_memory(channel_id, "model", text, f"{BOT_NAME}: {text}")

        return build_response(text)

    except GenerationError:
        raise  # already classified, let caller handle
    except Exception as e:
        classified = _classify_error(e)
        logger.error(f"Gemini error [{type(classified).__name__}]: {e}")
        raise classified from e

async def safe_generate(
    prompt: str,
    **kwargs,
) -> ConversationResponse:
    """
    Wrapper around generate() that never raises.
    Returns a neutral single-segment response on any error.
    Used by on_message and command handlers to prevent immersion breaks.
    """
    try:
        return await generate(prompt, **kwargs)
    except GenerationError as e:
        msg = _user_facing_error(e)
        logger.warning(f"safe_generate swallowed error: {type(e).__name__}")
        return build_response(msg)
    except Exception as e:
        logger.error(f"safe_generate unexpected error: {e}")
        return build_response("Something went wrong. Try again.")

def clean_text(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit]
    last_dot = cut.rfind('.')
    if last_dot > 1000:
        return cut[:last_dot + 1]
    return cut

# ---------------------------------------------------------------------------
# Web search
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Persona modals
# ---------------------------------------------------------------------------

class PersonaCoreModal(ui.Modal, title="Persona: Core & Background"):
    core_personality = ui.TextInput(
        label="Core Personality & Traits",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1024,
        placeholder="Describe the bot's personality, identity, and core traits.",
    )
    background = ui.TextInput(
        label="Background & History",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1024,
        placeholder="Origin, backstory, relevant history.",
    )

    def __init__(self, data: dict):
        super().__init__()
        self.core_personality.default = data.get("core_personality", "")
        self.background.default = data.get("background", "")

    async def on_submit(self, interaction: discord.Interaction):
        global PERSONA_DATA, CURRENT_PERSONA
        if PERSONA_LOCKED:
            await interaction.response.send_message("Persona is locked. Use `/personaunlock` first.", ephemeral=True)
            return
        PERSONA_DATA["core_personality"] = self.core_personality.value.strip()
        PERSONA_DATA["background"] = self.background.value.strip()
        CURRENT_PERSONA = assemble_persona(PERSONA_DATA)
        try:
            save_persona_json(PERSONA_DATA)
            await interaction.response.send_message(
                "✅ Core & Background saved. Use `/setpersona style` for the remaining fields.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(f"Save failed: {e}", ephemeral=True)


class PersonaStyleModal(ui.Modal, title="Persona: Style & Instructions"):
    beliefs = ui.TextInput(
        label="Beliefs, Likes & Dislikes",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1024,
        placeholder="Values, opinions, preferences, things they love or hate.",
    )
    language = ui.TextInput(
        label="Language & Communication Style",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1024,
        placeholder="Primary language, tone, slang, formality level.",
    )
    system_instructions = ui.TextInput(
        label="System Instructions",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1024,
        placeholder="Advanced rules, constraints, or override behavior.",
    )

    def __init__(self, data: dict):
        super().__init__()
        self.beliefs.default = data.get("beliefs", "")
        self.language.default = data.get("language", "")
        self.system_instructions.default = data.get("system_instructions", "")

    async def on_submit(self, interaction: discord.Interaction):
        global PERSONA_DATA, CURRENT_PERSONA
        if PERSONA_LOCKED:
            await interaction.response.send_message("Persona is locked. Use `/personaunlock` first.", ephemeral=True)
            return
        PERSONA_DATA["beliefs"] = self.beliefs.value.strip()
        PERSONA_DATA["language"] = self.language.value.strip()
        PERSONA_DATA["system_instructions"] = self.system_instructions.value.strip()
        CURRENT_PERSONA = assemble_persona(PERSONA_DATA)
        try:
            save_persona_json(PERSONA_DATA)
            await interaction.response.send_message("✅ Style & Instructions saved.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Save failed: {e}", ephemeral=True)

# ---------------------------------------------------------------------------
# /setpersona group
# ---------------------------------------------------------------------------

class SetPersonaGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="setpersona", description="Edit the bot's persona (Owner only).")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await interaction.client.is_owner(interaction.user):
            await interaction.response.send_message("Owner only.", ephemeral=True)
            return False
        return True

    @app_commands.command(name="core", description="Edit core personality and background.")
    async def set_core(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PersonaCoreModal(PERSONA_DATA))

    @app_commands.command(name="style", description="Edit beliefs, language style, and system instructions.")
    async def set_style(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PersonaStyleModal(PERSONA_DATA))

# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class GenAICog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.setpersona_group = SetPersonaGroup()
        bot.tree.add_command(self.setpersona_group)

    async def cog_unload(self):
        self.bot.tree.remove_command("setpersona")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if message.guild is None:
            return

        prefixes = await self.bot.get_prefix(message)
        if isinstance(prefixes, str):
            prefixes = (prefixes,)
        if message.content.startswith(tuple(prefixes)):
            return

        config = load_config()
        chat_channel_id = config.get("chat_channel_id")
        if not chat_channel_id or message.channel.id != int(chat_channel_id):
            return

        bot_mentioned = self.bot.user in message.mentions if self.bot.user else False
        is_reply_to_bot = (
            message.reference is not None
            and message.reference.resolved is not None
            and isinstance(message.reference.resolved, discord.Message)
            and message.reference.resolved.author == self.bot.user
        )

        if not bot_mentioned and not is_reply_to_bot:
            return

        username = message.author.display_name
        bot_name = self.bot.user.display_name if self.bot.user else BOT_NAME
        prompt = message.clean_content.replace(f"@{bot_name}", "").strip()

        response = await safe_generate(
            prompt,
            channel_id=message.channel.id,
            username=username,
        )
        await send_response(response, message.channel, reply_to=message)

    # ~write — structured output, stateless, single embed (no split)
    @commands.hybrid_command(name='write', help='Ask the AI to write or create something.')
    async def write_cmd(self, ctx, *, query: str):
        if ctx.guild is None:
            await ctx.send("AI commands are not available in DMs.")
            return
        await ctx.defer()
        response = await safe_generate(
            query,
            instruction_prefix="Respond with well-structured, written output. Use formatting where appropriate.",
        )
        embed = discord.Embed(
            title=f"{BOT_NAME} writes...",
            description=response.first_text(),
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    # ~ask — conversational, stateless, split messaging enabled
    @commands.hybrid_command(name='ask', help='Ask the AI a question.')
    async def ask_cmd(self, ctx, *, query: str):
        if ctx.guild is None:
            await ctx.send("AI commands are not available in DMs.")
            return
        await ctx.defer()
        response = await safe_generate(
            query,
            instruction_prefix="Answer conversationally and concisely.",
            username=ctx.author.display_name,
        )
        # First segment as reply, rest as follow-ups
        await send_response(response, ctx.channel, reply_to=ctx.message)

    # ~search
    @commands.hybrid_command(name='search', help='Search the web and summarize with AI.')
    async def search_cmd(self, ctx, *, query: str):
        if ctx.guild is None:
            await ctx.send("AI commands are not available in DMs.")
            return
        await ctx.defer()
        results = await web_search(query)
        response = await safe_generate(
            f"Summarize these search results:\n\n{results}",
            apply_persona=False,
        )
        embed = discord.Embed(
            title=f"Search: {query}",
            description=response.first_text(),
            color=discord.Color.blue()
        )
        url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
        embed.add_field(name="Full results", value=url)
        await ctx.send(embed=embed)

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
        profiles[name.lower()] = PERSONA_DATA.copy()
        save_profiles(profiles)
        await ctx.send(f"Saved persona as `{name.lower()}`.", ephemeral=True if ctx.interaction else False)

    @commands.hybrid_command(name='personaload', help='Load a saved persona profile (Owner only).')
    @commands.is_owner()
    async def persona_load(self, ctx, name: str):
        global PERSONA_DATA, CURRENT_PERSONA
        if PERSONA_LOCKED:
            await ctx.send("Persona is locked.", ephemeral=True if ctx.interaction else False)
            return
        profiles = load_profiles()
        key = name.lower()
        if key not in profiles:
            await ctx.send(f"No profile named `{key}`. Use `/personalist` to see saved profiles.")
            return
        loaded = profiles[key]
        if isinstance(loaded, str):
            CURRENT_PERSONA = loaded
            PERSONA_DATA = default_persona_json()
        else:
            PERSONA_DATA = loaded
            CURRENT_PERSONA = assemble_persona(PERSONA_DATA)
        save_persona_json(PERSONA_DATA)
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

    @commands.hybrid_command(name='personadelete', help='Delete a saved persona profile (Owner only).')
    @commands.is_owner()
    async def persona_delete(self, ctx, name: str):
        profiles = load_profiles()
        key = name.lower()
        if key not in profiles:
            await ctx.send(f"No profile named `{key}`.")
            return
        del profiles[key]
        save_profiles(profiles)
        await ctx.send(f"Deleted profile `{key}`.", ephemeral=True if ctx.interaction else False)

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
        legacy = "Yes — migrate via `/setpersona core` and `/setpersona style`" if LEGACY_DETECTED else "No"
        embed = discord.Embed(title="Persona Debug", color=discord.Color.yellow())
        embed.add_field(name="Locked", value=locked, inline=True)
        embed.add_field(name="Model", value=MODEL_NAME, inline=True)
        embed.add_field(name="Legacy Mode", value=legacy, inline=True)
        embed.add_field(name="Assembled Persona", value=f"```{CURRENT_PERSONA[:900]}```", inline=False)
        embed.add_field(name="Last Prompt (this channel)", value=f"```{last[:900]}```", inline=False)
        await ctx.send(embed=embed, ephemeral=True if ctx.interaction else False)

    # /clearmemory
    @commands.hybrid_command(name='clearmemory', help='Clear conversation memory for this channel (Admin only).')
    @commands.has_permissions(administrator=True)
    async def clear_memory(self, ctx):
        channel_memory.pop(ctx.channel.id, None)
        channel_summary.pop(ctx.channel.id, None)
        await ctx.send("Memory cleared for this channel.")


async def setup(bot):
    await bot.add_cog(GenAICog(bot))