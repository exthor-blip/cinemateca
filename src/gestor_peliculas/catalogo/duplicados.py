"""Deteccion de peliculas repetidas en el catalogo.

El HTML original resolvia esto con tres mecanismos: isSameEntry() de la File
System Access API para reconocer el mismo archivo fisico en otra ruta, un Set
de identificadores IMDb ya vistos, y uniqueMovies() que al dibujar colapsaba
por identificador quedandose con la entrada mas completa.

Con backend no hay handles de navegador, asi que la identidad se decide por:
  1. identificador IMDb, cuando lo hay (la senal mas fuerte),
  2. nombre de archivo mas tamanio en bytes (misma copia en otra carpeta),
  3. la ruta, que siempre es unica.

A diferencia del original, aca las dos copias se CONSERVAN en el catalogo: dos
discos con la misma pelicula son un hecho de la coleccion, y perder la segunda
significaria no poder reproducirla si el otro disco no esta conectado. Lo que
se hace es agruparlas para mostrar una sola tarjeta.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from ..modelos import Pelicula


def clave_identidad(pelicula: Pelicula) -> str:
    """Clave con la que dos registros se consideran la misma pelicula."""
    if pelicula.imdb_id:
        return f"imdb:{pelicula.imdb_id}"
    if pelicula.archivo_video and pelicula.tamanio_bytes:
        return f"archivo:{pelicula.archivo_video.lower()}:{pelicula.tamanio_bytes}"
    return f"ruta:{pelicula.ubicacion_id}:{pelicula.ruta_relativa.lower()}"


def _puntaje_completitud(pelicula: Pelicula) -> tuple[int, int, int]:
    """Cuan completa esta una copia, para elegir cual representa al grupo.

    Es el score de uniqueMovies() del HTML: ficha completa pesa mas que poster,
    y poster mas que nada. Se desempata por tamanio, que suele indicar mejor
    calidad de copia.
    """
    return (
        2 if pelicula.tiene_ficha else 0,
        1 if pelicula.poster_relativo else 0,
        pelicula.tamanio_bytes,
    )


def agrupar(peliculas: Iterable[Pelicula]) -> dict[str, list[Pelicula]]:
    """Agrupa las peliculas por identidad, en el orden en que llegaron."""
    grupos: dict[str, list[Pelicula]] = {}
    for pelicula in peliculas:
        grupos.setdefault(clave_identidad(pelicula), []).append(pelicula)
    return grupos


def unicas(peliculas: Iterable[Pelicula]) -> list[Pelicula]:
    """Una pelicula por identidad: la copia mas completa de cada grupo.

    Equivale a uniqueMovies() del HTML.
    """
    elegidas: list[Pelicula] = []
    for copias in agrupar(peliculas).values():
        elegidas.append(max(copias, key=_puntaje_completitud))
    return elegidas


def contar_duplicadas(peliculas: Sequence[Pelicula]) -> int:
    """Cuantos registros son copia de otro ya presente."""
    return len(peliculas) - len(agrupar(peliculas))


def copias_de(pelicula: Pelicula, catalogo: Iterable[Pelicula]) -> list[Pelicula]:
    """Las otras copias de la misma pelicula dentro del catalogo."""
    clave = clave_identidad(pelicula)
    return [
        otra for otra in catalogo
        if otra.id != pelicula.id and clave_identidad(otra) == clave
    ]
