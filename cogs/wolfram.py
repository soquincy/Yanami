import os
import aiohttp
import logging
import re
import discord
from discord.ext import commands

WOLFRAM_SHORT_APPID = os.getenv("WOLFRAM_APPID_SHORT")
WOLFRAM_LLM_APPID = os.getenv("WOLFRAM_APPID_LLM")

class WolframCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="math", aliases=['wa', 'wolfram', 'mq'], help="Answers math queries using Wolfram|Alpha.")
    async def math(self, ctx, *, query: str):
        logging.info(f"Processing query: {query}")
        
        # Try short answer API first
        short_result = await self.query_short_answer(query)
        
        if short_result and "did not understand" not in short_result.lower():
            logging.info(f"Short API succeeded: {short_result[:100]}...")
            embed = self.create_embed("Wolfram Alpha Result", short_result, query)
            await ctx.send(embed=embed)
            return
        
        logging.info("Short API failed or returned 'did not understand', trying full API")
        
        # If short answer fails, try full API
        full_result = await self.query_llm_api(query)
        
        if full_result:
            logging.info(f"Full API succeeded: {full_result[:100]}...")
            embed = self.create_embed("Wolfram Alpha Result", full_result, query)
            await ctx.send(embed=embed)
        else:
            logging.warning("Both APIs failed to return results")
            await ctx.send("Sorry, I couldn't find an answer to your query. Both Wolfram APIs were unable to process this request.")

    async def query_short_answer(self, query: str) -> str | None:
        if not WOLFRAM_SHORT_APPID:
            logging.error("WOLFRAM_SHORT_APPID not set")
            return None
        
        logging.info("Calling Wolfram Short Answer API")
        url = "http://api.wolframalpha.com/v1/result"
        params = {
            "appid": WOLFRAM_SHORT_APPID,
            "i": query,
            "units": "metric"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as resp:
                    logging.info(f"Short API response status: {resp.status}")
                    if resp.status == 200:
                        result = await resp.text()
                        logging.info(f"Short API result: {result}")
                        return result
                    elif resp.status == 501:
                        logging.info("Short API returned 501 (input not understood)")
                    else:
                        logging.warning(f"Short API returned unexpected status: {resp.status}")
                    return None
        except Exception as e:
            logging.error(f"Error in short answer query: {e}")
            return None

    async def query_llm_api(self, query: str) -> str | None:
        if not WOLFRAM_LLM_APPID:
            logging.error("WOLFRAM_LLM_APPID not set")
            return None
        
        logging.info("Calling Wolfram LLM API")
        url = "https://www.wolframalpha.com/api/v1/llm-api"
        params = {
            "appid": WOLFRAM_LLM_APPID,
            "input": query,
            "units": "metric",
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as resp:
                    logging.info(f"LLM API response status: {resp.status}")
                    if resp.status == 200:
                        content_type = resp.headers.get('content-type', '').lower()
                        logging.info(f"LLM API content type: {content_type}")
                        
                        if 'application/json' in content_type:
                            # JSON response format
                            data = await resp.json()
                            result = data.get("result")
                            if result:
                                logging.info(f"LLM API JSON result: {str(result)[:200]}...")
                                return str(result)
                            else:
                                logging.info("LLM API returned empty JSON result")
                        elif 'text/plain' in content_type:
                            # Plain text response format
                            result = await resp.text()
                            if result and result.strip():
                                logging.info(f"LLM API text result: {result[:200]}...")
                                return result.strip()
                            else:
                                logging.info("LLM API returned empty text result")
                        else:
                            logging.warning(f"LLM API returned unexpected content type: {content_type}")
                            # Try to get the text anyway for debugging
                            error_text = await resp.text()
                            logging.warning(f"LLM API response: {error_text[:200]}...")
                    else:
                        logging.warning(f"LLM API returned status: {resp.status}")
                        # Log response text for debugging
                        error_text = await resp.text()
                        logging.warning(f"LLM API error response: {error_text}")
                    return None
        except Exception as e:
            logging.error(f"Error in LLM API query: {e}")
            return None

    def format_wolfram_text(self, text: str) -> str:
        # Normalize whitespace and strip leading/trailing spaces/newlines
        text = re.sub(r' +', ' ', text).strip()
        text = re.sub(r'^\n+', '', text)  # remove leading newlines
        text = re.sub(r'\n+$', '', text)  # remove trailing newlines

        # Format headers like "Basic properties:"
        text = re.sub(r'^([^:\n]+):', r'**\1:**', text, flags=re.MULTILINE)

        # Add space after ≈ if missing
        text = re.sub(r'≈(?! )', '≈ ', text)

        # Bold left column in "A | B" table-like lines
        text = re.sub(r'(?m)^(\s*)([^:\n|]+)\s*\|\s*([^\n]+)', r'\1**\2** | \3', text)

        # Reduce multiple blank lines to max two
        text = re.sub(r'\n{3,}', '\n\n', text)

        return text

    def create_embed(self, title: str, content: str, query: str) -> discord.Embed:
        """Create a Discord embed for Wolfram Alpha results"""
        # Format the content
        formatted_content = self.format_wolfram_text(content)
        
        # Create embed with Wolfram Alpha branding
        embed = discord.Embed(
            title=title,
            description=formatted_content[:4096],  # Discord embed description limit
            color=0xFF6C00  # Wolfram Alpha orange
        )
        
        # Add query as footer
        embed.set_footer(text=f"Query: {query}")
        
        # Add Wolfram Alpha branding
        embed.set_author(
            name="Wolfram|Alpha",
            icon_url="https://www.wolframalpha.com/favicon.ico"
        )
        
        # If content is too long, truncate with indicator
        if len(formatted_content) > 4096:
            embed.description = formatted_content[:4090] + "..."
            embed.add_field(
                name="Note",
                value="Response truncated due to length limit",
                inline=False
            )
        
        return embed

async def setup(bot):
    await bot.add_cog(WolframCog(bot))