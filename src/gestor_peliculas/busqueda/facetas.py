"""Valores disponibles para cada filtro, con su cantidad de peliculas.

Es refreshFilters() del HTML, pero resuelto en SQL. La diferencia practica es
que cada opcion viene con un conteo, asi se ve cuantas peliculas hay de cada
pais o genero antes de elegir.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Opcion:
    valor: str
    cantidad: int

    @property
    def etiqueta(self) -> str:
        return f"{self.valor} ({self.cantidad})"


@dataclass(slots=True)
class Facetas:
    """Las opciones de los cuatro desplegables del catalogo."""

    paises: list[Opcion]
    anios: list[Opcion]
    generos: list[Opcion]
    idiomas: list[Opcion]
    ubicaciones: list[tuple[int, str, int]]


def _por_tipo(conexion: sqlite3.Connection, tipo: str) -> list[Opcion]:
    filas = conexion.execute(
        """
        SELECT e.valor, COUNT(pe.pelicula_id) AS cantidad
        FROM etiquetas e
        JOIN pelicula_etiquetas pe ON pe.etiqueta_id = e.id
        WHERE e.tipo = ?
        GROUP BY e.valor
        HAVING cantidad > 0
        ORDER BY e.valor COLLATE NOCASE
        """,
        (tipo,),
    ).fetchall()
    return [Opcion(f["valor"], f["cantidad"]) for f in filas]


def _anios(conexion: sqlite3.Connection) -> list[Opcion]:
    """Anios presentes, del mas nuevo al mas viejo.

    Usa el anio de la ficha de TMDb cuando existe y el de la carpeta si no, que
    es el mismo criterio con el que se muestra en la tarjeta.
    """
    filas = conexion.execute(
        """
        SELECT anio, COUNT(*) AS cantidad FROM (
            SELECT COALESCE(NULLIF(m.anio, ''), p.anio_carpeta) AS anio
            FROM peliculas p
            LEFT JOIN metadatos m ON m.pelicula_id = p.id
        )
        WHERE anio <> ''
        GROUP BY anio
        ORDER BY anio DESC
        """
    ).fetchall()
    return [Opcion(f["anio"], f["cantidad"]) for f in filas]


def _ubicaciones(conexion: sqlite3.Connection) -> list[tuple[int, str, int]]:
    filas = conexion.execute(
        """
        SELECT u.id, u.nombre, COUNT(p.id) AS cantidad
        FROM ubicaciones u
        LEFT JOIN peliculas p ON p.ubicacion_id = u.id
        GROUP BY u.id
        ORDER BY u.nombre COLLATE NOCASE
        """
    ).fetchall()
    return [(f["id"], f["nombre"], f["cantidad"]) for f in filas]


def calcular(conexion: sqlite3.Connection) -> Facetas:
    return Facetas(
        paises=_por_tipo(conexion, "pais"),
        anios=_anios(conexion),
        generos=_por_tipo(conexion, "genero"),
        idiomas=_por_tipo(conexion, "idioma"),
        ubicaciones=_ubicaciones(conexion),
    )


@dataclass(slots=True)
class Resumen:
    """Los numeros de la linea de estado del catalogo."""

    total: int = 0
    visibles: int = 0
    con_ficha: int = 0
    sin_imdb: int = 0
    ubicaciones: int = 0
    con_puntaje: int = 0

    @property
    def pendientes(self) -> int:
        return max(0, self.total - self.con_ficha)

    def __str__(self) -> str:
        return (
            f"{self.total} peliculas en el indice - {self.visibles} visibles - "
            f"{self.ubicaciones} ubicaciones"
        )


def resumir(conexion: sqlite3.Connection, visibles: int = 0) -> Resumen:
    def uno(consulta: str) -> int:
        return conexion.execute(consulta).fetchone()[0]

    return Resumen(
        total=uno("SELECT COUNT(*) FROM peliculas"),
        visibles=visibles,
        con_ficha=uno("SELECT COUNT(*) FROM metadatos"),
        sin_imdb=uno("SELECT COUNT(*) FROM peliculas WHERE imdb_id = ''"),
        ubicaciones=uno("SELECT COUNT(*) FROM ubicaciones"),
        con_puntaje=uno(
            "SELECT COUNT(*) FROM peliculas p "
            "JOIN puntajes_imdb s ON s.imdb_id = p.imdb_id WHERE p.imdb_id <> ''"
        ),
    )
