"""Paquete modular de interfaz de usuario (Front-end de Discord) para Tooodles v7."""

import asyncio
from datetime import datetime
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile

import discord
from discord.ext import commands
from discord.ui import Button

from sznLogger import get_logger
from .embeds import EmbedFactory
from .theme import UITheme, format_duration, render_progress_bar
from .views import (
    AddPlaylistModal,
    DeletePlaylistSelect,
    EditPlaylistModal,
    EditPlaylistSelect,
    HelpCategorySelect,
    HelpNavigatorView,
    MusicControls,
    PersistApprovalView,
    PlaylistSelect,
    PlaylistsView,
    PrefixModal,
    QueuePaginationView,
    SettingsControls,
)

logger = get_logger("ui")


class MusicUI(commands.Cog):
    """Cog principal de interfaz de usuario, paneles de control, ajustes y diagnóstico."""

    MusicControls = MusicControls
    SettingsControls = SettingsControls
    QueuePaginationView = QueuePaginationView
    HelpNavigatorView = HelpNavigatorView
    PlaylistsView = PlaylistsView

    def __init__(self, bot) -> None:
        self.bot = bot
        self.bot.add_check(self.check_command_channel)

    def cog_unload(self) -> None:
        """Elimina el check global de canal exclusivo al descargar el Cog."""
        self.bot.remove_check(self.check_command_channel)

    async def check_command_channel(self, ctx) -> bool:
        """Verifica si el comando fue ejecutado dentro del canal exclusivo configurado."""
        if not ctx.guild or not ctx.command:
            return True

        from sznUtils import load_config
        channel_id_str = load_config(f"cmd_channel_{ctx.guild.id}")
        if not channel_id_str or channel_id_str.strip() == "":
            return True

        if str(ctx.channel.id) == channel_id_str:
            return True

        exempt_commands = (
            "channel", "canal", "settings", "config", "persist", "persistencia",
            "join", "connect", "conectar", "unir", "j", "help", "ayuda", "h",
            "reloadrecsys",
        )
        cmd_name = getattr(ctx.command, "name", "").lower()
        invoked_with = getattr(ctx, "invoked_with", "").lower()
        if cmd_name in exempt_commands or invoked_with in exempt_commands:
            return True

        try:
            await ctx.message.delete(delay=3)
            await ctx.send(
                f"⚠️ Los comandos de música están restringidos al canal exclusivo: <#{channel_id_str}>.",
                delete_after=5,
            )
        except Exception as err:
            logger.debug(f"No se pudo eliminar mensaje fuera del canal exclusivo: {err}")

        return False

    async def notify_now_playing(self, ctx, song_dict: dict) -> None:
        """Publica el panel 'Ahora Reproduciendo' reemplazando cualquier panel previo del servidor."""
        core = self.bot.get_cog("MusicCore")
        if not core:
            return

        player = core.get_player(ctx)
        previous_msg = getattr(player, "now_playing_message", None)
        if previous_msg is not None:
            try:
                await previous_msg.delete()
            except Exception as err:
                logger.debug(f"Mensaje Now Playing anterior ya no existía: {err}")
            finally:
                player.now_playing_message = None

        vc_name = (
            ctx.author.voice.channel.name
            if getattr(ctx, "author", None) and getattr(ctx.author, "voice", None) and ctx.author.voice.channel
            else "Canal de voz"
        )
        embed = EmbedFactory.build_now_playing_embed(song_dict, player, vc_name=vc_name)

        view = self.MusicControls(core, ctx)
        if getattr(ctx, "guild", None) and getattr(ctx, "channel", None):
            view.add_item(
                Button(
                    label="📜 Ir al chat",
                    style=discord.ButtonStyle.link,
                    url=f"https://discord.com/channels/{ctx.guild.id}/{ctx.channel.id}/",
                )
            )

        try:
            sent_msg = await ctx.send(embed=embed, view=view, delete_after=300)
            player.now_playing_message = sent_msg
        except Exception as err:
            logger.warning(f"⚠️ Error al enviar notificación de reproducción: {err}")

    @commands.command(name="controls", aliases=["ctr", "player"])
    async def controls(self, ctx) -> None:
        """Muestra el panel interactivo con los controles del reproductor."""
        core = self.bot.get_cog("MusicCore")
        if not core:
            await ctx.send("❌ No se encontró el módulo de música.")
            return

        player = core.get_player(ctx)
        if not player.current_song:
            await ctx.send("⚠️ No hay ninguna canción reproduciéndose en este momento.")
            return

        await self.notify_now_playing(ctx, player.current_song)

    @commands.command(name="persist", aliases=["persistencia"])
    async def toggle_persist_queue(self, ctx, estado: str = None) -> None:
        """Habilita o deshabilita la persistencia de colas para este servidor (Solicitud al Dueño)."""
        if not ctx.guild:
            await ctx.send("⚠️ Este comando solo se puede usar en un servidor.")
            return

        is_admin = ctx.author.guild_permissions.administrator
        is_owner = await self.bot.is_owner(ctx.author)

        if not (is_admin or is_owner):
            await ctx.send("❌ Solo los administradores del servidor o el dueño del bot pueden cambiar esta configuración.")
            return

        from sznUtils import is_guild_persist_enabled, set_guild_persist_enabled

        if not estado:
            current = is_guild_persist_enabled(ctx.guild.id)
            status_str = "🟢 Activada" if current else "🔴 Desactivada"
            await ctx.send(
                f"ℹ️ La persistencia de colas en este servidor está: **{status_str}**.\n"
                f"Usa `{ctx.prefix}persist on`, `{ctx.prefix}persist off` o el panel `{ctx.prefix}settings`."
            )
            return

        mode = estado.lower().strip()
        if mode in ("on", "activar", "activado", "true", "1"):
            if is_owner:
                await asyncio.to_thread(set_guild_persist_enabled, ctx.guild.id, True)
                await ctx.send("✅ Persistencia de colas **activada** directamente por el dueño del bot.")
            else:
                try:
                    app_info = await self.bot.application_info()
                    owner = app_info.owner

                    embed = discord.Embed(
                        title="📩 Solicitud de Persistencia de Colas",
                        description=f"El administrador **@{ctx.author.name}** solicita activar la persistencia de colas.",
                        color=UITheme.WARNING,
                    )
                    embed.add_field(name="🏰 Servidor", value=f"`{ctx.guild.name}` (`{ctx.guild.id}`)", inline=True)
                    embed.add_field(name="👤 Solicitante", value=f"@{ctx.author.name} (`{ctx.author.id}`)", inline=True)
                    embed.set_footer(text="Usa los botones para responder a esta solicitud.")

                    view = PersistApprovalView(self.bot, ctx.guild, ctx)
                    await owner.send(embed=embed, view=view)
                    await ctx.send(
                        "📩 **Solicitud enviada**: Se envió un mensaje al dueño del bot para solicitar autorización. Te notificaremos cuando responda."
                    )
                except Exception as err:
                    logger.warning(f"⚠️ Error al enviar solicitud por DM al dueño: {err}")
                    await ctx.send("⚠️ No se pudo enviar el mensaje privado al dueño del bot. Por favor intenta más tarde.")

        elif mode in ("off", "desactivar", "desactivado", "false", "0"):
            await asyncio.to_thread(set_guild_persist_enabled, ctx.guild.id, False)
            await ctx.send("❌ Persistencia de colas **desactivada** para este servidor.")
        else:
            await ctx.send("⚠️ Opción no válida. Usa `on` o `off`.")

    @commands.command(name="q", aliases=["queue", "cola"])
    async def queueui(self, ctx) -> None:
        """Muestra la cola de reproducción interactiva con paginación y bordes protegidos."""
        core = self.bot.get_cog("MusicCore")
        if not core:
            await ctx.send("❌ No se encontró el módulo de música.")
            return

        player = core.get_player(ctx)
        if not player.current_song and not player.song_queue:
            await ctx.send("📭 La cola de canciones está vacía.")
            return

        pagination_view = QueuePaginationView(player, items_per_page=10)
        await ctx.send(
            embed=pagination_view.get_current_embed(),
            view=pagination_view,
            delete_after=300,
        )

    @commands.command(name="channel", aliases=["canal"])
    @commands.has_permissions(administrator=True)
    async def channel_config(self, ctx, *, arg: str = None) -> None:
        """Configura un único canal de texto para recibir comandos de música (Solo Admin)."""
        from sznUtils import load_config, save_config

        guild_id = ctx.guild.id
        config_key = f"cmd_channel_{guild_id}"

        if arg is None:
            current = load_config(config_key)
            if current:
                embed = discord.Embed(
                    title="⚙️ Configuración de Canal Exclusivo",
                    description=(
                        f"Los comandos están bloqueados al canal: <#{current}>.\n\n"
                        "Para desactivar esta restricción y permitir comandos en cualquier canal, escribe:\n"
                        "`td?channel reset`"
                    ),
                    color=UITheme.PRIMARY,
                )
            else:
                embed = discord.Embed(
                    title="⚙️ Configuración de Canal Exclusivo",
                    description=(
                        "El bot actualmente responde a comandos en **cualquier canal de texto**.\n\n"
                        "Para restringir los comandos a un único canal, escribe:\n"
                        "`td?channel #nombre-del-canal` o `td?channel aqui`"
                    ),
                    color=UITheme.PRIMARY,
                )
            await ctx.send(embed=embed)
            return

        arg_lower = arg.lower().strip()

        if arg_lower in ("reset", "off", "desactivar", "clear"):
            await asyncio.to_thread(save_config, config_key, "")
            embed = discord.Embed(
                title="⚙️ Configuración Actualizada",
                description="✅ Se ha desactivado la restricción de canal. El bot ahora responderá en **todos los canales de texto**.",
                color=UITheme.SPOTIFY,
            )
            await ctx.send(embed=embed)
            return

        if arg_lower in ("aqui", "aquí", "here", "this"):
            target_channel = ctx.channel
        else:
            target_channel = None
            match = re.search(r"\d+", arg)
            if match:
                try:
                    channel_id = int(match.group(0))
                    target_channel = ctx.guild.get_channel(channel_id)
                except ValueError:
                    target_channel = None

            if not target_channel:
                clean_name = arg.strip().lstrip("#").lower()
                target_channel = discord.utils.find(
                    lambda c: isinstance(c, discord.TextChannel) and c.name.lower() == clean_name,
                    ctx.guild.channels,
                )

        if not target_channel:
            await ctx.send("❌ No pude encontrar ese canal de texto. Menciónalo como `#nombre-canal` o escribe `td?channel aqui`.")
            return

        await asyncio.to_thread(save_config, config_key, str(target_channel.id))

        embed = discord.Embed(
            title="⚙️ Configuración Actualizada",
            description=(
                f"✅ Los comandos de música ahora están restringidos al canal {target_channel.mention}.\n\n"
                "Los comandos enviados en otros canales serán eliminados automáticamente y el bot los ignorará."
            ),
            color=UITheme.SPOTIFY,
        )
        await ctx.send(embed=embed)

    @channel_config.error
    async def channel_config_error(self, ctx, error) -> None:
        """Informa cuando un usuario sin permisos intenta ejecutar `td?channel`."""
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Necesitas permisos de **Administrador** para configurar el canal exclusivo.")

    @commands.command(name="settings", aliases=["config"])
    async def settings_dashboard(self, ctx) -> None:
        """Muestra el panel interactivo de configuración del servidor."""
        if not ctx.guild:
            await ctx.send("⚠️ El panel de ajustes de servidor solo está disponible dentro de un servidor.")
            return

        core = self.bot.get_cog("MusicCore")
        if not core:
            await ctx.send("❌ Módulo de música no encontrado.")
            return

        view = self.SettingsControls(core, self.bot, ctx.guild)
        await ctx.send(embed=view.get_embed(ctx.guild), view=view)

    async def _is_authorized_admin_or_trusted(self, ctx) -> bool:
        """Comprueba si el autor es Trusted, Dueño del Bot o Administrador del servidor."""
        from database import is_user_trusted
        if is_user_trusted(ctx.author.id):
            return True
        if await self.bot.is_owner(ctx.author):
            return True
        if ctx.guild and ctx.author.guild_permissions.administrator:
            return True
        return False

    @commands.command(name="trusted", aliases=["trust"])
    async def trusted_cmd(self, ctx, action: str = None, user_arg: str = None) -> None:
        """Administra los usuarios de confianza (Solo Dueño del Bot)."""
        if not await self.bot.is_owner(ctx.author):
            await ctx.send("❌ Solo el **Dueño del Bot** puede ver o gestionar la lista de usuarios Trusted.")
            return

        from database import add_trusted_user, get_trusted_users, remove_trusted_user

        if action and action.lower() in ("add", "agregar", "sumar"):
            if not user_arg:
                await ctx.send("⚠️ Uso: `td?trusted add @usuario_o_ID`")
                return
            match = re.search(r"\d+", user_arg)
            target_id = match.group(0) if match else user_arg.strip()
            target_user = self.bot.get_user(int(target_id)) if target_id.isdigit() else None
            uname = target_user.name if target_user else f"User_{target_id}"

            added = await asyncio.to_thread(add_trusted_user, target_id, uname)
            if added:
                await ctx.send(f"✅ Usuario **@{uname}** (`{target_id}`) añadido como **Trusted**.")
            else:
                await ctx.send(f"ℹ️ El usuario **@{uname}** ya estaba en la lista de Trusted.")
            return

        if action and action.lower() in ("remove", "del", "delete", "eliminar"):
            if not user_arg:
                await ctx.send("⚠️ Uso: `td?trusted remove @usuario_o_ID`")
                return
            match = re.search(r"\d+", user_arg)
            target_id = match.group(0) if match else user_arg.strip()

            removed = await asyncio.to_thread(remove_trusted_user, target_id)
            if removed:
                await ctx.send(f"🗑️ Usuario con ID `{target_id}` eliminado de la lista **Trusted**.")
            else:
                await ctx.send(f"⚠️ No se encontró al usuario con ID `{target_id}` en la lista Trusted.")
            return

        users = await asyncio.to_thread(get_trusted_users)
        embed = discord.Embed(
            title="🛡️ Usuarios de Confianza (Trusted Users)",
            description=f"Hay **{len(users)}** usuarios con acceso prioritario a comandos de Admin / Debug por DM.",
            color=UITheme.SPOTIFY,
        )
        if users:
            lines = [f"• **@{u['username']}** (`{u['user_id']}`)" for u in users]
            embed.add_field(name="📋 Lista de Trusted Users", value="\n".join(lines), inline=False)
        else:
            embed.add_field(
                name="ℹ️ Lista Vacía",
                value="Aún no hay usuarios de confianza registrados. Usa `td?trusted add @usuario`.",
                inline=False,
            )

        await ctx.send(embed=embed)

    @commands.command(name="logs", aliases=["log"])
    async def view_logs(self, ctx, lines: int = 20) -> None:
        """Muestra las últimas N líneas del archivo de logs del bot (Admin / Trusted / DM)."""
        if not await self._is_authorized_admin_or_trusted(ctx):
            await ctx.send("❌ Este comando requiere permisos de Administrador o estar en la lista Trusted.")
            return

        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        log_file = os.path.join(repo_root, "logs", "tooodles.log")

        if not os.path.exists(log_file):
            await ctx.send("📭 Aún no existe el archivo de logs.")
            return

        line_limit = max(1, min(lines, 50))
        try:
            with open(log_file, "r", encoding="utf-8") as file_handle:
                all_lines = file_handle.readlines()
                tail_lines = all_lines[-line_limit:] if len(all_lines) >= line_limit else all_lines

            content = "".join(tail_lines).strip()
            if not content:
                await ctx.send("📭 El archivo de logs está vacío.")
                return

            content = re.sub(r"\x1b\[[0-9;]*m", "", content)
            if len(content) > 1900:
                content = content[-1900:]

            embed = discord.Embed(
                title=f"📋 Últimas {len(tail_lines)} líneas de Logs",
                description=f"```text\n{content}\n```",
                color=UITheme.PRIMARY,
            )
            embed.set_footer(text=f"Solicitado por @{ctx.author.name}")
            await ctx.send(embed=embed)

        except Exception as err:
            await ctx.send(f"❌ Error al leer el archivo de logs: {err}")

    @commands.command(name="debug", aliases=["status", "botstatus", "health", "diag"])
    async def debug_status(self, ctx) -> None:
        """Muestra el estado de diagnóstico y telemetría del sistema (exclusivo vía DM para usuarios Trusted)."""
        if ctx.guild is not None:
            await ctx.send(
                "⚠️ El comando `status` / `debug` solo está disponible en Mensajes Directos (DM) para usuarios de confianza."
            )
            return

        if not await self._is_authorized_admin_or_trusted(ctx):
            await ctx.send("❌ Este comando requiere estar registrado en la lista de usuarios Trusted.")
            return

        try:
            total, used, free = shutil.disk_usage(tempfile.gettempdir())
            used_pct = (used / total) * 100
            disk_status = "🟢" if used_pct < 85 else ("⚠️" if used_pct < 95 else "🔴")
            disk_str = (
                f"{disk_status} `{used / (1024**3):.1f}GB / {total / (1024**3):.1f}GB ({used_pct:.1f}% usado)` "
                f"(Libre: `{free / (1024**3):.1f}GB`)"
            )
        except Exception as err:
            disk_str = f"⚠️ Error consultando disco: {err}"

        try:
            from database import engine
            from sqlalchemy import text
            with engine.connect() as conn:
                journal_mode = conn.execute(text("PRAGMA journal_mode;")).scalar()
                busy_timeout = conn.execute(text("PRAGMA busy_timeout;")).scalar()
            wal_str = f"🟢 **Modo WAL Activo** (`journal_mode={journal_mode}`, `busy_timeout={busy_timeout}ms`)"
        except Exception as err:
            wal_str = f"⚠️ Error consultando BBDD: {err}"

        music_cog = self.bot.get_cog("MusicCore") or self.bot.get_cog("MusicPlayerMixin")
        recsys_engine = getattr(music_cog, "recsys_engine", None)
        if recsys_engine:
            stats = recsys_engine.stats
            from recsys.train import ARTIFACTS_PATH
            if os.path.exists(ARTIFACTS_PATH):
                mtime = datetime.fromtimestamp(os.path.getmtime(ARTIFACTS_PATH)).strftime("%Y-%m-%d %H:%M:%S")
            else:
                mtime = "Sin entrenar en disco"

            recsys_str = (
                f"📊 **Canciones indexadas**: `{stats['n_songs']}`  •  **Usuarios**: `{stats['n_users']}`\n"
                f"⚙️ **Modelos**: ALS `{'✅' if stats['has_als'] else '❌'}` | Item2Vec `{'✅' if stats['has_item2vec'] else '❌'}`\n"
                f"⏱️ **Último entrenamiento**: `{mtime}`"
            )
        else:
            recsys_str = "❌ No disponible"

        try:
            temp_dir = tempfile.gettempdir()
            cache_files = glob.glob(os.path.join(temp_dir, "cache_*.webm")) + glob.glob(os.path.join(temp_dir, "*.tmp"))
            cache_size_bytes = sum(os.path.getsize(f) for f in cache_files if os.path.isfile(f))
            n_guilds = len(self.bot.guilds)
            n_vc = len(self.bot.voice_clients)

            sys_str = (
                f"🔊 **VCs Conectados**: `{n_vc}` de `{n_guilds}` servidores\n"
                f"🧹 **Archivos Caché /tmp**: `{len(cache_files)}` archivos (`{cache_size_bytes / (1024**2):.1f} MB`)\n"
                f"🐍 **Python**: `{sys.version.split()[0]}`  •  **discord.py**: `{discord.__version__}`"
            )
        except Exception as err:
            sys_str = f"⚠️ Error consultando sistema: {err}"

        embed = discord.Embed(
            title="📋 Tooodles — Ficha Técnica y Diagnóstico de Sistema",
            description="Información de salud del servidor, almacenamiento en disco, base de datos y modelo de recomendación ML.",
            color=UITheme.PRIMARY,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="💾 Espacio en Disco (/tmp)", value=disk_str, inline=False)
        embed.add_field(name="🗄️ Base de Datos (SQLite)", value=wal_str, inline=False)
        embed.add_field(name="🧠 Motor RecSys ML", value=recsys_str, inline=False)
        embed.add_field(name="🔊 Sistema y Caché", value=sys_str, inline=False)
        embed.set_footer(text=f"Solicitado vía DM Trusted  •  @{ctx.author.name}")

        await ctx.send(embed=embed)

    @commands.command(name="train", aliases=["recsys_train"])
    async def trigger_recsys_train(self, ctx) -> None:
        """Gatilla manualmente el reentrenamiento offline del RecSys (Admin / Trusted / DM)."""
        if not await self._is_authorized_admin_or_trusted(ctx):
            await ctx.send("❌ Este comando requiere permisos de Administrador o estar en la lista Trusted.")
            return

        msg = await ctx.send(
            "🧠 Iniciando entrenamiento offline del RecSys Híbrido (520 dims, 50 ALS iters, 100 Item2Vec epochs)..."
        )
        try:
            proc_result = await asyncio.to_thread(
                subprocess.run,
                [sys.executable, "-m", "recsys.train"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if proc_result.returncode == 0:
                music_cog = self.bot.get_cog("MusicCore")
                if music_cog and getattr(music_cog, "recsys_engine", None):
                    music_cog.recsys_engine.reload_if_updated()
                await msg.edit(content="✅ **Entrenamiento del RecSys completado y motor recargado exitosamente.**")
            else:
                await msg.edit(
                    content=f"⚠️ Entrenamiento finalizó con código {proc_result.returncode}:\n```text\n{proc_result.stderr[:500]}\n```"
                )
        except Exception as err:
            await ctx.send(f"❌ Error al ejecutar entrenamiento: {err}")

    @commands.command(name="help", aliases=["ayuda", "h"])
    async def help_cmd(self, ctx, category: str = None) -> None:
        """Muestra el centro de ayuda interactivo con selector desplegable por categorías."""
        is_dm = ctx.guild is None
        from sznUtils import load_config

        prefix = (load_config(f"prefix_{ctx.guild.id}") or "td?") if not is_dm else ""
        guild_name = ctx.guild.name if ctx.guild else None
        initial_category = category.lower().strip() if category else ("admin" if is_dm else "overview")

        embed = EmbedFactory.build_help_category_embed(
            category=initial_category,
            prefix=prefix or "td?",
            guild_name=guild_name,
            author_name=ctx.author.name,
        )
        view = HelpNavigatorView(
            prefix=prefix or "td?",
            guild_name=guild_name,
            author_name=ctx.author.name,
        )
        await ctx.send(embed=embed, view=view)

    @commands.command(name="playlists", aliases=["pl", "playlist"])
    async def playlists_cmd(self, ctx, action: str = None, *, args: str = None) -> None:
        """Muestra o administra las playlists guardadas del servidor."""
        if not ctx.guild:
            await ctx.send("⚠️ Este comando solo funciona en servidores.")
            return

        guild_id = ctx.guild.id
        from database import add_saved_playlist, get_saved_playlists, remove_saved_playlist
        from sznUtils import get_playlist_title

        if action and action.lower() in ("add", "agregar", "guardar"):
            if not args:
                await ctx.send("⚠️ Uso: `td?playlist add <URL> [Alias opcional]`")
                return

            parts = args.strip().split(" ", 1)
            url = parts[0]
            alias = parts[1] if len(parts) > 1 else None

            msg = await ctx.send("🔍 Obteniendo nombre oficial de la playlist...")
            official_title = await get_playlist_title(url)
            final_name = alias if alias else official_title

            await asyncio.to_thread(add_saved_playlist, guild_id, ctx.author.id, final_name, url)
            await msg.edit(content=f"✅ Playlist **{final_name}** guardada correctamente.")
            return

        if action and action.lower() in ("remove", "del", "delete", "eliminar"):
            if not args:
                await ctx.send("⚠️ Uso: `td?playlist remove <Nombre o Alias>`")
                return
            deleted = await asyncio.to_thread(remove_saved_playlist, guild_id, args)
            if deleted:
                await ctx.send(f"🗑️ Playlist **{args}** eliminada de la colección.")
            else:
                await ctx.send(f"⚠️ No se encontró la playlist **{args}**.")
            return

        playlists = await asyncio.to_thread(get_saved_playlists, guild_id)
        embed = EmbedFactory.build_playlists_embed(playlists, mode="play")
        view = PlaylistsView(guild_id, self.bot)
        await ctx.send(embed=embed, view=view)


async def setup(bot) -> None:
    """Registra el Cog MusicUI en la instancia del bot."""
    await bot.add_cog(MusicUI(bot))


__all__ = [
    "MusicUI",
    "UITheme",
    "EmbedFactory",
    "MusicControls",
    "SettingsControls",
    "QueuePaginationView",
    "HelpNavigatorView",
    "PlaylistsView",
    "PrefixModal",
    "PersistApprovalView",
    "AddPlaylistModal",
    "EditPlaylistModal",
    "PlaylistSelect",
    "EditPlaylistSelect",
    "DeletePlaylistSelect",
    "HelpCategorySelect",
    "format_duration",
    "render_progress_bar",
    "setup",
]
