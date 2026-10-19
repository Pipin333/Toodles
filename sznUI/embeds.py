"""Fábrica centralizada de Discord Embeds (EmbedFactory) para todas las superficies de Tooodles."""

import time
import discord

from .theme import UITheme, format_duration, render_progress_bar


class EmbedFactory:
    """Centraliza la construcción de todos los embeds del bot garantizando consistencia visual."""

    @staticmethod
    def build_now_playing_embed(song_dict: dict, player, vc_name: str = "Canal de voz") -> discord.Embed:
        """Construye el embed principal del panel 'Ahora Reproduciendo' con estado en vivo.

        Args:
            song_dict: Diccionario con metadatos de la pista en reproducción.
            player: Instancia de GuildPlayer del servidor actual.
            vc_name: Nombre del canal de voz conectado.

        Returns:
            Instancia de discord.Embed lista para enviarse o actualizarse.
        """
        song_title = song_dict.get("title", "Canción Desconocida")
        song_url = song_dict.get("url") or "https://www.youtube.com"
        origin = song_dict.get("origin", "🎵 Solicitada")
        duration_sec = int(song_dict.get("duration", 0) or 0)
        uploader = song_dict.get("uploader", "Artista Desconocido")
        thumbnail = song_dict.get("thumbnail", "")
        username = song_dict.get("username")

        start_time = getattr(player, "current_song_start_time", None)
        elapsed_sec = int(time.time() - start_time) if start_time else 0
        progress_display = render_progress_bar(elapsed_sec, duration_sec, length=12)

        vc = getattr(player, "voice_client", None)
        is_paused = bool(vc and hasattr(vc, "is_paused") and vc.is_paused())
        is_radio = "radio" in origin.lower() or "autoplay" in origin.lower()

        if is_paused:
            header_title = "⏸️ Reproducción en Pausa"
            embed_color = UITheme.WARNING
        elif is_radio:
            header_title = "📻 Radio & Autoplay IA"
            embed_color = UITheme.RADIO_ML
        elif "spotify" in origin.lower():
            header_title = "🎶 Ahora Reproduciendo"
            embed_color = UITheme.SPOTIFY
        else:
            header_title = "🎶 Ahora Reproduciendo"
            embed_color = UITheme.PRIMARY

        embed = discord.Embed(
            title=header_title,
            description=f"**[{song_title}]({song_url})**",
            color=embed_color,
        )
        embed.add_field(name="👤 Artista", value=f"`{uploader}`", inline=True)
        embed.add_field(name="⏱️ Progreso", value=progress_display, inline=True)

        if username:
            embed.add_field(name="📥 Pedido por", value=f"@{username}", inline=True)
        elif is_radio:
            embed.add_field(name="🧬 Origen", value="`Recomendador IA`", inline=True)
        else:
            embed.add_field(name="🧬 Origen", value=f"`{origin}`", inline=True)

        if thumbnail and thumbnail.startswith("http"):
            embed.set_thumbnail(url=thumbnail)

        vibe_size = len(getattr(player, "recent_artist_ids", []))
        autoplay_state = "ON" if getattr(player, "autoplay_mode", False) else "OFF"
        radio_state = "ON" if getattr(player, "radio_mode", False) else "OFF"
        embed.set_footer(
            text=f"🔊 {vc_name}  •  🤖 Autoplay: {autoplay_state}  •  📻 Radio: {radio_state} ({vibe_size}/5 semillas)"
        )
        return embed

    @staticmethod
    def build_queue_page_embed(player, page: int = 0, items_per_page: int = 10) -> tuple[discord.Embed, int]:
        """Construye una página de la cola de reproducción y calcula el total de páginas.

        Args:
            player: Instancia de GuildPlayer con `current_song` y `song_queue`.
            page: Índice de página base 0.
            items_per_page: Cantidad de canciones por página.

        Returns:
            Tupla `(embed, total_pages)`.
        """
        queue_items = getattr(player, "song_queue", [])
        total_songs = len(queue_items)
        total_pages = max(1, (total_songs + items_per_page - 1) // items_per_page)
        safe_page = max(0, min(page, total_pages - 1))

        embed = discord.Embed(
            title="📋 Cola de Reproducción",
            color=UITheme.PRIMARY,
        )

        current_song = getattr(player, "current_song", None)
        if current_song:
            current_title = current_song.get("title", "Desconocido")
            current_uploader = current_song.get("uploader", "Artista")
            current_duration = format_duration(current_song.get("duration", 0))
            embed.add_field(
                name="▶️ Sonando Ahora",
                value=f"**{current_title}** — `{current_uploader}` `[{current_duration}]`",
                inline=False,
            )
            thumb = current_song.get("thumbnail", "")
            if thumb and thumb.startswith("http"):
                embed.set_thumbnail(url=thumb)

        start_idx = safe_page * items_per_page
        end_idx = start_idx + items_per_page
        page_slice = queue_items[start_idx:end_idx]

        if page_slice:
            lines = []
            for idx, track in enumerate(page_slice, start=start_idx + 1):
                dur_str = format_duration(track.get("duration", 0))
                origin_str = track.get("origin", "").lower()
                origin_icon = "📻" if ("radio" in origin_str or "autoplay" in origin_str) else "🎵"
                requester = f"@{track.get('username')}" if track.get("username") else "Auto"
                lines.append(f"`{idx:02d}.` {origin_icon} **{track.get('title', 'Canción')}** `[{dur_str}]` ({requester})")
            queue_text = "\n".join(lines)
        else:
            queue_text = "*No hay más pistas en espera. Añade una con `td?play` o activa `🤖 Autoplay`.*"

        embed.add_field(name="🎶 Siguientes en Cola", value=queue_text, inline=False)

        total_duration = sum(int(s.get("duration", 0) or 0) for s in queue_items)
        total_duration_str = format_duration(total_duration) if total_duration > 0 else "0:00"
        embed.set_footer(
            text=f"Página {safe_page + 1}/{total_pages}  •  {total_songs} canciones en espera  •  Duración total: {total_duration_str}"
        )
        return embed, total_pages

    @staticmethod
    def build_collection_embed(
        title: str,
        lines: list[str],
        empty_message: str = "Aún no hay registros disponibles.",
        footer_text: str | None = None,
    ) -> discord.Embed:
        """Construye un embed estandarizado para listas de datos (Favoritas, Top, Historial).

        Args:
            title: Título del embed.
            lines: Líneas ya formateadas para el cuerpo.
            empty_message: Texto de estado vacío cuando `lines` no tiene elementos.
            footer_text: Pie de página opcional.

        Returns:
            Instancia de discord.Embed con estilo de colección.
        """
        description = "\n".join(lines) if lines else empty_message
        embed = discord.Embed(
            title=title,
            description=description,
            color=UITheme.COLLECTION,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text=footer_text or UITheme.FOOTER_BRAND)
        return embed

    @staticmethod
    def build_settings_embed(guild, core) -> discord.Embed:
        """Construye el embed del panel interactivo de ajustes del servidor (`td?settings`).

        Args:
            guild: Objeto discord.Guild del servidor.
            core: Instancia de MusicCore.

        Returns:
            Instancia de discord.Embed con el estado actual de configuración.
        """
        from sznUtils import is_guild_persist_enabled, load_config

        guild_id = guild.id
        cmd_channel = load_config(f"cmd_channel_{guild_id}")
        cmd_channel_val = f"<#{cmd_channel}>" if cmd_channel else "`Cualquier canal`"

        default_radio = load_config(f"default_radio_{guild_id}")
        default_radio_val = "`🟢 Activo`" if default_radio == "on" else "`⚪ Inactivo`"

        persist_enabled = is_guild_persist_enabled(guild_id)
        persist_val = "`🟢 Activada`" if persist_enabled else "`🔴 Desactivada`"

        prefix = load_config(f"prefix_{guild_id}") or "td?"
        player = core.get_player(guild_id)
        vibe_size = len(getattr(player, "recent_artist_ids", []))

        embed = discord.Embed(
            title=f"⚙️ Ajustes del Servidor — {guild.name}",
            description="Utiliza los controles inferiores para ajustar el comportamiento del bot en tiempo real.",
            color=UITheme.PRIMARY,
        )
        embed.add_field(name="⌨️ Prefijo", value=f"`{prefix}`", inline=True)
        embed.add_field(name="🔒 Canal Exclusivo", value=cmd_channel_val, inline=True)
        embed.add_field(name="💾 Persistencia de Cola", value=persist_val, inline=True)
        embed.add_field(name="📻 Radio al Conectar", value=default_radio_val, inline=True)
        embed.add_field(name="🧬 Semillas de Radio", value=f"`{vibe_size}/5` artistas", inline=True)
        embed.set_footer(text="Solo los Administradores del servidor pueden modificar estos ajustes.")
        return embed

    @staticmethod
    def build_help_category_embed(
        category: str,
        prefix: str = "td?",
        guild_name: str | None = None,
        author_name: str = "Usuario",
    ) -> discord.Embed:
        """Construye el embed de ayuda para la categoría seleccionada en el menú interactivo.

        Args:
            category: Identificador de categoría (`overview`, `music`, `recsys`, `playlists`, `admin`).
            prefix: Prefijo activo del servidor.
            guild_name: Nombre del servidor (o `None` si es DM).
            author_name: Nombre del usuario que solicitó la ayuda.

        Returns:
            Instancia de discord.Embed correspondiente a la categoría.
        """
        scope_label = f"Servidor: {guild_name}" if guild_name else "Sesión por Mensaje Directo (DM)"
        cat = (category or "overview").lower()

        if cat == "music":
            embed = discord.Embed(
                title="🎧 Reproducción y Gestión de Cola",
                description=f"Comandos para reproducir música y ordenar la fila de espera (Prefijo: `{prefix}`).",
                color=UITheme.PRIMARY,
                timestamp=discord.utils.utcnow(),
            )
            embed.add_field(
                name="▶️ Control de Audio",
                value=(
                    f"• `{prefix}play <canción / URL>` (`p`) — Reproduce o encola desde YouTube o Spotify.\n"
                    f"• `{prefix}join` (`j`) — Conecta al canal de voz y restaura la cola persistente.\n"
                    f"• `{prefix}pause` / `{prefix}resume` (`r`) — Pausa o reanuda la pista actual.\n"
                    f"• `{prefix}skip` (`s`) — Salta a la siguiente canción.\n"
                    f"• `{prefix}stop` (`dc`) — Guarda la cola (si aplica), limpia caché y desconecta.\n"
                    f"• `{prefix}np` / `{prefix}controls` — Muestra el panel interactivo de reproducción."
                ),
                inline=False,
            )
            embed.add_field(
                name="📋 Organización de la Cola",
                value=(
                    f"• `{prefix}queue` (`q`) — Abre el visor interactivo paginado de la cola.\n"
                    f"• `{prefix}shuffle` — Mezcla aleatoriamente las canciones en espera y re-optimiza caché.\n"
                    f"• `{prefix}move <origen> <destino>` — Reubica una canción dentro de la cola.\n"
                    f"• `{prefix}remove <posición>` — Elimina una pista específica de la cola.\n"
                    f"• `{prefix}clear` (`cq`) — Vacía la cola sin cortar la canción que está sonando."
                ),
                inline=False,
            )

        elif cat == "recsys":
            embed = discord.Embed(
                title="📻 Recomendador Híbrido IA, Radio y Favoritos",
                description="Motor multimodal (Implicit ALS + Item2Vec + Audio Features) y curaduría personal.",
                color=UITheme.RADIO_ML,
                timestamp=discord.utils.utcnow(),
            )
            embed.add_field(
                name="🤖 Modos de Descubrimiento Automático",
                value=(
                    f"• `{prefix}autoplay [off]` — Activa el Autoplay ML continuo basado en el modelo híbrido.\n"
                    f"• `{prefix}radio [off]` — Activa la Radio por expansión de géneros y artistas de Spotify.\n"
                    f"• `{prefix}favradio [temp]` — Crea una radio grupal combinando los favoritos de quienes están en el canal de voz (`temp` entre `0.0` y `1.0`)."
                ),
                inline=False,
            )
            embed.add_field(
                name="❤️ Feedback y Estadísticas",
                value=(
                    f"• `{prefix}like` / `{prefix}unlike` — Guarda o quita la canción actual de tus favoritas (`+5.0` en RecSys).\n"
                    f"• `{prefix}dislike` / `{prefix}undislike` — Marca o desmarca rechazo (`-5.0` en RecSys).\n"
                    f"• `{prefix}liked` — Muestra tu colección de canciones favoritas.\n"
                    f"• `{prefix}top` / `{prefix}historial` — Ranking de más escuchadas e historial reciente del servidor."
                ),
                inline=False,
            )

        elif cat == "playlists":
            embed = discord.Embed(
                title="📚 Playlists Guardadas y Precarga ML",
                description="Almacena playlists del servidor para lanzarlas con un clic o entrena tu perfil musical.",
                color=UITheme.COLLECTION,
                timestamp=discord.utils.utcnow(),
            )
            embed.add_field(
                name="🗂️ Gestor Interactivo de Playlists",
                value=(
                    f"• `{prefix}playlists` (`pl`) — Abre el panel con menú desplegable para reproducir, agregar, editar o eliminar playlists.\n"
                    f"• `{prefix}playlists add <URL> [Alias]` — Guarda directamente una playlist de Spotify o YouTube.\n"
                    f"• `{prefix}playlists remove <Nombre>` — Elimina una playlist guardada."
                ),
                inline=False,
            )
            embed.add_field(
                name="📥 Precarga Masiva al Motor IA",
                value=(
                    f"• `{prefix}preload <URL> [@usuario]` — Importa todas las pistas de una playlist/álbum como likes e historial de sesión y reentrena el modelo ML al instante."
                ),
                inline=False,
            )

        elif cat == "admin":
            embed = discord.Embed(
                title="⚙️ Configuración del Servidor y Diagnóstico (Admin / Trusted)",
                description="Herramientas de administración del servidor y telemetría por Mensaje Directo (DM).",
                color=UITheme.WARNING,
                timestamp=discord.utils.utcnow(),
            )
            embed.add_field(
                name="🏰 Ajustes del Servidor (Administradores)",
                value=(
                    f"• `{prefix}settings` (`config`) — Panel interactivo para Prefijo, Canal Exclusivo, Radio Default y Persistencia.\n"
                    f"• `{prefix}channel [#canal | aqui | reset]` — Restringe o libera el canal de comandos.\n"
                    f"• `{prefix}persist [on | off]` — Activa o solicita autorización de persistencia de colas."
                ),
                inline=False,
            )
            embed.add_field(
                name="🛡️ Diagnóstico y RecSys (Admin / Trusted Users en DM)",
                value=(
                    "• `debug` / `status` — Ficha técnica en DM (disco `/tmp`, modo WAL de SQLite, estado RecSys y conexiones).\n"
                    "• `logs [N]` — Muestra las últimas `N` líneas del archivo `tooodles.log`.\n"
                    "• `train` / `reloadrecsys` — Ejecuta el entrenamiento offline o recarga artefactos `.npz` en caliente.\n"
                    "• `trusted [add | remove] @usuario` — Gestiona usuarios de confianza (Solo Dueño del Bot)."
                ),
                inline=False,
            )

        else:
            embed = discord.Embed(
                title="🎶 Tooodles — Centro de Ayuda Interactivo",
                description=(
                    f"Prefijo activo: `{prefix}`\n"
                    "Selecciona una categoría en el **menú desplegable inferior** para explorar todos los comandos sin saturar el chat."
                ),
                color=UITheme.COLLECTION,
                timestamp=discord.utils.utcnow(),
            )
            embed.add_field(
                name="🚀 Inicio Rápido",
                value=(
                    f"• `{prefix}play <canción o link>` — Reproduce música al instante.\n"
                    f"• `{prefix}autoplay` — Deja que la IA continúe la sesión automáticamente.\n"
                    f"• `{prefix}playlists` — Abre la colección de playlists del servidor.\n"
                    f"• `{prefix}settings` — Configura prefijo, canal exclusivo y persistencia."
                ),
                inline=False,
            )

        embed.set_footer(text=f"{scope_label}  •  Solicitado por @{author_name}")
        return embed

    @staticmethod
    def build_playlists_embed(playlists: list[dict], mode: str = "play") -> discord.Embed:
        """Construye el embed para el gestor interactivo de playlists del servidor.

        Args:
            playlists: Lista de diccionarios con `name` y `url`.
            mode: Modo activo de la vista (`play`, `edit`, `delete`).

        Returns:
            Instancia de discord.Embed reflejando el modo actual.
        """
        if mode == "delete":
            mode_desc = "🗑️ **Modo Eliminar**: selecciona una playlist en el menú para borrarla."
            color = UITheme.DANGER
        elif mode == "edit":
            mode_desc = "✏️ **Modo Editar**: selecciona una playlist en el menú para modificar su alias o enlace."
            color = UITheme.WARNING
        else:
            mode_desc = "▶️ Selecciona una playlist en el menú desplegable para reproducirla de inmediato."
            color = UITheme.COLLECTION

        embed = discord.Embed(
            title="📚 Colección de Playlists del Servidor",
            description=f"Hay **{len(playlists)}** playlists guardadas.\n{mode_desc}",
            color=color,
        )
        if playlists:
            pl_lines = [f"• **{p['name']}** — `{p['url'][:45]}...`" for p in playlists[:10]]
            if len(playlists) > 10:
                pl_lines.append(f"*...y {len(playlists) - 10} más en el selector.*")
            embed.add_field(name="📋 Playlists Guardadas", value="\n".join(pl_lines), inline=False)
        else:
            embed.add_field(
                name="ℹ️ Colección Vacía",
                value="Aún no hay playlists guardadas. Pulsa el botón `➕ Agregar` o usa `td?playlist add <URL>`.",
                inline=False,
            )
        return embed

    @staticmethod
    def build_preload_result_embed(target_username: str, preload_result: dict, recsys_stats: dict) -> discord.Embed:
        """Construye el embed de resumen tras completar `td?preload`.

        Args:
            target_username: Nombre del usuario al que se asignaron los gustos.
            preload_result: Resultado devuelto por `bulk_preload_tracks`.
            recsys_stats: Estadísticas del motor `RecSysEngine`.

        Returns:
            Instancia de discord.Embed con el desglose de precarga y entrenamiento.
        """
        embed = discord.Embed(
            title="✅ Precarga y Entrenamiento ML Completados",
            description=f"Perfil musical de **@{target_username}** actualizado e indexado en el motor híbrido.",
            color=UITheme.SPOTIFY,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="📥 Pistas Procesadas", value=f"`{preload_result.get('total', 0)}`", inline=True)
        embed.add_field(name="🆕 Nuevas en Catálogo", value=f"`{preload_result.get('new_songs', 0)}`", inline=True)
        embed.add_field(name="❤️ Likes Asignados", value=f"`{preload_result.get('likes_added', 0)}`", inline=True)
        embed.add_field(
            name="🧠 Estado del Motor RecSys",
            value=(
                f"`{recsys_stats.get('n_songs', 0)}` canciones  •  "
                f"`{recsys_stats.get('n_users', 0)}` usuarios listos para Autoplay"
            ),
            inline=False,
        )
        embed.set_footer(text=UITheme.FOOTER_BRAND)
        return embed
