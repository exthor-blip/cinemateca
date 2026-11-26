"""Casos de uso de reproduccion."""

from __future__ import annotations

from pathlib import Path

from .. import registro
from ..almacenamiento.bd import BaseDatos
from ..config import Ajustes
from ..errores import ErrorDominio
from ..reproduccion import localizador_vlc, reproductor

log = registro.obtener(__name__)


class ServicioReproduccion:
    def __init__(self, bd: BaseDatos, ajustes: Ajustes) -> None:
        self.bd = bd
        self.ajustes = ajustes

    def _pelicula(self, pelicula_id: int):
        pelicula = self.bd.peliculas.obtener(pelicula_id)
        if pelicula is None:
            raise ErrorDominio("Esa pelicula no esta en el indice.")
        return pelicula

    def reproducir(self, pelicula_id: int) -> Path:
        """Abre el video en VLC. Devuelve la ruta que se abrio."""
        pelicula = self._pelicula(pelicula_id)
        return reproductor.reproducir(pelicula, ruta_vlc=self.ajustes.vlc_ruta)

    def abrir_carpeta(self, pelicula_id: int) -> Path:
        return reproductor.abrir_carpeta(self._pelicula(pelicula_id))

    def estado_vlc(self) -> tuple[bool, str]:
        """(disponible, ruta) para avisar en la interfaz si falta VLC."""
        ruta = localizador_vlc.localizar(self.ajustes.vlc_ruta)
        return (ruta is not None, str(ruta) if ruta else "")
