"""Ficha de una pelicula y pantalla de revision manual."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, url_for

from ...errores import ErrorDominio, RequiereRevision
from ...nucleo.coincidencias import ordenar_para_revision
from ...servicios.servicio_catalogo import ServicioCatalogo
from ...servicios.servicio_metadatos import ServicioMetadatos
from ...servicios.servicio_reproduccion import ServicioReproduccion
from .. import obtener_bd

bp = Blueprint("peliculas", __name__, url_prefix="/peliculas")


def catalogo() -> ServicioCatalogo:
    return ServicioCatalogo(obtener_bd())


def metadatos() -> ServicioMetadatos:
    return ServicioMetadatos(obtener_bd(), current_app.config["AJUSTES"])


@bp.get("/<int:pelicula_id>")
def ficha(pelicula_id: int):
    cat = catalogo()
    pelicula = cat.obtener_o_fallar(pelicula_id)
    disponible, _ruta = ServicioReproduccion(
        obtener_bd(), current_app.config["AJUSTES"]
    ).estado_vlc()

    return render_template(
        "peliculas/ficha.html",
        pelicula=pelicula,
        copias=cat.copias_de(pelicula),
        revision=obtener_bd().peliculas.estado_revision(pelicula_id),
        vlc_disponible=disponible,
    )


@bp.get("/<int:pelicula_id>/revisar")
def revisar(pelicula_id: int):
    """Pantalla para elegir la ficha correcta a mano."""
    cat = catalogo()
    pelicula = cat.obtener_o_fallar(pelicula_id)
    estado = obtener_bd().peliculas.estado_revision(pelicula_id)
    consulta = (request.args.get("q") or "").strip()

    candidatos: list = []
    aviso = ""
    if consulta and current_app.config["AJUSTES"].tiene_credencial_tmdb:
        try:
            encontrados = metadatos().buscar_candidatos(pelicula_id, consulta)
            candidatos = ordenar_para_revision(
                encontrados, pelicula.titulo_carpeta, pelicula.anio_carpeta,
                rechazados=set(estado.get("rechazados", [])),
            )
            if not candidatos:
                aviso = "No hubo resultados. Se puede probar otro titulo o pegar el enlace de IMDb."
        except ErrorDominio as error:
            aviso = str(error)
    elif consulta:
        aviso = ("Para buscar en TMDb hace falta la clave en el archivo .env. "
                 "Si ya tenes el enlace de IMDb, se puede pegar abajo y vincularlo.")

    return render_template(
        "peliculas/revision.html",
        pelicula=pelicula,
        revision=estado,
        consulta=consulta or pelicula.titulo_carpeta,
        candidatos=candidatos,
        aviso=aviso,
    )


@bp.post("/<int:pelicula_id>/completar")
def completar(pelicula_id: int):
    """Consulta TMDb para esta sola pelicula."""
    try:
        metadatos().completar_una(pelicula_id)
        return jsonify({"ok": True, "mensaje": "Ficha guardada."})
    except RequiereRevision as revision:
        return jsonify({
            "ok": False, "revisar": True, "mensaje": str(revision),
            "url": url_for("peliculas.revisar", pelicula_id=pelicula_id),
        }), 409
    except ErrorDominio as error:
        return jsonify({"ok": False, "mensaje": str(error)}), 400


@bp.post("/<int:pelicula_id>/guardar-candidato")
def guardar_candidato(pelicula_id: int):
    """Guarda la ficha que la persona confirmo."""
    try:
        tmdb_id = int(request.form.get("tmdb_id") or 0)
    except ValueError:
        raise ErrorDominio("El identificador de TMDb no es valido.") from None
    if tmdb_id <= 0:
        raise ErrorDominio("Falta el identificador de TMDb de la ficha elegida.")

    metadatos().guardar_candidato(
        pelicula_id, tmdb_id, (request.form.get("imdb_id") or "").strip()
    )
    return redirect(url_for("peliculas.ficha", pelicula_id=pelicula_id))


@bp.post("/<int:pelicula_id>/vincular")
def vincular(pelicula_id: int):
    """Guarda solo el enlace de IMDb, sin consultar TMDb."""
    metadatos().vincular_imdb(pelicula_id, request.form.get("enlace") or "")
    return redirect(url_for("peliculas.ficha", pelicula_id=pelicula_id))


@bp.post("/<int:pelicula_id>/rechazar")
def rechazar(pelicula_id: int):
    """Descarta un candidato para que no se vuelva a ofrecer."""
    metadatos().rechazar(pelicula_id, request.form.get("imdb_id") or "")
    return redirect(url_for("peliculas.revisar", pelicula_id=pelicula_id,
                            q=request.form.get("q") or ""))


@bp.post("/<int:pelicula_id>/quitar-ficha")
def quitar_ficha(pelicula_id: int):
    metadatos().quitar_ficha(pelicula_id)
    return redirect(url_for("peliculas.ficha", pelicula_id=pelicula_id))
