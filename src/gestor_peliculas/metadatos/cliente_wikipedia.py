"""Cliente de Wikipedia, solo para descubrir titulos alternativos.

Es Get-WikipediaAlternates() del linker. Wikipedia no da identificadores, asi
que su unico aporte es un nombre distinto con el que volver a preguntarle a
IMDb. Nunca confirma nada por si misma, y el original ya lo tenia claro: todo
lo que llega por esta via queda marcado para revision.
"""

from __future__ import annotations

import re

from .. import registro
from ..errores import ErrorFuenteExterna
from ..nucleo.titulos import normalizar_titulo
from .sesion_http import SesionHttp, sesion_compartida

log = registro.obtener(__name__)

API = "https://{}.wikipedia.org/w/api.php"
FUENTE = "Wikipedia"
IDIOMAS = ("es", "en")

#: "Tiburon (pelicula)" o "Jaws (1975 film)" -> se saca el parentesis.
_RE_DESAMBIGUACION = re.compile(
    r"\s*\((?:\d{4}\s+)?(?:film|pel[ií]cula|movie|filme|pel[ií]cula de \d{4})\)\s*$",
    re.IGNORECASE,
)


class ClienteWikipedia:
    def __init__(self, sesion: SesionHttp | None = None) -> None:
        self.sesion = sesion or sesion_compartida()

    def titulos_alternativos(self, titulo: str, anio: str = "", *, cancelado=None) -> list[str]:
        """Nombres de articulo que podrian ser la misma pelicula con otro titulo."""
        texto = (titulo or "").strip()
        if not texto:
            return []

        buscado = normalizar_titulo(texto)
        encontrados: dict[str, str] = {}

        for idioma in IDIOMAS:
            consulta = f"{texto} {anio} film".strip()
            try:
                datos = self.sesion.obtener_json(
                    API.format(idioma), fuente=FUENTE, cancelado=cancelado,
                    params={
                        "action": "query", "list": "search", "srsearch": consulta,
                        "srlimit": 5, "format": "json",
                    },
                )
            except ErrorFuenteExterna as error:
                log.info("Wikipedia (%s) no respondio: %s", idioma, error)
                continue

            resultados = ((datos.get("query") or {}).get("search")
                          if isinstance(datos.get("query"), dict) else None)
            for resultado in resultados or []:
                if not isinstance(resultado, dict):
                    continue
                nombre = _RE_DESAMBIGUACION.sub("", str(resultado.get("title") or "")).strip()
                if not nombre:
                    continue
                clave = normalizar_titulo(nombre)
                # Solo interesa un nombre DISTINTO del que ya se busco.
                if clave and clave != buscado:
                    encontrados.setdefault(clave, nombre)

        return list(encontrados.values())
