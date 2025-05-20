import discord
from discord.ext import commands
import re
import os
import asyncio
from dotenv import load_dotenv
from datetime import timedelta, datetime
import logging
import requests
import google.generativeai as genai
import urllib.parse # Added for web_search encoding

# Intents
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
Google_Search_API_KEY = os.getenv("GOOGLE_SEARCH_API_KEY") # Use standard naming convention
SEARCH_ENGINE_ID = os.getenv("SEARCH_ENGINE_ID")

if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY not found in environment variables!")
if not Google_Search_API_KEY:
    raise ValueError("GOOGLE_SEARCH_API_KEY not found in environment variables!")
if not SEARCH_ENGINE_ID:
    raise ValueError("SEARCH_ENGINE_ID not found in environment variables!")

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')
logger = logging.getLogger(__name__) # Use a logger instance

# Configure Gemini API
genai.configure(api_key=GOOGLE_API_KEY)
# ALWAYS check if this is correct
try:
    # Gemini GenAI 2.0
    model = genai.GenerativeModel('gemini-2.0-flash')
    logger.info("Gemini Model loaded: gemini-2.0-flash")
except Exception as e:
    logger.error(f"Failed to load Gemini model: {e}")
    raise # Stop the bot if the model can't load

# --- Rate Limiting (Adjust values based on Gemini API quotas) ---
RATE_LIMIT = 5  # Max requests
RATE_LIMIT_PERIOD = 60  # Seconds
api_semaphore = asyncio.Semaphore(RATE_LIMIT)

# --- Gemini Interaction ---

async def generate_gemini_content(prompt, apply_persona=True):
    """
    Generates content using the Gemini API with rate limiting, persona application,
    and error handling. Runs the blocking API call in a separate thread.
    """
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
"""
        full_prompt = f"{system_prompt}\n\nUser: {prompt}\nAnna:"
    else:
        # Use a simpler prompt for tasks like summarization if persona isn't needed
        full_prompt = prompt

    async with api_semaphore:  # Acquire semaphore
        try:
            logger.info("Requesting content from Gemini...")
            # Run the blocking API call in a separate thread
            response = await asyncio.to_thread(model.generate_content, full_prompt)
            logger.info("Received response from Gemini.")
            # Accessing response.text directly might raise if there's an error/block
            # The Gemini library usually includes safety ratings/finish reason in the response object itself.
            # Check for content existence before accessing .text
            if response.parts:
                 return response.text
            elif response.prompt_feedback:
                 # Handle cases where the prompt itself was blocked
                 block_reason = response.prompt_feedback.block_reason
                 logger.warning(f"Gemini prompt blocked. Reason: {block_reason}")
                 # You might want to check safety ratings here too if available
                 return f"My safety filters blocked the request (Reason: {block_reason}). Try rephrasing."
            else:
                 # Handle other potential non-text responses or empty results
                 logger.warning("Gemini returned no content or unexpected response structure.")
                 # Attempt to get safety ratings if available in the candidate
                 finish_reason = response.candidates[0].finish_reason if response.candidates else 'UNKNOWN'
                 safety_ratings_str = ""
                 if response.candidates and response.candidates[0].safety_ratings:
                     ratings = {r.category: r.probability for r in response.candidates[0].safety_ratings}
                     safety_ratings_str = "\nSafety Ratings:\n" + "\n".join(f"* **{k.name.replace('HARM_CATEGORY_', '').replace('_', ' ').title()}:** {v.name}" for k, v in ratings.items())

                 if finish_reason == 3: # FINISH_REASON_SAFETY
                    return f"The model refused to answer due to safety concerns.{safety_ratings_str}"
                 elif finish_reason == 4: # FINISH_REASON_RECITATION (Copyright)
                    return "The model could not answer due to potential copyright restrictions. Try rephrasing."
                 else:
                    return f"The model returned an empty response. (Finish Reason: {finish_reason})"


        except Exception as e:
            logger.error(f"Error during Gemini API call: {e}", exc_info=True)
            error_message = str(e)
            # Handle specific known errors based on string matching (less ideal but kept from original)
            if "429 Resource has been exhausted" in error_message:
                return "I'm experiencing high traffic (API rate limit hit). Please try again in a minute."
            # Add more specific exception handling if the library provides them
            # For example: except genai.types.BlockedPromptException as bpe: ...
            else:
                return f"An error occurred with the Gemini API: {error_message}"
        finally:
            # Release semaphore happens automatically with 'async with'
            # Add a small delay to help manage the rate limit timing
            await asyncio.sleep(RATE_LIMIT_PERIOD / RATE_LIMIT)

# --- Helper Functions ---

# Replace the old web_search function entirely with this one
async def web_search(query: str, num_results: int = 5) -> str:
    """
    Performs a web search using the Google Custom Search JSON API.
    Runs the blocking API call in a separate thread.
    """
    logger.info(f"Performing Google Custom Search for: {query}")
    api_key = Google_Search_API_KEY
    cse_id = SEARCH_ENGINE_ID
    search_url = "https://www.googleapis.com/customsearch/v1"
    params = {
        'key': api_key,
        'cx': cse_id,
        'q': query,
        'num': num_results # Request specific number of results
    }

    try:
        # Run the blocking network call in a separate thread
        response = await asyncio.to_thread(
            requests.get, search_url, params=params, timeout=10
        )
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        search_data = response.json()

        # Check for API-level errors within the JSON response
        if 'error' in search_data:
            error_details = search_data['error'].get('message', 'Unknown Google API error')
            logger.error(f"Google Custom Search API error: {error_details}")
            return f"Search API error: {error_details}"

        # Check if 'items' exists and has results
        if 'items' not in search_data or not search_data['items']:
            logger.info(f"No Google Custom Search results found for query: {query}")
            return "No relevant results found."

        # Format the results consistently with the previous function's output
        search_summary = []
        for item in search_data['items']:
            title = item.get('title', 'No Title')
            link = item.get('link', '#')
            snippet = item.get('snippet', 'No snippet available.').replace('\n', ' ') # Clean snippet
            search_summary.append(f"**{title}**: {snippet} ({link})")

        logger.info(f"Found {len(search_summary)} Google Custom Search results.")
        return "\n".join(search_summary)

    except requests.Timeout:
        logger.warning(f"Google Custom Search timed out for query: {query}")
        return "Search timed out."
    except requests.RequestException as e:
        logger.error(f"Error during Google Custom Search request: {e}", exc_info=True)
        return f"Error communicating with the search service: {e}"
    except Exception as e: # Catch potential JSON parsing errors or other unexpected issues
        logger.error(f"Unexpected error during web search processing: {e}", exc_info=True)
        return f"An unexpected error occurred during search: {e}"

# --- (Summarize function and others remain the same) ---
async def summarize_with_gemini(search_results, original_query):
    """Summarizes search results using Gemini (without persona)."""
    prompt = f"Based *only* on the following search results, provide a concise summary answering the query: '{original_query}'\n\nSearch Results:\n{search_results}\n\nSummary:"
    logger.info("Requesting summarization from Gemini.")
    # Use the main generator function, but disable the persona for straightforward summarization
    summary = await generate_gemini_content(prompt, apply_persona=False)
    return summary


def format_gemini_response(text):
    """Formats the Gemini response for better Discord display."""
    # Remove extra spaces
    text = re.sub(r' +', ' ', text).strip()
    # Basic Markdown improvements (can be expanded)
    # Bold lines starting with * or - (likely list headers)
    text = re.sub(r'^\s*([*+-])\s+(.*?):', r'**\1 \2:**', text, flags=re.MULTILINE)
    return text

def truncate_string(text, max_length=1950): # Increased slightly for embeds
    """Truncates a string, adding ellipsis if needed."""
    if len(text) > max_length:
        return text[:max_length] + "..."
    return text

def parse_time_string(time_str: str) -> timedelta | None:
    """Parses a time string like '10s', '5m', '1h', '2d' into a timedelta."""
    match = re.match(r"(\d+)([smhd])$", time_str.lower())
    if not match:
        return None

    value, unit = int(match.group(1)), match.group(2)
    if unit == "s":
        return timedelta(seconds=value)
    elif unit == "m":
        return timedelta(minutes=value)
    elif unit == "h":
        return timedelta(hours=value)
    elif unit == "d":
        return timedelta(days=value)
    return None # Should not happen with the regex, but good practice

def is_potentially_outdated(text, years_threshold=2):
    """Checks if text contains dates potentially older than threshold."""
    current_year = datetime.now().year
    # Look for 4-digit years (19xx or 20xx)
    for match in re.finditer(r'\b(19\d{2}|20\d{2})\b', text):
        year = int(match.group(1))
        # Check if the found year is significantly older than the current year
        if current_year - year >= years_threshold:
            logger.info(f"Detected potentially outdated year {year} in text.")
            return True
    return False

class AnnaCog(commands.Cog):
    def __init__(self, bot):
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

    @commands.command(name='write', aliases=['ask'], help='Ask Anna anything! Uses Gemini AI.')
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