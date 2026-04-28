import asyncio
import discord
from discord.ext import commands
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

    async def fetch_ytdlp(self, ctx, url: str, is_audio: bool, tmp_dir: str) -> str | None:
        ext = "mp3" if is_audio else "mp4"
        limit = 10 * 1024 * 1024  # 10MB

        if is_audio:
            output_path = os.path.join(tmp_dir, f"%(uploader)s – %(title)s.{ext}")
            cmd = [
                "yt-dlp",
                "-x", "--audio-format", "mp3", "--audio-quality", "5",
                "-o", output_path,
                "--no-playlist",
                "--verbose",
                url,
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                await asyncio.wait_for(proc.wait(), timeout=60)
            except asyncio.TimeoutError:
                proc.kill()
                await ctx.send("❌ yt-dlp timed out.")
                return None

            stdout, stderr = await proc.communicate()
            stderr_text = stderr.decode("utf-8", errors="replace").strip()
            if stderr_text:
                print(stderr_text)

            if proc.returncode != 0:
                error_msg = stderr_text or "No error output."
                await ctx.send(f"❌ yt-dlp failed (code {proc.returncode}):\n```\n{error_msg[:1800]}\n```")
                return None

            files = os.listdir(tmp_dir)
            if files:
                return os.path.join(tmp_dir, files[0])
            return None

        # Video: try qualities in order, stop at first one under 10MB
        for height in [1080, 480]:
            for f in os.listdir(tmp_dir):
                os.remove(os.path.join(tmp_dir, f))

            output_path = os.path.join(tmp_dir, f"%(uploader)s - %(title)s.{ext}")
            cmd = [
                "yt-dlp",
                "-f", f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/best[height<={height}][ext=mp4]/best[height<={height}]",
                "--merge-output-format", "mp4",
                "-o", output_path,
                "--no-playlist",
                "--verbose",
                url,
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                await asyncio.wait_for(proc.wait(), timeout=60)
            except asyncio.TimeoutError:
                proc.kill()
                await ctx.send("❌ yt-dlp timed out.")
                return None

            stdout, stderr = await proc.communicate()
            stderr_text = stderr.decode().strip()
            if stderr_text:
                print(stderr_text)

            if proc.returncode != 0:
                error_msg = stderr_text or "No error output."
                await ctx.send(f"❌ yt-dlp failed (code {proc.returncode}):\n```\n{error_msg[:1800]}\n```")
                return None

            files = os.listdir(tmp_dir)
            if files:
                path = os.path.join(tmp_dir, files[0])
                if os.path.getsize(path) <= limit:
                    return path

        return None

    async def handle_download(self, ctx, url: str, is_audio: bool):
        url = normalize_url(url)
        start_time = time.perf_counter()
        limit = 10 * 1024 * 1024  # 10MB
        kind = "Audio" if is_audio else "Video"

        async with ctx.typing():
            with tempfile.TemporaryDirectory() as tmp_dir:
                local_path = await self.fetch_ytdlp(ctx, url, is_audio, tmp_dir)

                if not local_path:
                    return await ctx.send(
                        "❌ Download failed. The link may be unsupported, unavailable, "
                        "or the file is too large even at 480p."
                    )

                elapsed = time.perf_counter() - start_time
                size = os.path.getsize(local_path)

                if size > limit:
                    return await ctx.send(
                        f"⚠️ **{kind} too large to upload** ({size // 1024 // 1024}MB). "
                        f"Discord's limit is 10MB.\n-# via yt-dlp • {elapsed:.2f}s"
                    )

                await ctx.send(
                    content=f"✅ **{kind} Downloaded** • {elapsed:.2f}s • via yt-dlp",
                    file=discord.File(local_path)
                )

    @commands.command(name="download", aliases=["dl"], help="Downloads a video via yt-dlp. Usage: <download <url>")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def download_video(self, ctx, url: str):
        await self.handle_download(ctx, url, is_audio=False)

    @commands.command(name="audio", aliases=["mp3"], help="Downloads a video as audio via yt-dlp. Usage: <audio <url>")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def download_audio(self, ctx, url: str):
        await self.handle_download(ctx, url, is_audio=True)

async def setup(bot):
    await bot.add_cog(YtDlp(bot))