import discord
from discord.ext import commands

class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='help', help='Shows help information for commands.')
    async def help_cmd(self, ctx, *, command_name: str = None):
        prefix = self.bot.command_prefix

        if not command_name:
            embed = discord.Embed(
                title="Anna's Command List!",
                description=f"Use `{prefix}help <command_name>` for more details on a specific command.",
                color=discord.Color.random()
            )
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)

            fun_cmds = []
            mod_cmds = []
            util_cmds = []

            for cmd in self.bot.commands:
                if cmd.hidden:
                    continue

                if cmd.name in ['hello', 'write', 'ask', 'today']:
                    fun_cmds.append(f"`{prefix}{cmd.name}` - {cmd.help or 'No description'}")
                elif cmd.name in ['kick', 'purge', 'removetimeout', 'rt', 'timeout', 'ban']:
                    mod_cmds.append(f"`{prefix}{cmd.name}` - {cmd.help or 'No description'}")
                elif cmd.name in ['math', 'search', 'help']:
                    util_cmds.append(f"`{prefix}{cmd.name}` - {cmd.help or 'No description'}")

            if fun_cmds:
                embed.add_field(name="🎉 Fun & Info", value="\n".join(fun_cmds), inline=False)
            if mod_cmds:
                embed.add_field(name="🛡️ Moderation", value="\n".join(mod_cmds), inline=False)
            if util_cmds:
                embed.add_field(name="🔧 Utility", value="\n".join(util_cmds), inline=False)

            embed.set_footer(text="Remember, my knowledge is mostly from early 2025!")
            await ctx.send(embed=embed)

        else:
            command = self.bot.get_command(command_name.lower())
            if command and not command.hidden:
                usage = f"`{prefix}{command.qualified_name}"
                params = []
                for name, param in command.params.items():
                    if name in ('self', 'ctx'):
                        continue
                    if param.kind == param.VAR_POSITIONAL:
                        params.append(f"<{name}...>")
                    elif param.default is param.empty:
                        params.append(f"<{name}>")
                    else:
                        params.append(f"[{name}]")
                usage += " " + " ".join(params) + "`"

                embed = discord.Embed(
                    title=f"Help for `~{command.name}`",
                    description=command.help or "No description provided.",
                    color=discord.Color.green()
                )
                embed.add_field(name="Usage", value=usage, inline=False)
                if command.aliases:
                    aliases = ", ".join([f"`{prefix}{a}`" for a in command.aliases])
                    embed.add_field(name="Aliases", value=aliases, inline=False)

                # Cooldown info
                if command._buckets and command._buckets._cooldown:
                    cd = command._buckets._cooldown
                    embed.add_field(name="Cooldown", value=f"{cd.rate} time(s) per {cd.per:.0f} seconds", inline=False)

                # Permissions info (basic)
                perm_names = []
                checks = getattr(command.callback, '__commands_checks__', [])
                for check in checks:
                    if 'has_permissions' in str(check):
                        try:
                            required_perms = [p for p, v in check.__closure__[0].cell_contents.items() if v]
                            perm_names.extend(p.replace('_', ' ').title() for p in required_perms)
                        except Exception:
                            pass
                    elif 'is_owner' in str(check):
                        perm_names.append("Bot Owner")
                if perm_names:
                    embed.add_field(name="Permissions", value=", ".join(perm_names), inline=False)

                await ctx.send(embed=embed)
            else:
                await ctx.send(f"Sorry, I couldn't find a command named `{command_name}`. Try `~help` for a list.")

async def setup(bot):
    await bot.add_cog(HelpCog(bot))
