"""Comando importar-puntajes: carga title.ratings.tsv.gz de IMDb."""

from __future__ import annotations

import argparse

from .. import puntajes
from ..almacenamiento.bd import BaseDatos
from ..config import cargar_ajustes


def registrar(comandos) -> None:
    orden = comandos.add_parser("importar-puntajes",
                                help="carga el archivo title.ratings.tsv.gz de IMDb")
    orden.add_argument("archivo", nargs="?",
                       help="ruta al title.ratings.tsv.gz (o .tsv sin comprimir)")
    orden.add_argument("--descargar", action="store_true",
                       help="lo descarga de datasets.imdbws.com en lugar de leer un archivo")
    orden.add_argument("--solo-del-catalogo", action="store_true",
                       help="guarda solo los puntajes de las peliculas que ya estan en el indice")
    orden.set_defaults(funcion=ejecutar)


def ejecutar(argumentos: argparse.Namespace) -> int:
    ajustes = cargar_ajustes()

    if not argumentos.archivo and not argumentos.descargar:
        print("Hay que indicar el archivo, o usar --descargar.")
        print()
        print("El archivo oficial es title.ratings.tsv.gz y se baja de:")
        print("  https://datasets.imdbws.com/title.ratings.tsv.gz")
        print("Condiciones de uso: https://developer.imdb.com/non-commercial-datasets/")
        return 1

    with BaseDatos(ajustes.ruta_bd) as bd:
        if argumentos.descargar:
            print("Descargando title.ratings.tsv.gz de datasets.imdbws.com...")
            origen = puntajes.descargar(ajustes.carpeta_datos)
            print(f"  Guardado en {origen}")
        else:
            origen = argumentos.archivo

        filtro = bd.peliculas.ids_con_imdb() if argumentos.solo_del_catalogo else None
        if filtro is not None:
            print(f"Se guardaran solo los puntajes de las {len(filtro)} peliculas del indice.")

        resultado = puntajes.importar(bd, origen, solo_estos=filtro, progreso=_mostrar)
        print()
        print(resultado)
        print(f"Puntajes en la base: {bd.puntajes.contar()}")
    return 0


def _mostrar(leidas: int, guardadas: int) -> None:
    print(f"\r  {leidas:>9} filas leidas, {guardadas:>8} guardadas", end="", flush=True)
