"""Conexion a SQLite, aplicacion del esquema y migraciones.

Decisiones:
- WAL, para que un indexado largo no bloquee la lectura de la web.
- foreign_keys ON, que en SQLite viene apagado por defecto.
- La version del esquema vive en user_version, y cada migracion es una funcion
  en MIGRACIONES. Asi no hace falta una dependencia como Alembic.
- Si FTS5 no estuviera disponible, la base se crea igual y la busqueda cae a
  LIKE (ver busqueda/consultas.py). En esta maquina FTS5 esta compilado.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from importlib import resources
from pathlib import Path

from .. import registro
from ..errores import ErrorAlmacenamiento

log = registro.obtener(__name__)

VERSION_ESQUEMA = 1
_MIGRACIONES: dict[int, Callable[[sqlite3.Connection], None]] = {}


def registrar_migracion(version: int) -> Callable[[Callable[[sqlite3.Connection], None]],
                                                  Callable[[sqlite3.Connection], None]]:
    """Decorador para declarar la migracion que lleva de version-1 a version."""

    def envoltura(funcion: Callable[[sqlite3.Connection], None]):
        _MIGRACIONES[version] = funcion
        return funcion

    return envoltura


def _leer_esquema() -> str:
    return resources.files("gestor_peliculas.almacenamiento").joinpath("esquema.sql").read_text(
        encoding="utf-8"
    )


def soporta_fts5(conexion: sqlite3.Connection) -> bool:
    try:
        conexion.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _prueba_fts USING fts5(a)")
        conexion.execute("DROP TABLE IF EXISTS _prueba_fts")
        return True
    except sqlite3.OperationalError:
        return False


def conectar(ruta: Path | str, *, solo_lectura: bool = False) -> sqlite3.Connection:
    """Abre una conexion configurada. No aplica el esquema: eso lo hace abrir()."""
    ruta = Path(ruta)
    try:
        if solo_lectura:
            conexion = sqlite3.connect(f"file:{ruta.as_posix()}?mode=ro", uri=True,
                                       check_same_thread=False)
        else:
            ruta.parent.mkdir(parents=True, exist_ok=True)
            conexion = sqlite3.connect(ruta, check_same_thread=False, timeout=15.0)
    except sqlite3.Error as error:
        raise ErrorAlmacenamiento(f"No se pudo abrir la base de datos en {ruta}: {error}") from error

    conexion.row_factory = sqlite3.Row
    conexion.execute("PRAGMA foreign_keys = ON")
    if not solo_lectura:
        conexion.execute("PRAGMA journal_mode = WAL")
        conexion.execute("PRAGMA synchronous = NORMAL")
    return conexion


def abrir(ruta: Path | str) -> sqlite3.Connection:
    """Abre la base, crea el esquema si falta y aplica las migraciones pendientes."""
    conexion = conectar(ruta)
    try:
        version = conexion.execute("PRAGMA user_version").fetchone()[0]
        if version == 0 and not _tiene_tablas(conexion):
            log.info("Creando el esquema de la base en %s", ruta)
            conexion.executescript(_leer_esquema())
            conexion.execute(f"PRAGMA user_version = {VERSION_ESQUEMA}")
            conexion.commit()
        else:
            _migrar(conexion, version)
    except sqlite3.Error as error:
        conexion.close()
        raise ErrorAlmacenamiento(f"No se pudo preparar la base de datos: {error}") from error
    return conexion


def _tiene_tablas(conexion: sqlite3.Connection) -> bool:
    fila = conexion.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'peliculas'"
    ).fetchone()
    return fila is not None


def _migrar(conexion: sqlite3.Connection, desde: int) -> None:
    if desde >= VERSION_ESQUEMA:
        return
    # Una base preexistente sin user_version se considera ya en la version 1.
    if desde == 0:
        conexion.execute(f"PRAGMA user_version = {VERSION_ESQUEMA}")
        conexion.commit()
        return
    for version in range(desde + 1, VERSION_ESQUEMA + 1):
        migracion = _MIGRACIONES.get(version)
        if migracion is None:
            continue
        log.info("Aplicando migracion a la version %s", version)
        migracion(conexion)
        conexion.execute(f"PRAGMA user_version = {version}")
        conexion.commit()


@contextmanager
def transaccion(conexion: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Commit al salir bien, rollback ante cualquier excepcion."""
    try:
        yield conexion
    except Exception:
        conexion.rollback()
        raise
    else:
        conexion.commit()


class BaseDatos:
    """Envoltorio con la conexion y los repositorios ya instanciados.

    Es lo que reciben los servicios, para no tener que pasar la conexion suelta
    por todas partes.
    """

    def __init__(self, ruta: Path | str) -> None:
        self.ruta = Path(ruta)
        self.conexion = abrir(self.ruta)
        self.fts_disponible = soporta_fts5(self.conexion)

        from .repositorio_metadatos import RepositorioMetadatos
        from .repositorio_peliculas import RepositorioPeliculas
        from .repositorio_puntajes import RepositorioPuntajes
        from .repositorio_ubicaciones import RepositorioUbicaciones

        self.ubicaciones = RepositorioUbicaciones(self.conexion)
        self.peliculas = RepositorioPeliculas(self.conexion)
        self.metadatos = RepositorioMetadatos(self.conexion)
        self.puntajes = RepositorioPuntajes(self.conexion)

    def cerrar(self) -> None:
        try:
            self.conexion.close()
        except sqlite3.Error:
            pass

    def __enter__(self) -> BaseDatos:
        return self

    def __exit__(self, *_excepcion: object) -> None:
        self.cerrar()
