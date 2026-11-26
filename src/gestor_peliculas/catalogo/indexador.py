"""Orquesta el escaneo del disco hacia la base de datos.

Es el unico lugar que decide que se da de alta, que se actualiza y que se da de
baja. Un re-indexado es idempotente: volver a correrlo sobre la misma carpeta
no duplica nada y no pierde lo que ya se sabia (identificador IMDb, ficha de
TMDb, poster), porque la verdad durable esta en disco y la base solo la refleja.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .. import registro
from ..almacenamiento.bd import BaseDatos
from ..errores import ErrorDominio
from ..modelos import ResumenIndexado, Ubicacion
from . import escaner

log = registro.obtener(__name__)


def indexar_ubicacion(bd: BaseDatos, ubicacion: Ubicacion, *,
                      cancelado: Callable[[], bool] | None = None,
                      progreso: Callable[[int, str], None] | None = None,
                      dar_de_baja_ausentes: bool = True) -> ResumenIndexado:
    """Escanea una ubicacion y sincroniza la base con lo que hay en el disco.

    Args:
        bd: base abierta.
        ubicacion: la ubicacion a escanear, ya dada de alta.
        cancelado: funcion que devuelve True para parar; lo escrito hasta ese
            momento se conserva.
        progreso: recibe (carpetas_examinadas, nombre_actual).
        dar_de_baja_ausentes: si True, las peliculas que ya no estan en el disco
            se quitan del indice. Se pasa False cuando la carpeta puede estar
            parcialmente accesible, para no vaciar el catalogo por un disco
            desconectado.

    Returns:
        ResumenIndexado con los conteos.
    """
    if ubicacion.id is None:
        raise ErrorDominio("La ubicacion tiene que estar dada de alta antes de indexarla.")
    if not ubicacion.ruta.is_dir():
        raise ErrorDominio(f"La carpeta {ubicacion.ruta} no esta disponible.")

    resumen = ResumenIndexado()
    # La identidad es (carpeta, archivo de video): una carpeta de saga tiene
    # varias peliculas.
    vistas: set[tuple[str, str]] = set()
    conocidas = {
        (p.ruta_relativa, p.archivo_video): p
        for p in bd.peliculas.listar_por_ubicacion(ubicacion.id)
    }
    carpetas = 0

    def informar(examinadas: int, nombre: str) -> None:
        nonlocal carpetas
        carpetas = max(carpetas, examinadas)
        if progreso:
            progreso(examinadas, nombre)

    for encontrada in escaner.escanear(
        ubicacion.ruta, nombre_ubicacion=ubicacion.nombre,
        cancelado=cancelado, progreso=informar,
    ):
        if cancelado and cancelado():
            log.info("Indexado de %s cancelado por la persona", ubicacion.nombre)
            break

        vistas.add((encontrada.ruta_relativa, encontrada.archivo_video))
        _, era_nueva = bd.peliculas.alta_o_actualizacion(
            ubicacion.id,
            encontrada.ruta_relativa,
            archivo_video=encontrada.archivo_video,
            titulo_carpeta=encontrada.titulo,
            anio_carpeta=encontrada.anio,
            imdb_id=encontrada.imdb_id,
            poster_relativo=encontrada.poster,
            tamanio_bytes=encontrada.tamanio_bytes,
        )
        if era_nueva:
            resumen.peliculas_nuevas += 1
        else:
            resumen.peliculas_actualizadas += 1
        if encontrada.varios_videos:
            resumen.en_carpeta_compartida += 1

    bd.conexion.commit()

    if dar_de_baja_ausentes and not (cancelado and cancelado()):
        ausentes = [p.id for clave, p in conocidas.items() if clave not in vistas and p.id]
        if ausentes:
            resumen.peliculas_eliminadas = bd.peliculas.baja_varias(ausentes)
            log.info("Se dieron de baja %s peliculas que ya no estan en el disco", len(ausentes))

    resumen.carpetas_examinadas = carpetas or escaner.contar_carpetas(ubicacion.ruta)
    bd.ubicaciones.marcar_escaneo(ubicacion.id)
    bd.metadatos.limpiar_etiquetas_huerfanas()
    log.info("Indexado de %s: %s", ubicacion.nombre, resumen)
    return resumen


def indexar_carpeta(bd: BaseDatos, ruta: Path | str, *, nombre: str = "",
                    cancelado: Callable[[], bool] | None = None,
                    progreso: Callable[[int, str], None] | None = None) -> tuple[Ubicacion, ResumenIndexado]:
    """Da de alta la carpeta como ubicacion si hace falta, y la indexa."""
    carpeta = Path(ruta).expanduser()
    if not carpeta.is_dir():
        raise ErrorDominio(f"No existe la carpeta {carpeta}.")

    ubicacion = bd.ubicaciones.alta(carpeta, nombre)
    resumen = indexar_ubicacion(bd, ubicacion, cancelado=cancelado, progreso=progreso)
    actualizada = bd.ubicaciones.obtener(ubicacion.id) or ubicacion
    return actualizada, resumen


def reindexar_todo(bd: BaseDatos, *, cancelado: Callable[[], bool] | None = None,
                   progreso: Callable[[int, str], None] | None = None) -> dict[str, ResumenIndexado]:
    """Re-indexa todas las ubicaciones disponibles.

    Una ubicacion cuyo disco no esta conectado se saltea con un aviso, en lugar
    de dar de baja todas sus peliculas.
    """
    resultados: dict[str, ResumenIndexado] = {}
    for ubicacion in bd.ubicaciones.listar():
        if cancelado and cancelado():
            break
        if not ubicacion.existe:
            log.warning("Se saltea %s: la carpeta %s no esta disponible",
                        ubicacion.nombre, ubicacion.ruta)
            continue
        resultados[ubicacion.nombre] = indexar_ubicacion(
            bd, ubicacion, cancelado=cancelado, progreso=progreso
        )
    return resultados
