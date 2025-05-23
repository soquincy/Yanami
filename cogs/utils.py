import discord
from discord.ext import commands
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

def parse_time_string(time_str: str) -> timedelta | None:
    """Parse time strings like '10s', '5m', '1h', '1d' into timedelta."""
    units = {'s': 'seconds', 'm': 'minutes', 'h': 'hours', 'd': 'days'}
    try:
        amount = int(time_str[:-1])
        unit = time_str[-1]
        if unit not in units:
            return None
        return timedelta(**{units[unit]: amount})
    except (ValueError, IndexError):
        return None

class ModerationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='purge', help='Deletes a specified number of messages (1-100).')
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def purge_cmd(self, ctx, amount: int):
        if 1 <= amount <= 100:
            try:
                deleted = await ctx.channel.purge(limit=amount + 1)  # +1 to delete command message
                await ctx.send(f"Poof! Deleted {len(deleted) - 1} message(s).", delete_after=5)
            except discord.Forbidden:
                await ctx.send("I need the 'Manage Messages' permission to do that!")
            except discord.HTTPException as e:
                logger.error(f"Failed to purge messages: {e}")
                await ctx.send("Something went wrong while deleting messages.")
        else:
            await ctx.send("Please provide a number between 1 and 100.")

    @commands.command(name='ban', help='Bans a member from the server.')
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def ban_cmd(self, ctx, member: discord.User, *, reason: str = "No reason provided"):
        # Attempt to get member from guild
        target = ctx.guild.get_member(member.id)

        if target:
            # User is in the server
            if target == ctx.author:
                await ctx.send("You can't ban yourself.")
                return
            if target == self.bot.user:
                await ctx.send("I can't ban myself.")
                return
            if ctx.author.top_role <= target.top_role and ctx.guild.owner != ctx.author:
                await ctx.send("You can't ban someone with a role higher than or equal to yours.")
                return

        try:
            await ctx.guild.ban(member, reason=f"Banned by {ctx.author}: {reason}")
            await ctx.send(f"{member.mention if isinstance(member, discord.Member) else member.name} has been banned. Reason: {reason}")
            logger.info(f"{ctx.author} banned {member}. Reason: {reason}")
        except discord.NotFound:
            await ctx.send("User not found. They might not exist or already be banned.")
        except discord.Forbidden:
            await ctx.send("I don't have permission to ban this user. Check role hierarchy and permissions.")
        except discord.HTTPException as e:
            logger.error(f"Failed to ban {member}: {e}")
            await ctx.send("An error occurred while trying to ban this user.")

    @commands.command(name='kick', help='Kicks a member from the server.')
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    async def kick_cmd(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        if member == ctx.author:
            await ctx.send("You can't kick yourself!")
            return
        if member == self.bot.user:
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

    @commands.command(name='timeout', aliases=['to', 'mute'], help='Times out a member (e.g., 10s, 5m, 1h, 1d, max 28d).')
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def timeout_cmd(self, ctx, member: discord.Member, time_str: str, *, reason: str = "No reason provided"):
        # Reject invalid targets
        if not isinstance(member, discord.Member):
            await ctx.send("That user isn't in this server.")
            return

        if member == ctx.author:
            await ctx.send("Can't timeout yourself!")
            return
        if member == self.bot.user:
            await ctx.send("Nice try, but I'm not timing myself out.")
            return
        if ctx.author.top_role <= member.top_role and ctx.guild.owner != ctx.author:
            await ctx.send("You can't timeout someone with a role higher than or equal to yours.")
            return

        # Parse time
        delta = parse_time_string(time_str)
        if delta is None:
            await ctx.send("Invalid time format. Use: `10s`, `5m`, `1h`, `3d`, etc.")
            return

        max_timeout = timedelta(days=28)
        if delta > max_timeout:
            await ctx.send("Timeout duration can't exceed 28 days.")
            return
        if delta <= timedelta(seconds=0):
            await ctx.send("Timeout duration must be positive.")
            return

        try:
            await member.timeout(delta, reason=f"Timed out by {ctx.author.name}: {reason}")
            
            # Format the actual applied duration
            total_seconds = int(delta.total_seconds())
            if total_seconds < 60:
                duration_display = f"{total_seconds}s"
            elif total_seconds < 3600:
                minutes = total_seconds // 60
                seconds = total_seconds % 60
                duration_display = f"{minutes}m" + (f" {seconds}s" if seconds > 0 else "")
            elif total_seconds < 86400:
                hours = total_seconds // 3600
                remaining = total_seconds % 3600
                minutes = remaining // 60
                duration_display = f"{hours}h" + (f" {minutes}m" if minutes > 0 else "")
            else:
                days = total_seconds // 86400
                remaining = total_seconds % 86400
                hours = remaining // 3600
                duration_display = f"{days}d" + (f" {hours}h" if hours > 0 else "")
            
            await ctx.send(f"{member.mention} has been timed out for {duration_display}. Reason: {reason}")
            logger.info(f"{ctx.author.name} timed out {member.name} for {duration_display}. Reason: {reason}")
        except discord.Forbidden:
            await ctx.send("I can't timeout that member. Check my permissions and role position.")
        except discord.HTTPException as e:
            logger.error(f"Failed to timeout {member.name}: {e}")
            await ctx.send(f"Something went wrong trying to timeout {member.mention}.")

    @commands.command(name='removetimeout', aliases=['rt', 'ut', 'untimeout'], help='Removes a timeout from a member.')
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def removetimeout_cmd(self, ctx, member: discord.Member):
        if not member.is_timed_out():
            await ctx.send(f"{member.mention} isn't currently timed out.")
            return
        try:
            await member.timeout(None, reason=f"Timeout removed by {ctx.author.name}")
            await ctx.send(f"Okay, {member.mention}'s timeout has been removed.")
            logger.info(f"{ctx.author.name} removed timeout from {member.name}.")
        except discord.Forbidden:
            await ctx.send("I don't have the permissions to remove timeouts. Check my 'Moderate Members' permission.")
        except discord.HTTPException as e:
            logger.error(f"Failed to remove timeout from {member.name}: {e}")
            await ctx.send(f"Something went wrong trying to remove the timeout from {member.mention}.")

async def setup(bot):
    await bot.add_cog(ModerationCog(bot))