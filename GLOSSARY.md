# 📖 Glosario de Dominio Ubicuo (DDD) — Tooodles

Este documento define el vocabulario ubicuo del dominio de **Tooodles** para mantener consistencia estricta entre modelos de datos, lógica de reproducción, motor de recomendación ML e interfaz de Discord.

| Término de Dominio | Símbolo / Entidad en Código | Definición Precisa |
|--------------------|-----------------------------|--------------------|
| **GuildPlayer** | `sznMusic.player.GuildPlayer` | Agregado de estado de reproducción aislado por servidor de Discord (`guild_id`). Encapsula la cola activa (`song_queue`), pista en curso (`current_song`), conexión de voz (`voice_client`), referencia al panel activo (`now_playing_message`), candado asíncrono (`play_lock`) y banderas de modo (`radio_mode`, `autoplay_mode`). |
| **MusicCore** | `sznMusic.MusicCore` | Cog central de reproducción que coordina los `GuildPlayer` de cada servidor, la extracción de audio con `yt-dlp`, la resolución de metadatos de Spotify y los bucles de mantenimiento en segundo plano. |
| **EmbedFactory** | `sznUI.embeds.EmbedFactory` | Fábrica centralizada que construye todos los `discord.Embed` del sistema (Reproductor, Cola Paginada, Colecciones, Ajustes, Ayuda por Categorías, Playlists y Precarga) bajo la paleta semántica `UITheme`. |
| **UITheme** | `sznUI.theme.UITheme` | Sistema de tokens de color semánticos (`PRIMARY`, `SPOTIFY`, `RADIO_ML`, `COLLECTION`, `WARNING`, `DANGER`) e indicadores de progreso para la capa de presentación en Discord. |
| **Hybrid RecSys Engine** | `recsys.engine.RecSysEngine` | Motor de inferencia en tiempo real (< 10 ms) que combina filtrado colaborativo **Implicit ALS** (256 dims), embeddings secuenciales **Item2Vec** (256 dims) y **Audio Features** acústicos (8 dims) en un espacio multimodal de 520 dimensiones. |
| **Autoplay ML** | `player.autoplay_mode` | Modo continuo impulsado por `RecSysEngine.get_autoplay_recommendations()` que pondera continuidad de *vibe* (70% Item2Vec + Audio) y personalización de oyentes activos en el canal de voz (30% ALS). |
| **Spotify Radio** | `player.radio_mode` | Modo de descubrimiento basado en el grafo de artistas y géneros de Spotify (`GENRE_EXPANSION` de 3 capas en `sznMusic/radio.py`). |
| **FavRadio (Radio Grupal)** | `sznDB.MusicDB.favradio` | Radio colaborativa armada a partir de la intersección y muestreo controlado por temperatura (`temp`) de las canciones favoritas (`UserLike`) de los miembros presentes en el canal de voz. |
| **3-Tier Queue Buffering** | `schedule_queue_optimizations` / `prefetch_chunk_throttled` | Estrategia de pre-carga en 3 niveles: Pista 1 en streaming Opus directo, Pista 2 descargada atómicamente a `/tmp/cache_*.webm` (`.tmp` → `.webm`) con análisis acústico local, y Pistas 3+ con pre-resolución de URL. |
| **Graceful Drain** | `main.graceful_shutdown` | Protocolo de apagado sin tiempo de inactividad ante señales `SIGTERM`/`SIGINT`: activa `bot.is_draining`, persiste las colas activas en base de datos y espera a que concluya la canción en curso antes de cerrar el contenedor. |
| **Queue Persistence** | `save_guild_queue` / `load_guild_queue` | Serialización JSON de la pista actual y la cola pendiente en `AppConfig` (`queue_{guild_id}`), restaurada automáticamente al reconectar con `td?j`. |
| **Trusted User** | `database.TrustedUser` | Usuario autorizado explícitamente por el dueño del bot para ejecutar comandos de telemetría, logs (`td?logs`), diagnóstico (`td?debug`) y reentrenamiento (`td?train`) vía Mensaje Directo (DM). |
| **PlayLog Telemetry** | `database.PlayLog` | Registro de eventos de escucha que captura duración efectiva reproducida (`listened_duration`), indicador de completitud (`completed` ≥ 80%) y segundo exacto de salto (`skipped_at`) para alimentar la matriz de confianza de ALS. |
