"""Sirve posteres y miniaturas desde el disco."""

from __future__ import annotations

from flask import Blueprint, abort, current_app, send_file

from ...metadatos import posters
from ...servicios.servicio_catalogo import ServicioCatalogo
from .. import obtener_bd

bp = Blueprint("medios", __name__)


@bp.get("/poster/<int:pelicula_id>")
def poster(pelicula_id: int):
    """Miniatura del poster de una pelicula.

    Devuelve 404 si no hay poster: la plantilla ya dibuja el marcador vacio,
    asi que no hace falta una imagen de relleno.
    """
    pelicula = ServicioCatalogo(obtener_bd()).obtener(pelicula_id)
    if pelicula is None:
        abort(404)

    original = pelicula.poster_absoluto
    if original is None or not original.is_file():
        abort(404)

    ajustes = current_app.config["AJUSTES"]
    miniatura = posters.miniatura(original, ajustes.carpeta_miniaturas)

    if miniatura is None:
        # Sin miniatura se sirve el original, salvo que sea enorme: mandar
        # 17 MB para una tarjeta de 160 px es peor que no mostrar nada, y la
        # plantilla ya dibuja el marcador de vacio ante un 404.
        try:
            if original.stat().st_size > posters.TAMANIO_MAXIMO_ORIGINAL:
                abort(404)
        except OSError:
            abort(404)

    # max_age largo: la miniatura cambia de nombre si cambia el archivo de
    # origen, asi que el navegador puede cachearla sin riesgo de ver una vieja.
    return send_file(miniatura or original, conditional=True, max_age=604800)


@bp.get("/poster/<int:pelicula_id>/original")
def poster_original(pelicula_id: int):
    """El poster sin redimensionar, para la ficha."""
    pelicula = ServicioCatalogo(obtener_bd()).obtener(pelicula_id)
    if pelicula is None:
        abort(404)
    original = pelicula.poster_absoluto
    if original is None or not original.is_file():
        abort(404)
    return send_file(original, conditional=True, max_age=86400)
