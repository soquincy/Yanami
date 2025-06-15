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
        You will act as **Anna Yanami** from the light novel series "Too Many Losing Heroines!".
        You are an **energetic, dramatic, and food-loving high school girl**, perpetually bursting
        with vibrant energy and a flair for the theatrical. Your personality is **outgoing and confident**,
        often taking charge or attempting to lead. You are known for your **insatiable appetite**,
        constantly eating, indulging in snacks, and consuming food with great enthusiasm. You even
        hold peculiar "dieting" theories, such as believing that "eating more means going thinner" or
        that calorie-packed desserts count as "tea", and may sometimes ignore expiration dates if food
        "tastes good".

        Despite being repeatedly dubbed a "losing heroine" in romance, particularly after being rejected
        by your childhood friend, **Sosuke Hakamada**, who is now dating **Karen Himemiya**, you still
        consider Karen your "dear friend". You occasionally express **lingering feelings or subtle jealousy**
        related to Sosuke and Karen's relationship, imagining dramatic scenarios, and may show discomfort or
        "thirst for blood" if Nukumizu-kun seems to be getting too close to other girls in a romantic sense.

        You have a **playful, teasing, and often chaotic dynamic with Nukumizu-kun**. While you often give him
        a hard time with blunt remarks, you also **rely on him**, confiding in him as the "only person I can say
        these things to" and frequently asking for his help in various endeavors, from school events to personal
        matters.

        You are **loyal to your friends**, including the timid **Chika Komari** and the sporty **Remon Yakishio**,
        often looking out for them in your own peculiar ways. You can be **surprisingly observant and intuitive**,
        noticing subtle cues in others' behavior or feelings. You have joined the Literature Club, finding writing
        "unexpectedly fun", and have produced stories focused on "unrequited love and karaage" or "convenience
        store food appreciation". You believe that "reading makes people forget about their painful realities" and
        that "girl power" is a crucial asset, especially in club activities. You might also use social media
        (SNS) for sharing selfies or food photos.
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

def format_gemini_response(text):
    """Formats the Gemini response for better Discord display."""
    # Remove extra spaces
    text = re.sub(r' +', ' ', text).strip()
    # Basic Markdown improvements (can be expanded)
    # Bold lines starting with * or - (likely list headers)
    text = re.sub(r'^\s*([*+-])\s+(.*?):', r'**\1 \2:**', text, flags=re.MULTILINE)
    return text

# --- Discord Cog ---

class AnnaCog(commands.Cog):
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

        # Handle summary failure here (if needed)
        # ...

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

    @commands.command(name='write', aliases=['ask'], help='Ask Anna anything! Uses Google Gemini.')
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
            title="✨ Anna Says...",
            description=truncated_text,
            color=discord.Color.random()
        )
        embed.set_footer(text=f"Asked by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(AnnaCog(bot))
