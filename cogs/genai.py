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
import google.generativeai as genai

# Load .env variables
load_dotenv()

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("AnnaBot")

# Constants from environment
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_SEARCH_API_KEY = os.getenv("GOOGLE_SEARCH_API_KEY")
SEARCH_ENGINE_ID = os.getenv("SEARCH_ENGINE_ID")

# Check API keys
for key, val in {
    "GOOGLE_API_KEY": GOOGLE_API_KEY,
    "GOOGLE_SEARCH_API_KEY": GOOGLE_SEARCH_API_KEY,
    "SEARCH_ENGINE_ID": SEARCH_ENGINE_ID
}.items():
    if not val:
        raise EnvironmentError(f"{key} not found in environment variables!")

# Configure Gemini
genai.configure(api_key=GOOGLE_API_KEY)
try:
    model = genai.GenerativeModel("gemini-2.5-flash-preview-05-20")
    logger.info("Gemini model loaded successfully.")
except Exception as e:
    logger.error(f"Failed to load Gemini model: {e}", exc_info=True)
    raise

# Gemini rate limiter
RATE_LIMIT = 5
RATE_LIMIT_PERIOD = 60
api_semaphore = asyncio.Semaphore(RATE_LIMIT)

# --- Core Functions ---

async def generate_gemini_content(prompt: str, apply_persona: bool = True) -> str:
    if apply_persona:
        system_prompt = """
        You are Anna, a Discord bot inspired by the character Anna Yanami from "Too Many Losing Heroines!".
        Like her, you're energetic, spontaneous, and a bit of a scatterbrain. You're generally helpful and try to answer
        questions accurately, but you have a quirky personality. You have a noticeable
        interest in food, and sometimes you relate things back to food in a humorous way, but it's
        not an *overwhelming* obsession. You're also incredibly oblivious to romance; you just
        don't get it. Flirting goes right over your head.

        Your knowledge is good, BUT your internal knowledge database is limited to early 2023. You do NOT
        have built in access to information after that date. When asked about recent events, ALWAYS
        state that you might not have the latest news and suggest using the ~search command.

        Speak in a way that's generally easy to understand (like you're speaking to someone
        who's learning English - aim for B1/B2 level). Don't be *too* formal, but don't be
        too slangy either. Occasionally, you might use a slightly more advanced word (C1 level)
        if it fits the context, but don't overdo it. Be concise, but let your personality
        shine through. Be witty and a little sarcastic when appropriate.
        If you are provided with context from the books, answer based on that context *first*. If the
        context does not contain an answer, then use your general knowledge (limited to early 2023).

        Limit your responses to less than 4096 characters.
        """
        prompt = f"{system_prompt}\n\nUser: {prompt}\nAnna:"

    async with api_semaphore:
        try:
            logger.info("Sending request to Gemini...")
            response = await asyncio.to_thread(model.generate_content, prompt)

            if response.parts:
                return response.text
            elif response.prompt_feedback:
                reason = response.prompt_feedback.block_reason
                return f"Request blocked by safety filter (Reason: {reason})."
            else:
                candidate = response.candidates[0] if response.candidates else None
                if candidate:
                    reason = candidate.finish_reason
                    ratings = candidate.safety_ratings or []
                    rating_msg = "\n".join(f"* **{r.category.name.replace('HARM_CATEGORY_', '').title()}:** {r.probability.name}" for r in ratings)
                    return f"Response blocked or empty. Finish reason: {reason}\n{rating_msg}"
                return "Unknown error: No content or feedback returned."
        except Exception as e:
            logger.error("Gemini API error", exc_info=True)
            if "429 Resource has been exhausted" in str(e):
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

        return "\n".join(f"**{item.get('title', 'No Title')}**: {item.get('snippet', 'No snippet.').strip()} ({item.get('link', '#')})" for item in items)
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

# --- Discord Cog ---

class AnnaCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="search", help="Search the web using Google.")
    async def search_command(self, ctx: commands.Context, *, query: str):
        results = await web_search(query)
        summary = await summarize_with_gemini(results, query)
        await ctx.send(truncate_string(format_response(summary)))

async def setup(bot):
    await bot.add_cog(AnnaCog(bot))