import asyncio
import discord
from discord.ext import commands
from discord import app_commands
import os
import tempfile
import time

def normalize_url(url: str) -> str:
    if "music.youtube.com" in url:
        url = url.replace("music.youtube.com", "www.youtube.com")
    return url

class YtDlp(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.limit = 10 * 1024 * 1024  # 10MB Discord Limit

    async def fetch_ytdlp(self, ctx, url: str, is_audio: bool, tmp_dir: str) -> str | None:
        ext = "mp3" if is_audio else "mp4"
        
        if is_audio:
            output_path = os.path.join(tmp_dir, f"%(uploader)s - %(title)s.{ext}")
            cmd = [
                "yt-dlp",
                "-x", "--audio-format", "mp3", "--audio-quality", "5",
                "--max-filesize", "10M",
                "-o", output_path,
                "--no-playlist",
                url,
            ]
            return await self.run_ytdlp(ctx, cmd, tmp_dir)

        # Video logic: Resolution iteration
        for height in [1080, 720, 480, 360]:
            check_cmd = [
                "yt-dlp",
                "--print", "%(filesize,filesize_approx)s",
                "-f", f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/best[height<={height}][ext=mp4]/best[height<={height}]",
                url
            ]
            
            check_proc = await asyncio.create_subprocess_exec(
                *check_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await check_proc.communicate()
            
            try:
                decoded = stdout.decode().strip().split()
                if decoded:
                    size_str = decoded[0]
                    if size_str.isdigit() and int(size_str) > self.limit:
                        continue 
            except (IndexError, ValueError):
                pass 

            output_path = os.path.join(tmp_dir, f"%(uploader)s - %(title)s_{height}p.{ext}")
            cmd = [
                "yt-dlp",
                "-f", f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/best[height<={height}][ext=mp4]/best[height<={height}]",
                "--merge-output-format", "mp4",
                "--max-filesize", "10M",
                "-o", output_path,
                "--no-playlist",
                url,
            ]
            
            path = await self.run_ytdlp(ctx, cmd, tmp_dir)
            if path and os.path.getsize(path) <= self.limit:
                return path
            
            for f in os.listdir(tmp_dir):
                try:
                    os.remove(os.path.join(tmp_dir, f))
                except:
                    pass

        return None

    async def run_ytdlp(self, ctx, cmd: list, tmp_dir: str) -> str | None:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            await asyncio.wait_for(proc.wait(), timeout=120)
        except asyncio.TimeoutError:
            proc.kill()
            return None

        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            return None

        files = os.listdir(tmp_dir)
        if files:
            # Sort by size to pick the actual video file, not leftovers
            files.sort(key=lambda x: os.path.getsize(os.path.join(tmp_dir, x)), reverse=True)
            return os.path.join(tmp_dir, files[0])
        return None

    async def handle_download(self, ctx, url: str, is_audio: bool):
        # Critical for slash commands: tells Discord to wait up to 15 mins
        await ctx.defer()
        
        url = normalize_url(url)
        start_time = time.perf_counter()
        kind = "Audio" if is_audio else "Video"

        with tempfile.TemporaryDirectory() as tmp_dir:
            local_path = await self.fetch_ytdlp(ctx, url, is_audio, tmp_dir)

            if not local_path or not os.path.exists(local_path):
                return await ctx.send(f"❌ {kind} too large for Discord (10MB limit) or link unavailable.")

            elapsed = time.perf_counter() - start_time
            size_mb = os.path.getsize(local_path) / (1024 * 1024)

            await ctx.send(
                content=f"✅ **{kind} Downloaded** • {elapsed:.2f}s • {size_mb:.1f}MB",
                file=discord.File(local_path)
            )

    @commands.hybrid_command(name="download", aliases=["dl"], help="Downloads video from a link (10MB limit).")
    @app_commands.describe(url="The URL of the video to download.")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def download_video(self, ctx, url: str):
        await self.handle_download(ctx, url, is_audio=False)

    @commands.hybrid_command(name="audio", aliases=["mp3"], help="Converts a video link to an MP3 file.")
    @app_commands.describe(url="The URL of the video to convert to audio.")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def download_audio(self, ctx, url: str):
        await self.handle_download(ctx, url, is_audio=True)

async def setup(bot):
    await bot.add_cog(YtDlp(bot))