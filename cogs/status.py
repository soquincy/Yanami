import discord
from discord.ext import commands, tasks

class StatusCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.update_status.start()

    async def cog_unload(self):
        self.update_status.cancel()

    @tasks.loop(minutes=5)
    async def update_status(self):
        await self.bot.wait_until_ready()

        if self.bot.guilds:
            server_name = self.bot.guilds[0].name
            await self.bot.change_presence(
                status=discord.Status.dnd,
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name=server_name
                )
            )

    @update_status.before_loop
    async def before_update_status(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(StatusCog(bot))