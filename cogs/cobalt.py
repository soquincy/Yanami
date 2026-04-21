import aiohttp
import discord
from discord.ext import commands
import random
import os
import tempfile
import time
from urllib.parse import urlparse

class Cobalt(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.instances = [
            "https://pizza.br0k3.me",
            "https://subito-c.meowing.de",
            "https://nuko-c.meowing.de",
            "https://api.v9.co"
        ]

    async def fetch_cobalt(self, url: str, is_audio: bool = False):
        random.shuffle(self.instances)
        
        payload = {
            "url": url,
            "filenameStyle": "nerdy",
            "downloadMode": "audio" if is_audio else "auto",
            "alwaysProxy": True
        }

        if not is_audio:
            payload["videoQuality"] = "720"

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36"
        }
        
        timeout = aiohttp.ClientTimeout(total=20)
        for api_base in self.instances:
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(f"{api_base}/", json=payload, headers=headers) as res:
                        if res.status == 200:
                            data = await res.json()
                            status = data.get("status")

                            # Handle TikTok/Insta "picker" (SD vs HD vs Audio choices)
                            if status == "picker":
                                items = data.get("picker", [])
                                if items:
                                    # Filter for items that have a URL and pick the first one
                                    picker_url = items[0].get("url")
                                    if picker_url:
                                        return picker_url, api_base
                            
                            # Handle standard direct redirect/tunnel
                            if data.get("url"):
                                return data.get("url"), api_base
            except Exception:
                continue
        return None, None

    async def handle_download(self, ctx, url: str, is_audio: bool):
        start_time = time.perf_counter()
        
        async with ctx.typing():
            file_url, instance_url = await self.fetch_cobalt(url, is_audio)
            
            if not file_url:
                return await ctx.send("❌ Could not get a download link. The instance might be blocked or the link is invalid.")

            instance_name = urlparse(instance_url).netloc
            ext = "mp3" if is_audio else "mp4"

            with tempfile.TemporaryDirectory() as tmp_dir:
                file_path = os.path.join(tmp_dir, f"download.{ext}")
                
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(file_url) as resp:
                            if resp.status != 200:
                                return await ctx.send("❌ Failed to download from provider.")
                            
                            content_length = resp.headers.get('Content-Length')
                            limit = 10 * 1024 * 1024 # 10MB Discord limit

                            if content_length and int(content_length) > limit:
                                elapsed = time.perf_counter() - start_time
                                # ADDED < > AROUND file_url TO SUPPRESS EMBED
                                return await ctx.send(
                                    f"✅ **{'Audio' if is_audio else 'Video'} Found:** Took {elapsed:.2f}s. Download [here](<{file_url}>)\n"
                                    f"-# File exceeds Discord's 10MB limit ({int(content_length)//1024//1024}MB)\n"
                                    f"-# downloaded from [{instance_name}]({instance_url})"
                                )

                            with open(file_path, 'wb') as f:
                                f.write(await resp.read())

                    total_elapsed = time.perf_counter() - start_time
                    # ADDED < > AROUND file_url TO SUPPRESS EMBED
                    content = (
                        f"✅ **{'Audio' if is_audio else 'Video'} Downloaded:** Took {total_elapsed:.2f}s. Download [here](<{file_url}>)\n"
                        f"-# downloaded from [{instance_name}]({instance_url})"
                    )

                    await ctx.send(content=content, file=discord.File(file_path))
                
                except Exception as e:
                    await ctx.send(f"❌ Error processing upload: `{e}`")

    @commands.command(name='download', aliases=['dl'], help='Downloads videos via cobalt.tools instances.')
    async def download_video(self, ctx, url: str):
        await self.handle_download(ctx, url, is_audio=False)

    @commands.command(name='audio', aliases=['mp3'], help='Downloads media to audio via cobalt.tools instances.')
    async def download_audio(self, ctx, url: str):
        await self.handle_download(ctx, url, is_audio=True)

async def setup(bot):
    await bot.add_cog(Cobalt(bot))