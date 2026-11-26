"""Cliente de Wikidata, para encontrar titulos en otros idiomas.

Es Get-WikidataCandidates() del linker, y sirve para un caso concreto y
frecuente en una coleccion en castellano: la carpeta dice "Tiburon" y en IMDb
la ficha se llama "Jaws". Wikidata guarda las etiquetas y los alias de una
pelicula en decenas de idiomas, y tambien el identificador IMDb (propiedad
P345) y el de TMDb (P4947).

Dos arreglos respecto del original:

  1. La verificacion de anio estaba escrita pero NO implementada: el bloque
     `if($releaseYears.Count -gt 0 -and $year -notin $releaseYears){ }` tenia el
     cuerpo vacio (lineas 147-150 del .ps1). Aca la fecha de estreno (P577) se
     compara de verdad, y una entidad cuyo anio no coincide con ninguno de los
     estrenos conocidos se descarta.
  2. Se consultan menos idiomas de busqueda (3 en lugar de 7) porque la
     busqueda de entidades ya es multilingue; los alias si se leen en los diez
     idiomas. Esto baja de decenas de peticiones por pelicula a unas pocas.
"""

from __future__ import annotations

import re

from .. import registro
from ..errores import ErrorFuenteExterna
from ..modelos import Candidato
from ..nucleo.identificadores import RE_IMDB_ID
from ..nucleo.titulos import normalizar_titulo
from .sesion_http import SesionHttp, sesion_compartida

log = registro.obtener(__name__)

API = "https://www.wikidata.org/w/api.php"
ENTIDAD = "https://www.wikidata.org/wiki/Special:EntityData/{}.json"
FUENTE = "Wikidata"

#: Idiomas en los que se busca la entidad.
IDIOMAS_BUSQUEDA = ("es", "en", "fr")

#: Idiomas de los que se leen etiquetas y alias.
IDIOMAS_ALIAS = ("es", "en", "fr", "pt", "de", "it", "ja", "ko", "ru", "zh")

#: Cuantas entidades se abren como maximo por pelicula.
MAXIMO_ENTIDADES = 6

_RE_ENTIDAD = re.compile(r"^Q\d+$")
_RE_ANIO_ESTRENO = re.compile(r"^[+-](\d{4})-")


class ClienteWikidata:
    def __init__(self, sesion: SesionHttp | None = None) -> None:
        self.sesion = sesion or sesion_compartida()

    def buscar(self, titulo: str, anio: str = "", *, cancelado=None) -> list[Candidato]:
        """Candidatos de Wikidata cuyo titulo o alias coincide con el buscado.

        Devuelve [] si la fuente no responde: es una fuente de apoyo.
        """
        texto = (titulo or "").strip()
        if not texto:
            return []

        buscado = normalizar_titulo(texto)
        candidatos: list[Candidato] = []
        vistas: set[str] = set()

        for entidad_id, etiqueta in self._entidades(texto, cancelado=cancelado):
            if len(vistas) >= MAXIMO_ENTIDADES:
                break
            if entidad_id in vistas:
                continue
            vistas.add(entidad_id)

            datos = self._entidad(entidad_id, cancelado=cancelado)
            if not datos:
                continue

            nombres = self._nombres(datos, etiqueta)
            normalizados = {normalizar_titulo(n) for n in nombres}
            if buscado not in normalizados:
                # Wikidata devuelve cosas no relacionadas: se exige titulo o
                # alias exacto, igual que el original.
                continue

            anios = self._anios_estreno(datos)
            if anio and anios and anio not in anios:
                # Esta es la comprobacion que en el .ps1 quedo sin implementar.
                log.debug("Se descarta %s: estrenos %s no incluyen %s", entidad_id, anios, anio)
                continue

            imdb_ids = self._valores(datos, "P345", RE_IMDB_ID)
            tmdb_ids = self._valores(datos, "P4947", re.compile(r"^\d+$"))

            if not imdb_ids and not tmdb_ids:
                continue

            candidatos.append(Candidato(
                imdb_id=imdb_ids[0].lower() if imdb_ids else "",
                tmdb_id=int(tmdb_ids[0]) if tmdb_ids else None,
                titulo=etiqueta or texto,
                anio=(anios[0] if anios else anio),
                fuente=FUENTE,
                nota=f"Identificador obtenido de Wikidata ({entidad_id}). Hay que verificarlo.",
                titulos_alternativos=sorted(nombres),
            ))

        return candidatos

    # --------------------------------------------------------------- internos

    def _entidades(self, texto: str, *, cancelado=None) -> list[tuple[str, str]]:
        """(id, etiqueta) de las entidades que devuelve la busqueda."""
        encontradas: dict[str, str] = {}
        for idioma in IDIOMAS_BUSQUEDA:
            try:
                datos = self.sesion.obtener_json(
                    API, fuente=FUENTE, cancelado=cancelado,
                    params={
                        "action": "wbsearchentities", "search": texto, "language": idioma,
                        "uselang": idioma, "format": "json", "limit": 8, "type": "item",
                    },
                )
            except ErrorFuenteExterna as error:
                log.info("Wikidata no respondio para %r: %s", texto[:40], error)
                continue

            for resultado in datos.get("search") or []:
                if not isinstance(resultado, dict):
                    continue
                entidad_id = str(resultado.get("id") or "")
                if _RE_ENTIDAD.match(entidad_id):
                    encontradas.setdefault(entidad_id, str(resultado.get("label") or ""))
        return list(encontradas.items())

    def _entidad(self, entidad_id: str, *, cancelado=None) -> dict | None:
        try:
            datos = self.sesion.obtener_json(
                ENTIDAD.format(entidad_id), fuente=FUENTE, cancelado=cancelado
            )
        except ErrorFuenteExterna as error:
            log.info("No se pudo leer la entidad %s: %s", entidad_id, error)
            return None
        entidades = datos.get("entities")
        if not isinstance(entidades, dict):
            return None
        entidad = entidades.get(entidad_id)
        return entidad if isinstance(entidad, dict) else None

    @staticmethod
    def _nombres(entidad: dict, etiqueta: str) -> set[str]:
        nombres: set[str] = {etiqueta} if etiqueta else set()

        etiquetas = entidad.get("labels") or {}
        alias = entidad.get("aliases") or {}
        for idioma in IDIOMAS_ALIAS:
            propia = etiquetas.get(idioma) if isinstance(etiquetas, dict) else None
            if isinstance(propia, dict) and propia.get("value"):
                nombres.add(str(propia["value"]))
            lista = alias.get(idioma) if isinstance(alias, dict) else None
            for entrada in lista or []:
                if isinstance(entrada, dict) and entrada.get("value"):
                    nombres.add(str(entrada["value"]))
        return {n for n in nombres if n.strip()}

    @staticmethod
    def _valores(entidad: dict, propiedad: str, patron: re.Pattern[str]) -> list[str]:
        claims = entidad.get("claims") or {}
        encontrados = []
        for declaracion in (claims.get(propiedad) or []) if isinstance(claims, dict) else []:
            if not isinstance(declaracion, dict):
                continue
            principal = declaracion.get("mainsnak") or {}
            valor = (principal.get("datavalue") or {}).get("value")
            if isinstance(valor, str) and patron.match(valor):
                encontrados.append(valor)
        return encontrados

    @staticmethod
    def _anios_estreno(entidad: dict) -> list[str]:
        """Anios de la propiedad P577 (fecha de publicacion)."""
        claims = entidad.get("claims") or {}
        anios: dict[str, None] = {}
        for declaracion in (claims.get("P577") or []) if isinstance(claims, dict) else []:
            if not isinstance(declaracion, dict):
                continue
            valor = ((declaracion.get("mainsnak") or {}).get("datavalue") or {}).get("value")
            tiempo = valor.get("time") if isinstance(valor, dict) else None
            if isinstance(tiempo, str):
                coincidencia = _RE_ANIO_ESTRENO.match(tiempo)
                if coincidencia:
                    anios.setdefault(coincidencia.group(1), None)
        return list(anios)
