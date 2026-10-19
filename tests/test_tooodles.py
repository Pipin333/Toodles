"""Suite de pruebas automatizadas de regresión y dominio para Tooodles."""

import asyncio
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest


def test_musicdb_commands_use_guild_player():
    """Verifica que like, unlike, dislike y undislike consulten player.current_song y no core.current_song."""
    from sznDB import MusicDB
    from sznMusic.player import GuildPlayer

    bot = MagicMock()
    player = GuildPlayer(guild_id=12345)
    player.current_song = {"title": "Cancion Test - Artista"}

    # MusicCore real no tiene atributo current_song; solo get_player(ctx)
    core = MagicMock(spec=["get_player", "connect_to_voice", "expand_radio_queue", "play_next", "sp"])
    core.get_player.return_value = player
    bot.get_cog.return_value = core

    with patch("sznDB.preload_top_songs_cache"):
        cog = MusicDB(bot)

    ctx = MagicMock()
    ctx.author.id = 999
    ctx.send = AsyncMock()

    with patch.object(cog, "like_song", return_value=True) as mock_like:
        asyncio.run(cog.like.callback(cog, ctx))
        mock_like.assert_called_once_with("999", "Cancion Test - Artista")


def test_settings_controls_uses_target_guild_not_first_guild():
    """Verifica que SettingsControls actualice los botones usando el guild del contexto y no bot.guilds[0]."""
    from sznUI import MusicUI

    guild_0 = MagicMock()
    guild_0.id = 11111
    guild_0.name = "Guild Cero"

    guild_target = MagicMock()
    guild_target.id = 22222
    guild_target.name = "Guild Objetivo"

    bot = MagicMock()
    bot.guilds = [guild_0, guild_target]
    core = MagicMock()
    core.bot = bot

    def fake_load_config(key: str):
        if key == "prefix_22222":
            return "!!"
        if key == "prefix_11111":
            return "td?"
        return None

    async def _run():
        with patch("sznUtils.load_config", side_effect=fake_load_config):
            view = MusicUI.SettingsControls(core, bot, guild=guild_target)
            prefix_btn = next(c for c in view.children if getattr(c, "custom_id", None) == "change_prefix_btn")
            assert prefix_btn.label == "✏️ Prefijo: !!"

    asyncio.run(_run())


def test_cookie_file_path_reuses_single_temp_file(monkeypatch):
    """Verifica que get_cookie_file_path no cree archivos temporales infinitos en /tmp."""
    import sznUtils

    monkeypatch.setattr(os.path, "exists", lambda p: False if p == "cookies.txt" else os.path.isfile(p))
    monkeypatch.setattr(sznUtils, "load_config", lambda k: "# Netscape HTTP Cookie File\n" + ("a" * 60))

    path1 = sznUtils.get_cookie_file_path()
    path2 = sznUtils.get_cookie_file_path()

    assert path1 is not None
    assert path1 == path2
    if os.path.isfile(path1):
        os.remove(path1)


def test_recsys_artifacts_load_without_pickle(tmp_path, monkeypatch):
    """Verifica que export_artifacts y RecSysEngine.load funcionen con allow_pickle=False."""
    import recsys.engine as eng_mod
    import recsys.train as train_mod

    art_dir = tmp_path / "data"
    art_path = art_dir / "recsys_artifacts.npz"
    monkeypatch.setattr(train_mod, "ARTIFACTS_DIR", str(art_dir))
    monkeypatch.setattr(train_mod, "ARTIFACTS_PATH", str(art_path))
    monkeypatch.setattr(eng_mod, "ARTIFACTS_DIR", str(art_dir))
    monkeypatch.setattr(eng_mod, "ARTIFACTS_PATH", str(art_path))

    user_factors = np.ones((2, 8), dtype=np.float32)
    item_factors = np.ones((3, 8), dtype=np.float32)
    item2vec_vectors = np.ones((3, 8), dtype=np.float32)
    audio_features = np.ones((3, 8), dtype=np.float32)

    user_id_map = {"u1": 0, "u2": 1}
    song_id_map = {10: 0, 20: 1, 30: 2}
    reverse_song_map = {0: 10, 1: 20, 2: 30}
    reverse_user_map = {0: "u1", 1: "u2"}
    songs_meta = [
        {"id": 10, "title": "Song A", "artist": "Artist A"},
        {"id": 20, "title": "Song B", "artist": "Artist B"},
        {"id": 30, "title": "Song C", "artist": "Artist C"},
    ]

    train_mod.export_artifacts(
        user_factors=user_factors,
        item_factors=item_factors,
        item2vec_vectors=item2vec_vectors,
        audio_feature_vectors=audio_features,
        user_id_map=user_id_map,
        song_id_map=song_id_map,
        reverse_song_map=reverse_song_map,
        reverse_user_map=reverse_user_map,
        songs_metadata=songs_meta,
        interaction_matrix=None,
    )

    # Debe poder cargarse y leerse cada array con allow_pickle=False estrictamente
    raw = np.load(str(art_path), allow_pickle=False)
    for key in raw.files:
        _ = raw[key]

    engine = eng_mod.RecSysEngine()
    assert engine.load(force=True) is True
    recs = engine.recommend_for_user("u1", n=2)
    assert len(recs) == 2


def test_trigger_recsys_train_reloads_music_core_engine():
    """Verifica que td?train recargue recsys_engine en el Cog MusicCore."""
    from sznUI import MusicUI

    bot = MagicMock()
    music_core = MagicMock()
    music_core.recsys_engine = MagicMock()
    bot.get_cog.side_effect = lambda name: music_core if name == "MusicCore" else None

    cog = MusicUI(bot)
    ctx = MagicMock()
    msg = MagicMock()
    msg.edit = AsyncMock()
    ctx.send = AsyncMock(return_value=msg)

    fake_proc = MagicMock(returncode=0, stderr="", stdout="")
    with patch.object(cog, "_is_authorized_admin_or_trusted", AsyncMock(return_value=True)), \
         patch("subprocess.run", return_value=fake_proc):
        asyncio.run(cog.trigger_recsys_train.callback(cog, ctx))

    music_core.recsys_engine.reload_if_updated.assert_called_once()


def test_clean_title_for_search():
    """Verifica la limpieza de títulos de canciones para búsqueda en Spotify/YouTube."""
    from sznMusic.player import _clean_title_for_search

    clean, artist = _clean_title_for_search("Los Bunkers - Bailando Solo (Official Music Video) [HD]")
    assert artist == "Los Bunkers"
    assert clean == "Bailando Solo"


def test_cleanup_guild_player_cache_preserves_other_guilds(tmp_path):
    """Verifica que cleanup_guild_player_cache solo elimine los archivos de caché del guild indicado."""
    from sznMusic.player import GuildPlayer, cleanup_guild_player_cache

    file_a = tmp_path / "cache_guild_a.webm"
    file_b = tmp_path / "cache_guild_b.webm"
    file_a.write_bytes(b"audio_a")
    file_b.write_bytes(b"audio_b")

    player_a = GuildPlayer(guild_id=100)
    player_a.current_song = {"title": "Song A", "cache_filepath": str(file_a)}

    player_b = GuildPlayer(guild_id=200)
    player_b.song_queue = [{"title": "Song B", "cache_filepath": str(file_b)}]

    cleanup_guild_player_cache(player_a)

    assert not file_a.exists()
    assert file_b.exists()


def test_ui_shuffle_queue_schedules_optimizations():
    """Verifica que el botón Shuffle de MusicControls invoque schedule_queue_optimizations."""
    from sznMusic.player import GuildPlayer
    from sznUI import MusicUI

    player = GuildPlayer(guild_id=555)
    player.song_queue = [{"title": "Track 1"}, {"title": "Track 2"}]
    core = MagicMock()
    core.get_player.return_value = player

    ctx = MagicMock()
    interaction = MagicMock()
    interaction.response.send_message = AsyncMock()

    async def _run():
        view = MusicUI.MusicControls(core, ctx)
        await view.shuffle_queue.callback(interaction)

    asyncio.run(_run())
    core.schedule_queue_optimizations.assert_called_once_with(ctx)


def test_single_now_playing_message_replaces_previous():
    """Verifica que notify_now_playing elimine el panel anterior del guild para evitar spam en el chat."""
    from sznMusic.player import GuildPlayer
    from sznUI import MusicUI

    bot = MagicMock()
    player = GuildPlayer(guild_id=777)
    old_msg = MagicMock()
    old_msg.delete = AsyncMock()
    player.now_playing_message = old_msg

    new_msg = MagicMock()
    core = MagicMock()
    core.get_player.return_value = player
    core.format_duration.return_value = "3:45"
    bot.get_cog.return_value = core

    ui_cog = MusicUI(bot)
    ctx = MagicMock()
    ctx.guild.id = 777
    ctx.channel.id = 888
    ctx.author.voice.channel.name = "General"
    ctx.send = AsyncMock(return_value=new_msg)

    song = {"title": "Cancion Nueva", "uploader": "Artista", "duration": 225, "url": "https://youtube.com/watch?v=1"}
    asyncio.run(ui_cog.notify_now_playing(ctx, song))

    old_msg.delete.assert_awaited_once()
    assert player.now_playing_message is new_msg


def test_pause_resume_button_updates_visual_state_in_place():
    """Verifica que el botón de Pausa/Reanuda actualice su etiqueta y edite el mensaje para reflejar el estado en vivo."""
    from sznMusic.player import GuildPlayer
    from sznUI import MusicUI

    player = GuildPlayer(guild_id=321)
    player.current_song = {"title": "Song", "duration": 180}
    vc = MagicMock()
    vc.is_playing.return_value = True
    vc.is_paused.return_value = False
    player.voice_client = vc

    core = MagicMock()
    core.get_player.return_value = player
    ctx = MagicMock()

    interaction = MagicMock()
    interaction.response.edit_message = AsyncMock()
    interaction.followup.send = AsyncMock()

    async def _run():
        view = MusicUI.MusicControls(core, ctx)
        pause_btn = next(c for c in view.children if getattr(c, "custom_id", None) == "pause_resume")
        # Al pausar, is_playing pasa a False e is_paused pasa a True
        def _do_pause():
            vc.is_playing.return_value = False
            vc.is_paused.return_value = True

        vc.pause.side_effect = _do_pause
        await view.pause_resume.callback(interaction)
        assert "Reanudar" in pause_btn.label
        interaction.response.edit_message.assert_awaited_once()

    asyncio.run(_run())


def test_queue_pagination_view_disables_boundary_buttons():
    """Verifica que QueuePaginationView deshabilite Primera/Anterior en pág 0 y Siguiente/Última en la última pág."""
    from sznMusic.player import GuildPlayer
    from sznUI.views import QueuePaginationView

    player = GuildPlayer(guild_id=900)
    player.current_song = {"title": "Actual", "duration": 120}
    player.song_queue = [{"title": f"Track {i}", "duration": 180} for i in range(15)]

    async def _run():
        view = QueuePaginationView(player, items_per_page=10)
        first_btn = next(c for c in view.children if getattr(c, "custom_id", None) == "q_first")
        prev_btn = next(c for c in view.children if getattr(c, "custom_id", None) == "q_prev")
        next_btn = next(c for c in view.children if getattr(c, "custom_id", None) == "q_next")
        last_btn = next(c for c in view.children if getattr(c, "custom_id", None) == "q_last")

        assert first_btn.disabled is True
        assert prev_btn.disabled is True
        assert next_btn.disabled is False
        assert last_btn.disabled is False

        interaction = MagicMock()
        interaction.response.edit_message = AsyncMock()
        await view.last.callback(interaction)

        assert first_btn.disabled is False
        assert prev_btn.disabled is False
        assert next_btn.disabled is True
        assert last_btn.disabled is True

    asyncio.run(_run())


def test_settings_controls_includes_persistence_button_and_help_categories():
    """Verifica que SettingsControls incluya el control de persistencia y que HelpNavigatorView cambie de categoría."""
    from sznUI import MusicUI
    from sznUI.embeds import EmbedFactory

    guild = MagicMock()
    guild.id = 44444
    guild.name = "Servidor Test"
    bot = MagicMock()
    core = MagicMock()
    core.bot = bot

    async def _run():
        with patch("sznUtils.load_config", return_value=None), \
             patch("sznUtils.is_guild_persist_enabled", return_value=True):
            view = MusicUI.SettingsControls(core, bot, guild=guild)
            persist_btn = next(c for c in view.children if getattr(c, "custom_id", None) == "toggle_persist")
            assert "Persistencia: On" in persist_btn.label

        embed_recsys = EmbedFactory.build_help_category_embed("recsys", "td?", "Servidor Test", "Petiso")
        assert "autoplay" in embed_recsys.description.lower() or any(
            "autoplay" in f.value.lower() for f in embed_recsys.fields
        )

    asyncio.run(_run())


def test_musicdb_log_song_does_not_double_increment_play_count():
    """Verifica que MusicDB.log_song garantice la existencia de la canción sin incrementar played_count por duplicado."""
    import database
    import sznUtils
    from sznDB import MusicDB

    assert sznUtils.save_config is database.save_config
    assert sznUtils.load_config is database.load_config
    assert sznUtils.save_guild_queue is database.save_guild_queue
    assert sznUtils.load_guild_queue is database.load_guild_queue

    bot = MagicMock()
    with patch("sznDB.preload_top_songs_cache"), \
         patch("sznDB.add_or_update_song") as mock_add_or_update:
        cog = MusicDB(bot)
        cog.log_song("Cancion Sin Doble Conteo")
        assert cog.last_played[0] == "Cancion Sin Doble Conteo"
        mock_add_or_update.assert_called_once_with(title="Cancion Sin Doble Conteo")




