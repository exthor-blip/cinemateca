"""Sesion HTTP compartida: timeouts, reintentos y cache de respuestas.

Tres cosas que el proyecto original no tenia y que se notaban:

1. **Reintentos.** Ninguna llamada reintentaba. Un corte momentaneo de red se
   traducia en "sin coincidencia" y la pelicula quedaba mal clasificada.
2. **Cache.** Get-Candidates se llamaba desde cinco lugares distintos sin
   recordar nada: una busqueda en Wikidata con 7 idiomas podia disparar decenas
   de consultas repetidas al mismo endpoint por una sola pelicula.
3. **Errores distinguibles.** Todos los `catch` del linker devolvian vacio, con
   lo cual un 401 por credencial vencida era indistinguible de "no esta".
   Aca cada fallo levanta ErrorFuenteExterna, que sabe si conviene detener el
   lote entero (401, 403, 429 y 5xx, como ya hacia el HTML).
"""

from __future__ import annotations

import threading
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .. import registro
from ..errores import ErrorFuenteExterna, OperacionCancelada

log = registro.obtener(__name__)

#: Identificacion propia y generica. No lleva ningun dato de la persona.
AGENTE = "GestorPeliculas/1.0 (+catalogo local de peliculas)"

#: Codigos ante los que no tiene sentido seguir con las demas peliculas.
CODIGOS_DETENER = frozenset({401, 403, 429})

TIEMPO_ESPERA = 25
INTENTOS = 3


class CacheRespuestas:
    """Cache en memoria con tiempo de vida, por proceso.

    Es deliberadamente simple: la aplicacion corre un rato y se cierra. No hace
    falta persistirla, y no persistirla evita servir fichas viejas.
    """

    def __init__(self, segundos: int = 900, maximo: int = 512) -> None:
        self.segundos = segundos
        self.maximo = maximo
        self._datos: dict[str, tuple[float, Any]] = {}
        self._candado = threading.Lock()

    def obtener(self, clave: str) -> Any | None:
        with self._candado:
            entrada = self._datos.get(clave)
            if entrada is None:
                return None
            momento, valor = entrada
            if time.monotonic() - momento > self.segundos:
                self._datos.pop(clave, None)
                return None
            return valor

    def guardar(self, clave: str, valor: Any) -> None:
        with self._candado:
            if len(self._datos) >= self.maximo:
                # Se descarta la entrada mas vieja; no hace falta un LRU real.
                mas_vieja = min(self._datos, key=lambda k: self._datos[k][0])
                self._datos.pop(mas_vieja, None)
            self._datos[clave] = (time.monotonic(), valor)

    def vaciar(self) -> None:
        with self._candado:
            self._datos.clear()


class SesionHttp:
    """Envoltorio de requests.Session con lo que necesitan los clientes."""

    def __init__(self, *, tiempo_espera: int = TIEMPO_ESPERA,
                 cache: CacheRespuestas | None = None) -> None:
        self.tiempo_espera = tiempo_espera
        self.cache = cache if cache is not None else CacheRespuestas()
        self.sesion = requests.Session()
        self.sesion.headers.update({"User-Agent": AGENTE, "Accept": "application/json"})

        # Los reintentos con espera creciente los maneja urllib3. 429 y 5xx se
        # reintentan; 401 y 403 no, porque reintentar una credencial invalida
        # solo suma demora.
        reintentos = Retry(
            total=INTENTOS - 1,
            backoff_factor=0.8,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            raise_on_status=False,
        )
        adaptador = HTTPAdapter(max_retries=reintentos, pool_connections=4, pool_maxsize=8)
        self.sesion.mount("https://", adaptador)
        self.sesion.mount("http://", adaptador)

    def obtener_json(self, url: str, *, fuente: str, params: dict | None = None,
                     headers: dict | None = None, cancelado=None,
                     usar_cache: bool = True) -> dict:
        """GET que devuelve JSON, o levanta ErrorFuenteExterna.

        Args:
            url: direccion completa.
            fuente: nombre legible para los mensajes de error.
            params: parametros de consulta.
            headers: cabeceras adicionales (la autorizacion, por ejemplo).
            cancelado: funcion que devuelve True si hay que abandonar.
            usar_cache: False para forzar una consulta fresca.
        """
        if cancelado and cancelado():
            raise OperacionCancelada("Consulta cancelada antes de salir.")

        clave = f"{url}?{sorted((params or {}).items())}"
        if usar_cache:
            guardada = self.cache.obtener(clave)
            if guardada is not None:
                return guardada

        try:
            respuesta = self.sesion.get(
                url, params=params, headers=headers or None,
                timeout=self.tiempo_espera, allow_redirects=False,
            )
        except requests.Timeout as error:
            raise ErrorFuenteExterna(
                f"{fuente} no respondio en {self.tiempo_espera} segundos.",
                fuente=fuente, detener_lote=True,
            ) from error
        except requests.RequestException as error:
            raise ErrorFuenteExterna(
                f"No hay conexion con {fuente}.", fuente=fuente, detener_lote=True
            ) from error

        if respuesta.status_code >= 400:
            detener = respuesta.status_code in CODIGOS_DETENER or respuesta.status_code >= 500
            mensaje = _mensaje_de_estado(fuente, respuesta.status_code)
            raise ErrorFuenteExterna(mensaje, fuente=fuente,
                                     estado=respuesta.status_code, detener_lote=detener)

        try:
            datos = respuesta.json()
        except ValueError as error:
            raise ErrorFuenteExterna(
                f"{fuente} devolvio una respuesta ilegible.", fuente=fuente
            ) from error

        if not isinstance(datos, dict):
            datos = {"resultado": datos}
        if usar_cache:
            self.cache.guardar(clave, datos)
        return datos

    def descargar(self, url: str, *, fuente: str, tamanio_maximo: int = 8 * 1024 * 1024) -> bytes:
        """Descarga un archivo binario (un poster) con tope de tamanio."""
        try:
            respuesta = self.sesion.get(url, timeout=self.tiempo_espera, stream=True)
            respuesta.raise_for_status()
        except requests.RequestException as error:
            raise ErrorFuenteExterna(
                f"No se pudo descargar la imagen de {fuente}.", fuente=fuente
            ) from error

        datos = bytearray()
        for trozo in respuesta.iter_content(65536):
            datos.extend(trozo)
            if len(datos) > tamanio_maximo:
                raise ErrorFuenteExterna(
                    f"La imagen de {fuente} es mas grande de lo razonable.", fuente=fuente
                )
        return bytes(datos)

    def cerrar(self) -> None:
        self.sesion.close()

    def __enter__(self) -> SesionHttp:
        return self

    def __exit__(self, *_excepcion: object) -> None:
        self.cerrar()


def _mensaje_de_estado(fuente: str, estado: int) -> str:
    if estado == 401:
        return f"{fuente} rechazo la credencial (HTTP 401). Revisa la clave en el archivo .env."
    if estado == 403:
        return f"{fuente} nego el acceso (HTTP 403). La credencial puede no tener permisos."
    if estado == 404:
        return f"{fuente} no tiene esa ficha (HTTP 404)."
    if estado == 429:
        return f"{fuente} pide esperar: demasiadas consultas seguidas (HTTP 429)."
    if estado >= 500:
        return f"{fuente} tiene un problema en su servidor (HTTP {estado})."
    return f"{fuente} respondio HTTP {estado}."


#: Sesion compartida del proceso, para que la cache sirva a todos los clientes.
_sesion_compartida: SesionHttp | None = None
_candado_sesion = threading.Lock()


def sesion_compartida() -> SesionHttp:
    global _sesion_compartida
    with _candado_sesion:
        if _sesion_compartida is None:
            _sesion_compartida = SesionHttp()
        return _sesion_compartida
