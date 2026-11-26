"""Casos de uso del catalogo: lo unico que la web y la CLI llaman para esto.

La regla de la arquitectura: web/ y cli/ hablan solo con servicios/. Un
servicio puede usar catalogo/, busqueda/, almacenamiento/ y nucleo/, nunca al
revés. Asi la logica se puede ejercitar desde la consola sin levantar Flask.
"""

from __future__ import annotations

from pathlib import Path

from .. import registro
from ..almacenamiento.bd import BaseDatos
from ..busqueda import facetas as modulo_facetas
from ..busqueda.consultas import ConsultaCatalogo
from ..busqueda.filtros import FiltroBusqueda, Pagina
from ..catalogo import duplicados, indexador
from ..errores import ErrorDominio
from ..modelos import Pelicula, ResumenIndexado, Ubicacion
from .tareas import Tarea, registro_tareas

log = registro.obtener(__name__)

TIPO_TAREA_INDEXADO = "indexado"


class ServicioCatalogo:
    def __init__(self, bd: BaseDatos) -> None:
        self.bd = bd
        self.consulta = ConsultaCatalogo(bd.conexion, usar_fts=bd.fts_disponible)

    # ------------------------------------------------------------------ lectura

    def buscar(self, filtro: FiltroBusqueda) -> Pagina:
        return self.consulta.buscar(filtro)

    def facetas(self) -> modulo_facetas.Facetas:
        return modulo_facetas.calcular(self.bd.conexion)

    def resumen(self, visibles: int = 0) -> modulo_facetas.Resumen:
        return modulo_facetas.resumir(self.bd.conexion, visibles)

    def obtener(self, pelicula_id: int) -> Pelicula | None:
        return self.bd.peliculas.obtener(pelicula_id)

    def obtener_o_fallar(self, pelicula_id: int) -> Pelicula:
        pelicula = self.obtener(pelicula_id)
        if pelicula is None:
            raise ErrorDominio(f"No hay ninguna pelicula con el numero {pelicula_id}.")
        return pelicula

    def copias_de(self, pelicula: Pelicula) -> list[Pelicula]:
        """Las otras carpetas donde esta la misma pelicula."""
        if not pelicula.imdb_id:
            return []
        return duplicados.copias_de(pelicula, self.bd.peliculas.listar_todas())

    def ubicaciones(self) -> list[Ubicacion]:
        return self.bd.ubicaciones.listar()

    # --------------------------------------------------------------- ubicaciones

    def agregar_ubicacion(self, ruta: Path | str, nombre: str = "") -> Ubicacion:
        carpeta = Path(str(ruta).strip().strip('"')).expanduser()
        if not str(carpeta).strip():
            raise ErrorDominio("Hay que indicar una carpeta.")
        if not carpeta.exists():
            raise ErrorDominio(f"La carpeta {carpeta} no existe.")
        if not carpeta.is_dir():
            raise ErrorDominio(f"{carpeta} no es una carpeta.")
        return self.bd.ubicaciones.alta(carpeta, nombre)

    def quitar_ubicacion(self, ubicacion_id: int) -> int:
        """Quita la ubicacion del indice. No borra ningun archivo del disco."""
        ubicacion = self.bd.ubicaciones.obtener(ubicacion_id)
        if ubicacion is None:
            raise ErrorDominio("Esa ubicacion ya no esta en el indice.")
        quitadas = self.bd.ubicaciones.baja(ubicacion_id)
        self.bd.metadatos.limpiar_etiquetas_huerfanas()
        log.info("Se quito la ubicacion %s con %s peliculas", ubicacion.nombre, quitadas)
        return quitadas

    def vaciar_indice(self) -> None:
        """Vacia todo el indice. Los videos y posteres del disco no se tocan."""
        self.bd.ubicaciones.vaciar()
        log.info("Indice vaciado a pedido de la persona")

    # ------------------------------------------------------------------ indexado

    def indexar(self, ruta: Path | str, nombre: str = "") -> tuple[Ubicacion, ResumenIndexado]:
        """Indexa en primer plano. Lo usa la CLI."""
        return indexador.indexar_carpeta(self.bd, ruta, nombre=nombre)

    def indexar_en_segundo_plano(self, ruta: Path | str, nombre: str = "") -> Tarea:
        """Indexa en un hilo, con progreso consultable. Lo usa la web."""
        ubicacion = self.agregar_ubicacion(ruta, nombre)

        def trabajo(tarea: Tarea) -> dict:
            tarea.informar(f"Examinando {ubicacion.nombre}...")
            resumen = indexador.indexar_ubicacion(
                self.bd, ubicacion,
                cancelado=lambda: tarea.cancelada,
                progreso=lambda n, actual: _informar_indexado(tarea, n, actual),
            )
            tarea.informar(str(resumen))
            return {
                "ubicacion": ubicacion.nombre,
                "ubicacion_id": ubicacion.id,
                "nuevas": resumen.peliculas_nuevas,
                "actualizadas": resumen.peliculas_actualizadas,
                "eliminadas": resumen.peliculas_eliminadas,
                "carpetas": resumen.carpetas_examinadas,
                "texto": str(resumen),
            }

        return registro_tareas.lanzar(
            TIPO_TAREA_INDEXADO, f"Indexando {ubicacion.nombre}", trabajo
        )

    def reindexar_en_segundo_plano(self) -> Tarea:
        def trabajo(tarea: Tarea) -> dict:
            tarea.informar("Revisando todas las ubicaciones...")
            resultados = indexador.reindexar_todo(
                self.bd,
                cancelado=lambda: tarea.cancelada,
                progreso=lambda n, actual: _informar_indexado(tarea, n, actual),
            )
            for nombre, resumen in resultados.items():
                tarea.anotar(f"{nombre}: {resumen}")
            total = sum(r.total for r in resultados.values())
            tarea.informar(f"{len(resultados)} ubicaciones revisadas, {total} peliculas.")
            return {"ubicaciones": len(resultados), "peliculas": total}

        return registro_tareas.lanzar(TIPO_TAREA_INDEXADO, "Revisando las ubicaciones", trabajo)

    @staticmethod
    def tarea_indexado() -> Tarea | None:
        return registro_tareas.ultima_de_tipo(TIPO_TAREA_INDEXADO)

    @staticmethod
    def detener_indexado() -> bool:
        return registro_tareas.cancelar_tipo(TIPO_TAREA_INDEXADO)


def _informar_indexado(tarea: Tarea, examinadas: int, actual: str) -> None:
    """Traduce el progreso del escaner a la barra de la pagina.

    No se sabe cuantas carpetas hay hasta terminar de recorrer, asi que el total
    se va corrigiendo hacia arriba: la barra avanza sin saltar hacia atras.
    """
    tarea.fijar_total(max(tarea.total, examinadas))
    with tarea._candado:
        tarea.hechos = examinadas
        tarea.mensaje = (f"Examinando {actual}..." if actual
                         else f"{examinadas} carpetas examinadas.")
