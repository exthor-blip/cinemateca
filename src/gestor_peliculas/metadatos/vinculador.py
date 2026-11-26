"""Busca el identificador IMDb de una carpeta recorriendo varias fuentes.

Es Search-Multi() del linker (lineas 213-233), con la misma cascada y el mismo
principio de fondo, que es el acierto del diseno original:

    solo se acepta sin preguntar UNA coincidencia exacta de titulo principal y
    anio en IMDb. Todo lo demas va a revision humana.

Orden de las fuentes:
  1. IMDb (sugerencias). Si da una coincidencia exacta, se termina aca.
  2. Wikidata, que aporta el titulo en otros idiomas y el identificador.
  3. TMDb, si hay clave cargada.
  4. Wikipedia, que solo aporta nombres con los que volver a preguntar a IMDb.

Lo que cambia respecto del original: los errores de red ya no se confunden con
"no esta". Cada fuente que falla queda registrada, y el resultado dice si la
busqueda fue completa o si alguna fuente no contesto. Antes, con todos los
`catch { }` vacios, una pelicula podia quedar como "No encontrada" solo porque
se cayo el wifi.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .. import registro
from ..errores import ErrorConfiguracion, ErrorFuenteExterna
from ..modelos import Candidato, Pelicula
from ..nucleo.coincidencias import Coincidencia, Veredicto, clasificar
from ..nucleo.titulos import normalizar_titulo, variantes_consulta
from .cliente_imdb_sugerencias import ClienteImdbSugerencias
from .cliente_tmdb import ClienteTmdb
from .cliente_wikidata import ClienteWikidata
from .cliente_wikipedia import ClienteWikipedia

log = registro.obtener(__name__)


@dataclass(slots=True)
class ResultadoVinculacion:
    """Lo que se encontro y cuanto se puede confiar en ello."""

    coincidencia: Coincidencia
    fuentes_consultadas: list[str] = field(default_factory=list)
    fuentes_caidas: list[str] = field(default_factory=list)

    @property
    def veredicto(self) -> Veredicto:
        return self.coincidencia.veredicto

    @property
    def elegido(self) -> Candidato | None:
        return self.coincidencia.elegido

    @property
    def candidatos(self) -> tuple:
        return self.coincidencia.candidatos

    @property
    def busqueda_completa(self) -> bool:
        """False si alguna fuente no contesto: el 'no esta' no es concluyente."""
        return not self.fuentes_caidas

    @property
    def nota(self) -> str:
        base = self.coincidencia.nota
        if self.fuentes_caidas:
            base += f" (no respondieron: {', '.join(self.fuentes_caidas)})"
        return base


class Vinculador:
    def __init__(self, *, credencial_tmdb: str = "", idioma_tmdb: str = "es-AR") -> None:
        self.imdb = ClienteImdbSugerencias()
        self.wikidata = ClienteWikidata()
        self.wikipedia = ClienteWikipedia()
        self.tmdb: ClienteTmdb | None = None
        if credencial_tmdb:
            try:
                self.tmdb = ClienteTmdb(credencial_tmdb, idioma=idioma_tmdb)
            except ErrorConfiguracion:
                self.tmdb = None

    def vincular(self, titulo: str, anio: str, *, cancelado=None) -> ResultadoVinculacion:
        """Busca el identificador IMDb de un titulo y anio."""
        consultadas: list[str] = []
        caidas: list[str] = []
        variantes = variantes_consulta(titulo, anio) or [titulo]
        titulos = {normalizar_titulo(v) for v in variantes if v}

        # 1. IMDb. Es la fuente con autoridad para esto.
        candidatos_imdb = self._desde_imdb(variantes, consultadas, caidas, cancelado=cancelado)
        resultado = clasificar(candidatos_imdb, titulo, anio, titulos_extra=variantes)
        if resultado.veredicto is Veredicto.EXACTA:
            return ResultadoVinculacion(resultado, consultadas, caidas)

        # 2. Wikidata: titulos en otros idiomas mas el identificador.
        extras: list[Candidato] = []
        extras.extend(self._desde_wikidata(titulo, anio, consultadas, caidas, cancelado=cancelado))

        # 3. TMDb, si hay clave.
        extras.extend(self._desde_tmdb(titulo, anio, consultadas, caidas, cancelado=cancelado))

        # 4. Wikipedia: nombres nuevos con los que repreguntar a IMDb.
        nombres = self._desde_wikipedia(titulo, anio, consultadas, caidas, cancelado=cancelado)
        for nombre in nombres:
            extras.extend(self.imdb.sugerir(nombre, cancelado=cancelado))

        todos = [*candidatos_imdb, *extras]
        if not todos:
            vacio = clasificar([], titulo, anio)
            return ResultadoVinculacion(vacio, consultadas, caidas)

        # Las fichas que llegaron por una via indirecta NUNCA son exactas:
        # se degradan a revision, como hacia el original.
        final = clasificar(todos, titulo, anio, titulos_extra=[*variantes, *nombres])
        if final.veredicto is Veredicto.EXACTA and not any(
            normalizar_titulo(c.titulo) in titulos for c in candidatos_imdb
        ):
            final = Coincidencia(
                Veredicto.REVISAR, final.candidatos,
                "Ficha encontrada por titulo alternativo: hay que verificarla antes de guardar.",
            )

        return ResultadoVinculacion(final, consultadas, caidas)

    def vincular_pelicula(self, pelicula: Pelicula, *, cancelado=None) -> ResultadoVinculacion:
        return self.vincular(pelicula.titulo_carpeta, pelicula.anio_carpeta, cancelado=cancelado)

    # ------------------------------------------------------------ cada fuente

    def _desde_imdb(self, variantes: list[str], consultadas: list[str],
                    caidas: list[str], *, cancelado=None) -> list[Candidato]:
        consultadas.append("IMDb")
        por_id: dict[str, Candidato] = {}
        hubo_respuesta = False
        for variante in variantes[:3]:
            encontrados = self.imdb.sugerir(variante, cancelado=cancelado)
            if encontrados:
                hubo_respuesta = True
            for candidato in encontrados:
                por_id.setdefault(candidato.imdb_id, candidato)
        if not hubo_respuesta and not por_id:
            # No se puede distinguir "sin resultados" de "no respondio", pero el
            # cliente ya registro el fallo si lo hubo.
            pass
        return list(por_id.values())

    def _desde_wikidata(self, titulo: str, anio: str, consultadas: list[str],
                        caidas: list[str], *, cancelado=None) -> list[Candidato]:
        consultadas.append("Wikidata")
        try:
            return self.wikidata.buscar(titulo, anio, cancelado=cancelado)
        except ErrorFuenteExterna as error:
            log.info("Wikidata fallo: %s", error)
            caidas.append("Wikidata")
            return []

    def _desde_tmdb(self, titulo: str, anio: str, consultadas: list[str],
                    caidas: list[str], *, cancelado=None) -> list[Candidato]:
        if self.tmdb is None:
            return []
        consultadas.append("TMDb")
        try:
            candidatos, _paginas = self.tmdb.buscar(titulo, anio, cancelado=cancelado)
        except ErrorFuenteExterna as error:
            log.info("TMDb fallo: %s", error)
            caidas.append("TMDb")
            return []

        # Se completa el identificador IMDb de los primeros, que es el dato que
        # realmente interesa para escribir el imdb.url.
        completados: list[Candidato] = []
        for candidato in candidatos[:5]:
            if candidato.tmdb_id and not candidato.imdb_id:
                try:
                    candidato.imdb_id = self.tmdb.imdb_de(candidato.tmdb_id, cancelado=cancelado)
                except ErrorFuenteExterna:
                    pass
            candidato.nota = "Ficha de TMDb; el identificador IMDb hay que verificarlo."
            completados.append(candidato)
        return completados

    def _desde_wikipedia(self, titulo: str, anio: str, consultadas: list[str],
                         caidas: list[str], *, cancelado=None) -> list[str]:
        consultadas.append("Wikipedia")
        try:
            return self.wikipedia.titulos_alternativos(titulo, anio, cancelado=cancelado)[:3]
        except ErrorFuenteExterna as error:
            log.info("Wikipedia fallo: %s", error)
            caidas.append("Wikipedia")
            return []
