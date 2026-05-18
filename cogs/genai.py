# cogs/genai.py: Google AI Studio functions.
# If you don't want to use AI you may remove it on line 49 at main.py (cogs.genai)

import os
import re
import json
import random
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
MODEL_NAME            = "gemini-flash-lite-latest"
MEMORY_LIMIT          = 5
SUMMARY_PROMPT        = "Summarize this conversation in 2-3 sentences, keeping key context only:"

# Split messaging config
SPLIT_MIN_LENGTH     = 280
SPLIT_DELAY_BASE     = 1.2
SPLIT_DELAY_PER_CHAR = 0.012
SPLIT_DELAY_MAX      = 3.5

# Debounce config
DEBOUNCE_SECONDS = 1.2   # wait this long after last message before responding

# Autonomy config
FREQUENCY_CHANCE = {"low": 0.04, "default": 0.10, "high": 0.20}
AUTONOMY_COOLDOWN_SECONDS = 120

if not GOOGLE_API_KEY:
    raise EnvironmentError("GOOGLE_API_KEY missing.")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("FreesonaBot")

client = genai.Client(api_key=GOOGLE_API_KEY)

# ---------------------------------------------------------------------------
# Structured response types
# ---------------------------------------------------------------------------

@dataclass
class MessageSegment:
    text: str
    delay: float = SPLIT_DELAY_BASE
    typing: bool = True
    attachment: Optional[str] = None

@dataclass
class ConversationResponse:
    segments: list[MessageSegment] = field(default_factory=list)
    reactions: list[str] = field(default_factory=list)
    suggested_gif: Optional[str] = None

    @property
    def is_empty(self) -> bool:
        return not self.segments

    def first_text(self) -> str:
        return " ".join(s.text for s in self.segments)

# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------

class GenerationError(Exception):
    pass

class TransientError(GenerationError):
    pass

class RateLimitError(GenerationError):
    pass

class MalformedResponseError(GenerationError):
    pass

class TimeoutGenerationError(GenerationError):
    pass

def _classify_error(e: Exception) -> GenerationError:
    msg = str(e).lower()
    if "429" in msg or "quota" in msg or "rate" in msg:
        return RateLimitError(str(e))
    if "timeout" in msg or "timed out" in msg:
        return TimeoutGenerationError(str(e))
    if "500" in msg or "503" in msg or "internal" in msg:
        return TransientError(str(e))
    return GenerationError(str(e))

_ERROR_MESSAGES: dict[type, str] = {
    RateLimitError:         "Take it easy! I'm getting a lot of requests. Try again in a minute or so.",
    TimeoutGenerationError: "That took long. Try again?",
    TransientError:         "Oops! Something went wrong on my end. Try again.",
    MalformedResponseError: "I didn't understand that. Try again.",
    GenerationError:        "Oops! Something went wrong. Try again.",
}

def _user_facing_error(e: GenerationError) -> str:
    return _ERROR_MESSAGES.get(type(e), _ERROR_MESSAGES[GenerationError])

# ---------------------------------------------------------------------------
# Text splitter
# ---------------------------------------------------------------------------

def split_into_segments(text: str) -> list[str]:
    if len(text) < SPLIT_MIN_LENGTH:
        return [text]

    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    if len(paragraphs) <= 1:
        sentences = re.split(r"(?<=[.!?])\s+", text)
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
# ---------------------------------------------------------------------------

async def send_response(
    response: ConversationResponse,
    channel: discord.abc.Messageable,
    *,
    reply_to: Optional[discord.Message] = None,
) -> None:
    if not response.segments:
        return

    full_text = "\n\n".join(segment.text for segment in response.segments if segment.text.strip())

    if not full_text.strip():
        return

    any_typing = any(segment.typing for segment in response.segments)
    total_delay = min(sum(segment.delay for segment in response.segments if segment.typing), 3.0)

    if any_typing and total_delay > 0:
        async with channel.typing():
            await asyncio.sleep(total_delay)

    if reply_to is not None:
        await reply_to.reply(full_text)
    else:
        await channel.send(full_text)

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
        if contents and contents[-1].role == entry["role"]:
            contents[-1].parts[0].text += f"\n{entry['text']}"
        else:
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
# Core generation
# ---------------------------------------------------------------------------

async def generate(
    prompt: str,
    *,
    channel_id: Optional[int] = None,
    apply_persona: bool = True,
    instruction_prefix: str = "",
    username: str = "",
    image_bytes: Optional[bytes] = None,
    image_mime: Optional[str] = None,
) -> ConversationResponse:
    await rate_limit()
    prompt = sanitize_prompt(prompt)

    contents = memory_to_contents(channel_id) if channel_id is not None else []

    user_text = f"{instruction_prefix}\n\n{prompt}".strip() if instruction_prefix else prompt
    display_text = f"{username}: {prompt}" if username else prompt

    parts = []

    if user_text:
        parts.append(types.Part(text=user_text))

    if image_bytes:
        parts.append(
            types.Part.from_bytes(
                data=image_bytes,
                mime_type=image_mime or "image/png"
            )
        )

    if not parts:
        parts.append(types.Part(text="Describe this image"))

    contents.append(
        types.Content(
            role="user",
            parts=parts
        )
    )

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
        raise
    except Exception as e:
        classified = _classify_error(e)
        logger.error(f"Gemini error [{type(classified).__name__}]: {e}")
        raise classified from e

async def safe_generate(
    prompt: str,
    **kwargs,
) -> ConversationResponse:
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
# Attachment processing helper
# ---------------------------------------------------------------------------

async def _extract_image(message: Optional[discord.Message]) -> tuple[Optional[bytes], Optional[str]]:
    if not message or not message.attachments:
        return None, None
    att = message.attachments[0]
    if att.content_type and "image" in att.content_type:
        try:
            image_bytes = await att.read()
            return image_bytes, att.content_type
        except Exception as e:
            logger.error(f"Failed to read message attachment: {e}")
    return None, None

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
        bot = interaction.client
        if isinstance(bot, commands.Bot):
            if not await bot.is_owner(interaction.user):
                await interaction.response.send_message("Owner only.", ephemeral=True)
                return False
            return True
        await interaction.response.send_message("Owner check failed.", ephemeral=True)
        return False

    @app_commands.command(name="core", description="Edit core personality and background.")
    async def set_core(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PersonaCoreModal(PERSONA_DATA))

    @app_commands.command(name="style", description="Edit beliefs, language style, and system instructions.")
    async def set_style(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PersonaStyleModal(PERSONA_DATA))

# ---------------------------------------------------------------------------
# Embed footer helper
# ---------------------------------------------------------------------------

def _embed_footer(author_display: str, query: str, max_query_len: int = 80) -> str:
    """Returns a footer string: 'Asked by <name> • <truncated query>'"""
    truncated = query if len(query) <= max_query_len else query[:max_query_len - 1] + "…"
    return f"Asked by {author_display}  •  {truncated}"

# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

# Module-level state for debounce and autonomy
_pending_responses: dict[int, asyncio.Task] = {}   # user_id -> pending task
_autonomy_cooldown: dict[int, float] = {}           # channel_id -> last fire timestamp

class GenAICog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.setpersona_group = SetPersonaGroup()
        bot.tree.add_command(self.setpersona_group)

    async def cog_unload(self):
        self.bot.tree.remove_command("setpersona")
        # Cancel any pending debounce tasks on unload
        for task in _pending_responses.values():
            task.cancel()
        _pending_responses.clear()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        KONATA_ID = 1482682376655208548

        if message.author.bot and message.author.id != KONATA_ID:
            return

        if message.guild is None:
            return

        if message.type not in (discord.MessageType.default, discord.MessageType.reply):
            return

        if getattr(message, "interaction_metadata", None):
            return

        prefix = await self.bot.get_prefix(message)
        prefixes = [prefix] if isinstance(prefix, str) else prefix
        if any(message.content.startswith(p) for p in prefixes):
            return

        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return

        # ---------------------------------------------------------------
        # Autonomy mode check
        # Fires independently of the normal response path — the bot can
        # chime in even if the message wasn't directed at it.
        # ---------------------------------------------------------------
        config = load_config()
        autonomy_on = config.get("autonomy", False)

        if autonomy_on and not message.author.bot and message.content.strip():
            frequency = config.get("autonomy_frequency", "default")
            chance = FREQUENCY_CHANCE.get(frequency, 0.10)
            now = time.time()
            last_fire = _autonomy_cooldown.get(message.channel.id, 0)

            if now - last_fire > AUTONOMY_COOLDOWN_SECONDS and random.random() < chance:
                _autonomy_cooldown[message.channel.id] = now
                logger.info(f"Autonomy firing in channel {message.channel.id}")
                image_bytes, image_mime = await _extract_image(message)
                response = await safe_generate(
                    message.content,
                    channel_id=message.channel.id,
                    username=message.author.display_name,
                    image_bytes=image_bytes,
                    image_mime=image_mime,
                )
                await send_response(response, message.channel)
                return  # don't double-respond in the same pass

        # ---------------------------------------------------------------
        # Debounce: cancel any existing pending response for this user,
        # then wait DEBOUNCE_SECONDS before actually generating.
        # This prevents double-replies when a user sends rapid messages.
        # ---------------------------------------------------------------
        user_id = message.author.id

        if user_id in _pending_responses:
            _pending_responses[user_id].cancel()
            logger.debug(f"Debounce: cancelled pending task for user {user_id}")

        # Snapshot what we need before the async gap
        content_snapshot   = message.content
        channel_snapshot   = message.channel
        username_snapshot  = message.author.display_name
        message_snapshot   = message

        async def debounced_respond():
            try:
                await asyncio.sleep(DEBOUNCE_SECONDS)
                image_bytes, image_mime = await _extract_image(message_snapshot)
                response = await safe_generate(
                    content_snapshot or "What's in this image?",
                    channel_id=channel_snapshot.id,
                    username=username_snapshot,
                    image_bytes=image_bytes,
                    image_mime=image_mime,
                )
                await send_response(response, channel_snapshot, reply_to=message_snapshot)
            except asyncio.CancelledError:
                logger.debug(f"Debounce: task cancelled for user {user_id}")
            finally:
                _pending_responses.pop(user_id, None)

        _pending_responses[user_id] = asyncio.create_task(debounced_respond())

    # -----------------------------------------------------------------------
    # ~write
    # -----------------------------------------------------------------------
    @commands.hybrid_command(name='write', help='Ask the AI to write or create something.')
    async def write_cmd(self, ctx, *, query: str):
        if ctx.guild is None:
            await ctx.send("AI commands are not available in DMs.")
            return
        await ctx.defer()
        image_bytes, image_mime = await _extract_image(ctx.message)
        response = await safe_generate(
            query,
            instruction_prefix=(
                "Return plain text only. "
                "Use double newlines between paragraphs. "
                "Do NOT use markdown, symbols, or headings. "
                "Each idea must be separated clearly."
            ),
            apply_persona=True,
            image_bytes=image_bytes,
            image_mime=image_mime,
        )
        embed = discord.Embed(
            title=f"{BOT_NAME} says...",
            description=response.first_text(),
            color=discord.Color.green()
        )
        embed.set_footer(text=_embed_footer(ctx.author.display_name, query))
        await ctx.send(embed=embed)

    # -----------------------------------------------------------------------
    # ~ask
    # -----------------------------------------------------------------------
    @commands.hybrid_command(name='ask', help='Ask the AI a question.')
    async def ask_cmd(self, ctx, *, query: str):
        if ctx.guild is None:
            await ctx.send("AI commands are not available in DMs.")
            return
        image_bytes, image_mime = await _extract_image(ctx.message)
        response = await safe_generate(
            query,
            instruction_prefix=(
                "Write in clean paragraphs. "
                "Use newline breaks between sections. "
                "Do NOT use markdown headings like ###."
            ),
            username=ctx.author.display_name,
            image_bytes=image_bytes,
            image_mime=image_mime,
        )
        embed = discord.Embed(
            title=f"{BOT_NAME} answers...",
            description=response.first_text(),
            color=discord.Color.blue()
        )
        embed.set_footer(text=_embed_footer(ctx.author.display_name, query))
        await ctx.send(embed=embed)

    # -----------------------------------------------------------------------
    # ~search
    # -----------------------------------------------------------------------
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
            instruction_prefix=(
                "Write in clean sections with paragraph breaks. "
                "Do not use markdown headings like ###. "
                "Keep structure readable in Discord embeds."
            )
        )
        text = response.first_text().replace("### ", "\n\n")
        embed = discord.Embed(
            title=f"Search: {query}",
            description=text[:4096],
            color=discord.Color.blue()
        )
        url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
        embed.add_field(name="Full results", value=url, inline=False)
        embed.set_footer(text=_embed_footer(ctx.author.display_name, query))
        await ctx.send(embed=embed)

    # -----------------------------------------------------------------------
    # Persona lock / unlock
    # -----------------------------------------------------------------------
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

    # -----------------------------------------------------------------------
    # Persona profiles
    # -----------------------------------------------------------------------
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
        await ctx.send(names, ephemeral=True if ctx.interaction else False)

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

    # -----------------------------------------------------------------------
    # /setchannel + /clearchannel
    # -----------------------------------------------------------------------
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

    # -----------------------------------------------------------------------
    # /debugpersona
    # -----------------------------------------------------------------------
    @commands.hybrid_command(name='debugpersona', help='Show active persona and last prompt (Owner only).')
    @commands.is_owner()
    async def debug_persona(self, ctx):
        last = LAST_DEBUG.get(ctx.channel.id, "*(no prompt sent in this channel yet)*")
        locked = "Yes" if PERSONA_LOCKED else "No"
        legacy = "Yes — migrate via `/setpersona core` and `/setpersona style`" if LEGACY_DETECTED else "No"
        config = load_config()
        autonomy_status = "On" if config.get("autonomy", False) else "Off"
        autonomy_freq = config.get("autonomy_frequency", "default")
        embed = discord.Embed(title="Persona Debug", color=discord.Color.yellow())
        embed.add_field(name="Locked", value=locked, inline=True)
        embed.add_field(name="Model", value=MODEL_NAME, inline=True)
        embed.add_field(name="Legacy Mode", value=legacy, inline=True)
        embed.add_field(name="Autonomy", value=f"{autonomy_status} ({autonomy_freq})", inline=True)
        embed.add_field(name="Assembled Persona", value=f"```{CURRENT_PERSONA[:900]}```", inline=False)
        embed.add_field(name="Last Prompt (this channel)", value=f"```{last[:900]}```", inline=False)
        await ctx.send(embed=embed, ephemeral=True if ctx.interaction else False)

    # -----------------------------------------------------------------------
    # /clearmemory
    # -----------------------------------------------------------------------
    @commands.hybrid_command(name='clearmemory', help='Clear conversation memory for this channel (Admin only).')
    @commands.has_permissions(administrator=True)
    async def clear_memory(self, ctx):
        channel_memory.pop(ctx.channel.id, None)
        channel_summary.pop(ctx.channel.id, None)
        await ctx.send("Memory cleared for this channel.")

    # -----------------------------------------------------------------------
    # /autonomy
    # -----------------------------------------------------------------------
    @app_commands.command(name="autonomy", description="Control autonomous mode (Admin only).")
    @app_commands.describe(
        action="on / off / frequency",
        frequency="low / default / high — only used when action is 'frequency'"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def autonomy_cmd(
        self,
        interaction: discord.Interaction,
        action: str,
        frequency: Optional[str] = None,
    ):
        config = load_config()
        action = action.lower().strip()

        if action == "on":
            config["autonomy"] = True
            save_config(config)
            await interaction.response.send_message("Autonomy mode enabled.", ephemeral=True)

        elif action == "off":
            config["autonomy"] = False
            save_config(config)
            await interaction.response.send_message("Autonomy mode disabled.", ephemeral=True)

        elif action == "frequency":
            if frequency not in ("low", "default", "high"):
                await interaction.response.send_message(
                    "Frequency must be `low`, `default`, or `high`.", ephemeral=True
                )
                return
            config["autonomy_frequency"] = frequency
            save_config(config)
            await interaction.response.send_message(
                f"Autonomy frequency set to `{frequency}`.", ephemeral=True
            )

        else:
            await interaction.response.send_message(
                "Unknown action. Use `on`, `off`, or `frequency`.", ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(GenAICog(bot))