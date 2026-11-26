"""Punto de entrada de la consola: python -m gestor_peliculas.cli <comando>

Los scripts dejan de ser archivos sueltos y pasan a ser comandos de un modulo
dentro del codigo fuente, que es lo que pedia la reestructuracion. Cada comando
usa los mismos servicios que la web, asi que no hay logica duplicada: la
consola y la pagina hacen exactamente lo mismo.

Comandos:
  servir               Levanta la aplicacion web local.
  indexar              Agrega una carpeta al catalogo y la indexa.
  enriquecer           Completa las fichas pendientes consultando TMDb.
  organizar            Analiza y organiza los archivos de una coleccion.
  vincular             Busca el identificador IMDb de cada carpeta.
  importar-puntajes    Carga title.ratings.tsv.gz de IMDb.
  importar-estado      Lee un .imdb_linker_estado.json del linker original.
  estado               Muestra un resumen del catalogo.
"""

from __future__ import annotations

import argparse
import logging
import sys

from .. import __version__, registro
from ..config import cargar_ajustes
from ..errores import ErrorDominio


def construir_analizador() -> argparse.ArgumentParser:
    analizador = argparse.ArgumentParser(
        prog="gestor-peliculas",
        description="Catalogo, organizacion y reproduccion de una coleccion local de peliculas.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    analizador.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    analizador.add_argument("-v", "--detallado", action="store_true",
                            help="muestra mas informacion de lo que va haciendo")

    comandos = analizador.add_subparsers(dest="comando", metavar="<comando>")

    from . import (
        enriquecer,
        importar_estado,
        importar_puntajes,
        indexar,
        organizar,
        servir,
        vincular,
    )

    for modulo in (servir, indexar, enriquecer, organizar, vincular,
                   importar_puntajes, importar_estado):
        modulo.registrar(comandos)

    estado = comandos.add_parser("estado", help="resumen del catalogo")
    estado.set_defaults(funcion=_estado)

    return analizador


def _estado(argumentos: argparse.Namespace) -> int:
    from ..almacenamiento.bd import BaseDatos
    from ..servicios.servicio_catalogo import ServicioCatalogo

    ajustes = cargar_ajustes()
    with BaseDatos(ajustes.ruta_bd) as bd:
        servicio = ServicioCatalogo(bd)
        resumen = servicio.resumen()
        print(f"Base de datos:     {ajustes.ruta_bd}")
        print(f"Peliculas:         {resumen.total}")
        print(f"Con ficha:         {resumen.con_ficha}")
        print(f"Pendientes:        {resumen.pendientes}")
        print(f"Sin enlace IMDb:   {resumen.sin_imdb}")
        print(f"Con puntaje:       {resumen.con_puntaje}")
        print(f"Puntajes cargados: {bd.puntajes.contar()}")
        print(f"Clave de TMDb:     {'cargada' if ajustes.tiene_credencial_tmdb else 'FALTA'}")
        print()
        print("Ubicaciones:")
        for ubicacion in servicio.ubicaciones():
            disponible = "" if ubicacion.existe else "  [no conectada]"
            print(f"  {ubicacion.nombre:28} {ubicacion.cantidad_peliculas:>5} peliculas  "
                  f"{ubicacion.ruta}{disponible}")
        if not servicio.ubicaciones():
            print("  (ninguna todavia)")
    return 0


def main(argv: list[str] | None = None) -> int:
    analizador = construir_analizador()
    argumentos = analizador.parse_args(argv)

    ajustes = cargar_ajustes()
    registro.configurar(
        ajustes.carpeta_registros,
        nivel=logging.DEBUG if argumentos.detallado else logging.INFO,
    )

    if not getattr(argumentos, "funcion", None):
        analizador.print_help()
        return 1

    try:
        return argumentos.funcion(argumentos) or 0
    except ErrorDominio as error:
        print(f"\nError: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrumpido.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
