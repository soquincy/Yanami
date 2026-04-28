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

    async def compress_video(self, input_path: str, target_size_mb: float = 9.5) -> str | None:
        """Forces the video to fit under the target size using FFmpeg."""
        output_path = input_path.replace(".mp4", "_fixed.mp4")
        
        duration_cmd = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", input_path
        ]
        proc = await asyncio.create_subprocess_exec(
            *duration_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        
        try:
            duration = float(stdout.decode().strip())
        except (ValueError, TypeError):
            return None

        target_total_bitrate = (target_size_mb * 8 * 1024 * 1024) / duration
        video_bitrate = int(target_total_bitrate - 128000)

        if video_bitrate < 100000:
            return None

        compress_cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-b:v", str(video_bitrate), "-maxrate", str(video_bitrate), "-bufsize", str(video_bitrate * 2),
            "-vcodec", "libx264", "-preset", "veryfast", "-acodec", "aac", "-b:a", "128k",
            output_path
        ]
        
        proc = await asyncio.create_subprocess_exec(*compress_cmd)
        await proc.wait()
        
        return output_path if os.path.exists(output_path) else None

    async def fetch_ytdlp(self, ctx, url: str, is_audio: bool, tmp_dir: str) -> str | None:
        ext = "mp3" if is_audio else "mp4"

        if is_audio:
            output_path = os.path.join(tmp_dir, f"%(uploader)s – %(title)s.{ext}")
            cmd = ["yt-dlp", "-x", "--audio-format", "mp3", "--audio-quality", "5", "-o", output_path, "--no-playlist", url]
            proc = await asyncio.create_subprocess_exec(*cmd)
            await proc.wait()
            files = os.listdir(tmp_dir)
            return os.path.join(tmp_dir, files[0]) if files else None

        for height in [1080, 720, 480]:
            for f in os.listdir(tmp_dir): 
                try: os.remove(os.path.join(tmp_dir, f))
                except: pass
            
            output_path = os.path.join(tmp_dir, f"%(uploader)s – %(title)s.{ext}")
            cmd = [
                "yt-dlp", "-f", f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/best[height<={height}][ext=mp4]",
                "--merge-output-format", "mp4", "-o", output_path, "--no-playlist", url
            ]
            proc = await asyncio.create_subprocess_exec(*cmd)
            await proc.wait()

            files = os.listdir(tmp_dir)
            if files:
                path = os.path.join(tmp_dir, files[0])
                if os.path.getsize(path) <= self.limit:
                    return path
                elif height == 480:
                    return await self.compress_video(path)
        return None

    async def handle_download(self, ctx, url: str, is_audio: bool):
        url = normalize_url(url)
        start_time = time.perf_counter()
        kind = "Audio" if is_audio else "Video"

        async with ctx.typing():
            with tempfile.TemporaryDirectory() as tmp_dir:
                local_path = await self.fetch_ytdlp(ctx, url, is_audio, tmp_dir)

                if not local_path or not os.path.exists(local_path):
                    return await ctx.send(f"❌ **{kind} failed.** Content is unavailable or too large.")

                elapsed = time.perf_counter() - start_time
                size_mb = os.path.getsize(local_path) / (1024 * 1024)

                if size_mb > 10.2: 
                    return await ctx.send(f"⚠️ **{kind} ({size_mb:.1f}MB) exceeds limit.**")

                await ctx.send(
                    content=f"✅ **{kind} Downloaded** • {elapsed:.2f}s",
                    file=discord.File(local_path)
                )

    @commands.hybrid_command(name="download", description="Download a video (1080p/720p/480p/Compressed)")
    @app_commands.describe(url="The URL of the video to download")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def download_video(self, ctx, url: str):
        await self.handle_download(ctx, url, is_audio=False)

    @commands.hybrid_command(name="audio", description="Download video as an MP3")
    @app_commands.describe(url="The URL of the audio to download")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def download_audio(self, ctx, url: str):
        await self.handle_download(ctx, url, is_audio=True)

    @download_video.error
    @download_audio.error
    async def dl_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"⏳ Wait **{error.retry_after:.1f}s**.", ephemeral=True, delete_after=10)

async def setup(bot):
    await bot.add_cog(YtDlp(bot))