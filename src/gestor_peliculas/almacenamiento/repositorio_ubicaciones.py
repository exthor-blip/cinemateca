"""Acceso a la tabla de ubicaciones (las carpetas raiz de la coleccion)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ..modelos import Ubicacion, ahora

_COLUMNAS = "u.id, u.nombre, u.ruta, u.agregada_en, u.ultimo_escaneo"
_CONTEO = "(SELECT COUNT(*) FROM peliculas p WHERE p.ubicacion_id = u.id) AS cantidad"


def _fila_a_ubicacion(fila: sqlite3.Row) -> Ubicacion:
    return Ubicacion(
        id=fila["id"],
        nombre=fila["nombre"],
        ruta=Path(fila["ruta"]),
        agregada_en=fila["agregada_en"],
        ultimo_escaneo=fila["ultimo_escaneo"],
        cantidad_peliculas=fila["cantidad"] if "cantidad" in fila.keys() else 0,
    )


class RepositorioUbicaciones:
    def __init__(self, conexion: sqlite3.Connection) -> None:
        self.conexion = conexion

    def listar(self) -> list[Ubicacion]:
        filas = self.conexion.execute(
            f"SELECT {_COLUMNAS}, {_CONTEO} FROM ubicaciones u ORDER BY u.nombre COLLATE NOCASE"
        ).fetchall()
        return [_fila_a_ubicacion(f) for f in filas]

    def obtener(self, ubicacion_id: int) -> Ubicacion | None:
        fila = self.conexion.execute(
            f"SELECT {_COLUMNAS}, {_CONTEO} FROM ubicaciones u WHERE u.id = ?", (ubicacion_id,)
        ).fetchone()
        return _fila_a_ubicacion(fila) if fila else None

    def buscar_por_ruta(self, ruta: Path | str) -> Ubicacion | None:
        """Busca por ruta normalizada, para no dar de alta la misma carpeta dos veces."""
        clave = self.normalizar(ruta)
        fila = self.conexion.execute(
            f"SELECT {_COLUMNAS}, {_CONTEO} FROM ubicaciones u WHERE u.ruta = ?", (clave,)
        ).fetchone()
        return _fila_a_ubicacion(fila) if fila else None

    @staticmethod
    def normalizar(ruta: Path | str) -> str:
        """Forma canonica de una ruta: absoluta, sin barra final.

        En Windows da igual la caja, asi que se guarda tal como la escribio la
        persona pero se compara ya resuelta.
        """
        return str(Path(ruta).expanduser().resolve())

    def alta(self, ruta: Path | str, nombre: str = "") -> Ubicacion:
        """Da de alta una ubicacion, o devuelve la existente si ya estaba."""
        clave = self.normalizar(ruta)
        existente = self.buscar_por_ruta(clave)
        if existente:
            return existente

        etiqueta = nombre.strip() or Path(clave).name or clave
        cursor = self.conexion.execute(
            "INSERT INTO ubicaciones (nombre, ruta, agregada_en) VALUES (?, ?, ?)",
            (etiqueta, clave, ahora()),
        )
        self.conexion.commit()
        return Ubicacion(id=cursor.lastrowid, nombre=etiqueta, ruta=Path(clave), agregada_en=ahora())

    def marcar_escaneo(self, ubicacion_id: int) -> None:
        self.conexion.execute(
            "UPDATE ubicaciones SET ultimo_escaneo = ? WHERE id = ?", (ahora(), ubicacion_id)
        )
        self.conexion.commit()

    def renombrar(self, ubicacion_id: int, nombre: str) -> None:
        self.conexion.execute(
            "UPDATE ubicaciones SET nombre = ? WHERE id = ?", (nombre.strip(), ubicacion_id)
        )
        self.conexion.commit()

    def baja(self, ubicacion_id: int) -> int:
        """Borra la ubicacion y sus peliculas. No toca ningun archivo del disco."""
        from .repositorio_peliculas import RepositorioPeliculas

        peliculas = RepositorioPeliculas(self.conexion)
        ids = [p.id for p in peliculas.listar_por_ubicacion(ubicacion_id) if p.id]
        peliculas.baja_varias(ids)
        self.conexion.execute("DELETE FROM ubicaciones WHERE id = ?", (ubicacion_id,))
        self.conexion.commit()
        return len(ids)

    def vaciar(self) -> None:
        """Vacia el indice completo. Equivale al boton Vaciar indice del HTML."""
        self.conexion.executescript(
            """
            DELETE FROM peliculas_fts;
            DELETE FROM pelicula_etiquetas;
            DELETE FROM revisiones;
            DELETE FROM metadatos;
            DELETE FROM peliculas;
            DELETE FROM ubicaciones;
            """
        )
        self.conexion.commit()
