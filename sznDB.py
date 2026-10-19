import asyncio
import discord
from discord.ext import commands
from rapidfuzz import process
from sznLogger import get_logger

logger = get_logger("db")
from database import (
    AppConfig,
    PlayLog,
    Song,
    UserDislike,
    UserLike,
    add_or_update_song,
    find_similar_song as db_find_similar_song,
    get_db_session,
    get_liked_songs_by_user as db_get_liked_songs_by_user,
    get_liked_songs_by_users as db_get_liked_songs_by_users,
    get_recent_history,
    get_top_songs,
    like_song as db_like_song,
    log_dislike_event,
    preload_top_songs_cache,
    remove_dislike,
    unlike_song as db_unlike_song,
)


class MusicDB(commands.Cog):
    """Cog de Discord para gestión de favoritos, ranking y telemetría de servidor."""

    def __init__(self, bot):
        self.bot = bot
        preload_top_songs_cache()
        self.last_played = []

    def log_song(self, title: str) -> None:
        """Registra la canción en el historial reciente en memoria y garantiza su existencia en BD sin duplicar played_count."""
        self.last_played.insert(0, title)
        if len(self.last_played) > 20:
            self.last_played.pop()

        try:
            add_or_update_song(title=title)
        except Exception as err:
            logger.warning(f"⚠️ Error al asegurar registro de canción en BD: {err}")

    def find_similar_song(self, query: str, threshold: int = 90):
        """Busca una canción similar delegando en la capa de datos centralizada."""
        return db_find_similar_song(query, threshold=threshold)

    def get_liked_songs_by_user(self, user_id: str):
        """Obtiene las canciones favoritas de un usuario desde database.py."""
        return db_get_liked_songs_by_user(user_id)

    def get_liked_songs_by_users(self, user_ids: list[str]):
        """Obtiene las canciones favoritas de múltiples usuarios desde database.py."""
        return db_get_liked_songs_by_users(user_ids)

    def like_song(self, user_id: str, song_title: str) -> bool:
        """Registra un me gusta delegando en database.py."""
        return db_like_song(user_id, song_title)

    def unlike_song(self, user_id: str, song_title: str) -> bool:
        """Elimina un me gusta delegando en database.py."""
        return db_unlike_song(user_id, song_title)

    @commands.command()
    async def like(self, ctx):
        """Le da me gusta a la canción que se está reproduciendo actualmente."""
        core = self.bot.get_cog("MusicCore")
        player = core.get_player(ctx) if core else None
        if not player or not player.current_song:
            await ctx.send("⚠️ No hay ninguna canción en reproducción.")
            return
        added = await asyncio.to_thread(self.like_song, str(ctx.author.id), player.current_song['title'])
        if added:
            await ctx.send(f"❤️ Canción guardada en tus favoritas: **{player.current_song['title']}**")
        else:
            await ctx.send("✅ Esta canción ya está en tus favoritas.")

    @commands.command()
    async def unlike(self, ctx):
        """Elimina la canción actual de tus favoritas."""
        core = self.bot.get_cog("MusicCore")
        player = core.get_player(ctx) if core else None
        if not player or not player.current_song:
            await ctx.send("⚠️ No hay ninguna canción en reproducción.")
            return
        removed = await asyncio.to_thread(self.unlike_song, str(ctx.author.id), player.current_song['title'])
        if removed:
            await ctx.send(f"❌ Canción eliminada de tus favoritas: **{player.current_song['title']}**")
        else:
            await ctx.send("ℹ️ Esta canción no estaba en tus favoritas.")

    @commands.command()
    async def dislike(self, ctx):
        """Marca la canción actual como no gustada (feedback negativo para recomendaciones)."""
        core = self.bot.get_cog("MusicCore")
        player = core.get_player(ctx) if core else None
        if not player or not player.current_song:
            await ctx.send("⚠️ No hay ninguna canción en reproducción.")
            return
        added = await asyncio.to_thread(log_dislike_event, str(ctx.author.id), player.current_song['title'])
        if added:
            await ctx.send(f"👎 Canción marcada como no gustada: **{player.current_song['title']}**")
        else:
            await ctx.send("ℹ️ Ya habías marcado esta canción como no gustada.")

    @commands.command()
    async def undislike(self, ctx):
        """Elimina la marca de no me gusta de la canción actual."""
        core = self.bot.get_cog("MusicCore")
        player = core.get_player(ctx) if core else None
        if not player or not player.current_song:
            await ctx.send("⚠️ No hay ninguna canción en reproducción.")
            return
        removed = await asyncio.to_thread(remove_dislike, str(ctx.author.id), player.current_song['title'])
        if removed:
            await ctx.send(f"✅ Se eliminó la marca de no gustada: **{player.current_song['title']}**")
        else:
            await ctx.send("ℹ️ Esta canción no estaba marcada como no gustada.")

    @commands.command()
    async def liked(self, ctx):
        """Muestra tus canciones favoritas."""
        songs = await asyncio.to_thread(self.get_liked_songs_by_user, str(ctx.author.id))
        if not songs:
            await ctx.send("📭 No tienes canciones favoritas aún. Usa `td?like` mientras suena una canción.")
            return
        lines = [f"`{i:02d}.` **{song.title}**" for i, song in enumerate(songs[:15], 1)]
        from sznUI.embeds import EmbedFactory
        embed = EmbedFactory.build_collection_embed(
            title=f"❤️ Tus Canciones Favoritas ({len(songs)})",
            lines=lines,
            footer_text=f"Colección personal de @{ctx.author.name}",
        )
        await ctx.send(embed=embed)

    @commands.command()
    async def favradio(self, ctx, temperatura: float = 0.75):
        """Activa modo radio grupal usando las canciones favoritas de los miembros en la llamada."""
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send("⚠️ Debes estar en un canal de voz para usar este comando.")
            return

        core = self.bot.get_cog("MusicCore")
        if not core:
            await ctx.send("❌ Módulo de música no encontrado.")
            return

        vc = await core.connect_to_voice(ctx)
        if not vc:
            return

        player = core.get_player(ctx)
        player.radio_temperature = max(0.0, min(1.0, float(temperatura)))

        members = ctx.author.voice.channel.members
        user_ids = [str(m.id) for m in members if not m.bot]
        liked_songs = await asyncio.to_thread(self.get_liked_songs_by_users, user_ids)

        if not liked_songs:
            await ctx.send("📭 Ningún participante en la llamada tiene canciones favoritas. Generando radio basada en el Top del servidor...")
            guild_id = ctx.guild.id if ctx.guild else None
            top_songs = await asyncio.to_thread(get_top_songs, guild_id=guild_id, limit=10)
            if not top_songs or not core.sp:
                await ctx.send("⚠️ No se pudo generar recomendaciones.")
                return
            for title, _ in top_songs[:5]:
                results = await asyncio.to_thread(core.sp.search, q=title, type='track', limit=1)
                if results and results.get('tracks', {}).get('items'):
                    seed_id = results['tracks']['items'][0]['id']
                    player.radio_mode = True
                    player.radio_seed_id = seed_id
                    await core.expand_radio_queue(ctx, seed_id=seed_id, seed_title=title)
                    if not player.current_song and player.voice_client and not player.voice_client.is_playing():
                        await core.play_next(ctx)
                    break
            else:
                await ctx.send("⚠️ No se pudo generar recomendaciones basadas en el top del servidor.")
            return

        if not core.sp:
            await ctx.send("❌ La conexión con Spotify no está configurada.")
            return

        await ctx.send("🎧 **Radio Grupal Activada**: Generando recomendaciones basadas en gustos colectivos...")
        import random
        random_song = random.choice(liked_songs)
        results = await asyncio.to_thread(core.sp.search, q=random_song.title, type='track', limit=1)
        if results and results.get('tracks', {}).get('items'):
            seed_id = results['tracks']['items'][0]['id']
            player.radio_mode = True
            player.radio_seed_id = seed_id
            await core.expand_radio_queue(ctx, seed_id=seed_id, seed_title=random_song.title)
            if not player.current_song and player.voice_client and not player.voice_client.is_playing():
                await core.play_next(ctx)
        else:
            await ctx.send("⚠️ No se pudo generar recomendaciones basadas en canciones favoritas.")

    @commands.command(name="historial")
    async def historial(self, ctx):
        """Muestra las últimas canciones reproducidas en este servidor."""
        guild_id = ctx.guild.id if ctx.guild else None
        history_titles = await asyncio.to_thread(get_recent_history, guild_id=guild_id, limit=10)
        if not history_titles and self.last_played:
            history_titles = self.last_played[:10]

        if history_titles:
            lines = [f"`{i + 1:02d}.` **{title}**" for i, title in enumerate(history_titles)]
            embed_title = f"🎧 Últimas Canciones Reproducidas — {ctx.guild.name}" if ctx.guild else "🎧 Últimas Canciones Reproducidas"
            from sznUI.embeds import EmbedFactory
            await ctx.send(embed=EmbedFactory.build_collection_embed(embed_title, lines))
        else:
            await ctx.send("📭 No hay historial reciente de reproducción en este servidor.")

    @commands.command(name="top")
    async def top(self, ctx):
        """Muestra las canciones más reproducidas en este servidor."""
        guild_id = ctx.guild.id if ctx.guild else None
        top_songs = await asyncio.to_thread(get_top_songs, guild_id=guild_id, limit=10)
        if top_songs:
            lines = [
                f"`{i + 1:02d}.` **{title}** — `{count} reproducciones`"
                for i, (title, count) in enumerate(top_songs)
            ]
            embed_title = f"📈 Top Canciones — {ctx.guild.name}" if ctx.guild else "📈 Top Canciones Más Reproducidas"
            from sznUI.embeds import EmbedFactory
            await ctx.send(embed=EmbedFactory.build_collection_embed(embed_title, lines))
        else:
            await ctx.send("📭 No hay estadísticas de canciones en este servidor aún.")

    def format_embed(self, title, content):
        from sznUI.embeds import EmbedFactory
        lines = content.splitlines() if isinstance(content, str) else list(content)
        return EmbedFactory.build_collection_embed(title, lines)

async def setup(bot):
    musicdb = MusicDB(bot)
    await bot.add_cog(musicdb)
    bot.musicdb = musicdb
    preload_top_songs_cache(limit=10)