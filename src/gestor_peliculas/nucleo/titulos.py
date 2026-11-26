"""Parseo y normalizacion de titulos y anios a partir de nombres de carpeta.

Unifica las tres convenciones que hoy conviven en el proyecto viejo:

  1. "IMDB linker 4.3.ps1" exige el formato estricto ANIO - TITULO y descarta
     en silencio todo lo demas.
  2. "Mi_Cinemateca_1_14.html" acepta el anio en cualquier posicion y limpia
     el prefijo "ANIO - " o el sufijo "(ANIO)".
  3. "Organizador_Peliculas.ps1" no parsea nada: usa el nombre de carpeta tal cual.

parsear_anio_titulo() acepta las tres y dice de donde salio el anio, asi quien
necesite ser estricto (el vinculador, que no puede inventar una busqueda) puede
exigir que el origen sea EXPLICITO.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

# Un anio plausible de cine: 18xx, 19xx o 20xx.
_ANIO = r"(?:18|19|20)\d{2}"

GUIONES = "-–—"

# "1975 - Tiburon", con guion ASCII, en dash o em dash.
_RE_PREFIJO = re.compile(rf"^\s*({_ANIO})\s*[{GUIONES}]\s*(.+?)\s*$")
# "Tiburon (1975)"
_RE_SUFIJO = re.compile(rf"^\s*(.+?)\s*\(\s*({_ANIO})\s*\)\s*$")
# Un anio suelto en cualquier parte del nombre.
_RE_SUELTO = re.compile(rf"(?:^|\D)({_ANIO})(?=\D|$)")

_RE_PARENTESIS_FINAL = re.compile(r"\s*\(([^()]*)\)\s*$")
_RE_ESPACIOS = re.compile(r"\s+")
_RE_PARTES = re.compile(rf"\s+[{GUIONES}]\s+|\s*\(\s*|\s*\)\s*|\s*\|\s*")


class OrigenAnio(StrEnum):
    """De donde se obtuvo el anio, para saber cuanto confiar en el."""

    EXPLICITO = "explicito"   # formato "ANIO - TITULO" o "TITULO (ANIO)"
    SUELTO = "suelto"         # un anio encontrado en cualquier posicion
    AUSENTE = "ausente"


@dataclass(frozen=True, slots=True)
class NombreAnalizado:
    """Resultado de partir un nombre de carpeta en titulo y anio."""

    titulo: str
    anio: str
    origen: OrigenAnio

    @property
    def tiene_anio(self) -> bool:
        return bool(self.anio)

    @property
    def es_explicito(self) -> bool:
        return self.origen is OrigenAnio.EXPLICITO


# Paises, gentilicios e idiomas que aparecen entre parentesis al final del
# nombre de carpeta como metadato, no como parte del titulo. Tomada de
# $script:originTags del linker, ya sin los duplicados que tenia el original
# (argentina, china, noruega y suiza estaban dos veces).
ETIQUETAS_ORIGEN: frozenset[str] = frozenset({
    "alemana", "aleman", "alemania", "american", "arabe", "argelia", "argentina", "argentino",
    "australia", "australiana", "australiano", "austria", "austriaco", "belga", "belgica",
    "brasil", "brasilena", "brasileno", "brazil", "britanica", "britanico", "canada",
    "canadiense", "chile", "chilena", "chileno", "china", "chino", "colombia", "colombiano",
    "corea", "coreana", "coreano", "cuba", "cubana", "cubano", "danes", "danesa", "dinamarca",
    "eeuu", "england", "english", "espana", "espanol", "espanola", "estados unidos", "france",
    "francesa", "frances", "francia", "french", "german", "germany", "gran bretana", "grecia",
    "griega", "griego", "hebreo", "hindi", "holanda", "hong kong", "india", "inglaterra",
    "inglesa", "ingles", "iran", "irani", "israel", "irlanda", "irlandes", "italia", "italiana",
    "italiano", "italy", "italian", "japan", "japanese", "japon", "japonesa", "japones",
    "korea", "mexicana", "mexicano", "mexico", "neerlandes", "noruega", "noruego",
    "nueva zelanda", "paises bajos", "peru", "peruana", "peruano", "polaca", "polaco",
    "polonia", "portugal", "portuguesa", "portugues", "reino unido", "rusa", "rusia", "ruso",
    "russia", "spain", "spanish", "sudafrica", "sueca", "suecia", "sueco", "suiza", "suizo",
    "tailandes", "tailandesa", "tailandia", "taiwan", "turca", "turco", "turquia", "uk",
    "uruguay", "uruguaya", "uruguayo", "us", "usa", "venezolano", "venezuela",
    # Combinaciones de idioma que el original listaba aparte, ya normalizadas
    # (la barra se convierte en espacio al normalizar).
    "espanol ingles", "frances ingles", "ingles espanol", "ingles frances",
})


def normalizar_titulo(texto: str) -> str:
    """Forma canonica para comparar titulos.

    Quita tildes y diacriticos, descarta apostrofes, pasa a minusculas y
    colapsa todo lo que no sea letra o numero a un espacio. Es Normalize-Title
    del linker y normalizeTitle() del HTML, que hacian lo mismo por separado.
    """
    if not texto:
        return ""
    descompuesto = unicodedata.normalize("NFKD", str(texto))
    sin_marcas = "".join(c for c in descompuesto if not unicodedata.combining(c))
    sin_apostrofes = sin_marcas.replace("’", "").replace("'", "")
    limpio = re.sub(r"[^0-9A-Za-zÀ-ɏ]+", " ", sin_apostrofes)
    return _RE_ESPACIOS.sub(" ", limpio).strip().lower()


def quitar_sufijo_origen(titulo: str) -> str:
    """Quita los parentesis finales que son pais o idioma, no parte del titulo.

    Repite Remove-OriginSuffix del linker: solo quita el parentesis si su
    contenido normalizado esta en ETIQUETAS_ORIGEN, de modo que un subtitulo
    oficial entre parentesis se conserva. Itera, asi "Z (Francia) (Argelia)"
    pierde los dos parentesis.
    """
    limpio = (titulo or "").strip()
    while True:
        coincidencia = _RE_PARENTESIS_FINAL.search(limpio)
        if not coincidencia:
            break
        if normalizar_titulo(coincidencia.group(1)) not in ETIQUETAS_ORIGEN:
            break
        candidato = limpio[: coincidencia.start()].strip()
        if not candidato:
            break
        limpio = candidato
    return limpio


def limpiar_titulo(nombre: str) -> str:
    """Quita el prefijo "ANIO - " o el sufijo "(ANIO)" y las etiquetas de origen.

    Es clean() del HTML mas Remove-OriginSuffix del linker.
    """
    texto = (nombre or "").strip()
    coincidencia = _RE_PREFIJO.match(texto)
    if coincidencia:
        texto = coincidencia.group(2)
    else:
        coincidencia = _RE_SUFIJO.match(texto)
        if coincidencia:
            texto = coincidencia.group(1)
    return quitar_sufijo_origen(texto) or texto.strip()


def extraer_anio(nombre: str) -> str:
    """Primer anio plausible del nombre, o cadena vacia."""
    coincidencia = _RE_SUELTO.search(nombre or "")
    return coincidencia.group(1) if coincidencia else ""


def _limpiar_separadores(texto: str) -> str:
    """Normaliza los separadores de un fragmento de nombre de archivo.

    En los nombres estilo "The.Matrix.1999.1080p.BluRay" el punto hace de
    espacio, asi que si el fragmento no tiene espacios pero si puntos o
    guiones bajos, se convierten en espacios.
    """
    limpio = (texto or "").strip(f" ._{GUIONES}")
    if limpio and " " not in limpio and re.search(r"[._]", limpio):
        limpio = re.sub(r"[._]+", " ", limpio).strip()
    return _RE_ESPACIOS.sub(" ", limpio).strip()


def parsear_anio_titulo(nombre: str) -> NombreAnalizado:
    """Separa anio y titulo de un nombre de carpeta, admitiendo las tres convenciones."""
    texto = (nombre or "").strip()
    if not texto:
        return NombreAnalizado("", "", OrigenAnio.AUSENTE)

    coincidencia = _RE_PREFIJO.match(texto)
    if coincidencia:
        anio, crudo = coincidencia.group(1), coincidencia.group(2).strip()
        return NombreAnalizado(quitar_sufijo_origen(crudo) or crudo, anio, OrigenAnio.EXPLICITO)

    coincidencia = _RE_SUFIJO.match(texto)
    if coincidencia:
        crudo, anio = coincidencia.group(1).strip(), coincidencia.group(2)
        return NombreAnalizado(quitar_sufijo_origen(crudo) or crudo, anio, OrigenAnio.EXPLICITO)

    coincidencia = _RE_SUELTO.search(texto)
    if coincidencia:
        anio = coincidencia.group(1)
        # Todo lo que sigue al anio en un nombre suelto suele ser calidad,
        # codec o grupo ("1080p", "BluRay", "x264"), no titulo. Asi que el
        # titulo es lo que viene antes, como en "The.Matrix.1999.1080p".
        antes = _limpiar_separadores(texto[: coincidencia.start(1)])
        titulo = antes or _limpiar_separadores(texto[coincidencia.end(1):]) or texto.strip()
        return NombreAnalizado(quitar_sufijo_origen(titulo) or titulo, anio, OrigenAnio.SUELTO)

    titulo = _limpiar_separadores(texto) or texto.strip()
    return NombreAnalizado(quitar_sufijo_origen(titulo) or titulo, "", OrigenAnio.AUSENTE)


def variantes_consulta(titulo: str, anio: str = "") -> list[str]:
    """Variantes de titulo para consultar a una fuente externa, sin repetidos.

    Es titleQueries() del HTML: el titulo completo y sus partes separadas por
    guion largo, parentesis o barra vertical, porque muchas carpetas traen
    "Titulo - Subtitulo" o "Titulo (Otro titulo)".
    """
    base = (titulo or "").strip()
    if anio:
        base = re.sub(rf"(?:^|[\s(]){re.escape(anio)}\)?$", "", base).strip()
    if not base:
        return []

    vistos: dict[str, str] = {}
    for parte in [base, *_RE_PARTES.split(base)]:
        limpio = parte.strip()
        clave = normalizar_titulo(limpio)
        if len(clave) >= 2 and clave not in vistos:
            vistos[clave] = limpio
    return list(vistos.values())


def mismo_titulo(uno: str, otro: str) -> bool:
    """Compara dos titulos ignorando tildes, puntuacion y mayusculas."""
    izquierda = normalizar_titulo(uno)
    return bool(izquierda) and izquierda == normalizar_titulo(otro)
