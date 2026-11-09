"""
Módulo de Comandos Interativos do Discord (Listener do Bot ObjectWatcher).
Permite alterar o canal oficial de notificações diretamente no chat do Discord com !canal.
"""

import logging
import discord
from discord.ext import commands
from src.config import settings
from src.database import DatabaseManager

logger = logging.getLogger("ObjectWatcher.BotListener")


def start_bot_listener(token: str | None = None):
    """Inicia o bot em modo de escuta para comandos interativos no Discord."""
    bot_token = token or settings.discord_bot_token
    if not bot_token:
        print("[Erro] DISCORD_BOT_TOKEN não configurado no .env.")
        return

    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True

    bot = commands.Bot(command_prefix="!", intents=intents)

    @bot.event
    async def on_ready():
        print(f"\n🤖 Bot {bot.user} conectado com sucesso no Discord!")
        print("💡 Para definir o canal de notificações, vá até o canal desejado no Discord e digite: !canal")
        print("   Para ver estatísticas no Discord, digite: !stats\n")
        print("Pressione Ctrl+C para encerrar o modo de escuta.\n")

    @bot.command(name="canal", aliases=["setchannel", "setcanal", "configurar"])
    async def cmd_set_channel(ctx: commands.Context):
        """Define o canal onde a mensagem foi enviada como o canal oficial de alertas."""
        channel_id = str(ctx.channel.id)
        channel_name = ctx.channel.name
        guild_name = ctx.guild.name if ctx.guild else "Servidor"

        # Salva a escolha no banco de dados SQLite persistente
        db = DatabaseManager()
        db.set_setting("target_channel_id", channel_id)

        embed = discord.Embed(
            title="✅ Canal de Notificações Configurado!",
            description=(
                f"O canal **#{channel_name}** no servidor **{guild_name}** foi definido com sucesso "
                "como o canal oficial de alertas fiscais da **ObjectData**.\n\n"
                "Todas as novas Notas Técnicas, Schemas XML e alterações tributárias serão postadas aqui."
            ),
            color=settings.color_info
        )
        embed.add_field(name="ID do Canal", value=f"`{channel_id}`", inline=True)
        embed.add_field(name="Configurado Por", value=ctx.author.mention, inline=True)
        embed.set_footer(text="ObjectWatcher • ObjectData Integrações Fiscais", icon_url=settings.discord_avatar_url)

        await ctx.send(embed=embed)
        logger.info(f"Canal alterado via comando do Discord para #{channel_name} (ID: {channel_id})")

    @bot.command(name="status", aliases=["stats", "info"])
    async def cmd_status(ctx: commands.Context):
        """Exibe o status e estatísticas de monitoramento."""
        db = DatabaseManager()
        stats = db.get_stats()
        active_id = db.get_setting("target_channel_id") or settings.discord_channel_id

        embed = discord.Embed(
            title="📊 Status do ObjectWatcher",
            color=settings.color_info
        )
        embed.add_field(name="Canal Ativo", value=f"<#{active_id}>" if active_id else "Não configurado", inline=True)
        embed.add_field(name="Total de Itens Analisados", value=str(stats.get("total_items", 0)), inline=True)

        by_source_lines = [f"• {src}: {cnt}" for src, cnt in stats.get("by_source", {}).items()]
        embed.add_field(name="Por Fonte", value="\n".join(by_source_lines) or "Nenhum ainda", inline=False)

        await ctx.send(embed=embed)

    try:
        bot.run(bot_token)
    except KeyboardInterrupt:
        print("\nModo de escuta finalizado.")
    except Exception as e:
        logger.error(f"Erro ao executar bot listener: {e}")

