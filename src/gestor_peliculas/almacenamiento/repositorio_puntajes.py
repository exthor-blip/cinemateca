"""Acceso a la tabla de puntajes del dataset no comercial de IMDb."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Sequence

from ..modelos import Puntaje


class RepositorioPuntajes:
    def __init__(self, conexion: sqlite3.Connection) -> None:
        self.conexion = conexion

    def obtener(self, imdb_id: str) -> Puntaje | None:
        if not imdb_id:
            return None
        fila = self.conexion.execute(
            "SELECT imdb_id, puntaje, votos FROM puntajes_imdb WHERE imdb_id = ?", (imdb_id,)
        ).fetchone()
        return Puntaje(fila["imdb_id"], fila["puntaje"], fila["votos"]) if fila else None

    def obtener_varios(self, ids: Sequence[str]) -> dict[str, Puntaje]:
        utiles = [i for i in ids if i]
        if not utiles:
            return {}
        marcas = ",".join("?" * len(utiles))
        filas = self.conexion.execute(
            f"SELECT imdb_id, puntaje, votos FROM puntajes_imdb WHERE imdb_id IN ({marcas})",
            tuple(utiles),
        ).fetchall()
        return {f["imdb_id"]: Puntaje(f["imdb_id"], f["puntaje"], f["votos"]) for f in filas}

    def guardar_lote(self, filas: Iterable[tuple[str, float, int]]) -> int:
        """Inserta o reemplaza un lote de puntajes. Devuelve cuantos escribio."""
        lote = list(filas)
        if not lote:
            return 0
        self.conexion.executemany(
            "INSERT INTO puntajes_imdb (imdb_id, puntaje, votos) VALUES (?, ?, ?) "
            "ON CONFLICT(imdb_id) DO UPDATE SET puntaje = excluded.puntaje, votos = excluded.votos",
            lote,
        )
        return len(lote)

    def contar(self) -> int:
        return self.conexion.execute("SELECT COUNT(*) FROM puntajes_imdb").fetchone()[0]

    def vaciar(self) -> None:
        self.conexion.execute("DELETE FROM puntajes_imdb")
        self.conexion.commit()
