"""Cliente de la API de TMDb.

Soporta las dos formas de credencial, igual que apiCall() del HTML original:
  - token de lectura v4 (empieza con eyJ) -> cabecera Authorization: Bearer
  - clave v3 (32 caracteres hexadecimales) -> parametro api_key

Los nombres de pais e idioma se traducen al castellano con locale.Locale del
sistema a traves de babel si estuviera, y si no con una tabla propia de los
codigos mas frecuentes mas el nombre en ingles que manda TMDb como respaldo.
Es el equivalente de Intl.DisplayNames del navegador, que en Python no existe.

Este producto usa la API de TMDb pero no esta avalado ni certificado por TMDb.
"""

from __future__ import annotations

import re

from .. import registro
from ..errores import ErrorConfiguracion, ErrorFuenteExterna
from ..modelos import Candidato, Metadatos, ahora
from ..nucleo import identificadores as ident
from .sesion_http import SesionHttp, sesion_compartida

log = registro.obtener(__name__)

BASE = "https://api.themoviedb.org/3"
BASE_IMAGEN = "https://image.tmdb.org/t/p"
FUENTE = "TMDb"

_RE_TOKEN_V4 = re.compile(r"^(?:Bearer\s+)?(eyJ\S+)$", re.IGNORECASE)
_RE_BEARER = re.compile(r"^Bearer\s+(\S+)$", re.IGNORECASE)
_RE_RUTA_IMAGEN = re.compile(r"^/[A-Za-z0-9]+\.(jpg|jpeg|png|webp)$", re.IGNORECASE)

#: Paises que aparecen en una coleccion de cine, en castellano.
PAISES = {
    "AR": "Argentina", "AT": "Austria", "AU": "Australia", "BE": "Belgica", "BR": "Brasil",
    "CA": "Canada", "CH": "Suiza", "CL": "Chile", "CN": "China", "CO": "Colombia",
    "CU": "Cuba", "CZ": "Republica Checa", "DE": "Alemania", "DK": "Dinamarca",
    "EG": "Egipto", "ES": "Espana", "FI": "Finlandia", "FR": "Francia",
    "GB": "Reino Unido", "GR": "Grecia", "HK": "Hong Kong", "HU": "Hungria",
    "ID": "Indonesia", "IE": "Irlanda", "IL": "Israel", "IN": "India", "IR": "Iran",
    "IS": "Islandia", "IT": "Italia", "JP": "Japon", "KR": "Corea del Sur",
    "MX": "Mexico", "NL": "Paises Bajos", "NO": "Noruega", "NZ": "Nueva Zelanda",
    "PE": "Peru", "PH": "Filipinas", "PL": "Polonia", "PT": "Portugal",
    "RO": "Rumania", "RS": "Serbia", "RU": "Rusia", "SE": "Suecia", "SU": "Union Sovietica",
    "TH": "Tailandia", "TR": "Turquia", "TW": "Taiwan", "UA": "Ucrania",
    "US": "Estados Unidos", "UY": "Uruguay", "VE": "Venezuela", "ZA": "Sudafrica",
}

#: Idiomas, por codigo ISO 639-1.
IDIOMAS = {
    "ar": "arabe", "bn": "bengali", "ca": "catalan", "cs": "checo", "da": "danes",
    "de": "aleman", "el": "griego", "en": "ingles", "es": "espanol", "et": "estonio",
    "eu": "euskera", "fa": "persa", "fi": "finlandes", "fr": "frances", "gl": "gallego",
    "he": "hebreo", "hi": "hindi", "hr": "croata", "hu": "hungaro", "id": "indonesio",
    "is": "islandes", "it": "italiano", "ja": "japones", "ko": "coreano", "la": "latin",
    "lt": "lituano", "nl": "neerlandes", "no": "noruego", "pl": "polaco",
    "pt": "portugues", "ro": "rumano", "ru": "ruso", "sk": "eslovaco", "sr": "serbio",
    "sv": "sueco", "th": "tailandes", "tr": "turco", "uk": "ucraniano", "vi": "vietnamita",
    "yi": "yidis", "zh": "chino", "cn": "chino",
}


def _nombre_pais(codigo: str, respaldo: str = "") -> str:
    clave = (codigo or "").strip().upper()
    return PAISES.get(clave) or respaldo or clave


def _nombre_idioma(codigo: str, respaldo: str = "") -> str:
    clave = (codigo or "").strip().lower()
    return IDIOMAS.get(clave) or respaldo or clave


def _lista_de_objetos(valor) -> list[dict]:
    return [x for x in valor if isinstance(x, dict)] if isinstance(valor, list) else []


def _anio(fecha: object) -> str:
    texto = str(fecha or "")
    return texto[:4] if len(texto) >= 4 and texto[:4].isdigit() else ""


def _id_valido(valor: object) -> int | None:
    """TMDb siempre manda enteros positivos; cualquier otra cosa es sospechosa."""
    if isinstance(valor, bool) or not isinstance(valor, int):
        return None
    return valor if valor > 0 else None


def url_poster(ruta: str | None, tamanio: str = "w500") -> str:
    """URL de un poster de TMDb, validando el formato de la ruta."""
    if not ruta or not _RE_RUTA_IMAGEN.match(str(ruta)):
        return ""
    return f"{BASE_IMAGEN}/{tamanio}{ruta}"


class ClienteTmdb:
    """Las cuatro consultas de TMDb que necesita el gestor."""

    def __init__(self, credencial: str, *, sesion: SesionHttp | None = None,
                 idioma: str = "es-AR") -> None:
        self.credencial = (credencial or "").strip()
        if not self.credencial:
            raise ErrorConfiguracion(
                "Falta la credencial de TMDb. Copiala en el archivo .env "
                "(TMDB_TOKEN). Se obtiene en https://www.themoviedb.org/settings/api"
            )
        self.sesion = sesion or sesion_compartida()
        self.idioma = idioma

    # ------------------------------------------------------------ autenticacion

    def _cabeceras_y_params(self, params: dict) -> tuple[dict, dict]:
        completos = {"language": self.idioma, **params}
        token = _RE_TOKEN_V4.match(self.credencial) or _RE_BEARER.match(self.credencial)
        if token:
            return {"Authorization": f"Bearer {token.group(1)}"}, completos
        completos["api_key"] = self.credencial
        return {}, completos

    def _pedir(self, camino: str, params: dict | None = None, *, cancelado=None) -> dict:
        cabeceras, completos = self._cabeceras_y_params(params or {})
        return self.sesion.obtener_json(
            f"{BASE}/{camino.lstrip('/')}", fuente=FUENTE,
            params=completos, headers=cabeceras, cancelado=cancelado,
        )

    def verificar_credencial(self, *, cancelado=None) -> bool:
        """Consulta barata para avisar temprano si la clave no sirve."""
        self._pedir("configuration", cancelado=cancelado)
        return True

    # -------------------------------------------------------------- consultas

    def buscar(self, consulta: str, anio: str = "", pagina: int = 1, *,
               cancelado=None) -> tuple[list[Candidato], int]:
        """Busca por titulo. Devuelve (candidatos, total_de_paginas)."""
        params: dict[str, object] = {
            "query": consulta, "include_adult": "false", "page": max(1, pagina)
        }
        if anio:
            params["primary_release_year"] = anio

        datos = self._pedir("search/movie", params, cancelado=cancelado)
        candidatos = [
            c for c in (self._a_candidato(r) for r in _lista_de_objetos(datos.get("results")))
            if c is not None
        ]
        try:
            paginas = int(datos.get("total_pages") or 1)
        except (TypeError, ValueError):
            paginas = 1
        return candidatos, max(1, paginas)

    def buscar_por_imdb(self, imdb_id: str, *, cancelado=None) -> int | None:
        """El identificador de TMDb que corresponde a un IMDb, o None."""
        limpio = ident.normalizar_imdb_id(imdb_id)
        if not limpio:
            return None
        datos = self._pedir(f"find/{limpio}", {"external_source": "imdb_id"}, cancelado=cancelado)
        peliculas = _lista_de_objetos(datos.get("movie_results"))
        return _id_valido(peliculas[0].get("id")) if peliculas else None

    def titulos_alternativos(self, tmdb_id: int, *, cancelado=None) -> list[str]:
        datos = self._pedir(f"movie/{tmdb_id}/alternative_titles", cancelado=cancelado)
        return [
            str(t.get("title") or "").strip()
            for t in _lista_de_objetos(datos.get("titles"))
            if str(t.get("title") or "").strip()
        ]

    def ficha(self, tmdb_id: int, *, imdb_esperado: str = "", cancelado=None) -> Metadatos:
        """Trae la ficha completa con el equipo tecnico.

        Verifica que la ficha devuelta sea la pedida: es la salvaguarda del
        original (lineas 456-458 del HTML), que evita guardar los datos de una
        pelicula sobre otra si la API devuelve algo inesperado.
        """
        datos = self._pedir(f"movie/{tmdb_id}", {"append_to_response": "credits"},
                            cancelado=cancelado)

        if _id_valido(datos.get("id")) != tmdb_id:
            raise ErrorFuenteExterna(
                "TMDb devolvio una ficha que no es la que se pidio.", fuente=FUENTE
            )

        imdb_devuelto = ident.normalizar_imdb_id(str(datos.get("imdb_id") or ""))
        esperado = ident.normalizar_imdb_id(imdb_esperado)
        if esperado and imdb_devuelto and imdb_devuelto != esperado:
            raise ErrorFuenteExterna(
                "La ficha de TMDb no coincide con el identificador IMDb de la carpeta.",
                fuente=FUENTE,
            )

        return self._a_metadatos(datos)

    def ficha_por_imdb(self, imdb_id: str, *, cancelado=None) -> Metadatos:
        tmdb_id = self.buscar_por_imdb(imdb_id, cancelado=cancelado)
        if tmdb_id is None:
            raise ErrorFuenteExterna(
                f"TMDb no tiene ninguna pelicula con el identificador {imdb_id}.", fuente=FUENTE
            )
        return self.ficha(tmdb_id, imdb_esperado=imdb_id, cancelado=cancelado)

    def imdb_de(self, tmdb_id: int, *, cancelado=None) -> str:
        datos = self._pedir(f"movie/{tmdb_id}/external_ids", cancelado=cancelado)
        return ident.normalizar_imdb_id(str(datos.get("imdb_id") or ""))

    # --------------------------------------------------------------- conversion

    def _a_candidato(self, crudo: dict) -> Candidato | None:
        tmdb_id = _id_valido(crudo.get("id"))
        if tmdb_id is None:
            return None
        return Candidato(
            tmdb_id=tmdb_id,
            titulo=str(crudo.get("title") or "").strip(),
            titulo_original=str(crudo.get("original_title") or "").strip(),
            anio=_anio(crudo.get("release_date")),
            poster_url=url_poster(crudo.get("poster_path")),
            fuente=FUENTE,
        )

    def _a_metadatos(self, datos: dict) -> Metadatos:
        creditos = datos.get("credits") if isinstance(datos.get("credits"), dict) else {}
        directores = [
            str(p.get("name") or "").strip()
            for p in _lista_de_objetos(creditos.get("crew"))
            if p.get("job") == "Director" and str(p.get("name") or "").strip()
        ]

        idiomas = []
        original = str(datos.get("original_language") or "")
        if original:
            idiomas.append(_nombre_idioma(original))
        for hablado in _lista_de_objetos(datos.get("spoken_languages")):
            idiomas.append(_nombre_idioma(
                str(hablado.get("iso_639_1") or ""),
                str(hablado.get("name") or hablado.get("english_name") or ""),
            ))

        duracion = datos.get("runtime")
        if not isinstance(duracion, int) or duracion <= 0:
            duracion = None

        return Metadatos(
            tmdb_id=_id_valido(datos.get("id")),
            titulo=str(datos.get("title") or "").strip(),
            titulo_original=str(datos.get("original_title") or "").strip(),
            anio=_anio(datos.get("release_date")),
            paises=_unicos(
                _nombre_pais(str(p.get("iso_3166_1") or ""), str(p.get("name") or ""))
                for p in _lista_de_objetos(datos.get("production_countries"))
            ),
            generos=_unicos(
                str(g.get("name") or "").strip()
                for g in _lista_de_objetos(datos.get("genres"))
            ),
            idiomas=_unicos(idiomas),
            director=", ".join(_unicos(directores)),
            duracion_min=duracion,
            sinopsis=str(datos.get("overview") or "").strip(),
            idiomas_verificados=True,
            actualizado_en=ahora(),
        )


def _unicos(valores) -> list[str]:
    """Quita vacios y repetidos conservando el orden de aparicion."""
    vistos: dict[str, None] = {}
    for valor in valores:
        limpio = str(valor or "").strip()
        if limpio:
            vistos.setdefault(limpio, None)
    return list(vistos)
