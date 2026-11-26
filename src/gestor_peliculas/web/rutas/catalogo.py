"""La pantalla principal: grilla, filtros, busqueda y paginacion."""

from __future__ import annotations

from flask import Blueprint, current_app, redirect, render_template, request, url_for

from ...busqueda.filtros import EstadoFicha, FiltroBusqueda, Orden
from ...servicios.servicio_catalogo import ServicioCatalogo
from .. import obtener_bd

bp = Blueprint("catalogo", __name__)


def servicio() -> ServicioCatalogo:
    return ServicioCatalogo(obtener_bd())


@bp.get("/")
def index():
    cat = servicio()
    filtro = FiltroBusqueda.desde_parametros(
        request.args.get, por_pagina=current_app.config["POR_PAGINA"]
    )
    pagina = cat.buscar(filtro)

    return render_template(
        "catalogo/index.html",
        filtro=filtro,
        pagina=pagina,
        facetas=cat.facetas(),
        resumen=cat.resumen(visibles=pagina.total),
        ordenes=list(Orden),
        estados_ficha=list(EstadoFicha),
        tarea_indexado=cat.tarea_indexado(),
        tarea_metadatos=_tarea_metadatos(),
    )


def _tarea_metadatos():
    from ...servicios.servicio_metadatos import ServicioMetadatos

    return ServicioMetadatos.tarea_actual()


@bp.post("/indice/vaciar")
def vaciar():
    """Vacia el indice. Los archivos del disco no se tocan."""
    servicio().vaciar_indice()
    return redirect(url_for("catalogo.index"))
