"""Fixtures compartidas por toda la suite."""

from __future__ import annotations

import gzip
from pathlib import Path

import pytest

from gestor_peliculas.almacenamiento.bd import BaseDatos

ACCESO_DIRECTO = "[InternetShortcut]\r\nURL=https://www.imdb.com/title/{id}/\r\n"
JPEG_MINIMO = bytes.fromhex("ffd8ffe000104a46494600010100000100010000ffd9")
PNG_MINIMO = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


@pytest.fixture()
def bd(tmp_path: Path):
    """Base de datos nueva en disco temporal, con el esquema aplicado."""
    base = BaseDatos(tmp_path / "prueba.db")
    yield base
    base.cerrar()


@pytest.fixture()
def coleccion(tmp_path: Path) -> Path:
    """Arbol de peliculas falso que cubre los casos del proyecto real.

    Reproduce a proposito las situaciones que el Organizador clasificaba en sus
    cuatro pestanas, mas los sidecars que escribe el linker.
    """
    raiz = tmp_path / "Peliculas"

    def crear(carpeta: str, archivos: dict[str, bytes | str]) -> None:
        destino = raiz / carpeta
        destino.mkdir(parents=True, exist_ok=True)
        for nombre, contenido in archivos.items():
            datos = contenido.encode("utf-8") if isinstance(contenido, str) else contenido
            (destino / nombre).write_bytes(datos)

    # Par completo: video, subtitulo, enlace IMDb y poster.
    crear("1975 - Tiburon", {
        "1975 - Tiburon.mkv": b"\x00" * 2048,
        "1975 - Tiburon.srt": "1\n00:00:01,000 --> 00:00:02,000\nHola\n",
        "imdb.url": ACCESO_DIRECTO.format(id="tt0073195"),
        "poster.jpg": JPEG_MINIMO,
    })
    # Solo video, sin sidecar ni poster: queda pendiente de enlazar.
    crear("1972 - El Padrino", {"1972 - El Padrino.avi": b"\x00" * 1024})
    # El ID viene en un .nfo de Kodi, no en un .url.
    crear("1994 - Pulp Fiction", {
        "pelicula.mp4": b"\x00" * 512,
        "pelicula.nfo": '<movie><uniqueid type="imdb">tt0110912</uniqueid></movie>',
        "poster.png": PNG_MINIMO,
    })
    # Nombre estilo scene: el anio esta suelto y el ID en el nombre del archivo.
    crear("The.Matrix.1999.1080p", {"The.Matrix.1999.1080p [tt0133093].mkv": b"\x00" * 256})
    # Dos videos: carpeta ambigua, no es una pelicula del catalogo.
    crear("2000 - Ambigua", {"parte1.mkv": b"\x00", "parte2.mkv": b"\x00"})
    # Sin video: se ignora.
    crear("_Notas", {"notas.md": "nada que ver aca"})
    # Video con archivos sueltos, para la pestana de limpieza del organizador.
    crear("1988 - Mi vecino Totoro (Japon)", {
        "1988 - Mi vecino Totoro (Japon).mkv": b"\x00" * 128,
        "muestra.nfo": "sin identificador aca",
        "basura.tmp": b"\x00",
        "publicidad.txt": "visitanos en ejemplo.invalid",
    })
    return raiz


@pytest.fixture()
def archivo_puntajes(tmp_path: Path) -> Path:
    """Un title.ratings.tsv.gz valido en miniatura."""
    destino = tmp_path / "title.ratings.tsv.gz"
    lineas = [
        "tconst\taverageRating\tnumVotes",
        "tt0073195\t8.1\t650000",
        "tt0068646\t9.2\t2000000",
        "tt0110912\t8.9\t2100000",
        "tt0133093\t8.7\t1900000",
        "tt9999999\t0.5\t0",          # sin votos: se descarta
        "tt8888888\t11.0\t100",       # fuera de rango: se descarta
    ]
    with gzip.open(destino, "wt", encoding="utf-8") as salida:
        salida.write("\n".join(lineas) + "\n")
    return destino
