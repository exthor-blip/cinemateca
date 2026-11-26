"""Envio de archivos sobrantes a la Papelera de reciclaje.

El original usaba Microsoft.VisualBasic.FileIO.FileSystem.DeleteFile con
RecycleOption.SendToRecycleBin. Aca se usa send2trash, que hace lo mismo en
Windows (SHFileOperation) y tambien funciona en macOS y Linux.

La decision de diseno se conserva entera: NUNCA se borra de forma definitiva.
Todo va a la Papelera, de modo que cualquier error se puede deshacer desde el
Explorador. Y nada se toca sin que la persona confirme la extension y vea el
recuento y el peso total.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .. import registro
from .analizador import esta_protegido

log = registro.obtener(__name__)


@dataclass(slots=True)
class ResultadoLimpieza:
    enviados: int = 0
    fallidos: int = 0
    protegidos: int = 0
    bytes_liberados: int = 0
    simulado: bool = False
    errores: list[str] = field(default_factory=list)

    @property
    def megabytes(self) -> float:
        return round(self.bytes_liberados / (1024 * 1024), 2)

    def __str__(self) -> str:
        verbo = "Se enviarian" if self.simulado else "Enviados"
        return (f"{verbo} a la Papelera: {self.enviados} archivos ({self.megabytes} MB). "
                f"Errores: {self.fallidos}.")


def a_papelera(archivos: list[Path], *, simular: bool = False,
               cancelado: Callable[[], bool] | None = None,
               progreso: Callable[[int, str], None] | None = None) -> ResultadoLimpieza:
    """Manda los archivos a la Papelera. Nunca borra de forma definitiva."""
    resultado = ResultadoLimpieza(simulado=simular)

    for indice, archivo in enumerate(archivos, start=1):
        if cancelado and cancelado():
            break
        if progreso:
            progreso(indice, archivo.name)

        if esta_protegido(archivo):
            resultado.protegidos += 1
            continue

        try:
            tamanio = archivo.stat().st_size
        except OSError:
            tamanio = 0

        if simular:
            resultado.enviados += 1
            resultado.bytes_liberados += tamanio
            continue

        try:
            from send2trash import send2trash

            send2trash(str(archivo))
            resultado.enviados += 1
            resultado.bytes_liberados += tamanio
        except Exception as error:  # noqa: BLE001 - send2trash levanta de todo
            resultado.fallidos += 1
            resultado.errores.append(f"{archivo.name}: {error}")
            log.warning("No se pudo enviar %s a la Papelera: %s", archivo, error)

    log.info("Limpieza: %s", resultado)
    return resultado


def archivos_de_extensiones(grupos, extensiones: list[str]) -> list[Path]:
    """Los archivos de los grupos cuyas extensiones se eligieron."""
    elegidas = {e.strip().upper() for e in extensiones if e.strip()}
    seleccionados: list[Path] = []
    for grupo in grupos:
        if grupo.extension.upper() in elegidas:
            seleccionados.extend(grupo.archivos)
    return seleccionados
