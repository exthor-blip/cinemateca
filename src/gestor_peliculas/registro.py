"""Configuracion de logging: consola legible y archivo rotativo en la carpeta de datos."""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

FORMATO = "%(asctime)s  %(levelname)-7s  %(name)-34s  %(message)s"
FECHA = "%Y-%m-%d %H:%M:%S"
_configurado = False


def configurar(carpeta: Path | None = None, *, nivel: int = logging.INFO,
               nombre_archivo: str = "gestor.log") -> None:
    """Configura el logging raiz una sola vez por proceso."""
    global _configurado
    if _configurado:
        return

    raiz = logging.getLogger()
    raiz.setLevel(nivel)
    formato = logging.Formatter(FORMATO, datefmt=FECHA)

    consola = logging.StreamHandler()
    consola.setFormatter(formato)
    raiz.addHandler(consola)

    if carpeta is not None:
        try:
            carpeta.mkdir(parents=True, exist_ok=True)
            archivo = logging.handlers.RotatingFileHandler(
                carpeta / nombre_archivo, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
            )
            archivo.setFormatter(formato)
            raiz.addHandler(archivo)
        except OSError:
            raiz.warning("No se pudo abrir el archivo de registro en %s", carpeta)

    # Las librerias HTTP son muy verbosas en DEBUG.
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    _configurado = True


def obtener(nombre: str) -> logging.Logger:
    return logging.getLogger(nombre)
