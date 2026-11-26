"""Reconoce subtitulos por su contenido, no solo por la extension.

Es IsSubtitleFile() de Organizador_Peliculas.ps1 (lineas 113-124). La idea
original es buena: en una coleccion vieja hay subtitulos guardados sin
extension, y leer los primeros bytes alcanza para reconocer el formato.

Cambio deliberado respecto del original: ahi `.txt` estaba en la lista de
extensiones de subtitulo, asi que CUALQUIER .txt en la carpeta de una pelicula
se renombraba como si fuera un subtitulo. Un `notas.txt` o la publicidad que
meten los grupos de release terminaban convertidos en
"1975 - Tiburon.txt". Aca `.txt` tiene que demostrar que es un subtitulo:
pasa por la deteccion de contenido como cualquier archivo sin extension.
"""

from __future__ import annotations

import re
from pathlib import Path

from .. import registro
from ..nucleo.extensiones import SUBTITULO_EXT

log = registro.obtener(__name__)

#: Mas grande que esto no es un archivo de subtitulos.
TAMANIO_MAXIMO = 10 * 1024 * 1024

#: Cuantos bytes se leen para reconocer el formato.
MUESTRA = 4096

#: Extensiones que hay que verificar por contenido antes de aceptar.
EXTENSIONES_DUDOSAS = frozenset({"", ".txt", ".sub"})

PATRONES = (
    # SRT: numero de linea, salto, marca de tiempo con flecha.
    re.compile(r"^\s*\d+\s*\r?\n\s*\d{2}:\d{2}:\d{2}[,.]\d{3}\s*-->", re.MULTILINE),
    re.compile(r"^WEBVTT", re.MULTILINE),
    re.compile(r"^\[Script Info\]", re.MULTILINE),
    re.compile(r"^Dialogue:", re.MULTILINE),
    # MicroDVD: {inicio}{fin}texto
    re.compile(r"^\{\d+\}\{\d+\}", re.MULTILINE),
    # SubViewer / SAMI
    re.compile(r"^\[INFORMATION\]", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^<SAMI>", re.MULTILINE | re.IGNORECASE),
)


def parece_subtitulo(datos: bytes) -> bool:
    """True si el contenido tiene la pinta de un formato de subtitulos conocido."""
    if not datos:
        return False
    for codificacion in ("utf-8-sig", "utf-8", "utf-16", "latin-1"):
        try:
            texto = datos.decode(codificacion)
        except (UnicodeDecodeError, LookupError):
            continue
        if any(patron.search(texto) for patron in PATRONES):
            return True
        break
    return False


def es_subtitulo(ruta: Path) -> bool:
    """Decide si un archivo es un subtitulo.

    Las extensiones inequivocas (.srt, .ass, .ssa, .vtt, .spa, .idx) se aceptan
    sin abrir el archivo. Las dudosas (.txt, .sub y los archivos sin extension)
    tienen que demostrarlo por contenido.
    """
    extension = ruta.suffix.lower()
    if extension in SUBTITULO_EXT and extension not in EXTENSIONES_DUDOSAS:
        return True
    if extension not in EXTENSIONES_DUDOSAS:
        return False

    try:
        tamanio = ruta.stat().st_size
        if tamanio == 0 or tamanio > TAMANIO_MAXIMO:
            return False
        with ruta.open("rb") as archivo:
            return parece_subtitulo(archivo.read(MUESTRA))
    except OSError as error:
        log.debug("No se pudo inspeccionar %s: %s", ruta, error)
        return False


def extension_para(ruta: Path) -> str:
    """Extension con la que guardar un subtitulo reconocido.

    Un archivo sin extension cuyo contenido es SRT se guarda como .srt, igual
    que hacia el original (linea 156 del .ps1).
    """
    if ruta.suffix:
        return ruta.suffix
    try:
        with ruta.open("rb") as archivo:
            datos = archivo.read(MUESTRA)
    except OSError:
        return ".srt"

    for codificacion in ("utf-8-sig", "utf-8", "utf-16", "latin-1"):
        try:
            texto = datos.decode(codificacion)
        except (UnicodeDecodeError, LookupError):
            continue
        if texto.lstrip().startswith("WEBVTT"):
            return ".vtt"
        if "[Script Info]" in texto or "Dialogue:" in texto:
            return ".ass"
        break
    return ".srt"
