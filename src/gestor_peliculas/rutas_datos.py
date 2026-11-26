r"""Ubicacion de los datos de la aplicacion en el disco.

La base de datos NO vive dentro del proyecto a proposito: el proyecto esta en
OneDrive y una base SQLite en carpeta sincronizada se corrompe o se queda
bloqueada. Por defecto todo va a %LOCALAPPDATA%\GestorPeliculas, y se puede
redirigir con la variable de entorno GESTOR_DATOS_DIR.
"""

from __future__ import annotations

import os
from pathlib import Path

NOMBRE_CARPETA = "GestorPeliculas"
NOMBRE_BD = "cinemateca.db"


def carpeta_datos(override: str | os.PathLike[str] | None = None) -> Path:
    """Devuelve la carpeta de datos, creandola si no existe."""
    if override:
        base = Path(override).expanduser()
    elif os.environ.get("GESTOR_DATOS_DIR"):
        base = Path(os.environ["GESTOR_DATOS_DIR"]).expanduser()
    else:
        raiz = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME")
        base = Path(raiz).expanduser() / NOMBRE_CARPETA if raiz else Path.home() / f".{NOMBRE_CARPETA}"
    base.mkdir(parents=True, exist_ok=True)
    return base


def ruta_bd(base: Path | None = None) -> Path:
    return (base or carpeta_datos()) / NOMBRE_BD


def carpeta_miniaturas(base: Path | None = None) -> Path:
    destino = (base or carpeta_datos()) / "miniaturas"
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def carpeta_registros(base: Path | None = None) -> Path:
    destino = (base or carpeta_datos()) / "registros"
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def carpeta_informes(base: Path | None = None) -> Path:
    """Informes del organizador cuando no se escriben junto a las peliculas."""
    destino = (base or carpeta_datos()) / "informes"
    destino.mkdir(parents=True, exist_ok=True)
    return destino
