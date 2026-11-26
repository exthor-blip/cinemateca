"""Encuentra vlc.exe en el sistema.

Es FindVlc() de Mi_Cinemateca_VLC.cs portado, con el mismo orden de busqueda:

  1. la ruta configurada a mano en el .env (VLC_RUTA), que no existia antes y
     resuelve el caso de una instalacion portable;
  2. App Paths del registro, en HKCU y despues en HKLM;
  3. las carpetas habituales de Program Files, incluida la de 32 bits;
  4. el PATH, por si se instalo con un gestor de paquetes.

El resultado se recuerda durante la ejecucion: consultar el registro en cada
clic de "Video" no aporta nada.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from .. import registro

log = registro.obtener(__name__)

CLAVE_APP_PATHS = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\vlc.exe"

#: Rutas tipicas en Windows.
CANDIDATAS_WINDOWS = (
    r"C:\Program Files\VideoLAN\VLC\vlc.exe",
    r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
)

#: En otros sistemas el ejecutable se llama vlc y esta en el PATH.
NOMBRES = ("vlc.exe", "vlc", "VLC")

_recordada: Path | None = None
_buscada = False


def _desde_registro() -> Path | None:
    if sys.platform != "win32":
        return None
    try:
        import winreg
    except ImportError:
        return None

    for raiz in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(raiz, CLAVE_APP_PATHS) as clave:
                valor, _tipo = winreg.QueryValueEx(clave, "")
        except OSError:
            continue
        if valor:
            ruta = Path(str(valor).strip('"'))
            if ruta.is_file():
                return ruta
    return None


def _desde_program_files() -> Path | None:
    if sys.platform != "win32":
        return None
    carpetas = [
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
        os.environ.get("ProgramW6432"),
    ]
    for carpeta in carpetas:
        if not carpeta:
            continue
        ruta = Path(carpeta) / "VideoLAN" / "VLC" / "vlc.exe"
        if ruta.is_file():
            return ruta
    for texto in CANDIDATAS_WINDOWS:
        ruta = Path(texto)
        if ruta.is_file():
            return ruta
    return None


def _desde_path() -> Path | None:
    for nombre in NOMBRES:
        encontrado = shutil.which(nombre)
        if encontrado:
            return Path(encontrado)
    return None


def localizar(ruta_configurada: str = "", *, volver_a_buscar: bool = False) -> Path | None:
    """Devuelve la ruta de vlc.exe, o None si no esta instalado."""
    global _recordada, _buscada

    if ruta_configurada:
        ruta = Path(ruta_configurada.strip().strip('"')).expanduser()
        if ruta.is_file():
            return ruta
        # Pueden haber apuntado a la carpeta en lugar del ejecutable.
        if ruta.is_dir():
            for nombre in NOMBRES:
                candidata = ruta / nombre
                if candidata.is_file():
                    return candidata
        log.warning("VLC_RUTA apunta a %s, que no es un ejecutable valido", ruta)

    if _buscada and not volver_a_buscar:
        return _recordada

    _recordada = _desde_registro() or _desde_program_files() or _desde_path()
    _buscada = True
    if _recordada:
        log.info("VLC encontrado en %s", _recordada)
    else:
        log.info("No se encontro VLC en el sistema")
    return _recordada


def esta_instalado(ruta_configurada: str = "") -> bool:
    return localizar(ruta_configurada) is not None


def olvidar() -> None:
    """Borra la ruta recordada. Para los tests y para un reintento manual."""
    global _recordada, _buscada
    _recordada = None
    _buscada = False
