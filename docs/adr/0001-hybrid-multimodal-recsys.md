# ADR 0001: Motor de Recomendación Híbrido Multimodal (ALS + Item2Vec + Audio Features) con Serialización NPY Segura

- **Estado**: Aceptado
- **Fecha**: 2026-10-18

## Contexto y Problema
Tooodles requiere generar recomendaciones musicales personalizadas y continuas (`td?autoplay` y `td?favradio`) para usuarios individuales y grupos de oyentes en canales de voz de Discord, corriendo sobre instancias cloud ARM64 con recursos acotados (1 vCPU, < 1 GB RAM disponible para ML).

Depender exclusivamente de la API de recomendaciones de Spotify presenta tres limitaciones críticas:
1. No incorpora el historial implícito real del servidor (saltos tempranos `< 30s`, escuchas completas `≥ 80%`, `likes` y `dislikes` locales).
2. No modela la co-ocurrencia secuencial de canciones dentro de una misma sesión de escucha en Discord.
3. Introduce latencia de red externa y límites de cuota (HTTP 429) durante la transición entre pistas.

Por otro lado, serializar artefactos de modelos entrenados con `pickle` (`allow_pickle=True` en NumPy) expone la aplicación a ejecución remota de código (RCE) si el archivo de artefactos en el volumen compartido se ve comprometido.

## Alternativas Consideradas
1. **Solo API externa (Spotify Recommendations / Last.fm)**:
   - *Pros*: Cero cómputo local de entrenamiento.
   - *Contras*: Ignora la telemetría local (`PlayLog`, `UserDislike`), sufre bloqueos por rate-limiting y carece de embeddings de usuarios del servidor.
2. **Filtrado Colaborativo Puro (Solo Implicit ALS)**:
   - *Pros*: Excelente personalización usuario-canción.
   - *Contras*: Sufre ante cambios bruscos de género en una sesión (*vibe* inmediato) y no aprovecha características acústicas de canciones nuevas.
3. **Motor Híbrido Multimodal Offline/Online (Implicit ALS + Gensim Item2Vec + Audio Features) con `.npz` nativo sin Pickle (Elegida)**:
   - *Pros*: Combina personalización a largo plazo (ALS 256d), continuidad secuencial de sesión (Item2Vec 256d) y similitud acústica (8 features normalizados) en un vector multimodal de 520 dimensiones. Inferencia en memoria `< 10 ms` usando producto punto en NumPy y recarga atómica por `mtime`.

## Decisión
Adoptamos la arquitectura híbrida en dos fases (`recsys/train.py` offline cada 6 horas con `threadpoolctl=1` y `recsys/engine.py` online en memoria):
- **Espacio Multimodal de 520 dimensiones**: Concatenación ponderada de embeddings ALS (256d), Item2Vec (256d) y vectores acústicos (8d).
- **Serialización Segura (`allow_pickle=False`)**: Todos los metadatos de canciones e índices se exportan como arreglos tipados nativos de NumPy (`dtype=np.str_`, `dtype=np.int64`, `dtype=np.float32`) dentro de `data/recsys_artifacts.npz`, prohibiendo el uso de `pickle`.

## Consecuencias
- **Positivas**: Inferencia en `< 10 ms`, inmunidad ante deserialización insegura (CWE-502), soporte nativo para recomendación grupal promediando embeddings de los miembros del canal de voz y degradación elegante a *cold-start* ponderado cuando no existen artefactos previos.
- **Negativas / Trade-offs**: Requiere ejecutar el pipeline `python -m recsys.train` periódicamente (consumiendo ~50% de 1 vCPU durante < 2 minutos cada 6 horas).
