"""Lectura de los archivos que acompanan a una pelicula en su carpeta.

El contrato con el proyecto viejo se mantiene intacto: "IMDB linker 4.3.ps1"
escribe `imdb.url` y `poster.jpg` dentro de la carpeta de cada pelicula, y este
modulo es el que los lee. Asi el catalogo nuevo entiende una coleccion ya
procesada por el linker original sin convertir nada.

Soporta, igual que Mi_Cinemateca_1_14.html:
  - accesos directos .url en ASCII o en UTF-16 con BOM,
  - .nfo de Kodi con <uniqueid type="imdb"> o <imdbid>,
  - el identificador incrustado en el nombre del video o de la carpeta,
  - `poster.jpg` exacto, y como segunda opcion cualquier `poster*`.
"""

from __future__ import annotations

from pathlib import Path

from .. import registro
from ..nucleo import identificadores as ident
from ..nucleo.extensiones import es_imagen, es_sidecar, es_video
from ..nucleo.identificadores import extraer_imdb_id_de_nombre

log = registro.obtener(__name__)

#: Un sidecar mas grande que esto no es un acceso directo ni un .nfo.
TAMANIO_MAXIMO_SIDECAR = 2 * 1024 * 1024


def _ordenar_sidecars(rutas: list[Path]) -> list[Path]:
    """Primero los que se llaman imdb, que son los que escribe el linker."""
    return sorted(rutas, key=lambda r: (0 if "imdb" in r.stem.lower() else 1, r.name.lower()))


def leer_imdb_de_archivo(ruta: Path) -> str:
    """Devuelve el identificador IMDb de un sidecar, o '' si no lo tiene.

    No propaga errores de disco: un archivo bloqueado o ilegible significa
    "este archivo no aporta un identificador", no un fallo del programa.
    """
    try:
        if ruta.stat().st_size > TAMANIO_MAXIMO_SIDECAR:
            return ""
        return ident.extraer_imdb_de_sidecar(ruta.read_bytes())
    except OSError as error:
        log.debug("No se pudo leer el sidecar %s: %s", ruta, error)
        return ""


def buscar_imdb_id(archivos: list[Path], nombre_video: str = "", nombre_carpeta: str = "") -> str:
    """Busca el identificador IMDb de una pelicula en orden de confianza.

    1. Los sidecars de la carpeta, empezando por los llamados `imdb`.
    2. El nombre del archivo de video.
    3. El nombre de la carpeta.

    Es groupImdbId() del HTML.
    """
    for ruta in _ordenar_sidecars([a for a in archivos if es_sidecar(a.name)]):
        encontrado = leer_imdb_de_archivo(ruta)
        if encontrado:
            return encontrado

    return (ident.extraer_imdb_id_de_nombre(nombre_video)
            or ident.extraer_imdb_id_de_nombre(nombre_carpeta))


def buscar_poster(archivos: list[Path]) -> str:
    """Nombre del archivo de poster dentro de la carpeta, o ''.

    Prefiere `poster.jpg` exacto (el que escribe el linker) y si no, cualquier
    archivo que empiece con `poster`. Es posterOf() del HTML.
    """
    imagenes = [a for a in archivos if es_imagen(a.name)]
    if not imagenes:
        return ""

    for imagen in imagenes:
        if imagen.stem.lower() == "poster":
            return imagen.name

    for imagen in sorted(imagenes, key=lambda r: r.name.lower()):
        nombre = imagen.stem.lower()
        if nombre.startswith("poster") or nombre.startswith("folder") or nombre.startswith("cover"):
            return imagen.name

    # Una sola imagen en la carpeta de una pelicula es, casi siempre, su poster.
    return imagenes[0].name if len(imagenes) == 1 else ""


def _del_mismo_nombre(archivos: list[Path], raiz_video: str) -> list[Path]:
    """Archivos que acompanan a un video concreto por compartir su nombre.

    En una carpeta de saga conviven "shrek 1 - 2001.mkv" y "shrek 2 - 2004.mkv";
    si hay un "shrek 1 - 2001.jpg", es el poster del primero y no del segundo.
    """
    clave = raiz_video.lower()
    return [a for a in archivos if a.stem.lower() == clave]


def buscar_imdb_de_video(archivos: list[Path], nombre_video: str,
                         nombre_carpeta: str = "", compartida: bool = False) -> str:
    """Identificador IMDb de un video concreto.

    Args:
        archivos: todos los archivos de la carpeta.
        nombre_video: nombre del archivo de video.
        nombre_carpeta: nombre de la carpeta que lo contiene.
        compartida: True si la carpeta tiene mas de un video. En ese caso los
            sidecars sueltos (`imdb.url`) no se usan: un solo `imdb.url` no
            puede describir cuatro peliculas, y asignarlo a todas seria peor
            que dejarlas sin enlace.
    """
    raiz = Path(nombre_video).stem

    # Un sidecar con el nombre del video siempre gana: es inequivoco.
    propio = buscar_imdb_id(_del_mismo_nombre(archivos, raiz), nombre_video, "")
    if propio:
        return propio

    if compartida:
        return extraer_imdb_id_de_nombre(nombre_video)

    return buscar_imdb_id(archivos, nombre_video, nombre_carpeta)


def buscar_poster_de_video(archivos: list[Path], nombre_video: str,
                           compartida: bool = False) -> str:
    """Poster de un video concreto, con el mismo criterio que el identificador."""
    raiz = Path(nombre_video).stem

    propios = [a for a in _del_mismo_nombre(archivos, raiz) if es_imagen(a.name)]
    if propios:
        return propios[0].name

    return "" if compartida else buscar_poster(archivos)


def buscar_video(archivos: list[Path]) -> Path | None:
    """El archivo de video de la carpeta: el mas grande si hubiera varios."""
    videos = [a for a in archivos if es_video(a.name)]
    if not videos:
        return None
    if len(videos) == 1:
        return videos[0]

    def tamanio(ruta: Path) -> int:
        try:
            return ruta.stat().st_size
        except OSError:
            return 0

    return max(videos, key=tamanio)
