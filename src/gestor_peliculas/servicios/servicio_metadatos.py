"""Casos de uso de metadatos: completar fichas en lote y revisar a mano.

El lote conserva el comportamiento del original porque estaba bien pensado:
  - pausa de 300 ms entre peliculas, para no castigar la API,
  - corte del lote completo ante 401, 403, 429 o 5xx,
  - las fichas que ya se consultaron se recuerdan: dos copias de la misma
    pelicula no gastan dos consultas,
  - lo ambiguo no se guarda, queda marcado para revisar.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .. import registro
from ..almacenamiento.bd import BaseDatos
from ..config import Ajustes
from ..errores import ErrorDominio, ErrorFuenteExterna, OperacionCancelada, RequiereRevision
from ..metadatos.cliente_tmdb import ClienteTmdb
from ..metadatos.enriquecedor import Enriquecedor, FichaEncontrada
from ..modelos import Candidato, EstadoRevision, Pelicula
from ..nucleo import identificadores as ident
from .tareas import Tarea, registro_tareas

log = registro.obtener(__name__)

TIPO_TAREA = "metadatos"


@dataclass(slots=True)
class ResultadoLote:
    """Los conteos que se muestran al terminar, como el $('result') del HTML."""

    guardadas: int = 0
    para_revisar: int = 0
    errores: int = 0
    interrumpido: bool = False
    mensajes: list[str] = field(default_factory=list)

    @property
    def procesadas(self) -> int:
        return self.guardadas + self.para_revisar + self.errores

    def __str__(self) -> str:
        return (f"{self.guardadas} guardadas - {self.para_revisar} para revisar - "
                f"{self.errores} errores")


class ServicioMetadatos:
    def __init__(self, bd: BaseDatos, ajustes: Ajustes) -> None:
        self.bd = bd
        self.ajustes = ajustes

    # ------------------------------------------------------------------ cliente

    def _enriquecedor(self) -> Enriquecedor:
        cliente = ClienteTmdb(self.ajustes.credencial_tmdb, idioma=self.ajustes.idioma_tmdb)
        return Enriquecedor(cliente)

    def exigir_credencial(self) -> None:
        if not self.ajustes.tiene_credencial_tmdb:
            raise ErrorDominio(
                "Falta la clave de TMDb. Copiala en el archivo .env del proyecto, "
                "en la linea TMDB_TOKEN. Se obtiene en themoviedb.org/settings/api"
            )

    # --------------------------------------------------------------- una ficha

    def completar_una(self, pelicula_id: int) -> FichaEncontrada:
        """Completa una sola pelicula. Levanta RequiereRevision si es ambigua."""
        self.exigir_credencial()
        pelicula = self.bd.peliculas.obtener(pelicula_id)
        if pelicula is None:
            raise ErrorDominio("Esa pelicula no esta en el indice.")

        try:
            encontrada = self._enriquecedor().enriquecer(pelicula)
        except RequiereRevision as revision:
            self._marcar_para_revisar(pelicula, str(revision), revision.candidatos)
            raise

        self._guardar(pelicula, encontrada)
        return encontrada

    def guardar_candidato(self, pelicula_id: int, tmdb_id: int,
                          imdb_id: str = "") -> FichaEncontrada:
        """Guarda la ficha que la persona confirmo en la pantalla de revision."""
        self.exigir_credencial()
        pelicula = self.bd.peliculas.obtener(pelicula_id)
        if pelicula is None:
            raise ErrorDominio("Esa pelicula no esta en el indice.")

        encontrada = self._enriquecedor().ficha_de_candidato(tmdb_id, imdb_esperado=imdb_id)
        self._guardar(pelicula, encontrada)
        return encontrada

    def vincular_imdb(self, pelicula_id: int, texto: str) -> str:
        """Guarda solo el enlace de IMDb, sin consultar TMDb.

        Es el boton "Vincular Imdb" del original: sirve cuando la persona tiene
        el enlace a mano y todavia no cargo la clave de TMDb.
        """
        imdb_id = ident.extraer_imdb_id(texto)
        if not imdb_id:
            raise ErrorDominio(
                "Ese texto no contiene un enlace de IMDb valido. "
                "Tiene que ser del estilo https://www.imdb.com/title/tt1234567/"
            )
        pelicula = self.bd.peliculas.obtener(pelicula_id)
        if pelicula is None:
            raise ErrorDominio("Esa pelicula no esta en el indice.")

        self.bd.peliculas.fijar_imdb_id(pelicula_id, imdb_id)
        self.bd.peliculas.guardar_revision(
            pelicula_id,
            EstadoRevision.COMPLETADA if pelicula.tiene_ficha else EstadoRevision.PENDIENTE,
            detalle="Enlace de IMDb guardado a mano.",
        )
        log.info("Pelicula %s vinculada a %s", pelicula_id, imdb_id)
        return imdb_id

    def buscar_candidatos(self, pelicula_id: int, texto: str) -> list[Candidato]:
        """Busqueda libre para la pantalla de revision."""
        self.exigir_credencial()
        pelicula = self.bd.peliculas.obtener(pelicula_id)
        if pelicula is None:
            raise ErrorDominio("Esa pelicula no esta en el indice.")
        consulta = (texto or "").strip() or pelicula.titulo_carpeta
        return self._enriquecedor().candidatos_para(consulta, pelicula.anio_carpeta)

    def rechazar(self, pelicula_id: int, imdb_id: str) -> None:
        """Recuerda un candidato descartado para no volver a ofrecerlo."""
        self.bd.peliculas.rechazar_candidato(pelicula_id, ident.normalizar_imdb_id(imdb_id))

    def quitar_ficha(self, pelicula_id: int) -> None:
        """Borra la ficha para volver a consultarla desde cero."""
        self.bd.metadatos.borrar(pelicula_id)
        self.bd.metadatos.limpiar_etiquetas_huerfanas()
        self.bd.peliculas.guardar_revision(
            pelicula_id, EstadoRevision.PENDIENTE, detalle="Ficha borrada a pedido."
        )

    # ------------------------------------------------------------------- lote

    def pendientes(self, limite: int | None = None) -> list[Pelicula]:
        """Peliculas que vale la pena consultar: hay con que buscarlas."""
        candidatas = self.bd.peliculas.pendientes_de_metadatos()
        utiles = [
            p for p in candidatas
            if p.imdb_id or (p.anio_carpeta and p.titulo_carpeta)
        ]
        return utiles[:limite] if limite else utiles

    def completar_lote(self, tarea: Tarea | None = None,
                       limite: int | None = None) -> ResultadoLote:
        """Consulta TMDb para todas las peliculas pendientes."""
        self.exigir_credencial()
        pendientes = self.pendientes(limite)
        resultado = ResultadoLote()
        if not pendientes:
            if tarea:
                tarea.informar("No hay peliculas para consultar.")
            return resultado

        if tarea:
            tarea.fijar_total(len(pendientes))

        enriquecedor = self._enriquecedor()
        # Dos copias de la misma pelicula no gastan dos consultas.
        por_imdb: dict[str, FichaEncontrada] = {}

        for indice, pelicula in enumerate(pendientes):
            if tarea and tarea.cancelada:
                raise OperacionCancelada("Lote detenido por la persona.")
            if tarea:
                tarea.informar(f"Consultando {pelicula.titulo_carpeta}...")

            try:
                guardada = por_imdb.get(pelicula.imdb_id) if pelicula.imdb_id else None
                encontrada = guardada or enriquecedor.enriquecer(
                    pelicula, cancelado=lambda: bool(tarea and tarea.cancelada)
                )
                if pelicula.imdb_id:
                    por_imdb[pelicula.imdb_id] = encontrada
                self._guardar(pelicula, encontrada)
                resultado.guardadas += 1

            except RequiereRevision as revision:
                self._marcar_para_revisar(pelicula, str(revision), revision.candidatos)
                resultado.para_revisar += 1

            except OperacionCancelada:
                raise

            except ErrorFuenteExterna as error:
                resultado.errores += 1
                aviso = f"{pelicula.titulo_carpeta}: {error}"
                resultado.mensajes.append(aviso)
                if tarea:
                    tarea.anotar(aviso)
                self.bd.peliculas.guardar_revision(
                    pelicula.id, EstadoRevision.ERROR, detalle=str(error)
                )
                if error.detener_lote:
                    resultado.interrumpido = True
                    if tarea:
                        tarea.informar(f"Lote interrumpido: {error}")
                    break

            except ErrorDominio as error:
                resultado.errores += 1
                resultado.mensajes.append(f"{pelicula.titulo_carpeta}: {error}")

            finally:
                if tarea:
                    tarea.avanzar()

            # Pausa entre consultas, igual que el setTimeout(300) del original.
            if indice + 1 < len(pendientes) and not (tarea and tarea.cancelada):
                time.sleep(self.ajustes.pausa_entre_consultas)

        if tarea:
            tarea.informar(str(resultado))
        log.info("Lote de metadatos: %s", resultado)
        return resultado

    def completar_lote_en_segundo_plano(self, limite: int | None = None) -> Tarea:
        self.exigir_credencial()

        def trabajo(tarea: Tarea) -> dict:
            resultado = self.completar_lote(tarea, limite)
            return {
                "guardadas": resultado.guardadas,
                "para_revisar": resultado.para_revisar,
                "errores": resultado.errores,
                "interrumpido": resultado.interrumpido,
                "texto": str(resultado),
            }

        return registro_tareas.lanzar(TIPO_TAREA, "Completando metadatos", trabajo)

    @staticmethod
    def tarea_actual() -> Tarea | None:
        return registro_tareas.ultima_de_tipo(TIPO_TAREA)

    @staticmethod
    def detener() -> bool:
        return registro_tareas.cancelar_tipo(TIPO_TAREA)

    # --------------------------------------------------------------- internos

    def _guardar(self, pelicula: Pelicula, encontrada: FichaEncontrada) -> None:
        self.bd.metadatos.guardar(pelicula.id, encontrada.metadatos)
        if encontrada.imdb_id and encontrada.imdb_id != pelicula.imdb_id:
            self.bd.peliculas.fijar_imdb_id(pelicula.id, encontrada.imdb_id)
        self.bd.peliculas.guardar_revision(
            pelicula.id, EstadoRevision.COMPLETADA,
            detalle=f"Ficha de TMDb guardada el {encontrada.metadatos.actualizado_en}.",
        )

    def _marcar_para_revisar(self, pelicula: Pelicula, motivo: str,
                             candidatos: list[Candidato]) -> None:
        mejor = candidatos[0] if candidatos else None
        self.bd.peliculas.guardar_revision(
            pelicula.id,
            EstadoRevision.REVISAR if candidatos else EstadoRevision.SIN_COINCIDENCIA,
            detalle=motivo,
            candidato_id=(mejor.imdb_id if mejor else ""),
            candidato_titulo=(mejor.titulo if mejor else ""),
            candidato_anio=(mejor.anio if mejor else ""),
            candidato_poster=(mejor.poster_url if mejor else ""),
        )
