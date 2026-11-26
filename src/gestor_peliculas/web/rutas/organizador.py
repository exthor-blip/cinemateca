"""Pantalla del organizador de archivos (lo que era Organizador_Peliculas.ps1)."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, url_for

from ...errores import ErrorDominio
from ...servicios.servicio_organizador import ServicioOrganizador
from .. import obtener_bd

bp = Blueprint("organizador", __name__, url_prefix="/organizador")


def servicio() -> ServicioOrganizador:
    return ServicioOrganizador(obtener_bd(), current_app.config["AJUSTES"])


@bp.get("/")
def index():
    org = servicio()
    ruta = (request.args.get("ruta") or "").strip()
    analisis = org.ultimo_analisis()

    if ruta and (analisis is None or str(analisis.raiz) != ruta):
        try:
            analisis = org.analizar(ruta)
        except ErrorDominio as error:
            return render_template(
                "organizador/index.html", ubicaciones=org.ubicaciones(),
                analisis=None, ruta=ruta, aviso=str(error), tarea=org.tarea_actual(),
            )

    return render_template(
        "organizador/index.html",
        ubicaciones=org.ubicaciones(),
        analisis=analisis,
        ruta=ruta or (str(analisis.raiz) if analisis else ""),
        aviso="",
        tarea=org.tarea_actual(),
    )


@bp.post("/analizar")
def analizar():
    ruta = (request.form.get("ruta") or "").strip()
    return redirect(url_for("organizador.index", ruta=ruta))


@bp.post("/renombrar-pares")
def renombrar_pares():
    simular = request.form.get("confirmar") != "si"
    tarea = servicio().renombrar_pares_en_segundo_plano(
        (request.form.get("ruta") or "").strip(), simular=simular
    )
    return redirect(url_for("organizador.index", ruta=request.form.get("ruta"), tarea=tarea.id))


@bp.post("/renombrar-sueltos")
def renombrar_sueltos():
    simular = request.form.get("confirmar") != "si"
    tarea = servicio().renombrar_sueltos_en_segundo_plano(
        (request.form.get("ruta") or "").strip(), simular=simular
    )
    return redirect(url_for("organizador.index", ruta=request.form.get("ruta"), tarea=tarea.id))


@bp.post("/minusculas")
def minusculas():
    simular = request.form.get("confirmar") != "si"
    tarea = servicio().minusculas_en_segundo_plano(
        (request.form.get("ruta") or "").strip(), simular=simular
    )
    return redirect(url_for("organizador.index", ruta=request.form.get("ruta"), tarea=tarea.id))


@bp.post("/limpiar")
def limpiar():
    simular = request.form.get("confirmar") != "si"
    tarea = servicio().limpiar_en_segundo_plano(
        (request.form.get("ruta") or "").strip(),
        request.form.getlist("extension"),
        simular=simular,
    )
    return redirect(url_for("organizador.index", ruta=request.form.get("ruta"), tarea=tarea.id))


@bp.post("/detener")
def detener():
    servicio().detener()
    return redirect(url_for("organizador.index", ruta=request.form.get("ruta")))


@bp.get("/informes")
def informes():
    return jsonify(servicio().informes_disponibles())
