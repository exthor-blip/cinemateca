"""Cliente de la API de sugerencias de IMDb.

Es Get-Candidates() del linker. Es la API que alimenta el buscador de imdb.com:
no esta documentada ni es oficial, asi que se trata como una fuente de apoyo,
no como una autoridad. Dos particularidades reales del endpoint:

  - la letra del camino tiene que coincidir con el primer caracter de la
    consulta, ya normalizado;
  - devuelve peliculas, series, personas y videojuegos mezclados, asi que hay
    que filtrar por identificador y por tipo.

A diferencia del original, aca NO se falsifica el User-Agent de un navegador:
se usa una identificacion propia y generica. Mentir sobre quien consulta no
hace falta y no corresponde.
"""

from __future__ import annotations

import unicodedata
from urllib.parse import quote

from .. import registro
from ..errores import ErrorFuenteExterna
from ..modelos import Candidato
from ..nucleo.identificadores import RE_IMDB_ID
from .sesion_http import SesionHttp, sesion_compartida

log = registro.obtener(__name__)

BASE = "https://v3.sg.media-imdb.com/suggestion"
FUENTE = "IMDb"

#: Tipos de ficha que son una pelicula. El resto (series, personas, juegos) se
#: descarta: el catalogo es de cine.
TIPOS_PELICULA = frozenset({"movie", "feature", "tvMovie", "video", "short", "tvShort"})


def _letra_inicial(consulta: str) -> str:
    """Primera letra normalizada, que es la que exige el camino del endpoint."""
    descompuesto = unicodedata.normalize("NFKD", consulta.strip().lower())
    sin_marcas = "".join(c for c in descompuesto if not unicodedata.combining(c))
    for caracter in sin_marcas:
        if caracter.isascii() and caracter.isalnum():
            return caracter
    return "x"


class ClienteImdbSugerencias:
    def __init__(self, sesion: SesionHttp | None = None) -> None:
        self.sesion = sesion or sesion_compartida()

    def sugerir(self, consulta: str, *, cancelado=None) -> list[Candidato]:
        """Candidatos de IMDb para un texto. Devuelve [] si la fuente falla.

        Esta fuente es de apoyo: si no responde, el vinculador sigue con
        Wikidata y TMDb. Pero el fallo se registra, en lugar de desaparecer en
        un catch vacio como en el original.
        """
        texto = (consulta or "").strip()
        if not texto:
            return []

        url = f"{BASE}/{_letra_inicial(texto)}/{quote(texto, safe='')}.json"
        try:
            datos = self.sesion.obtener_json(url, fuente=FUENTE, cancelado=cancelado)
        except ErrorFuenteExterna as error:
            log.info("IMDb no respondio para %r: %s", texto[:40], error)
            return []

        candidatos = []
        for crudo in datos.get("d") or []:
            candidato = self._a_candidato(crudo)
            if candidato is not None:
                candidatos.append(candidato)
        return candidatos

    def por_identificador(self, imdb_id: str, *, cancelado=None) -> Candidato | None:
        """Busca una ficha concreta por su identificador.

        El endpoint de sugerencias acepta un tt como consulta, aunque no es
        exhaustivo: puede no conocer una ficha que existe. En ese caso devuelve
        None y quien llama no debe inventar metadatos (es lo que hacia bien el
        original en Show-ManualLastResort).
        """
        for candidato in self.sugerir(imdb_id, cancelado=cancelado):
            if candidato.imdb_id == imdb_id.lower():
                return candidato
        return None

    @staticmethod
    def _a_candidato(crudo: object) -> Candidato | None:
        if not isinstance(crudo, dict):
            return None

        imdb_id = str(crudo.get("id") or "").strip().lower()
        if not RE_IMDB_ID.match(imdb_id):
            return None

        tipo = str(crudo.get("qid") or crudo.get("q") or "")
        if tipo and tipo not in TIPOS_PELICULA:
            return None

        anio = crudo.get("y")
        if not anio:
            return None

        imagen = crudo.get("i")
        poster = ""
        if isinstance(imagen, dict):
            poster = str(imagen.get("imageUrl") or "")

        return Candidato(
            imdb_id=imdb_id,
            titulo=str(crudo.get("l") or "").strip(),
            anio=str(anio),
            poster_url=poster,
            fuente=FUENTE,
            titulos_alternativos=[
                str(a).strip() for a in (crudo.get("akas") or [])
                if isinstance(a, str) and a.strip()
            ],
        )
