"""Completa la ficha de una pelicula consultando TMDb.

Dos caminos, como en el HTML original:

  - Si la carpeta ya tiene identificador IMDb (porque el linker dejo su
    `imdb.url`), se usa `find/{tt...}`: es exacto y no hay nada que adivinar.
  - Si no lo tiene, se busca por titulo y anio, y solo se acepta si hay UNA
    unica ficha cuyo titulo o titulo alternativo y anio coinciden. Cualquier
    ambiguedad levanta RequiereRevision con los candidatos, para que decida la
    persona.

Sin anio no se busca: titulo solo da demasiados falsos positivos. Esas
peliculas quedan como "sin datos suficientes" y se resuelven a mano desde la
ficha, igual que en la version 1.14.
"""

from __future__ import annotations

from dataclasses import dataclass

from .. import registro
from ..errores import RequiereRevision
from ..modelos import Candidato, Metadatos, Pelicula
from ..nucleo import identificadores as ident
from ..nucleo.coincidencias import Veredicto, clasificar
from ..nucleo.titulos import normalizar_titulo, variantes_consulta
from .cliente_tmdb import ClienteTmdb

log = registro.obtener(__name__)

#: Si una consulta por titulo devuelve mas paginas que esto, el titulo es
#: demasiado generico para confirmar nada. Es el limite del HTML original.
MAXIMO_PAGINAS = 5

#: Cuantas fichas se consultan por titulos alternativos antes de rendirse.
MAXIMO_ALTERNATIVOS = 8


@dataclass(slots=True)
class FichaEncontrada:
    """Resultado de enriquecer: la ficha mas el identificador que se confirmo."""

    metadatos: Metadatos
    imdb_id: str = ""
    tmdb_id: int | None = None


class Enriquecedor:
    def __init__(self, cliente: ClienteTmdb) -> None:
        self.cliente = cliente

    def enriquecer(self, pelicula: Pelicula, *, cancelado=None) -> FichaEncontrada:
        """Devuelve la ficha de la pelicula, o levanta RequiereRevision.

        Raises:
            RequiereRevision: hay candidatos pero ninguno concluyente.
            ErrorFuenteExterna: problema de red o de credencial.
        """
        if pelicula.imdb_id:
            return self._por_imdb(pelicula.imdb_id, cancelado=cancelado)
        return self._por_titulo(pelicula, cancelado=cancelado)

    # ------------------------------------------------------------ camino exacto

    def _por_imdb(self, imdb_id: str, *, cancelado=None) -> FichaEncontrada:
        metadatos = self.cliente.ficha_por_imdb(imdb_id, cancelado=cancelado)
        return FichaEncontrada(metadatos, ident.normalizar_imdb_id(imdb_id), metadatos.tmdb_id)

    # --------------------------------------------------------- camino por titulo

    def _por_titulo(self, pelicula: Pelicula, *, cancelado=None) -> FichaEncontrada:
        consultas = variantes_consulta(pelicula.titulo_carpeta, pelicula.anio_carpeta)
        if not pelicula.anio_carpeta or not consultas:
            raise RequiereRevision(
                "La carpeta no tiene titulo y anio suficientes para buscar. "
                "Se puede pegar el enlace de IMDb en la ficha."
            )

        candidatos = self._reunir_candidatos(consultas, pelicula.anio_carpeta, cancelado=cancelado)
        if not candidatos:
            raise RequiereRevision(
                f"TMDb no devolvio ninguna pelicula de {pelicula.anio_carpeta} "
                f"con ese titulo."
            )

        titulos = {normalizar_titulo(c) for c in consultas}
        resultado = clasificar(candidatos, pelicula.titulo_carpeta, pelicula.anio_carpeta,
                               titulos_extra=consultas)

        if resultado.veredicto is Veredicto.EXACTA:
            elegido = resultado.elegido
            return self._completar(elegido, cancelado=cancelado)

        # Antes de pedir intervencion humana se prueba con los titulos
        # alternativos de TMDb: "Jaws" contra una carpeta "Tiburon" solo
        # coincide por ahi. Es el segundo intento de searchMovie() del HTML.
        del_mismo_anio = [c for c in candidatos if c.anio == pelicula.anio_carpeta]
        if len(del_mismo_anio) <= MAXIMO_ALTERNATIVOS:
            por_alias = self._buscar_por_alias(del_mismo_anio, titulos, cancelado=cancelado)
            if len(por_alias) == 1:
                return self._completar(por_alias[0], cancelado=cancelado)
            if len(por_alias) > 1:
                raise RequiereRevision(
                    "Varias peliculas coinciden por titulo alternativo y anio.", por_alias
                )

        raise RequiereRevision(resultado.nota, list(resultado.candidatos))

    def _reunir_candidatos(self, consultas: list[str], anio: str, *,
                           cancelado=None) -> list[Candidato]:
        """Junta los resultados de todas las variantes, sin repetir fichas."""
        por_id: dict[int, Candidato] = {}
        for consulta in consultas:
            primeros, paginas = self.cliente.buscar(consulta, anio, cancelado=cancelado)
            if paginas > MAXIMO_PAGINAS:
                raise RequiereRevision(
                    "El titulo es demasiado generico: TMDb devuelve cientos de resultados."
                )
            for pagina in range(1, min(paginas, MAXIMO_PAGINAS) + 1):
                lote = primeros if pagina == 1 else self.cliente.buscar(
                    consulta, anio, pagina, cancelado=cancelado
                )[0]
                for candidato in lote:
                    # El filtro por anio de TMDb no siempre es estricto.
                    if anio and candidato.anio and candidato.anio != anio:
                        continue
                    if candidato.tmdb_id:
                        por_id.setdefault(candidato.tmdb_id, candidato)
        return list(por_id.values())

    def _buscar_por_alias(self, candidatos: list[Candidato], titulos: set[str], *,
                          cancelado=None) -> list[Candidato]:
        coincidentes: list[Candidato] = []
        for candidato in candidatos:
            if not candidato.tmdb_id:
                continue
            alias = self.cliente.titulos_alternativos(candidato.tmdb_id, cancelado=cancelado)
            if any(normalizar_titulo(a) in titulos for a in alias):
                coincidentes.append(candidato)
        return coincidentes

    # ----------------------------------------------------------------- comunes

    def _completar(self, candidato: Candidato, *, cancelado=None) -> FichaEncontrada:
        """Trae la ficha completa de un candidato ya elegido."""
        if candidato.tmdb_id is None:
            raise RequiereRevision("El candidato no tiene identificador de TMDb.")
        metadatos = self.cliente.ficha(candidato.tmdb_id, cancelado=cancelado)
        imdb_id = candidato.imdb_id or self.cliente.imdb_de(candidato.tmdb_id, cancelado=cancelado)
        return FichaEncontrada(metadatos, imdb_id, candidato.tmdb_id)

    def ficha_de_candidato(self, tmdb_id: int, *, imdb_esperado: str = "",
                           cancelado=None) -> FichaEncontrada:
        """Trae la ficha de una pelicula que la persona eligio a mano."""
        metadatos = self.cliente.ficha(tmdb_id, imdb_esperado=imdb_esperado, cancelado=cancelado)
        imdb_id = ident.normalizar_imdb_id(imdb_esperado) or self.cliente.imdb_de(
            tmdb_id, cancelado=cancelado
        )
        return FichaEncontrada(metadatos, imdb_id, tmdb_id)

    def candidatos_para(self, texto: str, anio: str = "", *, cancelado=None) -> list[Candidato]:
        """Busqueda libre para la pantalla de revision.

        Acepta un titulo o un enlace de IMDb pegado. Ordena por cercania de
        anio, como hacia el formulario de reviewMovie() del HTML.
        """
        imdb_id = ident.extraer_imdb_id(texto)
        if imdb_id:
            tmdb_id = self.cliente.buscar_por_imdb(imdb_id, cancelado=cancelado)
            if tmdb_id is None:
                return []
            ficha = self.cliente.ficha(tmdb_id, imdb_esperado=imdb_id, cancelado=cancelado)
            return [Candidato(
                imdb_id=imdb_id, tmdb_id=tmdb_id, titulo=ficha.titulo,
                titulo_original=ficha.titulo_original, anio=ficha.anio, fuente="TMDb",
                nota="Ficha encontrada por el enlace de IMDb.",
            )]

        candidatos, _ = self.cliente.buscar(texto, cancelado=cancelado)
        if not anio:
            return candidatos

        def distancia(candidato: Candidato) -> int:
            if not candidato.anio:
                return 999
            try:
                return abs(int(anio) - int(candidato.anio))
            except ValueError:
                return 999

        return sorted(candidatos, key=distancia)
