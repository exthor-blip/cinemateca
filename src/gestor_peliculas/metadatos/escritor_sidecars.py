"""Escribe `imdb.url`, `tmdb.url` y `poster.jpg` en la carpeta de la pelicula.

Es Write-Result() y Write-ExternalResult() del linker. Mantener este contrato
intacto es importante: son los archivos que el catalogo lee al indexar, y los
que ya existen en la coleccion procesada con la version anterior.

Las tres reglas del original se conservan tal cual:

  - **Nunca se sobrescribe.** Si ya hay un `imdb.url`, no se toca. Un enlace que
    alguien puso a mano vale mas que uno que adivino un programa.
  - **`tmdb.url` solo si no hay `imdb.url`.** No se dejan dos enlaces que podrian
    apuntar a peliculas distintas.
  - **El poster se valida por bytes magicos** antes de promoverlo desde el
    temporal. Un archivo que dice ser .jpg pero no lo es no se guarda.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .. import registro
from ..errores import ErrorDominio, ErrorFuenteExterna
from ..nucleo import identificadores as ident
from . import posters
from .sesion_http import SesionHttp, sesion_compartida

log = registro.obtener(__name__)

NOMBRE_IMDB = "imdb.url"
NOMBRE_TMDB = "tmdb.url"
NOMBRE_POSTER = "poster.jpg"

#: Los accesos directos de Windows se escriben en ASCII con fin de linea CRLF,
#: igual que los del original, para que el Explorador los abra sin problemas.
PLANTILLA_ACCESO = "[InternetShortcut]\r\nURL={}\r\n"


@dataclass(slots=True)
class ResultadoEscritura:
    enlace_escrito: bool = False
    poster_escrito: bool = False
    ya_existia: bool = False
    simulado: bool = False
    detalle: str = ""

    @property
    def completo(self) -> bool:
        return self.enlace_escrito and self.poster_escrito

    def __str__(self) -> str:
        if self.simulado:
            partes = []
            if self.enlace_escrito:
                partes.append("se escribiria el enlace")
            if self.poster_escrito:
                partes.append("se bajaria el poster")
            return ", ".join(partes) or "no habria cambios"
        if self.ya_existia:
            return "ya tenia enlace: no se modifico"
        partes = []
        if self.enlace_escrito:
            partes.append("enlace guardado")
        if self.poster_escrito:
            partes.append("poster guardado")
        return ", ".join(partes) or "sin cambios"


def _escribir_acceso_directo(destino: Path, url: str, *, simular: bool) -> bool:
    if destino.exists():
        return False
    if simular:
        return True
    try:
        destino.write_text(PLANTILLA_ACCESO.format(url), encoding="ascii", newline="")
        return True
    except (OSError, UnicodeEncodeError) as error:
        log.warning("No se pudo escribir %s: %s", destino, error)
        return False


def escribir_imdb(carpeta: Path, imdb_id: str, *, poster_url: str = "",
                  simular: bool = False,
                  sesion: SesionHttp | None = None) -> ResultadoEscritura:
    """Escribe `imdb.url` y, si se puede, `poster.jpg`."""
    limpio = ident.normalizar_imdb_id(imdb_id)
    if not limpio:
        raise ErrorDominio(f"{imdb_id!r} no es un identificador IMDb valido.")
    if not carpeta.is_dir():
        raise ErrorDominio(f"La carpeta {carpeta} no esta disponible.")

    resultado = ResultadoEscritura(simulado=simular)
    archivo_imdb = carpeta / NOMBRE_IMDB

    if archivo_imdb.exists():
        resultado.ya_existia = True
        resultado.detalle = "Ya existe imdb.url; no se modifica."
    else:
        resultado.enlace_escrito = _escribir_acceso_directo(
            archivo_imdb, ident.enlace_imdb(limpio), simular=simular
        )

    resultado.poster_escrito = _intentar_poster(
        carpeta, poster_url, simular=simular, sesion=sesion
    )
    return resultado


def escribir_tmdb(carpeta: Path, tmdb_id: int, *, poster_url: str = "",
                  simular: bool = False,
                  sesion: SesionHttp | None = None) -> ResultadoEscritura:
    """Escribe `tmdb.url`, solo si no hay ya un `imdb.url`.

    Es la regla de Write-ExternalResult: no se dejan dos enlaces distintos en la
    misma carpeta, porque podrian apuntar a peliculas diferentes.
    """
    if not tmdb_id or tmdb_id <= 0:
        raise ErrorDominio("El identificador de TMDb no es valido.")
    if not carpeta.is_dir():
        raise ErrorDominio(f"La carpeta {carpeta} no esta disponible.")

    if (carpeta / NOMBRE_IMDB).exists():
        return ResultadoEscritura(
            ya_existia=True, simulado=simular,
            detalle="Ya existe imdb.url: no se agrega un enlace alternativo.",
        )

    resultado = ResultadoEscritura(simulado=simular)
    resultado.enlace_escrito = _escribir_acceso_directo(
        carpeta / NOMBRE_TMDB, ident.enlace_tmdb(tmdb_id), simular=simular
    )
    resultado.poster_escrito = _intentar_poster(
        carpeta, poster_url, simular=simular, sesion=sesion
    )
    return resultado


def _intentar_poster(carpeta: Path, poster_url: str, *, simular: bool,
                     sesion: SesionHttp | None) -> bool:
    """Descarga el poster si hace falta. Un fallo aca no es un error grave."""
    if not poster_url:
        return False
    if any((carpeta / f"poster{e}").exists() for e in (".jpg", ".jpeg", ".png", ".webp")):
        return False
    if simular:
        return True

    try:
        datos = (sesion or sesion_compartida()).descargar(poster_url, fuente="poster")
        # La comprobacion exacta del original: solo se guarda como .jpg lo que
        # realmente es un JPEG.
        if not posters.es_jpeg(datos):
            log.info("El poster de %s no es un JPEG: no se guarda", poster_url)
            return False
        return posters.guardar_poster(datos, carpeta, nombre=NOMBRE_POSTER) is not None
    except (ErrorFuenteExterna, OSError) as error:
        log.info("No se pudo bajar el poster: %s", error)
        return False


def tiene_enlace(carpeta: Path) -> bool:
    return (carpeta / NOMBRE_IMDB).exists() or (carpeta / NOMBRE_TMDB).exists()


def tiene_poster(carpeta: Path) -> bool:
    return any((carpeta / f"poster{e}").exists() for e in (".jpg", ".jpeg", ".png", ".webp"))
