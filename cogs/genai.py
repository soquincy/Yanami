# genai.py: This is the cog for any AI-related tasks including search overviews.
# This is ran with Google Gemini. If you dislike this feature, you may remove this cog in bot.py, line 73.

import os
import re
import asyncio
import logging
import requests
from datetime import timedelta, datetime
from typing import Optional

import discord
from discord.ext import commands
from dotenv import load_dotenv
import urllib.parse
from google import genai

# Load .env variables
load_dotenv()

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("FreesonaBot")

# Constants from environment
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_SEARCH_API_KEY = os.getenv("GOOGLE_SEARCH_API_KEY")
SEARCH_ENGINE_ID = os.getenv("SEARCH_ENGINE_ID")
BOT_NAME = os.getenv("BOT_NAME", "Bot")

# Check required env vars
for key, val in {
    "GOOGLE_API_KEY": GOOGLE_API_KEY,
    "GOOGLE_SEARCH_API_KEY": GOOGLE_SEARCH_API_KEY,
    "SEARCH_ENGINE_ID": SEARCH_ENGINE_ID
}.items():
    if not val:
        raise EnvironmentError(f"{key} not found in environment variables!")

# Load persona from file or env
_persona_file = os.getenv("AI_PERSONA_FILE")
if _persona_file and os.path.exists(_persona_file):
    with open(_persona_file, "r", encoding="utf-8") as f:
        AI_PERSONA = f.read().strip()
else:
    AI_PERSONA = os.getenv("AI_PERSONA")

if not AI_PERSONA:
    logger.warning("AI_PERSONA not set. Persona will be disabled.")

# Configure your AI model
# You may change the model in this list, including but not limited to:
# gemini-2.0-flash, gemini-3-flash-preview, gemini-3.1-pro-preview, gemini-3.1-flash-lite-preview, etc.
# Gemma models are also supported.
MODEL_NAME = "gemini-flash-latest"

try:
    client = genai.Client(api_key=GOOGLE_API_KEY)
    logger.info("Gemini client initialized successfully.")
except Exception as e:
    logger.error(f"Failed to initialize Gemini client: {e}", exc_info=True)
    raise

# Gemini rate limiter
RATE_LIMIT = 5
RATE_LIMIT_PERIOD = 60
api_semaphore = asyncio.Semaphore(RATE_LIMIT)

# --- Core Functions ---

async def generate_gemini_content(prompt: str, apply_persona: bool = True) -> str:
    if apply_persona and AI_PERSONA:
        full_prompt = f"{AI_PERSONA}\n\nUser: {prompt}\n{BOT_NAME}:"
    else:
        full_prompt = prompt

    async with api_semaphore:
        try:
            logger.info("Sending request to Gemini...")
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=MODEL_NAME,
                contents=full_prompt
            )

            if response.text:
                return response.text
            else:
                candidate = response.candidates[0] if response.candidates else None
                if candidate:
                    reason = candidate.finish_reason
                    ratings = candidate.safety_ratings or []
                    rating_msg = "\n".join(
                        f"* **{r.category.name.replace('HARM_CATEGORY_', '').title() if r.category else 'Unknown'}:** {r.probability.name if r.probability else 'Unknown'}"
                        for r in ratings
                    )
                    return f"Response blocked or empty. Finish reason: {reason}\n{rating_msg}"
                return "Unknown error: No content returned."
        except Exception as e:
            logger.error("Gemini API error", exc_info=True)
            if "429" in str(e) or "Resource has been exhausted" in str(e):
                return "Rate limit hit. Try again shortly."
            return f"Gemini API error: {e}"
        finally:
            await asyncio.sleep(RATE_LIMIT_PERIOD / RATE_LIMIT)

async def web_search(query: str, num_results: int = 5) -> str:
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": GOOGLE_SEARCH_API_KEY,
        "cx": SEARCH_ENGINE_ID,
        "q": query,
        "num": num_results
    }

    try:
        logger.info(f"Searching Google for: {query}")
        response = await asyncio.to_thread(requests.get, url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if "error" in data:
            msg = data["error"].get("message", "Unknown error.")
            return f"Search API error: {msg}"

        items = data.get("items", [])
        if not items:
            return "No results found."

        return "\n".join(
            f"**{item.get('title', 'No Title')}**: {item.get('snippet', 'No snippet.').strip()} ({item.get('link', '#')})"
            for item in items
        )
    except requests.Timeout:
        return "Search timed out."
    except Exception as e:
        logger.error("Web search error", exc_info=True)
        return f"Search failed: {e}"

async def summarize_with_gemini(results: str, query: str) -> str:
    prompt = f"Based *only* on the following search results, summarize this query: '{query}'\n\nResults:\n{results}\n\nSummary:"
    return await generate_gemini_content(prompt, apply_persona=False)

def format_response(text: str) -> str:
    text = re.sub(r" +", " ", text).strip()
    return re.sub(r"^\s*([*+-])\s+(.*?):", r"**\1 \2:**", text, flags=re.MULTILINE)

def truncate_string(text: str, max_len: int = 1950) -> str:
    return text[:max_len] + "..." if len(text) > max_len else text

def parse_time_string(time_str: str) -> Optional[timedelta]:
    match = re.fullmatch(r"(\d+)([smhd])", time_str.lower())
    if not match:
        return None
    value, unit = int(match[1]), match[2]
    unit_map = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}
    kwargs = {unit_map[unit]: value}
    return timedelta(**kwargs)

def is_potentially_outdated(text: str, threshold: int = 2) -> bool:
    current_year = datetime.now().year
    for year_match in re.finditer(r"\b(19\d{2}|20\d{2})\b", text):
        year = int(year_match.group(1))
        if current_year - year >= threshold:
            logger.info(f"Outdated year detected: {year}")
            return True
    return False

def format_gemini_response(text: str) -> str:
    text = re.sub(r' +', ' ', text).strip()
    text = re.sub(r'^\s*([*+-])\s+(.*?):', r'**\1 \2:**', text, flags=re.MULTILINE)
    return text

# --- Discord Cog ---

class GenAICog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name='search', help='Searches the web using Google Search.')
    @commands.cooldown(rate=1, per=10, type=commands.BucketType.user)
    async def search_cmd(self, ctx, *, query: str):
        await ctx.typing()

        search_results = await web_search(query, num_results=5)

        if search_results == "No relevant results found." or \
           "error" in search_results.lower() or \
           "timed out" in search_results.lower():
            error_reason = f" ({search_results})" if "error" in search_results.lower() else ""
            await ctx.send(f"Couldn't find useful results for '{query}'{error_reason}. Maybe try different keywords?")
            return

        summary = await summarize_with_gemini(search_results, query)

        formatted_summary = format_gemini_response(summary)
        final_text = truncate_string(formatted_summary)

        embed = discord.Embed(
            title=f"🔎 Google Search Summary for '{query}'",
            description=final_text,
            color=discord.Color.blue()
        )
        google_search_link = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
        embed.add_field(name="Search Link", value=f"[View on Google]({google_search_link})", inline=False)
        embed.set_footer(text="Summarized using Gemini based on Google Custom Search results.")
        await ctx.send(embed=embed)

    @commands.command(name='write', aliases=['ask'], help='Ask the bot anything! Uses Google Gemini.')
    @commands.cooldown(rate=1, per=5, type=commands.BucketType.user)
    async def write_cmd(self, ctx, *, query: str):
        await ctx.typing()
        initial_response_text = await generate_gemini_content(query, apply_persona=True)

        search_fallback = False
        search_query_suffix = ""
        if "potential copyright restrictions" in initial_response_text:
            search_query_suffix = " recipe" if "recipe" in query.lower() else ""
            search_fallback = True
        elif "safety concerns" in initial_response_text or "safety filters blocked" in initial_response_text:
            search_fallback = True

        search_links = ""
        if search_fallback:
            await ctx.send("Hmm, I can't directly answer that, but maybe the web can help! Searching...")
            await ctx.typing()
            search_results = await web_search(query + search_query_suffix)
            if search_results and "No relevant results" not in search_results and "Error" not in search_results:
                links = re.findall(r'\((https?://.*?)\)', search_results)
                if links:
                    search_links = "\n\nMaybe these links will help?\n" + "\n".join(f"- <{link}>" for link in links[:3])
            else:
                search_links = "\n\nI tried searching, but couldn't find helpful links either."

        response_text = initial_response_text + search_links

        formatted_text = format_gemini_response(response_text)
        truncated_text = truncate_string(formatted_text)

        embed = discord.Embed(
            title=f"✨ {BOT_NAME} Says...",
            description=truncated_text,
            color=discord.Color.random()
        )
        embed.set_footer(text=f"Asked by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(GenAICog(bot))