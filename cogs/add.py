from discord.ext import commands

class AddCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='add', help='Adds two whole numbers.')
    async def add_cmd(self, ctx, num1: int, num2: int):
        """Adds two integers provided by the user."""
        result = num1 + num2
        await ctx.send(f"Okay, {num1} + {num2} = {result}. Easy peasy!")

async def setup(bot):
    await bot.add_cog(AddCog(bot))