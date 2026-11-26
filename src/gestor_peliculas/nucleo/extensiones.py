"""Extensiones de archivo reconocidas, unificadas para todo el proyecto.

Hoy las tres piezas del proyecto viejo no coinciden:
  - Organizador_Peliculas.ps1 incluye .flv y .3gp
  - Mi_Cinemateca_1_14.html no los incluye
  - el linker no mira archivos de video en absoluto
Se toma la union, que es la del Organizador, para que una pelicula en .flv no
quede fuera del catalogo.

Sobre .txt: en el Organizador estaba en la lista de subtitulos por extension,
asi que cualquier .txt junto a un video se renombraba como subtitulo. Aca .txt
queda fuera y pasa a depender de la deteccion por contenido
(organizador/deteccion_subtitulos.py), que reconoce SRT, WebVTT, SSA y ASS.
"""

from __future__ import annotations

from pathlib import Path

#: Contenedores de video que se consideran una pelicula.
VIDEO_EXT: frozenset[str] = frozenset({
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".m4v",
    ".mpg", ".mpeg", ".ts", ".webm", ".flv", ".3gp",
})

#: Subtitulos reconocidos por extension.
SUBTITULO_EXT: frozenset[str] = frozenset({
    ".srt", ".sub", ".ass", ".ssa", ".vtt", ".spa", ".idx",
})

#: Imagenes que pueden ser poster.
IMAGEN_EXT: frozenset[str] = frozenset({".jpg", ".jpeg", ".png", ".webp"})

#: Archivos que pueden contener un identificador IMDb (accesos directos, .nfo).
SIDECAR_EXT: frozenset[str] = frozenset({
    ".url", ".txt", ".webloc", ".website", ".nfo", ".desktop", ".inetloc", ".htm", ".html",
})

#: Formatos que el navegador no puede reproducir: se abren directamente en VLC.
SOLO_VLC_EXT: frozenset[str] = frozenset({".avi", ".mkv", ".wmv", ".flv", ".3gp", ".ts", ".mpg", ".mpeg"})


def _extension(nombre: str | Path) -> str:
    return Path(nombre).suffix.lower()


def es_video(nombre: str | Path) -> bool:
    return _extension(nombre) in VIDEO_EXT


def es_subtitulo_por_extension(nombre: str | Path) -> bool:
    return _extension(nombre) in SUBTITULO_EXT


def es_imagen(nombre: str | Path) -> bool:
    return _extension(nombre) in IMAGEN_EXT


def es_sidecar(nombre: str | Path) -> bool:
    """True para archivos que vale la pena abrir buscando un ID IMDb."""
    ruta = Path(nombre)
    if ruta.suffix.lower() in SIDECAR_EXT:
        return True
    # El HTML tambien aceptaba una carpeta/archivo llamado exactamente "imdb".
    return ruta.stem.lower() == "imdb" and not ruta.suffix


def necesita_vlc(nombre: str | Path) -> bool:
    return _extension(nombre) in SOLO_VLC_EXT
