import os
import aiohttp
from discord.ext import commands

WOLFRAM_SHORT_APPID = os.getenv("WOLFRAM_APPID_SHORT")
WOLFRAM_FULL_APPID = os.getenv("WOLFRAM_APPID_FULL")

class WolframCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="math", aliases=['wa', 'wolfram', 'mq'], help='Answers math queries. Uses the Wolfram|Alpha API.')
    async def math(self, ctx, *, query: str):
        """Query Wolfram|Alpha for math answers with fallback."""

        short_result = await self.query_short_answers(query)
        if not short_result or "did not understand" in short_result.lower():
            full_result = await self.query_full_results(query)
            if full_result:
                await ctx.send(full_result)
            else:
                await ctx.send("Sorry, I couldn't find an answer.")
        else:
            await ctx.send(short_result)

    async def query_short_answers(self, query):
        url = "https://api.wolframalpha.com/v1/result"
        params = {
            "appid": WOLFRAM_SHORT_APPID,
            "i": query,
            "units": "metric"
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    return await resp.text()
                return None

    async def query_full_results(self, query):
        url = "https://api.wolframalpha.com/v2/query"
        params = {
            "appid": WOLFRAM_FULL_APPID,
            "input": query,
            "format": "plaintext",
            "output": "JSON",
            "units": "metric"
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # Extract plaintext from pods
                    pods = data.get("queryresult", {}).get("pods", [])
                    texts = []
                    for pod in pods:
                        for subpod in pod.get("subpods", []):
                            if "plaintext" in subpod and subpod["plaintext"]:
                                texts.append(subpod["plaintext"])
                    return "\n".join(texts) if texts else None
                return None

async def setup(bot):
    await bot.add_cog(WolframCog(bot))