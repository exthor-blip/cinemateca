"""Recorrido del disco: encuentra las carpetas que contienen una pelicula.

Una pelicula es una carpeta con al menos un archivo de video. Es la misma
convencion que usaban las tres piezas del proyecto viejo, solo que aca el
recorrido es un generador: devuelve cada carpeta en cuanto la clasifica, para
que un indexado de miles de peliculas pueda informar progreso y cancelarse.

No escribe nada ni toca la base de datos.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from .. import registro
from ..nucleo.extensiones import es_subtitulo_por_extension, es_video
from ..nucleo.titulos import parsear_anio_titulo
from . import sidecars

log = registro.obtener(__name__)

#: Carpetas que nunca se recorren: metadatos de sistema, informes propios y
#: cachés de reproductores.
CARPETAS_IGNORADAS: frozenset[str] = frozenset({
    "$recycle.bin", "system volume information", ".git", "__pycache__",
    "_informes_organizador", "_informes", ".actors", "extrafanart", "extrathumbs",
    "subs", "subtitles", "sample", "samples", "featurettes", "trailers",
})


@dataclass(slots=True)
class CarpetaEscaneada:
    """Una carpeta del disco ya clasificada."""

    ruta: Path
    ruta_relativa: str
    archivos: list[Path] = field(default_factory=list)
    videos: list[Path] = field(default_factory=list)

    @property
    def nombre(self) -> str:
        return self.ruta.name

    @property
    def tiene_video(self) -> bool:
        return bool(self.videos)

    @property
    def ambigua(self) -> bool:
        """Mas de un video: no se puede decir cual es la pelicula."""
        return len(self.videos) > 1


@dataclass(slots=True)
class PeliculaEncontrada:
    """Lo que el escaner sabe de una pelicula antes de tocar la base de datos."""

    ruta_relativa: str
    carpeta: Path
    archivo_video: str
    titulo: str
    anio: str
    imdb_id: str = ""
    poster: str = ""
    tamanio_bytes: int = 0
    subtitulos: list[str] = field(default_factory=list)
    varios_videos: bool = False


def _ignorada(nombre: str) -> bool:
    return nombre.lower() in CARPETAS_IGNORADAS or nombre.startswith(".")


def recorrer(raiz: Path, *, cancelado: Callable[[], bool] | None = None,
             maxima_profundidad: int = 12) -> Iterator[CarpetaEscaneada]:
    """Recorre la raiz y devuelve cada carpeta con sus archivos del primer nivel.

    Usa os.scandir, que en Windows es bastante mas rapido que Path.iterdir
    porque reutiliza los datos del directorio. Salta enlaces simbolicos y
    puntos de union para no entrar en bucles, igual que ConvertAllToLowercase
    del Organizador.
    """
    raiz = Path(raiz)
    if not raiz.is_dir():
        return

    pendientes: list[tuple[Path, int]] = [(raiz, 0)]
    while pendientes:
        if cancelado and cancelado():
            return
        carpeta, profundidad = pendientes.pop()

        archivos: list[Path] = []
        try:
            with os.scandir(carpeta) as entradas:
                for entrada in entradas:
                    try:
                        if entrada.is_dir(follow_symlinks=False):
                            if profundidad < maxima_profundidad and not _ignorada(entrada.name):
                                pendientes.append((Path(entrada.path), profundidad + 1))
                        elif entrada.is_file(follow_symlinks=False):
                            archivos.append(Path(entrada.path))
                    except OSError:
                        continue
        except (OSError, PermissionError) as error:
            log.warning("No se pudo leer la carpeta %s: %s", carpeta, error)
            continue

        relativa = "" if carpeta == raiz else carpeta.relative_to(raiz).as_posix()
        yield CarpetaEscaneada(
            ruta=carpeta,
            ruta_relativa=relativa,
            archivos=archivos,
            videos=[a for a in archivos if es_video(a.name)],
        )


def analizar_carpeta(carpeta: CarpetaEscaneada,
                     nombre_ubicacion: str = "") -> list[PeliculaEncontrada]:
    """Convierte una carpeta escaneada en sus peliculas.

    Una carpeta con un solo video es una pelicula, y toma su titulo del nombre
    de la carpeta: es la convencion de toda la coleccion y la que usaba el
    proyecto original.

    Una carpeta con VARIOS videos son varias peliculas, una por archivo, y cada
    una toma su titulo del nombre de su archivo. Es el caso de las carpetas de
    saga ("- shrek" con "shrek 1 - 2001.mkv" y "shrek 2 - 2004.mkv") y el de
    una carpeta con videos sueltos. El proyecto original se quedaba con uno
    solo por carpeta y perdia el resto.
    """
    if not carpeta.videos:
        return []

    # La carpeta raiz de la ubicacion no tiene nombre propio util.
    nombre = carpeta.nombre if carpeta.ruta_relativa else (nombre_ubicacion or carpeta.nombre)
    compartida = len(carpeta.videos) > 1
    subtitulos = [a for a in carpeta.archivos if es_subtitulo_por_extension(a.name)]

    encontradas = []
    for video in sorted(carpeta.videos, key=lambda v: v.name.lower()):
        encontradas.append(_armar_pelicula(carpeta, video, nombre, compartida, subtitulos))
    return encontradas


def _armar_pelicula(carpeta: CarpetaEscaneada, video: Path, nombre_carpeta: str,
                    compartida: bool, subtitulos: list[Path]) -> PeliculaEncontrada:
    # Con varios videos manda el nombre del archivo; con uno solo, el de la
    # carpeta. Salvo en la raiz de la ubicacion, que es la coleccion entera y
    # no la carpeta de una pelicula: ahi siempre manda el nombre del archivo.
    en_la_raiz = not carpeta.ruta_relativa
    fuente_titulo = video.stem if (compartida or en_la_raiz) else nombre_carpeta
    analizado = parsear_anio_titulo(fuente_titulo)
    titulo, anio = analizado.titulo, analizado.anio

    # Si esa fuente no dio anio, se prueba con la otra.
    if not anio and not en_la_raiz:
        respaldo = parsear_anio_titulo(nombre_carpeta if compartida else video.stem)
        anio = respaldo.anio
        if not titulo:
            titulo = respaldo.titulo

    try:
        tamanio = video.stat().st_size
    except OSError:
        tamanio = 0

    if compartida:
        # Solo los subtitulos que comparten el nombre del video.
        propios = [s.name for s in subtitulos if s.stem.lower() == video.stem.lower()]
    else:
        propios = [s.name for s in subtitulos]

    return PeliculaEncontrada(
        ruta_relativa=carpeta.ruta_relativa,
        carpeta=carpeta.ruta,
        archivo_video=video.name,
        titulo=titulo or fuente_titulo or nombre_carpeta,
        anio=anio,
        imdb_id=sidecars.buscar_imdb_de_video(
            carpeta.archivos, video.name, nombre_carpeta, compartida=compartida
        ),
        poster=sidecars.buscar_poster_de_video(
            carpeta.archivos, video.name, compartida=compartida
        ),
        tamanio_bytes=tamanio,
        subtitulos=sorted(propios),
        varios_videos=compartida,
    )


def escanear(raiz: Path, *, nombre_ubicacion: str = "",
             cancelado: Callable[[], bool] | None = None,
             progreso: Callable[[int, str], None] | None = None) -> Iterator[PeliculaEncontrada]:
    """Devuelve las peliculas encontradas bajo la raiz.

    Args:
        raiz: carpeta de la ubicacion.
        nombre_ubicacion: nombre a usar si la raiz misma contiene el video.
        cancelado: funcion que devuelve True cuando hay que parar.
        progreso: recibe (carpetas_examinadas, nombre_actual) cada 20 carpetas.
    """
    examinadas = 0
    for carpeta in recorrer(raiz, cancelado=cancelado):
        examinadas += 1
        if progreso and examinadas % 20 == 0:
            progreso(examinadas, carpeta.nombre)
        yield from analizar_carpeta(carpeta, nombre_ubicacion)
    if progreso:
        progreso(examinadas, "")


def contar_carpetas(raiz: Path) -> int:
    """Cuenta carpetas para poder fijar el maximo de una barra de progreso."""
    return sum(1 for _ in recorrer(raiz))
