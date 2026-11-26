"""Acceso a la tabla de metadatos y a las etiquetas normalizadas."""

from __future__ import annotations

import sqlite3

from ..modelos import Metadatos, ahora
from .repositorio_peliculas import RepositorioPeliculas


class RepositorioMetadatos:
    def __init__(self, conexion: sqlite3.Connection) -> None:
        self.conexion = conexion
        self._peliculas = RepositorioPeliculas(conexion)

    def obtener(self, pelicula_id: int) -> Metadatos | None:
        fila = self.conexion.execute(
            "SELECT * FROM metadatos WHERE pelicula_id = ?", (pelicula_id,)
        ).fetchone()
        if not fila:
            return None
        etiquetas = self._peliculas.etiquetas_de(pelicula_id)
        return Metadatos(
            tmdb_id=fila["tmdb_id"],
            titulo=fila["titulo"] or "",
            titulo_original=fila["titulo_original"] or "",
            anio=fila["anio"] or "",
            paises=etiquetas.get("pais", []),
            generos=etiquetas.get("genero", []),
            idiomas=etiquetas.get("idioma", []),
            director=fila["director"] or "",
            duracion_min=fila["duracion_min"],
            sinopsis=fila["sinopsis"] or "",
            idiomas_verificados=bool(fila["idiomas_verificados"]),
            actualizado_en=fila["actualizado_en"] or "",
        )

    def guardar(self, pelicula_id: int, metadatos: Metadatos) -> None:
        """Guarda la ficha y sus etiquetas, y rehace el indice de texto."""
        self.conexion.execute(
            """
            INSERT INTO metadatos
                (pelicula_id, tmdb_id, titulo, titulo_original, anio, director,
                 duracion_min, sinopsis, idiomas_verificados, actualizado_en)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(pelicula_id) DO UPDATE SET
                tmdb_id = excluded.tmdb_id,
                titulo = excluded.titulo,
                titulo_original = excluded.titulo_original,
                anio = excluded.anio,
                director = excluded.director,
                duracion_min = excluded.duracion_min,
                sinopsis = excluded.sinopsis,
                idiomas_verificados = excluded.idiomas_verificados,
                actualizado_en = excluded.actualizado_en
            """,
            (
                pelicula_id, metadatos.tmdb_id, metadatos.titulo, metadatos.titulo_original,
                metadatos.anio, metadatos.director, metadatos.duracion_min, metadatos.sinopsis,
                int(metadatos.idiomas_verificados), metadatos.actualizado_en or ahora(),
            ),
        )
        self._peliculas.reemplazar_etiquetas(pelicula_id, {
            "pais": metadatos.paises,
            "genero": metadatos.generos,
            "idioma": metadatos.idiomas,
        })
        self._peliculas._sincronizar_fts(pelicula_id)
        self.conexion.commit()

    def borrar(self, pelicula_id: int) -> None:
        self.conexion.execute("DELETE FROM metadatos WHERE pelicula_id = ?", (pelicula_id,))
        self.conexion.execute(
            "DELETE FROM pelicula_etiquetas WHERE pelicula_id = ?", (pelicula_id,)
        )
        self._peliculas._sincronizar_fts(pelicula_id)
        self.conexion.commit()

    def limpiar_etiquetas_huerfanas(self) -> int:
        """Borra etiquetas que ya no usa ninguna pelicula, para que los filtros no mientan."""
        cursor = self.conexion.execute(
            "DELETE FROM etiquetas WHERE id NOT IN (SELECT etiqueta_id FROM pelicula_etiquetas)"
        )
        self.conexion.commit()
        return cursor.rowcount or 0
