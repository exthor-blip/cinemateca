"""Comando servir: levanta la aplicacion web local."""

from __future__ import annotations

import argparse
import threading
import webbrowser

from ..config import cargar_ajustes


def registrar(comandos) -> None:
    orden = comandos.add_parser("servir", help="levanta la aplicacion web local")
    orden.add_argument("--puerto", type=int, default=None, help="puerto (por defecto 5000)")
    orden.add_argument("--abrir-navegador", action="store_true",
                       help="abre el navegador al arrancar")
    orden.add_argument("--desarrollo", action="store_true",
                       help="usa el servidor de desarrollo de Flask, con recarga automatica")
    orden.set_defaults(funcion=ejecutar)


def ejecutar(argumentos: argparse.Namespace) -> int:
    from ..web import crear_app

    ajustes = cargar_ajustes()
    puerto = argumentos.puerto or ajustes.puerto
    direccion = f"http://127.0.0.1:{puerto}/"
    app = crear_app(ajustes)

    print("Mi Cinemateca")
    print(f"  Abrila en:      {direccion}")
    print(f"  Base de datos:  {ajustes.ruta_bd}")
    print(f"  Clave de TMDb:  {'cargada' if ajustes.tiene_credencial_tmdb else 'falta (.env)'}")
    print("  Para cerrar:    Ctrl+C")
    print()

    if argumentos.abrir_navegador:
        threading.Timer(1.2, lambda: webbrowser.open(direccion)).start()

    # Solo 127.0.0.1: la aplicacion lanza procesos y renombra archivos, asi que
    # no puede quedar accesible desde la red local.
    if argumentos.desarrollo:
        app.run(host="127.0.0.1", port=puerto, debug=True, use_reloader=True)
    else:
        from waitress import serve

        serve(app, host="127.0.0.1", port=puerto, threads=6, ident="Mi Cinemateca")
    return 0
