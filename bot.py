import discord
from discord.ext import commands
# import json # Not used, removed
import re
import os
import asyncio
from dotenv import load_dotenv
from datetime import timedelta, datetime
import logging
import requests
import google.generativeai as genai
import urllib.parse # Added for web_search encoding

# --- Configuration & Setup ---

# Load environment variables
# REMEMBER TO CHANGE THIS PATH TO YOUR ACTUAL .env FILE LOCATION
load_dotenv(r"/home/soquincy/Yanami/bot_token.env")
bot_token = os.getenv("BOT_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
channel_id_str = os.getenv("CHANNEL_ID")
Google_Search_API_KEY = os.getenv("Google_Search_API_KEY") # Use standard naming convention
SEARCH_ENGINE_ID = os.getenv("SEARCH_ENGINE_ID")

if not bot_token:
    raise ValueError("BOT_TOKEN not found in environment variables!")
if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY not found in environment variables!")
if not channel_id_str:
    raise ValueError("CHANNEL_ID not found in environment variables!")
if not Google_Search_API_KEY:
    raise ValueError("Google_Search_API_KEY not found in environment variables!")
if not SEARCH_ENGINE_ID:
    raise ValueError("SEARCH_ENGINE_ID not found in environment variables!")

try:
    CHANNEL_ID = int(channel_id_str)
except ValueError:
    raise ValueError("CHANNEL_ID in environment variables is not a valid integer!")

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')
logger = logging.getLogger(__name__) # Use a logger instance

# Define intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="~", intents=intents)

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

# --- Bot Events ---
@bot.event
async def on_ready():
    logger.info(f'Logged in as {bot.user.name} ({bot.user.id})')
    logger.info(f'Discord.py version: {discord.__version__}')
    logger.info(f'Rate limit set to {RATE_LIMIT} requests per {RATE_LIMIT_PERIOD} seconds.')

    # Send startup message to specified channel
    channel_id = CHANNEL_ID # Already checked if valid int during startup
    channel = bot.get_channel(channel_id)
    if channel:
        try:
            await channel.send("Heya! Anna reporting for duty! Ask me anything, but remember my knowledge is mostly from early 2023. For super fresh info, use `~search <your query>`!")
            logger.info(f"Sent startup message to channel {channel_id}")
        except discord.Forbidden:
            logger.warning(f"Missing permissions to send message in channel {channel_id}")
        except Exception as e:
            logger.error(f"Failed to send startup message: {e}")
    else:
        logger.warning(f"Could not find channel with ID {channel_id}. Bot may lack access or ID is incorrect.")

@bot.event
async def on_command_error(ctx: commands.Context, error):
    """Handles errors globally for commands."""
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("Huh? I don't know that command. Try `~help`.")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("Oops! You don't have the right permissions to do that.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"You forgot something! Missing argument: `{error.param.name}`. Try `~help {ctx.command.name}`.")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send(f"I couldn't find the member '{error.argument}'. Are they in this server?")
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"That doesn't look right. Invalid argument provided. Check `~help {ctx.command.name}`.")
    elif isinstance(error, commands.CommandOnCooldown):
         await ctx.send(f"Hold your horses! Try again in {error.retry_after:.2f} seconds.")
    elif isinstance(error, commands.NotOwner):
         await ctx.send("Only my owner can use that command!")
    elif isinstance(error, commands.CheckFailure): # General check failure (like permissions)
         await ctx.send("You can't run this command here or lack permissions.")
    else:
        # Log the full error traceback for debugging
        logger.error(f"Unhandled command error in '{ctx.command.name if ctx.command else 'Unknown Command'}': {error}", exc_info=True)
        await ctx.send("Something went wrong! I've logged the error.")

# --- Commands ---

@bot.command(name='hello', help='Says hello back!')
async def hello_cmd(ctx):
    await ctx.send(f"Hello {ctx.author.mention}!")

# Remove default help before adding custom one
bot.remove_command('help')

@bot.command(name='help', help='Shows help information for commands.')
async def help_cmd(ctx, *, command_name: str = None):
    """Shows help for all commands or a specific command."""
    prefix = bot.command_prefix

    if not command_name:
        # General help
        embed = discord.Embed(
            title="Anna's Command List!",
            description=f"Use `{prefix}help <command_name>` for more details on a specific command.",
            color=discord.Color.random() # A bit more Anna-like
        )
        embed.set_thumbnail(url=bot.user.display_avatar.url) # Add bot avatar

        # Group commands (you can customize categories)
        fun_cmds = []
        mod_cmds = []
        util_cmds = []

        for cmd in bot.commands:
            if cmd.hidden: continue # Skip hidden commands
            if cmd.cog_name: continue # Skip cog commands if not using cogs explicitly

            # Basic categorization example
            if cmd.name in ['add', 'hello', 'write', 'ask', 'today']:
                 fun_cmds.append(f"`{prefix}{cmd.name}` - {cmd.help or 'No description'}")
            elif cmd.name in ['kick', 'purge', 'removetimeout', 'rt', 'timeout', 'ban']:
                 mod_cmds.append(f"`{prefix}{cmd.name}` - {cmd.help or 'No description'}")
            elif cmd.name in ['search', 'help']:
                 util_cmds.append(f"`{prefix}{cmd.name}` - {cmd.help or 'No description'}")
            # Add more categories as needed

        if fun_cmds: embed.add_field(name="🎉 Fun & Info", value="\n".join(fun_cmds), inline=False)
        if mod_cmds: embed.add_field(name="🛡️ Moderation", value="\n".join(mod_cmds), inline=False)
        if util_cmds: embed.add_field(name="🔧 Utility", value="\n".join(util_cmds), inline=False)

        embed.set_footer(text="Remember, my knowledge is mostly from early 2023!")
        await ctx.send(embed=embed)

    else:
        # Specific command help
        command = bot.get_command(command_name.lower())
        if command and not command.hidden:
            # Construct usage string
            usage = f"`{prefix}{command.qualified_name}"
            params = []
            for name, param in command.params.items():
                 # Skip self/ctx
                 if name in ('self', 'ctx'): continue
                 # Format based on requirement and type
                 if param.kind == param.VAR_POSITIONAL:
                     params.append(f"<{name}...>") # e.g., <query...>
                 elif param.default is param.empty:
                     params.append(f"<{name}>")    # e.g., <member>
                 else:
                     params.append(f"[{name}]")    # e.g., [reason]
            usage += " " + " ".join(params) + "`"


            embed = discord.Embed(
                title=f"Help for `~{command.name}`",
                description=command.help or "No description provided.",
                color=discord.Color.green()
            )
            embed.add_field(name="Usage", value=usage, inline=False)
            if command.aliases:
                aliases = ", ".join([f"`{prefix}{a}`" for a in command.aliases])
                embed.add_field(name="Aliases", value=aliases, inline=False)

            # Add cooldown info if applicable
            if command.cooldown:
                cd = command.cooldown
                embed.add_field(name="Cooldown", value=f"{cd.rate} time(s) per {cd.per:.0f} seconds", inline=False)

            # Add required permissions if applicable
            perms = getattr(command.callback, '__commands_checks__', [])
            perm_names = []
            for check in perms:
                # This is a basic way, might need refinement for complex checks
                if 'has_permissions' in str(check):
                    # Extract perms from has_permissions check if possible (can be tricky)
                     try:
                         required_perms = [p for p, v in check.__closure__[0].cell_contents.items() if v]
                         perm_names.extend(p.replace('_', ' ').title() for p in required_perms)
                     except (AttributeError, IndexError, TypeError):
                         pass # Ignore if extraction fails
                elif 'is_owner' in str(check):
                    perm_names.append("Bot Owner")
            if perm_names:
                 embed.add_field(name="Permissions", value=", ".join(perm_names), inline=False)


            await ctx.send(embed=embed)
        else:
            await ctx.send(f"Sorry, I couldn't find a command named `{command_name}`. Try `~help` for a list.")

@bot.command(name='add', help='Adds two whole numbers.')
async def add_cmd(ctx, num1: int, num2: int):
    """Adds two integers provided by the user."""
    result = num1 + num2
    await ctx.send(f"Okay, {num1} + {num2} = {result}. Easy peasy!")

@bot.command(name='purge', help='Deletes a specified number of messages (1-100).')
@commands.has_permissions(manage_messages=True)
@commands.bot_has_permissions(manage_messages=True) # Check bot perms too
async def purge_cmd(ctx, amount: int):
    """Deletes messages. Requires Manage Messages permission."""
    if 1 <= amount <= 100:
        try:
            deleted = await ctx.channel.purge(limit=amount + 1) # +1 to delete the command message too
            await ctx.send(f"Poof! Deleted {len(deleted) - 1} message(s).", delete_after=5) # Notify briefly
        except discord.Forbidden:
             await ctx.send("I need the 'Manage Messages' permission to do that!")
        except discord.HTTPException as e:
             logger.error(f"Failed to purge messages: {e}")
             await ctx.send("Something went wrong while deleting messages.")
    else:
        await ctx.send("Please provide a number between 1 and 100.")

@bot.command(name='ban', help='Bans a member from the server.')
@commands.has_permissions(ban_members=True)
@commands.bot_has_permissions(ban_members=True)
async def ban_cmd(ctx, member: discord.Member, *, reason: str = "No reason provided"):
    """Bans a member. Requires Ban Members permission."""
    if member == ctx.author:
        await ctx.send("You can't ban yourself, silly!")
        return
    if member == bot.user:
        await ctx.send("I'm not banning myself!")
        return
    # Optional: Check role hierarchy
    if ctx.author.top_role <= member.top_role and ctx.guild.owner != ctx.author:
         await ctx.send("You can't ban someone with a role higher than or equal to yours.")
         return

    try:
        await member.ban(reason=f"Banned by {ctx.author.name}: {reason}")
        await ctx.send(f"Okay, {member.mention} has been banned. Reason: {reason}")
        logger.info(f"{ctx.author.name} banned {member.name}. Reason: {reason}")
    except discord.Forbidden:
        await ctx.send("I don't have the required permissions to ban this member. Maybe check my role hierarchy?")
    except discord.HTTPException as e:
        logger.error(f"Failed to ban {member.name}: {e}")
        await ctx.send(f"Something went wrong trying to ban {member.mention}.")

@bot.command(name='kick', help='Kicks a member from the server.')
@commands.has_permissions(kick_members=True)
@commands.bot_has_permissions(kick_members=True)
async def kick_cmd(ctx, member: discord.Member, *, reason: str = "No reason provided"):
    """Kicks a member. Requires Kick Members permission."""
    if member == ctx.author:
        await ctx.send("You can't kick yourself!")
        return
    if member == bot.user:
        await ctx.send("Can't kick me!")
        return
    if ctx.author.top_role <= member.top_role and ctx.guild.owner != ctx.author:
         await ctx.send("You can't kick someone with a role higher than or equal to yours.")
         return

    try:
        await member.kick(reason=f"Kicked by {ctx.author.name}: {reason}")
        await ctx.send(f"{member.mention} has been kicked. Reason: {reason}")
        logger.info(f"{ctx.author.name} kicked {member.name}. Reason: {reason}")
    except discord.Forbidden:
        await ctx.send("I don't have the permissions to kick this member. Check my roles?")
    except discord.HTTPException as e:
        logger.error(f"Failed to kick {member.name}: {e}")
        await ctx.send(f"Something went wrong trying to kick {member.mention}.")

@bot.command(name='timeout', help='Times out a member (e.g., 10s, 5m, 1h, 1d, max 28d).')
@commands.has_permissions(moderate_members=True)
@commands.bot_has_permissions(moderate_members=True)
async def timeout_cmd(ctx, member: discord.Member, time_str: str, *, reason: str = "No reason provided"):
    """Times out a member. Requires Moderate Members permission."""
    if member == ctx.author:
        await ctx.send("Can't timeout yourself!")
        return
    if member == bot.user:
        await ctx.send("Nice try, but no timing out the bot!")
        return
    if ctx.author.top_role <= member.top_role and ctx.guild.owner != ctx.author:
         await ctx.send("You can't timeout someone with a role higher than or equal to yours.")
         return

    delta = parse_time_string(time_str)

    if delta is None:
        await ctx.send("Invalid time format. Use numbers followed by s, m, h, or d (e.g., `10m`, `1h`, `3d`).")
        return

    max_timeout = timedelta(days=28)
    if delta > max_timeout:
        await ctx.send("Timeout duration cannot exceed 28 days.")
        return
    if delta <= timedelta(seconds=0):
         await ctx.send("Timeout duration must be positive.")
         return

    try:
        await member.timeout(delta, reason=f"Timed out by {ctx.author.name}: {reason}")
        # Format timedelta for user-friendly output (optional but nice)
        await ctx.send(f"{member.mention} has been timed out for {time_str}. Reason: {reason}")
        logger.info(f"{ctx.author.name} timed out {member.name} for {time_str}. Reason: {reason}")
    except discord.Forbidden:
        await ctx.send("I don't have the permissions to timeout this member. Check my 'Moderate Members' permission and role hierarchy.")
    except discord.HTTPException as e:
        logger.error(f"Failed to timeout {member.name}: {e}")
        await ctx.send(f"Something went wrong trying to timeout {member.mention}.")

@bot.command(name='removetimeout', aliases=['rt', 'untimeout'], help='Removes a timeout from a member.')
@commands.has_permissions(moderate_members=True)
@commands.bot_has_permissions(moderate_members=True)
async def removetimeout_cmd(ctx, member: discord.Member):
    """Removes timeout. Requires Moderate Members permission."""
    if not member.is_timed_out():
         await ctx.send(f"{member.mention} isn't currently timed out.")
         return

    try:
        await member.timeout(None, reason=f"Timeout removed by {ctx.author.name}") # Pass None to remove
        await ctx.send(f"Okay, {member.mention}'s timeout has been removed.")
        logger.info(f"{ctx.author.name} removed timeout from {member.name}.")
    except discord.Forbidden:
        await ctx.send("I don't have the permissions to remove timeouts. Check my 'Moderate Members' permission.")
    except discord.HTTPException as e:
        logger.error(f"Failed to remove timeout from {member.name}: {e}")
        await ctx.send(f"Something went wrong trying to remove the timeout from {member.mention}.")

@bot.command(name='search', help='Searches the web using Google Search.')
# Add a cooldown to prevent spamming external APIs
@commands.cooldown(rate=1, per=10, type=commands.BucketType.user)
async def search_cmd(ctx, *, query: str):
    """Searches the web using Google and provides a summary of results."""
    await ctx.typing() # Show typing indicator

    # Make sure this call is awaited
    search_results = await web_search(query, num_results=5) # Pass the query, optionally number of results

    # --- The rest of the command remains the same ---
    if search_results == "No relevant results found." or "error" in search_results.lower() or "timed out" in search_results.lower():
        # Slightly improved error checking
        error_reason = f" ({search_results})" if "error" in search_results.lower() else ""
        await ctx.send(f"Couldn't find useful results for '{query}'{error_reason}. Maybe try different keywords?")
        return

    # Summarize the findings using Gemini (without persona for clarity)
    summary = await summarize_with_gemini(search_results, query)

    # Check if summarization failed
    # ... (rest of the summary handling) ...

    formatted_summary = format_gemini_response(summary)
    final_text = truncate_string(formatted_summary)

    embed = discord.Embed(
         title=f"🔎 Google Search Summary for '{query}'", # Updated title
         description=final_text,
         color=discord.Color.blue()
    )
    # Optional: Add a link to the full search (Google Search link)
    Google_Search_link = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
    embed.add_field(name="Search Link", value=f"[View on Google]({Google_Search_link})", inline=False)
    embed.set_footer(text="Summarized using Gemini based on Google Custom Search results.")
    await ctx.send(embed=embed)

@bot.command(name='write', aliases=['ask'], help='Ask Anna anything! Uses Gemini AI.')
@commands.cooldown(rate=1, per=5, type=commands.BucketType.user) # Cooldown for AI generation
async def write_cmd(ctx, *, query: str):
    """Generates text using Gemini, applying Anna's persona."""
    await ctx.typing()
    initial_response_text = await generate_gemini_content(query, apply_persona=True) # Use the main function with persona

    # Check for specific refusal messages from Gemini to potentially add search links
    search_fallback = False
    if "potential copyright restrictions" in initial_response_text:
         search_query_suffix = " recipe" if "recipe" in query.lower() else ""
         search_fallback = True
    elif "safety concerns" in initial_response_text or "safety filters blocked" in initial_response_text:
         search_query_suffix = "" # General search for safety refusals
         search_fallback = True

    search_links = ""
    if search_fallback:
         await ctx.send(f"Hmm, I can't directly answer that, but maybe the web can help! Searching...")
         await ctx.typing()
         search_results = web_search(query + search_query_suffix)
         if search_results and "No relevant results" not in search_results and "Error" not in search_results:
             # Just provide links, not the full text here to avoid message clutter
             links = re.findall(r'\((https?://.*?)\)', search_results) # Extract URLs
             if links:
                  search_links = "\n\nMaybe these links will help?\n" + "\n".join(f"- <{link}>" for link in links[:3]) # Show first 3 links
         else:
              search_links = "\n\nI tried searching, but couldn't find helpful links either."

    # Combine initial response (which might be an error/refusal) with search links if generated
    response_text = initial_response_text + search_links

    # No need for the 'is_outdated' check here because the persona prompt already tells the AI
    # about its knowledge cutoff and suggests using ~search for recent info.
    # Adding another layer of search/regeneration based on dates found in the *persona's*
    # output might lead to confusing or incorrect results. Rely on the persona + search command.

    # Format and send the final response
    formatted_text = format_gemini_response(response_text)
    truncated_text = truncate_string(formatted_text)

    embed = discord.Embed(
        title="✨ Anna Says...", # More personality
        description=truncated_text,
        color=discord.Color.random() # Random color for fun
    )
    embed.set_footer(text=f"Asked by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
    await ctx.send(embed=embed)


@bot.command(name='today', help='Gets the current date and day.')
async def today_cmd(ctx):
    """Sends the current date."""
    now = datetime.now()
    # Example: Monday, May 05, 2025
    date_string = now.strftime("%A, %B %d, %Y")
    await ctx.send(f"Today is {date_string}. Hope it's a good one! Maybe time for snacks?")

# --- Run the Bot ---
if __name__ == "__main__":
    if not bot_token:
        print("ERROR: BOT_TOKEN environment variable not set. Bot cannot start.")
    else:
        try:
            logger.info("Starting bot...")
            bot.run(bot_token)
        except discord.LoginFailure:
            logger.error("Login failed: Invalid Discord Bot Token.")
        except Exception as e:
            logger.error(f"An error occurred while running the bot: {e}", exc_info=True)