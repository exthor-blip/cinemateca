"""Ajustes de la aplicacion, leidos de .env y del entorno.

Regla: ninguna credencial vive en el codigo. El .env no se versiona.
Se acepta TMDB_READ_ACCESS_TOKEN como nombre alternativo porque es el que
ya usaba "IMDB linker 4.3.ps1", asi quien lo tenia definido no cambia nada.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from . import rutas_datos

# Raiz del proyecto: .../gestor-peliculas (tres niveles sobre este archivo)
RAIZ_PROYECTO = Path(__file__).resolve().parents[2]

_NOMBRES_TOKEN = ("TMDB_TOKEN", "TMDB_READ_ACCESS_TOKEN", "TMDB_API_KEY")


def _entero(nombre: str, por_defecto: int) -> int:
    valor = (os.environ.get(nombre) or "").strip()
    try:
        return int(valor) if valor else por_defecto
    except ValueError:
        return por_defecto


def _booleano(nombre: str, por_defecto: bool = False) -> bool:
    valor = (os.environ.get(nombre) or "").strip().lower()
    if not valor:
        return por_defecto
    return valor in {"1", "si", "sí", "true", "yes", "on"}


@dataclass(frozen=True)
class Ajustes:
    """Configuracion efectiva de una ejecucion."""

    credencial_tmdb: str = ""
    carpeta_datos: Path = field(default_factory=rutas_datos.carpeta_datos)
    ruta_bd: Path = field(default_factory=rutas_datos.ruta_bd)
    vlc_ruta: str = ""
    puerto: int = 5000
    host: str = "127.0.0.1"
    por_pagina: int = 60
    idioma_tmdb: str = "es-AR"
    pausa_entre_consultas: float = 0.3
    tiempo_espera_http: int = 25
    clave_secreta: str = ""
    depurar: bool = False

    @property
    def tiene_credencial_tmdb(self) -> bool:
        return bool(self.credencial_tmdb)

    @property
    def carpeta_miniaturas(self) -> Path:
        return rutas_datos.carpeta_miniaturas(self.carpeta_datos)

    @property
    def carpeta_registros(self) -> Path:
        return rutas_datos.carpeta_registros(self.carpeta_datos)


def cargar_ajustes(*, recargar_env: bool = True) -> Ajustes:
    """Lee .env (sin pisar variables ya presentes en el entorno) y arma los ajustes."""
    if recargar_env:
        load_dotenv(RAIZ_PROYECTO / ".env", override=False)

    credencial = ""
    for nombre in _NOMBRES_TOKEN:
        valor = (os.environ.get(nombre) or "").strip()
        if valor:
            credencial = valor
            break

    base = rutas_datos.carpeta_datos(os.environ.get("GESTOR_DATOS_DIR") or None)

    return Ajustes(
        credencial_tmdb=credencial,
        carpeta_datos=base,
        ruta_bd=rutas_datos.ruta_bd(base),
        vlc_ruta=(os.environ.get("VLC_RUTA") or "").strip().strip('"'),
        puerto=_entero("GESTOR_PUERTO", 5000),
        por_pagina=max(12, _entero("GESTOR_POR_PAGINA", 60)),
        clave_secreta=(os.environ.get("GESTOR_CLAVE_SECRETA") or "").strip(),
        depurar=_booleano("GESTOR_DEPURAR"),
    )
