"""Tokens visuales, paleta semántica y utilidades de formato para la interfaz de Tooodles."""


class UITheme:
    """Paleta de tokens de color semánticos e indicadores visuales para Discord Embeds."""

    PRIMARY = 0x7D5FFF       # Violeta eléctrico (Reproductor, Cola, Diagnóstico)
    SPOTIFY = 0x1DB954       # Verde esmeralda (Spotify, Éxito, Confirmaciones)
    RADIO_ML = 0x8A2BE2      # Amatista profundo (Autoplay IA, Radio Automática)
    COLLECTION = 0x00D2D3    # Cian brillante (Playlists, Favoritas, Ranking/Historial)
    WARNING = 0xFFA801       # Ámbar (Advertencias, Modo Edición, Solicitudes pendientes)
    DANGER = 0xFF3F34        # Carmesí (Errores, Modo Eliminación, Detención)

    FOOTER_BRAND = "Tooodles Music Engine"


def format_duration(seconds: int | float | None) -> str:
    """Formatea una duración en segundos a cadena MM:SS o indica transmisión en vivo.

    Args:
        seconds: Duración total en segundos.

    Returns:
        Cadena formateada ``M:SS`` o ``EN VIVO`` cuando el valor es 0 o nulo.
    """
    if not seconds or seconds <= 0:
        return "EN VIVO"
    mins = int(seconds) // 60
    secs = int(seconds) % 60
    return f"{mins}:{secs:02d}"


def render_progress_bar(elapsed_sec: int, duration_sec: int, length: int = 12) -> str:
    """Construye una barra de progreso visual con deslizador para embeds de reproducción.

    Args:
        elapsed_sec: Segundos transcurridos de la canción actual.
        duration_sec: Duración total de la canción en segundos.
        length: Longitud de bloques de la barra (por defecto 12).

    Returns:
        Bloque formateado con tiempo transcurrido/total y barra visual.
    """
    elapsed_clean = max(0, int(elapsed_sec))
    elapsed_str = format_duration(elapsed_clean) if duration_sec > 0 else f"{elapsed_clean // 60}:{elapsed_clean % 60:02d}"
    if not duration_sec or duration_sec <= 0:
        return f"`{elapsed_str}` 🔴 **EN VIVO**"

    total_str = format_duration(duration_sec)
    ratio = min(1.0, max(0.0, elapsed_clean / float(duration_sec)))
    filled = int(length * ratio)
    bar_track = f"`{'▬' * filled}🔘{'▬' * (length - filled)}`"
    return f"`{elapsed_str} / {total_str}`\n{bar_track}"
