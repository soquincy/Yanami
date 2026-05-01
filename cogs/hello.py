# cogs/hello.py: Simple response and sample logic for future commands

from discord.ext import commands

class HelloCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name='hello', help='Says hello back!')
    async def hello_cmd(self, ctx):
        await ctx.send(f"Hello {ctx.author.mention}!")

async def setup(bot):
    await bot.add_cog(HelloCog(bot))