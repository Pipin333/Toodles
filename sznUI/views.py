"""Componentes interactivos de Discord (Views, Buttons, Selects y Modals) para Tooodles."""

import asyncio
import random

import discord
from discord.ui import Button, Modal, Select, TextInput, View

from sznLogger import get_logger
from .embeds import EmbedFactory
from .theme import UITheme

logger = get_logger("ui.views")


class PrefixModal(Modal, title="Configurar Prefijo del Bot"):
    """Modal para cambiar el prefijo de comandos de un servidor."""

    prefix_input = TextInput(
        label="Nuevo Prefijo (Máx. 5 caracteres)",
        placeholder="ej: !, $, td?, bot-",
        min_length=1,
        max_length=5,
        required=True,
    )

    def __init__(self, settings_view: "SettingsControls") -> None:
        super().__init__()
        self.settings_view = settings_view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Guarda el nuevo prefijo y actualiza el panel de ajustes."""
        new_prefix = self.prefix_input.value.strip()
        guild_id = interaction.guild.id

        from sznUtils import save_config
        await asyncio.to_thread(save_config, f"prefix_{guild_id}", new_prefix)

        self.settings_view.guild = interaction.guild
        self.settings_view.update_buttons()
        await interaction.response.edit_message(
            embed=self.settings_view.get_embed(interaction.guild),
            view=self.settings_view,
        )
        await interaction.followup.send(
            f"✅ El prefijo del bot ha sido cambiado a `{new_prefix}` para este servidor.",
            ephemeral=True,
        )


class PersistApprovalView(View):
    """Vista enviada por DM al dueño del bot para autorizar o rechazar la persistencia de un servidor."""

    def __init__(self, bot, guild, requester_target) -> None:
        super().__init__(timeout=86400)
        self.bot = bot
        self.guild = guild
        self.requester_target = requester_target

    @discord.ui.button(label="✅ Autorizar", style=discord.ButtonStyle.success, custom_id="approve_persist")
    async def approve(self, interaction: discord.Interaction, button: Button) -> None:
        """Aprueba la persistencia de colas para el servidor solicitante."""
        from sznUtils import set_guild_persist_enabled
        await asyncio.to_thread(set_guild_persist_enabled, self.guild.id, True)

        for item in self.children:
            item.disabled = True

        embed = interaction.message.embeds[0]
        embed.title = "✅ Solicitud de Persistencia AUTORIZADA"
        embed.color = discord.Color(UITheme.SPOTIFY)
        embed.set_footer(text=f"Aprobada por @{interaction.user.name}")
        await interaction.response.edit_message(embed=embed, view=self)

        if self.requester_target and hasattr(self.requester_target, "send"):
            try:
                await self.requester_target.send(
                    f"🎉 ¡El dueño del bot ha **autorizado** la persistencia de colas para el servidor **{self.guild.name}**!"
                )
            except Exception as err:
                logger.debug(f"No se pudo notificar aprobación al canal origen: {err}")

    @discord.ui.button(label="❌ Rechazar", style=discord.ButtonStyle.danger, custom_id="deny_persist")
    async def deny(self, interaction: discord.Interaction, button: Button) -> None:
        """Rechaza la persistencia de colas para el servidor solicitante."""
        from sznUtils import set_guild_persist_enabled
        await asyncio.to_thread(set_guild_persist_enabled, self.guild.id, False)

        for item in self.children:
            item.disabled = True

        embed = interaction.message.embeds[0]
        embed.title = "❌ Solicitud de Persistencia RECHAZADA"
        embed.color = discord.Color(UITheme.DANGER)
        embed.set_footer(text=f"Rechazada por @{interaction.user.name}")
        await interaction.response.edit_message(embed=embed, view=self)

        if self.requester_target and hasattr(self.requester_target, "send"):
            try:
                await self.requester_target.send(
                    f"❌ La solicitud de persistencia de colas para el servidor **{self.guild.name}** fue rechazada por el dueño del bot."
                )
            except Exception as err:
                logger.debug(f"No se pudo notificar rechazo al canal origen: {err}")


class QueuePaginationView(View):
    """Vista interactiva paginada para inspeccionar la cola de reproducción."""

    def __init__(self, player, items_per_page: int = 10) -> None:
        super().__init__(timeout=300)
        self.player = player
        self.items_per_page = items_per_page
        self.current_page = 0
        self.total_pages = max(1, (len(getattr(player, "song_queue", [])) + items_per_page - 1) // items_per_page)
        self._sync_boundary_buttons()

    def _sync_boundary_buttons(self) -> None:
        """Habilita o deshabilita los botones de navegación según la página actual."""
        total_songs = len(getattr(self.player, "song_queue", []))
        self.total_pages = max(1, (total_songs + self.items_per_page - 1) // self.items_per_page)
        self.current_page = max(0, min(self.current_page, self.total_pages - 1))

        at_start = self.current_page <= 0
        at_end = self.current_page >= (self.total_pages - 1)

        for child in self.children:
            cid = getattr(child, "custom_id", None)
            if cid in ("q_first", "q_prev"):
                child.disabled = at_start
            elif cid in ("q_next", "q_last"):
                child.disabled = at_end

    def get_current_embed(self) -> discord.Embed:
        """Devuelve el embed correspondiente a la página activa."""
        embed, total_pages = EmbedFactory.build_queue_page_embed(
            self.player,
            page=self.current_page,
            items_per_page=self.items_per_page,
        )
        self.total_pages = total_pages
        self._sync_boundary_buttons()
        return embed

    @discord.ui.button(label="⏮️ Primera", style=discord.ButtonStyle.secondary, custom_id="q_first")
    async def first(self, interaction: discord.Interaction, button: Button) -> None:
        """Salta a la primera página de la cola."""
        self.current_page = 0
        embed = self.get_current_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="⬅️ Anterior", style=discord.ButtonStyle.secondary, custom_id="q_prev")
    async def prev(self, interaction: discord.Interaction, button: Button) -> None:
        """Retrocede una página en la cola."""
        if self.current_page > 0:
            self.current_page -= 1
        embed = self.get_current_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="➡️ Siguiente", style=discord.ButtonStyle.secondary, custom_id="q_next")
    async def next(self, interaction: discord.Interaction, button: Button) -> None:
        """Avanza una página en la cola."""
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
        embed = self.get_current_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="⏭️ Última", style=discord.ButtonStyle.secondary, custom_id="q_last")
    async def last(self, interaction: discord.Interaction, button: Button) -> None:
        """Salta a la última página de la cola."""
        self.current_page = max(0, self.total_pages - 1)
        embed = self.get_current_embed()
        await interaction.response.edit_message(embed=embed, view=self)


class MusicControls(View):
    """Panel interactivo de 2 filas para el control en tiempo real del reproductor."""

    def __init__(self, core, ctx) -> None:
        super().__init__(timeout=300)
        self.core = core
        self.ctx = ctx
        self.update_toggle_buttons()

    def get_player(self):
        """Obtiene la instancia de GuildPlayer asociada al contexto actual."""
        return self.core.get_player(self.ctx)

    def _get_vc_name(self) -> str:
        """Obtiene el nombre legible del canal de voz conectado."""
        player = self.get_player()
        vc = getattr(player, "voice_client", None)
        if vc and getattr(vc, "channel", None) and getattr(vc.channel, "name", None):
            return vc.channel.name
        if getattr(self.ctx, "author", None) and getattr(self.ctx.author, "voice", None) and self.ctx.author.voice.channel:
            return self.ctx.author.voice.channel.name
        return "Canal de voz"

    def update_toggle_buttons(self) -> None:
        """Sincroniza las etiquetas y estilos de los botones de Pausa y Autoplay según el estado real."""
        player = self.get_player()
        vc = getattr(player, "voice_client", None)
        is_paused = bool(vc and hasattr(vc, "is_paused") and vc.is_paused())

        for child in self.children:
            cid = getattr(child, "custom_id", None)
            if cid == "pause_resume":
                if is_paused:
                    child.style = discord.ButtonStyle.success
                    child.label = "▶️ Reanudar"
                else:
                    child.style = discord.ButtonStyle.primary
                    child.label = "⏸️ Pausar"
            elif cid == "toggle_autoplay":
                if getattr(player, "autoplay_mode", False):
                    child.style = discord.ButtonStyle.success
                    child.label = "🤖 Autoplay: On"
                else:
                    child.style = discord.ButtonStyle.secondary
                    child.label = "🤖 Autoplay: Off"

    def update_radio_button(self) -> None:
        """Alias de compatibilidad para sincronizar botones de estado."""
        self.update_toggle_buttons()

    @discord.ui.button(label="⏸️ Pausar", style=discord.ButtonStyle.primary, custom_id="pause_resume", row=0)
    async def pause_resume(self, interaction: discord.Interaction, button: Button) -> None:
        """Alterna entre pausa y reproducción actualizando visualmente el panel para todo el canal."""
        player = self.get_player()
        if not player.voice_client or not player.current_song:
            await interaction.response.send_message("⚠️ No hay nada reproduciéndose.", ephemeral=True)
            return

        if player.voice_client.is_playing():
            player.voice_client.pause()
            status_notice = f"⏸️ Reproducción pausada por @{interaction.user.name}."
        elif player.voice_client.is_paused():
            player.voice_client.resume()
            status_notice = f"▶️ Reproducción reanudada por @{interaction.user.name}."
        else:
            await interaction.response.send_message("⚠️ No hay reproducción activa.", ephemeral=True)
            return

        self.update_toggle_buttons()
        updated_embed = EmbedFactory.build_now_playing_embed(
            player.current_song,
            player,
            vc_name=self._get_vc_name(),
        )
        await interaction.response.edit_message(embed=updated_embed, view=self)
        await interaction.followup.send(status_notice, ephemeral=True)

    @discord.ui.button(label="⏭️ Saltar", style=discord.ButtonStyle.secondary, custom_id="skip", row=0)
    async def skip(self, interaction: discord.Interaction, button: Button) -> None:
        """Salta la canción actual."""
        player = self.get_player()
        if not player.voice_client:
            await interaction.response.send_message("⚠️ No hay ninguna reproducción activa.", ephemeral=True)
            return

        if player.voice_client.is_playing() or player.voice_client.is_paused():
            player.current_song_skipped = True
            player.voice_client.stop()
            await interaction.response.send_message("⏭️ Canción saltada.", ephemeral=True)
        else:
            await interaction.response.send_message("🎵 La cola está vacía.", ephemeral=True)

    @discord.ui.button(label="🔀 Shuffle", style=discord.ButtonStyle.secondary, custom_id="shuffle_queue", row=0)
    async def shuffle_queue(self, interaction: discord.Interaction, button: Button) -> None:
        """Mezcla aleatoriamente la cola y reprograma la precarga N+1."""
        player = self.get_player()
        if not player.song_queue:
            await interaction.response.send_message("⚠️ La cola está vacía, no hay nada que mezclar.", ephemeral=True)
            return
        random.shuffle(player.song_queue)
        self.core.schedule_queue_optimizations(self.ctx)
        await interaction.response.send_message(
            f"🔀 Cola mezclada aleatoriamente ({len(player.song_queue)} canciones).",
            ephemeral=True,
        )

    @discord.ui.button(label="📋 Cola", style=discord.ButtonStyle.secondary, custom_id="show_queue", row=0)
    async def show_queue(self, interaction: discord.Interaction, button: Button) -> None:
        """Despliega el visor interactivo paginado de la cola de reproducción."""
        player = self.get_player()
        if not player.current_song and not player.song_queue:
            await interaction.response.send_message("📭 La cola está vacía.", ephemeral=True)
            return

        pagination_view = QueuePaginationView(player, items_per_page=10)
        await interaction.response.send_message(
            embed=pagination_view.get_current_embed(),
            view=pagination_view,
            ephemeral=True,
        )

    @discord.ui.button(label="❤️ Like", style=discord.ButtonStyle.secondary, custom_id="like_song", row=1)
    async def like_song_button(self, interaction: discord.Interaction, button: Button) -> None:
        """Alterna el estado de Me Gusta de la canción actual para el usuario que interactúa."""
        player = self.get_player()
        if not player.current_song or not player.current_song.get("title"):
            await interaction.response.send_message("⚠️ No hay ninguna canción en reproducción.", ephemeral=True)
            return

        song_title = player.current_song["title"]
        user_id = str(interaction.user.id)

        from database import toggle_like_song
        status = await asyncio.to_thread(toggle_like_song, user_id, song_title)
        if status == "removed":
            await interaction.response.send_message(f"❌ Eliminaste de tus favoritas: **{song_title}**", ephemeral=True)
        elif status == "added":
            await interaction.response.send_message(f"❤️ Guardaste en tus favoritas: **{song_title}**", ephemeral=True)
        else:
            await interaction.response.send_message(f"❤️ Registrado me gusta para: **{song_title}**", ephemeral=True)

    @discord.ui.button(label="👎 Dislike", style=discord.ButtonStyle.secondary, custom_id="dislike_song", row=1)
    async def dislike_song_button(self, interaction: discord.Interaction, button: Button) -> None:
        """Registra o elimina un Dislike en el motor RecSys sin interrumpir la canción actual."""
        player = self.get_player()
        if not player.current_song or not player.current_song.get("title"):
            await interaction.response.send_message("⚠️ No hay ninguna canción en reproducción.", ephemeral=True)
            return

        song_title = player.current_song["title"]
        user_id = str(interaction.user.id)

        from database import log_dislike_event, remove_dislike
        added = await asyncio.to_thread(log_dislike_event, user_id, song_title)
        if added:
            await interaction.response.send_message(f"👎 Marcaste como no gustada: **{song_title}**", ephemeral=True)
        else:
            await asyncio.to_thread(remove_dislike, user_id, song_title)
            await interaction.response.send_message(
                f"✅ Eliminaste la marca de no gustada: **{song_title}**",
                ephemeral=True,
            )

    @discord.ui.button(label="🤖 Autoplay", style=discord.ButtonStyle.secondary, custom_id="toggle_autoplay", row=1)
    async def toggle_autoplay(self, interaction: discord.Interaction, button: Button) -> None:
        """Activa o desactiva el modo Autoplay impulsado por el modelo híbrido RecSys."""
        player = self.get_player()
        player.autoplay_mode = not getattr(player, "autoplay_mode", False)
        self.update_toggle_buttons()
        status = "activado" if player.autoplay_mode else "desactivado"

        updated_embed = (
            EmbedFactory.build_now_playing_embed(player.current_song, player, vc_name=self._get_vc_name())
            if player.current_song
            else None
        )
        await interaction.response.edit_message(embed=updated_embed, view=self)

        if player.autoplay_mode and not player.song_queue and not (player.voice_client and player.voice_client.is_playing()):
            await self.core._fill_queue_from_recsys(self.ctx, player)
            if player.song_queue and player.voice_client and not player.voice_client.is_playing():
                await self.core.play_next(self.ctx)

        await interaction.followup.send(f"🤖 Autoplay ML **{status}**.", ephemeral=True)

    @discord.ui.button(label="⏹️ Detener", style=discord.ButtonStyle.danger, custom_id="stop", row=1)
    async def stop(self, interaction: discord.Interaction, button: Button) -> None:
        """Guarda la cola si la persistencia está activa, limpia la caché del servidor y desconecta el bot."""
        player = self.get_player()
        if player.voice_client:
            guild_id = interaction.guild.id if interaction.guild else (self.ctx.guild.id if getattr(self.ctx, "guild", None) else 0)
            if guild_id:
                from sznUtils import is_guild_persist_enabled
                if is_guild_persist_enabled(guild_id):
                    from database import save_guild_queue
                    tracks_to_save = []
                    if player.current_song:
                        tracks_to_save.append(player.current_song)
                    if player.song_queue:
                        tracks_to_save.extend(player.song_queue)
                    if tracks_to_save:
                        vc_id = player.voice_client.channel.id if player.voice_client.channel else None
                        tc_id = interaction.channel.id if interaction.channel else None
                        await asyncio.to_thread(save_guild_queue, guild_id, tracks_to_save, vc_id, tc_id)

            from sznMusic.player import cleanup_guild_player_cache
            cleanup_guild_player_cache(player)
            player.song_queue.clear()
            player.radio_mode = False
            player.autoplay_mode = False
            if player.voice_client:
                player.voice_client.stop()
                await player.voice_client.disconnect()
                player.voice_client = None
            player.current_song = None
            await interaction.response.send_message(
                "⏹️ Reproducción detenida y bot desconectado del canal.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message("⚠️ El bot no está conectado a ningún canal.", ephemeral=True)


class SettingsControls(View):
    """Panel interactivo de configuración del servidor (Prefijo, Canal, Radio Default y Persistencia)."""

    def __init__(self, core, bot, guild=None) -> None:
        super().__init__(timeout=300)
        self.core = core
        self.bot = bot
        self.guild = guild
        self.update_buttons()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Verifica que solo Administradores o el Dueño del Bot modifiquen los ajustes."""
        is_admin = bool(interaction.user.guild_permissions.administrator)
        is_owner = await self.bot.is_owner(interaction.user)
        if not (is_admin or is_owner):
            await interaction.response.send_message(
                "❌ Solo los **Administradores** pueden modificar la configuración del servidor.",
                ephemeral=True,
            )
            return False
        return True

    def get_embed(self, guild) -> discord.Embed:
        """Construye el embed de ajustes para el servidor indicado."""
        return EmbedFactory.build_settings_embed(guild, self.core)

    def update_buttons(self) -> None:
        """Actualiza etiquetas y colores de los botones según la configuración guardada del servidor."""
        from sznUtils import is_guild_persist_enabled, load_config

        guild_id = self.guild.id if self.guild else (self.core.bot.guilds[0].id if self.core.bot.guilds else 0)

        for child in self.children:
            cid = getattr(child, "custom_id", None)
            if cid == "toggle_channel":
                cmd_channel = load_config(f"cmd_channel_{guild_id}")
                if cmd_channel:
                    child.style = discord.ButtonStyle.danger
                    child.label = "🔓 Liberar Canal"
                else:
                    child.style = discord.ButtonStyle.primary
                    child.label = "🔒 Fijar Canal Aquí"

            elif cid == "toggle_default_radio":
                default_radio = load_config(f"default_radio_{guild_id}")
                if default_radio == "on":
                    child.style = discord.ButtonStyle.success
                    child.label = "📻 Radio Default: On"
                else:
                    child.style = discord.ButtonStyle.secondary
                    child.label = "📻 Radio Default: Off"

            elif cid == "toggle_persist":
                persist_on = is_guild_persist_enabled(guild_id)
                if persist_on:
                    child.style = discord.ButtonStyle.success
                    child.label = "💾 Persistencia: On"
                else:
                    child.style = discord.ButtonStyle.secondary
                    child.label = "💾 Persistencia: Off"

            elif cid == "change_prefix_btn":
                prefix = load_config(f"prefix_{guild_id}") or "td?"
                child.label = f"✏️ Prefijo: {prefix}"

    @discord.ui.button(label="🔒 Fijar Canal Aquí", style=discord.ButtonStyle.primary, custom_id="toggle_channel", row=0)
    async def toggle_channel(self, interaction: discord.Interaction, button: Button) -> None:
        """Fija o libera el canal de texto exclusivo para comandos de música."""
        from sznUtils import load_config, save_config

        self.guild = interaction.guild
        guild_id = interaction.guild.id
        config_key = f"cmd_channel_{guild_id}"

        current_channel = load_config(config_key)
        if current_channel:
            await asyncio.to_thread(save_config, config_key, "")
            confirm_msg = "🔓 Se ha desactivado la restricción de canal. El bot responderá en cualquier canal."
        else:
            await asyncio.to_thread(save_config, config_key, str(interaction.channel.id))
            confirm_msg = f"🔒 Canal exclusivo fijado a <#{interaction.channel.id}>."

        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(interaction.guild), view=self)
        await interaction.followup.send(confirm_msg, ephemeral=True)

    @discord.ui.button(label="📻 Radio Default: Off", style=discord.ButtonStyle.secondary, custom_id="toggle_default_radio", row=0)
    async def toggle_default_radio(self, interaction: discord.Interaction, button: Button) -> None:
        """Activa o desactiva el inicio automático del modo Radio al conectar al canal de voz."""
        from sznUtils import load_config, save_config

        self.guild = interaction.guild
        guild_id = interaction.guild.id
        config_key = f"default_radio_{guild_id}"

        current_default = load_config(config_key)
        if current_default == "on":
            await asyncio.to_thread(save_config, config_key, "off")
            confirm_msg = "📻 Radio automática por defecto desactivada."
        else:
            await asyncio.to_thread(save_config, config_key, "on")
            confirm_msg = "📻 Radio automática por defecto activada al conectar."

        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(interaction.guild), view=self)
        await interaction.followup.send(confirm_msg, ephemeral=True)

    @discord.ui.button(label="💾 Persistencia: Off", style=discord.ButtonStyle.secondary, custom_id="toggle_persist", row=1)
    async def toggle_persist(self, interaction: discord.Interaction, button: Button) -> None:
        """Alterna o solicita al dueño la activación de persistencia de colas desde el panel de ajustes."""
        from sznUtils import is_guild_persist_enabled, set_guild_persist_enabled

        self.guild = interaction.guild
        guild_id = interaction.guild.id
        currently_enabled = is_guild_persist_enabled(guild_id)
        is_owner = await self.bot.is_owner(interaction.user)

        if currently_enabled:
            await asyncio.to_thread(set_guild_persist_enabled, guild_id, False)
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(interaction.guild), view=self)
            await interaction.followup.send("❌ Persistencia de colas **desactivada** para este servidor.", ephemeral=True)
            return

        if is_owner:
            await asyncio.to_thread(set_guild_persist_enabled, guild_id, True)
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(interaction.guild), view=self)
            await interaction.followup.send("✅ Persistencia de colas **activada** directamente.", ephemeral=True)
            return

        try:
            app_info = await self.bot.application_info()
            owner = app_info.owner
            req_embed = discord.Embed(
                title="📩 Solicitud de Persistencia de Colas",
                description=f"El administrador **@{interaction.user.name}** solicita activar la persistencia de colas.",
                color=UITheme.WARNING,
            )
            req_embed.add_field(name="🏰 Servidor", value=f"`{interaction.guild.name}` (`{guild_id}`)", inline=True)
            req_embed.add_field(name="👤 Solicitante", value=f"@{interaction.user.name} (`{interaction.user.id}`)", inline=True)
            req_embed.set_footer(text="Usa los botones para autorizar o rechazar esta solicitud.")

            approval_view = PersistApprovalView(self.bot, interaction.guild, interaction.channel)
            await owner.send(embed=req_embed, view=approval_view)
            await interaction.response.send_message(
                "📩 **Solicitud enviada**: Se notificó al dueño del bot para autorizar la persistencia en este servidor.",
                ephemeral=True,
            )
        except Exception as err:
            logger.warning(f"⚠️ Error al enviar solicitud de persistencia por DM: {err}")
            await interaction.response.send_message(
                "⚠️ No se pudo enviar la solicitud al dueño del bot. Intenta más tarde.",
                ephemeral=True,
            )

    @discord.ui.button(label="✏️ Prefijo: td?", style=discord.ButtonStyle.secondary, custom_id="change_prefix_btn", row=1)
    async def change_prefix_btn(self, interaction: discord.Interaction, button: Button) -> None:
        """Abre el modal para configurar el prefijo personalizado del servidor."""
        await interaction.response.send_modal(PrefixModal(self))


class HelpCategorySelect(Select):
    """Selector desplegable para navegar entre las categorías de ayuda del bot."""

    def __init__(self, prefix: str, guild_name: str | None, author_name: str) -> None:
        self.prefix = prefix
        self.guild_name = guild_name
        self.author_name = author_name
        options = [
            discord.SelectOption(
                label="Resumen General",
                value="overview",
                description="Inicio rápido y comandos esenciales",
                emoji="🚀",
            ),
            discord.SelectOption(
                label="Reproducción y Cola",
                value="music",
                description="Play, skip, pausa, cola interactiva, shuffle y move",
                emoji="🎧",
            ),
            discord.SelectOption(
                label="Recomendador IA, Radio y Favoritos",
                value="recsys",
                description="Autoplay ML, Radio Spotify, FavRadio, Likes y Top",
                emoji="📻",
            ),
            discord.SelectOption(
                label="Playlists y Precarga ML",
                value="playlists",
                description="Colección de playlists del servidor y preload masivo",
                emoji="📚",
            ),
            discord.SelectOption(
                label="Configuración y Diagnóstico",
                value="admin",
                description="Panel settings, canal exclusivo, persistencia y DM debug",
                emoji="⚙️",
            ),
        ]
        super().__init__(
            placeholder="🔍 Explora los comandos por categoría...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="help_category_select",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        """Actualiza el embed de ayuda con la categoría elegida."""
        chosen_category = self.values[0]
        embed = EmbedFactory.build_help_category_embed(
            category=chosen_category,
            prefix=self.prefix,
            guild_name=self.guild_name,
            author_name=self.author_name,
        )
        await interaction.response.edit_message(embed=embed, view=self.view)


class HelpNavigatorView(View):
    """Vista contenedora del menú interactivo de ayuda por categorías."""

    def __init__(self, prefix: str = "td?", guild_name: str | None = None, author_name: str = "Usuario") -> None:
        super().__init__(timeout=300)
        self.add_item(HelpCategorySelect(prefix=prefix, guild_name=guild_name, author_name=author_name))


class AddPlaylistModal(Modal, title="➕ Guardar Nueva Playlist"):
    """Modal para registrar una nueva playlist en la colección del servidor."""

    url_input = TextInput(
        label="Link de YouTube o Spotify",
        placeholder="https://www.youtube.com/playlist?list=... o Spotify URL",
        min_length=10,
        max_length=300,
        required=True,
    )
    alias_input = TextInput(
        label="Alias Opcional (ej: Cumbia 90s, Mambo)",
        placeholder="Déjalo vacío para usar el nombre oficial automático",
        min_length=0,
        max_length=40,
        required=False,
    )

    def __init__(self, parent_view: "PlaylistsView | None" = None) -> None:
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Extrae el título oficial si no se indicó alias y persiste la playlist."""
        await interaction.response.defer(ephemeral=True)
        url = self.url_input.value.strip()
        alias = self.alias_input.value.strip() if self.alias_input.value else None

        from database import add_saved_playlist
        from sznUtils import get_playlist_title

        official_title = await get_playlist_title(url)
        final_name = alias if alias else official_title
        await asyncio.to_thread(add_saved_playlist, interaction.guild.id, interaction.user.id, final_name, url)

        await interaction.followup.send(
            f"✅ Playlist **{final_name}** guardada correctamente.",
            ephemeral=True,
        )
        if self.parent_view:
            await self.parent_view.refresh(interaction)


class PlaylistSelect(Select):
    """Selector desplegable para lanzar inmediatamente una playlist guardada."""

    def __init__(self, playlists: list[dict]) -> None:
        options = [
            discord.SelectOption(
                label=pl["name"][:100],
                value=pl["url"],
                description=f"Link: {pl['url'][:45]}...",
                emoji="🎵",
            )
            for pl in playlists[:25]
        ]
        super().__init__(
            placeholder="🔍 Selecciona una playlist para reproducir...",
            min_values=1,
            max_values=1,
            options=options if options else [discord.SelectOption(label="Sin playlists guardadas", value="none")],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        """Inicia la reproducción de la playlist seleccionada en el canal de voz del usuario."""
        if self.values[0] == "none":
            await interaction.response.send_message("⚠️ No hay playlists guardadas en este servidor.", ephemeral=True)
            return

        selected_url = self.values[0]
        await interaction.response.send_message(f"🚀 Reproduciendo playlist seleccionada: {selected_url}", ephemeral=True)

        try:
            music_cog = interaction.client.get_cog("MusicCore") or interaction.client.get_cog("Music")
            if music_cog:
                ctx = await interaction.client.get_context(interaction.message)
                ctx.author = interaction.user
                await music_cog.play(ctx, query=selected_url)
            else:
                logger.warning("⚠️ [PLAYLIST SELECT] MusicCore cog no encontrado.")
        except Exception as err:
            logger.error(f"❌ [PLAYLIST SELECT ERROR] {err}")


class EditPlaylistModal(Modal, title="✏️ Editar Playlist Guardada"):
    """Modal con campos pre-llenados para actualizar el nombre o URL de una playlist."""

    def __init__(self, old_name: str, current_url: str, parent_view: "PlaylistsView | None" = None) -> None:
        super().__init__()
        self.old_name = old_name
        self.parent_view = parent_view

        self.name_input = TextInput(
            label="Nombre / Alias de la Playlist",
            default=old_name,
            min_length=1,
            max_length=100,
            required=True,
        )
        self.url_input = TextInput(
            label="URL de YouTube o Spotify",
            default=current_url,
            min_length=10,
            max_length=300,
            required=True,
        )
        self.add_item(self.name_input)
        self.add_item(self.url_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Actualiza el registro de la playlist en la base de datos y refresca la vista."""
        await interaction.response.defer(ephemeral=True)
        new_name = self.name_input.value.strip()
        new_url = self.url_input.value.strip()

        from database import add_saved_playlist, remove_saved_playlist
        await asyncio.to_thread(remove_saved_playlist, interaction.guild.id, self.old_name)
        await asyncio.to_thread(add_saved_playlist, interaction.guild.id, interaction.user.id, new_name, new_url)

        await interaction.followup.send(f"✏️ Playlist **{new_name}** actualizada correctamente.", ephemeral=True)
        if self.parent_view:
            self.parent_view.mode = "play"
            await self.parent_view.refresh(interaction)


class EditPlaylistSelect(Select):
    """Selector desplegable para elegir qué playlist editar."""

    def __init__(self, playlists: list[dict], parent_view: "PlaylistsView | None" = None) -> None:
        self.parent_view = parent_view
        self.playlists_map = {pl["name"]: pl["url"] for pl in playlists[:25]}
        options = [
            discord.SelectOption(
                label=pl["name"][:100],
                value=pl["name"],
                description=f"Editar: {pl['url'][:40]}...",
                emoji="✏️",
            )
            for pl in playlists[:25]
        ]
        super().__init__(
            placeholder="✏️ Selecciona la playlist que deseas editar...",
            min_values=1,
            max_values=1,
            options=options if options else [discord.SelectOption(label="Sin playlists guardadas", value="none")],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        """Abre el modal de edición para la playlist seleccionada."""
        if self.values[0] == "none":
            await interaction.response.send_message("⚠️ No hay playlists guardadas para editar.", ephemeral=True)
            return

        target_name = self.values[0]
        current_url = self.playlists_map.get(target_name, "")
        modal = EditPlaylistModal(old_name=target_name, current_url=current_url, parent_view=self.parent_view)
        await interaction.response.send_modal(modal)


class DeletePlaylistSelect(Select):
    """Selector desplegable para eliminar una playlist guardada del servidor."""

    def __init__(self, playlists: list[dict], parent_view: "PlaylistsView | None" = None) -> None:
        self.parent_view = parent_view
        options = [
            discord.SelectOption(
                label=pl["name"][:100],
                value=pl["name"],
                description=f"Eliminar: {pl['url'][:40]}...",
                emoji="🗑️",
            )
            for pl in playlists[:25]
        ]
        super().__init__(
            placeholder="🗑️ Selecciona la playlist que deseas eliminar...",
            min_values=1,
            max_values=1,
            options=options if options else [discord.SelectOption(label="Sin playlists guardadas", value="none")],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        """Elimina la playlist elegida de la base de datos y refresca la vista."""
        if self.values[0] == "none":
            await interaction.response.send_message("⚠️ No hay playlists guardadas para eliminar.", ephemeral=True)
            return

        target_name = self.values[0]
        from database import remove_saved_playlist
        deleted = await asyncio.to_thread(remove_saved_playlist, interaction.guild.id, target_name)
        if deleted:
            await interaction.response.send_message(
                f"🗑️ Playlist **{target_name}** eliminada de la colección.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f"⚠️ No se pudo eliminar la playlist **{target_name}**.",
                ephemeral=True,
            )

        if self.parent_view:
            await self.parent_view.refresh(interaction)


class PlaylistsView(View):
    """Vista interactiva multimodal (Reproducir / Editar / Eliminar) para playlists del servidor."""

    def __init__(self, guild_id: int, bot) -> None:
        super().__init__(timeout=180)
        self.guild_id = guild_id
        self.bot = bot
        self.mode = "play"
        self.update_components()

    def update_components(self) -> None:
        """Reconstruye los selectores y botones de acción según el modo activo."""
        self.clear_items()
        from database import get_saved_playlists
        playlists = get_saved_playlists(self.guild_id)
        if playlists:
            if self.mode == "delete":
                self.add_item(DeletePlaylistSelect(playlists, parent_view=self))
            elif self.mode == "edit":
                self.add_item(EditPlaylistSelect(playlists, parent_view=self))
            else:
                self.add_item(PlaylistSelect(playlists))

        btn_add = Button(label="➕ Agregar", style=discord.ButtonStyle.success)
        btn_add.callback = self.on_add_click
        self.add_item(btn_add)

        if self.mode == "edit":
            btn_edit = Button(label="◀️ Reproducir", style=discord.ButtonStyle.primary)
        else:
            btn_edit = Button(label="✏️ Editar", style=discord.ButtonStyle.secondary)
        btn_edit.callback = self.on_toggle_edit_mode
        self.add_item(btn_edit)

        if self.mode == "delete":
            btn_del = Button(label="◀️ Reproducir", style=discord.ButtonStyle.primary)
        else:
            btn_del = Button(label="🗑️ Eliminar", style=discord.ButtonStyle.danger)
        btn_del.callback = self.on_toggle_delete_mode
        self.add_item(btn_del)

    async def on_add_click(self, interaction: discord.Interaction) -> None:
        """Abre el modal para agregar una nueva playlist."""
        await interaction.response.send_modal(AddPlaylistModal(parent_view=self))

    async def on_toggle_edit_mode(self, interaction: discord.Interaction) -> None:
        """Alterna entre el modo de edición y el modo de reproducción."""
        self.mode = "play" if self.mode == "edit" else "edit"
        await self.refresh(interaction)

    async def on_toggle_delete_mode(self, interaction: discord.Interaction) -> None:
        """Alterna entre el modo de eliminación y el modo de reproducción."""
        self.mode = "play" if self.mode == "delete" else "delete"
        await self.refresh(interaction)

    async def refresh(self, interaction: discord.Interaction) -> None:
        """Refresca el embed y los componentes interactivos de la vista."""
        self.update_components()
        from database import get_saved_playlists
        playlists = await asyncio.to_thread(get_saved_playlists, self.guild_id)
        embed = EmbedFactory.build_playlists_embed(playlists, mode=self.mode)

        try:
            await interaction.response.edit_message(embed=embed, view=self)
        except Exception:
            try:
                await interaction.message.edit(embed=embed, view=self)
            except Exception as err:
                logger.debug(f"No se pudo refrescar mensaje de playlists: {err}")
