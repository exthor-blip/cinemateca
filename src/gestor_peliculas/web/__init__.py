"""Fabrica de la aplicacion Flask.

Esta capa SOLO hace interfaz: recibe la peticion, llama a un servicio y
renderiza. No consulta la base ni la red por su cuenta.

Decisiones de seguridad, porque esta aplicacion lanza procesos (VLC) y renombra
archivos del disco:
  - escucha unicamente en 127.0.0.1 (ver cli/servir.py),
  - todos los POST llevan token CSRF (Flask-WTF),
  - la clave de sesion se genera y se guarda en la carpeta de datos, para que
    las sesiones no se invaliden en cada arranque.
"""

from __future__ import annotations

import secrets
from pathlib import Path

from flask import Flask, g, render_template
from flask_wtf.csrf import CSRFProtect

from .. import registro
from ..almacenamiento.bd import BaseDatos
from ..config import Ajustes, cargar_ajustes
from ..errores import ErrorDominio
from . import filtros_jinja

log = registro.obtener(__name__)
csrf = CSRFProtect()


def _clave_secreta(ajustes: Ajustes) -> str:
    """Clave de sesion estable, guardada junto a los datos.

    No va al .env porque no es algo que la persona tenga que elegir ni copiar:
    se genera la primera vez y se reutiliza.
    """
    if ajustes.clave_secreta:
        return ajustes.clave_secreta
    archivo = ajustes.carpeta_datos / "clave_sesion.txt"
    try:
        if archivo.exists():
            guardada = archivo.read_text(encoding="utf-8").strip()
            if guardada:
                return guardada
        nueva = secrets.token_hex(32)
        archivo.write_text(nueva, encoding="utf-8")
        return nueva
    except OSError:
        log.warning("No se pudo guardar la clave de sesion; se usa una temporal")
        return secrets.token_hex(32)


def obtener_bd() -> BaseDatos:
    """La base de esta peticion. Se abre una vez por peticion y se cierra al final."""
    if "bd" not in g:
        from flask import current_app

        g.bd = BaseDatos(current_app.config["RUTA_BD"])
    return g.bd


def crear_app(ajustes: Ajustes | None = None, *, ruta_bd: Path | str | None = None) -> Flask:
    """Arma la aplicacion. `ruta_bd` permite apuntarla a una base de prueba."""
    ajustes = ajustes or cargar_ajustes()
    registro.configurar(ajustes.carpeta_registros)

    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.update(
        AJUSTES=ajustes,
        RUTA_BD=Path(ruta_bd) if ruta_bd else ajustes.ruta_bd,
        SECRET_KEY=_clave_secreta(ajustes),
        POR_PAGINA=ajustes.por_pagina,
        MAX_CONTENT_LENGTH=4 * 1024 * 1024,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_HTTPONLY=True,
        JSON_AS_ASCII=False,
        # Siempre activo: es una aplicacion local de una sola persona, el costo
        # de comprobar la fecha de la plantilla es nulo, y permite retocar una
        # plantilla sin tener que reiniciar el servidor.
        TEMPLATES_AUTO_RELOAD=True,
    )

    csrf.init_app(app)
    filtros_jinja.registrar(app)

    from .rutas import catalogo, medios, metadatos, organizador, peliculas, reproduccion, ubicaciones
    from .rutas import tareas as rutas_tareas

    app.register_blueprint(catalogo.bp)
    app.register_blueprint(peliculas.bp)
    app.register_blueprint(ubicaciones.bp)
    app.register_blueprint(metadatos.bp)
    app.register_blueprint(reproduccion.bp)
    app.register_blueprint(organizador.bp)
    app.register_blueprint(medios.bp)
    app.register_blueprint(rutas_tareas.bp)

    @app.teardown_appcontext
    def _cerrar_bd(_excepcion: BaseException | None) -> None:
        base = g.pop("bd", None)
        if base is not None:
            base.cerrar()

    @app.context_processor
    def _contexto() -> dict:
        from .. import __version__

        return {
            "version": __version__,
            "hay_credencial_tmdb": ajustes.tiene_credencial_tmdb,
        }

    @app.errorhandler(ErrorDominio)
    def _error_dominio(error: ErrorDominio):
        log.info("Error de dominio: %s", error)
        return render_template("error.html", mensaje=str(error), codigo=400), 400

    @app.errorhandler(404)
    def _no_encontrado(_error):
        return render_template(
            "error.html", mensaje="No encontramos esa pagina.", codigo=404
        ), 404

    @app.errorhandler(500)
    def _error_interno(error):
        log.error("Error interno: %s", error)
        return render_template(
            "error.html",
            mensaje="Hubo un error inesperado. El detalle quedo en el archivo de registro.",
            codigo=500,
        ), 500

    log.info("Aplicacion lista. Base de datos en %s", app.config["RUTA_BD"])
    return app
