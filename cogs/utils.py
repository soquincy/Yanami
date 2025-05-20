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
    async def ban_cmd(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        if member == ctx.author:
            await ctx.send("You can't ban yourself, silly!")
            return
        if member == self.bot.user:
            await ctx.send("I'm not banning myself!")
            return
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

    @commands.command(name='timeout', help='Times out a member (e.g., 10s, 5m, 1h, 1d, max 28d).')
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def timeout_cmd(self, ctx, member: discord.Member, time_str: str, *, reason: str = "No reason provided"):
        if member == ctx.author:
            await ctx.send("Can't timeout yourself!")
            return
        if member == self.bot.user:
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
            await ctx.send(f"{member.mention} has been timed out for {time_str}. Reason: {reason}")
            logger.info(f"{ctx.author.name} timed out {member.name} for {time_str}. Reason: {reason}")
        except discord.Forbidden:
            await ctx.send("I don't have the permissions to timeout this member. Check my 'Moderate Members' permission and role hierarchy.")
        except discord.HTTPException as e:
            logger.error(f"Failed to timeout {member.name}: {e}")
            await ctx.send(f"Something went wrong trying to timeout {member.mention}.")

    @commands.command(name='removetimeout', aliases=['rt', 'untimeout'], help='Removes a timeout from a member.')
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