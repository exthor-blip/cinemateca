"""Lote de metadatos: lanzarlo, consultarlo y detenerlo."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, redirect, request, url_for

from ...errores import ErrorDominio
from ...servicios.servicio_metadatos import ServicioMetadatos
from .. import obtener_bd

bp = Blueprint("metadatos", __name__, url_prefix="/metadatos")


def servicio() -> ServicioMetadatos:
    return ServicioMetadatos(obtener_bd(), current_app.config["AJUSTES"])


@bp.post("/completar")
def completar():
    """Arranca el lote en segundo plano y vuelve al catalogo."""
    met = servicio()
    try:
        limite = int(request.form.get("limite") or 0) or None
    except ValueError:
        limite = None
    tarea = met.completar_lote_en_segundo_plano(limite)
    destino = request.form.get("volver") or url_for("catalogo.index")
    separador = "&" if "?" in destino else "?"
    return redirect(f"{destino}{separador}tarea={tarea.id}")


@bp.post("/detener")
def detener():
    ServicioMetadatos.detener()
    return redirect(request.form.get("volver") or url_for("catalogo.index"))


@bp.get("/pendientes")
def pendientes():
    """Cuantas peliculas vale la pena consultar, y por que motivo."""
    met = servicio()
    sin_credencial = not current_app.config["AJUSTES"].tiene_credencial_tmdb
    listas = met.pendientes()
    con_imdb = sum(1 for p in listas if p.imdb_id)
    return jsonify({
        "total": len(listas),
        "con_imdb": con_imdb,
        "por_titulo": len(listas) - con_imdb,
        "falta_credencial": sin_credencial,
    })


@bp.get("/credencial")
def credencial():
    """Comprueba que la clave de TMDb sirva, para avisar temprano."""
    met = servicio()
    try:
        met.exigir_credencial()
    except ErrorDominio as error:
        return jsonify({"valida": False, "mensaje": str(error)}), 200

    from ...metadatos.cliente_tmdb import ClienteTmdb

    ajustes = current_app.config["AJUSTES"]
    try:
        ClienteTmdb(ajustes.credencial_tmdb, idioma=ajustes.idioma_tmdb).verificar_credencial()
    except ErrorDominio as error:
        return jsonify({"valida": False, "mensaje": str(error)}), 200
    return jsonify({"valida": True, "mensaje": "La clave de TMDb funciona."})
