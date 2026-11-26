"""Conversion de todos los nombres a minusculas.

Es ConvertAllToLowercase() de Organizador_Peliculas.ps1 (lineas 304-350). Los
cuidados del original, todos conservados porque cada uno evita un problema real:

  - La carpeta raiz elegida NO se renombra: es la que la persona indico.
  - Se saltean los enlaces simbolicos y puntos de union (reparse points), que
    de otro modo llevarian el recorrido fuera de la coleccion o a un bucle.
  - Se saltean los archivos ocultos, de sistema y los protegidos.
  - Primero los archivos y despues las carpetas, estas ordenadas de la ruta mas
    larga a la mas corta: renombrar una carpeta padre antes que sus hijas
    invalidaria las rutas de las hijas.
  - El renombrado pasa por un nombre temporal, porque NTFS no distingue la caja.

Se conservan las tildes y las enies: solo cambia la caja.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .. import registro
from .analizador import CARPETAS_PROTEGIDAS, esta_protegido
from .renombrador import Operacion, Resultado, renombrar_solo_caja

log = registro.obtener(__name__)

#: FILE_ATTRIBUTE_REPARSE_POINT
_REPARSE = 0x400
_OCULTO = 0x2
_SISTEMA = 0x4


@dataclass(slots=True)
class ResultadoMinusculas:
    convertidos: int = 0
    sin_cambios: int = 0
    conflictos: int = 0
    errores: int = 0
    simulado: bool = False
    operaciones: list[Operacion] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.convertidos + self.conflictos + self.errores

    def __str__(self) -> str:
        verbo = "Se convertirian" if self.simulado else "Convertidos"
        return (f"{verbo}: {self.convertidos}. Conflictos: {self.conflictos}. "
                f"Errores: {self.errores}.")


def _salteable(entrada: os.DirEntry) -> bool:
    try:
        atributos = entrada.stat(follow_symlinks=False).st_file_attributes  # type: ignore[attr-defined]
    except (OSError, AttributeError):
        # Fuera de Windows no hay atributos: basta con no seguir enlaces.
        try:
            return entrada.is_symlink()
        except OSError:
            return True
    return bool(atributos & _REPARSE or atributos & _OCULTO or atributos & _SISTEMA)


def _recolectar(raiz: Path, cancelado: Callable[[], bool] | None) -> tuple[list[Path], list[Path]]:
    """Devuelve (archivos, carpetas) que tienen alguna mayuscula en el nombre."""
    archivos: list[Path] = []
    carpetas: list[Path] = []
    pendientes = [raiz]

    while pendientes:
        if cancelado and cancelado():
            break
        actual = pendientes.pop()
        try:
            with os.scandir(actual) as entradas:
                for entrada in entradas:
                    if _salteable(entrada):
                        continue
                    ruta = Path(entrada.path)
                    try:
                        es_carpeta = entrada.is_dir(follow_symlinks=False)
                    except OSError:
                        continue
                    if es_carpeta:
                        if entrada.name.lower() in CARPETAS_PROTEGIDAS:
                            continue
                        carpetas.append(ruta)
                        pendientes.append(ruta)
                    elif not esta_protegido(ruta):
                        archivos.append(ruta)
        except (OSError, PermissionError) as error:
            log.warning("No se pudo recorrer %s: %s", actual, error)

    con_mayusculas = [a for a in archivos if a.name != a.name.lower()]
    # De la ruta mas larga a la mas corta: las hijas antes que las madres.
    carpetas_a_cambiar = sorted(
        (c for c in carpetas if c.name != c.name.lower()),
        key=lambda c: len(str(c)),
        reverse=True,
    )
    return con_mayusculas, carpetas_a_cambiar


def contar_pendientes(raiz: Path | str) -> tuple[int, int]:
    """(archivos, carpetas) con mayusculas, para mostrar antes de confirmar."""
    base = Path(raiz).expanduser()
    if not base.is_dir():
        return (0, 0)
    archivos, carpetas = _recolectar(base, None)
    return (len(archivos), len(carpetas))


def convertir(raiz: Path | str, *, simular: bool = False,
              cancelado: Callable[[], bool] | None = None,
              progreso: Callable[[int, int, str], None] | None = None) -> ResultadoMinusculas:
    """Pasa a minusculas los nombres bajo la raiz, sin tocar la raiz misma."""
    base = Path(raiz).expanduser()
    resultado = ResultadoMinusculas(simulado=simular)
    if not base.is_dir():
        return resultado

    archivos, carpetas = _recolectar(base, cancelado)
    total = len(archivos) + len(carpetas)
    hechos = 0

    for ruta in [*archivos, *carpetas]:
        if cancelado and cancelado():
            break
        hechos += 1
        if progreso:
            progreso(hechos, total, ruta.name)

        operacion = renombrar_solo_caja(ruta, ruta.name.lower(), simular=simular)
        resultado.operaciones.append(operacion)

        if operacion.resultado in (Resultado.RENOMBRADO, Resultado.SIMULADO):
            resultado.convertidos += 1
        elif operacion.resultado is Resultado.SIN_CAMBIOS:
            resultado.sin_cambios += 1
        elif operacion.resultado is Resultado.CONFLICTO:
            resultado.conflictos += 1
        else:
            resultado.errores += 1

    log.info("Minusculas en %s: %s", base, resultado)
    return resultado
