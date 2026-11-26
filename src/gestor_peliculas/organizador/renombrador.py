"""Renombrado seguro de archivos y carpetas.

Porta SafeRename() y RenameCaseOnly() de Organizador_Peliculas.ps1. Los dos
problemas que resuelve, y que no son obvios:

1. **Cambios que solo afectan a las mayusculas.** NTFS no distingue la caja, asi
   que renombrar "PELICULA.MKV" a "pelicula.mkv" directamente falla o no hace
   nada. Hay que pasar por un nombre temporal. Si el segundo paso falla, se
   restaura el nombre original para no dejar el archivo con un nombre basura.

2. **Destinos ocupados.** Nunca se sobrescribe: si el destino ya existe y no es
   el propio archivo, la operacion se informa como conflicto y no se toca nada.

Se corrige de paso una inconsistencia del original: para los videos sueltos
comparaba el destino con `-cne` (sensible a la caja) mientras que para los
pares usaba OrdinalIgnoreCase. Eran dos criterios distintos para el mismo tipo
de conflicto; aca el criterio es uno solo.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from .. import registro

log = registro.obtener(__name__)

#: Cuantos nombres temporales se prueban antes de darse por vencido.
INTENTOS_TEMPORAL = 20


class Resultado(StrEnum):
    RENOMBRADO = "renombrado"
    SIN_CAMBIOS = "sin_cambios"
    CONFLICTO = "conflicto"
    ERROR = "error"
    SIMULADO = "simulado"

    @property
    def etiqueta(self) -> str:
        return {
            "renombrado": "Renombrado",
            "sin_cambios": "Ya estaba bien",
            "conflicto": "Conflicto: el destino ya existe",
            "error": "Error",
            "simulado": "Se renombraria",
        }[self.value]

    @property
    def exitoso(self) -> bool:
        return self in (Resultado.RENOMBRADO, Resultado.SIN_CAMBIOS, Resultado.SIMULADO)


@dataclass(slots=True)
class Operacion:
    """Un renombrado: que se queria hacer y que paso."""

    origen: Path
    destino: Path
    resultado: Resultado
    detalle: str = ""

    @property
    def nombre_origen(self) -> str:
        return self.origen.name

    @property
    def nombre_destino(self) -> str:
        return self.destino.name


def misma_ruta_exacta(uno: Path, otro: Path) -> bool:
    """Compara dos rutas respetando mayusculas y minusculas.

    Hace falta porque en Windows `Path("A.mkv") == Path("a.mkv")` devuelve True:
    PurePath compara sin distinguir la caja. Si se usara el == de Path, un
    archivo que solo hay que pasar a minusculas se daria por ya correcto y
    nunca se renombraria. Es la misma distincion que el original resolvia con
    -ceq y -cne, solo que aca se aplica en todos lados por igual.
    """
    return str(uno) == str(otro)


def _solo_cambia_la_caja(origen: Path, destino: Path) -> bool:
    return (not misma_ruta_exacta(origen, destino)
            and str(origen.parent) == str(destino.parent)
            and origen.name.lower() == destino.name.lower())


def destino_ocupado(destino: Path, origenes: list[Path]) -> bool:
    """True si el destino existe y no es uno de los archivos que se van a mover.

    Es DestinationOccupied() del original: dentro de un mismo lote, que el
    destino de un archivo sea el origen de otro no es conflicto, porque ese otro
    se va a mover.
    """
    if not destino.exists():
        return False
    clave = str(destino).lower()
    return all(str(origen).lower() != clave for origen in origenes)


def renombrar(origen: Path, destino: Path, *, simular: bool = False) -> Operacion:
    """Renombra un archivo o carpeta, sin sobrescribir nunca."""
    if misma_ruta_exacta(origen, destino):
        return Operacion(origen, destino, Resultado.SIN_CAMBIOS)

    if _solo_cambia_la_caja(origen, destino):
        return renombrar_solo_caja(origen, destino.name, simular=simular)

    if destino.exists():
        return Operacion(origen, destino, Resultado.CONFLICTO,
                         f"Ya existe {destino.name} en la carpeta.")

    if simular:
        return Operacion(origen, destino, Resultado.SIMULADO)

    try:
        origen.rename(destino)
        return Operacion(origen, destino, Resultado.RENOMBRADO)
    except OSError as error:
        log.warning("No se pudo renombrar %s: %s", origen, error)
        return Operacion(origen, destino, Resultado.ERROR, str(error))


def renombrar_solo_caja(origen: Path, nombre_nuevo: str, *, simular: bool = False) -> Operacion:
    """Cambia solo mayusculas y minusculas, en dos pasos con nombre temporal.

    Hace falta porque NTFS no distingue la caja: un rename directo de
    "Pelicula.mkv" a "pelicula.mkv" no sirve.
    """
    destino = origen.parent / nombre_nuevo

    if origen.name == nombre_nuevo:
        return Operacion(origen, destino, Resultado.SIN_CAMBIOS)

    if origen.name.lower() != nombre_nuevo.lower():
        # No es un cambio de caja: es un renombrado comun.
        return renombrar(origen, destino, simular=simular)

    if simular:
        return Operacion(origen, destino, Resultado.SIMULADO)

    temporal = _reservar_temporal(origen.parent)
    if temporal is None:
        return Operacion(origen, destino, Resultado.ERROR,
                         "No se pudo reservar un nombre temporal libre.")

    try:
        origen.rename(temporal)
    except OSError as error:
        return Operacion(origen, destino, Resultado.ERROR, str(error))

    try:
        temporal.rename(destino)
        return Operacion(origen, destino, Resultado.RENOMBRADO)
    except OSError as error:
        detalle = str(error)
        try:
            temporal.rename(origen)
        except OSError as segundo:
            detalle += f"; tampoco se pudo restaurar el nombre original: {segundo}"
        return Operacion(origen, destino, Resultado.ERROR, detalle)


def _reservar_temporal(carpeta: Path) -> Path | None:
    for _ in range(INTENTOS_TEMPORAL):
        candidato = carpeta / f".__organizador_tmp_{uuid.uuid4().hex}"
        if not candidato.exists():
            return candidato
    return None


def nombre_destino(carpeta: Path, extension: str, sufijo: str = "") -> Path:
    """El nombre que tiene que tomar un archivo: el de su carpeta.

    Es la regla del Organizador: el video y los subtitulos se llaman igual que
    la carpeta que los contiene, y el segundo subtitulo lleva el sufijo 1.
    """
    return carpeta / f"{carpeta.name}{sufijo}{extension}"
