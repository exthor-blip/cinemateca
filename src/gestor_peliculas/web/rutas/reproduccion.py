"""Abrir el video en VLC o mostrar su carpeta en el Explorador."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify

from ...errores import ErrorDominio
from ...servicios.servicio_reproduccion import ServicioReproduccion
from .. import obtener_bd

bp = Blueprint("reproduccion", __name__, url_prefix="/peliculas")


def servicio() -> ServicioReproduccion:
    return ServicioReproduccion(obtener_bd(), current_app.config["AJUSTES"])


@bp.post("/<int:pelicula_id>/reproducir")
def reproducir(pelicula_id: int):
    try:
        ruta = servicio().reproducir(pelicula_id)
    except ErrorDominio as error:
        return jsonify({"ok": False, "mensaje": str(error)}), 400
    return jsonify({"ok": True, "mensaje": f"Abriendo en VLC: {ruta.name}"})


@bp.post("/<int:pelicula_id>/carpeta")
def abrir_carpeta(pelicula_id: int):
    try:
        carpeta = servicio().abrir_carpeta(pelicula_id)
    except ErrorDominio as error:
        return jsonify({"ok": False, "mensaje": str(error)}), 400
    return jsonify({"ok": True, "mensaje": f"Carpeta abierta: {carpeta.name}"})


@bp.get("/vlc/estado")
def estado_vlc():
    disponible, ruta = servicio().estado_vlc()
    return jsonify({"disponible": disponible, "ruta": ruta})
