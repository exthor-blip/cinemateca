"""Extraccion y validacion de identificadores IMDb y TMDb.

Reune en un solo lugar lo que hoy esta repartido entre imdbId(), idFromName() y
extractImdb() del HTML y la validacion de URL de Show-ManualLastResort del
linker. Son funciones puras: reciben texto y devuelven texto.

El decodificado de archivos (BOM UTF-16, entidades HTML) vive aca porque es
donde esta el conocimiento del formato, pero no toca el disco: recibe bytes.
"""

from __future__ import annotations

import html
import re

#: Un identificador IMDb valido. Son 7 digitos o mas desde hace anios.
RE_IMDB_ID = re.compile(r"^tt\d{7,}$", re.IGNORECASE)

#: Un enlace IMDb dentro de texto libre, con o sin protocolo, con o sin www,
#: y admitiendo las variantes localizadas tipo /es/title/tt1234567/.
_RE_IMDB_URL = re.compile(
    r"(?:^|[^\w.@/+-])"
    r"(?:(?:https?:)?//)?"
    r"(?:www\.|m\.|akas\.)?imdb\.com/"
    r"(?:[a-z]{2}(?:-[a-z]{2})?/)?"
    r"title/(tt\d{7,})(?![\w-])",
    re.IGNORECASE,
)

#: Un ID suelto en un nombre de archivo o carpeta: "Pelicula [tt0073195].mkv".
_RE_EN_NOMBRE = re.compile(r"(?:^|[^a-z0-9])(tt\d{7,})(?=$|[^a-z0-9])", re.IGNORECASE)

#: Los .nfo de Kodi guardan el ID en una etiqueta propia.
_RE_NFO = re.compile(
    r"(?:<imdb(?:id|_id)>|<uniqueid\s+type=[\"']imdb[\"'][^>]*>)\s*(tt\d{7,})\s*<",
    re.IGNORECASE,
)

#: Una ficha de TMDb.
_RE_TMDB_URL = re.compile(
    r"(?:^|[^\w.@/+-])(?:(?:https?:)?//)?(?:www\.)?themoviedb\.org/movie/(\d+)",
    re.IGNORECASE,
)


def es_imdb_id(texto: str) -> bool:
    return bool(RE_IMDB_ID.match((texto or "").strip()))


def normalizar_imdb_id(texto: str) -> str:
    """Devuelve el ID en minusculas si el texto es exactamente un ID, o ''."""
    limpio = (texto or "").strip()
    return limpio.lower() if RE_IMDB_ID.match(limpio) else ""


def extraer_imdb_id(texto: str) -> str:
    """Busca un ID IMDb en texto libre: una URL, un ID suelto o un .nfo.

    Es imdbId() del HTML ampliado con el caso .nfo. Devuelve '' si no hay nada
    reconocible, nunca None, para que el resultado se pueda concatenar sin
    comprobar.
    """
    if not texto:
        return ""
    cadena = str(texto)

    coincidencia = _RE_IMDB_URL.search(cadena)
    if coincidencia:
        return coincidencia.group(1).lower()

    directo = normalizar_imdb_id(cadena)
    if directo:
        return directo

    coincidencia = _RE_NFO.search(cadena)
    if coincidencia:
        return coincidencia.group(1).lower()

    return ""


def extraer_imdb_id_de_nombre(nombre: str) -> str:
    """Busca un ID IMDb incrustado en un nombre de archivo o carpeta."""
    coincidencia = _RE_EN_NOMBRE.search(nombre or "")
    return coincidencia.group(1).lower() if coincidencia else ""


def extraer_tmdb_id(texto: str) -> int | None:
    coincidencia = _RE_TMDB_URL.search(str(texto or ""))
    if not coincidencia:
        return None
    try:
        valor = int(coincidencia.group(1))
    except ValueError:
        return None
    return valor if valor > 0 else None


def enlace_imdb(imdb_id: str) -> str:
    """URL canonica de una ficha IMDb, o '' si el ID no es valido."""
    limpio = normalizar_imdb_id(imdb_id)
    return f"https://www.imdb.com/title/{limpio}/" if limpio else ""


def enlace_tmdb(tmdb_id: int | None) -> str:
    return f"https://www.themoviedb.org/movie/{tmdb_id}" if tmdb_id else ""


def decodificar_texto(datos: bytes) -> str:
    """Decodifica el contenido de un sidecar a texto utilizable.

    Repite extractImdb() del HTML: los accesos directos de Windows pueden venir
    en UTF-16 con BOM, traen bytes nulos, y los .html guardados por el navegador
    escapan los caracteres como entidades. Nunca lanza: si nada funciona
    devuelve cadena vacia, porque un sidecar ilegible no es un error del
    programa sino un archivo que no sirve.
    """
    if not datos:
        return ""

    codificacion = "utf-8"
    if datos[:2] == b"\xff\xfe":
        codificacion = "utf-16-le"
    elif datos[:2] == b"\xfe\xff":
        codificacion = "utf-16-be"
    elif datos[:3] == b"\xef\xbb\xbf":
        codificacion = "utf-8-sig"

    try:
        texto = datos.decode(codificacion, errors="replace")
    except (UnicodeDecodeError, LookupError):
        texto = datos.decode("latin-1", errors="replace")

    texto = texto.replace("\x00", "")
    # Solo se resuelven las entidades numericas ASCII, igual que el HTML: el
    # objetivo es recomponer una URL escapada, no interpretar el documento.
    texto = re.sub(
        r"&#(x[\da-f]+|\d+);",
        lambda m: _entidad_ascii(m.group(1)),
        texto,
        flags=re.IGNORECASE,
    )
    return html.unescape(texto)


def _entidad_ascii(valor: str) -> str:
    try:
        codigo = int(valor[1:], 16) if valor[0].lower() == "x" else int(valor)
    except ValueError:
        return f"&#{valor};"
    return chr(codigo) if codigo < 128 else f"&#{valor};"


def extraer_imdb_de_sidecar(datos: bytes) -> str:
    """Decodifica un sidecar y devuelve el ID IMDb que contenga, o ''."""
    return extraer_imdb_id(decodificar_texto(datos))
