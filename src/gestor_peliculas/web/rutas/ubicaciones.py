"""Ubicaciones y el explorador de carpetas del servidor.

Por que hay un explorador propio: showDirectoryPicker() del navegador solo
servia porque en la version original el navegador ERA la aplicacion. Con un
backend, la carpeta que hay que elegir esta en el disco del servidor, y ningun
navegador le pasa una ruta local a una pagina. Asi que el servidor lista sus
propias carpetas y la persona navega por ellas, o pega la ruta a mano.

Es tambien mas robusto que la version anterior: no hay permisos de archivo que
se pierdan entre sesiones, que era la advertencia de la nota al pie del HTML.
"""

from __future__ import annotations

import os
import string
import sys
from pathlib import Path

from flask import Blueprint, jsonify, redirect, render_template, request, url_for

from ...errores import ErrorDominio
from ...servicios.servicio_catalogo import ServicioCatalogo
from .. import obtener_bd

bp = Blueprint("ubicaciones", __name__, url_prefix="/ubicaciones")

#: Carpetas que no se ofrecen al navegar: ruido o cosas del sistema.
OCULTAS = frozenset({"$recycle.bin", "system volume information", "windows",
                     "program files", "program files (x86)", "programdata",
                     "appdata", "$windows.~ws", "recovery", "perflogs"})


def servicio() -> ServicioCatalogo:
    return ServicioCatalogo(obtener_bd())


@bp.get("/")
def index():
    cat = servicio()
    return render_template(
        "ubicaciones/index.html",
        ubicaciones=cat.ubicaciones(),
        resumen=cat.resumen(),
        tarea=cat.tarea_indexado(),
    )


@bp.post("/agregar")
def agregar():
    """Da de alta una carpeta y la indexa en segundo plano."""
    ruta = (request.form.get("ruta") or "").strip()
    nombre = (request.form.get("nombre") or "").strip()
    tarea = servicio().indexar_en_segundo_plano(ruta, nombre)
    return redirect(url_for("ubicaciones.index", tarea=tarea.id))


@bp.post("/<int:ubicacion_id>/quitar")
def quitar(ubicacion_id: int):
    """Quita la ubicacion del indice. No borra nada del disco."""
    servicio().quitar_ubicacion(ubicacion_id)
    return redirect(url_for("ubicaciones.index"))


@bp.post("/<int:ubicacion_id>/renombrar")
def renombrar(ubicacion_id: int):
    nombre = (request.form.get("nombre") or "").strip()
    if not nombre:
        raise ErrorDominio("El nombre no puede quedar vacio.")
    obtener_bd().ubicaciones.renombrar(ubicacion_id, nombre)
    return redirect(url_for("ubicaciones.index"))


@bp.post("/reindexar")
def reindexar():
    tarea = servicio().reindexar_en_segundo_plano()
    return redirect(url_for("ubicaciones.index", tarea=tarea.id))


@bp.post("/detener")
def detener():
    servicio().detener_indexado()
    return redirect(url_for("ubicaciones.index"))


# ----------------------------------------------------- explorador de carpetas


def _unidades() -> list[dict]:
    """Unidades disponibles en Windows; en otros sistemas, la raiz y el hogar."""
    if sys.platform != "win32":
        return [{"nombre": "/", "ruta": "/"}, {"nombre": "Carpeta personal", "ruta": str(Path.home())}]
    encontradas = []
    for letra in string.ascii_uppercase:
        unidad = f"{letra}:\\"
        if os.path.exists(unidad):
            encontradas.append({"nombre": unidad, "ruta": unidad})
    return encontradas


def _subcarpetas(carpeta: Path) -> list[dict]:
    hijas = []
    try:
        with os.scandir(carpeta) as entradas:
            for entrada in entradas:
                try:
                    if not entrada.is_dir(follow_symlinks=False):
                        continue
                except OSError:
                    continue
                if entrada.name.startswith(".") or entrada.name.lower() in OCULTAS:
                    continue
                hijas.append({"nombre": entrada.name, "ruta": entrada.path})
    except (OSError, PermissionError):
        return []
    return sorted(hijas, key=lambda h: h["nombre"].lower())


@bp.get("/explorar")
def explorar():
    """Lista las subcarpetas de una ruta, para el modal de seleccion.

    Solo lista carpetas y nunca devuelve contenido de archivos, asi que no
    expone datos: es el equivalente de abrir el dialogo de Windows.
    """
    pedida = (request.args.get("ruta") or "").strip()

    if not pedida:
        hogar = Path.home()
        return jsonify({
            "ruta": "",
            "titulo": "Elegi una unidad o carpeta",
            "padre": None,
            "atajos": [
                {"nombre": "Carpeta personal", "ruta": str(hogar)},
                *[{"nombre": n, "ruta": str(hogar / n)}
                  for n in ("Videos", "Peliculas", "Movies", "Downloads", "Descargas")
                  if (hogar / n).is_dir()],
            ],
            "unidades": _unidades(),
            "carpetas": [],
        })

    carpeta = Path(pedida).expanduser()
    if not carpeta.is_dir():
        return jsonify({"error": f"La carpeta {carpeta} no esta disponible."}), 404

    try:
        carpeta = carpeta.resolve()
    except OSError:
        return jsonify({"error": "No se pudo abrir esa carpeta."}), 400

    padre = str(carpeta.parent) if carpeta.parent != carpeta else None
    return jsonify({
        "ruta": str(carpeta),
        "titulo": carpeta.name or str(carpeta),
        "padre": padre,
        "atajos": [],
        "unidades": [],
        "carpetas": _subcarpetas(carpeta),
    })
